# Bean creation failures due to auto-configuration conditions or missing dependencies

A Spring Boot application may compile successfully but fail at runtime to find beans such as `S3Client`, `SqsTemplate`, `ServiceBusClientBuilder`, `BlobServiceClient`, `PubSubTemplate`, or `Storage`. The root cause usually lies in how Spring Boot decides whether to register an auto-configuration and which libraries are actually present on the runtime classpath.

Spring Boot does not automatically create every bean for every cloud service. Auto-configuration only registers a configuration when its conditions are met. Provider starters are also split into modules: adding the AWS SDK S3, Azure SDK Blob, or Google Cloud Java Storage library directly does not necessarily add the corresponding Spring auto-configuration.

This article explains how to distinguish between an unregistered bean and a bean that fails during initialization, read the `ConditionEvaluationReport`, inspect the dependency graph and BOM, find the condition causing a configuration to be skipped, and troubleshoot examples on AWS, Azure, and Google Cloud.

## 1. Identify the exact error type before fixing

An error message containing the word "bean" is not enough to conclude that auto-configuration did not run. You need to determine whether the bean was skipped, not found, or created and then failed during initialization.

| Symptom | Common meaning | First check to perform |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | The context has no bean matching the requested type or name | Check dependencies, condition report, component scan, and bean name |
| `No qualifying bean of type ... available` | No bean found matching the type or qualifier | Check actual type, `@Qualifier`, and auto-configuration conditions |
| `UnsatisfiedDependencyException` | A dependent bean could not be resolved or a dependency bean failed to initialize | Read the deepest `Caused by` chain |
| `BeanCreationException` | Spring attempted to create the bean, but the factory method/constructor/init failed | Check root cause, properties, endpoint, and credentials |
| `NoClassDefFoundError` | The required class was available at compile time but is missing on the runtime classpath, or versions are incompatible | Check runtime dependency tree and exclusions |
| `NoSuchMethodError` | The class is present, but the API version is incompatible with the calling library | Check the BOM and overridden dependency versions |
| ApplicationContext starts up, but integration beans are missing | Auto-configuration did not match, or the module is not enabled/on the classpath | Read the report and dependency graph |

For example, if a service constructor requires `SqsTemplate` and the context does not have that bean, it may be a missing SQS starter or an unmatched SQS condition. If `SqsTemplate` is registered but `SqsAsyncClient` cannot resolve the region, the error occurs during bean creation and usually produces a `BeanCreationException` or a deeper SDK cause.

**First rule:** do not randomly add credentials, IAM roles, or endpoints before checking whether the bean is even registered. IAM usually affects API calls at runtime; it is not a common reason why a client bean is not registered in the Spring context.

## 2. How does auto-configuration decide to create beans?

`@SpringBootApplication` includes `@EnableAutoConfiguration`. Spring Boot discovers auto-configuration classes declared by libraries on the classpath, evaluates their conditions, and registers matching beans.

Auto-configuration is typically packaged inside a starter or integration library. When you add a starter for a service, the application receives the required modules and Spring Boot can detect the corresponding configuration. If you only add the base SDK, the application can call APIs by manually constructing clients, but you cannot assume Spring will provide pre-configured beans.

### 2.1. Common conditions

| Annotation | What does Spring check? | Example reason a bean is missing |
| --- | --- | --- |
| `@ConditionalOnClass` | Is the required class on the classpath? | Missing Azure Blob SDK or AWS SQS module |
| `@ConditionalOnMissingClass` | Is a class absent? | An integration is disabled when a conflicting library is present |
| `@ConditionalOnBean` | Has a dependent bean already been registered? | Template configuration only runs when a client bean exists |
| `@ConditionalOnMissingBean` | Does a bean of the same type/name already exist? | The default bean backs off in favor of an application bean |
| `@ConditionalOnProperty` | Does the property exist and have a matching value? | Module disabled by property or misconfigured value |
| `@ConditionalOnResource` | Does the required resource/file exist? | Missing configuration file or metadata |
| `@ConditionalOnWebApplication` | Is the context a web application of the expected type? | Configuration intended only for servlet apps running in reactive/non-web |
| `@ConditionalOnSingleCandidate` | Is there exactly one matching bean or one primary bean? | Multiple clients of the same type without a primary |
| `@ConditionalOnExpression` | Does the SpEL expression evaluate to true? | Unsatisfied placeholder or conditional expression |
| `@Profile` | Does the active profile match? | Bean declared only in the cloud profile while running locally |

Conditions can be placed at the configuration class level or on individual `@Bean` methods. If a class-level condition does not match, none of the beans in that configuration class are registered. If a method-level condition does not match, only the corresponding bean is skipped.

### 2.2. Classpath conditions

Example of a configuration requiring the AWS SQS client:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "software.amazon.awssdk.services.sqs.SqsAsyncClient")
class SqsClientConfiguration {

    @Bean
    SqsAsyncClient sqsAsyncClient() {
        return SqsAsyncClient.builder().build();
    }
}
```

If the `SqsAsyncClient` class is not on the runtime classpath, Spring Boot can skip this configuration. There will be no `SqsAsyncClient` bean to inject.

Placing a class condition on the configuration class is handled more safely than directly referencing a missing class type in the `@Bean` method signature. When writing your own auto-configuration, isolate SDK-dependent configuration in a class annotated with `@ConditionalOnClass`.

### 2.3. Property conditions

Example:

```java
@Configuration(proxyBeanMethods = false)
class StorageConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.storage",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    StorageFacade storageFacade() {
        return new StorageFacade();
    }
}
```

The bean only appears when `app.storage.enabled=true`. If the property is missing or set to `false`, the method is not invoked.

With `@ConditionalOnProperty`, when `havingValue` is not specified, by default the property must exist and not have the string value `false`. `matchIfMissing` defaults to `false`. When multiple names are listed in `name`, all conditions must match.

Do not confuse a property that enables/disables an integration with credential properties. For example, a module may be enabled while client creation fails due to a missing region; or a module may have all dependencies present but be disabled by a property.

### 2.4. Dependent bean conditions

One bean may depend on another bean:

```java
@Bean
@ConditionalOnBean(SqsAsyncClient.class)
@ConditionalOnMissingBean
SqsTemplate sqsTemplate(SqsAsyncClient client) {
    return SqsTemplate.newTemplate(client);
}
```

If `SqsAsyncClient` is missing, `SqsTemplate` is not registered either. When reading the condition report, trace the condition chain back from the desired bean to the first missing foundational bean.

Spring Boot recommends using `@ConditionalOnBean` and `@ConditionalOnMissingBean` on auto-configuration classes, because auto-configuration is processed after user-declared bean definitions. If a bean dependency condition is placed in a regular application configuration, processing order can yield unexpected results.

### 2.5. Default beans backing off

This is usually intentional behavior:

```java
@Bean
@ConditionalOnMissingBean
Clock cloudClock() {
    return Clock.systemUTC();
}
```

If the application already declares a `Clock` bean, auto-configuration no longer creates the default bean. This is not an error.

If you accidentally declare a bean of the same type, or a test configuration gets imported into the context, the provider's default bean may disappear. Check bean names and `@Bean` method return types before concluding that the starter is broken.

When writing custom beans, declare a return type specific enough for Spring conditions to evaluate accurately. If a method returns an overly broad interface while auto-configuration checks a concrete type, the condition may not behave as expected.

## 3. Distinguishing starters, SDKs, and auto-configuration modules

Each provider packages its libraries differently. You need to know whether an added dependency is an SDK, a Spring integration module, or a starter with auto-configuration.

| Provider | Example service starter dependency | Role |
| --- | --- | --- |
| AWS | `io.awspring.cloud:spring-cloud-aws-starter-s3` | Adds Spring Cloud AWS integration for S3 and auto-configures the corresponding client |
| AWS | `io.awspring.cloud:spring-cloud-aws-starter-sqs` | Adds SQS integration, including components such as `SqsTemplate` per the corresponding release |
| Azure | `com.azure.spring:spring-cloud-azure-starter-storage-blob` | Adds auto-configuration and Azure Blob Storage integration |
| Azure | `com.azure.spring:spring-cloud-azure-starter-servicebus` | Adds Azure Service Bus integration |
| Google Cloud | `com.google.cloud:spring-cloud-gcp-starter-storage` | Adds Spring integration with Cloud Storage |
| Google Cloud | `com.google.cloud:spring-cloud-gcp-starter-pubsub` | Adds Spring integration with Pub/Sub |
| Google Cloud | `com.google.cloud:spring-cloud-gcp-starter-data-spanner` | Adds Spring Data integration with Spanner |

These artifacts are examples for specific release lines; check the BOM and documentation for your exact version before using them. A starter typically pulls in the integration module and required dependencies. If you only add the SDK—such as `software.amazon.awssdk:s3`, `com.azure:azure-storage-blob`, or `com.google.cloud:google-cloud-storage`—you can create clients yourself using the SDK, but you should not assume Spring will provide templates or integration beans.

### 3.1. A starter does not mean one starter for the entire provider

For example, with Google Cloud:

- `spring-cloud-gcp-starter` provides Core components such as project ID and credentials provider.
- `spring-cloud-gcp-starter-pubsub` is what brings the Pub/Sub module into the application.
- `spring-cloud-gcp-starter-storage` is what brings the Storage module into the application.

Adding the Core starter does not mean `PubSubTemplate` or `Storage` is configured. Each service requires its corresponding module.

With Azure, `spring-cloud-azure-starter` is the Core starter; to integrate Service Bus, Blob Storage, Cosmos DB, or Key Vault, add the starter for the corresponding service.

With AWS, Spring Cloud AWS also splits starters by service. The S3 starter and SQS starter activate different groups of auto-configurations.

### 3.2. BOMs keep versions compatible

Do not pick individual versions manually for each starter if the provider supplies a BOM. The BOM manages Spring integration and SDK versions that have been tested together.

Maven example for an AWS module:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>${spring-cloud-aws.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-sqs</artifactId>
    </dependency>
</dependencies>
```

Maven example for Azure:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-servicebus</artifactId>
    </dependency>
</dependencies>
```

Maven example for Google Cloud:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>${spring-cloud-gcp.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
    </dependency>
</dependencies>
```

Do not copy a version from an old example into your current application. Cross-check the compatibility matrix between Spring Boot, the Spring Cloud release train, and the provider BOM. A BOM that manages provider dependencies does not automatically guarantee compatibility with every Spring Boot version.

## 4. Reading ConditionEvaluationReport to see why a bean was skipped

Spring Boot generates a `ConditionEvaluationReport` during startup. The report records which auto-configurations matched, which did not match, and why.

### 4.1. Enable debug at startup

Run the JAR with the `--debug` flag:

```bash
java -jar build/libs/orders-api.jar --debug
```

Or run with Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

Or set the JVM system property before `-jar`:

```bash
java -Ddebug=true -jar build/libs/orders-api.jar
```

Spring Boot prints the condition evaluation report to the log. Search for the relevant auto-configuration name or bean name, then read the positive matches and negative matches sections.

You can increase logging specifically for auto-configuration:

```yaml
logging:
  level:
    org.springframework.boot.autoconfigure: DEBUG
```

Do not leave full application debug logging enabled permanently in production. The report can contain class names, properties, and configuration details useful to operators; collect logs in a controlled environment and do not send secrets to logs.

### 4.2. Using the Actuator conditions endpoint

If the application includes Spring Boot Actuator, the `conditions` endpoint exposes the condition report as JSON.

Maven dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Configuration to expose the endpoint in a development environment:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
```

Once the application is running:

```http
GET /actuator/conditions
```

This endpoint can reveal internal configuration details. Only expose it locally/in dev or behind proper access controls; do not open it publicly on the Internet just for debugging.

### 4.3. How to read the report

An auto-configuration appears under positive matches if its conditions are satisfied. If it does not match, the report typically lists one of the following reasons:

- Required class was not found: missing class/dependency.
- A bean of type ... was not found: dependent bean has not been registered.
- A bean of type ... was found: `@ConditionalOnMissingBean` is no longer satisfied because another bean already exists.
- Property ... did not find property ...: property is missing.
- Property ... found different value: property value does not match `havingValue`.
- Not a web application: the context is not the required web application type.
- Excluded by ...: configuration was excluded or not imported.

Do not search only for the bean name in the report. Look for the auto-configuration containing that bean, then examine both class-level and method-level conditions. If the parent configuration does not match, child beans will not be created even if their individual conditions would evaluate to true.

## 5. Step-by-step diagnostic workflow

Use the following workflow to narrow down the cause. Execute each step and record the results before changing dependencies or properties.

### Step 1 — Confirm the bean you are looking for

Identify precisely:

- The bean type to inject.
- The bean name if using `@Qualifier` or `@Resource`.
- The cloud module responsible for providing the bean.
- The active profile and configuration.

For example, `SqsTemplate`, `SqsAsyncClient`, `S3Client`, `PubSubTemplate`, and `Storage` are all distinct types. Having an SDK client does not mean a Spring template exists, and vice versa.

You can print bean names by type in a temporary diagnostic snippet:

```java
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class BeanInventory {

    private final ApplicationContext context;

    public BeanInventory(ApplicationContext context) {
        this.context = context;
    }

    public void printStorageBeans() {
        String[] names = context.getBeanNamesForType(
                com.google.cloud.storage.Storage.class);

        for (String name : names) {
            System.out.println("Storage bean: " + name);
        }
    }
}
```

Log only bean names and types; do not log credentials or tokens. Remove the temporary diagnostic code once finished.

### Step 2 — Verify the starter is on the runtime classpath

Check dependencies of the exact module being executed. With Maven:

```bash
./mvnw dependency:tree -Dincludes="io.awspring.cloud:*,com.azure.spring:*,com.google.cloud:*"
```

You can filter for a single artifact:

```bash
./mvnw dependency:tree -Dincludes=com.google.cloud:spring-cloud-gcp-starter-pubsub
```

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Inspect a specific dependency:

```bash
./gradlew dependencyInsight --dependency spring-cloud-gcp-starter-pubsub --configuration runtimeClasspath
```

When running tests, also inspect `testRuntimeClasspath`. A dependency placed only in `testImplementation` or Maven `test` scope is not present when running the production application.

When specifically checking Pub/Sub, the `spring.cloud.gcp.pubsub.enabled` property controls the module's auto-configuration and defaults to `true` in the current reference. If this property is set to `false`, the starter can still be on the classpath, but Pub/Sub auto-configuration will not create the corresponding beans.

### Step 3 — Check for excluded or mis-scoped dependencies

Look for cases such as:

- The starter is declared in a different Gradle module rather than the module building the executable JAR.
- The dependency uses `test`, `provided`, or `optional` scope unintentionally.
- A parent POM or dependency management excludes a transitive SDK.
- Gradle uses `compileOnly` for a library needed at runtime.
- The dependency is excluded from an umbrella starter.
- A build profile only adds the starter in a different environment.
- The fat JAR or container image was built from stale artifacts.

If the starter is on `compileClasspath` but not `runtimeClasspath`, Spring Boot can compile the code yet fail to register auto-configuration at runtime.

### Step 4 — Read the condition report

Start the application with `--debug` or use Actuator `conditions`. Look for:

1. The service's auto-configuration.
2. Class-level conditions.
3. Conditions on the bean to inject.
4. Dependent beans required by conditions.
5. Module enable/disable properties.

When the report indicates a missing class, return to step 2. When the report indicates an unmatched property, check property sources and profiles. When the report indicates a bean already exists, locate the bean registered by the application or another library.

### Step 5 — Check property binding and profiles

Properties can come from:

- `application.yml` and `application-{profile}.yml`.
- Environment variables.
- JVM system properties.
- Command-line arguments.
- Config Server or external config.
- Test property sources.

Check the actual active profile:

```bash
java -jar build/libs/orders-api.jar --spring.profiles.active=dev --debug
```

Property names must use the correct module prefix for the exact release line. For example, `spring.cloud.gcp.pubsub.enabled` and `spring.cloud.gcp.core.enabled` are two separate settings; do not assume disabling Core disables all GCP modules or vice versa. For other providers, check the reference documentation to confirm property names and default values.

### Step 6 — Check bean overrides and bean types

If the report shows `@ConditionalOnMissingBean` did not match:

- Search for a bean of the same type in application code.
- Look for an unexpectedly imported `@TestConfiguration`.
- Check `@Primary`, `@Qualifier`, and bean names.
- Check whether the `@Bean` method returns an interface or a concrete class.
- Determine whether the custom bean is actually meant to replace the default bean.

If the bean already exists but injection still fails, the issue may be a qualifier mismatch, incompatible type, or multiple candidates without a primary; it is no longer a skipped auto-configuration issue.

### Step 7 — Check version compatibility

If the class is present but you encounter `NoSuchMethodError`, `NoClassDefFoundError`, `LinkageError`, or binding errors:

- Inspect the dependency tree for multiple versions of the same SDK.
- Verify that the provider BOM is imported.
- Verify the Spring Boot and Spring Cloud release train.
- Check for manually overridden dependencies.
- Confirm the Java version required by the release line.
- Clean old build outputs and repackage the artifact after fixing dependencies.

Do not resolve conflicts by randomly bumping a single SDK version. Use a compatible BOM or perform an intentional override after checking release notes.

## 6. Provider-specific examples

### 6.1. AWS: missing SqsTemplate

Suppose a service has this constructor:

```java
@Service
public class OrderPublisher {

    private final SqsTemplate sqsTemplate;

    public OrderPublisher(SqsTemplate sqsTemplate) {
        this.sqsTemplate = sqsTemplate;
    }
}
```

Checklist:

1. Confirm `io.awspring.cloud:spring-cloud-aws-starter-sqs` is on the runtime classpath.
2. Check the Spring Cloud AWS BOM and AWS SDK version.
3. Enable `--debug` and locate the SQS auto-configuration.
4. Check if a custom `SqsAsyncClient` or `SqsTemplate` bean is causing the default configuration to back off.
5. If the SQS client bean was created but failed to initialize, check the AWS region and credential provider chain.

Example dependency declaration:

```xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-sqs</artifactId>
</dependency>
```

The SQS starter provides auto-configuration for SQS integration. Adding only the AWS SDK SQS module may allow creating `SqsAsyncClient` manually, but it does not replace the starter if the application expects an `SqsTemplate` created by Spring Cloud AWS.

**Distinguishing errors:** a missing starter usually prevents SQS auto-configuration from appearing. A missing region or credentials usually causes client creation to fail. Missing IAM permissions usually appear only when calling the SQS API and returning an authorization error.

### 6.2. Azure: missing beans for Service Bus or Blob Storage

For Azure, verify the service-specific starters:

```xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-servicebus</artifactId>
</dependency>

<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
</dependency>
```

Check the `spring-cloud-azure-dependencies` BOM and supported Spring Boot version. Azure starters include the dependencies and auto-configuration logic needed for the corresponding module. Adding only the Azure SDK client library may require manual builder code instead of Spring integration beans.

When the condition report shows the module is not registered:

- Check that the starter is on the runtime classpath.
- Check the Azure SDK classes required by auto-configuration.
- Check module enable/disable properties and profiles.
- Check whether a custom bean of the same type is causing auto-configuration to back off.

If the client bean is created but fails to connect, check the tenant, managed identity, credential chain, endpoint, namespace, data-plane permissions, and network. Azure subscription roles or control-plane management permissions do not automatically grant data-plane permissions on Service Bus/Storage.

### 6.3. Google Cloud: Core is present, but PubSubTemplate is missing

Suppose the application has the Core dependency:

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter</artifactId>
</dependency>
```

The Core starter provides project ID and credentials provider. To use Pub/Sub integration, add the service starter:

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
</dependency>
```

To use Cloud Storage integration, add:

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-storage</artifactId>
</dependency>
```

If `PubSubTemplate` is missing:

1. Verify that the Pub/Sub starter—not just the Core starter—is on the runtime classpath.
2. Check the Spring Framework on Google Cloud BOM.
3. Search for Pub/Sub auto-configuration in the condition report.
4. Check the `spring.cloud.gcp.pubsub.enabled` property for your exact version.
5. Check custom `CredentialsProvider`, `PublisherFactory`, or `SubscriberFactory` beans if any exist.

If `PubSubTemplate` exists but publishing is rejected, then check the ADC principal, project/topic resource name, and Publisher IAM role. IAM is not the first step when the bean is not yet registered.

## 7. Common errors and fixes

| Cause | Symptom in report/logs | Fix |
| --- | --- | --- |
| Missing service starter | Auto-configuration does not appear or class condition fails to match | Add the starter for the correct service |
| Added plain SDK only | SDK client can be created manually, but no Spring template/bean exists | Add the starter or intentionally declare a `@Bean` yourself |
| Missing transitive class | `@ConditionalOnClass` fails to match or `NoClassDefFoundError` | Check dependency tree, exclusions, and runtime scope |
| Module disabled by property | Property condition fails to match | Check prefix, value, and property sources |
| Wrong profile active | Bean is in another profile's configuration | Check `spring.profiles.active` and profile files |
| Auto-configuration excluded | Report omits expected configuration or records an exclusion | Check `exclude`, `excludeName`, and `spring.autoconfigure.exclude` |
| Custom bean makes auto-config back off | `@ConditionalOnMissingBean` fails to match | Determine whether the custom bean is intentional or accidental |
| Missing foundational bean | `@ConditionalOnBean` fails to match | Find the first missing bean and the condition that creates it |
| Multiple beans of same type | `NoUniqueBeanDefinitionException` or ambiguous candidate | Use `@Primary` or `@Qualifier` |
| Incompatible BOM | `NoSuchMethodError`, `ClassNotFoundException`, binding errors | Align Spring Boot, Spring Cloud, and provider BOM versions |
| Dependency only in test scope | Tests pass, but production JAR is missing the bean | Move the starter to runtime dependencies |
| Missing region/endpoint | Client bean fails during initialization | Configure region/endpoint according to the provider |
| Missing credentials | Client builder or credential provider throws exception | Use the appropriate identity/ADC/managed identity/role |
| Insufficient IAM permissions | Bean exists, API returns 401/403 or access denied | Grant data-plane permissions on the target resource |
| Network or DNS error | Bean exists, requests time out or fail to resolve endpoint | Check routes, firewall, DNS, proxy, and private endpoints |

## 8. Checking auto-configuration exclusion settings

Auto-configuration can be excluded via annotation:

```java
@SpringBootApplication(
        exclude = SomeCloudAutoConfiguration.class)
public class OrdersApplication {
}
```

Or by class name in properties:

```yaml
spring:
  autoconfigure:
    exclude:
      - com.example.cloud.SomeCloudAutoConfiguration
```

When a provider bean does not appear, look for exclusion settings in:

- `@SpringBootApplication` or `@EnableAutoConfiguration`.
- `spring.autoconfigure.exclude` in YAML/properties.
- Properties passed via command line or environment variables.
- Test configurations or shared modules.

Only remove an exclusion if the integration is genuinely needed. Some applications exclude auto-configuration to manage clients manually, avoid conflicts, or opt out of using that service.

## 9. Writing tests to verify auto-configuration conditions

If your team develops custom starters or shared configurations, test conditions with `ApplicationContextRunner`. This utility creates a lightweight context allowing you to add properties, register beans, or hide classes from the classpath without booting the entire application.

Example testing an auto-configuration that creates a bean when a property is enabled:

```java
class StorageFacadeAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    StorageFacadeAutoConfiguration.class));

    @Test
    void createsStorageFacadeWhenEnabled() {
        contextRunner
                .withPropertyValues("app.storage.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(StorageFacade.class);
                });
    }

    @Test
    void doesNotCreateStorageFacadeWhenDisabled() {
        contextRunner
                .withPropertyValues("app.storage.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(StorageFacade.class);
                });
    }
}
```

You need the test dependencies matching your Spring Boot version, typically `spring-boot-starter-test`.

### 9.1. Testing a missing classpath

Spring Boot provides `FilteredClassLoader` to simulate a class missing from the runtime classpath:

```java
@Test
void disablesIntegrationWhenSdkClassIsMissing() {
    contextRunner
            .withClassLoader(
                    new FilteredClassLoader(RequiredCloudClient.class))
            .run(context -> {
                assertThat(context)
                        .doesNotHaveBean(StorageFacade.class);
            });
}
```

This test verifies that the integration is not activated when the SDK class is absent. It helps avoid class linkage errors in custom starters.

### 9.2. Printing the condition report in tests

You can attach a listener to print the report during tests:

```java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener
                        .forLogLevel(LogLevel.INFO))
        .run(context -> {
            // Assert the required beans.
        });
```

If the auto-configuration only runs in a servlet or reactive application, use `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner` to simulate the appropriate context type.

## 10. Do not confuse bean errors with credentials, IAM, or connectivity errors

An integration goes through multiple stages:

1. Dependencies are on the classpath.
2. Auto-configuration is discovered.
3. Conditions match and bean definitions are registered.
4. Factory method/constructor creates the client bean.
5. Client resolves credentials, region/project, and endpoint.
6. Request is sent to the cloud service.
7. Provider evaluates IAM/RBAC and processes the request.

Errors at each stage produce different symptoms:

| Stage | Example error | Question to answer |
| --- | --- | --- |
| Classpath | `ClassNotFoundException` | Are the right starter and SDK present at runtime? |
| Auto-configuration | Bean does not exist | Which condition failed to match? |
| Bean creation | `BeanCreationException` | Which factory method or property caused initialization to fail? |
| Authentication | Credential unavailable / invalid token | Which principal is the runtime using? |
| Authorization | 401/403 / access denied | Does the principal have permissions on the target resource? |
| Network | Timeout / DNS failure | Can the application reach the endpoint? |
| Resource | Not found / wrong project / region | Are the resource name and location accurate? |

Some SDKs defer connecting to the cloud until the first call. Therefore, a bean may initialize successfully even when IAM or networking is misconfigured. Only an integration test making a real API call proves permissions and connectivity.

## 11. Lab: finding why PubSubTemplate cannot be created

Goal: fix a Spring Boot application that declares `PubSubTemplate` in a constructor, yet the context lacks the corresponding bean.

### Step 1 — Confirm the error

Error message:

```text
No qualifying bean of type
'com.google.cloud.spring.pubsub.core.PubSubTemplate' available
```

Record the active profile and packaged artifact. Do not change credentials or IAM yet.

### Step 2 — Check runtime dependencies

Run:

```bash
./gradlew dependencyInsight --dependency spring-cloud-gcp-starter-pubsub --configuration runtimeClasspath
```

If the dependency is missing, add the Pub/Sub starter to the appropriate application module. Having only `spring-cloud-gcp-starter` is not enough for Pub/Sub integration.

### Step 3 — Check the BOM

Confirm that `spring-cloud-gcp-dependencies` is imported and compatible with your Spring Boot release line. Verify there are no differing manual versions between the starter and transitive modules.

### Step 4 — Enable the condition report

Start with:

```bash
java -jar build/libs/orders-api.jar --debug
```

Locate the Pub/Sub auto-configuration and read the negative match. If the class condition fails to match, check dependencies. If the property condition fails to match, check whether the module is disabled. If the report shows an existing bean, inspect custom configurations and bean overrides.

### Step 5 — Fix the identified cause

If the starter is missing, add the dependency:

```kotlin
dependencies {
    implementation(
        "com.google.cloud:spring-cloud-gcp-starter-pubsub"
    )
}
```

If the starter is already present but configuration is disabled, fix the property according to the reference documentation for the version in use. If an unwanted custom bean exists, adjust that configuration so auto-configuration can create the default bean.

### Step 6 — Verify the context and API

- Restart the application and confirm `PubSubTemplate` is in the context.
- Verify the ADC principal and project/topic name.
- Run an integration test publishing a message to a sandbox project.
- If the API returns 403, grant the Publisher role to the appropriate service account on the topic.
- If the API returns a connection error, check the endpoint, DNS, and network.

This lab is complete once you have verified both things: the bean is registered properly and the API operation succeeds using the expected identity.

## 12. Short checklist for production incidents

When production reports a missing bean after a deployment:

1. Compare the running artifact/version with the previous deployment.
2. Inspect the runtime dependency tree or SBOM of the artifact.
3. Collect the condition report from startup logs or a secured endpoint.
4. Identify the unmatched condition or missing dependency.
5. Check properties/profiles and exclusion settings.
6. Check BOM changes, dependency scopes, and image builds.
7. If the bean is already created, move on to checking credentials, region, endpoint, IAM, and network.
8. Restore compatible dependencies/BOM/configuration, build a new artifact, and deploy through the release pipeline.

Do not expose Actuator `conditions` publicly to investigate production. If the endpoint is not secured, use startup debug logs in a controlled reproduction or generate diagnostics stripped of sensitive information.

## 13. Key takeaways

- `NoSuchBeanDefinitionException` usually means the context has no matching bean; `BeanCreationException` usually means Spring attempted to create the bean, but initialization failed.
- Auto-configuration only runs when conditions such as classpath, bean, property, resource, profile, and application context type are satisfied.
- `@ConditionalOnClass` usually indicates a missing dependency; `@ConditionalOnProperty` usually indicates a property or profile; `@ConditionalOnBean` requires a foundational bean; `@ConditionalOnMissingBean` lets the application replace the default bean.
- Service starters typically provide both the integration module and auto-configuration. A plain SDK may suffice for manual client construction but does not automatically create Spring templates/beans.
- AWS, Azure, and Google Cloud all split starters by service; a provider's Core starter does not mean every service integration is included in the application.
- Use the provider's BOM and cross-check against the Spring Boot/Spring Cloud compatibility matrix; do not arbitrarily override SDK versions.
- Enable `--debug` or use Actuator `/actuator/conditions` to read `ConditionEvaluationReport`.
- Check `runtimeClasspath`, dependency exclusions, scopes, profiles, auto-configuration exclusions, and bean overrides.
- Credentials, region, endpoint, IAM/RBAC, and network usually affect the client creation or API call stages; they are not the primary cause of a missing bean definition.
- Use `ApplicationContextRunner` and `FilteredClassLoader` to unit-test auto-configuration conditions.

## Official reference documentation

1. [Spring Boot — Troubleshoot Auto-configuration](https://docs.spring.io/spring-boot/how-to/application.html)
2. [Spring Boot — Creating Your Own Auto-configuration and condition annotations](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
3. [Spring Boot — Auto-configuration classes](https://docs.spring.io/spring-boot/appendix/auto-configuration-classes/)
4. [Spring Boot — Build Systems and starter dependencies](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
5. [Spring Cloud AWS 3.4 — BOM, starter dependencies and auto-configuration](https://docs.awspring.io/spring-cloud-aws/docs/3.4.0/reference/html/index.html)
6. [Spring Cloud AWS — SQS starter and SqsTemplate](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/reference/html/index.html)
7. [Spring Cloud Azure — Developer Guide, BOM and starter dependencies](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview)
8. [Spring Cloud Azure — Auto-configure Azure SDK clients](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/auto-configure-azure-sdk-clients)
9. [Spring Framework on Google Cloud — Starter dependencies](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/)
10. [Spring Framework on Google Cloud Core — Core auto-configuration](https://googlecloudplatform.github.io/spring-cloud-gcp/8.2.0/reference/html/core.html)

Specific starter names, properties, and conditions depend on the release line. When investigating a real application, open the documentation for the exact version in use and inspect the source code of the corresponding AutoConfiguration class rather than relying on articles or examples from another version.
