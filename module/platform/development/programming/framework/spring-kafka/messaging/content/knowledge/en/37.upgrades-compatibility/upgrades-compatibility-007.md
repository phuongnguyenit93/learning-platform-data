# Checking Deprecations Before Upgrading

Before upgrading Spring Kafka, Spring Boot, or Kafka Client, you should audit APIs and configurations marked as deprecated. A deprecated API can still run in the current version, but library maintainers have signaled that applications should move to a newer usage pattern. In a later release, that API may be removed or altered, causing the application to fail compilation, fail startup, or process messages differently than before.

Checking deprecations before upgrading helps the development team identify exactly which code must change, how urgent each change is, and whether the change affects messaging flows. With Spring Kafka, the audit must cover Java APIs, Spring Boot configuration, Kafka Client, transitive dependencies, listeners/error handlers, serializers/deserializers, and operational tooling.

## 1. What does deprecation mean?

An API is marked deprecated when a library recommends against using it in new code or wants users to move to a replacement API. In Java, the `@Deprecated` annotation can provide additional details:

| Element | Meaning |
|---|---|
| `@Deprecated` | API is deprecated |
| `since` | Version in which the deprecation started, if provided by the library |
| `forRemoval` | `true` indicates the API is slated for removal in a future release |
| Javadoc `@deprecated` | Explains the reason and usually points to the replacement API |

Example:

```java
/**
 * @deprecated Use the new listener configuration instead.
 */
@Deprecated(since = "2.8", forRemoval = true)
public void configureLegacyListener() {
    // Legacy behavior
}
```

`forRemoval = true` is a signal to prioritize remediation because the API may be removed in a future release. However, `false` does not guarantee the API will stay forever; read the library's release notes and migration guides.

Deprecation does not mean the API is already removed or immediately unsafe. It is a warning about the direction of evolution. The application can still run normally today, while accumulating migration work for a future upgrade.

## 2. Distinguishing deprecated, removed, and breaking change

These three concepts are related but not identical:

| Status | What happens | Action |
|---|---|---|
| Deprecated | API still exists but is discouraged | Plan a replacement |
| Removed | API no longer exists in the target version | Must fix code/config before upgrading successfully |
| Breaking change | Behavior or contract changes, possibly unrelated to deprecation | Read the migration guide and test behavior |

Not every breaking change goes through a deprecation phase. A change can appear in a major release without an old API having been marked beforehand. Conversely, a deprecated API may persist across multiple versions.

Therefore, searching for `@Deprecated` annotations alone is not enough. You must read release notes, migration guides, compatibility matrices, and behavioral changes for each component.

## 3. Audit scope in a Spring Kafka application

Before upgrading, list the classes and configurations your application uses:

| Scope | Examples to inspect |
|---|---|
| Spring Kafka API | `KafkaTemplate`, listener containers, `@KafkaListener`, error handlers, recoverers |
| Kafka Client API | `Producer`, `Consumer`, `Admin`, producer/consumer configurations |
| Spring Boot | Auto-configuration, properties in `application.yml`, starter dependencies |
| Serialization | JSON, Avro, Protobuf, Schema Registry serializers/deserializers |
| Retry and DLT | `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, `@RetryableTopic` |
| Transactions | Kafka transaction manager, producer factory, listener transactions |
| Observability | Micrometer Observation, metrics, tracing, and logging |
| Build and runtime | Java version, Maven/Gradle plugins, transitive dependencies, and connectors |

Review source code, tests, YAML/properties files, deployment manifests, CLI scripts, and connector configs. The compiler only detects part of the problem; property names in YAML or settings built from environment variables may not produce compiler warnings.

## 4. Identifying current and target versions

Deprecation only makes sense when you know which version introduced it and which version the application plans to upgrade to. Record at least:

- Runtime Java and Java compiler release.
- Spring Boot version.
- Spring Framework version managed by Boot.
- Spring Kafka version.
- Kafka Client version (kafka-clients).
- Kafka broker version and connector/Schema Registry versions if applicable.

If the application uses Spring Boot dependency management, prefer letting the Boot BOM manage compatible Spring and Kafka dependencies. Do not override spring-kafka or kafka-clients individually just to get a new API without checking the compatibility matrix.

You can view the dependency tree with Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.kafka:spring-kafka,org.apache.kafka:kafka-clients,org.springframework.boot:spring-boot
```

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Note which dependencies are direct and which are pulled in transitively. Another library may bring in a different Kafka Client version than the one the application intends to use.

## 5. Enabling compiler warnings to find deprecated call sites

The Java compiler can warn when code calls deprecated APIs. Enabling detailed warnings helps locate the exact files and lines needing fixes.

With Maven Compiler Plugin:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <showWarnings>true</showWarnings>
        <compilerArgs>
            <arg>-Xlint:deprecation</arg>
            <arg>-Xlint:removal</arg>
        </compilerArgs>
    </configuration>
</plugin>
```

With Gradle Groovy DSL:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-Xlint:deprecation', '-Xlint:removal']
}
```

With Kotlin DSL:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.addAll(listOf("-Xlint:deprecation", "-Xlint:removal"))
}
```

After enabling warnings, compile both main and test source sets. Read the full output rather than just counting warnings; map each warning to its dependency and target version.

`-Xlint:deprecation` reveals call sites using deprecated APIs. `-Xlint:removal` focuses on APIs marked for removal. These options depend on the JDK; use the JDK matching your application's supported baseline.

Do not enable `-Werror` on the first audit pass if the project has warnings from generated sources or dependencies you cannot immediately modify. Once intentional warnings are cleaned up, consider turning new warnings into errors in CI to prevent deprecation debt from returning.

## 6. Searching annotations in source code

Searching for `@Deprecated` and Javadoc `@deprecated` helps inventory APIs declared by the project itself:

```bash
rg -n --glob "*.java" "@Deprecated|@deprecated" src
```

This command finds declarations of deprecated APIs in source files. It does not find all call sites calling deprecated APIs from external libraries. To detect call sites, use compiler warnings, IDE inspections, or appropriate analysis tools.

In your IDE, enable inspections for deprecated APIs and run Find Usages on marked symbols. Check:

- Production code and tests.
- Java configuration built via reflection.
- Annotations or class names declared as strings.
- Generated sources and template-generated code.
- Modules not built in the main pipeline.

Reflection, method handles, or string-based class/property names may escape compiler detection. These cases require manual review and startup testing.

## 7. Reading Javadoc and finding replacement APIs

When encountering a warning, open the Javadoc of the exact dependency version being compiled. Look for:

1. Reason the API was deprecated.
2. Version where deprecation began (`since`).
3. Whether `forRemoval` is set.
4. Recommended replacement API.
5. Differences in semantics, default values, thread safety, or lifecycle.
6. Links to migration guides or issues explaining the change.

Do not rename methods mechanically. A new API may change retry semantics, offset commits, transaction boundaries, exception classification, or how listener containers manage threads.

Historical example in Spring Kafka: `SeekToCurrentErrorHandler` was deprecated in favor of `DefaultErrorHandler`. During migration, compare how `BackOff`, recoverers, exception classification, and seek/commit behavior are configured in the target version. Do not simply rename the class and assume retry and DLT behavior remain unchanged.

## 8. Reading release notes and migration guides version by version

For every critical dependency, read the release notes for all major/minor versions between the current version and the target version. Look specifically for:

- Deprecated APIs and removed APIs.
- Renamed, deprecated, or removed configuration properties.
- Default value changes.
- Java/Spring baseline changes.
- Kafka protocol or broker compatibility changes.
- Retry, error handling, transaction, and offset behavior changes.
- Serializer, header, metrics, and tracing changes.

Do not read only the target version's notes. When upgrading from an old version across multiple major releases, an intermediate version may have required migration steps before reaching the target.

Official sources to use:

- Spring Kafka change history: https://docs.spring.io/spring-kafka/reference/appendix/change-history.html
- Spring Kafka reference: https://docs.spring.io/spring-kafka/reference/
- Spring Boot release notes and migration guides: https://github.com/spring-projects/spring-boot/wiki
- Apache Kafka upgrade guide: https://kafka.apache.org/documentation/#upgrade
- JDK jdeprscan documentation: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeprscan.html

Always open documentation matching your active or target version. The `current` page may describe APIs newer than your project's baseline.

## 9. Checking deprecations in Spring Boot configuration

Deprecations do not occur only in Java code. Spring Boot may deprecate old configuration properties and provide replacements. These properties often live in `application.yml`, `application.properties`, Helm values, environment variables, or secret/config maps.

Search for Kafka-related properties:

```bash
rg -n "spring[.]kafka|kafka[.]" src/main/resources deploy charts
```

Then cross-check each key against the configuration metadata and release notes of the target Spring Boot release. Check:

- Has the property been renamed or moved to another namespace?
- Have data types, time units, or default values changed?
- Is the old property still bound or silently ignored?
- Do environment variables still map to the new key properly?
- Do Helm/Kubernetes manifests override values inside the application?

During a Spring Boot upgrade, you can temporarily use the `spring-boot-properties-migrator` dependency to detect and help migrate certain renamed properties. Add the migrator matching the Spring Boot version in use, run the application in a test environment, read startup warnings, and fix the actual configuration. Remove the migrator dependency after completing migration; do not keep it as a permanent runtime dependency.

Temporary Maven dependency example:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-properties-migrator</artifactId>
    <scope>runtime</scope>
</dependency>
```

The properties migrator does not replace reading release notes and does not guarantee detecting custom keys, third-party library properties, or dynamically constructed configs.

## 10. Using jdeprscan within its proper scope

The JDK provides `jdeprscan` to find usage of deprecated Java SE APIs in bytecode. Example:

```bash
jdeprscan --release 21 --for-removal target/classes
```

You can scan a built JAR:

```bash
jdeprscan --release 21 --for-removal target/application.jar
```

`jdeprscan` is helpful when upgrading the JDK because it finds deprecated Java SE APIs, especially APIs marked for removal. It is not a deprecation scanner for Spring Kafka, Spring Boot, or Kafka Client. For those libraries, use compiler warnings, IDEs, Javadoc, and each library's release notes.

Do not confuse `jdeprscan` with `jdeps`. `jdeps` analyzes dependencies and module/package dependencies; it does not replace auditing deprecated APIs.

## 11. Analyzing dependency API changes

When upgrading a library version, you can use API comparison tools such as Revapi or japicmp to detect public API changes between two artifacts. They are helpful for checking binary/source compatibility of a library, though they do not automatically prove every call site in an application is safe.

Appropriate workflow:

1. Compare old and new artifacts to find removed APIs, changed signatures, or changed visibility.
2. Read Javadoc/release notes to understand deprecations and replacements.
3. Compile the application against the target dependency version to catch invalid call sites.
4. Run integration tests to catch behavioral changes not visible in signatures.

For internal libraries developed by your organization, you can put Revapi/japicmp in CI to guard the library's own public API. For external dependencies, treat reports as a supplementary signal.

## 12. Prioritizing findings

Not every warning must be fixed at the exact same time. Build a prioritized inventory table:

| Priority | Condition | Action |
|---|---|---|
| P0 - Blocker | API/property removed in target version or code fails to compile | Must fix before upgrading |
| P1 - High | `forRemoval=true`, clear replacement API, or high behavioral risk | Prioritize migration in the same wave |
| P2 - Medium | Deprecated without a clear removal timeline | Create ticket and replacement plan |
| P3 - Low | Warnings in tests/generated code or low-impact APIs | Assign owner, handle as scheduled |

The inventory should have columns:

| Field | Content |
|---|---|
| Symbol/property | API name or configuration key |
| Module/file | Where it is used |
| Dependency/version | Library and version providing the API |
| Deprecated since | Version where it was marked |
| For removal | Yes or no |
| Replacement | Replacement API/property |
| Behavior difference | Differences requiring tests |
| Owner/status | Responsible owner and progress |

Do not ignore warnings because they appear in tests. Tests often hold legacy configuration styles and can continue dragging deprecated APIs into the build.

## 13. Example error handler migration in Spring Kafka

Suppose a legacy application uses `SeekToCurrentErrorHandler` and needs to migrate to `DefaultErrorHandler`. Migration must review retry, backoff, and dead-letter recoverer behavior together.

Example configuration using the newer API:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
class KafkaErrorHandlerConfiguration {

    @Bean
    DefaultErrorHandler kafkaErrorHandler() {
        // Example: retry 2 times, 1 second apart each, then recover.
        return new DefaultErrorHandler(
                (record, exception) -> {
                    // Publish to DLT or record recovery outcome.
                },
                new FixedBackOff(1_000L, 2L)
        );
    }
}
```

This illustrates how to declare the new error handler; a real recoverer should be configured to publish the record to a DLT and confirm send success. Retry counts, exception classification, batch listener behavior, and offset commits must be decided per business requirements.

When replacing an error handler, test:

- Retryable and non-retryable exceptions.
- Number of delivery attempts and backoff intervals.
- Whether recovered records preserve original topic/partition/offset headers.
- How source offsets are handled if DLT publishing fails.
- Whether batch listeners and record listeners behave appropriately.
- Whether transactional listeners roll back and recover properly.

## 14. Do not hide warnings with arbitrary SuppressWarnings

`@SuppressWarnings("deprecation")` may be needed in compatibility adapters or code awaiting migration, but should not be placed at large package/class levels just to clean up logs.

If you must keep a deprecated API temporarily:

1. Limit suppression to the smallest method or statement.
2. Document the technical reason and planned replacement version.
3. Create an issue with an owner and deadline.
4. Confirm the API has not been removed in the target version.
5. Add tests protecting current behavior.

Do not suppress removal warnings without explicit review. An API marked for removal can turn into a compile error as soon as the dependency is bumped.

## 15. Upgrading dependency layers step by step

Spring Kafka runs alongside Spring Framework, Spring Boot, and Kafka Client. Upgrading multiple independent components simultaneously makes it difficult to pinpoint causes when builds or runtimes fail.

A standard controlled sequence:

1. Select the target Spring Boot version and verify the Java baseline.
2. Use the corresponding dependency management to identify supported Spring Framework, Spring Kafka, and Kafka Client versions.
3. Read migration guides/release notes for each major/minor release along the path.
4. Address deprecated/removed APIs and legacy properties in source/config.
5. Upgrade dependencies on a separate branch, compile, and run tests.
6. Run integration tests against the target broker version and active serializers/connectors.
7. Deploy to staging and observe warnings/logs/metrics before production.

Do not force a Kafka Client version newer than what Spring Kafka or Spring Boot supports without verifying compatibility. A broker may support multiple client versions, yet the application still needs a compatible dependency set on the Java side.

## 16. Testing after replacing deprecated APIs

Clean compilation only proves code matches new signatures. For messaging applications, behavior must also be verified:

| Area | Scenarios to test |
|---|---|
| Producer | Serialization, send success/failure, callbacks/futures, and retries |
| Consumer | Deserialization, listener invocation, concurrency, and shutdown |
| Offsets | AckMode, commit timing, and redelivery after errors |
| Error handler | Retry count, backoff, fatal exceptions, and recoverer |
| DLT | Destination, headers, send failures, and replay |
| Transactions | Commit/rollback and consume-transform-produce if used |
| Schema | Schema Registry, schema evolution, and legacy data |
| Configuration | Property binding, default values, and environment overrides |
| Observability | Metrics, tracing, log correlation, and alerts |

Integration tests should use a real Kafka broker or Testcontainers matching the target version. If using Schema Registry, test producer/consumer serializers too rather than only mocking `KafkaTemplate`.

## 17. Producing pre- and post-upgrade deprecation reports

Attach a report to the ticket or pull request so reviewers know which warnings were handled:

| API/property | Before status | Change | After status |
|---|---|---|---|
| Legacy error handler | Deprecated | Migrated to `DefaultErrorHandler` | Retry/DLT tested |
| Legacy Kafka property | Deprecated/renamed | Switched to new property | Startup binding PASS |
| JDK API for removal | Warning | Switched to modern Java SE API | `jdeprscan` clean |
| API in tests | Deprecated | Updated test fixtures | Test compile PASS |

After upgrading:

- Re-run compiler warnings with `-Xlint:deprecation` and `-Xlint:removal`.
- Scan JDK APIs with `jdeprscan` if upgrading the JDK.
- Inspect startup logs for deprecated or unknown properties.
- Compare the dependency tree against the approved version set.
- Record remaining warnings, reasons, and owners.

The goal does not have to be zero warnings immediately if external dependencies cannot yet be changed, but every warning must be visible, classified, and owned.

## 18. Common misconceptions

1. **Assuming deprecated means already removed.** Deprecation is a warning; the API may still work in the current version.
2. **Only grepping for `@Deprecated` in source.** Compiler warnings reveal call sites into dependencies; string-based configurations must be audited separately.
3. **Ignoring `forRemoval=true`.** This is a priority signal because the API can be dropped.
4. **Only reading the target version's release notes.** Multi-major migrations may have mandatory intermediate steps.
5. **Changing classes/methods without testing behavior.** Retry, offset, DLT, or transaction semantics may differ.
6. **Using `jdeprscan` to find Spring Kafka deprecations.** This tool focuses on Java SE APIs.
7. **Confusing `jdeps` with a deprecation scanner.** `jdeps` analyzes dependencies/modules, not compiler deprecation warnings.
8. **Overriding Kafka Client independently.** This can create a dependency set unsupported by Spring Kafka/Spring Boot.
9. **Suppressing all warnings.** Masks signals about APIs about to be removed.
10. **Forgetting YAML, environment variables, and deployment configs.** Applications may compile yet bind properties incorrectly at startup.

Checking deprecations before upgrading is a risk-management step in a Spring Kafka application's lifecycle. Combine compiler warnings, IDEs, Javadoc, release notes, migration guides, configuration checks, and tests on the exact target version. When every deprecated API has a replacement, an owner, and matching tests, upgrades become predictable and reduce hidden bugs in producers, consumers, retries, offsets, or DLTs.
