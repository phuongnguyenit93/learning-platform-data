# Handling Incompatible Dependencies via Upgrades, Hints, or Integration Changes

A dependency that works fine on the JVM but fails when compiling or running a GraalVM Native Image is not necessarily completely incompatible. Many libraries simply use reflection, load resources by name, create dynamic proxies, or rely on Java serialization or JNI that Native Image cannot fully infer through static analysis. These cases can often be fixed by upgrading to a native-supported version or adding reachability metadata.

Other libraries, however, rely on runtime behaviors incompatible with the closed-world model—such as loading arbitrary bytecode after the executable has been built, requiring a Java Instrumentation agent, or depending on a native library with no build for the deployment platform. Adding hints cannot resolve those limitations.

This lesson explains how to pinpoint the failing dependency, verify Native Image support, prioritize upgrades, supply missing metadata, and adjust integration boundaries when a library is truly unsuitable. Examples use Spring Boot, GraalVM Native Image, Maven, and Gradle.

## 1. Understand the Scope of Compatibility

Native Image performs static analysis at build time. The builder determines which classes, methods, and fields can be called from entry points, then produces an executable containing the required components. This reduces size and startup time, unlike a traditional JVM where classes and resources can be loaded dynamically throughout the process lifetime.

Dependencies typically need metadata for one or more of the following capabilities:

| Library capability | Why metadata is needed |
| --- | --- |
| Java Reflection | Classes, constructors, methods, or fields accessed by name or reflection API |
| Classpath resources | Files read by resource names constructed or determined at runtime |
| Dynamic proxies | Proxy interface sets not inferred by the compiler |
| Java serialization | Types requiring dynamic serialization/deserialization |
| JNI | Native code looking up Java classes/members by name |
| Resource bundles | Locales or bundles selected dynamically |
| FFM/native interop | Accessing native functions or memory via mechanisms requiring registration |

Missing metadata is usually a fixable issue. However, metadata only declares what needs to be retained and how it is accessed. It does not turn an unsupported runtime API into a supported one.

### Two Error Categories to Distinguish

**Missing reachability metadata:** the library can run under the Native Image model, but the builder does not yet know that a class, method, resource, proxy, or JNI member will be accessed dynamically. Supply precise metadata.

**Execution model incompatibility:** the library needs to load new arbitrary code after the executable is built, dynamically alter call sites based on runtime data, or require a Java agent based on Instrumentation/JVMTI. You must change the integration, replace the library, or isolate that component into a separate process.

## 2. Triage Process for Failing Dependencies

Do not start by adding hints for every package. First, identify the exact dependency and code path causing the failure.

~~~mermaid
flowchart TD
    A["JVM tests pass, native build or runtime fails"] --> B["Identify exception and call stack"]
    B --> C["Identify dependency, version, and call path"]
    C --> D{"Is there a Native Image-supported version?"}
    D -->|Yes| E["Upgrade and inspect dependency tree"]
    E --> F["Build and test native"]
    F -->|Pass| G["Keep verified version"]
    F -->|Fail| H["Check for missing metadata"]
    D -->|Not yet / unclear| H
    H --> I{"Is error a registrable dynamic access?"}
    I -->|Yes| J["Use repository, RuntimeHints, or JSON metadata"]
    J --> K["Re-test all code paths on native"]
    K -->|Pass| G
    K -->|Fail| L["Check execution limits and native dependencies"]
    I -->|No| L
    L --> M["Change integration or replace dependency"]
    M --> N["Isolate via adapter / separate process"]
~~~

Record the following details before making changes:

- Full exception, root cause, and stack trace.
- Direct dependency and related transitive dependencies.
- Actual resolved version, not just the version declared in the build file.
- Code path executed before the error occurred.
- Whether the error occurs during Spring AOT processing, Native Image compilation, or executable runtime.
- Platform, GraalVM/JDK version, and Native Build Tools version.

An error during AOT processing may indicate a Spring context or bean condition issue. An error during native compilation may be an unsupported feature or invalid metadata. An error that only appears when the native executable handles requests usually suggests an untested dynamic path or missing metadata.

## 3. Identify the Dependency and Actual Resolved Version

A direct dependency can pull in an older version of another library. Therefore, inspect the dependency tree and version resolution source before editing.

### Maven

View the full dependency tree:

~~~bash
./mvnw dependency:tree
~~~

Filter for a specific dependency:

~~~bash
./mvnw dependency:tree -Dincludes=com.vendor:legacy-sdk
~~~

If multiple dependencies pull in the same artifact, inspect which path brings in the older version. Check `dependencyManagement`, the Spring Boot BOM, and existing exclusions.

### Gradle

Inspect resolved dependencies:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Find why a specific version was selected:

~~~bash
./gradlew dependencyInsight \
  --dependency legacy-sdk \
  --configuration runtimeClasspath
~~~

Check configurations used for native build/test as well if they have dependencies different from `runtimeClasspath`.

### Check Native Image Support Level

Look up the exact group/artifact and version in the list of GraalVM-tested libraries and the GraalVM Reachability Metadata Repository. The list may distinguish:

- **Tested:** library maintainers continuously test with Native Image.
- **Community-tested:** tested via the metadata repository or community projects.

These labels are useful signals, not guarantees that every application configuration is compatible. Check the version range, JDK, GraalVM, and the specific modules the application actually uses.

Native Build Tools now integrates fetching metadata from the GraalVM Reachability Metadata Repository. If metadata is published for the dependency/version in use, the plugin can include that metadata in the native build without manually copying it into the project.

## 4. Prioritize Upgrading to a Native-Supported Version

When a library already has a version supporting Native Image, upgrading is usually the most maintainable fix. A newer release may:

- Package reachability metadata directly inside the JAR.
- Replace reflection with statically analyzable code.
- Add Spring `RuntimeHints` or GraalVM metadata.
- Fix class initialization so it does not depend on the build environment.
- Replace native libraries or provide binaries compatible with the target deployment platform.
- Fix bugs that only surface in the native runtime.

### Maven: Intentional Version Management

If the library is not managed by the Spring Boot BOM, declare the version explicitly:

~~~xml
<properties>
    <partner-sdk.version>VERIFIED_VERSION</partner-sdk.version>
</properties>

<dependencies>
    <dependency>
        <groupId>com.vendor</groupId>
        <artifactId>partner-sdk</artifactId>
        <version>${partner-sdk.version}</version>
    </dependency>
</dependencies>
~~~

If the library is managed by a BOM, prefer a compatible version from the BOM. Only override versions after verifying the compatibility matrix of related dependencies.

### Gradle: Declare Verified Versions

~~~kotlin
dependencies {
    implementation("com.vendor:partner-sdk:VERIFIED_VERSION")
}
~~~

If the project uses a version catalog or platform/BOM, update the version in the central location rather than declaring a second version in a module.

### What to Verify After Upgrading

1. Re-run JVM unit and integration tests.
2. Inspect the dependency tree to confirm the new version is actually resolved.
3. Build Spring AOT and the native executable.
4. Run native smoke/integration tests across the library's call paths.
5. Inspect logs, reflection/resource diagnostics, and linkage errors.
6. Record the verified version so all build environments use the same dependency graph.

Do not upgrade a single dependency in isolation while ignoring version requirements of Spring Boot, the JDK, or companion modules. A newer SDK release may require APIs from another library or change runtime behavior.

## 5. Use Existing Metadata from the GraalVM Reachability Metadata Repository

Before writing hints yourself, check whether community metadata already exists for the dependency. The repository stores metadata for popular JVM libraries so they work with Native Image.

Maven and Gradle Native Build Tools can use this repository automatically. Use an appropriate Native Build Tools version and inspect native build logs to confirm metadata is found and applied.

If metadata does not exist yet:

1. Verify the exact dependency coordinates and version.
2. Check whether a newer library release bundles metadata itself.
3. Identify which dynamic accesses are missing.
4. If reproducible with a minimal application, prepare a report and contribute metadata upstream.
5. Meanwhile, you can add metadata in the application if ownership and usage scope are clear.

Do not copy metadata from a different version and assume it fits the version in use. APIs, class names, and members can change between releases.

## 6. Use Spring `RuntimeHintsRegistrar` When the Application Owns the Integration

If the Spring Boot application calls a third-party library along a specific reflection/resource/proxy path, you can register hints with `RuntimeHintsRegistrar`.

For example, an SDK invokes a method via reflection, loads a config file, and creates a proxy for an interface:

~~~java
package com.example.orders.nativeconfig;

import java.lang.reflect.Method;

import com.vendor.sdk.VendorCodec;
import com.vendor.sdk.VendorService;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public class VendorSdkHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        Method decode = ReflectionUtils.findMethod(
                VendorCodec.class,
                "decode",
                String.class
        );

        if (decode != null) {
            hints.reflection().registerMethod(decode, ExecutableMode.INVOKE);
        }

        hints.resources().registerPattern("vendor/defaults.properties");
        hints.proxies().registerJdkProxy(VendorService.class);
    }
}
~~~

Activate the registrar in the Spring context:

~~~java
package com.example.orders.nativeconfig;

import org.springframework.aot.hint.annotation.ImportRuntimeHints;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(VendorSdkHints.class)
public class VendorNativeConfiguration {
}
~~~

The example above registers exactly three known accesses:

- Method `VendorCodec.decode(String)` invoked via reflection.
- Resource `vendor/defaults.properties` loaded from the classpath.
- JDK proxy created for the `VendorService` interface.

If the library uses Java serialization, Spring `RuntimeHints` also provides APIs to register serialization types. If DTOs are bound by Jackson or framework binding, prefer dedicated binding annotations such as `@RegisterReflectionForBinding` where appropriate.

### Principles for Writing Hints

- Register only classes/members/resources actually accessed dynamically.
- Prefer specific methods and constructors over opening all members of a package.
- Place hints alongside the corresponding adapter or integration configuration.
- Write tests verifying the registrar contributes the expected hints.
- Verify the native executable actually exercises that code path.

Hints do not fix bugs in library logic, install missing native libraries, or make unsupported APIs valid.

## 7. Use `reachability-metadata.json` for Spring-Independent Metadata

If metadata is needed only for Native Image and does not depend on Spring, you can declare JSON on the classpath.

Example file location:

`src/main/resources/META-INF/native-image/com.example/orders-api-additional/reachability-metadata.json`

Illustrative content:

~~~json
{
  "reflection": [
    {
      "type": "com.vendor.sdk.VendorCodec",
      "allPublicMethods": true
    }
  ],
  "resources": [
    {
      "glob": "vendor/config/*.properties"
    }
  ]
}
~~~

Where:

- `reflection` describes classes or members accessed dynamically.
- `allPublicMethods` enables reflection on public methods of the stated type.
- `resources` registers a group of resources using a glob pattern.

The example above intentionally uses `allPublicMethods` for illustration. In a real application, if only one or two methods are called, declare specific members to reduce metadata and limit the access surface.

GraalVM reads `reachability-metadata.json` under `META-INF/native-image/` on the classpath. Libraries can package their own metadata inside their JAR; applications can also provide supplemental metadata in a directory with its own coordinates to avoid overwriting resources generated by Spring AOT or other dependencies.

Validate JSON against the schema of the GraalVM version being built. Modern reachability metadata format combines multiple configuration types into one file; older separate files like `reflect-config.json` may still appear in legacy projects, but should not be newly created if the toolchain uses the newer schema.

## 8. Use the Tracing Agent to Find Missed Dynamic Accesses

When you don't know which classes or resources a library accesses via reflection, the GraalVM Tracing Agent can observe the application running on the JVM and record metadata.

With Spring Boot, run the executable JAR with AOT mode and the agent:

~~~bash
java \
  -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent \
  -jar target/orders-api.jar
~~~

Send requests through features that use the SDK, including success paths, error paths, optional configurations, and selectable subtypes. When the application stops, the agent writes metadata to the output directory.

You can re-run to add previously unobserved paths using `config-merge-dir`:

~~~bash
java \
  -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-merge-dir=target/native-agent \
  -jar target/orders-api.jar
~~~

After collecting:

1. Read each entry and identify the dependency/call path that produced it.
2. Remove entries that only serve test frameworks or code absent in production.
3. Verify classes, methods, resources, and proxies match the current dependency version.
4. Move necessary metadata into `META-INF/native-image/` in source or the module owning the integration.
5. Rebuild the native executable and run the same test suite.

The Tracing Agent only records code paths executed on the JVM. It cannot guarantee complete metadata for every input, plugin, or runtime branch. If tests run Spring test infrastructure, the collected metadata may include many entries unnecessary for the production application. Review and filter before committing.

## 9. Recognize When Hints Are Not Enough

Some dependencies rely on behaviors that cannot be solved with metadata alone:

| How the library works | Why hints may not be enough | Resolution path |
| --- | --- | --- |
| Loads arbitrary classes or bytecode after executable creation | New classes/methods are not in the analyzed code set | Use a finite registry, build-time code generation, or change integration |
| Java agent requiring runtime Instrumentation/JVMTI | Native executables do not operate like a HotSpot JVM with standard Java agents | Use a native-ready SDK/integration or keep that component on the JVM |
| Runtime plugins scanning and loading unknown JARs | Class set is not fixed at build time | Switch to a closed plugin registry or separate process |
| Depends on a native library available only for another OS/architecture | Metadata cannot synthesize a missing native binary | Replace the library or supply a native build for the target platform |
| Relies on changed/removed JDK internals or APIs | Hints cannot restore APIs that no longer exist | Upgrade the library or replace the API |
| Uses dynamic call sites whose targets vary by runtime data | Targets cannot always be inferred under closed-world analysis | Replace with explicit dispatch or a mechanism supported by Native Image |

GraalVM provides certain experimental runtime class-loading capabilities in specific versions. Do not enable them as a default workaround for a legacy plugin framework. Only consider them when the use case fits documented constraints, image/memory overhead is acceptable, and real class-loading tests exist.

### When Should You Change the Integration?

If a library offers a static API or explicit registry, use that path instead of unconstrained reflection. For example:

- Replace class names in configuration with a list of implementations registered at build time.
- Use explicitly declared serializers/codecs instead of package-scanning class discovery.
- Use fixed resource paths instead of scanning the entire classpath.
- Use HTTP/REST APIs or message contracts instead of loading in-process plugins.
- Replace an unsupported library with an equivalent tested library.
- Move the agent-dependent or runtime-class-loading component into a separate JVM service called over HTTP/gRPC.

## 10. Isolate Dependencies Behind an Adapter for Replaceability

Do not let an incompatible library's API leak across the entire application. Create a domain/application interface and place the SDK behind an adapter.

Example:

~~~java
public interface DocumentRenderer {
    byte[] render(Document document);
}
~~~

Adapter using the current library:

~~~java
@Component
public class VendorDocumentRenderer implements DocumentRenderer {

    private final VendorSdk sdk;

    public VendorDocumentRenderer(VendorSdk sdk) {
        this.sdk = sdk;
    }

    @Override
    public byte[] render(Document document) {
        return this.sdk.render(document.toVendorRequest());
    }
}
~~~

If the SDK cannot run natively, you can swap the adapter for another implementation:

- A native-compatible library.
- An HTTP client calling a dedicated rendering service.
- A minimal implementation for the required formats.

The business service still depends on `DocumentRenderer`. Consequently, changing the integration does not force rewriting all business logic.

### When Splitting into a Separate Process

Split a library into a JVM sidecar/service when it genuinely requires a Java agent, runtime plugin loading, or an irreplaceable JVM-only SDK. Clearly define:

- Request/response contracts and versioning.
- Timeouts, retries, idempotency, and circuit breakers.
- Authentication between the two processes.
- Logs, metrics, and trace propagation.
- Operational cost of running an additional service.
- Behavior when the dependent service is unavailable.

This is an architectural decision with real overhead. Apply it only when the value of keeping the existing library outweighs the cost of operating a separate process.

## 11. Special Considerations for JNI and Native Libraries

A dependency using JNI is not automatically incompatible with Native Image. Native Image supports JNI, but classes, methods, and fields looked up by name from native code must be registered upfront.

In addition to metadata, inspect the native library:

- Does a binary exist for the exact OS and CPU architecture?
- Does it match the ABI and libc of the runtime image?
- Does it depend on other shared libraries?
- Does it require CPU instructions beyond the deployment baseline?
- Is it packaged or discoverable via `java.library.path`/`System.loadLibrary`?

If the error is `UnsatisfiedLinkError`, a missing shared library, or an ABI mismatch, adding reflection hints will usually not help. You must fix the native dependency or the runtime image.

JNI metadata can be collected using the Tracing Agent on the JVM if tests actually invoke the native path. Afterward, you still need native integration tests to confirm loading and calling the library inside the executable.

## 12. Testing After Upgrading or Adding Hints

A dependency is only considered handled once the native executable exercises the flows using that dependency. A passing build is not enough.

### Recommended Test Matrix

| Test | JVM | Native executable |
| --- | --- | --- |
| Adapter unit tests | Yes | Can run native tests if needed |
| Spring ApplicationContext startup | Yes | Yes |
| SDK reflection paths | Yes | Required |
| Dynamic resource reading | Yes | Required |
| Dynamic proxies/serialization | Yes | Required if used by dependency |
| JNI/native library | Yes | Required |
| Configuration branches and plugins | Yes | Required for supported branches |
| Error handling when dependency fails | Yes | Yes |

On newer GraalVM versions that support it, enable exact reachability metadata to catch missing registrations early:

~~~bash
native-image --exact-reachability-metadata ...
~~~

You can use warning mode when running the executable:

~~~bash
./target/orders-api -XX:MissingRegistrationReportingMode=Warn
~~~

In strict tests, use exit mode to fail immediately when a missing registration is encountered:

~~~bash
./target/orders-api -XX:MissingRegistrationReportingMode=Exit
~~~

`Exit` is especially helpful if the application has code catching `Throwable`, because missing registration errors won't be swallowed and turned into hard-to-detect fallback behavior.

Reporting options and behavior depend on the GraalVM version. Check documentation for your exact toolchain if an option is unsupported.

### Do Not Swallow Errors with Broad Catches

A library may catch `Throwable` and silently ignore reflection failures. On the JVM, the operation might succeed; on native, a missing registration can be masked and produce wrong results. In native tests, enable the appropriate reporting mode and assert business outputs—don't just check that the process exits with code 0.

## 13. Manage Hints by Dependency Version

Hints are tied to the internal structure of a library. When upgrading a dependency, review old metadata:

- Were classes moved to a different package or renamed?
- Did method/constructor signatures change?
- Did resource paths change?
- Does the newer library version bundle metadata itself?
- Can application-declared hints be deleted because the dependency now provides them?

Keeping obsolete metadata can bloat the executable, retain unnecessary members, and mislead maintainers into thinking the old access path is still required.

Organize metadata by dependency/integration and document why it exists:

~~~text
src/main/resources/
  META-INF/
    native-image/
      com.example/
        orders-api-additional/
          reachability-metadata.json
~~~

When updating a dependency, run native tests and review metadata diffs. If metadata is packaged inside a library, prefer fixing or upgrading the library instead of maintaining manual copies across every application.

## 14. Quick Diagnostic Table

| Symptom | Possible cause | What to do first |
| --- | --- | --- |
| Works on JVM, native throws `MissingReflectionRegistrationError` | Missing class/member reflection | Check metadata repository, upgrade, or register specific members |
| Resource exists in JAR but native cannot read it | Resource unregistered or pattern mismatch | Register exact resource and check path/casing |
| Proxy works on JVM but fails on native | Proxy interface not declared | Use `RuntimeHints` or proxy metadata |
| Serialization fails on native | Serialized type unregistered or library uses unsupported mechanism | Check serialization metadata, consider explicit JSON/codecs |
| JNI lookup failure | Missing JNI metadata or native library | Register JNI members and verify native binary |
| `UnsupportedFeatureError` | Code path uses unsupported API/behavior or misconfiguration | Read full message; determine whether API can be swapped or dependency replaced |
| `ClassNotFoundException` only on native | Class chosen by dynamic name or not reachable | Verify class is on classpath and in metadata |
| `UnsatisfiedLinkError` | Missing library, ABI mismatch, or shared object not found | Check native binary and runtime image |
| Version upgrade breaks Spring context | Dependency version incompatible with Spring BOM/APIs | Inspect dependency tree and version matrix |
| Native tests pass but production fails | Agent missed production branch or config differs | Expand tests across actual profiles, inputs, resources, and integrations |

## 15. Hands-on Exercise: Resolving a Native-Incompatible SDK

Suppose `orders-api` uses a partner SDK to decode payloads. The SDK runs on the JVM, but the native executable fails when calling `VendorCodec.decode` and also cannot read `vendor/defaults.properties`.

### Part A — Locate the Dependency

1. Use Maven `dependency:tree` or Gradle `dependencyInsight` to determine the resolved SDK version.
2. Check that version in the GraalVM-tested libraries list and Reachability Metadata Repository.
3. Check the SDK release notes for native support or new metadata.
4. If a supported version exists, upgrade via the BOM/version catalog and re-run tests.

### Part B — Add Missing Metadata

If the SDK can run natively and only lacks dynamic access:

1. Run the Tracing Agent on the JVM with `spring.aot.enabled=true`.
2. Send requests exercising both successful decoding and error paths.
3. Verify whether the agent recorded `VendorCodec` and the resource.
4. If recorded accurately, place required entries into `reachability-metadata.json` or `RuntimeHintsRegistrar`.
5. Enable `--exact-reachability-metadata` if supported by the toolchain.
6. Build native and re-run tests.

### Part C — Decide to Change the Integration

If the SDK loads unknown plugin bytecode dynamically or requires a runtime Java agent:

1. Define the minimal business API the application needs.
2. Create an application-owned adapter interface.
3. Find another SDK with native support or replace with an HTTP protocol to a separate service.
4. Run contract tests to guarantee request/response and error semantics stay unchanged.
5. Compare latency, operational, and maintenance costs before choosing.

### Self-Check Questions

1. Why do passing JVM tests not prove a dependency is Native Image compatible?
2. Which kinds of dynamic access does reachability metadata solve?
3. When should you upgrade a dependency before writing hints yourself?
4. How does the GraalVM Reachability Metadata Repository help an application?
5. How do `RuntimeHintsRegistrar` and JSON metadata differ?
6. Why can't the Tracing Agent guarantee complete metadata for all code paths?
7. When are a Java agent or runtime class loading signs that the integration must change?
8. Why does a JNI dependency require checking both metadata and the native binary/ABI?
9. Why shouldn't you register all members of every class in a package?
10. Why should old hints be reviewed and removed after upgrading a library?

**Passing criteria:** identify the exact failing dependency/version; distinguish missing metadata from closed-world limits; prioritize upgrading when a native-compatible release exists; add exact reflection/resource/proxy/serialization/JNI hints when needed; use the Tracing Agent in a controlled manner; swap adapters or split into a separate process if the library cannot run natively; and finally verify all code paths on the native executable.

## Official Documentation

- Spring Boot — Advanced Native Images Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Spring Framework — Runtime Hints and AOT: https://docs.spring.io/spring-framework/reference/core/aot.html
- GraalVM — Reachability Metadata: https://www.graalvm.org/latest/reference-manual/native-image/metadata/
- GraalVM — Native Image Compatibility Guide: https://www.graalvm.org/latest/reference-manual/native-image/metadata/Compatibility/
- GraalVM — Collect Metadata with the Tracing Agent: https://www.graalvm.org/latest/reference-manual/native-image/metadata/AutomaticMetadataCollection/
- GraalVM — Java Native Interface in Native Image: https://www.graalvm.org/latest/reference-manual/native-image/dynamic-features/JNI/
- GraalVM — Libraries and Frameworks Tested with Native Image: https://www.graalvm.org/native-image/libraries-and-frameworks/
- GraalVM — Reachability Metadata Repository: https://github.com/oracle/graalvm-reachability-metadata
