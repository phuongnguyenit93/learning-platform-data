# When to Upgrade, Replace a Library, or Change the Integration Approach

## 1. Why Re-Evaluate Libraries When Moving to Native Image?

A Spring Boot application can run stably on the JVM yet fail when built or run with GraalVM Native Image. The root cause usually involves how a library uses reflection, proxies, resources, serialization, JNI, classloaders, or class initialization. Some libraries are built around the JVM's dynamic code discovery and loading, whereas Native Image analyzes the reachable codebase at build time under a closed-world model.

When issues arise, do not immediately replace the entire library or pile on broad RuntimeHints. Determine whether the library supports Native Image in the version in use, whether official metadata resolves the issue, and whether the maintenance cost of a workaround is justified.

This lesson provides a decision framework for **when to upgrade, replace a library, or change the integration approach** in the **SPRING_BOOT_NATIVE_IMAGE** module. The goal is to select a low-risk, testable, and long-term maintainable option while preserving application functionality, startup time, and memory usage.

## 2. Start From a Reproducible Failure

Before changing dependencies, create a minimal failing case:

- Record the Spring Boot, Spring Framework, JDK/GraalVM, and Native Build Tools versions.
- Identify the direct or transitive library involved.
- Capture the full stack trace and the phase where the failure occurs: AOT, Native Image compilation, or runtime.
- Identify the failing operation: reflection, resource loading, proxy, serialization, JNI, class initialization, or dynamic class loading.
- Create a small test exercising the exact failing path on both JVM and native.
- Confirm the error is not caused by build configuration, ABI, OS libraries, or runtime files.

For example, `ClassNotFoundException` may stem from an unregistered reflection target, or from a typo in a class name or a dependency missing from the classpath. `UnsatisfiedLinkError` usually calls for checking native libraries, architecture, and ABI; upgrading Spring Boot may be unrelated.

An error occurring only in native mode is evidence to investigate, not proof that the library is completely incompatible.

## 3. Classify the Root Cause Before Choosing an Option

| Root cause category | Common symptoms | Initial action |
|---|---|---|
| Old version lacks Native Image support | Newer release has native metadata or AOT integration | Check release notes and upgrade |
| Missing reachability metadata | Reflection/proxy/resource is not retained | Check official metadata, add RuntimeHints |
| Unsuitable library usage pattern | Dynamic class loading, runtime plugin JARs, compiler | Change integration approach or isolate service |
| Incorrect Spring AOT configuration | Beans/conditions/profiles differ from expected | Inspect AOT inputs and configuration |
| Platform mismatch | Wrong libc, loader, architecture, or shared library | Align builder/runtime/toolchain |
| Library or framework bug | Reproducible natively with valid configuration | Check issues/releases, upgrade, or report upstream |
| Application bug | Wrong reflection signature, resource path, or lifecycle | Fix code and add regression test |

Classification avoids fixing the wrong layer. For instance, adding reflection hints cannot make a new JAR appear inside an already built native executable; replacing a JSON library will not fix a mis-mounted config file either.

## 4. When Should You Upgrade the Library?

Upgrading is the first option to evaluate when a newer version offers any of these improvements:

- Official Spring AOT or GraalVM Native Image support.
- Added reachability metadata for reflection, proxies, resources, or serialization.
- Fixes for class initialization, JNI, or dynamic access bugs.
- Removal of deprecated APIs or incompatible mechanisms.
- Compatibility with the JDK, Spring Boot, and Native Build Tools versions in use.
- Native tests in CI or documentation confirming the support scope.

Do not look only at version numbers. Read release notes, migration guides, related issues, and the dependency graph. A major upgrade can alter APIs, default behavior, serialization formats, or transitive dependencies.

For example, if an older version of a serializer library required manual reflection hints while a newer version ships tested Native Image metadata, upgrading can eliminate custom application configuration. However, verify that the metadata covers the exact modules/features you use, not just the happy path.

## 5. Check Compatibility Across the Entire Dependency Chain

A direct library may support Native Image while one of its transitive dependencies uses unsupported reflection or JNI. Therefore, inspect the dependency graph:

Maven:

```bash
./mvnw dependency:tree
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Record:

- Direct and transitive dependencies.
- Actual resolved versions.
- Conflicted or overridden dependencies.
- Optional modules enabled at runtime.
- Bundled native libraries/resources.
- Which artifacts package reachability metadata.

Do not force-upgrade a single transitive dependency alone if the parent library does not yet support that version. Check BOMs, dependency management, and the framework's compatibility matrix before overriding.

## 6. Look for Existing Native Image Metadata

Before writing hints yourself, check whether the library provides official metadata. Many modern libraries package reachability metadata or integrate Spring RuntimeHints to declare reflection, resources, proxies, and serialization.

Sources to inspect:

- The library's official GraalVM Native Image documentation.
- Release notes and migration guides.
- The library's metadata repository.
- GraalVM Reachability Metadata Repository if the library has contributions there.
- Spring Boot/Spring Framework support documentation.
- Upstream native integration tests.

Metadata may be distributed inside the JAR using mechanisms and formats dependent on the GraalVM version. Do not copy metadata files from another version or place them in arbitrary folders assuming the compiler will read them.

If the library already provides metadata, verify that your build tool and GraalVM version recognize it. Inspect native image build logs, library tests, and real application execution paths.

## 7. When Should You Add Application RuntimeHints?

Adding hints yourself is appropriate when:

- The library exposes reflection-based APIs but cannot know the application's specific classes ahead of time.
- The application selects classes/members from a finite, known set.
- Classpath resources are picked dynamically by name from a fixed set of files.
- The application creates JDK proxies from known interfaces.
- Native code invokes callbacks into predetermined Java types.

Example registrar:

```java
final class PartnerSdkHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
                PartnerPayload.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );

        hints.resources().registerPattern(
                "partner/templates/*.json");
    }
}
```

Attaching the registrar:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PartnerSdkHints.class)
class PartnerSdkConfiguration {
}
```

Illustrative example; register only the exact constructors/methods/resources the SDK actually uses and check the API for your Spring Framework version. Do not register every member or an entire resource package just to make the build pass.

RuntimeHints are metadata for known types/resources. They do not enable Native Image to load new plugin classes from arbitrary JARs after the executable has been released.

## 8. When Should You Change the Integration Approach While Keeping the Library?

Sometimes a library is native-compatible when used along a static path, whereas the current integration relies on dynamic discovery. You can keep the dependency and change how it is called:

| Current integration approach | Integration approach to consider |
|---|---|
| Discovering implementations via runtime package scanning | Register implementations explicitly |
| Selecting classes by arbitrary string names | Finite registry of known classes |
| Creating arbitrary proxies | Use stable interface/proxy combinations and proxy hints |
| Looking up resources by dynamically constructed names | Register resource patterns or fixed file sets |
| Instantiating objects via reflection | Use constructor/factory injection where possible |
| Loading plugin JARs post-deployment | Move plugins into build inputs or isolate a plugin host |
| Compiling rules into Java classes at runtime | Use a DSL/interpreter or build-time generation |

Changing the integration approach is usually less costly than replacing the library if most of its capabilities still fit. However, preserve public contracts, error handling, and business performance.

## 9. When Should You Replace the Library?

Consider replacing the library when multiple conditions converge:

- Upstream has no plans or commitment to support Native Image.
- The failure lies in core design, such as dynamic class definition or a runtime compiler.
- Workarounds require broad metadata that is hard to test and fragile across version upgrades.
- The library is unmaintained or carries security risks.
- An alternative library meets functional, licensing, performance, and native support needs better.
- Migration cost can be contained through adapters and contract tests.

Do not replace a library just because of an obscure stack trace. First pinpoint the actual feature in use; many libraries offer optional modules or static modes that satisfy the use case without replacing everything.

## 10. Criteria for Selecting a Replacement Library

Evaluate candidates against verifiable criteria:

| Criterion | Question |
|---|---|
| Native support | Is there Native Image documentation/metadata and testing? |
| Spring integration | Is there appropriate Spring AOT/RuntimeHints support? |
| API fit | Does it satisfy current use cases without heavy adapter layers? |
| Maintenance | Are there recent releases, active issue handling, and a support policy? |
| Compatibility | Does it match the project's JDK, Spring Boot, GraalVM, and license? |
| Security | Is there a clean CVE history, patching process, and safe dependencies? |
| Performance | Do latency, throughput, allocation, and RSS meet requirements? |
| Migration | Can you migrate incrementally and roll back? |
| Operations | Do logging, metrics, tracing, and configuration fit? |

Run benchmarks using realistic workloads. Do not choose a library merely because its homepage claims "GraalVM compatible"; test the exact APIs, modules, and versions you will use.

## 11. Using an Adapter to Reduce Impact When Replacing a Library

Place an internal interface between business logic and the external library:

```java
public interface DocumentRenderer {
    byte[] render(RenderRequest request);
}
```

Current implementation:

```java
@Component
class LegacyDocumentRenderer implements DocumentRenderer {
    @Override
    public byte[] render(RenderRequest request) {
        // Call current library
        return new byte[0];
    }
}
```

Replacement implementation:

```java
@Component
class NativeFriendlyDocumentRenderer implements DocumentRenderer {
    @Override
    public byte[] render(RenderRequest request) {
        // Call Native Image-compatible library
        return new byte[0];
    }
}
```

Method bodies here are placeholders; in a real application, implement full logic and specific exception handling. Business services depend only on `DocumentRenderer`, never directly on the SDK.

An adapter helps:
- Confine changes to a single module.
- Write contract tests independent of the library.
- Run two implementations side by side during migration when safe.
- Standardize error models and logging.
- Roll back via configuration/bean selection if both implementations are packaged.

If using `@ConditionalOnProperty` to choose the adapter, remember that conditions affect the bean graph during Spring AOT. If you want runtime selection inside the same native binary, register the required implementations and use a runtime selector rather than excluding beans at build time.

## 12. Comparing the Three Options: Upgrade, Replace Library, Change Integration

| Option | Choose when | Benefits | Costs/risks |
|---|---|---|---|
| Upgrade library | Upstream fixed issues or added native metadata | Keeps familiar API, minimal business changes | Breaking changes, transitive dependencies |
| Change integration | Library works once unnecessary dynamic paths are removed | Keeps dependency, reduces migration scope | Adapter/registry code, must test new paths |
| Replace library | Core design is unsuitable or maintenance is poor | Eliminates long-term limitations | Migration effort, behavioral/performance differences, licensing |

Options can be combined. For instance, upgrade the SDK to a newer version while replacing plugin discovery with a static registry. If no version supports the dynamic use case, isolating that capability into a JVM service may make more sense than swapping in another library that shares the same limitation.

## 13. Assessing Impact on Spring AOT and Native Image

Every change in dependency or integration approach requires re-verifying:

- Bean registration and conditional configuration.
- Proxy/interface combinations.
- Reflection, JNI, and serialization hints.
- Classpath resource patterns.
- Class initialization policies.
- Native library architecture/ABI.
- Script engines, classloaders, and dynamic compilation.
- Buildpack/runtime image and shared libraries.

Do not assume old metadata remains valid after an upgrade. A new version may add hints, rename packages/classes, or alter behavior. Conversely, removing a library can leave previously hand-written `RuntimeHints` obsolete; remove unused metadata once tests confirm.

## 14. A Rollback-Capable Migration Workflow

A safe workflow:

1. **Baseline:** capture current test results, dependency tree, native build logs, startup/RSS, and behavior.
2. **Reproduce:** build a small test for the failing feature on both JVM and native.
3. **Research:** check upstream releases, metadata, issues, and compatibility.
4. **Select option:** upgrade version, change integration, replace library, or isolate service.
5. **Adapter/contract:** stabilize internal APIs and write contract tests.
6. **Isolated experiment:** change one dependency or call path at a time.
7. **Native validation:** run Spring AOT, build the executable, and test inside the runtime container.
8. **Regression:** run the full test suite and compare outputs.
9. **Benchmark:** measure startup, RSS, throughput, and latency under identical workloads.
10. **Rollout:** deploy via canary, monitor metrics/logs, and retain a rollback path.

Do not replace multiple libraries simultaneously without strong justification. Changing one piece at a time isolates impact and shortens regression root-cause analysis.

## 15. Compatibility Testing for External Libraries

A compatibility suite should cover the exact features the application uses:

| Test category | Examples |
|---|---|
| API behavior | Business results and exception contracts |
| Reflection | Dynamically accessed constructors/methods/fields |
| Resources | Templates/schemas/message bundles |
| Proxy/AOP | Interface lists, transactions/advice |
| Serialization | JSON, polymorphic types, custom serializers |
| Class initialization | Environment/file/network side effects |
| JNI | Library loading, callbacks, and architecture |
| Container | User, filesystem, shared libraries, config mounts |
| Version compatibility | JDK/Spring/GraalVM/plugin versions |
| Performance | Startup, RSS, throughput, and latency |

Run JVM tests first to verify basic functionality, then run native build/tests. If only native fails, keep a minimal fixture to investigate. If both fail after migration, it is likely a breaking library behavior change rather than a Native Image issue.

## 16. Signs You Should Stop Adding Hints

Stop expanding hints and evaluate architectural changes when:

- The application must compile arbitrary Java source code after the native executable is released.
- Unforeseen plugin classes must be loaded after build time.
- The engine relies on runtime bytecode generation without Native Image support.
- Metadata would have to register an unbounded set based on user data.
- Broad hints force the image to retain a large, hard-to-govern set of classes/members.
- Upstream confirms the feature is unsupported in Native Image.
- Workarounds reach deep into internal implementations and break across versions.

In these cases, consider a DSL/interpreter, build-time code generation, a JVM worker/service, or a dedicated process. Choose based on logic update frequency, security, latency, and operability requirements.

## 17. Hands-On Exercise: Deciding Between Upgrade and Integration Change

**Scenario:** a partner SDK uses reflection to instantiate payloads, reads templates from the classpath, and performs plugin discovery. It works on the JVM, while native builds report missing reflection/resource metadata; new plugins are loaded from a directory post-deployment.

**Step 1 — Break down features.** Create three separate tests: payload reflection, template loading, and plugin discovery.

**Step 2 — Inspect the current version.** Review the dependency tree, release notes, and the SDK's Native Image documentation.

**Step 3 — Trial the newer version.** Check whether the SDK ships official reflection/resource metadata and native tests; re-run all three tests.

**Step 4 — Evaluate plugins.** Determine whether plugins can be fixed at build time or truly must be added post-deployment. If the plugin set is fixed, include them in build inputs and register types/hints.

**Step 5 — Try changing integration.** Replace discovery with a static registry for known plugins; keep the SDK if the remaining features are compatible.

**Step 6 — Evaluate remaining limitations.** If post-release loading of new plugins remains mandatory, prototype isolating the plugin host into a JVM service and define the contract.

**Step 7 — Compare options.** Record migration cost, native build time, image size, startup, RSS, latency, security, and operations.

**Step 8 — Choose rollout.** Use adapters/contract tests, canary deployment, and rollback to verify production behavior.

Completion criteria: evidence exists for each root cause, the decision is justified by compatibility and cost, JVM/native tests pass for supported features, and remaining limitations have a clear architectural plan.

## 18. Conclusion

When an external library runs into issues with Spring Boot Native Image, classify the root cause and verify feature scope before deciding. **Upgrade** when upstream has improved native support; **change the integration** when the library works well with a known set of types/resources/proxies; **replace the library** when its design, maintenance, or native support fails to meet requirements. For post-deployment arbitrary code compilation or loading, consider isolating into a JVM service or specialized environment.

Use adapters, contract tests, dependency analysis, native integration tests, and benchmarks to govern migration. A sound decision ensures functionality, maintainability, security, and operational cost—not just getting a single native build to pass.
