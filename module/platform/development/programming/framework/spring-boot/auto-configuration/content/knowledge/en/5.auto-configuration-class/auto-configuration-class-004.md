# Conditions Placed on the Outer Class, Nested Class, and @Bean Method in Spring Boot Auto-Configuration

## 1. Why Does Condition Placement Matter?

Spring Boot does not merely ask "is the condition true?", it also asks **what scope the condition is guarding**. Placing the exact same `@ConditionalOnProperty` on an `@AutoConfiguration` class, a nested `@Configuration` class, or a `@Bean` method produces different outcomes.

This lesson focuses on three levels:

1. **Outer class:** the condition decides whether the entire auto-configuration is applied through the normal processing path. If it does not match, the beans provided by that configuration are not registered via that branch.
2. **Nested configuration class:** the condition guards only **one group of beans**. The rest of the outer class can still remain active.
3. **`@Bean` method:** the condition guards only **one bean definition**. Other methods in the same class can still be registered.

A structure with all three levels can be illustrated as follows:

~~~text
@AutoConfiguration
@ConditionalOnProperty("demo.auto=true")       ← outer class gate
└── MainAutoConfiguration
    ├── @Bean mainService()                     ← outer class bean
    │   └── @ConditionalOnMissingBean           ← mainService's own gate
    │
    └── @Configuration NestedMetricsConfig
        ├── @ConditionalOnProperty("demo.metrics=true")
        │                                        ← nested group gate
        ├── @Bean metricsService()              ← passing the group gate is enough
        └── @Bean detailsService()
            └── @ConditionalOnProperty("demo.details=true")
                                                 ← single-method gate
~~~

Along the normal configuration processing path, to obtain `detailsService`, **all three**—the outer condition, the nested group condition, and the method's own condition—must match. Conversely, obtaining `mainService` does not require `demo.metrics=true`, because this bean sits outside the metrics group.

**Goal:** understand the effective scope, evaluation milestones, and common pitfalls when designing auto-configurations; run a Java 17+ example yourself to observe outcomes changing with properties; know how to diagnose which exact class or bean failed to match.

## 2. From @Conditional to Bean Definition

In Spring Framework, `@Conditional` attaches one or more `Condition`s to a configuration component. Spring Boot provides convenient conditions, for example:

- `@ConditionalOnClass`, `@ConditionalOnMissingClass`: based on the presence of a class on the classpath.
- `@ConditionalOnProperty`: based on properties in the `Environment`.
- `@ConditionalOnBean`, `@ConditionalOnMissingBean`: based on bean definitions/beans observable at evaluation time.
- `@ConditionalOnWebApplication`: based on the web application environment.
- `@ConditionalOnResource`: based on the presence of a resource.

**Conditions are not a mechanism for controlling a bean instance after the bean is already running.** During configuration processing, they decide whether to admit the corresponding configuration or bean definition into the context. When a property changes after conditions have been evaluated, Spring Boot generally **does not re-evaluate all conditions to add or remove beans**.

Distinctions to keep in mind:

| Concept | Meaning |
| --- | --- |
| Auto-configuration is **discovered** | The class name is known to Spring Boot via imports resources on the classpath. |
| Auto-configuration is **selected/imported** | Considered after filtering, exclusions, and ordering mechanisms. |
| Condition **matches** | The class or method is permitted to participate according to its condition. |
| Bean definition is **registered** | The container knows how to create a bean, still subject to dependencies/scope/lazy. |
| Bean is **instantiated** | The actual instance is created and undergoes lifecycle; can still fail for other reasons. |

Do not use "condition passed" as proof that a bean was definitely instantiated. Nor use "bean absent" to claim the auto-configuration was never discovered.

### Evaluation Order and Combined Conditions

Along the normal processing path, conditions on enclosing and child components combine in an **all-must-permit** sense: if the outer class is rejected, the nested group and beans on that path are not registered. If the outer class is accepted but the nested group is rejected, beans outside the group can still be created.

A condition on a class can be evaluated at a different phase from a condition on a method. Spring Framework distinguishes `ConfigurationCondition.ConfigurationPhase.PARSE_CONFIGURATION` and `REGISTER_BEAN`; each implementation has its own phase. Therefore, the "three gates" diagram is a mental model of **scope**, not a guarantee that all conditions execute sequentially on one line of code.

An advanced note: `@Conditional` on an outer class is not "Java inheritance" applied to every nested class regardless of how it is loaded. If a nested `@Configuration` class is **registered separately** via component scan or an independent `@Import`, it can be processed using its own conditions; the outer class's conditions do not necessarily apply as they do when Spring traverses the outer class to parse nested classes. For clean architecture, do not simultaneously register a nested class through an independent path if you want it to always depend on the outer gate.

## 3. Placing @Conditional on the Outer @AutoConfiguration Class

Example:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo",
        name = "auto",
        havingValue = "true",
        matchIfMissing = true
)
public class DemoAutoConfiguration {
    // @Bean methods and nested @Configuration classes.
}
~~~

This is an **illustrative snippet**, without a package, beans, or standalone runnable program. It expresses:

- `demo.auto=true`: outer condition matches.
- `demo.auto=false`: does not match.
- Key `demo.auto` absent: **still matches** because `matchIfMissing=true`.
- Value `demo.auto=other`: does not match when `havingValue="true"`.

When the outer condition does not match, beans defined through this class are not registered **along the normal processing branch of that configuration class**. This fits when an auto-configuration has a **shared prerequisite** for the entire feature, such as a property disabling the whole feature, application type, or a required dependency.

However, do not push every minor condition up to the outer class. If only an auxiliary feature needs an optional library, putting `@ConditionalOnClass` on the entire outer class can inadvertently disable core beans **that do not depend on that library**.

**Criterion for choosing the outer class level:** if the condition fails to match, **every bean provided by this configuration should be absent**. If only a subset should be absent, use a nested class or a `@Bean` method.

### Where Should @ConditionalOnClass Be Placed?

`@ConditionalOnClass(SomeApi.class)` on a `@Configuration` class is a common pattern. Boot can read annotation metadata from bytecode (ASM) without necessarily loading the optional class eagerly. However, checking a class on a `@Bean` method whose **return type is an optional class** can cause issues before the condition is evaluated because the JVM must resolve the method signature.

When an integration depends on a class type that may not exist on the runtime classpath, **isolate the integration inside a nested `@Configuration` class annotated with `@ConditionalOnClass`**, rather than putting the condition solely on a method returning the optional class. Details are in section 5.

## 4. Placing @Conditional on a Nested @Configuration Class

A nested class groups beans sharing a single condition:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "demo",
        name = "metrics",
        havingValue = "true"
)
static class MetricsConfiguration {

    @Bean
    MetricsService metricsService() {
        return new MetricsService();
    }

    @Bean
    DetailsService detailsService() {
        return new DetailsService();
    }
}
~~~

This is an **illustrative snippet inside an outer configuration class**, not standalone compilable because imports and `MetricsService`/`DetailsService` declarations are missing. If the group condition `demo.metrics=true` does not match, both bean methods inside this group are skipped along that configuration branch; other beans on the outer class need not be skipped.

In auto-configurations, a **`static class`** annotated with `@Configuration(proxyBeanMethods = false)` is commonly used. `static` avoids an unnecessary binding to an outer class instance; `proxyBeanMethods=false` fits when beans are wired via dependency injection rather than direct cross-calling of `@Bean` methods as a proxied factory.

### Why Are Nested Groups Useful?

Suppose a library has a core processor that does not need a web library, yet adds an HTTP endpoint when the application has the Servlet API. If `@ConditionalOnClass` is placed on the outer class, the core part also disappears in CLI runs. Split them:

~~~java
@AutoConfiguration
public class SharedAutoConfiguration {

    @Bean
    CoreService coreService() {
        return new CoreService();
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "jakarta.servlet.Servlet")
    static class ServletOnlyConfiguration {

        // Servlet integration @Bean methods are declared here.
    }
}
~~~

This snippet is **structural, not a standalone runnable example**; `CoreService` and servlet beans are illustrative types. Meaning: the core bean can exist in a CLI or non-servlet app, while the servlet integration group is evaluated only when the required class is available.

Multiple independent nested classes can reside inside one `@AutoConfiguration`, each guarding a different integration branch. They do not have to share a common outer condition if the library has no single global prerequisite.

### Safety When Optional Classes Are Absent from the Classpath

Spring Boot recommends this exact isolation pattern:

~~~java
@AutoConfiguration
public class ExternalIntegrationAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.Client")
    static class VendorClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        com.vendor.sdk.Client client() {
            return new com.vendor.sdk.Client();
        }
    }
}
~~~

This is an **architectural illustration**, which will not compile unless the SDK dependency is added at compile time with a matching constructor. When packaging a library, the SDK may be a **compile dependency** to build the integration class yet **not required at runtime** in every application. Putting `@ConditionalOnClass` on an isolated configuration class lets Spring decide whether to parse the bean group containing optional type signatures. Do not place the annotation solely on `client()` and assume it protects against all class-loading errors.

If you need a composed annotation using `@ConditionalOnClass` as a meta-annotation, the Spring Boot documentation notes that you should use the `name` attribute instead of `value` referencing the class directly, because bytecode metadata reading differs from placing the annotation directly.

## 5. Placing @Conditional on a @Bean Method

A condition on a method controls **only the bean declared by that method**:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "demo",
        name = "details",
        havingValue = "true"
)
DetailsService detailsService() {
    return new DetailsService();
}
~~~

This is a snippet inside a configuration class, not a complete program. If `demo.details=false`, the `detailsService` bean is skipped, while `@Bean` methods without that condition can still be registered.

Another important pattern for auto-configuration is:

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService defaultGreetingService() {
    return () -> "AUTO";
}
~~~

This pattern assumes a `GreetingService` interface is declared. When the application already has a matching `GreetingService` bean, the default bean **backs off**; other beans in the same auto-configuration are not necessarily turned off. This is the right pattern when **you only want to allow overriding one default bean**.

### Placing @ConditionalOnMissingBean on the Class vs. Method?

| Placement | Meaning |
| --- | --- |
| On the `@AutoConfiguration` / `@Configuration` class | If it does not match, skips registering that configuration class and beans on its processing branch. |
| On a nested `@Configuration` class | If it does not match, skips the entire **bean group** belonging to that nested class. |
| On a single `@Bean` method | If it does not match, skips only **that method's bean definition**. |

Suppose a configuration contains three beans, yet only one bean needs back-off: if you put `@ConditionalOnMissingBean(MyService.class)` on the **outer class**, when the application defines `MyService`, the **entire configuration** is rejected, potentially dropping unrelated utility beans. Placing the condition on the exact method providing `MyService` avoids unintended side effects.

### Why Does Bean Definition Registration Order Matter?

`@ConditionalOnMissingBean` and `@ConditionalOnBean` inspect bean definitions/beans already processed at the time the condition is evaluated. They do not look ahead at every bean that might appear in the future. Spring Boot uses deferred auto-configuration importing to ensure user-supplied configurations are processed before auto-configuration, so bean conditions in auto-configuration can back off properly.

A note on types: bean-based conditions resolve only the type information Spring knows at evaluation time. With `@Bean`, declare a sufficiently specific and appropriate return type; do not needlessly use `Object`, which loses type information. In the hands-on example, we explicitly declare the interface type when we want the condition to check that interface.

### Multiple Conditions on the Same Level

If a bean has two conditions:

~~~java
@Bean
@ConditionalOnProperty(prefix = "demo", name = "logging", havingValue = "true")
@ConditionalOnMissingBean(AuditLogger.class)
AuditLogger auditLogger() {
    return new DefaultAuditLogger();
}
~~~

This is an illustrative snippet; `AuditLogger` and `DefaultAuditLogger` must be defined. The bean is registered only when **the property matches AND no matching logger bean exists**. It is not an "either one matches" condition. If you need complex OR logic, organize configuration groups or write an appropriate custom `Condition` rather than assuming multiple annotations mean OR.

## 6. Three-Tier Summary Table and How to Choose Placement

| Design question | Option to consider | Why |
| --- | --- | --- |
| One property disables the **entire** feature | Condition on the outer `@AutoConfiguration` class | Maintains a single master gate. |
| An integration depends on an optional SDK | Condition on a nested `@Configuration` class | Keeps core beans when SDK is missing and isolates class loading. |
| Only one bean should be replaceable by the app | `@ConditionalOnMissingBean` on the `@Bean` method | Only that default bean backs off. |
| A group of beans activates only when `feature.metrics=true` | Condition on the nested class containing the group | Avoids repeating annotations on every method. |
| Inside the metrics group, only details needs an extra property | Condition solely on `detailsService()` | Avoids disabling the whole metrics group. |
| One bean requires two independent conditions | Combine both annotations at the appropriate level | Both must match at that level. |

**Rule of thumb:** lift a condition to the highest level at which **every bean inside that scope requires that condition**. If you put it too high, you exclude extra beans; if you put it too low, you duplicate conditions and risk omissions or loading optional classes.

## 7. Runnable Example: Spring Boot 3.5.0 and Java 17+

We will write an auto-configuration registered via `AutoConfiguration.imports` that has all three tiers:

- **Outer** condition: `demo.auto=true` or property absent (enabled by default).
- **Nested class** condition: `demo.metrics=true` enables the metrics group.
- **Method inside nested class** condition: `demo.details=true` enables details specifically; because it sits in the metrics group, `demo.metrics=true` is still required.
- **Method on outer class** condition: `@ConditionalOnMissingBean(MessageService.class)` causes the default bean to back off if the application supplies `MessageService`.

The Java 17+ project requires no database, web server, or SDK beyond the Spring Boot starter. The demo pins **Spring Boot 3.5.0**, a specific version to avoid ambiguous dependence on latest APIs.

### 7.1. Structure

~~~text
condition-scopes-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── api/
    │   │   ├── MessageService.java
    │   │   ├── MetricsService.java
    │   │   └── DetailsService.java
    │   ├── app/DemoApplication.java
    │   └── autoconfig/DemoAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

`DemoApplication` resides in package `com.example.app`. `DemoAutoConfiguration` resides in `com.example.autoconfig`, **outside the application's default component scan area**. The auto-configuration class is discovered by the application solely via imports metadata; this layout avoids confusing results caused by component scan.

### 7.2. pom.xml

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
    <artifactId>condition-scopes-demo</artifactId>
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

### 7.3. Three Small Interfaces

`src/main/java/com/example/api/MessageService.java`:

~~~java
package com.example.api;

public interface MessageService {
    String message();
}
~~~

`src/main/java/com/example/api/MetricsService.java`:

~~~java
package com.example.api;

public interface MetricsService {
    String metric();
}
~~~

`src/main/java/com/example/api/DetailsService.java`:

~~~java
package com.example.api;

public interface DetailsService {
    String detail();
}
~~~

Each interface acts as a distinct bean type. They merely declare contracts; an interface's presence on the classpath **does not imply a bean already exists**.

### 7.4. DemoAutoConfiguration.java

`src/main/java/com/example/autoconfig/DemoAutoConfiguration.java`:

~~~java
package com.example.autoconfig;

import com.example.api.DetailsService;
import com.example.api.MessageService;
import com.example.api.MetricsService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo",
        name = "auto",
        havingValue = "true",
        matchIfMissing = true
)
public class DemoAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageService.class)
    MessageService defaultMessageService() {
        return () -> "AUTO";
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "demo",
            name = "metrics",
            havingValue = "true"
    )
    static class MetricsConfiguration {

        @Bean
        MetricsService metricsService() {
            return () -> "METRICS";
        }

        @Bean
        @ConditionalOnProperty(
                prefix = "demo",
                name = "details",
                havingValue = "true"
        )
        DetailsService detailsService() {
            return () -> "DETAILS";
        }
    }
}
~~~

Identify each level:

- `@ConditionalOnProperty(demo.auto)` on the outer class: affects **every bean** of this auto-configuration along this path.
- `@ConditionalOnMissingBean(MessageService.class)` on `defaultMessageService()`: skips only **the default bean**, without disabling the metrics group.
- `@ConditionalOnProperty(demo.metrics)` on `MetricsConfiguration`: controls **both `metricsService()` and `detailsService()`**.
- `@ConditionalOnProperty(demo.details)` on `detailsService()`: controls only **the details bean**, yet cannot pass the group gate if `demo.metrics=false`.

The nested class is `static` and annotated with `@Configuration(proxyBeanMethods = false)`, the right pattern for grouping conditions. All interface classes belong to the project and exist on the classpath, so the example does not need optional-dependency handling.

### 7.5. AutoConfiguration.imports Metadata

The file at the exact path `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` contains one line:

~~~text
com.example.autoconfig.DemoAutoConfiguration
~~~

**List only the outer auto-configuration class**; do not list `DemoAutoConfiguration$MetricsConfiguration` as an independent candidate. Spring processes the nested class through the outer configuration. If you deliberately declare the nested class as a separate auto-configuration or let component scan pick it up, the outer condition's scope will no longer match the three-tier model studied here.

### 7.6. DemoApplication.java

`src/main/java/com/example/app/DemoApplication.java`:

~~~java
package com.example.app;

import com.example.api.DetailsService;
import com.example.api.MessageService;
import com.example.api.MetricsService;
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
            prefix = "demo",
            name = "custom",
            havingValue = "true"
    )
    MessageService userMessageService() {
        return () -> "CUSTOM";
    }

    @Bean
    ApplicationRunner report(
            ObjectProvider<MessageService> messages,
            ObjectProvider<MetricsService> metrics,
            ObjectProvider<DetailsService> details) {
        return args -> {
            MessageService msg = messages.getIfAvailable();
            MetricsService met = metrics.getIfAvailable();
            DetailsService det = details.getIfAvailable();

            System.out.println("message="
                    + (msg == null ? "ABSENT" : msg.message()));
            System.out.println("metrics="
                    + (met == null ? "ABSENT" : met.metric()));
            System.out.println("details="
                    + (det == null ? "ABSENT" : det.detail()));
        };
    }
}
~~~

`userMessageService()` is a bean defined by **the application**, active when `demo.custom=true`. Because auto-configuration is processed after application bean definitions, `@ConditionalOnMissingBean` on the default bean sees the `MessageService` bean and backs off. `ObjectProvider` allows printing `ABSENT` without a required-injection failure when a type has no bean.

The cases in this lesson have at most one bean per interface. If you manually add two beans of the same type, `getIfAvailable()` can fail due to non-uniqueness; that is a separate DI topic, not a property of outer/nested/bean conditions.

### 7.7. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.main.banner-mode=off
logging.level.root=ERROR
~~~

Do not place `demo.auto`, `demo.metrics`, `demo.details`, or `demo.custom` in the file. These keys are supplied on the command line so each run toggles only the desired gates. Turning down logging makes it easier to separate the example's stdout from startup logs (messages from the JVM or environment may still appear).

### 7.8. Build and Run

Install JDK 17+ and Maven, navigate to `condition-scopes-demo`, and run:

~~~bash
mvn -q -DskipTests package
java -jar target/condition-scopes-demo-1.0.0.jar
~~~

Three lines printed by the program:

~~~text
message=AUTO
metrics=ABSENT
details=ABSENT
~~~

Explanation: `demo.auto` is absent, yet the outer condition has `matchIfMissing=true`; no user-declared `MessageService` bean exists, so `defaultMessageService` is created. `demo.metrics` is absent, so the entire nested group is skipped.

**Enable the metrics group without enabling details:**

~~~bash
java -jar target/condition-scopes-demo-1.0.0.jar --demo.metrics=true
~~~

~~~text
message=AUTO
metrics=METRICS
details=ABSENT
~~~

The nested class is accepted, but `detailsService()` is skipped because `demo.details` is absent. The bean outside the group remains present.

**Open all three gates to create details:**

~~~bash
java -jar target/condition-scopes-demo-1.0.0.jar --demo.metrics=true --demo.details=true
~~~

~~~text
message=AUTO
metrics=METRICS
details=DETAILS
~~~

This is the case where both the nested group and the method pass their conditions.

**Enable details without enabling the group:**

~~~bash
java -jar target/condition-scopes-demo-1.0.0.jar --demo.details=true
~~~

~~~text
message=AUTO
metrics=ABSENT
details=ABSENT
~~~

This is the critical experiment: `demo.details=true` **cannot create `detailsService`** if `MetricsConfiguration` is skipped. A method-level gate cannot bypass a closed group-level gate.

**Disable the entire auto-configuration:**

~~~bash
java -jar target/condition-scopes-demo-1.0.0.jar --demo.auto=false --demo.metrics=true --demo.details=true
~~~

~~~text
message=ABSENT
metrics=ABSENT
details=ABSENT
~~~

The outer class condition does not match; no default beans from this auto-configuration exist. Even though both properties for the nested class and method are `true`, they cannot "revive" an excluded configuration branch.

**Replace only MessageService with an application bean:**

~~~bash
java -jar target/condition-scopes-demo-1.0.0.jar --demo.custom=true --demo.metrics=true --demo.details=true
~~~

~~~text
message=CUSTOM
metrics=METRICS
details=DETAILS
~~~

`defaultMessageService()` is skipped by `@ConditionalOnMissingBean` because a user bean already exists; however, the metrics group is still registered. This clearly illustrates why a back-off condition for **one bean** should not accidentally be placed on **the entire outer class**.

**Application still keeps its custom bean when the outer class is disabled:**

~~~bash
java -jar target/condition-scopes-demo-1.0.0.jar --demo.auto=false --demo.custom=true --demo.metrics=true --demo.details=true
~~~

~~~text
message=CUSTOM
metrics=ABSENT
details=ABSENT
~~~

The `demo.auto=false` property disables only the **sample auto-configuration**, not `@Bean userMessageService()` declared by the application in another configuration class.

### 7.9. Result Matrix

| demo.auto | demo.custom | demo.metrics | demo.details | message | metrics | details |
| --- | --- | --- | --- | --- | --- | --- |
| absent | absent | absent | absent | AUTO | ABSENT | ABSENT |
| absent | absent | true | absent | AUTO | METRICS | ABSENT |
| absent | absent | true | true | AUTO | METRICS | DETAILS |
| absent | absent | absent | true | AUTO | ABSENT | ABSENT |
| false | absent | true | true | ABSENT | ABSENT | ABSENT |
| absent | true | true | true | CUSTOM | METRICS | DETAILS |
| false | true | true | true | CUSTOM | ABSENT | ABSENT |

The printed strings above are **stdout generated by the application**, excluding Spring Boot logs. Understand `AUTO`/`METRICS`/`DETAILS` as return values from lambdas in the sample code, not built-in Boot keywords or modes.

## 8. Reading the Condition Evaluation Report to Verify Each Tier

When a bean does not appear, use the condition report instead of guessing. Re-run the JAR, enable debug, and raise the log level so the report can be displayed:

~~~bash
java -jar target/condition-scopes-demo-1.0.0.jar --demo.metrics=true --debug --logging.level.root=INFO
~~~

Look for the class names:

- `DemoAutoConfiguration`: did the outer class condition match?
- `DemoAutoConfiguration.MetricsConfiguration` (exact formatting may vary): did the nested group match?
- `DemoAutoConfiguration.MetricsConfiguration#detailsService`: did the details bean's own property match?
- `DemoAutoConfiguration#defaultMessageService`: did `@ConditionalOnMissingBean` find an application-supplied `MessageService` bean?

Log names and structure can differ across versions; read the **reasons** under positive/negative matches rather than relying on character-for-character log text. The condition report is not a list of every bean successfully instantiated.

If using Actuator, the `/actuator/conditions` endpoint can expose condition information once dependencies, exposure, and security are configured. Do not assume this endpoint is already enabled or safe to expose publicly; avoid leaking sensitive properties while debugging.

### Quick Checks for Specific Cases

**Outer class shows negative match:** first check `demo.auto` in the Environment and overriding sources. Do not spend time debugging inner bean methods when the outer class has already been rejected.

**Outer class positive, metrics group negative:** inspect `demo.metrics`; do not tweak `demo.details` because the group itself has not been applied.

**Metrics group positive, `detailsService` negative:** check `demo.details` and `havingValue` on the details method.

**`MessageService` CUSTOM present, default absent:** check `@ConditionalOnMissingBean`; this may be **proper back-off** rather than a bug.

**Entire auto-configuration missing from report:** check `AutoConfiguration.imports` metadata in the JAR, exclusions, early filters/conditions, classpath, and the active context; absence from the report **does not by itself prove** a single cause.

## 9. Common Mistakes When Placing Conditions at the Wrong Level

### 9.1. Placing a Group Condition on the Outer Class

Wrong scope:

~~~java
@AutoConfiguration
@ConditionalOnProperty(prefix = "demo", name = "metrics", havingValue = "true")
public class MyAutoConfiguration {
    // Both coreService and metricsService are excluded if demo.metrics=false.
}
~~~

If `coreService` must still exist when metrics is disabled, this design is wrong. Fix: guard only a nested `MetricsConfiguration` or metrics bean; keep core outside the group condition.

### 9.2. Placing @ConditionalOnMissingBean on the Outer Class Just to Replace One Bean

If the outer class also provides `HealthMarker` and `EventPublisher`, when the application declares a `MessageService` bean, the outer condition causes every bean in the auto-configuration to be skipped. Place the condition only on `defaultMessageService()` if the goal is replacing only the message service.

### 9.3. Putting @ConditionalOnClass on a @Bean with an Optional Return Type

This is a trap when the return type is absent at runtime. The annotation may fail to guard against the JVM processing the method's signature. Place the condition on an **isolated nested `@Configuration` class** so Spring can evaluate class presence before processing methods whose signatures depend on that type.

### 9.4. Assuming a Nested Class Always Inherits Outer Conditions Automatically

Along the processing path through the outer config, the outer condition blocks the whole branch; however, if you **scan or directly import** the nested class via another route, conditions on the outer class are not necessarily applied. Keep auto-configuration outside component scan and do not publish nested classes as standalone candidates if you want to preserve the "three gates" model.

### 9.5. Confusing @Conditional with Runtime Logic

A condition filters out bean definitions while the context is starting; it is not an `if` re-evaluated on every method call. Changing a property after the application is ready usually does not automatically add or remove earlier bean definitions. If you want runtime behavior to change dynamically, design a service that reads dynamic configuration or uses an appropriate refresh mechanism instead of relying on auto-configuration conditions.

### 9.6. Confusing "Simultaneous Conditions" with OR

On the same bean, two condition annotations normally must **both match**. Likewise, if outer, nested, and bean method each carry a condition, **all relevant gates must be open**. Do not expect a matching method condition to bypass a failing nested-class condition.

### 9.7. Using Too Generic a Return Type Interface and Misinterpreting Bean Conditions

Bean conditions read the type information Spring knows at evaluation time; declaring `@Bean Object service()` can make specific type checks less reliable than expected. Declare a return type that is specific and clear. `@ConditionalOnMissingBean` with an explicit type is a good choice when you want a default bean replaceable by an implementation of the same contract.

### 9.8. Confusing a Class Condition with a Dependency Bean Already Existing

`@ConditionalOnClass(SomeType.class)` only verifies that the class exists on the classpath; it does not prove a `SomeType` bean exists in the context. To ensure a prerequisite bean exists, use an appropriate `@ConditionalOnBean` and understand bean definition order. With multi-level application contexts, also consider the `search` scope.

### 9.9. Putting Bean Conditions in Application Config Without Order Guarantees

When a missing-bean condition runs too early, it may not yet see a bean intended to be registered later. The Boot documentation recommends using `@ConditionalOnBean`/`@ConditionalOnMissingBean` primarily in auto-configurations because they are processed after user bean definitions.

### 9.10. Misinterpreting Results Due to Test Slices or Classpath

In a test slice, not all auto-configurations are loaded as in a full `@SpringBootTest`. If a bean is absent, verify the context type and which auto-configurations are imported. When comparing condition reports between two tests, ensure they run in equivalent contexts.

## 10. Process for Designing Condition Scope Properly

When building a new starter or auto-configuration:

1. **List the beans to provide**, separating core and optional groups. For each bean, note dependencies on classpath, properties, profiles, or other beans.
2. **Choose conditions shared by the entire class.** Place on the outer class only if failing to match means none of the configuration's beans should exist.
3. **Separate optional groups using static nested `@Configuration`.** Put `@ConditionalOnClass`, `@ConditionalOnProperty`, or web conditions on the nested class to group beans sharing the same prerequisite.
4. **Place specific conditions on individual `@Bean` methods.** Use `@ConditionalOnMissingBean` to let users replace a default bean; use a property condition to toggle a single bean.
5. **Take care when optional types are absent.** Put every method whose signature references an optional SDK inside a configuration class guarded by a class condition; do not guard only individual methods.
6. **Ensure Boot discovers the outer class properly.** Register the FQCN in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` and prevent accidental component scanning of the auto-config package.
7. **Create a test matrix.** Test outer ON/OFF, group ON/OFF, method ON/OFF, with/without custom bean. Also test the combination `child=true` with `group=false` to verify hierarchy.
8. **Inspect the report and bean definitions.** When results differ from expectations, locate the exact blocked tier before editing annotations.

A "decision" table useful during review:

| Review comment on requirement | Suggested change |
| --- | --- |
| "Disabling metrics also disables message service, unexpectedly" | Move `@ConditionalOnProperty(metrics)` from outer down to nested metrics config. |
| "Application defines a message bean and loses metrics too" | Move `@ConditionalOnMissingBean(MessageService.class)` from outer down to the default bean. |
| "details is still absent even though property details=true" | Check both outer `demo.auto` and nested `demo.metrics` first. |
| "Missing optional SDK causes app class-loading failure" | Isolate SDK signatures in a nested config guarded with `@ConditionalOnClass`. |
| "Log does not show `@Bean` details" | Use the condition report and check the method name specifically; don't inspect only the outer class. |

## 11. Self-Assessment Questions

**1. The outer condition does not match, but an inner `@Bean` condition matches—is the bean registered?** No, along the configuration processing path through the outer class; the method cannot get past the outer gate.

**2. The condition on the nested config does not match—does a bean placed directly on the outer class still exist?** It can, provided the outer class and that bean's own conditions match.

**3. Why should static nested `@Configuration` be used for an optional SDK?** To isolate configuration depending on classes that may be absent at runtime and avoid the risk of the JVM processing method signatures too early.

**4. Does `@ConditionalOnMissingBean` placed on a method affect all other beans in the same class?** No; it guards that method's bean definition.

**5. What if `demo.details=true` while `demo.metrics=false`?** The details bean inside the metrics group does not exist because the nested condition does not match.

**6. What if `demo.auto=false` and `demo.custom=true`?** The custom bean declared by the application is still present; the sample auto-configuration's beans are excluded.

**7. What if the application has a custom `MessageService` and metrics is enabled?** The default `MessageService` bean backs off, while `MetricsService` can still exist.

**8. Should `@ConditionalOnClass` be placed on a `@Bean` returning an optional SDK class to guarantee class-loading safety?** Do not rely solely on that; move the method into a nested configuration class carrying the class condition.

**9. Are conditions on a nested class automatically blocked by the outer class if the nested class is `@Import`ed directly from elsewhere?** You cannot assume that; an independent registration path can cause outer conditions not to be applied.

**10. To find out why a bean was not registered, what should you inspect?** Verify imports/exclusions, conditions on the outer class, nested group, and bean method, along with the Condition Evaluation Report and existing bean definitions.

## Official Documentation

- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot 3.5 — `ConditionalOnClass` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Framework — `@Conditional` and Composing Java Configuration: https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html

**Conclusion:** where `@Conditional` is placed determines **which scope of configuration is skipped**. Use conditions on the outer class for global prerequisites, on nested `@Configuration` for bean groups and optional dependencies, and on individual `@Bean` methods for bean-specific decisions such as back-off. Every condition along the path from outer to bean must permit it; this yields auto-configurations that are predictable, avoid over-disabling, and are easy to diagnose.