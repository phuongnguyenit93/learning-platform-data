# Defining Behavior When No Provider Exists or Multiple Providers Match

In Java extensibility architecture, a system typically discovers **providers** (implementations of an interface or Service Provider Interface, SPI) and then selects a provider that satisfies the current request. The crucial problem is not merely *finding providers*, but making **predictable decisions** when no candidate is found, when multiple candidates are found, or when the chosen provider fails to initialize or execute.

A sound selection policy should answer four questions upfront:

1. **No providers registered:** should the application fail, skip the feature, or use a built-in default?
2. **Providers exist, but none match the request:** is a fallback allowed, and does that fallback actually support the request?
3. **Multiple providers match:** prefer explicit configuration, priority score, unique-match requirement, or coordinate multiple providers?
4. **Provider is valid, but fails while loading or running:** stop, try another provider, or report a business error? This is a different failure from “no provider”.

Outcomes must never depend on which JAR appears first on the classpath or which provider happens to be iterated first.

## 1. Distinguishing Discovery, Eligibility, Selection, and Execution

Suppose an application exposes a `DocumentRenderer` interface for rendering documents; JARs provide `PdfRenderer`, `HtmlRenderer`, or a fallback provider. Four steps must be kept distinct:

```text
Available JAR / module list
             |
             v
[1] DISCOVER: find and instantiate providers
             |
             v
[2] FILTER: which providers support the request?
             |
             v
[3] SELECT: one provider, multiple providers, or fallback?
             |
             v
[4] EXECUTE: invoke selected provider, handle errors and resources
```

- **No provider found:** the registry or discovered set is empty. This can indicate a missing JAR, a missing service declaration, or an uninstalled optional feature.
- **No matching provider:** the registry is non-empty, but every candidate rejects the request based on capability, format, tenant, version, or policy.
- **Ambiguous:** at least two candidates tie on the highest criterion and the policy requires a unique selection.
- **Discovery failure:** malformed service descriptor, class cannot load, constructor/provider method fails, or incompatible dependencies. This is **not** the same as having no valid provider.
- **Execution failure:** a provider was selected but failed during processing. You cannot assume another provider would produce an equivalent result.

Keeping each state separate yields accurate error messages, metrics, and recovery policies.

## 2. Policy When No Matching Provider Exists

There is no single default policy that fits every system. Base the decision on whether the feature is **required or optional**, and whether a **business-valid fallback** exists.

| Policy | Behavior | When to use | Risk to avoid |
|---|---|---|---|
| **Fail fast / fail closed** | Return an error with a clear code; at startup, may refuse to boot | Critical functions, cryptography, payments, authorization checks | Never turn it into “allow” or a fake result just to keep running |
| **Explicit fallback** | Invoke only a configured fallback provider verified to support the request | Plain text instead of rich format, basic mode | Fallback corrupting format, losing data, or silently lowering security |
| **Intentional no-op** | Skip the operation and record status | Optional telemetry/hooks, secondary features that do not affect correctness | Reporting success when a mandatory task never ran |
| **Unsupported / disabled** | Return a feature-unsupported or disabled status | Capabilities installed only for certain environments/tenants | Callers mistaking it for a transient infrastructure failure |
| **Wait/load external provider** | Only when the system designs a time-bounded provisioning mechanism | Platforms that load plugins on demand | Loading arbitrary code or hanging requests indefinitely |

For example: if no image-preview plugin is present, you may display “preview unavailable”; if no digital-signature verification provider exists, you must fail or reject the operation, never treat it as verified.

**Fallbacks require strict conditions:**

- Use only for `NO_PROVIDERS` / `NO_MATCH` if business rules permit. Never auto-apply to `AMBIGUOUS`, `DISCOVERY_FAILED`, or `EXECUTION_FAILED`.
- Have a fixed identity/version, tested, configured, and monitored like a normal provider.
- Check `supports(request)` and enforce data/format limits; never assume a “default” provider supports every input.
- Serve as a **last resort**, never silently masking a release missing a required plugin.
- Separate normal success from fallback success in logs, metrics, and responses whenever it affects users.

Distinguishing “empty registry” from “no match” enables proper diagnosis: the former usually points to installation or discovery, while the latter points to capabilities or out-of-scope requests.

## 3. Policy When Multiple Providers Match

Multiple matching providers **do not mean picking the first provider**. Depending on the goal, design one of the contracts below.

| Policy | Rule | Example |
|---|---|---|
| **Require unique match** | Exactly one candidate is valid; two or more return `AMBIGUOUS_PROVIDER` | A single specialized codec for a registered format |
| **Explicit provider ID** | Configuration/caller chooses an allowed ID; that ID must exist and support the request | Tenant A picks `s3-v2`, tenant B picks `azure-v1` |
| **Priority + reject tie** | Pick the highest priority; if multiple share the highest priority, return an ambiguity error | Prefer a specialized implementation over a generic one |
| **Specificity + priority** | Compare capability/tenant specificity first, then priority; final ties still need a policy | A provider for `image/png` is more specific than `image/*` |
| **Ordered chain** | Try candidates in configured order, provided probing is safe | Parsers capable of returning “unrecognized” before processing |
| **Composition / fan-out** | Intentionally invoke multiple providers and merge results via a clear protocol | Sending the same event to multiple monitoring sinks |

**Do not confuse “chain” with “composition”:** a chain usually searches for one provider that handles the request; composition intentionally uses multiple providers. Only use either when the extension contract allows it. For operations with side effects such as charging money or sending email, trying multiple providers after an ambiguous failure can cause duplicate execution.

### Priority Order Must Be Stable

If using priority, clearly publish:

1. **Mandatory preconditions:** the provider must be enabled, API-compatible, on the allowlist, and support the request.
2. **Explicit selection** if present: the specified ID must exist and support the request; if invalid, return an error rather than silently switching to another provider.
3. **Ranking:** for example, priority is an integer where **a higher number wins**; if specificity applies, publish the evaluation order.
4. **Tie handling:** report `AMBIGUOUS_PROVIDER` or apply an agreed business rule. Sorting IDs just for deterministic error reporting **does not automatically turn a tie into a valid choice**.
5. **Fallback:** considered only when **no eligible candidates remain**, if policy allows.

Never rely on `ServiceLoader` iteration order, classpath order, JAR filenames, or provider download order. Those factors can change across deployment environments.

## 4. Runnable Java 17 Example: No Provider, Priority Selection, and Ambiguity Detection

The following example implements a selector **independent of how providers are discovered**. In practice, the `registry` list can come from `ServiceLoader`, a module layer, or an application-managed plugin registry. This selector applies the policy:

- If registry is empty: `NO_PROVIDERS`; if providers exist but none support the request: `NO_MATCH`.
- Fallback is used only when no eligible candidate exists, and the fallback itself must support the request.
- If candidates exist: pick the highest priority. Two candidates sharing the highest priority trigger `AMBIGUOUS`, rather than picking one arbitrarily.
- Provider IDs must have a value and must not duplicate within the registry.

Save as **`ProviderSelectionDemo.java`**:

```java
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class ProviderSelectionDemo {

    record Request(String kind, String data) {}

    interface Provider {
        String id();
        int priority();
        boolean supports(Request request);
        String execute(Request request);
    }

    record SimpleProvider(String id, int priority, String kind, String prefix)
            implements Provider {

        @Override
        public boolean supports(Request request) {
            return kind.equals("*") || kind.equals(request.kind());
        }

        @Override
        public String execute(Request request) {
            return prefix + ":" + request.data();
        }
    }

    record Selection(Provider provider, boolean fallback) {}

    static Selection select(
            Request request, List<Provider> registry, Provider fallback) {

        Set<String> ids = new HashSet<>();
        for (Provider provider : registry) {
            if (provider == null || provider.id() == null
                    || provider.id().isBlank()
                    || !ids.add(provider.id())) {
                throw new IllegalArgumentException("INVALID_REGISTRY");
            }
        }

        List<Provider> matches = registry.stream()
                .filter(provider -> provider.supports(request))
                .toList();

        if (matches.isEmpty()) {
            if (fallback != null && fallback.supports(request)) {
                return new Selection(fallback, true);
            }
            String code = registry.isEmpty() ? "NO_PROVIDERS" : "NO_MATCH";
            throw new IllegalStateException(
                    code + " kind=" + request.kind());
        }

        int maxPriority = matches.stream()
                .mapToInt(Provider::priority)
                .max()
                .orElseThrow();

        List<Provider> best = matches.stream()
                .filter(provider -> provider.priority() == maxPriority)
                .sorted(Comparator.comparing(Provider::id))
                .toList();

        if (best.size() != 1) {
            List<String> names = best.stream().map(Provider::id).toList();
            throw new IllegalStateException(
                    "AMBIGUOUS kind=" + request.kind()
                    + " priority=" + maxPriority
                    + " providers=" + names);
        }

        return new Selection(best.get(0), false);
    }

    static void demo(
            String label, String kind,
            List<Provider> registry, Provider fallback) {

        Request request = new Request(kind, "hello");

        try {
            Selection selection = select(request, registry, fallback);
            String mode = selection.fallback() ? "FALLBACK" : "SELECTED";
            System.out.println(
                    label + ": " + mode + " " + selection.provider().id()
                    + " -> " + selection.provider().execute(request));
        } catch (IllegalStateException exception) {
            System.out.println(label + ": " + exception.getMessage());
        }
    }

    public static void main(String[] args) {
        Provider basic =
                new SimpleProvider("basic", 10, "text", "BASIC");
        Provider premium =
                new SimpleProvider("premium", 20, "text", "PREMIUM");
        Provider alternate =
                new SimpleProvider("alternate", 20, "text", "ALT");
        Provider plain =
                new SimpleProvider("plain", 0, "*", "PLAIN");

        demo("empty-registry", "text", List.of(), null);
        demo("no-match", "csv", List.of(basic, premium), null);
        demo("unique-best", "text", List.of(basic, premium), null);
        demo("priority-tie", "text", List.of(premium, alternate), null);
        demo("fallback", "csv", List.of(basic), plain);
    }
}
```

Run with **JDK 17+**:

```bash
javac ProviderSelectionDemo.java
java ProviderSelectionDemo
```

Exact stdout:

```text
empty-registry: NO_PROVIDERS kind=text
no-match: NO_MATCH kind=csv
unique-best: SELECTED premium -> PREMIUM:hello
priority-tie: AMBIGUOUS kind=text priority=20 providers=[alternate, premium]
fallback: FALLBACK plain -> PLAIN:hello
```

**Output explanation:**

- `empty-registry`: no providers registered and no fallback; error is identified as `NO_PROVIDERS`.
- `no-match`: both registered providers handle only `text`; the `csv` request has no candidate so it returns `NO_MATCH`.
- `unique-best`: `basic` and `premium` both handle `text`, but `premium` has priority 20 > 10, so it is selected.
- `priority-tie`: `premium` and `alternate` share priority 20. Sorting IDs provides a **deterministic error message**; the selector still rejects the ambiguous result.
- `fallback`: `basic` does not support `csv`; fallback `plain` advertises `kind="*"` so it is selected and the result is marked `FALLBACK`.

This is a program demonstrating **selection decisions**, not a production plugin manager. In a real application, you must add registration-time validation, permission/capability controls, protection against errors in `supports`, per-use-case policy configuration, provider lifecycle, and execution error handling.

## 5. Connecting the Selector to ServiceLoader and a Plugin Registry

`java.util.ServiceLoader` helps find SPI implementations published by JARs/modules. It **does not automatically decide** which provider is selected when multiple candidates match. Therefore, the usual steps are:

1. Define a stable interface/SPI, such as `DocumentRenderer` with `id()`, `supports(request)`, and `render(request)`.
2. Providers advertise themselves via `META-INF/services/<fully-qualified-interface>` or `provides ... with ...` in `module-info.java`.
3. Capture a provider **snapshot** at a clear lifecycle boundary; validate IDs, API versions, availability, and dependencies.
4. Call the selector with the snapshot and the request. Execute the provider only after selection completes.
5. Record the provider ID/version and selection reason; release resources when replacing the snapshot.

**Integration illustration** snippet (assuming `DocumentRenderer` is an already-defined public SPI; this is not a standalone program):

```java
ServiceLoader<DocumentRenderer> loader =
        ServiceLoader.load(DocumentRenderer.class);

List<DocumentRenderer> discovered = loader.stream()
        .map(ServiceLoader.Provider::get)
        .toList();

// Pass providers into the application's selector/registry,
// after validating ID, API version, capability, and policy.
```

`ServiceLoader` finds/loads providers lazily and may throw `ServiceConfigurationError` if declarations or providers are invalid. Do not catch this error and pretend the registry is empty: that hides packaging/dependency errors. `ServiceLoader.reload()` clears that instance's provider cache for subsequent lookups; it **does not automatically detect new JARs**, does not swap objects currently serving requests, and does not allow modifying bytecode of already-loaded classes. If the application dynamically loads JARs, you must also manage class loaders/module layers and snapshot versions.

### When Configuration Specifies a Particular Provider

If a tenant configures `provider.id=pdf-pro`, selection logic should:

1. Look up the exact ID in the trusted and allowed list.
2. Not found: return `CONFIGURED_PROVIDER_NOT_FOUND`, instead of picking the first plugin.
3. Found but does not support the request: `CONFIGURED_PROVIDER_UNSUPPORTED`.
4. Found two entries with duplicate IDs: `INVALID_REGISTRY` at registration time; do not let the later entry overwrite the earlier one.
5. Only when **no explicit specification exists** evaluate automatic policy-based selection.

This enables repeatable configuration testing and avoids situations where classpath changes silently alter outcomes.

## 6. Distinguishing Fallback on No-Match from Failover on Execution Failure

These two terms are easily confused:

- **Fallback on no-match:** no suitable implementation exists; an approved default handles it instead, before starting the main action.
- **Failover on execution failure:** an implementation was already selected and may have caused side effects; trying another implementation after an error requires a dedicated retry/failover contract.

For example, a payment provider times out. Timing out does not prove the transaction was not completed; automatically calling another provider could charge the customer a second time. Failover requires assessing **idempotency**, transaction boundaries, deduplication, correlation IDs, indeterminate states, and reconciliation.

Define at least these error codes:

| Error code | Stage | Typical handling |
|---|---|---|
| `NO_PROVIDERS` | Discovery/registry | Check JAR/descriptor/config; fall back if defined |
| `NO_MATCH` | Capability filtering | Report unsupported; fall back if a fallback provider supports it |
| `AMBIGUOUS_PROVIDER` | Selection | Require an explicit ID or fix priority/policy |
| `INVALID_REGISTRY` | Registration | Reject registries with duplicate IDs, missing IDs, or incompatible APIs |
| `DISCOVERY_FAILED` | Provider loading | Report broken config/plugin, halt or isolate extension per policy |
| `PROVIDER_CHECK_FAILED` | Predicate `supports` | Mark provider unhealthy; do not silently treat as `false` |
| `EXECUTION_FAILED` | Invocation | Preserve trace, handle retry/failover per business safety |

Do not lump every `RuntimeException` or `ServiceConfigurationError` into `NO_MATCH`. Catch errors at boundaries where recovery decisions can be made; do not swallow errors to maintain a fake “success”.

## 7. Defining Priority, Specificity, and Tie-Breaking Rules

In a large registry, a single integer priority may not suffice. For example:

- Provider A supports `image/*`, priority 100.
- Provider B specifically supports `image/png`, priority 50.
- The request needs `image/png`.

If the policy picks highest priority first, A wins; if the policy picks **specificity** first, B wins. **Both can be valid**, but this must be defined and tested upfront. Never guess that higher priority always means a better-fitting provider.

A clear policy can be ordered from strongest to weakest:

```text
1. Explicit provider ID (if the caller is allowed to specify it)
2. Eligibility: enabled + API compatible + supports(request)
3. Specificity score (exact format > format family > wildcard)
4. Priority (higher value wins)
5. If still tied: AMBIGUOUS_PROVIDER
6. Fallback only when there are no eligible candidates
```

If you need a deterministic winner even on ties, define a **business-meaningful tie-breaker** (such as a provider specified in config) and verify that the choice meets requirements. Using lexicographical ID order can make results reproducible, but it easily masks configuration mistakes when two providers were meant to rank equally.

With capability-based selection, note also that a provider advertising multiple formats might not genuinely support every option of each format; `supports(request)` must inspect all decisive attributes, not just file extensions.

## 8. Policy When the Registry Changes at Runtime

Providers may be enabled/disabled, JARs updated, configs changed, or discovered during a reload. Never mutate a shared registry mid-selection and mid-execution:

- Create an **immutable snapshot** holding validated ID, version, capabilities, priority, and health state.
- For a single request, use the same snapshot throughout selection; never filter on an old snapshot and fetch the implementation from a new one.
- If an update succeeds, atomically publish the new snapshot for subsequent requests; in-flight requests can finish on the old snapshot.
- Only unload/close old providers/class loaders after all references are released or per a defined lifecycle policy; loaders/classes remain alive as long as references hold them.
- When a new policy introduces ambiguity, reject publishing the snapshot if it can be pre-checked against known capabilities; for dynamic request conditions, handle `AMBIGUOUS_PROVIDER` at runtime.
- If the selected provider becomes unhealthy, do not silently swap to another provider mid-transaction; re-select at a safe request boundary.

These guarantees belong to the application's plugin registry; `ServiceLoader` is only an implementation-discovery mechanism and does not provide complete lifecycle/hot-swap support.

## 9. Observing and Testing the Selection Policy

To explain “why did the system choose provider X”, record:

- **At discovery:** number of providers found, IDs and versions, descriptor/dependency errors, validation results.
- **At filtering:** request type/capability, eligible candidate count, exclusion reasons (disabled, unsupported, version mismatch).
- **At selection:** policy/version, selected ID, priority/specificity, tied IDs, whether fallback was used.
- **At execution:** provider ID/version, duration, success/failure, retries/failover performed.

Example structured logs (illustrative, not stdout from the program above):

```text
event=provider_selected capability=render/text provider=premium policy=highest-priority fallback=false
event=provider_selection_failed capability=render/text code=AMBIGUOUS_PROVIDER candidates=[alternate,premium]
event=provider_fallback capability=render/csv provider=plain reason=NO_MATCH
```

Avoid logging full document payloads, tokens, security keys, or personal data just to diagnose provider selection.

### Minimum Test Scenarios

| Scenario | Expectation |
|---|---|
| Empty registry, mandatory capability | `NO_PROVIDERS`, must not report success |
| Registry non-empty, no match, fallback disabled | `NO_MATCH` or unsupported |
| No match, valid fallback | Select fallback, mark reason and outcome |
| No match, fallback also unsupported | Reject; do not force-run fallback |
| Single provider matches | Select that provider |
| Multiple providers match, different priorities | Select the exact highest-priority provider |
| Two providers share highest priority | `AMBIGUOUS_PROVIDER` or defined tie-breaker |
| Two providers share duplicate ID | `INVALID_REGISTRY` before selection |
| Config specifies non-existent ID | Specific config error; do not silently pick another |
| Descriptor/JAR fails to load | `DISCOVERY_FAILED`; do not convert to no-match |
| `supports()` throws an error | `PROVIDER_CHECK_FAILED`; do not treat as unsupported |
| Provider runs and throws timeout | `EXECUTION_FAILED`; fail over only if business-safe |
| Registry version changes mid-request | Request uses selected snapshot; new version applies at safe boundary |

Unit tests for the selector are usually easy to write with mock providers like the Java example. Integration tests need real JAR/`META-INF/services` or module layers, broken-dependency cases, and reloads to verify the discovery path.

## 10. Common Design Mistakes

1. **“Taking the first element from ServiceLoader is enough.”** Wrong in multi-provider scenarios: discovery order is not a meaningful selection policy.
2. **“No provider means nothing needs to be done.”** Wrong if the capability is mandatory; distinguish optional from required.
3. **“On no-match, always fall back.”** Wrong if the fallback does not support the input or lowers security/correctness.
4. **“Two providers with equal priority mean picking the one with the smallest ID.”** That is deterministic, not necessarily business-correct; the policy must be explicitly agreed upon.
5. **“Multiple providers is an error.”** Not always: broadcast or chain systems can intentionally use multiple providers; a coordination contract is needed.
6. **“A plugin load error means no plugin exists.”** Wrong: invalid descriptors, missing dependencies, or constructor errors need dedicated reporting.
7. **“On timeout, try the next provider.”** Risks duplicate side effects; requires idempotency and transaction state tracking.
8. **“Once a provider is selected, version doesn't matter.”** Version/API compatibility affects runnability, rollback, and diagnostics.
9. **“ServiceLoader.reload() performs instant hot-swap.”** Wrong: you must build a layer managing snapshots, class loaders, instances, and lifecycle.
10. **“Priority is an access-control mechanism.”** Wrong: providers may only be considered after checking allowlists, tenant permissions, and trust; priority only ranks eligible candidates.

**Principle to remember:** *No candidates* is a decision about **required/optional/fallback**; *multiple candidates* is a decision about **uniqueness/priority/specificity/composition**; *a failing provider* is a decision about **recovery and business safety**. Each state must have its own behavior, error code, and observable evidence so an extensible Java application remains predictable and testable.