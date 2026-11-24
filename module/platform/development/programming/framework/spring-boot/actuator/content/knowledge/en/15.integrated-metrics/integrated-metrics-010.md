# Observing Spring Data Repository Calls via the Supported Mechanism

## 1. What Are We Observing?

In a Spring application, repositories are where business code calls operations such as saving, finding, or counting data. When an application slows down, knowing "the database is connected" does not answer which repository method is called frequently, which method takes time, and which method is failing.

Spring Boot Actuator has built-in integration with Spring Data to record these calls using Micrometer. The measured target is **repository method invocations passing through integrated Spring Data infrastructure**, such as `CustomerRepository.findByName(...)`. A measurement includes execution duration and the outcome recorded by that infrastructure. This provides visibility at the application's data-access layer.

This lesson uses Spring Boot **3.3.x**, Spring Data JPA, and synchronous calls as primary examples. Property names, integration classes, and outcome conventions must be re-verified when changing version lines. The lab pins Boot 3.3.0 to fix the example environment clearly; do not use that version number to infer current support policy.

After this lesson, you should be able to do three things: identify conditions required for metrics to appear, invoke a method and locate its exact metric series, and explain the limits of conclusions drawn from those metrics.

## 2. Integration Mechanism and Measurement Boundary

Conceptual measurement flow:

```text
Code calls Spring Data-created repository bean
    → Spring Data method execution infrastructure
    → RepositoryMethodInvocationListener receives outcome and duration
    → MetricsRepositoryMethodInvocationListener records Timer
    → MeterRegistry
    → Actuator metrics or metrics exporter
```

`MetricsRepositoryMethodInvocationListener` implements Spring Data's `RepositoryMethodInvocationListener` extension point. It receives call info and records measurements; it does not require wrapping every method manually in a timer. See [Boot 3.3 listener API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/metrics/data/MetricsRepositoryMethodInvocationListener.html).

Practical preconditions are a Spring-managed Spring Data repository, Actuator metrics with an active `MeterRegistry`, and relevant auto-configuration not excluded or improperly replaced. Merely putting `@Repository` on a custom DAO class does not turn it into a Spring Data repository. An object instantiated manually with `new` does not receive this integration either.

**This boundary determines how results must be read.** A repository method can execute multiple queries; an operation can hit a cache; a query can trigger further work via lazy loading. Thus, one repository recording does not equal one SQL statement. With an outer transaction in a service, a repository method's outcome also does not prove the overall transaction ultimately committed.

Additionally, having a Timer does not prove a tracing span exists. Collecting aggregated metrics and tracing individual executions are separate concerns; verify observation/span integration if tracing is required.

## 3. Metric Name, Tags, and Measurement Type

The default name is `spring.data.repository.invocations`. Default tags distinguish repository, method, state, and exception. Micrometer's `@Timed` is supported on the repository interface or on interface methods. See [Spring Data Repository Metrics integration in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-data-repository).

| Tag | Interpretation |
| --- | --- |
| `repository` | Simple name of the repository interface, e.g., `CustomerRepository` |
| `method` | Method name, e.g., `findByName` |
| `state` | State reported by Spring Data for the invocation; values include `SUCCESS`, `ERROR`, `CANCELED`, `RUNNING` |
| `exception` | Simple name of the reported exception; in Boot 3.3.0 defaults, no error is represented as `None` |

Case sensitivity matters when filtering tags. Do not turn `None` into `none` on your own, or guess exception names from user-facing messages. Exceptions can be wrapped/translated at another layer; inspect the actual meter values.

A `Timer` records event count and total duration; depending on registry and configuration, it may also provide statistics like maximum time or distributions. There is no need to add a separate `Counter` merely to re-count calls already recorded by the Timer. See Micrometer's [Timer](https://docs.micrometer.io/micrometer/reference/concepts/timers.html) and [Counter](https://docs.micrometer.io/micrometer/reference/concepts/counters.html).

The appearance of `RUNNING` in the state model does not mean a regular Timer counts currently running tasks. This lesson reads completed synchronous calls; do not use `COUNT` to infer active tasks.

## 4. Standalone Example: Calling a Repository and Reading MeterRegistry

The example uses JDK 21, Gradle 8.5, and in-memory H2. Gradle must be installed; if your project already has a wrapper, use a compatible wrapper instead of the `gradle` command. Initial dependency resolution requires Maven Central access.

This is a separate practice project. The Java files below share package `demo`; the directory holding configuration and application classes looks like:

```text
repository-metrics-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── Customer.java
    │   ├── CustomerRepository.java
    │   └── DemoApplication.java
    └── resources/application.properties
```

**`settings.gradle`**

```groovy
rootProject.name = 'repository-metrics-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'application'
}
repositories {
    mavenCentral()
}
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
application {
    mainClass = 'demo.DemoApplication'
}
```

Boot's BOM manages library versions. The `application` plugin provides the `run` task; the example does not rely on an undeclared `bootRun` task.

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:repo_demo;DB_CLOSE_DELAY=-1
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
management.endpoints.web.exposure.include=health,metrics
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
```

Exposure allows reading `metrics` over HTTP when running in web mode. It is not the switch enabling repository measurements. The example adds no Spring Security; real apps must maintain proper authentication and endpoint authorization. The log-silencing lines only keep practice output clear; when diagnosing startup errors, remove `logging.level.root=OFF`.

**`src/main/java/demo/Customer.java`**

```java
package demo;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class Customer {
    @Id
    @GeneratedValue
    private Long id;

    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }
}
```

**`src/main/java/demo/CustomerRepository.java`**

```java
package demo;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Optional<Customer> findByName(String name);
}
```

**`src/main/java/demo/DemoApplication.java`**

```java
package demo;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner experiment(CustomerRepository repository, MeterRegistry registry) {
        return args -> {
            repository.save(new Customer("Lan"));
            boolean found = repository.findByName("Lan").isPresent();
            boolean missing = repository.findByName("Nobody").isEmpty();

            try {
                repository.findById(null);
                throw new IllegalStateException("Expected invalid id to fail");
            } catch (IllegalArgumentException
                    | org.springframework.dao.InvalidDataAccessApiUsageException expected) {
                // Continue so that the error metric can be inspected.
            }

            System.out.println("FOUND=" + found);
            System.out.println("MISSING=" + missing);
            System.out.println("findByName.SUCCESS="
                    + count(registry, "findByName", "SUCCESS"));
            System.out.println("findById.ERROR="
                    + count(registry, "findById", "ERROR"));
        };
    }

    private static long count(MeterRegistry registry, String method, String state) {
        return registry.find("spring.data.repository.invocations")
                .tags("repository", "CustomerRepository",
                        "method", method, "state", state)
                .timers().stream().mapToLong(Timer::count).sum();
    }
}
```

`save` creates a customer. Two `findByName` calls test present and missing data. `findById(null)` intentionally passes an invalid ID to trigger an input error, then catches the exception so meters can still be read. In real business code, do not catch and ignore errors this way.

Run from the project directory, with `JAVA_HOME` pointing to JDK 21:

```shell
gradle --console=plain run --args="--spring.main.web-application-type=none"
```

On a fresh startup with the example's default configuration and no extra calls, the four lines printed by the program are expected to be:

```text
FOUND=true
MISSING=true
findByName.SUCCESS=2
findById.ERROR=1
```

These are the application's output lines, not all of Gradle's stdout. The example runs with framework and dependencies, so you cannot just run `javac Customer.java` and expect the full classpath.

How to interpret the result:

- Both name lookups completed normally, so the `findByName/SUCCESS` group has count 2. Finding no record, represented by `Optional.empty()`, does not automatically become a technical error.
- The null-ID call entered the error path, so `findById/ERROR` has count 1. This input error does not prove the database received a query or experienced an outage.
- `save` also has its own measurement, yet the `count` helper filters only the supplied method and state, so `save` is excluded from those two count lines.
- `registry.find(...)` looks up existing meters. Calling `registry.timer(...)` to "check if a meter exists" can create an empty Timer itself, defeating diagnostic verification.

Do not hardcode an exact runtime duration for the example. JIT, ORM startup, caches, and machine load all affect duration. Compare measurements under identical conditions before evaluating optimizations.

## 5. Reading the Same Measurements via Actuator

Rerun in web mode so the application keeps its HTTP port open:

```shell
gradle --console=plain run
```

In another terminal, read the list and then the meter name:

```shell
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/spring.data.repository.invocations
```

On Windows PowerShell, use `curl.exe` if `curl` is an alias for another command. To prevent `&` from being interpreted by the shell, filter with individually encoded parameters:

```shell
curl --get http://localhost:8080/actuator/metrics/spring.data.repository.invocations --data-urlencode "tag=repository:CustomerRepository" --data-urlencode "tag=method:findByName" --data-urlencode "tag=state:SUCCESS"
```

Inspect `measurements` for the `COUNT` statistic; in a clean run of the example, the filter above yields count 2. Inspect `availableTags` in a less-filtered response to discover actual values, then add tags when distinguishing exception groups.

Do not read an unfiltered response aggregating all repositories and attribute it to one method. Without enough tag filters, multiple meters can match together. Nor should you pass Prometheus-transformed names into this endpoint: use the original dotted name here.

The `metrics` endpoint suits ad-hoc diagnostics. For retaining history, computing rates, and building alerts, use a registry/exporter and suitable monitoring backend; do not turn this diagnostic endpoint into a historical time-series store. See [metrics endpoint REST API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

## 6. Measuring Only Selected Methods With @Timed

If automatically measuring every repository is undesirable, turn off autotime and pick methods via annotation. Boot 3.3 configuration provides `management.metrics.data.repository.autotime.enabled`, defaulting to `true`; `management.metrics.data.repository.metric-name` sets the default autotimed name. See [Boot 3.3 properties reference](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

In a separate practice run, add to `application.properties`:

```properties
management.metrics.data.repository.autotime.enabled=false
```

Replace the repository interface with the following:

```java
package demo;

import java.util.Optional;
import io.micrometer.core.annotation.Timed;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    @Timed("demo.customer.lookup")
    Optional<Customer> findByName(String name);
}
```

Start a new process and invoke as in the previous example. Look up meter `demo.customer.lookup` instead of continuing to look for this method under the default name:

```shell
curl http://localhost:8080/actuator/metrics/demo.customer.lookup
```

With two name-lookup calls, the selected Timer's count is 2. Methods not annotated with `@Timed` are no longer auto-measured now that autotime is disabled. Because `count` in the original example queries `spring.data.repository.invocations`, both count lines from that helper will be 0 in this selective scenario. To print the new meter, update the queried name in the helper to `demo.customer.lookup`; `findByName/SUCCESS` will reflect two calls.

Place the annotation where repository integration supports it, such as the interface/method above. Do not assume every annotation containing "Timed" is equivalent: the import here is `io.micrometer.core.annotation.Timed`.

There is no need to add a general `TimedAspect` just to measure this repository example. If an AOP mechanism also times the same method concurrently, verify whether two recordings occur for one execution. Instrumenting custom services is a separate scope and must not be used to claim repository integration is missing.

Another change, independent of the annotation scenario, is renaming autotime:

```properties
management.metrics.data.repository.metric-name=demo.repository.invocations
```

When using this change with default autotime, update the queried name accordingly. Renaming the default property does not promise to rename an explicit `@Timed("demo.customer.lookup")`. Do not flip multiple variants simultaneously during an initial check; clarify which configuration is active.

## 7. Reading Metrics to Answer Practical Questions

### Do More Invocations Mean More User Requests?

Not necessarily. A single request can call a repository multiple times; background jobs can call it too. If an API handles 100 requests while calling a repository 500 times, inspect loops, pagination, or extra queries before concluding external traffic grew fivefold.

Cumulative counts also depend on process lifetime. Comparing two instances started at different times using absolute counts can mislead; to examine load over an interval, use rate of change or deltas over the same time window. When a process restarts, the monitoring system must handle counter resets.

### How Is Average Time Computed?

Given the exact same meter set, unit, and meaningful collection interval:

```text
average duration = total duration / recorded count

Illustrative example:
COUNT = 4
TOTAL_TIME = 0.080 seconds
Average = 0.020 seconds = 20 ms
```

This is an illustrative calculation, not a guaranteed runtime of the program. Never divide when count is 0. When aggregating across instances, sum total durations and sum counts before dividing; averaging per-instance averages is wrong if call counts differ across instances. Moreover, averages hide rare slow calls; appropriate distributions/histograms are needed for latency-tail questions.

### Does SUCCESS Prove the Entire Business Operation Succeeded?

No. In the example, not finding a user is still a normally completed repository call. The application may consider "not found" an unsatisfactory business outcome, yet that is a different classification.

Likewise, a service can call a repository successfully and then throw an exception or roll back the transaction in a later step. To measure overall business outcomes, define that business boundary and instrument it separately; do not twist repository tag meanings to suit a dashboard wish.

### Does ERROR Mean a SQL Error?

No. The null-ID mistake in the example sufficed to enter the error path without implying any SQL failed. Combine the exception tag, correlated logs, traces where available, and driver/database data to find root causes. Do not stuff full exception messages into tags as a substitute for reading logs.

## 8. Boundaries to Respect

| Available Metrics | What Can Be Concluded | What Needs Further Evidence |
| --- | --- | --- |
| Timer of a repository method | Frequency and duration recorded at the repository boundary | Per-SQL duration, execution plan, scanned rows |
| Tag `state=SUCCESS` | Repository execution itself was reported as completing normally | Whether the whole service succeeded or the transaction committed |
| Meters `jdbc.connections.*` or `hikaricp.*` | Corresponding connection/pool state | Which repository method is the root cause |
| An aggregated metric series | Trend for the call group matching the tags | Detailed trace of one specific request |

For repositories returning `Stream`, asynchronous types, or reactive types, do not assume the moment the result object is returned is when all work finished. With reactive models, also check subscription execution, completion, error, or cancellation. When adapting the example to another Spring Data store, verify listener boundaries for that exact version/store; do not extrapolate counts from this synchronous JPA program to every return type.

Default helper methods on interfaces, internal calls, or custom implementations must also be tested along the real execution path before assuming coverage. Do not count Java call sites in source code and assume they equal `COUNT` of a given timer.

## 9. Controlled Tag Customization

Boot provides the `RepositoryTagsProvider` extension point. If you define a replacement bean, you are responsible for returning appropriate tags; if you still want default tags, retain them explicitly. See [RepositoryTagsProvider API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/metrics/data/RepositoryTagsProvider.html).

A manageable design might add a bounded tag such as functional domain with a handful of known values. Conversely, customer IDs, emails, search strings, parameterized SQL strings, and free-form error messages create too many tag values. Each tag combination can become a distinct time series, driving up storage and resource costs in your monitoring system. Per-request details belong in logs/tracing under appropriate data policies. See [Micrometer naming and tag value rules](https://docs.micrometer.io/micrometer/reference/concepts/naming.html).

Default `method` is only the method name, not the full signature. Two overloads with the same name may not be separated by this tag alone; two repositories sharing a simple name in different packages also need thought during tag design. Do not use an under-differentiated tag and assume metrics belong solely to one signature or class.

## 10. When Metrics Are Missing or Differ From Expectations

Check in order to distinguish no measurement, inaccessible endpoint, and wrong metric filtering:

1. **Did the application start cleanly?** Check datasource config, dependencies, and logs before suspecting an Actuator bug.
2. **Was the repository bean actually called?** Declaring an interface does not prove a sample was recorded. Trigger one controlled call and re-read.
3. **Is it a real Spring Data repository and the right registry?** Check the actual bean, relevant auto-configuration, and the registry you are reading; do not measure a manually instantiated object outside the infrastructure.
4. **Is autotime or a meter filter blocking it?** When autotime is off, check supported annotations and chosen metric names; if custom `MeterFilter`s exist, check deny/rename rules.
5. **Is the HTTP endpoint exposed and authorized?** 401/403 is an access control issue, insufficient to conclude the timer is absent. Port, context path, and management base path may differ from the example.
6. **Are names and tags right?** Inspect original names and `availableTags`; verify `SUCCESS`, `ERROR`, repository name, method name, and actual exception. Filtering on the wrong tag set yields empty results.
7. **Were there unexpected invocations?** Runners, data seeders, startup checks, scheduled jobs, or other tests can all invoke repositories. Compare before/after deltas on the same tag set rather than staring at one total.
8. **Is there double measurement?** Check manual timers, custom aspects, and extra annotations before concluding Spring Data double-counted.

Do not work around issues by exposing all endpoints, adding duplicate timers with the same meaning, or stripping all tags to hide unexpected counts. First determine which measurement is being recorded and which call path triggers it.

## 11. Self-Verification Practice

Execute each scenario on a fresh process or record before/after counts to avoid mixing results:

| Scenario | Action | Expectation to Verify |
| --- | --- | --- |
| Default | Keep example as-is, no annotations | Both name-lookup calls fall in SUCCESS; null-ID error falls in ERROR |
| No record found | Query a non-existent name | `Optional.empty()` yet invocation completes normally |
| Selective measurement | Disable autotime, add `@Timed("demo.customer.lookup")` | Selected timer exists; do not expect unselected calls under the default name |
| Rename autotime | Use metric-name property, without annotation variant | Query the new name instead of the default name |
| Metrics unexposed | Remove metrics from exposure while still calling repository | Distinguish metrics existing in the registry from HTTP accessibility |

When reporting results, state version, configuration, meter name, tag set, and actual calls generated. A solid conclusion must answer: "Which execution segment does this figure represent, and what evidence is still missing to prove the cause of slowness or failure?"
