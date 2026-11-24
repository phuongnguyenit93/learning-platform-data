# Contract: missing dependencies must not cause failures outside the feature scope

## 1. Goal: a missing optional library only disables that specific integration

A Spring Boot library often supports multiple features. The core functionality can work independently, while some integrations require additional external libraries such as Jackson, Kafka, Redis, or a vendor SDK.

A good starter must uphold this contract:

- If an optional library is **not on the classpath**, the application still starts and core features remain usable.
- Beans belonging to the optional integration are not registered when required dependencies are absent.
- Classes referencing optional APIs are not forced to be loaded by the JVM when the integration is not enabled.
- If the library is present but an infrastructure bean required by the integration has not been provided, the integration must not break unrelated parts.
- When the user explicitly enables the feature and required dependencies are present, the integration is configured normally.
- Users can replace default beans with their own implementations.

Example: an audit library has a core event-recording API. The feature that encodes events as JSON requires Jackson. If the application does not use JSON, the absence of Jackson must not cause AuditService or basic audit beans to fail.

This article uses **Spring Boot 3.5.16, Spring Framework 6.2, and Java 17+**. The main examples use Spring Boot conditions, nested configurations, and ApplicationContextRunner.

## 2. Distinguish three states: class present, bean present, and feature enabled

An optional integration typically requires multiple independent conditions:

| Condition | Question | Common annotation |
| --- | --- | --- |
| Classpath | Is the required library actually packaged? | @ConditionalOnClass, @ConditionalOnMissingClass |
| ApplicationContext | Has the required infrastructure bean been provided? | @ConditionalOnBean, @ConditionalOnMissingBean |
| User configuration | Did the user explicitly enable the feature? | @ConditionalOnProperty |

Example with the JSON feature:

- ObjectMapper must be present on the classpath.
- An ObjectMapper bean must exist in the context, provided either by Spring Boot or by the application.
- The property acme.audit.json.enabled must be set to true.
- If the application has already provided its own AuditJsonCodec, auto-configuration does not create a second default codec.

The decision flow can be visualized as:

~~~text
AuditAutoConfiguration is discovered
                 |
                 v
Core AuditService is registered
                 |
                 v
Is Jackson class on classpath?
          /              \
         No              Yes
          |                |
  Skip JSON config     ObjectMapper bean present?
                          /          \
                         No          Yes
                          |            |
                  Skip JSON config  Property enabled?
                                      /          \
                                     No          Yes
                                      |            |
                              Skip JSON config  Create JSON codec
~~~

These conditions answer different questions. Checking only the classpath does not prove an infrastructure bean has been configured. Checking only a property does not make a missing class appear on the classpath.

## 3. Why can a missing optional dependency cause NoClassDefFoundError?

Suppose a library has an auto-configuration:

~~~java
@AutoConfiguration
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnClass(ObjectMapper.class)
    AuditJsonCodec auditJsonCodec(ObjectMapper objectMapper) {
        return new JacksonAuditJsonCodec(objectMapper);
    }
}
~~~

The intent is to create AuditJsonCodec only when Jackson is present. However, the `@Bean` method signature directly references ObjectMapper.

The JVM may need to load and resolve types in the method signature before the method's condition is evaluated. When Jackson is not on the classpath, a linkage error can happen before Spring has a chance to skip the method.

The error message can look like:

~~~text
java.lang.NoClassDefFoundError:
com/fasterxml/jackson/databind/ObjectMapper
~~~

This is why `@ConditionalOnClass` on a `@Bean` method is not always enough to isolate optional types.

Spring Boot recommends placing methods that reference optional types inside a separate configuration class with `@ConditionalOnClass` at the class level. Spring reads the configuration's metadata to evaluate the condition before loading that optional configuration.

### 3.1. Safe structure: nested static configuration

~~~java
@AutoConfiguration
public class AuditAutoConfiguration {

    // Core beans do not reference Jackson.

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name =
            "com.fasterxml.jackson.databind.ObjectMapper")
    static class JacksonConfiguration {

        @Bean
        AuditJsonCodec auditJsonCodec(ObjectMapper objectMapper) {
            return new JacksonAuditJsonCodec(objectMapper);
        }
    }
}
~~~

Key points:

- AuditAutoConfiguration has no fields, constructors, or method signatures referencing ObjectMapper.
- JacksonConfiguration is isolated as a nested static configuration.
- @ConditionalOnClass is placed on the configuration class so Spring evaluates the library's presence before processing methods that depend on it.
- If Jackson is absent, the JSON configuration section is not activated; core beans can still be created.

@ConditionalOnClass(ObjectMapper.class) can be used directly on the configuration class because Spring Boot reads annotation metadata via ASM before loading the class. The String-based `name` attribute is also appropriate and useful when you want to avoid referencing optional classes in the outer class source.

**Do not leak optional types back into the outer class** through return types, method parameters, fields, superclasses, interfaces, or static initializers. Doing so breaks the class-loading boundary that the nested configuration establishes.

## 4. Use the right condition for each dependency type

### 4.1. @ConditionalOnClass: library is on the classpath

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name =
        "com.fasterxml.jackson.databind.ObjectMapper")
static class JacksonConfiguration {
}
~~~

Use this when the feature depends on a specific class or library.

@ConditionalOnClass only confirms that the requested class can be found. It does not confirm that:

- A corresponding bean has been created.
- The library version is compatible with the API used by the code.
- The feature property has been enabled.
- The external service has connected successfully.

If a class must be absent, `@ConditionalOnMissingClass` can be used.

### 4.2. @ConditionalOnBean: infrastructure bean has been provided

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnBean(type =
        "com.fasterxml.jackson.databind.ObjectMapper")
static class JacksonConfiguration {
}
~~~

Use this when the integration requires a Spring-managed collaborator, such as ObjectMapper, RedisConnectionFactory, KafkaTemplate, DataSource, or an SDK client.

Having a class on the classpath does not mean the bean exists in the context. For example, an application may add jackson-databind without configuring an ObjectMapper; an integration needing a mapper should not assume that bean exists.

When the condition does not match, Spring skips the optional configuration. The core part does not need to depend on that bean.

### 4.3. @ConditionalOnProperty: user explicitly enables the feature

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "acme.audit.json",
        name = "enabled",
        havingValue = "true")
static class JacksonConfiguration {
}
~~~

Property:

~~~properties
acme.audit.json.enabled=true
~~~

When the property is not declared, the condition above does not match because `matchIfMissing` defaults to `false`.

Explicit opt-in suits integrations that expand dependencies, consume resources, or extend application behavior. Users can include the library while keeping the feature off until explicitly enabled.

### 4.4. @ConditionalOnMissingBean: allow the application to replace the default implementation

~~~java
@Bean
@ConditionalOnMissingBean(AuditJsonCodec.class)
AuditJsonCodec auditJsonCodec(ObjectMapper objectMapper) {
    return new JacksonAuditJsonCodec(objectMapper);
}
~~~

If the application provides its own AuditJsonCodec, auto-configuration does not register the default codec.

This is part of the starter extensibility contract. Do not force users to use the library's implementation if they already have a suitable implementation of their own.

### 4.5. Combining conditions

An optional integration may need class, bean, and property conditions simultaneously:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name =
        "com.fasterxml.jackson.databind.ObjectMapper")
@ConditionalOnBean(type =
        "com.fasterxml.jackson.databind.ObjectMapper")
@ConditionalOnProperty(
        prefix = "acme.audit.json",
        name = "enabled",
        havingValue = "true")
static class JacksonConfiguration {
}
~~~

Only when all three conditions match is the JSON configuration processed.

Do not add conditions merely to make code look safer. Each condition should correspond to a real requirement of the integration and have tests for both matching and non-matching cases.

## 5. Do not let optional types leak into the core API

Suppose AuditService only records events. If this class has a constructor taking ObjectMapper, then the entire audit functionality becomes dependent on Jackson:

~~~java
public class AuditService {

    private final ObjectMapper objectMapper;

    public AuditService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }
}
~~~

Even when users do not use JSON, Spring still has to resolve the ObjectMapper dependency to create AuditService.

A better design separates the core API and optional adapters:

~~~java
public record AuditEvent(String action, String actor) {
}
~~~

~~~java
public class AuditService {

    public AuditEvent createEvent(String action, String actor) {
        return new AuditEvent(action, actor);
    }
}
~~~

~~~java
public interface AuditJsonCodec {

    String encode(AuditEvent event);
}
~~~

AuditService and AuditEvent do not know Jackson exists. Only the JacksonAuditJsonCodec implementation inside the nested configuration references ObjectMapper.

Benefits:

- The core API is not locked into a single JSON library.
- Users can choose a different serializer or omit serialization altogether.
- Optional dependencies can be absent without affecting core beans.
- Core tests do not need to construct a mapper or pull JSON libraries into the context.
- Integrations can be replaced with custom implementations via `@ConditionalOnMissingBean`.

If you need to connect the core API to an optional capability, use an interface belonging to the core module or a provider that may be absent. Avoid putting external library classes into the public signatures of the core API.

## 6. Managing dependencies in Maven, Gradle, and starter modules

Runtime conditions only matter when dependencies are declared properly in artifacts.

### 6.1. Maven optional dependency

In the auto-configuration module:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <optional>true</optional>
</dependency>
~~~

`optional=true` means the dependency remains available when building and testing this module, but is not propagated transitively to projects consuming the module.

Therefore:

- The auto-configuration module can compile the Jackson integration.
- Consumers do not automatically pull in Jackson simply by adding the auto-configuration module.
- If consumers want the JSON integration, they must add Jackson or a dedicated starter that brings Jackson onto the classpath.

**Optional dependencies and `@ConditionalOnClass` solve two different problems.** Maven `optional` controls dependency propagation; Spring conditions control runtime configuration. `optional=true` alone does not prevent `NoClassDefFoundError` if code still references the optional type in an unconditionally loaded class.

### 6.2. Gradle compileOnly

With Gradle, an optional library can be declared as:

~~~kotlin
dependencies {
    compileOnly("com.fasterxml.jackson.core:jackson-databind")

    testImplementation("com.fasterxml.jackson.core:jackson-databind")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

`compileOnly` lets the module compile against the Jackson API without putting that dependency onto the consumer's runtime classpath. Tests still need the dependency to exercise the Jackson integration branch.

Consumers wanting to enable the feature must declare the runtime dependency themselves or use a dedicated starter.

### 6.3. Splitting starters by optional feature

When a library has multiple integrations, modules can be organized like this:

~~~text
acme-audit/
├── acme-audit-core
├── acme-audit-spring-boot-autoconfigure
├── acme-audit-spring-boot-starter
├── acme-audit-spring-boot-starter-json
└── acme-audit-spring-boot-starter-kafka
~~~

| Module | Dependencies and responsibility |
| --- | --- |
| acme-audit-core | Event API and core logic |
| acme-audit-spring-boot-autoconfigure | Auto-configuration, properties, and optional integrations |
| acme-audit-spring-boot-starter | Dependencies needed for basic audit functionality |
| acme-audit-spring-boot-starter-json | Basic starter plus Jackson and required JSON configuration |
| acme-audit-spring-boot-starter-kafka | Basic starter plus Kafka integration |

This split lets consumers pick the exact features they need. Do not force every application to install Kafka, Redis, or Jackson just to use a core API.

For a small library with only one feature, splitting into many modules is unnecessary. Create separate starters only when it clarifies the dependency contract.

## 7. Complete example: audit core working when Jackson is absent

This example proves the following states:

1. AuditService can always be created.
2. The JSON codec appears only when Jackson is on the classpath, an ObjectMapper bean exists, and the property is enabled.
3. The application can replace the default codec.
4. Missing Jackson does not cause the core context to fail.

### 7.1. Project structure

~~~text
audit-optional-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/audit/
    │   │   ├── AuditEvent.java
    │   │   ├── AuditService.java
    │   │   ├── AuditJsonCodec.java
    │   │   └── autoconfigure/
    │   │       └── AuditAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/audit/
            └── AuditAutoConfigurationTests.java
~~~

### 7.2. Maven dependencies

File pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>audit-optional-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

The Jackson dependency is marked optional. This module can still compile the JSON integration and test the Jackson-present branch, while consumers do not automatically receive that dependency.

### 7.3. Core API independent of Jackson

File AuditEvent.java:

~~~java
package com.example.audit;

public record AuditEvent(String action, String actor) {
}
~~~

File AuditService.java:

~~~java
package com.example.audit;

public class AuditService {

    public AuditEvent createEvent(String action, String actor) {
        return new AuditEvent(action, actor);
    }
}
~~~

File AuditJsonCodec.java:

~~~java
package com.example.audit;

public interface AuditJsonCodec {

    String encode(AuditEvent event);
}
~~~

These three types do not import any Jackson classes.

### 7.4. Auto-configuration isolating the JSON section

File autoconfigure/AuditAutoConfiguration.java:

~~~java
package com.example.audit.autoconfigure;

import com.example.audit.AuditJsonCodec;
import com.example.audit.AuditService;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration(
        afterName = "org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration")
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AuditService auditService() {
        return new AuditService();
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name =
            "com.fasterxml.jackson.databind.ObjectMapper")
    @ConditionalOnBean(type =
            "com.fasterxml.jackson.databind.ObjectMapper")
    @ConditionalOnProperty(
            prefix = "acme.audit.json",
            name = "enabled",
            havingValue = "true")
    static class JacksonConfiguration {

        @Bean
        @ConditionalOnMissingBean(AuditJsonCodec.class)
        AuditJsonCodec auditJsonCodec(ObjectMapper objectMapper) {
            return event -> {
                try {
                    return objectMapper.writeValueAsString(event);
                }
                catch (JsonProcessingException exception) {
                    throw new IllegalStateException(
                            "Could not encode audit event as JSON",
                            exception);
                }
            };
        }
    }
}
~~~

Analysis:

- The AuditService bean lives in the outer configuration and has no Jackson dependency.
- JacksonConfiguration is a nested static configuration.
- @ConditionalOnClass requires ObjectMapper to be present.
- @ConditionalOnBean requires the context to already contain a mapper bean.
- @ConditionalOnProperty requires the user to enable acme.audit.json.enabled=true.
- @ConditionalOnMissingBean(AuditJsonCodec.class) lets the application supply its own codec.
- afterName orders this auto-configuration after Spring Boot's Jackson auto-configuration if that auto-configuration is present, so the bean condition can see the mapper registered by Boot.

Jackson imports appear in the source file because the auto-configuration module needs to compile the nested integration. However, methods and signatures referencing Jackson live inside the nested configuration guarded by the class condition. Do not move ObjectMapper into methods or fields of the outer AuditAutoConfiguration class.

### 7.5. Register auto-configuration

Create file:

src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

Content:

~~~text
com.example.audit.autoconfigure.AuditAutoConfiguration
~~~

Spring Boot discovers the auto-configuration through the imports file. No broad package component scanning is needed to find this configuration class.

## 8. Test classpaths with and without dependencies

ApplicationContextRunner creates lightweight contexts to test each combination of conditions. FilteredClassLoader simulates a class or package being absent from the runtime classpath.

### 8.1. Complete test class

File src/test/java/com/example/audit/AuditAutoConfigurationTests.java:

~~~java
package com.example.audit;

import com.example.audit.autoconfigure.AuditAutoConfiguration;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AuditAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AuditAutoConfiguration.class));

    @Test
    void coreServiceWorksWhenJacksonIsMissing() {
        this.contextRunner
                .withClassLoader(
                        new FilteredClassLoader("com.fasterxml.jackson"))
                .withPropertyValues("acme.audit.json.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AuditService.class);
                    assertThat(context).doesNotHaveBean(AuditJsonCodec.class);
                });
    }

    @Test
    void jsonFeatureIsDisabledWhenPropertyIsMissing() {
        this.contextRunner
                .withUserConfiguration(JacksonMapperConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AuditService.class);
                    assertThat(context).doesNotHaveBean(AuditJsonCodec.class);
                });
    }

    @Test
    void jsonFeatureIsDisabledWhenMapperBeanIsMissing() {
        this.contextRunner
                .withPropertyValues("acme.audit.json.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AuditService.class);
                    assertThat(context).doesNotHaveBean(AuditJsonCodec.class);
                });
    }

    @Test
    void jsonFeatureWorksWhenDependencyBeanAndPropertyArePresent() {
        this.contextRunner
                .withUserConfiguration(JacksonMapperConfiguration.class)
                .withPropertyValues("acme.audit.json.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AuditService.class);
                    assertThat(context).hasSingleBean(AuditJsonCodec.class);

                    AuditJsonCodec codec =
                            context.getBean(AuditJsonCodec.class);

                    assertThat(codec.encode(
                            new AuditEvent("LOGIN", "alice")))
                            .isEqualTo(
                                    "{\"action\":\"LOGIN\",\"actor\":\"alice\"}");
                });
    }

    @Test
    void userCodecMakesDefaultCodecBackOff() {
        this.contextRunner
                .withUserConfiguration(
                        JacksonMapperConfiguration.class,
                        CustomCodecConfiguration.class)
                .withPropertyValues("acme.audit.json.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AuditJsonCodec.class);

                    AuditJsonCodec codec =
                            context.getBean(AuditJsonCodec.class);

                    assertThat(codec.encode(
                            new AuditEvent("LOGIN", "alice")))
                            .isEqualTo("custom:alice");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class JacksonMapperConfiguration {

        @Bean
        ObjectMapper objectMapper() {
            return new ObjectMapper();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomCodecConfiguration {

        @Bean
        AuditJsonCodec customAuditJsonCodec() {
            return event -> "custom:" + event.actor();
        }
    }
}
~~~

### 8.2. Run tests

~~~bash
mvn test -Dtest=AuditAutoConfigurationTests
~~~

Expected result: **5 tests PASS**.

| Test | Classpath | Mapper bean | Property | Result |
| --- | --- | --- | --- | --- |
| Core without Jackson | Jackson missing | Absent | true | Core works, JSON codec absent |
| Property missing | Jackson present | Present | Not declared | JSON codec absent |
| Mapper missing | Jackson present | Absent | true | JSON codec absent |
| All conditions match | Jackson present | Present | true | JSON codec created |
| User codec supplied | Jackson present | Present | true | Default codec backs off |

The first test is the most important proof: even though the property requests JSON, lacking the Jackson library does not cause AuditService to fail or prevent the context from starting.

FilteredClassLoader("com.fasterxml.jackson") hides the Jackson package in the test context's classloader. This simulates a missing library at runtime without removing the dependency from the test project.

## 9. When the dependency is present but the bean is not

A common mistake is using only `@ConditionalOnClass`:

~~~java
@ConditionalOnClass(name =
        "com.fasterxml.jackson.databind.ObjectMapper")
static class JacksonConfiguration {
}
~~~

The Jackson class may exist on the classpath without an ObjectMapper bean in the context. In that case, a `@Bean` method needing a mapper can still fail because it cannot resolve the dependency.

If the integration needs a Spring-managed bean, add `@ConditionalOnBean`.

There are two design choices:

1. **Require the application to provide the bean:** appropriate when sharing a centrally configured mapper, such as the mapper created by Spring Boot or the application.
2. **Create the collaborator inside the integration:** appropriate when the library has a sensible default and does not need shared configuration. In that case, check for conflicts and allow user override via `@ConditionalOnMissingBean`.

Do not assume a bean exists while declaring neither a condition nor a default. The dependency contract must be explicit.

## 10. Condition ordering: do not let @ConditionalOnBean run too early

`@ConditionalOnBean` and `@ConditionalOnMissingBean` evaluate bean definitions processed up to the moment the condition runs. If an auto-configuration needs a bean provided by another auto-configuration, ordering can affect the result.

For example, the Jackson mapper may be created by JacksonAutoConfiguration. If a custom integration checks for ObjectMapper before Jackson auto-configuration is processed, the condition may fail to match.

You can declare ordering:

~~~java
@AutoConfiguration(
        afterName = "org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration")
public class AuditAutoConfiguration {
}
~~~

`afterName` uses a class name String so the outer auto-configuration class does not need to import the Jackson auto-configuration type.

Key notes:

- Auto-configuration ordering controls bean definition registration order.
- It does not determine instance instantiation order; the dependency graph determines that.
- User-defined bean definitions are processed before auto-configuration, so application-declared beans are normally visible to conditions.
- Do not rely on accidental classpath order or imports file order.

If an optional bean may be created by a specific auto-configuration, use explicit ordering and test both with and without the dependency.

## 11. Do not catch NoClassDefFoundError as an optional dependency mechanism

A tempting shortcut is:

~~~java
try {
    Class.forName("com.example.optional.OptionalClient");
}
catch (Throwable exception) {
    // Ignore and continue.
}
~~~

Or catching `NoClassDefFoundError` around the entire bean creation process.

This is poor design because:

- Linkage errors can appear after a class has been partially loaded.
- Catching `Throwable` can swallow serious JVM errors.
- An incompatible library version error can be mistaken for a missing optional dependency.
- The context may proceed missing a bean that another component expects.
- Tests struggle to prove clearly which features are enabled or disabled.

Use Spring Boot conditions to decide whether a bean should be registered. If a class is present with an incompatible version, that is a dependency/version error to solve with dependency management and compatibility testing—not a missing optional library case.

## 12. When the user enables the feature but the dependency is still missing

Distinguish two situations:

**Feature not requested:** property not enabled or library absent. Default behavior should be to skip the integration and keep core functionality intact.

**User explicitly enables the feature but forgets the dependency:** for example, `acme.audit.json.enabled=true` without Jackson present. Choose one of two policies:

- Keep the integration inactive and log a clear condition report/diagnostic.
- Fail fast with an actionable error message, only when the property activates that feature.

If choosing fail fast, the error must clearly state which dependency to add and which property activated the feature. Core features should not fail simply because an unrequested optional library is absent.

For production starters, document the policy in configuration docs and test it explicitly. Do not leave users guessing why an optional bean did not appear.

## 13. Other types of optional integrations

The same principle applies beyond Jackson:

| Integration | Classpath condition | Common bean condition |
| --- | --- | --- |
| Redis | RedisConnectionFactory API present | RedisConnectionFactory present |
| Kafka | Kafka client classes present | KafkaTemplate or required factory present |
| JDBC | Appropriate JDBC driver/Boot JDBC classes | DataSource present |
| Web MVC | Servlet/MVC classes present | Context is a servlet web application |
| Metrics | Micrometer API present | Appropriate registry present |
| Cloud SDK | SDK client class present | Client/configuration bean provided |

Redis integration example:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name =
        "org.springframework.data.redis.connection.RedisConnectionFactory")
@ConditionalOnBean(type =
        "org.springframework.data.redis.connection.RedisConnectionFactory")
@ConditionalOnProperty(
        prefix = "acme.cache.redis",
        name = "enabled",
        havingValue = "true")
static class RedisConfiguration {
    // Redis-specific beans are declared here.
}
~~~

Classes in this example must be isolated inside the optional configuration. Do not let `RedisConnectionFactory` appear in bean signatures of the core configuration.

## 14. Testing the optional dependency matrix

An auto-configuration library should test at least these cases:

| State | Expectation |
| --- | --- |
| Optional class absent | Core context starts; optional bean does not exist |
| Optional class present, property off | Optional bean does not exist |
| Optional class present, property on, collaborator bean absent | Core context starts; optional bean absent or follows explicit policy |
| Optional class present, collaborator bean present, property on | Optional bean is created |
| User already provided optional bean | Default bean backs off |
| Optional integration lacks dependency | Core APIs and beans remain usable |
| Dependency present with incompatible version | Tests/build catch compatibility error; linkage error is not swallowed |

Tools to use:

- ApplicationContextRunner for conditions, properties, and user beans.
- FilteredClassLoader to simulate missing classes/packages.
- ConditionEvaluationReport to inspect why conditions matched or did not match.
- Integration tests with real dependencies and service tests when verifying real communication.

Do not check only "context has not failed". Assert simultaneously:

- Core beans still exist.
- Optional beans are absent when dependencies are missing.
- Optional beans are present when all conditions match.
- User beans are preserved when auto-configuration must back off.

## 15. Diagnosing when an app still fails despite @ConditionalOnClass

Follow this sequence:

1. Identify the root exception: `NoClassDefFoundError`, `ClassNotFoundException`, `UnsatisfiedDependencyException`, or `BeanCreationException`.
2. Find the optional class appearing in the stack trace or bean method signature.
3. Check whether that class lives in the core configuration or a nested optional configuration.
4. Check whether the condition is at the class level or only on a `@Bean` method.
5. Check whether the optional type leaks into a constructor, field, superclass, interface, or static initializer of an unconditionally loaded class.
6. Check whether the collaborator bean exists in the `ApplicationContext`.
7. Check whether the property is enabled with the right prefix and name.
8. Check auto-configuration ordering if the collaborator is created by another auto-configuration.
9. Use `FilteredClassLoader` to reproduce the missing-dependency case.
10. Inspect the Maven/Gradle dependency graph to confirm optional dependencies are not pulled in unintentionally.
11. Run tests with the dependency present to confirm the integration still works.
12. Read the condition report to learn precisely why the configuration was skipped.

A matching class condition does not guarantee all other bean dependencies are ready. Check the classpath, bean graph, and properties together.

## 16. Common design mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Optional type appears in outer auto-configuration | JVM may resolve class when dependency is absent | Isolate inside nested static configuration |
| Using only @ConditionalOnProperty | Property enabled yet required class is missing | Add @ConditionalOnClass |
| Using only @ConditionalOnClass | Class exists yet collaborator bean does not exist | Add @ConditionalOnBean or provide a suitable default |
| Optional dependency not marked optional in Maven | Consumers pull extra libraries even when unused | Use `optional=true` or a separate starter |
| Base starter pulls in all integrations | Huge dependency tree and version conflicts | Split starters by feature |
| Core API directly accepts optional SDK types | Core features also require external libraries | Use an interface in the core module |
| Using Class.forName and catching Throwable | Hides linkage errors and real bugs | Use Spring conditions |
| @ConditionalOnBean runs before auto-config creating collaborator | Integration skipped even though collaborator appears later | Use `after`/`afterName` and test ordering |
| User bean not protected by @ConditionalOnMissingBean | Default and custom beans both exist | Allow intentional override |
| Testing only with dependency present | Fails to catch crashes when optional library is absent | Test with FilteredClassLoader |
| Testing only that context does not fail | Fails to prove optional bean was properly skipped | Assert both core beans and optional beans |
| Using conditions to mask incompatible library versions | Hard-to-diagnose runtime errors | Manage versions and test compatibility |

## 17. Optional integration design checklist

### Classpath and modules

- [ ] Clearly identify which dependencies are required vs. optional.
- [ ] Declare Maven `optional` or Gradle `compileOnly` properly.
- [ ] Base starter does not pull dependencies for unrequested integrations.
- [ ] Separate starter exists if a group of optional dependencies is commonly used together.

### Auto-configuration

- [ ] Auto-configuration is registered via `AutoConfiguration.imports`.
- [ ] Broad component scanning is not used to find library configurations.
- [ ] Optional types appear only inside guarded nested configurations.
- [ ] `@ConditionalOnClass` is present for required libraries.
- [ ] `@ConditionalOnBean` is present if collaborator beans are required.
- [ ] `@ConditionalOnProperty` is present if the feature needs opt-in.
- [ ] Default beans use `@ConditionalOnMissingBean` to support overriding.
- [ ] Ordering is declared if conditions depend on other auto-configurations.

### API and tests

- [ ] Core API does not reference optional libraries.
- [ ] Optional integration uses suitable interfaces or adapters.
- [ ] Test missing-dependency classpath with `FilteredClassLoader`.
- [ ] Test classpath with dependency present but collaborator bean missing.
- [ ] Test property disabled and property enabled.
- [ ] Test user-defined bean override.
- [ ] Test proving core beans still work when optional features are absent.
- [ ] Never swallow `NoClassDefFoundError` or `Throwable` to simulate optional dependencies.

## 18. Self-check questions

**Question 1.** Why might `@ConditionalOnClass` on a `@Bean` method be insufficient to guard an optional type?

**Answer:** The JVM may load types in the method signature before the method condition is evaluated. Isolate methods referencing optional types inside a nested configuration with class-level `@ConditionalOnClass`.

**Question 2.** How do `@ConditionalOnClass` and `@ConditionalOnBean` differ?

**Answer:** One annotation checks whether a class is on the classpath; the other checks whether a corresponding bean already exists in the `ApplicationContext`.

**Question 3.** When should `@ConditionalOnProperty` be used?

**Answer:** When users need to explicitly enable or disable an optional feature via configuration, rather than enabling it automatically just because the library is on the classpath.

**Question 4.** Does Maven `optional=true` automatically prevent `NoClassDefFoundError`?

**Answer:** No. It only stops the dependency from propagating transitively to consumers. Code still needs class-level conditions and isolation of optional types.

**Question 5.** Why shouldn't the core API accept `ObjectMapper` if JSON is optional?

**Answer:** Because every consumer of the core API would have to resolve Jackson. Splitting the serializer into an optional interface/adapter lets the core work independently.

**Question 6.** What is `FilteredClassLoader` used for?

**Answer:** Creating a test classloader that simulates classes or packages missing from the runtime classpath, helping verify auto-configuration when dependencies are absent.

**Question 7.** What does `@ConditionalOnMissingBean` protect?

**Answer:** It prevents auto-configuration from creating a default bean when the application already supplies a matching bean, giving custom implementations precedence.

**Question 8.** Why might `@ConditionalOnBean` not match even if the bean is created later?

**Answer:** Bean conditions evaluate bean definitions processed up to the time the condition runs. Auto-configurations must be ordered properly with `after` or `afterName`.

**Question 9.** How should the library behave if the user enables a feature while its dependency is missing?

**Answer:** Follow the published policy: report clear condition/diagnostic details or fail fast indicating the required dependency. When the feature is not requested, core features must not fail.

## 19. Official references

- Spring Boot 3.5 — Creating Your Own Auto-configuration, class conditions, bean conditions, starter modules, and optional dependencies: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — ConditionalOnClass: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.5 API — ConditionalOnBean: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
- Spring Boot 3.5 API — ConditionalOnProperty: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.5 API — ConditionalOnMissingBean: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.5 API — FilteredClassLoader: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/FilteredClassLoader.html
- Spring Boot 3.5 API — ApplicationContextRunner: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
