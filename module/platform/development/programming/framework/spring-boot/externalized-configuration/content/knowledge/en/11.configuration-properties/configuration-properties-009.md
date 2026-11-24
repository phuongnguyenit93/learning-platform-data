# Distinguishing Bean Creation, Property Binding, and Dependency Injection with @ConfigurationProperties

## 1. A Seemingly Simple Requirement Involving Three Distinct Tasks

Suppose a Spring Boot application processes batch jobs. `application.yaml` contains:

~~~yaml
jobs:
  batch-size: 200
  timeout: 15s
  endpoint: https://jobs.example.test
~~~

You want Java code to use these values safely with explicit data types:

~~~java
public record JobProperties(
        int batchSize,
        Duration timeout,
        URI endpoint) {
}
~~~

Looking solely at the code and YAML file, you might think Spring Boot automatically creates a `JobProperties`, reads each key, and passes the object into a service. In reality, there are **three separate responsibilities**:

1. **Bean creation and registration**: how does `JobProperties` become a Spring-managed object in `ApplicationContext`?
2. **Configuration binding**: how are `jobs.batch-size`, `jobs.timeout`, and `jobs.endpoint` from `Environment` converted into corresponding Java values?
3. **Dependency injection (DI)**: once the configuration object is a bean, how does `JobService` receive it via its constructor?

`@ConfigurationProperties` primarily describes **the property group to bind**. It does not mean every class carrying this annotation automatically appears in the container under all circumstances. Registration can happen via configuration scanning, explicit registration, or standard bean creation; binding mechanics depend on the object type and registration mechanism.

**Learning objective:** after this lesson, you will distinguish "missing bean," "configuration binding failure," and "dependency injection failure" errors, and choose the right `@ConfigurationProperties` registration and binding approach in Spring Boot.

## 2. Three Concepts from the Perspective of ApplicationContext and Environment

### 2.1. Bean Creation and Registration

A **bean** is an object managed by the Spring container. Spring learns about bean definitions through:

- `@Component` and component scanning.
- `@Bean` on a method inside a configuration class.
- `@Import`, `@EnableConfigurationProperties`, or registration mechanisms provided by the framework.
- Scanning `@ConfigurationProperties` classes via `@ConfigurationPropertiesScan`.
- Auto-configuration or an appropriate extension registration mechanism.

Saying "bean creation" generally covers Spring knowing the bean definition and then instantiating the object via the appropriate mechanism. To participate in dependency injection, an object must **be managed by the container**; an object instantiated manually with `new` outside Spring does not automatically become a bean.

### 2.2. Configuration Binding

**Binding** is retrieving properties from `Environment`, converting types, and populating a Java object according to its declared structure.

For example:

~~~properties
jobs.batch-size=200
jobs.timeout=15s
~~~

binds to:

~~~java
int batchSize = 200;
Duration timeout = Duration.ofSeconds(15);
~~~

With `@ConfigurationProperties(prefix = "jobs")`, Spring Boot treats properties starting with `jobs` as data intended for the configuration object.

Binding can occur via **setter/JavaBean binding** or **constructor binding**, depending on the configuration class and registration mechanism. It does not mean a service has already received that object.

### 2.3. Dependency Injection

**Dependency injection** is the mechanism by which Spring supplies required collaborators to another bean.

~~~java
@Service
public class JobService {
    private final JobProperties properties;

    public JobService(JobProperties properties) {
        this.properties = properties;
    }
}
~~~

In this example, `JobService` depends on `JobProperties`. Spring locates a matching bean by type and passes it into the constructor.

DI does not decide what `jobs.batch-size` equals. **Binding** handles that. And DI does not necessarily instantiate a new `JobProperties` for every `JobService`; typically a singleton bean is reused according to its bean scope.

### 2.4. Overall Model

~~~text
application.yaml ──────┐
application-prod.yaml ─┤
OS environment ────────┤
JVM -Dproperties ──────┼─> Environment / PropertySources
CLI --key=value ───────┘                |
                                     reads jobs.*
                                          |
                                          v
                                Configuration Binder
                                   |          |
                 constructor binding          JavaBean/setter binding
                                   |          |
                                   +-----+----+
                                         |
                                 JobProperties bean
                                         |
                                   Spring DI
                                         |
                                         v
                                      JobService
~~~

This diagram shows responsibilities, not a rigid sequence for every bean type. With constructor binding, the binder **uses configuration values directly while instantiating the object**; with JavaBean binding, the container may instantiate the object first and the binder populates properties afterwards. Both ultimately provide a bean for Spring to inject into other components.

## 3. Why Is Adding `@ConfigurationProperties` Alone Not Enough?

A class:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "jobs")
public class JobProperties {
    private int batchSize;
    private Duration timeout;

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

`@ConfigurationProperties(prefix = "jobs")` states that this object **can receive bound configuration from the `jobs` group**.

If the application has no mechanism registering this class as a bean:

~~~java
@Service
public class JobService {
    public JobService(JobProperties properties) {
    }
}
~~~

the application can fail to start because Spring **cannot find a `JobProperties` bean**.

This is a failure at the **bean registration** layer, not evidence that the binder failed to parse `batch-size` or `timeout`.

Separate your diagnostic questions:

- Is there a `JobProperties` bean definition in the context?
- If so, how was the bean created?
- Did the binder locate the right keys and convert types successfully?
- Can `JobService` resolve a single matching bean to inject?

A failure at an earlier step prevents later steps from executing.

## 4. Standard Registration: @ConfigurationPropertiesScan

For configuration classes designed specifically for Spring Boot, `@ConfigurationPropertiesScan` is a familiar choice.

### 4.1. Declaring an Immutable Record

~~~java
package com.example.demo.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "jobs")
public record JobProperties(
        int batchSize,
        Duration timeout,
        URI endpoint) {
}
~~~

This record:

- Has three fields that are immutable after creation.
- Needs no setters.
- Uses its canonical constructor to receive values.
- Allows Spring Boot to convert `200` to `int`, `15s` to `Duration`, and a valid URL to `URI`.

### 4.2. Enabling Configuration Scanning

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

With package structure:

~~~text
com.example.demo
├── DemoApplication.java
├── config
│   └── JobProperties.java
└── service
    └── JobService.java
~~~

`@ConfigurationPropertiesScan` locates eligible configuration classes under the annotated class's default scan package. It **registers** `JobProperties` and lets Spring Boot instantiate it via constructor binding.

The prerequisite is placing the class within scan scope or explicitly declaring packages to scan:

~~~java
@ConfigurationPropertiesScan("com.example.shared.config")
~~~

If the class sits outside scan scope without another registration mechanism, having the annotation on the class alone does not guarantee the bean exists.

### 4.3. The Right Mental Model

`@ConfigurationPropertiesScan` is responsible for **discovering and registering** `@ConfigurationProperties` classes. Once definitions are processed, Spring Boot's infrastructure performs **binding**. Services subsequently receive the bean via **DI**.

These three mechanisms combine to give the impression that "everything just works," yet each retains an independent role.

## 5. Explicit Registration: @EnableConfigurationProperties

Instead of package scanning, you can list the exact configuration classes to register:

~~~java
package com.example.demo;

import com.example.demo.config.JobProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(JobProperties.class)
public class JobConfiguration {
}
~~~

Spring Boot registers `JobProperties` explicitly and then binds values from `Environment`.

Useful when:

- Only a few specific configuration groups are needed.
- Classes reside in a module/library outside scanned packages.
- You want the configuration class to state explicitly which property groups it owns.
- Auto-configuration or module-specific config needs to enable a specific properties type.

If you use `@EnableConfigurationProperties(JobProperties.class)`, you do not need to also add `@ConfigurationPropertiesScan` just to register **the same class**. Pick one clear mechanism and avoid duplicate registration that is hard to trace.

### Why Does This Clarify the Three Layers?

In this example:

- `@EnableConfigurationProperties`: instructs Spring Boot to register the required bean type.
- `@ConfigurationProperties(prefix = "jobs")` on `JobProperties`: describes input data for the binder.
- `JobService(JobProperties properties)`: asks Spring to inject the managed bean into the service.

All three work together, yet each annotation or constructor expresses one clear responsibility.

## 6. Standard Bean Creation: @Component with @ConfigurationProperties

A mutable class can also be created via component scanning:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "jobs")
public class MutableJobProperties {

    private int batchSize;
    private Duration timeout = Duration.ofSeconds(10);

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Here:

1. `@Component` and component scanning tell Spring to register/create the bean via standard component mechanics.
2. `@ConfigurationProperties` tells the binding infrastructure to populate `jobs.*` values onto the created instance.
3. A service can receive `MutableJobProperties` via constructor injection.

This is **JavaBean binding** with setters, distinct from creating immutable records via constructor binding.

### Limitations to Understand

Do not use `@Component` as a default way to create classes whose only constructor takes **configuration values** expecting Spring Boot to automatically perform constructor binding.

For example:

~~~java
@Component
@ConfigurationProperties(prefix = "jobs")
public record JobProperties(int batchSize, Duration timeout) {
}
~~~

In this setup, Spring treats the record as an ordinary component and tries to resolve constructor parameters as **bean dependencies**. `@ConfigurationProperties` constructor binding does not apply in the same way to beans created by standard mechanisms such as `@Component`.

For `@ConfigurationProperties` records, register via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` to use constructor binding properly.

**Remember:** `@ConfigurationPropertiesScan` does not scan classes also annotated with `@Component` as separate configuration-properties classes. With `@Component`, registration belongs to component scanning and binding uses the mechanism suited to existing beans.

## 7. How Do Constructor Binding and JavaBean Binding Differ?

| Criterion | Constructor Binding | JavaBean / Setter Binding |
| --- | --- | --- |
| Typical target | Records, immutable classes with configuration constructors | Mutable classes with appropriate constructor and setters |
| Value population path | Binder resolves and converts values before calling constructor | Spring creates object, then binder updates writable properties |
| Setters required? | No | Usually setters for scalar properties being bound |
| Registration integration | `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties` | Either of those, or Spring-created beans via `@Component`/`@Bean` |
| Advantages | Stable post-creation data; required parameters clear | Convenient for mutable classes and existing library objects |
| Considerations | Constructor must accept config values; do not mix arbitrarily with DI beans | Object may briefly be in a partially bound state during initialization |

### 7.1. Records and Constructor Binding

~~~java
@ConfigurationProperties(prefix = "mail")
public record MailProperties(
        String from,
        int retryCount) {
}
~~~

In Spring Boot 3.x, a record with an eligible canonical constructor supports constructor binding when registered via configuration scanning or `@EnableConfigurationProperties`. The binder reads `mail.from` and `mail.retry-count`, then constructs `MailProperties` with those two values.

You do not need to write:

~~~java
new MailProperties(
    environment.getProperty("mail.from"),
    environment.getProperty("mail.retry-count", Integer.class));
~~~

The binder already handles reading and converting types according to your declared structure.

### 7.2. Immutable Class with Multiple Constructors

When a class has multiple constructors, you may need to annotate the constructor to use for binding:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "gateway")
public class GatewayProperties {

    private final String host;
    private final Duration timeout;

    @ConstructorBinding
    public GatewayProperties(String host, Duration timeout) {
        this.host = host;
        this.timeout = timeout;
    }

    public GatewayProperties(String host) {
        this(host, Duration.ofSeconds(5));
    }

    public String getHost() {
        return host;
    }

    public Duration getTimeout() {
        return timeout;
    }
}
~~~

In Spring Boot 3.x, `@ConstructorBinding` is placed on the **constructor** and lives in `org.springframework.boot.context.properties.bind`. Do not copy syntax or package names from older Spring Boot releases if your project uses Boot 3.x.

This example illustrates constructor selection. For a record or class with a single eligible parameterized constructor, Spring Boot normally infers it without requiring an explicit annotation.

### 7.3. JavaBean Binding via Setters

~~~java
@ConfigurationProperties(prefix = "gateway")
public class MutableGatewayProperties {

    private String host = "localhost";
    private Duration timeout = Duration.ofSeconds(5);

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

With JavaBean binding, initial field values serve as defaults when configuration omits the matching key; when present, the binder updates them via setters.

In the example above, `timeout` defaults to 5 seconds. If `gateway.timeout=30s` is active, the object holds `Duration.ofSeconds(30)` after binding.

**There is no requirement that every `@ConfigurationProperties` class must be immutable.** What matters is that registration style, class purpose, and binding mechanics align cleanly.

## 8. Dependency Injection: Once the Configuration Bean Is Ready

After `JobProperties` is registered and created/bound successfully, another service can receive it:

~~~java
package com.example.demo.service;

import com.example.demo.config.JobProperties;
import org.springframework.stereotype.Service;

@Service
public class JobService {

    private final JobProperties properties;

    public JobService(JobProperties properties) {
        this.properties = properties;
    }

    public int batchSize() {
        return properties.batchSize();
    }

    public String destination() {
        return properties.endpoint().toString();
    }
}
~~~

Spring inspects the `JobService(JobProperties properties)` constructor and searches the context for a `JobProperties` bean. Finding a single compatible bean, Spring passes it in.

**What DI solves:** giving `JobService` the configuration object it needs.

**What DI does not solve:** converting `15s` into `Duration`, understanding `jobs.batch-size`, or checking whether a URI is valid. Those belong to configuration binding and type conversion.

### No `@Autowired` Needed When Only One Constructor Exists

In modern Spring Framework, a bean with a single constructor normally does not need `@Autowired` on that constructor:

~~~java
@Service
public class JobService {
    private final JobProperties properties;

    public JobService(JobProperties properties) {
        this.properties = properties;
    }
}
~~~

Constructor injection makes mandatory dependencies explicit, simplifies testing, and keeps fields `final`.

Do not confuse a constructor receiving a **`JobProperties` bean** with `JobProperties`'s own constructor receiving **configuration values**. Both constructors look similar syntactically, yet different parts of the infrastructure invoke them based on registration:

~~~text
JobProperties(int batchSize, Duration timeout, URI endpoint)
               ^^^^^^^^^       ^^^^^^^^        ^^^
               configuration data converted by the Binder

JobService(JobProperties properties)
           ^^^^^^^^^^^^^^^^^^^^^^^^
           registered bean supplied by Spring DI
~~~

This is the single most important distinction in this lesson.

## 9. Complete Example: From `application.yaml` to Service

### 9.1. Project Layout

~~~text
src/main/
├── java/com/example/reporting/
│   ├── ReportingApplication.java
│   ├── config/
│   │   └── ReportProperties.java
│   └── service/
│       ├── ReportService.java
│       └── ReportRunner.java
└── resources/
    └── application.yaml
~~~

### 9.2. Configuration File

~~~yaml
reports:
  batch-size: 120
  timeout: 8s
  endpoint: https://reporting.example.test
  enabled: true
~~~

### 9.3. ConfigurationProperties Record

~~~java
package com.example.reporting.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "reports")
public record ReportProperties(
        int batchSize,
        Duration timeout,
        URI endpoint,
        boolean enabled) {
}
~~~

### 9.4. Application Enabling Scanning

~~~java
package com.example.reporting;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ReportingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReportingApplication.class, args);
    }
}
~~~

### 9.5. Service Receiving the Bean via DI

~~~java
package com.example.reporting.service;

import com.example.reporting.config.ReportProperties;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    private final ReportProperties properties;

    public ReportService(ReportProperties properties) {
        this.properties = properties;
    }

    public String summary() {
        return "enabled=" + properties.enabled()
                + ", batchSize=" + properties.batchSize()
                + ", timeout=" + properties.timeout()
                + ", endpoint=" + properties.endpoint();
    }
}
~~~

### 9.6. Runner Displaying the Result

~~~java
package com.example.reporting.service;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ReportRunner implements ApplicationRunner {

    private final ReportService service;

    public ReportRunner(ReportService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(service.summary());
    }
}
~~~

With default configuration, illustrative output:

~~~text
enabled=true, batchSize=120, timeout=PT8S, endpoint=https://reporting.example.test
~~~

Because `Duration.toString()` formats in ISO-8601, `8s` is displayed as `PT8S` in Java.

Running with overriding arguments:

~~~bash
java -jar reporting.jar --reports.batch-size=250 --reports.timeout=30s
~~~

The service receives:

~~~text
enabled=true, batchSize=250, timeout=PT30S, endpoint=https://reporting.example.test
~~~

Actual sequence:

1. Spring Boot loads configuration sources and resolves effective values for `reports.*`.
2. `@ConfigurationPropertiesScan` discovers and registers `ReportProperties`.
3. The Binder instantiates the record with converted values.
4. Spring creates `ReportService` and injects the `ReportProperties` bean.
5. Spring creates `ReportRunner`, injects `ReportService`, and executes the runner after context startup.

This traces all three mechanisms end to end: **bean creation/registration – binding – DI**.

## 10. `@Bean` and `@ConfigurationProperties`: Configuring Third-Party Objects

Not every class you want to bind has editable source code where `@ConfigurationProperties` can be added. For an existing mutable class from an external library or shared module, you can combine `@Bean` and `@ConfigurationProperties` on a **factory method**.

Suppose we have a mutable class `RemoteClientOptions`:

~~~java
package com.example.reporting.client;

import java.net.URI;
import java.time.Duration;

public class RemoteClientOptions {

    private URI endpoint;
    private Duration timeout = Duration.ofSeconds(5);

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Bean configuration:

~~~java
package com.example.reporting.config;

import com.example.reporting.client.RemoteClientOptions;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RemoteClientConfig {

    @Bean
    @ConfigurationProperties(prefix = "remote.client")
    RemoteClientOptions remoteClientOptions() {
        return new RemoteClientOptions();
    }
}
~~~

With:

~~~yaml
remote:
  client:
    endpoint: https://gateway.example.test
    timeout: 12s
~~~

what happens is:

- The `@Bean` method **creates and registers** a `RemoteClientOptions` instance.
- `@ConfigurationProperties(prefix = "remote.client")` asks the binder to **bind properties** onto that object via its setter methods.
- Other beans can **inject** `RemoteClientOptions` by Java type.

~~~java
package com.example.reporting.client;

import org.springframework.stereotype.Service;

@Service
public class RemoteGateway {

    private final RemoteClientOptions options;

    public RemoteGateway(RemoteClientOptions options) {
        this.options = options;
    }

    public String targetDescription() {
        return options.getEndpoint() + " (" + options.getTimeout() + ")";
    }
}
~~~

This pattern is especially useful for configuring third-party mutable objects with matching JavaBean properties.

**Important limitation:** `@Bean @ConfigurationProperties` operates on the instance returned by the factory, generally via JavaBean binding. Do not expect putting `@ConfigurationProperties` on a `@Bean` method to make Spring Boot perform constructor binding on a record returned by the factory.

## 11. Binding Is Not Automatic Injection of Arbitrary Beans into Properties

A common misconception is thinking a `@ConfigurationProperties` class with a constructor accepting `DataSource`, `RestClient`, or another service will have those beans injected by the binder.

Example of a flawed design when registered via configuration properties scanning:

~~~java
@ConfigurationProperties(prefix = "integration")
public class IntegrationProperties {

    private final AuditService auditService;

    public IntegrationProperties(AuditService auditService) {
        this.auditService = auditService;
    }
}
~~~

When Spring Boot selects constructor binding, it tries to bind a **configuration property** matching `auditService`, rather than performing DI like a `@Service` constructor. This class does not even have plain data fields coming from `integration.*`.

Separate the two responsibilities:

~~~java
@ConfigurationProperties(prefix = "integration")
public record IntegrationProperties(
        String endpoint,
        int retries) {
}
~~~

~~~java
@Service
public class IntegrationService {

    private final IntegrationProperties properties;
    private final AuditService auditService;

    public IntegrationService(
            IntegrationProperties properties,
            AuditService auditService) {
        this.properties = properties;
        this.auditService = auditService;
    }
}
~~~

Assume `AuditService` is already a valid bean. The second version ensures:

- `IntegrationProperties` holds only configuration data.
- `IntegrationService` receives both the configuration bean and the business bean via DI.
- The Binder does not try to treat a service as YAML properties.

Spring Boot documentation recommends that `@ConfigurationProperties` objects work primarily with **`Environment`** and avoid depending directly on other beans. If you genuinely need bean-dependent logic during object construction, use a separate bean/service or an appropriate `@Bean` method.

## 12. `@Value` Is Value Injection, Yet Different from `@ConfigurationProperties`

A service can also read individual values via `@Value`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class SimpleReportService {

    private final int batchSize;
    private final String endpoint;

    public SimpleReportService(
            @Value("${reports.batch-size:100}") int batchSize,
            @Value("${reports.endpoint}") String endpoint) {
        this.batchSize = batchSize;
        this.endpoint = endpoint;
    }
}
~~~

Here:

- `SimpleReportService` is registered because of `@Service`.
- Expressions inside `@Value("${...}")` are resolved by Spring from `Environment`.
- Spring injects those values into the service constructor.

There is no intermediate `ReportProperties` object.

### Comparison

| Criterion | `@Value` | `@ConfigurationProperties` |
| --- | --- | --- |
| Primary purpose | Inject one or a few values at the point of use | Bind a group of values into a configuration class/record |
| Separate config bean registration? | Not required | Required if injecting a properties object |
| Key group structure | Write each `${key}` expression individually | Uses `prefix` and matching fields |
| Type conversion | Supported via Spring conversion mechanism | Handled by Binder according to object structure |
| Relaxed binding | Not fully equivalent to Binder | A core strength |
| Group-level validation | Must organize manually | Integrates cleanly with Bean Validation |
| Best suited for | Few keys, simple logic | Larger, typed configurations reused across places |

When a class only needs a display title, `@Value` is enough. When a module needs an endpoint, timeout, batch size, nested groups, and validation, `@ConfigurationProperties` is much cleaner to read, test, and scale.

## 13. Bean Created, but Binding Fails: Which Layer Failed?

Suppose:

~~~yaml
reports:
  batch-size: abc
  timeout: 8s
  endpoint: https://reporting.example.test
~~~

While the record declares:

~~~java
@ConfigurationProperties(prefix = "reports")
public record ReportProperties(
        int batchSize,
        Duration timeout,
        URI endpoint) {
}
~~~

The bean was **registered** via scanning or `@EnableConfigurationProperties`, yet the binder cannot convert `abc` into a valid integer for `int batchSize`. Bean creation/binding fails with `ConfigurationPropertiesBindException` or an underlying `BindException`.

This is not a "Spring doesn't know `ReportProperties` is a bean" error. It is a **binding or type conversion** error.

Conversely:

~~~text
No qualifying bean of type '...ReportProperties'
~~~

signals you to inspect **bean registration**, package scanning, or context conditions.

And:

~~~text
expected single matching bean but found 2
~~~

is a **DI multiple-candidates** error, e.g., when you accidentally registered two beans of the same type.

These three error categories point straight to different fixes.

## 14. Validation: Checking Business Validity of Values

Successful type conversion does not guarantee valid business data. For instance, `batch-size=0` is a valid integer syntactically, yet invalid if the system requires at least 1 item per batch.

You can use Bean Validation:

~~~java
package com.example.reporting.config;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "reports")
public record ReportProperties(
        @Min(1) int batchSize,
        @NotNull Duration timeout,
        @NotNull URI endpoint,
        boolean enabled) {
}
~~~

If the project includes an appropriate Bean Validation provider (commonly via `spring-boot-starter-validation`), Spring Boot validates constraints during configuration binding.

In this example:

- `reports.batch-size=0` violates `@Min(1)`.
- Missing `reports.endpoint` violates `@NotNull`.
- `reports.timeout=invalid` triggers a type conversion error **before** reaching validation.

If `timeout` must be positive, add an appropriate constraint or custom validation rule for that data type. Do not assume `@NotNull` alone guarantees a `Duration` is positive.

### Binding and Validation Remain Separate

1. **Bean registration** determines which objects to create.
2. **Binding** retrieves and converts properties.
3. **Validation** checks object values against rules.
4. **DI** delivers the valid bean to consumers.

When validation fails, the application refuses to finish starting with an invalid config bean. This is beneficial: misconfiguration is caught immediately.

## 15. PropertySource Precedence Affects Binding, Not Bean Type

With file:

~~~yaml
reports:
  batch-size: 120
  timeout: 8s
~~~

and command:

~~~bash
java -jar reporting.jar --reports.batch-size=250
~~~

under Spring Boot's default configuration, `reports.batch-size` from the command line takes precedence over the file. The Binder reads the **effective value** from `Environment`, so the record receives `250`.

You do not change `@ConfigurationProperties(prefix="reports")` or modify `ReportService`. Source precedence dictates the values the binder receives.

### Profiles and Environment-Specific Files

~~~yaml
# application.yaml
reports:
  batch-size: 100
~~~

~~~yaml
# application-prod.yaml
reports:
  batch-size: 1000
~~~

When the `prod` profile is active and no higher-precedence source overrides it, `ReportProperties.batchSize()` holds `1000`.

**This is still the exact same `ReportProperties` bean type**, not a separate "dev bean" and "prod bean" generated by `@ConfigurationProperties`. Profiles alter data sources, whereas conditional bean creation per profile requires separate bean conditions such as `@Profile`.

## 16. `@Profile` Can Decide Bean Creation, While `@ConfigurationProperties` Supplies Data

Suppose a system has two `ReportPublisher` implementations:

~~~java
public interface ReportPublisher {
    String destination();
}
~~~

Configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class PublisherConfiguration {

    @Bean
    @Profile("!prod")
    ReportPublisher localPublisher(ReportProperties properties) {
        return () -> "local: " + properties.endpoint();
    }

    @Bean
    @Profile("prod")
    ReportPublisher productionPublisher(ReportProperties properties) {
        return () -> "production: " + properties.endpoint();
    }
}
~~~

In this example:

- `@Profile("prod")` and `@Profile("!prod")` choose which **`ReportPublisher` bean** gets registered.
- `@ConfigurationProperties` on `ReportProperties` specifies the **`reports.*` data group** used to populate the properties bean.
- The `ReportProperties properties` parameter on `@Bean` methods is supplied by **Spring DI**.
- `application-prod.yaml` can provide `reports.endpoint` when the `prod` profile is active.

Thus all three responsibilities collaborate within the same configuration class.

If both `prod` and `cloud` are active, `@Profile("prod")` still matches while `!prod` does not. However, if you declare two beans of the same type with `@Profile("prod")` and `@Profile("cloud")`, both can be created, causing ambiguous DI. Profile file ordering does not automatically pick a winning bean.

## 17. One Configuration Bean Can Be Shared by Multiple Services

Example:

~~~java
@Service
public class ReportService {

    private final ReportProperties properties;

    public ReportService(ReportProperties properties) {
        this.properties = properties;
    }
}
~~~

~~~java
@Service
public class AlertService {

    private final ReportProperties properties;

    public AlertService(ReportProperties properties) {
        this.properties = properties;
    }
}
~~~

Both services receive the same **`ReportProperties` bean** in a standard singleton context.

Spring Boot does not re-bind configuration separately for each service. The Binder creates/populates the properties bean during context lifecycle, and DI injects that managed bean into all consuming components.

One advantage is that multiple services share **a single source of truth for configuration** instead of each service independently reading and converting the same keys.

### Do Not Confuse with Manually Creating Objects via `new`

~~~java
ReportProperties manual = new ReportProperties(
        10,
        Duration.ofSeconds(1),
        URI.create("https://manual.example.test"));
~~~

`manual` is a plain Java object. Invoking this constructor **does not register it** into `ApplicationContext` and does not make the binder read `application.yaml`.

Similarly, manually writing:

~~~java
JobService service = new JobService(manual);
~~~

is dependency injection in the general object-oriented sense, not Spring container wiring from bean definitions. In Spring Boot design, always know what Spring manages versus what your code instantiates manually.

## 18. Avoid Duplicate Registration When Mixing `@Component`, `@Bean`, and Scanning

An error can occur if you simultaneously:

- Annotate `MutableJobProperties` with `@Component`.
- Declare another `@Bean MutableJobProperties` in a `@Configuration` class.
- Inject `MutableJobProperties` by type without specifying which bean to use.

Then the context holds **two beans of the same type**, making a constructor taking `MutableJobProperties` ambiguous.

Example:

~~~java
@Component
@ConfigurationProperties(prefix = "jobs")
public class MutableJobProperties {
    // fields, getters, setters
}
~~~

~~~java
@Configuration
public class ExtraConfiguration {

    @Bean
    MutableJobProperties anotherProperties() {
        return new MutableJobProperties();
    }
}
~~~

If a service writes:

~~~java
public JobService(MutableJobProperties properties) {
}
~~~

Spring reports multiple qualifying beans of that type.

To prevent this:

- Choose one registration mechanism per properties type matching your actual design.
- For binder-constructed configuration records, prefer `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.
- For mutable third-party objects, use `@Bean @ConfigurationProperties` when suitable.
- For mutable component-scanned Spring beans, `@Component @ConfigurationProperties` can be used.
- When multiple beans of the same type are intentional, distinguish them with bean names, qualifiers, or separate types for DI.

Do not blindly mask the issue by slapping `@Primary` onto one bean without knowing why two definitions exist. `@Primary` picks one candidate, yet leaves the duplicate registration intact.

## 19. Package Scan Scope and Module Organization

Suppose:

~~~text
com.acme.application
└── DemoApplication.java

com.acme.shared
└── SharedProperties.java
~~~

If `@ConfigurationPropertiesScan` is on `DemoApplication` without specifying additional packages, `SharedProperties` **falls outside scan scope** because it is not in `com.acme.application` or a subpackage.

Direct fix:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan({
    "com.acme.application",
    "com.acme.shared"
})
public class DemoApplication {
}
~~~

Or explicit class registration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(SharedProperties.class)
public class SharedConfig {
}
~~~

Both approaches let Spring Boot register the bean. Binding then uses the prefix declared on `SharedProperties`.

### Annotation Prefix Is Not a Package Scan Directive

`@ConfigurationProperties(prefix = "shared")` means **bind `shared.*` keys**. It does not mean "scan package `com.acme.shared`." Those are completely different concepts.

## 20. Symptoms That Pinpoint the Failing Layer

| Symptom | Layer to Inspect First | Hint |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` for properties class | Bean registration | Check `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, packages, and component scan. |
| Injection fails due to multiple beans of same type | DI / registration | Check for duplicate creation via `@Component`, `@Bean`, or multiple configs. |
| `ConfigurationPropertiesBindException` | Binding | Check key names, Java types, syntax, and values in `Environment`. |
| `batchSize=0` even though 200 expected | Binding / sources | Check `batch-size` key, prefix, effective value, and primitive default. |
| Bean exists, yet URI is invalid | Type conversion / validation | Check `URI`, config value, and validation constraints. |
| CLI value beats YAML | PropertySource precedence | Normal behavior when CLI source has higher precedence. |
| Using record, yet Spring looks for `int` or `Duration` bean in constructor | Wrong registration style for constructor binding | Check whether `@Component` was added or bean was registered normally. |
| Service keeps old config after file edit | Configuration lifecycle | Editing files does not automatically refresh properties beans. |

In error logs, locate the **first meaningful root cause**. `UnsatisfiedDependencyException` can wrap a missing bean, or it can wrap a bean creation failure caused by binding failure. Never diagnose solely from the outermost exception class name.

## 21. When Configuration Is Bound and Runtime Changes

In a standard application, Spring Boot prepares `Environment` and processes Config Data during startup. Configuration beans are created and bound as the context constructs required components.

Editing `application.yaml` on disk after the application is already running **does not guarantee** `@ConfigurationProperties` beans will rebind. For an immutable record, its values cannot change after instantiation anyway.

For dynamic configuration updates, an application needs a dedicated mechanism to reload config sources and refresh affected components. Do not expect `@ConfigurationPropertiesScan`, setter binding, or constructor injection to refresh automatically.

Distinguish clearly:

- **`Environment` can change at runtime** if code or another mechanism actively adds or updates a `PropertySource`.
- **Already-bound properties beans** continue holding the values captured at creation/binding time.
- **Services holding constructor-injected properties beans** keep references to the injected bean rather than automatically receiving a new instance.

Therefore, when diagnosing runtime behavior, verify **when values were read** rather than looking solely at the file currently on disk.

## 22. Testing Each Responsibility Separately

You can write a Spring Boot test verifying the full path from configuration source to service.

Example:

~~~java
package com.example.reporting;

import com.example.reporting.config.ReportProperties;
import com.example.reporting.service.ReportService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
        "reports.batch-size=25",
        "reports.timeout=3s",
        "reports.endpoint=https://test.example.test",
        "reports.enabled=false"
})
class ReportPropertiesIntegrationTest {

    @Autowired
    ReportProperties properties;

    @Autowired
    ReportService service;

    @Test
    void bindsAndInjectsConfiguration() {
        assertEquals(25, properties.batchSize());
        assertEquals(Duration.ofSeconds(3), properties.timeout());
        assertEquals(25, service.batchSize());
    }
}
~~~

Assuming the application configuration uses `@ConfigurationPropertiesScan` and includes the service, this test confirms all three steps:

1. `ReportProperties` **is registered** so Spring injects it into the test.
2. Values from test properties **are bound by the binder** into proper types.
3. `ReportService` **receives the bean** with expected values.

### Isolating Binding Failure Tests

Try passing `reports.batch-size=not-a-number`. Context startup fails before the service runs, because the binder cannot convert the value to `int`.

### Isolating Registration Failure Tests

If you remove all registration mechanisms for `ReportProperties` while keeping a service that requires the bean, context startup reports a missing bean. That tests registration wiring, not type conversion.

### Isolating Ambiguous DI Tests

If you intentionally register an extra `ReportProperties` bean of the same type, observe the ambiguous injection error and resolve it intentionally with qualifiers or design separation, rather than leaving hidden duplicate beans.

## 23. Diagnosing with Environment and Spring Boot Tools

For non-sensitive data, you can inspect an effective property:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ReportConfigProbe {

    private final Environment environment;

    ReportConfigProbe(Environment environment) {
        this.environment = environment;
    }

    Integer effectiveBatchSize() {
        return environment.getProperty(
                "reports.batch-size", Integer.class);
    }
}
~~~

If `effectiveBatchSize()` returns `250` while the properties bean shows `0`, investigate registration/binding and field names. If `Environment` itself already returns an unexpected value, investigate **configuration sources and precedence** first.

Spring Boot Actuator exposes endpoints like `/actuator/configprops` and `/actuator/env` when installed, enabled, and properly authorized. They help inspect bound property groups and sources, yet can expose sensitive details. Use them only with proper security controls and value sanitization.

Never print an entire `@ConfigurationProperties` object to logs when it may hold passwords, tokens, or connection credentials.

## 24. Confusing Scenarios and Solutions

### Scenario A — Only Adding the Annotation to a Record

~~~java
@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(String merchantId) {
}
~~~

A service injects `PaymentProperties`, yet the application has not enabled `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, or another registration mechanism.

**Expected result:** Spring does not automatically create a `PaymentProperties` bean solely because the class has `@ConfigurationProperties`. Register it using an appropriate mechanism.

### Scenario B — Bean Exists, but Matching Config Is Absent

~~~java
@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(String merchantId) {
}
~~~

The application registered the bean properly, yet `payments.merchant-id` is missing from all configuration sources.

**Key takeaway:** registration remains a separate responsibility. During binding, values can be missing or take Java structure/type defaults. If data is mandatory, add validation or verification rather than assuming required keys always exist.

### Scenario C — `@Component` on a Record to Get a Bean

~~~java
@Component
@ConfigurationProperties(prefix = "payments")
public record PaymentProperties(String merchantId) {
}
~~~

**Problem:** this is standard component registration, not standard constructor binding for immutable configuration properties. Spring may attempt to treat the constructor as dependency injection, even though `merchantId` is just a configuration value. Use dedicated scanning or `@EnableConfigurationProperties` for records.

### Scenario D — A Service Needs Both Configuration and Business Beans

~~~java
@Service
public class PaymentService {

    private final PaymentProperties properties;
    private final PaymentGateway gateway;

    public PaymentService(
            PaymentProperties properties,
            PaymentGateway gateway) {
        this.properties = properties;
        this.gateway = gateway;
    }
}
~~~

Assuming both dependencies are valid beans, this is service-level DI: `PaymentProperties` handles bound configuration, while `PaymentGateway` is registered/created as a business collaborator bean.

### Scenario E — Third-Party Object with Setters

You cannot modify `ThirdPartyOptions` source code to add annotations. However, the class has a default constructor and setters for its properties.

**Right choice:** a `@Bean` method creating `ThirdPartyOptions` annotated with `@ConfigurationProperties(prefix="third-party")`, so the binder updates the instance before the bean is consumed.

### Scenario F — Value Is in YAML, Yet Not Reaching the Service

Check in order:

1. Is `JobProperties` registered?
2. Do prefix `jobs` and field `batchSize` map cleanly to `jobs.batch-size`?
3. Is another configuration source overriding the value?
4. Is the binder reporting a conversion or validation error?
5. Is the service injecting the right bean type, or are there multiple candidates?

This sequence separates data sources, registration, binding, and DI.

## 25. Practice Exercises

### Exercise 1 — Classify Responsibilities

Given:

~~~java
@ConfigurationProperties(prefix = "mail")
public record MailProperties(String from, int retryCount) {
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(MailProperties.class)
class MailConfig {
}
~~~

~~~java
@Service
class MailService {
    MailService(MailProperties properties) {
    }
}
~~~

Identify:

- Which line describes the key group to bind?
- Which line requests bean registration?
- Which line requests dependency injection?

**Answer:** `@ConfigurationProperties` describes binding, `@EnableConfigurationProperties` registers the bean, and `MailService`'s constructor is the DI point.

### Exercise 2 — Using a Record with Spring Boot 3.x

Define:

~~~java
@ConfigurationProperties(prefix = "storage")
public record StorageProperties(
        String bucket,
        int maxSize) {
}
~~~

Enable record registration via `@ConfigurationPropertiesScan` and supply:

~~~yaml
storage:
  bucket: files-demo
  max-size: 25
~~~

Create `StorageService(StorageProperties properties)` and verify `properties.bucket()` equals `files-demo` and `maxSize()` equals `25`.

**Key insight:** the Binder constructs the record; Spring DI passes the **constructed record** into the service.

### Exercise 3 — Fixing Improper Registration

Code:

~~~java
@Component
@ConfigurationProperties(prefix = "storage")
public record StorageProperties(String bucket) {
}
~~~

The goal is constructor binding on the record.

**Fix:** remove `@Component` from the record and register it via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(StorageProperties.class)`.

### Exercise 4 — Configuring a Mutable Object

Create a class with:

~~~java
public class RetryOptions {
    private int maxAttempts = 3;

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
~~~

Then declare:

~~~java
@Bean
@ConfigurationProperties(prefix = "client.retry")
RetryOptions retryOptions() {
    return new RetryOptions();
}
~~~

With:

~~~yaml
client:
  retry:
    max-attempts: 5
~~~

Who creates the instance, who writes the value `5`, and who delivers `RetryOptions` to services?

**Answer:** the `@Bean` method creates the instance; the configuration binder invokes the property setter to set `5`; Spring DI injects the bean into services.

### Exercise 5 — Predicting the Error

You have:

~~~java
@ConfigurationProperties(prefix = "service")
public record ServiceProperties(int port) {
}
~~~

The application registers it properly via `@ConfigurationPropertiesScan`, yet YAML specifies:

~~~yaml
service:
  port: abc
~~~

**Answer:** this is a binding/type-conversion error because `abc` cannot convert to `int`. Adding `@Service` on another class will not fix the cause.

### Exercise 6 — Command-Line Override

In `application.yaml`:

~~~yaml
service:
  port: 8080
~~~

Run:

~~~bash
java -jar app.jar --service.port=9191
~~~

With `@ConfigurationProperties(prefix="service")` and proper bean registration, `port` receives `9191` because the CLI source overrides the file.

**Key insight:** changing the value source does not change how bean registration or DI works.

### Exercise 7 — Testing Bean Count

Create an application with one `StorageProperties` and one `StorageService`. In a test using `ApplicationContext`:

~~~java
assertEquals(
        1,
        context.getBeansOfType(StorageProperties.class).size());
~~~

If the count exceeds one, check whether you registered the same type using multiple mechanisms or created an extra factory bean of the same type.

### Exercise 8 — Enforcing Validation

Suppose `service.max-connections` must be at least 1.

Define a `ServiceProperties` record with `@Min(1)` on `maxConnections`, add `@Validated` on the class, register the bean via `@ConfigurationPropertiesScan`, and add appropriate Bean Validation infrastructure.

**Expected behavior:** a value of `0` is caught during binding/validation before any service runs with an invalid setting.

## 26. Summary Table

| Task | Common Tool | Input | Output |
| --- | --- | --- | --- |
| Discover/register properties classes | `@ConfigurationPropertiesScan` | Package with annotated classes | Bean definitions for properties classes |
| Register specific properties classes | `@EnableConfigurationProperties` | Listed classes | Bean definitions for those classes |
| Create mutable bean via standard Spring mechanics | `@Component` or `@Bean` | Class or factory method | Container-managed bean |
| Bind properties onto object | `@ConfigurationProperties(prefix="...")` + Binder | Effective values in `Environment` | Object/fields populated and type-converted |
| Create immutable configuration object | Constructor binding | Config values matching constructor parameters | Immutable record/class constructed by binder |
| Bind onto factory-created object | `@Bean @ConfigurationProperties` | Created bean, writable setters/properties | Mutable bean populated with config |
| Provide properties to service | Constructor injection | Registered `ReportProperties` bean | Service receives dependency and uses it |
| Validate allowed values | `@Validated`, Bean Validation | Bound object | Fails on constraint violations |
| Change values per environment | Config Data, env vars, CLI | Config sources and precedence order | New input values for Binder |

## 27. Conclusion

The three actions—**bean creation**, **property binding**, and **dependency injection**—are related yet clearly bounded mechanisms.

- Bean registration/creation answers: *"Does this configuration object exist in `ApplicationContext`, and who creates it?"*
- Configuration binding answers: *"How are keys from `Environment` converted into fields or constructor parameters?"*
- Dependency injection answers: *"Which beans/services receive the Spring-managed configuration object?"*

For application-owned configuration classes, the standard Spring Boot pattern is declaring `@ConfigurationProperties` on a record or POJO, registering it via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`, and injecting that bean via a service constructor.

For mutable objects created by factories or component scanning, JavaBean binding and `@Bean @ConfigurationProperties` can be better suited. Choosing the right registration and binding approach lets you tell apart missing-bean errors, conversion errors, validation errors, and DI errors instead of applying fixes to the wrong layer.

## References

- [Spring Boot — Externalized Configuration, Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties).
- [Spring Boot — ConfigurationProperties API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html).
- [Spring Boot — ConfigurationPropertiesScan API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesScan.html).
- [Spring Framework — The IoC Container](https://docs.spring.io/spring-framework/reference/core/beans.html).