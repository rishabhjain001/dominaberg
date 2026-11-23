/* A.U.D.I.T. Mission Control - plain ES2020, no build step. */
(() => {
  'use strict';

  const MULTIPLIER = 8;
  const WS_RETRY_MS = 2000;
  const DETECTION_LIMIT = 200;
  const LOG_LIMIT = 120;
  const CREATE_DEBOUNCE_MS = 350;
  const DEFAULT_WORLD = { width_m: 240, height_m: 180, origin_lat: 0, origin_lon: 0 };

  const CLASS_LABELS = {
    pothole: 'Pothole',
    missing_cover: 'Missing cover',
    waterlogging: 'Waterlogging',
    debris: 'Debris',
    pavement_damage: 'Pavement damage',
  };

  const STATUS_TEXT = {
    idle: 'Idle',
    running: 'Running',
    paused: 'Paused',
    complete: 'Complete',
    reconnecting: 'Reconnecting',
  };

  const $ = (id) => document.getElementById(id);

  const dom = {
    pill: $('status-pill'),
    missionId: $('mission-id'),
    banner: $('error-banner'),
    bannerText: $('error-text'),
    bannerRetry: $('error-retry'),
    seed: $('seed'),
    altitude: $('altitude'),
    altitudeValue: $('altitude-value'),
    speed: $('speed'),
    speedValue: $('speed-value'),
    planLanes: $('plan-lanes'),
    planLength: $('plan-length'),
    launch: $('launch'),
    pause: $('pause'),
    reset: $('reset'),
    map: $('mission-map'),
    mapFrame: $('map-frame'),
    mapMeta: $('map-meta'),
    mapSkeleton: $('map-skeleton'),
    popover: $('pin-popover'),
    popoverCrop: $('popover-crop'),
    popoverClass: $('popover-class'),
    popoverId: $('popover-id'),
    popoverConfidence: $('popover-confidence'),
    popoverCoord: $('popover-coord'),
    popoverClose: $('popover-close'),
    metricCoverage: $('metric-coverage'),
    metricDistance: $('metric-distance'),
    metricBattery: $('metric-battery'),
    metricFrames: $('metric-frames'),
    metricUnique: $('metric-unique'),
    metricElapsed: $('metric-elapsed'),
    feedList: $('feed-list'),
    feedEmpty: $('feed-empty'),
    feedCount: $('feed-count'),
    logList: $('log-list'),
    scorecard: $('scorecard'),
    scorePrecision: $('score-precision'),
    scoreRecall: $('score-recall'),
    scoreF1: $('score-f1'),
    scoreError: $('score-error'),
    scoreClasses: $('score-classes'),
    exportCsv: $('export-csv'),
    exportGeo: $('export-geojson'),
    exportMd: $('export-md'),
  };

  const state = {
    scenario: null,
    world: null,
    roads: [],
    home: null,
    missionId: null,
    plan: null,
    status: 'idle',
    reconnecting: false,
    pose: null,
    telemetry: null,
    stats: null,
    flown: [],
    detections: [],
    selectedId: null,
    socket: null,
    retryTimer: null,
    loading: true,
    lastLogSecond: -1,
    createSeq: 0,
    createTimer: null,
    seedTouched: false,
    retryAction: null,
  };

  const mapView = { w: 0, h: 0, dpr: 1, scale: 1, ox: 0, oy: 0 };
  const context = dom.map.getContext('2d');
  let palette = {};
  let frameRequested = false;

  /* ---------- formatting ---------- */

  const DASH = '\u2014';

  function finite(value) {
    return typeof value === 'number' && Number.isFinite(value);
  }

  function toNumber(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function fmt1(value) {
    return finite(value) ? value.toFixed(1) : DASH;
  }

  function pct(value) {
    return finite(value) ? `${value.toFixed(1)}%` : DASH;
  }

  function ratio(value) {
    return finite(value) ? `${(value * 100).toFixed(1)}%` : DASH;
  }

  function intText(value) {
    return finite(value) ? String(Math.round(value)) : DASH;
  }

  function clock(seconds) {
    const total = Math.max(0, Math.floor(toNumber(seconds) || 0));
    const minutes = Math.floor(total / 60);
    const rest = total % 60;
    return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
  }

  function classLabel(key) {
    if (CLASS_LABELS[key]) return CLASS_LABELS[key];
    const text = String(key || 'unknown').replace(/_/g, ' ');
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function coordText(detection) {
    const lat = toNumber(detection.lat);
    const lon = toNumber(detection.lon);
    if (lat === null || lon === null) return 'coordinates unavailable';
    return `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
  }

  function confidencePct(value) {
    const confidence = toNumber(value);
    if (confidence === null) return null;
    return Math.max(0, Math.min(100, Math.round(confidence * 100)));
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function simNow() {
    return state.telemetry ? toNumber(state.telemetry.elapsed_s) || 0 : 0;
  }

  /* ---------- http ---------- */

  async function api(path, options) {
    const request = Object.assign({ method: 'GET' }, options);
    if (request.body) {
      request.headers = Object.assign({ 'Content-Type': 'application/json' }, request.headers);
    }
    const response = await fetch(path, request);
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`);
    }
    const type = response.headers.get('content-type') || '';
    return type.includes('application/json') ? response.json() : response.text();
  }

  /* ---------- error banner ---------- */

  function showError(message, retry) {
    dom.bannerText.textContent = message;
    dom.banner.hidden = false;
    dom.bannerRetry.hidden = !retry;
    state.retryAction = retry || null;
  }

  function hideError() {
    dom.banner.hidden = true;
    state.retryAction = null;
  }

  /* ---------- status and controls ---------- */

  function effectiveStatus() {
    return state.reconnecting ? 'reconnecting' : state.status;
  }

  function renderStatus() {
    const key = effectiveStatus();
    dom.pill.textContent = STATUS_TEXT[key] || STATUS_TEXT.idle;
    dom.pill.dataset.state = key;
    renderControls();
  }

  function renderControls() {
    const status = effectiveStatus();
    const hasMission = Boolean(state.missionId);
    const configLocked =
      state.loading || status === 'running' || status === 'paused' ||
      status === 'reconnecting' || status === 'complete';

    dom.launch.disabled =
      !hasMission || status === 'running' || status === 'reconnecting' || status === 'complete';
    dom.launch.textContent = status === 'paused' ? 'Resume mission' : 'Launch mission';
    dom.pause.disabled = status !== 'running';
    dom.reset.disabled = !hasMission;
    dom.seed.disabled = configLocked || !hasMission;
    dom.altitude.disabled = configLocked || !hasMission;
    dom.speed.disabled = configLocked || !hasMission;
  }

  function updateOutputs() {
    dom.altitudeValue.textContent = `${dom.altitude.value} m`;
    dom.speedValue.textContent = `${dom.speed.value} m/s`;
  }

  /* ---------- log ---------- */

  function logEvent(text, seconds) {
    const entry = document.createElement('li');
    entry.className = 'log-row';

    const time = document.createElement('span');
    time.className = 'log-time';
    time.textContent = clock(seconds === undefined ? simNow() : seconds);

    const body = document.createElement('span');
    body.className = 'log-text';
    body.textContent = text;
    body.title = text;

    entry.append(time, body);
    dom.logList.prepend(entry);
    while (dom.logList.children.length > LOG_LIMIT) {
      dom.logList.lastElementChild.remove();
    }
  }

  /* ---------- feed ---------- */

  function createFeedRow(detection) {
    const row = document.createElement('li');
    row.className = 'feed-row';

    const thumb = document.createElement('img');
    thumb.className = 'feed-thumb';
    thumb.width = 52;
    thumb.height = 52;
    thumb.alt = `Crop of ${classLabel(detection.class)} ${detection.id}`;
    thumb.loading = 'lazy';
    if (detection.crop) {
      thumb.src = detection.crop;
    } else {
      thumb.hidden = true;
    }

    const main = document.createElement('div');
    main.className = 'feed-main';

    const top = document.createElement('div');
    top.className = 'feed-top';

    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.dataset.class = detection.class || '';
    chip.textContent = classLabel(detection.class);

    const confidence = confidencePct(detection.confidence);
    const confidenceWrap = document.createElement('span');
    confidenceWrap.className = 'feed-conf';
    confidenceWrap.setAttribute('aria-hidden', 'true');

    const bar = document.createElement('span');
    bar.className = 'feed-bar';
    const fill = document.createElement('span');
    fill.className = 'feed-bar-fill';
    fill.style.setProperty('--conf', `${confidence === null ? 0 : confidence}%`);
    bar.append(fill);

    const number = document.createElement('span');
    number.className = 'feed-conf-num';
    number.textContent = confidence === null ? DASH : `${confidence}%`;
    confidenceWrap.append(bar, number);

    const coord = document.createElement('p');
    coord.className = 'feed-coord';
    coord.textContent = `${coordText(detection)} \u00b7 ${detection.id}`;

    top.append(chip, confidenceWrap);
    main.append(top, coord);
    row.append(thumb, main);
    return row;
  }

  function addDetection(detection, options) {
    if (!detection || !detection.id) return;
    if (state.detections.some((item) => item.id === detection.id)) return;

    state.detections.push(detection);
    dom.feedList.prepend(createFeedRow(detection));
    while (dom.feedList.children.length > DETECTION_LIMIT) {
      dom.feedList.lastElementChild.remove();
    }
    dom.feedEmpty.hidden = true;
    dom.feedCount.textContent = String(state.detections.length);

    if (!options || options.log !== false) {
      logEvent(
        `Detection ${detection.id} \u00b7 ${classLabel(detection.class)} at ${confidencePct(detection.confidence) || 0}%.`
      );
    }
    markDirty();
    updateMapLabel();
  }

  /* ---------- telemetry ---------- */

  function setMetric(node, text) {
    node.textContent = text;
  }

  function renderTelemetry() {
    if (!state.telemetry && !state.stats) {
      setMetric(dom.metricCoverage, DASH);
      setMetric(dom.metricDistance, DASH);
      setMetric(dom.metricBattery, DASH);
      setMetric(dom.metricFrames, DASH);
      setMetric(dom.metricUnique, DASH);
      setMetric(dom.metricElapsed, DASH);
      return;
    }
    const telemetry = state.telemetry || {};
    const stats = state.stats || {};
    setMetric(dom.metricCoverage, pct(stats.coverage_pct));
    setMetric(dom.metricDistance, finite(stats.distance_m) ? `${fmt1(stats.distance_m)} m` : DASH);
    setMetric(dom.metricBattery, pct(telemetry.battery_pct));
    setMetric(dom.metricFrames, intText(stats.frames_captured));
    setMetric(
      dom.metricUnique,
      finite(stats.unique_discrepancies) ? intText(stats.unique_discrepancies) : String(state.detections.length)
    );
    setMetric(dom.metricElapsed, clock(telemetry.elapsed_s));
  }

  function renderPlan() {
    const plan = state.plan;
    dom.planLanes.textContent = plan && finite(plan.lane_count) ? String(plan.lane_count) : DASH;
    dom.planLength.textContent =
      plan && finite(plan.path_length_m) ? `${Math.round(plan.path_length_m)} m` : DASH;
  }

  function clearSkeletons() {
    document.querySelectorAll('.skeleton-text').forEach((node) => {
      node.classList.remove('skeleton-text');
    });
    dom.mapSkeleton.hidden = true;
  }

  /* ---------- scorecard ---------- */

  function setExportsEnabled(enabled) {
    const missionId = state.missionId;
    const targets = [
      [dom.exportCsv, 'csv'],
      [dom.exportGeo, 'geojson'],
      [dom.exportMd, 'md'],
    ];
    targets.forEach(([link, extension]) => {
      if (enabled && missionId) {
        link.href = `/api/missions/${encodeURIComponent(missionId)}/report.${extension}`;
        link.target = '_blank';
        link.rel = 'noopener';
        link.removeAttribute('aria-disabled');
        link.removeAttribute('tabindex');
        link.classList.remove('is-disabled');
      } else {
        link.removeAttribute('href');
        link.removeAttribute('target');
        link.removeAttribute('rel');
        link.setAttribute('aria-disabled', 'true');
        link.setAttribute('tabindex', '-1');
        link.classList.add('is-disabled');
      }
    });
  }

  function renderScorecard(evaluation) {
    const result = evaluation || {};
    dom.scorePrecision.textContent = ratio(result.precision);
    dom.scoreRecall.textContent = ratio(result.recall);
    dom.scoreF1.textContent = ratio(result.f1);
    dom.scoreError.textContent = finite(result.localization_error_m)
      ? `${result.localization_error_m.toFixed(2)} m`
      : DASH;

    const rows = Array.isArray(result.per_class) ? result.per_class : [];
    dom.scoreClasses.replaceChildren();
    if (!rows.length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 3;
      cell.className = 'empty';
      cell.textContent = 'No per-class results were returned.';
      row.append(cell);
      dom.scoreClasses.append(row);
    } else {
      rows.forEach((item) => {
        const row = document.createElement('tr');

        const nameCell = document.createElement('td');
        const chip = document.createElement('span');
        chip.className = 'chip';
        chip.dataset.class = item.class || '';
        chip.textContent = classLabel(item.class);
        nameCell.append(chip);

        const matchedCell = document.createElement('td');
        matchedCell.className = 'num';
        matchedCell.textContent = `${intText(item.matched)}/${intText(item.truth)}`;

        const precisionCell = document.createElement('td');
        precisionCell.className = 'num';
        precisionCell.textContent = ratio(item.precision);

        row.append(nameCell, matchedCell, precisionCell);
        dom.scoreClasses.append(row);
      });
    }

    dom.scorecard.hidden = false;
    setExportsEnabled(true);
    // The result is the payoff of the run: put it above the feed and bring the
    // rail back to the top so the operator sees the score without scrolling.
    const rail = dom.scorecard.parentElement;
    if (rail && rail.firstElementChild !== dom.scorecard) {
      rail.prepend(dom.scorecard);
    }
    if (rail) {
      rail.scrollTop = 0;
    }
  }

  /* ---------- mission state ---------- */

  function normalizeSeedInput() {
    const value = Number(dom.seed.value);
    if (!Number.isInteger(value) || value < 0) {
      const fallback = state.scenario && finite(state.scenario.default_seed)
        ? state.scenario.default_seed
        : 20261123;
      dom.seed.value = String(fallback);
      return fallback;
    }
    dom.seed.value = String(value);
    return value;
  }

  function clearMissionState() {
    clearTimeout(state.createTimer);
    state.createTimer = null;
    closeSocket();
    clearTimeout(state.retryTimer);
    state.retryTimer = null;

    state.missionId = null;
    state.plan = null;
    state.status = 'idle';
    state.reconnecting = false;
    state.pose = null;
    state.telemetry = null;
    state.stats = null;
    state.flown = [];
    state.detections = [];
    state.selectedId = null;
    state.lastLogSecond = -1;

    dom.missionId.textContent = '';
    dom.missionId.hidden = true;
    dom.feedList.replaceChildren();
    dom.feedEmpty.hidden = false;
    dom.feedCount.textContent = '0';
    dom.logList.replaceChildren();
    dom.scorecard.hidden = true;
    dom.scoreClasses.replaceChildren();
    dom.scorePrecision.textContent = DASH;
    dom.scoreRecall.textContent = DASH;
    dom.scoreF1.textContent = DASH;
    dom.scoreError.textContent = DASH;
    setExportsEnabled(false);
    hidePopover();
    renderPlan();
    renderTelemetry();
    renderStatus();
    markDirty();
  }

  async function createMission(options) {
    const reason = options && options.reason ? options.reason : 'config';
    const seq = ++state.createSeq;

    if (reason === 'reset') {
      clearMissionState();
      logEvent('Reset. Rebuilding the mission with the same seed.', 0);
    }

    const seed = normalizeSeedInput();
    const payload = {
      seed,
      altitude_m: Number(dom.altitude.value),
      speed_mps: Number(dom.speed.value),
      multiplier: MULTIPLIER,
    };

    try {
      const mission = await api('/api/missions', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      if (seq !== state.createSeq) return;

      state.missionId = mission.mission_id;
      state.plan = mission.plan || null;
      if (mission.world) state.world = Object.assign({}, DEFAULT_WORLD, mission.world);
      if (Array.isArray(mission.roads)) state.roads = mission.roads;

      dom.missionId.textContent = mission.mission_id;
      dom.missionId.hidden = false;
      dom.missionId.title = `Mission ${mission.mission_id}`;

      clearSkeletons();
      renderPlan();
      renderMapMeta();
      computeProjection();
      updateMapLabel();
      markDirty();
      hideError();
      setExportsEnabled(false);

      if (reason !== 'config') {
        const lanes = mission.plan && finite(mission.plan.lane_count) ? mission.plan.lane_count : DASH;
        const length = mission.plan && finite(mission.plan.path_length_m)
          ? `${Math.round(mission.plan.path_length_m)} m`
          : DASH;
        logEvent(`Mission ${mission.mission_id} planned \u00b7 ${lanes} lanes, ${length}.`, 0);
      }
      state.status = 'idle';
      state.reconnecting = false;
      renderStatus();
    } catch (error) {
      if (seq !== state.createSeq) return;
      showError(
        'Could not create the mission plan. Check that the backend is running.',
        () => createMission({ reason })
      );
    } finally {
      if (seq === state.createSeq) {
        state.loading = false;
        renderControls();
      }
    }
  }

  function onConfigChange() {
    updateOutputs();
    if (state.loading) return;
    if (state.status !== 'idle' || !state.missionId) {
      renderControls();
      return;
    }
    clearTimeout(state.createTimer);
    state.createTimer = setTimeout(() => {
      state.createTimer = null;
      if (state.status === 'idle' && state.missionId) {
        createMission({ reason: 'config' });
      }
    }, CREATE_DEBOUNCE_MS);
  }

  /* ---------- commands ---------- */

  async function launchMission() {
    if (!state.missionId) return;
    const status = effectiveStatus();
    if (status === 'running' || status === 'reconnecting' || status === 'complete') return;

    const missionId = state.missionId;
    dom.launch.disabled = true;
    try {
      await api(`/api/missions/${encodeURIComponent(missionId)}/start`, { method: 'POST' });
      if (state.missionId !== missionId) return;
      state.status = 'running';
      state.reconnecting = false;
      renderStatus();
      logEvent('Launch accepted. Opening the telemetry link.');
      connectSocket();
    } catch (error) {
      if (state.missionId !== missionId) return;
      showError('Could not start the mission. Check that the backend is running.', launchMission);
      renderControls();
    }
  }

  async function pauseMission() {
    if (!state.missionId) return;
    const missionId = state.missionId;
    try {
      await api(`/api/missions/${encodeURIComponent(missionId)}/pause`, { method: 'POST' });
      if (state.missionId !== missionId) return;
      state.status = 'paused';
      state.reconnecting = false;
      renderStatus();
      logEvent('Pause command accepted.');
    } catch (error) {
      if (state.missionId !== missionId) return;
      showError('Could not pause the mission. Retry once the link is back.', pauseMission);
    }
  }

  function resetMission() {
    normalizeSeedInput();
    createMission({ reason: 'reset' });
  }

  /* ---------- websocket ---------- */

  function socketUrl() {
    const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${scheme}//${window.location.host}/ws/missions/${encodeURIComponent(state.missionId)}`;
  }

  function connectSocket() {
    if (!state.missionId) return;
    closeSocket();

    let socket;
    try {
      socket = new WebSocket(socketUrl());
    } catch (error) {
      handleSocketDown();
      return;
    }
    state.socket = socket;

    socket.addEventListener('open', () => {
      if (state.socket !== socket) return;
      clearTimeout(state.retryTimer);
      state.retryTimer = null;
      const wasReconnecting = state.reconnecting;
      state.reconnecting = false;
      renderStatus();
      if (wasReconnecting) {
        logEvent('Telemetry link restored.');
        catchUp().catch(() => {});
      }
    });

    socket.addEventListener('message', (event) => {
      if (state.socket !== socket) return;
      let message = null;
      try {
        message = JSON.parse(event.data);
      } catch (error) {
        message = null;
      }
      if (message) handleEvent(message);
    });

    socket.addEventListener('close', () => {
      if (state.socket !== socket) return;
      state.socket = null;
      handleSocketDown();
    });

    socket.addEventListener('error', () => {
      /* the close event that follows drives the retry loop */
    });
  }

  function closeSocket() {
    const socket = state.socket;
    state.socket = null;
    if (socket) {
      try {
        socket.close();
      } catch (error) {
        /* already closed */
      }
    }
  }

  function handleSocketDown() {
    if (!state.missionId) return;
    if (state.status !== 'running' && state.status !== 'paused') return;
    if (!state.reconnecting) {
      state.reconnecting = true;
      renderStatus();
      logEvent('Telemetry link lost. Reconnecting every 2 s.');
    }
    scheduleReconnect();
  }

  function scheduleReconnect() {
    if (state.retryTimer) return;
    state.retryTimer = setTimeout(() => {
      state.retryTimer = null;
      if (!state.missionId) return;
      if (state.status !== 'running' && state.status !== 'paused') return;
      catchUp()
        .catch(() => {})
        .then(() => {
          if (!state.missionId) return;
          connectSocket();
        });
    }, WS_RETRY_MS);
  }

  function applySnapshot(snapshot) {
    if (!snapshot) return;
    if (Array.isArray(snapshot.flown) && snapshot.flown.length > state.flown.length) {
      state.flown = snapshot.flown.slice();
    }
    if (snapshot.pose) state.pose = snapshot.pose;
    if (snapshot.telemetry) state.telemetry = snapshot.telemetry;
    if (snapshot.stats) state.stats = snapshot.stats;
    if (Array.isArray(snapshot.detections)) {
      snapshot.detections.forEach((detection) => addDetection(detection, { log: false }));
    }
    if (snapshot.status === 'running' || snapshot.status === 'paused') {
      state.status = snapshot.status;
      renderStatus();
    }
    renderTelemetry();
    updateMapLabel();
    markDirty();
  }

  async function catchUp() {
    const missionId = state.missionId;
    if (!missionId) return;
    const snapshot = await api(`/api/missions/${encodeURIComponent(missionId)}`);
    if (state.missionId !== missionId || !snapshot) return;
    applySnapshot(snapshot);
    if (snapshot.status === 'complete') {
      await finishMission(snapshot.stats, null);
    }
  }

  /* ---------- events ---------- */

  function handleEvent(message) {
    if (!message || typeof message.type !== 'string') return;
    switch (message.type) {
      case 'tick':
        onTick(message);
        break;
      case 'detection':
        if (message.stats) {
          state.stats = message.stats;
          renderTelemetry();
        }
        addDetection(message.detection);
        break;
      case 'status':
        onStatusEvent(message.status);
        break;
      case 'snapshot':
        applySnapshot(message.snapshot);
        if (message.snapshot && message.snapshot.status === 'complete') {
          finishMission(message.snapshot.stats, null);
        }
        break;
      case 'complete':
        finishMission(message.stats, message.evaluation);
        break;
      default:
        break;
    }
  }

  function onStatusEvent(status) {
    if (status !== 'running' && status !== 'paused') return;
    const previous = state.status;
    state.status = status;
    state.reconnecting = false;
    renderStatus();
    if (previous !== status) {
      logEvent(status === 'paused' ? 'Mission paused.' : 'Mission running.');
    }
  }

  function onTick(message) {
    if (message.pose) state.pose = message.pose;
    if (message.telemetry) state.telemetry = message.telemetry;
    if (message.stats) state.stats = message.stats;
    if (Array.isArray(message.flown) && message.flown.length) {
      state.flown.push(...message.flown);
    }

    if (state.status !== 'running' && state.status !== 'paused') {
      state.status = 'running';
      state.reconnecting = false;
      renderStatus();
    }

    renderTelemetry();
    updateMapLabel();
    markDirty();

    const second = Math.floor(simNow());
    if (second !== state.lastLogSecond) {
      state.lastLogSecond = second;
      const stats = state.stats || {};
      const telemetry = state.telemetry || {};
      logEvent(
        `Coverage ${pct(stats.coverage_pct)} \u00b7 battery ${pct(telemetry.battery_pct)} ` +
          `\u00b7 ${intText(telemetry.gps_sats)} sats`,
        second
      );
    }
  }

  async function finishMission(stats, evaluation) {
    const missionId = state.missionId;
    state.status = 'complete';
    state.reconnecting = false;
    clearTimeout(state.retryTimer);
    state.retryTimer = null;
    closeSocket();
    if (stats) state.stats = stats;
    renderStatus();
    renderTelemetry();

    let result = null;
    if (missionId) {
      try {
        const payload = await api(`/api/missions/${encodeURIComponent(missionId)}/evaluation`);
        result = payload && payload.evaluation ? payload.evaluation : payload;
      } catch (error) {
        result = null;
      }
    }
    if (!result && evaluation) result = evaluation;
    if (state.missionId !== missionId) return;

    renderScorecard(result);
    setExportsEnabled(true);
    logEvent('Mission complete. Scorecard ready.', simNow());
    markDirty();
  }

  /* ---------- popover ---------- */

  function positionPopover(detection) {
    const point = toScreen(detection.x, detection.y);
    const width = dom.popover.offsetWidth || 220;
    const height = dom.popover.offsetHeight || 100;
    const edge = palette.mapPad / 2;
    const left = clamp(point[0] + palette.pinHit + 6, edge, Math.max(edge, mapView.w - width - edge));
    const top = clamp(point[1] - height / 2, edge, Math.max(edge, mapView.h - height - edge));
    dom.popover.style.left = `${Math.round(left)}px`;
    dom.popover.style.top = `${Math.round(top)}px`;
  }

  function openPopover(detection) {
    if (!finite(detection.x) || !finite(detection.y)) return;
    state.selectedId = detection.id;

    dom.popoverClass.textContent = classLabel(detection.class);
    dom.popoverClass.dataset.class = detection.class || '';

    const confidence = confidencePct(detection.confidence);
    dom.popoverConfidence.textContent =
      confidence === null ? 'Confidence unavailable' : `${confidence}% confidence`;
    dom.popoverId.textContent = detection.id;
    dom.popoverCoord.textContent = coordText(detection);

    if (detection.crop) {
      dom.popoverCrop.src = detection.crop;
      dom.popoverCrop.alt = `Crop of ${classLabel(detection.class)} ${detection.id}`;
      dom.popoverCrop.hidden = false;
    } else {
      dom.popoverCrop.removeAttribute('src');
      dom.popoverCrop.alt = '';
      dom.popoverCrop.hidden = true;
    }

    dom.popover.hidden = false;
    positionPopover(detection);
    markDirty();
  }

  function hidePopover() {
    if (dom.popover.hidden) return;
    dom.popover.hidden = true;
    state.selectedId = null;
    markDirty();
  }

  /* ---------- map ---------- */

  function readPalette() {
    const styles = window.getComputedStyle(document.documentElement);
    const read = (name) => styles.getPropertyValue(name).trim();
    palette = {
      mapInner: read('--map-bg-inner'),
      grid: read('--map-grid'),
      border: read('--map-border'),
      road: read('--map-road'),
      roadEdge: read('--map-road-edge'),
      roadLine: read('--map-road-line'),
      home: read('--map-home'),
      route: read('--map-route'),
      flown: read('--map-flown'),
      pinStroke: read('--map-pin-stroke'),
      drone: read('--map-drone'),
      halo: read('--map-halo'),
      muted: read('--muted'),
      font: read('--font-mono'),
      fontSize: parseFloat(read('--fs-2xs')) || 10,
      mapPad: parseFloat(read('--map-pad')) || 16,
      pinRadius: parseFloat(read('--pin-radius')) || 5,
      pinHalo: parseFloat(read('--pin-halo')) || 12,
      pinHit: parseFloat(read('--pin-hit')) || 8,
      pinStroke: parseFloat(read('--pin-stroke')) || 2,
      droneSize: parseFloat(read('--drone-size')) || 9,
      droneHalo: parseFloat(read('--drone-halo')) || 16,
      classes: {
        pothole: read('--class-pothole'),
        missing_cover: read('--class-missing_cover'),
        waterlogging: read('--class-waterlogging'),
        debris: read('--class-debris'),
        pavement_damage: read('--class-pavement_damage'),
      },
    };
  }

  function worldSize() {
    const world = state.world || DEFAULT_WORLD;
    return {
      w: finite(world.width_m) && world.width_m > 0 ? world.width_m : DEFAULT_WORLD.width_m,
      h: finite(world.height_m) && world.height_m > 0 ? world.height_m : DEFAULT_WORLD.height_m,
    };
  }

  function computeProjection() {
    const size = worldSize();
    const availableW = Math.max(mapView.w - palette.mapPad * 2, 1);
    const availableH = Math.max(mapView.h - palette.mapPad * 2, 1);
    mapView.scale = Math.min(availableW / size.w, availableH / size.h);
    mapView.ox = (mapView.w - size.w * mapView.scale) / 2;
    mapView.oy = (mapView.h - size.h * mapView.scale) / 2;
  }

  function toScreen(x, y) {
    const size = worldSize();
    return [mapView.ox + x * mapView.scale, mapView.oy + (size.h - y) * mapView.scale];
  }

  function gridStep(width, height) {
    const target = Math.max(width, height) / 8;
    const steps = [5, 10, 20, 25, 30, 50, 100];
    for (let index = 0; index < steps.length; index += 1) {
      if (steps[index] >= target) return steps[index];
    }
    return 100;
  }

  function roadRect(road, size) {
    const width = finite(road.width_m) && road.width_m > 0 ? road.width_m : 6;
    const from = finite(road.from_m) ? road.from_m : 0;
    const to = finite(road.to_m) ? road.to_m : size.h;
    const center = finite(road.center_m) ? road.center_m : 0;

    if (road.orientation === 'v') {
      const left = clamp(center - width / 2, 0, size.w);
      const right = clamp(center + width / 2, 0, size.w);
      const bottom = clamp(from, 0, size.h);
      const top = clamp(to, 0, size.h);
      return {
        x0: left,
        y0: top,
        x1: right,
        y1: bottom,
        line: [center, clamp(top, bottom, top), center, clamp(bottom, top, bottom)],
      };
    }

    const left = clamp(from, 0, size.w);
    const right = clamp(to, 0, size.w);
    const bottom = clamp(center - width / 2, 0, size.h);
    const top = clamp(center + width / 2, 0, size.h);
    return {
      x0: left,
      y0: top,
      x1: right,
      y1: bottom,
      line: [clamp(left, right, left), center, clamp(right, left, right), center],
    };
  }

  function drawMap() {
    if (!context) return;
    const width = mapView.w;
    const height = mapView.h;
    context.clearRect(0, 0, width, height);

    if (!state.world) {
      context.fillStyle = palette.muted;
      context.font = `${palette.fontSize}px ${palette.font}`;
      context.textAlign = 'center';
      context.textBaseline = 'middle';
      context.fillText('Waiting for scenario', width / 2, height / 2);
      context.textAlign = 'start';
      return;
    }

    const size = worldSize();
    const left = mapView.ox;
    const top = mapView.oy;
    const worldPxW = size.w * mapView.scale;
    const worldPxH = size.h * mapView.scale;
    const right = left + worldPxW;
    const bottom = top + worldPxH;

    context.fillStyle = palette.mapInner;
    context.fillRect(left, top, worldPxW, worldPxH);

    const step = gridStep(size.w, size.h);
    context.strokeStyle = palette.grid;
    context.lineWidth = 1;
    context.beginPath();
    for (let x = 0; x <= size.w + 0.001; x += step) {
      const screenX = toScreen(x, 0)[0];
      context.moveTo(screenX, top);
      context.lineTo(screenX, bottom);
    }
    for (let y = 0; y <= size.h + 0.001; y += step) {
      const screenY = toScreen(0, y)[1];
      context.moveTo(left, screenY);
      context.lineTo(right, screenY);
    }
    context.stroke();

    state.roads.forEach((road) => {
      if (!road) return;
      const rect = roadRect(road, size);
      const start = toScreen(rect.x0, rect.y0);
      const end = toScreen(rect.x1, rect.y1);
      context.fillStyle = palette.road;
      context.fillRect(start[0], start[1], end[0] - start[0], end[1] - start[1]);
      context.strokeStyle = palette.roadEdge;
      context.lineWidth = 1;
      context.strokeRect(start[0] + 0.5, start[1] + 0.5, end[0] - start[0] - 1, end[1] - start[1] - 1);

      const lineStart = toScreen(rect.line[0], rect.line[1]);
      const lineEnd = toScreen(rect.line[2], rect.line[3]);
      context.save();
      context.strokeStyle = palette.roadLine;
      context.lineWidth = 1;
      context.setLineDash([6, 6]);
      context.beginPath();
      context.moveTo(lineStart[0], lineStart[1]);
      context.lineTo(lineEnd[0], lineEnd[1]);
      context.stroke();
      context.restore();
    });

    context.strokeStyle = palette.border;
    context.lineWidth = 1;
    context.strokeRect(left + 0.5, top + 0.5, worldPxW - 1, worldPxH - 1);

    const waypoints = state.plan && Array.isArray(state.plan.waypoints) ? state.plan.waypoints : [];
    if (waypoints.length > 1) {
      context.save();
      context.strokeStyle = palette.route;
      context.lineWidth = 1.25;
      context.lineJoin = 'round';
      context.lineCap = 'round';
      context.setLineDash([5, 6]);
      context.beginPath();
      waypoints.forEach((point, index) => {
        if (!finite(point.x) || !finite(point.y)) return;
        const screen = toScreen(point.x, point.y);
        if (index === 0) context.moveTo(screen[0], screen[1]);
        else context.lineTo(screen[0], screen[1]);
      });
      context.stroke();
      context.restore();
    }

    if (state.flown.length === 1) {
      const point = toScreen(state.flown[0].x, state.flown[0].y);
      context.beginPath();
      context.arc(point[0], point[1], palette.pinRadius - palette.pinStroke, 0, Math.PI * 2);
      context.fillStyle = palette.flown;
      context.fill();
    } else if (state.flown.length > 1) {
      context.save();
      context.strokeStyle = palette.flown;
      context.lineWidth = 2;
      context.lineJoin = 'round';
      context.lineCap = 'round';
      context.beginPath();
      state.flown.forEach((point, index) => {
        const screen = toScreen(point.x, point.y);
        if (index === 0) context.moveTo(screen[0], screen[1]);
        else context.lineTo(screen[0], screen[1]);
      });
      context.stroke();
      context.restore();
    }

    if (state.home && finite(state.home.x) && finite(state.home.y)) {
      const home = toScreen(state.home.x, state.home.y);
      context.fillStyle = palette.home;
      context.fillRect(home[0] - 4, home[1] - 4, 8, 8);
      context.strokeStyle = palette.pinStroke;
      context.lineWidth = palette.pinStroke;
      context.strokeRect(home[0] - 4, home[1] - 4, 8, 8);
      context.font = `${palette.fontSize}px ${palette.font}`;
      context.textBaseline = 'middle';
      const labelWidth = context.measureText('HOME').width;
      context.fillStyle = palette.mapInner;
      context.fillRect(home[0] + 7, home[1] - palette.fontSize / 2, labelWidth + 4, palette.fontSize);
      context.fillStyle = palette.muted;
      context.fillText('HOME', home[0] + 9, home[1]);
    }

    state.detections.forEach((detection) => {
      if (!finite(detection.x) || !finite(detection.y)) return;
      const point = toScreen(detection.x, detection.y);
      if (point[0] < -palette.pinHalo || point[0] > width + palette.pinHalo) return;
      if (point[1] < -palette.pinHalo || point[1] > height + palette.pinHalo) return;

      const color = palette.classes[detection.class] || palette.halo;
      if (detection.id === state.selectedId) {
        context.beginPath();
        context.arc(point[0], point[1], palette.pinHalo, 0, Math.PI * 2);
        context.globalAlpha = 0.3;
        context.fillStyle = color;
        context.fill();
        context.globalAlpha = 1;
      }
      context.beginPath();
      context.arc(point[0], point[1], palette.pinRadius, 0, Math.PI * 2);
      context.fillStyle = color;
      context.fill();
      context.lineWidth = palette.pinStroke;
      context.strokeStyle = palette.pinStroke;
      context.stroke();
    });

    if (state.pose && finite(state.pose.x) && finite(state.pose.y)) {
      const drone = toScreen(state.pose.x, state.pose.y);
      const heading = ((toNumber(state.pose.heading_deg) || 0) * Math.PI) / 180;
      context.save();
      context.translate(drone[0], drone[1]);
      context.beginPath();
      context.arc(0, 0, palette.droneHalo, 0, Math.PI * 2);
      context.fillStyle = palette.halo;
      context.fill();
      context.rotate(heading);
      context.beginPath();
      context.moveTo(0, -palette.droneSize);
      context.lineTo(palette.droneSize * 0.72, palette.droneSize * 0.72);
      context.lineTo(0, palette.droneSize * 0.36);
      context.lineTo(-palette.droneSize * 0.72, palette.droneSize * 0.72);
      context.closePath();
      context.fillStyle = palette.drone;
      context.fill();
      context.lineWidth = 1.5;
      context.strokeStyle = palette.pinStroke;
      context.stroke();
      context.restore();
    }
  }

  function markDirty() {
    if (frameRequested) return;
    frameRequested = true;
    window.requestAnimationFrame(() => {
      frameRequested = false;
      drawMap();
      if (state.world && !dom.mapSkeleton.hidden) dom.mapSkeleton.hidden = true;
    });
  }

  function resizeCanvas() {
    const rect = dom.map.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(Math.round(rect.width), 1);
    const height = Math.max(Math.round(rect.height), 1);
    if (width === mapView.w && height === mapView.h && dpr === mapView.dpr) return;

    mapView.w = width;
    mapView.h = height;
    mapView.dpr = dpr;
    dom.map.width = Math.round(width * dpr);
    dom.map.height = Math.round(height * dpr);
    if (context) context.setTransform(dpr, 0, 0, dpr, 0, 0);
    computeProjection();
    markDirty();

    if (state.selectedId) {
      const detection = state.detections.find((item) => item.id === state.selectedId);
      if (detection) positionPopover(detection);
    }
  }

  function renderMapMeta() {
    if (!state.world) {
      dom.mapMeta.textContent = 'Waiting for scenario';
      return;
    }
    const world = state.world;
    const lat = toNumber(world.origin_lat);
    const lon = toNumber(world.origin_lon);
    const origin = lat !== null && lon !== null
      ? `origin ${lat.toFixed(4)}, ${lon.toFixed(4)}`
      : 'local ENU';
    dom.mapMeta.textContent = `${world.width_m} \u00d7 ${world.height_m} m \u00b7 ${origin}`;
  }

  function updateMapLabel() {
    if (!state.world) {
      dom.map.setAttribute('aria-label', 'Mission map. Scenario not loaded yet.');
      return;
    }
    const count = state.detections.length;
    const pose = state.pose;
    const drone = pose && finite(pose.x) && finite(pose.y)
      ? `drone at ${pose.x.toFixed(1)}, ${pose.y.toFixed(1)} metres`
      : 'drone on standby';
    dom.map.setAttribute(
      'aria-label',
      `Mission map with ${count} detection pin${count === 1 ? '' : 's'}, ${drone}.`
    );
  }

  function hitTest(clientX, clientY) {
    const rect = dom.map.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    let hit = null;
    state.detections.forEach((detection) => {
      if (!finite(detection.x) || !finite(detection.y)) return;
      const point = toScreen(detection.x, detection.y);
      if (Math.hypot(point[0] - x, point[1] - y) <= palette.pinHit) hit = detection;
    });
    return hit;
  }

  /* ---------- wiring ---------- */

  function bindEvents() {
    dom.launch.addEventListener('click', launchMission);
    dom.pause.addEventListener('click', pauseMission);
    dom.reset.addEventListener('click', resetMission);

    dom.seed.addEventListener('input', () => {
      state.seedTouched = true;
    });
    dom.seed.addEventListener('change', () => {
      normalizeSeedInput();
      onConfigChange();
    });

    dom.altitude.addEventListener('input', updateOutputs);
    dom.altitude.addEventListener('change', onConfigChange);
    dom.speed.addEventListener('input', updateOutputs);
    dom.speed.addEventListener('change', onConfigChange);

    dom.map.addEventListener('click', (event) => {
      const hit = hitTest(event.clientX, event.clientY);
      if (hit) openPopover(hit);
      else hidePopover();
    });

    dom.popoverClose.addEventListener('click', hidePopover);

    document.addEventListener('pointerdown', (event) => {
      if (dom.popover.hidden) return;
      const target = event.target;
      if (dom.popover.contains(target)) return;
      if (target === dom.map) return;
      hidePopover();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        hidePopover();
        return;
      }
      if (event.code !== 'Space' && event.key !== ' ') return;
      if (event.repeat) return;
      const target = event.target;
      if (target instanceof HTMLElement) {
        const tag = target.tagName;
        if (
          tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' ||
          tag === 'BUTTON' || tag === 'A' || target.isContentEditable
        ) {
          return;
        }
      }
      event.preventDefault();
      const status = effectiveStatus();
      if (status === 'running') pauseMission();
      else if (status === 'idle' || status === 'paused') launchMission();
    });

    dom.bannerRetry.addEventListener('click', () => {
      const retry = state.retryAction;
      hideError();
      if (retry) retry();
    });

    if ('ResizeObserver' in window) {
      const observer = new ResizeObserver(() => {
        resizeCanvas();
        markDirty();
      });
      observer.observe(dom.mapFrame);
    } else {
      window.addEventListener('resize', () => {
        resizeCanvas();
        markDirty();
      });
    }

    window.addEventListener('pagehide', closeSocket);
    window.addEventListener('load', () => {
      resizeCanvas();
      markDirty();
    });
  }

  /* ---------- boot ---------- */

  async function loadScenario() {
    state.loading = true;
    dom.mapMeta.textContent = 'Loading scenario';
    renderControls();

    try {
      const scenario = await api('/api/scenario');
      state.scenario = scenario;
      state.world = Object.assign({}, DEFAULT_WORLD, scenario.world || {});
      state.roads = Array.isArray(scenario.roads) ? scenario.roads : [];
      state.home = scenario.home || null;

      if (!state.seedTouched && finite(scenario.default_seed)) {
        dom.seed.value = String(scenario.default_seed);
      }
      renderMapMeta();
      computeProjection();
      updateMapLabel();
      markDirty();
      hideError();
      clearSkeletons();
      await createMission({ reason: 'initial' });
    } catch (error) {
      clearSkeletons();
      dom.mapMeta.textContent = 'Scenario unavailable';
      showError(
        'Could not load the survey scenario. Check that the backend is running on this origin.',
        loadScenario
      );
      state.loading = false;
      renderControls();
    }
  }

  function boot() {
    readPalette();
    updateOutputs();
    renderStatus();
    renderTelemetry();
    renderPlan();
    setExportsEnabled(false);
    bindEvents();
    resizeCanvas();
    logEvent('Mission control ready. Load a mission to begin.', 0);
    loadScenario();
  }

  boot();
})();
