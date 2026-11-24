# Reading Scheduled Tasks with the `scheduledtasks` Endpoint

## 1. From Operational Question to Readable Information

Suppose an application has a task that refreshes the cache every 10 seconds and cleans temporary data after each run. When deploying, you want to verify: which schedules did Spring register, which method is attached to each schedule, and what is the actual interval after reading configuration?

`scheduledtasks` is a built-in Actuator endpoint that inspects tasks supplied to the endpoint by Spring's scheduling infrastructure. This article focuses on reading schedule registrations in a running application. A method appearing in the list does not prove that its most recent execution succeeded. `ScheduledTasksEndpoint`'s API exposes the read operation via `@ReadOperation`. [Spring Boot 3.3 Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/scheduling/ScheduledTasksEndpoint.html)

Three concepts to distinguish:

- **Task:** the unit of work to execute, such as the `refreshCache()` method.
- **Scheduler:** the component that arranges when the work executes.
- **Trigger:** the rule determining when the next run is due, such as a cron expression.

The examples and response structures in this article apply to **Spring Boot 3.3.x, Java 21**; the practice project pins Boot `3.3.13` to match that version's documentation. When using a different Boot branch, read that branch's API docs before writing a JSON parser.

## 2. How Data Is Collected

Typical flow with `@Scheduled`:

```text
Bean with @Scheduled method
    -> @EnableScheduling enables annotation processing
    -> Spring registers task with scheduling infrastructure
    -> ScheduledTaskHolder supplies registered tasks
    -> ScheduledTasksEndpoint builds descriptions
    -> GET /actuator/scheduledtasks returns JSON
```

`ScheduledAnnotationBeanPostProcessor` processes `@Scheduled` methods and also participates in the `ScheduledTaskHolder` contract. This component also collects registrations via `SchedulingConfigurer`. Therefore, the data source can include both annotation-declared schedules and schedules registered programmatically through that infrastructure. [`@Scheduled` processor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/annotation/ScheduledAnnotationBeanPostProcessor.html)

The endpoint's auto-configuration receives `ScheduledTaskHolder` beans from Spring. This implies an important limitation: a background thread or a manually created `ScheduledExecutorService` does not automatically appear just because it runs in the same JVM; tasks must be provided through the contract the endpoint reads. [`scheduledtasks` auto-configuration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/scheduling/ScheduledTasksEndpointAutoConfiguration.html)

## 3. Runnable Example: Creating Three Schedule Types and Reading the Output

### 3.1. Preparing a Standalone Project

Create the practice project with JDK 21 and Gradle 8.5. File structure:

```text
scheduledtasks-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/scheduling/
    │   ├── SchedulerApplication.java
    │   └── DemoJobs.java
    └── resources/application.properties
```

Contents of `settings.gradle`:

```groovy
rootProject.name = 'scheduledtasks-demo'
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

application {
    mainClass = 'example.scheduling.SchedulerApplication'
}
```

The `application` plugin provides the `run` task; Boot's BOM aligns dependency versions. The two starters provide the HTTP server and Actuator. This example runs with Gradle because the Java code requires Spring libraries on the classpath.

Contents of `src/main/java/example/scheduling/SchedulerApplication.java`:

```java
package example.scheduling;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class SchedulerApplication {
    public static void main(String[] args) {
        SpringApplication.run(SchedulerApplication.class, args);
    }
}
```

Contents of `src/main/java/example/scheduling/DemoJobs.java`:

```java
package example.scheduling;

import java.util.concurrent.TimeUnit;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DemoJobs {

    @Scheduled(cron = "0 * * * * *", zone = "Asia/Ho_Chi_Minh")
    public void createMinuteReport() {
        System.out.println("minute-report");
    }

    @Scheduled(fixedDelay = 7, initialDelay = 2, timeUnit = TimeUnit.SECONDS)
    public void cleanTemporaryData() {
        System.out.println("cleanup");
    }

    @Scheduled(fixedRateString = "${demo.cache-rate-ms}", initialDelay = 3000)
    public void refreshCache() {
        System.out.println("cache-refresh");
    }
}
```

The methods take no parameters and return `void`. `DemoJobs` lies within the application class's bean scanning scope. `@EnableScheduling` activates `@Scheduled` processing; adding Actuator alone does not replace this step. The default unit for numeric values in `@Scheduled` is milliseconds; `timeUnit` changes the unit of the corresponding interval attributes. [`@Scheduled` contract](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html)

### 3.2. Allowing Endpoint Access in the Practice Environment

Contents of `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,scheduledtasks
demo.cache-rate-ms=10000
```

In Boot 3.3, distinguish between **enabling an endpoint** and **exposing an endpoint over HTTP**. `scheduledtasks` is enabled by default, but HTTP only exposes `health` by default. If the application sets `management.endpoints.enabled-by-default=false`, you must add `management.endpoint.scheduledtasks.enabled=true`; `exposure.exclude` takes precedence over `include`. [Endpoint enablement and exposure rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

The practice project does not add Spring Security and listens only on the loopback address. In production systems, restrict access to schedule information with proper security and network rules; class and method names can reveal internal structure. When Spring Security is present, authentication rules also depend on the active `SecurityFilterChain`. [Actuator Security](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security)

### 3.3. Running the Application and Sending a Request

In the practice project directory, with `gradle` 8.5 installed and JDK 21 available:

```shell
gradle run
```

If the project already has a corresponding Gradle Wrapper, use `./gradlew run` on supported shells or `.\gradlew.bat run` on Windows. Keep the process running and open a second terminal:

```shell
curl -i http://127.0.0.1:8080/actuator/scheduledtasks
```

In PowerShell, use `curl.exe` if `curl` is mapped to another command.

Expected response body for this example, formatted with indentation for readability:

```json
{
  "cron": [
    {
      "runnable": {
        "target": "example.scheduling.DemoJobs.createMinuteReport"
      },
      "expression": "0 * * * * *"
    }
  ],
  "fixedDelay": [
    {
      "runnable": {
        "target": "example.scheduling.DemoJobs.cleanTemporaryData"
      },
      "initialDelay": 2000,
      "interval": 7000
    }
  ],
  "fixedRate": [
    {
      "runnable": {
        "target": "example.scheduling.DemoJobs.refreshCache"
      },
      "initialDelay": 3000,
      "interval": 10000
    }
  ],
  "custom": []
}
```

A successful read request returns HTTP `200`. JSON property order is not a pass/fail criterion. The numbers `2000`, `7000`, `3000`, and `10000` are expected values from the code and configuration above; you do not need to wait for the first task execution to read the registration info. The default path and response structure are described in [Boot 3.3 `scheduledtasks` API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/scheduledtasks.html).

The methods print `minute-report`, `cleanup`, and `cache-refresh` respectively. The console also shows startup logs; the order of task lines depends on startup timing and execution schedules. Therefore, do not use console line order to infer JSON element order.

## 4. Reading Each Group and Field

| Group/Field | How to Read |
| --- | --- |
| `cron` | Tasks governed by cron expressions. |
| `cron[].expression` | Expression determining execution times. |
| `fixedDelay` | Tasks that wait an interval after the previous run finishes. |
| `fixedRate` | Tasks with periods measured from expected start timestamps. |
| `initialDelay` | Initial delay, in milliseconds in the response. |
| `interval` | Interval, in milliseconds in the response. |
| `runnable.target` | Object/method being executed. |
| `custom[].trigger` | String describing a custom trigger condition. |

These are the groups of the Boot 3.3 REST contract; a group with no tasks can be an empty array. [Official response structure description](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/scheduledtasks.html#scheduledtasks.retrieving.response-structure)

### 4.1. Where Do `fixedDelay` and `fixedRate` Differ?

Using the example values and assuming each run takes exactly 2 seconds while the scheduler is not busy:

```text
fixedDelay: initialDelay=2s, interval=7s
start 2s -> end 4s -> wait 7s -> start 11s

fixedRate: initialDelay=3s, interval=10s
expected start timestamps: 3s, 13s, 23s, ...
```

This is an illustrative timeline measured from scheduling time, not a real-time precision guarantee. A busy machine or another task occupying the thread can make a run start late. `fixedRate` describes the expected cadence; that word alone is not enough to conclude that the same task will run concurrently/overlap.

In the default configuration without virtual threads enabled, Boot's auto-configured scheduler uses a single thread. A long-blocking job can delay other jobs even while the endpoint still displays the configured `interval`. `scheduledtasks` does not expose thread pool size or execution lag to diagnose this cause directly. [Boot 3.3 scheduler configuration](https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html)

### 4.2. Cron and Time Zone

In the example, `0 * * * * *` has six fields: second, minute, hour, day of month, month, day of week. It selects second 0 of every minute. `zone` specifies the time zone used when resolving the schedule. Do not take a five-field OS cron expression and assume it can be copied directly into Spring. [CronExpression syntax](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/support/CronExpression.html) and [zone attribute](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html)

The Boot 3.3 response above provides `expression`; it does not provide a `zone` field or the next execution time. To check the time zone, verify against the actual annotation/configuration. Two machines returning the same cron expression can still have different local-time schedules if they use different time zones.

### 4.3. `custom` and Programmatically Registered Schedules

`ScheduledTaskRegistrar` supports programmatic registration, such as `addTriggerTask(Runnable, Trigger)`. When a task goes through the corresponding collection infrastructure, the endpoint can describe it even without `@Scheduled` on the method. [Task registration API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/config/ScheduledTaskRegistrar.html)

Do not equate every `TriggerTask` with the `custom` group: Boot has dedicated descriptions for `CronTrigger` and `PeriodicTrigger` running with fixed delay/fixed rate. `custom` is used for corresponding custom trigger conditions. The `trigger` string or lambda-generated class name is useful for diagnostics but is not a durable business identifier; avoid using them as long-term storage keys. [Endpoint descriptor classes](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/scheduling/ScheduledTasksEndpoint.html)

## 5. Extracting Necessary Information When Many Tasks Exist

Instead of visually scanning the entire JSON, you can filter with `jq` if the tool is installed. The following example is for Bash:

```bash
curl -fsS http://127.0.0.1:8080/actuator/scheduledtasks \
  | jq -r '.fixedRate[] | [.runnable.target, .initialDelay, .interval] | @tsv'
```

For the practice project, the filter stdout is a single line with three tab-separated columns:

```text
example.scheduling.DemoJobs.refreshCache	3000	10000
```

To verify precisely that a schedule received the expected configuration:

```bash
curl -fsS http://127.0.0.1:8080/actuator/scheduledtasks \
  | jq -e 'any(.fixedRate[]; .runnable.target == "example.scheduling.DemoJobs.refreshCache" and .interval == 10000)'
```

For the example, the output is `true` and `jq` exits with code `0`. If no matching element exists, the output is `false` and the exit code is `1`. The exit code rules for `-e` are described in the [jq manual](https://jqlang.org/manual/#invoking-jq). This check confirms the schedule descriptor has the expected value; to verify the job processed data, additional evidence from the job itself is required.

## 6. Limitations When Using the Endpoint for Diagnostics

### 6.1. Having a Schedule and Having Results Are Different Evidence

The Boot 3.3 response describes schedules; it does not provide success/failure history, total run count, per-run duration, stack traces, or business status. For instance, the data cleanup method might be registered yet failing with database access errors.

In that situation, use `scheduledtasks` to confirm the exact task name and configuration; then cross-check logs, recorded metrics, and data outcomes. If you need to know where a running execution is stuck, use runtime evidence such as a thread dump appropriate to your access level. The schedule fields in this version are bounded by the [REST response contract](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/scheduledtasks.html).

### 6.2. Scope Is the Queried Application Instance

With multiple application instances, the response from one instance is not a cluster-wide inventory. If called through a load balancer, two calls may hit two different instances; identify the instance and deployment version before comparing.

The endpoint also does not create distributed locks or guarantee a job runs only once across the cluster. If each instance registers the same schedule, you must design job coordination according to system requirements.

Jobs managed by Quartz have their own `quartz` endpoint. When investigating a Quartz Job, start with the dedicated Quartz tool rather than treating an empty `scheduledtasks` array as proof the Job does not exist. [Boot 3.3 Quartz API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/quartz.html)

### 6.3. Reading the Endpoint Does Not Change the Schedule

Sending `GET /actuator/scheduledtasks` only reads descriptions. This API does not provide commands to trigger a task immediately, pause it, or change cron expressions. Nor should you assume editing an external property has already rescheduled the task: verify the configuration reload and task re-registration mechanism your application actually implements. [Endpoint read operation](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/scheduling/ScheduledTasksEndpoint.html)

## 7. Symptom-Based Troubleshooting

| Symptom | Next Check |
| --- | --- |
| HTTP 404 | Check port, base path, endpoint enablement, and HTTP exposure configuration. |
| HTTP 401 or 403 | Check authentication, caller permissions, and active security filter chain. |
| HTTP 200 but all groups are empty | Check `@EnableScheduling`, whether beans are scanned, profile/conditional bean creation, and schedule registration source. |
| Task name present but no effect observed | Search the task's own logs, dependency errors, and data evidence; check thread starvation/waiting. |
| Interval differs from expectation | Cross-check units, resolved properties, active profile, and deployed version. |
| Two calls return different lists | Check whether you queried the same instance/same deployment configuration. |

HTTP 404 has several causes, so check each layer before changing Java code. If you changed `management.endpoints.web.base-path`, use the new path; if there is a separate management port, send the request to that port. The default API uses the `/actuator` prefix. [Actuator URL rules](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/index.html)

When results are empty, start by asking "where was the task registered?" An object instantiated manually with `new DemoJobs()` outside bean management will not have its annotations processed like the bean in the example. A cron set to `-` also indicates a disabled schedule in Spring; do not confuse this with the HTTP endpoint being disabled. [Cron processing and disabling rules](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html)

## 8. Practice and Self-Check

Perform step by step on the standalone project:

1. Run the application, read the endpoint, and locate all three `DemoJobs` methods in their correct groups.
2. Change `demo.cache-rate-ms` to `15000`, stop and restart the application. Verify `refreshCache`'s `fixedRate` has `interval=15000`; `initialDelay` remains `3000`.
3. Remove `@EnableScheduling`, restart, and read the response. For this specific project, the endpoint remains accessible, but the three annotation-registered schedules are gone.
4. Add `@EnableScheduling` back, restart, and verify the list is restored.
5. Remove `scheduledtasks` from `management.endpoints.web.exposure.include`, restart, and call the endpoint. With the example config, that path returns 404, while the tasks may continue printing their lines.

If you can explain the following three outcomes, you have grasped the core of the lesson:

- `fixedDelay.interval=7000` means waiting 7 seconds after the previous run finishes, not a promise to start strictly every 7 seconds.
- `fixedRate.interval=10000` comes from the resolved property in the application, no longer the string `${demo.cache-rate-ms}`.
- A task appearing in the response indicates the infrastructure provided its registration descriptor; the business outcome of each run must be verified with execution evidence.
