# Splitting Additional Integrations into Independent Configurations

> **Spring Boot Auto Configuration → Auto-Configuration Library.** This lesson explains how to split a library into a core auto-configuration and optional integration auto-configurations. The goal is for applications to load only the features they need, keep optional dependencies out of core, control ordering and conditions, prevent missing-class errors when optional libraries are absent from the classpath, and test each integration independently. Examples use Java 17+, Maven, and Spring Boot 3.3.x.

## 1. Why Split Additional Integrations?

Suppose a notification library has a core feature called `NoticeClient`. Over time, users want additional integrations:
- Jackson to serialize notification payloads to JSON.
- JDBC to store delivery history.
- Micrometer to record metrics.
- Kafka to publish events.
- Vendor SDKs to send real notifications.

If everything is crammed into a single `NoticeAutoConfiguration` class, the library runs into problems:

1. Applications needing only core functionality are forced to pull in unused Jackson, JDBC, Kafka, or SDK dependencies.
2. A missing optional dependency can prevent the entire auto-configuration from loading, including the core part that does not need that dependency.
3. One wrong condition can accidentally block every bean, even when only one integration is missing.
4. Core and integration configurations have different development lifecycles, versioning, and maintenance requirements.
5. Tests struggle to distinguish core failures from adapter failures.
6. Documentation for enabling/disabling features and ordering becomes hard to follow.

Good design usually splits along **independent capabilities**:
- **Core auto-configuration:** provides foundational beans without depending on optional integration libraries.
- **Integration auto-configuration:** each integration has its own configuration class, applied only when its required dependencies and foundational beans are present.
- **Starter:** bundles artifacts that users commonly want together. A starter is mainly a dependency descriptor and does not need heavy configuration logic.

Architecture example:

~~~text
                  Spring Boot Application
                           |
            +--------------+--------------+
            |              |              |
            v              v              v
       Core starter   JSON starter   JDBC starter
            |              |              |
            v              v              v
     core-autoconfig  json-autoconfig jdbc-autoconfig
            |              |              |
            +--------------+--------------+
                           |
                           v
                    Core API / Client
~~~

Each integration is added separately. An application using only core can depend only on the core artifact; an application needing JSON adds the JSON integration; an application needing JDBC adds the JDBC integration.

**Splitting configurations is not just breaking one Java class into multiple files.** The goal is cleanly separating dependencies, conditions, auto-configuration registration, bean contracts, and tests.

## 2. Distinguishing Core, Integration, and Starter

| Component | Responsibility | Should it depend on other integrations? |
| --- | --- | --- |
| Core API / core library | Foundational types and behavior used by other features | No |
| Core auto-configuration | Creates core beans and default configuration | Should not depend on optional integration libraries |
| Integration library | Adapter bridging core with an external library | May depend on core and the corresponding library |
| Integration auto-configuration | Creates adapter beans when classpath, beans, and properties match | Only references dependencies belonging to that integration |
| Starter | Aggregates dependencies for convenient installation | May bundle core and one or more integrations |
| Demo / application | Selects only the modules actually needed | Decides which integrations to add |

Artifact naming example:

~~~text
notice/
├── notice-core
├── notice-core-autoconfigure
├── notice-jackson
├── notice-jackson-autoconfigure
├── notice-jdbc
├── notice-jdbc-autoconfigure
├── notice-spring-boot-starter
└── notice-jackson-spring-boot-starter
~~~

Not every project needs eight artifacts. For a small library, core API and core auto-configuration can be combined; as integrations grow, splitting modules gives finer control over dependencies and versions.

### 2.1. Core Must Not Know About Optional Integrations

Core should not import `ObjectMapper`, `JdbcTemplate`, `KafkaTemplate`, or external SDK classes if those libraries are not required core dependencies.

Core API example:

~~~java
package demo.notice.core;

public final class NoticeClient {

    public String send(String message) {
        return "sent:" + message;
    }
}
~~~

This is an independent type. It does not know whether data will be serialized with Jackson, saved to a database, or published via Kafka. Additional integrations depend on the core API and act as adapters.

Benefits:
- Core users do not have to install Jackson or JDBC.
- Swapping JSON libraries does not require changing core.
- Core can be tested without spinning up a database or broker.
- Integrations can be released and upgraded independently if contracts remain compatible.

### 2.2. Integrations Depend on Core, Never Pull Core Back Into Integrations

A JSON adapter can use `NoticeClient` and Jackson:

~~~java
package demo.notice.jackson;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import demo.notice.core.NoticeClient;

public final class NoticeJsonFormatter {

    private final ObjectMapper objectMapper;
    private final NoticeClient noticeClient;

    public NoticeJsonFormatter(
            ObjectMapper objectMapper,
            NoticeClient noticeClient) {
        this.objectMapper = objectMapper;
        this.noticeClient = noticeClient;
    }

    public String format(String message) {
        try {
            return objectMapper.writeValueAsString(
                    new NoticePayload(
                            message,
                            noticeClient.send(message)
                    )
            );
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                    "Cannot serialize notice payload",
                    exception
            );
        }
    }

    public record NoticePayload(String message, String delivery) {
    }
}
~~~

This is an adapter class in the JSON module. It can use core and Jackson; core does not need to know `NoticeJsonFormatter` exists.

## 3. Splitting Auto-Configuration Along Feature Boundaries

A library can declare multiple `@AutoConfiguration` classes. Each class represents a group of beans with relatively independent conditions and dependencies.

~~~text
NoticeCoreAutoConfiguration
    └── NoticeClient

NoticeJacksonAutoConfiguration
    └── NoticeJsonFormatter

NoticeJdbcAutoConfiguration
    ├── NoticeHistoryRepository
    └── JDBC adapter

NoticeKafkaAutoConfiguration
    └── NoticeEventPublisher
~~~

An integration class typically needs three kinds of conditions:

- `@ConditionalOnClass`: the integration library is on the classpath.
- `@ConditionalOnBean`: foundational beans needed by the adapter are already registered.
- `@ConditionalOnProperty`: whether the user has enabled this feature.

You can also add `@ConditionalOnMissingBean` to let the application provide a replacement adapter.

High-level example:

~~~java
@AutoConfiguration(after = NoticeCoreAutoConfiguration.class)
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
@ConditionalOnBean(NoticeClient.class)
@ConditionalOnProperty(
        prefix = "demo.notice.json",
        name = "enabled",
        havingValue = "true"
)
public class NoticeJacksonAutoConfiguration {
    // Registers beans dedicated to the Jackson integration.
}
~~~

In real code, carefully consider which class may directly reference optional types. Section 5 explains how to safely isolate optional types.

### 3.1. Why Should Each Integration Have Its Own Conditions?

If Jackson is absent, only `NoticeJacksonAutoConfiguration` should not match. `NoticeCoreAutoConfiguration` can still create `NoticeClient`.

If the user disables JSON with `demo.notice.json.enabled=false`, the JSON bean is not created; core still works.

If the user supplies their own `NoticeJsonFormatter`, `@ConditionalOnMissingBean` lets auto-configuration yield to the replacement bean.

This is the desired behavior: **a missing or disabled integration does not drag down other independent features**.

### 3.2. Place Conditions at the Right Scope

If a condition sits on the entire auto-configuration class, every bean declared inside that class is governed by that condition. If only one bean needs a dedicated dependency or property, place the condition on the method or on a nested configuration class.

For example, suppose an integration has two beans:
- `NoticeJsonFormatter` requires Jackson.
- `NoticeJsonMetrics` requires Micrometer.

Do not place `@ConditionalOnClass` for Jackson on a class wrapping both beans if missing Jackson would also suppress metrics that do not need Jackson. Split them into two nested configurations or two independent auto-configurations.

## 4. Registering Multiple Auto-Configurations in Spring Boot 3

With Spring Boot 3.x, libraries register auto-configurations in the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Each auto-configuration is written as its fully qualified class name, one class per line.

Core artifact:

~~~text
demo.notice.core.autoconfigure.NoticeCoreAutoConfiguration
~~~

JSON integration artifact:

~~~text
demo.notice.jackson.autoconfigure.NoticeJacksonAutoConfiguration
~~~

Boot reads all imports files across the classpath and aggregates candidates from different artifacts. Thus each module can contribute its own auto-configurations.

Notes:
- The file must reside under `src/main/resources/META-INF/spring/`.
- Package and class names must match exactly.
- A class present in a JAR but neither registered nor imported will not automatically become an auto-configuration candidate.
- When building multiple JARs, each JAR can carry its own imports file; Boot's mechanism reads and merges them.
- Do not treat line order in the file as an ordering contract; declare `before` / `after` explicitly when needed.

### 4.1. Ordering Between Core and Integration

If the JSON integration uses the `NoticeClient` bean, declare:

~~~java
@AutoConfiguration(after = NoticeCoreAutoConfiguration.class)
public class NoticeJacksonAutoConfiguration {
}
~~~

When both configurations are discovered, Boot processes core before the integration. This is especially important when the integration has `@ConditionalOnBean(NoticeClient.class)`.

Ordering controls auto-configuration processing and bean definition registration order. It does not replace dependency injection during instantiation; factory methods should still accept `NoticeClient` as a parameter.

### 4.2. Using `afterName` to Avoid Compile-Time Dependencies

If an integration may depend on another auto-configuration only at runtime, use `afterName` / `beforeName`:

~~~java
@AutoConfiguration(
    afterName = "demo.notice.core.autoconfigure.NoticeCoreAutoConfiguration"
)
public class OptionalAdapterAutoConfiguration {
}
~~~

The name must be a fully qualified class name. This avoids a direct class reference, though string names must be tested because the compiler does not spell-check them.

### 4.3. Avoiding Ordering Cycles

Do not declare:
- A `after` B
- B `after` A

That creates an ordering cycle. Sketch the dependency graph and pick one direction: the integration depends on core, so the integration runs after core.

## 5. Isolating Optional Classes to Prevent Errors When Dependencies Are Missing

This is the most error-prone area when splitting integrations.

Suppose Jackson is optional. If a core class has a method signature referencing `ObjectMapper`, an application installing only core may encounter class-loading errors before conditions have a chance to exclude the configuration.

Do not write a core class like:

~~~java
@Configuration
class CoreConfiguration {

    @Bean
    NoticeJsonFormatter formatter(ObjectMapper mapper) {
        // ...
    }
}
~~~

if core does not guarantee Jackson is always present.

### 5.1. Put Classes Referencing Optional Types in a Separate Module

The cleanest approach is:
- `notice-core-autoconfigure` references only the core API and Spring Boot.
- `notice-jackson-autoconfigure` depends on core and Jackson.
- Applications needing only core do not add the JSON artifact.

When the JSON module is not on the classpath, `NoticeJacksonAutoConfiguration` does not even exist in the runtime artifacts; core has no reference to it whatsoever.

### 5.2. Using `@ConditionalOnClass` with Class Name and Nested Configuration

Inside the JSON module, you can write:

~~~java
package demo.notice.jackson.autoconfigure;

import com.fasterxml.jackson.databind.ObjectMapper;
import demo.notice.core.NoticeClient;
import demo.notice.core.autoconfigure.NoticeCoreAutoConfiguration;
import demo.notice.jackson.NoticeJsonFormatter;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration(after = NoticeCoreAutoConfiguration.class)
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
public class NoticeJacksonAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnBean(NoticeClient.class)
    @ConditionalOnProperty(
            prefix = "demo.notice.json",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    static class JacksonConfiguration {

        @Bean
        @ConditionalOnMissingBean(NoticeJsonFormatter.class)
        NoticeJsonFormatter noticeJsonFormatter(
                ObjectMapper objectMapper,
                NoticeClient noticeClient) {

            return new NoticeJsonFormatter(objectMapper, noticeClient);
        }
    }
}
~~~

This code belongs to the JSON module, which has Jackson on its compile classpath, so importing `ObjectMapper` is valid. The outer auto-configuration checks the classpath via a string name; the nested configuration holds the method signature referencing the optional type and is processed only when the outer condition matches.

In a real project, add the `NoticeCoreAutoConfiguration` import if it is in a different package. This snippet illustrates the structure; Section 7 provides a complete project with consistent imports and packages.

### 5.3. Avoid Putting the Condition on a Method Whose Signature Already Needs Optional Types

The following pattern is fragile:

~~~java
@Bean
@ConditionalOnClass(ObjectMapper.class)
NoticeJsonFormatter formatter(ObjectMapper mapper) {
    return new NoticeJsonFormatter(mapper);
}
~~~

A method-level condition cannot always protect against the JVM/Spring introspecting the method's parameter types. When a type might be absent, place the condition at the configuration level and isolate the method inside a class or nested configuration processed only after the classpath condition matches.

### 5.4. Class Literals vs. String Names

- `@ConditionalOnClass(ObjectMapper.class)` works when the class can be safely referenced in the module containing the annotation.
- `@ConditionalOnClass(name = "...")` uses a string name, avoiding resolving a class literal when metadata is read.
- Splitting out an integration artifact is the strongest boundary: core does not need to know whether the optional type exists.

Do not use `@ConditionalOnClass` as a replacement for dependency management. If the integration genuinely needs Jackson to run, the integration module must declare the appropriate dependency; the condition only prevents the auto-configuration from applying when the environment lacks the class.

## 6. Optional Dependencies, Integration Artifacts, and Starters

Two concepts are easy to confuse:

An **optional dependency** in Maven describes a dependency used by the current module that should not be transitively propagated to every consumer by default. An **optional integration artifact** is a separate JAR that an application adds only when it wants that integration capability.

Example:
- `notice-core-autoconfigure` does not depend on Jackson.
- `notice-jackson-autoconfigure` depends on core and Jackson.
- `notice-jackson-spring-boot-starter` pulls in core, JSON auto-config, and Jackson.
- `notice-spring-boot-starter` pulls in only core if the goal is a minimal starter.

A starter can consist solely of a POM:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo.notice</groupId>
    <artifactId>notice-jackson-spring-boot-starter</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>demo.notice</groupId>
            <artifactId>notice-core-autoconfigure</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>demo.notice</groupId>
            <artifactId>notice-jackson-autoconfigure</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
~~~

This is an illustrative POM for a starter published by the same project. If the JSON auto-config artifact already declares Jackson as a required compile/runtime dependency, Jackson will be pulled in when an application adds that module. If you want applications to choose the Jackson version themselves, you can consider dependency management/optional strategies while keeping the runtime contract clear.

Do not create a single starter pulling in every integration if users normally need only a small subset. A better option is a core starter alongside focused starters such as `notice-jackson-spring-boot-starter` and `notice-jdbc-spring-boot-starter`.

## 7. Complete Multi-Module Example with Core and Jackson Integration

The lab below has three Maven modules:
1. `notice-core-autoconfigure`: provides `NoticeClient`.
2. `notice-jackson-autoconfigure`: integrates Jackson and creates `NoticeJsonFormatter`.
3. `notice-demo`: application using both modules to observe results.

The core module has no Jackson dependency. When the JSON module is removed from the application's dependencies, core still runs.

Requirements: JDK 17+, Maven, and network access to download dependencies. The example uses Spring Boot 3.3.13.

### 7.1. Directory Structure

~~~text
notice-platform/
├── pom.xml
├── notice-core-autoconfigure/
│   ├── pom.xml
│   └── src/main/
│       ├── java/demo/notice/core/
│       │   ├── NoticeClient.java
│       │   └── autoconfigure/NoticeCoreAutoConfiguration.java
│       └── resources/META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
├── notice-jackson-autoconfigure/
│   ├── pom.xml
│   └── src/main/
│       ├── java/demo/notice/jackson/
│       │   ├── NoticeJsonFormatter.java
│       │   └── autoconfigure/NoticeJacksonAutoConfiguration.java
│       └── resources/META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── notice-demo/
    ├── pom.xml
    └── src/main/
        └── java/demo/app/NoticeDemoApplication.java
~~~

### 7.2. Parent `pom.xml`

File `notice-platform/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo.notice</groupId>
    <artifactId>notice-platform</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
    <properties>
        <java.version>17</java.version>
    </properties>
    <modules>
        <module>notice-core-autoconfigure</module>
        <module>notice-jackson-autoconfigure</module>
        <module>notice-demo</module>
    </modules>
</project>
~~~

The Maven reactor builds in dependency graph order; module order in the POM does not replace declaring dependencies between modules.

### 7.3. Core Module `pom.xml`

File `notice-core-autoconfigure/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.notice</groupId>
        <artifactId>notice-platform</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>notice-core-autoconfigure</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

There are no Jackson, JDBC, or Kafka dependencies in the core module. `spring-boot-autoconfigure` provides the required auto-configuration annotations and mechanisms.

### 7.4. Core API: `NoticeClient.java`

File `notice-core-autoconfigure/src/main/java/demo/notice/core/NoticeClient.java`:

~~~java
package demo.notice.core;

public final class NoticeClient {

    public String send(String message) {
        return "sent:" + message;
    }
}
~~~

This is a simple core API so the lab produces deterministic output. In a real library, this class might manage queues or call a service, but it should not depend on Jackson merely so a JSON adapter can exist.

### 7.5. `NoticeCoreAutoConfiguration.java`

File `notice-core-autoconfigure/src/main/java/demo/notice/core/autoconfigure/NoticeCoreAutoConfiguration.java`:

~~~java
package demo.notice.core.autoconfigure;

import demo.notice.core.NoticeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.notice",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class NoticeCoreAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NoticeClient.class)
    NoticeClient noticeClient() {
        return new NoticeClient();
    }
}
~~~

Core is enabled by default when the property is missing; setting `demo.notice.enabled=false` disables the default bean. Applications can supply their own `NoticeClient` if replacement is needed.

### 7.6. Registering Core Auto-Configuration

File `notice-core-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` contains:

~~~text
demo.notice.core.autoconfigure.NoticeCoreAutoConfiguration
~~~

The fully qualified class name must match character for character. Without this file, Boot will not auto-discover the core auto-configuration merely because the JAR is on the classpath.

### 7.7. JSON Module `pom.xml`

File `notice-jackson-autoconfigure/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.notice</groupId>
        <artifactId>notice-platform</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>notice-jackson-autoconfigure</artifactId>
    <dependencies>
        <dependency>
            <groupId>demo.notice</groupId>
            <artifactId>notice-core-autoconfigure</artifactId>
            <version>@@PROJECT_VERSION@@</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Jackson is added only to the integration module. The core module does not need to know this dependency exists.

### 7.8. `NoticeJsonFormatter.java`

File `notice-jackson-autoconfigure/src/main/java/demo/notice/jackson/NoticeJsonFormatter.java`:

~~~java
package demo.notice.jackson;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import demo.notice.core.NoticeClient;

public final class NoticeJsonFormatter {

    private final ObjectMapper objectMapper;
    private final NoticeClient noticeClient;

    public NoticeJsonFormatter(
            ObjectMapper objectMapper,
            NoticeClient noticeClient) {
        this.objectMapper = objectMapper;
        this.noticeClient = noticeClient;
    }

    public String format(String message) {
        try {
            NoticePayload payload = new NoticePayload(
                    message,
                    noticeClient.send(message)
            );
            return objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                    "Cannot serialize notice payload",
                    exception
            );
        }
    }

    public record NoticePayload(String message, String delivery) {
    }
}
~~~

`NoticeJsonFormatter` is an adapter. It combines JSON serialization and the core client, without introducing any back-reference into core.

### 7.9. `NoticeJacksonAutoConfiguration.java`

File `notice-jackson-autoconfigure/src/main/java/demo/notice/jackson/autoconfigure/NoticeJacksonAutoConfiguration.java`:

~~~java
package demo.notice.jackson.autoconfigure;

import com.fasterxml.jackson.databind.ObjectMapper;
import demo.notice.core.NoticeClient;
import demo.notice.core.autoconfigure.NoticeCoreAutoConfiguration;
import demo.notice.jackson.NoticeJsonFormatter;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration(after = NoticeCoreAutoConfiguration.class)
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
public class NoticeJacksonAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnBean(NoticeClient.class)
    @ConditionalOnProperty(
            prefix = "demo.notice.json",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    static class JacksonConfiguration {

        @Bean
        @ConditionalOnMissingBean(NoticeJsonFormatter.class)
        NoticeJsonFormatter noticeJsonFormatter(
                ObjectMapper objectMapper,
                NoticeClient noticeClient) {
            return new NoticeJsonFormatter(objectMapper, noticeClient);
        }
    }
}
~~~

Four notable points:

1. `@AutoConfiguration(after = NoticeCoreAutoConfiguration.class)` places the integration after core.
2. `@ConditionalOnClass(name = "...ObjectMapper")` applies the integration only when Jackson is on the classpath.
3. The nested configuration requires `NoticeClient` and `demo.notice.json.enabled=true`.
4. `@ConditionalOnMissingBean` allows the application to supply its own `NoticeJsonFormatter`.

Because this class lives in the JSON module, the Jackson compile dependency is present. The outer class uses a string name in its condition; the nested class holds the method signature needing `ObjectMapper`. The core module never references JSON types.

### 7.10. Registering JSON Auto-Configuration

File `notice-jackson-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` contains:

~~~text
demo.notice.jackson.autoconfigure.NoticeJacksonAutoConfiguration
~~~

When an application has both JARs, Boot reads both imports files and discovers both configurations. When an application has only the core JAR, the JSON auto-configuration does not exist on the classpath and cannot affect core.

### 7.11. Demo App `pom.xml`

File `notice-demo/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>demo.notice</groupId>
        <artifactId>notice-platform</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>notice-demo</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
        </dependency>
        <dependency>
            <groupId>demo.notice</groupId>
            <artifactId>notice-core-autoconfigure</artifactId>
            <version>@@PROJECT_VERSION@@</version>
        </dependency>
        <dependency>
            <groupId>demo.notice</groupId>
            <artifactId>notice-jackson-autoconfigure</artifactId>
            <version>@@PROJECT_VERSION@@</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-json` supplies Jackson configuration and `ObjectMapper` for the application. The integration module provides the formatter; it should not assume an `ObjectMapper` bean will always exist if the application has not installed the mapper infrastructure.

If the application does not need JSON, remove the `notice-jackson-autoconfigure` and `spring-boot-starter-json` dependencies; core continues to work.

### 7.12. `NoticeDemoApplication.java`

File `notice-demo/src/main/java/demo/app/NoticeDemoApplication.java`:

~~~java
package demo.app;

import demo.notice.core.NoticeClient;
import demo.notice.jackson.NoticeJsonFormatter;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NoticeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(NoticeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner report(
            ObjectProvider<NoticeClient> clients,
            ObjectProvider<NoticeJsonFormatter> formatters) {

        return args -> {
            NoticeClient client = clients.getIfAvailable();
            NoticeJsonFormatter formatter = formatters.getIfAvailable();

            System.out.println("core client present: " + (client != null));
            System.out.println("json formatter present: " + (formatter != null));

            if (formatter != null) {
                System.out.println(
                        "formatted: " + formatter.format("hello")
                );
            }
        };
    }
}
~~~

`ObjectProvider` is used because the integration is optional. The `ApplicationRunner` still executes when the JSON module is removed from the classpath or the JSON property is disabled.

## 8. Building and Observing Each Integration Combination

From the `notice-platform` directory:

~~~bash
mvn -q clean package
~~~

### 8.1. Core and JSON Present, JSON Enabled

Run:

~~~bash
java -jar notice-demo/target/notice-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.notice.json.enabled=true
~~~

Stdout printed by the program:

~~~text
core client present: true
json formatter present: true
formatted: {"message":"hello","delivery":"sent:hello"}
~~~

The core bean is created; the JSON integration sees the core bean and `ObjectMapper`, and the property permits it, so the formatter is created.

### 8.2. Both Modules Present, JSON Disabled

Run:

~~~bash
java -jar notice-demo/target/notice-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.notice.json.enabled=false
~~~

Stdout:

~~~text
core client present: true
json formatter present: false
~~~

The JSON integration does not create the formatter, while core remains present. This proves the integration property does not disable core.

### 8.3. Core Disabled

Run:

~~~bash
java -jar notice-demo/target/notice-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF --demo.notice.enabled=false --demo.notice.json.enabled=true
~~~

Stdout:

~~~text
core client present: false
json formatter present: false
~~~

The JSON integration requires `NoticeClient`, so `@ConditionalOnBean` does not match. Without core, the adapter is not created.

### 8.4. Core Only, Removing Integration Dependencies

In `notice-demo/pom.xml`, remove two dependencies:
- `notice-jackson-autoconfigure`
- `spring-boot-starter-json`

Keep `notice-core-autoconfigure` and `spring-boot-starter`. Rebuild:

~~~bash
mvn -q clean package
~~~

Run:

~~~bash
java -jar notice-demo/target/notice-demo-1.0.0.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Expected stdout after replacing the application source with the core-only version below:

~~~text
core client present: true
json formatter present: false
~~~

The original application class imported `NoticeJsonFormatter`, so when removing the JSON module completely, replace the application with the core-only version below so source code no longer has a compile-time dependency on the optional type.

~~~java
package demo.app;

import demo.notice.core.NoticeClient;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NoticeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(NoticeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner report(ObjectProvider<NoticeClient> clients) {
        return args -> {
            NoticeClient client = clients.getIfAvailable();
            System.out.println("core client present: " + (client != null));
            System.out.println("json formatter present: false");
        };
    }
}
~~~

This is the replacement source for the core-only demo. It demonstrates that the application does not need to import classes from the JSON module when the integration is removed from the dependency graph.

## 9. Testing Each Configuration Independently with ApplicationContextRunner

Testing per module prevents integration errors from obscuring core failures. You should have these test groups:
- Core tests: whether core beans are created per property and back off when the user supplies a bean.
- Integration tests: formatter is created only when core, Jackson, and the property are all satisfied.
- Optional dependency tests: when optional classes are missing, the integration does not match.
- User override tests: application-supplied beans are preserved.
- Starter tests: when the application uses an umbrella starter, all expected integrations are present.

In `notice-demo/pom.xml`, add the test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

### 9.1. Independent Core Tests

~~~java
package demo.notice;

import demo.notice.core.NoticeClient;
import demo.notice.core.autoconfigure.NoticeCoreAutoConfiguration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class NoticeCoreAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            NoticeCoreAutoConfiguration.class
                    ));

    @Test
    void coreIsEnabledByDefault() {
        runner.run(context ->
                assertThat(context).hasSingleBean(NoticeClient.class)
        );
    }

    @Test
    void coreCanBeDisabled() {
        runner.withPropertyValues("demo.notice.enabled=false")
                .run(context ->
                        assertThat(context)
                                .doesNotHaveBean(NoticeClient.class)
                );
    }

    @Test
    void userClientMakesCoreAutoConfigurationBackOff() {
        runner.withBean(
                NoticeClient.class,
                () -> new NoticeClient()
        ).run(context ->
                assertThat(context).hasSingleBean(NoticeClient.class)
        );
    }
}
~~~

This test loads only the core auto-configuration; it does not need `ObjectMapper`, the Jackson integration, or a web server.

### 9.2. JSON Integration Tests

~~~java
package demo.notice;

import com.fasterxml.jackson.databind.ObjectMapper;
import demo.notice.core.autoconfigure.NoticeCoreAutoConfiguration;
import demo.notice.jackson.NoticeJsonFormatter;
import demo.notice.jackson.autoconfigure.NoticeJacksonAutoConfiguration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class NoticeJacksonAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withBean(ObjectMapper.class, ObjectMapper::new)
                    .withConfiguration(AutoConfigurations.of(
                            NoticeJacksonAutoConfiguration.class,
                            NoticeCoreAutoConfiguration.class
                    ));

    @Test
    void formatterIsCreatedWhenCoreJacksonAndPropertyArePresent() {
        runner.withPropertyValues("demo.notice.json.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(NoticeJsonFormatter.class);
                    NoticeJsonFormatter formatter =
                            context.getBean(NoticeJsonFormatter.class);
                    assertThat(formatter.format("hello"))
                            .isEqualTo(
                                "{\"message\":\"hello\",\"delivery\":\"sent:hello\"}"
                            );
                });
    }

    @Test
    void formatterIsSkippedWhenFeatureIsDisabled() {
        runner.withPropertyValues("demo.notice.json.enabled=false")
                .run(context ->
                        assertThat(context)
                                .doesNotHaveBean(NoticeJsonFormatter.class)
                );
    }

    @Test
    void formatterIsSkippedWhenCoreIsDisabled() {
        runner.withPropertyValues(
                "demo.notice.enabled=false",
                "demo.notice.json.enabled=true"
        ).run(context ->
                assertThat(context)
                        .doesNotHaveBean(NoticeJsonFormatter.class)
        );
    }
}
~~~

`AutoConfigurations.of(...)` intentionally lists the integration before core. The `after` annotation on the JSON auto-configuration expresses the ordering relationship; the test checks the final result instead of relying on line order in the imports file.

With Spring Boot 3.3.13 and Jackson, all 3 JSON tests and 3 core tests are expected to PASS. To test a missing Jackson class, you can use `FilteredClassLoader` from Spring Boot test to hide the Jackson package; when doing so, ensure the test references the integration class in a way that does not force resolving optional types before the condition is evaluated.

### 9.3. Why Is Per-Module Testing Important?

If core tests fail, the problem lies in the core API, core conditions, or bean definitions. If core tests pass but JSON tests fail, investigate:
- Is Jackson on the test runtime classpath?
- Is there an `ObjectMapper` bean?
- Was `NoticeClient` created?
- Are `demo.notice.json.enabled` name and value exact?
- Does the JSON imports file have the exact FQCN?
- Does ordering ensure the condition sees the core bean definition?

Splitting tests by module speeds up diagnosis and reduces the dependencies each test must initialize.

## 10. How Should Other Integrations Be Split?

### 10.1. JDBC Integration

A `NoticeJdbcAutoConfiguration` should live in a dedicated JDBC artifact. It may require:
- `JdbcTemplate` or `DataSource`.
- `@ConditionalOnClass(JdbcTemplate.class)`.
- `@ConditionalOnBean(DataSource.class)`.
- `@ConditionalOnProperty(prefix="demo.notice.jdbc", name="enabled", havingValue="true")`.
- `@ConditionalOnMissingBean(NoticeHistoryRepository.class)`.

Do not put `JdbcTemplate` or `DataSource` into the core API if core does not need a database. Applications using only core/JSON will not have to install JDBC drivers.

### 10.2. Kafka Integration

A `NoticeKafkaAutoConfiguration` may require:
- Kafka client/Spring Kafka on the classpath.
- `KafkaTemplate` or the required producer bean.
- Configured topic and serializer.
- A dedicated property like `demo.notice.kafka.enabled`.

If Kafka is missing or disabled, core still runs. Do not give core beans a required constructor parameter of `KafkaTemplate` when Kafka is only an optional integration.

### 10.3. Metrics Integration

A `NoticeMetricsAutoConfiguration` can depend on Micrometer. It should register a separate meter binder or listener when `MeterRegistry` is present. Core does not need to import `MeterRegistry` if metrics recording is not mandatory.

### 10.4. Web Integration

A `NoticeWebAutoConfiguration` can create a controller/endpoint or converter when Spring MVC/WebFlux is on the classpath. If the integration targets MVC, do not accidentally make it require WebFlux; check the specific classpath and application type.

### 10.5. Decision Table

| Integration | Which module owns the dependency? | Typical conditions | Does core need to know? |
| --- | --- | --- | --- |
| Jackson JSON | `notice-jackson-autoconfigure` | `ObjectMapper` + `NoticeClient` + property | No |
| JDBC history | `notice-jdbc-autoconfigure` | `JdbcTemplate` / `DataSource` + property | No |
| Kafka publisher | `notice-kafka-autoconfigure` | `KafkaTemplate` + property | No |
| Metrics | `notice-metrics-autoconfigure` | `MeterRegistry` + property | No |
| MVC endpoint | `notice-webmvc-autoconfigure` | Spring MVC classpath + property | No |

## 11. Designing Properties and Back-Off for Each Integration

Each integration should have its own namespace to avoid conflicts:

~~~yaml
demo:
  notice:
    enabled: true
    json:
      enabled: true
    jdbc:
      enabled: false
    kafka:
      enabled: false
    metrics:
      enabled: true
~~~

Key principles:
- `demo.notice.enabled` controls core.
- `demo.notice.json.enabled` controls the JSON adapter.
- `demo.notice.jdbc.enabled` controls history persistence.
- `demo.notice.kafka.enabled` controls the publisher.
- Integration properties should not silently alter core behavior.
- Each integration's defaults must be documented in metadata/README and tested separately.

When core is disabled, integrations requiring core beans must also fail to match. When an integration is disabled, core is not disabled along with it. This is one-way independence: integrations depend on core, while core does not depend on integrations.

### 11.1. `@ConditionalOnMissingBean` Protects Replaceability

~~~java
@Bean
@ConditionalOnMissingBean(NoticeJsonFormatter.class)
NoticeJsonFormatter noticeJsonFormatter(
        ObjectMapper mapper,
        NoticeClient client) {
    return new NoticeJsonFormatter(mapper, client);
}
~~~

If the application already supplies its own formatter, auto-configuration does not create the default formatter. Declare a concrete return type so type-based conditions can evaluate accurately.

Back-off only decides whether to register the default bean. It does not remove user beans, fix dependencies of user beans, or guarantee user beans work properly.

### 11.2. Avoid Placing Integration Properties on Core Classes

Do not place `@ConditionalOnProperty(prefix="demo.notice.json", ...)` on `NoticeCoreAutoConfiguration` if only JSON needs toggling. Doing so causes missing or disabled JSON to eliminate `NoticeClient` as well.

Place property conditions on the appropriate JSON auto-configuration or nested configuration.

## 12. Organizing Dependencies and Versions Across Modules

When publishing multiple artifacts, keep versions compatible:

- Core API and core auto-configuration must be compatible with each other.
- The JSON integration must declare the range of core versions it supports.
- Starters should manage internal artifact versions consistently.
- External library dependencies should be managed by the Spring Boot BOM or a dedicated BOM.
- Do not let an integration pull in a different core version that causes duplicate classes or binary incompatibility.

A project can use a parent POM to manage internal versions. When publishing for external consumers, you can provide a BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>demo.notice</groupId>
            <artifactId>notice-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Consumers can then declare dependencies without repeating versions once the BOM manages them. This is an illustrative dependency management snippet; the BOM must be published separately and list the corresponding artifacts/versions.

Do not bump core versions arbitrarily without testing integrations. A public API change in core can impact every adapter; run cross-module matrix tests before releasing.

## 13. Common Mistakes When Splitting Integrations

1. **Letting core import optional classes.** Applications without the integration may hit class-loading failures.
2. **Splitting classes only while keeping all dependencies in one artifact.** The dependency graph does not change, and users still pull in unneeded libraries.
3. **Forgetting to register the integration in `AutoConfiguration.imports`.** The JAR contains the class, but Boot does not auto-load the configuration.
4. **Incorrect FQCN in imports.** The auto-configuration is not discovered.
5. **Condition on a method while optional types appear in the method signature.** The class may be introspected before the method condition can guard it.
6. **Placing integration conditions on core.** Disabling one adapter drops core beans.
7. **Omitting `after` when conditions depend on beans from another auto-configuration.** `@ConditionalOnBean` may evaluate before foundational beans are registered.
8. **Using ordering instead of dependency injection.** Ordering helps conditions see definitions; injection still needs to express dependencies at instantiation time.
9. **Missing `@ConditionalOnMissingBean`.** Users struggle to replace default adapters and may hit multiple beans of the same type.
10. **Not testing missing-dependency scenarios.** An integration may work with a full classpath while breaking core when optional libraries are missing.
11. **Starter pulling in all integrations.** Small applications must install many unnecessary dependencies.
12. **All integrations sharing one `enabled` property.** Users cannot disable one adapter while keeping core and other adapters active.
13. **Core API exposing third-party library types.** Optional dependencies become mandatory dependencies in the public API.
14. **Not verifying the runtime classpath.** IDE builds/tests have dependencies, whereas executable JARs/containers lack them.
15. **Version mismatch across modules.** An adapter may call APIs absent in the resolved core version.
16. **Creating circular module dependencies.** Core depends on an integration while the integration depends on core; keep dependencies one-way.
17. **Assuming a missing integration means missing core.** When split properly, core operates independently.
18. **Confusing auto-configuration with starter.** Auto-configuration holds conditional bean registration logic; starters mainly aggregate dependencies.
19. **Using component scan to register all integrations.** Boot 3 libraries should use `AutoConfiguration.imports`; component scanning can expose configurations unexpectedly.
20. **Testing only context startup.** Assert which beans are present/absent per module and property rather than checking startup success alone.

## 14. Practical Workflow for Extracting an Integration from a Large Auto-Configuration

1. **List beans and dependencies:** record which beans belong to core and which serve only the integration.
2. **Define dependency direction:** integrations use core; core never references integrations.
3. **Split source/package/artifact:** move adapters and dedicated configuration into the integration module.
4. **Split dependencies:** external dependencies belong only in modules that need them.
5. **Create imports files:** each auto-configuration is registered exactly once in its owning artifact.
6. **Add conditions:** classpath, foundational beans, and integration properties.
7. **Declare ordering:** use `after` when conditions depend on beans registered by core auto-configuration.
8. **Preserve back-off:** let users replace adapters via `@ConditionalOnMissingBean`.
9. **Split tests:** core-only, integration-on, integration-off, missing dependency, and user override.
10. **Inspect dependency tree and executable artifacts:** verify core-only does not pull in optional libraries.
11. **Update starters and metadata:** users know which dependency enables which integration.
12. **Run compatibility tests:** ensure core and every integration version are compatible.

## 15. Pre-Release Checklist for Multi-Integration Libraries

- [ ] Core API does not reference types from optional integrations.
- [ ] Core auto-configuration creates only foundational beans.
- [ ] Each integration has an independent auto-configuration.
- [ ] External dependencies are declared only in modules that genuinely need them.
- [ ] Each artifact has `AutoConfiguration.imports` with accurate FQCNs.
- [ ] Classpath conditions guard the right module and do not block core.
- [ ] Bean conditions specify required foundational dependencies.
- [ ] Dedicated properties control each integration.
- [ ] `after` / `before` ordering reflects dependencies between auto-configurations.
- [ ] Default beans have `@ConditionalOnMissingBean` when overrides should be supported.
- [ ] Optional classes are isolated so missing classes do not break core.
- [ ] Core-only tests do not require integration dependencies.
- [ ] Integration tests cover enabled, disabled, missing core, and user override cases.
- [ ] Starters pull in only the integrations users actually want.
- [ ] Core and integration versions are managed consistently.
- [ ] Executable JARs/containers are verified for runtime dependencies.
- [ ] README and configuration metadata accurately describe properties, defaults, and artifacts to install.

## 16. Self-Check Questions

**Question 1.** An application needs only core and lacks Jackson. What design keeps the application running?  
**Answer:** Core API and core auto-configuration do not reference Jackson; the JSON adapter resides in a separate artifact and is added only when needed.

**Question 2.** Why does `NoticeJacksonAutoConfiguration` need `@ConditionalOnClass`?  
**Answer:** So the integration applies only when Jackson is on the runtime classpath; missing the JSON library does not cause core to fail.

**Question 3.** Why use `@AutoConfiguration(after = NoticeCoreAutoConfiguration.class)`?  
**Answer:** The integration may use `@ConditionalOnBean(NoticeClient.class)` and needs core bean definitions processed first.

**Question 4.** Should disabling `demo.notice.json.enabled` make `NoticeClient` disappear?  
**Answer:** No. The JSON property controls only the JSON integration; core has its own property.

**Question 5.** What does `@ConditionalOnMissingBean(NoticeJsonFormatter.class)` protect?  
**Answer:** It allows applications to provide their own formatter; auto-configuration does not create the default formatter when a matching bean already exists.

**Question 6.** Why should `ObjectMapper` not appear in the core API?  
**Answer:** It turns Jackson into a core dependency and forces core-only applications to know about the JSON library.

**Question 7.** How does a starter differ from an auto-configuration?  
**Answer:** A starter mainly bundles dependencies for users to install; an auto-configuration contains conditional bean registration logic.

**Question 8.** If an integration lacks a class yet its condition sits on a method whose signature uses that class, what is the risk?  
**Answer:** Spring/the JVM may need to introspect the method signature before the method condition can protect it. Isolate the type inside a dedicated configuration with a class-level classpath condition.

## 17. Conclusion and References

Splitting integrations into independent configurations keeps core dependencies small, enables adapters based on classpath/beans/properties, and lets each feature be developed, tested, and released separately. The dependency graph should flow in one direction: **integrations depend on core; core does not depend on integrations**. For each auto-configuration, keep imports, conditions, ordering, and back-off cleanly scoped.

Official documentation:
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
- [Spring Boot Reference — Auto-configuration Conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.condition-annotations).
- [Spring Boot Reference — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing).
- [Spring Boot Javadoc — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html).
- [Spring Boot Javadoc — ConditionalOnClass](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html).
- [Spring Boot Javadoc — ConditionalOnBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html)