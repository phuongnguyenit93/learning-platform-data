# Identifying Public APIs, SPIs, and Implementation Details Without Stability Guarantees

When upgrading a Java version or changing a framework, a program can stop working even though the classes and methods it used are still declared public. The reason is that **Java language accessibility** and **vendor compatibility guarantees** are not the same thing. A component may be accessible yet only serve internal purposes; a public interface may be designed for plugins to implement as an SPI; a documented API may have a deprecation policy or change behavior within published boundaries.

This lesson belongs to the **Java Advance Compatibility Migration** topic, **API Evolution** chapter, explaining how to identify the contract surface between an application, the JDK, frameworks, and external libraries. The goal is to know what is a **supported public API**, what is a **Service Provider Interface (SPI)** for provider authors, and what are **implementation details without stability guarantees** that should be avoided as long-term dependencies.

## 1. Three Common Types of Surfaces

### 1.1. Supported Public API

An Application Programming Interface is the set of integration points that a platform or library provides to consumers. In Java, an API includes more than method signatures:

- Classes, interfaces, enums, annotations, and public constructors.
- Methods, fields, parameter types, return types, and generic signatures.
- Contracts regarding null, exceptions, input errors, and boundary handling.
- Rules on state, object lifetime, and thread-safety.
- Data formats, serialization, encoding, and result ordering if guaranteed.
- Behavior defined by specification, API documentation, or version contract.

For example, java.util.List is a Java SE API described by official documentation. Consumers can program against the guaranteed methods of List without needing to know whether the implementation uses an array, linked nodes, or another structure.

A supported public API does not mean all behavior is immutable. The vendor can still fix bugs, change optimizations, deprecate, or remove components according to their policy and release lifecycle. Consumers must follow what is actually specified.

### 1.2. SPI for Providers

A Service Provider Interface is a contract for a third party to create an implementation that is called back by a framework or platform.

For example:

- JDBC has a mechanism for database drivers to participate in the ecosystem.
- java.nio.file.spi.FileSystemProvider is an extension point for filesystem providers.
- java.util.spi and java.text.spi contain extension points of the Java Platform.
- A framework may publish an authentication provider, serializer, task plugin, or storage adapter.

With a regular API, the application **calls** the service. With an SPI, the application or plugin **implements** an interface and the framework **calls back** into that implementation. An SPI can still be a supported public API, but the dependency direction and compatibility responsibilities differ.

### 1.3. Implementation detail

An implementation detail is a component serving how a library is implemented, not guaranteed by the vendor to be maintained as an external integration point:

- Classes belonging to internal or impl packages.
- Private data structures read via reflection.
- Compiler internals or runtime internals.
- Public classes used only between internal modules.
- Temporary resources, cache formats, and implementation-specific paths.
- Iteration order or timing not guaranteed by the contract.
- Specific exception types or error message contents not promised in documentation to be stable.

A public class can be an implementation detail. The fact that the compiler allows importing that class does not mean the vendor has to keep it in the next upgrade.

### 1.4. Quick Comparison Table

| Criterion | Public API | SPI | Implementation detail |
|---|---|---|---|
| Primary role | Consumer calls functionality | Provider implements for framework to call | Component used internally by library |
| Can it be public? | Usually yes | Usually yes | Can be |
| Important contract | Parameters, results, exceptions, behavior | Callbacks, lifecycle, discovery, concurrency | Usually unpublished |
| Evidence | API docs, specification, support policy | SPI docs, provider guide, service metadata | Source, internal annotations, packages, and documentation |
| Risk when upgrading | Signature/behavior changes | Incompatible provider | May disappear or change at any time |
| How to handle | Follow release notes and migration guide | Test from the provider side | Migrate to supported API/SPI |

## 2. Public Access Is Not a Stability Guarantee

Consider a hypothetical library:

~~~java
package com.example.cache.internal;

public final class CacheTable {
    public static int nextCapacity(int current) {
        return current * 2;
    }
}
~~~

The CacheTable class is public, so it can be accessed in certain classpath or module configurations. However, the internal package indicates it is very likely an implementation detail. If the application calls nextCapacity directly, changing the cache storage strategy in a new version can cause the application to fail at compile time or runtime.

The library should publish a contract such as:

~~~java
package com.example.cache.api;

public interface Cache<K, V> {
    V get(K key);
    void put(K key, V value);
}
~~~

The application depends on Cache, while the library can replace CacheTable without breaking the contract.

**Three questions must be distinguished:** Is it accessible? Did the vendor intend for external use? Under what policy does the vendor commit to maintaining it? The first question alone is not enough to identify a stable API.

Some libraries make classes public due to constraints from serializers, dependency injection, or module architecture. Therefore, a type being public needs to be cross-checked against documentation, annotations, release notes, and support policy.

## 3. Identifying Supported JDK APIs

For the JDK, prioritize the official specification and API documentation for the target Java version. Many standard APIs reside in java.util, java.time, java.net, java.nio, java.sql, java.security, and other documented packages.

You cannot draw absolute conclusions just by looking at the package prefix. For example:

| Component | Actual Classification |
|---|---|
| java.util.List | Documented Java SE API |
| java.time.Instant | Documented Java SE API |
| java.sql.Connection | Published API; JDBC driver provides implementation |
| java.nio.file.spi.FileSystemProvider | Published SPI |
| java.util.ServiceLoader | API for finding and loading providers |
| com.sun.source.tree.Tree | Documented compiler API in jdk.compiler |
| com.sun.tools.javac.* | Compiler implementation packages, should not be assumed to be stable APIs |
| jdk.internal.misc.Unsafe | Internal JDK API |
| sun.misc.Unsafe | Critical internal API in jdk.unsupported, does not carry the same guarantees as a Java SE API |

A prefix like com.sun does not automatically make every type internal; a public class provided by the JDK is also not automatically a standard API. Check the documentation for the exact module and exact JDK release.

### 3.1. Cases Using JDK Internal APIs

An application or dependency may rely on sun.misc.Unsafe, jdk.internal.*, compiler internals, or reflection into internal fields. Those dependency paths are easily affected when the JVM changes memory management, module encapsulation, or class structure.

If the source code uses internal APIs to manipulate atomic fields, evaluate VarHandle where appropriate. If using memory/native APIs, evaluate the public Foreign Function & Memory APIs on a JDK version that meets requirements. Do not mechanically replace one method with another: memory ordering, ownership, alignment, lifetime, and errors may differ.

If a third-party library needs a JDK internal API, prioritize upgrading the library to a version verified by the vendor on the target JDK. The application should not patch the library's implementation itself if a supported upgrade path exists.

## 4. JPMS: What Accessibility Do exports and opens Provide?

Java 9 introduced the Java Platform Module System. A module descriptor can declare:

~~~java
module com.example.orders {
    exports com.example.orders.api;
    opens com.example.orders.persistence to org.hibernate.orm.core;
    requires java.sql;
}
~~~

Meaning:

- exports provides accessibility to the package's public types to eligible modules.
- opens allows reflective access within the specified scope.
- requires defines dependencies between modules.

**An exported package is not synonymous with a permanently stable API.** A vendor may export a package for its own modules to communicate. There are also qualified exports that restrict consumers:

~~~java
module com.example.engine {
    exports com.example.engine.api;
    exports com.example.engine.bridge to com.example.engine.tools;
}
~~~

The bridge package is exported with restrictions; it does not mean every application should use it.

It is also necessary to distinguish between classpath and module path. An application running on the traditional classpath usually belongs to the unnamed module. When moving to the module path, the compiler/runtime may detect module readability violations or non-exported packages. A public class in a module that is not exported may still be inaccessible from another module.

### 4.1. Access-Opening Flags Do Not Make an API More Stable

You may encounter configurations such as:

~~~bash
java --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -jar app.jar
~~~

or:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

The flags above serve different access needs. They can help a legacy application or library get past a barrier during a transition period, but they do not create a guarantee to maintain implementation details.

During migration, record the component needing the flag, the opened package, the reason, the risk scope, and the dependency version expected to remove that need. Starting from Java 17, strong encapsulation of JDK internals was tightened under JEP 403, so some legacy access paths no longer work as they did on previous JDKs.

## 5. Identifying APIs and SPIs of Third-Party Frameworks or Libraries

For external dependencies, examine:

- Published API reference and Javadoc.
- Migration guides and release notes.
- Stability policy and version support schedule.
- Package conventions: api, spi, extension, internal, impl.
- Annotations such as @Internal, @ApiStatus.Internal, @ApiStatus.Experimental, or library-specific annotations.
- Module exports and qualified exports if the library uses JPMS.
- Official code samples and extension/provider writing guides.

For example, a library may have a structure like:

~~~text
com.example.framework.api.RequestContext
com.example.framework.spi.RequestHandlerProvider
com.example.framework.internal.FastDispatcher
com.example.framework.impl.DefaultRequestContext
~~~

Package names are initial signals, not enough to draw conclusions. A class in impl may be published for use as a default implementation; a class in api may be marked experimental or deprecated. You must read the contract for the exact release.

Javadoc tags @apiNote, @implSpec, and @implNote help explain the API contract and implementation obligations. They do not by themselves guarantee compatibility across all versions.

### 5.1. Application-Published APIs Can Also Leak Implementations

Consider a public method returning an internal type:

~~~java
package com.example.api;

public class ReportService {
    public com.example.internal.RowBuffer loadRows() {
        throw new UnsupportedOperationException();
    }
}
~~~

Consumers must reference RowBuffer to use the method. Thus, an implementation detail has leaked into the public signature, restricting the ability to change internal structure.

A clearer contract is:

~~~java
package com.example.api;

import java.util.List;

public interface ReportService {
    List<ReportRow> loadRows();
}
~~~

Where ReportRow is also a documented public API type. Designing the API surface needs to consider return types, generic types, checked exceptions, annotations, and inheritance types, not just method names.

## 6. SPI: Reverse Call Direction and Lifecycle Contracts

An API is usually a component that the application actively calls. An SPI usually requires the application to provide a provider for the framework to instantiate and call back.

~~~text
Application using feature
            |
            v
         Public API
            |
            v
    Framework / Platform
            |
            v
         SPI contract
            ^
            |
     Provider implementation
~~~

The framework can decide the number of provider instances, callback order, initialization time, close time, concurrency, and exception handling. Therefore, the fact that an SPI interface does not change its signature does not guarantee that an old provider is behaviorally compatible.

### 6.1. ServiceLoader Example

Suppose the reporting system publishes an interface:

~~~java
package com.example.report.spi;

public interface FormatterProvider {
    String id();
    String format(Report report);
}
~~~

Report here is an API type of the system, not an internal implementation. A provider:

~~~java
package com.example.report.json;

public final class JsonFormatterProvider implements FormatterProvider {
    @Override
    public String id() {
        return "json";
    }

    @Override
    public String format(Report report) {
        return report.toJson();
    }
}
~~~

The framework finds providers:

~~~java
ServiceLoader<FormatterProvider> loader =
        ServiceLoader.load(FormatterProvider.class);

for (FormatterProvider provider : loader) {
    System.out.println(provider.id());
}
~~~

The illustrative code does not list full imports and Report types; in a real project, the exact published APIs and packages must be used.

### 6.2. Registering Services on the Module Path

The module publishing the service type:

~~~java
module com.example.report {
    exports com.example.report.api;
    exports com.example.report.spi;
    uses com.example.report.spi.FormatterProvider;
}
~~~

A provider module:

~~~java
module com.example.report.json {
    requires com.example.report;

    provides com.example.report.spi.FormatterProvider
        with com.example.report.json.JsonFormatterProvider;
}
~~~

The provider implementation does not necessarily have to reside in an exported package intended for users. ServiceLoader can use module information to find providers according to the service contract.

If using the classpath, a common registration mechanism is the file:

~~~text
META-INF/services/com.example.report.spi.FormatterProvider
~~~

With the provider class name content:

~~~text
com.example.report.json.JsonFormatterProvider
~~~

When packaging a shaded JAR or fat JAR, ensure that META-INF/services descriptors are merged rather than overwritten. A provider may exist in the JAR yet fail to be discovered by ServiceLoader if the registration resource is lost.

### 6.3. Questions Specific to SPIs

Check the provider contract:

1. Does the framework create instances via constructor, factory, or dependency injection?
2. Can multiple providers be active at the same time?
3. Are providers selected based on priority, name, or iteration order?
4. Can callbacks be invoked concurrently from multiple threads?
5. Are there thread-safety or reentrancy constraints?
6. Is the provider allowed to hold caches or shared state?
7. When to initialize, flush, close, and dispose?
8. Which exceptions is the provider allowed to throw; how does the framework handle them?
9. Is there an API version or capability negotiation?
10. By what mechanism does the provider need to be packaged and discovered?

A provider that compiles successfully but fails to load, or loads but violates the new lifecycle, is still a failed SPI migration.

## 7. Distinguishing API Changes and SPI Changes

### 7.1. Consumer-Called API

Suppose a library provides:

~~~java
public interface SearchClient {
    List<Result> search(String query);
}
~~~

The new version changes it to:

~~~java
public interface SearchClient {
    List<Result> search(SearchRequest request);
}
~~~

Consumers using the old signature must modify their code. Previously compiled consumers may encounter linkage errors when running with the new library if the old method is removed.

When adding a new overload, old binary code may continue to link, but recompiling source code may introduce overload ambiguity with null, lambdas, or method references. Therefore, source compatibility and binary compatibility must be evaluated separately.

### 7.2. Provider-Implemented SPI

An initial SPI:

~~~java
public interface FormatterProvider {
    String format(Object value);
}
~~~

The new version adds an abstract method:

~~~java
public interface FormatterProvider {
    String format(Object value);
    boolean supports(Class<?> type);
}
~~~

Old providers without supports may fail to recompile. At runtime, calling the new method on an old provider may throw AbstractMethodError.

One evolution approach is a default method:

~~~java
public interface FormatterProvider {
    String format(Object value);

    default boolean supports(Class<?> type) {
        return true;
    }
}
~~~

However, a default method does not guarantee that every provider behaves correctly. The value true may not reflect the provider's capability, and a default method can interact with existing inheritance hierarchies. Testing with real providers is necessary.

### 7.3. Replaced Implementation Details

A framework can replace an internal class FastDispatcher with another implementation while preserving the public API. Consumers using the API can function normally. Consumers that imported FastDispatcher, cast to that class, or used reflection on private fields may fail even though the upgrade is valid according to the support policy.

That is why API/SPI boundaries and implementation code need to be audited before upgrading versions.

## 8. Analyzing Different Levels of Compatibility

| Compatibility Level | Question to Answer |
|---|---|
| Source | Does old consumer/provider source code compile with the new version? |
| Binary | Does compiled bytecode link and run with the new library? |
| Behavioral | Do results and side effects still conform to the contract? |
| SPI | Is the provider discovered, initialized, and called with the right lifecycle? |
| Runtime | Can the artifact run on the target JVM? |
| Operational | Do logs, metrics, startup, shutdown, and rollback work? |

An example of behavioral compatibility is HashMap iteration order. The API does not guarantee iteration order, so an application relying on the accidental order of the current JDK version is depending on an implementation detail. When the order changes, the bug lies in the application's expectation, even though the interface still honors the contract.

If business logic requires ordering, use a collection with a clear contract such as LinkedHashMap for insertion order, or sort the results using a Comparator.

Another example is asserting verbatim exception messages. Unless documentation guarantees the message, changing wording in a patch release is usually not a breaking API change.

## 9. Signs of Depending on Implementation Details

When inventorying source code, watch for these signals:

- Importing jdk.internal or sun.*.
- Importing com.sun.tools.javac instead of a published compiler API.
- Importing internal, impl, or private packages of a framework.
- Calling setAccessible(true), getDeclaredField, or getDeclaredMethod on JDK/framework classes.
- Calling Class.forName with concrete implementation names.
- Casting from a public interface to a concrete implementation.
- Extending a class not documented as an extension point.
- Reading internal resources, caches, temporary files, or metadata.
- Relying on unguaranteed timing, iteration order, or error messages.
- Requiring --add-opens or --add-exports to bypass encapsulation.
- Using APIs marked @Internal or @Experimental without evaluating the risk.
- Application public methods exposing internal types in their signatures.

This is an investigation checklist of signals. A package named impl sometimes contains a default implementation officially supported by the vendor. Conversely, an API in a clean-looking package may be marked experimental. Do not draw automatic conclusions based solely on names.

## 10. Identification and Inspection Tools

### 10.1. jdeps

The JDK's jdeps tool can analyze JAR dependencies and detect certain internal JDK APIs:

~~~bash
jdeps --jdk-internals app.jar
~~~

With dependencies on the classpath:

~~~bash
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
~~~

If analyzing a multi-release JAR, you can specify the target release:

~~~bash
jdeps --multi-release 21 --jdk-internals app.jar
~~~

The output shows static reference paths to JDK internals. It may not find every reflection path, dynamically constructed class name, runtime-loaded plugin, or dependency missing from the analyzed classpath. Having no warnings from jdeps is not enough to prove the application has zero internal dependencies.

### 10.2. jdeprscan

The jdeprscan tool helps detect usage of deprecated Java SE APIs:

~~~bash
jdeprscan --release 21 app.jar
~~~

To view APIs marked for-removal:

~~~bash
jdeprscan --for-removal --release 21 app.jar
~~~

Deprecated APIs differ from internal APIs. A supported API can be deprecated with a public replacement path; an internal API may never have been published as stable.

### 10.3. javap and jar

View public members in a class file:

~~~bash
javap -public -classpath library.jar com.example.api.SearchClient
~~~

View class metadata:

~~~bash
javap -verbose -classpath library.jar com.example.api.SearchClient
~~~

View a JAR's module declaration when present:

~~~bash
jar --describe-module --file library.jar
~~~

These tools provide technical evidence about access and bytecode. They do not by themselves indicate how long the vendor commits to maintaining the API.

### 10.4. Comparing APIs Across Versions

Tools such as Revapi or japicmp can detect changes to class/method/field signatures, superclasses, interfaces, and visibility between two releases. They should be configured to compare the exact supported public surface.

If every internal package is included in the report and every change is treated as a breaking change, the results will have a lot of noise. If only bytecode is compared, changes in exceptions, lifecycle, serialization, or SPI semantics may be missed.

### 10.5. Finding Usage in the Repository

You can search quickly using ripgrep:

~~~bash
rg -n "jdk[.]internal|sun[.]misc|com[.]sun[.]tools[.]javac" src
~~~

Find reflection:

~~~bash
rg -n "setAccessible|getDeclaredField|getDeclaredMethod|Class[.]forName" src
~~~

Find imports by package convention:

~~~bash
rg -n "import .*([.]internal[.]|[.]impl[.])" src
~~~

Ripgrep is only text search, so it can miss generated sources, dependency bytecode, or dynamically constructed class names. Cross-check both compile/runtime dependencies and deployment configurations.

## 11. Determining Actual Dependency Versions

Before concluding that a framework changed an API, you must know which dependency version is actually resolved, including transitive dependencies.

Maven:

~~~bash
./mvnw dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Trace a module using Gradle:

~~~bash
./gradlew dependencyInsight --dependency some-library --configuration runtimeClasspath
~~~

Graph results can be affected by BOMs, parent POMs, Gradle platforms, constraints, resolution rules, and profiles. The actual version sometimes differs from the version shown in a declaration found via search.

Beyond compile/runtime dependencies, also account for annotation processors, Java agents, plugins, dynamically loaded drivers, native libraries, and provider discovery resources. These components may also depend on implementation details that the main source does not import.

## 12. Example: Replacing a JDK Internal API with a Public API

Some older codebases use internal Base64 utilities instead of the Java SE API. Since Java 8, java.util.Base64 provides a public API for Base64 encoding/decoding.

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class TokenCodec {
    public static String encode(String input) {
        byte[] bytes = input.getBytes(StandardCharsets.UTF_8);
        return Base64.getEncoder().encodeToString(bytes);
    }

    public static String decode(String input) {
        byte[] bytes = Base64.getDecoder().decode(input);
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
~~~

When replacing an old implementation, you must verify:

- Basic Base64, URL-safe Base64, or MIME?
- Are there line breaks and padding?
- Is the input UTF-8 or binary data?
- How is invalid input handled?
- Does the stored format or format exchanged over APIs change?

New code using a supported API may alter wire data if the wrong variant is chosen. Fixing internal dependencies must preserve the business contract, not just make the code compile.

## 13. Example: Moving from an Implementation Class to an Extension Point

Suppose the application depends on an internal framework class:

~~~java
import com.example.framework.internal.DefaultRetryPolicy;

public class JobRunner {
    private final DefaultRetryPolicy policy =
            new DefaultRetryPolicy();
}
~~~

The framework does not guarantee the constructor and behavior of DefaultRetryPolicy. When upgrading versions, the class may change or disappear.

If the framework publishes a contract:

~~~java
package com.example.framework.api;

public interface RetryPolicy {
    boolean shouldRetry(int attempt, Throwable failure);
}
~~~

and a supported factory, the application can depend on RetryPolicy instead of a concrete implementation class.

~~~java
RetryPolicy policy = RetryPolicies.exponentialBackoff(3);
~~~

Factory names are for illustration only; when modifying a real project, you must reference the exact API published in the framework documentation.

After switching, check retry counts, backoff, jitter, retryable errors, and idempotency of side effects. A replacement API may be syntactically valid yet differ in behavior.

## 14. Preview, Incubator, and Experimental APIs

Not every new API in the JDK has the same stability status as a final Java SE API.

### 14.1. Preview

A preview feature may require compiler and runtime options:

~~~bash
javac --enable-preview --release 21 Example.java
java --enable-preview Example
~~~

The syntax to enable preview only illustrates the mechanism; which features are in preview depends on the exact release being used. A preview feature may change or be removed before becoming final.

### 14.2. Incubator

An incubator module in the JDK is used to experiment with APIs and gather feedback. Even though distributed with the JDK, that API can change significantly as it evolves. Some releases used modules named jdk.incubator.*.

### 14.3. Experimental in Frameworks

A library may mark an API as experimental, unstable, or incubating. If the product needs to use that feature, clearly record the reason, tested version, owner tracking release notes, and migration plan when the API changes.

It is not necessarily required to ban all experimental APIs, but you should not inadvertently treat them as multi-year stable contracts.

## 15. Building a Pre-Migration Risk Matrix

| Component | Classification | Evidence | Recommended Action |
|---|---|---|---|
| Java SE documented API | Public API | Java API docs | Check deprecation and run tests |
| Framework documented API | Public API | Javadoc, migration guide | Upgrade per vendor policy |
| Plugin/provider interface | SPI | SPI guide, callback contract | Test discovery, lifecycle, concurrency |
| Framework internal package | Implementation | Documentation, annotations, source | Replace with API or extension point |
| JDK internals | Implementation | jdeps, docs | Upgrade dependency or replace API |
| Deep reflection | Internal coupling | Source and runtime flags | Remove or change integration approach |
| Preview/incubator | Not final | JDK docs, JEP | Accept risk intentionally |
| Deprecated for removal | API at risk of removal | API docs | Plan replacement |

Priority also depends on the criticality of the business flow, number of consumers, upgrade frequency, and rollback capability.

A library that only uses an internal class in tests may have a different impact than a production service calling an internal API on the main processing path.

## 16. Testing Contracts from Both Sides

### 16.1. For API Consumers

Test according to contract documentation:

- Input values, output values, and boundary cases.
- Null, empty, timezone, encoding, locale if relevant.
- Documented exceptions.
- Thread-safety and idempotency.
- Serialization, data format, and consumer compatibility.
- New version behavior on the target runtime.

Do not write tests that tightly lock onto internal details such as cache structure, exception messages, or iteration order when the API does not guarantee them.

### 16.2. For SPI Providers

Test as an independent plugin:

1. Package the provider properly for classpath/module path.
2. Register via ServiceLoader or the mechanism required by the framework.
3. Let the framework discover the provider automatically.
4. Initialize and invoke main callbacks.
5. Check exceptions, retries, shutdown, and cleanup.
6. Check concurrency and reentrancy if required by the contract.
7. Check multiple providers coexisting.
8. Run with the target JDK/framework version.

Source-compatible does not mean the provider loads successfully. A shaded JAR missing META-INF/services can prevent the framework from finding the provider even when the source compiles normally.

### 16.3. For Module Boundaries

If using JPMS, run tests on the actual module path. Tests on the classpath may miss issues with exports, opens, service binding, and readability. If temporary access opening is needed, record the flag and the conditions for removal.

## 17. Process for Identifying and Handling Dependency Points

### Step 1 — Inventory Contracts

Separate the lists:

- JDK/framework APIs that the application calls.
- Public APIs that the application publishes to other modules.
- SPIs that the application implements.
- SPIs that the application publishes to third parties.
- Implementation classes and reflection currently in use.

### Step 2 — Verify Support Sources

For each integration point, locate documentation, annotations, module exports, release notes, and compatibility policy. If there is no evidence yet, mark it **unverified**, rather than assuming it is stable.

### Step 3 — Map Risk to Actual Execution Paths

Look at usage in compile, runtime, tests, plugins, annotation processors, and agents. Not every import has the same impact; usages on production execution paths usually require higher priority.

### Step 4 — Choose an Approach

You can keep APIs currently supported; upgrade providers when an SPI changes; move from concrete implementations to facades/factories; replace unsupported libraries; create adapters to protect consumers; remove unnecessary reflection; or keep temporary JVM flags with clear deadlines and owners.

### Step 5 — Verify by Contract Type

- API: compile, binary linkage, and behavior.
- SPI: discovery, callbacks, lifecycle, and thread-safety.
- Public library: source/binary compatibility with consumers.
- Internal dependency: confirm the dependency path has been removed.
- JPMS: module path, exports, opens, and service wiring.

### Step 6 — Record the Decision

You can use the template:

~~~text
MODULE
  Name:
  Current JDK / target JDK:
  Framework and dependency versions:
  Runtime / packaging:

INTEGRATION SURFACE
  Package and type:
  Consumer or provider:
  API / SPI / implementation detail:
  Source or artifact location:

CONTRACT EVIDENCE
  Documentation and version:
  Module exports / opens:
  Stability annotation:
  Deprecation status:
  Vendor support policy:

MIGRATION RISK
  Source compatibility:
  Binary compatibility:
  Behavioral compatibility:
  SPI lifecycle and discovery:
  Reflection or native access:

DECISION
  Keep / replace / adapt / defer:
  Supported replacement:
  Owner and milestone:

VALIDATION
  Build:
  API compatibility test:
  SPI integration test:
  Runtime test:
  Rollback:
~~~

A valuable record must allow reviewers to trace back from a specific dependency to contract evidence, risks, and post-migration verification methods.

## 18. Common Misconceptions

**“A public class is definitely a supported API.”** Incorrect. Public is access control. Check documentation and support policy.

**“An exported package must be kept forever by the vendor.”** Incorrect. JPMS controls accessibility; the version policy defines compatibility commitments.

**“An SPI is just a Java interface.”** Not enough. Providers must also satisfy discovery, lifecycle, callbacks, thread-safety, and error rules.

**“A successful build means the provider is compatible.”** Incorrect. The provider may fail to load, lack a suitable constructor, or error during framework callbacks.

**“If jdeps reports no internals, the application is safe.”** Not enough. Reflection, dynamic loading, and binary dependencies may not be fully analyzed.

**“Adding --add-opens solves everything.”** The flag only opens access in some cases. It does not turn an implementation detail into a supported API.

**“Deprecated means it will be removed immediately in the next release.”** Not necessarily. Check the deprecation status, for-removal, and release notes for the specific version.

**“Replacing an internal API with a new API always preserves behavior.”** Not certain. Check data formats, exceptions, concurrency, and important side effects.

## 19. Takeaways When Finalizing a Migration Plan

Before upgrading the JDK or framework, answer:

1. Is this component a consumer-called API, a provider-implemented SPI, or an implementation detail?
2. What evidence shows the vendor actually supports it?
3. Is the package exported, and if so, at what scope?
4. Are there internal, experimental, deprecated, or for-removal annotations?
5. Is there reflection, native access, or hardcoded internal class names?
6. What changes could break source, binary linkage, behavior, or SPI lifecycle?
7. Is there a replacement API/SPI published by the vendor?
8. Which tests prove that consumers and providers work on the target version?

When API, SPI, and implementation boundaries are clearly identified and documented, migration no longer relies on guessing from class names or a successful compilation. Development teams can prioritize removing unstable dependency paths, using appropriate extension points, and protecting truly critical contracts with tests on the target JDK and framework.
