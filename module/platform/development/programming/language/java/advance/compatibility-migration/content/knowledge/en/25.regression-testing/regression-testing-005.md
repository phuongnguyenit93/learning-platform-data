# Contract Testing for APIs, SPIs, and Third-Party Plugins

When upgrading the JDK, a framework, or a Java library, a system may boot normally while a plugin compiled years earlier fails only when a user triggers one specific feature. A library's public API changes a method signature and older clients fail with `NoSuchMethodError`; an SPI interface adds an abstract method and older providers throw `AbstractMethodError`; or a provider registered via `META-INF/services` disappears when migrating from the classpath to the module path.

Issues like these are routinely **missed by unit tests run exclusively against classes recompiled together on the same version**. This lesson focuses on **contract testing for APIs, SPIs, and third-party plugins** within **Java Advance Compatibility Migration**: defining contract boundaries, storing baselines, running compatibility matrices across old and new artifacts, verifying discovery and class loading, validating behavior, and designing rollout or rollback when not every plugin can be updated simultaneously.

One core principle guides everything here: **"compiles cleanly" is different from "old binaries still link," and both are different from "behavior remains correct."**

## 1. Distinguishing API, SPI, and plugin

These three terms are related, yet each plays a distinct role.

### 1.1. API — Application Programming Interface

An API is the surface a library or platform **exposes to callers**: public types, methods, constructors, fields, annotations, exceptions, module exports, and data contracts.

Example library API:

~~~java
package com.acme.payments.api;

import java.math.BigDecimal;

public interface PriceCalculator {
    BigDecimal calculate(String productId, int quantity);
}
~~~

External applications call `PriceCalculator.calculate`. If a library upgrade changes the return type or deletes the method without a binary bridge, client classes compiled against an earlier version can fail to link at runtime.

An API can also take HTTP, gRPC, GraphQL, or event-contract form. Within the Java ecosystem, however, a **binary API** additionally comprises class names and JVM method descriptors not fully captured in JSON or OpenAPI schemas.

### 1.2. SPI — Service Provider Interface

An SPI is the contract a platform **requires extensions to implement**. Example:

~~~java
package com.acme.reports.spi;

public interface ReportPlugin {
    String id();
    byte[] render(byte[] request);
}
~~~

The host defines `ReportPlugin`; a third-party vendor writes an implementation class and registers the provider. An SPI looks syntactically similar to an API, yet SPI changes propagate in the **reverse direction**: the new host must continue executing plugins compiled externally against the older SPI.

Adding a method to an SPI cannot be assumed safe simply because the host compiled cleanly.

### 1.3. Plugin — an extension unit with its own lifecycle

A plugin typically includes:

- Implementation classes for one or more SPIs.
- Descriptors or registration metadata.
- Its own dependencies.
- Plugin version and supported host version range.
- Configuration, resources, schemas, or permissions.
- Discovery and loading semantics governed by the host.
- Lifecycle callbacks such as initialize, execute, and shutdown.

Examples include JDBC drivers, Java logging providers, annotation processors, IDE extensions, build-tool plugins, authentication adapters, report generators, and internal plugin platforms.

A plugin can be released, downloaded, and loaded into the JVM **independently of the host**. That is why testing only plugins living in the same repository falls short.

### 1.4. Comparing boundaries

| Contract type | Who defines it? | Who implements it? | Prominent failures |
|---|---|---|---|
| Public Java API | Library/platform | Client/application | `NoSuchMethodError`, `IllegalAccessError` |
| SPI | Host/platform | Provider/plugin | `AbstractMethodError`, contract violation |
| Plugin packaging | Provider + host conventions | Plugin loader | `ClassNotFoundException`, `ServiceConfigurationError` |
| HTTP/event API | Service producer/provider | Consumer/client | Schema/semantic mismatch, status/data divergence |
| JVM/module boundary | JDK + module author | Class/module loader | `ResolutionException`, reflective access failure |

In Java migrations, test both **called APIs** and **implemented SPIs**. Testing one direction never substitutes for the other.

## 2. Compatibility dimensions that must be tested

At least five dimensions matter:

1. **Source compatibility:** does existing consumer/plugin source still compile against the new API?
2. **Binary compatibility:** does bytecode compiled against the old API/SPI link and execute on the new library or host?
3. **Behavioral/semantic compatibility:** even when invocation succeeds, do outputs, side effects, and exception contracts hold?
4. **Discovery/loading compatibility:** can existing plugins still be discovered and loaded in the new environment?
5. **Operational/security compatibility:** do lifecycle hooks, threading models, permissions, logging, resource limits, and configs remain valid?

For example, the host adds a `default` method to an SPI. Old plugins may still load and execute other methods cleanly, yet the new default implementation may violate business semantics. Binary tests pass while behavioral contracts fail.

### 2.1. Compatibility claims must always carry scope

Avoid vague declarations like:

~~~text
Plugin compatible: YES
~~~

Record explicit scope instead:

~~~text
Provider old-plugin-1.4.2:
  - Loads on host 3.0 / JDK 21: PASS
  - Service discovery: PASS
  - Required callbacks: PASS
  - Optional capability negotiation: FAIL
  - Shutdown/reload: NOT TESTED
  - Binary/API diff: REVIEWED
~~~

Compatibility claims are meaningful only when tied to **exact artifacts, class loaders, JDK, host versions, environment setup, and executed scenarios**.

## 3. Version matrix for APIs and SPIs

Let:

- `A1`: old API/SPI contract version.
- `A2`: new API/SPI contract version.
- `P1`: plugin/consumer compiled against A1.
- `P2`: plugin/consumer compiled against A2.
- `H1`: old host version.
- `H2`: new host version.

Core compatibility matrix:

| Plugin artifact | Host runtime | Meaning |
|---|---|---|
| P1 | H1 | Baseline |
| P1 | H2 | **Backward runtime compatibility:** new host executes old plugin |
| P2 | H2 | New plugin on new host |
| P2 | H1 | **Forward compatibility:** new plugin on old host, vital for staged rollouts/downgrades |

In the P1→H2 cell, **never recompile P1** before testing. Rebuilding the plugin against the new API erases the very test condition that matters most: the prebuilt binary customers actually run.

### 3.1. API clients and SPI providers run in opposite directions

With a regular API, the newer library serves older clients.

With an SPI, the newer host may have to execute older implementations.

~~~text
API:
  Client v1 (caller) ----> Library API v2 (callee)

SPI:
  Host v2 (caller) ------> Plugin v1 (implementation)

Plugin runtime:
  Host v2 + SPI API v2 + Plugin v1 + Dependencies
~~~

Compiling client source against the new library does not prove older plugins still execute.

## 4. API changes that break binary linkage

Java binary compatibility follows strict rules. Small source edits can break previously compiled bytecode dramatically.

### 4.1. Changing return type changes the method descriptor

Old API:

~~~java
public interface PriceService {
    long priceInCents(String sku);
}
~~~

New API:

~~~java
public interface PriceService {
    java.math.BigDecimal priceInCents(String sku);
}
~~~

Old client bytecode references a method descriptor returning `long`; the new API supplies only a descriptor returning `BigDecimal`. When linked at runtime, execution can throw `NoSuchMethodError`.

A safer bridge retains the old method while introducing a distinct new method name:

~~~java
public interface PriceService {
    @Deprecated
    long priceInCents(String sku);

    java.math.BigDecimal precisePrice(String sku);
}
~~~

From there, deprecate across multiple releases with conversion helpers and precision/overflow tests. **You cannot keep two methods with identical names and parameter lists differing only by return type in ordinary Java source**; Java does not overload on return type.

### 4.2. Switching static vs. instance breaks linkage

Changing an instance method to `static` while keeping its name and parameters breaks callers whose bytecode emits virtual/interface invocation instructions. Runtime throws `IncompatibleClassChangeError` or related linkage errors because invocation semantics no longer match.

Recompiling source will not catch this; you need a binary fixture compiled prior to the API edit.

### 4.3. Narrowing visibility or moving the declaring type

Lowering `public` to package-private or `protected`, or relocating a method outside old callers' access scope, triggers `IllegalAccessError`. Deleting a method or moving it out of the expected type hierarchy causes `NoSuchMethodError`.

On the module path, failing to export a package via `exports` can block access even when the method itself stays `public`.

### 4.4. Adding overloads can separate source and binary compatibility

Suppose a new API adds an overload:

~~~java
void send(String message);
void send(CharSequence message);
~~~

Adding an overload typically does not break bytecode already bound to `send(String)`. However, overload resolution during **recompilation** can pick a different overload around `null` literals, varargs, generics, or newly introduced supertypes/subtypes.

Adding unrelated overloads such as `send(String)` and `send(byte[])` makes `send(null)` ambiguous at compile time—a source incompatibility even though precompiled binaries still link.

## 5. SPI interface changes: failures often surface only on invocation

Suppose SPI v1 is:

~~~java
package com.acme.spi;

public interface Exporter {
    byte[] export(String documentId);
}
~~~

Plugin v1:

~~~java
package com.thirdparty.plugin;

import com.acme.spi.Exporter;

public final class LegacyExporter implements Exporter {
    @Override
    public byte[] export(String documentId) {
        return documentId.getBytes(
            java.nio.charset.StandardCharsets.UTF_8);
    }
}
~~~

Plugin v1 was compiled into `legacy-exporter.jar` and shipped to customers months ago.

### 5.1. Host v2 adds an abstract method

SPI v2:

~~~java
public interface Exporter {
    byte[] export(String documentId);

    boolean supportsFormat(String format);
}
~~~

The old plugin lacks `supportsFormat`. Under Java interface evolution rules, loading the old class and invoking `export` can still succeed because JVM linkage defers errors for missing concrete methods. Yet as soon as host v2 executes:

~~~java
Exporter plugin = loadPlugin();
boolean supported = plugin.supportsFormat("pdf");
~~~

runtime fails with:

~~~text
java.lang.AbstractMethodError
~~~

**Key takeaway:** tests that only instantiate the plugin or call `export` fail to detect new SPI methods unimplemented by legacy binaries. Exercise every capability and callback host v2 actually calls.

### 5.2. Adding default methods can provide a bridge

SPI v2 can declare:

~~~java
public interface Exporter {
    byte[] export(String documentId);

    default boolean supportsFormat(String format) {
        return "plain-text".equals(format);
    }
}
~~~

Existing plugins do not have to recompile simply to supply that method. Still:

- Default behavior may misrepresent real plugins.
- Complex interface hierarchies implemented by plugins can cause default method conflicts.
- Default methods can change runtime dispatch behavior.
- Never use a default method to falsely advertise support for a capability an old plugin cannot perform.

In complex interface hierarchies where two unrelated default methods clash, invocation can throw `IncompatibleClassChangeError`. Test against real implementation classes, not the SPI interface in isolation.

### 5.3. Larger SPI changes may warrant a versioned interface or adapter

When edits are too breaking, introducing a new interface preserves the existing contract:

~~~java
public interface ExporterV1 {
    byte[] export(String documentId);
}

public interface ExporterV2 {
    String id();
    byte[] export(ExportRequest request);
    java.util.Set<String> supportedFormats();
}
~~~

During a transition window, the new host can support both interfaces and adapt `ExporterV1` into the internal model—provided legacy data semantics can truly be preserved.

Do not assume adding a `V2` suffix finishes the job: plan discovery, dependency isolation, lifecycle hooks, and eventual V1 deprecation too.

## 6. Adding methods, constructors, or fields: test binaries, not just compilation

Common cases:

| Change | Source compatibility | Binary/runtime risk |
|---|---|---|
| Add a new public method to a class | Usually safe | May affect dispatch or inheritance in edge cases |
| Remove a public method | Old clients fail recompilation | `NoSuchMethodError` when invoked at runtime |
| Change method descriptor | Client source needs edits | Existing binary reference fails to resolve |
| Change static ↔ instance | Invocation syntax changes | Linkage/ICCE at runtime |
| Narrow access visibility | New clients fail compile | `IllegalAccessError` |
| Add abstract method to SPI interface | Implementor source must implement it | `AbstractMethodError` when called on old plugin |
| Add default method to SPI | Generally eases migration | Default conflict or semantic shift |
| Change public constructor | Consumer source must update | `NoSuchMethodError` during instantiation |
| Replace public field with getter method | Client source must update | `NoSuchFieldError` |
| Change class to interface or vice versa | Breaks consumers broadly | `IncompatibleClassChangeError` |
| Change generic parameterization | Can shift source type checking | Erasure/bridge/binary descriptors require separate checks |

Actual rules run deeper than a summary table. When upgrading widely consumed libraries, pair binary API diff tools with **executable binary fixtures** to validate every real combination.

## 7. Generics, type erasure, and bridge methods

Java generics operate primarily through **type erasure**; JVM method descriptors encode erased types, while generic signatures persist as metadata.

Example:

~~~java
public interface Store<T> {
    T load(String id);
}
~~~

Implementation:

~~~java
public final class StringStore implements Store<String> {
    @Override
    public String load(String id) {
        return id;
    }
}
~~~

Compilers emit bridge methods to preserve polymorphism against erased interface signatures. Changing generic hierarchy, type bounds, or covariant return types during library upgrades can alter emitted bridge methods and break binary linkage.

Inspect:

- Reflection tools reading generic signatures.
- Binary method descriptors (including return types).
- Bridge and synthetic methods.
- Interface dispatch.
- Source recompilation of third-party plugins.
- Kotlin/Scala/Groovy plugins when extensions use non-Java JVM languages.

Commands:

~~~bash
javap -classpath api.jar -p -s com.acme.spi.Store
javap -classpath plugin.jar -p -v com.thirdparty.StringStore
~~~

`javap -s` shows descriptors; `-v` dumps detailed bytecode. Static bytecode dumps provide evidence, never replacing live runtime dispatch tests.

## 8. Exception contracts and behavioral semantics

An API can stay binary-compatible while breaking behavioral expectations:

~~~java
PaymentResult authorize(PaymentRequest request);
~~~

Suppose the old version returned `PaymentResult.rejected` on bad input while the new version throws `IllegalArgumentException`. Everything compiles and links, yet callers miss catching the exception or misread transaction state.

Verify:

- Checked vs. unchecked exception types and trigger conditions.
- Mapping of failures to HTTP status codes or plugin error callbacks.
- Retry safety and risk of duplicated side effects.
- Nullability vs. `Optional`.
- Callback ordering and transaction boundaries.
- Encoding, timezone, numeric precision, and enum handling.
- Thread-safety, reentrancy, and blocking semantics.
- Resource ownership: who opens and closes streams, connections, and executors.
- Timeout, cancellation, and shutdown behavior.

A thorough **contract test** asserts these behavioral guarantees directly instead of merely verifying types exist.

## 9. Designing a testable SPI

Consider a report-generator plugin SPI:

~~~java
package com.acme.reports.spi;

public interface ReportPlugin {
    String id();

    byte[] render(ReportRequest request);

    default boolean supports(String outputFormat) {
        return "text/plain".equals(outputFormat);
    }
}
~~~

`ReportRequest` should be a cleanly versioned DTO/contract, e.g.:

~~~java
package com.acme.reports.spi;

public final class ReportRequest {
    private final String reportId;
    private final String outputFormat;

    public ReportRequest(String reportId, String outputFormat) {
        this.reportId = reportId;
        this.outputFormat = outputFormat;
    }

    public String getReportId() {
        return reportId;
    }

    public String getOutputFormat() {
        return outputFormat;
    }
}
~~~

SPI documentation should specify explicitly:

1. May `id()` return `null`? Must IDs be unique?
2. May `render()` block indefinitely, and who enforces timeouts?
3. Are inputs immutable, and may plugins retain references?
4. When a format is unsupported, should plugins throw an exception or return a specific status?
5. Must created resources be closed by the host or by the plugin?
6. May multiple threads invoke one plugin instance concurrently?
7. May `render` run before `initialize` or after `close`?
8. Across how many major/minor releases does the host guarantee binary compatibility?
9. Which JDK versions are supported?
10. Does discovery rely on `ServiceLoader`, module descriptors, a registry, or a custom loader?

An SPI lacking documented behavioral contracts leads every plugin vendor to different interpretations, making migration verification painful.

## 10. Testing provider contracts with a shared suite

Rather than testing only in-house plugins, define a **provider conformance test suite** every plugin must satisfy.

JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

abstract class ReportPluginContract {

    protected abstract ReportPlugin createPlugin();

    @Test
    void pluginHasStableId() {
        ReportPlugin plugin = createPlugin();
        assertNotNull(plugin.id());
        assertFalse(plugin.id().isBlank());
    }

    @Test
    void supportsTextFormat() {
        ReportPlugin plugin = createPlugin();
        assertTrue(plugin.supports("text/plain"));
    }

    @Test
    void rendersNonNullPayloadForValidRequest() {
        ReportPlugin plugin = createPlugin();
        ReportRequest request =
            new ReportRequest("R-100", "text/plain");

        byte[] bytes = plugin.render(request);
        assertNotNull(bytes);
        assertTrue(bytes.length > 0);
    }
}
~~~

`String.isBlank` requires Java 11+, so substitute equivalent logic if the contract module targets Java 8. The snippet above shows modern syntax rather than applying universally to every baseline.

Implementation test:

~~~java
class LegacyReportPluginTest extends ReportPluginContract {
    @Override
    protected ReportPlugin createPlugin() {
        return new LegacyReportPlugin();
    }
}
~~~

This suite validates compatibility meaningfully only when plugin artifacts compile and run under intentionally chosen versions. If `LegacyReportPlugin` recompiles cleanly alongside tests on SPI v2, you still have not proven v1 binaries load and run. Always add **tests that load JARs precompiled against the old SPI**.

### 10.1. Contract tests must not lock onto internal implementation details

Assert strictly what the SPI guarantees:

- Output formats and semantics.
- Required callback ordering.
- Input validation and failure modes.
- Resource ownership.
- Thread-safety where specified by contract.
- Execution timeouts where SLA applies.

Avoid asserting private call sequences, internal field names, or concrete class loader types unless part of the contract. Over-specified assertions turn contract suites into brittle implementation tests.

## 11. Binary fixtures: the foundational rule

To verify binary compatibility of a Java API/SPI, preserve **JARs produced by the older compiler** as binary fixtures.

~~~text
fixtures/
  api-v1.jar
  old-plugin-v1.jar       # Precompiled against api-v1.jar
  old-client-v1.jar       # Precompiled against api-v1.jar
target/
  api-v2.jar
  host-v2.jar
~~~

Workflow:

1. Compile `old-plugin-v1.jar` against `api-v1.jar` and archive the immutable JAR.
2. Compile `host-v2.jar` and `api-v2.jar` for the target release.
3. Launch a fresh JVM process on the target JDK using `api-v2.jar + host-v2.jar + old-plugin-v1.jar`.
4. Ensure `api-v1.jar` does not leak onto the classpath.
5. Load the plugin via production discovery mechanics.
6. Exercise both existing and new callbacks actually invoked by the host.
7. Assert return values, exceptions, resource cleanup, and concurrency behavior.
8. Capture class-loading logs when diagnosing linkage failures.

If tests recompile old plugins against `api-v2.jar`, compilation either fails or transparently rebinds descriptors—losing fidelity to real customer deployments.

### 11.1. Why run a separate JVM process?

If a JUnit runner loads `api-v1.jar` first on the test classpath and tests later attempt to load `api-v2.jar`, cached classes and shared class loaders distort results. Spawning an isolated subprocess with an explicit classpath mirrors real packaging and runtime resolution far better.

Store binary fixtures in an artifact repository or controlled test store alongside checksums, compiler JDK version, release target, and dependency lists for reproducibility.

## 12. Example matrix executing old binaries against a new host

Suppose you have:

~~~text
report-api-v1.jar
report-plugin-v1.jar
report-api-v2.jar
report-host-v2.jar
~~~

Illustrative Linux/macOS invocation:

~~~bash
java -cp "report-api-v2.jar:report-host-v2.jar:report-plugin-v1.jar" \
  com.acme.reports.host.PluginContractRunner
~~~

On Windows, substitute `;` for `:` in classpaths. Real deployments also include plugin and host dependencies.

Never put both `report-api-v1.jar` and `report-api-v2.jar` onto the same **flat classpath** and guess which class wins. First-wins classpath resolution hides real incompatibilities or introduces non-deterministic breakage.

### 12.1. Combinations to test

- Old host + old plugin: baseline.
- New host + old plugin: backward compatibility.
- New host + new plugin: target state.
- Old host + new plugin: whenever rollback or forward compatibility matters.
- New host + plugin missing dependencies: error handling.
- New host + plugin bundling a duplicate API JAR: loader isolation.
- New host + plugin throwing during init: cleanup behavior.
- New host + plugin lacking a new capability: graceful fallback.

When upgrading the JDK, repeat supported combinations across each committed JDK runtime.

## 13. ServiceLoader and META-INF/services

Java's `ServiceLoader` is a common service provider discovery mechanism.

Suppose the SPI is:

~~~java
package com.acme.spi;

public interface TextFilter {
    String apply(String input);
}
~~~

Plugin:

~~~java
package com.thirdparty.filters;

import com.acme.spi.TextFilter;

public final class UppercaseFilter implements TextFilter {

    public UppercaseFilter() {
    }

    @Override
    public String apply(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Inside the provider JAR create:

~~~text
META-INF/services/com.acme.spi.TextFilter
~~~

Containing:

~~~text
com.thirdparty.filters.UppercaseFilter
~~~

The host discovers providers via:

~~~java
ServiceLoader<TextFilter> loader =
    ServiceLoader.load(TextFilter.class);

for (TextFilter filter : loader) {
    System.out.println(filter.apply("sample"));
}
~~~

Add the proper `java.util.ServiceLoader` import for compilation.

### 13.1. Conditions for discovery to succeed

- Provider JAR actually sits on the intended classpath or module path.
- Service descriptor lives at the exact expected entry path and names a valid provider class.
- Provider class can be loaded and instantiated per `ServiceLoader` rules.
- Provider class is a true subtype of the service interface **visible to the host**.
- All provider dependencies are present and compatible.
- The class loader or module layer performing discovery can see the provider.
- Static initializers, constructors, or provider factory methods throw no errors.

Seeing the provider listed in `jar tf` does not prove the host resolves it via `ServiceLoader`.

### 13.2. Changes that break service descriptors

- Renaming the provider's package or class.
- Renaming the SPI package.
- Moving from classpath to JPMS without updating module declarations.
- Shading JARs without merging `META-INF/services`.
- Repackaging plugin bundles in a way that strips metadata.
- Removing the public no-arg constructor expected under classpath loading.
- Loading the provider JAR under a class loader isolated from the shared SPI interface.

### 13.3. Testing ServiceLoader failure cases

Maintain fixtures covering:

- Missing service descriptor.
- Non-existent provider class name.
- Provider not implementing the SPI.
- Constructor failure.
- Static initializer failure.
- Missing transitive dependency.
- Multiple providers where ordering is unspecified.
- Duplicate provider registration.
- Providers colliding on business `id()`.

Treat `ServiceConfigurationError` as an explicit failure scenario; never swallow it silently and let the host boot with missing functionality.

## 14. JPMS service contracts: uses/provides

With explicit named modules, service declarations reside in `module-info.java`.

API module:

~~~java
module com.acme.text.api {
    exports com.acme.spi;
}
~~~

Provider module:

~~~java
module com.thirdparty.filter {
    requires com.acme.text.api;
    provides com.acme.spi.TextFilter
        with com.thirdparty.filters.UppercaseFilter;
}
~~~

Host module:

~~~java
module com.acme.text.host {
    requires com.acme.text.api;
    uses com.acme.spi.TextFilter;
}
~~~

This illustrates module structure; working builds require properly organized module paths and provider conventions matching the target Java release.

### 14.1. Moving from classpath to module path takes more than CLI flags

Adopting named modules requires reviewing:

- Module name stability.
- `requires`/`exports`/`opens` and module readability.
- `uses` and `provides` clauses.
- Module graph resolution and root module selection.
- Automatic module caveats and constraints.
- Split package conflicts.
- Framework reflection/injection requiring opened packages.
- Provider visibility across custom module layers.
- Changes in context class-loader behavior.

A JAR relying solely on `META-INF/services` may work on the classpath while failing discovery on a modular module path. Test using the exact launch mode deployed to production.

### 14.2. Do not confuse public classes with exported packages

Under JPMS, a `public` class in a named module stays inaccessible to other modules unless its package is exported. Deep reflection additionally distinguishes `opens` from `exports`. Never scatter `--add-opens ...=ALL-UNNAMED` globally when fixing module descriptors or updating libraries is viable.

## 15. Class loaders are part of the plugin contract

Inside the JVM, class identity depends on both binary name and **defining class loader**.

Suppose the host loads:

~~~text
com.acme.spi.TextFilter (HostClassLoader)
~~~

while a plugin loader loads its own copy:

~~~text
com.acme.spi.TextFilter (PluginClassLoader)
~~~

Both share an identical source name yet constitute incompatible runtime types. The plugin implements its private loader's interface, causing casts inside the host to fail with:

~~~text
java.lang.ClassCastException
~~~

or causing `ServiceLoader` to reject the provider as not being a subtype.

### 15.1. Parent-first vs. child-first loading

Plugin systems typically adopt:

- **Parent-first:** prefers parent APIs/classes, useful for sharing SPI contracts cleanly.
- **Child-first:** prefers plugin-bundled dependencies, reducing version clashes.
- **Selective delegation:** shares SPI/API types from the parent while isolating internal implementation libraries per child.

No single delegation scheme fits every platform. Yet **any SPI type exchanged across the host/plugin boundary must share one unambiguous class loader identity**.

Example hierarchy:

~~~text
Boot/Platform Classes
          |
          v
Host ClassLoader
  +-- report-api.jar      <---- shared SPI types
  +-- host-core.jar
          |
          +----------------------------+
          |                            |
          v                            v
 PluginClassLoader A            PluginClassLoader B
  +-- plugin-A.jar                 +-- plugin-B.jar
  +-- dependency-A.jar             +-- dependency-B.jar
~~~

If plugins A and B embed incompatible versions of an internal helper library, child isolation is valuable—yet if either embeds an incompatible duplicate of `report-api.jar`, type identity breaks unless guarded.

### 15.2. Thread Context Class Loader

Libraries and `ServiceLoader` often inspect the Thread Context Class Loader (TCCL). Switching host executors, threading models, or module setup can alter resource lookup and provider discovery.

Example observation:

~~~java
ClassLoader contextLoader =
    Thread.currentThread().getContextClassLoader();

System.out.println(contextLoader);
~~~

Contracts should state which context loader active callbacks see, who restores the TCCL afterward, and whether plugins may spawn threads. When setting the TCCL temporarily, always restore it inside `finally` so context never leaks across pooled tasks.

## 16. Plugin lifecycle must also be tested

Plugins almost always involve more than one execution method:

~~~text
DISCOVERED
    |
    v
VALIDATED
    |
    v
INITIALIZED
    |
    v
ACTIVE ----> QUIESCING ----> STOPPED
    |
    +----> FAILED / DISABLED
~~~

Typical callbacks include:

- `initialize(PluginContext)`.
- `start()`.
- `execute(request)`.
- `onConfigurationChanged(...)`.
- `stop()` / `close()`.
- `health()`.

Contracts should answer:

- Which callbacks fire once vs. repeatedly?
- May callbacks be invoked concurrently?
- Is the context still valid after `stop`?
- When initialization fails, does the host invoke cleanup?
- How are plugin-owned threads and executors shut down?
- Can plugins reload or upgrade without restarting the JVM?
- Are files, sockets, and class loaders closed cleanly to prevent leaks?
- Can one slow or broken plugin wedge the entire host?

A quick unit test like `new Plugin().execute()` skips every lifecycle concern. Upgrade verification must drive plugins through the **same lifecycle manager** used in production.

## 17. Resource allocation, timeouts, and plugin thread-safety

Method signatures can remain unchanged while a newer host changes concurrency rules—for instance moving from single-threaded host v1 invocations to concurrent worker execution in host v2.

If the SPI never specified thread-safety and older plugins hold unsynchronized mutable state, race conditions appear without a single binary signature break.

Test:

- Concurrent calls against shared plugin instances.
- Reentrancy and nested callbacks.
- Cancellation and thread-interruption semantics.
- Timeouts and retry behavior.
- Shared mutable state.
- Backpressure and resource quotas.
- JDBC pools, network clients, and file descriptor bounds.
- Clean shutdown and executor termination.

If migrating Java coincides with adopting virtual threads or reactive runtimes, treat that as a **concurrency contract shift** demanding dedicated testing—never assume unchanged signatures guarantee thread compatibility.

## 18. Java agents and bytecode instrumentation are specialized plugins

A Java agent may attach at startup:

~~~bash
java -javaagent:/opt/agents/monitoring-agent.jar \
  -jar application.jar
~~~

Written against the Instrumentation API, agents intercept class loading, transform bytecode, and depend on bytecode manipulation libraries.

Upgrading the JDK can expose agent issues:

- Older agents cannot parse newer class-file versions.
- Stronger JVM encapsulation restricts reflective access.
- Class transformers misalign with internals of newer JDKs or frameworks.
- Agent config flags and startup options change.
- Overhead and observability metrics shift.

Testing an agent takes more than running `java -version`. Pair the **exact target agent artifact** with the target application JAR and JDK, exercise instrumented code paths, and verify startup, tracing, class loading, latency, and shutdown.

Never disable production agents merely to score a "green" migration test without an approved observability/security replacement.

## 19. Build-tool plugins also enforce SPI contracts

Maven plugins, Gradle plugins, and annotation processors act as build-ecosystem extensions. Upgrading the JDK, Maven, or Gradle can break build plugins even when application code stayed fixed.

### 19.1. Maven plugins

Maven plugins bind to Maven APIs, Plexus/class-loader rules, and build lifecycle phases. Verify:

- Configured plugin goals actually execute.
- Parameter names, types, and defaults behave identically.
- Plugin-scoped dependencies resolve cleanly.
- The Java runtime launching Maven satisfies plugin requirements.
- Generated sources, resources, and packaging layouts match expectations.
- Exit codes and warning/error policies stay consistent.
- Plugins avoid broken JDK internals or outdated bytecode tools.

Passing `./mvnw --version` never proves critical Maven plugin goals work.

### 19.2. Gradle plugins

Gradle plugins depend on Gradle APIs, Groovy/Kotlin DSL conventions, configuration caches, declared task inputs/outputs, and Java toolchains. After upgrading the Gradle Wrapper or JDK, run all registered tasks rather than `help` alone.

Verify:

- Plugin application and extension DSLs.
- Task names, declared inputs/outputs, and cache keys.
- Deprecated or removed Gradle APIs.
- Lazy provider/property configuration.
- Separation of configuration phase vs. execution phase.
- Test tasks, generated sources, and packaging outputs.
- Plugin compatibility matrices across target Gradle and JDK versions.

Never assume a third-party Gradle plugin supports a newer JDK simply because the underlying Gradle distribution supports running on that JDK.

### 19.3. Annotation processors as compile-time plugins

Processors run during compilation:

~~~java
@SupportedAnnotationTypes("com.acme.annotations.AutoGenerate")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class CodegenProcessor extends AbstractProcessor {
    // ...
}
~~~

This snippet demonstrates annotation processing API usage, not a complete processor. Legacy processors frequently access `javac` internal ASTs or recognize only older `SourceVersion` constants.

Test by compiling representative sample code with the target compiler, inspecting emitted sources/resources, checking incremental annotation processing, diagnostics, and runtime bytecode compatibility.

## 20. Third-party APIs: behavioral shifts outside the JVM

Plugins frequently call external REST, gRPC, database, or message-broker APIs. Upgrading HTTP clients, JSON serializers, or TLS providers alongside the JDK can shift wire behavior outside the JVM.

Example REST payload:

~~~http
POST /v1/payments
Content-Type: application/json

{"orderId":"O-100","amount":"125000.00","currency":"VND"}
~~~

Consumer contracts encompass:

- URLs, HTTP verbs, and status codes.
- Auth headers, mTLS certificates, and token scopes.
- Field names/types, optional/default/null handling.
- Timestamps, numeric precision, and ordering.
- Retry and idempotency rules.
- Timeouts, rate-limiting, and error payloads.

Combine OpenAPI/gRPC schema checks, consumer-driven contracts, mock servers, and staging integration tests with downstream systems as needed—never test Java method signatures alone.

### 20.1. Mocks cannot catch every contract shift

Fake test servers often reflect the client team's assumptions, passing even after real upstream behavior diverged. Include:

- Agreed contracts or versioned specifications.
- Verification against real provider implementations in test environments.
- Fixtures capturing both legacy and updated payloads/errors.
- Review of upstream API release notes and versions.
- Negative scenarios: auth failure, timeouts, rate limits, malformed payloads.

Likewise on the SPI side, a mock plugin written against the current host never substitutes for precompiled historical partner binaries.

## 21. Layered compatibility testing

A dependable contract test strategy covers multiple layers:

| Layer | What it tests | Failures detected |
|---|---|---|
| Static API diff | Public surface and binary signatures | Removed or altered methods, fields, classes |
| Source compilation | Old consumer/plugin source vs. new API | Source incompatibilities |
| Binary fixtures | Old precompiled JARs vs. new API/host | Runtime linkage errors |
| Provider conformance suite | SPI semantics and lifecycle | Behavioral contract violations |
| Discovery integration | ServiceLoader, JPMS, descriptors | Missing or undiscovered providers |
| Loader isolation | Flat/plugin classpaths, TCCL | Type identity clashes and duplicate libs |
| External integration | DB, HTTP, brokers, filesystem | Wire and external contract regressions |
| Load & concurrency | Thread safety, latency, cleanup | Races and resource leaks |
| Deployment smoke | Packaging, launcher, JDK, agents | Packaging and runtime mismatches |
| Rollback testing | Legacy host/plugin/state post-upgrade | Forward compatibility gaps |

No single tool spans all ten layers on its own.

## 22. Static API diffing with appropriate tools

Tools such as **Revapi** and **japicmp** compare Java API surfaces between releases. Within the JDK itself, `javap` and `jdeps` help too.

Example:

~~~bash
javap -classpath api-v1.jar -public com.acme.spi.ReportPlugin
javap -classpath api-v2.jar -public com.acme.spi.ReportPlugin

javap -classpath api-v1.jar -s com.acme.spi.ReportPlugin
javap -classpath api-v2.jar -s com.acme.spi.ReportPlugin
~~~

Wire API diff tools into CI to classify source vs. binary breaks against release policy. Check exact version documentation for each diff tool's configuration and detection coverage.

Limitations of static API diffing:

- Cannot tell whether runtime business behavior changed.
- Cannot verify ServiceLoader or JPMS visibility.
- Ignores external config files and secrets.
- Cannot decide whether a removed method was an approved breaking change or a mistake.
- Cannot observe callback ordering, thread safety, retries, or resource leaks.

### 22.1. jdeps helps statically, not dynamically

~~~bash
jdeps --summary plugin.jar
jdeps --jdk-internals plugin.jar
~~~

`jdeps` reports statically observable dependencies and detects calls into JDK internals, yet can miss reflective lookups, SPI providers, resource lookups, and custom plugin class loaders.

Pair static scans with **live runtime integration** using actual binary artifacts.

## 23. Compatibility gate for public API releases

A public Java library release pipeline typically runs:

1. Build v2 artifact.
2. Run static API diff between v1 and v2.
3. Classify changes: compatible, binary breaking, source breaking, behavioral/semantic.
4. Validate approved exclusions per versioning policy.
5. Recompile sample legacy client source against v2.
6. Run `old-client.jar` (compiled against v1) on a classpath carrying only `api-v2.jar`.
7. Execute key behavioral contract tests.
8. Run smoke tests across every supported JDK version.
9. Export compatibility reports tied to commits and artifact hashes.
10. Publish only after all unapproved breaks are fixed or documented per policy.

Projects adhering to SemVer can gate minor/patch releases on zero unapproved breaking diffs—bearing in mind SemVer is a promise, **not automated runtime proof** that 2.3.4 never breaks 2.3.3 consumers.

## 24. Contract gate for SPI/plugin host releases

When upgrading host H1 → H2:

1. Document all SPI methods and callback expectations.
2. Maintain released third-party plugin binaries.
3. Run ServiceLoader / module discovery checks.
4. Boot plugins through the real host lifecycle manager.
5. Call all callbacks H2 uses, including newly added capabilities.
6. Test capability fallbacks cleanly.
7. Confirm bundled duplicate API JARs in plugins never shadow host SPI types.
8. Test multi-plugin deployments and transitive dependency conflicts.
9. Test shutdown/reload, concurrent execution, and plugin faults.
10. Exercise H2→H1 rollback whenever mixed clusters or downgrades exist.

If a legacy plugin proves incompatible, decide explicitly:

- Ship a compatibility adapter.
- Gate features via capability negotiation.
- Schedule a mandatory partner plugin upgrade.
- Isolate the legacy plugin out-of-process.
- Reject unsupported plugins cleanly during preflight diagnostics.
- Update support timelines with partner communication.

Never let an incompatible plugin crash live production traffic on an infrequently visited code path.

## 25. Capability negotiation and versioned SPIs

In plugin ecosystems, the real question is rarely "which plugin version?"—it is "does this plugin support capability X?"

Contract:

~~~java
public interface ReportPlugin {
    String id();
    byte[] render(ReportRequest request);

    default boolean supports(String format) {
        return "text/plain".equals(format);
    }
}
~~~

The host checks:

~~~java
if (!plugin.supports("application/pdf")) {
    throw new UnsupportedOperationException(
        "Plugin does not support PDF");
}
~~~

Never assume a plugin supports PDF simply because the host upgraded JDKs or added a `default` method returning `true`.

### 25.1. Version negotiation differs from binary compatibility

A plugin descriptor might specify:

~~~properties
plugin.id=thirdparty.report
plugin.version=1.4.0
host.api.range=[2.0,3.0)
capabilities=text/plain
~~~

This illustrates a **custom system-defined metadata schema**, not a built-in Java standard. Hosts can reject mismatched plugins early—but declared version metadata never replaces runtime binary tests, since a plugin claiming a wide version range can still fail due to missing methods or incompatible dependencies.

### 25.2. Never rely solely on artifact names or version strings

External ecosystems frequently vary artifact naming and versioning schemes. Prefer:

- Explicit API/SPI contract versions.
- Explicit capability declarations.
- Host compatibility ranges.
- Verified checksums and artifact provenance.
- Live runtime verification tests.
- Clear error messages reporting exact unsupported capabilities or ranges.

## 26. Separate API compatibility from serialization compatibility

Plugins frequently exchange Java objects with the host or persist internal state. Converting a public POJO into a Java `record` or renaming its package can break both precompiled bytecode and previously serialized state.

Test:

- Java serialization (`serialVersionUID`, class names, and field evolution).
- JSON, Avro, and Protobuf schemas.
- DTO constructors, getters, and `record` accessors.
- Pre-upgrade cache entries and persisted sessions.
- Queued messages, retry queues, and dead-letter queues.
- Plugin state files and database tables.
- Whether state written by the newer host/plugin stays readable upon rollback.

Example legacy client call:

~~~java
String id = customerDto.getId();
~~~

If v2 converts it to:

~~~java
public record CustomerDto(String id) {}
~~~

`record` generates `id()`, not `getId()`. Precompiled clients throw `NoSuchMethodError` because `getId()` vanished—a binary breaking API change even when JSON payloads still emit field `id`.

Never bundle source-modernization refactors into compatibility releases without checking binary and serialization consumers first.

## 27. Runtime exceptions: classify type and timing accurately

Practical troubleshooting reference:

| Error | Root cause to inspect | When it typically surfaces |
|---|---|---|
| `NoSuchMethodError` | Binary method descriptor disappeared | Upon invoking the missing method |
| `NoSuchFieldError` | Referenced field removed or altered | When bytecode accesses the field |
| `AbstractMethodError` | Old implementation lacks new SPI method | When host invokes the new SPI method |
| `IncompatibleClassChangeError` | Class/interface swap, static change, or default conflict | Class linkage or dispatch |
| `IllegalAccessError` | Insufficient access visibility across types/modules | Resolution/linkage or member access |
| `ClassNotFoundException` | Requested class name not visible to loader | Dynamic load or reflection |
| `NoClassDefFoundError` | Required class unavailable or uninitialized | Loading, linking, or initialization |
| `ClassCastException` | Type or defining class loader mismatch | Cast or `instanceof`/assignment checks |
| `ServiceConfigurationError` | Invalid SPI descriptor, constructor, or subtype | `ServiceLoader` iteration/instantiation |
| `ExceptionInInitializerError` | Static initializer failed | First class initialization |
| `LayerInstantiationException` or resolution errors | Broken module graph or JPMS layer | Module resolution or layer setup |
| `InaccessibleObjectException` | Deep reflection blocked by encapsulation | Reflective call invocation |

**Failures often arrive late.** A `ClassNotFoundException` inside an edge PDF exporter won't trigger during login smoke tests. Drive actual callbacks and provider code paths in verification suites rather than stopping after host boot.

### 27.1. Never swallow LinkageError indiscriminately

Plugin hosts often aim to survive a single failing plugin through controlled isolation and disabling. Never catch `Throwable`, log a generic message, and treat the plugin as active—critical linkage errors get masked silently.

Build explicit error boundaries tied to plugin lifecycle: mark failed plugins disabled, release acquired resources, emit metrics/alerts, and never fabricate placeholder business outputs.

## 28. Plugin sandboxing and security after JDK migration

Third-party plugins typically run inside the host process with identical OS privileges unless explicitly isolated. **ClassLoader isolation is not a security sandbox.**

On modern JDKs, do not count on Java Security Manager for untrusted-plugin sandboxing; Security Manager deprecation and removal tracks evolved dramatically across Java releases. Where untrusted code execution truly applies, rely on process or container isolation, OS permissions, network policies, and dedicated security controls.

Test security aspects including:

- Valid artifact origin, cryptographic signatures, and checksums.
- Whether plugins download remote executable code dynamically.
- Least-privilege delivery of secrets and credentials.
- Permitted filesystem and network scopes for plugins.
- Resistance to classpath poisoning or dependency substitution.
- Handling of untrusted deserialized inputs.
- Protection against resource exhaustion, infinite loops, and unbounded thread creation.
- Ensuring logs leak no tokens or PII.
- Policy mechanisms for disabling or revoking compromised plugins.

Never "solve" plugin reflective access failures by opening broad JDK internals or elevating process privileges when the real problem is an unmaintained plugin.

## 29. Preflight checks for incompatible plugins before activation

Preflight pipeline:

~~~text
Plugin artifact
       |
       v
Verify origin and checksum
       |
       v
Read plugin descriptor / API version / capabilities
       |
       v
Check host + JDK version ranges
       |
       v
Resolve plugin dependencies
       |
       v
Classloader/module resolution
       |
       v
Provider discovery and contract smoke check
       |
       v
Enable plugin or quarantine with notification
~~~

Preflight checks cannot validate full business behavior, yet they catch missing classes, malformed descriptors, and version-range violations early. Pair preflight validation with integration tests, load runs, and rollback drills.

When rejecting a plugin, emit clear diagnostics:

~~~text
Plugin thirdparty.report 1.4.0 disabled:
requires Host SPI [1.0,2.0), found Host SPI 3.0
~~~

This illustrates an informative diagnostic format rather than a standard JDK message—vastly preferable to a random `NoClassDefFoundError` when an end user clicks Export.

## 30. Designing test fixtures for a plugin ecosystem

Representative fixture suite:

~~~text
compat-fixtures/
  api/
    api-v1.jar
    api-v2.jar
  plugins/
    legacy-plugin-v1.jar
    new-plugin-v2.jar
    missing-dependency-plugin.jar
    invalid-service-descriptor.jar
    duplicate-api-plugin.jar
    failing-init-plugin.jar
  configs/
    legacy-plugin.properties
    current-plugin.properties
  expected/
    outputs-v1.json
    lifecycle-events.json
~~~

Record artifact metadata alongside fixtures:

- Source commit and version.
- Compiler JDK and `--release` level.
- Compiled API/SPI version.
- Dependencies and SHA-256 checksums.
- Signatures and provenance where applicable.
- Supported host/JDK matrix.
- Confirmation that fixture data contains no PII or secrets.

Never fabricate `old-plugin.jar` by compiling legacy source against current APIs—that ceases to be an authentic historical binary fixture.

## 31. Incompatibility tests should fail predictably

Regression suites are not meant to force every historical plugin to pass across every future major release. Some old plugins are **intentionally unsupported**.

Negative contract test example:

~~~text
Given:
  - Host 3.0
  - Plugin 1.0 declares max Host API 2.x

Expect:
  - Plugin is rejected before receiving traffic.
  - An incompatibility error message is emitted.
  - Host continues operating with other plugins.
  - Plugin resources are not retained.
  - Metrics/alerts record the exact plugin ID.
  - No fake fallback impersonates plugin success.
~~~

Explicit unsupported-plugin tests verify safety boundaries cleanly instead of forcing unsafe hacks like exposing broad JDK internals or putting mixed API JARs onto a shared classpath.

## 32. Performance and resource lifecycle belong to operational contracts

Plugin v1 may work functionally on host v2 yet consume multiples more CPU or memory due to revised host call patterns or GC behavior.

Measure:

- Initialization and startup duration.
- Per-call latency and p95/p99 latency under load.
- Throughput and memory allocation rate.
- Active thread counts.
- Open file descriptors and sockets.
- Classloader memory retention across reloads or uninstalls.
- Shutdown duration and resource release.
- Retry/backoff load when plugins error.
- Queue saturation and concurrency behavior.

Hold plugin binaries, workloads, and resource caps steady when comparing JDKs. Upgrading the plugin simultaneously confounds JDK effects with implementation changes.

## 33. Contract tests for HTTP and event-driven plugins

Plugins frequently act as Kafka consumers or REST clients to downstream services. Java SPI tests can pass completely while external schema changes still crash production runs.

Example event payload:

~~~json
{
  "eventType": "order.created",
  "schemaVersion": 2,
  "eventId": "evt-100",
  "payload": {
    "orderId": "O-100",
    "amount": "125000.00",
    "currency": "VND"
  }
}
~~~

Verify:

- Consumer v1 tolerates message v2 during coexisting rollouts.
- Consumer v2 processes v1 backlog and dead-letter messages.
- Unknown enums and extra fields degrade gracefully.
- Idempotency keys persist unchanged through migration.
- Retries and manual replays preserve schema versions.
- Producers emit newer schemas only after consumers are ready.

For REST plugins, test status codes, headers, auth/TLS, payloads, and error semantics; for gRPC/Protobuf, test field-number evolution, enums, and generated stubs.

External wire contracts frequently outlive individual JDK or framework deployments; never test only new plugins against new payloads.

## 34. CI pipeline for API, SPI, and plugin compatibility

Illustrative pipeline:

~~~text
Stage 1 — Build library/host on target JDK
Stage 2 — Static API difference report
Stage 3 — Compile existing source clients
Stage 4 — Run precompiled old-client.jar against new API
Stage 5 — Load old-plugin.jar into new host
Stage 6 — ServiceLoader/JPMS/classloader contract tests
Stage 7 — Provider lifecycle/behavior tests
Stage 8 — DB/HTTP/broker integration tests
Stage 9 — Multi-JDK runtime matrix if committed
Stage 10 — Packaging and rollback simulation
~~~

Maven/Gradle reference commands:

~~~bash
# Maven using the repository Wrapper
./mvnw -B clean verify

# Gradle using the repository Wrapper
./gradlew clean test
~~~

These commands illustrate typical learner invocation steps, not build verification executed by editing documentation. Production pipelines must configure concrete test tasks, dependencies, JDK toolchains, and precompiled JAR fixtures explicitly.

### 34.1. Preserve artifacts and compatibility reports

Archive:

- Host and API/SPI versions, git commits, and build digests.
- JDK vendor/version and OS/architecture.
- Plugin artifact names, versions, and checksums.
- Compatibility matrix pass/fail results.
- Static API diff reports.
- Necessary discovery and class-loading logs.
- Failing callbacks and contract violations with context.
- Records of approved breaking changes.

Never proclaim "zero breaking changes" simply because monorepo CI compiled everything in one tree—partner plugins outside the monorepo still run older precompiled binaries.

## 35. Case study: reporting host upgrades JDK and SPI

Scenario:

~~~text
Host H1 / JDK 11
  SPI ReportPlugin v1
  Old plugin 1.2 already distributed to partners

Target:
Host H2 / JDK 21
  SPI ReportPlugin v2
  Many partner plugins not yet rebuilt
~~~

The team wants to query supported output formats:

~~~java
boolean supports(String format);
~~~

### 35.1. High-risk approach

1. Add `supports` as an abstract method in SPI v2.
2. Recompile the host and internal in-repo plugins.
3. Run unit tests using those freshly compiled plugins.
4. Ship H2.
5. In production, invoking an un-rebuilt partner plugin throws `AbstractMethodError`.

Green monorepo builds never prove precompiled provider binaries stay compatible when older binaries went untested.

### 35.2. Controlled migration workflow

**Step 1 — Inventory:** list active plugin versions, API/SPI versions, JDK targets, and dependencies.

**Step 2 — Golden binaries:** obtain real plugin JARs compiled against SPI v1 and archive checksums and metadata.

**Step 3 — Design backward compatibility:** weigh safe `default` methods, versioned interfaces, adapters, or capability negotiation.

**Step 4 — Static diff:** run API compatibility checks comparing `spi-v1.jar` and `spi-v2.jar`.

**Step 5 — Binary test:** execute `old-plugin-v1.jar` inside host H2 on JDK 21 without recompiling the plugin.

**Step 6 — Discovery test:** verify ServiceLoader, descriptors, and class loaders resolve the legacy provider.

**Step 7 — Behavior test:** exercise `id`, `render`, `supports`, lifecycle hooks, and unsupported format fallbacks.

**Step 8 — Integration test:** execute realistic report payloads, DB queries, HTTP calls, and queue interactions.

**Step 9 — Failure isolation:** ensure incompatible plugins disable cleanly with clear diagnostics instead of taking down the host.

**Step 10 — Rollout:** canary across representative plugin configurations while tracking callback failures, retries, and latency.

**Step 11 — Rollback:** verify plugin descriptors or persisted state created under H2 remain safe if rolling back to H1.

### 35.3. Required evidence

| Contract | Evidence |
|---|---|
| Binary API/SPI | API diff report + precompiled plugin fixtures |
| Provider discovery | ServiceLoader/JPMS test runs |
| Behavioral SPI | Conformance test suite and callback semantics |
| Dependencies | Resolved runtime classpaths + ClassLoader logs |
| Runtime JDK | Real tests on target JDK 21 |
| Data & external integrations | Historical fixtures and staging integration runs |
| Failure policy | Verified disabling/error reporting for incompatible plugins |
| Rollback | Host H1 validated against post-H2 state where required |

Only with this evidence in hand can teams truthfully state that "the new host continues supporting legacy plugins" across tested scope.

## 36. Questions to ask third-party plugin vendors

When external vendors own plugin source, host teams cannot patch plugins directly. Maintain a vendor checklist:

1. Which plugin version is officially verified against our target JDK and host version?
2. Which JDK and `--release` flag compiled the released plugin?
3. Does the plugin rely on JDK internal APIs or older bytecode libraries?
4. Does it employ custom class loading, deep reflection, or Java agents?
5. Which host API/SPI version range does it declare and support?
6. How does it implement or fall back on newly introduced SPI callbacks?
7. What is its plan for `javax`→`jakarta` namespace transitions if frameworks upgrade?
8. Does it ship custom JDBC/HTTP clients, TLS configs, or truststores?
9. Are signed artifacts and checksums published for verification?
10. Are test fixtures or staging endpoints available to host integration suites?
11. What is the release ETA and support lifecycle for JDK-compatible versions?
12. If a plugin malfunctions post-upgrade, can it be safely disabled or downgraded?

Never equate "latest plugin version" with target-JDK compatibility—verify release notes, official matrices, and executable runtime tests.

## 37. Common misconceptions

**"A green build proves API compatibility."** False. Precompiled legacy clients and plugins may not sit in the current build graph.

**"An SPI is just an interface, so adding methods is safe."** False. Adding abstract methods triggers `AbstractMethodError` only when the host invokes them on older providers.

**"Adding a default method is always safe."** False. Default method conflicts and unsuitable fallback semantics still break behavior.

**"Seeing a provider class inside the JAR means ServiceLoader finds it."** False. Descriptors, class loaders, type identity, constructors, and module exports all matter.

**"ClassLoader isolation eliminates every conflict."** False. Shared SPI interfaces require identical loader identity; child-first loading can bundle duplicate SPI copies and cause `ClassCastException`.

**"Plugin version ranges in descriptors guarantee compatibility."** False. Metadata states intent; only binary and runtime execution tests confirm compatibility.

**"Testing in-repo plugins covers everything."** False. You must also run unmodified third-party binary JARs from released versions.

**"If a plugin boots at startup, all features work."** False. Linkage and SPI callback failures frequently surface only on rarely executed paths.

**"You can move classpath apps to JPMS without testing service discovery."** False. Module graphs, `uses`/`provides`, and package exports alter provider resolution.

**"Re-running unit tests is enough after upgrading the JDK."** False. Agents, class loaders, SPI discovery, TLS, native libraries, and external contracts demand dedicated checks.

**"If a plugin fails, just catch Throwable and carry on."** False. Use proper isolation and cleanup policies instead of masking fatal linkage errors or faking success.

**"A plugin running Java 21 works on every Java 21 host."** False. Host SPIs, frameworks, and shared libraries enforce independent contract boundaries.

## 38. Pre-release checklist for Java compatibility migrations

- [ ] Recorded exact JDK, host, API/SPI, framework, and plugin versions.
- [ ] Separated source, binary, behavioral, and discovery compatibility tests.
- [ ] Inventoried all active third-party plugins.
- [ ] Preserved pre-migration compiled JARs intact without rebuilding them.
- [ ] Executed static API diff checks against baseline artifacts.
- [ ] Audited removed or altered methods, fields, constructors, and visibility modifiers.
- [ ] Reviewed abstract/default SPI methods, inheritance hierarchies, and dispatch behavior.
- [ ] Verified generics erasure and bridge methods on complex SPIs.
- [ ] Tested old precompiled clients vs. new libraries and old plugins vs. new hosts.
- [ ] Verified behavioral SPI guarantees with a conformance test suite.
- [ ] Audited callback ordering, resource ownership, and exception contracts.
- [ ] Tested ServiceLoader descriptors, provider visibility, and initialization.
- [ ] Validated JPMS `module-info` declarations when using the module path.
- [ ] Verified defining class-loader identity and protection against duplicate API JARs.
- [ ] Tested missing dependencies, malformed descriptors, conflicts, and init failures.
- [ ] Exercised thread-safety, timeouts, shutdown/reload, and leak-free cleanup.
- [ ] Tested Java agents, annotation processors, and relevant build plugins.
- [ ] Verified HTTP, event, and database external contracts used by plugins.
- [ ] Executed serialization and persisted-data fixtures created before the upgrade.
- [ ] Verified plugin checksums, signatures, provenance, and runtime permissions.
- [ ] Tested controlled failure isolation and clear alerts when plugins are disabled.
- [ ] Executed suites on production-like JDK runtimes and packaging layouts.
- [ ] Published the supported host/plugin/JDK matrix alongside clean rejection behavior.
- [ ] Tested rollback compatibility with plugins and persisted state touched after upgrade.
- [ ] Documented all approved breaking changes and deprecation timelines.

## 39. Conclusion

**Contract testing for APIs, SPIs, and third-party plugins** anchors regression verification in Java Advance Compatibility Migration. API changes affect external callers; SPI changes govern extension implementers; and full plugin platforms add layers around descriptors, ServiceLoader, JPMS, class loaders, lifecycles, dependency isolation, and security.

A rigorous test suite preserves **precompiled legacy binaries**, executes them against upgraded hosts, libraries, and JDKs, and validates not merely class loading but also method dispatch, runtime semantics, callback sequences, concurrency safety, persisted state, and downstream integrations. Static API diffs catch signature drift reliably, yet never substitute for live behavioral contract execution.

Where full backward compatibility is unattainable, combine **capability negotiation, adapters, or safe rejection policies** with explicit version bounds, actionable diagnostics, and partner upgrade schedules. Declare a migration successful only when every supported plugin truly **loads, executes, serves traffic, and shuts down cleanly in the target environment**—not merely when the host build turns green.
