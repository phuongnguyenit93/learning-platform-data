# Each configuration has a clear purpose, inputs, and output beans

## 1. Auto-configuration is a contract

An auto-configuration class should answer three questions before someone reads the code:

1. **Purpose:** which library capability will be integrated?
2. **Inputs:** which conditions, dependencies, properties, and beans must be present for the configuration to apply?
3. **Outputs:** which beans are created, of what type, for whom, and how can users replace them?

For example, instead of a generic description like "Acme configuration", describe it concretely:

> **AcmeAuditAutoConfiguration** provides a default **AuditClient** when the transport SDK is on the classpath, **acme.audit.enabled=true**, and the application has not already provided an AuditClient. Its output is a **DefaultAuditClient**, whose endpoint and timeout are bound from **AuditProperties**.

This description tells maintainers what to inspect when the bean does not appear, which bean is the public extension point, and which changes might break the contract.

An auto-configuration can create multiple beans if they serve the same capability and have clear relationships. The goal is not to create one class per bean, but to keep each configuration class with a narrow enough responsibility to understand, test, and change independently.

This article uses Spring Boot 3.3.13, Java 17+, and the Acme Audit library example. The content walks through the contract, inputs, output beans, properties, conditions, optional dependencies, back-off, ordering, module boundaries, and testing with ApplicationContextRunner.

## 2. Write the contract before writing beans

For each configuration class, document its purpose, input conditions, output beans, and extension points. The table below is the blueprint for the example:

| Component | AcmeAuditAutoConfiguration Contract |
| --- | --- |
| Purpose | Provide a default audit client for the application |
| Classpath input | AuditTransport from the transport SDK is present |
| Property input | acme.audit.enabled=true |
| Configuration input | AuditProperties provides endpoint and timeout |
| Bean input | No existing bean implements AuditClient |
| Bean output | A DefaultAuditClient, exposed as AuditClient |
| Customization | The application can declare its own AuditClient; the default bean backs off |
| Side effects | Does not send requests or open connections just because the ApplicationContext is created |

This contract helps answer operational questions:

- If the SDK is absent, can the application start? Yes; the SDK configuration branch does not apply.
- If the feature is disabled, does the client bean appear? No.
- If the user creates their own AuditClient, who wins? The user's bean.
- If the endpoint changes, does code need to change? No; it is a bound property.
- If we want to add a web endpoint, should that bean be added to the same class? Only if it belongs to the same capability and shares the same conditions; if it has web-specific inputs, split it into a separate configuration.

### 2.1. Short contract template for each configuration

| Field | Content to document |
| --- | --- |
| Purpose | One sentence describing the capability and why the class exists |
| Applies when | Classpath, property, resource, web type, or bean conditions |
| Requires | Required dependencies/beans/properties to produce the output |
| Provides | Bean type, bean name if meaningful, default implementation |
| Backs off when | User beans or conditions that prevent the default from being created |
| Ordering | Which auto-configurations must run before/after and why |
| Tests | ON/OFF, missing dependency, and override cases that must be verified |

There is no need to turn this table into lengthy boilerplate for every class. A few clear lines in Javadoc, together with tests expressing the contract, are usually sufficient.

## 3. Categorize auto-configuration inputs

Inputs are not just properties. Spring Boot provides many condition types; choose the right kind for what the configuration actually needs.

### 3.1. Classpath input

Use **@ConditionalOnClass** when a capability needs a specific library or API:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.sdk.AuditTransport")
public class AcmeAuditAutoConfiguration {
    // ...
}
```

Use the name attribute when you want to avoid a direct reference to a class that may be absent. If you use value = AuditTransport.class, Spring Boot can read annotation metadata using ASM without loading that class immediately.

If a bean method's signature or implementation references an optional class, isolate it in a nested **@Configuration** annotated with **@ConditionalOnClass**. The JVM may have to load the method's types before method-level conditions are evaluated. Conditional nested configurations prevent optional types from being processed too early.

Example:

```java
@AutoConfiguration
public class AcmeAuditAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(AuditTransport.class)
    static class TransportConfiguration {

        @Bean
        @ConditionalOnMissingBean(AuditClient.class)
        DefaultAuditClient auditClient(AuditProperties properties) {
            return new DefaultAuditClient(
                    new AuditTransport(),
                    properties.getEndpoint(),
                    properties.getTimeout());
        }
    }
}
```

In a real library, AuditTransport usually comes from an optional SDK dependency. This class and any SDK-only types should be kept inside the conditional configuration branch. Do not expose that SDK type in a public method signature of the outer configuration if the class might not exist.

### 3.2. Property input

Use **@ConditionalOnProperty** when a property determines whether a capability should be created:

```java
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
```

With havingValue left empty, @ConditionalOnProperty matches by default when the property exists and does not equal the string false. If the contract requires strictly boolean true, specify havingValue = "true" to avoid unexpected string values.

matchIfMissing should reflect the product choice:

- false: the feature is disabled by default if the user does not declare it.
- true: the feature is enabled by default if the property is absent.

Do not use a property condition just because a property has a name similar to the capability. The property should genuinely govern whether the configuration applies.

### 3.3. Bean input

**@ConditionalOnBean** and **@ConditionalOnMissingBean** check existing bean definitions.

For example, create an adapter only if the application has already provided a ConnectionFactory:

```java
@AutoConfiguration
@ConditionalOnBean(ConnectionFactory.class)
public class AcmeReactiveAutoConfiguration {
    // Beans that depend on ConnectionFactory.
}
```

For example, provide a default if no implementation has been declared by the application:

```java
@Bean
@ConditionalOnMissingBean(AuditClient.class)
DefaultAuditClient auditClient(AuditProperties properties) {
    return new DefaultAuditClient(properties);
}
```

Bean conditions depend on the bean definitions already processed at the time the condition is evaluated. Therefore, Spring Boot recommends using @ConditionalOnBean and @ConditionalOnMissingBean at the auto-configuration level: auto-configuration is processed after user-declared bean definitions.

When placing @ConditionalOnMissingBean on a bean method, the default target type is inferred from the return type. If the public extension point is the AuditClient interface, explicitly declare @ConditionalOnMissingBean(AuditClient.class) and return a concrete implementation such as DefaultAuditClient.

### 3.4. Resource and application type

Other input types:

| Condition | Checked input | Usage example |
| --- | --- | --- |
| @ConditionalOnResource | Resource exists | Enable integration only when a schema/resource file is present |
| @ConditionalOnWebApplication | Servlet or reactive web context | Register the appropriate web adapter |
| @ConditionalOnNotWebApplication | Non-web context | Configuration for batch/CLI |
| @ConditionalOnWarDeployment | WAR deployed to a traditional Servlet container | Difference between external container and embedded server |
| @ConditionalOnExpression | SpEL evaluation result | Cases that genuinely require a compound expression |

Limit @ConditionalOnExpression when specialized conditions are sufficient. Referencing beans in SpEL can cause beans to be initialized very early during refresh, before post-processing such as configuration properties binding finishes. At that point, the bean's state may be incomplete.

### 3.5. Distinguish conditions from dependency injection

Conditions answer **whether to register a bean/configuration**. Dependency injection answers **which beans a registered bean needs to operate**.

Example:

```java
@Bean
DefaultAuditClient auditClient(
        AuditTransport transport,
        AuditProperties properties) {
    return new DefaultAuditClient(
            transport,
            properties.getEndpoint(),
            properties.getTimeout());
}
```

Here transport is a dependency of the bean. There is no need to add @ConditionalOnBean(AuditTransport.class) if the configuration is already guarded by @ConditionalOnClass and transport is registered in the same branch. Avoid redundant conditions; every extra condition makes the contract harder to follow.

## 4. Define clear output beans

A bean method is where a configuration publishes its output. The return type should clearly show which bean is created.

### 4.1. Prefer concrete return types

Spring Boot recommends providing as much type information as possible in the method signature, especially when bean conditions rely on the return type.

Good example:

```java
@Bean
@ConditionalOnMissingBean(AuditClient.class)
DefaultAuditClient auditClient(AuditProperties properties) {
    return new DefaultAuditClient(properties);
}
```

On the application side, code can still inject via the abstraction:

```java
@Service
class AuditJob {

    private final AuditClient auditClient;

    AuditJob(AuditClient auditClient) {
        this.auditClient = auditClient;
    }
}
```

The method returns DefaultAuditClient so metadata and conditions have the concrete type; the application depends on AuditClient to keep coupling low.

If a method returns Object or an overly general interface, bean conditions may not see the required type from the method signature. Use a general return type only when that is genuinely the output contract.

### 4.2. One output should have one responsibility

Avoid a single configuration creating multiple unrelated beans just because they share a dependency:

```java
@AutoConfiguration
public class AcmeAutoConfiguration {

    @Bean
    AuditClient auditClient() { ... }

    @Bean
    MetricsExporter metricsExporter() { ... }

    @Bean
    AdminController adminController() { ... }

    @Bean
    ReactiveAdapter reactiveAdapter() { ... }
}
```

If beans have different input conditions, split them by capability. For example:

- AcmeAuditClientAutoConfiguration: the client and the objects needed for the client to work.
- AcmeAuditMetricsAutoConfiguration: metrics integration, only when Actuator/Micrometer is present.
- AcmeAuditWebAutoConfiguration: controller or web adapter, only in the right type of web application.
- AcmeAuditReactiveAutoConfiguration: reactive adapter and its dedicated dependencies.

A configuration can create multiple related beans, such as a client and a customizer for that same client. Do not over-split to the point where every bean has its own configuration class without yielding clearer boundaries.

### 4.3. Clearly publish bean names and types

When multiple beans share a type, the contract needs to state:

- Which bean is the default?
- Which bean is primary if there is a reason to select a default?
- Which beans carry qualifiers?
- Can the application replace the entire abstraction or only a single collaborator?
- When a user bean appears, does auto-configuration back off for one bean or the entire group?

Do not use @Primary to mask a design that has two default beans of the same type without clear roles. If there are two clients for different purposes, use separate interfaces, named qualifiers, or configure two independent capabilities.

## 5. Organize configuration classes by capability

Class names should let readers infer functionality without opening the file.

Example for an audit library:

```text
com.acme.audit.autoconfigure/
├── AcmeAuditClientAutoConfiguration.java
├── AcmeAuditWebAutoConfiguration.java
├── AcmeAuditMetricsAutoConfiguration.java
├── AcmeAuditProperties.java
└── package-info.java
```

Each class can have its own contract:

| Configuration | Purpose | Inputs | Outputs |
| --- | --- | --- | --- |
| AcmeAuditClientAutoConfiguration | Provide the audit client | SDK client class, acme.audit.enabled, AuditProperties, no existing AuditClient | Default AuditClient |
| AcmeAuditWebAutoConfiguration | Provide HTTP endpoint/adapter | Servlet web application, existing client | Web adapter/controller |
| AcmeAuditMetricsAutoConfiguration | Provide metrics for audit | Micrometer/Actuator classpath, client/registry | MeterBinder or metrics contributor |

Do not place @ConditionalOnWebApplication on the core client if the client can be used in batch or CLI applications. Web conditions should only surround web-specific beans.

### 5.1. Split optional integrations

If Kafka, AWS, Redis, or WebFlux SDKs are optional, create a nested configuration or separate module for each integration. A non-matching condition only prevents beans from being registered; it does not remove the dependency from the classpath. Splitting modules/starters lets applications pull in only the integrations they actually need.

### 5.2. Keep a dedicated package and avoid component scanning

Auto-configuration must be discovered via the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Example:

```text
com.acme.audit.autoconfigure.AcmeAuditClientAutoConfiguration
com.acme.audit.autoconfigure.AcmeAuditWebAutoConfiguration
com.acme.audit.autoconfigure.AcmeAuditMetricsAutoConfiguration
```

Auto-configuration should live in a dedicated package and be loaded only via the imports file. Do not make that package a target of component scanning. Also do not add @ComponentScan to auto-configuration to discover auxiliary components. Use explicit @Import for needed configuration/helper classes.

If an auto-configuration class is not top-level, its name in the imports resource uses `$` to separate the nested class. However, top-level classes are generally easier to refactor and review.

## 6. Properties are structured inputs

The property contract needs a dedicated namespace, clear data types, sensible defaults, and useful descriptions. Do not let individual bean methods read scattered keys with @Value when those keys belong to the same configuration group.

### 6.1. Use @ConfigurationProperties

Example:

```java
package com.acme.audit.autoconfigure;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.audit")
public class AuditProperties {

    private URI endpoint = URI.create("https://audit.example.test");

    private Duration timeout = Duration.ofSeconds(3);

    public URI getEndpoint() {
        return this.endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return this.timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

Properties have a clear namespace:

```yaml
acme:
  audit:
    enabled: true
    endpoint: https://audit.internal.example
    timeout: 5s
```

enabled is the input for the condition. endpoint and timeout are configuration data for the selected bean. Separating these roles helps readers see which property governs bean presence and which properties only configure the output.

Prefer Duration over long so users can write 5s, 250ms, or an appropriate unit. Use URI, enums, collections, and suitable domain types instead of leaving every value as a String.

### 6.2. Register properties intentionally

In auto-configuration, use @EnableConfigurationProperties:

```java
@AutoConfiguration
@EnableConfigurationProperties(AuditProperties.class)
public class AcmeAuditClientAutoConfiguration {
    // ...
}
```

If properties are only meaningful when an integration is present and enabled, you can place the annotation inside the nested configuration that carries the corresponding conditions. That way, the properties bean does not appear when the capability is not activated.

Do not rely on @ConfigurationPropertiesScan in the consumer application to discover property types inside the library. Auto-configuration should register the properties it owns itself.

### 6.3. Name and document properties

Use an organization/product prefix, such as acme.audit. Avoid placing library keys in namespaces owned by Spring Boot such as spring, server, or management.

Field Javadoc should explain the meaning without repeating the default value:

```java
/**
 * Endpoint used by the audit client.
 */
private URI endpoint = URI.create("https://audit.example.test");

/**
 * Timeout for one audit request.
 */
private Duration timeout = Duration.ofSeconds(3);
```

Enable spring-boot-configuration-processor so IDEs have metadata for the keys. If using a record for @ConfigurationProperties, document components with Javadoc @param tags at the class level.

If validation is required, add the appropriate validation dependency and use constraints such as @NotNull, @Min, or a custom validator. Metadata/IDE hints do not replace runtime validation.

## 7. Design conditions with exact intent

The clearer the conditions, the more predictable the behavior. Each condition should guard an actual requirement of the bean.

### 7.1. Combine class, property, and bean conditions

Client configuration example:

```java
@AutoConfiguration
public class AcmeAuditAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(AuditTransport.class)
    @ConditionalOnProperty(
            prefix = "acme.audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @EnableConfigurationProperties(AuditProperties.class)
    static class ClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(AuditClient.class)
        DefaultAuditClient auditClient(AuditProperties properties) {
            return new DefaultAuditClient(
                    new AuditTransport(),
                    properties.getEndpoint(),
                    properties.getTimeout());
        }
    }
}
```

The inputs of ClientConfiguration are visible right on the class and bean method:

- AuditTransport must be on the classpath.
- acme.audit.enabled must be true.
- AuditProperties is bound.
- No user-provided AuditClient bean exists yet.

The output is a DefaultAuditClient, injectable as AuditClient.

### 7.2. Place conditions at class level or bean method level?

| Location | When is it appropriate? | Result when not matched |
| --- | --- | --- |
| On the auto-configuration class | The entire capability does not apply | The configuration class is not registered |
| On a nested @Configuration | An optional branch requires dedicated classpath/property conditions | Only that branch is not applied |
| On a bean method | A specific bean is optional while other beans are still needed | Only that bean method is skipped |

If a condition guards a group of beans that depend on the same SDK, a nested configuration usually makes the contract easier to read. If only a single auxiliary bean is optional, a method-level condition may suffice.

### 7.3. Avoid redundant or contradictory conditions

For example, suppose a configuration already has @ConditionalOnClass(AuditTransport.class) and a bean method requires injecting AuditTransport. If transport is registered in the same branch, there is no need to add @ConditionalOnBean(AuditTransport.class) merely to repeat the classpath check.

Conversely, a class being on the classpath does not prove a bean instance has been registered. Class conditions and bean conditions are two different kinds of inputs.

Write conditions matching the exact question:

- Need an API present? @ConditionalOnClass.
- Need a property enabled? @ConditionalOnProperty.
- Need a registered bean? @ConditionalOnBean.
- Need to yield to a user bean? @ConditionalOnMissingBean.
- Need a resource to exist? @ConditionalOnResource.
- Need a specific web type? @ConditionalOnWebApplication.

## 8. Back-off is part of the customization contract

Auto-configuration provides defaults. Applications must have the right to replace a default with their own bean when the extension point is designed for it.

```java
@Bean
@ConditionalOnMissingBean(AuditClient.class)
DefaultAuditClient auditClient(AuditProperties properties) {
    return new DefaultAuditClient(properties);
}
```

If the application declares:

```java
@Configuration(proxyBeanMethods = false)
class CustomAuditConfiguration {

    @Bean
    AuditClient customAuditClient() {
        return payload -> "custom";
    }
}
```

auto-configuration does not create DefaultAuditClient. The application gets exactly one AuditClient per the contract.

### 8.1. Choose the right type for the missing-bean condition

If the published output is AuditClient, the condition should check AuditClient.class. If it checks DefaultAuditClient.class, a user-provided bean using a different implementation will not prevent the default from being created; the application could end up with two beans implementing the same interface.

### 8.2. Do not back off too broadly

Do not place @ConditionalOnMissingBean on the entire configuration class if the user only needs to replace one bean while still keeping other supporting beans. In that case, place the condition on the corresponding bean method.

Conversely, if all beans in a capability only make sense when the user has not provided a higher-level abstraction, a class-level condition can be appropriate. Document the back-off scope clearly in the contract and test it.

### 8.3. Callbacks and customizers

When finer customization than replacing the entire client is needed, publish a callback/customizer:

```java
@FunctionalInterface
public interface AuditClientCustomizer {

    void customize(AuditClientBuilder builder);
}
```

Auto-configuration can accept a list of customizers and apply them when building the client. This is an appropriate extension point when users only need to adjust timeout policies, headers, retry policies, or interceptors.

Add customizers only when there is a real need. Every callback is a public API requiring compatibility maintenance and a clear application order.

## 9. Ordering between auto-configurations

Do not use ordering to compensate for an unclear input/output contract.

If an auto-configuration must be applied after another configuration, declare:

```java
@AutoConfiguration(after = WebMvcAutoConfiguration.class)
public class AcmeAuditWebAutoConfiguration {
    // Web-specific beans
}
```

Or use before, after, beforeName, afterName, @AutoConfigureBefore, @AutoConfigureAfter, and @AutoConfigureOrder.

Several principles:

- Declare ordering only when the configuration genuinely depends on other bean definitions/configurations.
- Use afterName when you do not want a direct compile-time dependency on an optional module's class.
- Auto-configuration ordering determines the order in which bean definitions are registered.
- It does not determine bean instance initialization order; the dependency graph and @DependsOn govern initialization relationships.
- @Order on beans typically controls ordering within collections/injection, not a replacement for @AutoConfigureAfter.

With @ConditionalOnBean and @ConditionalOnMissingBean, remember they inspect the bean definitions processed up to that point. Therefore, place bean conditions in auto-configuration and declare explicit ordering when real dependencies exist.

## 10. Avoid side effects during configuration registration

An auto-configuration should describe how to create beans, not execute business logic when the class is loaded.

Avoid:

- Sending HTTP requests in static initializers.
- Connecting to a database or Kafka merely to check credentials while parsing configuration.
- Reading large files or calling remote discovery services inside bean factory methods.
- Registering global listeners without a clear lifecycle.
- Calling ApplicationContext.getBean() to look up dependencies manually instead of constructor/method injection.
- Using SpEL to reference beans in conditions when beans might be initialized too early.

Bean factory methods should construct objects and wire dependencies. Opening connections or executing requests should live in well-designed lifecycle hooks or operations with timeouts, cleanup, and error handling.

A test context should be able to start without calling external systems. This makes auto-configuration easy to test and prevents applications from hitting unexpected side effects simply by adding the starter.

## 11. Complete example: an AuditClient with a clear contract

This section combines the principles into a minimal runnable project on Java 17 and Spring Boot 3.3.13. AuditTransport acts as a small stand-in for an external SDK; in a real library, this class comes from an optional transport dependency.

### 11.1. Directory structure

```text
acme-audit-autoconfigure/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/audit/
    │   │   ├── AuditClient.java
    │   │   ├── AuditProperties.java
    │   │   ├── AuditTransport.java
    │   │   ├── DefaultAuditClient.java
    │   │   └── autoconfigure/AcmeAuditAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/acme/audit/autoconfigure/
        └── AcmeAuditAutoConfigurationTest.java
```

### 11.2. Maven POM

File pom.xml:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>acme-audit-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

In a real library, the transport SDK can be declared optional in the autoconfigure module and re-added by the starter as a default dependency. The lab example places AuditTransport in source so tests run standalone without a vendor SDK.

### 11.3. Output abstraction

File AuditClient.java:

```java
package com.acme.audit;

public interface AuditClient {

    String target();
}
```

This interface is the contract used by consumer applications. Consumers do not need to depend on a concrete implementation.

### 11.4. Input properties

File AuditProperties.java:

```java
package com.acme.audit;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.audit")
public class AuditProperties {

    private URI endpoint = URI.create("https://audit.example.test");

    private Duration timeout = Duration.ofSeconds(3);

    public URI getEndpoint() {
        return this.endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return this.timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

### 11.5. Transport dependency

File AuditTransport.java:

```java
package com.acme.audit;

import java.net.URI;
import java.time.Duration;

public final class AuditTransport {

    public String describe(URI endpoint, Duration timeout) {
        return endpoint + " (timeout=" + timeout + ")";
    }
}
```

This class represents the transport SDK API. The describe method only builds a string to demonstrate wiring; it performs no network I/O.

### 11.6. Default implementation

File DefaultAuditClient.java:

```java
package com.acme.audit;

import java.net.URI;
import java.time.Duration;

public final class DefaultAuditClient implements AuditClient {

    private final AuditTransport transport;

    private final URI endpoint;

    private final Duration timeout;

    public DefaultAuditClient(
            AuditTransport transport,
            URI endpoint,
            Duration timeout) {
        this.transport = transport;
        this.endpoint = endpoint;
        this.timeout = timeout;
    }

    @Override
    public String target() {
        return this.transport.describe(this.endpoint, this.timeout);
    }

    public URI getEndpoint() {
        return this.endpoint;
    }

    public Duration getTimeout() {
        return this.timeout;
    }
}
```

The implementation receives dependencies through its constructor. There is no hidden ApplicationContext lookup and no external connection in the constructor.

### 11.7. Auto-configuration class

File AcmeAuditAutoConfiguration.java:

```java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditClient;
import com.acme.audit.AuditProperties;
import com.acme.audit.AuditTransport;
import com.acme.audit.DefaultAuditClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class AcmeAuditAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(AuditTransport.class)
    @ConditionalOnProperty(
            prefix = "acme.audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @EnableConfigurationProperties(AuditProperties.class)
    static class ClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(AuditClient.class)
        DefaultAuditClient auditClient(AuditProperties properties) {
            return new DefaultAuditClient(
                    new AuditTransport(),
                    properties.getEndpoint(),
                    properties.getTimeout());
        }
    }
}
```

Read this class's contract:

- **Purpose:** create the default audit client.
- **Classpath input:** AuditTransport must be present.
- **Property input:** acme.audit.enabled=true.
- **Configuration input:** AuditProperties.
- **Bean input:** no user-provided AuditClient exists yet.
- **Output:** a DefaultAuditClient, injectable as AuditClient.
- **Back-off:** user AuditClient wins; the default is not created.

@ConditionalOnClass sits on the nested configuration to isolate the optional transport type. @ConditionalOnMissingBean sits on the default factory method, allowing replacement at the exact extension point.

### 11.8. Register auto-configuration

File src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports:

```text
com.acme.audit.autoconfigure.AcmeAuditAutoConfiguration
```

Auto-configuration is discovered by Spring Boot through this resource. Do not add @ComponentScan to the configuration class.

### 11.9. Test the four key contracts

File AcmeAuditAutoConfigurationTest.java:

```java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditClient;
import com.acme.audit.AuditProperties;
import com.acme.audit.AuditTransport;
import com.acme.audit.DefaultAuditClient;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAuditAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AcmeAuditAutoConfiguration.class));

    @Test
    void disabledByDefaultCreatesNoAuditClient() {
        this.contextRunner.run(context -> {
            assertThat(context).doesNotHaveBean(AuditClient.class);
            assertThat(context).doesNotHaveBean(AuditProperties.class);
        });
    }

    @Test
    void enabledCreatesDefaultClientAndBindsProperties() {
        this.contextRunner
                .withPropertyValues(
                        "acme.audit.enabled=true",
                        "acme.audit.endpoint=https://audit.internal.example",
                        "acme.audit.timeout=5s")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditClient.class);
                    assertThat(context).hasSingleBean(DefaultAuditClient.class);

                    DefaultAuditClient client =
                            context.getBean(DefaultAuditClient.class);

                    assertThat(client.getEndpoint().toString())
                            .isEqualTo("https://audit.internal.example");
                    assertThat(client.getTimeout())
                            .isEqualTo(java.time.Duration.ofSeconds(5));
                });
    }

    @Test
    void userClientReplacesDefaultClient() {
        this.contextRunner
                .withUserConfiguration(UserAuditConfiguration.class)
                .withPropertyValues("acme.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditClient.class);
                    assertThat(context).doesNotHaveBean(DefaultAuditClient.class);
                    assertThat(context.getBean(AuditClient.class).target())
                            .isEqualTo("custom");
                });
    }

    @Test
    void missingTransportClassDisablesOnlyThisIntegration() {
        this.contextRunner
                .withClassLoader(new FilteredClassLoader(AuditTransport.class))
                .withPropertyValues("acme.audit.enabled=true")
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context).doesNotHaveBean(AuditClient.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserAuditConfiguration {

        @Bean
        AuditClient customAuditClient() {
            return () -> "custom";
        }
    }
}
```

The four tests verify:

1. Feature disabled by default: no client and no properties bean registered for the client branch.
2. Feature enabled: default client appears and endpoint/timeout are bound correctly.
3. User provides client: default implementation backs off.
4. SDK class absent: context still starts, and the integration branch creates no bean.

FilteredClassLoader simulates a classpath missing a dependency. This is a useful way to test auto-configuration with optional SDKs.

### 11.10. Run tests

From the project directory:

```bash
mvn clean test
```

Expected output:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Detailed summaries may vary by Maven Surefire version, but all four tests must pass.

### 11.11. Verify the packaged artifact

After packaging:

```bash
mvn clean package
jar tf target/acme-audit-autoconfigure-1.0.0.jar
```

The JAR must contain:

```text
com/acme/audit/autoconfigure/AcmeAuditAutoConfiguration.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

To verify end-to-end, have an independent consumer project that only depends on the installed or published starter/JAR. The consumer uses @EnableAutoConfiguration and verifies the bean appears without importing the auto-configuration class directly. ApplicationContextRunner above focuses on testing the internal contract of the configuration; the consumer smoke test additionally verifies the imports resource and packaging.

## 12. Test by input/output matrix

A good test suite expresses meaningful contract combinations rather than checking only a single happy path.

| Classpath | Property | User bean | Expected result |
| --- | --- | --- | --- |
| SDK present | Missing/false | No | No default client |
| SDK present | true | No | Exactly one default client |
| SDK present | true | AuditClient present | User client kept, default backs off |
| SDK absent | true | No | Context starts; no integration client |
| SDK present | true, endpoint override | No | Client uses bound endpoint |
| SDK present | true, timeout override | No | Client uses bound timeout |

Beyond the main matrix, also test:

- Properties validation on invalid input.
- Servlet and reactive contexts if web-specific configuration exists.
- Two integrations present simultaneously on the classpath.
- Beans of the same type with different qualifiers if the library has multiple clients.
- Condition evaluation report when a test fails to create the expected bean.

Use ConditionEvaluationReportLoggingListener at INFO/DEBUG level when you need to see which conditions matched or did not match. Do not guess from a missing bean; the report pinpoints which property, classpath, or bean condition was not satisfied.

## 13. Common design mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| One auto-configuration class has unrelated beans | Multiple capabilities lumped into one configuration | Split by client, web, metrics, integration |
| Unclear why a bean is created | Scattered conditions or vague property names | Write the contract and group conditions by capability |
| User bean is present yet default is still created | @ConditionalOnMissingBean checks the wrong type | Check against the public extension point |
| Auto-configuration fails when SDK is absent | Optional type appears in method signature/config outside guarded branch | Use a nested configuration with @ConditionalOnClass |
| Bean condition is flaky | Relies on bean definitions processed earlier | Place bean conditions in auto-configuration and declare ordering when needed |
| Tests pass but starter consumer fails | Tests import the class directly, bypassing discovery | Add a consumer smoke test via the imports resource |
| Condition sees the interface but not the implementation | Bean method return type is too general | Return the concrete implementation type |
| App cannot swap a small collaborator | Only option is replacing the entire bean | Consider callbacks/customizers with a clear contract |
| Bean connects to external system at startup | Constructor/configuration has side effects | Separate object creation from I/O operations |
| Property namespace collision | Keys placed under Spring Boot namespaces | Use the library's dedicated prefix |
| Condition expression initializes bean too early | SpEL references beans inside a condition | Use specialized property/class/bean conditions |
| Auto-configuration is component-scanned | Package falls under component scan | Use imports resource and a dedicated package |

## 14. Auto-configuration maintenance workflow

When modifying a configuration class, review in order:

1. **Is the purpose still accurate?** If a capability has split, move its beans to a new configuration.
2. **Have inputs changed?** Classpath, property, bean prerequisites, resources, or web types.
3. **Have outputs changed?** Bean type, bean name, default implementation, scope, or lifecycle.
4. **Is back-off still right?** Can old/new user beans still replace the default?
5. **Is ordering truly necessary?** Do not use ordering to work around unclear dependency injection.
6. **Are optional dependencies isolated?** Test with a classloader missing the SDK.
7. **Do tests reflect the new contract?** Add tests for both matching and non-matching branches.
8. **Are metadata/documentation updated?** Describe properties, defaults, output beans, and migration behavior.

When renaming an auto-configuration class or package, update the imports resource. If the class is referenced in before/after or excludes, consider Spring Boot's resource replacements to support class name migration. Never leave both the old and new classes registering the same set of beans without a compatibility plan.

## 15. Pre-merge review checklist

**Purpose and boundaries**

- [ ] Each configuration class describes one specific capability.
- [ ] Classes do not mix beans from integrations with different input conditions.
- [ ] Auto-configuration package is dedicated and not targeted by component scanning.
- [ ] Component scanning is not enabled inside auto-configuration.

**Inputs**

- [ ] Classpath conditions reflect genuinely required dependencies.
- [ ] Optional classes are isolated in nested configurations.
- [ ] Property conditions use a dedicated prefix and clear semantics.
- [ ] matchIfMissing reflects the published ON/OFF default.
- [ ] Bean conditions check the right public extension point.
- [ ] @ConfigurationProperties has appropriate types, defaults, validation, and documentation.
- [ ] Resource/web conditions are used only when the capability requires them.

**Outputs**

- [ ] Each output bean has a clear type and responsibility.
- [ ] Bean methods expose concrete return types where appropriate.
- [ ] User beans can override defaults per the contract.
- [ ] Bean names/qualifiers/primary have clear meaning when multiple beans share a type.
- [ ] Bean factories do not perform unnecessary external side effects.

**Ordering and maintainability**

- [ ] @AutoConfigureBefore/@AutoConfigureAfter are used only for real dependencies.
- [ ] Auto-configuration order is not confused with bean instantiation order.
- [ ] Optional integrations are split by capability when the dependency graph requires it.
- [ ] Imports resource contains exact FQCNs and is packaged in the JAR.

**Testing**

- [ ] Tests cover disabled/default behavior.
- [ ] Tests cover enabled feature and property binding.
- [ ] Tests cover user bean back-off.
- [ ] Tests cover missing optional dependencies using FilteredClassLoader.
- [ ] Tests cover web contexts if configuration depends on web types.
- [ ] Tests cover consumer artifact/discovery via imports resource.
- [ ] Condition Evaluation Report can be inspected when a test fails.

**Takeaway:** An auto-configuration is maintainable when a reader can look at the class and immediately understand which capability it provides, which classes/properties/beans it requires, and which beans it creates. Write the contract first, group conditions by capability, use typed properties, return concrete bean types, and let user beans replace defaults at the proper extension point. Split optional integrations, justify ordering, and use ApplicationContextRunner to verify each input combination. When purpose, inputs, and outputs are clear, configurations scale cleanly without turning into an unpredictable tangle of beans.

## Official Documentation

- Spring Boot 3.3.13 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3.13 — Externalized Configuration and ConfigurationProperties: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3.13 API — AutoConfiguration: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3.13 API — ConditionalOnMissingBean: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.3.13 API — ConditionalOnClass: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.3.13 API — ConditionalOnProperty: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
