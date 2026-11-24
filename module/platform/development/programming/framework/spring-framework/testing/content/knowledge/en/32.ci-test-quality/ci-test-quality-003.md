# Aligning JUnit, Spring Test, Mockito, and Java Versions

A Spring test suite can fail even when both test code and application code are correct if the testing libraries are incompatible with one another. For example, the JUnit Jupiter API may compile successfully while the engine is not found at runtime; `SpringExtension` may come from a different `spring-test` version than `spring-core`; the Mockito extension may be out of sync with `mockito-core`; or the JDK used in CI may not meet Spring Framework's baseline.

Version alignment means selecting a compatible toolkit against a single baseline: Java runtime/toolchain, Spring Framework or Spring Boot, JUnit Platform/Jupiter, Mockito, and the Maven or Gradle test runner plugin. The safest approach is to let a dependency management platform govern related versions, and only override when there is a clear reason and compatibility has been verified.

## 1. Components That Must Be Aligned

A Spring test suite typically involves several layers of libraries:

| Component | Role | Example artifacts |
| --- | --- | --- |
| Java JDK | Compile and run the application/tests. | JDK 17, 21, or a version supported by the project. |
| Spring Framework | Core container, context, MVC, transactions, and test integration. | `spring-core`, `spring-context`, `spring-test`. |
| Spring Boot (if used) | Dependency management and auto-configuration for the app/tests. | `spring-boot-dependencies`, `spring-boot-starter-test`. |
| JUnit Platform | Foundation for discovering and executing test engines. | `junit-platform-engine`, `junit-platform-launcher`. |
| JUnit Jupiter | API, parameterized tests, and engine for JUnit 5+. | `junit-jupiter-api`, `junit-jupiter-params`, `junit-jupiter-engine`. |
| JUnit Vintage (if needed) | Runs JUnit 3/4 tests on JUnit Platform. | `junit-vintage-engine`. |
| Mockito | Mocking, stubbing, and verifying interactions. | `mockito-core`. |
| Mockito JUnit integration | Extension to initialize mocks and manage strictness. | `mockito-junit-jupiter`. |
| Build test plugin | Launches test engines from Maven or Gradle. | Maven Surefire/Failsafe, Gradle test task. |

Not every project needs all of the artifacts above. A Spring Boot application usually gets most libraries through `spring-boot-starter-test`. A plain Spring Framework project needs to declare the appropriate dependencies and BOMs explicitly. JUnit Vintage is only needed while JUnit 3/4 tests remain; if all tests already use Jupiter, omit this engine.

## 2. Start from a Java Version Supported by the Entire Stack

The Java version is the foundation of dependency compatibility. The JDK version used to compile, the bytecode version produced, and the JDK used to run tests must be configured consistently.

Important baselines by framework generation:

| Component / generation | Java baseline to watch |
| --- | --- |
| Spring Framework 5.x | Supports older Java lines depending on minor release; commonly seen in Java 8/11 apps. |
| Spring Framework 6.x | Requires Java 17 or higher and moves to Jakarta EE APIs (`jakarta.*`). |
| Spring Framework 7.x | Continues a Java 17+ baseline; check specific requirements of the minor release and modules. |
| Spring Boot 3.x | Java 17 or higher. |
| Mockito 5.x | Java 11 or higher. |
| JUnit Platform/Jupiter | Baseline varies by major release; check the requirement for the exact major version chosen. |

The project baseline must satisfy the highest requirement among all components used. For instance, if the application uses Spring Framework 6.x, Java 11 is insufficient even though Mockito 5 can run on Java 11. If Spring requires Java 17, only JDK 17 or newer is a valid choice.

Do not check only `java -version` on a developer machine. The build may use a different JDK via a Maven toolchain, Gradle toolchain, or CI image. You must align:

- The JDK running Maven/Gradle and test workers.
- The Java toolchain selected by compiler/test tasks.
- Compiler `source`/`target` or `--release`.
- The JDK installed in CI runners.
- The Java version declared in Docker images or build containers, if any.

### Maven compiler configuration

You can use `maven.compiler.release` to constrain APIs and bytecode to the target Java release:

```xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>${java.version}</maven.compiler.release>
</properties>
```

If the project uses the Spring Boot parent, the parent usually manages plugins and related properties. Set the Java version according to the baseline chosen by the application, without declaring conflicting `source`, `target`, and `release` values.

### Gradle Java toolchain

With Gradle, toolchains let the build select the JDK explicitly:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

If you need to set a bytecode target, configure `options.release` on `JavaCompile` to match the same release. Toolchains can help Gradle locate or download an appropriate JDK depending on environment configuration, though CI must still be prepared with access to that JDK.

## 3. Spring Boot: Prefer Boot's Dependency Management

Spring Boot provides the `spring-boot-dependencies` BOM and parent POM to manage a set of versions tested together. `spring-boot-starter-test` bundles commonly used testing libraries, including Spring Test, JUnit Jupiter, Mockito, AssertJ, and several others.

Maven example using the Spring Boot parent:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.4.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

`3.4.0` is an illustrative version for parent configuration; when applying this, replace it with the Spring Boot release chosen by your project and confirmed compatible with Java and other libraries.

If not using the Boot parent, you can import the BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

When using the Boot BOM, you normally do not specify separate versions for `spring-test`, `junit-jupiter`, `mockito-core`, or `mockito-junit-jupiter`. Declaring a custom version for a BOM-managed library can introduce a combination not tested by that Boot release.

### Gradle with the Spring Boot plugin

In Gradle, the Spring Boot plugin and dependency management plugin can manage dependencies via the BOM. A typical Kotlin DSL configuration:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.x.y"
    id("io.spring.dependency-management") version "1.x.y"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
```

The versions in the plugin example are placeholders. With plain Gradle, you can use `platform("org.springframework.boot:spring-boot-dependencies:...")` in `testImplementation` or configure equivalent dependency management so test libraries inherit versions from the BOM.

## 4. Plain Spring Framework: Use Spring BOM and JUnit BOM

If a project does not use Spring Boot, manage Spring Framework modules along the same release train. Do not leave `spring-test` at one version while `spring-core`, `spring-context`, or `spring-webmvc` is at another.

Maven can import the Spring Framework BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>${spring-framework.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>${junit.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<properties>
    <spring-framework.version>6.2.x</spring-framework.version>
    <junit.version>5.x.y</junit.version>
    <mockito.version>5.x.y</mockito.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.mockito</groupId>
        <artifactId>mockito-core</artifactId>
        <version>${mockito.version}</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.mockito</groupId>
        <artifactId>mockito-junit-jupiter</artifactId>
        <version>${mockito.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Versions like `6.2.x`, `5.x.y`, and `5.x.y` are merely illustrative placeholders for a release line; replace them with concrete versions. The Spring BOM manages Spring modules, and the JUnit BOM manages JUnit modules. Mockito does not share a BOM in this example, so `mockito-core` and `mockito-junit-jupiter` share the same version property.

If the project uses a different dependency management platform, keep the same principle: one unified Spring version, one unified JUnit BOM, and the same version across related Mockito artifacts.

### Gradle with platforms

Gradle can consume BOMs via `platform(...)`:

```kotlin
dependencies {
    implementation(platform("org.springframework:spring-framework-bom:6.2.x"))
    testImplementation(platform("org.junit:junit-bom:5.x.y"))

    testImplementation("org.springframework:spring-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.mockito:mockito-core:5.x.y")
    testImplementation("org.mockito:mockito-junit-jupiter:5.x.y")
}

tasks.test {
    useJUnitPlatform()
}
```

With a Gradle version catalog, you can declare versions centrally in `libs.versions.toml` and reuse the same alias/version for `mockito-core` and `mockito-junit-jupiter`. Avoid scattering versions across multiple modules, as doing so easily creates version drift during upgrades.

## 5. Align JUnit API, Engine, and Platform

JUnit 5 is split into components with distinct responsibilities:

- JUnit Jupiter API contains annotations and assertion APIs such as `@Test`, `@BeforeEach`, and `Assertions`.
- JUnit Jupiter Engine executes Jupiter tests.
- JUnit Platform Engine defines the contract for test engines.
- JUnit Platform Launcher discovers and launches test engines; build tools or IDEs may invoke the launcher in their own ways.
- JUnit Vintage Engine allows running JUnit 3/4 tests on JUnit Platform.

Having `junit-jupiter-api` on the compile classpath does not mean tests have an engine to run. If the engine is missing or the plugin does not use JUnit Platform, tests may go undiscovered.

### Maven

A concise dependency often used is `junit-jupiter`, because this aggregate artifact brings in the matching API, params, and engine. It can be declared through the BOM without needing a separate version:

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

Maven Surefire requires a version that supports JUnit Platform compatibly with the JUnit version in use. With modern Maven, using Surefire 3.x is common; if a project still uses an older plugin, check plugin documentation and upgrade when needed.

Example plugin configuration:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>${maven-surefire.version}</version>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-failsafe-plugin</artifactId>
            <version>${maven-failsafe.version}</version>
        </plugin>
    </plugins>
</build>
```

Surefire typically runs unit tests in the `test` phase; Failsafe typically runs integration tests in the `integration-test` and `verify` phases. Both plugins need versions compatible with JUnit Platform and the project's test configuration.

### Gradle

Gradle must be configured to use JUnit Platform:

```kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
```

In some newer Gradle versions, the launcher is handled automatically depending on plugin or dependency management setup, yet declaring `junit-platform-launcher` explicitly on the test runtime classpath helps prevent missing-launcher errors when a build requires it. Keep the launcher on the same release train as the JUnit Platform managed by the BOM.

### Should You Use JUnit Vintage?

If the project still has JUnit 4 tests and wants to run them on JUnit Platform, add `junit-vintage-engine` with its version managed by the JUnit BOM. If no JUnit 3/4 tests remain, remove this engine to reduce dependencies and avoid discovery confusion.

Do not mix JUnit 4 `@RunWith` and Jupiter `@ExtendWith` haphazardly. Choose the engine matching each test class and follow an intentional migration path.

## 6. Align Mockito Core and Mockito JUnit Jupiter

Mockito has a core library containing the mock/stub/verify API and a `mockito-junit-jupiter` module providing `MockitoExtension` for JUnit Jupiter. These two artifacts must share the exact same version.

```java
@ExtendWith(MockitoExtension.class)
class PriceServiceTest {

    @Mock
    ExchangeRateClient exchangeRateClient;

    @InjectMocks
    PriceService priceService;

    @Test
    void shouldConvertPrice() {
        when(exchangeRateClient.rate("USD", "EUR"))
                .thenReturn(new BigDecimal("0.92"));

        assertThat(priceService.convert(
                new BigDecimal("10.00"), "USD", "EUR"))
                .isEqualByComparingTo("9.20");
    }
}
```

If `mockito-core` and `mockito-junit-jupiter` have mismatched versions, you may hit `NoSuchMethodError`, `NoClassDefFoundError`, extension discovery failures, or inconsistent behavior. Manage them via a single property or an appropriate BOM/platform.

### Mockito and Java Versions

Mockito 5 requires Java 11 or higher and uses the inline mock maker by default. This can affect how final classes/methods are mocked and how a project configures its mock maker. If an application runs on Java 8, you cannot simply upgrade Mockito to 5 while ignoring the baseline; either choose a Mockito line compatible with Java 8 or upgrade the project's Java version.

When upgrading a Mockito major version, read Mockito's release notes and check:

- The Java baseline of the new version.
- Changes to the default mock maker.
- Static/final mocking behavior and instrumentation requirements.
- Deprecated or removed APIs.
- Compatibility with plugins, agents, or CI runtimes.

Do not mechanically add `mockito-inline` if your Mockito version already uses the inline mock maker by default or if that dependency no longer fits your current Mockito line. Mock maker configuration should reflect your actual version and needs.

## 7. Distinguish `SpringExtension` from `MockitoExtension`

The two extensions serve different roles:

| Extension | Responsibility |
| --- | --- |
| `SpringExtension` | Bridges JUnit Jupiter with the Spring TestContext Framework; manages contexts, dependency injection, and Spring test listeners. |
| `MockitoExtension` | Initializes Mockito annotations, manages strict stubbing, and handles mock lifecycles in tests. |

Tests verifying pure Java services typically use `MockitoExtension`:

```java
@ExtendWith(MockitoExtension.class)
class BillingServiceTest {
    @Mock PaymentGateway paymentGateway;
    @InjectMocks BillingService billingService;
}
```

Tests requiring a Spring context use `SpringExtension`, usually through `@SpringJUnitConfig`, `@SpringBootTest`, `@DataJpaTest`, or Boot test slice annotations:

```java
@SpringJUnitConfig(AppConfig.class)
class BillingIntegrationTest {
    @Autowired BillingService billingService;
}
```

If a test genuinely needs both a Spring context and the Mockito extension, JUnit Jupiter allows registering multiple extensions:

```java
@ExtendWith({SpringExtension.class, MockitoExtension.class})
class CombinedTest {
    // Use Spring injection and independent Mockito mocks.
}
```

However, both are not always needed. In Spring tests, Spring can manage mock beans using the version-appropriate bean override mechanism, such as `@MockitoBean` in Spring versions that support it. For unit tests that do not need a context, using `MockitoExtension` is simpler and avoids unnecessary Spring startup.

### `@Mock` Is Not the Same as `@MockitoBean`

`@Mock` creates a Mockito mock on the test instance. It does not automatically replace a bean in the Spring `ApplicationContext`. `@MockitoBean` (in Spring Framework versions that support it) registers a bean override so a bean in the context is replaced with a mock. Older Spring Boot lines provide `@MockBean`; API availability and status depend on the Boot version.

Conceptual example:

```java
@SpringBootTest
class BillingControllerTest {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    MockMvc mockMvc;
}
```

Do not replace `@MockBean` with `@MockitoBean` based on name alone. Check your Spring Framework/Boot version and import the annotation actually available in the project.

## 8. Align `spring-test` with Other Spring Modules

`spring-test` depends on APIs from other Spring Framework modules. If `spring-test` resolves to a different version than `spring-core`, `spring-context`, `spring-beans`, or `spring-webmvc`, runtime errors can occur even when compilation succeeds.

Common symptoms:

- `NoSuchMethodError`: code compiled against a newer API version, while runtime loaded an older class version.
- `NoClassDefFoundError` or `ClassNotFoundException`: missing class because a dependency is absent or its version lacks the required API.
- `AbstractMethodError`: incompatible interface or abstract method across versions.
- `ApplicationContext` or listener initialization failures: parts of Spring Test and Spring Framework are not on the same release train.
- Unrecognized annotations: tests use an API only available in a newer version while runtime still loads an older version.

Rule: keep all `org.springframework` modules on the same version line governed by the Spring BOM or Spring Boot BOM. Avoid specifying an independent version for `spring-test` when other Spring modules are already platform-managed.

## 9. Jakarta EE and the Transition from Spring 5 to Spring 6

Spring Framework 6 moved from Java EE `javax.*` to Jakarta EE `jakarta.*`. This is not just renaming imports in source code; all dependencies related to Servlet, Persistence, Validation, and other Jakarta APIs must be compatible.

Example:

```java
// Spring Framework 5 / legacy Java EE ecosystem
import javax.servlet.http.HttpServletRequest;

// Spring Framework 6+ / Jakarta EE ecosystem
import jakarta.servlet.http.HttpServletRequest;
```

If a test still pulls in an old `javax.servlet`-based library while Spring 6 uses `jakarta.servlet`, class-loading errors or type mismatches can occur. Upgrade related test dependencies alongside Spring Framework, such as servlet APIs, validation providers, persistence providers, test utilities, or embedded servers.

You cannot resolve an incompatible `javax.*` dependency merely by upgrading JUnit or Mockito. Identify the namespace that library uses and choose a version compatible with your Spring/Jakarta stack.

## 10. Maven: Inspecting the Dependency Tree

Maven can resolve multiple versions of the same library through transitive dependencies. The chosen version may differ from what a developer assumes is being used.

Useful commands:

```bash
mvn dependency:tree -Dscope=test
```

Filter key libraries:

```bash
mvn dependency:tree -Dscope=test -Dincludes=org.springframework,org.junit,org.mockito
```

Inspect the effective POM to see which BOM, parent, and properties determine versions:

```bash
mvn help:effective-pom
```

If an unintended version override occurs, trace which dependency path pulls it in. Use `dependencyManagement` to govern versions intentionally; only use exclusions once you understand the replacement dependency and ensure no class needed by another library is dropped.

## 11. Gradle: Inspecting Dependency Resolution

Gradle selects versions using resolution strategies, platforms, constraints, or version catalogs. Use `dependencies` and `dependencyInsight` to see which version is actually selected.

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

Inspect a specific module:

```bash
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter-engine --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency mockito-core --configuration testRuntimeClasspath
```

`testCompileClasspath` shows dependencies used when compiling tests; `testRuntimeClasspath` shows dependencies actually present when running tests. A test may compile cleanly yet select a different version at runtime, so inspect both when diagnosing linkage errors.

If using a version catalog, declare versions centrally:

```toml
[versions]
spring = "6.2.x"
junit = "5.x.y"
mockito = "5.x.y"

[libraries]
spring-test = { module = "org.springframework:spring-test", version.ref = "spring" }
junit-jupiter = { module = "org.junit.jupiter:junit-jupiter", version.ref = "junit" }
mockito-core = { module = "org.mockito:mockito-core", version.ref = "mockito" }
mockito-junit-jupiter = { module = "org.mockito:mockito-junit-jupiter", version.ref = "mockito" }
```

This illustrates how to centralize versions; real projects should prefer a BOM/platform whenever possible instead of manually pinning individual Spring or JUnit module versions when a BOM already manages them.

## 12. Build Plugins and IDEs Must Also Be Compatible

Correct dependencies are not enough if Maven Surefire, Failsafe, Gradle test tasks, or IDE runners fail to recognize the test engine properly.

With Maven:

- Use a Surefire version that supports JUnit Platform for Jupiter unit tests.
- Use a suitable Failsafe version for integration tests if the project separates phases.
- Verify plugin versions managed by the Spring Boot parent or parent POM.
- Avoid legacy JUnit 4 provider configurations when the project uses Jupiter only.

With Gradle:

- Configure `useJUnitPlatform()` on test tasks.
- Ensure the JUnit Platform launcher is on the runtime classpath if required by the Gradle version/configuration.
- Keep the Gradle wrapper on a version compatible with the JDK used in CI.

With the IDE:

- Check the Project SDK and Gradle/Maven JVM.
- Align the test runner with the build tool so tests run identically in the IDE and CI.
- When the IDE reports no engine found while the command line works, check the IDE's runner configuration and classpath.

## 13. Signs of Version Mismatch and How to Handle Them

| Symptom | Possible cause | Where to check |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Runtime JDK is older than the dependency or test bytecode. | Check the JDK actually running tests and each library's Java baseline. |
| `NoSuchMethodError` in Spring | Mismatched Spring modules or runtime classpath picks an older version. | Inspect dependency tree/runtime classpath and BOM. |
| `NoClassDefFoundError` for Jupiter Engine | Missing engine or version conflict. | Check `junit-jupiter-engine` and Platform. |
| Tests compile but do not run | Build plugin does not use JUnit Platform or engine is absent. | Check Surefire/Failsafe or `useJUnitPlatform()`. |
| Mockito extension not found | Missing `mockito-junit-jupiter` or mismatched artifact version. | Check test dependencies and core/extension versions. |
| `NoSuchMethodError` in Mockito | `mockito-core` and extension/module have different versions. | Align all Mockito artifacts. |
| `javax.servlet`/`jakarta.servlet` errors | Dependency uses an incompatible namespace. | Upgrade libraries for Spring 6+ or choose a compatible Spring 5 stack. |
| Fails only in CI | JDK, toolchain, plugin, or dependency cache differs from local. | Record `java -version`, wrapper/plugins, and dependency resolution. |

Do not fix errors by appending random dependency versions at the end of a build file. First identify the actual resolved version and the dependency path that introduced it.

## 14. Synchronized Upgrade Workflow

When upgrading JUnit, Spring Test, Mockito, or Java, proceed layer by layer:

1. Select the target Java baseline and verify developer, build tool, and CI runtimes satisfy it.
2. Select the Spring Boot or Spring Framework line matching your Java and Jakarta namespace.
3. If using Spring Boot, upgrade the Boot BOM/parent first and let it govern Spring/JUnit/Mockito dependencies.
4. If using plain Spring Framework, upgrade the Spring BOM while selecting a compatible JUnit BOM and Mockito version.
5. Ensure `spring-test` matches the version of all other Spring modules.
6. Ensure JUnit API, Jupiter Engine, Platform Launcher, and Vintage (if needed) are on the same release train.
7. Ensure `mockito-core` and `mockito-junit-jupiter` share the exact same version.
8. Upgrade Maven Surefire/Failsafe or Gradle wrapper/test configuration if necessary.
9. Inspect the dependency tree/runtime classpath to detect unintended overrides.
10. Run test compilation, unit tests, and integration tests; resolve errors from API or baseline changes.
11. Update the CI JDK image/toolchain and document supported versions in the project.

Avoid upgrading every component simultaneously to the latest version without checking compatibility. Changing one platform or one major version at a time makes isolating root causes much easier.

## 15. Examples of Aligned Configuration for Two Project Styles

### Spring Boot project

With Spring Boot, configuration is usually concise because the starter and BOM manage dependencies:

```xml
<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

In this setup, the Boot version is chosen at the parent or BOM. Do not declare separate versions for Spring Test, JUnit, or Mockito unless there is a concrete reason and compatibility has been verified.

### Spring Framework project without Boot

With plain Spring, manage versions via BOMs and properties:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <spring-framework.version>6.2.x</spring-framework.version>
    <junit.version>5.x.y</junit.version>
    <mockito.version>5.x.y</mockito.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>${spring-framework.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>${junit.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.mockito</groupId>
        <artifactId>mockito-core</artifactId>
        <version>${mockito.version}</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.mockito</groupId>
        <artifactId>mockito-junit-jupiter</artifactId>
        <version>${mockito.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Replace `x` and `y` with concrete versions. The project must also declare compatible Maven plugins to run JUnit Platform. With Spring Framework 6.x, `maven.compiler.release` must be 17 or higher.

## 16. Principles for Maintaining Compatibility in CI

CI should validate the exact toolkit the project claims to support. A reliable pipeline should:

- Pin the JDK or use an intentional JDK matrix.
- Use Maven Wrapper or Gradle Wrapper for consistent build tool versions.
- Use dependency BOMs/platforms rather than scattered versions.
- Print Java and dependency resolution details when diagnosing failures.
- Run tests using the same build commands developers use.
- Verify both test compile and test runtime classpaths.
- Never cache libraries or build outputs in a way that mixes dependencies across branches or Java versions.
- Upgrade dependencies periodically and review release notes for Spring, JUnit, Mockito, and build tools.

If supporting multiple JDKs, run a matrix across the declared JDKs. Do not let CI accidentally run on the runner's newest JDK while the project actually supports only an older JDK. Conversely, once a framework raises its baseline, update the CI pipeline JDK and project documentation at the same time.

## Conclusion

Aligning JUnit, Spring Test, Mockito, and Java begins with the project's Java baseline and dependency platform. With Spring Boot, prefer the BOM/parent and `spring-boot-starter-test`; with plain Spring Framework, use the Spring Framework BOM, JUnit BOM, and centralized Mockito version management. Keep `spring-test` on the same release train as other Spring modules, JUnit API/engine/launcher compatible, and `mockito-core` at the same version as `mockito-junit-jupiter`.

When runtime errors or missing test discovery occur, inspect the actual resolved dependencies and the JDK actually running tests before adding overrides. A clear version set used consistently by build tools and CI makes the test suite more stable and framework upgrades predictable.
