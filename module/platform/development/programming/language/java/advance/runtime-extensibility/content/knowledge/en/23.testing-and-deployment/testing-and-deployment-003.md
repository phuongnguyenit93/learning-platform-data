# Testing Zero, One, Many, and Misconfigured Providers

## 1. Why Are These Four Scenarios the Minimum?

In a Java system that supports plugins, provider discovery may come from `ServiceLoader`, a registry, dependency injection, or `ModuleLayer`. Finding a list of providers **does not mean** that the list has the right count, is API-compatible, is validly configured, or is safe to activate.

At minimum, a plugin manager must be tested against four states:

1. **Zero providers:** discovery returns empty or no candidate satisfies the requirement.
2. **Exactly one provider:** the provider can be selected and invoked according to contract.
3. **Many providers:** apply a policy to pick one, invoke all, or build a pipeline; never let discovery order decide implicitly.
4. **Misconfigured provider:** metadata, dependency, constructor, factory, or lifecycle is invalid; the host must handle the failure cleanly.

These four groups exercise *discovery*, *validation*, *selection*, and *activation*. They help prevent common bugs: calling `iterator().next()` on an empty result, picking randomly among multiple providers, initializing a broken plugin that crashes the whole host, or publishing a registry containing an unready provider.

## 2. Define the Contract Before Writing Tests

Suppose the host defines a service:

```java
public interface ExportProvider {
    String id();
    boolean supports(String format);
    String export(String payload);
}
```

The host needs an explicit **selection policy**. For example, in this lesson: for a requested format, there must be **exactly one** supporting provider; zero reports missing; more than one reports ambiguous; a provider that fails initialization must be rejected and never silently added to the registry.

This rule is not mandatory for every architecture:

| Purpose | Potentially Suitable Policy |
|---|---|
| Choose a single data exporter | Exactly-one provider or explicit priority |
| Send events to logger, audit, metrics | All-providers/broadcast with aggregated result |
| Run validate → transform → persist steps | Ordered pipeline with failure policy |
| Find first handler that accepts request | Chain of Responsibility/fallback with stop condition |

**Before testing, write down the policy explicitly.** Otherwise, the "many providers" scenario has no deterministic expected outcome. Never treat `ServiceLoader` or `HashMap` iteration order as business priority.

## 3. Core Test Matrix

| Scenario | Setup Data | Expectation |
|---|---|---|
| Zero providers | Empty registry | Report `NO_PROVIDER` error or configured degraded mode |
| One provider | One valid implementation | Select properly and invoke exactly once |
| Many providers with same capability | Two implementations both returning `supports("csv")` | Report `AMBIGUOUS_PROVIDER` if using exactly-one |
| Many providers with different capabilities | CSV provider and JSON provider | Select the right provider by format |
| Misconfigured provider | Missing ID, duplicate ID, wrong API version | Reject before publication |
| Provider instantiation failure | Factory/constructor throws exception | Record root cause; do not publish broken instance |
| Provider execution failure | `export` throws exception | Classify runtime failure and keep registry consistent |
| Replaced plugin | V1 active, V2 being prepared | Publish V2 only after validation/health check |
| Retry after failure | Side effects from first attempt | Do not blindly retry and duplicate side effects |

These four core cases should be expanded into negative cases such as duplicate IDs, unstable ordering, and rollback. Tests must not only check "whether an exception is thrown"; they must also verify **no unwanted side effects**, no partial registry mutation, and clear logs/diagnostics.

## 4. Zero Providers Scenario

When discovery finds no provider:

```text
Request(format=csv)
       |
       v
Discovery / Registry: []
       |
       v
NO_PROVIDER
```

There are at least three valid ways to handle this depending on requirements:

- **Provider is mandatory:** reject startup or the request with a stable error code.
- **Optional feature:** mark unavailable/degraded without affecting unrelated features.
- **Approved fallback:** pick a truly compatible default implementation, rather than automatically "guessing" a provider.

Tests should verify there is no `NoSuchElementException`, `NullPointerException`, or vague error message. With `ServiceLoader`, `findFirst()` returns `Optional`; use `orElseThrow` with an application-meaningful error instead of an unchecked `get()`.

**Do not assume an empty list means no JAR exists:** the JAR may exist while lacking service registration, its module may not be resolved, its factory may not publish the service, or the class loader may not see the provider. Unit testing an empty registry and integration testing real discovery address two different classes of bugs.

## 5. Exactly One Provider Scenario

With one valid provider, tests should confirm:

1. The provider is discovered/registered.
2. Metadata and compatibility are checked before activation.
3. `supports` matches the right request type.
4. The provider is invoked **once**, receiving the right input and returning the right output.
5. Lifecycle `start`/`stop` or `close` is managed per contract.
6. The selected instance has the expected ID, version, and class loader.

Do not assert only output if multiple providers could produce the same output; verify the provider was **actually invoked**. With mocks/fakes you can count invocations; in integration tests, use logs, metrics, or a controlled side effect.

A valid provider that returns `supports=false` for the current request must be treated as **no matching candidate**, not used by default merely because the registry has only one entry.

## 6. Many Providers Scenario

Having multiple providers is not inherently an error. The question is **which policy is being tested**.

### Exactly-one

If two providers both support `csv` when the host requires a single responsible handler, detect the ambiguity and reject instead of picking the "first element".

```text
providers = [CsvA, CsvB]
request = csv
matches = [CsvA, CsvB]
=> AMBIGUOUS_PROVIDER
```

### Fan-out

If both audit and metrics must receive an event, tests must verify each side is invoked exactly once. Define clear rules when one handler fails: fail-fast or best-effort; if asynchronous, also test timeouts, backpressure, and idempotency.

### Pipeline

If steps produce output sequentially, tests must verify order and that the output of the previous step becomes the input of the next. An implementation iterating an unordered `Set` is unsuitable when order affects the result.

### Priority

If the host uses priority, tests need cases with both distinct and **equal** priorities. On a tie, there must be a documented tie-breaker or a configuration error returned. Tests must never rely on accidental discovery order.

## 7. Misconfigured Provider Scenario

A "misconfigured provider" can occur at multiple stages:

| Stage | Error Example | Expectation |
|---|---|---|
| Metadata | Missing `Plugin-Id`, invalid ID, bad schema | Reject artifact without running provider code |
| Version | Host API does not satisfy requirement | Reject before activation |
| Dependency | Missing module/service dependency | Do not publish; report the specific dependency |
| Factory | Constructor throws exception | Classify startup failure; clean up opened parts |
| Registration | Two providers share the same ID | Reject per duplicate policy |
| Health check | Instantiated but check fails | Keep old registry; close new instance |
| Runtime | Provider method throws exception | Report invocation failure; do not blindly clear whole registry |

Do not collapse everything into `catch (Exception) { return emptyList(); }`: doing so disguises misconfiguration as "no provider", making diagnostics extremely difficult.

In `ServiceLoader`, iteration may instantiate providers and throw `ServiceConfigurationError` when a declaration or provider is broken. Linkage errors can also occur; record the root cause. Exception handling at the plugin boundary must avoid masking serious JVM errors or continuing when host state is no longer trustworthy.

## 8. Standalone Java 17+ Example: Testing All Four Scenarios

The example below uses an in-memory registry to isolate **selection and validation logic** from the discovery mechanism. It runs on JDK 17+ with no JUnit or external dependencies.

Save as **`ProviderScenarios.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ProviderScenarios {
    interface Provider {
        String id();
        boolean supports(String format);
        String run(String input);
    }

    record SimpleProvider(String id, String format) implements Provider {
        @Override
        public boolean supports(String requested) {
            return format.equals(requested);
        }

        @Override
        public String run(String input) {
            return id + ":" + input;
        }
    }

    static final class SelectionException extends RuntimeException {
        SelectionException(String code) {
            super(code);
        }
    }

    static List<Provider> validate(List<Provider> discovered) {
        List<Provider> ready = new ArrayList<>();
        for (Provider provider : discovered) {
            if (provider == null || provider.id() == null ||
                    provider.id().isBlank()) {
                throw new SelectionException("INVALID_PROVIDER");
            }
            if (ready.stream().anyMatch(
                    existing -> existing.id().equals(provider.id()))) {
                throw new SelectionException("DUPLICATE_PROVIDER_ID");
            }
            ready.add(provider);
        }
        return List.copyOf(ready);
    }

    static Provider selectOne(List<Provider> providers, String format) {
        Objects.requireNonNull(format, "format");
        List<Provider> matches = providers.stream()
                .filter(p -> p.supports(format))
                .toList();
        if (matches.isEmpty()) {
            throw new SelectionException("NO_PROVIDER");
        }
        if (matches.size() != 1) {
            throw new SelectionException("AMBIGUOUS_PROVIDER");
        }
        return matches.get(0);
    }

    static void expectFailure(String expected, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected " + expected);
        } catch (SelectionException e) {
            if (!expected.equals(e.getMessage())) {
                throw new AssertionError(
                        "Expected " + expected + ", got " + e.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        // 1. No provider.
        expectFailure("NO_PROVIDER",
                () -> selectOne(validate(List.of()), "csv"));
        System.out.println("empty: PASS");

        // 2. Exactly one provider.
        List<Provider> single = validate(List.of(
                new SimpleProvider("csv-main", "csv")));
        String result = selectOne(single, "csv").run("report");
        if (!"csv-main:report".equals(result)) {
            throw new AssertionError(result);
        }
        System.out.println("single: PASS");

        // 3. Multiple providers supporting the same format.
        List<Provider> multiple = validate(List.of(
                new SimpleProvider("csv-a", "csv"),
                new SimpleProvider("csv-b", "csv")));
        expectFailure("AMBIGUOUS_PROVIDER",
                () -> selectOne(multiple, "csv"));
        System.out.println("multiple: PASS");

        // 4. Misconfigured provider: blank ID.
        expectFailure("INVALID_PROVIDER",
                () -> validate(List.of(
                        new SimpleProvider(" ", "csv"))));
        System.out.println("invalid: PASS");
    }
}
```

Compile and run:

```bash
javac ProviderScenarios.java
java ProviderScenarios
```

Exact stdout:

```text
empty: PASS
single: PASS
multiple: PASS
invalid: PASS
```

Explanation:

- Each `expectFailure` verifies the **expected error code**; if the action does not fail or fails with the wrong error, the test fails with `AssertionError`.
- The registry validates before selection, and `List.copyOf` produces a list that cannot be mutated through the API.
- The single-provider case returns output to verify the invocation path.
- The multi-provider case applies the **exactly-one** policy, so an ambiguity error is the expected behavior.
- The misconfigured case only checks a blank ID; full lifecycle testing requires adding a fake factory and health check.

**Limitation of this example:** there is no `ServiceLoader`, no dynamic class loader, and no automatic simulation of factory failures. This is a selection/validation unit test and does not replace plugin packaging integration tests.

## 9. Integration Testing with ServiceLoader: Verifying the Real Artifact

Once selection logic is solid, test the real discovery mechanism:

```java
// Integration snippet: Provider is the published service interface;
// classpath/module path must be prepared by the test fixture.
ServiceLoader<Provider> loader = ServiceLoader.load(Provider.class);
List<Provider> discovered = new ArrayList<>();
for (Provider provider : loader) {
    discovered.add(provider);
}
List<Provider> ready = validate(discovered);
```

This is not a standalone program; it requires the real `Provider` interface and provider registration.

**Classpath provider:** the JAR declares the file:

```text
META-INF/services/com.example.spi.Provider
```

containing the fully qualified name of the implementation. **JPMS provider:** an explicit module declares:

```java
provides com.example.spi.Provider with com.example.plugin.CsvProvider;
```

The consuming host module must declare `uses com.example.spi.Provider` per JPMS design; the service API must share the exact same class identity between host and plugin.

Integration fixtures should be separated so one test cannot interfere with another:

1. Fixture with no service registration.
2. Fixture with one valid provider.
3. Fixture with two valid providers, including matching format and differing formats.
4. Fixture with broken registration, missing dependency, or failing constructor/factory.

Creating a **new class loader or ModuleLayer per fixture** isolates tests and avoids unintended caching/discovery. However, fixtures must also mirror the host's actual loader mechanism to catch parent delegation and duplicate-API issues.

## 10. Testing Real Errors While Iterating ServiceLoader

`ServiceLoader` can throw `ServiceConfigurationError` in situations such as an invalid provider declaration, a missing provider class, or failure to instantiate. If code runs:

```java
ServiceLoader.load(Provider.class).stream().toList()
```

collecting provider metadata is not the same as calling `Provider.get()` on every entry; depending on the API and mechanism, failures may surface when creating the `Provider` wrapper, reading `type()`, or instantiating the implementation. Test **the exact code path production uses**, including `Provider.get()`, constructor execution, and lifecycle start.

A testing principle:

```text
Unverified artifact
        |
  manifest/module descriptor validation
        |
  trusted source/version/dependency checks
        |
  discovery/provider creation
        |
  initialization + health check
        |
    publish registry
```

If a package fails, the active registry must retain the old snapshot. Never publish providers incrementally one by one only to discover another provider fails midway.

For predictable failures in an optional plugin, the host can quarantine that plugin and let others run according to policy; for a mandatory service, startup may have to fail. Tests must reflect the policy rather than assuming every error must shut down the entire application.

## 11. Testing Lifecycle and Atomic Registry Publication

If the host supports hot reload, testing the four scenarios also involves state transitions.

Example:

```text
Registry V1 (currently ACTIVE)
        |
Prepare Registry V2
   |-- validate metadata
   |-- construct providers
   |-- start + health check
   |
   +-- error --> close partial V2, V1 remains ACTIVE
   |
   +-- PASS --> atomic publish V2
                   |
                  drain V1
                   |
                  close V1
```

Key assertions:

- Before publication, readers see only V1; after publication, new readers see V2.
- No snapshot ever contains half V1 and half V2 when the application requires an atomic registry version.
- A provider that fails during start never appears in the active registry.
- If an existing reader is still calling V1, the writer does not close V1 prematurely.
- Resources of a partially initialized provider are cleaned up even when startup fails.

`AtomicReference<ImmutableRegistry>` is useful for atomic publication; safe `stop/close` requires a lease/drain or another lifecycle synchronization mechanism. Unit tests with fake providers can count `start`, `run`, and `stop` calls and inject controlled failures.

## 12. Testing Errors and Observability

Check not only the API response but also operational telemetry:

| Test Case | What to Observe |
|---|---|
| Zero providers | Error code, requested service/format, discovery environment |
| One provider | Selected provider ID/version and invocation count |
| Many providers | List of matching IDs, resolution policy |
| Bad config | Plugin ID, invalid field, validation reason |
| Factory failure | Error class, root cause, resource cleanup |
| Startup failure | Registry unchanged, no lingering temporary resources |
| Runtime failure | Request failure isolation, no blind side-effect retries |

Never log secrets, credentials, or sensitive payloads. If a plugin is untrusted, its constructor or static initializer may trigger side effects; integration tests should run in an isolated environment with synthetic data and least privilege.

## 13. Common Mistakes in Test Design

- Testing only one successful provider and assuming the plugin system is solid.
- Failing to test an empty list or missing service registration.
- Using `findFirst()` without testing multiple providers with overlapping capabilities.
- Writing tests that depend on `ServiceLoader` order without an ordering policy.
- Treating "zero providers" and "broken provider configuration" as the same error.
- Calling real third-party plugin constructors in unit tests without sandboxing.
- Testing a simple `HashMap` and assuming JPMS/module path will work.
- Asserting only the exception type without checking registry state and resource cleanup after failure.
- Treating successful provider instantiation as covering the entire lifecycle.
- Sharing a loader/registry across tests and leaking state between fixtures.
- Lacking race tests when swapping plugin snapshots while requests are in flight.

## 14. Pre-Deployment Checklist

Before shipping a plugin system:

- Are **zero / one / many / invalid** cases tested with explicit outcomes?
- Is there a provider selection policy for multiple candidates, including duplicates and ties?
- Are providers supporting the wrong format and duplicate provider IDs tested?
- Are there integration tests for service metadata/classloader/module layer of the final artifact?
- Are version/API/capability checks run before startup?
- Are constructor/start/health failures and cleanup tested?
- Are atomic registry publication, draining, and rollback tested?
- Are runtime failures, timeouts, and idempotency tested?
- Are logs/metrics sufficient to distinguish discovery, selection, configuration, and invocation failures?
- Are permissions and resources restricted when testing untrusted plugins?

**Remember:** the four cases—**zero, one, many, and misconfigured**—form the baseline for proving a plugin manager works beyond the "happy path". Good tests verify **selection behavior, clear errors, consistent registry state, and safe lifecycle** across both unit tests and real packaged artifacts.
