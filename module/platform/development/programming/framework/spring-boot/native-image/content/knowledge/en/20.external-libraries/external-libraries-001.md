# Evaluating Third-Party Libraries Before Using Them in Native Image

## 1. Why Does Each Dependency Need Separate Evaluation?

A Spring Boot application can run reliably on the JVM yet fail when compiled or run with GraalVM Native Image. Sometimes the cause is not in the application's source code, but in a third-party library: the library uses reflection by runtime name, generates bytecode dynamically, reads resources by pattern, loads a JNI library, initializes environment-dependent static state, or relies on a JVM API that is not supported in the way it is being used.

Therefore, evaluating dependencies is a dedicated step in preparing for Native Image. You should not just look at whether a library is on Maven Central, has a recent version, or whether the application already runs on the JVM. You need to verify Native Image support for the exact version, the metadata the library provides, runtime limitations, and the business flows actually used.

In the **SPRING_BOOT_NATIVE_IMAGE** module, the goal is to compile a Spring Boot application with Spring AOT and GraalVM Native Image, run compatibility tests, package containers, and evaluate startup and memory. Each important dependency needs to be classified and verified in the exact application module along with the toolchain that will be released.

## 2. Common Risks in Third-Party Libraries

| Technique or behavior | Risk for Native Image | Evidence to look for |
|---|---|---|
| Reflection by class/member name | Static analysis cannot infer the target | Runtime hints, reachability metadata, native documentation |
| Runtime bytecode generation | Needs to generate new classes after build | AOT integration, pre-generated proxies, or documented limitations |
| Custom ClassLoader | May load classes not included in the image | Class loading description and native tests |
| Dynamic resource lookup | Resource is not packaged into the executable | Resource hints, metadata, or resource patterns |
| JDK dynamic proxy | The set of proxy interfaces may not be declared | Proxy hints or AOT contribution |
| Java serialization | Missing metadata for types and object graphs | Serialization hints and round-trip tests |
| JNI/native library | Missing library or mismatched OS/CPU/ABI | JNI metadata, binary artifacts, run-image requirements |
| Static initializer with side effects | Build-time state is baked into the image | Initialization guidance and diagnostic logs |
| Instrumentation/agent | Depends on JVM runtime capabilities | Specific GraalVM support documentation |
| Process or shell invocation | External executable is missing in the container | Runtime packages, paths, and permissions |

Seeing a technique in this table does not automatically mean a library is incompatible. Many libraries already provide AOT integration, metadata, or suitable fallbacks. This table is used to identify the questions to answer and the tests to run.

## 3. Start From the Exact Dependency Graph

Evaluation must be based on the actual dependencies of the application module, not just the root build file. In a Gradle multi-project build, select the exact project containing the Spring Boot application.

For example:

```bash
./gradlew :api-app:dependencies --configuration runtimeClasspath
```

Trace the dependency origin:

```bash
./gradlew :api-app:dependencyInsight --dependency example-library --configuration runtimeClasspath
```

With Maven:

```bash
./mvnw dependency:tree
```

You need to identify:

- Direct and transitive dependencies.
- The actual resolved version, including when versions are managed by a BOM.
- Exclusions and dependency constraints.
- Scope/configuration, especially the runtime classpath.
- Dependencies used only in tests versus dependencies included in the production artifact.
- Platform-specific artifacts or optional native modules.

A library might work on the JVM simply because a class is only used on a rarely hit endpoint. Therefore, the dependency graph is the starting point for inspection, not complete proof of runtime compatibility.

## 4. Check Vendor Native Image Support Claims

For each important dependency, check the official documentation for the exact version:

1. Is there a Native Image/GraalVM/Spring AOT support section?
2. From which version is support provided?
3. Is a separate artifact/classifier or additional dependency required?
4. Is there a `RuntimeHintsRegistrar`, Spring AOT contribution, or reachability metadata?
5. Are there limitations regarding reflection, proxies, serialization, JNI, OS, or architecture?
6. Does it require build argument configuration or an initialization policy?
7. Is there a test matrix for the GraalVM/Spring Boot/JDK versions being used?

Clearly distinguish three claim levels:

- **Officially supported**: documentation explicitly states the version and configuration steps.
- **Metadata available but requires configuration**: the library provides hints/metadata, and the application must enable or supplement them as instructed.
- **Unverified**: no official statement is found, or only community reports exist. Experimental verification is required before releasing.

Do not infer that a library supports Native Image just because its dependency appears in another native application. That other application might exercise a smaller code path or supply its own custom metadata.

## 5. Inspect Metadata Packaged in the Artifact

A library can bundle metadata inside its JAR so consuming applications do not have to rewrite every hint themselves. Common mechanisms include:

- Spring AOT contribution or `RuntimeHintsRegistrar`.
- `META-INF/spring/aot.factories` to register registrars via the appropriate Spring AOT mechanism.
- GraalVM reachability metadata following the schema/format supported by the Native Image version.
- Service/provider metadata or required resources as specified by the framework.

Inspect the JAR contents:

```bash
jar tf path/to/library.jar
```

Look for common metadata locations such as `META-INF/spring/aot.factories`, GraalVM reachability metadata, `META-INF/services`, resources, and native binaries. Exact paths vary by ecosystem and version; do not assume every library uses the same layout.

If metadata exists, verify:

- Is the file present in the actual resolved artifact version?
- Is the registrar class packaged and loadable?
- Do the keys, schema, and packages match the framework/toolchain version?
- Do the AOT logs show that the registrar/contribution was discovered?
- Does the metadata cover the code paths the application actually uses?

Having a metadata file in the JAR does not guarantee the metadata was successfully consumed. Check the AOT/build output and runtime tests.

## 6. Distinguish Spring RuntimeHints From Reachability Metadata

Spring RuntimeHints is an abstraction provided by Spring to describe reflection, resources, proxies, serialization, and other runtime capabilities. Spring AOT collects hints from the application and supported integrations.

GraalVM Native Image has its own reachability metadata. This metadata describes elements to retain or how to handle dynamic operations according to the GraalVM schema. Spring and Native Image integrate with each other according to the version/toolchain.

| Mechanism | Role | When evaluating a library |
|---|---|---|
| RuntimeHintsRegistrar | Library contributes hints via Spring AOT | Verify the registrar is discovered |
| Spring AOT contribution | Library participates in AOT processing via supported APIs | Check version/API compatibility |
| GraalVM reachability metadata | Describes Native Image requirements standalone or via metadata repository | Check schema and distribution |
| Tracing Agent output | Suggests metadata from code paths observed on the JVM | Review and run additional tests |

Do not manually translate Spring API names into GraalVM JSON without checking the schema. Do not duplicate the same metadata across multiple mechanisms just to increase the chance of a passing build; first identify which source the toolchain consumes.

## 7. Compatibility Areas Requiring Separate Checks

### Reflection and Class Loading

Look for calls such as `Class.forName`, `getDeclaredMethod`, `getDeclaredConstructor`, `Field.get`, and `setAccessible`. Check whether the library provides hints for the specific classes/members. If a class is selected from runtime data, you must define an allowlist or a predetermined list of implementations.

### Proxy and Bytecode Generation

Look for JDK dynamic proxies, CGLIB, Byte Buddy, ASM, or instrumentation. Distinguish proxies that Spring AOT can prepare from classes generated arbitrarily after the executable has been built. JDK proxy hints cannot replace arbitrary runtime subclass/bytecode generation.

### Resources and Configuration

Check templates, schemas, SQL files, message bundles, and resources loaded by dynamic names. Verify that resources are present in the JAR and packaged into the Native Image. Configuration files or secrets that need to vary by environment should be supplied at runtime via the filesystem, environment variables, or a secret manager.

### Serialization

Check object graphs, custom serialization hooks, proxy handlers, and serialization metadata. Prefer DTOs/snapshots with stable contracts; avoid serializing Spring beans, connections, or proxies holding infrastructure state.

### JNI and Native Libraries

Look for native methods, `System.loadLibrary`, `.so`/`.dll`/`.dylib` libraries, and ABI requirements. Verify binaries match the target OS/CPU, bridge libraries, and final run image.

### Class Initialization

Check whether static initializers read the environment, time, random state, files, or native libraries. Follow official initialization policy guidance; do not apply `--initialize-at-run-time` broadly to mask errors.

## 8. Distinguish Dependency Errors From Application Configuration Errors

When a native build or runtime fails, identify the error category first:

| Symptom | Category to inspect |
|---|---|
| Class not found | Runtime dependency graph, version, classloader |
| Reflection constructor/method error | Reflection metadata and signatures |
| Resource returns null | Resource path, JAR contents, and resource hints |
| Proxy cannot be created | Proxy strategy, AOT integration, interface/class constraints |
| Serialization error | Object graph and serialization metadata |
| UnsatisfiedLinkError | JNI library, load path, ABI, and JNI metadata |
| Incorrect static value | Class initialization policy |
| AOT context missing bean | Profiles, conditions, classpath, and build-time properties |
| Build OOM or linker failure | Toolchain, builder resources, and target platform |

Do not try to fix every error by adding reflection hints. For example, a dependency missing from the runtime classpath cannot be fixed with RuntimeHints; a class generated arbitrarily via runtime bytecode cannot be resolved simply by opening a constructor.

## 9. Test Libraries Standalone Before Deep Integration

For high-risk dependencies, create a small sample application or isolated test module to exercise the exact APIs being used. The goal is to separate library issues from the complex configuration of a large application.

A useful sequence:

1. Create a minimal Spring Boot application with the exact dependency version.
2. Call the APIs representing production code paths.
3. Run JVM tests and record baseline behavior.
4. Run Spring AOT with the exact JDK, profiles, and classpath.
5. Build the Native Image.
6. Run the executable and trigger that API.
7. Package the container with the intended production run image.
8. Verify OS/architecture, resources, JNI libraries, and permissions.

A smoke test that only starts the context is insufficient if the dependency is only used when handling requests, running scheduled jobs, or executing migrations. Tests must exercise the actual features the application will use.

## 10. Verify the Version Matrix

Compatibility depends on the combination of versions, not just the library alone.

| Component | What to record |
|---|---|
| Spring Boot | Version and corresponding plugin |
| Spring Framework | Version managed by Boot |
| JDK | Vendor, version, and toolchain |
| GraalVM Native Image | Distribution and version |
| Native Build Tools | Plugin version and configuration |
| Dependency | Artifact, resolved version, and classifier |
| Builder/buildpack | Image digest and buildpack version if using CNB |
| Run image | Distribution, digest, libc, and architecture |
| Target | OS, CPU architecture, and ABI |

Use dependency management/BOMs and Gradle dependency locking where appropriate to reduce discrepancies between developers and CI. When upgrading a dependency, re-run the relevant native tests; do not assume metadata from an older version applies unchanged to a new version.

## 11. Create a Dependency Evaluation Report

You can maintain a table in the pull request or release record:

| Dependency | Resolved version | Dynamic techniques | Metadata/support | Native test | Conclusion |
|---|---|---|---|---|---|
| Library A | … | Reflection | Registrar | Pass/Fail | Verified/Needs work |
| Library B | … | JNI | Vendor metadata | Pass/Fail | Verified/Needs work |
| Library C | … | Runtime proxy | Unclear | Pass/Fail | Investigate |
| Library D | … | Resource lookup | Resource hints | Pass/Fail | Verified/Needs work |

Record the commit, build ID, JDK/GraalVM, OS/architecture, container digest, and test report. Avoid merely writing "native compatible" without stating which version and code paths were verified.

You can use internal statuses:

- **Verified**: native and container tests for the required code paths passed.
- **Verified with configuration**: passed after adding documented metadata/configuration.
- **Limited**: only certain features/OS/architectures are supported.
- **Unverified**: insufficient reliable native evidence.
- **Incompatible for current design**: relies on dynamic behavior that cannot be satisfied with the current configuration.

This is a project management classification, not an official GraalVM label.

## 12. How to Handle Incomplete Library Support

Prioritize steps in this order:

1. Upgrade to a version with official Native Image support if functionally compatible.
2. Use the native artifact/classifier or module recommended by the vendor.
3. Enable the provided Spring AOT contribution or reachability metadata.
4. Add RuntimeHints for the clearly identified parts controlled by the application.
5. Switch from arbitrary reflection to a registry/allowlist or static factory.
6. Switch runtime proxy generation to proxies/AOT artifacts that can be prepared ahead of time.
7. Replace the library if mandatory code paths are incompatible.
8. If the feature requires JVM dynamic loading/runtime compilation, isolate that feature into a JVM-based process/service when architecture permits.

Do not maintain a broad, opaque set of hints just to make the build pass. Each hint should have a reason, a proving test, and an owner when upgrading the dependency version.

## 13. Pre-Acceptance Checklist for a Dependency

- Exact runtime dependency graph and resolved version identified.
- Native support documentation for the exact version reviewed.
- Relevant reflection, proxy, resource, serialization, JNI, and class initialization checked.
- Metadata exists in the artifact and is actually consumed by Spring AOT/GraalVM.
- No reliance on unsupported runtime bytecode generation or class loading.
- Native tests exercise production code paths.
- Container tests use the exact target OS/architecture/run image.
- Version matrix, test results, and artifact digest documented.
- Remaining limitations clearly documented before release.

## 14. Self-Check Questions

1. Why is a dependency running well on the JVM not enough to prove Native Image compatibility?
2. Which metadata sources should be inspected inside a library's JAR?
3. What is the difference between `RuntimeHintsRegistrar` and GraalVM reachability metadata?
4. Why must a dependency be checked on the runtime classpath of the exact application module?
5. When can reflection hints not solve a runtime bytecode generation issue?
6. Why does JNI compatibility depend on OS, CPU architecture, and ABI?
7. What code paths beyond startup should a native smoke test exercise?
8. What information must be recorded to conclude that a dependency version is verified?

**Remember:** evaluate third-party libraries by their exact version, dependency graph, and actual code paths. Verify AOT/reachability metadata, reflection, proxies, resources, serialization, JNI, and class initialization; then build and run tests on the target native executable/container before considering a dependency compatible.
