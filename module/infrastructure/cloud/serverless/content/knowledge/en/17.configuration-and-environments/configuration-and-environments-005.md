# Feature Flags and Progressive User Group Rollouts

In the **Configuration and Environments** chapter, a feature flag is a mechanism that decides whether a branch of application behavior is enabled for a given audience or environment. Instead of redeploying code every time you want to open a feature to a group of users, the application reads the decision from configuration and selects the corresponding behavior.

Feature flags are commonly used to gradually release features, test new experiences, quickly disable a malfunctioning capability, or restrict features to an internal group. For serverless applications, this mechanism must account for cold starts, multiple execution environments running in parallel, configuration caching, retries, and the possibility that different instances observe different flag versions for a brief window.

This lesson belongs to the **CLOUD_SERVERLESS** module, focusing on developing and deploying applications in the serverless model—especially Java functions triggered by HTTP, messages, or events. Learners work through triggers, state, access permissions, retries, idempotency, cold starts, scaling, and cost to decide when FaaS fits. Feature flags are part of runtime configuration: they enable controlled behavior changes without modifying code or redeploying every time.

## 1. What is a feature flag?

A feature flag is a configuration decision checked by the application at runtime to choose a behavior. For example, the exact same Java function version can:

- Enable a new checkout UI for internal employees.
- Allow 5% of customer accounts to use the new workflow.
- Enable larger batch processing in staging.
- Temporarily disable a processing branch causing increased database errors.
- Run an A/B experiment with two content variants.

A flag typically has a stable key, a default value, targeting rules, and governance metadata. For example:

~~~json
{
  "key": "new-checkout-flow",
  "enabled": true,
  "rolloutPercentage": 10,
  "environment": "production",
  "owner": "checkout-team",
  "expiresAt": "2027-03-31"
}
~~~

This is an illustrative structure. Real flag management services may store rules, segments, variants, and conditions under their own schemas. Applications should not depend directly on a specific vendor's internal JSON; map it into the evaluation model needed by application code.

Flags are usually part of dynamic configuration. Values can change independently of code deployments, though the application only sees updates once configuration is loaded or refreshed successfully.

## 2. Distinguishing feature flags, configuration, and authorization

These three concepts are related but do not replace one another.

| Concept | Question answered | Example |
|---|---|---|
| Feature flag | Should this behavior be enabled for this subject? | Use the new checkout for the beta group |
| Runtime configuration | What parameters configure this behavior? | API timeout is 2 seconds |
| Authorization / entitlement | Is this principal permitted to perform this action or access this data? | User has permission to view the tenant's invoices |

Feature flags decide code paths or experiences. Authorization checks permissions based on identity, resources, and policies. Never use a flag as the sole means to protect data or grant access.

For instance, a flag might enable a new export report button in the UI, yet the backend must still verify whether the caller is authorized to export reports for that tenant. Users can craft requests or call APIs directly; hiding a button in the UI does not secure the API.

Some systems have the concept of entitlements or service tiers. When access to a feature is part of a customer contract, check entitlements in a policy service or domain logic backed by a trusted data source. Flags can govern technical rollouts, whereas entitlements determine whether a customer is licensed to use the capability.

## 3. Types of feature flags

Flags can be categorized by purpose and lifespan:

| Flag type | Purpose | Typical lifespan |
|---|---|---|
| Release toggle | Phased feature rollout | Short to medium term |
| Operational toggle | Enable/disable components to protect the system | Can be long-lived if acting as a kill switch |
| Experiment toggle | Split traffic to compare variants | Duration of the experiment |
| Permission/entitlement toggle | Represent usage rights | Should be managed by a dedicated permissions system; never treat rollout flags as an authority source |

Release toggles let you deploy code ahead of enabling the feature. Operational toggles let you disable a processing branch when a dependency degrades. Experiment toggles assign subjects to variants to measure impact.

A flag should not linger indefinitely just because removal was forgotten. Every flag should have an owner, purpose, creation date, planned removal date, and accountable person. Once rollout completes, remove the legacy code branch and the flag to avoid accumulating hard-to-test code paths.

## 4. Targeting: selecting user groups or workloads

Targeting is the set of rules determining which subjects receive which flag value. Rules can be based on:

- Environment: dev, staging, production.
- Internal groups or beta cohorts.
- Stable account ID or tenant ID.
- Region or device type when justified by business logic.
- Application version or client type.
- Rollout percentage of eligible subjects.
- Allowlists or denylists.

Example rule evaluation order:

1. Disable the flag in special test environments.
2. If the tenant is excluded, disable the feature.
3. If the subject is on the internal employee list, enable the feature.
4. If the subject is in the beta cohort, enable the feature.
5. If the subject falls within the 10% rollout, enable the feature.
6. All remaining subjects receive the default value `false`.

Order and priority must be explicitly defined. If a subject appears in both an allowlist and an exclusion list, policy must dictate which rule wins. A common convention gives deny/exclusion rules highest priority, followed by explicit allowlists, segments, and rollout percentages; regardless, the system must document the actual precedence.

### 4.1. Choosing a stable identifier

To prevent a user from switching groups on every request, use a stable identifier such as an authenticated account ID or tenant ID. Never generate a fresh random number per invocation.

For multi-tenant B2B systems, decide whether the rollout unit is the user or the tenant. If a feature affects shared data, enabling it for only some users within the same tenant can create an inconsistent experience. In that case, roll out by tenant so every member of an organization receives the same decision.

Do not use email addresses, phone numbers, or personal data as targeting keys when an internal stable ID suffices. Avoid putting sensitive data into flag evaluation logs.

### 4.2. Context must be trustworthy

Targeting context typically contains a subject ID and attributes such as tenant, role, region, or app version. Attributes used for decisions must be authenticated or sourced from a trusted authority.

Do not trust a client-supplied `tenantId` or `role` field before the backend verifies it. A user could forge headers or payloads to place themselves in a beta group or a tier with premium features.

HTTP trigger adapters should validate tokens, build an internal principal, and only then construct the evaluation context. For message triggers, context should come from source-authenticated events or metadata produced by a trusted publisher.

## 5. Percentage rollouts and stable cohorts

A 10% rollout generally means consistently selecting 10% of eligible subjects—not randomly enabling 10% of invocations.

Conceptually:

\[
bucket = H(flagKey, subjectKey, salt) \bmod 100
\]

If the bucket is less than the rollout percentage, enable the flag. `H` is a deterministic hash function; `salt` produces independent groupings across flags if desired. In production, prefer your flag provider's bucketing mechanism or a stable algorithm with verified distribution.

For example: a subject hashing to bucket `07` will remain in the 10% cohort for that flag on subsequent requests. If the rollout increases to 25%, subjects in buckets `10` through `24` are added to the enabled set, while already-enabled subjects remain enabled.

Do not use process-unstable hashes or per-request random numbers. Nor should you use complex object hash codes that can change across code versions. If implementing custom bucketing, specify encoding, normalization, salt, algorithm, and tests to ensure identical results across runtimes and languages.

### 5.1. Illustrative Java bucketing example

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

public final class StableBucketing {
    private StableBucketing() {
    }

    public static int bucket(
            String flagKey,
            String subjectKey,
            String salt) {

        try {
            String input = flagKey + ":" + subjectKey + ":" + salt;
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(input.getBytes(StandardCharsets.UTF_8));

            long value = Integer.toUnsignedLong(
                    ByteBuffer.wrap(digest).getInt());

            return (int) (value % 100);
        } catch (Exception failure) {
            throw new IllegalStateException(
                    "Unable to calculate rollout bucket", failure);
        }
    }

    public static boolean isEnabled(
            String flagKey,
            String subjectKey,
            String salt,
            int percentage) {

        if (percentage < 0 || percentage > 100) {
            throw new IllegalArgumentException(
                    "percentage must be between 0 and 100");
        }

        return bucket(flagKey, subjectKey, salt) < percentage;
    }
}
~~~

This example only illustrates the stability principle. Production systems should use a tested bucketing implementation with explicit input normalization, and avoid inventing an algorithm that diverges from the provider when multiple services must share identical cohorts.

## 6. Flag evaluation architecture in serverless

A function can be invoked via HTTP, queues, or event buses. Each trigger constructs the evaluation context differently, yet application code should interact with a single port.

~~~mermaid
flowchart TB
    H["HTTP / Queue / Event"] --> AD["Trigger adapter"]
    AD --> CTX["Trusted evaluation context"]
    CTX --> APP["Application use case"]
    APP --> FLAG["Feature flag evaluator"]
    FLAG --> CACHE["Local snapshot / cache"]
    CACHE --> CFG["Flag configuration service"]
    APP --> PATH1["Old behavior"]
    APP --> PATH2["New behavior"]
~~~

Responsibilities can be separated into:

- **Configuration source:** manages flags, rules, environments, and rollouts.
- **Provider adapter:** communicates with a specific service or SDK.
- **Local cache:** holds downloaded snapshots to avoid network calls on every invocation.
- **Evaluator:** applies rules against the evaluation context.
- **Application code:** receives the evaluated decision and picks the behavior.

Application code should not call AWS AppConfig, LaunchDarkly, or vendor APIs directly across every business branch. Wrap the provider behind an internal interface or an open standard like OpenFeature to reduce coupling.

## 7. Defining the port in Java

A small interface can express the application's needs:

~~~java
import java.util.Map;

public record FlagContext(
        String subjectKey,
        Map<String, String> attributes) {

    public FlagContext {
        attributes = Map.copyOf(attributes);
    }
}

public record FlagDecision(
        boolean enabled,
        String variant,
        String reason,
        String configurationVersion) {
}

public interface FeatureFlagEvaluator {
    FlagDecision evaluate(
            String flagKey,
            FlagContext context,
            boolean defaultValue);
}
~~~

`subjectKey` is a verified, stable identifier. `attributes` contains only fields needed for targeting—avoid passing full user profiles or personal information into the evaluator.

A use case can evaluate a flag:

~~~java
public final class CheckoutService {
    private final FeatureFlagEvaluator flags;
    private final LegacyCheckout legacyCheckout;
    private final NewCheckout newCheckout;

    public CheckoutService(
            FeatureFlagEvaluator flags,
            LegacyCheckout legacyCheckout,
            NewCheckout newCheckout) {
        this.flags = flags;
        this.legacyCheckout = legacyCheckout;
        this.newCheckout = newCheckout;
    }

    public CheckoutResult checkout(
            CheckoutCommand command,
            FlagContext context) {

        FlagDecision decision = flags.evaluate(
                "new-checkout-flow",
                context,
                false);

        if (decision.enabled()) {
            return newCheckout.execute(command);
        }

        return legacyCheckout.execute(command);
    }
}
~~~

A default value of `false` falls back to the legacy path when the flag cannot be read. This is appropriate if the legacy path remains safe and supported. If a flag guards a risky operation—such as enabling a flow capable of writing corrupted data—the default must be chosen based on risk and may need to fail closed.

## 8. Safe flag evaluation when the provider fails

The flag provider may become unreachable due to networking, throttling, timeouts, expired credentials, or misconfiguration. The application must define behavior when evaluation fails.

Three common strategies exist:

| Strategy | Behavior | When appropriate |
|---|---|---|
| Fail open | Allow the default branch to proceed | Non-sensitive features where the default path is safe |
| Fail closed | Reject or disable the risky branch | Features that could corrupt data or incur high cost |
| Last known good | Use the most recent valid snapshot | Brief tolerance for slightly stale configuration |

No single default fits every flag. Define the default and failure policy for each flag when creating it. If the provider does not respond, the evaluator should return a decision with a clear `reason` for logs/metrics instead of throwing an exception that unexpectedly fails the entire request.

Never use last-known-good indefinitely. Enforce a max-stale age; once a snapshot is too old, switch to the default or defined safe policy. For system-protection kill switches, stale configuration can leave functions executing behavior meant to be stopped. Account for propagation speed and separate alerting mechanisms.

## 9. Caching flags in Lambda and FaaS

Execution environments may be reused across multiple invocations, yet the platform can terminate them at any time. Therefore:

- Static caches reduce configuration fetches within a single environment.
- Caches must never be treated as durable state stores.
- Different environments may temporarily hold different flag versions.
- Cold starts can spawn many environments that fetch configuration simultaneously.
- Concurrent invocations in the same environment must read snapshots thread-safely.

Avoid calling a remote flag service over the network on every request when avoidable. Doing so increases latency, cost, and pressure on the control plane, and introduces another failure dependency.

### 9.1. Time-bounded snapshot cache

A snapshot can contain a version, load timestamp, flag definitions, and metadata. Evaluators read immutable snapshots; refreshes build a new snapshot and swap the reference atomically.

Simple example:

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

public record FlagSnapshot(
        String version,
        Instant loadedAt,
        Map<String, Boolean> values) {

    public FlagSnapshot {
        values = Map.copyOf(values);
    }
}

public final class SnapshotFlagEvaluator
        implements FeatureFlagEvaluator {

    private final AtomicReference<FlagSnapshot> current;

    public SnapshotFlagEvaluator(FlagSnapshot initial) {
        this.current = new AtomicReference<>(initial);
    }

    public void replaceSnapshot(FlagSnapshot next) {
        current.set(next);
    }

    @Override
    public FlagDecision evaluate(
            String flagKey,
            FlagContext context,
            boolean defaultValue) {

        FlagSnapshot snapshot = current.get();
        boolean enabled = snapshot.values().getOrDefault(
                flagKey, defaultValue);

        return new FlagDecision(
                enabled,
                enabled ? "on" : "off",
                "local_snapshot",
                snapshot.version());
    }
}
~~~

This is a simple boolean snapshot example and does not yet model targeting rules or TTLs. A real implementation must map rules by key, enforce snapshot age checks, and ensure maps cannot be mutated after publication. `AtomicReference` ensures invocations observe either the complete old snapshot or the complete new snapshot, never a half-modified structure.

### 9.2. Refreshing and avoiding thundering herds

If every execution environment refreshes at the exact same moment, a scale-out event can flood the configuration service with concurrent requests. Mitigate load using:

- Jittered TTLs so environments do not refresh in lockstep.
- Exponential backoff on provider failures.
- Background refreshes if supported by the runtime and execution model.
- Loading snapshots during initialization or first use, then serving from cache.
- Local extensions/agents or caching built into the provider SDK.
- Bounded retry counts and timeouts.

In Lambda, background threads are not guaranteed to keep running when a function receives no invocations. If using background refresh, understand the runtime lifecycle and do not rely on those threads for timely updates. A synchronous refresh upon cache expiration can be simpler, provided it has a short timeout and clear fallback.

### 9.3. Consistency across environments

When increasing a rollout from 5% to 20%, execution environments may refresh snapshots at different times. For a brief period, the same user may see different evaluations if requests hit environments running different config versions.

To minimize issues:

- Use deterministic bucketing by flag key and subject key.
- Include the rollout percentage and salt in the snapshot version.
- Monitor which configuration version each environment is serving.
- Choose a TTL aligned with required propagation speed.
- Never use local flags to govern decisions requiring strict global consistency or carrying security impact.

If a change must take effect instantaneously, a TTL-based local cache may be insufficient. Use a control-plane mechanism or policy check with appropriate consistency guarantees, accepting its cost and latency trade-offs.

## 10. Managing flags with AWS AppConfig

AWS AppConfig is a service for managing and deploying application configuration. You can use AppConfig to distribute feature flags and dynamic configuration organized by application, environment, and configuration profile.

Core concepts:

- **Application:** logical grouping of configurations belonging to one application.
- **Environment:** environments such as dev, staging, or production.
- **Configuration profile:** type of configuration distributed, either feature flags or freeform configuration.
- **Hosted configuration version:** a configuration version stored in AppConfig or a supported source.
- **Deployment strategy:** defines how a configuration version rolls out over time and traffic.
- **Validator:** validates configuration before deployment.

AppConfig helps deploy changes gradually, monitor deployments, and roll back when issues arise. The service manages configuration distribution; the application still needs to evaluate flags with the right context and handle caching/fallbacks.

### 10.1. Fetching configuration from Lambda

You can use the AWS AppConfig Agent or an appropriate Lambda extension to serve cached configuration to the function via a local endpoint. Another option is calling the AWS AppConfig Data APIs directly in an adapter.

Extension model:

1. The Lambda execution environment starts the function and the extension.
2. The extension fetches configuration from AppConfig per deployment configuration.
3. The function reads the snapshot from the local endpoint.
4. The extension refreshes periodically and caches the response.
5. The function continues using the snapshot while handling invocations.

This reduces direct calls from the function to the control plane. Configure the extension, IAM permissions, application/environment/profile identifiers, and polling interval properly. Extensions can affect init duration, memory, and telemetry; benchmark before enabling broadly.

### 10.2. Decoupling the AppConfig adapter from application core

`FeatureFlagEvaluator` can be implemented via an AppConfig adapter:

~~~java
public final class AppConfigFeatureFlagAdapter
        implements FeatureFlagEvaluator {

    private final AppConfigSnapshotProvider snapshots;

    public AppConfigFeatureFlagAdapter(
            AppConfigSnapshotProvider snapshots) {
        this.snapshots = snapshots;
    }

    @Override
    public FlagDecision evaluate(
            String flagKey,
            FlagContext context,
            boolean defaultValue) {

        FlagSnapshot snapshot = snapshots.current();
        // Look up the flag and apply targeting rules with context.
        // If the flag is missing or the snapshot is invalid,
        // return the configured policy default.
        boolean enabled = snapshot.values().getOrDefault(
                flagKey, defaultValue);

        return new FlagDecision(
                enabled,
                enabled ? "on" : "off",
                "appconfig_snapshot",
                snapshot.version());
    }
}
~~~

`AppConfigSnapshotProvider` is an illustrative interface. A real adapter calls the extension's local endpoint or the AWS AppConfig Data API, parses the schema, and constructs the snapshot. Use cases depend only on `FeatureFlagEvaluator`, not the AppConfig SDK.

### 10.3. Validators and deployment strategies

Before deploying configuration, validate that:

- Flag keys are unique.
- Data types match the schema.
- Percentages fall within 0–100.
- Rules have explicit priorities.
- Default values are declared.
- Flags have owners and required metadata.
- No sensitive or invalid targeting attributes are included.

Use deployment strategies with bake time and gradual rollout when configuration changes affect many functions. Monitor error rates, duration, throttles, and business metrics during rollout. If you only learn about problems from user complaints, the rollout lacks adequate guardrails.

## 11. OpenFeature integration

OpenFeature is an open standard providing a vendor-neutral API for feature flag evaluation. Applications code against the OpenFeature API, while specific providers connect to the underlying flag system.

Benefits:

- Reduces direct coupling to a single vendor SDK.
- Allows swapping providers with minimal application code changes.
- Supports evaluation contexts and multiple flag value types.
- Simplifies using test providers or no-op providers during testing.

OpenFeature is not a flag storage service. You still need a provider—such as an AppConfig adapter or another feature management service—along with processes for managing rules, rollouts, and edit permissions.

One clean structure has an adapter translate internal `FlagContext` into OpenFeature's evaluation context. If you switch providers, only the provider adapter and bootstrap configuration change; use cases keep calling your internal port or chosen standard API.

## 12. Targeting by group and environment

Targeting rules need a readable, testable structure. A rule may include:

- Priority or evaluation order.
- Environment conditions.
- Segment or subject-attribute conditions.
- Rollout percentage.
- Returned value or variant.
- Start/end timestamps.
- Owner and change rationale.

Example rule table:

| Priority | Condition | Outcome |
|---:|---|---|
| 1 | Environment is test and flag is locked | OFF |
| 2 | Tenant is on exclusion list | OFF |
| 3 | Subject is on internal allowlist | ON |
| 4 | Tenant belongs to beta cohort | ON |
| 5 | Bucket is less than 10 | ON |
| 6 | No rule matched | OFF |

Specific rules must establish precedence. This table is just an example: if exclusions must override allowlists, give exclusions higher priority. Never leave two conflicting rules where the evaluator picks an undocumented winner.

### 12.1. Grouping by tenant

In multi-tenant SaaS, rolling out by tenant avoids situations where some users in an organization see a feature while colleagues do not. However, features that do not impact shared data or workflows can be rolled out per user.

Context should carry both verified subject and tenant identifiers:

~~~java
FlagContext context = new FlagContext(
        authenticatedUser.internalId(),
        Map.of(
                "tenantId", authenticatedUser.tenantId(),
                "environment", deploymentEnvironment,
                "clientVersion", clientVersion));
~~~

Never extract `tenantId` directly from a request body for targeting unless the backend has verified the user belongs to that tenant. Accidentally placing a tenant into beta can expose features or disrupt the entire organization's workflow.

### 12.2. Environments and production safety

Do not share flag configurations across dev, staging, and production when environments serve different purposes. Each environment needs its own profile or namespace, with appropriate edit permissions and approval workflows.

Enabling a flag in staging does not mean it should automatically enable in production. Configuration promotions require review, versioning, and audit trails just like other deployment changes.

## 13. Variants and A/B experiments

A boolean flag only has on/off states. Experiments may require multiple variants, such as A/B/C:

- Variant A: current interface.
- Variant B: single-page checkout.
- Variant C: step-by-step checkout.

The evaluator returns the variant along with assignment metadata. Subjects must stay assigned to the same variant throughout the experiment, keyed by stable subject and experiment identifiers.

When designing an experiment, specify:

- Whether the randomization unit is user, tenant, or session.
- Primary metrics and guardrail metrics.
- Experiment duration and sample size.
- How to handle users switching devices or tenants.
- How to exclude bots, employees, and invalid traffic.
- Stopping rules if error rates or latency degrade.

Never randomize variants per invocation. If a user sees multiple variants during the same journey, experiment data becomes noisy and the user experience turns inconsistent.

Feature flags distribute variants; concluding which variant performs better requires proper experimental analysis. Never draw conclusions from just the first few conversions.

## 14. Combining feature flags with deployments and canaries

Deployment and feature rollout are two separate activities:

- **Deployment:** shipping a new code version to an environment.
- **Feature rollout:** deciding who executes the new code branch.

You can deploy code first with the flag OFF. After smoke tests confirm safety, turn it on for internal staff, then gradually ramp up user percentages. This decouples artifact deployment risk from behavior activation risk.

Canary deployments typically route a fraction of traffic to a new function version or alias. Feature flag rollouts can enable a new code path within that same version. Both mechanisms can work together, provided you avoid unintentionally multiplying percentages.

For example: 10% of traffic hits the new Lambda version, and inside that version only 20% of subjects have the feature flag enabled. The share of overall requests hitting both the new version and the new branch is not 20% system-wide; if independent, it is roughly 2%. Track both the version and flag variant dimensions to interpret metrics accurately.

## 15. Kill switches and incident control

Operational flags can disable a feature when a dependency degrades or metrics cross thresholds. For example, pause thumbnail generation if an image-processing service is overloaded while keeping the main API running.

A kill switch needs:

- A safe default.
- An owner and authorized operators.
- A fast, tested update path.
- Metrics confirming the flag took effect.
- A clear fallback path.
- Documentation on how to re-enable and criteria for removal.

Not every kill switch should rely on a long cache. If disabling within seconds is required, adjust the cache TTL or use a faster distribution mechanism. If functions hold stale snapshots, flipping a switch in the control plane may not take effect immediately across all environments.

Do not use feature flags as a substitute for circuit breakers. Flags control predefined behaviors; circuit breakers react dynamically to dependency failure states based on thresholds and timers. The two mechanisms complement each other but serve different purposes.

## 16. Evaluating flags in HTTP, queue, and scheduled functions

### 16.1. HTTP-triggered functions

HTTP adapters authenticate callers, construct context, and evaluate flags. When results affect the response, log or trace the variant and flag version without recording PII.

If a client needs to know whether a capability is available, the backend can return capabilities in the response. However, the client must never enforce access itself; the backend must re-verify permissions when actions arrive.

### 16.2. Queue-triggered functions

Messages may be redelivered or processed many minutes later. If an evaluator uses percentage rollouts by user/tenant, preserve a stable subject key inside the event. When no specific subject exists, evaluate by tenant, event type, or a global policy.

Decide when flags are evaluated:

- **At event ingestion:** the decision is stored in the event or metadata so retries follow the same decision.
- **At processing time:** each retry may observe updated configuration.

If a workflow requires consistency, store the variant or flag configuration version alongside processing state so retries do not switch behavior mid-flight. For risky operations, avoid letting a retry hours later silently switch to a different business branch just because a flag changed.

### 16.3. Scheduled functions

Scheduled functions generally lack a user context. Flags can target environments, job types, tenant batches, or partition percentages. For high-impact jobs, explicitly log the config version and scope of processed data.

If a job iterates per tenant, roll out by tenant. If a job processes partitions, use a stable partition key so a partition does not flip branches between retries.

## 17. Impact on cold starts, latency, and cost

Flag evaluation adds overhead if every evaluation calls a remote API. In serverless, this cost multiplies with invocations and concurrency.

Factors to consider:

- SDK or provider initialization time.
- Initial configuration download time.
- Cache lookup overhead.
- Refresh frequency per execution environment.
- Snapshot size and deserialization cost.
- Memory consumed by SDKs, extensions, and caches.
- Metrics/logs emitted by evaluations.

Generally, local evaluation against a cached snapshot has much lower latency than remote calls. Initialize the provider once per execution environment, reuse thread-safe clients, and refresh according to TTL. Never create a new SDK client inside every handler invocation.

However, do not inflate TTLs solely to save cost if the flag is an operational control needing rapid response. Pick TTLs based on propagation requirements, staleness tolerance, and failure impact when the config service errors.

## 18. Security and flag governance permissions

Anyone with permission to edit flags can change production behavior without deploying code. Therefore, flag administration permissions are sensitive operational privileges.

Apply these controls:

- Separate permissions for viewing, editing, approving, and deploying configuration.
- Isolate permissions across dev, staging, and production.
- Audit every change, including actor, timestamp, old value, and new value.
- Require peer review or approval for high-impact flags.
- Protect management APIs with IAM/SSO and MFA per organizational policy.
- Never grant public applications write access to flag configuration.
- Never put secrets into flag values if the flag system is not a secret manager.
- Minimize context attributes to avoid sending PII to external providers.

Flags are not secret stores. Flag values may be cached, logged, or propagated through many components. Passwords, private keys, and tokens belong in a secret manager.

## 19. Observing and measuring rollout impact

Not every flag evaluation needs full logging, yet enough telemetry must exist to understand how a rollout is behaving.

Useful fields to record:

- `flagKey`.
- `variant` or enabled state.
- `configurationVersion`.
- `evaluationReason`.
- `environment`.
- `functionVersion`.
- `requestId` or `eventId`.
- Anonymized subject cohort if needed for analysis.

Never use `subjectId` or `userId` as a CloudWatch metric dimension because of high cardinality. For cohort analysis, emit metrics by variant, environment, or bounded groups; detailed per-subject telemetry belongs in analytics systems with proper access control and retention.

Track both technical and business metrics:

- Error rates, p95/p99 duration, throttles.
- Queue age, retries, and DLQs.
- Success rates per variant.
- Conversion or completion rates.
- Database load and external API errors.
- Count of environments running older config versions when observable.

Rollouts need guardrails. If error rates or latency breach thresholds, pause percentage increases or disable the flag. Never ramp up a rollout merely because no users have reported bugs yet.

## 20. Testing feature flags

A flagged feature creates multiple execution paths. Test both branches as well as failure modes.

Minimum test matrix:

| Case | Expected outcome |
|---|---|
| Flag OFF | Legacy path runs |
| Flag ON | New path runs |
| Missing flag | Default value is used |
| Provider timeout | Defined fail-open/closed policy applies |
| Stale snapshot | Max-stale policy applies |
| Subject in allowlist | Decision matches rule |
| Subject in exclusion | Excluded per precedence |
| Rollout percentage changes | Cohort remains stable per algorithm |
| Context missing attribute | Default or fallback rule applies |
| Retried event | Idempotent behavior and variant follow policy |

You can use a fake evaluator in unit tests:

~~~java
public final class FixedFlagEvaluator
        implements FeatureFlagEvaluator {

    private final boolean enabled;

    public FixedFlagEvaluator(boolean enabled) {
        this.enabled = enabled;
    }

    @Override
    public FlagDecision evaluate(
            String flagKey,
            FlagContext context,
            boolean defaultValue) {

        return new FlagDecision(
                enabled,
                enabled ? "on" : "off",
                "test_provider",
                "test-version");
    }
}
~~~

Tests can inject an ON or OFF evaluator to exercise both paths without calling a real flag service. Integration tests must verify the adapter parses the schema, refreshes snapshots, handles timeouts, and enforces rule precedence.

## 21. Flag lifecycle and cleanup

Flags introduce extra code branches and test combinations. A release flag rolled out to 100% that remains in the codebase adds unnecessary complexity and makes it unclear which branch is still active.

Typical lifecycle:

1. Create the flag with an owner, purpose, default, and expected expiration date.
2. Ship code containing both old and new branches.
3. Verify in dev/staging.
4. Enable for internal allowlists.
5. Roll out by cohort or percentage.
6. Monitor guardrails and business metrics.
7. Ramp to 100% once criteria are met.
8. Delete the old branch and remove the flag from configuration.
9. Remove rollout-only rules, dashboards, or alerts if no longer needed.

Operational kill switches may live longer, but still require an owner, documentation, and periodic testing. Never let an unowned flag turn into a production toggle nobody dares touch.

## 22. Common mistakes

**Using flags for authorization:** Users can call APIs directly. The backend must always enforce permissions independently.

**Randomizing rollouts on every invocation:** The same user keeps bouncing between branches. Use deterministic bucketing by subject/tenant and flag key.

**Calling the provider on every request:** Increases latency, cost, and network fragility. Use snapshot/caching with TTLs and fallbacks.

**Caching indefinitely:** Some environments fail to receive updated kill switches. Enforce max-stale limits, versions, and refresh procedures.

**Treating static caches as durable state:** Execution environments can be replaced at any time. Persist long-lived business decisions in durable storage.

**Targeting on unverified client-supplied data:** Users can spoof tenant or role attributes to enter restricted cohorts. Use verified context.

**Unclear rule precedence:** Allowlists and exclusions can conflict. Document evaluation order and write tests.

**Undefined behavior on provider failure:** A config failure brings down the entire function or turns on features accidentally. Define defaults and failure policies per flag.

**Changing flags mid-retry:** A single event gets processed under two different business versions. Persist the variant/config version when consistency is required.

**Ignoring guardrails:** Rollouts continue increasing even as latency or error rates worsen. Tie rollouts to alarms and stop criteria.

**Never cleaning up flags:** Legacy and new paths linger, multiplying test combinations. Set expiration dates and owners.

**Storing secrets inside flags:** Flag services do not replace secret managers. Store secrets in a secret manager and pass references only.

## 23. Feature flag implementation workflow for Java Lambda

Follow this workflow:

1. **Clarify purpose:** Is the flag for a release, operational toggle, or experiment?
2. **Choose targeting unit:** User, tenant, account, partition, or environment?
3. **Define defaults:** When the flag is missing or the provider fails, what behavior is safe?
4. **Define rules:** Allowlists, exclusions, segments, percentages, and precedence.
5. **Design the port:** Application core depends on a provider-neutral interface.
6. **Select provider:** AWS AppConfig, a feature management platform, or an OpenFeature provider.
7. **Configure caching:** TTL, jitter, max-stale, refresh, and last-known-good policies.
8. **Build trusted context:** Authenticate subject, tenant, and rule attributes.
9. **Implement both code paths:** Ensure both legacy and new branches are tested.
10. **Roll out internally, then ramp gradually:** Track technical and business metrics.
11. **Define rollback:** Toggle the flag off or revert to a known code/config version.
12. **Clean up:** Delete the old branch after rollout finishes and record closure with the owner.

## 24. Pre-production checklist for feature flags

- [ ] Every flag has a stable key, owner, purpose, and planned expiration date.
- [ ] Flags are clearly distinguished from runtime configuration and authorization.
- [ ] Default values and provider-failure behavior are explicitly defined.
- [ ] Targeting uses stable, trustworthy subject/tenant keys.
- [ ] No PII or unverified client-supplied attributes are used for rollout decisions.
- [ ] Rule precedence and exclusion/allowlist resolution are documented.
- [ ] Percentage rollouts use deterministic bucketing.
- [ ] Lambda does not call remote providers on every invocation unnecessarily.
- [ ] Caches define TTL, jitter, max-stale, and fallback behavior.
- [ ] Snapshots are swapped thread-safely under concurrent invocations.
- [ ] Message retries do not accidentally switch variants when business consistency is needed.
- [ ] Flags never replace backend authorization checks.
- [ ] Metrics and guardrails exist to halt rollouts during incidents.
- [ ] Production flag edit permissions are restricted and audited.
- [ ] No secrets are stored in flag configuration.
- [ ] Tested ON, OFF, missing, stale, timeout, and rule-conflict cases.
- [ ] Rollback and post-rollout flag cleanup plans are ready.
- [ ] Latency, cold start, memory, and cost impacts have been evaluated.

## Conclusion

Feature flags decouple deploying code from enabling behavior for users. Targeting via allowlists, cohorts, or percentages supports controlled releases; operational toggles help mitigate incidents; experiment flags enable comparing variants.

In serverless, use stable identifiers, authenticated contexts, and time-bounded caches because each execution environment can hold different snapshots temporarily. Wrap flag providers behind a port or standard like OpenFeature; AWS AppConfig can manage and distribute configuration, while Lambda extensions/agents help cache near the function. Always define defaults, staleness policies, retry behavior, guardrails, governance permissions, and cleanup dates. Feature flags control rollout behavior; authorization must still be enforced independently on the backend.
