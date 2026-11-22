# Documenting Service Provider Contracts

In the Java Platform Module System (JPMS), the ServiceLoader mechanism allows a module to **consume a service** without depending directly on the implementation class. One module defines the public service API; other modules register providers via the `provides ... with ...` directive; consumers declare `uses` and discover providers at runtime.

An easily overlooked point is: **module-info.java only declares connectivity; it does not describe the full operational contract**. A provider can be discovered and instantiated successfully by ServiceLoader and still be incompatible with the application if it returns wrong data, handles null differently from expectations, is unsafe under concurrent calls, or uses unmanaged resources.

Therefore, service provider contract (SPI contract) documentation must make clear **what consumers can expect** and **what providers are required to implement**. This article explains how to document the contract from module declarations to behavior, errors, lifecycle, testing, and API evolution.

## 1. Distinguishing service API, SPI, provider, and consumer

Common roles:

| Role | Responsibility | Example |
| --- | --- | --- |
| Service API / SPI | Defines the interface or abstract class providers must satisfy | GreetingService |
| Provider | Implements the contract and registers with JPMS | EnglishGreetingProvider |
| Consumer | Uses ServiceLoader to discover and invoke providers | GreetingApplication |
| Host / runtime | Resolves the module graph and creates the provider loading environment | Java launcher or ModuleLayer |
| Contract document | Describes behavior, constraints, errors, and compatibility of the SPI | This document or a README next to the SPI |

In small projects, the service API and SPI may be the same interface. In large systems, the public consumer API and extension SPI may be separated into distinct packages. Regardless of organization, the contract must identify the exact **service type that serves as the stable extension point**.

ServiceLoader does not automatically verify business rules. It only handles discovering and instantiating providers according to the module configuration. Contract compliance must be established through documentation and testing.

## 2. What questions must the contract answer?

Documentation sufficient for provider authors must answer:

1. What is the service interface name and which module owns it?
2. Which methods must a provider implement, and with what exact semantics?
3. Which parameters may be null, empty, or out of valid range?
4. Can return values be null, and are they immutable or fixed-format?
5. Which exceptions represent input errors, business errors, and infrastructure errors?
6. May the provider hold state or access network/files during initialization?
7. Can a single instance be called concurrently from multiple threads?
8. Does the provider require a unique id, version, or priority?
9. How does the consumer select a provider when multiple implementations exist?
10. How does the provider module register using `provides ... with ...`?
11. Is the provider discovered in the boot layer or a plugin layer?
12. How are contract tests run and backward compatibility verified?

If documentation merely says “implement this interface and add provides”, critical operational questions remain unanswered.

## 3. Service contract example: GreetingService

Suppose an application wants to allow multiple extension packs to supply greetings by language. The API module is defined as:

~~~java
module com.example.greeting.api {
    exports com.example.greeting.spi;
}
~~~

SPI interface:

~~~java
package com.example.greeting.spi;

public interface GreetingService {
    String id();

    String greet(String name);
}
~~~

This is valid Java syntax, but looking only at the interface is not enough to know:

- Can `id` be empty, uppercase, or change over time?
- Can `name` be null?
- Can `greet` return null?
- May the provider store user state?
- What will the consumer do if two providers return the same `id`?

These details must be written down as an explicit contract.

## 4. Writing Javadoc right next to the SPI

Javadoc is the closest reference point for implementers. You can redefine the interface with concrete contracts:

~~~java
package com.example.greeting.spi;

import java.util.Objects;

/**
 * Extension point for language-specific greetings.
 *
 * <p>Implementations must be thread-safe after construction.
 * Returned values must never be null.
 *
 * @implSpec Providers must not perform network access in the
 * constructor and must return a stable identifier for the
 * lifetime of the provider instance.
 */
public interface GreetingService {

    /**
     * Stable provider identifier in lowercase ASCII.
     *
     * @return a non-empty id matching [a-z][a-z0-9-]*
     */
    String id();

    /**
     * Creates a greeting for one non-empty name.
     *
     * @param name user-visible name, never null or blank
     * @return a non-null and non-blank greeting
     * @throws NullPointerException if name is null
     * @throws IllegalArgumentException if name is blank
     */
    String greet(String name);

    /**
     * Shared input validation used by implementations.
     */
    static void validateName(String name) {
        Objects.requireNonNull(name, "name");
        if (name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
    }
}
~~~

The example uses Javadoc to communicate constraints; the specific content is a design decision for this SPI, not a default rule for every service.

You can add `@since` on individual methods, e.g. `@since 1.1`, as the interface evolves. For methods with default behavior, clarify whether overriding is allowed and what invariants are maintained.

Javadoc should serve as the contract source close to code; the README/module documentation can explain registration, project structure, and operational flows.

## 5. Input and output specifications must be verifiable

Each public method in the SPI should have a contract table:

| Method | Input preconditions | Required output | Exceptions |
| --- | --- | --- | --- |
| id() | No parameters | Non-null, non-empty, stable string in lowercase ASCII id format | No exceptions thrown under normal operation |
| greet(name) | `name` non-null and non-blank | Non-null, non-blank string; does not mutate input data | NullPointerException if null, IllegalArgumentException if blank |

When the contract has format rules, state valid and invalid examples clearly:

~~~text
Valid provider ids: en, vi, en-us
Invalid provider ids: "", "EN", "en us", "123"
~~~

Avoid vague descriptions such as “returns a valid string” when consumers need to know how to process the result.

One provider may reply in Vietnamese and another in English, but both must preserve the same rules regarding null, empty strings, and exceptions. These shared invariants allow consumers to swap providers without modifying logic.

## 6. Sample provider and implementation responsibilities

An implementation is placed in a separate provider module:

~~~java
module com.example.greeting.english {
    requires com.example.greeting.api;

    provides com.example.greeting.spi.GreetingService
        with com.example.greeting.english.EnglishGreetingProvider;
}
~~~

Provider:

~~~java
package com.example.greeting.english;

import com.example.greeting.spi.GreetingService;

public final class EnglishGreetingProvider
        implements GreetingService {

    public EnglishGreetingProvider() {
        // Lightweight initialization only.
    }

    @Override
    public String id() {
        return "en";
    }

    @Override
    public String greet(String name) {
        GreetingService.validateName(name);
        return "Hello, " + name.strip() + "!";
    }
}
~~~

Contract points fulfilled:

- `id` is stable over the instance lifetime and has the required format.
- `greet` validates null/blank per specification.
- `greet` returns a non-null, non-blank string.
- The provider does not hold mutable per-call state, supporting thread safety.
- The constructor does not perform heavy I/O.

The provider does not need to export its implementation package just so ServiceLoader can find it. The `provides ... with ...` directive registers the service provider class; the implementation package can remain unexported.

In this example, the provider class is public and has a public no-arg constructor. JPMS also supports the provider method mechanism under specified conditions, though the instantiation choice should be clearly documented if that mechanism is used.

## 7. Consumer declares uses

The application module using the service:

~~~java
module com.example.greeting.app {
    requires com.example.greeting.api;

    uses com.example.greeting.spi.GreetingService;
}
~~~

Consumer code:

~~~java
package com.example.greeting.app;

import com.example.greeting.spi.GreetingService;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        for (GreetingService provider : loader) {
            System.out.println(
                    provider.id() + ": " + provider.greet("Lan"));
        }
    }
}
~~~

For a named module calling `ServiceLoader.load`, the `uses` directive explicitly declares which service type the module consumes.

ServiceLoader can discover eligible providers in the module configuration or current loading scope. However, a JAR sitting on the module path does not by itself prove the provider module has been resolved.

Therefore, deployment documentation must state how provider modules are brought into the module graph.

## 8. Ensuring the provider is in the module graph

Module structure:

~~~text
src/
├── com.example.greeting.api/
│   ├── module-info.java
│   └── com/example/greeting/spi/GreetingService.java
├── com.example.greeting.english/
│   ├── module-info.java
│   └── com/example/greeting/english/EnglishGreetingProvider.java
└── com.example.greeting.app/
    ├── module-info.java
    └── com.example/greeting/app/Main.java
~~~

Wait—let me check line 258 of the original `004.md`: it was `└── com/example/greeting/app/Main.java`, not `com/example/greeting/app`? No, line 258 was `└── com/example/greeting/app/Main.java`! Good catch! Let me make sure I keep exact `└── com/example/greeting/app/Main.java`. Let's continue carefully.

You can compile using the module source path:

~~~bash
javac --module-source-path src \
    -d out \
    -m com.example.greeting.api,com.example.greeting.english,com.example.app
~~~

(Wait: in original line 266 it is `com.example.greeting.app`, let's verify exact line 266: `com.example.greeting.api,com.example.greeting.english,com.example.greeting.app`! Always copy code blocks verbatim!)

When running, add the provider module as an additional root module:

~~~bash
java --module-path out \
    --add-modules com.example.greeting.english \
    -m com.example.greeting.app/com.example.greeting.app.Main
~~~

The `--add-modules` option here ensures the provider module is resolved in the illustrated runtime configuration. If using a system that creates layers with service binding, or a different launcher configuration, how providers are added to the graph will differ.

On Windows, the module path separator depends on the OS; in this example there is only a single element `out`, so no multi-path separator is needed.

## 9. ServiceLoader does not guarantee business-desired provider ordering

If the system has multiple providers, do not implicitly assume the first provider returned by ServiceLoader is a stable default. Discovery order can depend on module configuration, class loaders, and packaging.

A good contract should define an explicit selection mechanism, such as selecting by id:

~~~java
import com.example.greeting.spi.GreetingService;
import java.util.ServiceLoader;

public final class GreetingLookup {
    public static GreetingService require(String id) {
        GreetingService result = null;

        for (GreetingService provider :
                ServiceLoader.load(GreetingService.class)) {

            if (!provider.id().equals(id)) {
                continue;
            }

            if (result != null) {
                throw new IllegalStateException(
                        "Duplicate provider id: " + id);
            }

            result = provider;
        }

        if (result == null) {
            throw new IllegalStateException(
                    "No provider for id: " + id);
        }

        return result;
    }
}
~~~

In this example:

- Provider `id` must be unique among providers discovered by the consumer.
- No matching provider is a clearly reportable configuration error.
- Two providers sharing the same id is an error rather than an arbitrary choice.

If prioritizing providers by priority, you must document how priority is computed, tie-breakers, missing metadata cases, and whether changing defaults across runs is acceptable.

## 10. Documenting provider discovery and instantiation

ServiceLoader is a lazy-loading mechanism: providers are typically discovered and instantiated while iterating the loader or invoking the corresponding API. Lifecycle details must be understood per ServiceLoader instance.

SPI documentation should state clearly:

- Is the constructor allowed to perform I/O, and are there time limits?
- May it throw exceptions when configuration is missing?
- May it read environment variables or system properties?
- Is the provider permitted to start threads during initialization?
- Is a shutdown/close mechanism required?
- Does the consumer retain the instance long-term?
- Can multiple ServiceLoaders or provider instances exist concurrently?

In the GreetingService example, the contract can stipulate a fast constructor that does not touch the network or spawn threads; the provider holds no resources requiring closing. If data connections or thread pools are needed, define an explicit lifecycle API.

Do not assume ServiceLoader will automatically call `close()` or stop threads created by a provider.

## 11. Classpath providers vs. JPMS providers differ

ServiceLoader can be used in both modular and non-modular applications, but registration depends on configuration.

Explicit named modules typically register with:

~~~java
provides com.example.greeting.spi.GreetingService
    with com.example.greeting.english.EnglishGreetingProvider;
~~~

In traditional classpath applications, a provider may be declared via a service configuration file:

~~~text
META-INF/services/com.example.greeting.spi.GreetingService
~~~

The file content is the fully qualified name of the provider class:

~~~text
com.example.greeting.english.EnglishGreetingProvider
~~~

Documentation must state clearly whether an artifact is supported on the module path, the classpath, or both. Do not assume the exact same registration mechanism works identically across all packaging styles.

If a JAR is an automatic module on the module path, registration and module name are inferred under the corresponding JPMS rules. Inspect the actual artifact rather than guessing the module name from the filename.

## 12. Provider method vs. constructor: specify the mechanism

In an explicit named module, ServiceLoader can instantiate a provider through a suitable constructor or a public static provider method named `provider` per API rules.

When choosing the provider method mechanism, the class listed after `provides` can act as a factory supplying the service object. This approach fits when controlled construction is needed.

One descriptive pattern:

~~~java
public final class GreetingProviderFactory {
    public static GreetingService provider() {
        return new EnglishGreetingProvider();
    }
}
~~~

The provider module's descriptor points to the factory class:

~~~java
provides com.example.greeting.spi.GreetingService
    with com.example.greeting.english.GreetingProviderFactory;
~~~

The example assumes the factory and implementation belong to the same module and related classes are configured properly. With an explicit module, the factory class does not necessarily implement the service interface itself as long as it provides a valid `provider()` method.

Points to record in documentation:

- Does the provider use a public no-arg constructor or a provider method?
- What type does the provider method return and how does it handle errors?
- Does each call create a new instance or return a shared instance?
- Is dependency injection or external configuration required?

For automatic modules, do not rely on the provider method mechanism as a general feature; check the specific requirements for provider classes.

## 13. Declaring thread safety as part of the contract

If consumers may call the service from multiple threads, documentation must clearly state:

| Policy | Meaning |
| --- | --- |
| Thread-safe | A single provider instance can correctly handle multiple concurrent calls. |
| Thread-confined | An instance may only be used from one designated thread. |
| Caller synchronized | The consumer must synchronize when sharing an instance. |
| Immutable | State after construction never changes, which often helps achieve thread safety. |

For example, GreetingService may require all implementations to be thread-safe. This means providers must not use unprotected mutable state when `greet()` is called concurrently.

If a provider truly needs a mutable cache, it must ensure thread safety of the cache or implement an appropriate synchronization strategy.

Do not label a class “thread-safe” merely because it has the `final` modifier. A `final` class does not guarantee that its internal fields are immutable or concurrent operations are safe.

## 14. Specifying runtime latency, timeouts, and blocking

An SPI has not only a type contract but also an operational contract.

A provider's behavior might involve:

- Pure in-memory computation, typically returning quickly.
- Reading local files, which may block.
- Calling network APIs, which may time out or fail.
- Writing data, causing side effects.

Consumers need to know this to decide whether calls can run on an event-loop thread, a UI thread, or require a worker pool.

For GreetingService, the contract may stipulate that `greet()` performs no I/O, does not block waiting on external services, and does not mutate global state. When remote providers are desired, consider a separate asynchronous SPI or update the documentation to specify timeouts and cancellation policies.

If the contract does not mandate absolute timings, at minimum classify methods as blocking/non-blocking, timeout possibilities, and retry responsibilities.

## 15. Exception contract: distinguishing provider errors from consumer errors

Documentation should distinguish:

1. **Input errors** caused by callers violating preconditions: `NullPointerException` or `IllegalArgumentException`.
2. **Business errors** defined by the SPI: possibly custom exceptions or error result types.
3. **Environmental errors** in the provider: I/O, network, permissions, or configuration.
4. **Discovery/instantiation errors** when ServiceLoader cannot load a provider: `ServiceConfigurationError`.

Example:

~~~java
try {
    for (GreetingService provider :
            ServiceLoader.load(GreetingService.class)) {
        System.out.println(provider.greet("Lan"));
    }
} catch (java.util.ServiceConfigurationError error) {
    System.err.println(
            "Unable to discover or instantiate service provider");
    throw error;
}
~~~

`ServiceConfigurationError` is an `Error`, not a regular checked `Exception`. Consumers must decide whether to fail-fast, report invalid configuration, or isolate the provider; do not swallow the error silently and claim no provider exists.

The contract also needs to define which runtime exceptions providers are permitted to throw during normal operation. If providers may return error results instead of throwing exceptions, document the invariants of the result type.

## 16. Difference between ServiceLoader errors and business method errors

These two errors happen at two stages:

- **Discovery/instantiation:** invalid module descriptor, provider class cannot be loaded, constructor/provider method fails, or missing dependency. ServiceLoader may throw `ServiceConfigurationError`.
- **Invocation:** the provider was created, but `greet()` throws `IllegalArgumentException`, `NullPointerException`, or another contracted exception.

When logging, retain the module name, provider class, and `id` if an instance is available. This helps identify the failing provider without scanning the entire codebase.

Do not call `provider.id()` inside an error-handling path if `id()` itself can fail unpredictably. The contract should stipulate that `id()` is stable, side-effect-free, and does not throw errors in normal state.

## 17. ServiceLoader in a separate ModuleLayer

A plugin application can create a dedicated `ModuleLayer` containing providers. In that case, use the method:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(pluginLayer, GreetingService.class);
~~~

In the example, `pluginLayer` is a previously created `ModuleLayer` object, and `GreetingService.class` is the service type shared with the host.

Documentation must state clearly:

- In which layer the provider is resolved and which parent layers are involved.
- From which module/layer the service API is loaded.
- Whether the plugin layer properly binds provider modules into its graph.
- Whether the host and plugin share the exact same class identity of `GreetingService`.
- When reloading a plugin, how the host recreates layers/loaders and cleans up resources.

If the host and plugin each load a separate copy of `GreetingService` through two incompatible class loaders, the provider may be incompatible with the service type the host expects. Do not treat matching class names as sufficient; the class loader defining a type is part of its runtime identity.

## 18. Documenting compatibility when evolving an SPI

Changing an interface can break external providers:

- Adding an abstract method makes older providers fail to satisfy the new interface.
- Changing parameter types, return types, or method names can break source/binary compatibility.
- Changing a method's semantics can cause behavioral bugs even if the code still compiles.
- Tightening null or exception rules can invalidate older providers.

When an SPI needs to evolve, one approach is adding a `default` method with compatible behavior:

~~~java
public interface GreetingService {
    String id();

    String greet(String name);

    default boolean supportsFormalGreeting() {
        return false;
    }
}
~~~

This example allows older implementations to continue using the new method's default value, though compatibility must still be checked against the library's versioning policy.

Version documentation should state:

- The first version introducing the new method or rule.
- The minimum supported provider version.
- Breaking changes and migration instructions.
- Removal timelines for deprecated APIs, if any.

Do not assume a small code change means no impact on provider authors.

## 19. Provider selection conventions when multiple implementations exist

In an extensible system, multiple providers may support a single capability. The contract should pick a transparent policy:

| Scenario | Possible policy choice |
| --- | --- |
| No provider | Report configuration error or use documented fallback. |
| Exactly one matching provider | Use that provider. |
| Multiple providers with distinct ids | Select by id specified by user or configuration. |
| Multiple providers with the same id | Report duplicate id; do not rely on ServiceLoader order. |
| Provider fails on initialization | Fail-fast or isolate the error per published policy. |
| Provider fails on invocation | Propagate, retry, or fall back per error contract, never arbitrarily. |

A consumer may supply explicit id configuration or a priority list. What matters is that provider authors understand how implementations are chosen.

If the API requires unique ids, explain the uniqueness scope: within a single JVM, a single module layer, or a set of plugins loaded in a session.

## 20. Security and resource management documentation

Providers may be written by external organizations. The contract must clarify the permissions and resources the host allows:

- Are reading system properties or environment variables permitted?
- Are accessing credentials, keys, or the filesystem permitted?
- Are opening sockets or making network calls permitted?
- Are spawning threads or executors permitted?
- Is closing resources required when unloading plugins?
- May the provider retain user data after a call?

Do not view JPMS or class loaders as a security sandbox. Named modules help control dependencies and package access, but provider code still runs inside the same process with corresponding OS privileges.

For untrusted providers, process-level isolation and separate controls must be considered. SPI documentation should state trust boundaries clearly without creating false expectations about ServiceLoader's sandboxing capabilities.

## 21. Contract tests for providers

A useful provider contract should come with a shared test suite. Every implementation must pass tests describing the SPI's invariants.

Framework-independent testing example:

~~~java
import com.example.greeting.spi.GreetingService;

public final class GreetingContractTest {
    public static void assertContract(GreetingService service) {
        String id = service.id();

        if (id == null || !id.matches("[a-z][a-z0-9-]*")) {
            throw new AssertionError("Invalid provider id");
        }

        String greeting = service.greet("Lan");
        if (greeting == null || greeting.isBlank()) {
            throw new AssertionError("Blank greeting");
        }

        try {
            service.greet(null);
            throw new AssertionError(
                    "Expected NullPointerException");
        } catch (NullPointerException expected) {
            // Contract satisfied.
        }

        try {
            service.greet("  ");
            throw new AssertionError(
                    "Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            // Contract satisfied.
        }
    }
}
~~~

In real tests, JUnit can be used and expanded with tests for concurrency, lifecycle, exception contracts, and compatibility with released versions.

The test suite should be run against each built provider and with a host application using ServiceLoader to verify module registration as well. Unit tests passing the implementation directly are insufficient to catch `provides`/`uses` or module graph errors.

## 22. Testing provider registration via ServiceLoader

You can test provider discovery in an actual runtime configuration:

~~~java
import com.example.greeting.spi.GreetingService;
import java.util.HashSet;
import java.util.ServiceLoader;
import java.util.Set;

public final class ProviderDiscoveryCheck {
    public static void main(String[] args) {
        Set<String> ids = new HashSet<>();
        int count = 0;

        for (GreetingService provider :
                ServiceLoader.load(GreetingService.class)) {

            GreetingContractTest.assertContract(provider);

            if (!ids.add(provider.id())) {
                throw new AssertionError(
                        "Duplicate provider id: " + provider.id());
            }

            count++;
        }

        if (count == 0) {
            throw new AssertionError(
                    "No GreetingService provider discovered");
        }
    }
}
~~~

To run the example with a named test module, the module containing `ProviderDiscoveryCheck` needs `requires` on the service API and `uses GreetingService`. At the same time, ensure at least one provider module is resolved in the graph.

This test confirms both sides: the provider obeys the checked constraints and the discovery mechanism locates the implementation.

If the system permits a zero-provider configuration, adjust the `count == 0` assertion to match documented policy.

## 23. Service provider contract README template

A README for plugin authors can use the following structure:

~~~text
# GreetingService Provider Contract

Module API: com.example.greeting.api
Service type: com.example.greeting.spi.GreetingService
Minimum runtime: Java 17 (per project policy)

1. Purpose
   - Provide greetings for a given language.

2. Registration
   - Provider module requires com.example.greeting.api.
   - Declare provides GreetingService with Implementation.
   - Provider must have a suitable constructor/provider method.

3. Method contract
   - id(): non-null, non-empty, lowercase ASCII, stable.
   - greet(name): name non-null and non-blank;
     result non-null and non-blank.

4. Runtime
   - Provider is thread-safe.
   - Constructor does not make network calls or spawn threads.
   - greet method has no side effects.

5. Failure
   - Null input -> NullPointerException.
   - Blank input -> IllegalArgumentException.
   - Discovery/config error -> handled per host policy.

6. Selection
   - Consumer selects by id.
   - Duplicate id -> configuration error.

7. Testing
   - Run contract test on the provider.
   - Run ServiceLoader discovery test on the module path.

8. Compatibility
   - Document breaking changes by version.
   - Publish migration policy.
~~~

This is a template, not a standalone project file. When applying it, replace illustrative details with actual module names, Java versions, and policies.

## 24. Module documentation and linking to contracts

In a multi-module project, place contract links where provider authors can easily find them:

- Javadoc on the service interface, especially `@implSpec` and `@implNote`.
- `package-info.java` of the `spi` package to describe extension points.
- `module-info.java` Javadoc on the API module or host module.
- Library/plugin SDK README.
- Release notes and migration guides for version changes.

Example `package-info.java`:

~~~java
/**
 * Service Provider Interfaces for greeting extensions.
 *
 * <p>Provider authors should implement GreetingService
 * according to its method and lifecycle contract.
 */
package com.example.greeting.spi;
~~~

Maintain a single authoritative description source, then link to it from other places rather than duplicating rules that may drift into contradiction. When the contract changes, update Javadoc, test fixtures, and migration guides in the same release.

## 25. Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Provider not found | Provider module unresolved or missing provides/uses | Check descriptors and launch setup. |
| ServiceConfigurationError | Invalid provider class/factory, missing dependency, or init error | Read root cause; verify constructor/provider method mechanism. |
| Provider loaded but unused by host | Selector mismatch on id/capability or priority policy | Read selection contract and log ids. |
| Two providers share the same id | Uniqueness contract not enforced | Report duplicate config; add contract tests. |
| Unexpected NullPointerException | Provider violates null contract | Review Javadoc and constraint tests. |
| Failures under concurrent load | Provider fails thread-safety contract | Guard shared state or change instance model. |
| ClassCastException between plugin and host | Service API loaded from incompatible loaders | Share service API from an appropriate parent layer/loader. |
| Had to export implementation package to load provider | Misunderstood `provides` mechanism | Register provider in descriptor; keep implementation unexported if unneeded. |
| Using the first provider sometimes picks the wrong one | Relied on discovery order | Select deterministically by id/priority rules. |

## 26. Diagnostic workflow and operational guide

When the host cannot find or use a provider:

1. Check the actual JAR or output deployed.
2. Run `jar --describe-module` on the provider JAR to verify module name and `provides`.
3. Confirm the consumer module declares `uses` for the service type.
4. Confirm the provider module `requires` the right API module and `provides` the right service type.
5. Check that the provider module is resolved into the runtime configuration.
6. Check that the service API shares the same class identity between host and plugin.
7. Log the provider id after instantiation and inspect the selection policy.
8. If encountering `ServiceConfigurationError`, identify the initialization failure or missing dependency.
9. Run contract tests, especially null/blank cases, duplicate ids, and concurrency.
10. Compare the host SPI version against the version the provider was built against.

Descriptor inspection command:

~~~bash
jar --describe-module --file plugins/greeting-provider.jar
~~~

Command to observe resolution when running a modular application:

~~~bash
java --show-module-resolution \
    --module-path out \
    --add-modules com.example.greeting.english \
    -m com.example.greeting.app/com.example.greeting.app.Main
~~~

Artifact and module names in the examples are illustrative; replace them with your actual project values.

## 27. Principles for maintaining a service provider contract

- Place service types in an exported API/SPI package with a clear module name.
- Write Javadoc for every method covering preconditions, postconditions, nullability, and exceptions.
- Publish id rules, provider selection, and policies for missing/duplicate providers.
- Separate provider responsibilities from host orchestration and selection.
- Clarify constructor/provider method, lifecycle, resource ownership, and thread safety.
- Do not depend on the provider order returned by ServiceLoader.
- Clarify the module graph, how providers are resolved, and class identity in plugin layers.
- Do not assume ServiceLoader closes resources or sandboxes providers.
- Provide shared contract tests for third-party providers.
- Manage SPI changes with versioning, migration, and compatibility policies.
- Synchronize README, Javadoc, and tests whenever the contract changes.

The service provider contract is the bridge between an extension point in code and the guarantees the host can rely on. JPMS lets you explicitly declare `uses`/`provides` and keep implementation packages encapsulated; contract documentation supplies what the descriptor cannot express: behavior, errors, lifecycle, and per-provider compatibility.

## 28. Self-check questions

**Question 1:** Why is `provides ... with ...` alone not enough to guarantee provider compatibility?

Because `provides` only registers an implementation for a service type. It does not check nullability, id rules, thread safety, lifecycle, or method semantics.

**Question 2:** What must a consumer module declare when using ServiceLoader for a service type?

A named consumer module must declare `uses service.type` and `requires` on the module containing the service API when referencing that type.

**Question 3:** Does a provider need to export its implementation package for ServiceLoader to instantiate it?

Not solely for registration. With an explicit named module, `provides` allows service loading to locate the provider via the module contract; the implementation package can remain unexported.

**Question 4:** If two providers both return id `"en"`, what should the consumer do?

Under the illustrated contract, the consumer reports a duplicate id configuration error instead of relying on ServiceLoader iteration order.

**Question 5:** Why shouldn't the first provider be treated as a stable default?

ServiceLoader does not promise business priority ordering. The host should choose by id, priority, or a documented policy.

**Question 6:** Is a test calling `new EnglishGreetingProvider()` sufficient to prove the provider module works?

No. Direct instantiation tests implementation logic but does not verify the module descriptor, root resolution, and ServiceLoader discovery. Integration testing in a modular runtime is needed.

**Question 7:** What is the risk when adding an abstract method to a published SPI?

Older providers may not implement the new method and become incompatible. Consider a default method, adapter, or deliberate migration/versioning.

**Question 8:** If a provider runs in a separate module layer, what besides the interface's fully qualified name must match the host?

Class identity of the service type: the same definition shared across an appropriate class loader/module layer. Two classes with the same name from different loaders are not necessarily interchangeable.
