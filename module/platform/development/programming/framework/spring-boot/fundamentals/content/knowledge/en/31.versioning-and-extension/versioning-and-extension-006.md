# Changing Starters, Modules, Logging, or Test Tools When Upgrading Versions

Upgrading a Spring Boot version is not just changing one number in a build file. Spring Boot manages an ecosystem consisting of Spring Framework, Spring Data, Spring Security, Jackson, Hibernate, logging libraries, test frameworks, and many other dependencies. Starters pull the appropriate components onto the classpath, while dependency management selects compatible versions. When upgrading Boot, these selections can shift simultaneously.

As a result, a project may build cleanly yet still fail at runtime: a logging provider loads twice, a module is no longer discovered by auto-configuration, Hibernate changes behavior, JUnit tests are not discovered, or an older library calls a removed API. Conversely, some changes only involve renaming a starter or splitting a module without altering business behavior.

This lesson focuses on how to handle changes commonly encountered during version upgrades: **starters and dependency graphs, module structure, the logging stack, testing tools, and the migration workflow**. The goal is to help developers identify impact scope, update builds in a controlled way, and verify that the application runs cleanly on the target version.

## 1. Why Can Upgrading Spring Boot Affect Many Components?

Spring Boot provides a curated set of dependency versions tested and managed together. When a project uses the Spring Boot parent or BOM, many libraries have their versions aligned into a compatible set.

For example, a web application might use:

~~~text
Application source
       |
       v
spring-boot-starter-web
       |
       +--> Spring MVC
       +--> Embedded servlet container
       +--> JSON integration
       +--> Logging starter
       |
       v
Spring Boot dependency management
       |
       +--> Spring Framework
       +--> Jackson
       +--> Tomcat
       +--> SLF4J / Logback
       |
       v
Runtime classpath
~~~

When upgrading Boot, dependency management can update many components at once. This saves you from selecting individual versions manually, though it also means a small bump in the parent version can bring significant runtime changes.

Commonly affected areas:

- **JDK and build tools:** Java baseline, Maven/Gradle plugins, compilers, annotation processing.
- **Spring Framework:** container, web, AOP, transactions, validation, and core APIs.
- **Starters:** names, dependency contents, and module splits.
- **Persistence:** Spring Data, Hibernate, JDBC drivers, and migration tooling.
- **Serialization:** Jackson, JSON configuration, and date/time handling.
- **Logging:** SLF4J API, providers, bridges, and implementations.
- **Testing:** JUnit, Mockito, AssertJ, Spring Test, and test slices.
- **Auto-configuration:** imports metadata, condition evaluation, and ordering.
- **Third-party integrations:** security, metrics, tracing, messaging, and cloud libraries.

A safe upgrade requires knowing which groups changed and testing the behaviors that depend on those groups.

## 2. Distinguishing Versions Within a Project

Do not treat “the application's version” as a single number. A Spring Boot project involves multiple version layers:

| Component | Example | Role |
|---|---|---|
| Spring Boot | 3.x or 4.x | Platform and dependency management |
| Spring Framework | 6.x or 7.x depending on Boot | Container, web, core APIs |
| Java | 17, 21, or supported baseline | Language and runtime |
| Maven/Gradle | Wrapper version | Build engine |
| Boot build plugin | Maven/Gradle plugin | Packaging, image building, AOT |
| Logging API/provider | SLF4J, Logback, Log4j 2 | Logging |
| Test platform | JUnit Platform/Jupiter | Test discovery and execution |
| Test libraries | Mockito, AssertJ | Mocking and assertions |
| Database stack | Hibernate, driver | ORM and data connectivity |

These versions maintain compatibility relationships. For example, a Spring Boot release only supports a specific range of Java and Spring Framework versions. Never upgrade Spring Framework independently to a new major version while staying on an older Boot release if Boot's dependency management does not support that combination.

### Checking Compatibility Before Making Changes

Before upgrading, identify:

1. The current Boot version and target Boot version.
2. The Java baseline required by the target version.
3. Supported Maven/Gradle wrapper versions.
4. Whether external libraries impose specific version constraints.
5. Breaking and deprecated changes documented in release notes and migration guides.
6. Whether internal modules directly depend on Spring APIs.

Pick one concrete target version, read migration documentation for all relevant major/minor releases, and compile a change list. Do not upgrade by swapping version numbers en masse without knowing which ecosystem each number belongs to.

## 3. Dependency Management: Letting Spring Boot Pick Compatible Versions

One of Spring Boot's primary advantages is dependency management. Rather than pinning versions for every Spring library and related dependency manually, projects can use the Boot parent or BOM.

### Maven with spring-boot-starter-parent

A common configuration:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.x.y</version>
    <relativePath/>
</parent>
~~~

Managed dependencies can be declared without repeating versions:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

When bumping the parent version, the managed dependency set shifts in sync.

### Maven When You Cannot Use the Boot Parent

An organization may enforce its own corporate parent POM. In that case, import the Boot BOM inside `dependencyManagement`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

The application can still declare starters without specifying individual versions. However, importing the BOM **does not automatically pull in all plugin configurations** provided by the Boot parent. If you need executable JAR repackaging or `build-image`, configure the plugin explicitly.

### Gradle with Plugins and Dependency Management

A Kotlin DSL example:

~~~kotlin
plugins {
    id("org.springframework.boot") version "3.x.y"
    id("io.spring.dependency-management") version "1.x.y"
    java
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
}
~~~

Depending on your Gradle setup, you may combine the Spring Boot plugin with the dependency-management plugin or use Gradle's native platform/BOM support. What matters is knowing **which source manages versions** and avoiding multiple mechanisms overriding one another.

### Do Not Pin Versions Manually on Every Starter

An example to avoid unless a clear compatibility justification exists:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <version>3.a.b</version>
</dependency>
~~~

Forcing starters to mismatched versions can pull in Spring modules from incompatible release trains. Let the BOM manage versions unless an override is intentionally evaluated and tested.

## 4. What Is a Starter and Why Can Starter Names Change?

Starters are Spring Boot convenience dependency descriptors. They group libraries commonly used together so developers do not have to curate every underlying dependency manually.

Examples:

- `spring-boot-starter-web` for Servlet/Web MVC applications.
- `spring-boot-starter-data-jpa` for JPA and persistence integration.
- `spring-boot-starter-security` for Spring Security.
- `spring-boot-starter-validation` for Bean Validation integration.
- `spring-boot-starter-test` for the standard testing stack.

A starter is rarely the direct implementation of a feature itself. It serves as an entry point into the dependency graph.

### One Starter Can Pull in Many Libraries

~~~text
spring-boot-starter-data-jpa
          |
          +--> Spring Data JPA
          +--> Spring ORM / transaction integration
          +--> Hibernate ORM
          +--> JDBC-related infrastructure
          +--> Logging dependencies
~~~

The exact dependency graph depends on the Boot version. When starter contents shift or modules split, the runtime classpath can change even if the dependency line in your POM stays identical.

### Do Not Add a Starter Just Because Its Name Sounds Useful

If an app only uses `JdbcTemplate`, it may not need the JPA starter. If it only exposes REST APIs without server-side HTML rendering, it does not need a template engine starter. Unused starters bloat dependency counts, widen scan surfaces, and can activate unwanted auto-configurations.

Select starters matching the capabilities actually used, rather than copying another tutorial's starter list.

## 5. Starter Changes When Upgrading Versions

When upgrading Boot, some starters may be renamed, change contents, or split into standalone starters. Workflow to handle this:

1. Identify current dependencies.
2. Read the migration guide and release notes for the target version.
3. Check for new replacement artifacts or split modules.
4. Update dependency declarations.
5. Review whether older exclusions are still needed.
6. Re-inspect which auto-configurations are activated.
7. Build and verify the runtime classpath.

### Example: Splitting a Capability Out of a Larger Starter

Suppose a platform release extracts an integration into its own starter. Previously the project had:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

After migrating, the extracted capability may require declaring an explicit starter/module per the target release guide:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-example-integration</artifactId>
</dependency>
~~~

The artifact name here is a conceptual placeholder showing module extraction, not a real dependency to copy. Use the exact artifact published for the release you target.

### Remove Legacy Dependencies Only After Inspecting the Graph

A library may still be pulled transitively by another starter. Deleting one direct dependency does not guarantee the class disappears from the runtime classpath. Conversely, adding a new starter may pull in a competing implementation.

Use the dependency tree to verify the effective graph instead of trusting build-file declarations alone.

## 6. Dependency Exclusions and Swapping Default Implementations

Occasionally an application replaces a default implementation—for example, switching from Logback to Log4j 2 or swapping HTTP clients.

Maven exclusion:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

This example excludes the default logging starter coming through the web starter. If other starters still pull in the logging starter, a single exclusion on one dependency may not remove it from the graph.

One clean strategy is placing exclusions consistently across dependency declarations or applying deliberate dependency management/constraints, then adding the replacement implementation explicitly.

### Exclusions Can Cause Runtime Failures

If you exclude a library still required by your code or another starter, the application may throw:

- `ClassNotFoundException`.
- `NoClassDefFoundError`.
- `NoSuchMethodError`.
- Auto-configuration bean creation failures.
- Logging system initialization failures.

Never add exclusions merely to shrink the dependency tree output. Every exclusion must have a clear reason and be verified through build, tests, and runtime.

## 7. Module Changes and Boundaries Between Applications and Libraries

A multi-module Spring Boot system might be structured as:

~~~text
store-platform/
├── store-domain/
├── store-application/
├── store-persistence/
├── store-web/
├── store-observability/
└── store-service/
~~~

Design intent:

- `store-domain` holds models and business rules with minimal framework coupling.
- `store-application` holds use cases and orchestration.
- `store-persistence` implements repository/database integrations.
- `store-web` holds controllers and HTTP adapters.
- `store-observability` holds metrics, logging, and tracing integrations.
- `store-service` boots the application and wires final configuration.

Not every project warrants splitting into many modules. Every module introduces a separate dependency and build boundary, so splits should be justified by maintenance, reuse, or ownership needs.

### Library Modules Are Not Necessarily Spring Boot Applications

A shared internal module can remain a plain Java library:

~~~xml
<packaging>jar</packaging>
~~~

It does not need the Boot repackage plugin or a main class. Applying the Spring Boot executable plugin blindly across every module can produce unusable artifacts or complicate downstream builds.

Only deployable application modules need executable packaging unless a library module has special build requirements.

### Avoid Circular Dependencies Across Modules

A clean structure enforces a clear dependency direction:

~~~text
store-service
   |
   +--> store-web
   +--> store-persistence
   +--> store-application
              |
              v
         store-domain
~~~

If the domain module depends back on web or persistence implementations, upgrading modules or swapping starters becomes painful. Define interfaces at appropriate boundaries so implementations depend inward on abstractions.

## 8. Spring Boot Auto-Configuration in Internal Modules

An internal module can provide auto-configuration so consuming applications receive default beans simply by adding the dependency.

Example:

~~~java
@AutoConfiguration
public class AuditModuleAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditSink.class)
    AuditSink auditSink() {
        return new ConsoleAuditSink();
    }
}
~~~

In modern Spring Boot generations, auto-configuration imports are typically listed in:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The file lists fully qualified auto-configuration class names, one per line:

~~~text
com.example.audit.AuditModuleAutoConfiguration
~~~

When upgrading Boot in an internal module, check:

- Whether auto-configuration annotations remain appropriate.
- Whether imports metadata paths and formats match.
- Whether ordering and before/after constraints hold.
- Whether condition classes and optional dependencies are compatible.
- Whether tests load auto-configuration via the real discovery mechanism.

### Why Direct Class Tests Are Insufficient

A test like:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(
                        AuditModuleAutoConfiguration.class
                )
        )
        .run(context -> {
            assertThat(context).hasSingleBean(AuditSink.class);
        });
~~~

proves the class works when loaded explicitly. It **does not prove imports metadata was packaged properly inside the JAR**.

Supplement this with discovery/packaging checks or integration tests consuming the module as an actual dependency.

### Avoid Turning Auto-Configuration into Broad Component Scanning

A library module should not force host applications to scan its entire package tree just to discover one bean. Using auto-configuration imports and conditions keeps integration boundaries crisp while letting consuming apps override default beans cleanly.

## 9. Reviewing Packages and Public APIs When Upgrading Modules

A major Spring Framework version shift can change packages, method signatures, and annotations. A prominent example from Spring Boot 2 to Spring Boot 3 is the Jakarta ecosystem transition.

Legacy `javax.*` imports for APIs moved to Jakarta EE must switch to matching `jakarta.*` packages. Common example:

~~~java
// Before migration in the legacy Java EE ecosystem:
import javax.persistence.Entity;

// After migration to Jakarta Persistence:
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class OrderEntity {

    @Id
    private Long id;
}
~~~

Similarly, Servlet, Bean Validation, and common annotation APIs moved to matching Jakarta packages.

### Not Every javax Package Moved to jakarta

Several Java SE packages retained `javax`, such as `javax.crypto` or `javax.sql`. Never run a global find-and-replace from `javax.` to `jakarta.`.

Migrate only APIs belonging to the Jakarta EE namespace shift, guided by compiler diagnostics and migration guides.

### Check Generated Code and Annotation Processing

Lombok, MapStruct, QueryDSL, and other annotation processors can depend on compiler, JDK, or framework internals. When upgrading Java or Spring, inspect:

- Annotation processor versions.
- Compiler plugin configurations.
- Generated source directories.
- Jakarta annotation and type imports.
- Multi-module build ordering.
- IDE annotation processing settings.

A module may compile locally in the IDE yet fail in CI if processor paths diverge.

## 10. Major Spring Boot Upgrades: Java and Framework Baselines

Major upgrades carry more extensive shifts than minor or patch bumps.

For instance, migrating from Boot 2 to Boot 3 entails Spring Framework 6, a Java 17 baseline, and Jakarta namespaces across enterprise APIs. Upgrading means updating source code, dependencies, and runtime images alongside the parent version.

A migration checklist:

- Ensure compile and runtime JDKs satisfy the baseline.
- Upgrade Maven/Gradle wrappers and required build plugins.
- Migrate Java EE package imports to Jakarta for moved APIs.
- Review Spring Security configuration.
- Review Hibernate/JPA behavior and dialects.
- Check the Bean Validation provider.
- Check Servlet container and web APIs.
- Verify third-party libraries support the target framework line.
- Check deprecated or renamed properties.
- Execute tests on the target JDK and runtime image.

### Avoid Blindly Upgrading JDK and Boot Together

If a project runs on an older JDK, bumping the JDK itself can surface compiler or runtime issues distinct from framework migration issues. Proceed in controlled steps:

1. Identify the target JDK required by the Boot version.
2. Update toolchain and wrapper config so the project compiles on that JDK.
3. Run baseline tests before changing framework versions when possible.
4. Upgrade Spring Boot and resolve migration errors.
5. Optimize compiler flags and runtime tuning once behavior stabilizes.

Some migrations require stepping multiple pieces together, yet keeping commits focused makes root-cause analysis far easier.

## 11. Logging Changes: Understanding API, Bridge, and Implementation Layers

Java logging usually spans three distinct layers:

1. **Logging API/facade:** what application code calls, such as SLF4J.
2. **Implementation/provider:** what actually formats and writes logs, such as Logback or Log4j 2.
3. **Bridge:** adapts calls from another logging API into the active facade or provider.

Diagram:

~~~text
Application code
       |
       v
SLF4J API
       |
       v
SLF4J provider
       |
       +--> Logback
       |
       +--> Log4j 2 provider
       |
       +--> Other provider
~~~

Other libraries may emit logs via JUL, Commons Logging, or Log4j APIs. Bridges funnel those calls into one unified logging backend.

### Why Does Logging Frequently Break After Upgrades?

- SLF4J API moved to a new major version while an older provider remains incompatible.
- Two providers sit on the runtime classpath simultaneously.
- A bridge and implementation form a forwarding cycle.
- The default logging starter stayed on the classpath even after adding Log4j 2.
- A dependency pulled an incompatible SLF4J version transitively.
- Test runtime classpath differs from application runtime classpath.

Symptoms include missing-provider warnings, multiple-binding/provider warnings, silent missing logs, duplicated log lines, or startup failures during logging initialization.

## 12. SLF4J 1.7 vs. SLF4J 2.x: Bindings and Providers

In SLF4J 1.7 and earlier, implementations were discovered via static binding classes such as:

~~~text
StaticLoggerBinder
~~~

In SLF4J 2.x, discovery moved to the standard `ServiceLoader` provider mechanism:

~~~text
org.slf4j.spi.SLF4JServiceProvider
~~~

Consequently, upgrading the SLF4J API requires upgrading compatible implementations and providers. Legacy bindings do not magically become 2.x providers.

### Do Not Override slf4j-api Independently

When Spring Boot's BOM already manages SLF4J, pinning a different `slf4j-api` version solely for one third-party library can break runtime alignment. Check which version Boot's target release train provides and which versions the library supports first.

If an override is genuinely unavoidable, verify every provider, bridge, and logging module aligns with the chosen API version.

## 13. Keeping Default Logback vs. Switching to Log4j 2

Spring Boot includes a default logging starter centered on Logback. Without special requirements, keeping the default entails the least upgrade churn.

If organizational standards mandate Log4j 2 or specific Log4j features are required, swap the implementation per Boot documentation.

Illustrative Maven snippet:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-log4j2</artifactId>
</dependency>
~~~

In web applications, the default logging starter can arrive transitively through multiple starters. Exclusions must cover the actual dependency graph per your build configuration; this example illustrates swapping out the default logging starter.

### Do Not Add Log4j 2 While Leaving Logback Active

If both Logback and Log4j 2 providers exist on the classpath, SLF4J detects multiple implementations. Inspect the runtime dependency tree and exclude the unwanted backend completely.

### Log4j 2 API and Provider Are Different Artifacts

An application may contain:

- `log4j-api`: API called by application or library code.
- `log4j-core`: Log4j 2 backend implementation.
- `log4j-slf4j2-impl`: SLF4J 2.x provider routing to Log4j 2.
- Dedicated bridges for JUL, Commons Logging, or Log4j 1 APIs.

Do not add every Log4j artifact simply because the name contains "Log4j". Select exact providers and bridges matching your logging architecture.

## 14. Logging Bridges: Avoiding Cycles

Bridges consolidate legacy logging API calls into one backend, yet mispairing them creates infinite loops.

Example chain to avoid:

~~~text
SLF4J
  |
  v
JUL bridge
  |
  v
JUL
  |
  v
SLF4J bridge
  |
  +---- back to SLF4J
~~~

Bridges exist to route logs strictly in one direction. Putting opposing directional bridges onto the same classpath can cause infinite recursion or runtime errors.

### Verification Checklist

- Choose one primary logging facade for application code.
- Choose one primary implementation/provider.
- Add only the bridges needed for third-party libraries calling other APIs.
- Never include a reverse bridge contradicting an existing bridge.
- Inspect transitive logging dependencies across starters.
- Run a startup check confirming each log event prints once.

### Missing Logs After Upgrading

If the application starts without emitting expected logs:

1. Check provider/binding compatibility against the SLF4J API version.
2. Verify the provider actually sits on the runtime classpath.
3. Check which logging configuration file was loaded.
4. Check logger levels, filters, and appenders.
5. Verify where output writes (stdout, file, or external collector).
6. Confirm bridges route strictly in the intended direction.

Do not change levels to `TRACE` until verifying that a working provider initialized properly.

## 15. Logging Configuration Files Can Change Too

Projects commonly contain files such as:

~~~text
logback-spring.xml
logback.xml
log4j2-spring.xml
log4j2.xml
~~~

Switching logging backends does not convert existing configuration files automatically. Appenders, encoders, rolling policies, and property syntax differ between Logback and Log4j 2.

When migrating from Logback to Log4j 2:

- Swap the logging dependency/provider.
- Rewrite appender and rolling configuration.
- Verify profile-specific logging rules.
- Check environment property expansion syntax.
- Check async logging behavior and clean shutdown flush.
- Verify exception stack traces and MDC/context rendering.
- Verify test output and CI log capture.

### MDC and Structured Logging

SLF4J MDC commonly attaches request IDs, trace IDs, or user-safe correlation metadata to log entries. When upgrading backends or bridges, confirm MDC keys propagate across threads/executors and render accurately.

Never put passwords, tokens, or sensitive PII into MDC. A logging migration is an ideal time to audit log data hygiene alongside XML syntax.

## 16. Changing Logging Starters in a Rollback-Friendly Way

Avoid upgrading Boot, swapping providers, changing output to JSON, and rewriting logging policies inside one huge change unless truly required.

A clear sequence:

1. Upgrade Boot with the default logging implementation first if possible.
2. Confirm clean startup and basic log output.
3. If switching backends, open a separate isolated change.
4. Exclude the default logging starter.
5. Add the compatible replacement provider.
6. Migrate the configuration file.
7. Inspect bridges and the dependency graph.
8. Run integration tests and verify real log output.
9. Update operational docs and container log collectors.

If something breaks after step 4, the investigation scope is dramatically narrower than when changing everything simultaneously.

## 17. What Does the Test Starter Contain?

`spring-boot-starter-test` is a convenience starter for test scope. It typically brings together:

- Spring Boot Test and Spring Test.
- JUnit Jupiter.
- AssertJ.
- Hamcrest.
- Mockito.
- JSON test utilities and supporting libraries per release version.

The exact transitive list shifts across Spring Boot releases. Do not assume two major versions of `spring-boot-starter-test` yield identical graphs.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

### Keep the Test Starter Out of Runtime Scope

Test libraries belong strictly in `test` scope/configuration. Adding the test starter to main runtime dependencies ships JUnit, Mockito, and testing helpers inside production deployable artifacts.

Verify dependency scopes after every migration, especially when converting between Maven and Gradle or refactoring multi-module layouts.

## 18. JUnit 4 and JUnit 5/Jupiter

A common migration is moving from JUnit 4 to JUnit Jupiter.

JUnit 4:

~~~java
import org.junit.Test;
import org.junit.runner.RunWith;
import org.springframework.test.context.junit4.SpringRunner;

@RunWith(SpringRunner.class)
public class OrderServiceTest {

    @Test
    public void createsOrder() {
        // ...
    }
}
~~~

JUnit Jupiter:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.test.context.junit.jupiter.SpringExtension;

@ExtendWith(SpringExtension.class)
class OrderServiceTest {

    @Test
    void createsOrder() {
        // ...
    }
}
~~~

With `@SpringBootTest`, Spring Boot's test annotation includes the matching extension automatically, so declaring `@ExtendWith(SpringExtension.class)` explicitly is not always required.

### Common Annotation Changes

| JUnit 4 | JUnit Jupiter |
|---|---|
| `org.junit.Test` | `org.junit.jupiter.api.Test` |
| `@Before` | `@BeforeEach` |
| `@After` | `@AfterEach` |
| `@BeforeClass` | `@BeforeAll` |
| `@AfterClass` | `@AfterAll` |
| `@Ignore` | `@Disabled` |
| `@RunWith` | Extension model via `@ExtendWith` |
| `@Rule` / `@ClassRule` | Extension APIs or appropriate test lifecycle hooks |
| `Assert.assertEquals` | JUnit Jupiter `Assertions` or AssertJ |

JUnit Jupiter does not use JUnit 4's runner model by default. If legacy tests still rely on JUnit 4, decide whether to migrate them or temporarily retain the Vintage engine if your dependency stack supports it.

### Tests Not Discovered

A test class may compile cleanly yet silently not run if:

- `org.junit.Test` is mistakenly imported while only the Jupiter engine is present.
- Maven Surefire or Gradle test tasks lack JUnit Platform configuration.
- Test classes or methods break engine discovery rules.
- The test engine dependency is missing.
- CI uses a wrapper or build config differing from local settings.

Inspect discovered test counts explicitly, not merely build exit codes.

## 19. Mockito and Spring Test Annotations

Mockito creates mocks for dependencies in unit tests:

~~~java
@ExtendWith(MockitoExtension.class)
class InvoiceServiceTest {

    @Mock
    InvoiceRepository repository;

    @InjectMocks
    InvoiceService service;

    @Test
    void loadsInvoice() {
        // ...
    }
}
~~~

This is a plain Mockito unit test without a Spring context.

In Spring integration tests, you may need to replace a bean inside the context with a mock. Annotations supporting this have evolved across Spring Boot and Spring Framework generations. Newer Spring Boot releases introduced replacement APIs for older mock-bean annotations and deprecated the legacy ones.

### Do Not Swap Annotations Blindly Just Because the IDE Suggests It

Before migrating:

1. Identify your exact Spring Boot and Spring Test versions.
2. Verify whether the current annotation is still supported or deprecated.
3. Confirm whether the replacement API exists in your target version.
4. Read mock/spy, bean override, and reset semantics carefully.
5. Rerun context tests.

For example, in versions supporting `@MockitoBean`, you can override a bean in the test context:

~~~java
@SpringBootTest
class CheckoutIntegrationTest {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Test
    void usesConfiguredPaymentGateway() {
        // ...
    }
}
~~~

This example targets versions containing that API. If your target version lacks this annotation, use the API supported by your version; do not copy annotations from documentation of a newer release.

### Mock in Unit Tests vs. Mock in Spring Context Tests Differ

- `@Mock` creates a standalone Mockito mock object.
- `@InjectMocks` instantiates the test target and injects mocks per Mockito rules.
- Bean override annotations replace beans inside a Spring Test context.
- `@MockBean`/`@MockitoBean` carry semantics tied to Spring contexts and the test framework.

Do not convert every `@Mock` into `@MockitoBean`. Doing so can turn fast unit tests into slow context tests.

## 20. AssertJ and assertion APIs

The test starter typically brings AssertJ onto the test classpath. Example:

~~~java
@Test
void calculatesTotal() {
    BigDecimal total = calculator.total(
            new BigDecimal("10.00"),
            new BigDecimal("5.00")
    );

    assertThat(total).isEqualByComparingTo("15.00");
}
~~~

AssertJ provides fluent assertions that express expectations clearly.

When upgrading the test stack, you may encounter API changes, generic inference updates, or overload resolution differences. When that happens:

- Read the full compiler error.
- Check static imports.
- Check method overloads in the new version.
- Avoid replacing typed assertions with string comparisons just to compile.
- Preserve assertion semantics, especially for `BigDecimal`, collections, and exceptions.

For example, `BigDecimal.equals` distinguishes scale, whereas `compareTo` compares numeric value. Choose assertions matching the contract.

## 21. Spring test slices and starter changes

Spring Boot provides test slices to initialize only the relevant subset of an application.

Examples:

- `@WebMvcTest` for the MVC controller/web layer.
- `@DataJpaTest` for the JPA/persistence slice.
- `@JsonTest` for JSON serialization.
- `@RestClientTest` for REST client test scenarios.
- `@WebFluxTest` for the reactive web layer.

When upgrading Boot, test slices may change which auto-configurations are imported or how mock beans are registered. A previously passing test can fail because:

- A bean is no longer part of the slice.
- A dependency moved into a separate module.
- Auto-configuration conditions changed.
- The security filter chain is configured differently.
- Jackson/module registration changed.
- A test annotation was deprecated or changed semantics.

### Example @WebMvcTest

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void returnsOrder() throws Exception {
        // Arrange mock and execute request.
    }
}
~~~

Using `@MockitoBean` applies only to Spring Test versions providing that API. The goal of a slice is testing the MVC layer without booting a real database and the full service graph.

### When a test slice fails after an upgrade

Do not immediately convert it to `@SpringBootTest`. First inspect which slice is loading, which beans were excluded, which auto-configurations changed, and which dependencies need mocking. Broaden the context only if the test question genuinely requires wider scope.

## 22. Test runtime and build plugins

A test framework may exist on the classpath yet fail to be discovered or executed by the build tool.

### Maven

Check:

- Whether Maven Surefire Plugin version is managed by the Boot parent or overridden.
- Whether the JUnit Platform provider matches.
- Test source naming conventions.
- `test` scope of dependencies.
- Whether build profiles accidentally skip tests.
- Whether Failsafe is used for integration tests.

A common command:

~~~bash
mvn test
~~~

To see full test execution details:

~~~bash
mvn -DtrimStackTrace=false test
~~~

Customize plugin versions only when required. If using the Boot parent, try the managed plugin version first.

### Gradle

With Gradle:

~~~kotlin
tasks.test {
    useJUnitPlatform()
}
~~~

Then:

~~~bash
./gradlew test
~~~

Check:

- JUnit Platform is enabled.
- Test source sets live in the right module.
- Dependencies use `testImplementation`.
- The engine is on test runtime.
- Filters/tags are not excluding all tests.
- The Gradle wrapper is compatible with the JDK and Boot plugin.

### Compiling tests does not mean tests ran

A pipeline can compile test sources yet discover zero tests. CI should report the executed test count and fail on unexpected drops using mechanisms matching the project workflow.

## 23. Testcontainers and integration dependencies

If a project uses Testcontainers for PostgreSQL, Kafka, or Redis, upgrading Boot can impact:

- Java baseline.
- JUnit integration module.
- Container image versions.
- Docker/Testcontainers APIs.
- Database drivers.
- Spring Boot service connection support on corresponding versions.

Gradle example:

~~~kotlin
dependencies {
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
}
~~~

Testcontainers versions can be managed via a dedicated BOM or compatible dependency management. Do not upgrade a single Testcontainers module while ignoring related modules.

### ServiceConnection and dynamic properties

Some Spring Boot versions support `@ServiceConnection` for Testcontainers. Older versions typically use `@DynamicPropertySource` or another property injection mechanism.

Example using supported APIs:

~~~java
@Testcontainers
@SpringBootTest
class RepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");
}
~~~

This example is version-dependent. If your Boot version does not yet support that annotation or container type, configure test properties using the mechanism supported by that release.

### Do not upgrade database images without checking compatibility

The Testcontainers image version is part of the test environment. A newer PostgreSQL major version can alter behavior or migration assumptions. Keep test database versions aligned with deployment environments or test migrations intentionally.

## 24. Test modules in multi-module projects

In multi-module Maven builds, a library module may need test dependencies without pulling starter test into runtime:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

In Gradle:

~~~kotlin
dependencies {
    testImplementation(
        "org.springframework.boot:spring-boot-starter-test"
    )
}
~~~

If an application module depends on a library module, the library module's test libraries must not leak into the application runtime.

### Use test fixtures intentionally

If multiple modules share test helpers, use Gradle's test-fixtures feature or a separate test utility module. Do not put test helpers into the main source set just so other modules can import them.

This prevents test-only implementations from being packaged into production artifacts.

### Verify the module graph after migration

- Which module is the executable application?
- Which modules are libraries only?
- Where is the Boot plugin applied?
- Is dependency management consistent?
- Are test dependencies exported transitively?
- Are generated sources built in the right order?
- Which module JAR holds auto-configuration metadata?

## 25. Dependency tree: an essential tool when upgrading versions

After changing starters or modules, inspect the actual dependency graph.

### Maven

~~~bash
mvn dependency:tree
~~~

Filter for one library:

~~~bash
mvn dependency:tree -Dincludes=org.slf4j
~~~

Inspect dependency conflicts and selected versions, then find which module pulls each dependency in.

### Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Inspect a specific dependency:

~~~bash
./gradlew dependencyInsight \
  --dependency slf4j-api \
  --configuration runtimeClasspath
~~~

For tests:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
~~~

### Runtime and test classpaths can differ

An error occurring only during tests may stem from the test runtime graph rather than application runtime. Conversely, tests may pass because test scope provides an implementation absent from the production artifact.

Therefore, inspect the right configuration:

- Maven compile/runtime/test scopes.
- Gradle `compileClasspath`/`runtimeClasspath`/`testRuntimeClasspath`.
- Annotation processor path.
- Plugin classpath if errors occur inside build plugins.

### Finding duplicate implementations

For logging, check:

- SLF4J API version.
- Provider/binding.
- Logback.
- Log4j 2 provider.
- JUL/Commons Logging bridges.
- Dependencies pulling implementations transitively.

Do not merely count artifacts with "logging" in their names; identify each artifact's role in the graph.

## 26. Version conflicts and dependency convergence

One module may require library version A while another requires version B. Dependency management selects a version per the build tool's rules, which can cause a runtime mismatch.

Example:

~~~text
Application
   |
   +--> Starter A --> library-core 2.x
   |
   +--> Module B --> library-core 3.x
   |
   v
Resolved version
~~~

If code compiles against the newer API while runtime resolves the older version, `NoSuchMethodError` or `NoClassDefFoundError` can occur.

### How to resolve

1. Identify the conflicting dependency.
2. Locate direct/transitive modules introducing each version.
3. Check whether the Boot BOM manages that artifact.
4. Determine which library version is compatible with the target Boot release.
5. Upgrade related modules along a compatible release train.
6. Override a version only with justification.
7. Run tests and verify the runtime classpath.

### Do not use force versions to suppress every conflict

Forcing all modules to the highest version may let the build pass while runtime fails due to API incompatibility. Dependency convergence is an investigation signal, not a goal to reach at any cost.

## 27. Configuration property changes and deprecated settings

Upgrading versions can deprecate, rename, or change the semantics of properties. An old property may keep working during a transition period and be removed in a subsequent major release.

General example:

~~~yaml
spring:
  feature:
    old-option: true
~~~

When release notes indicate a new property:

- Replace the key with the new property.
- Verify values/defaults are equivalent.
- Check profile-specific files.
- Check environment variables mapping to the new property.
- Remove the old key once confirmed no consumer remains.
- Update deployment manifests and Helm values.

Do not guess a new property name simply by renaming keys; semantics may have changed as well.

### Configuration metadata

IDE autocomplete reads metadata from dependencies. After upgrading starters, updated metadata flags deprecated or removed properties. However, metadata does not always cover custom properties and environment overrides.

Use release notes, generated configuration metadata, and startup warnings together.

## 28. Security configuration when upgrading Spring Security

A Boot upgrade may bring a newer Spring Security version. Older configurations may be deprecated or fail to compile.

Modern configurations typically use a `SecurityFilterChain` bean:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http
    ) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/actuator/health").permitAll()
                        .anyRequest().authenticated()
                )
                .build();
    }
}
~~~

This is an illustrative skeleton. A real application also requires appropriate authentication mechanisms, CSRF policies, CORS, session strategies, OAuth2/resource server setup, and endpoint rules.

### Do not fix compile errors by setting permitAll everywhere

If a method API changed, deleting rules or widening access just to compile alters security behavior. Rewrite rules equivalently under the new semantics and verify with security tests.

### Security tests after an upgrade

- Anonymous requests to protected endpoints.
- Authenticated requests with valid roles.
- Users lacking permissions.
- CSRF behavior for state-changing requests.
- CORS/preflight if browser clients exist.
- OAuth2 token validation if using a resource server.
- Actuator endpoint exposure and authorization.

## 29. Persistence modules and Hibernate upgrades

Spring Boot manages compatible Spring Data and Hibernate versions. Upgrading can advance the ORM major version and change:

- SQL generation.
- Type mapping.
- Dialect handling.
- Lazy loading/proxy behavior.
- Schema validation.
- Query parsing.
- Identifier generation.
- Transaction semantics or API deprecations.

### Example: query behavior must be tested

A repository method may compile yet generate different SQL or an invalid query. Therefore, run integration tests against an appropriate database rather than relying solely on unit tests around repository interfaces.

### Checking schema migrations

If using Flyway or Liquibase:

- Upgrade plugin/runtime library versions for compatibility.
- Check the database driver.
- Run migrations from a production-like schema snapshot.
- Confirm Hibernate `ddl-auto` does not unintentionally alter the schema.
- Check rollback/forward-only policies.
- Confirm migrations run once safely across multi-instance deployments.

Do not run migration tests only against an in-memory database if production uses a database engine with different semantics.

## 30. JSON serialization and Jackson modules

The web starter typically pulls in Jackson for JSON. When versions change, check:

- Date/time serialization.
- Enum handling.
- Null/missing properties.
- Polymorphic typing.
- Constructor/record deserialization.
- Custom serializers/deserializers.
- Java Time module.
- Naming strategies.
- Unknown property handling.

A JSON test:

~~~java
@JsonTest
class OrderJsonTests {

    @Autowired
    JacksonTester<OrderResponse> json;

    @Test
    void serializesOrder() throws Exception {
        OrderResponse response =
                new OrderResponse("order-1", "PAID");

        assertThat(json.write(response))
                .extractingJsonPathStringValue("$.status")
                .isEqualTo("PAID");
    }
}
~~~

JSON test slice APIs and auto-configuration must match the Boot version. After upgrading, run contract tests on important payloads to catch wire format changes.

### Do not inspect only Java objects

An application might serialize/deserialize Java objects cleanly in unit tests while the API contract changes in property names, date formats, or null handling. Verify the actual JSON consumed by clients.

## 31. Observability starters: metrics, tracing, and logging

Some systems use Micrometer, tracing bridges, OpenTelemetry, or Actuator. Upgrading Boot can change versions or integration modules.

Check:

- Selected meter registry.
- Tracing bridge and exporter.
- Observation conventions.
- Propagation formats.
- Correlation IDs.
- Actuator endpoint exposure.
- Health contributors.
- Log correlation/MDC.

In particular, avoid putting two tracing bridges with the same role on the classpath if they produce duplicate instrumentation.

### Metric names/tags can be operational contracts

Dashboards, alerts, and SLOs may depend on metric names/tags. A library upgrade can alter naming conventions or histogram configurations. Verify dashboards and alert queries alongside code.

## 32. Maven/Gradle plugins must also upgrade compatibly

Spring Boot build plugins can handle:

- Repackaging executable JAR/WAR files.
- Building OCI images.
- AOT processing.
- Native image workflows.
- Build metadata and layered archives.

When upgrading Boot, keep the plugin on the same release train unless there is a specific reason to pin a different version.

### Maven plugin

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

When using the Boot parent, the plugin version is usually managed. When only importing the BOM, the plugin version may need to be declared explicitly.

### Gradle plugin

~~~kotlin
plugins {
    id("org.springframework.boot") version "3.x.y"
    id("io.spring.dependency-management") version "1.x.y"
    java
}
~~~

Do not copy plugin versions from tutorials without confirming compatibility with your Gradle wrapper, Java, and Boot versions.

### The wrapper is part of the build

Commit the Maven Wrapper or Gradle Wrapper so developers and CI use the same build engine version. Upgrading the JDK without updating the wrapper can cause build failures unrelated to Spring code.

## 33. A step-by-step controlled upgrade workflow

A controlled process:

~~~text
1. Record baseline
       |
       v
2. Choose target Boot/JDK/build tool
       |
       v
3. Read migration guide and release notes
       |
       v
4. Upgrade parent/BOM/plugin
       |
       v
5. Resolve starters and dependency graph
       |
       v
6. Fix source/module/API migrations
       |
       v
7. Lock down logging provider/bridges
       |
       v
8. Upgrade and fix test tooling
       |
       v
9. Run layered tests
       |
       v
10. Smoke test artifact/runtime
       |
       v
11. Update CI and deployment
       |
       v
12. Release with rollback plan
~~~

### Step 1: record the baseline

Before editing, save:

- Current build/test results.
- Dependency tree.
- Java version.
- Maven/Gradle wrapper version.
- Startup logs.
- Logging backend.
- Discovered test count.
- Artifact size and startup behavior if relevant.

The baseline identifies which failures already existed before the upgrade.

### Step 2: choose an explicit target

Avoid vague version ranges. Pick a concrete release and verify JDK/build tool support.

### Step 3: read the migration guide

Focus on breaking changes relevant to the project's actual dependencies. You do not need to apply guidance for modules the project does not use.

### Step 4: update the Boot version

Update the parent/BOM/plugin version in the central management file. In multi-module projects, avoid declaring different Boot versions per module.

### Step 5: build to surface compile errors

Compile errors typically highlight changed APIs/packages. Address them by group rather than suppressing warnings or removing dependencies indiscriminately.

### Step 6: run tests and verify runtime

A passing build proves only compilation/packaging. Testing startup, logging, persistence, web, and external integrations verifies actual behavior.

## 34. Strategy for upgrading across multiple major releases

If a project spans multiple major versions, it is usually easier to control when stepping sequentially through supported migration milestones rather than jumping across multiple release trains without checking intermediate changes.

General flow:

~~~text
Current release
      |
      v
Intermediate supported release
      |
      v
Target major release
      |
      v
Resolve migration warnings/errors
      |
      v
Final validation
~~~

Not every project must install and deploy every intermediate release. However, read migration notes across relevant milestones so you do not miss a property, package, or plugin change removed by the final version.

### Do not keep compatibility hacks permanently

During a transition period, temporary adapters or bridges may be needed. Document why they exist and when to remove them, avoiding an indefinite mix of old and new APIs.

## 35. Post-upgrade test matrix

A minimal test matrix may include:

| Layer | What to verify |
|---|---|
| Compile | Sources and annotation processing are compatible |
| Unit tests | Business logic unchanged |
| Context tests | Bean wiring, conditions, lifecycle |
| Web slice | Controllers, serialization, security |
| Persistence slice | JPA mappings, repositories, transactions |
| Logging | Single provider, accurate output and levels |
| Integration tests | DB, broker, external clients |
| Packaging | Executable JAR/WAR and manifest |
| Container smoke | Image starts, ports, health, signals |
| CI | Test discovery, reports, artifact publication |

Not every commit must run the full matrix. However, before releasing the target version, gather evidence covering all active integrations.

### Test count is an important signal

After upgrading JUnit/Surefire/Gradle, compare the discovered test count against your baseline. If 800 tests used to run and after the upgrade only 0 or 120 run, the build may still exit 0 depending on configuration while leaving the suite largely unexecuted.

Inspect reports and build logs rather than looking only at `BUILD SUCCESSFUL`.

## 36. Troubleshooting: new starter causes missing beans

Symptom:

~~~text
No qualifying bean of type 'ExampleClient' available
~~~

Possibilities:

- The starter providing the bean changed artifacts.
- Auto-configuration is no longer imported.
- An optional dependency is missing from the classpath.
- A property condition failed to match.
- User configuration is not scanned/imported.
- The new module supplies only APIs while the implementation sits in another starter.

Resolution:

1. Check the dependency tree.
2. Identify the class and module containing the implementation.
3. Check auto-configuration imports metadata.
4. Enable the condition evaluation report.
5. Check properties/profiles.
6. Write a small context test for the auto-configuration.
7. Verify the module JAR was packaged properly.

Do not widen component scanning before knowing where the bean is supposed to come from.

## 37. Troubleshooting: duplicate logging providers/bindings

Symptoms may include:

~~~text
Class path contains multiple SLF4J providers
~~~

or warnings about incompatible bindings/providers.

Resolution:

1. Inspect `runtimeClasspath` or Maven dependency tree.
2. Locate the actual providers and versions.
3. Verify whether the default logging starter is still present.
4. Verify the new provider matches the SLF4J API version.
5. Check bidirectional bridges.
6. Exclude redundant implementations on the right dependency path.
7. Run the application and confirm logs are written exactly once.

Do not exclude `slf4j-api` just because it appears in the graph. The API is usually the contract application libraries call; the problem usually lies in the provider/binding or bridges.

## 38. Troubleshooting: JUnit tests do not run

Symptoms:

- Build succeeds with a test count of 0.
- Tests compile yet are not discovered.
- Some JUnit 4 tests stop running after dropping Vintage.
- Tests run in the IDE yet fail to run in CI.

Resolution:

- Check `@Test` annotation imports.
- Check the JUnit engine on test runtime.
- Check Surefire/Gradle test configurations.
- Check naming conventions and test filters.
- Check profiles/skip flags.
- Compare wrapper and JDK between local/CI.
- Inspect test reports.

Do not move tests into different source folders just to make the build tool find them if the root cause is a missing engine.

## 39. Troubleshooting: NoSuchMethodError after upgrade

`NoSuchMethodError` usually signals runtime loaded a class version missing the method compiled code calls.

Causes:

- Compiled against a newer version while runtime resolved an older version.
- A transitive dependency overrode a version managed by the BOM.
- An internal module was built against a different release train.
- Classpath contains multiple versions and resolution order differed from expectations.

Resolution:

1. Identify the class in the exception.
2. Identify the artifact containing that class.
3. Inspect dependency tree/insight.
4. Compare compiled and runtime versions.
5. Remove unnecessary overrides or upgrade dependent modules.
6. Rebuild all modules in a multi-module repo to clear stale artifacts.

Do not merely drop a newer JAR into runtime if the build tool still picks another version elsewhere.

## 40. Troubleshooting: BeanCreationException after upgrade

After upgrading Boot, startup may fail due to:

- API package changes.
- Changed auto-configuration conditions.
- Deprecated/removed properties.
- Default bean changed or split to another module.
- Logging provider conflict.
- Hibernate mapping/query behavior.
- Missing validation provider.
- Dependency version mismatch.
- Invalid security configuration.

Investigation steps:

1. Read the bean name and nested cause.
2. Identify which module/starter defines the dependency.
3. Check relevant release notes.
4. Check properties and active profiles.
5. Use the condition report if a bean was not registered.
6. Inspect the dependency tree if classes/APIs are incompatible.
7. Write a context test to lock down the intended behavior.

A container exception does not automatically prove a Spring Boot release is buggy; typically a specific dependency or configuration changed.

## 41. Managing deprecations and removals

A deprecation warning is a migration signal, not noise to silence by suppressing warnings.

When encountering a deprecated API:

1. Find the replacement API in the target version.
2. Read the deprecation note and planned removal.
3. Verify semantics, not just method names.
4. Update tests to confirm behavior.
5. Delete the old adapter once all callers have migrated.

If a third-party library emits warnings, check for a compatible newer version rather than forking or suppressing all warnings.

### Do not upgrade a dependency just because a newer version exists

The latest version of a library is not guaranteed compatible with your current Boot release. Prefer the platform's dependency management and compatibility guidance.

## 42. Updating CI/CD after upgrading

Upgrading versions in source while CI still uses an older JDK/wrapper creates local/CI divergence.

Check:

- JDK distribution and version.
- Maven/Gradle wrapper.
- Build cache.
- Environment variables.
- Testcontainers/Docker availability.
- Native toolchain if applicable.
- Artifact packaging tasks.
- Image builders and registry access.
- Test report uploads.
- Dependency vulnerability scanning.
- Deployment runtime base image.

### Build matrix if supporting multiple JDKs

If the application commits to running across multiple JDKs, CI should verify supported versions. However, build JDK and runtime JDK can differ in some workflows; document both toolchain targets and runtime support clearly.

### Do not let stale CI dependency caches mask bugs

After changing BOMs/starters, build caches can obscure troubleshooting. Use clean/reproducible builds to verify migration, without wiping every cache blindly unless cache corruption is suspected.

## 43. Updating documentation and module contracts

After migration, update:

- Java/Boot versions in README and build docs.
- Starter dependencies provided by modules.
- Public APIs and package imports.
- Logging backend and configuration files.
- Test framework conventions.
- Instructions to run unit/integration tests.
- Profiles and configuration properties.
- Local development instructions.
- Base image/runtime version.
- Known limitations and deprecation cleanup tasks.

If an internal module serves as a starter for multiple apps, document clearly:

- Which dependencies form the API contract.
- Which dependencies are implementation details.
- Which default beans can be overridden.
- Which properties are supported.
- Which logging provider is expected.
- Which test utilities belong strictly in test scope.

A module without clear contracts forces every consuming app to guess during upgrades.

## 44. A controlled Maven migration example

Suppose an application uses web, JPA, security, default logging, and the test starter.

Illustrative POM:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.x.y</version>
    <relativePath/>
</parent>

<properties>
    <java.version>21</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`3.x.y` is a placeholder. The project must use a concrete release chosen after checking compatibility.

Workflow:

1. Update parent version.
2. Check Java toolchain.
3. Run dependency tree.
4. Compile and handle Jakarta/API changes if part of migration.
5. Run unit tests.
6. Run context/web/JPA/security tests.
7. Check the logging provider.
8. Package the executable JAR.
9. Run smoke tests using the JAR.
10. Update CI/runtime images.

Do not add individual versions to each starter when the Boot parent manages them.

## 45. A controlled Gradle migration example

Illustrative Kotlin DSL:

~~~kotlin
plugins {
    id("org.springframework.boot") version "3.x.y"
    id("io.spring.dependency-management") version "1.x.y"
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Again, versions here are placeholders. Choose plugin versions compatible with your wrapper and Boot release.

Run:

~~~bash
./gradlew clean test
./gradlew bootJar
~~~

Then inspect:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

The goal is verifying that application runtime and test runtime contain the expected modules, providers, and engines.

## 46. Keeping changes easy to review

A migration often spans many changes. Group them by theme:

| Change group | Contents |
|---|---|
| Build baseline | Boot parent/BOM, JDK, wrapper, plugins |
| Source migration | Jakarta imports, API deprecations |
| Starters/modules | Added/removed/changed starters, auto-configuration metadata |
| Logging | Providers, bridges, configurations |
| Testing | JUnit/Mockito/Spring Test, test discovery |
| Runtime integration | Hibernate, database drivers, security, metrics |
| CI/deployment | JDK images, build tasks, health/smoke tests |

Splitting commits by group helps reviewers isolate the cause if a test or runtime behavior shifts. If a large commit is unavoidable, at least document dependency graph diffs and test results by group.

### Do not alter business behavior outside the migration goal

A migration should keep application behavior stable unless explicitly requested otherwise. Mixing business logic edits makes it very hard to tell whether a regression came from the version upgrade or the feature edit.

## 47. Choosing strategy when changing logging or test tools

Not every change needs to happen simultaneously with a Boot upgrade.

| Change | When to do alongside migration? | When to separate? |
|---|---|---|
| Upgrading SLF4J/provider managed by Boot | When dependency compatibility requires it | When merely wanting to swap backend/format |
| Switching Logback to Log4j 2 | When target platform mandates it | When it is an independent logging architecture change |
| JUnit 4 to Jupiter | When old engine/APIs are no longer supported | When Vintage can remain during transition |
| Newer Mockito annotations | When old APIs are removed | When it is just deprecation cleanup |
| Splitting internal modules | When module APIs/metadata require change | When doing architectural refactoring independent of version |
| Changing Hibernate major | When the target Boot pulls that major | When schema/data migration needs a separate plan |

### Keep migration scope small enough

A platform upgrade already carries its own risk. Avoid combining a logging backend swap, JUnit migration, module split, and security rewrite in one batch unless dependencies force it.

However, if the target Boot release removed an older API, complete the associated migration before considering the upgrade finished.

## 48. Common mistakes

### Upgrading spring-core or spring-context alone

This can skew the Spring Framework version managed by Boot. Prefer upgrading the Boot release train or using well-justified overrides.

### Keeping an old starter after a capability was split

This can pull in unused dependencies or activate unwanted auto-configuration. Check release notes and the dependency tree.

### Adding a new provider while forgetting to exclude the old one

This can trigger multiple-provider warnings or non-deterministic logging behavior.

### Turning every test into a Spring context test

Pure unit tests do not need Spring. Use a context only when a test genuinely needs DI, conditions, or framework integration.

### Removing JUnit 4 while tests still import JUnit 4

Tests may fail to compile or silently go undiscovered if the engine is absent.

### Upgrading Mockito without checking Spring mock annotations

Some mock-bean APIs belong to Spring Test, not plain Mockito annotations. Check versions and semantics before replacing.

### Running compile only

Compilation does not catch bean initialization, SQL behavior, logging configuration, test discovery, or container runtime failures.

### Forcing versions just to clear dependency tree conflicts

The build may pass while runtime suffers API mismatches. Check actual compatibility, not just version numbers.

### Disabling validation/security to get the context starting

This alters behavior and weakens safety. Find the underlying configuration or API migration issue.

### Skipping checks on the final artifact

The test classpath can differ from the runtime artifact. Run the actual executable JAR/image or native artifact targeted for deployment.

## 49. Pre-completion checklist for version upgrades

1. **Lock down the target release.** Are Boot, Java, Maven/Gradle wrapper, and plugins compatible?
2. **Read the migration guide.** Identify breaking changes relevant to the codebase.
3. **Check dependency management.** Parent/BOM acts as a clear version source.
4. **Audit the starter graph.** Which starters changed, split, or are no longer needed?
5. **Audit module boundaries.** Do application and library modules have clear roles?
6. **Check auto-configuration metadata.** Are imports, conditions, and ordering valid?
7. **Check Jakarta/API migration.** Migrate only namespaces belonging to moved APIs.
8. **Check the logging stack.** One provider, unidirectional bridges, compatible configs.
9. **Check test starters.** Test libraries reside strictly in test scope.
10. **Check JUnit engines.** Test discovery and executed test counts match.
11. **Check Mockito/Spring mocks.** Annotations match versions and test types.
12. **Check test slices.** MVC, JPA, JSON, client, and security behavior.
13. **Check dependency trees.** Runtime and test classpaths do not diverge unintentionally.
14. **Check configuration properties.** Deprecated keys, binding, validation, and profiles.
15. **Check Hibernate/database.** Mappings, SQL, migrations, and drivers.
16. **Check security.** Authentication, authorization, CSRF, CORS, and actuator.
17. **Run integration tests.** External services use appropriate containers/fakes.
18. **Check packaging.** JAR/image contains expected dependencies and launcher.
19. **Update CI/CD.** JDK, wrapper, build cache, test reports, and artifact scans.
20. **Document results.** Versions, dependency changes, tests, and rollback path.

## Conclusion

Upgrading Spring Boot means changing a **release train**, not editing a single version line. Starters determine which capability groups enter the classpath; the BOM/parent manages compatible versions; module boundaries govern where configurations and auto-configurations are registered; logging APIs/providers/bridges determine how logs are routed; and test starters plus build plugins determine whether tests compile, get discovered, and execute reliably.

A solid migration workflow starts by picking the target Boot/JDK/build tool, reading release notes, updating dependency management, and inspecting the dependency graph. Next, address source/API changes, starter/module metadata, logging providers, and test tooling group by group. Finally, run layered tests, verify executed test counts, inspect the runtime classpath, and smoke test the actual releasable artifact.

By keeping clear boundaries between **starters, modules, the logging stack, and the test stack**, developers can upgrade the platform with reviewable scope, catch dependency conflicts early, and reduce the risk of a green build whose production runtime loses logs, misses beans, or skips its entire test suite.
