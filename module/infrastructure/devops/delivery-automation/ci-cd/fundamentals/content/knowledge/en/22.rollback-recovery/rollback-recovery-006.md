# Distinguishing Feature Disablement from Deployment Rollback

## Learning Objectives

After this lesson, learners can:

- Distinguish disabling a feature with a feature flag from rolling back a deployed application version.
- Explain the blast radius, response speed, and limitations of each measure.
- Choose the appropriate incident mitigation when a bug is isolated to one feature versus affecting the entire release.
- Determine the conditions for safely disabling a feature, including request paths, side effects, dependencies, and data.
- Evaluate rollback feasibility based on artifacts, configurations, schemas, and current data state.
- Design kill switches, approval workflows, auditing, and post-change verification.
- Coordinate feature disablement, deployment rollback, and data recovery in an incident response workflow.

## 1. Two Actions Addressing Two Different Scopes

When a release causes an incident, teams commonly mention two options: turning off the new feature or rolling back the deployment. Both actions can reduce impact, yet they change different parts of the system.

**Feature disablement** changes the on/off state of a capability inside the application. It typically uses a feature flag, kill switch, or runtime configuration to stop a functional flow from being used while the application continues running the same version.

**Deployment rollback** replaces the running artifact with a previously released version. This action changes the executed code or image, potentially along with its corresponding configuration and deployment revision.

Example:

- V2 adds a new payment flow controlled by a feature flag.
- After deploying V2, a bug causes the payment failure rate to spike.
- If the bug is confined to the new payment flow and V2 still has a working legacy path, disabling the flag stops the new flow.
- If the bug lies in a shared library causing processes to leak memory or slowing down every request, turning off one feature flag will not fix it; rolling back the version must be considered.

Feature disablement typically has a narrow scope and can respond quickly if configuration distributes well. Rollback changes the running version and can resolve bugs across many parts of a release, though it usually takes extra time to redeploy, start instances, and verify.

Principle to remember:

> Disabling a feature stops a specific capability from continuing to be used. Rollback changes the running software version. Choose the action based on the bug's scope and the actual system state.

The two measures are not mutually exclusive. You can disable a feature to reduce impact immediately, then roll back the version if needed. You can also roll back first and keep a flag turned off while investigating.

## 2. What Is a Feature Flag?

A feature flag is a mechanism allowing an application to decide whether to execute a capability based on configuration state.

A flag can control:

- Enabling a new UI.
- Selecting a pricing algorithm.
- Switching from an old payment provider to a new provider.
- Granting a user cohort access to a feature.
- Enabling a consumer or background job.
- Switching to a new implementation while retaining the old path.

Simple logic example:

~~~java
if (featureFlags.isEnabled("new-checkout", userContext)) {
    return newCheckoutService.checkout(request);
}
return legacyCheckoutService.checkout(request);
~~~

When the flag is off, the application takes the old branch. The V2 artifact is still running; only the behavior selected at runtime changes.

Feature flags can be read from:

- Configuration files or environment variables.
- A config service.
- A feature management platform.
- A database or cache.
- An application's dedicated runtime control plane.

How flag state is distributed determines the actual shutoff time. If the application reads flags only at startup, changing a flag may require a restart. If the application refreshes periodically or receives push updates, state can change while processes are running.

Do not assume turning off a flag in an admin UI means every instance immediately stopped the feature. Propagation time must be measured and verified.

## 3. What Is a Kill Switch and How Does It Differ from a Regular Feature Flag?

A kill switch is an emergency control designed to rapidly disable a function or execution path when risk arises.

Examples:

- Stop accepting payment requests through a failing provider.
- Pause bulk email or SMS sending.
- Block new order creation while auditing inventory data.
- Shut off a background job generating bad data.
- Block a new write flow while still allowing reads of existing data.

A regular feature flag may be used for rollouts, experiments, or cohort customization. A kill switch requires stricter operational characteristics:

- Can be toggled rapidly during emergencies.
- Has an explicit owner and authorized activators.
- Has a safe default value when configuration cannot be read.
- Has observable state and effective scope.
- Audits who changed it, why, and when.
- Provides a way to verify every instance received the new state.
- Has instructions for recovery or re-enabling after the incident is resolved.

A kill switch must not bypass access controls. When a feature is disabled, APIs must still enforce authorization. Never rely on a feature flag as the sole mechanism to protect data or block unauthorized access.

Also distinguish a kill switch from a circuit breaker. A circuit breaker automatically stops calling a dependency when errors or timeouts exceed thresholds, then probes recovery via a half-open state. A kill switch is typically a deliberate operational decision to disable a capability or path. Both mechanisms can work together, yet their goals and trigger conditions differ.

## 4. What Is a Deployment Rollback?

A deployment rollback reverts an environment to a previously released artifact or deployment revision.

Example:

~~~text
Previous state:
  application = V1
  artifact = sha256:old
  config = config-41

After release:
  application = V2
  artifact = sha256:new
  config = config-42

After deployment rollback:
  application = V1
  artifact = sha256:old
  config = config-41 (if compatible and selected for restoration)
~~~

A rollback may include:

- Redeploying the old container image or package.
- Restoring the previous deployment manifest or release revision.
- Shifting routing back to the old version pool.
- Restoring specific configs that changed alongside the release.
- Verifying the old version is actually serving traffic.

Not every rollback automatically restores all configuration. In some cases only the artifact is replaced, while runtime configs and feature flags keep their current state. Therefore, deployment records must clearly show both artifact and config revisions after rollback.

Rollback is appropriate when the bug belongs to the new version, has wide impact or cannot be isolated via a flag, and the old version remains compatible with current schemas, data, and dependencies.

## 5. Comparing Feature Disablement and Deployment Rollback

| Criterion | Feature disablement | Deployment rollback |
|---|---|---|
| Target of change | Flag state or runtime config | Artifact or deployment revision |
| Scope | Usually narrow, by feature or cohort | Usually broader, by service/release |
| Response time | Can be fast if flags distribute dynamically | Depends on rollout, scheduling, and startup |
| Running code | Remains the current version | Reverts to the old version |
| Prerequisites | Flag exists and shutoff path is safe | Old artifact exists and can be redeployed |
| Impact on data | Does not undo already-written data | Does not undo already-written data |
| Risks | Fallback branch may fail or flag may fail to propagate | Old code may be incompatible with schema/data |
| Required evidence | Flag revision, per-instance state, per-feature metrics | Artifact digest, deployment ID, config revision, health |
| Suitable cases | Bug isolated within one feature | Broad bug in code or release |
| Limitations | Does not remove faulty code from the process | Takes time and may not reverse migrations |

Never conclude that feature disablement is always safer or rollback is always more thorough. The decision depends on where the bug resides, whether the fallback path works, whether data has changed, and whether the previous version is compatible.

## 6. When Should You Disable a Feature?

Disabling a feature is usually the right choice when these conditions are met:

- The bug can be isolated to a single feature or processing branch.
- A flag is checked at the right boundary before executing side effects.
- The flag-off branch still works and has been tested.
- The feature can be stopped without leaving dangerous intermediate states.
- Shared dependencies or shared code are not the root cause.
- Turning it off does not break essential operations.
- Flag state can propagate and be verified quickly relative to incident severity.

Suitable examples:

- A new pricing algorithm produces wrong totals while the old algorithm still works.
- A new UI fails while the old API still serves properly.
- An external provider is failing and a backup provider exists.
- An experimental feature increases latency for a specific cohort.
- A new background job emits bad events and can be stopped independently.

Disabling a flag can immediately shrink the blast radius while the team investigates root cause or prepares a fix.

## 7. When Should You Roll Back a Deployment?

Rollback is usually appropriate when:

- The bug affects multiple endpoints or multiple features.
- A shared library causes crashes, memory leaks, or security flaws.
- Startup or process behavior is broken.
- A framework or runtime change causes widespread errors.
- No flag exists to isolate the functionality.
- The flag-off fallback path is also impacted.
- A verified old artifact exists and is compatible with the current data state.

Examples:

- V2 upgrades an HTTP client and all outbound requests time out.
- V2 introduces a connection pool bug exhausting resources.
- A new dependency causes class-loading errors at application startup.
- A logging or instrumentation change overloads the entire service.
- A newly disclosed security vulnerability requires removing code or a dependency from the runtime environment.

In these cases, turning off a feature flag cannot eliminate bugs in shared code. Rollback or releasing a patch may be required.

However, if the old version is incompatible with the new schema, direct rollback may cause further errors. A forward fix or an intermediate compatible version is needed instead.

## 8. When Must Both Be Coordinated?

Some incidents require multi-layered response.

Example where a new checkout flow writes incorrect order statuses:

1. Disable the new checkout flag to block new requests from entering the faulty flow.
2. Keep order read and lookup capabilities operating.
3. Identify the deployed artifact and config revision.
4. Assess whether the old version is compatible with the current schema.
5. If compatible, roll back the application to remove the new code.
6. Identify orders written with bad data and recover them selectively.
7. Verify business state and related events.
8. Re-enable the feature only after the fix has been tested.

In this example, feature disablement acts as fast containment; deployment rollback returns code to a known-good version; data recovery repairs affected data. No single action completely replaces the other two.

## 9. Flags Must Sit at the Right Boundary Before Side Effects

A flag is effective only if evaluated before the system executes the action you want to prevent.

Payment flow example:

~~~mermaid
flowchart TD
    A["Checkout request"] --> B["Check authorization"]
    B --> C["Read feature flag"]
    C --> D{"New payment enabled?"}
    D -- "Yes" --> E["New payment flow"]
    D -- "No" --> F["Legacy payment flow"]
    E --> G["Call payment provider"]
    F --> G
    G --> H["Record result"]
~~~

If the flag only hides a UI button while the API still accepts requests and calls the provider, the feature is not truly disabled.

Check flags server-side at every point executing side effects:

- API handler or application service.
- Background worker before processing a job.
- Consumer before executing an action.
- Scheduler before creating new work.
- Integration adapter before calling external services.

You do not need to scatter flag checks across every line of code. Place them at clear business boundaries, ensuring every entry path into the capability passes through that check.

If multiple entry points exist—such as HTTP, queues, and scheduled jobs—check all of them. Disabling an API feature does not automatically stop consumers continuing to process messages already sitting in the queue.

## 10. Flag States Need Safe Defaults

When the feature flag service is unreachable, the application must know how to behave.

Two common options:

- **Fail closed:** treat the feature as off when state cannot be determined. Appropriate for high-risk features or sensitive side effects.
- **Fail open:** keep using the enabled state or the latest cached value. Appropriate only when disabling would cause greater disruption and the risk is accepted.

No single default fits every flag. Classify flags by impact:

| Flag category | Behavior when state cannot be read |
|---|---|
| Experimental feature | Usually off or limited to controlled cohort |
| New payment flow | Usually fail closed or fall back to verified provider/flow |
| Essential functionality | May retain last known state if turning off causes service outage |
| Safety kill switch | Must be designed so the off state activates and propagates reliably |
| UI enhancement | Can fall back to the legacy UI |

If using a local cache, define maximum TTL, refresh strategy, and expiration behavior. An indefinite cache can leave some instances keeping a feature enabled after operators turned the flag off.

For kill switches, provide a status inspection mechanism confirming adoption across all instances. Never rely solely on an "update successful" message from the control plane.

## 11. Propagation Delay and Inconsistent State

In multi-instance systems, a flag may update in the control plane while individual processes receive the new state at different times.

Causes:

- Polling intervals.
- Dropped push notifications.
- Unrefreshed local caches.
- Network partitions.
- Instances disconnected from the config service.
- Background workers using config loaded at startup.
- A region or cluster that has not yet received the new revision.

Therefore, observe:

- Current flag revision in the control plane.
- Revision used by each instance.
- Timestamp when each instance received the config.
- Rate of requests still entering the feature branch after shutoff.
- Which workers or consumers are still processing old work.
- Which instances have not confirmed the new state.

In severe incidents, you may need to drain or restart instances that have not picked up the new flag, or pause consumers and schedulers. This is an evidence-driven operational decision; never assume all instances update instantaneously.

## 12. Disabling a Feature Does Not Reverse Data or Side Effects

This is the most important limitation of feature disablement.

Suppose the new feature already:

- Created orders.
- Deducted inventory.
- Published events to a message broker.
- Sent emails to customers.
- Called a payment provider.
- Wrote data using a new schema.

Turning off the flag only prevents subsequent executions from entering that branch. It does not delete created orders, automatically restore inventory, recall sent emails, or cancel payment transactions.

Distinguish between:

- Preventing new side effects.
- Identifying side effects that already occurred.
- Compensating or recovering those side effects.
- Verifying the final state.

For example, if a feature created duplicate payment transactions, disabling the feature stops future duplicates. Existing transactions must be reconciled with the payment provider and refunded or voided per business rules.

Never run raw deletes on transaction history to make data "look like it never happened." For financial operations, preserve audit trails and use proper compensating transactions.

## 13. Disabling a Feature Does Not Remove Faulty Code or Vulnerabilities

A feature flag can prevent a code branch from being invoked under normal flow, yet the code remains inside the artifact and process.

If the defect is:

- A vulnerable dependency loaded at startup.
- A shared parser exploitable through another endpoint.
- A background thread continuing to run despite the UI feature being off.
- A memory leak in shared code.
- An API endpoint still directly callable without going through the UI.
- A module executing side effects before checking the flag.

Then turning off the flag alone may not eliminate the risk.

For security incidents, trace the exploit path and every entry point. If compromised code or dependencies remain loaded or reachable, release a patch or roll back the artifact per security policy.

Feature flags also do not replace authorization, input validation, or access control. Never rely on flag state to protect a sensitive resource.

## 14. Deployment Rollback Also Has Limitations

Deployment rollback is not a time-machine button for the entire system.

Issues to evaluate:

- Is the old version compatible with the current schema?
- Did a migration drop or transform data?
- Do feature flags and runtime configs need separate restoration?
- Are old secret versions still valid?
- Have messages or events emitted by the new version already been processed?
- Does the old artifact still exist in the registry and is it verified?
- Have external dependencies or infrastructure changed?
- Is the old version compatible with current dependency APIs?

If the new version ran a destructive migration, a deployment rollback may prevent the old application from starting or cause it to write corrupted data.

If the bug lies in a single feature, rolling back the entire service may forfeit other useful fixes or cause unnecessary downtime. Weigh bug scope against rollback scope.

## 15. Incident Response Workflow

When a post-deploy failure is detected, follow this workflow:

1. **Containment:** reduce immediate impact by disabling flags, stopping consumers, pausing jobs, or throttling traffic as appropriate.
2. **Classify:** determine whether the fault is in a feature, shared code, dependency, config, schema, or data.
3. **Measure:** inspect metrics by version, feature, cohort, and endpoint.
4. **Check compatibility:** verify whether old code can run with the current schema and data.
5. **Choose action:** keep current version and adjust flags, roll back deployment, or ship a forward fix.
6. **Recover state:** address already-occurred data changes or side effects if needed.
7. **Verify:** confirm flag revisions, artifact digests, instance health, and business invariants.
8. **Communicate and record:** log decisions, actors, timelines, and blast radius.
9. **Re-enable carefully:** re-enable the feature only after the fix is tested and rolled out with controls.

~~~mermaid
flowchart TD
    A["Post-deploy error detected"] --> B["Contain impact"]
    B --> C["Classify: feature or release-wide?"]
    C --> D{"Can it be safely isolated via flag?"}
    D -- "Yes" --> E["Disable feature / kill switch"]
    E --> F["Verify flag propagation"]
    F --> G["Assess data and side effects"]
    D -- "No" --> H["Assess rollback compatibility"]
    H --> I{"Is old artifact compatible?"}
    I -- "Yes" --> J["Roll back deployment"]
    I -- "No" --> K["Forward fix / compatible release"]
    G --> L["Recover or compensate if needed"]
    J --> M["Verify entire system"]
    K --> M
    L --> M
    M --> N["Write audit log and monitor"]
~~~

In real incidents, branches can combine. For instance, disable a flag first to stop new requests, then roll back the application and recover affected records.

## 16. Example: Disabling a New Payment Flow

A checkout service deploys V2 with a new payment flow. A feature flag is enabled for 10% of users. After 15 minutes, metrics show payment timeouts rising sharply in the new cohort while the legacy cohort remains stable.

The team needs to:

1. Turn off the `new-payment-flow` flag.
2. Confirm all API instances received the new flag revision.
3. Check whether background workers and retry queues are still calling the new provider.
4. Confirm new requests route to the legacy flow.
5. Reconcile payment intents created during those 15 minutes.
6. Check with the provider for transactions that succeeded despite callback timeouts.
7. Reconcile indeterminate transactions without sending duplicate payments.
8. Monitor timeout rates and checkout success rates after shutoff.
9. Investigate root cause and prepare a fix.

In this situation, rolling back all of V2 may be unnecessary if the fault is confined to the new flow and the rest of the code is stable. However, if V2 also changed a shared HTTP client affecting the legacy flow as well, consider rollback or a forward fix.

## 17. Example: Bug in Shared Runtime Code

A release upgrades a JSON processing library. After deployment, every endpoint handling large payloads spikes in memory and restarts processes. The feature flag only controls a new UI, not the JSON library.

Turning off the new UI does not stop the failures because old endpoints also use the new library. The team needs to:

1. Halt the rollout so more instances are not impacted.
2. Identify the artifact digest and dependency version.
3. Check whether the previous version is compatible with current schema and config.
4. If compatible, roll back to the old artifact by digest.
5. Verify memory, restart counts, and latency return to normal.
6. Check data or requests partially processed during the failure window.
7. Record the release and rollback conditions.
8. Fix the dependency, add load tests, and redeploy after review.

This example shows feature disablement only works when a clean functional boundary isolates the bug.

## 18. Feature Flag Lifecycle Management

Feature flags introduce extra state and code branches. Without governance, systems accumulate stale flags that cause confusion and increase risk.

Every flag should have:

- A descriptive name stating its purpose.
- An accountable owner.
- Flag type: release, experiment, operational, or kill switch.
- Default value.
- Scope and targeting rules.
- Creation date and planned review/removal date.
- Behavior when the flag service is unreachable.
- Auditing and change permissions.
- Metrics used to observe impact.

Once a feature stabilizes and toggling is no longer needed, remove the flag along with the old code branch in a reviewed change. Avoid leaving flags permanently straddling two branches for years.

Kill switches may be kept longer as valuable operational controls, provided they are rehearsed periodically and ownership stays current.

## 19. Testing Feature Disablement and Deployment Rollback

Do not test only the flag-enabled path. Test the disabled path and how the system reacts when state changes mid-request.

Scenarios to test:

- Flag disabled from application startup.
- Flag switched from enabled to disabled while the application is running.
- An instance failing to receive config updates.
- Flag service losing connectivity.
- In-flight requests during a flag state change.
- Jobs already queued before feature shutoff.
- Workers continuing to process older messages.
- Feature falling back to legacy implementation.
- Old code running on an expanded schema.
- Rollback after migrations have executed.
- Rollback mid-rollout.
- Restoring routing and verifying the actual running artifact.

Distinguish in-flight requests at shutoff time from new requests. A flag typically does not cancel an already-started transaction or request. If in-flight work must stop immediately, separate cancellation or draining mechanisms are required.

## 20. Operational Configuration Example

An illustrative configuration can describe feature flags and incident actions:

~~~yaml
features:
  new-checkout:
    enabled: false
    owner: checkout-team
    default_on_error: false
    evaluation_scope: server
    reviewed_at: 2026-11-18

operations:
  kill_switches:
    payment-provider-new:
      enabled: false
      owner: payments-oncall
      reason: incident-reference
      audit_required: true

deployment:
  artifact_digest: sha256:example
  previous_artifact_digest: sha256:previous
  config_revision: config-42
  rollback_compatible: verified
~~~

This is an illustrative structure, not a mandatory schema for any tool. Never store real secrets in this configuration. The `rollback_compatible` field must be backed by compatibility evidence, not a self-declared value that a pipeline trusts unconditionally.

A pipeline or control plane can:

- Verify the requester and permissions.
- Write before/after audit logs.
- Update the flag or deployment.
- Wait for state propagation.
- Check metrics and health.
- Finish only when actual state matches desired state.

## 21. Common Anti-Patterns

| Anti-pattern | Risk | Improvement |
|---|---|---|
| Hiding a UI button and assuming the feature is off | APIs or workers still execute | Check flags at server-side boundaries |
| Turning off a flag without checking instances | Some processes keep running the new branch | Track flag revision per instance |
| Using flags in place of authorization | Users can call APIs directly | Keep access control independent |
| Disabling a feature and assuming data is fixed | Prior side effects remain | Reconcile and run data recovery if needed |
| Rolling back the entire service for a single-feature bug | Increases blast radius and downtime | Use a flag if the fallback branch is safe |
| Turning off a flag for a shared-library bug | Faulty code is still called by other branches | Assess dependencies and roll back/fix artifact |
| Rolling back code without checking schema | Old version may error or corrupt data | Check compatibility before rollback |
| Flag service fails and defaults to enabled | Risky feature may keep running | Choose fail-open/closed by classification |
| Never cleaning up obsolete flags | Multiplies code branches and complicates testing | Manage owners, expiration, and cleanup |
| No audit trail for kill switches | Hard to trace emergency decisions | Record actor, reason, revision, and timestamp |

## 22. Checklist for Choosing Mitigation During an Incident

Before deciding between disabling a feature or rolling back a deployment, confirm:

- [ ] Whether the bug lies in a feature, shared code, dependency, or configuration is identified.
- [ ] All entry points are identified: APIs, workers, queues, schedulers, and integrations.
- [ ] The feature flag is checked before side effects.
- [ ] The flag-off fallback branch has been tested.
- [ ] Flag revisions can be verified across all instances.
- [ ] In-flight requests and jobs at shutoff time are accounted for.
- [ ] Already-generated data and side effects are identified.
- [ ] The old artifact is confirmed present with the right digest.
- [ ] Old code is verified compatible with current schema and data.
- [ ] Related runtime configs, secrets, and dependencies are evaluated.
- [ ] Accountable owners and execution permissions are in place.
- [ ] Auditing exists for flag or deployment changes.
- [ ] Post-action health and business metrics are verified.
- [ ] Data recovery or compensation plans exist if needed.
- [ ] Criteria and an owner exist for re-enabling the feature after fixing.

## 23. Self-Assessment Exercise

An e-commerce platform just deployed version V5. This release includes three changes:

- A new checkout UI enabled for 20% of users behind a feature flag.
- An upgraded shared HTTP library.
- A migration adding the `payment_reference` column and starting to write data into the new column.

After 10 minutes, operations observes:

- Error rate on the new checkout rises sharply.
- The legacy order lookup API continues working.
- Some background workers continue sending requests via the new HTTP client.
- 15 payment intents have been created with unknown final status.
- Version V4 remains in the registry, yet only knows the old schema.

Build a plan answering:

1. Should the new checkout flag be turned off immediately? Why?
2. Will turning off the flag stop the background workers?
3. What side effects must be checked from the 15 payment intents?
4. Does the shared HTTP library require a deployment rollback?
5. Can V4 run on the current schema? What evidence is needed?
6. Can the `payment_reference` column stay after rollback?
7. When is a forward fix needed instead of rollback?
8. How should flag state and running artifacts be verified on each instance?
9. When can the new checkout be re-enabled?

A solid plan may disable the flag for containment, pause or reconfigure workers, reconcile the payment intents, test V4 compatibility against the expanded schema, and decide on rollback based on the HTTP client bug's scope. Afterward, fix the bug, test both enabled/disabled branches, and roll out again with controls.

## Conclusion

Feature disablement and deployment rollback operate at different scopes. A feature flag or kill switch changes the behavior of a capability inside the running version; a deployment rollback swaps out the serving artifact or revision. Feature disablement fits isolated bugs when a safe fallback branch exists, whereas rollback fits broader bugs in code, runtimes, or dependencies.

Neither automatically undoes already-created data or side effects. During incident response, block new impact, classify fault scope, inspect per-instance state, check schema and artifact compatibility, and recover data if needed. A process with auditing, metrics, and drills covering both feature shutoff and rollback helps teams respond rapidly while maintaining system consistency.
