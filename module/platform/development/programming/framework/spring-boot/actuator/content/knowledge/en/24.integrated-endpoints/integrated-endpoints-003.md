# Reading Quartz Jobs, Triggers, and Masked Data

## 1. Understanding Jobs, Triggers, and Data Properly

When a report is not generated on time, there are at least three distinct questions: has the job been registered, which schedule will trigger the job, and what data does the job receive? Spring Boot Actuator's `quartz` endpoint helps inspect information from the Quartz Scheduler used by the application.

In Quartz, concepts are clearly separated:

| Concept | Role | Example in this article |
| --- | --- | --- |
| `Job` | Code that performs the work via the `execute` method. | `ReportJob` |
| `JobDetail` | Defines a specific job: key, execution class, and data. | Group `reporting`, name `report` |
| `Trigger` | Schedule determining when to fire the job. | Every 30 seconds or top of each minute |
| `JobDataMap` | Data attached to a job definition or trigger. | `channel`, `apiToken` |
| `Scheduler` | Component that manages and executes Quartz registrations. | Scheduler configured by Boot |

One job can be fired by multiple triggers; one trigger points to one job. Keys are formed from **group and name**, so knowing only the name is not enough to identify the exact object. A trigger's group can also differ from the job's group. [Quartz: Jobs, Triggers, and Identities](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/tutorial-lesson-02.html)

The scope of this article is **reading the `quartz` endpoint on Spring Boot 3.3.x**, including how to interpret values replaced with `******`. The examples use Java 21 and Boot `3.3.13` to provide a concrete version reference.

## 2. Requirements to Read the Endpoint

The application needs Actuator, Quartz, and a properly configured `Scheduler`. When using `spring-boot-starter-quartz`, Boot can auto-configure a `Scheduler` via `SchedulerFactoryBean`; `JobDetail` and `Trigger` beans are registered into the scheduler. By default, the job store is in-memory. [Boot 3.3 Quartz integration](https://docs.spring.io/spring-boot/3.3/reference/io/quartz.html)

Three layers must be distinguished:

1. **Presence:** the application has Quartz infrastructure for the endpoint to observe.
2. **Accessibility:** the endpoint is enabled, exposed over HTTP, and the caller passes access control.
3. **Raw value visibility:** the sanitization policy allows the caller to view `data` or only shows `******`.

Being able to read the JSON does not mean you can view the raw data. Conversely, changing the value-display policy does not automatically expose the endpoint over HTTP.

## 3. Standalone Practice Project

### 3.1. Creating the Structure and Gradle Configuration

Prepare JDK 21 and Gradle 8.5. Create the following files in a separate practice project:

```text
quartz-read-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/sample/quartz/
    │   ├── QuartzReadApplication.java
    │   ├── ReportJob.java
    │   └── QuartzJobs.java
    └── resources/application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'quartz-read-demo'
```

`build.gradle`:

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
    implementation 'org.springframework.boot:spring-boot-starter-quartz'
}

application {
    mainClass = 'sample.quartz.QuartzReadApplication'
}
```

The `application` plugin provides the run command; Boot's BOM aligns library versions. The project uses memory to store schedules, so no database configuration is needed for this experiment.

### 3.2. Startup Class and Job Code

`src/main/java/sample/quartz/QuartzReadApplication.java`:

```java
package sample.quartz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QuartzReadApplication {
    public static void main(String[] args) {
        SpringApplication.run(QuartzReadApplication.class, args);
    }
}
```

`src/main/java/sample/quartz/ReportJob.java`:

```java
package sample.quartz;

import org.quartz.Job;
import org.quartz.JobExecutionContext;

public class ReportJob implements Job {
    @Override
    public void execute(JobExecutionContext context) {
        String channel = context.getMergedJobDataMap().getString("channel");
        System.out.println("report:" + channel);
    }
}
```

`JobExecutionContext.getMergedJobDataMap()` merges data from the job and the firing trigger. On key collision, the value from the trigger takes precedence. The job detail endpoint and trigger detail endpoint show the two separate data sources, whereas the code above reads the merged data for a single execution. [JobExecutionContext Javadoc](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/JobExecutionContext.html)

### 3.3. One Job, Two Triggers

`src/main/java/sample/quartz/QuartzJobs.java`:

```java
package sample.quartz;

import java.util.TimeZone;
import org.quartz.CronScheduleBuilder;
import org.quartz.CronTrigger;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.SimpleScheduleBuilder;
import org.quartz.SimpleTrigger;
import org.quartz.TriggerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class QuartzJobs {

    @Bean
    public JobDetail reportJob() {
        return JobBuilder.newJob(ReportJob.class)
                .withIdentity("report", "reporting")
                .withDescription("Creates a demo report")
                .usingJobData("channel", "job-default")
                .usingJobData("apiToken", "demo-token-not-a-secret")
                .storeDurably()
                .build();
    }

    @Bean
    public SimpleTrigger every30Seconds(JobDetail reportJob) {
        return TriggerBuilder.newTrigger()
                .withIdentity("every30Seconds", "ops")
                .forJob(reportJob)
                .usingJobData("channel", "simple-trigger")
                .startNow()
                .withSchedule(SimpleScheduleBuilder.simpleSchedule()
                        .withIntervalInSeconds(30)
                        .repeatForever())
                .build();
    }

    @Bean
    public CronTrigger minuteReport(JobDetail reportJob) {
        return TriggerBuilder.newTrigger()
                .withIdentity("minuteReport", "calendar")
                .forJob(reportJob)
                .usingJobData("source", "minute-clock")
                .withSchedule(CronScheduleBuilder.cronSchedule("0 * * * * ?")
                        .inTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh")))
                .build();
    }
}
```

The `apiToken` value is dummy data to observe data masking. The job code only prints `channel`.

Created identifiers:

```text
JobKey: reporting / report
    <- TriggerKey: ops / every30Seconds
    <- TriggerKey: calendar / minuteReport
```

`storeDurably()` keeps the job definition when no triggers reference it anymore. It does not turn an in-memory store into a store that persists across restarts; choosing the storage backend and keeping an unreferenced job are two separate decisions. [JobDetail contract](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/JobDetail.html)

### 3.4. Exposing the Endpoint for Local Experimentation

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,quartz
management.endpoint.quartz.show-values=never
```

`quartz` is enabled by default in Boot 3.3, but HTTP only exposes `health` by default. If the application disabled all endpoints by default, you must enable this one explicitly with `management.endpoint.quartz.enabled=true`. `exposure.exclude` takes precedence over `include`. [Endpoint enablement and exposure rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

The practice project does not add Spring Security and listens only on loopback. When applying to a production system, configure endpoint access permissions according to the application's security model; masked data can still expose class names, job names, key names, and execution times.

In the project directory, using installed Gradle 8.5:

```shell
gradle run
```

If an appropriate Gradle Wrapper is present, you can use `./gradlew run` or `.\gradlew.bat run`. Once the application starts, keep the process running to send read requests from another terminal.

With trigger `ops/every30Seconds`, each job invocation prints:

```text
report:simple-trigger
```

With trigger `calendar/minuteReport`, each job invocation prints:

```text
report:job-default
```

The second output uses the job's data because the cron trigger does not redefine `channel`. The console also contains startup logs; timing and interleaving of lines depend on execution schedules.

## 4. Navigating from Lists to the Exact Object

All requests below use **GET**. In PowerShell, use `curl.exe` if `curl` points to another command.

| Path after `/actuator/quartz` | Information to Read |
| --- | --- |
| None | Job groups and trigger groups |
| `/jobs` | Job names by group |
| `/triggers` | Trigger names by group |
| `/jobs/{group}` | Jobs in a group |
| `/triggers/{group}` | Triggers in a group |
| `/jobs/{group}/{name}` | Details of one job and its associated triggers |
| `/triggers/{group}/{name}` | Details of one trigger |

These are the read paths of the [Quartz API in Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/quartz.html). When changing the base path or management port, adjust the URL accordingly.

### 4.1. Checking Groups First

```shell
curl -i http://127.0.0.1:8080/actuator/quartz
```

Expected response body of the practice project:

```json
{
  "jobs": {
    "groups": ["reporting"]
  },
  "triggers": {
    "groups": ["calendar", "ops"]
  }
}
```

Do not rely on group order to determine meaning. `reporting` is a job group; `calendar` and `ops` are two trigger groups. Both use the same word `groups`, but under two different data branches.

### 4.2. Viewing Names and Job–Trigger Relationships

```shell
curl -i http://127.0.0.1:8080/actuator/quartz/jobs
curl -i http://127.0.0.1:8080/actuator/quartz/triggers
curl -i http://127.0.0.1:8080/actuator/quartz/jobs/reporting
curl -i http://127.0.0.1:8080/actuator/quartz/triggers/ops
```

The `/jobs` response has the following branch:

```json
{
  "groups": {
    "reporting": {
      "jobs": ["report"]
    }
  }
}
```

Continue reading the specific job:

```shell
curl -i http://127.0.0.1:8080/actuator/quartz/jobs/reporting/report
```

Notable stable fields are excerpted as follows; the full response also includes firing times inside each element of `triggers`:

```json
{
  "group": "reporting",
  "name": "report",
  "description": "Creates a demo report",
  "className": "sample.quartz.ReportJob",
  "durable": true,
  "requestRecovery": false,
  "data": {
    "channel": "******",
    "apiToken": "******"
  },
  "triggers": [
    {"group": "ops", "name": "every30Seconds"},
    {"group": "calendar", "name": "minuteReport"}
  ]
}
```

This is an intentional excerpt, not the verbatim full JSON. Trigger order depends on when it is read. The job definition tells you the execution class; the two trigger keys lead you to the exact schedules to inspect.

## 5. Reading Job and Trigger Details

### 5.1. What Can Be Concluded from the Job

In the example, `className` points to `sample.quartz.ReportJob`; the job's key is `reporting/report`. `data` is the data attached to `JobDetail`, and the `triggers` list shows the schedules linked to the job.

Two flags that are frequently misunderstood:

- `durable=true`: the job can be retained when no triggers reference it. To know whether it survives a restart, you must check the storage backend type.
- `requestRecovery=true`: requests Quartz's recovery mechanism to consider re-executing when a crash recovery/failover situation occurs. This is not a configuration to auto-retry every business exception.

The meaning of both flags comes from the [JobDetail contract](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/JobDetail.html). In the example, `requestRecovery` keeps its default value `false`.

`triggers: []` alone does not prove the job definition is broken. A retained job may simply be waiting for a new schedule to be attached. Check the configuration intent before concluding.

### 5.2. Reading SimpleTrigger

```shell
curl -i http://127.0.0.1:8080/actuator/quartz/triggers/ops/every30Seconds
```

The stable portion of the response is excerpted as follows:

```json
{
  "group": "ops",
  "name": "every30Seconds",
  "type": "simple",
  "data": {
    "channel": "******"
  },
  "simple": {
    "interval": 30000,
    "repeatCount": -1
  }
}
```

The full response also contains `state`, timestamps, and `simple.timesTriggered`. How to read the `simple` section:

- `interval=30000`: repeat interval is 30,000 milliseconds.
- `repeatCount=-1`: repeats indefinitely in the example configuration.
- `timesTriggered`: number of times the trigger has fired; this value changes depending on when it is read.

This is information about the trigger, not a counter of successful reports. If a finite repeat count of `2` is configured, the schedule has one initial firing and two repeats, totaling three expected firings when nothing else alters the schedule. [SimpleTrigger API](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/SimpleTrigger.html)

Do not use `timesTriggered` as a long-term business audit history; it belongs to the current trigger and can change when the trigger is replaced or the schedule is re-initialized.

### 5.3. Reading CronTrigger

```shell
curl -i http://127.0.0.1:8080/actuator/quartz/triggers/calendar/minuteReport
```

The cron description of the practice project:

```json
{
  "type": "cron",
  "data": {
    "source": "******"
  },
  "cron": {
    "expression": "0 * * * * ?",
    "timeZone": "Asia/Ho_Chi_Minh"
  }
}
```

Here, `expression` selects second 0 of every minute. Read `timeZone` as well when analyzing schedules in local time. The time zone used to resolve the schedule and the UTC offset in returned timestamp strings are two pieces of information that must be distinguished when comparing.

Quartz also has `dailyTimeInterval`, `calendarInterval`, and `custom` trigger types. When reading detailed responses, use `type` to select the right object containing type-specific attributes; do not apply the `simple` structure to every type. [Boot 3.3 trigger response types](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/quartz.html)

### 5.4. Reading Timestamps and State Without Over-Inferring

| Field | Question It Helps Answer |
| --- | --- |
| `startTime`, `endTime` | When does the schedule take effect and stop repeating? |
| `previousFireTime` | When was the previous firing, if any? |
| `nextFireTime` | When is the next firing expected to occur? |
| `priority` | What is the priority when triggers share the same fire time? |
| `calendarName` | Is any Quartz Calendar exclusion schedule attached? |

Conditional fields may be absent when they do not yet have a value. A new trigger that has never fired may not have `previousFireTime`; an exhausted schedule may no longer have `nextFireTime`. Having a previous fire timestamp does not prove that run completed successfully. Timestamps reflect trigger information at the moment of observation. [Trigger API](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/Trigger.html)

`state` is the state of the **trigger**, not the business outcome of the job. Quartz-defined values include `NONE`, `NORMAL`, `PAUSED`, `COMPLETE`, `ERROR`, `BLOCKED`. [TriggerState](https://www.quartz-scheduler.org/api/2.3.0/org/quartz/Trigger.TriggerState.html)

How to use them in diagnostics:

- `NORMAL`: continue cross-checking expected timestamps and execution evidence; do not automatically conclude the job is currently running.
- `PAUSED`: check whether the schedule or group was intentionally paused.
- `COMPLETE`: check whether the schedule exhausted its fire count or reached its time limit; do not treat this state name as certification of successful business processing.
- `ERROR`: investigate errors in the scheduling mechanism and related logs; the response does not provide the full exception cause.
- `BLOCKED`: check execution blocking conditions, such as a job configured against concurrent execution already having another run in progress.

The endpoint does not replace execution history, logs, or business metrics. When `nextFireTime` differs from expectations, also check time zone, effective range, exclusion calendars, and misfire handling.

## 6. Understanding Masked Data

### 6.1. What Does `******` Mean?

With `management.endpoint.quartz.show-values=never`, values inside job/trigger data are replaced with `******` when returned by the endpoint. Default masking is not based solely on password-like key names. Therefore, `channel`, `source`, and `apiToken` in the example are all masked. The default value of this property is `never`. [Quartz endpoint properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#application-properties.actuator.management.endpoint.quartz.show-values)

From a masked response, you can still tell **which keys are present**, but you cannot conclude whether two original values are equal or whether an original value is empty. For example, `channel` in job data and `channel` in trigger data both display `******`, even though the example assigned two different strings.

Masking is a transformation at the **management output layer**. It does not encrypt the Quartz store, does not modify the underlying `JobDataMap`, and does not guarantee other logging paths also mask the data. Evidence right inside the experiment: the endpoint shows `******`, while `execute` still reads the real `channel` string to print output.

### 6.2. Three Display Modes

| `management.endpoint.quartz.show-values` | How Raw Values Are Displayed |
| --- | --- |
| `never` | Always mask values. |
| `when-authorized` | Only allow qualified callers to view raw values. |
| `always` | Allow everyone who can access the endpoint to view raw values, except what custom sanitizing functions still mask. |

A custom `SanitizingFunction` can still mask values it handles, even when the policy allows viewing raw data. The display policy is not a way to bypass those sanitizing functions. [Actuator data sanitization mechanism](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization)

To require a specific role on an **application that already has HTTP authentication and endpoint access control configured**, you can use:

```properties
management.endpoint.quartz.show-values=when-authorized
management.endpoint.quartz.roles=QUARTZ_ADMIN
```

This snippet only illustrates the data-viewing policy. It does not create users or configure Spring Security. `roles` is the list of roles used to decide raw-value visibility; when the list is empty, all authenticated users can view values under `when-authorized` mode. [Quartz roles property](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#application-properties.actuator.management.endpoint.quartz.roles)

Therefore, two decisions must be evaluated in strict order:

```text
Is the caller allowed to access the endpoint?
    -> if no: security mechanism rejects the request
    -> if yes: evaluate show-values policy and roles
        -> qualified: view values not masked by custom functions
        -> not qualified: may still receive JSON with masked data
```

For example, if security allows an account to read the endpoint but the account lacks `QUARTZ_ADMIN`, `when-authorized` mode can still return HTTP 200 with `******` values. If security blocks read access upfront, the request receives a denial response instead of reaching this display step.

### 6.3. Observing Data from Both Sources

When viewing raw values is permitted and no custom sanitizing function applies, the `data` sections of the example show:

```text
GET .../jobs/reporting/report
  channel = job-default
  apiToken = demo-token-not-a-secret

GET .../triggers/ops/every30Seconds
  channel = simple-trigger

GET .../triggers/calendar/minuteReport
  source = minute-clock
```

The lines above illustrate the data relationship, not verbatim `curl` stdout. They explain why the job reads `simple-trigger` when SimpleTrigger fires, but reads `job-default` when CronTrigger fires.

In a real environment, expose only the values needed for diagnostics to personnel with appropriate permissions. Having permission to read raw data does not make copying it into logs, screenshots, or public reports appropriate.

## 7. Symptom-Based Troubleshooting

| Symptom | Next Check |
| --- | --- |
| 404 at `/actuator/quartz` | Right application, port/base path, Quartz infrastructure, endpoint enabled, and HTTP exposure configured? |
| Group found but expected object missing | Using the exact group and name of the job/trigger? |
| 401 or 403 | How are HTTP endpoint authentication and authorization configured? |
| 200 but `data` is all `******` | Check `show-values`, caller roles, and custom sanitizing functions. |
| Job present but no reports produced | Cross-check triggers, timestamps, state, logs, and data outcomes. |
| Dynamic registrations lost after restart | Check whether using in-memory store or JDBC and re-registration logic. |
| `previousFireTime` present but processing failed | Read run logs/history; fire timestamp is not a success result. |

For group/object names containing special characters, URL-encode each path segment properly. Do not drop the group and try by name alone because that can point the investigation to a different object.

When deploying multiple application instances, identify which scheduler you are reading. One response does not automatically describe all independent schedules across every instance. If using Quartz with JDBC and cluster configuration, verify shared store configuration and actual clustering before inferring coordination behavior.

In the practice project, the in-memory store is recreated when the application runs. Configuration beans recreate the job and triggers, whereas dynamic changes outside that configuration are not retained automatically. `JobDetail`'s `durable=true` does not change this fact.

## 8. Verification Exercise

1. Run the project, call the root endpoint, and confirm job group `reporting` and two trigger groups `ops`, `calendar`.
2. Read `reporting/report` details, follow both trigger keys, and check the corresponding `simple`/`cron` types.
3. Verify SimpleTrigger has `interval=30000`, `repeatCount=-1`; cron has expression `0 * * * * ?` and time zone `Asia/Ho_Chi_Minh`.
4. Keep `show-values=never`, read data from the job and both triggers. Explain why an ordinary key like `channel` is also masked.
5. Check the console: each time SimpleTrigger fires, the job prints `report:simple-trigger`; each time CronTrigger fires, it prints `report:job-default`. Explain the trigger data precedence rule.
6. Change the repeat interval in code from 30 seconds to 45 seconds, stop and restart. Verify `simple.interval=45000` and continue verifying data remains masked.

If you need to test the raw-value display policy in an authenticated environment, test with two accounts both allowed to read the endpoint but holding different roles. Compare both the HTTP status code and the `data` section, then restore the configuration to the appropriate policy afterward.

Self-check questions:

- Why does one job have two triggers but only one `JobDetail`?
- Does `durable=true` guarantee schedules remain intact after shutting down the JVM?
- Does `previousFireTime` prove the report was generated successfully?
- Are two values both showing `******` necessarily equal?
- Can everyone who can read the endpoint necessarily see raw data?

Answers should be grounded in job–trigger relationships, storage backend type, execution evidence, and data display policy; a state name or masked string does not substitute for that evidence.
