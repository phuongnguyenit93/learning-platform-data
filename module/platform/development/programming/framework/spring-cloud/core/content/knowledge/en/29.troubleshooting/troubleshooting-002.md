# Bean Not Found Even After Adding Starter

> **Chapter:** Troubleshooting
> **Module:** `SPRING_CLOUD_CORE` — understand the core foundations of Spring Cloud in distributed systems, especially Spring Cloud Commons, Context, externalized configuration, and version compatibility with Spring Boot. Learners explore refresh scope, discovery, service registry, service communication, and how to test and operate common abstractions.
> **Focus:** Adding a starter to the build does not guarantee a bean will appear in the ApplicationContext. This lesson guides you through tracing runtime dependencies, auto-configuration discovery mechanisms, bean creation conditions, component scanning, profiles, and version compatibility; then using ConditionEvaluationReport, Actuator conditions, and small context tests to pinpoint exactly why a bean is not registered.

## 1. Understanding Bean Not Found Errors

A Spring Boot application may compile successfully after adding a starter yet still fail at runtime:

```text
NoSuchBeanDefinitionException:
No qualifying bean of type 'com.example.PaymentClient' available
```

Or the exception may be wrapped inside UnsatisfiedDependencyException while Spring is creating another bean.

This does not necessarily mean the dependency was not downloaded. The library may already be on the classpath, but Spring does not create the bean because auto-configuration has not been loaded, conditions do not match, user configuration falls outside the scan scope, or a property/profile disables the feature.

Three layers must be distinguished:

1. **Dependency present on runtime classpath:** the JVM can load the required classes.
2. **Configuration discovered by Spring:** auto-configuration or user configuration is included in the ApplicationContext creation process.
3. **Bean registered:** the conditions on the configuration/bean method are all satisfied and no other mechanism causes the bean to be excluded.

A starter primarily packages commonly used dependencies. Auto-configuration defines how to create beans and the required conditions. With Spring Cloud, a starter for a general abstraction may also not be the starter for the specific implementation the application expects.

### Learning Outcomes

After this lesson, learners can:

1. distinguish missing beans from missing runtime dependency errors;
2. inspect actual dependencies on the runtime classpath;
3. understand the roles of starters, auto-configuration, and auto-configuration registration files;
4. read Conditional annotations that prevent a bean from being created;
5. inspect component scanning and ConfigurationPropertiesScan;
6. distinguish Spring Cloud abstractions from implementations for Eureka, Consul, or other providers;
7. identify auto-configurations that are excluded or backing off;
8. inspect profiles, properties, and web application type;
9. diagnose Spring Boot/Spring Cloud version conflicts;
10. use ConditionEvaluationReport and ApplicationContextRunner to reproduce the issue.

## 2. Distinguishing Error Types

| Error | Common Meaning | First Check |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | No bean matching the requested type or name exists | Bean definitions, component scan, auto-configuration, and conditions |
| `NoUniqueBeanDefinitionException` | Multiple matching beans exist and which one to use is ambiguous | Primary, Qualifier, bean names, and implementations |
| `UnsatisfiedDependencyException` | A bean cannot be created because its dependency could not be resolved | Read the root cause inside the exception |
| `BeanCreationException` | Bean was selected for creation but failed during initialization | Constructor, Bean method, lifecycle, and nested cause |
| `ClassNotFoundException` | Class is missing from the class loader at invocation time | Runtime dependency, scope, packaging, and classpath |
| `NoClassDefFoundError` | JVM cannot define or link a required class | Runtime dependency, static initializer failure, and root cause |
| `BeanCurrentlyInCreationException` | Circular dependency or referencing a bean while creation is incomplete | Dependency cycle and how configuration is split |

NoUniqueBeanDefinitionException is not a missing bean error. Adding another starter can increase the number of implementations and make the error more pronounced. Read the deepest exception and see which bean is actually being requested.

## 3. How Are Beans Created in Spring Boot?

When calling SpringApplication.run(...), Spring Boot prepares the Environment, reads configuration, determines configuration sources, and creates the ApplicationContext. During configuration processing, Spring registers user configurations and matching auto-configurations. Then the BeanFactory creates beans according to the dependency graph and lifecycle.

There are two common paths for a bean to enter the context:

- **User configuration:** the application declares Configuration, Component, Service, Repository classes, or Bean methods. These classes must be imported or lie within the component scan scope.
- **Auto-configuration:** a library provides configuration classes, Spring Boot discovers them via auto-configuration registration metadata, and conditions decide whether to apply the configuration or individual bean methods.

Adding a dependency only makes classes potentially available on the classpath. It does not guarantee configuration is discovered or bean conditions are met.

### 3.1. Starter and Auto-Configuration Are Two Separate Roles

For an in-house library, the structure is typically separated into:

```text
my-client/
├── my-client-core/
├── my-client-spring-boot-autoconfigure/
└── my-client-spring-boot-starter/
```

- core contains the client and logic independent of Spring Boot;
- autoconfigure contains AutoConfiguration, Bean, Conditional, and metadata;
- starter bundles commonly needed dependencies so users add a single dependency.

According to Spring Boot guidelines, a starter is usually a nearly empty JAR whose main purpose is to provide the appropriate dependencies. Auto-configuration is packaged in a separate module. If the starter does not pull in the auto-configuration module, the application may have the client classes without automatic beans.

### 3.2. Auto-Configuration Is Not Discovered by Component Scan

In modern Spring Boot, auto-configuration classes are listed in the file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line is the fully qualified name of an auto-configuration class. Spring Boot reads this file to find auto-configuration candidates.

For Spring Boot 3.x and 4.x, check the AutoConfiguration.imports file inside the JAR. Older projects may use legacy registration mechanisms; when upgrading, follow the documentation for the corresponding Spring Boot version.

An auto-configuration class should not rely on being picked up by component scan. It is loaded through auto-configuration metadata and often uses Import to bring specific configurations into the context.

### 3.3. Checking Whether the JAR Contains Metadata

If developing an internal starter, verify that the published JAR contains the AutoConfiguration.imports file and lists the exact class names. If the file is missing, at the wrong path, has a misspelled class name, or was lost during packaging/shading, Spring Boot will not find the auto-configuration.

If the JAR is built with a shading or assembly tool, check resource merge rules. Some plugins overwrite metadata files of the same name instead of merging lines from multiple dependencies.

## 4. Checking Runtime Dependencies

### 4.1. A Successful Build Does Not Mean the Runtime Has the Dependency

A dependency may appear on the compile classpath yet be omitted from runtime because:

- Maven uses `provided` or `test` scope;
- Gradle declares `compileOnly` instead of `implementation`/`runtimeOnly`;
- the dependency is marked `optional` and is not pulled in;
- the dependency is excluded via `exclusions`;
- the starter is in another module rather than the executable application;
- a dependency conflict selects an incompatible version;
- packaging creates a JAR/image missing the required library.

In a Spring Boot executable JAR, libraries normally reside in BOOT-INF/lib. If classes exist at compile time but runtime throws ClassNotFoundException, inspect the actual deployed artifact instead of looking only at the IDE.

### 4.2. Maven Dependency Tree

```bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.cloud
```

Inspect the starter, auto-configuration module, provider implementation, dependencies marked `omitted for conflict` or excluded, and whether Spring Cloud module versions align with the BOM.

### 4.3. Gradle Dependency Insight

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-context --configuration runtimeClasspath
```

Replace spring-cloud-context with the artifact needed by the bean, such as the module containing the discovery client implementation or auto-configuration.

Do not inspect only the `implementation` configuration in a subproject. Check the `runtimeClasspath` of the exact module that builds the executable JAR.

### 4.4. Inspecting Executable JAR Contents

```bash
jar tf target/application.jar
```

Look for BOOT-INF/lib containing dependencies, BOOT-INF/classes containing application classes, and AutoConfiguration.imports metadata inside the relevant library.

If using layered container images, inspect the dependency layer included in the image. The local artifact and the running artifact can differ due to build caches or deployment pipelines.

## 5. Confirming Auto-Configuration Is Enabled

### 5.1. The Application Must Opt In to Auto-Configuration

Typically, the main class has:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

@SpringBootApplication includes @EnableAutoConfiguration and @ComponentScan along with related defaults.

If the application creates AnnotationConfigApplicationContext directly and registers a configuration class, Spring Boot auto-configuration may not run as it does when started with SpringApplication.

In tests, @SpringBootTest creates the context via Spring Boot and is suitable when verifying actual auto-configuration behavior. A test using only @ContextConfiguration may not set up all features provided by SpringApplication.

### 5.2. Do Not Arbitrarily Declare Auto-Configuration Multiple Times

Spring Boot recommends having only one @SpringBootApplication or @EnableAutoConfiguration on the primary configuration class.

If multiple modules declare auto-configuration or multiple separate contexts are created, a bean may reside in a different context from where it is being injected. Identify the exact ApplicationContext handling requests or creating services.

### 5.3. Checking Exclusions

Auto-configuration can be excluded via annotation:

```java
@SpringBootApplication(
    exclude = PaymentClientAutoConfiguration.class
)
public class OrdersApplication {
}
```

Or via property:

```properties
spring.autoconfigure.exclude=com.acme.payment.autoconfigure.PaymentClientAutoConfiguration
```

Search both places, including profile-specific configurations and environment variables mapped to properties. If auto-configuration has been excluded, the starter may still be on the classpath, yet the bean will not be created.

## 6. Reading @Conditional Conditions

Auto-configurations usually create beans only when appropriate conditions hold. A missing bean can be intentional behavior.

| Condition | Meaning | Example Mismatch Cause |
| --- | --- | --- |
| `@ConditionalOnClass` | Required class is on the classpath | Missing implementation module or excluded dependency |
| `@ConditionalOnMissingClass` | A class must be absent | Another dependency causes this configuration branch to turn off |
| `@ConditionalOnBean` | Dependent bean already exists | Foundation bean missing or auto-configurations ordered incorrectly |
| `@ConditionalOnMissingBean` | No matching bean exists yet for auto-configuration to provide a default | Application already declared a bean of the same type, so default configuration backs off |
| `@ConditionalOnProperty` | Property has a matching value | Property set to false, wrong name, or profile not active |
| `@ConditionalOnResource` | Required resource can be found | Configuration file or resource not on classpath |
| `@ConditionalOnWebApplication` | Application has the appropriate web context type | App runs as non-web or uses reactive instead of servlet |
| `@ConditionalOnExpression` | SpEL expression evaluates to true | Missing placeholder or expression evaluates to false |

### 6.1. ConditionalOnClass

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class PaymentAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(PaymentSdk.class)
    static class PaymentSdkConfiguration {

        @Bean
        @ConditionalOnMissingBean
        PaymentClient paymentClient(PaymentSdk sdk) {
            return new PaymentClient(sdk);
        }
    }
}
```

If PaymentSdk is not on the runtime classpath, the nested configuration is not applied. Isolating branches that depend on optional classes into a separate configuration avoids forcing the JVM to resolve method signatures referencing nonexistent classes. Adding a similarly named starter that does not contain the actual SDK will not satisfy this condition.

### 6.2. ConditionalOnProperty

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

@AutoConfiguration
@ConditionalOnProperty(
    prefix = "acme.payment",
    name = "enabled",
    havingValue = "true"
)
public class PaymentAutoConfiguration {
    // Bean methods
}
```

Configuration:

```yaml
acme:
  payment:
    enabled: true
```

If the property is set to false, has the wrong prefix, or the profile containing the property is not active, the configuration will not match. Check the effective value in Environment; do not just read the default application.yml file.

If the annotation uses matchIfMissing = true, omitting the property can still be considered a match. If it is not set, check the semantics of @ConditionalOnProperty.

### 6.3. ConditionalOnBean and Auto-Configuration Ordering

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;

@AutoConfiguration
@ConditionalOnBean(PaymentTransport.class)
public class PaymentClientAutoConfiguration {
    // ...
}
```

If PaymentTransport is not registered at the time the condition is evaluated, the configuration may not be applied. For custom auto-configurations, check ordering with AutoConfigureAfter, AutoConfigureBefore, or split configurations by dependency.

Spring Boot recommends placing bean conditions on @Bean methods when appropriate because user bean definitions are already registered before auto-configuration is applied. Also declare concrete return types on @Bean methods so type-based conditions have sufficient information.

### 6.4. ConditionalOnMissingBean Is a Back-Off Mechanism

```java
@Bean
@ConditionalOnMissingBean(PaymentClient.class)
PaymentClient paymentClient() {
    return new DefaultPaymentClient();
}
```

If the application already has a PaymentClient bean, auto-configuration will not create the default bean. This is intentional replacement behavior.

To see which bean is causing auto-configuration to back off, inspect the list of beans by type and the condition report. Do not arbitrarily delete a bean before verifying whether another module is using it.

## 7. Distinguishing Component Scanning from Auto-Configuration

### 7.1. Component Outside the Root Package

Example structure:

```text
com.acme.orders
├── OrdersApplication.java
├── service
│   └── OrderService.java
└── payment
    └── PaymentClient.java
com.acme.shared.payment
└── PaymentConfiguration.java
```

If OrdersApplication is in com.acme.orders, default component scan does not automatically scan the sibling package com.acme.shared.payment.

The clearest way is to import the required configuration:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(PaymentConfiguration.class)
public class OrdersApplication {
}
```

Or expand the scan intentionally:

```java
@SpringBootApplication(
    scanBasePackages = {
        "com.acme.orders",
        "com.acme.shared.payment"
    }
)
public class OrdersApplication {
}
```

Prefer scanBasePackageClasses or @Import by class when possible to avoid string-based package dependencies.

### 7.2. Place the Main Class in the Root Package

Spring Boot recommends placing the @SpringBootApplication class in the root package above all application subpackages. This keeps component scan scoped to the project and avoids declaring long package lists.

Do not place the application class in the default package. That can cause scanning to read classes across many JARs and lead to performance issues or unintended discovery.

### 7.3. @ConfigurationProperties Does Not Automatically Become a Bean

A class annotated only with @ConfigurationProperties is not automatically picked up by component scan like a regular @Component.

It can be registered via:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
}
```

Or declared explicitly:

```java
@Configuration
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentConfiguration {
}
```

Without one of these two registration mechanisms, the @ConfigurationProperties bean may not exist even though both the class and properties are present.

### 7.4. @Bean Methods Must Belong to a Loaded Configuration

A @Bean method is not registered simply because its enclosing class is inside a JAR. That class must be discovered via import, component scan, or auto-configuration metadata.

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    PaymentClient paymentClient(PaymentProperties properties) {
        return new DefaultPaymentClient(properties);
    }
}
```

If PaymentConfiguration is outside the scan scope and not @Imported, the method will not run. Check configuration sources in the context rather than just searching for the class in source code.

## 8. A Spring Cloud Starter Does Not Equal a Provider Implementation

Spring Cloud provides many common abstractions. Some beans only exist when a specific provider is placed on the classpath.

### 8.1. DiscoveryClient and Provider-Specific DiscoveryClient

DiscoveryClient is the abstraction for looking up service instances. Spring Cloud Commons provides the abstraction and default mechanisms, while an implementation tied to a registry requires the corresponding provider module.

| Requirement | Dependency to Check |
| --- | --- |
| General discovery abstraction | spring-cloud-commons |
| Eureka DiscoveryClient | spring-cloud-starter-netflix-eureka-client |
| Consul DiscoveryClient | spring-cloud-starter-consul-discovery |
| Zookeeper DiscoveryClient | Spring Cloud Zookeeper discovery starter |

Artifact names and versions must match the release train in use. Add the proper provider starter to the runtime classpath, then check whether the provider's auto-configuration matches.

Spring Cloud Commons can supply SimpleDiscoveryClient if no service-registry-based discovery client is on the classpath. The simple client reads instance lists from properties and does not connect to Eureka or Consul.

Therefore, successfully injecting DiscoveryClient does not prove Eureka/Consul is working. Verify the actual implementation bean.

### 8.2. EnableDiscoveryClient Does Not Create a Provider Implementation

In current Spring Cloud, EnableDiscoveryClient is no longer required if the corresponding DiscoveryClient implementation is already on the classpath. This annotation does not automatically download Eureka or Consul dependencies and cannot replace a provider starter.

Discovery providers also have Spring Cloud's own registration mechanism: Commons documentation describes DiscoveryClient implementations being discovered via META-INF/spring.factories with the key org.springframework.cloud.client.discovery.EnableDiscoveryClient. This is Spring Cloud extension metadata; do not confuse it with the AutoConfiguration.imports file that Spring Boot uses to list auto-configuration classes.

### 8.3. ServiceRegistry Requires an Appropriate Provider

ServiceRegistry is the abstraction for registering/deregistering services. Implementations can be EurekaServiceRegistry, ConsulServiceRegistry, or ZookeeperServiceRegistry.

If an application injects ServiceRegistry while only adding Commons, the desired provider bean may be missing. Check the provider dependency and auto-configuration conditions. Also distinguish a missing bean error from an error where the bean is present but the registry endpoint is unreachable.

### 8.4. RefreshScope Belongs to Spring Cloud Context

RefreshScope, ContextRefresher, and refresh components belong to Spring Cloud Context. If an application needs these APIs, verify the module containing them is on the runtime classpath.

A starter for discovery or load balancing should not be assumed to pull every Context/refresh feature into the application. Choose dependencies according to the features actually used.

## 9. Profiles, Properties, and Application Type

### 9.1. Profile Not Active

A bean may be annotated:

```java
@Configuration
@Profile("production")
public class ProductionPaymentConfiguration {
    // ...
}
```

If production is not among the active profiles, the configuration is not loaded. Check spring.profiles.active, environment variables, command-line arguments, and profiles added programmatically.

You can enable profile logging at startup or inspect Actuator env/configprops if those endpoints are properly secured.

### 9.2. Property Can Be Overridden by Another Source

Suppose the local file declares:

```yaml
acme:
  payment:
    enabled: true
```

But the deployment environment sets ACME_PAYMENT_ENABLED=false. Then the condition may fail to match even though the local file looks correct.

Inspect the final value in Environment and higher-precedence property sources. Avoid inferring from a single configuration file.

### 9.3. Mismatched Web Application Type

An auto-configuration may require a servlet web application:

```java
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;

@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
```

If the application is configured with spring.main.web-application-type=reactive or none, the condition does not match.

If both Spring MVC and WebFlux are on the classpath, Spring Boot may choose MVC by default detection rules. When a reactive context is needed, explicitly configure the application type and verify dependencies do not accidentally pull in MVC.

### 9.4. Test Profile Configuration

A test slice such as WebMvcTest loads only a subset of configuration. Service beans or auto-configurations outside the slice may be absent by design.

If you need to test the entire application, use SpringBootTest. If you only want to test a specific configuration, intentionally use Import or ImportAutoConfiguration.

## 10. Checking Spring Boot and Spring Cloud Version Compatibility

Spring Cloud release trains are published to be compatible with specific Spring Boot lines. Mixing individual module versions arbitrarily can lead to:

- changed APIs or classes;
- auto-configurations no longer having the same name or package;
- dependency conflicts;
- conditions failing to match because a class is missing;
- linkage errors or NoSuchMethodError;
- application failing during compatibility verification.

Use the Spring Cloud BOM to manage versions consistently:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Then declare starters without specifying individual versions:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
</dependency>
```

With Gradle, import the BOM via platform:

```groovy
dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion")
    implementation "org.springframework.cloud:spring-cloud-starter-netflix-eureka-client"
}
```

Do not mix Spring Cloud modules from multiple release trains or manually override a core dependency just to make the build pass.

### 10.1. Compatibility Verifier

Spring Cloud Commons provides a Spring Boot compatibility check mechanism. It can be enabled with:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
```

When enabled and the Boot version is not in the set accepted by the release train, the application may fail startup with an incompatible version message.

According to Spring Cloud Commons 5.0.4 configuration properties, the verifier is disabled by default. Enable it in CI/staging or production if you want early detection of unsupported version combinations; do not mistake this default state for a recommendation to skip compatibility checking.

The spring.cloud.compatibility-verifier.compatible-boot-versions property allows declaring an accepted version range when there is a clear technical reason. Do not disable the verifier or widen the range to mask using the wrong release train.

### 10.2. How to Determine the Required Versions

1. Identify the actual Spring Boot version in the runtime dependency tree.
2. Identify the imported Spring Cloud BOM version.
3. Open the release train compatibility table on the Spring Cloud page.
4. Select a release train that supports that Boot version.
5. Remove explicit versions on individual Spring Cloud starters/modules so the BOM manages them.
6. Inspect the dependency tree after building.
7. Run the application and check the compatibility verifier if enabled.

Do not rely on an outdated version table from a blog post or an answer from years ago for a current project.

## 11. Reading ConditionEvaluationReport to See Why a Bean Is Absent

### 11.1. Enabling Debug at Startup

Fastest way:

```bash
java -jar application.jar --debug
```

Or use the JVM/system property -Ddebug. Spring Boot prints the ConditionEvaluationReport to the log, showing which auto-configurations matched and did not match.

Focus on the Positive matches, Negative matches, Exclusions, and Unconditional classes sections. Section names and formats can vary across versions, but the report still states the condition reasons.

### 11.2. Actuator Conditions Endpoint

If the application includes Actuator, the conditions endpoint exposes ConditionEvaluationReport as JSON:

```properties
management.endpoints.web.exposure.include=health,conditions
```

You can access /actuator/conditions on the management interface. Protect this endpoint because the report can reveal dependencies, configuration, and internal application structure.

Do not expose conditions publicly in production. Use a management port or an access-restricted debug environment.

### 11.3. Read the Exact Condition Instead of Searching Only by Bean Name

For example, the report may show PaymentClientAutoConfiguration did not match because PaymentSdk is not on the classpath. That is different from a case where auto-configuration matched, but ConditionalOnProperty on the bean method did not match.

Go level by level:

1. Does the auto-configuration appear in the report?
2. If so, do class-level conditions match?
3. Is the bean method processed?
4. Do method-level conditions match?
5. Is another bean causing ConditionalOnMissingBean to back off?
6. Was the bean created, yet failed in its constructor or dependency?

Do not modify properties or add dependencies before knowing which condition is failing.

## 12. Inspecting the Bean Registry Directly

If the context has started, you can inspect beans by type:

```java
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class BeanInventory {

    public BeanInventory(ApplicationContext context) {
        String[] names = context.getBeanNamesForType(PaymentClient.class);

        for (String name : names) {
            System.out.println("PaymentClient bean: " + name);
        }
    }
}
```

Or inspect directly in a debugger:

- getBeanNamesForType(PaymentClient.class);
- getBeansOfType(PaymentClient.class);
- containsBean("paymentClient");
- getBeanDefinitionNames().

If there is a parent/child ApplicationContext, determine which context holds the bean. Beans in the parent can be accessed by the child context per lookup rules; conversely, beans only in the child are unavailable in the parent. Do not compare two different contexts and conclude a bean is missing.

Do not log the entire bean registry in production if the output contains unnecessary internal information.

## 13. Testing Auto-Configuration with ApplicationContextRunner

ApplicationContextRunner creates a lightweight context with configuration and properties specified by the test. It is ideal for verifying whether an auto-configuration creates beans under specific combinations of conditions.

### 13.1. Testing That a Bean Is Created When Conditions Are Met

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    PaymentClientAutoConfiguration.class
                            )
                    );

    @Test
    void createsClientWhenEnabled() {
        runner.withPropertyValues("acme.payment.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(PaymentClient.class)
                );
    }

    @Test
    void backsOffWhenDisabled() {
        runner.withPropertyValues("acme.payment.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(PaymentClient.class)
                );
    }
}
```

This test verifies property-based conditions. If the auto-configuration requires additional classpath dependencies or foundational beans, supply the appropriate dependencies/configurations to the runner.

### 13.2. Testing When a Class Is Missing from the Classpath

Spring Boot provides FilteredClassLoader to simulate a missing dependency:

```java
import org.springframework.boot.test.context.FilteredClassLoader;

@Test
void doesNotCreateClientWhenSdkIsMissing() {
    runner.withClassLoader(new FilteredClassLoader(PaymentSdk.class))
            .run(context ->
                    assertThat(context).doesNotHaveBean(PaymentClient.class)
            );
}
```

This test confirms that auto-configuration safely turns off when an optional class is absent. In a real project, tests must use the corresponding classloader and module dependencies.

### 13.3. Printing the Condition Report in Tests

You can add an initializer:

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

@Test
void printsConditionReport() {
    runner.withInitializer(
            ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
    ).run(context -> {
        assertThat(context).hasNotFailed();
    });
}
```

When a test fails, the report helps reveal which condition was not satisfied right in the test run.

### 13.4. When Is SpringBootTest Needed?

Use ApplicationContextRunner to test small, controlled auto-configurations. Use SpringBootTest when you need to verify:

- whether the real application classes are discovered;
- whether profiles and external configurations are loaded;
- whether the application's full dependency graph creates the bean;
- whether Spring Cloud provider auto-configuration works in a real context.

Do not replace an integration test with a runner if the error only appears due to application-wide configuration or dependencies.

## 14. Diagnostic Example: Need EurekaDiscoveryClient but Only Added Commons

Suppose a service has:

```java
@Service
public class CatalogLookupService {

    private final DiscoveryClient discoveryClient;

    public CatalogLookupService(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }
}
```

The application adds spring-cloud-commons and injects a DiscoveryClient, yet the developer expects instances to be fetched from Eureka.

Two situations can happen:

**Case A — only SimpleDiscoveryClient exists:** Spring Cloud Commons provides a simple client reading instances from properties. The abstraction bean exists, but it never queries Eureka.

**Case B — no matching DiscoveryClient exists:** the dependency is missing, discovery is disabled, or the implementation's context/conditions do not match.

Resolution steps:

1. Inspect the runtime dependency tree.
2. Confirm spring-cloud-starter-netflix-eureka-client is in the module running the application.
3. Confirm the version is managed by the Spring Cloud BOM.
4. Enable --debug and locate Eureka auto-configuration in the report.
5. Check that spring.cloud.discovery.enabled is not set to false.
6. Verify the implementation bean with getBeansOfType(DiscoveryClient.class).
7. Verify the Eureka client connects to the registry and receives the instance list.

EnableDiscoveryClient does not replace the Eureka dependency. In current Spring Cloud, this annotation is unnecessary if the provider implementation is already on the classpath.

## 15. Diagnostic Example: ConfigurationProperties Is Not Registered

A class has the annotation:

```java
@ConfigurationProperties(prefix = "client.remote")
public class RemoteClientProperties {

    private URI endpoint;

    // getters and setters
}
```

Yet constructor injection reports RemoteClientProperties cannot be found.

The cause may be that this class was not registered via ConfigurationPropertiesScan or EnableConfigurationProperties.

How to fix:

```java
@SpringBootApplication
@ConfigurationPropertiesScan(basePackageClasses = RemoteClientProperties.class)
public class OrdersApplication {
}
```

Or:

```java
@Configuration
@EnableConfigurationProperties(RemoteClientProperties.class)
public class RemoteClientConfiguration {
}
```

Then verify property binding separately. The existence of the bean does not mean client.remote.endpoint already holds a valid value.

## 16. Ordered Diagnostic Runbook

When getting a "starter added but bean not found" error, proceed in order:

1. Read the deepest exception and identify the requested bean type.
2. Distinguish NoSuchBeanDefinitionException from NoUniqueBeanDefinitionException, ClassNotFoundException, and bean initialization errors.
3. Identify the exact module that produces the executable application.
4. Inspect the dependency tree of `runtimeClasspath`.
5. Confirm the dependency containing implementation classes and the auto-configuration module are present.
6. Verify the deployed artifact contains the required dependencies and metadata.
7. Confirm the application runs via SpringApplication with SpringBootApplication or EnableAutoConfiguration.
8. Enable --debug and read ConditionEvaluationReport.
9. Check class-level and method-level conditions.
10. Check properties, profiles, and web application type.
11. Check component scan, Import, and configuration properties registration.
12. Check auto-configuration exclusions and ConditionalOnMissingBean.
13. Verify Spring Boot/Spring Cloud version compatibility.
14. Write a small context test reproducing the failing condition.
15. Fix only the identified root cause, then rerun relevant context and integration tests.

If the bean exists in the context yet injection still fails, check qualifiers, generic types, bean names, parent/child contexts, and bean proxy types before changing dependencies.

## 17. Quick Symptom and Resolution Table

| Symptom | Common Cause | How to Verify |
| --- | --- | --- |
| Starter added but no auto-config | Starter does not pull autoconfigure module or metadata missing | Dependency tree and AutoConfiguration.imports |
| Auto-config in JAR but absent from report | Auto-configuration not registered or not enabled | --debug, check metadata and EnableAutoConfiguration |
| Negative match due to missing class | Implementation dependency missing at runtime | dependencyInsight, runtimeClasspath, BOOT-INF/lib |
| Negative match due to property | Property false, wrong name, or profile inactive | Environment and config report |
| Service Component not found | Package outside component scan | Main class package, scanBasePackages, Import |
| ConfigurationProperties does not exist | Missing scan or EnableConfigurationProperties | Check properties registration configuration |
| Default bean not created | User bean of same type makes ConditionalOnMissingBean back off | getBeansOfType and condition report |
| DiscoveryClient exists but not using Eureka | Only SimpleDiscoveryClient or missing provider | Check implementation bean and Eureka starter |
| Fails only in test slice | Slice does not load required configuration or auto-config | Use ImportAutoConfiguration or SpringBootTest |
| Startup fails with compatibility message | Spring Boot outside release train compatibility range | Check BOM and release train |
| NoSuchBeanDefinitionException yet bean of same name exists in another context | Parent/child context or test creating separate context | Inspect the exact BeanFactory performing injection |
| NoUniqueBeanDefinitionException | Multiple implementations of the same type | Primary, Qualifier, and bean list |

## 18. Checklist Before Concluding a Starter Is Broken

- [ ] Starter is in the right module that builds the application.
- [ ] Dependency is in runtimeClasspath.
- [ ] Module containing implementation classes is present.
- [ ] Auto-configuration module is present if the starter relies on auto-configuration.
- [ ] AutoConfiguration.imports file has the proper entry for custom starters.
- [ ] Application enables auto-configuration via SpringBootApplication or EnableAutoConfiguration.
- [ ] No exclusions in annotations or spring.autoconfigure.exclude.
- [ ] Both class-level and bean-method conditions match.
- [ ] Properties and active profiles are correct.
- [ ] Component is within scan scope or has been imported.
- [ ] ConfigurationProperties are registered properly.
- [ ] Provider starter matches the required abstraction.
- [ ] Spring Boot and Spring Cloud versions are compatible.
- [ ] Condition report was read before adding random dependencies.
- [ ] A test reproduces the bean creation condition.

## 19. Practice Exercises

### Exercise 1 — Starter Present but Auto-Configuration Does Not Appear

A custom starter contains PaymentClientAutoConfiguration, yet the application has no PaymentClient bean.

Inspect the dependency tree, the autoconfigure module, and the META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports file. Explain why component scan is not the standard way to register auto-configuration.

### Exercise 2 — Component Outside the Root Package

The main class is in com.acme.orders, while FraudDetectionService is in com.acme.shared.fraud.

Explain why the bean is not scanned and write two ways to bring the configuration into the context using Import or intentional package scanning.

### Exercise 3 — Property Condition Does Not Match

Auto-configuration uses ConditionalOnProperty(prefix = "acme.cache", name = "enabled", havingValue = "true"). The local file sets true, yet production still has no bean.

List the property sources that could override it, how to check active profiles, and how to read ConditionEvaluationReport.

### Exercise 4 — DiscoveryClient Exists Without Eureka

The application successfully injects DiscoveryClient but only receives instances declared in properties.

Explain SimpleDiscoveryClient, provider starters, and how to verify the actual implementation bean.

### Exercise 5 — Auto-Configuration Backs Off

The application declares a custom PaymentClient bean. Afterward, the starter's default bean does not appear.

Explain ConditionalOnMissingBean, how to inspect existing beans, and why this can be the intended behavior.

### Exercise 6 — Dependency Conflict Between Spring Boot and Spring Cloud

After upgrading Spring Boot, the application fails to create several Spring Cloud beans and startup logs linkage errors.

Propose a procedure to check the release train, BOM, dependency tree, and compatibility verifier. State why disabling the verifier does not fix the root cause.

## 20. Quick Self-Check

1. Does adding a starter guarantee a bean is created? **No, it also depends on auto-configuration and conditions.**
2. Do starters and auto-configuration have the same role? **No; starters bundle dependencies, while auto-configuration defines how beans are created.**
3. Where is modern auto-configuration listed? **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports.**
4. Does SpringBootApplication include auto-configuration? **Yes, via EnableAutoConfiguration.**
5. What does a ConditionalOnClass mismatch usually mean? **The required class is not on the appropriate classpath.**
6. What does ConditionalOnMissingBean do? **Allows auto-configuration to skip creating a default bean when a replacement bean already exists.**
7. Does ConfigurationProperties create a bean with just its annotation? **No, it requires scanning or explicit registration.**
8. Is EnableDiscoveryClient required when a provider implementation is already on the classpath? **Not required in current Spring Cloud.**
9. Does SimpleDiscoveryClient mean Eureka is active? **No.**
10. Which command enables ConditionEvaluationReport at startup? **java -jar application.jar --debug.**
11. Which Actuator endpoint displays conditions? **/actuator/conditions, if exposed and secured.**
12. Why should you use the Spring Cloud BOM? **To keep modules aligned on the same release train and compatible with Spring Boot.**
13. What is ApplicationContextRunner useful for? **Testing auto-configuration across combinations of classpath, beans, and properties.**
14. If a bean of the same type exists yet injection reports not found, what should you check? **The injecting context, qualifiers, generic types, and parent/child contexts.**

**Core takeaway:** When a bean fails to appear even after adding a starter, trace from the runtime classpath to auto-configuration metadata, conditions, and bean registration. Distinguish Spring Cloud abstractions from provider implementations, check component scan and version compatibility, and then use ConditionEvaluationReport or ApplicationContextRunner to prove the cause. Only when you know precisely which condition failed can you fix the problem without bloating the classpath or accidentally enabling unintended features.

**References:**

- [Spring Boot 4.1 — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot 4.1 — Structuring Your Code](https://docs.spring.io/spring-boot/reference/using/structuring-your-code.html)
- [Spring Boot 4.1 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot — Troubleshoot Auto-configuration](https://docs.spring.io/spring-boot/how-to/application.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Cloud Commons 5.0.4 — Common Abstractions and DiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons 5.0.4 — Configuration Properties and Compatibility Verifier](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Cloud — Release Train Compatibility](https://spring.io/projects/spring-cloud#overview)

Class names, packages, artifacts, and auto-configuration conditions may change between releases. Always consult the documentation for the Spring Boot/Spring Cloud release train in use and inspect the application's own runtime dependency tree.
