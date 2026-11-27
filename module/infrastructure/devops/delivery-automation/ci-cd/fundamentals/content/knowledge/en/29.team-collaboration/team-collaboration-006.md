# Recording Incidents to Improve Processes Instead of Just Rerunning Until Green

A pipeline that turns red and then green after clicking rerun can create the illusion that the problem disappeared. Yet a rerun only proves that the subsequent execution succeeded under its own conditions. It does not explain why the first run failed, what changed between runs, or whether the fault will return on the next release.

In CI/CD, rerunning is a recovery action or a way to gather another signal. Recording the incident is how you turn that signal into actionable understanding. Teams must preserve evidence, determine impact, uncover contributing conditions, assign improvement actions with accountable owners, and verify whether the change actually reduced risk.

This lesson explains how development, testing, operations, and security collaborate to handle incidents with a learning mindset. The goal is not adding bureaucracy to every failed build, but accurately identifying issues that affect pipeline reliability, release capability, or end users.

## 1. Distinguishing Failed Runs, Events, and Incidents

Not every red job is an operational incident. A unit test failing because it just caught a bug in a pull request is the exact feedback the pipeline was designed to deliver. Conversely, a test that repeatedly times out on shared runners, an artifact released with the wrong digest, or a deployment that disrupts service may require an incident management process.

Three concepts can be distinguished:

- **Failed run:** a single job or pipeline execution that finishes unsuccessfully. This is a technical status, not enough on its own to conclude root cause or impact severity.
- **Event:** an observable occurrence, such as a runner disconnecting, a dependency registry returning HTTP 503, a test timing out, or a deployment health check failing.
- **Incident:** a situation that significantly degrades reliability, availability, security, or software delivery capability; it requires coordinated response, impact assessment, and tracking until risk is controlled.

One incident can span multiple failed runs and related events. A single failed run can also become an incident if it exposes secrets, produces an untrustworthy artifact, or impacts users.

Teams should define recording thresholds suited to their product. For example, open an incident when a deployment disrupts service, release pipelines are broadly blocked, unreliable test results recur, artifact or provenance integrity is in doubt, or credentials show signs of exposure. An expected test failure on a feature branch can simply be handled as pull request feedback.

Severity should reflect impact and scope, not merely a red pipeline indicator. An auxiliary job failing for a few minutes may have low impact; an artifact signature verification failure can be critical even before any user experiences downtime.

## 2. Why Simply Rerunning Is Not Enough

Reruns can be useful in certain situations:

- An external service suffered a transient error and recovered.
- A runner lost connectivity or a VM was preempted.
- The test harness depends on timing, scheduling, or shared resources.
- A flaky test passes in one run and fails in another.

However, a passing rerun does not prove the underlying cause was eliminated. When the subsequent run passes, you need to know what changed: did the commit stay identical, did dependencies change, was it a different runner, was the cache refreshed, was test data regenerated, and did external services recover?

If teams only record the final "success" status, critical signals vanish:

- Flaky test rates go unmeasured.
- Recurring infrastructure faults are masked by retries.
- Developer wait time rises without showing up in quality reports.
- A risky change may still ship without human evaluation.
- Other teams keep hitting the same fault because no shared knowledge or preventive control exists.

Therefore, preserve both the initial failure and subsequent attempts. The final status may be green, yet the record must still show that the pipeline retried and why the retry was accepted.

## 3. CI/CD Incident Handling Workflow

A streamlined workflow can follow sequential stages. During severe incidents, some steps run in parallel, though recording evidence and decisions still requires an accountable owner.

~~~mermaid
flowchart TD
    A["Detect anomalous signal"] --> B["Triage impact and severity"]
    B --> C["Stabilize system, protect users"]
    C --> D["Collect and preserve evidence"]
    D --> E["Build timeline and investigate root cause"]
    E --> F["Document lessons and contributing factors"]
    F --> G["Assign improvement actions with owners"]
    G --> H["Implement changes and measure effectiveness"]
    H --> I{"Risk reduced per criteria?"}
    I -->|No| G
    I -->|Yes| J["Close incident and update knowledge base"]
~~~

### 3.1. Detection and Triage

Detection sources can include pipeline alerts, deployment health checks, service monitoring, user reports, security advisories, or developer escalations.

At intake, record detection timestamp, affected systems, reporter or team, observed symptoms, and urgency level. Initial classification may shift as new evidence emerges; what matters is preserving the initial decision and its rationale.

### 3.2. Stabilization and Impact Mitigation

Prioritize restoring service capability and preventing impact from spreading. Depending on the situation, actions may include halting promotion, locking a release pipeline, shifting traffic back to a stable version, revoking credentials, cordoning a runner pool, or temporarily throttling concurrency.

Record who made the decision, execution timestamp, change scope, and observed outcome. If a retry is needed to test reproducibility, confirm it is safe and causes no side effects such as duplicate releases, double notifications, or non-idempotent migrations.

### 3.3. Preserving Evidence

Collect evidence before logs expire, runners are recycled, or environments mutate. Never edit raw log contents to make reports prettier. When excerpting or normalizing data, keep links to the original source and document how the excerpt was produced.

### 3.4. Investigation and Action Decisions

Construct a timeline, inspect changes near the onset time, and separate triggers from underlying causes and contributing factors. Then translate findings into actions with accountable owners, deadlines, and acceptance criteria.

### 3.5. Verification and Closing the Incident

A ticket marked done does not automatically prove risk dropped. Verify through tests, metrics, logs, drills, or observation over a representative window. If an action misses its criteria, reopen it or file a follow-up linked to the original incident.

## 4. Collecting Reproducible Evidence

Good evidence helps others understand the incident even if they weren't present when it happened. For CI/CD, collect the following evidence categories:

| Evidence Category | Information to Preserve | Question Answered |
|---|---|---|
| Change identification | Repository, commit SHA, pull request, branch, merge base | Which code was being verified? |
| Pipeline | Pipeline/run ID, workflow or pipeline definition revision, trigger, start/end timestamps | Which automated flow executed? |
| Job and attempt | Job ID, stage, step, attempt count, exit code, duration | Exactly which step failed? |
| Worker | Runner/agent ID, image or version, OS, resource type, pool | Was the fault tied to the execution environment? |
| Dependencies | Lockfile, resolved versions, registry, checksums | Did the build use identical dependencies? |
| Artifact | Name, version, digest, build metadata, provenance | Which output was produced or deployed? |
| Environment | Environment, deployment ID, relevant configuration and revisions | Where and under what config did the error occur? |
| Observability | Logs, metrics, traces, health checks, infrastructure events | How did the system behave before and after the failure? |
| Impact | Services, users, outage duration, blocked releases | Who or what was affected? |

Not every incident needs every single field above. Store at minimum enough data to link commit, pipeline, attempt, worker, artifact, and environment.

Timestamps should use explicit time zones, preferably UTC and ISO 8601. Synchronizing clocks across runners, CI systems, registries, and observability backends makes timeline reconstruction far more accurate.

Protect sensitive data throughout collection. Never paste access tokens, private keys, passwords, cookies, secret contents, or unnecessary personal data into tickets or reports. Reference secrets by ID or credential management path; redact sensitive fields before sharing logs. Access to evidence must follow least privilege with appropriate retention windows.

If credential exposure is suspected, treat revoking or rotating the credential as an immediate standalone response action. Never wait for the root-cause report to finish before containing an active exposure risk.

## 5. Building a Timeline Instead of Guessing from One Log Line

A timeline is a chronological sequence of events backed by timestamps and evidence sources. A useful timeline typically includes:

1. When the commit or configuration changed.
2. When the pipeline triggered and jobs started.
3. When the first anomalous signal appeared.
4. When retries, rollbacks, promotion halts, or mitigations occurred.
5. When the system recovered.
6. When post-recovery verification completed and closure was decided.

For instance, two jobs failing minutes apart might stem from different causes. If the timeline reveals both ran on the same overloaded runner, a shared-resource contention hypothesis has strong backing. If only one project failed right after a dependency lockfile changed, investigate the dependency before blaming runners.

When exact timestamps are unknown, label them explicitly as estimates along with the estimation source. Never turn speculation into confirmed fact. Label statements as "verified", "investigating", or "insufficient data" so teams collaborate without confusing certainty levels.

## 6. Analyzing Root Causes Without Blaming Individuals

The purpose of an investigation is understanding the conditions that allowed the incident to happen and why safeguards failed to prevent or detect it sooner. Asking "who messed up?" degrades information quality. A far more useful question is: "what in our tools, processes, interfaces, or working conditions made that action seem reasonable at the time?"

Distinguish these concepts:

- **Trigger:** the initiating change or event, such as a new commit, a slow dependency registry, or a preempted runner.
- **Underlying cause:** the systemic condition allowing the trigger to cause an incident, such as timeouts unsuited to real load or pipelines lacking test data isolation.
- **Contributing factor:** conditions increasing likelihood or severity, such as missing metrics, unbounded retries, or unclear runbooks.
- **Detection gap:** why the team failed to spot the issue earlier, such as monitoring only final pipeline status while ignoring retry rates.

Useful analysis techniques include:

- **5 Whys:** ask "why?" repeatedly to trace the causal chain. Do not force exactly five steps; stop once you reach a verifiable cause with an actionable fix.
- **Fishbone/Ishikawa:** group factors across people, process, tooling, environment, data, and measurement so analysis looks beyond code alone.
- **Comparing good vs. bad runs:** diff commits, dependencies, runners, configs, caches, data, and timestamps.
- **Fault tree:** start from the consequence and decompose combinations of conditions that could produce it.

Never conclude "human carelessness" or "flaky network" without supporting evidence. A statement like "registry request timed out" only describes a symptom; dig further to find which layer timed out, whether it recurred, whether it correlated with load or connection limits, and why the pipeline failed to handle it gracefully.

## 7. Evaluating Retries as a Diagnostic Signal

Retries can change execution conditions. Therefore, record the first attempt and every subsequent attempt under the same correlation identifiers.

When inspecting a passing retry, verify:

- Did the commit SHA and pipeline definition stay identical?
- Did the dependency lockfile and resolved versions change?
- Was the artifact reused or rebuilt?
- Did the runner, image, region, network route, or resource quota differ?
- Were caches and workspaces preserved, cleared, or recreated?
- Did test data, databases, queues, or external service states change?
- Did the retry execute the exact same task or inadvertently trigger another side effect?

From these checks, perform initial triage:

| Symptom | Likely Area to Investigate |
|---|---|
| Same commit and dependencies, succeeds on a different runner | Runner, resources, networking, or worker config |
| Same runner, same inputs, test passes and fails intermittently | Race condition, shared state, or flaky test |
| Retry succeeds after a delay | Rate limiting, dependent service, or eventual consistency |
| Failure always reproduces for one specific commit | Regression or config/dependency change |
| Failure occurs only when multiple jobs run concurrently | Contention for resources, locks, ports, or shared data |
| Retry produces different state or duplicate side effects | Non-idempotent job or missing deduplication |

These are investigation hypotheses, not automatic conclusions. Check logs, metrics, and runtime conditions before assigning a root cause.

### 7.1. Designing Bounded Retries

Retries should be applied selectively:

- Retry only errors classified as likely transient.
- Bound both attempt count and total wait time.
- Use exponential backoff and jitter when calling overload-prone services.
- Preserve results and logs for all attempts, including the initial failed attempt.
- Never blindly retry authentication errors, config errors, signature checks, or deterministic logic errors.
- Retry only idempotent operations or those guarded against duplicate side effects.
- Surface "retried" or "unstable" status in quality reports.

General logic example:

~~~text
for attempt in 1..MAX_ATTEMPTS:
    result = execute_job()
    store_attempt_evidence(attempt, result)

    if result.success:
        if attempt > 1:
            report_as_recovered_after_retry()
        stop_successfully()

    if not is_retryable(result.error):
        stop_with_failure()

    if attempt == MAX_ATTEMPTS:
        stop_with_failure()

    wait(exponential_backoff_with_jitter(attempt))
~~~

This example illustrates decision flow only. Real policies must explicitly define which errors are retryable, which attempts may rerun, and which conditions still block release. For security checks, mandatory quality checks, or provenance verification, a passing retry should not automatically scrub the initial failure from release decisions.

For deployments or migrations, exercise extra caution: a retry might create a duplicate release, run a migration twice, or re-send commands to an already-updated system. Before retrying, inspect actual system state and design idempotent operations or reconciliation checks.

## 8. Example: Tests Only Failing on Shared Runners

Suppose a pipeline runs unit tests for the Order API. The first attempt times out after 60 seconds. A developer clicks retry, and the second attempt succeeds. Looking solely at final status, the team might dismiss it as a random glitch.

An incident record is opened, and the team gathers evidence:

- Both attempts used the exact same commit and dependency lockfile.
- The first attempt ran on a shared runner pool alongside several heavy jobs.
- Runner metrics showed elevated CPU and I/O wait during the test timeout window.
- The second attempt landed on a less loaded runner.
- Re-running under high concurrent load reliably reproduces the timeout.

With this evidence, the team can investigate resource contention. The trigger was running tests during peak contention. Contributing factors included an unsegmented runner pool mixing heavy and light workloads, concurrency exceeding real capacity, and test timeouts not calibrated against measured duration distributions.

Improvement actions might include:

1. Separate heavy test workloads from lightweight jobs, owned by the runner platform team.
2. Cap concurrency to runner capacity and monitor queue wait times.
3. Add CPU, memory, I/O, and test duration metrics per runner pool.
4. Re-measure runtime distributions to pick realistic timeouts.
5. Track timeout and retry rates over upcoming sprints.

Verification criteria go beyond "the next run is green." The team may require timeout rates to drop below an agreed threshold over a meaningful observation window, without significantly increasing queue wait time, while keeping critical jobs within target turnaround times.

This example also demonstrates that a test can have zero logic bugs yet yield unreliable feedback when the execution environment is unstable. Teams must improve both execution isolation and measurement rather than extending timeouts endlessly or cranking up retry counts.

## 9. Writing Actionable Post-Incident Reports

A post-incident report (incident review or postmortem) should help readers understand what happened, how big the impact was, what the team learned, and what must change. It is not a disciplinary report hunting for someone to blame.

A report can include these sections:

| Section | Content to Capture |
|---|---|
| Summary | One or two sentences describing the incident and current status |
| Scope and impact | Affected services, teams, releases, users, duration, and severity |
| Detection | Who or which system detected it, and via which signal |
| Timeline | Key events, timestamps, and evidence sources |
| Trigger | Verified initiating event |
| Causes and contributing factors | Systemic conditions and supporting evidence |
| Response | Stabilization steps, rollbacks, retries, revocations, or containment |
| What went well | Effective detection, coordination, or recovery mechanisms |
| Gaps | Conditions that widened impact or prolonged duration |
| Actions | Specific tasks, owners, due dates, and verification criteria |
| Follow-up | Updated metrics, dashboards, runbooks, or processes |

Example structured summary record:

~~~yaml
incident:
  id: CI-2026-014
  title: Unit test timeout on shared runner pool
  severity: SEV-3
  status: monitoring
  detected_at: "2026-11-18T02:15:00Z"
  resolved_at: "2026-11-18T03:05:00Z"
  affected:
    - order-api-ci
  impact:
    blocked_pull_requests: 8
    production_outage: false
  trigger: "Test workload ran during high runner contention"
  contributing_factors:
    - "Runner pool mixed heavy and lightweight jobs"
    - "No alert on resource saturation"
  evidence:
    pipeline_run: "run-1842"
    commit: "a1b2c3d"
    attempts: 2
  actions:
    - id: ACT-101
      description: "Separate heavy test workload"
      owner: platform-team
      due_date: "2026-11-25"
      success_measure: "Timeout rate below agreed threshold"
~~~

This is an illustrative data structure, not a mandatory severity schema or ID convention. Fields must match internal conventions. Never store secrets, tokens, or personal data in incident records.

## 10. Turning Lessons into Improvement Actions

A report only pays off when investigation results change how the system operates. Actions should target one of four levers:

- **Prevention:** reduce likelihood of failure, such as isolating test data, pinning dependencies, bounding concurrency, or validating configs pre-deploy.
- **Detection:** spot issues earlier, such as alerting on retry rates, tracking runner saturation, or verifying post-deploy health checks.
- **Impact reduction:** shrink blast radius, such as canary rollouts, halting promotion on bad signals, or isolating faulty runners.
- **Recovery:** enable safer restoration, such as rehearsed rollbacks, credential revocation procedures, or provenance-backed artifact reconstruction.

Every action requires:

1. A concrete description of the change to be made.
2. One accountable owner driving it to completion.
3. A due date or review checkpoint.
4. Priority based on impact and recurrence likelihood.
5. Observable or measurable acceptance criteria.
6. Links to associated tickets, pull requests, dashboards, or runbooks.

Avoid vague actions such as "be more careful," "monitor closer," or "don't let it happen again." If the action is "improve test stability," translate it into concrete tasks like removing execution-order dependencies, isolating test data, adding per-step timeouts, and tracking flaky test rates.

Do not solve every incident by adding retries. Retries can reduce visible pipeline failures without eliminating the underlying defect. Similarly, raising timeouts can mask runner overload. Select fixes backed by observed evidence.

## 11. Coordinating Across Roles

CI/CD incidents frequently live at the boundary between teams. A test timeout could stem from test code, runners, networking, databases, or pipeline resource allocation. Investigations stall if each team inspects only its own slice.

Useful role assignments include:

- **Incident lead:** maintains focus on resolution, sets severity, coordinates decisions, and drives status updates.
- **Technical investigator:** analyzes code, pipelines, runners, dependencies, and affected environments.
- **Communicator:** updates impacted teams, release stakeholders, and partners on an agreed cadence.
- **Scribe:** maintains the timeline, decisions, hypotheses, evidence links, and action items.

On small teams, one person may cover multiple roles. For minor incidents, avoid heavy ceremony; still clarify who coordinates and who records decisions.

When handing off between development and platform teams, provide an inspectable context bundle: pipeline/run ID, commit SHA, job and attempt, runner, timestamps, observed error, steps already attempted, and links to sanitized logs. Avoid sending a bare screenshot showing "failed" with zero context.

Critical decisions—such as proceeding with a release, halting promotion, rolling back, or accepting a retry—must be made by authorized owners. Reports must capture decisions and rationale so oncoming shifts can continue smoothly.

## 12. Measuring Whether the Process Is Improving

Teams can track a focused metric set to identify trends and evaluate improvements.

| Metric | Interpretation | Management Question |
|---|---|---|
| Retry rate | Jobs requiring retries divided by total jobs or total failed jobs (specify denominator) | How many runs are unstable? |
| Post-retry pass rate | Jobs that failed initially then passed on retry divided by retried jobs | How many failures are being masked by retries? |
| Flaky test rate | Proportion of tests yielding inconsistent results on identical inputs and conditions | Which tests are untrustworthy? |
| Pipeline failure rate | Pipeline failure rate segmented by cause category | Which failure class is growing? |
| Time to detect | Elapsed time from incident onset to detection | How early does the system spot issues? |
| Time to restore | Elapsed time from detection until service or delivery flow recovers | How long does impact last? |
| Recurrence rate | Proportion of incidents recurring by root-cause category or component | Did earlier fixes actually work? |
| Action completion | Proportion of actions finished on time and meeting acceptance criteria | Are lessons turning into real changes? |

Denominator definitions and measurement scope must stay consistent. For example, retry rate can be calculated over all jobs or over failed jobs; the two answer different questions. Document the formula directly on the dashboard so readers do not misinterpret it.

Never use metrics to pressure teams into hiding failures or turning pipelines green at any cost. A high green-pipeline rate paired with rising retry rates often signals eroding quality. A fast, safe rollback can indicate a healthy process even though that release counts as a change failure.

Segment metrics by cause type, runner pool, repository, test tier, and pipeline stage. Avoid using one aggregate number to blame a team or individual.

## 13. Feeding Lessons Back into the CI/CD Workflow

Once improvement actions are implemented, update the artifacts that keep others from hitting the same issue:

- Pipeline as Code: add validation checks, timeouts, concurrency limits, retry policies, or verification steps.
- Test suites: isolate data, eliminate ordering dependencies, improve failure diagnostics, and reduce non-determinism.
- Runners and agents: segregate workloads, update images, cap resources, or expand telemetry.
- Artifacts and dependencies: lock versions, verify checksums, and store digests and provenance.
- Release processes: add health checks, canaries, approvals, or rollbacks justified by incidents.
- Runbooks: document verification steps, recovery actions, contacts, and escalation triggers.
- Onboarding: add key lessons to docs so new members understand agreed conventions and design decisions.

If a fix lives only in personal notes, it vanishes when that person changes teams. Encode knowledge into code, documentation, dashboards, or processes that can be reviewed and maintained.

## 14. Common Mistakes in Incident Handling

| Mistake | Consequence | How to Improve |
|---|---|---|
| Recording only final status after retry | Destroys evidence of initial failure | Store every attempt and link them to the same pipeline |
| Concluding root cause from one log line | Fixes the wrong layer or misses contributing factors | Build a timeline and test hypotheses across multiple sources |
| Blaming an individual | Participants hesitate to share honest context | Focus on systemic conditions and defenses |
| Raising retry counts for all errors | Masks deterministic faults and slows pipelines | Apply conditional, bounded retries with metrics |
| Increasing timeouts without measuring load | Hides resource bottlenecks | Measure duration and resource distributions before tuning |
| Closing an incident when tickets close | Unclear whether risk actually declined | Close against verification criteria and an observation window |
| Assigning actions to "the whole team" | Unclear accountability | Assign one owner and supporting contributors |
| Pasting full raw logs into public tickets | Risks leaking credentials or sensitive data | Redact, restrict permissions, and store evidence securely |

## 15. Post-Incident Review Checklist

Before closing an incident review, teams can walk through this checklist:

- [ ] Incident category, severity, scope, and impact are defined.
- [ ] Associated repository, commit, pipeline, job, attempt, runner, artifact, and environment are linked.
- [ ] Raw evidence is preserved with secrets and personal data protected.
- [ ] Timeline separates verified facts from hypotheses or estimated timestamps.
- [ ] Trigger, underlying cause, contributing factors, and detection gaps are documented.
- [ ] Significance of each retry and what changed between attempts were examined.
- [ ] Report focuses on learning and systemic conditions without blaming individuals.
- [ ] Every action item has an owner, due date, priority, and acceptance criteria.
- [ ] Metrics or evidence verify that actions actually reduced risk.
- [ ] Runbooks, pipelines, tests, dashboards, or documentation were updated as needed.
- [ ] Affected teams know the status, decisions, and ongoing monitoring plan.

## 16. Closing Principle

A pipeline turning green after a retry is useful data, not proof that the system is healthy. Teams only improve when they preserve the first failure, understand the conditions behind it, separate verified facts from guesses, and convert lessons into verifiable changes.

When incident reviews have clear owners, acceptance criteria, and follow-up telemetry, every incident makes the CI/CD process more dependable. Team collaboration then moves beyond simply getting a single run back to green—it steadily lowers recurrence likelihood and shrinks impact when problems do occur.
