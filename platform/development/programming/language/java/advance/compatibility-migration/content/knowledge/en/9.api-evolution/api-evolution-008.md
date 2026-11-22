# Maintaining compatibility for SPI implementers and third-party plugins

A Java platform can fully preserve its API for callers yet still break plugins developed by customers or partners. Simply adding an abstract method to an extension interface, changing when callbacks are invoked, altering the provider discovery mechanism, or raising the minimum Java level can cause a previously working plugin to stop running.

In the **Java Advance Compatibility Migration** topic, the **API Evolution** chapter, maintaining compatibility for **Service Provider Interface (SPI)** implementers and third-party plugins is a problem of **extension contracts**, not merely keeping class names and method signatures. This lesson presents how to identify who implements an SPI, how to evolve interfaces safely, distinguishing source and binary compatibility, preserving plugin discovery mechanisms and lifecycle, along with versioning, testing, and release strategies to reduce risks when upgrading Java or frameworks.

## 1. Why does an SPI require a separate evaluation approach?

APIs and SPIs can both be public interfaces or classes. The difference lies in the **direction of dependency and control**.

With a typical API:

~~~text
External application
       |
       | calls method
       v
Platform API
       |
       v
Platform implementation
~~~

With an SPI:

~~~text
Platform / plugin host
       |
       | discovers, instantiates, and invokes callbacks
       v
SPI contract
       ^
       | implements / extends
       |
Third-party plugin
~~~

In the SPI model, plugin developers typically have to write code depending on interfaces published by the platform. At runtime, it is the platform that chooses when to instantiate and call that implementation. Therefore, a small change in the SPI contract can force **multiple independent plugin vendors** to modify and re-release code.

Distinguish three parties:

- **SPI owner:** the team maintaining the extension interface and rules.
- **Plugin author/provider:** partners or the community implementing the SPI.
- **Plugin host:** the runtime/framework that discovers, instantiates, invokes, and manages providers.

Within a product, the SPI owner and plugin host may be the same team. However, plugin authors usually sit outside that team's release cycle. It is this gap in release cadence that makes backward compatibility especially critical.

### 1.1. Not every public interface is an SPI

A public interface that an application only receives to invoke methods on is a consumer API. A public interface that third parties are invited to implement can be an SPI. An interface in an internal package may not be supported for external implementation, even if the compiler permits it.

Check the official documentation: **Does the platform invite third parties to implement an interface or subclass a class?** If not, do not assume every point that can be implemented or extended is guaranteed to be a stable extension point.

## 2. What contracts does a compatible SPI consist of?

When evaluating an SPI, separate at least the following layers.

| Contract layer | What implementers need to know | Example failure upon change |
|---|---|---|
| Source | Type names, methods, generics, annotations, checked exceptions | Old plugins fail to recompile |
| Binary | JVM descriptors, class/interface hierarchy, visibility | NoSuchMethodError, AbstractMethodError, IncompatibleClassChangeError |
| Runtime/JDK | Class-file version, module access, dependencies, bytecode APIs | UnsupportedClassVersionError, IllegalAccessError |
| Discovery | ServiceLoader, descriptors, modules, plugin registries | Plugin exists but is not discovered |
| Construction | Constructors, factories, dependency injection | Unable to instantiate provider |
| Lifecycle | init, start, invoke, stop, close, reload | Resource leaks or callbacks at the wrong time |
| Behavior | Meaning of results, exceptions, retries, transactions | Plugin runs but yields wrong results |
| Concurrency | Thread-safety, reentrancy, thread context | Race conditions, deadlocks |
| Configuration | Properties, metadata, environment, secrets | Plugin cannot read configuration |
| Operations | Logs, metrics, errors, timeouts, rollbacks | Host cannot isolate faulty plugins |

**Preserving method signatures is necessary in many cases, but not sufficient.** An SPI whose source code does not change can still break compatibility if the host changes callback ordering or begins invoking providers concurrently.

## 3. Identifying the supported SPI surface

Before upgrading versions, catalog the extension points that third parties actually use. Information sources usually include:

- API/SPI reference and migration guides.
- Lists of official and community plugins.
- Module descriptors: exports, uses, provides.
- META-INF/services configurations on the classpath.
- Plugin registries, manifests, or annotations defined by the framework.
- Base classes/plugins documented as subclassable.
- Version compatibility matrices and published artifacts.
- Extensions implemented by partners whose source is not in the main repository.

A classification example:

~~~text
com.example.platform.api.Document
    -> public API: applications and providers use the data type

com.example.platform.spi.DocumentImporter
    -> SPI: plugin providers are invited to implement

com.example.platform.internal.ImporterDispatcher
    -> implementation detail: used internally by the host

com.example.partner.csv.CsvImporter
    -> partner plugin: implements DocumentImporter
~~~

Package names are a useful signal, but do not replace documentation. A class in an spi package is not guaranteed to be a supported extension point in every version; a base class in an api package may be meant only for calling, not for inheritance.

### 3.1. Finding dependencies that plugins already have

Identify:

1. Which SPI version was the plugin compiled against?
2. Which JVM does the plugin run on?
3. Which SPI version is the host loading?
4. Does the plugin bundle a copy of the SPI itself?
5. Does the plugin also use internal implementation classes?
6. Are there transitive dependencies or Java agents affecting class loading?

If a plugin accidentally bundles the host's API into its own JAR, a type identity conflict can occur: two classes with the exact same fully qualified name loaded by two different classloaders are not necessarily the same type to the JVM. Clearly define which dependencies are provided by the host and which belong to the plugin.

## 4. Source, binary, and behavioral compatibility of an SPI

These three compatibility levels must be evaluated separately.

### 4.1. Source compatibility

A provider previously implemented:

~~~java
package com.example.platform.spi;

public interface Importer {
    String id();
    String importText(byte[] source);
}
~~~

Old provider:

~~~java
public final class CsvImporter implements Importer {
    @Override
    public String id() {
        return "csv";
    }

    @Override
    public String importText(byte[] source) {
        return new String(source, java.nio.charset.StandardCharsets.UTF_8);
    }
}
~~~

If the new SPI adds an abstract method:

~~~java
public interface Importer {
    String id();
    String importText(byte[] source);

    boolean supportsStreaming();
}
~~~

then CsvImporter must implement the new method in order to recompile, unless it is an abstract class or has special inheritance conditions. This is a **source-incompatible** change for providers.

### 4.2. Binary compatibility

When only replacing the SPI/host JAR without recompiling the plugin, the JVM can load the old provider. However, if the host calls supportsStreaming on an implementation that lacks the corresponding method, AbstractMethodError may occur.

This shows:

- A change can allow an old class to load yet still fail when the new callback is invoked.
- Do not take successful plugin instantiation as proof of full binary compatibility.
- You must actually invoke the callback paths that the new host will use.

Other changes—such as changing a method from instance to static, changing an interface to a class, changing visibility, or changing descriptors—can cause other linkage errors.

### 4.3. Behavioral compatibility

Suppose the interface keeps the importText method, yet previously the host called it once per document; the new version splits data into multiple chunks and invokes the method multiple times. The provider may no longer process properly, even though classes, signatures, and bytecode remain valid.

Similarly, if the host starts invoking callbacks from multiple threads, a provider holding unsynchronized mutable state can encounter race conditions. The SPI contract must specify whether or not there is a thread-confinement guarantee.

A useful question to ask:

> Will old plugins continue to be discovered, instantiated, receive callbacks with the right semantics, and release resources properly on the new host?

This is a much stricter standard than “compiled successfully”.

## 5. Evolving SPI interfaces with default methods

For Java 8 and above, default methods can provide a default implementation for new methods.

~~~java
package com.example.platform.spi;

public interface Importer {
    String id();
    String importText(byte[] source);

    default int priority() {
        return 0;
    }
}
~~~

Old providers do not have to add priority when recompiling. For providers already compiled against the old SPI, the new host can invoke the default implementation in many typical compatibility scenarios.

### 5.1. When is a default method a reasonable choice?

- An accurate and safe default behavior can be defined.
- Old providers can genuinely continue operating without knowing about the new capability.
- The new method does not force plugins to manage new state or lifecycle.
- The default value does not introduce unintended changes to selection order or security.
- There are no significant method inheritance conflicts.

In the priority example, defaulting to 0 keeps older providers at a baseline priority. However, if the host uses priority to select a single plugin, deterministic tie-breaking must be designed. Do not assume ServiceLoader enumeration order is a selection contract unless explicitly promised by the documentation.

### 5.2. Default methods do not automatically guarantee compatibility

There are risks:

- An implementation already has a method with the same name but different semantics.
- Multiple parent interfaces provide conflicting default methods.
- The default value alters behavior inappropriately for old plugins.
- The new host relies on functionality that the default implementation cannot perform properly.
- The new method leaks types not present on the older JDK baseline.

Do not add a default method merely to make compile errors disappear if the actual contract requires every provider to supply a meaningful implementation.

### 5.3. Capabilities can be checked via opt-in

An old SPI can remain intact, while new functionality is placed into a secondary interface:

~~~java
public interface Importer {
    String id();
    String importText(byte[] source);
}

public interface StreamingImporter extends Importer {
    void start();
    void accept(byte[] chunk);
    String finish();
}
~~~

Host checks the capability:

~~~java
if (importer instanceof StreamingImporter) {
    StreamingImporter streaming = (StreamingImporter) importer;
    streaming.start();
    // Call accept(...) for each chunk according to the contract
    String result = streaming.finish();
} else {
    // Keep the importText(...) flow of the old provider
}
~~~

This approach avoids forcing every old provider to implement streaming. In exchange, the host must manage two execution paths and explicit fallback rules.

## 6. Using versioned SPIs instead of breaking old contracts

When a feature requires major changes to semantics or lifecycle, consider creating a new SPI rather than heavily modifying an interface already implemented by many plugins.

Example:

~~~java
public interface ExporterV1 {
    byte[] export(Document document);
}

public interface ExporterV2 {
    void begin(ExportContext context);
    void write(DocumentChunk chunk);
    void end();
}
~~~

The host can maintain an adapter from V1 to V2:

~~~java
public final class LegacyExporterAdapter {
    private final ExporterV1 legacy;

    public LegacyExporterAdapter(ExporterV1 legacy) {
        this.legacy = legacy;
    }

    public byte[] export(Document document) {
        return legacy.export(document);
    }
}
~~~

The adapter above illustrates keeping the V1 call path; to fully support V2, you must design how chunks are aggregated, buffering is managed, and lifecycle fits appropriately. Not every streaming change can be safely adapted from an API returning a byte array.

### 6.1. Parallel strategy

During a transition period:

1. The host still registers and loads V1 providers.
2. The host also discovers V2 providers.
3. The two provider types have separate registries or service descriptors.
4. Logs/metrics indicate which plugins are still running V1.
5. Documentation states the future deprecation milestone for dropping V1.
6. Remove V1 only in a pre-announced release according to the support policy.

Crucially, the host must actually run tests against already-released V1 plugins, not just against V1 source recompiled with the new library.

### 6.2. Semantic versioning is a signal, not a guarantee

A policy may stipulate:

- Patch: bug fixes without changing the published contract.
- Minor: adding API/SPI in a backward-compatible way.
- Major: may make incompatible contract changes.

However, actual versioning practices vary across vendors. You cannot infer that a plugin is guaranteed to be compatible simply because a minor number increased. Read the policy documentation and execute compatibility testing.

## 7. Preserving the provider discovery path: ServiceLoader

Java ServiceLoader is the standard mechanism for a host to locate implementations of a service type.

Suppose the published API is:

~~~java
package com.example.codec.spi;

public interface TextCodec {
    String id();
    byte[] encode(String text);
    String decode(byte[] data);
}
~~~

A plugin:

~~~java
package com.example.codec.utf8;

import com.example.codec.spi.TextCodec;
import java.nio.charset.StandardCharsets;

public final class Utf8Codec implements TextCodec {
    public Utf8Codec() {
    }

    @Override
    public String id() {
        return "utf8";
    }

    @Override
    public byte[] encode(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    @Override
    public String decode(byte[] data) {
        return new String(data, StandardCharsets.UTF_8);
    }
}
~~~

Host:

~~~java
import com.example.codec.spi.TextCodec;
import java.util.ServiceLoader;

ServiceLoader<TextCodec> providers = ServiceLoader.load(TextCodec.class);

for (TextCodec codec : providers) {
    System.out.println(codec.id());
}
~~~

This is an application-level source example; in real deployments, package structure, modules, and class-loading paths must be consistent.

### 7.1. Registration via classpath

With traditional JARs, a plugin declares a resource:

~~~text
META-INF/services/com.example.codec.spi.TextCodec
~~~

Contents:

~~~text
com.example.codec.utf8.Utf8Codec
~~~

The file name must be the fully qualified name of the service type. The contents must be the provider name following the classpath registration mechanism. A typo or a missing resource during packaging is enough to prevent the provider from being discovered.

When using shading or fat JARs, multiple dependencies may contain the same META-INF/services path. The build must merge descriptors according to the packaging tool's rules rather than keeping only one file.

### 7.2. Registration via module path

The service type is placed in an API module:

~~~java
module com.example.codec.api {
    exports com.example.codec.spi;
}
~~~

Provider module:

~~~java
module com.example.codec.utf8 {
    requires com.example.codec.api;
    provides com.example.codec.spi.TextCodec
        with com.example.codec.utf8.Utf8Codec;
}
~~~

Host module:

~~~java
module com.example.codec.host {
    requires com.example.codec.api;
    uses com.example.codec.spi.TextCodec;
}
~~~

These declarations inform the module system of the service relationship. Provider implementations do not necessarily need to export a separate package for direct calls by the host. The platform has a mechanism to instantiate providers from appropriate provides declarations.

When shifting from classpath to module path, specifically verify:

- Has the module been resolved into the active layer?
- Does the host declare the appropriate uses clause?
- Does the provider declare provides accurately?
- Do constructors/factories comply with ServiceLoader rules in the deployment model?
- Which packages are exported and which only need reflective access?
- Does the host use the right classloader or ModuleLayer to locate providers?

### 7.3. Discovery changes that can break plugins

Some risky changes:

- Renaming the package or fully qualified name of the service interface.
- Changing the registration mechanism without supporting the old path.
- Changing the classloader used to locate providers.
- Moving to the module path without migrating service descriptors or provides clauses.
- Changing provider filtering or selection mechanisms.
- Changing constructor, factory, or metadata requirements.
- Failing to merge resources during repackaging.
- Implicitly requiring plugin signing or new configuration without a transition roadmap.

If discovery must change, the host should support the old mechanism in parallel during a transition period, or release adapters/upgrade tooling with clear instructions.

## 8. Classloader isolation and type identity

Many plugin systems use dedicated classloaders to isolate each plugin's dependencies. This is a frequent source of errors during Java migrations.

~~~text
Bootstrap / Platform classes
             |
             v
      Host classloader
      - SPI interface
      - Host API
             |
       +-----+------+
       |            |
       v            v
Plugin A loader  Plugin B loader
- A classes      - B classes
- A libraries    - B libraries
~~~

If each plugin packages its own copy of the service interface instead of sharing the interface loaded by the host, the following can happen:

~~~text
com.example.spi.Importer loaded by HostLoader
!=
com.example.spi.Importer loaded by PluginLoader
~~~

Two classes with the same name loaded by different classloaders can be type-incompatible. The result can be ClassCastException, ServiceConfigurationError, or failures when the host checks instanceof.

### 8.1. Dependency partitioning rules

It is usually advisable to define clearly:

- **Host-provided:** SPI API, shared contract types.
- **Plugin-private:** plugin's own dependencies, implementations, and resources.
- **Shared approved libraries:** only libraries published as shared.
- **Forbidden bundled libraries:** classes not allowed to be packaged redundantly alongside the host API.

With Maven, the provided scope can be used for host-provided parts where appropriate. With Gradle, compileOnly can be used, though actual packaging must still be inspected. These two configurations only express build-time dependencies; they do not automatically prove the plugin classloader is arranged correctly.

### 8.2. Be careful with the context classloader

Some frameworks and ServiceLoader use the thread context classloader depending on API calls and initialization mechanisms. If the plugin system switches threads or classloaders, provider discovery behavior can change.

When upgrading the host/JDK, confirm:

- Which classloader loads the SPI?
- Which classloader loads the provider?
- Is the thread context classloader used?
- Do async tasks preserve the required context?
- Are providers unloaded/reloaded cleanly according to the lifecycle?
- Are there static or thread-local caches holding old classloaders and causing memory leaks?

Do not treat success on a flat local classloader as proof that a plugin system with isolation works in production.

## 9. Maintaining Java baseline and artifact compatibility for plugins

Plugins developed outside the organization may be built on different JDKs. The host upgrading its JDK does not mean every plugin must be recompiled immediately, but it must preserve the ability to load the class files and APIs that plugins use.

### 9.1. Distinguishing the versions

For plugins, record:

| Component | Question |
|---|---|
| Build JDK | Which JDK does the plugin author use to run Maven/Gradle? |
| Compiler/toolchain | Which JDK does javac actually come from? |
| Release target | What is the minimum bytecode and Java platform API version? |
| Plugin SPI version | Which SPI contract was the plugin compiled against? |
| Host runtime | Which JVM does the plugin actually run on? |
| Host-supported versions | Which SPI versions does the host commit to accepting? |

For example, a plugin built with JDK 21 targeting Java 17 release can be compatible with a Java 17 runtime when all dependencies and APIs are also compatible. A plugin built for Java 21 will not run on a Java 17 JVM merely by changing the host SPI version.

### 9.2. Major class-file versions

Common milestones:

| Java | Class-file major |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

If a plugin's class-file version is higher than the runtime supports, the host may hit UnsupportedClassVersionError.

You can inspect a specific class file:

~~~bash
javap -verbose -classpath plugin.jar com.example.plugin.MyProvider
~~~

However, checking a single class is not enough: a plugin may contain multiple JARs, generated classes, or Multi-Release JARs. You also need to check the API baseline, native dependencies, and third-party libraries.

### 9.3. Compile release configuration

Maven:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

The configuration above illustrates using a newer compiler while still producing Java 17 artifacts. In a real system, check whether the Gradle/Maven version, plugins, annotation processors, and dependencies satisfy the release target.

If the host supports plugins on multiple JDKs, run the test matrix on the exact published runtimes, not only compiling with --release.

## 10. Lifecycle changes: risks are often greater than signature changes

An SPI can keep every method unchanged yet change when or how they are called.

Example:

~~~java
public interface Plugin {
    void initialize(PluginContext context);
    void start();
    void stop();
}
~~~

The contract needs to describe the sequence:

~~~text
DISCOVERED
     |
     v
CONSTRUCTED
     |
     v
INITIALIZED
     |
     v
STARTED -----> CALLBACKS
     |              |
     |              v
     |           STOPPING
     v              |
STOPPED <------------+
     |
     v
RELEASED
~~~

This is an illustrative diagram. Real systems must define valid transitions, failure handling, and restart state.

Important questions:

- Is initialize called exactly once?
- Can callbacks happen before start?
- Can stop be called after initialize fails?
- Are start/stop idempotent?
- Can a plugin instance be recreated after stop?
- Can the host run multiple instances concurrently?
- Is the context allowed to be used after stop?
- Does shutdown have a deadline or timeout?

If the new host starts invoking callbacks concurrently, old non-thread-safe plugins can break. If the host switches from one system-wide instance to one instance per request, cache or connection pool management can also change.

### 10.1. Do not change exception handling silently

The SPI should specify what exceptions callbacks may throw and how the host reacts:

- Ignore the plugin and continue?
- Disable the plugin for the running session?
- Retry?
- Roll back the transaction?
- Fail-fast the entire application?
- Log and return an error to the consumer?

For example, if the host previously caught exceptions and skipped faulty providers, the new version failing entire requests can cause an old plugin to trigger wider system disruption. Any change to the failure policy must be documented and tested.

### 10.2. Thread-safety and reentrancy

Explicitly specify:

- Can a provider be invoked on multiple threads simultaneously?
- Can a callback invoke a host API and lead to nested callbacks?
- Is there thread-affinity, transaction context, or security context?
- Does the host hold any locks while invoking the plugin?
- Is the plugin allowed to block or perform I/O?

When using virtual threads or changing executors, do not infer that the threading contract remains unchanged. Specifically inspect plugins using ThreadLocal, synchronized blocks, callback ordering, or libraries depending on thread identity.

## 11. Data, error, and behavioral contracts of plugins

SPIs often pass data types defined by the host. When these types evolve, plugins can be affected even if the service interface does not change.

### 11.1. DTOs and input data

Example:

~~~java
public interface PaymentPlugin {
    Decision evaluate(PaymentContext context);
}
~~~

If PaymentContext begins returning null on a field that was previously always non-null, plugins can fail with NullPointerException. If Decision gets a new enum constant added, code using a switch statement without default may fail to handle it fully.

Document:

- Nullability.
- Immutability/mutability of DTOs.
- Ownership and lifetime of data.
- Time format and timezone.
- Encoding.
- Enum extensibility.
- Schema/serialization version.
- Compatibility level of error codes.

### 11.2. Controlling default behavior

When adding a new capability, the safe approach is usually:

- The new capability is opt-in.
- Old providers follow the old processing path.
- The host can detect unsupported providers.
- Fallbacks do not violate security or correctness.
- Logs/metrics exist to track the proportion of providers using the old path.

Do not allow an old provider by default to perform a new operation without a guaranteed contract. In security or payment domains, a wrong fallback can be more dangerous than a clearly surfaced error.

### 11.3. Contract tests matter more than checking class presence

An SPI test should simulate the exact inputs the new host will send, along with expectations for outputs, exceptions, timeouts, transactions, and cleanup. Plugins need to be tested as standalone published artifacts rather than always compiled together with the new host.

## 12. Version negotiation and capability discovery

Some plugin platforms require explicit version or capability declarations to decide whether to load a plugin.

Illustrative metadata example:

~~~text
plugin.id=com.example.csv-importer
plugin.version=2.4.1
spi.min=1
spi.max=2
requires.java=17
capabilities=batch-import,csv
~~~

This is a host-defined illustrative format, **not a built-in metadata standard of Java ServiceLoader**.

The host can use metadata to:

1. Reject plugins not supporting the SPI version the host requires.
2. Select a V1/V2 adapter.
3. Block plugins requiring a higher Java runtime.
4. Check permissions/capabilities before running.
5. Display clear compatibility errors to operators.
6. Record metrics by version and capability.

### 12.1. Compatibility by version range

Avoid merely comparing version strings with lexicographic operators. Use the system's valid versioning rules and explicitly declare major/minor/patch or schema versions.

Example support table:

| Host version | Supported SPI | Tested plugins |
|---|---|---|
| Host 3 | SPI 1, SPI 2 | Providers V1 and V2 |
| Host 4 | SPI 2 | Provider V2 |
| Host 5 | SPI 2, SPI 3 | Providers V2 and V3 |

The table above is an illustrative design only. In a real system, publish the compatibility policy, deprecation milestones, and verified combinations.

A plugin self-declaring version support is not sufficient proof it works; the host still needs to test functionality and verify dependencies/classloaders.

## 13. Controlled SPI change workflow

An SPI upgrade should be treated as a change-management process.

### Step 1 — Inventory existing plugins

Record:

- In-house plugins developed by the company.
- Third-party, open-source, or partner plugins.
- Customer-built plugins.
- Plugin and SPI versions currently in use.
- Supported Java/OS versions.
- Whether the plugin has source available or only binary artifacts.
- Owners and plugin updateability.

Do not assume all plugins reside in the same repository or are rebuilt together with the host.

### Step 2 — Write down the current contract

Document service types, methods, constructors/factories, discovery, lifecycle, error semantics, threading, security, and configuration. Separate what has been committed to from unpublished implementation details.

### Step 3 — Classify the planned changes

| Change type | Risk | Approach |
|---|---|---|
| Add optional capability | Usually can be made compatible | Default method or extension interface |
| Add abstract method | Old providers may fail compile/callbacks | Consider default, adapter, or SPI V2 |
| Remove/rename method | Source/binary break | Keep bridge or version it |
| Change parameter/return type | Binary descriptor may change | New API/SPI or adapter |
| Change callback timing | Behavioral break | Preserve old behavior or opt-in |
| Change discovery | Plugins not discovered | Support old registration in parallel |
| Raise Java baseline | Plugins or host cannot run on old runtimes | Publish matrix and test |
| Change classloader | Type identity and resource visibility | Verify host/plugin packaging |
| Add security requirement | Providers may lose permissions | Capability negotiation and transition notice |

Do not apply a single tactic to every change. Assess whether a correct and safe fallback can be maintained or a breaking release must be announced.

### Step 4 — Choose an implementation approach

Common options:

- Keep the old SPI unchanged, add a new interface.
- Add default methods with documented semantics.
- Build an adapter so the new host supports old providers.
- Maintain two service registries during the transition period.
- Add capability/version metadata.
- Release an SDK or test kit for plugin authors.
- Change the major version and publish a migration guide when compatibility cannot be preserved.

### Step 5 — Update documentation and examples

Documentation should include:

- Supported SPIs by host version.
- Minimum Java runtime.
- How to compile plugins and declare dependencies.
- How to register providers.
- Threading/lifecycle/error contracts.
- Optional features and how to declare capabilities.
- Items to be deprecated and removal dates.
- An example migrating a real plugin from V1 to V2.
- How to verify compatibility before releasing.

### Step 6 — Maintain a compatibility window

If the product must support third-party plugins, have a window where the host accepts both old and new providers when feasible. When V1 is nearing removal, warn early, log deprecations, and provide a clear upgrade path.

## 14. Testing SPI compatibility with old artifacts

A common mistake is checking out old plugin source and compiling it against the new SPI. That detects source compatibility, but can mask binary compatibility and actual packaging issues.

Maintain a **corpus of plugin fixtures**:

~~~text
fixtures/
  plugin-v1-built-with-java-17.jar
  plugin-v1-with-service-descriptor.jar
  plugin-v2-modular.jar
  plugin-with-private-dependencies.jar
  plugin-using-context-classloader.jar
  plugin-with-lifecycle-state.jar
~~~

File names are illustrative only. Actual fixtures should be verified artifacts, stored alongside SDK versions, checksums, and build instructions.

### 14.1. Build a compatibility test matrix

Example:

| Host | Provider artifact | Runtime | Tests |
|---|---|---|---|
| New host | Pre-built Plugin V1 | Target JDK | Loading, callbacks, and shutdown |
| New host | Recompiled Plugin V1 | Target JDK | Source compatibility |
| New host | Plugin V2 | Target JDK | New capabilities |
| Old host | Plugin V2 if committed to | Supported old JDK | Backward compatibility |
| New host | Plugin from isolated classloader | Target JDK | Type identity, isolation |
| New host | Modular plugin | Module path | uses/provides and access |

Distinguish **new host running old plugins** (backward compatibility) from **old host running new plugins** (forward compatibility). Many products only commit to the first direction.

### 14.2. Which tests must be run?

- **Discovery:** ServiceLoader or registry finds the right provider.
- **Instantiation:** Constructor/factory is invoked properly.
- **Type contract:** Interfaces are loaded from the right classloader.
- **Callbacks:** Every callback the host uses is exercised.
- **Semantics:** Results and errors conform to the contract.
- **Lifecycle:** initialize, start, stop, cleanup, and failure paths.
- **Concurrency:** Multi-threaded scenarios if permitted by the contract.
- **Dependencies:** No missing classes, version conflicts, or incompatible bytecode.
- **JPMS:** exports, opens, uses, provides on the actual module path.
- **Operations:** Logs, metrics, isolation, timeouts, rollbacks.

Tests must include failure paths, not only the happy path. A provider might work when processing valid documents yet leak threads or connections when an exception occurs.

### 14.3. Test kit for plugin developers

A platform can provide a Plugin Compatibility Test Kit for partners to run before releasing:

~~~text
plugin-test-kit
  -> verify metadata
  -> load provider
  -> validate service discovery
  -> execute contract cases
  -> exercise lifecycle
  -> inspect runtime dependencies
  -> report supported host/SPI versions
~~~

The test kit should provide meaningful error messages and clearly record test kit, host, and JVM versions. A plugin passing the test kit still needs integration tests for real use cases, yet it reduces the cost of catching common contract errors early.

## 15. Checking API/binary compatibility with tools

The following tools assist investigation. They do not themselves replace SPI behavioral testing.

### 15.1. javap

Inspect the public surface of an interface in the artifact:

~~~bash
javap -public -classpath spi-api.jar com.example.platform.spi.Importer
~~~

Inspect additional descriptors and metadata:

~~~bash
javap -verbose -classpath spi-api.jar com.example.platform.spi.Importer
~~~

Helps identify method signatures and the class-file version of the actual artifact.

### 15.2. jdeps

Check dependencies and usage of JDK internal APIs:

~~~bash
jdeps --jdk-internals plugin.jar
~~~

For relevant dependencies, add classpath/module path as appropriate. jdeps performs static analysis and may miss reflection, dynamic loading, and all runtime-loaded plugins.

### 15.3. API diff

Revapi or japicmp can compare versions of spi-api.jar to detect changes:

- Removed classes/interfaces.
- Removed methods or changed descriptors.
- Access modifiers.
- Supertypes/interfaces.
- Annotations and certain metadata.
- Changes risking source/binary incompatibility.

However, a “no breaking changes” API diff does not prove lifecycle or behavioral compatibility. Every SPI change must be verified with real providers.

### 15.4. Build dependency graph

Maven:

~~~bash
./mvnw dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Pay attention to the actually resolved spi-api version, host-provided dependencies, plugin-bundled dependencies, and provider artifacts.

## 16. Faulty plugins: isolation and rollback capability

When the host begins loading incompatible plugins, clear operational behavior is required:

- Do not mask linkage errors by catching every Throwable and continuing arbitrarily.
- Log the plugin ID, version, SPI version, and cause.
- Do not leak secrets or user data in diagnostics.
- Allow disabling plugins if functionality is optional.
- Expose health status or alerts when a provider fails to load.
- Do not let one faulty plugin take down the entire host if the architecture can isolate safely.
- Have a plan to revert to the previous host/runtime/plugin artifacts.

The decision to fail-fast or skip a plugin must depend on business criticality. A mandatory security plugin may need to block startup if missing; an optional report-export plugin might be temporarily disabled with a clear message. Do not silently skip providers on critical processing paths.

### 16.1. Rollback is not just reverting the JAR

If a new SPI changes data formats, schemas, or plugin configuration, the old host might fail to read already-written state. Rollback plans must consider:

- Database/schema version.
- Plugin metadata.
- Caches or serialized state.
- Messages already sent.
- In-flight jobs.
- Native resources or external services.
- Service registries and classloader state.

In many cases, rollback requires ensuring bidirectionally compatible formats or a data recovery plan, not just swapping container images.

## 17. Release guidelines for SPI providers

A platform project should establish specific rules to reduce unintended breaking changes.

**Design minimal SPIs:** Publish only callbacks that are truly needed. Avoid forcing providers to subclass internal base classes or access private host state.

**Prefer composition:** Use small interfaces, documented DTOs, and opt-in capabilities rather than a monolithic interface continuously accumulating methods.

**Document dependency directions:** Explicitly state which artifacts the host provides, which artifacts plugins must bundle, and supported version ranges.

**Do not overuse default methods:** Add only when the fallback is sufficiently correct, safe, and testable.

**Manage lifecycle explicitly:** Specify invocation timing, concurrency, deadlines, errors, shutdown, and instance reuse.

**Publish a roadmap:** Deprecate, maintain adapters, warn, and remove only at milestones aligned with the support policy.

**Automate backward testing:** CI runs plugin fixtures precompiled against the legacy SPIs the product commits to supporting.

**Monitor real plugins:** Collect statistics on versions/capabilities in use where permitted by privacy and organizational policy, to know when legacy paths can be retired.

## 18. Example roadmap for upgrading SPI V1 to V2

Suppose the platform has plugins importing data from files. SPI V1 provides:

~~~java
public interface FileImporter {
    String format();
    Object importFile(byte[] content);
}
~~~

The new requirement is processing large data via streaming, with cancellation and progress.

A plan that does not cause an immediate breaking change could be:

### Phase A — Keep V1

The host still accepts V1 plugins. Documentation points out memory and file size limits without changing existing methods.

### Phase B — Introduce V2

Add StreamingFileImporter with published callbacks and lifecycle. The host checks whether a plugin implements V2 and executes the new path when appropriate.

~~~java
public interface StreamingFileImporter {
    String format();
    void begin(ImportContext context);
    void accept(byte[] chunk);
    Object finish();
    void cancel();
}
~~~

ImportContext is a platform contract type. In a real system, ownership, threading, exceptions, backpressure, and cleanup must be clearly defined.

### Phase C — Support both

- V1 continues receiving byte[] as before.
- V2 is invoked via the streaming mechanism.
- The host logs and records metrics identifying plugin versions.
- The test kit tests V1/V2 providers in parallel.
- The host raises warnings if V1 processes files exceeding resource limits.

### Phase D — Announce V1 removal milestone

When policy permits removing V1, publish a migration guide, source examples, and verification tools. Only switch to a host version that drops V1 support after announcing it, assessing the ecosystem, and accepting the support plan.

Some systems may keep V1 long-term if adapter cost is low. There is no need to remove every old SPI just because a new SPI exists.

## 19. Compatibility profile template for plugins

Use the following record when preparing a migration:

~~~text
HOST
  Host name/version:
  Current JDK:
  Target JDK:
  Runtime classpath or module path:
  Plugin loader model:

SPI CONTRACT
  Service interface:
  Current SPI version:
  Target SPI version:
  Public DTOs:
  Discovery mechanism:
  Construction contract:
  Lifecycle callbacks:
  Concurrency contract:
  Error and timeout policy:

PLUGIN INVENTORY
  Plugin ID:
  Vendor/owner:
  Plugin version:
  Build release:
  SPI version compiled against:
  Bundled/shared dependencies:
  Source available?:
  Deployment criticality:

CHANGE ASSESSMENT
  Added/removed/changed methods:
  Default methods:
  DTO/schema changes:
  Capability flags:
  JPMS and classloader changes:
  Behavioral differences:
  Support/deprecation policy:

VALIDATION
  Old plugin binary on new host:
  Recompile old plugin:
  Service discovery:
  Callback/lifecycle tests:
  Concurrency/error tests:
  Runtime integration:
  Packaging and shading:
  Rollback test:

DECISION
  Compatible / requires adapter / breaking:
  Workaround and expiry:
  Required partner action:
  Owner:
  Release milestone:
~~~

A good record must indicate **which plugin version was tested on which host**, rather than simply writing “plugin supported” in general.

## 20. Common misconceptions

### “The interface still exists so the plugin will definitely run”

Incorrect. The host may call new methods, change lifecycle, or no longer discover providers under old registrations.

### “Just recompiling the plugin is enough”

Insufficient. Old plugin binaries must be tested to verify backward compatibility; recompiling can mask compatibility bugs with already-released artifacts.

### “Default methods solve every change”

Incorrect. They are only suitable when the fallback has valid semantics. For required features, a new SPI or opt-in capability can be safer.

### “ServiceLoader will automatically find all plugins”

Not always. Discovery depends on classpath/module path, service descriptors, uses/provides, classloaders, or ModuleLayer. Improper packaging can make providers disappear.

### “Plugins using the same class name are the same type”

False in systems with multiple classloaders. JVM type identity also depends on the classloader defining the class.

### “Just keeping the same Java source level is enough”

Insufficient. Plugins also have dependencies, bytecode releases, used Java APIs, module access, agents, and runtime behavior.

### “Old SPIs can be removed in a minor release without affecting anyone”

Do not assume that. Version commitments must be based on published policies and the inventory of existing plugins, not merely on version numbers.

### “If a plugin fails, skip it so the host continues”

It depends on business requirements. For plugins mandatory for security or payments, skipping can be more dangerous than failing fast. There must be an explicit failure policy.

## 21. Summary

Maintaining compatibility for SPI implementers and third-party plugins requires thinking in terms of a **two-way contract**. Platform providers must keep stable what has been published for plugins to implement; plugin authors must follow the callback, discovery, lifecycle, and runtime rules supported by the host.

A sustainable strategy includes these principles:

1. **Identify the SPI accurately:** distinguish user-called APIs, externally implemented extension points, and implementation details.
2. **Do not check only compilation:** evaluate source, binary, behavioral, lifecycle, discovery, JPMS, and classloader compatibility.
3. **Evolve with transition paths:** prefer appropriate default methods, extension interfaces, adapters, or versioned SPIs when needed.
4. **Protect released plugins:** run legacy binary fixtures on the new host/JDK, not just recompiled source.
5. **Manage the ecosystem:** version matrices, capability negotiation, metadata, documentation, test kits, and deprecation timelines.
6. **Deployable and rollback-ready:** monitor failing plugins, maintain clear failure policies, and preserve safe fallback options.

When these conditions are verified using real artifacts and contract tests, the platform can evolve its Java API without forcing the entire external plugin ecosystem to upgrade simultaneously or suffer unexpected breakage.
