# Metadata Bundled in JARs and Hints Provided by Spring Integrations

A Java library can run normally on the JVM yet lack information needed when an application is compiled into a **GraalVM Native Image**. Frameworks often access classes, methods, resources, serialization types, or JDK proxies in ways that static analysis cannot fully infer. A native-compatible library needs to provide metadata so the compiler knows which dynamic elements must be retained.

There are two common ways library authors provide this information: **bundling reachability metadata directly inside the JAR**, or providing a **Spring integration** that contributes `RuntimeHints` during Spring AOT. Additionally, GraalVM maintains a community metadata repository for many third-party libraries that do not yet package their own metadata. These mechanisms can complement one another, though they differ in origin, scope, and when they are loaded.

This lesson shows how to read metadata layouts inside JARs, use the GraalVM Reachability Metadata Repository with Gradle/Maven, write a `RuntimeHintsRegistrar` for Spring, test hints, and handle missing or overlapping metadata.

## 1. Why Must External Libraries Provide Metadata?

GraalVM Native Image statically analyzes call paths from entry points to decide which classes, methods, and resources to include in the executable. When a library performs dynamic access based on data only available at runtime, the compiler may not know which targets to retain.

Consider a payment SDK example:

~~~java
public final class PaymentCodec {

    public PaymentRequest decode(String payload)
            throws ReflectiveOperationException {

        Class<?> type = Class.forName(
            "com.acme.payment.model.PaymentRequest"
        );

        Constructor<?> constructor = type.getDeclaredConstructor();
        Object request = constructor.newInstance();

        // Payload decoding omitted for illustration.
        return (PaymentRequest) request;
    }
}
~~~

On the JVM, the class loader can locate classes by string name. With Native Image, classes and constructors must be identified at build time. If the compiler cannot infer this reflection path, the application may fail with a missing registration error when running natively.

An external library is usually the best place to know:

- Which classes are loaded dynamically.
- Which constructors, methods, or fields are invoked via reflection.
- Which resources are read by name or pattern.
- Which interfaces are passed into a JDK dynamic proxy.
- Which types are serialized/deserialized through dynamic mechanisms.
- Which native/JNI entries need metadata.

Therefore, **library authors should package metadata close to the code performing dynamic access**. Applications using the library do not have to guess internal details or copy metadata from multiple places.

## 2. Three Common Metadata Sources

In a Spring Boot Native Image application, metadata can come from three sources:

| Source | Provided by | Where stored | When used |
|---|---|---|---|
| Metadata bundled in JAR | Library author | `META-INF/native-image/...` inside the JAR | Native Image reads from classpath at build time |
| GraalVM Reachability Metadata Repository | GraalVM community and library maintainers | Separate repository, looked up by dependency coordinates and version | Native Build Tools fetches/loads during native build |
| Spring `RuntimeHints` | Spring Framework, Spring Boot, or library integration module | Java code/annotations/`META-INF/spring/aot.factories` | Spring AOT invokes registrars and emits metadata for native build |

Some libraries may simultaneously have metadata in their JAR and an entry in the community repository. A Spring integration may also register hints for the same library. In such cases, understand whether entries supplement or duplicate each other, and avoid overly broad reflection member exposure.

**Do not assume there is only a single source.** Inspect the actual metadata fed into the native build, the library version, and the integration in use.

## 3. Metadata Directly Inside the JAR

GraalVM Native Image searches for reachability metadata on the classpath. Under the current schema, the main file is `reachability-metadata.json`, typically placed under a path namespaced to the library:

~~~text
payment-sdk.jar
└── META-INF/
    └── native-image/
        └── com.acme/
            └── payment-sdk/
                └── reachability-metadata.json
~~~

This path ties metadata to the artifact, preventing name collisions across multiple libraries. When the JAR is a dependency of the application and sits on the native build classpath, its metadata can be collected by Native Image alongside other metadata.

Minimal example content:

~~~json
{
  "reflection": [
    {
      "type": "com.acme.payment.model.PaymentRequest",
      "allDeclaredConstructors": true,
      "methods": [
        {
          "name": "validate",
          "parameterTypes": []
        }
      ]
    }
  ],
  "resources": [
    {
      "glob": "com/acme/payment/schema/*.json"
    }
  ]
}
~~~

This example requests keeping the declared constructors of `PaymentRequest`, the `validate()` method, and matching schema resources. In real libraries, register only the exact constructors/members needed instead of enabling all fields, methods, and constructors for every class.

Current metadata can describe reflection, JNI, resources, resource bundles, serialization, proxies, and several other dynamic features. Exact schemas evolve across GraalVM versions; check against the schema used by your toolchain.

## 4. Legacy Metadata vs. Current Metadata

Older Native Image projects commonly packaged several separate JSON files:

~~~text
META-INF/native-image/
├── reflect-config.json
├── resource-config.json
├── proxy-config.json
├── jni-config.json
└── serialization-config.json
~~~

Newer GraalVM versions support the unified `reachability-metadata.json` format. File names, schemas, and certain fields can differ across toolchain generations.

| Format | Purpose | Notes |
|---|---|---|
| `reachability-metadata.json` | Unified schema for dynamic features | Prefer per target GraalVM documentation and schema |
| `reflect-config.json` | Reflection in legacy configuration | Verify compatibility with the GraalVM version in use |
| `resource-config.json` | Classpath resources in legacy configuration | Can be replaced by the `resources` section of the new schema |
| `proxy-config.json` | JDK dynamic proxies in legacy configuration | New schema describes proxies in unified metadata |
| `jni-config.json` | JNI access in legacy configuration | Check schema and support by version |

Do not rename a legacy file to `reachability-metadata.json` while keeping its original contents. They are two different formats. If a library supports multiple GraalVM versions, verify a compatible metadata packaging strategy and test against the declared supported toolchains.

## 5. How Metadata Inside a JAR Is Loaded by Native Image

Native Image reads metadata from classpath entries at build time. For Maven/Gradle applications, dependency JARs on the native build classpath can contribute their own metadata.

General flow:

~~~mermaid
flowchart TD
    A["Spring Boot Application"] --> B["Native build classpath"]
    C["payment-sdk.jar"] --> B
    D["json-library.jar"] --> B
    E["jdbc-driver.jar"] --> B
    B --> F["Locate META-INF/native-image"]
    F --> G["Read reachability metadata"]
    H["Spring AOT RuntimeHints"] --> I["AOT-generated metadata"]
    G --> J["GraalVM reachability analysis"]
    I --> J
    J --> K["Native executable"]
~~~

Each dependency can contribute its own metadata. Native Image merges information from eligible sources during the build.

Several things need to be verified:

- The JAR is actually on the classpath of the native build task.
- Metadata files are not stripped from the artifact during packaging.
- Paths are properly placed under `META-INF/native-image`.
- The schema is compatible with the GraalVM version.
- Declared classes/members/resources exist in the artifact.
- Transitive dependencies referenced by metadata are also present.
- Shading/relocation tools do not overwrite or drop metadata.

**Having a metadata file in the source tree is not enough.** Verify the file made it into the final JAR and that the JAR is used in the native build.

## 6. Packaging Metadata When Developing a Library

If you develop `payment-sdk`, place metadata in the module's resources:

~~~text
payment-sdk/
└── src/
    └── main/
        └── resources/
            └── META-INF/
                └── native-image/
                    └── com.acme/
                        └── payment-sdk/
                            └── reachability-metadata.json
~~~

Gradle or Maven will package the resource file into the JAR like any regular resource. Library users do not need to manually copy metadata into their application if the JAR is on the native build classpath.

After packaging, verify:

~~~bash
jar tf build/libs/payment-sdk.jar | grep META-INF/native-image
~~~

With Maven:

~~~bash
jar tf target/payment-sdk.jar | grep META-INF/native-image
~~~

You can extract the contents to verify:

~~~bash
unzip -p build/libs/payment-sdk.jar \
  META-INF/native-image/com.acme/payment-sdk/reachability-metadata.json
~~~

On Windows, `jar tf` works if the JDK is in `PATH`; you can use `jar xf` to extract into a temporary directory and read the JSON file. Only inspecting the packaged artifact proves the metadata was actually bundled.

## 7. Why Does the GraalVM Reachability Metadata Repository Exist?

Not every library was designed from the start for Native Image. Some popular libraries perform dynamic accesses whose authors have not yet shipped metadata in the JAR. To avoid duplicated effort across individual applications, the community maintains the **GraalVM Reachability Metadata Repository**.

The repository contains metadata organized by library Maven coordinates and supported versions. GraalVM Native Build Tools can query this repository to fetch dependency metadata when creating a native image.

The repository serves to:

- Supply metadata for libraries that do not package their own.
- Share verified configurations across multiple projects.
- Track metadata by artifact version.
- Reduce the need for every application to recreate the same set of hints.
- Provide a place to report and contribute when a dependency lacks metadata or has incomplete metadata.

The repository is a community metadata source, **not proof that every version of every library is supported**. You must check the exact `groupId`, `artifactId`, and version in use.

## 8. Native Build Tools Automatically Uses the Repository

GraalVM Native Build Tools provides Gradle and Maven plugins. These plugins integrate with the Reachability Metadata Repository to look up metadata for libraries in the dependency graph.

With Gradle, run:

~~~bash
./gradlew nativeCompile
~~~

With Maven:

~~~bash
./mvnw -Pnative package
~~~

Depending on plugin version and project configuration, the plugin can automatically download the selected metadata repository and apply metadata during the native build. Check your plugin configuration and logs for the version in use, especially when building offline, behind a proxy, or in CI without repository access.

Some projects need to pin versions of GraalVM Native Build Tools and the metadata repository for reproducible builds. Do not allow uncontrolled plugin upgrades or repository version changes, because new metadata can alter or change dynamic access behavior.

Spring Boot does not automatically provide all hints for every third-party library. Spring Boot relies on the GraalVM Reachability Metadata Repository and metadata supplied by the library/integration itself for cases beyond Spring's inference capabilities.

## 9. Checking Dependencies Missing Metadata With Gradle

Native Build Tools provides a task to list dependencies that lack metadata in the repository.

~~~bash
./gradlew listLibrariesMissingMetadata
~~~

This task helps identify direct external runtime dependencies not yet supported by the repository and may output a report or corresponding issue links, depending on plugin version.

Its results do not mean all dynamic access paths have been tested. A library with metadata may still have uncovered code paths or behavior changes in newer versions.

When deeper investigation is needed:

1. Check the dependency coordinates and version in the report.
2. Verify whether the dependency is an actual runtime dependency.
3. Check whether metadata was pulled into the native build by the plugin.
4. Run native tests covering the features provided by the library.
5. If metadata is missing, consider adding temporary hints and contributing upstream.

Do not automatically dismiss a dependency from the report just because it is an auxiliary library. A transitive dependency can still perform reflection or dynamic resource access at runtime.

## 10. Checking Dependencies Missing Metadata With Maven

With the GraalVM Maven plugin, you can run:

~~~bash
./mvnw native:list-libraries-missing-metadata
~~~

This goal scans direct external runtime dependencies as supported by the plugin, cross-checks against the metadata repository, and may write a JSON report under `target/native`.

When reading the results, distinguish between:

- Dependency has no metadata in the repository.
- Dependency has metadata, but a specific code path still lacks hints.
- Dependency is not used in the runtime artifact.
- Dependency is only for test or build purposes.
- Metadata is available, but the plugin is not configured to use it.

If the task reports missing metadata, you do not necessarily have to write all hints yourself immediately. First check release metadata, existing issues, the library's native support, and the vendor's recommended integration approach.

## 11. Embedding Repository Metadata Into a JAR for External Builds

Normally, the metadata repository is only used during native builds managed by Native Build Tools. However, sometimes an application is packaged as a JAR first, and another tool later converts that JAR into a native image, such as Paketo Buildpacks or a custom organizational pipeline.

In that scenario, you can **copy repository metadata into the JAR itself** so downstream tools can discover the metadata from the classpath.

With Gradle, Native Build Tools provides the `collectReachabilityMetadata` task. You can wire the task output into the JAR:

~~~groovy
tasks.named("jar") {
    from collectReachabilityMetadata
}
~~~

The task downloads metadata into `build/native-reachability-metadata` following the `META-INF/native-image/...` layout. Adding the output to the JAR lets the artifact carry the necessary metadata for external native conversion steps.

With Maven, GraalVM Native Build Tools provides the `add-reachability-metadata` goal. You can declare an execution:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>add-reachability-metadata</id>
            <goals>
                <goal>add-reachability-metadata</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

This goal is typically bound to the `generate-resources` phase per plugin configuration. Verify the exact behavior with the Native Build Tools version in use.

**Not every application needs to copy repository metadata into the JAR.** If the native image is built directly by the plugin already integrated with the repository, the plugin can use the metadata without repackaging it inside the application JAR.

## 12. Spring RuntimeHints Is Another Source

Spring Framework provides the `RuntimeHints` API to describe dynamic accesses that Spring AOT needs to pass to GraalVM.

Runtime hints can describe:

- Reflection: classes, constructors, methods, and fields.
- Resources: files or patterns on the classpath.
- Serialization: Java serialization data types.
- JDK dynamic proxies: sets of interfaces to proxy.

Spring AOT collects hints while processing the `ApplicationContext` and emits the corresponding native configuration. This is ideal when a library integrates deeply with Spring and knows the exact dynamic accesses needed during operation of its own components.

Example of a library needing reflection for a request model, reading schemas, and creating an interface proxy:

~~~java
public final class PaymentSdkRuntimeHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
            PaymentRequest.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS
        );

        hints.resources().registerPattern(
            "com/acme/payment/schema/*.json"
        );

        hints.proxies().registerJdkProxy(
            PaymentGateway.class
        );
    }
}
~~~

Imports are omitted to focus on the API. Choose the exact `MemberCategory` matching the actual operation; if code only reads metadata or only invokes a constructor, do not expose all members.

## 13. Activating a Registrar With @ImportRuntimeHints

A `RuntimeHintsRegistrar` is only called when Spring knows how to register it. A common way to declare it is using `@ImportRuntimeHints` on a relevant component or configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentSdkRuntimeHints.class)
class PaymentSdkNativeConfiguration {
}
~~~

If the library provides Spring Boot auto-configuration, this configuration can be registered via Spring Boot's auto-configuration mechanism. Hints are then contributed only when the corresponding integration is enabled.

Another option is placing the annotation directly near the component needing hints:

~~~java
@Component
@ImportRuntimeHints(PaymentSdkRuntimeHints.class)
class PaymentClient {
    // SDK dynamic access operations.
}
~~~

Spring Framework recommends placing `@ImportRuntimeHints` as close as possible to the component that needs the hints. When the component is not registered in the `BeanFactory`, its associated hints do not need to be contributed either. This helps minimize unnecessary metadata.

Do not use a single global registrar for all features if only a small module needs specific resources or reflection. Split hints by component or integration for easier testing and maintenance.

## 14. Registering RuntimeHintsRegistrar via META-INF/spring/aot.factories

For libraries wanting static registrar registration, Spring supports the file:

~~~text
META-INF/spring/aot.factories
~~~

Example contents:

~~~properties
org.springframework.aot.hint.RuntimeHintsRegistrar=\
com.acme.payment.PaymentSdkRuntimeHints
~~~

Spring AOT discovers implementations declared in this file and invokes `registerHints` at build time. This suits infrastructure libraries that want to contribute hints without tying the registrar to a specific bean.

Important notes:

- The file must reside in resources and be packaged into the JAR.
- Interface and implementation names must use exact packages.
- If multiple JARs supply a file at the same path, check the packaging tool's resource merge mechanism.
- Registrars must not depend on business beans or call external services during hint registration.
- If hints are only needed when a specific component is used, `@ImportRuntimeHints` usually provides clearer scoping.

## 15. Where Should GraalVM Metadata vs. Spring Hints Be Placed?

The choice depends on who consumes the library:

| Scenario | Approach to consider |
|---|---|
| Pure Java library, no Spring dependency | Package GraalVM reachability metadata inside the JAR |
| Library with dynamic accesses shared across frameworks | JAR metadata or contribute to GraalVM Reachability Metadata Repository |
| Library with Spring integration logic, needing to know which components are registered | Spring `RuntimeHintsRegistrar` and `@ImportRuntimeHints` |
| Spring Boot starter providing auto-configuration | Registrar attached to the corresponding auto-configuration or component |
| Application making its own custom dynamic reflection/resource calls | Hints inside the application itself |
| Dependency lacking upstream metadata | Temporarily add controlled hints, test them, and contribute upstream |
| JAR converted to native by buildpack/tool outside Native Build Tools | Bundle required metadata in the JAR for downstream tools to read |

A library can publish a pure Java core JAR alongside a separate `payment-sdk-spring` module. The core JAR carries shared GraalVM metadata; the Spring module supplies the registrar and auto-configuration. Splitting modules this way avoids forcing non-Spring users to pull in Spring dependencies just to receive hints.

If both JAR metadata and Spring hints describe the same member, check whether they truly overlap and differ in access permissions. Duplication does not always cause errors, but it complicates updates and can inadvertently broaden metadata scope.

## 16. Testing RuntimeHintsRegistrar With RuntimeHintsPredicates

Spring provides `RuntimeHintsPredicates` to verify whether a registrar contributes the expected hints. These are fast unit tests that do not require compiling a native image.

Example resource check:

~~~java
class PaymentSdkRuntimeHintsTests {

    @Test
    void registersPaymentSchemaResources() {
        RuntimeHints hints = new RuntimeHints();

        new PaymentSdkRuntimeHints().registerHints(
            hints,
            getClass().getClassLoader()
        );

        assertThat(
            RuntimeHintsPredicates.resource()
                .forResource("com/acme/payment/schema/v1.json")
        ).accepts(hints);
    }
}
~~~

Corresponding predicates exist for reflection, serialization, and proxies. Tests should verify the exact classes/members or interfaces a component requires, rather than merely checking that `RuntimeHints` is non-empty.

These tests confirm **the registrar declares the right information**. They do not prove the native executable can actually execute all code paths; native integration tests are still required.

## 17. RuntimeHints Agent vs. GraalVM Tracing Agent

Two tools for capturing dynamic accesses are easily confused:

| Tool | Purpose | How to use |
|---|---|---|
| Spring RuntimeHints Agent | Tracks dynamic access calls in tests and helps verify them against Spring-provided hints | Use the `org.springframework:spring-core-test` module |
| GraalVM Native Image Tracing Agent | Observes reflection, proxies, JNI, resources, and dynamic features while running on the JVM | Run app/tests with `-agentlib:native-image-agent` |

Spring RuntimeHints Agent is suited for checking whether a Spring integration library contributes sufficient hints for operations executed in tests. GraalVM Tracing Agent is suited for collecting Native Image reachability metadata JSON from exercised application flows.

Example running the JVM with GraalVM Tracing Agent:

~~~bash
java \
  -agentlib:native-image-agent=config-output-dir=target/native-agent-config \
  -jar target/application.jar
~~~

After exercising the required flows and stopping the application, inspect the metadata in the output directory. The agent only records code paths that actually executed. If tests do not traverse a particular serializer, plugin, profile, or business branch, metadata for that branch may not be generated.

**Do not ship raw agent output directly to a library or production without reviewing it.** Agent metadata can include entries for test infrastructure, unnecessary classes, or environment-dependent information.

## 18. Controlling Metadata Versions, Conditions, and Scope

Metadata must be tested alongside the library versions and toolchains supported by the project.

Key principles:

- Tie metadata to exact artifact coordinates and versions.
- Update metadata when a library changes classes, methods, resources, or implementations.
- Use conditional metadata when supported by the schema and use case, enabling entries only when related types are reachable.
- Do not enable `allDeclaredMethods` or `allDeclaredFields` across entire packages just to silence errors.
- Do not register classes absent from the artifact expecting metadata to load them automatically.
- Do not treat metadata as a way to load new plugin JARs after the native executable is built.
- Validate the JSON schema against the target GraalVM version.

In newer metadata schemas, entries can use `typeReached` conditions to restrict when metadata takes effect. This helps reduce the footprint of unneeded metadata, though you must understand accurately when a type is considered reached.

A library change can invalidate older metadata. Therefore, run native tests when upgrading dependency versions, especially for serializers, ORMs, HTTP clients, logging, validation, and drivers.

## 19. Diagnosing When Library Metadata Is Not Applied

| Symptom | Possible cause | What to check |
|---|---|---|
| JAR has metadata but native build still reports missing registration | JAR is not on the native build classpath or path is wrong | Inspect JAR contents and classpath |
| Metadata JSON is not read | Wrong file name, wrong directory, or incompatible schema | Verify `META-INF/native-image` and schema |
| Spring hints do not appear | Registrar not imported or statically registered | Check `@ImportRuntimeHints`, `aot.factories`, and component scan |
| Registrar runs but method is missing | Incorrect member category or signature | Cross-check actual call and add narrow hint |
| Repository does not supply metadata | Dependency version lacks entry or plugin lacks repository config | Run missing metadata check task and inspect report |
| Metadata exists in repository but buildpack does not see it | Repository metadata is only used during plugin build; JAR lacks metadata | Use collect/add metadata task when downstream needs a self-contained JAR |
| New errors appear after upgrading dependency | Old metadata no longer matches implementation | Update repository/plugin or library metadata |
| Native test fails only under a different profile | That AOT/profile or code path has not been tested | Build with the exact profile and run native tests for it |
| Metadata file lost in shaded JAR | Packaging tool mishandles duplicate resources | Check merge strategy and final JAR contents |

To detect missing registrations early, you can enable `--exact-reachability-metadata` during builds on GraalVM versions supporting it, then run the native executable with `-XX:MissingRegistrationReportingMode=Warn`. During testing, `Exit` mode can help catch cases where code catches `Throwable` and inadvertently hides missing registration errors. Check your GraalVM version documentation before using these flags.

## 20. Practical Workflow: Packaging Hints for a Spring Library

Suppose you develop a `payment-sdk` library with these requirements:

- Reads JSON schemas from the classpath.
- Uses reflection to instantiate `PaymentRequest`.
- Creates a JDK proxy for the `PaymentGateway` interface.
- Is used in a Spring Boot Native Image application.

### Step 1 — Identify Dynamic Accesses

List required classes, constructors, methods, resources, and proxies. Separate what can be statically inferred from what depends on runtime data.

### Step 2 — Bundle GraalVM Metadata in the Core JAR

Create the file:

~~~text
src/main/resources/META-INF/native-image/com.acme/payment-sdk/reachability-metadata.json
~~~

Include the reflection/resource/proxy/serialization entries that the core SDK genuinely needs. Build the JAR and verify with `jar tf`.

### Step 3 — Create the Spring Integration Module

Create `PaymentSdkRuntimeHints` implementing `RuntimeHintsRegistrar`. Apply `@ImportRuntimeHints` on the Spring module's configuration/auto-configuration so the registrar only applies when the integration is active.

### Step 4 — Test the Hints

Use `RuntimeHintsPredicates` to test required resources, reflection, serialization, and proxies. If the library has extensive dynamic access, add the Spring RuntimeHints Agent in tests to spot unhinted calls.

### Step 5 — Check the GraalVM Repository

Run:

~~~bash
./gradlew listLibrariesMissingMetadata
~~~

or:

~~~bash
./mvnw native:list-libraries-missing-metadata
~~~

Check `payment-sdk` and transitive dependencies. Even if the library bundles its own metadata, verify the plugin is not configured to exclude it.

### Step 6 — Build and Test Native

~~~bash
./gradlew nativeCompile
~~~

or:

~~~bash
./mvnw -Pnative package
~~~

Run the executable and test schema loading, reflective request creation, proxy invocation, and serialization flows. If a buildpack or downstream system consumes the JAR rather than the direct native build classpath, consider bundling repository metadata into the JAR using the corresponding task/goal.

### Acceptance Checklist

| Item | Evidence |
|---|---|
| Metadata in JAR | `jar tf` displays the exact path |
| JSON schema | Validated against schema matching GraalVM |
| Spring hints | `RuntimeHintsPredicates` unit tests pass |
| Registrar discovery | AOT logs show the registrar was invoked |
| Dependency metadata | Missing metadata report reviewed |
| Native build | `nativeCompile` or Maven native package succeeds |
| Native runtime | Reflection, resources, proxies, and serialization run cleanly |
| Version compatibility | Spring, GraalVM, Native Build Tools, and dependency versions recorded |

## 21. Remember

Metadata inside a JAR lets a library self-describe the dynamic accesses Native Image needs, fitting pure Java libraries or requirements shared across frameworks. The GraalVM Reachability Metadata Repository supplements community metadata for dependencies that do not package their own and can be consumed automatically by Native Build Tools during native builds.

Spring `RuntimeHintsRegistrar` fits Spring integration logic: registrars are discovered via `@ImportRuntimeHints` or `META-INF/spring/aot.factories`, and Spring AOT translates hints into native configuration. Keep hints close to the components using them, verify them with `RuntimeHintsPredicates`, and run native tests on real code paths.

When releasing a library, keep core metadata and Spring integration in their proper modules, version them properly, declare minimal scope, and verify files actually exist in the artifact. **Metadata only describes dynamic accesses; it cannot replace unpackaged classes/bytecode and does not guarantee an untested dependency will automatically be native-compatible.**

### References

- GraalVM — Reachability Metadata: https://www.graalvm.org/latest/reference-manual/native-image/metadata/
- GraalVM — Reachability Metadata Repository: https://github.com/oracle/graalvm-reachability-metadata
- GraalVM Native Build Tools — Gradle Plugin: https://graalvm.github.io/native-build-tools/latest/gradle-plugin
- GraalVM Native Build Tools — Maven Plugin: https://graalvm.github.io/native-build-tools/latest/maven-plugin.html
- Spring Framework — Ahead of Time Optimizations: https://docs.spring.io/spring-framework/reference/core/aot.html
- Spring Boot — Advanced Native Image Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html

Metadata schemas, plugin tasks, and Spring APIs can change across versions. When releasing a library, pin your toolchain and consult documentation for the exact supported GraalVM, Spring Framework, Spring Boot, and Native Build Tools versions.
