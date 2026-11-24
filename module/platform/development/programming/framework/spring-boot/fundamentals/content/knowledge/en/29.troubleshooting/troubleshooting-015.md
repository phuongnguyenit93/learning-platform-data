# Combining Logs, Conditions Report, Dependency Tree, and Reproduction Tests

When a Spring Boot application fails to start or behaves unexpectedly, a single error message is often insufficient to identify the cause. A bean might not be created because an auto-configuration condition did not match; a dependency might be missing or have a version conflict; configuration might be overridden by a profile or environment variable; or logic might only fail under a specific combination of beans and properties.

An effective diagnostic workflow combines four sources of evidence:

1. **Logs and stack traces** reveal what happened, at what time, and where the error surfaced.
2. **The conditions report** explains why Spring Boot applied or skipped an auto-configuration.
3. **The dependency tree** reveals which libraries are actually present, through which path they were pulled in, and which version was selected.
4. **Reproduction tests** turn a hypothesis into a small, repeatable case that confirms the fix.

Each source answers a different question. Logs alone do not fully explain the dependency graph; a dependency tree does not prove a bean was registered; the conditions report does not validate business logic; and a reproduction test verifies the cause in a controlled environment.

## 1. Start with the symptom and error scope

Before changing configuration or upgrading library versions, describe exactly what is happening.

Examples:

- The application stops at startup with `UnsatisfiedDependencyException`.
- An endpoint returns `404` while the application still starts.
- A bean from an auto-configuration does not appear.
- A test passes when run alone yet fails when running the full suite.
- The application runs in the IDE, yet the executable JAR throws `NoClassDefFoundError`.
- A library works on a developer's machine, yet CI hits `NoSuchMethodError`.

Record at least:

- Exact launch command or test command.
- Java, Spring Boot, and build tool versions.
- Active profiles and relevant property overrides.
- Environment where the error occurs: IDE, local terminal, CI, container, or production.
- Stage of failure: compile, test, ApplicationContext creation, request handling, or shutdown.
- Whether the error reproduces consistently, or only under specific timing/load.

An error occurring at the compile step must be handled differently from an error occurring when Spring creates beans. If the application cannot even create the ApplicationContext, inspecting controller mappings is usually not the right starting point.

### Classifying by stage

| Stage | Indicator | Evidence to inspect first |
|---|---|---|
| Dependency resolution / compile | Missing class, method, or artifact | Dependency tree, compile output, repositories, and versions |
| Test startup | Context loading fails | Stack trace, conditions report, test properties |
| Application startup | Bean creation or auto-configuration fails | Startup logs, failure analysis, conditions report |
| Runtime request | HTTP status, business error, timeout | Request logs, traces, configuration, and external dependencies |
| Shutdown | Task does not finish, resource stays open | Lifecycle logs, thread dump, graceful shutdown config |
| Fails only in CI | Environment or execution order differences | Java/build versions, environment, test isolation, dependency resolution |

The goal is to determine whether the fault lies in the **build**, **Spring bootstrap**, **application logic**, or an **external system** before diving deep into a specific tool.

## 2. Reading logs and stack traces systematically

Logs tell you how far the application progressed and where the first meaningful error occurred. In Spring Boot, startup logs typically include:

- Spring Boot and Java versions.
- Active profiles.
- ApplicationContext initialization steps.
- Which port the web server started on.
- When the context finished starting up.
- Warnings or exceptions during bean creation.

When the application fails, locate the **first meaningful exception**, then follow the nested cause chain down to the root cause. The outermost exception usually describes the phase where Spring failed, while deeper exceptions may state the actual cause.

Abbreviated example:

~~~text
APPLICATION FAILED TO START

Description:
Parameter 0 of constructor in com.example.OrderService
required a bean of type 'com.example.PaymentGateway'
that could not be found.

Action:
Consider defining a bean of type 'com.example.PaymentGateway'
in your configuration.
~~~

This message indicates Spring could not find a bean of type `PaymentGateway`. However, it does not yet answer why:

- Has the implementation not been created yet?
- Is the package outside component scan?
- Is a `@Profile` inactive?
- Did `@ConditionalOnProperty` fail to match?
- Was an auto-configuration excluded?
- Is the dependency containing the implementation missing from the runtime classpath?

This is where combining logs with the conditions report and dependency tree comes in.

### Reading the caused-by chain

A stack trace can have multiple exception layers:

~~~text
UnsatisfiedDependencyException
  caused by BeanCreationException
    caused by NoSuchBeanDefinitionException
~~~

How to read it:

1. `UnsatisfiedDependencyException`: Spring could not satisfy a dependency for a bean.
2. `BeanCreationException`: creating a specific bean failed.
3. `NoSuchBeanDefinitionException`: the deeper cause is that no matching bean exists in the context.

Do not read only the first exception line and immediately conclude you must add a dependency. The dependency may already be present while the condition to create the bean did not match.

If the root cause is `NoClassDefFoundError` or `NoSuchMethodError`, investigation shifts to the runtime classpath and version compatibility rather than looking only at component scanning.

### Do not overlook logs preceding the exception

Several lines immediately before the error carry very useful information:

- Active profiles.
- Which configuration class was being processed.
- Whether the DataSource or embedded server had been created.
- Which beans initialized successfully beforehand.
- Whether an auto-configuration was excluded or a property deprecated.
- Whether an external connection timeout occurred before the context failed.

Inspect enough of the log preceding the root cause. Copying only the final line can lose the sequence of events leading to the failure.

## 3. Choosing targeted logging levels

Spring Boot uses a logging facade and logging implementation per the application's dependencies; common setups may use Logback. Log levels can be adjusted in the configuration file:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.boot.autoconfigure: DEBUG
    org.springframework.context.annotation: DEBUG
    com.example.orders: DEBUG
~~~

Meaning:

- `root: INFO` keeps general logging moderate.
- `org.springframework.boot.autoconfigure: DEBUG` adds details about auto-configuration.
- `org.springframework.context.annotation: DEBUG` helps observe certain configuration and bean definition processing steps.
- `com.example.orders: DEBUG` increases detail for the business package under investigation.

Do not enable `TRACE` across all of `root` in production without understanding log volume and sensitive data exposure risks. Enable logging per required package or class, reproduce the issue, collect evidence, and restore appropriate log levels afterward.

### Changing log levels via command line

You can override properties at launch time:

~~~bash
java -jar app.jar --logging.level.org.springframework.boot.autoconfigure=DEBUG
~~~

Or set JVM/system properties suited to your launch method. Spring Boot command-line properties are a quick way to investigate without editing packaged configuration files.

With Gradle:

~~~bash
./gradlew bootRun --args='--logging.level.org.springframework.boot.autoconfigure=DEBUG'
~~~

With the Maven Spring Boot plugin:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--logging.level.org.springframework.boot.autoconfigure=DEBUG
~~~

Argument-passing syntax can depend on plugin version and configuration. When using wrappers or custom scripts, confirm the application actually received the property via startup logs or Environment.

### What does --debug do?

Spring Boot supports the flag:

~~~bash
java -jar app.jar --debug
~~~

`--debug` enables Spring Boot debug mode and prints the **conditions evaluation report** alongside related diagnostic logs. It does not mean every logger across every application package switches to DEBUG.

If you need logs for a specific package, configure `logging.level.<logger-name>`. The two mechanisms complement each other:

- `--debug`: focuses on the auto-configuration condition report and certain core loggers.
- `logging.level`: controls log levels for specific packages/classes.

It can also be enabled via configuration:

~~~yaml
debug: true
~~~

For short-term investigations, command line is usually convenient because debug changes do not have to be committed to default configuration files.

## 4. What does the conditions report answer?

Spring Boot auto-configuration relies on conditions such as:

- Whether a class is present on the classpath.
- Whether a bean already exists or not.
- Whether a property has a matching value.
- Whether the web application type is servlet or reactive.
- Whether a resource exists.
- Whether another configuration was imported.

These conditions are expressed via annotations such as:

~~~java
@ConditionalOnClass(...)
@ConditionalOnMissingBean(...)
@ConditionalOnBean(...)
@ConditionalOnProperty(...)
@ConditionalOnWebApplication(...)
@ConditionalOnResource(...)
~~~

For example, an auto-configuration may create a bean only when a library is present and the user has not supplied their own implementation:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(PaymentClient.class)
@ConditionalOnMissingBean(PaymentGateway.class)
class PaymentAutoConfiguration {

    @Bean
    PaymentGateway paymentGateway(PaymentClient client) {
        return new DefaultPaymentGateway(client);
    }
}
~~~

If the `PaymentGateway` bean does not appear, there are at least two direct hypotheses:

1. `PaymentClient` is absent from the classpath, so `@ConditionalOnClass` did not match.
2. Another `PaymentGateway` bean already exists or bean configuration was affected by another condition, so `@ConditionalOnMissingBean` did not match.

The conditions report helps determine which conditions matched or did not match.

## 5. Enabling the conditions evaluation report

The fastest way when running the application:

~~~bash
java -jar app.jar --debug
~~~

During startup, Spring Boot can print the `CONDITIONS EVALUATION REPORT` section, typically divided into:

- **Positive matches:** auto-configurations or conditions that matched.
- **Negative matches:** auto-configurations not applied because conditions did not match.
- **Exclusions:** excluded auto-configurations.
- **Unconditional classes:** configurations independent of conditions according to the report.

Illustrative example:

~~~text
CONDITIONS EVALUATION REPORT

Positive matches:

   DataSourceAutoConfiguration matched:
      - @ConditionalOnClass found required classes
      - @ConditionalOnMissingBean did not find a bean of type DataSource

Negative matches:

   MongoAutoConfiguration:
      Did not match:
         - @ConditionalOnClass did not find
           'com.mongodb.client.MongoClient'

   WebMvcAutoConfiguration:
      Did not match:
         - @ConditionalOnWebApplication did not find
           a servlet web application
~~~

This is illustrative output to explain how to read it; actual condition names, contents, and formats depend on Boot version, dependencies, and application.

### Reading positive matches

A positive match shows a configuration passed the reported conditions. It **does not guarantee all beans inside the configuration initialized successfully**.

For example, `DataSourceAutoConfiguration` matched, yet creating the DataSource can still fail due to a missing URL, driver, credentials, or unreachable database. In that case, read the exception and bean creation logs.

### Reading negative matches

A negative match is often the clue when a default bean is missing.

Example:

~~~text
SomeAutoConfiguration:
   Did not match:
      - @ConditionalOnProperty (feature.enabled=true)
        found different value
~~~

Check:

- Is the property name right?
- Was the value overridden by an environment variable or command-line argument?
- Did a profile change the configuration file?
- Does the property sit in an inactive YAML document?
- Is there a difference in prefix or relaxed binding?

Do not rush to edit the condition annotation if a property source is supplying an unexpected value.

### Reading exclusions

An auto-configuration can be excluded via:

~~~java
@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class
)
public class Application {
}
~~~

Or via property:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

If the conditions report states an auto-configuration was excluded, find where the exclusion is configured. Adding a database dependency will not fix it if the auto-configuration itself was excluded from evaluation.

## 6. The conditions report is not a dependency report

The two reports are frequently confused:

| Tool | Question answered |
|---|---|
| Conditions evaluation report | Why did Spring Boot select or skip an auto-configuration? |
| Dependency tree | Which libraries did the build tool resolve, from where, and at what version? |
| ApplicationContext/beans report | Which beans were actually created in the context? |
| Runtime logs | What happened when beans or the application initialized? |

For example, the conditions report says `@ConditionalOnClass` did not match because `com.example.PaymentClient` was missing. The dependency tree can confirm the library containing that class was never put on the runtime classpath.

Conversely, a dependency tree showing a JAR is present does not prove Spring created a bean from that JAR. Component scanning, auto-configuration imports, profiles, and conditions still govern whether the bean gets registered.

### The conditions report in Actuator

If the application has Actuator and the version supports the conditions endpoint, you can inspect the report at:

~~~text
GET /actuator/conditions
~~~

This endpoint must be created, enabled, and exposed over HTTP or the appropriate transport; callers must also have access permissions. It does not appear automatically merely by adding the Actuator starter.

Exposure example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
~~~

The conditions endpoint can reveal information about the application's configuration structure and libraries. Expose it only to appropriate environments and operators, paired with authentication/authorization; do not open every Actuator endpoint merely to investigate one bug.

In certain versions or configurations, other inspection endpoints such as `beans`, `env`, or `configprops` can help determine actual state. These endpoints also require protection because they can expose sensitive information.

## 7. Dependency tree: checking the classpath resolved by the build tool

When an error involves classes or methods, inspect the dependency graph instead of guessing versions from build files.

A dependency tree shows:

- Direct dependencies and transitive dependencies.
- Which path pulled a library in.
- Which version was chosen after conflict resolution.
- Which scope/configuration a dependency belongs to.
- Whether a library was excluded.

Suppose the application declares:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'com.example:payment-adapter:2.0.0'
}
~~~

`payment-adapter` may pull in a different version of a client library that the application also uses directly. The build tool selects a version per resolution rules; the version written in one declaration line is not always the final version on the runtime classpath.

This is why you must inspect the **resolved graph**.

## 8. Maven dependency:tree

With Maven, the dependency plugin provides the goal:

~~~bash
mvn dependency:tree
~~~

Increase detail with:

~~~bash
mvn dependency:tree -Dverbose
~~~

Filter for a dependency:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-core
~~~

Filter by specific group/artifact:

~~~bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

When inspecting a specific scope, you can use arguments supported by the dependency plugin version in use, for example:

~~~bash
mvn dependency:tree -Dscope=runtime
~~~

Abbreviated output example:

~~~text
com.example:catalog-service:jar:1.0.0
+- org.springframework.boot:spring-boot-starter-web:jar:...
|  +- org.springframework.boot:spring-boot-starter:jar:...
|  |  +- org.springframework:spring-core:jar:...
|  |  - org.springframework:spring-context:jar:...
|  - org.springframework.boot:spring-boot-starter-json:jar:...
- com.example:payment-adapter:jar:2.0.0
   - com.fasterxml.jackson.core:jackson-databind:jar:...
~~~

This illustrative output shows dependencies can arrive from multiple branches. If the same artifact appears with different versions, inspect the conflict/omitted entries to see which version Maven chose.

### Using effective POM to understand dependency management

Maven can manage versions via a parent POM or BOM. When a dependency does not declare a version directly, inspect the effective POM:

~~~bash
mvn help:effective-pom
~~~

This command shows the configuration after parent inheritance, profile application, and merging relevant sections.

Distinguish:

- `dependencyManagement` manages default versions/scopes when a dependency is declared.
- `dependencies` declares the module's actual dependencies.
- Maven profiles can change the effective POM and dependency graph.
- The dependency tree reflects dependencies resolved for the current project.

If a dependency is absent from the tree, adding a version to `dependencyManagement` alone will not necessarily make it appear; the module must still declare the dependency or inherit it from an appropriate configuration.

## 9. Gradle dependencies and dependencyInsight

With Gradle, the general command is:

~~~bash
./gradlew dependencies
~~~

For a Spring Boot application, inspect the appropriate configuration. Examples:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

The three configurations can differ:

- `compileClasspath`: what is needed to compile main sources.
- `runtimeClasspath`: what is needed when running the application.
- `testRuntimeClasspath`: what is needed when running tests.

If an error appears only when running the executable JAR, `runtimeClasspath` usually matters more than compile classpath.

To investigate a specific dependency:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Or:

~~~bash
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Gradle can show the selected version, dependency paths leading to it, and resolution reasons such as version constraints, conflict resolution, or build-applied rules.

### Example of reading dependencyInsight

Illustrative output:

~~~text
org.springframework:spring-core:6.x.y
   Selection reasons:
      - By constraint
      - By conflict resolution

org.springframework:spring-core:6.x.y
--- org.springframework:spring-context:6.x.y
     --- runtimeClasspath
~~~

If one library pulls an older version yet Gradle selects a newer version, identify what introduced the constraint or rule. Do not add a dependency of the same name with a newer version merely to "force" a green build without understanding compatibility.

### Inspecting test configurations

A library may exist on `runtimeClasspath` yet be missing from `testRuntimeClasspath` if configurations or variants differ. If the error occurs only in tests, inspect the test configuration directly.

Do not assume every Gradle configuration has the same dependency graph. An application can compile successfully yet lack a provider at test runtime, or pass tests while the executable archive misses a runtime dependency.

## 10. Understanding common dependency errors

Certain exceptions point clearly to the kind of problem to look for.

| Error | Common meaning | Where to investigate |
|---|---|---|
| `ClassNotFoundException` | A class was requested yet the classloader could not find it | Runtime classpath, scopes, packaging |
| `NoClassDefFoundError` | The JVM cannot use a required class at runtime; either missing or failed initialization earlier | Dependency tree, first failure cause, classloader |
| `NoSuchMethodError` | Class is present yet the method does not exist in the loaded version | Version conflicts, dependency alignment |
| `NoSuchFieldError` | Expected field does not exist in the loaded class | Version mismatch |
| `NoSuchBeanDefinitionException` | Spring cannot find a matching bean | Component scan, conditions, profiles, bean registration |
| `NoUniqueBeanDefinitionException` | Multiple matching beans without a unique choice | `@Primary`, `@Qualifier`, conditions |
| `BeanCreationException` | Creating a bean failed | Nested cause, constructors, factory methods, configuration |
| `UnsatisfiedDependencyException` | Cannot resolve a bean's dependency | Bean graph and root cause |
| `NoSuchBeanDefinitionException` from auto-config | Conditions or user-defined beans do not match | Conditions report, classpath, properties |

### ClassNotFoundException

Example:

~~~text
java.lang.ClassNotFoundException: com.example.payment.PaymentClient
~~~

The class may be missing from the runtime classpath, its dependency excluded, declared compile-only, or the executable archive may lack the corresponding JAR.

Check Gradle:

~~~bash
./gradlew dependencyInsight --dependency payment-client --configuration runtimeClasspath
~~~

Check Maven:

~~~bash
mvn dependency:tree -Dincludes=com.example:payment-client
~~~

If the dependency appears in the tree yet the class is still missing, verify whether that exact JAR contains the class, whether the artifact uses the right classifier/variant, and whether the classloader is using a different archive.

### NoSuchMethodError

Example:

~~~text
java.lang.NoSuchMethodError:
  'void com.example.client.ApiClient.setTimeout(...)'
~~~

This error typically indicates code was compiled against one API version while runtime loaded the class from another version lacking that method.

Investigation:

1. Identify which artifact supplies the loaded class.
2. Check versions on compile classpath and runtime classpath.
3. Find which dependency pulls in the different version.
4. Check the BOM or dependency constraints.
5. Align versions per the framework/library compatibility matrix.

Simply adding a new JAR to the build may not fix it if the older version still wins resolution or duplicate classes exist.

## 11. Version alignment with the Spring Boot BOM

Spring Boot provides dependency management so ecosystem libraries have mutually compatible versions. When using the Spring Boot parent or BOM, leverage managed versions rather than pinning individual Spring modules arbitrarily.

Maven with parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version><!-- Spring Boot version --></version>
    <relativePath/>
</parent>
~~~

Or import the BOM when using a different parent:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version><!-- Spring Boot version --></version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Gradle native BOM support:

~~~groovy
dependencies {
    implementation platform(
        "org.springframework.boot:spring-boot-dependencies:<spring-boot-version>"
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Version placeholders must be replaced with the Spring Boot version the project actively uses.

Do not upgrade `spring-core`, `spring-context`, or another Spring Framework module out of step with the Boot-managed version line without a clear compatibility reason. A dependency tree helps spot version skew, while the fix should be guided by ecosystem-wide version alignment and compatibility.

### Dependency convergence and exclusions

When two dependencies pull different versions of the same artifact, the build tool must pick one version under resolution rules. Resolution succeeding does not guarantee all libraries are compatible with the chosen version.

When an exclusion is needed:

~~~groovy
dependencies {
    implementation('com.example:legacy-adapter:1.4.0') {
        exclude group: 'commons-logging', module: 'commons-logging'
    }
}
~~~

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-adapter</artifactId>
    <version>1.4.0</version>
    <exclusions>
        <exclusion>
            <groupId>commons-logging</groupId>
            <artifactId>commons-logging</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Exclude only after confirming that the dependency is genuinely unnecessary or replaced by a compatible implementation. Careless exclusions can turn an obvious conflict into an obscure runtime failure.

## 12. Connecting the conditions report to the dependency tree

This is the key step where the two reports reinforce each other.

Suppose the startup log reports that the `PaymentGateway` bean is missing. The conditions report displays:

~~~text
PaymentAutoConfiguration:
   Did not match:
      - @ConditionalOnClass did not find
        'com.example.payment.PaymentClient'
~~~

From here, move to the dependency tree:

**Maven**

~~~bash
mvn dependency:tree -Dincludes=com.example:payment-client
~~~

**Gradle**

~~~bash
./gradlew dependencyInsight --dependency payment-client --configuration runtimeClasspath
~~~

You may find one of these cases:

- No artifact present: the dependency was never declared.
- Artifact present at compile yet missing at runtime: wrong scope/configuration.
- Artifact present with wrong version/classifier: expected class does not exist.
- Dependency excluded or wrong variant chosen.
- Dependency present yet another auto-configuration condition failed to match.

If the dependency tree confirms the right artifact and class are present, move on to other conditions such as `@ConditionalOnProperty`, `@ConditionalOnBean`, profiles, or auto-configuration imports.

Do not repeat adding the same dependency multiple times when the condition is actually blocked by a property or another bean.

## 13. From the conditions report to actual configuration

Suppose the report states:

~~~text
FeatureAutoConfiguration:
   Did not match:
      - @ConditionalOnProperty
        (app.feature.enabled=true) found different value
~~~

Inspect effective configuration sources:

- `application.yml` on the classpath.
- `application-{profile}.yml`.
- Files outside the JAR.
- Environment variables.
- Java system properties.
- Command-line arguments.
- Test properties or programmatic configuration.

For example, a default file has:

~~~yaml
app:
  feature:
    enabled: false
~~~

Yet the deployment environment sets:

~~~bash
APP_FEATURE_ENABLED=true
~~~

or vice versa. A higher-precedence property source can override values from the file.

You can raise log levels for configuration packages and use Actuator `env`/`configprops` if the application configures, exposes, and secures them properly. Do not expose these endpoints publicly just for investigative convenience, as they can reveal configuration details and sensitive values.

### Profiles are also conditions

A bean may be declared as:

~~~java
@Component
@Profile("production")
public class ProductionPaymentGateway implements PaymentGateway {
}
~~~

If the application runs with profile `prod` instead of `production`, this bean is not registered. The conditions report can help spot affected configurations, while startup logs show the actual active profiles.

Verify the exact profile name and where it is activated. Maven `-Pprod` or Gradle `-PtargetEnv=prod` does not automatically activate Spring profile `prod`.

## 14. Reproduction tests: turning a hypothesis into a small test

Once logs, the conditions report, and the dependency tree yield a hypothesis, write a test that reproduces the bug without needing the whole environment unless necessary.

Hypothesis example:

> Auto-configuration only creates `PaymentGateway` when `app.payment.enabled=true` and `PaymentClient` is on the classpath.

You can use `ApplicationContextRunner` to test auto-configuration conditions in a lightweight context.

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            PaymentAutoConfiguration.class
                    ));

    @Test
    void createsGatewayWhenFeatureIsEnabled() {
        contextRunner
                .withPropertyValues("app.payment.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(PaymentGateway.class);
                });
    }

    @Test
    void doesNotCreateGatewayWhenFeatureIsDisabled() {
        contextRunner
                .withPropertyValues("app.payment.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(PaymentGateway.class);
                });
    }
}
~~~

This is an illustrative example; real auto-configuration needs the corresponding classes and dependencies. If conditions include `@ConditionalOnClass`, the test classpath must be configured appropriately to verify both presence and absence of the class.

### Why is ApplicationContextRunner useful?

It lets you:

- Spin up a small context per test.
- Supply properties via `withPropertyValues`.
- Register targeted configurations or auto-configurations.
- Assert presence/absence of beans.
- Observe context startup failures.
- Avoid starting web servers, databases, and the whole application when unnecessary.

Each `run(...)` call creates an isolated context for its scenario. Tests do not depend on an earlier test to mutate profile or bean state.

### Testing startup failures

Example when required configuration is missing:

~~~java
@Test
void failsWhenRequiredPropertyIsMissing() {
    new ApplicationContextRunner()
            .withUserConfiguration(PaymentClientConfiguration.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure()).isNotNull();
            });
}
~~~

This test confirms the context fails when required configuration is absent. If you need to verify the exact exception type or property name, walk the cause chain and assert stable details; avoid coupling tests to full stack traces whose formatting can shift across framework versions.

## 15. Choosing tests matched to the failure scope

Not every Spring Boot bug calls for `@SpringBootTest`.

| Issue to reproduce | Suitable test type |
|---|---|
| Pure service logic | JUnit + Mockito/fakes, without Spring |
| Auto-configuration conditions | `ApplicationContextRunner` |
| Application-wide bean wiring | `@SpringBootTest` or scoped context test |
| MVC mapping and serialization | `@WebMvcTest` |
| JPA repositories and mappings | `@DataJpaTest` |
| JSON serialization | `@JsonTest` |
| HTTP client adapters | Mock server or suitable `@RestClientTest` |
| Real database interaction | Integration test with dedicated test database/Testcontainers |
| Multiple components working together | Integration or end-to-end test |

A smaller test usually makes the root cause clearer. Still, if the bug depends on AOP proxies, servlet containers, transaction managers, or integrated auto-configuration, pure unit tests cannot fully verify that behavior. Pick test scope according to the suspected mechanism.

### @WebMvcTest

Example:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTests {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    void returnsOrder() throws Exception {
        // Stub service and verify HTTP response.
    }
}
~~~

`@MockitoBean` exists in newer Spring Framework versions; older Spring Boot projects can use `@MockBean`. Choose the annotation matching the version in use.

This test slice focuses on MVC infrastructure and the specified controller. It is not meant to verify the entire database or every application service integration.

### @DataJpaTest

Example:

~~~java
@DataJpaTest
class OrderRepositoryTests {

    @Autowired
    OrderRepository repository;

    @Test
    void persistsOrder() {
        // Create entity, save, and read back.
    }
}
~~~

This test slice focuses on JPA components. Depending on dependencies and configuration, Spring Boot may choose an embedded database instead of the production database; if you need to verify behavior on the exact engine, configure a matching test database or use Testcontainers.

## 16. Using tests to confirm dependency problems

If the dependency graph hints at a version conflict, do not merely write a mock test proving a service invokes a collaborator. Mock tests do not load real implementation classes, so they can miss `NoSuchMethodError` or linkage errors.

You need to test at the layer that exercises the real dependency:

- Build an ApplicationContext containing the required auto-configurations.
- Execute a narrow code path through the library's API.
- Run the test with a runtime classpath matching deployment.
- For packaging-only errors, run the executable archive or a smoke test on the built artifact.

For example, if an error occurs when running the JAR yet passes in IDE tests, compile/runtime classpaths or packaging may differ. An integration test on Gradle's test classpath does not guarantee the executable JAR contains all required dependencies.

For binary compatibility bugs, tests should instantiate and call the exact failing method against the resolved version rather than merely checking a bean exists.

## 17. Integration testing external dependencies

If the hypothesized root cause lies in an adapter calling HTTP or a database, test **that adapter** against controllable test infrastructure.

HTTP example:

~~~text
Service unit test
    |
    +--> Mock RoomAvailabilityPort
    |
    v
Verify reservation business logic

Adapter integration test
    |
    +--> Real HttpRoomAvailabilityAdapter
    |
    +--> Mock HTTP server on dynamic port
    |
    v
Verify URL, headers, JSON, timeouts, and HTTP errors
~~~

A mock server helps reproduce specific responses:

- HTTP 200 with valid JSON.
- HTTP 404 or 409.
- HTTP 500.
- Timeouts or connection refused.
- Payloads violating schema.

Tests avoid calling staging/production APIs, avoid personal credentials, and avoid real service rate limits.

When contract checks between two systems are needed, use dedicated contract tests. Business service unit tests should not be dragged into performing that role.

## 18. Using Testcontainers when a real database or broker is needed

Some bugs appear only against a real database engine: SQL dialect, locking, indexes, transaction isolation, constraints, or migrations. Mock repositories are insufficient in those cases.

Testcontainers can spin up dedicated database/broker containers for integration tests:

~~~text
Test setup
    |
    v
Start PostgreSQL test container
    |
    v
Spring context + real repository
    |
    v
Execute query / transaction
    |
    v
Assert result
    |
    v
Stop container and clean test data
~~~

Testcontainers increases realism yet slows down tests and requires Docker or a compatible container runtime in the execution environment. Use it only when real infrastructure is part of the question being verified.

If a failure comes from an unrelated external service, spinning up a container for that service expands scope without solving the design issue. Start only the services the test genuinely needs.

## 19. Reproducing the exact profiles and properties of the failing environment

A reproduction test must use the relevant properties and profiles. If production fails when profile `prod` is active, a test running only with the default profile may fail to reproduce it.

With integration tests:

~~~java
@SpringBootTest(properties = {
        "app.payment.enabled=true",
        "app.payment.timeout=2s"
})
@ActiveProfiles("test")
class PaymentStartupTests {
}
~~~

Or use `@DynamicPropertySource` to supply the runtime address of a container:

~~~java
@DynamicPropertySource
static void paymentProperties(DynamicPropertyRegistry registry) {
    registry.add("app.payment.base-url", mockServer::getUrl);
}
~~~

This snippet assumes the mock server and its corresponding lifecycle are declared. `@DynamicPropertySource` is useful when a property is only known after test infrastructure starts, such as a dynamic port from Testcontainers or a mock server.

When reproducing issues from live environments, never copy production secrets into tests. Substitute structurally equivalent test values, or use dedicated credentials with limited permissions.

## 20. Confirming which properties are actually effective

A common culprit is that tests and the application receive different properties despite sharing configuration files.

Spring Boot has multiple property sources, such as:

- Config Data on the classpath.
- External Config Data.
- Environment variables.
- JVM system properties.
- Command-line arguments.
- Test properties and dynamic properties.

Values from higher-precedence sources can override values from lower-precedence sources.

Example:

~~~yaml
app:
  payment:
    enabled: false
~~~

Yet the test runs:

~~~java
@SpringBootTest(properties = "app.payment.enabled=true")
~~~

so the test override can cause auto-configuration to match, differing from the default environment.

To inspect effective values, you can use `Environment` directly in a test:

~~~java
@Autowired
Environment environment;

@Test
void printsEffectiveFlag() {
    assertEquals(
            "true",
            environment.getProperty("app.payment.enabled")
    );
}
~~~

Do not use tests solely to print values without asserting anything. Turn expected values into meaningful assertions and supply explicit test properties.

## 21. Reproducing a bug does not mean hardcoding workarounds into tests

When investigating failures, you might test adding a property, excluding an auto-configuration, or swapping a dependency to validate a hypothesis. Still, distinguish:

- **Test reproducer:** minimizes inputs to reproduce the failure.
- **Fix:** changes code, dependencies, or configuration to resolve the root cause.
- **Regression test:** retains the reproduction conditions to verify the bug does not return.

For example, if a bean failed to appear because of a misspelled property name, the regression test should assert the proper property name and value activate the bean. Do not add a mock bean workaround just to make the test pass when the goal is verifying auto-configuration.

If the fault is a version conflict, the test must run against the fixed dependency graph and exercise the failing API. Do not exclude an unrelated library merely to shorten the dependency tree.

## 22. Diagnostic workflow combining all four sources

A practical workflow proceeds as follows.

### Step 1 — Gather symptoms

Record the command, environment, profiles, versions, and timing of failure. Keep logs around the first exception and the full necessary cause chain.

### Step 2 — Enable targeted diagnostics

Re-run with `--debug` to capture the conditions report. When necessary, raise loggers for relevant packages instead of enabling system-wide TRACE.

### Step 3 — Find unmatched conditions

Identify which auto-configuration or bean should have appeared. Inspect positive/negative matches, exclusions, and property conditions.

### Step 4 — Verify the classpath

If the report cites a missing class or logs show linkage errors, run Maven `dependency:tree` or Gradle `dependencyInsight` on the exact configuration. Inspect runtime classpaths, not just compile classpaths.

### Step 5 — Cross-check effective configuration

Check active profiles, property sources, external files, and environment variables. Verify the condition receives the expected value.

### Step 6 — Write a minimal reproducer

Pick `ApplicationContextRunner` for auto-configurations, unit tests for business logic, slice tests for MVC/JPA, or integration tests for real dependencies.

### Step 7 — Confirm the root cause

The test must fail under the error conditions and pass once the fix is applied. If the test cannot reproduce the bug, revisit your hypothesis or environment differences.

### Step 8 — Run regression tests and inspect the artifact

Run targeted tests, then related tests. For runtime/packaging issues, verify the dependency graph and execute the packaged artifact the same way it is deployed.

### Step 9 — Document the evidence

Record clearly:

- Initial symptom.
- Failing condition or dependency.
- Confirmed root cause.
- Applied fix.
- Before/after reproduction tests.
- Versions and environments verified.

This evidence helps others understand why changes were made rather than seeing only an added dependency or a modified property.

## 23. Complete investigation example: bean not auto-configured

Suppose the application needs a `PaymentGateway` bean, yet startup reports a missing bean.

**Log:**

~~~text
Parameter 0 of constructor in CheckoutService
required a bean of type PaymentGateway that could not be found.
~~~

**Conditions report:**

~~~text
PaymentAutoConfiguration did not match:
   @ConditionalOnClass did not find
   'com.example.payment.PaymentClient'
~~~

**Maven dependency tree:**

~~~bash
mvn dependency:tree -Dincludes=com.example:payment-client
~~~

No matching dependency appears. In the POM, the adapter was only declared inside a Maven profile not activated in this environment.

**Hypothesis:** the runtime artifact lacks the payment client library due to a build profile or dependency scope.

**Reproducer:** create a context test with the auto-configuration and verify the bean does not appear when the classpath lacks the dependency; then add the dependency in a suitable test fixture and verify the class condition matches. For a real third-party library, tests should use the actual artifact rather than inventing a dummy class of the same name.

**Fix:** move the dependency onto the application module's runtime classpath using a version controlled by dependency management.

**Regression test:** initialize the context and verify `PaymentGateway` is registered under required config; also check the runtime dependency graph in the build.

This evidence chain—logs -> conditions -> dependency tree -> reproducer—explains the exact cause. Manually adding a dummy bean might silence the startup error while leaving the real adapter missing.

## 24. Version conflict investigation example: NoSuchMethodError

Suppose the application starts, yet handling a request triggers:

~~~text
java.lang.NoSuchMethodError:
  com.example.json.JsonMapper.configure(...)
~~~

**Log:** identifies the missing class and method.

**Dependency tree:** reveals two dependencies pulling in different versions of `json-core`.

**DependencyInsight:** shows which version Gradle picked and why.

**Hypothesis:** code compiled against a newer API yet runtime loaded an older API or an incompatible variant.

**Reproducer:** write a test/integration test calling the exact API via the real dependency, running on the same runtime classpath as the application.

**Fix:** align versions via the BOM or compatible constraints, remove unnecessary manual version pins, then run tests and the executable artifact.

Do not simply add a newer dependency version without checking conflict resolution. The build might still pick the older version due to constraints or dependency management.

## 25. Context-loading test failure investigation example

Suppose `@SpringBootTest` fails while creating `AnalyticsClient` because it cannot reach an external endpoint—even though the test checks order total calculation rules.

Evidence:

- Logs show the error occurred in `AnalyticsClient` during startup.
- The conditions report shows analytics auto-configuration is enabled by a property.
- The dependency tree shows the analytics SDK is present.
- The test source does not use analytics in the business logic under test.

The root cause is not necessarily a bug in the total-calculation service. **The context scope is pulling an unrelated integration into the test.**

Options to handle it:

- Unit test the service directly with constructor injection and fake/mock collaborators.
- Use a test slice or narrower context test.
- Configure the test to disable analytics if the application supports that option.
- Replace the analytics adapter with a deterministic test bean if the context still needs the collaborator.

If the goal is to test analytics integration, write a dedicated test with a mock server or SDK test environment. Do not make order-calculation tests depend on analytics uptime.

## 26. Supporting tools when more evidence is needed

The four main sources can be supplemented by tools suited to the question.

| Tool | When to use |
|---|---|
| Actuator `conditions` | Inspect auto-configuration conditions in a running app, if enabled and exposed |
| Actuator `beans` | Determine which beans actually exist |
| Actuator `env` | Observe property sources and effective values, with proper protection |
| Actuator `configprops` | Inspect `@ConfigurationProperties` binding |
| Actuator `loggers` | Observe or adjust runtime log levels when permitted |
| `jdeps` | Analyze Java dependencies at bytecode/module level |
| `jar tf` | Inspect packaged archive contents |
| Build scan | Analyze Gradle dependency resolution and build performance when configured |
| Thread dump | Investigate deadlocks, thread starvation, or hung tasks |
| Testcontainers | Reproduce integrations requiring real databases/brokers |

You do not need to run every tool for every error. Choose according to your hypothesis: inspect conditions for auto-configuration bugs; dependency graphs and archives for linkage errors; narrow contexts and reproducers for test context failures.

### Inspecting executable JAR contents

If the application runs from a JAR, inspect it with:

~~~bash
jar tf build/libs/app.jar
~~~

For a Spring Boot executable JAR, look for sections such as `BOOT-INF/classes/` and `BOOT-INF/lib/`. A dependency present on the compile classpath is not guaranteed to be packaged properly; checking the archive confirms packaging results.

### Inspecting Java dependencies

`jdeps` ships with the JDK and can analyze class/module dependencies at bytecode level:

~~~bash
jdeps --summary build/libs/app.jar
~~~

Analyzing nested dependencies inside Spring Boot executable archives has limitations depending on archive layout and tool version. Do not treat `jdeps` as a replacement for Maven/Gradle dependency trees; the two tools inspect different layers.

## 27. Security when collecting and sharing diagnostics

Logs, conditions reports, and Actuator can contain sensitive system information:

- Internal class, bean, and package names.
- File paths and hostnames.
- Property keys, URLs, or connection metadata.
- Stack traces containing request data.
- Dependencies and versions in use.
- Internal infrastructure details.

Before sharing logs or reports outside the team, scrub passwords, tokens, cookies, private keys, personal data, and other sensitive details. Never publicly expose `env`, `configprops`, `beans`, or `conditions` endpoints merely for debugging convenience.

Enabling DEBUG/TRACE can also increase log volume and reveal values that should never be logged. Enable them only for the necessary scope, limit duration, retain per policy, and turn them off once the investigation concludes.

In production, prefer accessing diagnostics through operational channels with clear authentication, authorization, and network policies.

## 28. Common mistakes

### Looking only at the outermost exception

The outermost exception may only tell you which bean failed to create. The root cause might be a wrong property, missing dependency, database timeout, or constructor exception. Follow the cause chain and the logs preceding the error.

### Enabling DEBUG across the entire application

This can flood logs and obscure critical information. Enable logging per relevant package or logger; use `--debug` for the conditions report.

### Seeing a dependency in build source and assuming runtime has it

Declarations in a build file may be compile-only, test-only, optional, inside an inactive profile, or excluded. Check the actual runtime configuration and executable archive.

### Seeing a class present and concluding auto-configuration must match

`@ConditionalOnClass` is just one of many conditions. Properties, beans, web application type, resources, and exclusions can still stop a configuration from applying.

### Adding dependencies randomly to fix NoClassDefFoundError

New dependencies can worsen version conflicts. Identify which artifact owns the class and trace dependency paths before making changes.

### Using @SpringBootTest for every reproducer

A full context can drag many unrelated integrations into tests. Choose unit tests, `ApplicationContextRunner`, or test slices whenever they suffice to test your hypothesis.

### Checking green tests without running the real artifact

Bugs can surface only inside the executable JAR due to runtime classpath/packaging differences. When symptoms happen after deployment, verify the archive and the matching launch method.

### Fixing bugs by excluding auto-configurations without understanding consequences

Excluding may let the app start while silently dropping DataSource, web infrastructure, or a needed integration. Only exclude when the architecture genuinely does not need that configuration and tests prove it.

### Re-running tests until they pass

A flaky test can pass by chance. Rerunning only gathers more evidence; find the shared state, race condition, timing, or external dependency causing instability.

## 29. Template for recording an investigation

A brief record can follow this structure:

~~~text
Symptom:
  Application startup fails with UnsatisfiedDependencyException.

Environment:
  Java:
  Spring Boot:
  Build tool:
  Active profiles:
  Command:

Log evidence:
  First relevant exception:
  Root cause:
  Related startup messages:

Conditions report:
  Auto-configuration:
  Positive/negative condition:
  Exclusions:

Dependency evidence:
  Artifact:
  Selected version:
  Dependency path:
  Runtime scope/configuration:

Reproducer:
  Test class:
  Minimal properties:
  Expected result:
  Actual result:

Root cause:
  ...

Fix:
  ...

Regression evidence:
  Test command:
  Result:
  Packaged artifact check:
~~~

This template lets readers verify the evidence rather than guessing from a one-line "fixed dependency" note.

## 30. Summary workflow

When a Spring Boot issue is hard to pin down, move from broad evidence to a narrow reproducer:

1. Describe the symptom and pinpoint the stage of failure.
2. Read startup/runtime logs, stack traces, and cause chains.
3. Enable `--debug` to capture the conditions evaluation report; raise targeted loggers if needed.
4. Identify the unmatched auto-configuration, bean, or property condition.
5. Check Maven's dependency tree or Gradle's dependencyInsight on the right compile/runtime/test configuration.
6. Cross-check versions, scopes, profiles, and property sources against the failing environment.
7. Write a small reproducer via unit tests, `ApplicationContextRunner`, test slices, or integration tests as suited to the mechanism.
8. Apply the root-cause fix and keep the regression test.
9. If the bug only happens when packaged, inspect the archive and run the actual executable artifact.
10. Record evidence, dial back debug logging, and protect sensitive information.

**Logs tell you what happened; the conditions report tells you why Spring selected or skipped configuration; the dependency tree shows how compile/runtime classpaths were assembled; reproduction tests verify the hypothesis and keep the bug from returning.** Combining all four sources against the right questions produces evidence-backed diagnosis, avoids random edits, and yields a verifiable fix.
