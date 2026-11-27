# Migrating from Legacy Experimental Spring Native to Supported Spring Boot AOT

## 1. Migration Context and Goals

Spring Native was an experimental project for bringing Spring applications to GraalVM Native Image. Version 0.12.2 was one of the final releases in that experimental line, tested with Spring Boot 2.7.7 and GraalVM 22.1. Following the experimental phase, Spring moved native support officially into Spring Boot 3. The Spring Native repository has been archived and no longer receives new releases.

With Spring Boot 3, Spring AOT, Runtime Hints, and Native Build Tools integration became part of the core Spring Boot/Spring Framework ecosystem. Applications no longer need to retain the experimental Spring Native dependency or the legacy project's separate AOT plugin.

Migration is more than removing a dependency and bumping a version. You must verify simultaneously:

- Versions of Spring Boot, Java, Spring Framework, and related libraries.
- Legacy experimental dependencies and plugins.
- How AOT is configured in Maven or Gradle.
- Native hints for reflection, resources, proxies, and serialization.
- Profiles/conditions evaluated at build time.
- Jakarta EE compatibility and major Spring Boot 3 changes.
- Testing AOT on the JVM, native tests, and the final native executable.

This lesson belongs to the **Migration and Upgrade** chapter of the **SPRING_BOOT_NATIVE_IMAGE** module. Its goal is to move an application using Spring Native onto Spring Boot's built-in AOT mechanism so it can be built and tested reproducibly.

## 2. Differences Between Spring Native and Spring Boot Native Support

| Component | Experimental Spring Native | Spring Boot Built-in AOT |
| --- | --- | --- |
| Status | Experimental project, archived | Official native support in Spring Boot 3 and later |
| AOT engine | Separate `org.springframework.experimental` plugin | Built into Spring Boot and Spring Framework |
| Maven AOT | `spring-aot-maven-plugin` | `spring-boot-maven-plugin` with `process-aot` |
| Gradle AOT | `org.springframework.experimental.aot` | Spring Boot Gradle plugin with Native Build Tools |
| Native hints | `@NativeHint`, `@TypeHint`, `NativeConfiguration` | `RuntimeHintsRegistrar`, `@ImportRuntimeHints`, `@RegisterReflectionForBinding` |
| Native compiler | Native Build Tools or Buildpacks with legacy config | Native Build Tools and Spring Boot Buildpacks integration |
| AOT/native testing | Legacy plugin test mechanism | `process-test-aot`, `nativeTest`, and Native Build Tools |
| Third-party metadata | Spring Native configuration modules | Reachability Metadata Repository and library-provided metadata |

Spring Native 0.12.2 only validated a specific beta support matrix; legacy documentation cites Spring Boot 2.7.7 and GraalVM 22.1. Those versions should no longer be used as a baseline for new projects. Spring Boot 3 makes native compilation an official target and integrates more deeply with GraalVM tooling.

Spring's migration blog post: [From Spring Native to Spring Boot 3](https://spring.io/blog/2023/02/23/from-spring-native-to-spring-boot-3). The legacy Spring Native documentation also explicitly notes that the project has been superseded by official native support in Spring Boot 3.

## 3. Inventorying the Legacy Project Before Upgrading

Before editing build files, record the current state so you know everything that needs to change.

| Area | What to inspect |
| --- | --- |
| Spring Boot | Current version, usually 2.7.x if using Spring Native 0.12.x |
| Java/GraalVM | JDK, GraalVM distribution, edition, and `native-image` version |
| Maven/Gradle | Wrapper version, plugin versions, and build profiles |
| Spring Native dependencies | `org.springframework.experimental:spring-native`, `spring-native-configuration` |
| AOT plugin | `spring-aot-maven-plugin` or `org.springframework.experimental.aot` |
| Native Build Tools | `native-maven-plugin` or `org.graalvm.buildtools.native` |
| Hints | `@NativeHint`, `@TypeHint`, `NativeConfiguration`, `spring.factories` |
| Native JSON metadata | `META-INF/native-image` and reflect/resource/proxy files |
| Buildpacks | `BP_NATIVE_IMAGE`, builder, and buildpack versions |
| Tests | JVM tests, AOT tests, native tests, and test fixtures |
| Dependencies | Whether libraries support Spring Boot 3, Jakarta, and GraalVM |

Save the dependency tree output and the list of applied plugins. If an old dependency comes from a shared module or centrally managed plugin, locate where it is actually declared before removing it.

Dependency check examples:

```bash
./mvnw dependency:tree
./gradlew dependencies
```

With Gradle, you can filter dependencies by group/artifact using the task or dependency report suited to your build. Do not remove a dependency just because its name contains "native"; determine whether it comes from legacy Spring Native, Native Build Tools, or another runtime library.

## 4. Choosing a Spring Boot Upgrade Path

If the project is on Spring Boot 2.7, stabilize the application on the latest 2.7 maintenance release before moving to Boot 3. This separates framework upgrade issues from native build pipeline changes.

Spring Boot 3.0 requires Java 17 or higher and Spring Framework 6.0. It also migrates Java EE APIs within Spring Boot's scope to Jakarta EE. Prepare the platform migration accordingly:

1. Upgrade JDK/build tools to levels supported by Spring Boot 3.
2. Check compatibility of Spring Cloud, Spring Data, Spring Security, and third-party libraries.
3. Migrate Jakarta EE `javax.*` APIs to `jakarta.*`.
4. Upgrade Spring Boot and plugins along the same release line.
5. Run the standard JVM application first.
6. Only move to the native AOT build after the application is stable on Boot 3.

Do not mix upgrading Spring Boot, swapping database drivers, changing logging, and migrating native hints in one giant change if they can be split into independently reviewable steps.

Refer to the [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide) and release notes for your target version. Specific Spring Boot 3.0 requirements are a historical milestone; when choosing a newer Boot release, verify system requirements and GraalVM compatibility for that exact version.

## 5. Removing Legacy Spring Native Dependencies

With Maven, the experimental dependency was commonly declared as:

```xml
<dependency>
    <groupId>org.springframework.experimental</groupId>
    <artifactId>spring-native</artifactId>
    <version>0.12.2</version>
</dependency>
```

Remove this dependency after moving the application to Spring Boot native support. Spring Boot 3 does not require `spring-native` to run native executables.

With Gradle, the old Spring AOT plugin may have pulled `spring-native` transitively. After removing the old plugin, check the dependency tree to confirm the experimental dependency is no longer added indirectly.

If the project has `spring-native-configuration` or a custom native configuration module, classify every hint before deleting it. Do not delete metadata the application still needs just because the module containing hints was created during the Spring Native era. Migrate still-needed hints to the Runtime Hints API or appropriate JSON metadata.

## 6. Migrating Maven Configuration

### 6.1. Legacy Configuration

A Maven project using Spring Native 0.12.x typically had two separate parts:

- `org.springframework.experimental:spring-aot-maven-plugin` to generate sources/AOT artifacts.
- `org.graalvm.buildtools:native-maven-plugin` to invoke the `native-image` compiler.

Legacy AOT plugin example:

```xml
<plugin>
    <groupId>org.springframework.experimental</groupId>
    <artifactId>spring-aot-maven-plugin</artifactId>
    <version>0.12.2</version>
    <executions>
        <execution>
            <id>generate</id>
            <goals>
                <goal>generate</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Remove this execution along with legacy configurations meant only for the experimental plugin. Stop invoking the `spring-aot:generate` goal once moved to Spring Boot AOT.

### 6.2. New Integrated Configuration

If using `spring-boot-starter-parent`, the Spring Boot Maven plugin's `native` profile configures `process-aot` execution and suitable defaults for Native Build Tools. The application module should declare the Spring Boot plugin and Native Build Tools plugin:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>

        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

Build the native executable:

```bash
./mvnw -Pnative native:compile
```

Or build a container image using Buildpacks if the project configures a suitable builder:

```bash
./mvnw -Pnative spring-boot:build-image
```

The `native` profile provided by the Spring Boot parent includes useful AOT and Native Build Tools settings. If the project does not use `spring-boot-starter-parent`, configure the `process-aot` execution on the Spring Boot Maven plugin and configure Native Build Tools per the documentation for your version. Do not assume the parent profile automatically exists in a POM that only imports a BOM.

### 6.3. Check Plugin Versions

Do not copy Native Build Tools versions verbatim from an old Spring Native project. Legacy examples may use plugin 0.9.x; Spring Boot 3.0 requires GraalVM 22.3 or later and Native Build Tools 0.9.17 or later. Newer Spring Boot releases have updated compatibility matrices.

To select versions:

- Match the Spring Boot release line being deployed.
- Verify the GraalVM distribution/version supported by that release.
- Verify the compatible Native Build Tools plugin version.
- Prefer dependency/plugin management provided by the Spring Boot parent or build conventions.
- Record actual versions in build metadata for reproducibility.

## 7. Migrating Gradle Configuration

### 7.1. Legacy Configuration

Legacy Spring Native Gradle builds typically used:

```groovy
plugins {
    id 'org.springframework.boot' version '2.7.x'
    id 'org.springframework.experimental.aot' version '0.12.2'
}
```

The `org.springframework.experimental.aot` plugin belongs to the experimental project. Remove this plugin and any milestone/snapshot repositories added solely to download the old plugin if no other dependencies need them.

### 7.2. New Configuration

Replace with the Spring Boot Gradle plugin and the GraalVM Native Build Tools plugin:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<compatible-version>'
    id 'org.graalvm.buildtools.native' version '<native-build-tools-version>'
}
```

When the Native Image plugin is applied, the Spring Boot Gradle plugin automatically configures AOT processing and required task dependencies. There is no need to retain `org.springframework.experimental.aot`.

Build the native executable:

```bash
./gradlew nativeCompile
```

The native executable is typically generated under `build/native/nativeCompile/`. Exact path/file name may vary depending on binary configuration and plugin version.

If using Kotlin DSL, convert the `plugins` block to `plugins { id("...") version "..." }` syntax and inspect Gradle-generated tasks with `./gradlew tasks`.

## 8. Migrating from Legacy Buildpacks Configuration

Legacy Spring Native often required enabling the buildpack via `BP_NATIVE_IMAGE=true` in `bootBuildImage` or Maven plugin configuration. Spring Boot's built-in native support supplies appropriate Buildpacks configuration when using the `native` profile and corresponding plugins.

After migration:

1. Remove legacy configuration meant solely for the Spring Native plugin.
2. Select a builder/buildpack compatible with your GraalVM and Spring Boot versions.
3. Inspect Buildpacks logs to confirm AOT processing and native compilation ran.
4. Verify the container image actually contains a native executable.
5. Run smoke tests inside the final image.
6. Record builder digest, GraalVM version, architecture, and build arguments.

Do not mix legacy `BP_NATIVE_IMAGE` settings with new native configuration without understanding precedence and where variables are consumed. If custom buildpack arguments are needed, use mechanisms supported by your current Spring Boot/Buildpacks documentation.

## 9. Migrating the Native Hints API

This is the part requiring the closest review during migration. Legacy Spring Native had `@TypeHint`, `@NativeHint`, `@JdkProxyHint`, and `NativeConfiguration`. Modern Spring Boot/Spring Framework uses the Runtime Hints API with clearer hint types.

| Legacy API | Migration path |
| --- | --- |
| `@TypeHint` for DTO needing JSON binding | `@RegisterReflectionForBinding` if the purpose is binding |
| `@TypeHint` for general reflection | `RuntimeHintsRegistrar` and `hints.reflection()` |
| `@NativeHint` containing resource patterns | `hints.resources()` |
| `@JdkProxyHint` | `hints.proxies().registerJdkProxy(...)` |
| `@NativeHint` containing serialization metadata | `hints.serialization()` or corresponding API |
| `NativeConfiguration` | `RuntimeHintsRegistrar` imported via `@ImportRuntimeHints` |
| `spring.factories` listing `NativeConfiguration` | Register registrar from a configuration class using `@ImportRuntimeHints` |
| Native image build options | Native Build Tools build arguments or `native-image.properties` as appropriate |

Not every legacy annotation has a one-to-one replacement. Understand the intent of each hint and translate it to the matching new API. `@RegisterReflectionForBinding` is intended for types needing binding/serialization introspection; it does not replace all reflection, proxy, JNI, or class initialization hints.

### 9.1. DTO Binding with `RegisterReflectionForBinding`

Legacy example:

```java
@TypeHint(types = PartnerResponse.class)
@SpringBootApplication
public class OrdersApplication {
}
```

If the hint's purpose is solely allowing Jackson to bind the DTO, migrate to:

```java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@RegisterReflectionForBinding(PartnerResponse.class)
public class OrdersApplication {
}
```

This annotation instructs Spring to register the reflection metadata needed for binding. If the class is accessed via reflection for other reasons, use the Runtime Hints API with appropriate member access categories.

### 9.2. Reflection and Resources with `RuntimeHintsRegistrar`

New registrar example:

```java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class PartnerRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
            PartnerPayload.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS
        );

        hints.resources().registerPattern("partner/*.json");
    }
}
```

Import the registrar from a configuration class:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PartnerRuntimeHints.class)
class PartnerNativeConfiguration {
}
```

Register only members actually required at runtime. Overly broad hints increase binary size and erode static analysis benefits; missing hints cause failures that only surface when running natively.

### 9.3. Proxies and Serialization

If legacy code registered JDK proxies, migrate to `hints.proxies().registerJdkProxy(...)` with the exact proxied interfaces. For Java serialization, use `RuntimeHints`'s serialization API and test with the actual object types.

Do not confuse JDK dynamic proxies with CGLIB/AOT-generated proxies. Spring AOT can generate some proxies needed for beans and configuration; custom proxies or libraries generating proxies themselves still require separate evaluation.

### 9.4. Static JSON Hints

GraalVM JSON metadata files under `META-INF/native-image` can still be used if the schema and options remain compatible with the target GraalVM version. Do not bulk-delete `reflect-config.json`, `resource-config.json`, or `proxy-config.json` merely because you are leaving Spring Native.

Verify:

- Which dependency owns each file and who maintains it.
- Whether the metadata is still accurate for the new library version.
- Whether it duplicates hints generated by Spring AOT.
- Whether GraalVM recognizes the metadata path.
- Whether native integration tests prove the metadata is still needed.

Spring Boot AOT places some generated hints under `META-INF/native-image/{groupId}/{artifactId}/`. Place supplemental hints in a different directory to avoid overwriting or colliding with generated output.

## 10. Migrating `NativeConfiguration` and `spring.factories`

In Spring Native, libraries could implement `NativeConfiguration`, annotate with `@NativeHint`, and list implementations under a dedicated key in `META-INF/spring.factories`.

In modern Spring Framework, a registrar implements `RuntimeHintsRegistrar` and is activated via `@ImportRuntimeHints` on an appropriate configuration class or application configuration.

Example layout:

```text
src/main/java/
  com/example/partner/
    PartnerRuntimeHints.java
    PartnerNativeConfiguration.java
```

If developing a shared library, design the registrar so it does not depend on classes present only in consuming applications. Test the registrar independently and run integration tests with a sample application.

Note: `spring.factories` has not disappeared completely from Spring. What must be replaced here is Spring Native's custom `NativeConfiguration` registration mechanism. Spring Boot 3 auto-configuration registration changed separately: libraries should use `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` per Spring Boot's migration guide.

## 11. Profiles, Conditions, and the AOT Environment

Spring AOT prepares the `BeanFactory` and evaluates conditions at build time. Therefore, profiles or properties that alter the bean graph must be configured when running AOT.

For example, if `@ConditionalOnProperty` determines which adapter exists, the property value used during AOT must reflect the intended structure of the native executable.

With Maven, configure profiles for `process-aot` via the Spring Boot Maven plugin. With Gradle, configure arguments/environment for the `processAot` task. Do not assume activating a profile in the container runtime will add beans excluded during AOT.

If a single binary must support multiple runtime choices, design the bean graph so all needed implementations exist in the image, then pick the implementation via runtime logic. This works only if all required classes, dependencies, and hints are already included in the binary.

## 12. Handling Jakarta and Spring Boot 3 Changes

Moving off Spring Native 0.12.x typically coincides with upgrading from Spring Boot 2.7 to 3.x. Several changes need review:

- Java 17 or higher is the Spring Boot 3.0 baseline.
- Spring Framework 6 requires Jakarta EE compatibility.
- Jakarta EE imports change from `javax.*` to `jakarta.*`, such as Servlet, Persistence, and Validation.
- Spring Security 6 introduces configuration and behavior changes.
- Newer Hibernate 6 and Spring Data versions may change APIs, mappings, or query behavior.
- Spring Cloud must select a release train compatible with the target Spring Boot version.
- Certain properties, auto-configurations, and dependencies were renamed or removed.

Do not blindly replace every `javax` in source with `jakarta`. Change only Jakarta EE packages; Java SE packages such as `javax.crypto`, `javax.net.ssl`, or `javax.sql` remain in the standard Java namespace.

Spring Boot provides `spring-boot-properties-migrator` to detect properties renamed or removed during upgrades. Use it temporarily during migration and remove the dependency once all warnings are resolved.

## 13. Auditing Third-Party Libraries and Reachability Metadata

Legacy Spring Native had the `spring-native-configuration` module providing hints for several libraries. In the new ecosystem, Spring Boot does not bundle hints for every third-party library; libraries may ship their own reachability metadata or be supported via the GraalVM Reachability Metadata Repository.

For each important dependency:

1. Verify the version supports Spring Boot 3 and Java 17+.
2. Check whether the library ships built-in native metadata.
3. Inspect reflection, JNI, resource loading, serialization, and proxy usage.
4. Check `native-image` logs to see which metadata gets loaded.
5. Run integration tests on the native executable.
6. Add application-level hints only when library metadata does not cover a path.

Do not copy hints verbatim from legacy modules into the new application without checking. Legacy hints may be overly broad, duplicate newer hints, or target classes whose packages/APIs changed.

## 14. Layered Migration Testing

Increase testing granularity progressively to catch errors early and avoid repeated long native builds.

### 14.1. JVM Tests

Run standard unit and integration tests after upgrading Spring Boot. This is where you fix API, Jakarta, configuration, and behavior issues before introducing native-specific debugging.

### 14.2. AOT-Processed JVM

Build an artifact with AOT-generated code and run it with `spring.aot.enabled=true`:

```bash
./mvnw -Pnative package
java -Dspring.aot.enabled=true -jar target/orders-api.jar
```

With Gradle, ensure the `org.graalvm.buildtools.native` plugin is applied so AOT tasks are configured:

```bash
./gradlew bootJar
java -Dspring.aot.enabled=true -jar build/libs/orders-api.jar
```

This step validates AOT-generated initialization code without waiting for `native-image` compilation. It does not replace native tests.

### 14.3. Native Executable

Build and run the actual binary:

```bash
./mvnw -Pnative native:compile
./target/orders-api
```

With Gradle:

```bash
./gradlew nativeCompile
./build/native/nativeCompile/orders-api
```

File names and output directories depend on artifact name, OS, and build configuration. Run smoke tests across HTTP, database, messaging, serialization, and TLS along the flows the application uses.

### 14.4. Native Tests

Spring Boot and Native Build Tools support running tests inside a native image. With Maven using `spring-boot-starter-parent`, the `nativeTest` profile configures AOT test processing and native test execution:

```bash
./mvnw -PnativeTest test
```

With Gradle:

```bash
./gradlew nativeTest
```

Native tests have higher build cost than JVM tests. Keep most tests on the JVM, run native tests for flows sensitive to reflection/resources/proxies, and schedule them in CI or release gates appropriately.

## 15. Testing Runtime Hints

Runtime Hints can be unit-tested with `RuntimeHintsPredicates` without building a native image for every change.

Example testing a resource hint:

```java
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class PartnerRuntimeHintsTests {

    @Test
    void registersPartnerSchema() {
        RuntimeHints hints = new RuntimeHints();

        new PartnerRuntimeHints()
            .registerHints(hints, getClass().getClassLoader());

        assertThat(
            RuntimeHintsPredicates.resource()
                .forResource("partner/schema.json")
        ).accepts(hints);
    }
}
```

Add corresponding tests for reflection, proxy, or serialization hints if used by the application. These tests confirm the registrar declares the expected metadata; native integration tests are still needed to verify actual behavior inside the binary.

## 16. Inspecting AOT Output and Native Metadata

After AOT processing, inspect generated output directories to see what Spring produced.

With Maven, AOT typically generates sources, classes, and resources under `target/spring-aot/main/sources`, `target/spring-aot/main/classes`, and `target/spring-aot/main/resources`. Native hints are placed under resources, usually in `META-INF/native-image`; when packaged, they appear on the artifact's classpath.

With Gradle, outputs typically appear under `build/generated/aotSources`, `build/generated/aotClasses`, and `build/generated/aotResources/META-INF/native-image` depending on plugin version.

Check:

- Generated sources contain expected bean initializers.
- Runtime hints include required DTOs, resources, and proxies.
- Static JSON metadata is packaged.
- The native compiler picks up metadata from dependencies.
- No stale output from the old Spring Native plugin enters the classpath.

Do not edit generated sources or generated hint outputs directly. Fix the registrar, annotations, metadata sources, or build configuration and re-run AOT.

## 17. Common Migration Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Cannot find `org.springframework.experimental` | Old dependency/plugin removed while source still imports it | Migrate hint APIs to Runtime Hints or delete obsolete code |
| `spring-aot:generate` goal missing | Invoking legacy AOT plugin | Use `process-aot` or tasks configured by the Spring Boot plugin |
| `@NativeHint`/`@TypeHint` fails to resolve | Spring Native APIs removed from new dependencies | Migrate by intent to `@RegisterReflectionForBinding`, `RuntimeHintsRegistrar`, or JSON metadata |
| Native executable lacks DTO binding | Old hint not migrated or registered on wrong class | Register binding on exact DTO and run native tests |
| Resource not found | Missing resource hint or wrong pattern | Register `hints.resources()` and test resource predicate |
| Runtime profile fails to create bean | Condition evaluated during AOT | Select profile at AOT time or design bean graph for runtime selection |
| JVM tests pass but native fails | Reflection, proxy, JNI, or resource missing metadata | Read `native-image` diagnostics, add targeted hints, and re-test |
| Dependency incompatible with Boot 3 | Library still uses `javax` or old APIs | Upgrade library version or replace dependency |
| Buildpacks builds JVM image instead of native | Builder/profile not configured for native | Check `native` profile, builder, and Buildpacks logs |
| Multi-module build skips AOT output | Plugin applied only to non-application module | Apply plugin and `native` profile to the application module |
| Duplicate hints registered | Keeping both old JSON hints and new registrar | Audit metadata sources and remove duplicates after testing |
| Native tests do not run | `nativeTest` unconfigured or GraalVM toolchain missing | Check plugins, profiles, and native test task |

## 18. Phased Migration Workflow

A migration plan can proceed in sequence:

1. **Freeze baseline:** save commit, dependency tree, plugin list, native build command, and legacy test results.
2. **Stabilize Spring Boot 2.7:** upgrade to an appropriate maintenance release and fix deprecations.
3. **Upgrade platform:** move to JDK 17+, select compatible GraalVM and Native Build Tools.
4. **Upgrade Spring Boot:** address Jakarta, Spring Framework, Spring Security, Spring Data, and Spring Cloud.
5. **Remove Spring Native:** delete experimental dependencies, AOT plugin, and experimental build configuration.
6. **Integrate new AOT:** configure Spring Boot Maven/Gradle plugin and Native Build Tools.
7. **Migrate hints:** convert each `@NativeHint`, `@TypeHint`, `NativeConfiguration`, and needed metadata.
8. **Verify dependencies:** confirm libraries have reachability metadata or native support.
9. **Run JVM tests and AOT JVM:** fix errors before native compilation.
10. **Build native and native tests:** verify endpoints, databases, serialization, resources, proxies, and TLS.
11. **Package container:** verify architecture, libc, environment, and startup behavior.
12. **Canary and rollout:** compare startup, memory, latency, error rate, and keep rollback image ready.

Keep a verified legacy artifact for rollback during transition. Do not simultaneously change GraalVM version, builder image, and optimization flags if the migration's goal is to validate moving from Spring Native to Spring Boot AOT.

## 19. Hands-on Exercise: Migrating a Spring Native 0.12.x App to Spring Boot AOT

**Context:** A REST service using Spring Boot 2.7.x, Spring Native 0.12.2, Maven, and a `@TypeHint` for a DTO deserialized by an HTTP client.

**Steps:**

1. Save the dependency tree, native build output, and test baseline of the legacy app.
2. Upgrade to an appropriate Spring Boot 2.7 maintenance release before jumping major versions.
3. Upgrade Java to 17 and check dependency compatibility with Jakarta EE.
4. Upgrade Spring Boot to the chosen 3.x release line and resolve `javax`/`jakarta` changes.
5. Remove the `org.springframework.experimental:spring-native` dependency.
6. Remove the `spring-aot-maven-plugin` plugin and `generate`/`test-generate` goals.
7. Declare the Spring Boot Maven plugin and Native Build Tools Maven plugin.
8. Convert the DTO `@TypeHint` to `@RegisterReflectionForBinding` if its purpose is JSON binding.
9. Convert custom reflection/resource/proxy hints to `RuntimeHintsRegistrar`.
10. Run JVM tests, AOT-processed JVM, and native compilation.
11. Send requests to the native executable to confirm DTO binding, HTTP client, and business behavior.
12. Run native tests, package the container, and verify the deployable artifact.
13. Compare startup, RSS, container size, and latency against the legacy baseline.

**Passing criteria:**

- No remaining experimental Spring Native dependencies or plugins.
- Build pipeline uses built-in Spring Boot AOT.
- Runtime hints are migrated by intent without overly broad reflection registration.
- Jakarta and dependencies are compatible with the target Spring Boot version.
- AOT-processed JVM starts cleanly.
- Native executable handles critical HTTP/serialization flows.
- Native tests and container smoke tests pass.
- Build metadata documents Spring Boot, GraalVM, Native Build Tools, and builder versions.
- Legacy artifact and rollback procedure are available during rollout.

## 20. Summary

Spring Native 0.12.x was an experimental project superseded by official native support in Spring Boot 3. During migration, remove the `spring-native` dependency and the experimental `spring-aot-maven-plugin` or Gradle plugin, then switch to Spring Boot AOT alongside GraalVM Native Build Tools.

The area requiring careful review is Runtime Hints: convert `@TypeHint` based on binding vs. general reflection intent, migrate `@NativeHint`/`NativeConfiguration` to `RuntimeHintsRegistrar`, retain still-needed JSON metadata, and audit third-party libraries. Simultaneously handle Java 17, Jakarta EE, and Spring Boot 3 changes. Testing in order—JVM, AOT-processed JVM, native tests, and native executable—catches errors early before releasing the new artifact.

## References

- [From Spring Native to Spring Boot 3](https://spring.io/blog/2023/02/23/from-spring-native-to-spring-boot-3/)
- [Spring Native 0.12.x Reference Documentation](https://docs.spring.io/spring-native/docs/0.12.x/reference/htmlsingle/)
- [Spring Boot — Ahead-of-Time Processing with Maven](https://docs.spring.io/spring-boot/maven-plugin/aot.html)
- [Spring Boot — Ahead-of-Time Processing with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/aot.html)
- [Spring Boot — Advanced Native Image Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/3.4/how-to/native-image/testing-native-applications.html)
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)

