# Setting Up Test Dependencies and Aligning JUnit Versions with Spring Test

JUnit Jupiter is the standard testing foundation in modern Spring projects. For tests to compile, be discovered, and run properly, a project needs the right components from JUnit Jupiter, JUnit Platform, and Spring Test. These dependencies are interrelated, yet they do not share a single version number: Spring Framework has its own release line, JUnit Jupiter has its own release line, and JUnit Platform also belongs to the JUnit ecosystem.

Proper dependency management helps a project avoid issues such as compiling successfully but failing to find a test engine at runtime, missing `SpringExtension`, or encountering `NoSuchMethodError` due to incompatible JUnit API and engine versions. For Spring Boot applications, the simplest choice is usually to use `spring-boot-starter-test` and let Spring Boot manage compatible versions. For projects using only Spring Framework, Spring and JUnit versions should be managed with appropriate BOMs.

## 1. Understanding the Components in the Testing Stack

Before declaring dependencies, it is necessary to distinguish the role of each component.

| Component | Typical Artifact | Role |
|---|---|---|
| JUnit Jupiter API | `org.junit.jupiter:junit-jupiter-api` | Provides annotations and APIs for writing tests such as `@Test`, `@BeforeEach`, `Assertions`, and the extension model |
| JUnit Jupiter Params | `org.junit.jupiter:junit-jupiter-params` | Provides `@ParameterizedTest`, `@ValueSource`, `@CsvSource`, and argument sources |
| JUnit Jupiter Engine | `org.junit.jupiter:junit-jupiter-engine` | Executes tests written with JUnit Jupiter |
| JUnit Platform | `org.junit.platform:*` | Foundation for discovering and launching test engines; includes launcher, engine, and reporting APIs |
| Spring Test | `org.springframework:spring-test` | Provides the Spring TestContext Framework, `SpringExtension`, `MockMvc`, and Spring testing utilities |
| Spring Boot Test | `org.springframework.boot:spring-boot-test` | Provides testing utilities tailored for Spring Boot |
| Spring Boot Test AutoConfigure | `org.springframework.boot:spring-boot-test-autoconfigure` | Provides test slice annotations such as `@WebMvcTest`, `@DataJpaTest`, and related auto-configuration |

JUnit Jupiter and JUnit Platform are normally used together. The API allows test code to compile, while the engine is responsible for execution. Having only the API without the engine can cause tests to compile cleanly yet fail to run. JUnit Jupiter Params is needed when using parameterized tests; the aggregate dependency `junit-jupiter` helps declare these Jupiter components together.

Spring Test adds integration with Spring. For instance, `SpringExtension` connects JUnit Jupiter with the Spring TestContext Framework to manage the `ApplicationContext`, dependency injection, test transactions, and test lifecycle callbacks. `@SpringBootTest` and `@SpringJUnitConfig` already integrate the corresponding extension; for a plain JUnit Jupiter test class that needs a Spring context, you can declare `@ExtendWith(SpringExtension.class)` together with appropriate context configuration.

## 2. Choosing Dependencies by Project Type

### 2.1. Spring Boot Projects

For Spring Boot applications, `spring-boot-starter-test` is the right starting point. This starter bundles Spring Boot Test, Spring Test, JUnit Jupiter, and commonly used testing libraries such as Mockito, AssertJ, Hamcrest, JSONassert, JsonPath, and XMLUnit at versions managed by Spring Boot.

Ordinarily, there is no need to declare `junit-jupiter-api`, `junit-jupiter-engine`, or `spring-test` separately when already using the starter. Re-adding these artifacts with manually chosen versions can introduce unnecessary conflicts.

### 2.2. Spring Framework-Only Projects

A Java library or Spring application without Spring Boot can declare directly:

- `spring-test` to use the Spring TestContext Framework and Spring testing utilities.
- `junit-jupiter` to write and run JUnit Jupiter tests.
- Additional assertion or mocking libraries if needed by the project.

In this case, manage Spring module versions with the Spring Framework BOM and manage JUnit modules with the JUnit BOM. The two BOMs have different responsibilities, and you should not assume their versions must be identical.

### 2.3. Java Projects Not Using Spring Test

If you are only writing pure Java unit tests and not initializing a Spring context, you may only need JUnit Jupiter along with the supporting libraries actually used. There is no reason to add `spring-test` merely because the application uses Spring in production code. Dependencies should reflect the testing responsibilities of the module.

## 3. Declaring Dependencies with Maven

### 3.1. Using the Spring Boot Parent

If the project inherits from `spring-boot-starter-parent`, the parent provides dependency management and build plugin configurations matching the chosen Spring Boot version. In `pom.xml`, simply add the test starter in the `test` scope:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

The `test` scope ensures testing libraries are only present on the test classpath and do not become runtime dependencies of the packaged application. Versions of JUnit, Spring Test, and accompanying testing libraries are resolved from Spring Boot's dependency management.

A Spring Boot test can use annotations as follows:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ApplicationContextTest {

    @Test
    void applicationContextLoads() {
        assertThat(true).isTrue();
    }
}
```

The example above illustrates how JUnit Jupiter and Spring Boot Test work together in a test. In a real test, assertions should verify meaningful application behavior or state.

### 3.2. Not Using Spring Boot Parent, Yet Using the Spring Boot BOM

Some projects need to keep their own parent POM. You can import `spring-boot-dependencies` in `dependencyManagement`, then declare the starter without specifying versions on individual dependencies:

```xml
<properties>
    <spring-boot.version>3.3.13</spring-boot.version>
</properties>

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

Version `3.3.13` merely illustrates a specific Spring Boot 3.3 release; the project should use the Spring Boot version selected and supported in its own environment. When importing the BOM, there is no need to repeat versions for individual Spring or JUnit modules managed by the BOM.

Note: importing the BOM only provides dependency management. If you do not inherit from the Spring Boot parent, Maven plugin configurations such as Surefire still need to be managed appropriately so Maven discovers and runs JUnit Platform. Do not assume that importing the BOM automatically applies all build configurations from the parent POM.

### 3.3. Using Spring Framework Without Spring Boot

For projects using only Spring Framework, import the Spring Framework BOM and JUnit BOM separately:

```xml
<properties>
    <spring-framework.version>6.1.21</spring-framework.version>
    <junit.version>5.10.5</junit.version>
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
</dependencies>
```

The two versions in the example belong to two independent release lines: `spring-framework.version` manages Spring modules, while `junit.version` manages the JUnit ecosystem. There is no need to make the two version numbers match. When selecting actual versions, cross-check the project's Java, Spring Framework, and JUnit requirements.

With Maven when not using the Spring Boot parent, configure a Maven Surefire version compatible with JUnit Platform. If the project has multiple modules, place the BOMs and plugin management in the parent POM so child modules share the same rules.

## 4. Declaring Dependencies with Gradle

### 4.1. Spring Boot Gradle Plugin and Dependency Management

In a Spring Boot project using Gradle, declare the starter in the `testImplementation` configuration:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The example assumes the project has already configured the Spring Boot Gradle Plugin along with dependency management as used by the project. When the `io.spring.dependency-management` plugin is applied alongside the Spring Boot Gradle Plugin, Spring Boot can automatically import the corresponding BOM. If the project uses native Gradle BOM support, declare the platform as shown in the next example.

`useJUnitPlatform()` tells Gradle to run tests via JUnit Platform. Declaring JUnit dependencies without enabling this platform can prevent Gradle from discovering Jupiter tests as expected.

### 4.2. Using Native Gradle BOM Support

Gradle supports importing Maven BOMs via `platform(...)`. With Spring Boot, you can declare the BOM before the starter:

```groovy
dependencies {
    testImplementation platform(
        "org.springframework.boot:spring-boot-dependencies:${springBootVersion}"
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The `springBootVersion` variable must be defined in the project's Gradle configuration or version catalog and must match the Spring Boot version used by the application. Avoid simultaneously applying multiple version management mechanisms with differing override rules unless you clearly understand their precedence.

### 4.3. Spring Framework-Only Projects

For projects without Spring Boot, import the two independent BOMs in the test configuration:

```groovy
dependencies {
    testImplementation platform(
        "org.springframework:spring-framework-bom:${springFrameworkVersion}"
    )
    testImplementation 'org.springframework:spring-test'

    testImplementation platform("org.junit:junit-bom:${junitVersion}")
    testImplementation 'org.junit.jupiter:junit-jupiter'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`springFrameworkVersion` and `junitVersion` must be defined in the project's configuration. The Spring Framework BOM aligns `spring-test` with other Spring modules; the JUnit BOM aligns Jupiter API, Params, Engine, and Platform modules within the same ecosystem. `junit-platform-launcher` is declared at runtime when the build configuration or development tools require the launcher on the test runtime classpath. Keep the launcher on the same Platform release line managed by the JUnit BOM.

In a project using only JUnit Jupiter without Spring Test, you can omit the Spring dependencies and keep only the JUnit BOM, `junit-jupiter`, the launcher if needed, and `useJUnitPlatform()`.

### 4.4. Distinguishing Gradle Configurations

Gradle provides separate configurations so dependencies appear on the right classpath:

| Configuration | Purpose | Examples |
|---|---|---|
| `testImplementation` | Dependencies needed to compile code in `src/test` and present on the test compile/runtime classpath | `spring-boot-starter-test`, `spring-test`, `junit-jupiter` |
| `testRuntimeOnly` | Dependencies needed only when running tests | JUnit Platform Launcher in setups requiring explicit declaration |
| `implementation` | Production code dependencies, present on the main compile/runtime classpath | Libraries directly used by `src/main` code |
| `testCompileOnly` | Dependencies needed only to compile tests, not at runtime | Specialized cases, not the default configuration for the JUnit engine |

Do not put JUnit or Mockito into `implementation` just to make tests compile. That pulls testing libraries into the main application's dependencies and can increase artifact size or expose unnecessary dependencies to module consumers.

## 5. Aligning JUnit Versions with Spring Test

### 5.1. Aligning Within Each Ecosystem

Spring Test and JUnit integrate with each other, but they do not share a common version number. Management rules should be:

1. `spring-test`, `spring-core`, `spring-context`, and related Spring Framework modules must share the same Spring Framework release line.
2. `junit-jupiter-api`, `junit-jupiter-params`, and `junit-jupiter-engine` must be compatible and should be managed at the same JUnit Jupiter version.
3. JUnit Platform modules such as the launcher and engine must belong to the Platform version set corresponding to the chosen JUnit Jupiter version.
4. If using Spring Boot, prefer letting the Spring Boot BOM manage both Spring Framework and JUnit according to the version set tested by that Boot release.

For example, Spring Framework `6.1.x` can pair with JUnit Jupiter `5.10.x` in a suitable setup. The two version numbers do not need to match. What matters is that modules within the same ecosystem are aligned and the chosen version set can interoperate.

### 5.2. Why the Spring Boot Starter Is Usually the Best Choice

The Spring Boot BOM is designed to manage a compatible set of dependencies for the corresponding Spring Boot release. When using `spring-boot-starter-test`, the project receives test dependencies according to the version matrix controlled by that BOM.

If you manually specify versions for `spring-test` or `junit-jupiter-engine`, dependencies can drift from the version set managed by Boot. For example, upgrading JUnit Engine alone while keeping the API on an older version can cause class or method linkage errors at runtime. Upgrading `spring-test` independently can also put it out of sync with the `spring-core` or `spring-context` selected by Boot.

Therefore, with Spring Boot, the default approach should be:

- Declare `spring-boot-starter-test` in the test scope.
- Do not specify separate versions for dependencies already managed by the Boot BOM.
- Only override versions when there is a clear technical reason and compatibility across the entire related dependency set has been verified.

### 5.3. When Do You Need to Override the JUnit Version?

There may be cases where a project needs a JUnit bug fix or new feature before upgrading Spring Boot. In that case, check the JUnit version currently managed by the Spring Boot BOM, its support scope, and compatibility changes.

If an override is unavoidable, manage a unified JUnit version via the JUnit BOM or the property/dependency management mechanism used by the project. Do not upgrade only `junit-jupiter-engine` while leaving `junit-jupiter-api`, `junit-jupiter-params`, or JUnit Platform on older versions.

After overriding, run the entire test suite on CI and inspect the actual dependency graph. If Spring Test integrates with a JUnit API that changed, errors may appear during extension initialization or callback execution, even if the test code compiles cleanly.

### 5.4. Avoiding Accidental Mixing of JUnit 4 and JUnit Jupiter

JUnit 4 uses packages and mechanisms such as `org.junit.Test`, `@RunWith`, and `SpringRunner`. JUnit Jupiter uses `org.junit.jupiter.api.Test`, `@ExtendWith`, and the extension model.

A Jupiter test class typically starts like this:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.test.context.junit.jupiter.SpringExtension;

@ExtendWith(SpringExtension.class)
class RepositoryIntegrationTest {

    @Test
    void loadsWithSpringContext() {
        // Test body
    }
}
```

The snippet illustrates connecting Spring Extension with JUnit Jupiter; a real test class needs to configure the context using `@ContextConfiguration`, `@SpringJUnitConfig`, or another appropriate annotation.

If a legacy project still has JUnit 4 tests, the JUnit Vintage Engine can be used to run those tests via JUnit Platform. Add Vintage only when genuinely needed to maintain JUnit 4 tests during a migration period. For new tests, standardize on JUnit Jupiter to avoid managing two extension models and two sets of imports.

## 6. How Spring Test Connects to JUnit Jupiter

Spring Test provides `SpringExtension`, a JUnit Jupiter extension. This extension connects Jupiter's test lifecycle with the Spring TestContext Framework. It allows Spring to create and reuse an `ApplicationContext`, inject beans into tests, manage test transactions, and apply Spring listeners/callbacks.

With Spring Boot, `@SpringBootTest` can be used:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class GreetingServiceTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void returnsGreeting() {
        assertThat(greetingService.greet("Lan"))
                .isEqualTo("Hello, Lan");
    }
}
```

`@SpringBootTest` initializes the application context according to Spring Boot configuration and integrates Spring Extension. Therefore, there is no need to add `@ExtendWith(SpringExtension.class)` again in this example.

With Spring Framework without Boot, `@SpringJUnitConfig` combines context configuration:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(classes = GreetingTestConfig.class)
class GreetingServiceTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void returnsGreeting() {
        assertThat(greetingService.greet("Lan"))
                .isEqualTo("Hello, Lan");
    }
}

@Configuration
class GreetingTestConfig {

    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }
}
```

`@SpringJUnitConfig` is a way to combine Spring TestContext configuration with JUnit Jupiter. In a real module, `GreetingService` and the configuration may live in separate packages or files; the important part here is that the `spring-test` dependency provides Spring integration, while JUnit Jupiter provides the test engine and API.

## 7. Verifying That Dependencies Are Aligned

When tests fail to run or classpath-related errors appear, inspect the dependency graph before changing versions by guesswork.

### 7.1. With Maven

The following command displays test dependencies belonging to the Spring and JUnit groups:

```bash
mvn dependency:tree -Dscope=test -Dincludes=org.springframework,org.springframework.boot,org.junit,org.junit.jupiter,org.junit.platform
```

Check the following points:

- `org.springframework` modules have the same Spring Framework version according to the chosen BOM.
- `spring-boot-test` and `spring-boot-test-autoconfigure` match the project's Spring Boot version.
- JUnit Jupiter API, Params, and Engine are not pulled to unexpectedly different versions.
- JUnit Platform Launcher and other Platform modules do not conflict due to transitive dependencies.
- No legacy dependency inadvertently brings JUnit 4 or a different JUnit Jupiter version onto the test classpath.

You can use `mvn help:effective-pom` to inspect the final dependency management and plugin configuration after Maven merges parent POMs, BOMs, and module settings.

### 7.2. With Gradle

Inspect the actual dependencies on the test runtime classpath:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

To find out why a dependency was resolved to a specific version, use `dependencyInsight`:

```bash
./gradlew dependencyInsight \
    --dependency junit-jupiter-api \
    --configuration testRuntimeClasspath

./gradlew dependencyInsight \
    --dependency junit-jupiter-engine \
    --configuration testRuntimeClasspath

./gradlew dependencyInsight \
    --dependency spring-test \
    --configuration testRuntimeClasspath
```

Gradle displays the selected version, which dependency requested that version, and which rules affected version resolution. This is helpful when another library pulls in an unwanted JUnit or Spring version.

After inspecting the graph, run the tests:

```bash
./gradlew test
```

With Maven:

```bash
mvn test
```

Do not modify dependencies simply because you see multiple versions in caches or download logs. Base decisions on the dependency graph of the actual configuration being executed and identify real conflicts on the classpath.

## 8. Common Configuration Errors

### 8.1. Tests Compile, but Gradle Finds No Tests

A common cause is that the `test` task has not enabled JUnit Platform or the engine configuration is not on the runtime classpath.

With Gradle, confirm you have:

```groovy
tasks.named('test') {
    useJUnitPlatform()
}
```

Also confirm that `junit-jupiter` or `junit-jupiter-engine` is present on the test runtime classpath.

### 8.2. TestEngine Not Found or Tests Not Executed

If only JUnit Jupiter API is declared, test code can compile but has no engine to run. Use the aggregate `org.junit.jupiter:junit-jupiter` dependency or declare both API and Engine from the same version set.

With some Gradle setups and development tools, `junit-platform-launcher` may be needed in `testRuntimeOnly`. Check the requirements of the build tool version in use before adding this dependency.

### 8.3. `SpringExtension` Not Found

`SpringExtension` belongs to the `spring-test` artifact. If only JUnit Jupiter is declared without Spring Test, the compiler will not find this class. With Spring Boot, `spring-boot-starter-test` normally already provides the necessary dependency; with standalone Spring Framework projects, `spring-test` must be declared.

### 8.4. `NoSuchMethodError` or `NoClassDefFoundError`

Class linkage errors typically occur when part of a library was compiled against a different API version than what is present at runtime. Inspect JUnit Jupiter API, Engine, Params, Platform, and Spring Framework modules together.

Do not simply re-add the missing dependency with an arbitrary version. Identify which dependency pulled in the incompatible version, then adjust the BOM or constraint at the proper management level.

### 8.5. Confusing JUnit 4 and JUnit Jupiter Annotations

These two imports belong to two different systems:

```java
import org.junit.Test;                 // JUnit 4
import org.junit.jupiter.api.Test;     // JUnit Jupiter
```

A test class using `org.junit.Test` does not automatically become a Jupiter test simply because the project added `junit-jupiter`. If you need to run JUnit 4 tests, an appropriate engine such as Vintage must be present, or the test must be intentionally migrated to Jupiter.

### 8.6. Manually Adding Multiple Spring Test Versions

If `spring-test` differs in version from `spring-core` or `spring-context`, Spring TestContext may fail at runtime. With Spring Boot, remove explicit versions and rely on the Boot BOM. With standalone Spring Framework, use the Spring Framework BOM across all Spring modules.

### 8.7. Confusing Context Initialization Errors with JUnit Dependency Errors

A `Failed to load ApplicationContext` message does not mean JUnit has mismatched versions. The cause may be a missing bean, misconfiguration, unreachable datasource, unsuitable profile, or application startup failure. Read the root cause in the stack trace before changing test dependencies.

## 9. Managing Dependencies in Multi-Module Projects

With Gradle multi-project or Maven multi-module builds, versions should be managed at the root level or via a shared convention plugin. Test modules should not pick different JUnit versions independently without a clear requirement.

A structure can be organized as follows:

```text
root project
├── dependency management / version catalog
├── module-a
│   └── testImplementation: spring-boot-starter-test
├── module-b
│   └── testImplementation: spring-boot-starter-test
└── module-c
    └── testImplementation: junit-jupiter (if it is a pure Java module)
```

Spring Boot modules share the same Boot BOM version. Pure Java modules can use the JUnit BOM without pulling in the entire Spring Boot starter. This approach keeps dependencies scoped to what each module needs while maintaining centralized version rules.

With Maven, declare BOMs in the parent POM or an internal BOM and let child modules inherit them. With Gradle, use a version catalog, convention plugins, or platform declarations in shared configuration. When updating versions, inspect the dependency graph of each module because an individual module may bring its own transitive dependencies.

## 10. Practical Checklist When Upgrading JUnit or Spring Test

When upgrading versions, proceed in a verifiable order:

1. Identify whether the project uses Spring Boot or standalone Spring Framework and locate the BOM managing dependencies.
2. Check the current Spring Boot/Spring Framework version along with the selected JUnit Jupiter and Platform versions.
3. Prefer upgrading the Spring Boot version if the goal is to adopt a set of Spring and JUnit dependencies already tested together.
4. If only JUnit needs upgrading, verify compatibility with Spring Test, then update the entire JUnit BOM or unified management mechanism.
5. Inspect the test runtime dependency graph to find overridden or unexpectedly pulled-in versions.
6. Run tests locally and in CI, including integration tests that use a Spring context.
7. Remove duplicate dependencies or manually declared versions that are no longer needed.

When documenting the configuration in project documentation, state clearly which dependencies come from starters, which BOM manages versions, and which tasks run tests on JUnit Platform. This helps new team members understand why modules do not declare individual JUnit versions and reduces the risk of accidentally creating mismatched dependency sets.

Setting up test dependencies properly means ensuring sufficient APIs to compile, sufficient engines to execute, Spring Test when Spring integration is needed, and a clear version management rule. In Spring Boot, the starter together with the BOM usually handles most of that work. In standalone Spring Framework projects, use separate Spring Framework and JUnit BOMs, keep modules within each ecosystem aligned, and verify the result via the actual dependency graph.
