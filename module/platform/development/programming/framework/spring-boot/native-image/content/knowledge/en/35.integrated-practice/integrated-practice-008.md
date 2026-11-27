# Integrating a Dependency with Repository Metadata or Application Hints

## 1. Practice Objectives

This practice integrates a third-party library with dynamic operations, checks whether the library already supplies GraalVM reachability metadata, and then builds and runs a Spring Boot Native Image. If upstream metadata does not cover the operation used by the application, we add Spring AOT RuntimeHints in the application module.

Distinguish two sources of metadata:

- Metadata shipped with the dependency: maintained by the vendor/library, typically packaged inside the JAR or supplied via the GraalVM Reachability Metadata Repository.
- Application hints: declared by the application for how it uses the dependency, typically via RuntimeHintsRegistrar.

The library coordinates below are illustrative placeholders, not real dependencies to copy verbatim. Replace them with your project's actual library and check the vendor's documentation/version.

## 2. Scenario: A Library Instantiating a Formatter via Reflection

Suppose the service uses a document processing library with this API:

```java
DocumentFormatter formatter =
    DocumentEngine.createFormatter("com.vendor.docs.PdfFormatter");
byte[] output = formatter.format(input);
```

The application calls a public API, while internally the library looks up the class by name and invokes its constructor via reflection. On the JVM, the full classpath generally allows this operation. In Native Image, dynamically accessed classes/members require appropriate reachability metadata.

Do not immediately add a reflection hint upon seeing an API that takes a class name. First check whether the dependency already includes built-in metadata.

## 3. Add the Dependency to the Right Application Module

Gradle:

```groovy
dependencies {
    implementation("com.vendor:document-engine:2.4.0")
}
```

Maven:

```xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>document-engine</artifactId>
    <version>2.4.0</version>
</dependency>
```

These group, artifact, and version values are placeholders. Replace them with the coordinates published by the vendor. The dependency must be on the runtime classpath of the application module, not solely in test scope or a tooling module.

Inspect the resolved dependency:

```bash
./gradlew :api-app:dependencyInsight --dependency document-engine --configuration runtimeClasspath
```

Or Maven:

```bash
./mvnw -pl api-app dependency:tree
```

Record the actual resolved version, transitive dependencies, and the module owning the dependency. If the library has multiple artifacts, determine whether metadata is bundled in the main JAR or published separately.

## 4. Inspect Metadata Inside the JAR

Reachability metadata may reside inside the JAR following the GraalVM convention, usually under META-INF/native-image/. Newer versions support the unified reachability-metadata.json format; older libraries may use separate files for reflection, resources, proxies, or JNI.

List the JAR contents:

```bash
jar tf document-engine-2.4.0.jar | grep META-INF/native-image
```

If the dependency resides in the Gradle cache or Maven local repository, inspect the exact resolved JAR. Do not inspect a manually downloaded JAR whose version differs from what the build actually uses.

Some libraries provide metadata through the GraalVM Reachability Metadata Repository instead of bundling it inside the JAR. Native Build Tools/GraalVM can look up entries by artifact/version coordinates depending on configuration and toolchain. Consult your plugin version's documentation to confirm repository support is enabled properly and metadata is actually loaded.

## 5. Read the Metadata and Determine Its Scope

A unified metadata file can describe reflection, resources, serialization, JNI, and proxies. Illustrative example:

```json
{
  "reflection": [
    {
      "type": "com.vendor.docs.PdfFormatter",
      "allDeclaredConstructors": true
    }
  ]
}
```

This is a conceptual example; supported schemas and fields depend on the GraalVM metadata version. Do not author files with fields rejected by the current schema.

When reviewing metadata, ask:

- Which types are registered?
- Which constructors, methods, or fields need access?
- Are all members registered?
- Are resource patterns overly broad?
- Is the metadata conditional on a class/feature?
- Does the metadata apply to the exact library version in use?

Overly broad metadata can bloat retained code and metadata. Overly narrow metadata can cause a runtime branch to fail.

## 6. Verify That the Metadata Repository Is Used

If metadata comes from the repository rather than the JAR, verify:

1. Resolved dependency coordinates and version.
2. Native Build Tools/GraalVM version supports the corresponding repository mechanism.
3. Repository configuration is enabled per plugin instructions.
4. Build logs indicate metadata was found and loaded.
5. Native Image build inputs include the expected metadata.
6. Regression tests confirm the dynamic operation works.

Do not assume adding a dependency automatically fetches repository metadata under every configuration. Integration details depend on the GraalVM Native Image and Native Build Tools versions.

If the repository lacks an entry for the dependency version or metadata is not resolved, consult the vendor or add application-level hints after identifying the exact requirement.

## 7. Write an Integration Test Before Adding Hints

Create a test that calls the library's real API:

```java
@SpringBootTest
class DocumentFormattingTest {

    @Autowired
    DocumentService documentService;

    @Test
    void formatsPdfDocument() {
        byte[] result = documentService.format(sampleDocument());
        assertThat(result).isNotEmpty();
        assertThat(result).startsWith("%PDF");
    }
}
```

This is an illustrative example; assertions must match the real output format. Fixtures should be small, deterministic, and independent of uncontrolled external data.

Run the JVM test:

```bash
./gradlew :api-app:test
```

A passing JVM test proves the feature works on the JVM. It does not prove Native Image metadata is sufficient.

## 8. Build Native to Verify Metadata

Run native compilation using the task/goal configured by your project. Gradle example:

```bash
./gradlew :api-app:clean :api-app:nativeCompile
```

Tasks may differ depending on the Spring Boot plugin and Native Build Tools versions. Check the task list and build logs. With Maven, use the Spring Boot Maven Plugin/Native Build Tools goals matching the pinned versions.

After building, run the exact generated executable and execute the corresponding test/HTTP request. If compilation fails, keep the complete compiler log. If the build passes but the feature fails at runtime, save the exception, binary hash, and request fixture.

## 9. When Dependency Metadata Is Sufficient

If the JAR/repository supplies the proper metadata for the library's operations, you usually do not need to re-declare the same hints in the application.

Avoid duplicating broad metadata into the app because the two copies can drift when upgrading the dependency, making reviews harder and forcing the application to maintain metadata it does not own.

Keep the dependency version pinned, document the metadata source, and add a native regression test to catch metadata changes during upgrades.

## 10. When Dependency Metadata Is Missing: Add RuntimeHints

If you determine the library requires constructor reflection without matching metadata, the application can register a hint:

```java
package com.example.api;

import com.vendor.docs.PdfFormatter;
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class DocumentRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
            PdfFormatter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
    }
}
```

The example registers only the constructor. If the stack trace proves the library needs other methods/fields, register the exact corresponding member category. Exact APIs must match your project's Spring Framework version.

Register the registrar with Spring AOT:

```java
package com.example.api;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(DocumentRuntimeHints.class)
public class NativeRuntimeHintsConfiguration {
}
```

If the registrar belongs to an internal shared library, it can be packaged inside that library using the mechanism supported by your Spring version. If it only serves how the application invokes the library, keeping hints in the application module is usually easier to manage.

## 11. Test the Registrar with RuntimeHintsPredicates

Write a test confirming the hint is registered:

```java
class DocumentRuntimeHintsTest {

    @Test
    void registersPdfFormatterConstructor() {
        RuntimeHints hints = new RuntimeHints();

        new DocumentRuntimeHints().registerHints(
            hints,
            getClass().getClassLoader()
        );

        assertThat(
            RuntimeHintsPredicates.reflection()
                .onType(PdfFormatter.class)
                .withMemberCategory(
                    MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
                )
                .test(hints)
        ).isTrue();
    }
}
```

Imports and test dependencies depend on the Spring Framework version. This test verifies the registrar; it does not replace a native integration test.

## 12. Do Not Duplicate Dependency and Application Metadata

Before adding a hint, build a comparison table:

| Library Operation | Dependency Metadata | Application Hint | Decision |
|---|---|---|---|
| Invoke PdfFormatter constructor | Present | None | Use dependency metadata |
| Invoke method via reflection | Missing | Registered required method | Keep application hint |
| Read template by pattern | Suitable pattern present | None | Do not duplicate |
| Create JDK proxy | Unverified | None | Investigate and test first |

The table is illustrative only. Fill in real data based on stack traces, vendor docs, metadata files, and native tests.

If dependency metadata exists but is wrong/incomplete for the current version, consider upgrading the version, reporting to the vendor, or adding a tested supplementary hint. Do not strip upstream metadata just to replace it with a local copy.

## 13. Metadata Is Distinct from Dependencies and Application Configuration

Metadata describes runtime capabilities required by a library, such as reflection/resources/proxies. It does not replace:

- The actual dependency JAR.
- Spring bean registration.
- Profiles or conditional configuration.
- External configuration/secrets.
- OS shared libraries.
- Mounted runtime files.

If PdfFormatter is absent from the runtime classpath, a reflection hint will not load the class into the application. If a Spring bean is excluded by an AOT condition, a hint will not create the bean. If a library needs fonts on the filesystem, resource metadata will not install fonts into the container.

Diagnose the right layer of root cause before adding metadata.

## 14. Use the Tracing Agent as Supplementary Evidence

If the vendor provides no metadata and it is unclear which members are invoked dynamically, the tracing agent can observe test scenarios running on the JVM.

1. Run the application with the tracing agent according to your GraalVM version.
2. Execute representative feature scenarios.
3. Collect reflection/resource/proxy/JNI output.
4. Review every entry and remove unnecessary items.
5. Convert metadata into RuntimeHints or an appropriate metadata format.
6. Build Native Image and re-run tests on native.

The agent only records what occurred in observed scenarios. It does not guarantee detecting rare subtypes, error paths, or unactivated plugins.

## 15. Upgrading Dependencies and Managing Metadata by Version

Metadata is tied to the behavior of a specific dependency version. When upgrading a library:

- Check release notes and Native Image support statements.
- Compare metadata in the JAR or repository.
- Check whether metadata changed types, members, or resource patterns.
- Run JVM and native integration tests.
- Remove application hints that became redundant if supported by evidence.
- Keep lockfiles and dependency versions explicit.

Do not delete an application hint merely because a new version includes metadata; verify the new metadata covers the exact operation and is loaded in the actual build.

## 16. End-to-End Practice Workflow

1. Select a dependency with dynamic operations and Native Image documentation.
2. Add the dependency to the application module's runtime classpath.
3. Record the version and dependency graph.
4. Inspect the JAR under META-INF/native-image/ and the metadata repository.
5. Read the metadata to identify supported types/members/resources.
6. Write a JVM integration test for the real feature.
7. Build native and run tests to verify.
8. If metadata is missing, identify the dynamic operation from the stack trace/agent.
9. Add narrow RuntimeHints in the application or upgrade the dependency if fixed upstream.
10. Test the registrar with RuntimeHintsPredicates.
11. Run Spring AOT, Native Image compile, and native integration tests.
12. Package the final container and test the feature in the release image.
13. Archive dependency version, metadata source, test results, and binary/image digest.

## 17. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Dependency has metadata but native still fails | Metadata does not cover the member/feature being used | Read metadata and stack trace |
| Metadata repository is not loaded | Plugin/version/config has not enabled repository | Check Native Build Tools docs and build logs |
| Hint has no effect | Registrar not imported/discovered | Check AOT configuration/generated output |
| Class not found | Dependency missing from runtime classpath | Inspect dependency graph |
| Bean does not exist | Spring AOT condition/profile excluded the bean | Check bean graph; do not add reflection hint |
| Missing resource | Pattern/resource metadata insufficient or file absent | Inspect JAR and runtime filesystem |
| JVM test passes, native fails | Test has not run in native or metadata is missing | Add native regression test |
| Hint is too broad | Registered all members/packages | Narrow down to observed operations |
| Upgrading dependency reintroduces error | Metadata changed between versions | Diff metadata and re-run feature tests |

## 18. Completion Checklist

- The real dependency is added to the proper application runtime classpath.
- Version and transitive dependency graph are documented.
- Metadata inside the JAR and/or reachability metadata repository was inspected.
- Metadata was verified to be loaded by Native Build Tools during the build.
- A JVM integration test covers the dependency's real API.
- A native test reproduces and verifies the feature.
- No duplicate hints were added if dependency metadata already suffices.
- If metadata was missing, the registrar registers only required types/members/resources.
- The registrar is discovered by Spring AOT.
- The RuntimeHintsPredicates test passes.
- Both the native executable and final container image are tested.
- Regression tests cover the feature and dependency version.
- Metadata source, dependency version, logs, and artifact digest are archived.

## 19. Self-Check Questions

1. How does the reachability metadata repository differ from metadata packaged inside a JAR?
2. How do you verify the actual dependency version on the application runtime classpath?
3. Why must you inspect existing metadata before writing RuntimeHints?
4. When should you rely on upstream metadata and when is an application registrar needed?
5. Can RuntimeHints fix a missing dependency or missing Spring bean?
6. What do RuntimeHintsPredicates prove?
7. Why cannot the tracing agent cover every dynamic operation?
8. When upgrading a dependency, how should metadata and native tests be re-verified?

**Remember:** check upstream metadata first, pinpoint the exact missing dynamic operation, and add minimal RuntimeHints in the rightful owning module. Verify the registrar, run native integration tests, and test the final container to prove the dependency works in the artifact you will release.
