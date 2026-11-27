# Testing Native Image, AOT, and Reflection When Deployment Requires It

When deploying Spring Data JPA as a GraalVM Native Image, tests running on a standard JVM are not enough to prove the application works properly. Native Image analyzes reachable code at build time; reflection calls, classpath resources, proxies, or dynamically loaded services may require additional metadata. Spring AOT pre-generates part of the initialization code and runtime hints, yet does not automatically guarantee that every third-party library, Hibernate extension, or JDBC driver is compatible with the native runtime.

A reliable testing workflow should have three layers: functional and integration tests on the JVM against the target database, running the application with Spring AOT code on the JVM, and building and smoke-testing the actual native executable/container. Only enable native image when deployment requirements gain clear benefits in startup time, footprint, or distribution model; if an application runs normally on the JVM, do not add AOT/native complexity merely to follow a trend.

> The Java snippets below are excerpts for Java 17+ projects using Spring Boot 3+ and `spring-boot-starter-data-jpa`. They illustrate configurations and tests to integrate into a project, not standalone programs runnable directly with `javac`/`java`.

## 1. Distinguishing JVM, AOT, and Native Image

These three modes are related but test different risks:

| Mode | How it runs | What it can catch |
|---|---|---|
| Standard JVM | Bytecode runs on the JVM; Spring builds the ApplicationContext at runtime | Business logic, JPA mappings, queries, transactions, and database interactions |
| JVM with Spring AOT | Runs a JAR containing pre-generated AOT code with `spring.aot.enabled=true` | Bugs in generated Spring initialization code, bean conditions fixed at build time, and some AOT gaps |
| GraalVM Native Image | Reachable application and library code is compiled into a native executable | Reachability, reflection, resources, proxies, service loading, native runtime, and target OS environment issues |

Spring AOT analyzes the ApplicationContext at build time, generating initialization code and runtime hints. When running a native image, Spring uses that generated initialization. GraalVM further performs reachability analysis to determine which code gets included in the executable.

Therefore, running a JAR on the JVM with `spring.aot.enabled=true` is a useful check, not equivalent to running the native executable. An application can pass JVM AOT and still fail in native image due to missing reflection metadata or a library lacking native runtime support.

AOT also has an important constraint: the classpath and configuration affecting the bean graph are determined at build time. `@Profile`, `@Conditional` conditions, and properties that govern bean creation must be supplied appropriately at build time. You cannot assume changing a profile or dropping in a plugin JAR after building will make a native image discover new beans automatically.

## 2. Locking down the version matrix and target platform

Before writing tests, record the exact components that will be deployed:

| Component | Information to pin |
|---|---|
| JDK | Java version used to compile and target bytecode |
| Spring Boot | Version and dependency management |
| Spring Framework / Spring Data JPA | Actual versions managed by Boot |
| Hibernate ORM | Version of `hibernate-core` and extension modules |
| GraalVM | Distribution, version, and Native Image toolchain |
| Native Build Tools | Maven/Gradle plugin and version |
| OS / architecture | Linux, Windows, macOS; x86_64 or ARM64 |
| libc / container base | glibc or musl and base image |
| JDBC driver | Exact artifact and version |
| Database | Database engine, major/minor version, extensions, and configuration |

Do not upgrade `hibernate-core` separately outside Spring Boot's dependency management without verifying compatibility with Spring Data JPA, Jakarta Persistence, bytecode enhancement, and other Hibernate modules. Modules such as Envers, Spatial, custom dialects, cache providers, or extension libraries can have different native limitations.

For Hibernate ORM, check the documentation for the exact release. Hibernate documentation currently describes `hibernate-graalvm` as an experimental extension supporting GraalVM Native Image compilation; that does not mean every Spring Data JPA + Hibernate configuration is guaranteed native-ready. Test the exact Hibernate version, dialect, driver, and extensions used by your application. If native image is a mandatory production requirement, obtain test evidence for the full target stack before finalizing the architecture.

Do not use `latest` or floating image tags in test pipelines. Pin database image and toolchain versions so errors are reproducible. If supporting multiple version combinations, build a CI matrix covering the minimum and maximum supported combinations rather than testing only on a single developer machine.

## 3. Building a JVM test suite with a real database

Most unit tests and integration tests should still run on the JVM for a fast development loop. However, JPA tests should use the same database engine as deployment when behavior depends on dialects, data types, sequences/identity, locking, JSON, stored procedures, or vendor-specific SQL.

Testcontainers can spin up a real database in Docker. With Spring Boot 3.1+, you can use `@ServiceConnection` so Spring Boot configures the connection from the container automatically:

**Test database configuration:**

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
class TargetDatabaseConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgres() {
        // Choose an exact major/minor close to the deployment database.
        return new PostgreSQLContainer<>("postgres:16.4-alpine");
    }
}
```

Required test dependencies, with versions managed by the Spring Boot BOM:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
```

For Spring Boot older than 3.1, use `@DynamicPropertySource` to register the JDBC URL, username, and password from the container. The database tag in the example is illustrative; replace it with an actually supported database version and pin it strictly in CI.

Run production migrations on the test database. If production uses Flyway or Liquibase, do not create the schema only with `hibernate.ddl-auto=create`. Migrations are what validate schemas, indexes, constraints, sequences, defaults, and data types matching the application version.

A JPA integration test should flush and clear the persistence context before reading back, confirming that data actually round-trips through JDBC and the database:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Import(TargetDatabaseConfiguration.class)
class JpaTargetDatabaseIT {

    @Autowired
    private AuditRecordRepository repository;

    @Autowired
    private EntityManager entityManager;

    @Test
    @Transactional
    void persistsAndReloadsVendorSpecificMapping() {
        AuditRecord saved = repository.save(
                new AuditRecord(Map.of(
                        "source", "native-compatibility-test",
                        "enabled", true)));

        entityManager.flush();
        Long id = saved.getId();

        entityManager.clear();

        AuditRecord loaded = repository.findById(id).orElseThrow();

        assertThat(loaded.getPayload())
                .containsEntry("source", "native-compatibility-test")
                .containsEntry("enabled", true);
    }
}
```

The example checks the path save → SQL → database → reload. If an entity uses vendor-specific data types, the mapping must be declared for the target dialect. For example, PostgreSQL `jsonb` can use Hibernate `@JdbcTypeCode(SqlTypes.JSON)` in supported versions; when changing databases, re-verify SQL types, serializers, and corresponding JSON queries.

Do not substitute H2 for PostgreSQL/MySQL/Oracle in tests verifying native database behavior. H2 remains useful for fast tests, but it does not prove SQL and drivers work properly on the target vendor.

## 4. Testing AOT on the JVM before building native

Once you have a JAR containing AOT code, run the application on the JVM with `spring.aot.enabled=true`. With Maven using `spring-boot-starter-parent`, the native profile can generate the required AOT assets:

```bash
./mvnw -Pnative package
java -Dspring.aot.enabled=true -jar target/application.jar
```

Replace `target/application.jar` with the actual artifact name. For Gradle, apply the Spring Boot AOT plugin or GraalVM Native Image plugin according to project setup to generate AOT assets before running.

While the application runs in AOT mode, execute key smoke tests via HTTP or the service layer:

- ApplicationContext starts with the profiles and properties selected at build time.
- DataSource initializes and connects to the target database.
- EntityManagerFactory initializes, entity mappings and repository scanning succeed.
- Migrations run in the right order and schema validation passes.
- Key repository queries return accurate data.
- Transaction commit/rollback and lazy loading behave as expected.
- Components relying on reflection, proxies, or resources function properly.

AOT mode on the JVM catches generated initialization bugs early, but it does not replace running the native executable. The JVM still allows more flexible reflection and class loading than a native image.

## 5. Building and running a real native executable

Once AOT mode is stable, build the native image using Native Build Tools or Cloud Native Buildpacks.

With Maven, a project using the Spring Boot parent and native profile can run:

```bash
./mvnw -Pnative native:compile
```

If you need to create an OCI image with Buildpacks:

```bash
./mvnw -Pnative spring-boot:build-image
```

With Gradle applying `org.graalvm.buildtools.native`:

```bash
./gradlew nativeCompile
```

Native compilation requires the matching toolchain and can be time-consuming, so it may run in CI rather than on every unit test run. After building successfully, launch the exact generated executable or container, point the JDBC URL to a test/staging database, and run smoke tests against the application's real port.

Do not conclude native tests pass simply because the compile command finished successfully. A native image can build cleanly and still fail at runtime due to missing reflection hints, resources, proxies, JDBC service providers, encodings, or runtime configuration. Verify startup, health endpoints, JPA read/write operations, and connection shutdown inside the native process itself.

A native image depends on the target OS and architecture. Building on Linux x86_64 does not produce an executable that runs directly on Windows or ARM64. For container deployments, build using an environment/Buildpack matching the production platform and test the final image on the same runtime type.

## 6. Running tests inside the native image

GraalVM Native Build Tools supports running JUnit tests inside a native image. This is a deeper verification layer useful for tests that must validate reflection, proxies, and runtime behavior directly inside a native executable.

With Maven, when the project has the Spring Boot Maven plugin and Native Build Tools plugin along with the `nativeTest` profile configured:

```bash
./mvnw test -PnativeTest
```

With Gradle:

```bash
./gradlew nativeTest
```

Spring TestContext can perform AOT processing for the test context and package the JUnit TestEngine into the native test image. You can use `@SpringBootTest` or appropriate test slices. Native test builds are significantly slower than JVM tests, so teams typically select a critical subset to run on a schedule or in release pipelines.

There is no need to move all unit tests to native mode. Keep most tests running on the JVM; pick representative tests for high-risk native paths such as binding, custom converters, entity mappings, proxies, service loading, and resource loading. Also verify test infrastructure and mocking libraries, because not every test library has the same level of native support.

## 7. Testing Runtime Hints and reflection

Native Image requires metadata for operations that cannot be fully inferred from static analysis. Spring AOT automatically generates many hints for beans, proxies, and types recognized by Spring. However, application code or libraries using reflection by custom conventions may need extra hints.

Spring RuntimeHints describes requirements such as:

- Reflection to invoke constructors, methods, or access fields.
- Classpath resources loaded by name or pattern.
- Java serialization.
- JDK dynamic proxies.

If a DTO is bound via reflection and Spring cannot infer it from controller signatures or configuration, you can use `@RegisterReflectionForBinding` on an appropriate configuration/bean. For custom cases, implement `RuntimeHintsRegistrar` and register it via `@ImportRuntimeHints`.

Example registering reflection access for a legacy type invoked reflectively:

```java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class LegacyPayloadHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
                LegacyPayload.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS,
                MemberCategory.DECLARED_FIELDS);
    }
}
```

Registering the registrar:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(LegacyPayloadHints.class)
class NativeHintsConfiguration {
}
```

Only add members that are genuinely used. Do not register the entire classpath or every entity mechanically; overly broad hints bloat the image and mask libraries relying on unsuitable dynamic mechanisms. For Hibernate, follow the native-image guide of the exact Hibernate release and test in practice; do not assume registering reflection for entities alone suffices for bytecode providers, proxies, service loaders, and extensions.

You can test the registrar with RuntimeHintsPredicates before building the image:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

class LegacyPayloadHintsTests {

    @Test
    void registersReflectionForLegacyPayload() {
        RuntimeHints hints = new RuntimeHints();

        new LegacyPayloadHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.reflection()
                .onType(LegacyPayload.class))
                .accepts(hints);
    }
}
```

This test verifies that the registrar registered the type hint. It does not prove the entire native application works; you still must build and run the native image along the real code paths.

## 8. Using the tracing agent to discover missing hints

The GraalVM tracing agent can run the application or tests on the JVM and record reflection, resource, and proxy operations that actually occur. This helps find missing hints when a library or custom code uses reflection that Spring AOT did not detect.

An illustrative command when running a JAR with AOT assets:

```bash
java -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=build/native-agent-output \
  -jar target/application.jar
```

After startup, exercise the business flows to check: initializing EntityManagerFactory, persisting/finding entities, running projections, converters, custom types, lazy associations, serialization, and queries. The agent writes metadata into the output directory when the process exits.

Read and review the metadata files before placing them under `src/main/resources/META-INF/native-image/`. The agent only records code paths that were executed; unexecuted paths can still lack hints. If you run the entire test suite, the metadata may include access entries needed only by the test framework. Use the tracing agent's access-filter or filter carefully so you do not bundle unnecessary configuration.

Do not treat tracing agent output as proof of compatibility. It is a discovery tool, whereas testing the native executable is what confirms the metadata suffices for the target workload.

## 9. Spring Data JPA/Hibernate paths to test in native mode

When native image is a deployment requirement, choose tests covering behaviors where JVM and native runtime can diverge:

| Area | Behavior to verify |
|---|---|
| Entity metadata | Entity scanning, constructors, field/property access, inheritance, embeddables, and mappings |
| Repository proxies | Derived queries, JPQL, native queries, projections, specifications, and repository fragments |
| Associations | Lazy/eager loading, proxies, collection wrappers, cascades, and orphan removal |
| Type mappings | Enums, UUIDs, date/time, JSON, arrays, custom types, converters, and nulls |
| Transactions | Commit, rollback, propagation, isolation, optimistic/pessimistic locks |
| Database | JDBC driver, dialect, sequences/identity, stored procedures, generated columns, and migrations |
| Reflection | DTO binding, custom converters, method lookups, and libraries invoking reflection |
| Resources | SQL scripts, migrations, templates, message bundles, configs, and files loaded by name |
| Proxies/service loading | JDK proxies, ServiceLoader-registered providers, and bytecode providers |

For Hibernate extensions, add dedicated tests for every feature actually used, such as Envers audit revisions, Spatial types/functions, custom dialects, interceptors, event listeners, filters, or cache providers. Do not extrapolate from core repository tests passing to all extension modules.

Check generated SQL against the target database. If queries use vendor-specific syntax, confirm they execute on the exact database and driver. For native images, specifically verify that the JDBC driver is packaged, registers properly, and initializes inside the executable. A JVM repository test only validates the JDBC path on the JVM runtime.

## 10. Common errors and diagnostics

| Symptom | Possible cause | Troubleshooting direction |
|---|---|---|
| JVM tests pass but native startup fails | Generated AOT code or runtime hints are insufficient | Run JVM AOT mode, inspect the first error, and check hints |
| Native image build fails with reflection warning/error | Missing reachability metadata or library uses dynamic reflection | Use tracing agent, inspect the library, and register minimal hints |
| EntityManagerFactory fails to initialize | Hibernate, bytecode provider, dialect, or service loading incompatible with native | Verify exact Hibernate release/extension and JDBC driver; try an isolated smoke test |
| Repository proxy or lazy association fails | Missing proxy/reflection metadata or pattern not recognized by AOT | Inspect generated hints and test the exact association in native mode |
| JSON DTO fails on serialize/deserialize | Reflection binding or constructor/field access not registered | Check `@RegisterReflectionForBinding` or required RuntimeHintsRegistrar |
| SQL/config file not found | Resource loaded by name was not included in the image | Register the resource pattern and test the actual read path |
| Different beans between JVM and AOT | Profiles/conditional properties are resolved at build time | Supply exact profiles and environment at build time |
| Works on dev machine but fails in container | Different OS/arch/libc, charset, timezone, or native toolchain | Build/test in an environment close to deployment |
| Native tests fail even though native app runs | Test framework or mocking dependency lacks native support | Select suitable tests, check test dependency limits, and separate JVM vs. native tests |

Do not fix every error by adding blanket reflection hints or enabling build-time class initialization. Overly broad hints can mask problems, while wrong build-time initialization can freeze state the application expects to initialize at runtime. Pinpoint the exact code path missing metadata, check library support, and add the minimal required permissions.

## 11. Recommended testing pipeline

A pipeline can be structured into the following stages:

1. **Every commit:** run JVM unit tests and integration tests with the target database, real migrations, critical queries, and mapping tests.
2. **Pull request or main branch:** build AOT assets, run the application on the JVM with `spring.aot.enabled=true`, verify startup and critical JPA endpoints.
3. **Nightly or release candidate:** build the native executable/container on the exact target OS/architecture, run smoke tests against the target database and a representative integration test subset.
4. **Release:** verify the final image, runtime configuration, secrets, JDBC URL, health/readiness, shutdown, and database connectivity in a production-equivalent environment.

Archive artifacts from each build including the version matrix, AOT logs, native compilation logs, packaged metadata/hints, test results, and image digests. When upgrading Spring Boot, Spring Data, Hibernate, JDBC drivers, or GraalVM, re-run the test matrix; do not reuse results from an older stack to claim the new stack is compatible.

## 12. Pre-deployment checklist

- Confirmed whether native image is a genuine deployment requirement.
- Pinned versions of Spring Boot, Spring Data JPA, Hibernate ORM, GraalVM, Native Build Tools, JDBC driver, and database.
- Checked native support status for the Hibernate release and all extensions in use.
- JVM integration tests run against the target database engine and migrations.
- JAR runs with Spring AOT enabled on the JVM.
- Native executable/container builds cleanly and actually starts up.
- Native runtime connects to the database, runs repository queries, writes/reads entities, and completes transactions.
- Reflection, proxy, serialization, and resource hints are tested and scoped strictly to actual needs.
- Tracing agent was used on necessary code paths if signs of missing hints appeared.
- Native smoke tests run on the exact OS, architecture, and container base of the deployment environment.
- CI archives the version matrix, build logs, and test results for reproducibility.

Native image and AOT can improve deployment characteristics, but they make the classpath, reflection, and build-time configuration part of the runtime contract. With Spring Data JPA, verify Spring AOT, Hibernate, the JDBC driver, and the target database using integration tests and a real native executable; a single successful compile or JVM test suite is not enough to prove the full stack is ready.

## References

- [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html)
- [Spring Boot — Advanced Native Image Topics and Custom Hints](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/maven-plugin/aot.html)
- [Spring Framework — Runtime Hints and AOT](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Hibernate ORM — Getting Started and Modules](https://docs.hibernate.org/orm/7.2/quickstart/html_single/)
- [Hibernate ORM — Documentation and Version Support](https://hibernate.org/orm/documentation/)
