# Halting Expansion or Switching to Recovery on Adverse Signals

A completed deployment does not mean the new version operates well under real conditions. Once traffic reaches the new version, errors may appear only for a specific user cohort, region, request type, or as load climbs. If a pipeline continues expanding a rollout on schedule without reading operational signals, a small canary bug can become a widespread outage.

Therefore, rollouts need pre-defined **continuation conditions, pause conditions, and recovery conditions**. When adverse signals appear, the system must halt further expansion of the change, preserve enough evidence for investigation, and choose the right action: wait for more data, disable a feature, shift traffic, roll back the artifact, or roll forward with a fix. Decisions must rest on impact severity and reversibility, not merely on a successful deploy status.

## 1. Successful Deployment Does Not Mean a Healthy Service

A deployment controller typically confirms that resources were updated: pods were created, processes started, or the load balancer registered new instances. Those checks are necessary but insufficient to conclude the new version is safe.

An application can:

- Start successfully yet return errors on a business endpoint.
- Pass readiness probes yet hit slow database connections or exhaust pools under load.
- Return HTTP 200 yet write incorrect data or create duplicate transactions.
- Work fine in one region yet fail in another.
- Show a low error rate when the canary takes minimal traffic, yet degrade as percentage increases.
- Exhibit no obvious technical errors yet drop conversion or transaction completion rates.

Distinguish three milestones:

| Milestone | What is confirmed | What is not proven |
|---|---|---|
| Deployment complete | Version installed or rollout controller reports finished | Real behavior under traffic |
| Smoke/health check pass | A few basic paths respond properly | All business flows and realistic load |
| Post-deployment validation pass | Guardrails and metrics pass during the observation window | That no errors could appear later |

Post-deployment validation is the decision point for whether to keep expanding. It must link check results to the exact artifact digest, deployment revision, environment, and observation period.

## 2. Identifying Signals to Monitor Before Deployment

Do not wait until errors happen to pick metrics. Before rollout, the team must identify signals reflecting technical health, user experience, and business correctness.

| Signal group | Example | Can detect |
|---|---|---|
| Availability | Request success rate, health checks, ready instance count | Service unable to serve requests |
| Errors | HTTP 5xx, exceptions, failed jobs, timeouts | Functional regressions or dependency failures |
| Latency | p50, p95, p99, processing time by endpoint | Performance degradation |
| Saturation | CPU, memory, threads, connection pools, queue depth | Resource exhaustion or bottlenecks |
| Dependency | Database errors, cache misses, provider 429/5xx, message lag | Cascading impact from dependent systems |
| Business | Payment success, checkout completion, order creation | Bugs affecting business outcomes |
| Data correctness | Corrupt records, duplicates, reconciliation mismatches | App running yet producing wrong data |
| Deployment | Restarts, crash loops, failed probes, stalled rollout | Unstable new version |

You do not need to watch hundreds of metrics on every release. Pick a small set covering indicators the release could affect plus guardrails protecting the service. Every metric needs a clear definition, data source, measurement scope, and accountable owner.

A health endpoint returning 200 only shows one check path responded. It does not prove payments, order creation, or critical business flows work properly. Combine health checks with synthetic transactions or business checks using safe test data.

## 3. Comparing Against Baselines and SLOs

A standalone number is often hard to interpret. A 1% error rate might be normal for an internal tool yet a severe degradation for a payment flow normally steady at 0.05%.

A baseline is the reference operating level before deployment. It can come from:

- The same service, endpoint, and region over a window prior to release.
- Instances currently running the stable version.
- A control cohort not receiving the new feature.
- Agreed SLOs/SLIs and error budgets.
- A comparable load benchmark from previous releases.

When comparing, keep scopes equivalent. Comparing p95 of a canary's payment endpoint against system-wide p95 can hide problems if request mixes differ.

SLOs define the required service level. Error budgets express the tolerable amount of degradation over a period under policy. A release causing rapid error budget burn may require halting rollout even before the total error budget runs out.

Examples of interpretation:

- Availability drops below baseline and nears the SLO threshold.
- Canary error rate exceeds the stable group over the same period.
- p95 latency rises steadily after traffic increases.
- Error budget burn rate exceeds the defined alert threshold.

Do not treat a baseline as permanently fixed forever. Traffic, seasonality, user mix, and system architecture evolve; baselines must be selected for appropriate time ranges and conditions.

## 4. Setting Guardrails with Thresholds, Duration, and Scope

A guardrail is a boundary condition deciding whether a rollout may proceed. A guardrail can use an absolute threshold, a delta relative to baseline, or both.

Examples:

| Guardrail | Illustrative condition | Action |
|---|---|---|
| HTTP 5xx | Significantly higher than baseline over 10 minutes with sufficient requests | Halt traffic increase, investigate |
| p95 latency | Exceeds 1.5x baseline over a sustained window | Hold rollout or reduce traffic |
| Pod restarts | Crash loops or abnormal restart spikes | Halt rollout, inspect runtime |
| Payment success | New cohort drops past agreed threshold | Disable flag or shift traffic back to stable |
| Database pool | Connection waits and timeouts climb continuously | Halt expansion, inspect database load |
| Data integrity | Duplicates or reconciliation mismatches detected | Block rollout and trigger data remediation workflow |

These thresholds and durations are illustrative only. Teams must derive them from SLOs, baselines, risk levels, and traffic traits. Never copy one generic number across all services.

A guardrail should specify:

- Metric and calculation formula.
- Scope: service, endpoint, region, tenant, or cohort.
- Warning threshold and stop threshold.
- Evaluation window and sustained violation duration.
- Minimum sample size to conclude.
- Action when breached.
- Person or system authorized to decide.

If a metric lacks data, never treat it as passing automatically. Distinguish between passing, breaching, and insufficient data.

## 5. Observation Windows and Sample Sizes

Metrics fluctuate naturally. A single error or a few-second spike may not be a regression, yet waiting too long can widen the blast radius.

The observation window should fit:

- Actual service traffic volume.
- Business cycles, such as payment settlement time or batch processing.
- Application startup and warm-up duration.
- Telemetry pipeline latency.
- Severity if a failure occurs.
- Sufficient requests or transactions for comparison.

With high traffic, shifts can be detected in minutes. For low-traffic services, extend the window, use synthetic tests, or run active checks so you do not conclude from a handful of requests.

An evaluation rule may require simultaneously:

1. Metric breaches threshold.
2. Violation persists over a minimum duration.
3. Sufficient request or transaction volume is present.
4. Signal originates from the exact target revision or cohort.

For example, high p95 over 30 seconds across 8 requests lacks the confidence of p95 climbing steadily over 10 minutes across thousands of requests. Conversely, a data corruption event or wrong transaction may require stopping immediately without waiting for sample quotas.

## 6. Distinguishing Adverse Signals from Noisy Alerts

Not every alert requires a rollback. An alert may stem from monitoring systems, dependencies, or shifting background load unrelated to the release.

When an adverse signal appears, cross-check:

- Timing of error onset against deploy and traffic-shift timestamps.
- Canary cohort vs. stable cohort.
- Affected endpoints vs. unrelated endpoints.
- Regions with the new version vs. un-updated regions.
- Application metrics vs. database, cache, and provider metrics.
- Logs, traces, and deployment events for the same revision.

If both canary and stable degrade together because the database is overloaded, rolling back the artifact may not fix the root cause. However, if canary degrades markedly while stable remains healthy, a release regression is far more likely.

Distinguish **correlation** from **causation**. Errors appearing after deploy signal a need to investigate, without yet proving new code is the cause. For severe failures, prioritize containing impact first, then continue root-cause analysis once the service stabilizes.

## 7. Decisions When Adverse Signals Appear

Not every situation requires immediate rollback. Processes need actions with graduated levels of intervention.

| Decision | When appropriate | Outcome |
|---|---|---|
| Continue | Guardrails pass and data is sufficiently reliable | Proceed to next rollout stage |
| Hold/pause | Metrics unstable or samples insufficient | Hold ratio, wait for more data |
| Stop expansion | Adverse signals present, rollback need not yet confirmed | Do not increase audience or traffic |
| Reduce exposure | Issue impacts only a specific cohort or percentage | Lower percentage or narrow audience |
| Disable feature | Bug sits behind a flag with a safe fallback | Revert to old code path |
| Rollback deployment | New binary causes errors and old version remains compatible | Restore previous artifact |
| Roll forward | Rollback unsafe or fast fix needed | Deploy tested fix |
| Emergency mitigation | Risk of data loss, security breach, or major outage | Activate incident runbook |

Critically, **stopping expansion** and **recovery** are two separate decisions. Stopping rollout prevents more users from being affected while the team identifies the cause. Recovery restores system stability through the appropriate action.

## 8. Designing Clear Rollout States

A controlled rollout should have pre-defined states and transitions.

~~~mermaid
stateDiagram-v2
    [*] --> Preparing
    Preparing --> Validating: Deploy complete
    Validating --> Expanding: Guardrails pass
    Validating --> Paused: Missing data or unclear signals
    Validating --> Recovery: Severe violation
    Expanding --> Observing: Traffic step increased
    Observing --> Expanding: Guardrails pass
    Observing --> Paused: Alert requiring investigation
    Observing --> Recovery: Stop threshold breached
    Paused --> Observing: Sufficient data and cleared to proceed
    Paused --> Recovery: Recovery confirmed necessary
    Recovery --> Verifying: Recovery action complete
    Verifying --> Stable: Post-recovery checks pass
    Verifying --> Incident: Service not yet stable
    Stable --> [*]
~~~

States should carry clear operational meaning:

- **Preparing:** verify artifact, target, policy, and rollout plan.
- **Validating:** deployment finished, run smoke tests and initial observation.
- **Expanding:** increase exposure in defined increments.
- **Observing:** hold current ratio during an evaluation window.
- **Paused:** freeze changes for investigation.
- **Recovery:** disable flag, reduce traffic, roll back, or roll forward.
- **Verifying:** confirm the system has recovered.
- **Stable:** finalize rollout and store evidence.
- **Incident:** requires incident response per operational procedures.

Never allow a job timeout or monitoring disconnect to auto-transition to Stable. When mandatory signals cannot be retrieved, rollout must stay paused or failed per policy.

## 9. Progressive Rollouts Need Incremental Steps and Stop Points

Example of a traffic-percentage rollout:

| Stage | Traffic share | Condition |
|---|---:|---|
| Internal | Internal only | Smoke tests and primary flows pass |
| Canary | 1% | Metrics have enough samples, no critical errors |
| Small | 5% | Error rate and latency within guardrails |
| Medium | 25% | Business metrics and dependencies stable |
| Large | 50% | No downward trend |
| Full | 100% | Eligible to complete per policy |

Percentages must be tuned to traffic scale, isolation capability, and risk level. One service may need 1%, 2%, 5%, 10% steps; another may use 10%, 25%, 50%, 100%.

After each increment, open a fresh observation window. Do not keep stepping up automatically just because the previous check passed right after deploy. Some issues surface late due to cache warm-up, batch jobs, peak-load hours, or new data patterns.

When a guardrail is breached, the controller must hold or reduce exposure per policy. Never let a timed rollout schedule keep advancing independently of validation results.

## 10. Canary Example: Halting Traffic Expansion When Error Rate Spikes

Suppose a new version of the orders API receives 5% traffic. The team sets illustrative guardrails:

- Canary 5xx error rate must not exceed stable by more than the defined margin.
- p95 latency must not exceed the SLO threshold.
- Minimum request count must be met before comparing.
- Violation sustained across two consecutive windows halts traffic expansion.
- Any sign of wrong writes or data loss stops rollout immediately.

Observed results:

| Metric | Stable | Canary | Assessment |
|---|---:|---:|---|
| 5xx rate | 0.2% | 1.8% | Markedly worse |
| p95 latency | 180 ms | 310 ms | Degraded |
| Request count | 18,000 | 950 | Sufficient samples per example |
| Database connection wait | Normal | Elevated | Likely tied to new code |

The right decision is to halt traffic increases, preserve logs/traces, and investigate. If the fault is confirmed in the new code and the old path remains safe, shift traffic back to stable or roll back. Never push onward to 25% just because the deployment controller still reports all pods healthy.

## 11. When to Halt Rollout vs. When to Recover Immediately?

Impact severity can guide initial action:

| Severity | Signs | Initial action |
|---|---|---|
| Low | Single isolated alert, no user impact, insufficient samples | Hold ratio and observe |
| Medium | Error rate or latency worse than baseline, no data loss | Halt expansion, investigate |
| High | Many critical requests failing, SLO visibly impacted | Halt rollout and reduce exposure or roll back per runbook |
| Critical | Data loss, wrong transactions, data leak, or security impact | Stop immediately, trigger incident response and isolation measures |

Severity must be defined per service and business impact. A bug in a secondary feature might be tolerated briefly; misrecording monetary amounts or leaking data requires immediate response even if the failing request percentage is low.

When unsure of root cause, halting expansion is usually the safest first step. For critical signals, do not wait for investigation to finish before mitigating impact.

## 12. Choosing Between Disabling a Feature Flag, Shifting Traffic, and Rolling Back an Artifact

The recovery action depends on how the release was engineered.

| Situation | Potentially suitable action | What to verify |
|---|---|---|
| New feature fails, old code still in artifact | Disable feature flag | Fallback path still works and data is compatible |
| Canary instances fail, stable instances healthy | Shift traffic back to stable | Load balancer/service routing and capacity |
| New binary fails across all requests | Roll back artifact or roll forward | Old version compatible with current schema and config |
| New config causes errors | Restore previous config version | Old config remains compatible with running binary |
| Dependency overloaded by traffic surge | Reduce exposure, rate limit, or fall back | Do not worsen backlogs and retry storms |
| Migration already altered data | Follow data runbook; possibly roll forward or restore | Impact on transactions created after migration |

Disabling a flag will not help if new code already modified shared state before evaluating the flag. Rolling back an image also falls short if a database migration broke backward compatibility. Therefore, release and migration strategies must be designed together.

## 13. Automated Recovery Needs Safety Guardrails

Automated rollback cuts response time, yet wrong actions can compound incidents. Automate only when conditions, scope, and actions have been tested.

Safe candidates for automation:

- Halting rollout percentage increases when guardrails breach.
- Shifting traffic off canary if stable has sufficient capacity.
- Disabling a feature flag that has a verified fallback.
- Restoring a previous config version if the change is reversible.
- Filing an incident or paging operational channels per policy.

Exercise caution or require human operators for:

- Rolling back after an incompatible schema change.
- Canceling an in-progress migration.
- Restoring databases or data.
- Deleting resources or taking actions with hard-to-reverse side effects.
- Changing permissions, secrets, or security configurations.
- Rolling back when the previous version also has known issues.

Automation needs idempotency, timeouts, bounded retries, auditing, and stop conditions. Never let a controller oscillate between rollback and redeploy when a metric hovers near a threshold.

## 14. Avoiding Rollout Flapping and Overreaction

If a metric repeatedly crosses and dips back below a threshold, the system may toggle flags or shift traffic back and forth. This flapping complicates investigation and can destabilize the system further.

Techniques to reduce oscillation:

- **Hysteresis:** use separate thresholds for stopping and resuming.
- **Consecutive windows:** require sustained breaches across multiple windows before acting, except for critical errors.
- **Cooldown:** wait a period after changing traffic or flags before re-evaluating.
- **Minimum sample size:** do not decide based on too few requests.
- **Maximum pause duration:** if data remains insufficient past a deadline, require an operator decision.
- **One action at a time:** do not alter traffic, flags, and config simultaneously before knowing each change's effect.

For example, halt rollout when error rate exceeds 2% across two 5-minute windows, yet allow resuming only when error rate stays below 0.8% across three consecutive windows. These thresholds are illustrative; the gap between stop and resume thresholds prevents constant state flipping.

Never use cooldowns to delay responding to severe errors like data corruption or security incidents. Emergency conditions must have an immediate stop path.

## 15. Recovery Workflow Once Adverse Signals Are Confirmed

When guardrails confirm a release is causing impact, follow a clear runbook:

1. **Freeze rollout:** lock all further traffic increases or promotions.
2. **Contain impact:** halt canary, reduce percentage, disable flag, or shift traffic via the safe path.
3. **Identify revision:** record artifact digest, config version, deployment revision, and start time.
4. **Collect evidence:** logs, traces, metrics, events, request IDs, and dependency status.
5. **Choose remediation:** disable flag, roll back artifact, restore config, or roll forward.
6. **Check compatibility:** verify schema, data, messages, and consumers before changing versions.
7. **Execute recovery:** run steps in defined order with an accountable owner.
8. **Re-verify:** smoke tests, synthetic transactions, SLIs, and business metrics.
9. **Keep rollout paused:** resume only with an explicit decision and fresh evidence.
10. **Document incident:** root cause, blast radius, recovery duration, and preventive actions.

Do not delete pods, logs, or artifacts of the failing version before gathering necessary evidence, unless emergency isolation is required to protect the system. Evidence identifies root causes and prevents repeat defects in future releases.

## 16. Verifying After Recovery

Completing a rollback or flag toggle operationally does not mean the service has recovered. Re-run checks after the action.

Verification steps should include:

- Version serving traffic matches the deployment record.
- Ready instance ratio is healthy with no crash loops.
- Health checks and smoke tests pass.
- Synthetic transactions complete and data writes accurately.
- Error rates and latency return within guardrails.
- Database connections, queue depth, and dependencies stabilize.
- Zero traffic still hits the isolated version or feature.
- No residual backlog or retry storm remains from the outage phase.
- Business metrics reconciled to detect missing or duplicate transactions.

Maintain a post-recovery observation window. Closing an incident after a single successful test request risks errors returning when load climbs or caches expire.

For data incidents, include a separate reconciliation step. Disabling a flag or rolling back code does not automatically fix records already written incorrectly.

## 17. Designing Pipelines with a Guardrail Evaluation Step

Pipelines can model post-deployment validation as a mandatory gate between deploy and promote.

Pseudocode example:

~~~text
deploy(candidate_revision, target)

if not smoke_test(candidate_revision):
    pause_rollout()
    recover_using_runbook()
    stop

start_observation_window()

while observation_window_active:
    signals = collect_signals(candidate_revision, stable_revision)

    if critical_data_or_security_signal(signals):
        freeze_rollout()
        execute_emergency_runbook()
        stop

    if required_signal_missing(signals):
        pause_rollout()
        request_operator_decision()
        stop

    if guardrail_breached(signals):
        freeze_rollout()
        reduce_exposure_or_recover()
        verify_recovery()
        stop

if all_guardrails_passed_with_enough_samples():
    promote_to_next_stage()
else:
    keep_rollout_paused()
~~~

This example illustrates decision flow, not runnable code. Signal collection must tie metrics to the exact revision/cohort; guardrail conditions must specify concrete thresholds and durations; recovery actions must follow runbooks appropriate for the application and data.

Pipelines must never simply wait for a smoke test command to exit 0 and auto-promote. Enforce sufficient observation time, sample counts, and mandatory metrics. If monitoring is unreachable, the outcome is unverified, not successful.

## 18. Preserving Evidence and Rollout Decision Traceability

Every halt or recovery needs a record so the team knows what happened and why.

Information to record:

- Release ID, artifact digest, and source commit.
- Deployment revision, target environment, and rollout stage.
- Traffic percentage or audience at each timestamp.
- Baseline metrics, observed metrics, and evaluation windows.
- Breached guardrails, thresholds, and sample counts.
- Decision: continue, pause, stop, disable, roll back, or roll forward.
- Person or automation initiating the action.
- Timestamp and outcome of recovery.
- Post-recovery smoke tests, synthetic checks, and business verification.
- Related incident/ticket and conclusions.

Do not place secrets or raw personal data in logs and reports. Use request IDs, trace IDs, or minimized identifiers to link evidence.

These records help calibrate rollout thresholds, spot slow-to-detect signals, and prove why a release proceeded or halted.

## 19. End-to-End Example: Payment API Rollout Hits Errors

A new version of the payment API deploys to production. Initially, 1% of traffic shifts to the canary. Smoke tests pass, yet after a few minutes payment success rate drops and timeouts to the payment provider climb.

Handling flow:

1. Controller holds percentage at 1%, blocking progression to 5%.
2. Team compares canary against stable and confirms errors cluster on the new revision.
3. Traces show new requests call the provider twice on retries, increasing timeouts and duplicate-charge risk.
4. Team disables the new retry-flow flag because the old code path remains intact and tested.
5. Synthetic transactions confirm new payments run through the old flow.
6. Team reconciles transactions within the impacted window to spot requests with ambiguous state.
7. Error rate and payment success return within guardrails during the post-recovery observation window.
8. Rollout remains paused; the fix is tested before reopening the canary.

If the bug caused incorrect data writes, toggling the flag alone is insufficient. The team needs transaction reconciliation and remediation per the business runbook before continuing the release.

## 20. Checklist for Safe Rollout Halting and Recovery

Before expanding or closing a deployment, check:

- [ ] Artifact digest, revision, and target are clearly identified.
- [ ] Appropriate baselines exist for service, endpoint, and cohort.
- [ ] Guardrails cover availability, errors, latency, saturation, and critical business metrics.
- [ ] Each guardrail has thresholds, windows, minimum sample counts, and actions.
- [ ] Missing metrics or monitoring outages are never treated as pass.
- [ ] Each traffic increment has its own observation window.
- [ ] Canary is compared against stable under equivalent conditions.
- [ ] Pause/stop states exist to freeze rollout.
- [ ] Halting expansion is distinguished from rollback or recovery.
- [ ] Clear criteria exist for disabling flags, shifting traffic, rolling back, or rolling forward.
- [ ] Automated actions apply only to tested, reversible scenarios.
- [ ] Hysteresis, cooldowns, and retry bounds prevent oscillation.
- [ ] Runbooks exist for critical errors, data loss, and security incidents.
- [ ] Post-recovery checks include smoke tests, synthetic checks, and business verification.
- [ ] Evidence and decisions are saved alongside release ID and revision.

A safe rollout is not one that always marches to 100%. It is a rollout that can stop in time, contain blast radius, and recover based on evidence. When guardrails are pre-defined, pipelines have authority to pause, and teams have solid runbooks, adverse post-deployment signals become inputs to controlled decisions rather than ignored alerts.
