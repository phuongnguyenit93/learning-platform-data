# Limiting Transitive Dependencies to Avoid Accidentally Activating Other Features

## 1. The Problem: A Core Starter Can Pull In an Entire Feature Stack

A custom starter is typically added to an application with a single dependency. If the core starter pulls in too many libraries, those libraries appear on the runtime classpath of every consumer and can cause Spring Boot to activate additional auto-configurations.

For example:

- A core starter needs a simple client yet depends on `spring-boot-starter-web`. A CLI application may be detected as a Servlet web application and spin up an embedded server.
- A notification library only needs email in some applications, yet the base starter always pulls in `spring-boot-starter-mail`.
- A data starter pulls in `spring-boot-starter-data-jpa` even when consumers only need the core API; JDBC, JPA, and Hibernate appear unnecessarily.
- A third-party SDK pulls in another starter across multiple transitive hops, even though the application's direct POM never declares it.

What must be controlled is **the consumer's actual dependency graph**, especially the runtime classpath. Looking solely at direct dependencies in the POM is not enough.

### Dependency Presence and Auto-Configuration Activation Are Two Different Things

When a JAR appears on the runtime classpath:

1. Spring Boot can detect the library's classes.
2. Auto-configurations from Spring Boot or that library can become candidates.
3. Conditions such as `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, and `@ConditionalOnMissingBean` decide which configurations/beans are applied.
4. Beans are registered if the corresponding conditions match.

Therefore, distinguish between:

- **Limiting transitive dependencies:** preventing unnecessary JARs from entering the runtime classpath.
- **Limiting feature activation:** when the dependency is already present, registering configuration only when appropriate conditions match.

`@ConditionalOnClass` only controls whether a configuration applies; it **does not remove the JAR from the dependency graph**. `@ConditionalOnProperty` can disable your starter's own feature, yet does not prevent another library's auto-configuration from running if that library's dependencies remain present.

## 2. A Controllable Custom Starter Structure

Spring Boot recommends separating auto-configuration from the starter aggregator. For libraries with multiple flavors or optional features, cleanly separate each integration so consumers choose only what they need.

```text
acme/
├── acme-core
├── acme-spring-boot-autoconfigure
├── acme-spring-boot-starter
├── acme-spring-boot-starter-web
└── acme-spring-boot-starter-mail
```

| Module | Responsibility | Dependencies it should contain |
| --- | --- | --- |
| `acme-core` | API and foundational logic independent of web/mail | Only dependencies genuinely needed by core |
| `acme-spring-boot-autoconfigure` | `@AutoConfiguration` classes for core | Spring Boot autoconfigure; optional libraries marked optional |
| `acme-spring-boot-starter` | Core starter | Core + autoconfigure + `spring-boot-starter` |
| `acme-spring-boot-starter-web` | Flavor for web | Core starter + `spring-boot-starter-web` |
| `acme-spring-boot-starter-mail` | Flavor for email | Core starter + `spring-boot-starter-mail` |

A starter aggregator is usually a nearly empty JAR whose primary purpose is declaring dependencies. Auto-configuration code lives in a separate module.

Design principles:

- The core starter pulls only dependencies **every consumer needs**.
- Each optional integration gets its own starter.
- Do not put `spring-boot-starter-web`, `spring-boot-starter-data-jpa`, `spring-boot-starter-mail`, or database drivers in the core starter unless every application needs them.
- If modules cannot be split yet, mark dependencies optional and require consumers to declare them again when using the feature.
- Split auto-configurations by feature so each configuration can be guarded by matching conditions.
- Do not use consumer-side dependency exclusions to patch an overly broad starter you own; fix the dependency graph at the root module whenever possible.

## 3. Maven: Optional Dependencies and Feature-Specific Starters

### 3.1. Regular Dependencies Propagate Transitively

Suppose module A declares dependency B:

```text
Application -> A -> B
```

If B is a regular dependency in A's POM, Maven brings B into the dependency graph of applications using A, unless scope or exclusions alter propagation rules.

An inappropriate example for a core starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

If this snippet sits inside `acme-spring-boot-starter`, every application using the core starter receives the web stack. Even if the application has no controllers, Spring Boot may still detect the Servlet web classpath and create an embedded server.

### 3.2. `<optional>true</optional>` Prevents Automatic Propagation

If the auto-configuration module needs a library to compile and test, yet consumers are not required to use that library, Maven allows marking it optional:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-mail-client</artifactId>
    <version>1.0.0</version>
    <optional>true</optional>
</dependency>
```

When the auto-configuration module builds, `acme-mail-client` remains on that module's own classpath. Yet when another application depends solely on the auto-configuration module, Maven **does not automatically propagate** this optional dependency to the application. Consumers wanting the mail feature must declare that dependency explicitly.

Key points:

- `optional=true` does not mean the dependency is compile-only.
- It does not remove the dependency from the declaring module's classpath.
- It changes whether the dependency propagates to **projects depending on that module**.
- If a feature starter needs this library at runtime, that starter must declare the dependency non-optionally.

### 3.3. Sample POMs for the Modules

The POMs below use Spring Boot 3.3.5 as the parent managing Spring dependency versions. Acme modules use internal version `1.0.0-SNAPSHOT`.

**Root POM: `pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.acme</groupId>
    <artifactId>acme-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>
    <modules>
        <module>acme-core</module>
        <module>acme-spring-boot-autoconfigure</module>
        <module>acme-spring-boot-starter</module>
        <module>acme-spring-boot-starter-web</module>
        <module>demo-app</module>
    </modules>
</project>
```

**Module `acme-core`: `acme-core/pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>acme-core</artifactId>
</project>
```

**Module `acme-spring-boot-autoconfigure`: `acme-spring-boot-autoconfigure/pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>acme-spring-boot-autoconfigure</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-core</artifactId>
            <version>1.0.0-SNAPSHOT</version>
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

`acme-core` is optional in the auto-configuration module so applications using only the auto-configuration artifact are not forced to receive the core library. The core starter redeclares `acme-core` as a mandatory dependency. Test dependencies serve only module tests and are not propagated to consumers.

**Core starter: `acme-spring-boot-starter/pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>acme-spring-boot-starter</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-core</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot-autoconfigure</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </dependency>
    </dependencies>
</project>
```

The core starter brings only Boot core, Acme core, and core auto-configuration. There is no `spring-boot-starter-web`.

**Optional web starter: `acme-spring-boot-starter-web/pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>acme-spring-boot-starter-web</artifactId>
    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot-starter</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
</project>
```

The web starter is explicitly opt-in. Only applications selecting `acme-spring-boot-starter-web` receive Spring MVC, the embedded Servlet server, and related dependencies.

### 3.4. Distinguishing `optional` from Maven Scopes

| Declaration | Current module classpath | Propagated to consumers | Meaning |
| --- | --- | --- | --- |
| `compile` (default) | Compile + runtime | Yes | Regular dependency |
| `runtime` | Runtime + test, not compile | Yes at runtime | Needed only when running |
| `provided` | Compile + test | No | Another environment/container supplies at runtime |
| `test` | Test compile + test runtime | No | For tests only |
| `optional=true` | Still present per declared scope | Not auto-propagated | Consumers must re-select if needed |

Do not use `provided` to simulate an optional dependency. `provided` assumes the deployment environment provides the library at runtime; an executable JAR may miss classes if no container supplies that dependency.

`runtime` is also not a way to hide dependencies from consumers. It still propagates onto the runtime classpath and can activate auto-configurations.

## 4. Gradle: Understanding api, implementation, compileOnly, and runtimeOnly Correctly

The Gradle Java Library Plugin offers configurations with distinct meanings:

| Configuration | Current module | Consumer compile classpath | Consumer runtime classpath |
| --- | --- | --- | --- |
| `api` | Compile + runtime | Yes | Yes |
| `implementation` | Compile + runtime | Does not export compile API | **Yes** |
| `compileOnly` | Compile only | No | No |
| `runtimeOnly` | Runtime only | No | **Yes** |
| `testImplementation` | Test only | No | No |

A common misconception: `implementation` does not mean “private so consumers do not receive the dependency”. It withholds the dependency from the consumer's compile API, yet the dependency still enters **runtimeElements** and the consumer's runtime classpath. Therefore, declaring `implementation 'org.springframework.boot:spring-boot-starter-web'` in a library still pulls Spring MVC into applications.

Example auto-configuration module using an optional SDK to compile:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'
    compileOnly 'com.acme:acme-core:1.0.0'
    testImplementation 'com.acme:acme-core:1.0.0'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

In the core starter:

```groovy
dependencies {
    implementation project(':acme-core')
    implementation project(':acme-spring-boot-autoconfigure')
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

In the web starter:

```groovy
dependencies {
    implementation project(':acme-spring-boot-starter')
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Consumers selecting the web starter get the web dependency in their runtime graph. Consumers selecting only the core starter do not receive web dependencies.

`compileOnly` is not an exact replica of Maven `optional=true`. `compileOnly` also omits the dependency from the module's own runtime classpath. If auto-configuration code needs the SDK at runtime, the feature starter must declare the SDK with an appropriate runtime dependency. Use `testImplementation` so module tests can execute against the SDK.

## 5. Conditions Guarding Auto-Configuration When Dependencies Are Optional

Limiting the dependency graph is the first line of defense. If a library might still be absent under another packaging setup, auto-configuration must check the classpath before using the library's types.

### 5.1. Using `@ConditionalOnClass`

Example configuration with an optional integration:

```java
@AutoConfiguration
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.mail.MailClient")
    static class MailConfiguration {

        @Bean
        @ConditionalOnMissingBean
        MailNotificationSender mailNotificationSender(
                MailClient mailClient) {
            return new MailNotificationSender(mailClient);
        }
    }
}
```

This is a structural pattern; `MailClient` and `MailNotificationSender` belong to the integration module. The nested configuration isolates method signatures referencing the optional class. When `MailClient` is absent from the classpath, Spring skips the nested configuration.

Do not place methods whose return type or parameters use optional classes directly on the outer configuration and assume a condition on the `@Bean` method itself always stops the JVM from loading that type. Spring Boot notes that method-level conditions do not protect the same way as configuration-class-level conditions, because the JVM may have to load the method's types before evaluating conditions. Extract a nested configuration or separate auto-configuration module.

### 5.2. Combining Properties When Users Must Explicitly Enable a Feature

`@ConditionalOnClass` answers “is the library present?”. If the dependency is present yet the feature still needs intentional opt-in, combine with a property:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.acme.mail.MailClient")
@ConditionalOnProperty(
        prefix = "acme.mail",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
static class MailConfiguration {
    // @Bean methods exclusively for the mail integration.
}
```

With `matchIfMissing=false`, omitting the property means the feature stays off. If users add a dedicated mail starter and want that dependency itself to represent opt-in intent, you can choose `matchIfMissing=true`. Default rules must be clearly documented in the starter documentation.

### 5.3. What Conditions Do Not Do

| Mechanism | What it can do | What it cannot do |
| --- | --- | --- |
| `@ConditionalOnClass` | Skip configuration when a class is missing | Remove the JAR from the dependency graph |
| `@ConditionalOnProperty` | Enable/disable configuration via properties | Prevent dependencies from being downloaded |
| `@ConditionalOnMissingBean` | Let defaults back off when a bean exists | Remove dependencies or disable another library's auto-config |
| Maven `optional=true` | Avoid auto-propagating a dependency to consumers | Automatically re-enable the dependency when consumers need the feature |
| Maven `exclusions` | Remove a dependency along one specific path | Remove all other paths that also bring the artifact into the graph |
| Splitting starters | Let consumers select dependencies per feature | Automatically guarantee feature code is bug-free when present |

An Acme property cannot disable Spring Boot's `WebMvcAutoConfiguration` if `spring-boot-starter-web` remains on the runtime classpath. To avoid unintended web-stack activation, you must fix the dependency graph.

## 6. Runnable Example: Core Starter Does Not Pull Spring MVC, Web Starter Enables the Web Stack

This example uses Spring Boot 3.3.5 and Java 17+. We build the multi-module Maven project following the POMs in section 3.3. The demo app needs only the Acme core starter; the web starter can be added to observe the impact.

### 6.1. Core API: `acme-core/src/main/java/com/acme/core/AcmeClient.java`

```java
package com.acme.core;

public record AcmeClient(String mode) {
}
```

### 6.2. Core Auto-Configuration: `acme-spring-boot-autoconfigure/src/main/java/com/acme/autoconfigure/AcmeAutoConfiguration.java`

```java
package com.acme.autoconfigure;

import com.acme.core.AcmeClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.core.AcmeClient")
    static class CoreConfiguration {

        @Bean
        @ConditionalOnMissingBean
        AcmeClient acmeClient() {
            return new AcmeClient("default");
        }
    }
}
```

The nested configuration applies only when the Acme core API is on the classpath. The `acme-core` dependency is marked optional in the auto-configuration module, while the core starter declares it as a mandatory dependency so the default bean is created.

### 6.3. Registering Auto-Configuration

Create the file:

```text
acme-spring-boot-autoconfigure/
└── src/main/resources/
    └── META-INF/spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Contents:

```text
com.acme.autoconfigure.AcmeAutoConfiguration
```

Spring Boot 3.x reads `AutoConfiguration.imports` to discover auto-configurations from external JARs. Do not place auto-configuration classes into packages scanned by the application's component scan; register them via imports.

### 6.4. Consumer Application: `demo-app/src/main/java/demo/DemoApplication.java`

```java
package demo;

import com.acme.core.AcmeClient;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.util.ClassUtils;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner reportDependencies(ApplicationContext context) {
        return args -> {
            boolean mvcPresent = ClassUtils.isPresent(
                    "org.springframework.web.servlet.DispatcherServlet",
                    context.getClassLoader());

            int servletFactoryCount =
                    context.getBeanNamesForType(
                            ServletWebServerFactory.class).length;

            System.out.println("acmeClient=" +
                    context.containsBean("acmeClient"));
            System.out.println("springMvcOnClasspath=" + mvcPresent);
            System.out.println("servletFactoryCount=" + servletFactoryCount);

            AcmeClient client = context.getBean(AcmeClient.class);
            System.out.println("clientMode=" + client.mode());
        };
    }
}
```

The application creates no controllers or business APIs. It prints one core bean and two web-stack signals: whether Spring MVC's class is on the classpath, and the count of `ServletWebServerFactory` beans in the context.

`ServletWebServerFactory` belongs to the Spring Boot API, allowing the demo app to compile using only the core starter. The `DispatcherServlet` class is checked by string name to avoid forcing the demo app to compile directly against Spring MVC.

### 6.5. `demo-app/pom.xml`: Using Only the Core Starter

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>
    <artifactId>demo-app</artifactId>
    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot-starter</artifactId>
            <version>1.0.0-SNAPSHOT</version>
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
```

Build from the root directory:

```bash
mvn -q -pl demo-app -am package
```

Run:

```bash
java -jar demo-app/target/demo-app-1.0.0-SNAPSHOT.jar
```

Expected output:

```text
acmeClient=true
springMvcOnClasspath=false
servletFactoryCount=0
clientMode=default
```

The application receives the Acme core bean without Spring MVC and without creating an embedded Servlet server. The core starter does not inadvertently pull the web stack onto the runtime classpath.

### 6.6. Opting In to the Web Starter

If the application is genuinely a web application, add this dependency to `demo-app/pom.xml`:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-spring-boot-starter-web</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</dependency>
```

Rebuild and run the same command. Expected output:

```text
acmeClient=true
springMvcOnClasspath=true
servletFactoryCount=1
clientMode=default
```

This time `spring-boot-starter-web` is added via the web starter. Spring MVC is present on the runtime classpath, Spring Boot selects Servlet web mode, and creates an embedded server factory. The web process keeps running to serve requests; stop with Ctrl+C when testing locally.

This is an intentional change: only after adding the feature dependency do the corresponding web components appear. No dummy controller is needed to prove the web stack was activated.

## 7. Inspecting the Dependency Graph Instead of Guessing from the Direct POM

### 7.1. Maven `dependency:tree`

To trace the Spring Web/Tomcat propagation path:

```bash
mvn -pl demo-app -am dependency:tree
mvn -pl demo-app -am dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web,org.springframework:spring-webmvc,org.apache.tomcat.embed:tomcat-embed-core
```

When the demo uses only the core starter, the filter command should find no `spring-boot-starter-web`, `spring-webmvc`, or `tomcat-embed-core` in the demo's dependency graph.

After adding the web starter, the filter command will show a propagation path similar to:

```text
demo-app
\- acme-spring-boot-starter-web
   \- spring-boot-starter-web
      +- spring-boot-starter-tomcat
      |  \- tomcat-embed-core
      \- spring-webmvc
```

This is an abbreviated shape; the actual tree contains additional starters and related libraries depending on versions and dependency mediation.

### 7.2. Finding Where a Dependency Comes From

When a dependency appears unexpectedly:

1. Run `mvn dependency:tree` on the exact consumer module.
2. Locate the suspect artifact, e.g., `spring-boot-starter-web` or `spring-webmvc`.
3. Trace parent nodes upward to find the first direct dependency pulling it in.
4. Check whether that dependency truly needs web capabilities.
5. Fix the starter/module owning that dependency or apply an exclusion on that exact edge if upstream cannot be modified.
6. Re-run the dependency tree and runtime tests.

Do not merely search for the artifact name in the application's POM. A dependency can arrive from an SDK, another starter, or an internal module across multiple intermediate hops.

### 7.3. Gradle Dependency Reports

With Gradle:

```bash
./gradlew :demo-app:dependencies --configuration runtimeClasspath
./gradlew :demo-app:dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
```

`dependencies` displays the entire runtime graph; `dependencyInsight` shows why a dependency was selected and which path brought it in. For auto-configuration activation problems, `runtimeClasspath` is usually more important than compile classpath.

## 8. Exclusions: Blocking a Dependency Along a Specific Path

If you cannot control a third-party library's POM and it pulls unnecessary dependencies, Maven supports exclusions:

```xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>vendor-client</artifactId>
    <version>2.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

An exclusion is declared on **one dependency edge**. If another dependency also pulls `spring-boot-starter-web`, the artifact can remain in the graph.

Before excluding, verify whether the vendor library uses classes from the excluded dependency. If `vendor-client` genuinely needs Spring MVC to run, an exclusion can cause `NoClassDefFoundError` or bean creation failures at startup.

Do not use wildcards to strip foundational dependencies en masse, and do not exclude logging/JSON/validation solely to shrink JAR counts without verifying the runtime contract.

Handling priority:

1. Split features into dedicated starters in libraries you own.
2. Mark dependencies optional in the auto-configuration module when it matches the contract.
3. Apply targeted exclusions if unwanted dependencies come from unmodifiable upstreams.
4. Verify the runtime graph and run tests after removing the dependency.

## 9. Combining the Dependency Graph With Conditions and Properties

A well-designed starter often needs multiple layers of protection:

| Layer | Tool | Goal |
| --- | --- | --- |
| Artifact/module | Separate core starter and feature starters | Consumers receive only dependencies they choose |
| Dependency declaration | Maven optional / appropriate Gradle configuration | Prevent unwanted propagation of optional dependencies |
| Classpath | `@ConditionalOnClass` | Skip loading configuration when the library is absent |
| Property | `@ConditionalOnProperty` | Allow intentional feature enablement/disabling |
| Bean | `@ConditionalOnMissingBean` | Allow users to replace default beans |

For example, a mail integration should only activate when the mail SDK is present and the property is enabled:

```java
@AutoConfiguration
public class AcmeMailAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.mail.MailClient")
    @ConditionalOnProperty(
            prefix = "acme.mail",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    static class MailConfiguration {

        @Bean
        @ConditionalOnMissingBean
        MailNotificationSender mailNotificationSender(
                MailClient mailClient) {
            return new MailNotificationSender(mailClient);
        }
    }
}
```

This is an illustrative pattern; mail types belong to a separate integration. The mail dependency should go into `acme-spring-boot-starter-mail`, not the core starter. The property guards the bean provided by Acme; separating the starter is what keeps the mail dependency out of non-mail apps.

## 10. Testing Dependencies and Auto-Configuration

### 10.1. Testing the Default Core Bean

In the auto-configuration module, use `ApplicationContextRunner`:

```java
package com.acme.autoconfigure;

import com.acme.core.AcmeClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            AcmeAutoConfiguration.class));

    @Test
    void createsCoreClientWhenCoreLibraryIsPresent() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AcmeClient.class);
            assertThat(context.getBean(AcmeClient.class).mode())
                    .isEqualTo("default");
        });
    }

    @Test
    void userClientReplacesDefault() {
        this.runner
                .withBean(AcmeClient.class, () -> new AcmeClient("custom"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context.getBean(AcmeClient.class).mode())
                            .isEqualTo("custom");
                });
    }
}
```

This test verifies core bean back-off. It does not replace inspecting the consumer's dependency graph.

### 10.2. Testing Classpath Conditions

You can add a test hiding the core class with `FilteredClassLoader`:

```java
import org.springframework.boot.test.context.FilteredClassLoader;

@Test
void skipsCoreConfigurationWhenCoreClassIsAbsent() {
    new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                    AcmeAutoConfiguration.class))
            .withClassLoader(new FilteredClassLoader(AcmeClient.class))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(AcmeClient.class);
            });
}
```

This test proves the classpath condition protects auto-configuration when an optional library is missing. It does not prove the library was omitted from the dependency tree; those are two separate checks.

### 10.3. Testing the Dependency Graph in CI

You can add a build step to verify the runtime dependency graph:

- Maven: capture `mvn -pl demo-app -am dependency:tree` output or filter unwanted artifacts using `-Dincludes`.
- Gradle: use `dependencies --configuration runtimeClasspath` and `dependencyInsight`.
- Integration test: start the core consumer and verify `WebApplicationType.NONE` or no `ServletWebServerFactory`; verify web consumer has Servlet infrastructure present.

Do not test only that the application starts successfully. A CLI application can still start even when a starter accidentally pulls in Tomcat; only a bean inventory and dependency tree catch the redundant web stack.

## 11. Common Design Mistakes

1. **Core starter depending on every Spring Boot starter.** Every consumer receives a huge runtime graph and may trigger unnecessary auto-configurations. Add only shared dependencies truly needed.
2. **Thinking Gradle `implementation` does not propagate to consumer runtime.** Wrong: implementation does not export compile API, yet the dependency still appears in `runtimeElements`.
3. **Thinking `@ConditionalOnClass` removes a dependency.** Wrong: the condition only skips configuration; the JAR remains on the classpath.
4. **Using properties to patch an overly broad dependency graph.** Properties only control your configuration or configurations reading those properties; they do not disable another library's auto-configuration automatically.
5. **Placing optional classes in `@Bean` signatures of the outer configuration.** Risks class-loading errors before method conditions are evaluated. Isolate inside a nested configuration with `@ConditionalOnClass` or a separate module.
6. **Marking every dependency optional.** Core dependencies actually needed must be required in the core starter; misusing optional leaves consumers missing classes at runtime.
7. **Using `provided` instead of `optional`.** The two scopes have different meanings; provided assumes the runtime environment supplies the dependency.
8. **Excluding an artifact without checking other paths.** Exclusions apply only to the declared edge; the artifact may still enter via another dependency.
9. **Excluding libraries the vendor genuinely needs.** Builds may pass while runtime fails due to missing classes or dependent auto-configurations.
10. **Using `@ConditionalOnMissingBean` as a classpath gate.** Bean conditions do not replace class conditions; missing bean and missing library are two distinct states.
11. **Not testing core apps and feature apps separately.** Starters need a consumer matrix to guarantee core does not pull unintended features and feature starters supply needed dependencies.
12. **Checking only the compile classpath.** Auto-configuration executes at application startup, so the runtime classpath is what must be checked.

## 12. Pre-Release Checklist for a Custom Starter

- [ ] Core starter contains only dependencies mandatory for all consumers.
- [ ] Web, mail, database, messaging, and optional integrations have separate starters/modules when needed.
- [ ] Optional library dependencies in auto-configuration are declared with proper optional semantics.
- [ ] Feature starters explicitly redeclare required runtime dependencies.
- [ ] Do not use Gradle `implementation` assuming dependencies disappear from consumer runtime.
- [ ] Optional classes are guarded with `@ConditionalOnClass` at the appropriate configuration level.
- [ ] Opt-in features have the library's own property namespace.
- [ ] Default beans have `@ConditionalOnMissingBean` when users need to replace them.
- [ ] `AutoConfiguration.imports` registers only necessary auto-configurations.
- [ ] Inspected the dependency tree/`runtimeClasspath` of each starter.
- [ ] Verified apps using only the core starter have no unintended web/database/mail stacks.
- [ ] Verified apps adding feature starters receive the right dependencies and infrastructure beans.
- [ ] Ran auto-configuration tests with dependencies present/absent, properties enabled/disabled, and custom beans.
- [ ] Verified dependency exclusions do not break the runtime contract.

## Official Documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): separating auto-configuration/starter, optional dependencies, `@ConditionalOnClass`, `AutoConfiguration.imports`, and testing.
- [Maven — Optional and Excluded Dependencies](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies): semantics of `optional` and per-edge exclusions.
- [Maven POM Reference — Dependency Scopes](https://maven.apache.org/pom.html#dependency-scopes): differences among compile, runtime, provided, and test.
- [Gradle — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `api`, `implementation`, `compileOnly`, and `runtimeOnly`.
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html): how configurations construct compile/runtime classpaths and propagate dependencies to consumers.
