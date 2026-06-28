// DevPilot dashboard client.
// The supplied visual UI is preserved; this file connects it to the real
// cross-language analyzer, background-job progress feed, exports, and history.

class DevPilotApp {
    constructor() {
        this.currentTab = 'github';
        this.isAnalyzing = false;
        this.activeJobId = null;
        this.lastReport = null;
        this.initElements();
        this.bindEvents();
    }

    initElements() {
        this.loadingScreen = document.getElementById('loading-screen');
        this.progressFill = document.getElementById('progress-fill');
        this.progressPercentage = document.getElementById('progress-percentage');
        this.loadingStatus = document.getElementById('loading-status');
        this.loadingEta = document.getElementById('loading-eta');
        this.loadingElapsed = document.getElementById('loading-elapsed');
        this.loadingEvents = document.getElementById('loading-events');
        this.heroSection = document.getElementById('hero-section');
        this.dashboard = document.getElementById('dashboard');
        this.repoInput = document.getElementById('repo-input');
        this.analyzeBtn = document.getElementById('analyze-btn');
        this.tabBtns = document.querySelectorAll('.tab-btn');
        this.exampleBtns = document.querySelectorAll('.example-btn');
        this.issueTabs = document.querySelectorAll('.issue-tab');
        this.issuesPanels = document.querySelectorAll('.issues-panel');
        this.exportButton = document.querySelector('.export-btn');
        this.exportMenu = document.getElementById('export-menu');
        this.historyDrawer = document.getElementById('history-drawer');
        this.historyList = document.getElementById('history-list');
        this.inputError = document.getElementById('input-error');
    }

    bindEvents() {
        this.tabBtns.forEach((button) => button.addEventListener('click', () => this.switchTab(button.dataset.tab)));
        this.analyzeBtn.addEventListener('click', () => this.startAnalysis());
        this.repoInput.addEventListener('input', () => this.clearInputError());
        this.repoInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                this.startAnalysis();
            }
        });
        this.exampleBtns.forEach((button) => button.addEventListener('click', () => {
            this.currentTab = 'github';
            this.switchTab('github');
            this.repoInput.value = button.dataset.url;
            this.clearInputError();
            this.startAnalysis();
        }));
        document.getElementById('back-btn').addEventListener('click', () => this.showHero());
        this.issueTabs.forEach((tab) => tab.addEventListener('click', () => this.switchIssueTab(tab.dataset.issueType)));
        this.exportButton.addEventListener('click', () => this.toggleExportMenu());
        document.querySelectorAll('[data-export-format]').forEach((button) => {
            button.addEventListener('click', () => this.exportReport(button.dataset.exportFormat));
        });
        document.querySelector('.share-btn').addEventListener('click', () => this.shareReport());
        document.getElementById('dashboard-nav').addEventListener('click', (event) => {
            event.preventDefault();
            this.showHero();
        });
        document.getElementById('history-nav').addEventListener('click', (event) => {
            event.preventDefault();
            this.openHistory();
        });
        document.getElementById('history-close').addEventListener('click', () => this.closeHistory());
        document.getElementById('about-nav').addEventListener('click', (event) => {
            event.preventDefault();
            this.showToast('DevPilot runs language-aware repository audits, real progress events, and downloadable reports.', 'info');
        });
        document.addEventListener('click', (event) => {
            if (!event.target.closest('.export-wrap')) this.closeExportMenu();
        });
    }

    switchTab(tab) {
        this.currentTab = tab;
        this.clearInputError();
        this.tabBtns.forEach((button) => button.classList.toggle('active', button.dataset.tab === tab));
        this.repoInput.placeholder = tab === 'github'
            ? 'https://github.com/username/repository'
            : 'C:\\Projects\\your-repository  or  /path/to/project';
    }

    async startAnalysis() {
        if (this.isAnalyzing) return;
        const source = this.repoInput.value.trim();
        this.clearInputError();
        if (!source) {
            this.showError('Enter a local repository path or a public GitHub repository URL.');
            return;
        }
        if (this.currentTab === 'github') {
            const validationError = this.githubUrlValidationMessage(source);
            if (validationError) {
                this.showError(validationError);
                return;
            }
        }
        this.isAnalyzing = true;
        this.showLoading();
        this.setAnalyzeButtonState(true);
        try {
            const response = await this.api('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source, analysis_type: this.currentTab }),
            });
            this.activeJobId = response.jobId;
            const finalJob = await this.waitForCompletion(response.jobId);
            if (!finalJob.report) throw new Error('The audit completed without a report payload.');
            this.lastReport = finalJob.report;
            await this.sleep(280);
            this.showDashboard(finalJob.report);
        } catch (error) {
            this.hideLoading();
            this.showError(error.message || 'Analysis failed. Please check the source and try again.');
        } finally {
            this.isAnalyzing = false;
            this.setAnalyzeButtonState(false);
        }
    }

    isValidGithubUrl(url) {
        return !this.githubUrlValidationMessage(url);
    }

    githubUrlValidationMessage(value) {
        let parsed;
        try {
            parsed = new URL(value);
        } catch (_) {
            return 'Use a public GitHub URL such as https://github.com/owner/repository.';
        }
        const host = parsed.hostname.toLowerCase();
        if (!['github.com', 'www.github.com'].includes(host) || !['http:', 'https:'].includes(parsed.protocol)) {
            return 'DevPilot accepts public GitHub repositories only. Use https://github.com/owner/repository.';
        }
        if (parsed.search || parsed.hash) {
            return 'Paste the repository root URL only. Remove query text and # fragments.';
        }
        const parts = parsed.pathname.split('/').filter(Boolean);
        if (parts.length !== 2) {
            return 'Paste the repository root URL only: https://github.com/owner/repository. Do not use /tree/, /blob/, /issues/, or profile links.';
        }
        const [owner, repository] = parts;
        const segment = /^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,98}[A-Za-z0-9])?$/;
        const cleanRepository = repository.replace(/\.git$/i, '');
        if (!segment.test(owner) || !cleanRepository || !segment.test(cleanRepository)) {
            return 'That GitHub repository address is malformed. Use https://github.com/owner/repository.';
        }
        return '';
    }

    async waitForCompletion(jobId) {
        let networkFailures = 0;
        while (true) {
            try {
                const job = await this.api(`/api/jobs/${encodeURIComponent(jobId)}`);
                networkFailures = 0;
                this.updateLoading(job);
                if (job.state === 'completed') return job;
                if (job.state === 'failed') throw new Error(job.error || 'The repository audit could not be completed.');
            } catch (error) {
                networkFailures += 1;
                if (networkFailures >= 4) throw error;
                this.loadingStatus.textContent = 'Reconnecting to the audit engine…';
            }
            await this.sleep(240);
        }
    }

    showLoading() {
        this.closeHistory();
        this.loadingScreen.classList.remove('hidden');
        this.resetProgress();
    }

    hideLoading() {
        this.loadingScreen.classList.add('hidden');
    }

    resetProgress() {
        this.progressFill.style.width = '0%';
        this.progressPercentage.textContent = '0%';
        this.loadingStatus.textContent = 'Starting repository audit…';
        this.loadingEta.innerHTML = '<i class="fas fa-stopwatch"></i> Calibrating ETA';
        this.loadingElapsed.innerHTML = '<i class="fas fa-clock"></i> Elapsed 0s';
        this.loadingEvents.replaceChildren();
        document.querySelectorAll('.step').forEach((step) => step.classList.remove('active'));
    }

    updateLoading(job) {
        const progress = job.progress || {};
        const timing = job.timing || {};
        const percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
        this.progressFill.style.width = `${percent}%`;
        this.progressPercentage.textContent = `${Math.round(percent)}%`;
        this.loadingStatus.textContent = progress.label || 'Repository audit in progress…';
        this.loadingElapsed.innerHTML = `<i class="fas fa-clock"></i> Elapsed ${this.formatDuration(timing.elapsedSeconds || 0)}`;
        this.loadingEta.innerHTML = `<i class="fas fa-stopwatch"></i> ${this.etaText(timing)}`;
        this.activateLoadingSteps(progress.phase || 'queued');
        this.renderLoadingEvents(job.events || []);
    }

    etaText(timing) {
        if (!timing.estimatedSeconds) return 'Calibrating workload';
        const elapsed = Number(timing.elapsedSeconds || 0);
        const remaining = Math.max(0, timing.estimatedSeconds - elapsed);
        if (remaining <= 0 && elapsed > 0) return `Estimate ${this.formatDuration(timing.estimatedSeconds)} · finalizing`;
        const range = timing.lowerSeconds && timing.upperSeconds
            ? `${this.formatDuration(timing.lowerSeconds)}–${this.formatDuration(timing.upperSeconds)}`
            : this.formatDuration(timing.estimatedSeconds);
        return `Est. ${range} · about ${this.formatDuration(remaining)} left`;
    }

    activateLoadingSteps(phase) {
        const phaseToStep = {
            queued: 0, calibrate: 1, prepare: 1, clone: 1, scan: 1,
            structure: 2, code: 2, readme: 3, dependencies: 3,
            security: 4, testing: 5, score: 5, complete: 5,
        };
        const activeCount = phaseToStep[phase] || 1;
        document.querySelectorAll('.step').forEach((step, index) => {
            step.classList.toggle('active', index < activeCount);
        });
    }

    renderLoadingEvents(events) {
        this.loadingEvents.replaceChildren();
        events.slice(-3).reverse().forEach((event) => {
            const row = document.createElement('div');
            row.className = 'loading-event';
            const dot = document.createElement('span');
            dot.className = 'event-dot';
            const label = document.createElement('span');
            label.textContent = event.label || 'Audit event';
            const pct = document.createElement('b');
            pct.textContent = `${event.percent || 0}%`;
            row.append(dot, label, pct);
            this.loadingEvents.append(row);
        });
    }

    showDashboard(data) {
        this.hideLoading();
        this.heroSection.classList.add('hidden');
        this.dashboard.classList.remove('hidden');
        this.updateDashboard(data);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    showHero() {
        if (this.isAnalyzing) return;
        this.closeHistory();
        this.closeExportMenu();
        this.dashboard.classList.add('hidden');
        this.heroSection.classList.remove('hidden');
        window.scrollTo({ top: 0, behavior: 'smooth' });
        this.repoInput.focus();
    }

    updateDashboard(data) {
        document.getElementById('repo-name').textContent = data.repoName || 'Repository';
        document.getElementById('repo-url-display').textContent = data.repoUrl || 'Local repository';
        const analysis = data.analysis || {};
        document.getElementById('language-display').innerHTML = `<i class="fas fa-code-branch"></i> ${this.escapeHtml(analysis.languageLabel || 'No supported source detected')}`;
        document.getElementById('analysis-time-display').innerHTML = `<i class="fas fa-stopwatch"></i> Audit ${this.formatDuration(analysis.actualSeconds || 0)}${analysis.estimatedSeconds ? ` / est. ${this.formatDuration(analysis.estimatedSeconds)}` : ''}`;

        const overallScore = Number(data.overallScore || 0);
        this.animateNumber(document.getElementById('overall-score'), 0, overallScore, 1000);
        document.getElementById('overall-grade').textContent = data.grade || '--';
        document.getElementById('grade-description').textContent = data.gradeDescription || 'Repository audit completed.';
        this.animateScoreCircle(overallScore);

        const breakdown = data.breakdown || {};
        this.updateBreakdownCard('code-quality', breakdown.codeQuality, Boolean(analysis.codeQualityApplicable));
        this.updateBreakdownCard('documentation', breakdown.documentation);
        this.updateBreakdownCard('testing', breakdown.testing);
        this.updateBreakdownCard('security', breakdown.security);
        this.updateBreakdownCard('dependencies', breakdown.dependencies);
        this.updateBreakdownCard('structure', breakdown.structure);

        const stats = data.stats || {};
        this.animateNumber(document.getElementById('total-files'), 0, Number(stats.totalFiles || 0), 700);
        this.animateNumber(document.getElementById('source-files'), 0, Number(stats.sourceFiles || 0), 700);
        this.animateNumber(document.getElementById('test-files'), 0, Number(stats.testFiles || 0), 700);
        this.animateNumber(document.getElementById('dependencies-count'), 0, Number(stats.dependencies || 0), 700);
        this.animateNumber(document.getElementById('language-count'), 0, Number(stats.languages || 0), 700);

        this.renderPointList('strong-points-list', data.strongPoints, 'No strong signals were returned.');
        this.renderPointList('weak-points-list', data.weakPoints, 'No major weakness identified.');
        this.renderLanguageMatrix(data.languages || [], analysis);
        this.renderRoadmap(data.roadmap || []);
        this.renderIssues('code-issues-list', data.codeIssues || [], 'No file-level code issue detected.');
        this.renderIssues('security-issues-list', data.securityIssues || [], 'No security warning detected.');
        this.renderRecommendations(data.recommendations || []);
        document.getElementById('code-issues-badge').textContent = (data.codeIssues || []).length;
        document.getElementById('security-issues-badge').textContent = (data.securityIssues || []).length;
        document.getElementById('recommendations-badge').textContent = (data.recommendations || []).length;
    }

    animateScoreCircle(score) {
        const circle = document.getElementById('overall-score-circle');
        const circumference = 2 * Math.PI * 54;
        circle.style.strokeDasharray = `${circumference} ${circumference}`;
        circle.style.strokeDashoffset = circumference;
        const safeScore = Math.max(0, Math.min(100, score));
        setTimeout(() => {
            circle.style.strokeDashoffset = circumference - (safeScore / 100) * circumference;
            circle.style.stroke = this.scoreColor(safeScore);
        }, 80);
    }

    updateBreakdownCard(category, score, isApplicable = true) {
        const scoreElement = document.getElementById(`${category}-score`);
        const barElement = document.getElementById(`${category}-bar`);
        const card = barElement.closest('.breakdown-card');
        if (score === null || score === undefined || !isApplicable) {
            scoreElement.textContent = 'N/A';
            barElement.style.width = '12%';
            barElement.style.background = 'linear-gradient(135deg, #64748b 0%, #475569 100%)';
            card.classList.add('not-applicable');
            return;
        }
        card.classList.remove('not-applicable');
        const safeScore = Math.max(0, Math.min(100, Number(score)));
        this.animateNumber(scoreElement, 0, safeScore, 800);
        setTimeout(() => {
            barElement.style.width = `${safeScore}%`;
            barElement.style.background = this.scoreGradient(safeScore);
        }, 150);
    }

    renderPointList(listId, points, emptyMessage) {
        const list = document.getElementById(listId);
        list.replaceChildren();
        const items = Array.isArray(points) && points.length ? points : [emptyMessage];
        items.forEach((point) => {
            const li = document.createElement('li');
            if (point === emptyMessage) li.className = 'empty-state';
            li.textContent = point;
            list.append(li);
        });
    }

    renderLanguageMatrix(languages, analysis) {
        const grid = document.getElementById('language-health-grid');
        const empty = document.getElementById('language-matrix-empty');
        const count = document.getElementById('language-matrix-count');
        grid.replaceChildren();
        count.textContent = `${languages.length} ${languages.length === 1 ? 'LANGUAGE' : 'LANGUAGES'}`;
        if (!languages.length) {
            empty.classList.remove('hidden');
            if (analysis.codeQualityReason) empty.textContent = analysis.codeQualityReason;
            return;
        }
        empty.classList.add('hidden');
        languages.forEach((language) => {
            const card = document.createElement('article');
            card.className = 'language-health-card';
            const header = document.createElement('div');
            header.className = 'language-card-header';
            const title = document.createElement('h4');
            title.textContent = language.name;
            const score = document.createElement('span');
            score.className = 'language-score';
            score.textContent = `${language.score}/100`;
            header.append(title, score);
            const bar = document.createElement('div');
            bar.className = 'language-score-bar';
            const fill = document.createElement('span');
            fill.style.width = '0%';
            fill.style.background = this.scoreGradient(Number(language.score));
            bar.append(fill);
            const stats = document.createElement('div');
            stats.className = 'language-mini-stats';
            [
                `${language.files} files`,
                `${this.formatNumber(language.lines)} LOC`,
                `${language.functions} funcs`,
                `${language.commentRatio}% comments`,
            ].forEach((label) => {
                const item = document.createElement('span');
                item.textContent = label;
                stats.append(item);
            });
            const issues = document.createElement('p');
            issues.className = 'language-issue-summary';
            issues.textContent = language.issues && language.issues.length
                ? `${language.issues.length} targeted finding${language.issues.length === 1 ? '' : 's'}`
                : 'No significant language-specific finding';
            card.append(header, bar, stats, issues);
            grid.append(card);
            requestAnimationFrame(() => { fill.style.width = `${Math.max(0, Math.min(100, Number(language.score)))}%`; });
        });
    }

    renderRoadmap(items) {
        const timeline = document.getElementById('roadmap-timeline');
        timeline.replaceChildren();
        const roadmap = Array.isArray(items) && items.length ? items : [{ phase: 'Final', title: 'Preserve repository quality', priority: 'low', tasks: ['No urgent roadmap item was generated.'] }];
        roadmap.forEach((item) => {
            const row = document.createElement('article');
            row.className = `timeline-item ${item.priority || 'medium'}`;
            const phase = document.createElement('div');
            phase.className = 'timeline-phase';
            phase.textContent = `Phase ${item.phase}`;
            const title = document.createElement('h4');
            title.className = 'timeline-title';
            title.textContent = item.title || 'Repository improvement';
            const tasks = document.createElement('ul');
            tasks.className = 'timeline-tasks';
            (item.tasks || []).forEach((task) => {
                const taskRow = document.createElement('li');
                taskRow.textContent = task;
                tasks.append(taskRow);
            });
            row.append(phase, title, tasks);
            timeline.append(row);
        });
    }

    renderIssues(containerId, issues, emptyMessage) {
        const list = document.getElementById(containerId);
        list.replaceChildren();
        if (!issues.length) {
            const empty = document.createElement('p');
            empty.className = 'empty-state issue-empty';
            empty.textContent = emptyMessage;
            list.append(empty);
            return;
        }
        issues.forEach((issue) => {
            const row = document.createElement('article');
            const severity = this.normalizedSeverity(issue.severity);
            row.className = `issue-item ${severity}`;
            const header = document.createElement('div');
            header.className = 'issue-header';
            const type = document.createElement('span');
            type.className = 'issue-type';
            type.textContent = issue.type || 'finding';
            const badge = document.createElement('span');
            badge.className = `issue-severity ${severity}`;
            badge.textContent = severity;
            header.append(type, badge);
            const description = document.createElement('p');
            description.className = 'issue-description';
            description.textContent = issue.description || 'No description provided.';
            const location = document.createElement('span');
            location.className = 'issue-location';
            location.textContent = issue.location || 'Repository scan';
            row.append(header, description, location);
            list.append(row);
        });
    }

    renderRecommendations(items) {
        const list = document.getElementById('recommendations-list');
        list.replaceChildren();
        const recommendations = items.length ? items : ['No additional recommendation was generated.'];
        recommendations.forEach((recommendation) => {
            const row = document.createElement('article');
            row.className = 'issue-item low';
            const description = document.createElement('p');
            description.className = 'issue-description';
            description.textContent = recommendation;
            row.append(description);
            list.append(row);
        });
    }

    switchIssueTab(issueType) {
        this.issueTabs.forEach((tab) => tab.classList.toggle('active', tab.dataset.issueType === issueType));
        this.issuesPanels.forEach((panel) => panel.classList.toggle('active', panel.id === `${issueType}-issues-panel`));
    }

    toggleExportMenu() {
        if (!this.activeJobId) {
            this.showError('Run an analysis before exporting a report.');
            return;
        }
        const willOpen = this.exportMenu.classList.contains('hidden');
        this.exportMenu.classList.toggle('hidden', !willOpen);
        this.exportButton.setAttribute('aria-expanded', String(willOpen));
    }

    closeExportMenu() {
        this.exportMenu.classList.add('hidden');
        this.exportButton.setAttribute('aria-expanded', 'false');
    }

    exportReport(format) {
        if (!this.activeJobId) return;
        this.closeExportMenu();
        window.location.assign(`/api/jobs/${encodeURIComponent(this.activeJobId)}/export/${encodeURIComponent(format)}`);
    }

    async shareReport() {
        const text = this.lastReport
            ? `DevPilot scored ${this.lastReport.repoName} ${this.lastReport.overallScore}/100 (${this.lastReport.grade}).`
            : 'DevPilot repository analysis.';
        try {
            if (navigator.share) {
                await navigator.share({ title: 'DevPilot Analysis Report', text, url: window.location.href });
            } else if (navigator.clipboard) {
                await navigator.clipboard.writeText(`${text} ${window.location.href}`);
                this.showToast('Report summary copied to your clipboard.', 'success');
            } else {
                this.showToast(text, 'info');
            }
        } catch (error) {
            if (error.name !== 'AbortError') this.showToast('Could not share this report from the current browser.', 'error');
        }
    }

    async openHistory() {
        this.historyDrawer.classList.remove('hidden');
        this.historyList.replaceChildren();
        const loading = document.createElement('p');
        loading.className = 'empty-state';
        loading.textContent = 'Loading recent audits…';
        this.historyList.append(loading);
        try {
            const payload = await this.api('/api/history');
            this.renderHistory(payload.items || []);
        } catch (error) {
            this.renderHistory([], error.message);
        }
    }

    closeHistory() {
        this.historyDrawer.classList.add('hidden');
    }

    renderHistory(items, errorMessage = '') {
        this.historyList.replaceChildren();
        if (!items.length) {
            const empty = document.createElement('p');
            empty.className = 'empty-state';
            empty.textContent = errorMessage || 'No completed audit in this session yet.';
            this.historyList.append(empty);
            return;
        }
        items.forEach((item) => {
            const button = document.createElement('button');
            button.className = 'history-item';
            const headline = document.createElement('span');
            headline.textContent = item.repository;
            const meta = document.createElement('small');
            meta.textContent = `${item.score}/100 · ${item.grade} · ${this.formatDuration(item.completedSecondsAgo)} ago`;
            button.append(headline, meta);
            button.addEventListener('click', async () => {
                try {
                    const job = await this.api(`/api/jobs/${encodeURIComponent(item.jobId)}`);
                    if (!job.report) throw new Error('The saved report is no longer available.');
                    this.activeJobId = item.jobId;
                    this.lastReport = job.report;
                    this.closeHistory();
                    this.showDashboard(job.report);
                } catch (error) {
                    this.showError(error.message || 'Could not open that audit.');
                }
            });
            this.historyList.append(button);
        });
    }

    setAnalyzeButtonState(isBusy) {
        this.analyzeBtn.disabled = isBusy;
        this.analyzeBtn.querySelector('.btn-text').textContent = isBusy ? 'Analyzing…' : 'Analyze Repository';
    }

    animateNumber(element, start, end, duration) {
        if (!element) return;
        const startTime = performance.now();
        const safeEnd = Number.isFinite(Number(end)) ? Number(end) : 0;
        const animate = (now) => {
            const progress = Math.min((now - startTime) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 4);
            element.textContent = Math.round(start + (safeEnd - start) * eased);
            if (progress < 1) requestAnimationFrame(animate);
        };
        requestAnimationFrame(animate);
    }

    scoreColor(score) {
        if (score >= 80) return '#22c55e';
        if (score >= 60) return '#3b82f6';
        if (score >= 40) return '#f59e0b';
        return '#ef4444';
    }

    scoreGradient(score) {
        if (score >= 80) return 'linear-gradient(135deg, #22c55e 0%, #10b981 100%)';
        if (score >= 60) return 'linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)';
        if (score >= 40) return 'linear-gradient(135deg, #f59e0b 0%, #f97316 100%)';
        return 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)';
    }

    normalizedSeverity(value) {
        return ['low', 'medium', 'high', 'critical'].includes(String(value).toLowerCase())
            ? String(value).toLowerCase()
            : 'medium';
    }

    formatDuration(seconds) {
        const safe = Math.max(0, Math.round(Number(seconds) || 0));
        if (safe < 60) return `${safe}s`;
        return `${Math.floor(safe / 60)}m ${safe % 60}s`;
    }

    formatNumber(value) {
        return new Intl.NumberFormat().format(Number(value) || 0);
    }

    escapeHtml(value) {
        const node = document.createElement('span');
        node.textContent = value;
        return node.innerHTML;
    }

    showError(message) {
        this.showInputError(message);
        this.showToast(message, 'error');
    }

    showInputError(message) {
        if (!this.repoInput || !this.inputError) return;
        this.repoInput.classList.add('invalid');
        this.repoInput.setAttribute('aria-invalid', 'true');
        this.inputError.textContent = message;
        this.inputError.classList.add('visible');
    }

    clearInputError() {
        if (!this.repoInput || !this.inputError) return;
        this.repoInput.classList.remove('invalid');
        this.repoInput.removeAttribute('aria-invalid');
        this.inputError.textContent = '';
        this.inputError.classList.remove('visible');
    }

    showToast(message, type = 'info') {
        document.querySelectorAll('.app-toast').forEach((node) => node.remove());
        const toast = document.createElement('div');
        toast.className = `app-toast ${type}`;
        const icon = document.createElement('i');
        icon.className = type === 'error' ? 'fas fa-circle-exclamation' : type === 'success' ? 'fas fa-circle-check' : 'fas fa-circle-info';
        const text = document.createElement('span');
        text.textContent = message;
        toast.append(icon, text);
        document.body.append(toast);
        requestAnimationFrame(() => toast.classList.add('visible'));
        setTimeout(() => {
            toast.classList.remove('visible');
            setTimeout(() => toast.remove(), 260);
        }, 4200);
    }

    async api(url, options = {}) {
        const response = await fetch(url, options);
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status}).`);
        return payload;
    }

    sleep(milliseconds) {
        return new Promise((resolve) => setTimeout(resolve, milliseconds));
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.app = new DevPilotApp();
});
