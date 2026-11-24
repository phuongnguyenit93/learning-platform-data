# Configuration Errors Shifted to First Use Under Lazy Initialization in Spring Boot

## 1. The Problem: Startup Succeeds Yet a Feature Breaks on the First Call

In Spring Boot, **lazy initialization** lets Spring defer creating a bean until a component actually requests it. This mechanism can reduce work at startup, but carries an important consequence: **configuration errors normally caught during bean creation may no longer fail the application at startup; they only surface on first use**.

For example, a bean requires the mandatory property **demo.remote.url** to be constructed. If the bean is created eagerly during **ApplicationContext.refresh()**, a missing property fails startup. If the bean is created lazily and no other component has requested it yet, the context can finish refreshing and Spring Boot can publish **ApplicationReadyEvent**, yet the first call via **getBean()** or a lazy dependency hits an exception.

~~~text
EAGER (ordinary singleton)
    |
    +-- refresh()
          +-- create RemoteClient
                +-- demo.remote.url missing
                      +-- BeanCreationException
                            +-- startup FAIL
                            +-- no ApplicationReadyEvent

LAZY (RemoteClient not yet requested by anything)
    |
    +-- refresh()
          +-- store BeanDefinition, RemoteClient not created yet
    +-- runners and ready event complete
          +-- startup looks successful
    +-- first request for RemoteClient
          +-- create bean
                +-- demo.remote.url missing
                      +-- BeanCreationException
                            +-- error surfaces at use time
~~~

**What must be understood correctly:** lazy initialization **does not fix misconfiguration**. It can only **change when an error is detected**. When an error surfaces late, the failure can directly impact user requests, message consumers, or background jobs instead of being caught at startup.

This lesson uses **Spring Boot 3.3.x / Spring Framework 6.1, Java 17+**, and focuses on identifying, reproducing, testing, monitoring, and proactively preventing deferred configuration errors.

## 2. How Do Eager and Lazy Initialization Differ?

### 2.1. Eager Singletons Are the Default

In Spring Framework, ordinary singleton beans are created by Spring during the completion phase of **refresh()**, unless a bean is configured as lazy or has a distinct lifecycle mechanism. During initialization, Spring must:

1. Identify the BeanDefinition and bean creation method.
2. Resolve constructor/factory method parameters and dependencies.
3. Instantiate the object.
4. Inject properties, apply bindings, and perform required setup steps.
5. Invoke BeanPostProcessors and initialization callbacks such as **@PostConstruct** if present.
6. Cache the created singleton so subsequent uses receive the same instance.

If a required property is missing in the factory method or a dependency cannot be resolved, an error can occur right inside the startup sequence and prevent the context from completing refresh.

### 2.2. Lazy Singletons Are Created Only On Demand

When a bean is marked lazy, its BeanDefinition still exists in the container, yet **the singleton instance is not instantiated solely because refresh reached the normal singleton creation phase**.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    @Lazy
    RemoteClient remoteClient(Environment environment) {
        String url =
                environment.getRequiredProperty("demo.remote.url");
        return new RemoteClient(url);
    }
}
~~~

This is a **snippet**, assuming the **RemoteClient** class and corresponding imports already exist. When the context refreshes while **no eager bean needs RemoteClient**, Spring can leave the bean uncreated. Only when a component calls:

~~~java
RemoteClient client = context.getBean(RemoteClient.class);
~~~

does Spring execute the factory method and read the required property. If **demo.remote.url** is absent, the error is detected **right on the bean request**, rather than during the eager singleton creation phase.

**Not every lazy bean is guaranteed to be created after startup.** If another eager singleton depends on it directly, Spring still must create the dependency when initializing the eager bean. Laziness only defers creation **when no actual demand exists yet**.

### 2.3. `@Lazy`, `@Lazy(false)`, and Application-Wide Lazy Initialization

There are two common configuration approaches:

- **@Lazy** on a component class or **@Bean** to apply at the bean level.
- Spring Boot property **spring.main.lazy-initialization=true** to enable lazy initialization broadly.

Boot configuration example:

~~~properties
spring.main.lazy-initialization=true
~~~

Or via CLI:

~~~bash
java -jar app.jar --spring.main.lazy-initialization=true
~~~

If you want a bean **initialized eagerly even when the application enables global lazy**, Spring Boot supports specifying:

~~~java
@Bean
@Lazy(false)
CriticalClient criticalClient(Environment environment) {
    return new CriticalClient(
            environment.getRequiredProperty("critical.endpoint"));
}
~~~

This snippet assumes **CriticalClient** and imports for **@Bean**, **@Lazy**, and **Environment**. The meaning is **do not defer** this critical bean: related configuration errors are caught during startup when that singleton is initialized under the normal lifecycle.

**Global lazy does not mean 100% of infrastructure beans are deferred.** Spring Boot has elements that must be created early for the system to boot; some beans may be created because processors, runners, lifecycle hooks, or other dependencies require them. Always inspect the **dependency graph** and actual Boot version instead of looking at a single property.

## 3. Which Kinds of Errors Can Be Deferred to First Use?

Not every error is deferred. Errors that require **creating an instance or using a dependency** to be detected are the typical candidates.

### 3.1. Missing Required Property When a Factory Method Runs

Example:

~~~java
@Bean
RemoteClient remoteClient(Environment environment) {
    String url =
            environment.getRequiredProperty("demo.remote.url");
    return new RemoteClient(url);
}
~~~

If **demo.remote.url** is missing, **getRequiredProperty(...)** throws an exception when the method runs. When the bean is lazy, running the method is deferred until the container first creates the bean.

The same can occur with **@Value** injection: a required placeholder that cannot be resolved during bean creation can cause **BeanCreationException** or a nested exception to surface at instantiation time.

### 3.2. Value Present Yet Malformed or Invalid

For example, a bean that parses a URL, port number, timeout, or enum upon creation:

~~~java
@Bean
RemoteClient remoteClient(Environment environment) {
    String endpoint =
            environment.getRequiredProperty("demo.remote.url");

    if (!endpoint.startsWith("https://")) {
        throw new IllegalArgumentException(
                "demo.remote.url must start with https://");
    }

    return new RemoteClient(endpoint);
}
~~~

If the bean is lazy and has not yet been requested, validation inside the factory method **has not run yet**. A setting like **demo.remote.url=http://insecure.example** may not raise an error until the bean is first requested.

**Distinction:** validation of **@ConfigurationProperties** can run when that bean is bound/initialized, yet the exact outcome depends on whether the bean is requested early and how Boot configures binding. Do not claim all configuration errors are deferred in the exact same manner.

### 3.3. Unsatisfied Dependency Checked Only Upon Bean Creation

A lazy bean whose constructor requires another bean:

~~~java
@Component
@Lazy
class ReportService {

    private final MissingFormatter formatter;

    ReportService(MissingFormatter formatter) {
        this.formatter = formatter;
    }
}
~~~

This snippet assumes **MissingFormatter** is a type for which the context has no registered bean. If `ReportService` is not created during refresh, the missing-dependency error may only appear when the container attempts to create `ReportService`.

However, if an eager bean injects `ReportService` directly, the dependency graph can force Spring to create `ReportService` right during refresh; the error returns to the startup phase.

### 3.4. Errors from `@PostConstruct` or Initialization Callbacks

Example:

~~~java
@Component
@Lazy
class RemoteIndex {

    @PostConstruct
    void initialize() {
        // If config validation or remote API calls happen here,
        // errors may surface when the bean is created for the first time.
    }
}
~~~

This snippet requires importing **@Component**, **@Lazy**, and **@PostConstruct**; with Spring Boot 3, use **jakarta.annotation.PostConstruct**, not the legacy **javax.annotation.PostConstruct**.

Callbacks like **@PostConstruct**, **InitializingBean.afterPropertiesSet()**, and custom init methods run during bean initialization. If the bean is lazy, those callbacks are also typically deferred along with bean creation.

**Warning:** do not perform I/O without timeouts inside `@PostConstruct` merely to fail fast. Separate pure configuration validation from network connectivity checks, and clearly decide what is a startup prerequisite versus what should be handled by runtime retries.

### 3.5. Errors on First Business Operation

Even after a bean has been created successfully, an error may only appear when a method first calls a backend: wrong DNS, expired access token, unreachable database, or an unsupported operation.

That is **not necessarily a lazy bean initialization error**. Distinguish:

- **Bean creation error:** occurs in the constructor, factory method, dependency injection, binding, or init callbacks.
- **Operational error:** occurs after the bean was created, when a method actually connects or performs work.

Enabling eager initialization can catch **bean creation errors earlier**, yet **does not guarantee** all operational errors are detected without intentional verification checks.

## 4. Errors That Can Still Appear During Startup Despite Lazy Mode

Lazy initialization **does not disable** `SpringApplication` preparing the Environment, parsing configuration, registering BeanDefinitions, processing auto-configuration, or refreshing the context.

Several failures can occur before lazy beans are ever instantiated:

| Error Category | Why Can It Still Fail at Startup? |
| --- | --- |
| Severely malformed **application.yaml** syntax | Config Data is parsed during Environment preparation |
| **spring.config.import** pointing to a missing required source | Errors can occur in the Config Data loading mechanism |
| Errors processing **@Configuration**, **@Import**, classpath, or BeanDefinition | Configuration registration/inspection steps happen during refresh |
| Duplicate bean names when overriding is disallowed | Registry conflicts are caught when registering definitions |
| Errors from **BeanDefinitionRegistryPostProcessor** or **BeanFactoryPostProcessor** | Processors must run during refresh before ordinary singletons |
| Errors from infrastructure beans needed by the web server or application context | Infrastructure must be initialized for the context to run |
| Error inside an **ApplicationRunner** invoked by Boot | Runners are still called before ApplicationReadyEvent |
| Lazy bean depended on by an eager bean | Dependency demand forces early lazy bean creation |

**Conclusion:** the property **spring.main.lazy-initialization=true** is not a way to bypass validation. It alters the creation policy for many beans while the rest of bootstrap still executes.

## 5. Runnable Java 17+ Example: Missing Configuration, Eager Fail vs. Lazy Fail

The following example demonstrates both failure timings using **the same source code** and **the same required property**. No real HTTP service is needed, because the goal is observing when the factory method executes.

### 5.1. Project Structure

Uses **Java 17+**, **Spring Boot 3.3.13**, and Maven 3.9+:

~~~text
lazy-config-demo/
  pom.xml
  src/main/java/com/example/lazy/LazyFailureApplication.java
~~~

**pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>lazy-config-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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

### 5.2. Complete Application Code

**src/main/java/com/example/lazy/LazyFailureApplication.java**:

~~~java
package com.example.lazy;

import org.springframework.beans.BeansException;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class LazyFailureApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(LazyFailureApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("STARTUP | run returned");

            try {
                RemoteClient client = context.getBean(RemoteClient.class);
                client.call();
                System.out.println("FIRST_USE | success");
            } catch (BeansException ex) {
                System.out.println("FIRST_USE | bean creation failed");
                // In a real app: log the error with secrets masked,
                // classify the cause, and decide fail-fast/retry.
            }
        }
    }

    @Bean
    RemoteClient remoteClient(Environment environment) {
        String url =
                environment.getRequiredProperty("demo.remote.url");

        if (!url.startsWith("https://")) {
            throw new IllegalArgumentException(
                    "demo.remote.url must start with https://");
        }

        System.out.println("BEAN | remoteClient created");
        return new RemoteClient(url);
    }

    public record RemoteClient(String url) {
        public void call() {
            // Example does not actually make a network call.
            System.out.println("USE | endpoint=" + url);
        }
    }
}
~~~

Explanation of choices:

- **@Bean remoteClient** has no **@Lazy**. Thus the default configuration is eager and the lazy variant is controlled via **spring.main.lazy-initialization=true**.
- **Environment.getRequiredProperty(...)** checks the property when the factory method is called. If missing, it throws an exception; Spring may wrap it in a **BeanCreationException**.
- The **https://** validation is placed right in the factory method to illustrate an invalid-value error.
- **RemoteClient.call()** only prints a string without network I/O. The example therefore cleanly isolates **bean creation** errors from network errors.
- **SpringApplication.run(...)** completes and prints **STARTUP** before **getBean(RemoteClient.class)** explicitly requests the bean.
- Catching **BeansException** in the example highlights the failure point without depending on a specific subclass exception name. **In production systems, do not catch exceptions and pretend the operation succeeded.**
- **WebApplicationType.NONE** and **try-with-resources** fit a short CLI lesson app. Do not close the context right after `run` in a web application that must continuously serve requests.

### 5.3. Build and Run Without the Required Property — Lazy Enabled

From the project directory:

~~~bash
mvn -q -DskipTests package
java -jar target/lazy-config-demo-1.0.0.jar --spring.main.lazy-initialization=true
~~~

**Lines printed by the program itself:**

~~~text
STARTUP | run returned
FIRST_USE | bean creation failed
~~~

Spring Boot may print additional framework logs. There is no **BEAN | remoteClient created** line because the factory method failed before completing validation.

In this run, **SpringApplication.run(...) returned the context successfully**. Only when `main` called **context.getBean(RemoteClient.class)** did Spring attempt to create the bean and discover **demo.remote.url** was missing. This is a configuration error shifted to first use.

### 5.4. Run Without the Property — Lazy Disabled

~~~bash
java -jar target/lazy-config-demo-1.0.0.jar --spring.main.lazy-initialization=false
~~~

In the default eager configuration, Spring attempts to create **remoteClient** when finishing refresh. The factory method throws because **demo.remote.url** is missing. **SpringApplication.run(...) does not return normally**, so you **do not see** the line:

~~~text
STARTUP | run returned
~~~

Startup reports an error via logs/stack trace and the application fails. **Do not assert an exact verbatim stack trace**: nested exception names and log formatting depend on framework versions and logger configuration. The critical timing relationship is **failure before STARTUP**.

### 5.5. Valid Property — Comparing Bean Creation Order

Run lazy:

~~~bash
java -jar target/lazy-config-demo-1.0.0.jar \
  --spring.main.lazy-initialization=true \
  --demo.remote.url=https://example.invalid
~~~

**Lines printed by the program:**

~~~text
STARTUP | run returned
BEAN | remoteClient created
USE | endpoint=https://example.invalid
FIRST_USE | success
~~~

The bean is created **after** `run` returns, right when `main` calls `getBean`.

Run eager:

~~~bash
java -jar target/lazy-config-demo-1.0.0.jar \
  --spring.main.lazy-initialization=false \
  --demo.remote.url=https://example.invalid
~~~

**Lines printed by the program:**

~~~text
BEAN | remoteClient created
STARTUP | run returned
USE | endpoint=https://example.invalid
FIRST_USE | success
~~~

In this run, the bean is created **during startup**. `main` simply looks up the already-existing instance.

### 5.6. Malformed Property — Not Only Missing Keys

Run:

~~~bash
java -jar target/lazy-config-demo-1.0.0.jar \
  --spring.main.lazy-initialization=true \
  --demo.remote.url=http://insecure.example
~~~

The context can finish startup, yet **context.getBean(RemoteClient.class)** runs the factory method, throws **IllegalArgumentException** from validation, and `main` prints:

~~~text
STARTUP | run returned
FIRST_USE | bean creation failed
~~~

When switched to eager, validation fails during refresh. Thus both **missing properties** and **invalid values** can be deferred to first bean creation.

## 6. Why Does a Lazy Bean Sometimes Still Fail Startup?

A lazy annotation or property is not a mechanism that blocks bean creation in every case. Spring always has to satisfy dependencies required by other beans.

### 6.1. An Eager Bean Directly Depends on a Lazy Bean

Suppose:

~~~java
@Component
class EagerReportRunner {

    private final LazyRemoteClient remoteClient;

    EagerReportRunner(LazyRemoteClient remoteClient) {
        this.remoteClient = remoteClient;
    }
}
~~~

and:

~~~java
@Component
@Lazy
class LazyRemoteClient {

    LazyRemoteClient(Environment environment) {
        environment.getRequiredProperty("demo.remote.url");
    }
}
~~~

These are snippets requiring **@Component**, **@Lazy**, and **Environment** imports. **EagerReportRunner** is an eager singleton by default. When creating `EagerReportRunner`, Spring must supply **LazyRemoteClient** to its constructor. Therefore the lazy target can be created right during startup to satisfy the dependency.

**Conclusion:** examine the **dependency graph**, not merely the lazy label on one class. If startup still fails despite adding `@Lazy`, an eager bean may be requesting it.

### 6.2. `@Lazy` at an Injection Point vs. a Lazy Target Bean Are Two Different Things

Spring supports **@Lazy at an injection point** to supply a proxy that defers resolving the actual dependency:

~~~java
@Component
class ReportCoordinator {

    private final RemoteClient remoteClient;

    ReportCoordinator(@Lazy RemoteClient remoteClient) {
        this.remoteClient = remoteClient;
    }

    void execute() {
        remoteClient.call();
    }
}
~~~

This is an **illustrative snippet**, requiring `RemoteClient` to be a type proxyable under Spring's configuration. If `RemoteClient` is a **record/final class** like in the complete Section 5 example, do not assume Spring can create a subclass proxy for it. When deferring a dependency on a final type or wanting explicit lookup timing, **ObjectProvider** is the better choice.

A lazy-injection proxy can defer dependency resolution until a method is invoked on the proxy, yet calling the method early can still trigger the error during startup.

### 6.3. `ObjectProvider` Defers Lookup, Not Fixes Configuration

Example:

~~~java
@Component
class ReportCoordinator {

    private final ObjectProvider<RemoteClient> clientProvider;

    ReportCoordinator(ObjectProvider<RemoteClient> clientProvider) {
        this.clientProvider = clientProvider;
    }

    void execute() {
        RemoteClient client = clientProvider.getObject();
        client.call();
    }
}
~~~

This snippet requires **@Component** and **ObjectProvider** imports. `ReportCoordinator`'s constructor receives only the provider. Only when **execute()** calls **getObject()** does the container have to resolve the target bean if it does not yet exist.

**Key point:** if `ReportCoordinator`'s constructor or **@PostConstruct** **calls execute() immediately**, the error can still surface during startup. `ObjectProvider` only defers lookup **until the developer actually requests the object**.

### 6.4. Runners, Lifecycle, and Infrastructure Can Request Beans Early

An **ApplicationRunner** can be invoked by Spring Boot after refresh yet **before ApplicationReadyEvent**. If the runner injects or invokes a lazy bean, the error can occur in the post-refresh startup phase and fail the run before readiness.

Similarly, `BeanFactoryPostProcessor`, `BeanPostProcessor`, infrastructure listeners/lifecycle hooks, or the web server can trigger early initialization per framework needs. Never assume every lazy bean is "only created after application ready."

## 7. Readiness, Health Checks, and First-Request Latency

### 7.1. Ready Does Not Mean All Lazy Beans Are Valid

In Spring Boot, **ApplicationReadyEvent** signals that the standard startup sequence completed. It **does not imply all lazy beans were created** or all external dependencies connected successfully.

For example, a web application has a lazy controller/service not requested at startup. The health/readiness endpoint can report traffic-accepting status, and then the first request to that specific endpoint triggers the service and hits the configuration error. Whether Actuator detects an error depends on which health indicators are enabled, what they check, and which beans have been initialized.

**Do not equate "HTTP port is open," "Spring Boot ready," and "all features are working."** Those are three distinct levels of assurance.

### 7.2. First-Hit Latency and Concurrency

Even with valid configuration, the first call can be slower because it must:

- Create the bean along with any missing dependencies.
- Bind configuration properties and validate them.
- Build proxies or initialize related caches.
- Open connections to data sources (if initialization logic requires it).
- Execute `@PostConstruct` or custom initialization.

If multiple requests arrive for the same lazy singleton nearly simultaneously, Spring must coordinate creating that singleton; requests may wait together or receive errors based on initialization results. Never design SLAs for first requests as if they were warm requests without measuring.

### 7.3. An Error Shifted from Startup to Production Traffic

Scenario:

~~~text
Deploy new version
       |
       +-- lazy initialization = true
       +-- optionalFeature bean has invalid URL
       +-- startup and readiness succeed
       |
       +-- first traffic reaches optionalFeature
                |
                +-- create bean -> validation fails
                +-- request fails
                +-- monitoring detects only then
~~~

This can be **more dangerous than fail-fast** for critical functionality. When a bean is mandatory for core business logic, failing immediately at startup usually aborts a bad rollout early and prevents routing traffic to an unready version.

For rarely used optional features, lazy initialization can still be worthwhile, provided telemetry and a clear error policy are in place.

## 8. Catching Critical Errors Early Without Losing All Lazy Benefits

### 8.1. Marking Critical Beans Eager

When global lazy is enabled, use **@Lazy(false)** for mandatory beans:

~~~java
@Configuration(proxyBeanMethods = false)
class CriticalConfiguration {

    @Bean
    @Lazy(false)
    CriticalService criticalService(Environment environment) {
        String endpoint =
                environment.getRequiredProperty("critical.endpoint");
        return new CriticalService(endpoint);
    }
}
~~~

This snippet assumes **CriticalService** is already declared; requires **Configuration**, **Bean**, **Lazy**, and **Environment** imports. The bean must be managed by Spring as a normal singleton. When configuration is valid, the service is created at startup; when the property is missing, it can fail startup at the desired time.

**Use selectively.** Marking every bean eager defeats global lazy. Clearly define which beans are truly required for readiness and which are only needed when a secondary feature is invoked.

### 8.2. Validating Configuration Independently of Service Creation

You do not have to instantiate an entire client or open a network connection just to validate a property's format. Create a lightweight **startup validator** checking mandatory conditions:

~~~java
@Component
class CriticalConfigValidator implements ApplicationRunner {

    private final Environment environment;

    CriticalConfigValidator(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String url =
                environment.getRequiredProperty("critical.endpoint");

        if (!url.startsWith("https://")) {
            throw new IllegalArgumentException(
                    "critical.endpoint must start with https://");
        }
    }
}
~~~

This snippet requires **@Component**, **ApplicationRunner**, **ApplicationArguments**, and **Environment** imports. Boot invokes runners before **ApplicationReadyEvent**. Thus if the validator is registered and runs normally, invalid configuration fails startup **before ready**, even if the client using that property remains lazy.

Advantage: lightweight validation without creating clients or network connections. Drawback: potential **duplicated validation** across places; extract rules into a small shared helper used by both the startup validator and client construction to prevent policy drift.

### 8.3. Pre-Warming a Few Essential Dependencies

If readiness requires certain lazy beans to be constructed and initialized, a runner can request them deliberately:

~~~java
@Component
class CriticalBeanWarmup implements ApplicationRunner {

    private final ObjectProvider<CriticalClient> clientProvider;

    CriticalBeanWarmup(
            ObjectProvider<CriticalClient> clientProvider) {
        this.clientProvider = clientProvider;
    }

    @Override
    public void run(ApplicationArguments args) {
        clientProvider.getObject();
        // If needed, invoke a very specific verification call.
    }
}
~~~

This snippet assumes **CriticalClient**, importing **ObjectProvider** and runner APIs. **getObject()** triggers target creation if absent; bean creation errors fail the runner and block the ready milestone for that startup.

Do not blindly pre-warm every bean. If external services must be checked, set **timeouts**, bound retries, confirm the application truly requires that backend to receive traffic, and avoid overloading downstream systems during rollouts.

### 8.4. Choosing the Right Level of Health/Readiness Checks

With Actuator/Kubernetes, distinguish:

- **Liveness:** is the process alive or deadlocked; avoid depending heavily on external services.
- **Readiness:** can the application serve current traffic?
- **Startup validation:** is mandatory static configuration valid?
- **Runtime monitoring:** lazy tasks, optional features, and dependencies that fail after ready.

A custom readiness indicator can verify essential components, yet should not tie readiness to every optional feature or brief network blip, as that can destabilize rollouts and clusters. Health checks must be targeted and cost-bounded.

## 9. Practices for `@ConfigurationProperties` and Validation

### 9.1. Risk When Validation Is Tied to a Lazily Created Bean

If a configuration bean uses **@ConfigurationProperties** with validation (such as **@Validated** and **@NotBlank**), binding/validation is typically tied to **creating that configuration bean**. If that bean is genuinely lazy and nothing has requested it yet, errors can be deferred until creation.

Conceptual example:

~~~java
@ConfigurationProperties(prefix = "demo.remote")
@Validated
public class RemoteProperties {

    @NotBlank
    private String url;

    public String getUrl() {
        return url;
    }

    public void setUrl(String url) {
        this.url = url;
    }
}
~~~

This is a snippet requiring **ConfigurationProperties**, **Validated**, and **NotBlank** imports, plus an appropriate validation dependency (such as **spring-boot-starter-validation**). The bean must be registered via **@EnableConfigurationProperties**, configuration properties scanning, or an equivalent mechanism.

**Do not claim all `@ConfigurationProperties` beans are always initialized lazily.** Auto-configuration, binding, or eager consumers can create them early; metadata-phase conditions are still evaluated during refresh. What you must check is **when binding and validation actually execute for that specific configuration bean**.

### 9.2. Fail-Fast for Mandatory Properties

If **demo.remote.url** is indispensable for core request handling:

1. Define a clear schema/config contract.
2. Validate format, length, presence, or allowed values during a startup step.
3. Separate pure validation from network I/O when possible.
4. Publish readiness only after minimum prerequisites pass.
5. Add tests for missing/malformed properties as well as valid configurations.

A reliably fail-fast application usually gives much clearer deployment signals than starting cleanly and failing on the first request.

## 10. Testing the Difference Between Refresh and First Bean Creation

You do not need a web server to verify the principle. In Spring Framework, **@Lazy** on a **@Bean** can be tested directly using **AnnotationConfigApplicationContext**. This tests **bean-level lazy** semantics, whereas Boot's global **spring.main.lazy-initialization** setting belongs to Spring Boot and should additionally be tested with a real `SpringApplication`.

### 10.1. Adding JUnit

In the Section 5 Maven project, add the test dependency to `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

### 10.2. Unit/Context Test for a `@Lazy` Bean

Create **src/test/java/com/example/lazy/LazyBeanBehaviorTest.java**:

~~~java
package com.example.lazy;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.BeansException;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LazyBeanBehaviorTest {

    @Configuration(proxyBeanMethods = false)
    static class TestConfiguration {

        @Bean
        @Lazy
        LazyFailureApplication.RemoteClient remoteClient(
                Environment environment) {
            String url =
                    environment.getRequiredProperty("demo.remote.url");
            return new LazyFailureApplication.RemoteClient(url);
        }
    }

    @Test
    void missingPropertyFailsOnFirstLookupNotRefresh() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.register(TestConfiguration.class);
            context.refresh();

            assertTrue(context.isActive());
            assertFalse(
                    context.getBeanFactory()
                           .containsSingleton("remoteClient"));

            assertThrows(
                    BeansException.class,
                    () -> context.getBean(
                            LazyFailureApplication.RemoteClient.class));
        }
    }

    @Test
    void validPropertyCreatesBeanOnlyWhenRequested() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource(
                            "test",
                            Map.of("demo.remote.url",
                                   "https://example.invalid")));

            context.register(TestConfiguration.class);
            context.refresh();

            assertFalse(
                    context.getBeanFactory()
                           .containsSingleton("remoteClient"));

            var client = context.getBean(
                    LazyFailureApplication.RemoteClient.class);

            assertEquals("https://example.invalid", client.url());
            assertTrue(
                    context.getBeanFactory()
                           .containsSingleton("remoteClient"));
        }
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Why this test is meaningful:**

- The **remoteClient(...)** method in `TestConfiguration` has **@Lazy**; context refresh does not automatically initialize that singleton.
- **containsSingleton("remoteClient")** before lookup returns false in this test configuration, even though the definition is registered.
- When the property is missing, **getBean(...)** triggers the factory method, throwing an error in the **BeansException** hierarchy.
- When the property is valid, `getBean` creates the instance and **containsSingleton** returns true.
- The test needs no database or HTTP server because the error is isolated at the configuration validation layer.

**Limitation:** this test verifies **Spring Framework `@Lazy`** at the bean level, not Spring Boot's entire global **spring.main.lazy-initialization=true** mechanism directly. To verify the global property, run the Section 5 sample program with both CLI commands or write a startup integration test using a real `SpringApplication`.

### 10.3. Testing Full-Application Bootstrap

An integration suite should cover at minimum:

| Scenario | Expectation |
| --- | --- |
| Global lazy **false**, missing `demo.remote.url` | **run(...) fails**, never reaching `MAIN` code after `run` |
| Global lazy **true**, missing `demo.remote.url`, no lookup | **run(...) completes** |
| Global lazy **true**, missing `demo.remote.url`, calling `getBean` | **Fails at first lookup** |
| Global lazy **true**, valid endpoint, calling `getBean` | **Bean created successfully on lookup** |
| Global lazy **false**, valid endpoint | **Bean created during refresh** |
| Bean has **@Lazy(false)** even with global lazy true | **Bean created eagerly**; static errors can fail startup |
| Lazy bean directly injected by an eager bean | **May be created immediately during startup** |

In CI, when testing an expected startup failure, the test should **assert the exception from `run`**, rather than letting the process exit fail the pipeline without context.

For web applications, add a first-request test against endpoints depending on lazy beans to measure **first-hit latency** and verify errors follow proper error handling. Do not draw production performance conclusions from a single timing measurement.

## 11. Handling Real Errors Without Hiding Misconfiguration

### 11.1. Never Catch Exceptions and Return Fake Success

In the educational example, `main` catches `BeansException` to print the failure milestone. In production, the following pattern can be dangerous:

~~~java
try {
    criticalService.execute();
} catch (BeansException ex) {
    return "OK";
}
~~~

This snippet illustrates an anti-pattern. It turns a configuration error into **fake success**, hindering detection and corrupting business behavior. For critical features, fail startup or fail the request explicitly, log safely, and emit appropriate metrics/alerts.

### 11.2. Diagnosing the Exception Chain

A lazy failure typically manifests through an exception chain:

~~~text
BeanCreationException / UnsatisfiedDependencyException
    |
    +-- related bean name or dependency
            |
            +-- factory method / constructor / binding
                    |
                    +-- IllegalStateException
                        (required property demo.remote.url not found)
~~~

This is a typical diagram, **not a fixed stack trace**. Nested exception names, message wording, and wrapper depth depend on how the bean is declared and the framework version. When debugging, read the **root cause**, bean name, and when the error occurred.

Classification:

- **Missing property:** check `Environment` and `PropertySources` precedence without logging secrets.
- **Malformed value:** add clear validation and include the key name in error messages.
- **Missing bean dependency:** inspect component scanning, auto-configuration, conditions, and the injection graph.
- **Broken init callback:** inspect `@PostConstruct`/`afterPropertiesSet` logic and side effects performed inside it.
- **External resource unavailable:** separate static configuration errors from transient network failures; use timeouts and appropriate retry/circuit-breaker policies.

### 11.3. Contextual Logs and Metrics

Log or monitor:

- **Bean name** and failing class (never dump whole objects containing secrets into logs).
- **Lifecycle phase**: refresh, runner, first lookup, first HTTP request, or background job.
- Related **feature/endpoint**.
- Impact severity: critical/optional.
- **Failure count** and **time to detection after deploy**.
- When measuring first-hit latency: measure bean initialization separately from total request duration when possible.

Never print the entire `Environment`, command line, or secret configurations into logs just to explain an error. With Actuator, configuration-exposing endpoints must be secured and sensitive values masked.

## 12. Performance, Operational, and Design Trade-offs

### 12.1. Real Benefits of Lazy Initialization

An application with many beans where only a subset of features is used per run can save startup time and initial resources with lazy initialization. It is worth considering for:

- Applications with many optional features.
- CLI tools where each invocation runs only one subset of commands.
- Development, test environments, or workloads where startup time matters.
- Features that only need to load large modules when actually invoked.

However, actual gains depend on how many beans are avoided, the dependency graph, and the workload. Never promise lazy always makes an application faster overall.

### 12.2. Costs Can Shift to More Sensitive Moments

Laziness can increase:

- **First-request latency.**
- **Latency variance** between first and subsequent requests.
- **Risk of runtime errors after ready.**
- Difficulty analyzing startup, dependencies, and health.
- Sudden load bursts when a wave of users triggers an un-warmed feature concurrently.

If the application serves heavy traffic with strict SLOs, benchmark critical paths and pre-warm selectively. Do not treat lazy as the sole fix for slow startup without finding root causes.

### 12.3. A Balanced Strategy

A practical policy:

| Component Type | Recommendation |
| --- | --- |
| Core services and dependencies mandatory to accept traffic | **Eager** or validate/pre-warm before ready |
| Rarely used optional features | Can be **lazy**, with first-use failure monitoring |
| Config beans holding metadata that must be valid | Validate at startup without depending on consumers creating the bean |
| Clients connecting to temporarily unavailable backends | Separate config validation from runtime connectivity; explicit timeouts/retries |
| Very heavy beans used frequently | Consider pre-warming after measuring cost and readiness |
| Fast startup in dev/test | Can enable lazy per profile, while still testing the eager path before production |

No single lazy toggle fits every system. Base the decision on **readiness requirements, late-failure impact, and actual bean creation costs**.

## 13. Common Misconceptions

### 13.1. "`spring.main.lazy-initialization=true` ensures the app always starts up"

False. Config Data, infrastructure configuration, `BeanFactoryPostProcessor`s, and required dependencies can still fail before the context completes.

### 13.2. "With `@Lazy`, a bean is guaranteed not to be created during startup"

False. An eager bean or runner can still request it before ready. Laziness changes the **default creation policy**, not an unbreakable time barrier.

### 13.3. "`@Lazy` at an injection point and `@Lazy` on the target bean are equivalent"

Not quite. On the bean, it controls the `BeanDefinition`; at the injection point, it typically supplies a **proxy deferring target resolution**. When the target is a `final` class or `record`, subclass proxying may not work; **ObjectProvider** is usually clearer for explicit lookup.

### 13.4. "If startup is ready, all `@ConfigurationProperties` have already validated"

Not necessarily. Binding/validation tied to configuration bean creation can be deferred unless the bean was requested or has separate startup validation.

### 13.5. "Enabling eager automatically verifies remote connections"

Not automatically. Eager only forces bean creation to run. If the constructor does not perform network I/O and the client only connects on method calls, the backend can still fail on the first request.

### 13.6. "An error after ready must be caused by `@Lazy`"

Insufficient evidence. It could be a runtime bug, bad input data, network timeout, cold cache, expired credentials, or a concurrency issue. Verify **whether the bean was being created on that call** and read the root cause.

### 13.7. "Just call `getBean` for every bean during startup"

Avoid doing this. It can allocate many unnecessary resources, raise startup latency, and negate lazy initialization's benefits. Only validate/pre-warm truly mandatory dependencies.

### 13.8. "Catching first-use exceptions is enough; readiness can stay green"

For mandatory features, green readiness while functionality is broken sends the wrong operational signal. Adjust startup validation or readiness policy rather than hiding exceptions.

### 13.9. "Using `@PostConstruct` to call external APIs without timeouts"

Unsafe. If the bean is lazy, network failure hits the first request. If eager, network failure can hang or block startup. In either phase, I/O requires timeouts, retry policies, and clear fail-open/fail-closed criteria.

### 13.10. "Disabling lazy in production is enough; no need to test"

You still must test missing configuration, binding, profiles, conditions, and external dependency behavior. Eager catches one class of errors earlier, yet does not automatically verify correctness of all features.

## 14. Pre-Enablement Checklist for Lazy Initialization

- [ ] Know exactly which beans are lazy and which stay eager.
- [ ] Reviewed the dependency graph: do any eager singletons force lazy targets early?
- [ ] Mandatory properties for core features are validated before ready.
- [ ] Distinguished bean creation errors from method/network call errors.
- [ ] Have tests for missing properties, invalid values, and valid cases.
- [ ] Have tests for both **spring.main.lazy-initialization=true** and **false** when behavior matters.
- [ ] Not assuming `@ConfigurationProperties` always binds/validates before ready.
- [ ] Have a `@Lazy(false)` or selective pre-warm strategy for critical dependencies.
- [ ] Measured first-hit latency on real request paths.
- [ ] Readiness/liveness are targeted and do not sweep external dependencies indiscriminately.
- [ ] Have logs/metrics by bean, feature, and failure phase without leaking secrets.
- [ ] Runners cannot block indefinitely on validation or network connections.
- [ ] Not using catch-all handlers to report fake success when critical beans fail.
- [ ] Reviewed behavior across multiple contexts, background jobs, and rarely invoked consumers.
- [ ] Have operational docs explaining why certain errors may appear after deployment.

## 15. Self-Check Questions

**Question 1.** A lazy singleton requires a mandatory property, yet no other bean requests it. Will Spring Boot definitely catch the missing property during refresh?

**Answer:** No. If the check only runs upon bean creation and nothing requests the bean, the error can be deferred until the bean is first created.

**Question 2.** Why can the same missing-property configuration fail startup under eager yet fail on the first request under lazy?

**Answer:** Eager runs factory methods/constructors/init callbacks during refresh's singleton-creation phase. Lazy defers those steps until an instance is needed, so validation tied to them is also deferred.

**Question 3.** A bean has **@Lazy** yet is constructor-injected by an eager singleton. Is the lazy bean guaranteed to be created only after ready?

**Answer:** No. An eager singleton's dependency can force Spring to create the lazy bean right at startup.

**Question 4.** Does enabling lazy prevent YAML syntax errors from being caught when `SpringApplication` prepares the `Environment`?

**Answer:** No. Parsing Config Data belongs to bootstrap and can still fail before the container creates application singletons.

**Question 5.** When is **@Lazy(false)** used?

**Answer:** When you want an important bean initialized eagerly even when the application enables lazy initialization broadly, so related errors are caught earlier.

**Question 6.** Does **ObjectProvider.getObject()** fix a misconfigured URL?

**Answer:** No. It only defers lookup until `getObject` is called; if the factory method requires the URL and the URL is still invalid, the error still occurs at first lookup.

**Question 7.** Once an eager bean is created successfully, is DNS/backend guaranteed to work?

**Answer:** No. If the bean has not attempted an actual connection, connectivity errors can occur inside a method at runtime. That is an operational error distinct from validation/creation.

**Question 8.** Why can the readiness endpoint report healthy while a lazy feature still fails?

**Answer:** Readiness does not create and validate all lazy beans by itself. If health indicators do not check that feature and no request has triggered the bean yet, the error has not surfaced.

**Question 9.** How can you enforce a valid property before ready while keeping the client itself lazy?

**Answer:** Separate configuration validation into a lightweight startup step (such as an `ApplicationRunner`), or an eager validator bean; there is no need to build the full client or open network connections.

**Question 10.** Does a unit test using **AnnotationConfigApplicationContext** with `@Bean @Lazy` prove Spring Boot's global lazy flag works properly?

**Answer:** Not yet. It proves bean-level lazy semantics in Spring. Run `SpringApplication` with the global property to verify Boot's configuration behavior.

## 16. Summary and Official Documentation

**Lazy initialization changes when a bean is created, so it can also shift when configuration errors tied to bean creation are detected.** With eager singletons, missing properties, unresolved dependencies, or initialization errors can fail startup. With unrequested lazy singletons, the context can still reach ready, and errors surface only when the instance is first created.

However, **laziness does not defer all errors**: Config Data, registry, post-processors, infrastructure, and dependencies requested early can still fail during refresh. Choose **@Lazy(false)**, startup validation, selective pre-warming, and proper readiness policies for critical components; use unit/context tests and run both eager and lazy variants so you know when errors appear. Never sacrifice production reliability for faster startup without measuring first-hit latency and the blast radius of late failures.

Official documentation:

- Spring Boot — Lazy Initialization: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework — Lazy-initialized Beans: https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html
- Spring Framework — @Lazy API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/context/annotation/Lazy.html
- Spring Framework — ObjectProvider API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/ObjectProvider.html
- Spring Boot — Configuration Properties and Validation: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot — Application Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework — BeanCreationException API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/BeanCreationException.html