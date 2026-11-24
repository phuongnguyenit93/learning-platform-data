# Testing the Same Contract Suite Against Every Supported Provider

## 1. Why Use a Shared Contract Test Suite?

In a Java system that supports runtime extensibility, the host defines a **service contract** (an interface or abstract class), while multiple providers supply implementations. For example, the same `Slugifier` service might have two implementations: one using a character loop and another using regular expressions. The host should not care which algorithm runs; the host needs confidence that **every supported provider honors the promises of the service API**.

A common mistake is thoroughly testing the default provider while only checking that other plugin-supplied providers "can be instantiated". If a second provider handles empty input differently, throws the wrong exception, or is unsafe under concurrent calls, the host may work fine in environment A yet fail in environment B.

**Contract testing** solves this by turning the service's behavioral specification into **one uniform set of assertions** and running it against **all providers in the supported catalog**, independent of how each provider is implemented. It complements each implementation's own unit tests; it does not replace internal implementation tests, integration tests, or security tests.

An organizational model:

~~~text
Shared service API + contract version
                |
                v
       Shared Contract Suite
       - valid inputs / outputs
       - invalid inputs / errors
       - invariants / repeatability
       - concurrency if promised
       - lifecycle/resource semantics
                |
        +-------+-------+
        |       |       |
    Provider A  B       C ... (discovered/catalogued)
        |       |       |
       PASS    PASS    FAIL → do not support deploying this version C
~~~

**Goal of this lesson:** design a testable contract, run the exact same suite for every provider, prevent "green tests" when providers are missing, standardize fixtures/lifecycle, distinguish tests that apply to all providers from optional capabilities, and wire the suite into CI/deployment gates.

## 2. Start from Observable Contract Behavior, Not Algorithms

An interface only states **signatures**; it does not fully specify behavior:

~~~java
public interface Slugifier {
    String id();
    String slugify(String text);
}
~~~

The snippet above only illustrates signatures; it has no package or standalone runnable program. For providers to be interchangeable, API documentation must define **preconditions, postconditions, errors, state, and concurrency**.

For example, suppose we publish the `Slugifier` contract as follows:

| Aspect | Required Contract |
| --- | --- |
| Valid input | String consisting of **ASCII letters** A–Z/a–z, digits 0–9, and ASCII separators: space, `_`, `-` |
| Output | Only ASCII lowercase letters/digits, joining groups with a single `-` |
| Normalization | Collapse consecutive separators; trim leading/trailing separators |
| `null` input | Throws `NullPointerException` |
| Empty or separator-only input | Throws `IllegalArgumentException` |
| Out-of-domain characters, including non-ASCII Unicode or punctuation | Throws `IllegalArgumentException` |
| Repeatability | Same input and valid state must produce the same result |
| Thread safety | Concurrent calls to `slugify` on **a single instance** must be safe; sample implementations are stateless |
| `id()` | Returns a non-blank ID, stable over the instance's lifetime, unique across providers in the catalog under test |

This is the **example's contract**; real applications may choose different Unicode rules. Never judge a provider as wrong merely because it differs from the test author's preference: behavioral standards must come from agreed API documentation/policy.

### 2.1. Contract Tests Differ from Implementation Tests

| Test Type | What It Asserts | Scope |
| --- | --- | --- |
| Contract | `slugify("Hello WORLD")` returns `"hello-world"` for **every** implementation | All supported providers |
| Implementation unit | Private regex helper uses the right pattern or loop handles an internal branch | Only that specific provider |
| Discovery/packaging | Provider is found via SPI/module layer with valid metadata and dependencies | A single artifact or runtime catalog |
| Integration | Provider works with real or fake DB/network/config | Specific host environment |
| Compatibility | Provider built against API version X runs in a host supporting X | Host–provider version pairs |
| Performance/security | SLOs, resource usage, trust boundaries, untrusted input | Per system policy |

**Never put algorithmic details** (loop vs. regex, private field layout, internal class names) into the shared suite. Assert only what callers are entitled to expect from the contract.

### 2.2. Contracts Must Be Measurable

A vague statement like "the provider handles requests quickly and accurately" is hard to turn into stable tests. Replace it with:
- canonical input/output examples and edge cases;
- exception classes/causes for invalid input;
- invariants, such as outputs having no duplicate separators and passing validation;
- state, idempotence, and determinism semantics when promised;
- concurrency guarantees if truly part of the API;
- resource/close contracts when the service has a lifecycle.

Add timeouts or throughput assertions to the common contract only when backed by a concrete budget and measurement environment. Flaky CI benchmarks create false failures; performance usually belongs in a separate tier.

## 3. Provider Catalog: Never Report "Green Tests" When None Are Found

An anti-pattern:

~~~java
// Illustration of broken coverage code:
ServiceLoader.load(Slugifier.class).forEach(provider -> {
    // verify(provider)
});
// If no provider is found, no assertions run yet the job still passes.
~~~

A proper suite must prove:
1. **Providers are actually found.**
2. **The discovered set matches the expected supported set**, or follows an explicit required/optional policy.
3. Each provider has a **valid, unique ID** and matching API/version/capability metadata.
4. **Every expected provider is instantiated and runs the exact same suite**; any provider failing causes the job to fail.
5. Unexpected providers are never silently ignored when doing so violates the deployment catalog.

For example, a build fixture supports two IDs `loop` and `regex`; the test must fail if only one is discovered or if an unapproved provider appears.

### 3.1. ServiceLoader Has a Discovery Scope

- On the classpath: providers register in `META-INF/services/<binary-service-name>`; use `ServiceLoader.load(Service.class, classLoader)` and ensure resources/JARs are in the right lookup scope.
- With named JPMS modules: the consumer declares `uses demo.api.Slugifier;`; the provider declares `provides demo.api.Slugifier with ...;`; you can use `ServiceLoader.load(layer, Slugifier.class)`.
- `ServiceLoader.load(service)` uses the **thread context class loader (TCCL)** at the time the loader is created. If the test runner's TCCL differs from the plugin runtime's, providers can be missed.
- Layer-based discovery searches the layer and its parent layers; classloader-based discovery can also see configurations in parents. Thus "found two providers" does not necessarily mean two providers **from the intended generation** under test.

Build a **test catalog** from the deployed artifact/version manifest, then compare the actual discovered provider set against the expected catalog. Never use `findFirst()`: it only proves the first provider works and gives no coverage of the rest.

### 3.2. Metadata First, Instantiation Second

`ServiceLoader.stream()` returns `Stream<ServiceLoader.Provider<S>>`, allowing you to inspect `Provider.type()` and module/class metadata before calling `Provider.get()`. Keep in mind:
- `Provider.type()` does not mean the provider instance has been initialized.
- `Provider.get()` does not promise to return the same object identity on every call; do not treat it as a singleton API.
- For named modules using a static `provider()` factory method, `Provider.type()` is the method's return type, not necessarily the implementation holder class.
- `ServiceConfigurationError` may be thrown when locating/instantiating a provider; it **must fail the test** rather than skipping the broken provider.
- `ServiceLoader` is not documented as thread-safe; do not share the same loader instance for parallel discovery without synchronization. A provider's concurrency contract is separate from `ServiceLoader` thread safety.

## 4. Java 17+ Lab: Two Providers, One Contract Suite, No JUnit Required

This lab runs on JDK 17+ with no external dependencies. Two providers implement **the same interface** using two different algorithms. `ContractSuite` discovers all providers via `ServiceLoader`, verifies the exact supported catalog, and then calls **the exact same `verifyContract` method** for each provider.

### 4.1. Directory Structure

~~~text
provider-contract-demo/
├── src/
│   ├── demo/
│   │   ├── api/Slugifier.java
│   │   ├── providers/LoopSlugifier.java
│   │   ├── providers/RegexSlugifier.java
│   │   └── test/ContractSuite.java
│   └── META-INF/
│       └── services/
│           └── demo.api.Slugifier
└── out/                     # created upon compilation
~~~

The paths and package names below must match **character for character**. The file `META-INF/services/demo.api.Slugifier` is an SPI resource, not Java source.

### 4.2. File src/demo/api/Slugifier.java

~~~java
package demo.api;

/**
 * Accepts only ASCII letters, digits, and separators ' ', '_', or '-'.
 * Null -> NullPointerException.
 * Empty, separator-only, or out-of-domain chars -> IllegalArgumentException.
 * Returns lowercase slug, collapses separators to '-', trims both ends.
 * slugify is safe for concurrent calls on the same instance.
 */
public interface Slugifier {
    String id();
    String slugify(String text);
}
~~~

The Javadoc describes **observable behavior**. Implementations do not have to use the same regex/loop, provided they honor the contract.

### 4.3. Provider A — Loop: src/demo/providers/LoopSlugifier.java

~~~java
package demo.providers;

import demo.api.Slugifier;
import java.util.Objects;

public final class LoopSlugifier implements Slugifier {
    @Override
    public String id() {
        return "loop";
    }

    @Override
    public String slugify(String text) {
        Objects.requireNonNull(text, "text");

        StringBuilder result = new StringBuilder();
        boolean pendingSeparator = false;

        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            boolean asciiLetter = c >= 'A' && c <= 'Z'
                    || c >= 'a' && c <= 'z';
            boolean digit = c >= '0' && c <= '9';

            if (asciiLetter || digit) {
                if (pendingSeparator && result.length() > 0) {
                    result.append('-');
                }
                result.append(Character.toLowerCase(c));
                pendingSeparator = false;
            } else if (c == ' ' || c == '_' || c == '-') {
                if (result.length() > 0) {
                    pendingSeparator = true;
                }
            } else {
                throw new IllegalArgumentException("Unsupported character");
            }
        }

        if (result.length() == 0) {
            throw new IllegalArgumentException("No letters or digits");
        }
        return result.toString();
    }
}
~~~

Implementation A uses a local `StringBuilder`/flag per invocation and keeps no mutable instance state. Leading/trailing separators are dropped; multiple separators between two groups become a single `-`.

### 4.4. Provider B — Regex: src/demo/providers/RegexSlugifier.java

~~~java
package demo.providers;

import demo.api.Slugifier;
import java.util.Locale;
import java.util.Objects;

public final class RegexSlugifier implements Slugifier {
    @Override
    public String id() {
        return "regex";
    }

    @Override
    public String slugify(String text) {
        Objects.requireNonNull(text, "text");
        if (!text.matches("[A-Za-z0-9 _-]+")) {
            throw new IllegalArgumentException("Unsupported character");
        }

        String result = text
                .replaceAll("^[ _-]+|[ _-]+$", "")
                .replaceAll("[ _-]+", "-")
                .toLowerCase(Locale.ROOT);

        if (result.isEmpty()) {
            throw new IllegalArgumentException("No letters or digits");
        }
        return result;
    }
}
~~~

Implementation B takes a different approach yet guarantees the same outputs and exception types. `Locale.ROOT` prevents output from varying by machine locale, and the character domain is restricted to ASCII so there are no ambiguous Unicode assumptions. Both classes are public with an implicit public no-argument constructor, suitable for classpath SPI.

### 4.5. SPI File Registering Both Providers

Exact content of `src/META-INF/services/demo.api.Slugifier`:

~~~text
demo.providers.LoopSlugifier
demo.providers.RegexSlugifier
~~~

Do not include quotes or JAR names in the file. The resource must be copied onto the **runtime class path**. In real products, each provider may be packaged in its own JAR; the lab uses a single output directory for ease of execution and verification.

### 4.6. File src/demo/test/ContractSuite.java

~~~java
package demo.test;

import demo.api.Slugifier;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.ServiceLoader;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class ContractSuite {
    private static void equal(Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    "expected=" + expected + ", actual=" + actual);
        }
    }

    private static void throwsType(
            Class<? extends RuntimeException> expected, Runnable action) {
        try {
            action.run();
        } catch (RuntimeException actual) {
            if (expected.isInstance(actual)) {
                return;
            }
            throw new AssertionError(
                    "wrong exception: " + actual.getClass().getName(),
                    actual);
        }
        throw new AssertionError(
                "expected exception: " + expected.getName());
    }

    // Every provider must run the EXACT SAME rule set.
    private static void verifyContract(Slugifier provider) throws Exception {
        equal("hello-world", provider.slugify(" Hello  WORLD "));
        equal("xml-parser", provider.slugify("XML_parser"));
        equal("a-b", provider.slugify("a--b"));
        equal("hello-there", provider.slugify("__HELLO--there__"));
        equal("abc123", provider.slugify("abc123"));
        equal("a-b", provider.slugify("A B"));
        equal("same-value", provider.slugify("Same_Value"));

        String once = provider.slugify("ALPHA_BETA");
        equal(once, provider.slugify("ALPHA_BETA"));
        equal(provider.id(), provider.id());

        throwsType(NullPointerException.class,
                () -> provider.slugify(null));
        throwsType(IllegalArgumentException.class,
                () -> provider.slugify(""));
        throwsType(IllegalArgumentException.class,
                () -> provider.slugify("  "));
        throwsType(IllegalArgumentException.class,
                () -> provider.slugify("___"));
        throwsType(IllegalArgumentException.class,
                () -> provider.slugify("café"));
        throwsType(IllegalArgumentException.class,
                () -> provider.slugify("hello!"));

        // Run concurrently on the SAME provider instance; required by contract.
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Callable<String>> tasks = new ArrayList<>();
            for (int i = 0; i < 32; i++) {
                tasks.add(() -> provider.slugify("  Hello__WORLD  "));
            }
            for (Future<String> result : pool.invokeAll(tasks)) {
                equal("hello-world", result.get());
            }
        } finally {
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        List<Slugifier> discovered =
                ServiceLoader.load(
                        Slugifier.class, ContractSuite.class.getClassLoader())
                .stream()
                .map(ServiceLoader.Provider::get)
                .toList();

        if (discovered.isEmpty()) {
            throw new AssertionError("No providers discovered");
        }

        Set<String> ids = new HashSet<>();
        for (Slugifier provider : discovered) {
            String id = provider.id();
            if (id == null || id.isBlank() || !ids.add(id)) {
                throw new AssertionError("Invalid or duplicate provider id");
            }
        }

        // This supported catalog is independent of ServiceLoader output.
        Set<String> expectedIds = Set.of("loop", "regex");
        equal(expectedIds, ids);

        for (Slugifier provider : discovered.stream()
                .sorted(Comparator.comparing(Slugifier::id)).toList()) {
            verifyContract(provider);
            System.out.println("PASS " + provider.id());
        }

        System.out.println("providers=" + discovered.size());
        System.out.println("ALL CONTRACTS PASSED");
    }
}
~~~

**How the test suite works:**

1. `ServiceLoader.load(Slugifier.class, testClassLoader)` uses an explicit loader, avoiding accidental TCCL dependence.
2. `stream().map(Provider::get).toList()` **forces discovery and instantiation of all visible providers**, not just `findFirst()`.
3. If there are no providers, null/blank/duplicate IDs, or the ID set differs from catalog `{"loop","regex"}`, the test fails **before** marking the contract suite as passed.
4. `sorted(Comparator.comparing(Slugifier::id))` is used only to **stabilize display order**. Never rely on discovery order as business priority.
5. `verifyContract` contains **one shared set** of inputs/outputs, exceptions, repeatability, and concurrent calls. It never branches with "if regex, test less".
6. Any provider breaking the contract throws `AssertionError` or fails the test, causing the process to exit nonzero; CI can block release.
7. The pool used for concurrency testing is shut down in `finally`. The demo providers hold no resources requiring stop; if a service API has a lifecycle, the fixture must close each provider per policy.

**Do not over-extrapolate:** the program only checks `slugify` thread safety under the calls in the test; it does not mathematically prove absolute safety across every interleaving. Unit/concurrency stress tests should use longer workloads, repeated runs, and dedicated tools when thread safety is a critical requirement.

### 4.7. Compiling and Running

Run inside `provider-contract-demo` using PowerShell with JDK 17+:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac --release 17 -encoding UTF-8 -d out src/demo/api/Slugifier.java src/demo/providers/LoopSlugifier.java src/demo/providers/RegexSlugifier.java src/demo/test/ContractSuite.java

Copy-Item -Recurse -Force src/META-INF out

java -cp out demo.test.ContractSuite
~~~

**Exact expected stdout** when only the two demo providers are on the classpath:

~~~text
PASS loop
PASS regex
providers=2
ALL CONTRACTS PASSED
~~~

Why does `PASS loop` print before `PASS regex`? Because the test **sorts by ID** before printing; `ServiceLoader` must not be assumed to have a deterministic discovery order across configurations/modules.

You can also verify SPI file packaging:

~~~powershell
jar --create --file demo-all.jar -C out .
jar tf demo-all.jar
java -cp demo-all.jar demo.test.ContractSuite
~~~

`jar tf` prints many entries, so no fixed stdout is listed here. Verify that `META-INF/services/demo.api.Slugifier` actually exists inside the JAR; the subsequent `java` command will produce the same four PASS lines above when the JAR contains the right classes and resources.

### 4.8. Injecting Faults to See What the Suite Catches

- Remove `demo.providers.RegexSlugifier` from `META-INF/services/demo.api.Slugifier`, recopy the resource, and run the suite. The provider list is still non-empty, yet the `expectedIds` comparison fails because `regex` is missing. This guards against **false greens**.
- Modify `RegexSlugifier` so `slugify("  ")` returns an empty string instead of throwing `IllegalArgumentException`. The suite fails on the error case; no implementation test is allowed to drop this case.
- Change `RegexSlugifier.id()` to `"loop"`. The suite fails due to **duplicate ID**.
- Add a new provider to SPI without updating the expected catalog. The suite fails, forcing owners to review and recognize the new provider before claiming support.
- Make `LoopSlugifier` store a mutable `StringBuilder` field and reuse it unsynchronized across calls. The concurrency test will likely catch the race, though races do not always reproduce deterministically; stress testing and design review are needed for certainty.

## 5. Moving to JUnit Jupiter While Keeping One Shared Contract

The pure-JDK example above works well as a smoke gate. In real projects, JUnit Jupiter gives CI per-provider/per-case reporting and build tool integration. Two common approaches are:
- **Parameterized tests** (`@ParameterizedTest` + `@MethodSource`): each provider/fixture becomes an invocation of the same test.
- **Dynamic tests** (`@TestFactory` + `DynamicTest`): generates test cases from the runtime provider catalog.

Illustrative example **using JUnit Jupiter; it will not run standalone without adding `junit-jupiter`, the test engine, and providers to the test runtime classpath**:

~~~java
import demo.api.Slugifier;
import java.util.List;
import java.util.ServiceLoader;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class SlugifierJupiterTest {
    @TestFactory
    Stream<DynamicTest> eachProviderRunsSharedExample() {
        List<Slugifier> all = ServiceLoader.load(Slugifier.class)
                .stream()
                .map(ServiceLoader.Provider::get)
                .toList();

        assertFalse(all.isEmpty(), "No providers discovered");
        return all.stream().map(provider -> DynamicTest.dynamicTest(
                provider.id() + " / normalization",
                () -> assertEquals(
                        "hello-world",
                        provider.slugify("Hello WORLD"))));
    }
}
~~~

This only illustrates **how to generate tests per provider**, not a replacement for the full suite. In production, place shared assertions in `SlugifierContract.assertAll(provider)` or, even better, generate a dynamic test **for each contract rule** with CI-searchable names: `providerId/empty-input`, `providerId/concurrency`, `providerId/normalization`, etc. You still need the **expected provider catalog check**, because `assertFalse(all.isEmpty())` does not detect when one provider is present and three are missing.

**Watch out for dynamic test lifecycle:** in JUnit Jupiter, `@BeforeEach`/`@AfterEach` callbacks apply to the **factory method** execution, not automatically before/after each generated dynamic test. If each test needs a fresh instance, transaction rollback, temp directory, or resource close, manage the fixture inside the lambda or use parameterized tests with appropriate lifecycle. Never share a mutable provider across parallel dynamic tests unless the contract promises thread safety.

### 5.1. Designing Fixtures with a Provider Factory

For services with mutable state, reusing one instance across all cases can introduce order-dependent bugs (test A mutates state and test B fails). The contract suite should accept a **factory creating valid fixtures**, for example:

~~~java
// Illustrative API sketch, not standalone:
interface ProviderFixture<S> extends AutoCloseable {
    String id();
    S createFreshService() throws Exception;
    void resetExternalState() throws Exception;
    @Override void close() throws Exception;
}
~~~

For each invocation:
1. create the fixture/provider per the defined lifecycle;
2. prepare fakes/stubs/external test resources;
3. run the shared assertions;
4. clean up resources in `finally`/`AutoCloseable` regardless of pass or fail.

**Do not assume `ServiceLoader.Provider.get()` always returns a new instance.** The API allows different provider mechanisms, especially when a module uses a factory method; if a fresh service per case is needed, the contract/fixture factory must enforce it explicitly.

## 6. Organizing the Contract Suite by Rule Category

A good suite goes beyond a few "happy path" examples. At minimum, group tests into:

| Category | What Is Asserted | Example for Slugifier |
| --- | --- | --- |
| Discovery | Provider exists, matches catalog, right loader/layer/API | `loop`, `regex` found; no duplicate IDs |
| Valid normalization | Exact output on canonical sample set | `"Hello WORLD" → "hello-world"` |
| Boundary/empty | Empty strings, separator-only, leading/trailing separators | `"___"` rejected; `"__A__" → "a"` |
| Character domain | ASCII vs. Unicode/punctuation | `"café"` and `"hello!"` throw |
| Exception contract | Right exception type, no side effects | `null → NullPointerException` |
| Invariant | Output lowercase, no consecutive separators | Output matches `[a-z0-9]+(-[a-z0-9]+)*` |
| Repeatability | Same input → same output | Repeated calls on same instance |
| Concurrency | Multiple threads calling concurrently when API promises thread safety | Concurrent calls return identical results |
| Lifecycle | `start`, `close`, idempotence/ownership per API | Only if service defines hooks |
| Compatibility | Provider implements expected API version and capabilities | Catalog/API compatibility matrix |

**Do not overuse exact output assertions** for contracts that intentionally permit multiple valid answers. For instance, a search service might not guarantee result order; assert **set equality/invariants** instead of forcing one order. Similarly, exception tests must match the contract: if the API promises only a `RuntimeException` subtype, do not tighten it arbitrarily to one concrete class.

### 6.1. Contract Invariants and Property-Based Testing

For a slugifier, we can write invariants:

~~~text
valid input → non-empty slug
slug matches "[a-z0-9]+(-[a-z0-9]+)*"
slug does not start/end with '-'
slug does not contain "--"
same input → same output
invalid input → documented exception
~~~

You can generate random inputs **with a fixed seed** to test across all providers, logging the seed and input on failure for reproduction. Choose a generator matching the input domain; avoid fuzz tests that only produce trivial inputs. When generating Unicode/invalid inputs, separate expected behavior per contract.

Never use one specific provider as an **absolute oracle** when both could fail in the same way. Expected results should come from the API specification, a reviewed reference implementation, or a specification-independent oracle.

### 6.2. Metamorphic Tests

When exact outputs are hard to know for arbitrary inputs, test relationships across calls. For `Slugifier`:
- for a valid input, adding leading/trailing separators does not change the slug;
- converting ASCII uppercase to lowercase does not change the slug;
- replacing a run of multiple separators with a single separator does not change the slug.

These are **properties valid solely because the contract publishes them**; do not blindly apply them to other services such as encryption, hashing, or digital signatures without verifying the corresponding mathematics.

## 7. Baseline Contract vs. Optional Features

In real plugin systems, not every provider has identical capabilities. For example, a `StorageProvider` has a minimum contract `put/get/delete`, while some plugins additionally support transactions, streaming, or server-side encryption.

Split tests into:
- **Core contract:** every provider declared to support the service must pass; never use `assumeTrue(provider.supports...)` to silently skip core cases.
- **Capability contracts:** only providers **declaring and confirmed by the catalog** to support capability X run tests for X. If `supportsTransactions=true` is declared and the transaction test fails, the job must fail.
- **Environment constraints:** tests requiring external services (cloud credentials, container runtimes, hardware) belong in a separate tier, still gated appropriately before release. An untested provider cannot automatically be marked "supported".

An illustrative catalog representation:

~~~text
provider loop:
  apiVersion: 1
  required: true
  capabilities: [ascii-slug, thread-safe]
provider regex:
  apiVersion: 1
  required: true
  capabilities: [ascii-slug, thread-safe]
~~~

This is **illustrative metadata**, not standard `ServiceLoader` syntax. `ServiceLoader` does not provide provider IDs, semantic versions, or capabilities on its own. The host/plugin platform must define its own metadata/registry, validate it, and bind it to the artifact digest.

### 7.1. Never Use Skips to Hide Missing Providers

A report saying "12 passed, 8 skipped" does not prove 20 providers succeeded. You must know **why 8 were skipped**, whether by capability or broken discovery. Distinguish statuses:
- `PASS`: provider ran and passed the core contract;
- `FAIL`: ran and violated the contract;
- `MISSING`: required by catalog but not found;
- `UNEXPECTED`: found but absent from the approved manifest;
- `NOT_APPLICABLE`: capability contract does not apply per verified metadata;
- `BLOCKED`: test environment lacked prerequisites; must not be reported as pass.

## 8. Testing ServiceLoader and Packaging Separately from Business Contracts

An implementation may pass `verifyContract` when instantiated via `new` yet fail when deployed via SPI due to bad metadata, missing public constructor, classloader visibility, or version conflicts. Therefore, use **two test layers**:

1. **Direct fixture contract test:** a provider factory instantiates the provider and tests behavior. Focuses on business semantics.
2. **Packaged discovery test:** loads the **actual** release artifact in a host/layer environment matching production, verifies the catalog, instantiates providers, and re-runs the core suite.

For classpath SPI:
- resource is named exactly `META-INF/services/demo.api.Slugifier`;
- each line contains a fully qualified provider class name;
- provider class is visible and assignable to the shared service API;
- public no-arg constructor for typical classpath providers;
- fat JAR/shading must merge service files instead of overwriting them;
- across multiple plugin JARs, also test discovering multiple service files.

For JPMS:
- consumer module declares `uses`;
- provider module declares `provides ... with ...` and `requires` on the API;
- test with `ModuleLayer`/`Configuration` matching the release module path;
- if multiple sibling layers contain the same module name/different versions, do not accidentally merge those providers into one catalog;
- `Provider.type()` and `Provider.get()` have specific semantics with provider factory methods.

**Never swallow `ServiceConfigurationError`** and drop that provider from the list so the suite stays "green". That is a discovery/deployment bug CI must catch.

### 8.1. Isolation by Generation

A provider may work on the application class loader yet fail when loaded in its own plugin loader due to a duplicate API JAR or missing transitive dependency. Real host tests should use **the exact classloader/module-layer boundaries intended for production**:
- shared API defined in parent;
- implementation/private dependencies in child;
- expected provider metadata bound to generation/artifact digest;
- check class identity, missing classes, `NoSuchMethodError`, `ClassCastException`;
- create a new generation for v2 rather than merely calling `ServiceLoader.reload()` on the v1 loader.

A job can run the full core contracts **for each candidate generation before publication**. Only if all pass does the host route requests to that version; older requests and older providers follow the previous generation's lifecycle.

## 9. Clean Fixtures, Lifecycle, and Avoiding Cross-Test Contamination

In a multi-provider suite, tests must not depend on running provider A before B, or on leftover state from an earlier provider.

### 9.1. Sources of Contamination

- mutable static singletons shared inside a class loader;
- unreset provider caches, transactions, or database tables;
- shared temporary file/resource paths;
- TCCL not restored on thread pools;
- unregistered listeners/logging registries;
- unstable timing/randomness/network services;
- stateful provider instances reused across tests;
- provider-created threads/executors never shut down.

For stateful services, allocate **a dedicated test namespace per provider** (tenant/database schema/tmp directory/prefix), reset state per contract, and clean up via `try/finally`. When running providers A and B in parallel, never share database keys without isolation.

### 9.2. Testing AutoCloseable Lifecycle

If the contract includes `close()`, define:
- when it is called and who owns it;
- whether calling it multiple times is allowed;
- what operations after close throw;
- whether it waits for in-flight operations;
- whether threads/resources remaining after close are permitted.

Test only **what is promised**; do not assume all `AutoCloseable` providers behave identically. For plugins with dedicated loaders, after finishing a fixture: stop the service, close resources, restore TCCL, close `URLClassLoader` when safe, drop strong references, and verify against leaks in a dedicated test tier. `URLClassLoader.close()` does not force immediate class unloading.

### 9.3. Testing Exceptions and Cancellation

Do not assert only successful results. Verify whether bad inputs or dependency failures produce:
- exception types/statuses matching the contract;
- no partial data writes violating policy;
- cleaned-up resources/transactions;
- proper retry/idempotence if promised by the API;
- consistent timeout/cancellation handling.

For providers calling the network, use a fake HTTP server/test database and fault injection to deterministically trigger timeouts, 5xx responses, partial results, or connection resets. Do not rely on real intermittent network errors that make the suite flaky.

## 10. Cross-Provider Comparison: Useful, Never the Sole Oracle

When provider outputs are strictly equivalent under the contract, **differential testing** can send the same input to A/B/C and compare results:

~~~text
Input vector X
  ├── provider A → output A
  ├── provider B → output B
  └── provider C → output C

If the contract promises identical canonical output:
  assert(output A == output B == output C)
~~~

This can catch a diverging provider where test vectors are incomplete. However, if all three have the same bug, the comparison still passes. Therefore keep **specification-based tests** (known expected outputs/invariants) as the source of truth.

If the contract promises only **semantic equivalence**, canonicalize per specification before comparing:
- `Set` equality instead of array order;
- numeric tolerance only when the API defines an error bound;
- normalized timestamps/timezones per contract;
- exclude internal IDs, logging, or nondeterministic metadata unless the API promises stability.

**Do not compare performance across providers by requiring identical timings**; throughput/latency belong in a separate tier with dedicated SLO/hardware test policies.

## 11. Running the Same Suite Across a Version and Environment Matrix

A "supported" provider is not just source code; define the artifact and compatibility matrix.

| Test Dimension | Example | Purpose |
| --- | --- | --- |
| Provider ID/artifact digest | loop v1, regex v1, external provider | Cover all supported builds |
| Service API version | API 1.x/2.x | Binary/semantic compatibility |
| Host version | current host and still-supported versions | Prevent regressions on older hosts |
| JDK target/runtime | compile `--release 17`; run supported JDKs | Bytecode, module, runtime behavior |
| ClassLoader scope | application, per-plugin loader | Catch API/private dependency collisions |
| JPMS layer | boot/custom/sibling layers | Catch bad `uses/provides/requires` |
| Config/capability profile | baseline, optional modes | Never skip declared optional contracts |
| OS/locale/charset/timezone | key target environments | Catch implicit environment dependencies |
| Concurrency/workload | single, multithread, repeated | State, races, resource lifecycle |
| Artifact packaging | exploded classes, JAR, shaded JAR | SPI metadata and dependency completeness |

You do not need to run **every Cartesian combination** on every commit if cost is prohibitive. Split CI tiers:
- PR: fast, core contract suite on every modified provider artifact.
- Merge/release: full supported-provider catalog and packaged discovery.
- Nightly: multi-JDK/OS, concurrency/stress, wide compatibility matrix.
- Pre-deploy/canary: candidate generation inside a production-like host, health + strong core contract subset; failures halt rollout.

Crucially, regardless of tiering, **never declare a provider supported** if its exact artifact has not passed the defined release gate.

## 12. CI/CD: Conditions for Meaningful Results

A suitable pipeline:

~~~text
Build host API and provider artifacts
           |
Resolve exact supported-provider catalog
           |
Package SPI/module metadata and dependencies
           |
Discover providers in intended loader/layer scope
           |
Assert expected IDs, versions, counts, uniqueness
           |
Run shared core contract suite for EACH provider
           |
Run capability tests for declared capabilities
           |
Run lifecycle/isolation/integration compatibility tests
           |
Aggregate result by provider ID + artifact digest
           |
All mandatory gates PASS?
   ├── No → block release, attach per-provider failures
   └── Yes → mark candidate READY; allow deploy/canary
~~~

### 12.1. Report Per Provider, Not Just Total Test Counts

Generate a report like:

~~~text
service=demo.api.Slugifier contractVersion=1
expectedProviders=[loop, regex]
discoveredProviders=[loop, regex]
loop:  core=PASS  discovery=PASS  concurrency=PASS
regex: core=PASS  discovery=PASS  concurrency=PASS
missing=[] unexpected=[] duplicateIds=[]
releaseGate=PASS
~~~

This is a **design report template**, not the stdout of the demo program; the sample program prints only the four `PASS`/`providers`/`ALL CONTRACTS PASSED` lines. When a provider fails, CI should print **provider ID, contract rule, test input, expected vs actual, exception cause, and artifact digest**, not merely "ServiceLoader error".

### 12.2. Explicit Failure Criteria

The release gate must fail when:
- an expected provider is missing, has a duplicate ID, or has the wrong API version;
- an unexpected provider violates catalog/trust policy;
- an SPI/resource/module descriptor fails to load;
- a provider violates a core rule or declares a capability whose capability contract fails;
- fixture/resource cleanup fails per release policy;
- tests are skipped/blocked without approved waiver;
- mandatory compatibility tests or JDK platform tests fail.

A test suite that "could not run because the environment lacked credentials" must be recorded as **BLOCKED**, never treated as passed. Use mocks for PRs and credentialed integration tests in a secure CI environment.

## 13. Common Mistakes and How to Fix Them

### 13.1. Checking Only `findFirst()`

The first provider passing says nothing about the remaining providers. **Iterate the entire catalog**, force instantiation, and run the same suite. Validate the expected ID set, not just the count.

### 13.2. Testing with `new MyDefaultProvider()` Without Testing Packaging

Provider source code can be correct while the plugin JAR lacks `META-INF/services` or `provides`. Run both direct fixture tests **and** packaged `ServiceLoader` tests against the real artifact.

### 13.3. Hardcoding Branches by Concrete Implementation Class

~~~java
// Illustrative anti-pattern:
if (provider instanceof SomeConcreteProvider) {
    // Only this provider runs the full test cases.
}
~~~

Program against the contract interface/capabilities; the core suite applies to every provider. A test is not "shared" if a branch skips mandatory rules for less-used providers.

### 13.4. Ignoring Broken Providers with a Catch-All

~~~java
// Illustrative anti-pattern:
try {
    // ServiceLoader ... instantiate
} catch (Throwable ignored) {
    // continue with remaining providers, job still succeeds
}
~~~

This **masks discovery failures**. In release tests, fail and log the cause. A production host may have a policy to quarantine a broken provider so the service stays up, yet test results must reflect that the provider **failed support**.

### 13.5. Over-Specifying or Under-Specifying Test Outputs

For APIs that do not promise ordering, asserting exact list order is a buggy test. Conversely, when a contract requires exact normalization, asserting only "non-null" output is too weak. Assertion strictness must match the observable specification.

### 13.6. Shared State Causing Order-Dependent Tests

A provider passing in isolation yet failing after another provider can stem from databases, static caches, timers, or TCCL. Create dedicated fixtures/namespaces, reset state, and clean up per lifecycle; when CI runs in parallel, isolate both instances and external state.

### 13.7. Assuming One Passing Concurrency Run Proves Thread Safety

Races may not reproduce on every run. Use stress/repeat/specialized concurrency tests when a thread-safety contract matters, and review shared mutable state. Never impose thread-safety requirements if the API actually promises only single-threaded use.

### 13.8. Using Discovery Order to Determine Provider Importance

Provider order depends on module/classpath resource lookup. Tests and hosts should use explicit provider IDs/priority metadata; sort IDs for deterministic reporting, never turning SPI file order into business priority.

### 13.9. Mixing API Classes Across Loaders

An implementation and the host can end up with two copies of a service interface sharing the same binary name but defined by different loaders, causing `ClassCastException` or `ServiceConfigurationError`. Place the shared API in a common parent/layer and verify artifacts do not accidentally embed duplicates.

### 13.10. Forgetting to Test New Versions Before Shifting Traffic

A candidate plugin v2 may load cleanly yet violate an edge case of the core contract. Run the suite against the **real candidate loader/layer generation** before publishing, add health/canary checks, and keep a rollback policy. `ServiceLoader.reload()` is no substitute for testing or creating a fresh classloader generation.

## 14. Checklist for Implementing a Shared Contract Suite

1. **Define the contract** independently of implementations, including input domain, output semantics, exceptions, state, concurrency, and lifecycle.
2. **Version the contract** and compatibility rules for host/provider.
3. **Maintain a supported-provider catalog** with IDs, artifact digests, versions, capabilities, and loader/layer scope.
4. **Prevent false greens:** fail on empty/missing/unexpected/duplicate-ID catalogs; never test only the first provider.
5. **Use the same assertion set** for all providers, with no branches bypassing core rules.
6. **Build clean fixtures** for stateful providers; reset external state and clean up resources even when assertions fail.
7. **Run packaged discovery** through SPI/module layers alongside direct unit tests.
8. **Separate capability contracts** based on verified metadata; skipped ≠ passed.
9. **Test non-happy paths**, property-based/invariants, concurrency, and resource lifecycle per API.
10. **Report by provider/rule** so you know exactly which implementation violated the spec.
11. **Wire into CI release gates** and candidate generations before deployment.
12. **Repeat across the compatibility matrix** of JDK/API/host/config/artifact for all declared supported environments.

**Conclusion:** a trustworthy plugin platform has not just a shared interface, but **shared behavioral proof**. Every provider claimed as supported must be discovered in the right loader/layer scope, uniquely identified, and run against **the exact same contract assertions**. Algorithmic freedom belongs to the provider; equivalence of outputs, errors, and lifecycle under the specification is the obligation that lets the host swap providers safely.

## 15. References

- Java SE 17 — `ServiceLoader`, `ServiceLoader.Provider`, `iterator()`, `stream()`, and discovery errors: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17 — `ModuleLayer` and provider discovery in named modules: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Java SE 17 — `ClassLoader` and class identity/delegation: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- JUnit 5 User Guide — Dynamic Tests (`@TestFactory`) and Parameterized Tests: https://docs.junit.org/5.13.1/user-guide/index.html
- Java SE 17 — `ExecutorService` and `Future` in concurrency tests: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
