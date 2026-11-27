# Testing Behavior When Flags Are Enabled and Disabled

Feature flags allow changing application behavior without necessarily releasing a new binary. The same artifact can serve users through two logic branches: the current branch when the flag is off, and the new branch when the flag is on. This release approach supports gradual rollouts, controlled experimentation, and rapidly disabling a feature when an incident is detected.

However, a feature flag creates multiple states that the pipeline must verify. Testing only the enabled branch can leave the system breaking current behavior when the flag is off. Testing only the disabled branch means new code might never be executed before turning it on for users. Targeting configurations, default values, errors fetching flag state, and runtime state transitions can also introduce bugs.

**Testing both when a flag is enabled and when it is disabled** means verifying both behavioral branches against the feature's contract, while also testing the conditions that cause the application to select each branch. The goal is to ensure the new feature works properly when enabled, current behavior is preserved when disabled, and the system can transition safely across the release lifecycle.

## 1. What does a feature flag change?

A feature flag is a runtime or configuration decision that controls whether a piece of behavior executes. Examples:

- Release toggle: deploy code early, enable the feature later when ready.
- Experiment toggle: split users into variants for measurement.
- Operational toggle: disable a resource-intensive capability when the system is under heavy load.
- Permission/entitlement toggle: determine which users or groups may use a capability.
- Kill switch: quickly stop a risky behavior during an incident.

Not every type of flag has the same semantics. A flag used to expose a new feature may default to off; a flag controlling a safety mode may need to default to on. Default values must be determined by risk and safe application behavior, rather than mechanically applying a "every flag is false" rule.

For example, an order service might add a new pricing flow:

```java
public Price calculate(Order order, EvaluationContext context) {
    if (featureFlags.isEnabled("new-pricing", context, false)) {
        return newPricing.calculate(order);
    }
    return legacyPricing.calculate(order);
}
```

When the flag is off, the application uses the legacy pricing logic. When the flag is on, the application uses the new pricing engine. Both branches represent behavior that must be tested within the same artifact version.

## 2. Defining the contract for each state

Before writing tests, clearly specify what the application must do in each state:

| State | Behavior to verify |
|---|---|
| Flag OFF | Preserves existing behavior; triggers no side effects exclusive to the new feature |
| Flag ON | Executes the new behavior per requirements; data and outputs are accurate |
| Flag missing | Uses the defined default value and behaves safely |
| Flag provider unreachable | Applies policy-defined fallback; does not cause unexpected application failures |
| Invalid flag value | Does not interpret arbitrarily; uses fallback and logs configuration error |
| User outside cohort | Does not enable the feature for that user |
| User inside cohort | Enables the exact specified variant or behavior |

The contract must state both observable outputs and side effects. For example, when the flag is off, the API response may stay on the old schema, emit no new events, and write no data into tables exclusive to the new feature. When the flag is on, responses and events must conform to the new contract.

For multi-state flags such as `control`, `treatment-a`, and `treatment-b`, do not force them into Booleans in test design. Verify each supported variant and the fallback behavior when an unrecognized value is returned.

## 3. Testing the OFF branch: protecting existing behavior

The OFF branch is often overlooked because the new feature is not enabled yet. Yet during a progressive rollout, the majority of users may still run on this branch. A bug in the OFF branch can impact all existing users.

Things to verify:

- Business outcomes match the contract prior to adding the feature flag.
- API responses, status codes, and schemas do not change unexpectedly.
- Services or APIs needed only by the new feature are not called.
- New events, messages, or records are not written if the OFF branch is not supposed to produce them.
- Existing processing order, transactions, and calculation rules remain unchanged.
- New dependencies used only by the ON branch are not required when running the OFF branch.
- Logging and metrics do not throw errors or expose sensitive data.

Do not check only whether the return value matches or differs. Inspect critical side effects such as payment gateway calls, database writes, message publishing, and audit events. For instance, when the flag is off, the legacy flow may need to continue using the current payment provider and send zero requests to the new provider.

A strong way to protect the OFF branch is characterization/regression testing: capture valid inputs and outputs of the legacy behavior before making changes, then re-run them with the flag OFF.

## 4. Testing the ON branch: thoroughly verifying the new feature

The ON branch must be tested against the feature's acceptance criteria. Do not stop at confirming the code branch executes.

Aspects typically requiring verification:

- Business outcomes with valid, boundary, and invalid inputs.
- Access permissions and eligibility rules.
- Integration with databases, APIs, message brokers, or external services.
- Validation, error handling, timeouts, and retries.
- Events or side effects generated exactly once with accurate payloads.
- Compatibility with both legacy and new data.
- Metrics, logs, and traces containing sufficient information to monitor the feature.
- Performance and resource usage as the enabled user volume grows.

In the pricing example, the ON branch needs tests for discount rules, rounding, currencies, taxes, failures fetching rate tables, and consistency between displayed prices and prices recorded in orders.

If the new feature relies on new APIs or schemas, also test scenarios where dependencies are not yet ready. Never assume flag ON means every dependency is operating flawlessly.

## 5. Testing default values and flag provider failures

Feature flags may be loaded from config files, environment variables, SDKs, or a remote flag management service. In practice, configs can be missing, or the provider may time out or return invalid values.

Tests must answer:

- If the flag is undeclared, which value does the application use?
- If the SDK has not finished initializing, is the behavior safe?
- If the flag service is temporarily unreachable, does the application use a cached value or the default?
- How long may a stale cached value be used?
- If config changes data types or mistypes a variant name, how does the application handle it?
- When the provider recovers, does the application pick up the updated value properly?

Fallback depends on the flag type. For a release toggle guarding a new feature, default OFF is usually the safe choice to preserve known behavior. For a kill switch meaning "allow risky capability," the default must follow fail-safe principles—likely disabling the capability when state cannot be determined. Conversely, a protective toggle may require default ON. Each flag's documentation must justify this choice.

Do not let a flag provider outage take down the entire application when a safe fallback is possible. Conversely, never silently enable a new feature when config cannot be read if doing so increases business risk.

## 6. Testing targeting and cohort rollouts

Many systems do not enable a flag for all users at once. Flags may target by user ID, tenant, region, plan, internal group, or traffic percentage.

Cases to test:

- Users inside the enabled cohort receive the new behavior.
- Users outside the cohort continue receiving the legacy behavior.
- Missing or invalid user/tenant IDs fall back to the default.
- Precedence rules across targeting conditions operate properly.
- A user stays in the same cohort across requests if policy requires stable bucketing.
- Changing rollout percentages does not unexpectedly flip users back and forth between branches.
- Internal groups or test accounts are enabled via explicit rules.

When using percentage rollouts, ensure stable bucketing based on an appropriate key, such as user ID or tenant ID. Do not generate a fresh random draw per request if the goal is keeping a user in the same cohort over a phase. When increasing from 10% to 25%, understand which users will be added and whether switching cohorts affects data or user experience.

Example targeting matrix:

| Context | Rule | Expected result |
|---|---|---|
| Internal user | Internal allowlist | ON |
| Pilot tenant | Tenant in allowlist | ON |
| User in rollout bucket | Bucket below current threshold | ON |
| User outside bucket | Bucket above threshold | OFF |
| Missing user ID | Cannot evaluate cohort | Use defined default |
| Excluded tenant | Explicit deny/exclusion | OFF even if matching broader rule |

If both allow and deny rules exist, define explicit precedence and test conflicting cases. Never let rule ordering in a UI dashboard become implicit behavior that the team does not understand.

## 7. Testing ON/OFF state transitions

Flags are often changed while the application is running. Therefore, test state transitions, not just static states.

Key transitions:

- OFF → ON: the new feature begins taking effect.
- ON → OFF: the system reverts to legacy behavior or safe mode.
- OFF → ON → OFF: verify toggling on, off, and back on leaves no broken state behind.
- Provider available → unavailable → available: verify caching and fallbacks.

Pay special attention to data created during the ON period. Once the flag turns off, the application may still have to read that data or remain compatible with already-created records and events. Turning off a flag does not automatically roll back database migrations, emitted messages, sent emails, or completed transactions.

If an action is irreversible—such as submitting a payment or sending a notification—tests must specify what happens if the flag flips mid-flight. Never assume toggling a flag cancels side effects that have already occurred.

## 8. Testing data and database migrations

Feature flags are commonly used to decouple code deployment from feature activation. However, database schemas and persisted data can make disabling a flag nontrivial.

For example, suppose a new feature adds a `pricing_model` column:

1. Deploy an expanded schema that remains compatible with old code.
2. Deploy code capable of reading both old and new schemas; keep the flag OFF by default.
3. Enable the flag for a pilot cohort and write data using the new schema.
4. Verify data integrity, readability, and downstream consumers.
5. Remove legacy columns or compatibility paths only after the feature stabilizes and the rollback window expires.

Tests should cover:

- Old code running against the expanded schema.
- New code running with the flag OFF.
- New code running with the flag ON.
- Records created by the ON branch remaining readable when the flag is OFF if business requirements demand it.
- Application rollback not failing due to incompatible migrations.

This is why the expand-and-contract strategy is recommended. Destructive schema changes or altering data semantics before the rollback window ends can prevent turning off the flag from restoring the system.

## 9. Placing tests across multiple layers

There is no need to test every combination end-to-end. Distribute tests by cost and type of evidence:

| Layer | What to test | Purpose |
|---|---|---|
| Unit tests | Flag ON/OFF, defaults, fallbacks, rule selection | Fast, deterministic verification of branching logic |
| Component tests | Old/new service behavior, side effects, transactions | Verify contracts of individual components |
| Integration tests | Database, message broker, APIs, cache | Verify cross-system interactions |
| Contract tests | Schemas/APIs/events in both states | Maintain compatibility with consumers/providers |
| End-to-end tests | User journeys under ON and OFF | Confirm system-wide behavior |
| Staging/canary | Targeting, rollout, metrics, and state transitions | Validate near-production configuration before expanding |

Unit tests should cover both branches because they are fast and easy to control flag state in. Integration tests focus on differences that produce side effects. E2E tests should select a few representative business flows to validate the whole system, avoiding duplicating every case across every layer.

## 10. Making feature flag tests deterministic

Tests must not depend on live flag states managed in production. If CI reads directly from a remote flag service, the exact same commit could produce different results depending on timing or an operator's recent change.

Do the following:

- Inject an interface or provider allowing tests to set flag state explicitly.
- Use deterministic fakes/stubs in unit tests.
- Use versioned configuration fixtures in integration tests.
- Record a snapshot or version of the flag configuration when running staging tests.
- Never use production secrets or production flag environments in CI validation.
- Test remote provider connectivity separately in an appropriate job rather than making every unit test network-dependent.
- Reset flag state between tests to avoid state leakage.

Example Java interface:

```java
public interface FeatureFlags {
    boolean isEnabled(
        String key,
        EvaluationContext context,
        boolean defaultValue
    );
}
```

Tests can use a fixed implementation:

```java
final class FixedFeatureFlags implements FeatureFlags {
    private final Map<String, Boolean> values;

    FixedFeatureFlags(Map<String, Boolean> values) {
        this.values = Map.copyOf(values);
    }

    @Override
    public boolean isEnabled(
        String key,
        EvaluationContext context,
        boolean defaultValue
    ) {
        return values.getOrDefault(key, defaultValue);
    }
}
```

With this fake, tests can instantiate two separate configurations: one returning OFF and one returning ON. There is no need to modify state in a remote flag service to exercise either branch.

## 11. Unit test example for both branches

Example using JUnit 5 and a pricing service:

```java
class PricingServiceTest {
    @Test
    void usesLegacyPricingWhenFlagIsOff() {
        FeatureFlags flags = new FixedFeatureFlags(
            Map.of("new-pricing", false)
        );
        PricingService service = new PricingService(
            flags,
            new LegacyPricing(),
            new NewPricing()
        );

        Price result = service.calculate(sampleOrder(), testContext());

        assertEquals(expectedLegacyPrice(), result);
    }

    @Test
    void usesNewPricingWhenFlagIsOn() {
        FeatureFlags flags = new FixedFeatureFlags(
            Map.of("new-pricing", true)
        );
        PricingService service = new PricingService(
            flags,
            new LegacyPricing(),
            new NewPricing()
        );

        Price result = service.calculate(sampleOrder(), testContext());

        assertEquals(expectedNewPrice(), result);
    }
}
```

Constructor names and fixtures are illustrative and should be adapted to the project's codebase. Both tests should verify concrete business outcomes. If two algorithms produce identical outputs on trivial inputs, pick inputs that highlight the difference or verify side effects/interactions to prove the right branch executed.

Beyond return values, you can verify that the OFF branch does not call `NewPricing` and the ON branch does not call `LegacyPricing` if the contract mandates executing only one implementation. Avoid asserting excessive internal details outside the contract, as that makes tests brittle during refactoring.

## 12. Managing multiple feature flags and avoiding combinatorial explosion

With n independent Boolean feature flags, the theoretical number of combinations is 2^n. Six flags produce 64 combinations; ten flags produce 1,024 combinations. Not every combination is meaningful or needs an E2E run.

To scope testing effectively:

1. Identify which flags interact directly around data, APIs, permissions, or side effects.
2. Thoroughly test ON/OFF for each critical flag at the unit/component level.
3. Test pairs of flags that have dependencies or potential conflicts.
4. Use pairwise/combinatorial testing for large configuration spaces where appropriate.
5. Select a small set of risk-driven representative end-to-end scenarios.
6. Test invalid or policy-forbidden states.

Pairwise testing ensures every pair of values appears at least once in the test suite, though it does not prove every interaction among three or more flags is bug-free. High-risk combinations still need explicit tests.

Model dependencies between flags explicitly. For example, `new-checkout` is only valid when `new-cart-api` is already enabled. If configuration allows enabling checkout before the API is ready, tests should verify the application rejects that configuration or applies the defined fallback.

## 13. Checking coverage and evidence in CI

The pipeline should prove both ON and OFF branches were executed in mandatory test suites. Branch coverage helps surface unexecuted branches, though coverage never replaces assertions on outcomes and side effects.

A reference CI job:

```yaml
jobs:
  feature_flag_tests:
    runs-on: ubuntu-24.04
    steps:
      - name: Checkout
        uses: actions/checkout@<FULL_COMMIT_SHA>
      - name: Run unit and component tests
        run: ./gradlew test componentTest
      - name: Publish test reports
        if: always()
        run: ./gradlew aggregateTestReports
```

Action SHAs and tasks `componentTest` and `aggregateTestReports` are placeholders to be replaced with actual project configuration. Reports should capture commit SHA, test run, flag configuration fixture/version, and results. If the reporting job runs after a test failure, the overall job status must still reflect the failure.

For staging or canary runs, record cohort/targeting configuration version, artifact digest, flag change timestamps, and metrics across the observation window. Never log personal data or secrets in test reports; record only necessary identifiers per privacy policy.

## 14. Feature flags need a lifecycle

Feature flags should not live forever without an owner. Long-lived flags add extra logic branches, multiply combinations, and complicate test suites.

When creating a flag, record:

- Name/key and description of the controlled behavior.
- Flag type and safe default value.
- Responsible owner.
- Creation date and planned review/removal date.
- Dependencies or related flags.
- Permitted user groups/environments.
- Mandatory tests for ON, OFF, and fallbacks.

Once rollout completes:

1. Confirm the new feature is stable and reverting to the legacy branch is no longer required.
2. Remove the flag and obsolete code branches in a reviewed change.
3. Delete old targeting rules, dashboards, and overrides.
4. Update tests to retain only supported behavior.
5. Verify databases/schemas after the rollback window expires before cleaning up backward-compatibility layers.

Do not remove a flag before confirming all environments share the same behavior and no consumer still requires the legacy branch. Note that kill switches or operational toggles may need to remain long-term if they serve as operational safety mechanisms.

## 15. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Testing only flag ON | Legacy behavior may break when OFF | Maintain regression tests for OFF |
| Testing only flag OFF | New code remains unverified | Test ON before opening to cohorts |
| Using live flag provider in unit tests | Results depend on network and external config | Inject deterministic fakes/stubs |
| Skipping default and provider failure tests | Config errors can accidentally enable features | Test missing/invalid/unavailable states |
| Asserting responses only | Unintended side effects go unnoticed | Verify events, writes, API calls, and transactions |
| Random bucketing per request | Users continuously flip cohorts | Use stable bucketing keyed by identity |
| Enabling flag with incompatible schema | Data errors or unsafe rollback | Use expand-and-contract and test both branches |
| Running too many E2E combinations | Slow, hard-to-maintain pipeline | Layer tests and select combinations by risk |
| Keeping old flags indefinitely | Bloated logic branches and testing debt | Enforce owners, expiry dates, and cleanup processes |

## 16. Feature flag ON/OFF testing checklist

- [ ] Every flag has a description, owner, type, default, and safe behavior when the provider fails.
- [ ] Separate unit/component tests cover both ON and OFF branches.
- [ ] The OFF branch preserves the legacy contract and creates no unexpected new side effects.
- [ ] The ON branch satisfies acceptance criteria and tests dependency failures.
- [ ] Missing flags, invalid values, timeouts, and cached values are tested.
- [ ] Targeting, allowlists/denylists, percentage rollouts, and stable bucketing are tested.
- [ ] Transitions OFF → ON and ON → OFF are tested, including already-generated data/side effects.
- [ ] Schemas and migrations remain compatible with old/new code throughout the rollback window.
- [ ] Tests use deterministic fakes/config fixtures without depending on the production flag service.
- [ ] Flag combinations are chosen based on dependencies and risk rather than relying solely on pairwise testing.
- [ ] CI archives test reports, commit, artifact, and flag configuration version.
- [ ] Flags have a lifecycle, owner, and removal plan when no longer needed.

Testing both states turns feature flags into a controllable release mechanism. When the OFF branch safeguards current behavior, the ON branch is thoroughly verified, and fallbacks and targeting are tested, teams can deploy code first and open features gradually while retaining the ability to disable or recover whenever needed.
