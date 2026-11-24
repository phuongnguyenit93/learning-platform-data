# How Do Class-Level and Method-Level Conditions Affect Registration Scope?

## 1. The Core Question

In Spring Boot auto-configuration, a conditional annotation does not just decide **true/false**; where you place the annotation determines **the scope of configuration affected when the condition does not match**.

Compare the two declarations below:

~~~java
// Approach A: class-level condition
@AutoConfiguration
@ConditionalOnProperty(prefix = "demo", name = "enabled", havingValue = "true")
public class DemoAutoConfiguration {

    @Bean
    ServiceA serviceA() { /* ... */ return null; }

    @Bean
    ServiceB serviceB() { /* ... */ return null; }
}
~~~

~~~java
// Approach B: condition on exactly one @Bean method
@AutoConfiguration
public class DemoAutoConfiguration {

    @Bean
    ServiceA serviceA() { /* ... */ return null; }

    @Bean
    @ConditionalOnProperty(prefix = "demo", name = "enabled", havingValue = "true")
    ServiceB serviceB() { /* ... */ return null; }
}
~~~

**Both snippets are illustrative diagrams, not runnable programs**: actual `ServiceA`/`ServiceB` types do not exist yet, and `return null` is not how you provide a complete service.

If `demo.enabled=false`:

- **Approach A:** the entire configuration class is not applied along the normal registration path; both `serviceA` and `serviceB` bean definitions belonging to this class are not registered.
- **Approach B:** the configuration class can still be processed; `serviceA` can still be registered, while `serviceB` is skipped due to the condition attached to its method.

That is the difference in **registration scope**. Place a condition at the class level when the entire configuration depends on a single premise; place it at the method level when only one bean depends on that premise.

This lesson belongs to the **Condition Mechanism** group of Spring Boot auto-configuration. The focus is on the impact on bean definitions in the context, not a mechanism for toggling Java methods at runtime.

## 2. Distinguish Five Layers Before Searching for the Root Cause

When investigating why a bean does not appear, avoid conflating the following concepts:

| Layer | Meaning | Potential confusion |
| --- | --- | --- |
| **Auto-configuration candidate** | Spring Boot finds the class name via metadata on the classpath. | Having a candidate does not mean all conditions match. |
| **Import/configuration selection** | The class enters parsing after exclusions/filters and import processing. | A selected class can still be rejected by a class-level condition. |
| **Condition evaluation** | Spring checks `Condition`s attached to the class or method. | One condition level passing does not guarantee all related levels pass. |
| **Bean definition registration** | Spring stores the blueprint for creating the bean in the `BeanFactory`. | Having a definition differs from having created an instance. |
| **Bean instance creation** | The container creates the object per scope/dependencies/lifecycle. | Constructor failures or lazy init are not condition mismatches. |

Spring Boot's `@AutoConfiguration` is a form of `@Configuration`. Boot provides conditional annotations such as `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnWebApplication`, etc.

The underlying mechanism is Spring Framework's `@Conditional`. A condition can be applied to a configuration type or a bean-producing method. Spring Boot's conditions are written to support configuration registration based on classpath, environment, and existing beans.

Typically, an auto-configuration is published by a library at:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

This file contains the fully qualified names of candidate auto-configuration classes. Registering a candidate **does not guarantee** that class conditions match, method conditions match, or beans are created successfully.

## 3. Class-Level Conditions: The Shared Gate of a Configuration

Consider the configuration:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class FeatureAutoConfiguration {

    @Bean
    FeatureEngine engine() { /* ... */ return null; }

    @Bean
    FeatureRegistry registry() { /* ... */ return null; }
}
~~~

This is a scope illustration snippet; the types are not defined. The annotation on **`FeatureAutoConfiguration`** means: only process this configuration branch when `demo.feature.enabled` resolves to `true`.

With `matchIfMissing=false` (the default), a missing key also fails the condition. If the outer class does not match, **neither the `engine` nor the `registry` bean definitions are declared through this class**.

Diagram:

~~~text
FeatureAutoConfiguration
  @ConditionalOnProperty(demo.feature.enabled=true)
          |
          +-- false / missing ----> skip configuration branch
          |                         |- engine: not registered
          |                         '- registry: not registered
          |
          '-- true --------------> process @Beans inside
                                     |- engine: still checks own conditions
                                     '- registry: still checks own conditions
~~~

Thus, a class-level condition **does not mean all beans in the context are deleted**. It only governs applying that configuration class along the evaluated registration branch. Application beans, other auto-configurations, or independent import paths are not automatically removed with it.

In particular, when a configuration class does not match, do not explain it by saying Spring created the beans and then "turned them off". In the standard processing path, those bean definitions **were never registered in the first place**.

### When Should You Place a Condition at the Class Level?

- The entire configuration only makes sense when a foundational library is on the classpath — for instance, integration A cannot operate without A's API.
- The entire group of beans belongs to one feature with a shared on/off switch.
- The configuration only makes sense in a servlet or reactive web application respectively.
- If the premise is false, **none of the beans in that class** need to exist.

If only one bean depends on a property or optional library, a class-level condition may be **overly broad**. In that case, move it down to the method or a narrower nested configuration.

### @ConditionalOnProperty at the Class Level

Cases with `havingValue="true"` and `matchIfMissing=false`:

| Resolved Environment value | Result |
| --- | --- |
| `"true"` | Matches. |
| `"false"` | Does not match. |
| `"other"` | Does not match. |
| Key absent | Does not match. |

If `matchIfMissing=true`, a missing key can be treated as matching. If `havingValue` is omitted, `@ConditionalOnProperty`'s default rule is that the key exists with a value **not equal to `false`**; do not assume this rule is strict boolean equality. Spring Boot 3.5 also offers `@ConditionalOnBooleanProperty` when you want to explicitly express a boolean property.

A key can appear in `application.properties` yet be overridden by a higher-precedence source; the condition checks the value resolved from `Environment` at evaluation time, not a single file.

## 4. Conditions on `@Bean` Methods: Gate for a Single Bean Definition

Consider:

~~~java
@AutoConfiguration
public class FeatureAutoConfiguration {

    @Bean
    FeatureEngine engine() { /* ... */ return null; }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "report-enabled",
            havingValue = "true"
    )
    ReportService reportService() { /* ... */ return null; }
}
~~~

This is also an illustrative snippet, not runnable on its own. There is no outer class condition, so `engine()` can be registered normally. `reportService()` is registered **only when** property `demo.report-enabled=true`; a false property does not cause `engine()` to be skipped.

~~~text
FeatureAutoConfiguration (processed)
       |
       +-- @Bean engine() ----------> registered unless another gate blocks it
       |
       '-- @Bean reportService()
              @ConditionalOnProperty
                    |
                    +-- false -----> only reportService is not registered
                    '-- true ------> reportService may be registered
~~~

Note that "may be registered" is the accurate phrasing: one condition matching does not prove there are no other constraints, configuration errors, or issues at the instance creation step.

### Why Does Method-Level Condition Scope Matter?

An auto-configuration often provides several related beans with non-uniform conditions:

- `CoreService` can work even in a CLI application.
- `HttpAdapter` is only needed when HTTP integration is enabled.
- `MetricsReporter` is only needed when metrics are enabled.
- `DefaultNotifier` is only needed when the user has not declared their own `Notifier`.

If you put all three optional conditions on the outer class, disabling one secondary feature can wipe out the core service too. Placing them on individual bean methods or grouping via nested configuration classes yields a much more adaptable design.

## 5. How Do Class-Level and Method-Level Conditions Combine?

Conditions along the path from configuration class to bean act like **gates that must all be open**. For a bean that has conditions on both the class and the method, the method condition cannot "rescue" the bean when the class condition has already excluded the configuration:

~~~java
@AutoConfiguration
@ConditionalOnProperty(prefix = "demo", name = "auto", havingValue = "true")
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "demo", name = "reports", havingValue = "true")
    ReportService reportService() { /* ... */ return null; }
}
~~~

The logical condition for the bean to appear along this branch is:

~~~text
autoConfiguration discovered / not excluded
  AND demo.auto = true
  AND demo.reports = true
  AND all other relevant conditions match
  THEN reportService may be registered
~~~

Table illustrating the exact scope:

| `demo.auto` | `demo.reports` | Outer class | `reportService` |
| --- | --- | --- | --- |
| `true` | `true` | Passes gate | May be registered |
| `true` | `false` | Passes gate | Skipped |
| `false` | `true` | Skipped | Skipped along with outer class |
| `false` | `false` | Skipped | Skipped |
| Absent | `true` | Does not match with default `matchIfMissing=false` | Skipped |

The table does not imply Spring definitely invokes the method condition when the class condition has already rejected the class. In a skipped configuration branch, deeper evaluation may not happen at all. This is an **outcome model**, not a list of callbacks guaranteed to run.

### Multiple Conditions at the Same Level

Example:

~~~java
@Bean
@ConditionalOnProperty(prefix = "demo", name = "audit", havingValue = "true")
@ConditionalOnMissingBean(AuditService.class)
AuditService auditService() { /* ... */ return null; }
~~~

This is a snippet; class `AuditService` is not declared. The bean can only be registered when **the property permits it and no matching bean exists yet**. Multiple conditions at the same location generally must **all match simultaneously**, not in an OR relationship.

If you want "A or B", you cannot assume placing two conditional annotations creates OR. You need to structure configuration branches or write a custom `Condition` for the desired logic.

## 6. At Which Level Should `@ConditionalOnMissingBean` Be Placed?

A very important case in auto-configuration is **back-off**: the library supplies a default, while the application is allowed to replace the library's bean.

Suppose an auto-configuration has both a default `NotificationService` and an `AuditRegistry`. If you write:

~~~java
@AutoConfiguration
@ConditionalOnMissingBean(NotificationService.class)
public class NotificationAutoConfiguration {

    @Bean
    NotificationService defaultNotificationService() { /* ... */ return null; }

    @Bean
    AuditRegistry auditRegistry() { /* ... */ return null; }
}
~~~

then when the application declares its own `NotificationService`, the **class-level** condition does not match. Along this processing path, **both `defaultNotificationService` and `auditRegistry`** are affected. This can be an unwanted side effect if the registry should exist even when the notifier has been replaced.

If the condition is meant solely to replace the notifier, move it down to the method:

~~~java
@AutoConfiguration
public class NotificationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationService.class)
    NotificationService defaultNotificationService() { /* ... */ return null; }

    @Bean
    AuditRegistry auditRegistry() { /* ... */ return null; }
}
~~~

When the application has its own `NotificationService`, **the default bean** backs off, while `auditRegistry` can still be registered. This placement matches the requirement "only skip one default bean".

**Detail to get right:** according to the Spring Boot documentation, for bean conditions such as `@ConditionalOnMissingBean`, placing the condition at the class level does not mean the condition uses an entirely different bean-lookup rule set from method level; one crucial difference is that **a class condition can prevent registering the configuration class itself if it fails**, whereas a method condition only skips the corresponding bean.

### Why Must `@ConditionalOnMissingBean` Pay Attention to Timing?

`@ConditionalOnBean` and `@ConditionalOnMissingBean` inspect bean definitions that have already been processed by the time the condition runs; they do not look ahead at definitions that will appear later. Spring Boot defers auto-configuration imports so regular application bean definitions have a chance to be processed first; therefore, these bean conditions belong best in auto-configuration.

For type-based conditions to be reliable, declare clear return types on `@Bean` methods. As of Spring Boot 3.5, bean conditions can take generic information on method return types into account; if you want to check all beans of a raw type, specify the type explicitly in the annotation, e.g. `@ConditionalOnMissingBean(Converter.class)`, rather than relying on generic inference.

Do not write `@Bean Object notifier()` and expect every `NotificationService`-based condition to infer the exact runtime type of the object in every phase.

## 7. `@ConditionalOnClass`: Why Class Placement Sometimes Affects Class Loading Too?

Spring Boot supports `@ConditionalOnClass` to only use a configuration when a library class is available on the classpath. When placed directly on a `@Configuration` class, the framework can read annotation metadata via ASM before having to load the configuration class, thereby protecting a configuration branch with optional dependencies.

However, the following case carries risk:

~~~java
@Bean
@ConditionalOnClass(name = "com.vendor.sdk.Client")
com.vendor.sdk.Client client() {
    return new com.vendor.sdk.Client();
}
~~~

**This is an illustrative example and will not compile without the SDK at compile time.** Even though the method has `@ConditionalOnClass`, the JVM may have to read the method's signature containing return type `Client` before the condition is evaluated. If the optional dependency is missing at runtime, class-loading problems can occur.

A safer pattern for auto-configuration:

~~~java
@AutoConfiguration
public class VendorAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.Client")
    static class ClientConfiguration {

        @Bean
        com.vendor.sdk.Client client() {
            return new com.vendor.sdk.Client();
        }
    }
}
~~~

This is an **architectural pattern, not runnable** without the SDK; annotation imports are also omitted. The `ClientConfiguration` class is only processed when the required class is available, isolating the SDK-dependent method signature from the rest of the auto-configuration. In real projects, the SDK may exist at compile time for the auto-configuration module while being an optional dependency at application runtime.

**Do not conclude that every `@ConditionalOnClass` on a method is useless.** The specific warning applies especially when the method signature references an optional class that may be absent.

### Nested Classes as an Intermediate Level

Beyond class and method levels, Spring supports `static nested @Configuration` to group a branch of beans:

~~~text
Outer @AutoConfiguration
    |- CoreService (outer-level bean)
    '- Nested @Configuration, @ConditionalOnClass(optional SDK)
         |- OptionalClient
         '- OptionalAdapter
~~~

Here, `@ConditionalOnClass` on the nested class blocks the entire group of two SDK integration beans, yet **does not block CoreService** in the outer class. Thus a nested class provides an **intermediate scope**, avoiding both an overly broad outer condition and duplicating conditions on each method.

However, if the nested class is imported independently or lies within component-scan scope via another path, do not assume every outer condition automatically covers it the way it does when the nested class is processed solely through the outer configuration.

## 8. Runnable Maven/Java 17+ Example: Observing Class-Level and `@Bean`-Level Scope

To see the difference in practice rather than theory, let's build a simple Spring Boot application consisting of:

- An `@AutoConfiguration` class with a **shared gate** `demo.auto.enabled`. By default the gate is open when the property is absent.
- A `CoreService` bean with no method-level condition of its own.
- A `ReportService` bean registered only when `demo.report.enabled=true`.
- An `HttpMarker` bean registered only when `demo.http.enabled=true`. The name "HttpMarker" is just an illustrative label and **does not start an HTTP server**.
- A default `Notifier` bean using `@ConditionalOnMissingBean` at the method level. The application can replace it with its own custom bean.
- An `ApplicationRunner` that checks which types are actually present in the context.

The example uses **Spring Boot 3.5.0, Java 17+, and Maven**, with no database, web dependency, or external server needed.

### 8.1. Directory Structure

~~~text
conditional-scope-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── api/
    │   │   ├── CoreService.java
    │   │   ├── ReportService.java
    │   │   ├── HttpMarker.java
    │   │   └── Notifier.java
    │   ├── app/DemoApplication.java
    │   └── autoconfig/ScopeAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The application's package is `com.example.app`; the auto-configuration's package is `com.example.autoconfig`. These are sibling packages, so the application's default component scan does not pick up the auto-configuration automatically. Boot loads the class intentionally via imports metadata.

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>conditional-scope-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

### 8.3. Four Interfaces

File `src/main/java/com/example/api/CoreService.java`:

~~~java
package com.example.api;

public interface CoreService {
    String value();
}
~~~

File `src/main/java/com/example/api/ReportService.java`:

~~~java
package com.example.api;

public interface ReportService {
    String value();
}
~~~

File `src/main/java/com/example/api/HttpMarker.java`:

~~~java
package com.example.api;

public interface HttpMarker {
    String value();
}
~~~

File `src/main/java/com/example/api/Notifier.java`:

~~~java
package com.example.api;

public interface Notifier {
    String value();
}
~~~

Simple interfaces clearly identify types for bean conditions and `ObjectProvider`. Merely declaring a type on the classpath does not mean Spring has created a bean of that type.

### 8.4. ScopeAutoConfiguration.java

File `src/main/java/com/example/autoconfig/ScopeAutoConfiguration.java`:

~~~java
package com.example.autoconfig;

import com.example.api.CoreService;
import com.example.api.ReportService;
import com.example.api.HttpMarker;
import com.example.api.Notifier;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.auto",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class ScopeAutoConfiguration {

    @Bean
    CoreService coreService() {
        return () -> "CORE";
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.report",
            name = "enabled",
            havingValue = "true"
    )
    ReportService reportService() {
        return () -> "REPORT";
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.http",
            name = "enabled",
            havingValue = "true"
    )
    HttpMarker httpMarker() {
        return () -> "HTTP";
    }

    @Bean
    @ConditionalOnMissingBean(Notifier.class)
    Notifier defaultNotifier() {
        return () -> "DEFAULT";
    }
}
~~~

Scope breakdown:

- **`demo.auto.enabled` on the class:** blocks all beans declared from `ScopeAutoConfiguration` when `false`. When the property is absent, `matchIfMissing=true` allows the class.
- **`demo.report.enabled` on the method:** only blocks `reportService()`; core, marker, and notifier are unaffected.
- **`demo.http.enabled` on the method:** only blocks `httpMarker()`; independent of `demo.report.enabled` itself.
- **`@ConditionalOnMissingBean(Notifier.class)` on the method:** only blocks the default notifier if a matching `Notifier` bean already exists. Does not remove `CoreService` or `ReportService`.

Both `ReportService` and `HttpMarker` here are simulated functional interfaces requiring no web classpath.

### 8.5. AutoConfiguration.imports

Create the file at the exact path:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Single-line content:

~~~text
com.example.autoconfig.ScopeAutoConfiguration
~~~

This file lets Boot discover the candidate auto-configuration class. If the file is missing or the FQCN is wrong, the absence of default beans may be due to **configuration non-discovery**, which is different from class-level or method-level conditions failing to match.

### 8.6. DemoApplication.java

File `src/main/java/com/example/app/DemoApplication.java`:

~~~java
package com.example.app;

import com.example.api.CoreService;
import com.example.api.ReportService;
import com.example.api.HttpMarker;
import com.example.api.Notifier;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.custom",
            name = "enabled",
            havingValue = "true"
    )
    Notifier customNotifier() {
        return () -> "CUSTOM";
    }

    @Bean
    ApplicationRunner printBeans(
            ObjectProvider<CoreService> coreProvider,
            ObjectProvider<ReportService> reportProvider,
            ObjectProvider<HttpMarker> httpProvider,
            ObjectProvider<Notifier> notifierProvider) {

        return args -> {
            CoreService core = coreProvider.getIfAvailable();
            ReportService report = reportProvider.getIfAvailable();
            HttpMarker http = httpProvider.getIfAvailable();
            Notifier notifier = notifierProvider.getIfAvailable();

            System.out.println("core="
                    + (core == null ? "ABSENT" : core.value()));
            System.out.println("report="
                    + (report == null ? "ABSENT" : report.value()));
            System.out.println("http="
                    + (http == null ? "ABSENT" : http.value()));
            System.out.println("notifier="
                    + (notifier == null ? "ABSENT" : notifier.value()));
        };
    }
}
~~~

Because the application has a custom `Notifier` in user configuration, `@ConditionalOnMissingBean` on the auto-configuration can back off. `ObjectProvider#getIfAvailable()` prints `ABSENT` if the type has no bean. Across the example's scenarios, each type has at most one bean; if you deliberately add multiple beans of the same type without a single primary/candidate, you may hit an ambiguity error.

### 8.7. application.properties

~~~properties
spring.main.banner-mode=off
logging.level.root=ERROR
~~~

Located at `src/main/resources/application.properties`. We omit the four `demo.*.enabled` switches from the file so we can vary them via the command line. Non-program log lines may vary by environment; the stdout shown below consists of the four lines printed by `printBeans` itself.

### 8.8. Build and Test Each Scenario

With Java 17+ and Maven installed, from the `conditional-scope-demo` directory:

~~~bash
mvn -q -DskipTests package
java -jar target/conditional-scope-demo-1.0.0.jar
~~~

Four lines printed by the program:

~~~text
core=CORE
report=ABSENT
http=ABSENT
notifier=DEFAULT
~~~

Reason: the `demo.auto.enabled` class condition permits an absent property; `coreService()` has no condition of its own; the report and http methods are not enabled; no custom notifier exists yet, so the default notifier is registered.

**Scenario 2 — enable only report:**

~~~bash
java -jar target/conditional-scope-demo-1.0.0.jar --demo.report.enabled=true
~~~

~~~text
core=CORE
report=REPORT
http=ABSENT
notifier=DEFAULT
~~~

Enabling report does not alter the HTTP or notifier beans. This is direct evidence of **method-level scope**.

**Scenario 3 — enable only the HTTP marker:**

~~~bash
java -jar target/conditional-scope-demo-1.0.0.jar --demo.http.enabled=true
~~~

~~~text
core=CORE
report=ABSENT
http=HTTP
notifier=DEFAULT
~~~

The marker feature is controlled independently from report. There is no real HTTP server, so the experiment requires no ports or web dependencies.

**Scenario 4 — enable both methods:**

~~~bash
java -jar target/conditional-scope-demo-1.0.0.jar --demo.report.enabled=true --demo.http.enabled=true
~~~

~~~text
core=CORE
report=REPORT
http=HTTP
notifier=DEFAULT
~~~

**Scenario 5 — disable the class-level condition even when both methods are enabled:**

~~~bash
java -jar target/conditional-scope-demo-1.0.0.jar --demo.auto.enabled=false --demo.report.enabled=true --demo.http.enabled=true
~~~

~~~text
core=ABSENT
report=ABSENT
http=ABSENT
notifier=ABSENT
~~~

The outer class is not applied, so no beans are contributed **through this auto-configuration class**. Both method conditions evaluating to `true` cannot make beans "bypass" the class-level condition.

**Scenario 6 — application replaces only the default notifier:**

~~~bash
java -jar target/conditional-scope-demo-1.0.0.jar --demo.custom.enabled=true --demo.report.enabled=true
~~~

~~~text
core=CORE
report=REPORT
http=ABSENT
notifier=CUSTOM
~~~

The application's custom bean causes `@ConditionalOnMissingBean(Notifier.class)` not to match, yet `CoreService` and `ReportService` remain active. If the missing-bean condition had been placed on the **outer class** instead of the method, it could have excluded core/report too — defeating the goal of replacing only the notifier.

**Scenario 7 — auto-configuration class disabled while application bean remains:**

~~~bash
java -jar target/conditional-scope-demo-1.0.0.jar --demo.auto.enabled=false --demo.custom.enabled=true --demo.report.enabled=true
~~~

~~~text
core=ABSENT
report=ABSENT
http=ABSENT
notifier=CUSTOM
~~~

The class condition only governs beans supplied by `ScopeAutoConfiguration`. The `customNotifier()` bean lives in a different configuration class, so it can continue to exist.

### 8.9. Outcome Matrix

| `auto` | `report` | `http` | `custom` | Core | Report | HTTP | Notifier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| absent | absent | absent | absent | CORE | ABSENT | ABSENT | DEFAULT |
| absent | true | absent | absent | CORE | REPORT | ABSENT | DEFAULT |
| absent | absent | true | absent | CORE | ABSENT | HTTP | DEFAULT |
| absent | true | true | absent | CORE | REPORT | HTTP | DEFAULT |
| false | true | true | absent | ABSENT | ABSENT | ABSENT | ABSENT |
| absent | true | absent | true | CORE | REPORT | ABSENT | CUSTOM |
| false | true | absent | true | ABSENT | ABSENT | ABSENT | CUSTOM |

When a CLI argument is not passed, the value is **absent**; not all properties default to false. Specifically, `demo.auto.enabled` is permitted when absent thanks to `matchIfMissing=true`. The method properties use the default `matchIfMissing=false`.

## 9. How to Debug Class-Level and Method-Level Conditions

Do not only inspect `Environment.getProperty(...)` at `ApplicationRunner` time. Conditions are evaluated while Spring processes configurations/bean definitions; changing a property later does not make Spring re-register beans automatically.

To see the reasons, run the application with the condition report:

~~~bash
java -jar target/conditional-scope-demo-1.0.0.jar --demo.report.enabled=true --debug --logging.level.root=INFO
~~~

In the `Condition Evaluation Report` output (when logging allows it to display), look for:

- `ScopeAutoConfiguration`: the class-level condition `demo.auto.enabled`.
- `ScopeAutoConfiguration#reportService`: the report method condition.
- `ScopeAutoConfiguration#httpMarker`: the HTTP method condition.
- `ScopeAutoConfiguration#defaultNotifier`: the missing-bean condition.
- Compare against running `--demo.auto.enabled=false` to observe the outer class condition change.

Exact display names and log formatting depend on the Boot version; read the **match/mismatch reasons**, rather than insisting on a fixed log line. When the class condition does not match, method conditions may not be evaluated independently as they are when the class is accepted. Therefore, **not seeing a negative match for a method** is not enough to claim the method will definitely be registered.

If using Spring Boot Actuator, the `/actuator/conditions` endpoint (when the dependency is present and safely exposed) provides condition details. Do not expose sensitive diagnostic endpoints publicly without access control. In a simple lesson, installing Actuator is unnecessary; the report via `--debug` suffices.

### Short Checklist When a Bean Is Missing

1. **Verify auto-configuration discovery**: the class is in `AutoConfiguration.imports` and the JAR is on the runtime classpath.
2. **Check exclusions/filters**: did the application exclude that class via `exclude` or `spring.autoconfigure.exclude`?
3. **Check the class-level condition first**: if it is already false, bean methods in this branch are not registered.
4. **If the class matches, check the specific method**: its own property, prerequisite bean, missing class, scope.
5. **Cross-check the resolved property value**: command line, system properties, environment variables, config files, and profiles can override one another.
6. **If conditions match yet the bean still fails**, distinguish an instance-creation/dependency error from a definition-registration error.
7. **Compare a minimal pair of runs**: flip only one parameter from false to true to pinpoint the affected scope.

## 10. Mistakes Worth Avoiding

### Mistake 1: "If one method condition is false, the whole class is skipped"

Incorrect. `@Conditional` placed on a method only affects the bean definition contributed by that method. Other methods still have a chance to be processed if the class and relevant conditions do not block them.

### Mistake 2: "Class condition true means every bean method inside is guaranteed to exist"

Incorrect. A true class condition only opens the outer gate. Each method still has its own conditions; there can also be bean creation failures, `@Lazy`, or other constraints.

### Mistake 3: "A true method condition can reopen an already excluded class"

Incorrect. If the outer configuration is not applied, methods inside that branch are not used to register beans. A matching method property does not override a failing class property.

### Mistake 4: "`@ConditionalOnMissingBean` on a class only skips one default bean"

Incorrect if the class provides other beans as well: when the class-level condition fails to match, the impacted scope is broader. Place the missing-bean condition on the exact method of the bean that should back off when other beans must stay active.

### Mistake 5: "Declaring `@ConditionalOnClass` on a method is always safe enough for optional SDKs"

Do not rely on this when the method's return type is an optional class. Extract it into a nested `@Configuration` with a class-level condition to avoid loading the method signature before the condition is evaluated.

### Mistake 6: "`@ConditionalOnClass` proves a bean of that type already exists"

Incorrect. It checks the classpath; to check for an existing bean definition/prerequisite bean, use `@ConditionalOnBean` aligned with processing order.

### Mistake 7: "A missing bean means the candidate was not discovered"

Incorrect. You need to check imports metadata, exclusions, class conditions, method conditions, and finally bean instantiation. A missing bean has multiple possible causes across different stages.

### Mistake 8: "Adding a property inside ApplicationRunner will automatically create a new bean"

No. Property conditions run during configuration evaluation, not as an event listener reacting to every `Environment` change. To alter the bean graph via startup conditions, configure properly before refresh and build the context with that configuration.

### Mistake 9: "Every `@Bean` return type is inspected identically"

Not quite. Bean conditions only use type information Spring knows at evaluation time. Declaring clear, accurate return types (including generics where relevant) keeps conditions stable. Do not hide a type behind `Object` and expect interface-based missing-bean checks to always be accurate.

### Mistake 10: "Conditional annotations combine with OR"

With multiple conditions at the same level, all must generally match. If a method has both a property condition and a missing-bean condition, both must allow registration. Conditional structures with true OR logic must be designed explicitly.

## 11. How to Decide Where to Place a Condition

When building an auto-configuration, apply this sequence:

**Step 1 — List all beans.** Which beans are needed in every case, which only when a feature is enabled, and which can be replaced by the user?

**Step 2 — Find shared premises.** Only elevate a condition to the outer class if **every bean in the class** genuinely depends on that premise.

**Step 3 — Isolate individual options.** Beans integrating reporting, HTTP, observability, or optional adapters should have method conditions or a separate nested configuration.

**Step 4 — Place back-off precisely.** `@ConditionalOnMissingBean` on the default bean is usually better than on the entire class, unless the whole configuration genuinely must turn off when that bean exists.

**Step 5 — Handle optional classes safely.** If a bean method's signature mentions a class that may be absent at runtime, isolate the method in a `static nested @Configuration` with a classpath condition.

**Step 6 — Test the matrix.** Have tests for both true and false class conditions, and with the class condition true, for each method condition true and false. Test user-supplied beans separately.

**Step 7 — Debug by scope.** Look up the exact component in the condition report: the class or `Class#method`. A "negative match" on a method does not mean the outer class was rejected.

A simple decision question: **"If this condition does not match, how many beans do I actually want to skip?"** The answer "all of them" points to class level; "one bean" points to method level; "a group" suggests nested `@Configuration`.

## 12. Self-Check Questions

**1. A class has three `@Bean` methods and the class-level condition is false. How many beans from that branch are registered?** Zero beans are registered through that class branch.

**2. Class condition is true, method B is false, method A has no condition of its own. Is method A skipped?** Not just because B is false; A can still be registered if no other condition blocks it.

**3. Method property=true but class property=false — does the bean exist?** Not through that branch; the method cannot get past the class gate.

**4. The application already supplies a `Notifier`, and `defaultNotifier()` has `@ConditionalOnMissingBean`. What happens?** The default notifier is skipped and the application's `Notifier` bean remains; other methods are not automatically skipped.

**5. Why not put every `@ConditionalOnProperty` on the outer class?** It can exclude beans that do not depend on that property, causing unrelated features to disappear.

**6. What does `@ConditionalOnClass` check?** The classpath, not whether a bean of that type already exists in the context.

**7. When a `@Bean` return type is an optional SDK class, how should it be guarded?** Use a nested configuration with a class-level condition to isolate the method signature.

**8. How does `@ConditionalOnProperty` behave by default without `havingValue`?** It matches when the key is present and its value is not `false`; with `matchIfMissing=false`, an absent key does not match.

**9. Why does a condition report need to be read for both the class and `Class#method`?** Because the class may be selected while an individual method is still excluded by its own condition.

**10. Are conditions evaluated before or after `ApplicationRunner`?** During configuration/bean-definition processing at context initialization, typically before runners; runners do not trigger condition re-evaluation.

## Official Documentation Sources

- Spring Boot — Creating Your Own Auto-configuration (Class Conditions, Bean Conditions, Property Conditions): https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — `@ConditionalOnClass` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot — `@ConditionalOnProperty` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot — Using Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Framework — `@Conditional` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Conditional.html

**Conclusion:** **class-level** conditions guard the scope of an entire configuration; **method-level** conditions guard the scope of a single bean definition. When combined, a bean is registered only if all relevant condition gates allow it. Choosing the right level helps auto-configuration back off where needed without disabling other beans.