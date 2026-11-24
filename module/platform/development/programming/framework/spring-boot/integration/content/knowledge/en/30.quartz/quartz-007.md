# `spring.quartz.*` and `SchedulerFactoryBeanCustomizer`

In Spring Boot Integration, many integration tasks must run on a schedule: reconciling partner transactions every 5 minutes, sweeping outbox records, syncing data from external systems, or cleaning up stale processing states. **Quartz** provides `Job` (the work to do), `JobDetail` (job identity and configuration), `Trigger` (when to run), and `Scheduler` (the coordinator). Spring Boot connects these components via `SchedulerFactoryBean`.

This lesson focuses on two points of control for the scheduler: **`spring.quartz.*` properties** for declarative configuration and **`SchedulerFactoryBeanCustomizer`** for cases requiring direct customization of `SchedulerFactoryBean`. Examples are set in the context of integrating via APIs, databases, and processing flows that may be deployed across multiple instances.

## 1. How Does Spring Boot Create and Configure Quartz?

When the application includes the `spring-boot-starter-quartz` dependency, Spring Boot auto-configures a `Scheduler` via `SchedulerFactoryBean`. Beans of type `JobDetail`, `Trigger`, and `org.quartz.Calendar` are discovered and registered with the scheduler. You do not need to define your own `SchedulerFactoryBean` just to declare simple schedules.

~~~text
application.yml / environment variables
            |
            v
    spring.quartz.* ----------------------+
            |                             |
            v                             v
 QuartzProperties                SchedulerFactoryBeanCustomizer
            |                             |
            +----------> SchedulerFactoryBean
                              |
                    JobDetail + Trigger
                              |
                              v
                          Scheduler
                              |
                         runs Quartz Job
                              |
                 HTTP / Database / Outbox / Broker
~~~

An important distinction:

| Component | Answers Which Question | Where Configured? |
| --- | --- | --- |
| `Job` / `JobDetail` | Which business task runs, and under what identity? | Java bean or registered with `Scheduler` |
| `Trigger` | When does it run, by cron or repeat interval? | Java bean / Quartz API |
| `spring.quartz.*` | How does the scheduler start, use RAM or JDBC, or overwrite stored schedules? | `application.yml`, `application.properties`, environment variables |
| `spring.quartz.properties.*` | What are the native Quartz settings such as thread pool, cluster, misfire threshold? | Spring Boot configuration |
| `SchedulerFactoryBeanCustomizer` | Which factory characteristics need direct tuning, such as executor or listeners? | Java bean |

`spring.quartz.*` configures the **scheduler**; it does not replace `Trigger` definitions, individual job cron expressions, or business retry/idempotency mechanisms.

## 2. Important `spring.quartz.*` Properties

| Property | Typical Default | Meaning and Notes |
| --- | --- | --- |
| `spring.quartz.scheduler-name` | `quartzScheduler` | Scheduler name; must match across nodes in the same Quartz cluster |
| `spring.quartz.job-store-type` | `memory` | `memory` stores schedules in RAM; `jdbc` persists `JobDetail`/`Trigger` to a DB via Quartz tables |
| `spring.quartz.auto-startup` | `true` | Automatically starts the scheduler after initialization |
| `spring.quartz.startup-delay` | `0s` | Delays scheduler startup after initialization; does not replace readiness checks for downstream dependencies |
| `spring.quartz.wait-for-jobs-to-complete-on-shutdown` | `false` | Waits for running jobs to complete during scheduler shutdown; consider deployment shutdown timeouts |
| `spring.quartz.overwrite-existing-jobs` | `false` | Whether application-configured job/trigger definitions overwrite existing entries in the JDBC job store |
| `spring.quartz.jdbc.initialize-schema` | `embedded` | Controls Quartz table creation script execution: `embedded`, `always`, `never` |
| `spring.quartz.jdbc.schema` | Platform-specific Quartz script | Path to custom schema SQL script, useful when DDL adjustments are required |
| `spring.quartz.jdbc.platform` | Auto-detected | Selects the platform name for the `@@platform@@` placeholder in the schema path |
| `spring.quartz.jdbc.continue-on-error` | `true` | Whether to continue if schema initialization scripts fail; should not be used to hide migration errors |
| `spring.quartz.properties.*` | No extra map | Passes native `org.quartz.*` keys to Quartz; verify exact key names and units |

Defaults and supported keys may change across Spring Boot versions, so cross-check configuration metadata for your actual version when upgrading. There is no global `spring.quartz.cron` for all jobs: each task's schedule belongs to its `Trigger`.

### 2.1. Running a Single Instance in Memory

~~~yaml
spring:
  quartz:
    scheduler-name: integration-scheduler
    job-store-type: memory
    auto-startup: true
    startup-delay: 5s
    wait-for-jobs-to-complete-on-shutdown: true
    properties:
      "[org.quartz.threadPool.threadCount]": "6"
      "[org.quartz.jobStore.misfireThreshold]": "60000"
~~~

This configuration suits development environments or schedules that can be completely rebuilt at startup. After a restart, the in-memory job store loses prior state; Spring Boot re-registers `JobDetail` and `Trigger` beans. `startup-delay: 5s` only delays the scheduler; it does not guarantee partner APIs or brokers are ready.

In YAML, `properties` is a map forwarded to Quartz. Writing keys like `"[org.quartz.threadPool.threadCount]"` preserves the full dotted key name during Spring Boot binding. The value `60000` for `misfireThreshold` is in **milliseconds** (60 seconds), unlike the `5s` duration syntax of `startup-delay`.

### 2.2. Running Durably with JDBC JobStore

~~~yaml
spring:
  quartz:
    scheduler-name: integration-scheduler
    job-store-type: jdbc
    auto-startup: true
    overwrite-existing-jobs: false
    wait-for-jobs-to-complete-on-shutdown: true
    jdbc:
      initialize-schema: never
    properties:
      "[org.quartz.scheduler.instanceId]": AUTO
      "[org.quartz.jobStore.isClustered]": "true"
      "[org.quartz.jobStore.clusterCheckinInterval]": "20000"
      "[org.quartz.jobStore.misfireThreshold]": "60000"
      "[org.quartz.threadPool.threadCount]": "8"
~~~

For this configuration to work, the application must have a `DataSource` connected to a database containing `QRTZ_*` tables matching the exact version and dialect. Nodes in the same cluster must point to the **same Quartz tables**, share compatible cluster settings, and have distinct `instanceId` values; `AUTO` lets Quartz generate each instance identifier automatically. `isClustered=true` should only be used with JDBC job store, not `memory`. If running a single standalone instance, omit cluster settings rather than copying them blindly.

**Operational warning:** `spring.quartz.jdbc.initialize-schema=always` may run standard scripts containing drop-and-recreate table statements, wiping stored triggers and jobs on every startup. For environments requiring schedule persistence, manage Quartz DDL via migrations/DBA and set `initialize-schema: never`. The default `embedded` does not auto-create tables on production databases.

If Quartz must use a separate database or transaction manager, mark the corresponding bean with `@QuartzDataSource` or `@QuartzTransactionManager`. Spring Boot uses `@QuartzDataSource` for both the scheduler and schema initialization. Using these annotations is more consistent than calling `factory.setDataSource(...)` manually inside a customizer. These annotations live in the Quartz auto-configuration package of your Boot version.

### 2.3. Distinguishing Boot Properties from Native Quartz Properties

~~~properties
# Keys understood by Spring Boot and mapped to factory properties
spring.quartz.scheduler-name=integration-scheduler
spring.quartz.job-store-type=jdbc
spring.quartz.jdbc.initialize-schema=never

# Native Quartz keys forwarded into scheduler Properties
spring.quartz.properties.org.quartz.scheduler.instanceId=AUTO
spring.quartz.properties.org.quartz.jobStore.isClustered=true
spring.quartz.properties.org.quartz.threadPool.threadCount=8
~~~

Do not configure the same setting at both layers and guess which wins. For instance, if `scheduler-name` already sets the scheduler name, do not also set `org.quartz.scheduler.instanceName`. When Spring supplies the `DataSource` for JDBC job store, do not manually set `org.quartz.jobStore.class=org.quartz.impl.jdbcjobstore.JobStoreTX`: it can conflict with the Spring-managed `LocalDataSourceJobStore`.

## 3. What Problem Does `SchedulerFactoryBeanCustomizer` Solve?

`SchedulerFactoryBeanCustomizer` is a functional interface with the method:

~~~java
void customize(SchedulerFactoryBean schedulerFactoryBean);
~~~

Spring Boot invokes customizer beans while configuring `SchedulerFactoryBean`. It fits when you need factory setter APIs that `spring.quartz.*` properties cannot express directly, such as:

- Attaching a custom Spring-managed `Executor` via `setTaskExecutor(...)`.
- Registering `JobListener`, `TriggerListener`, or `SchedulerListener` for observability and auditing.
- Configuring a specialized `JobFactory` when the application has custom job instantiation/injection needs.
- Populating `SchedulerContext` for an intentionally shared object.

This remains a **factory configuration step before the scheduler starts**, distinct from injecting `org.quartz.Scheduler` and calling runtime job/trigger control APIs.

### 3.1. Example: Using a Dedicated Executor for Quartz

By default, a regular Spring Boot `Executor` bean does **not automatically** become Quartz's executor. To use a Spring-managed `ThreadPoolTaskExecutor`, define a customizer:

~~~java
import java.util.concurrent.Executor;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.quartz.SchedulerFactoryBeanCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class QuartzExecutorConfig {

    @Bean("integrationQuartzExecutor")
    ThreadPoolTaskExecutor integrationQuartzExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(40);
        executor.setThreadNamePrefix("quartz-integration-");
        return executor; // Spring manages bean initialization and shutdown.
    }

    @Bean
    SchedulerFactoryBeanCustomizer quartzExecutorCustomizer(
            @Qualifier("integrationQuartzExecutor") Executor executor) {
        return factory -> factory.setTaskExecutor(executor);
    }
}
~~~

> **Version compatibility:** the import `org.springframework.boot.autoconfigure.quartz.SchedulerFactoryBeanCustomizer` above is for Spring Boot **3.x**. In Spring Boot **4.x**, change it to `org.springframework.boot.quartz.autoconfigure.SchedulerFactoryBeanCustomizer`; the interface name and usage pattern stay the same. Check the package against your actual dependencies when copying examples.

`setTaskExecutor` tells Spring/Quartz to use that executor as the job execution backend. When using this approach, size the pool, queue capacity, downstream API/DB load, and rejection policy carefully. Do not try to tune thread counts via `org.quartz.threadPool.threadCount` expecting it to control Spring's `ThreadPoolTaskExecutor`. If you have no special executor requirements, configuring Quartz's default `SimpleThreadPool` via `spring.quartz.properties.org.quartz.threadPool.threadCount` is usually simpler.

### 3.2. Example: Registering a Listener to Observe Job Execution

Assuming the application has a bean implementing `org.quartz.JobListener` named `IntegrationJobListener`, register it globally for all jobs:

~~~java
@Bean
SchedulerFactoryBeanCustomizer integrationJobListenerCustomizer(
        IntegrationJobListener listener) {
    return factory -> factory.setGlobalJobListeners(listener);
}
~~~

Place this snippet inside the `@Configuration` class importing `SchedulerFactoryBeanCustomizer` and `@Bean` from the previous example. The listener can log `JobKey`, `fireInstanceId`, execution duration, outcome, and exceptions, linking correlation IDs to your observability system. If registering multiple listeners, pass them in a single `setGlobalJobListeners(...)` call so another customizer does not overwrite the list. Never put sensitive details, connections, or large business payloads into logs.

### 3.3. Choosing the Right Configuration Mechanism

| Need | Use |
| --- | --- |
| Rename scheduler, startup/shutdown, JDBC job store | `spring.quartz.*` |
| Tune `threadCount`, `misfireThreshold`, `isClustered` | `spring.quartz.properties.*` |
| Create a 5-minute periodic job or time-zoned cron | `JobDetail` and `Trigger` beans |
| Wire a Spring-managed executor or global listeners | `SchedulerFactoryBeanCustomizer` |
| Pause, fire immediately, or reschedule a running app's job | Inject `Scheduler` and call `pauseJob`, `triggerJob`, `rescheduleJob`... |
| Point Quartz at a dedicated database | `@QuartzDataSource`; and `@QuartzTransactionManager` if a separate transaction manager is needed |

## 4. Complete Integration Example: Partner Reconciliation Every 5 Minutes

An integration service calls a partner API to reconcile records stuck in `PENDING`. We need a fixed schedule, a job with a stable identity, protection against overlapping runs of the same `JobDetail`, and proper handling of missed runs.

### 4.1. Job Containing Business Delegation

~~~java
import org.quartz.DisallowConcurrentExecution;
import org.quartz.JobExecutionContext;
import org.quartz.JobExecutionException;
import org.springframework.scheduling.quartz.QuartzJobBean;

@DisallowConcurrentExecution
public class PartnerReconcileJob extends QuartzJobBean {

    private PartnerReconcileService partnerReconcileService;

    // Populated by Spring Bean JobFactory from the matching bean.
    public void setPartnerReconcileService(
            PartnerReconcileService partnerReconcileService) {
        this.partnerReconcileService = partnerReconcileService;
    }

    @Override
    protected void executeInternal(JobExecutionContext context)
            throws JobExecutionException {
        try {
            partnerReconcileService.reconcilePending();
        } catch (RuntimeException ex) {
            throw new JobExecutionException(
                    "Failed to reconcile partner data", ex);
        }
    }
}
~~~

`PartnerReconcileService` is an application-implemented business bean that selects a batch of unsynced records, calls an HTTP client with timeouts, updates status, and emits events per the data contract. Quartz decides **when to call**; HTTP retries, idempotency, transactions, and malformed data handling remain at the business layer.

`@DisallowConcurrentExecution` prevents concurrent runs of **the same `JobDetail`/`JobKey`** under Quartz rules. It does not lock all jobs sharing the same Java class, does not stop another service from touching the same records, and does not replace database unique constraints or partner idempotency keys.

### 4.2. Declaring `JobDetail` and Cron `Trigger`

~~~java
import java.util.TimeZone;

import org.quartz.CronScheduleBuilder;
import org.quartz.JobBuilder;
import org.quartz.JobDetail;
import org.quartz.Trigger;
import org.quartz.TriggerBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class PartnerReconcileSchedule {

    @Bean
    JobDetail partnerReconcileJobDetail() {
        return JobBuilder.newJob(PartnerReconcileJob.class)
                .withIdentity("partner-reconcile", "integration")
                .storeDurably()
                .build();
    }

    @Bean
    Trigger partnerReconcileTrigger(
            @Qualifier("partnerReconcileJobDetail") JobDetail jobDetail) {
        return TriggerBuilder.newTrigger()
                .forJob(jobDetail)
                .withIdentity("partner-reconcile-cron", "integration")
                .withSchedule(CronScheduleBuilder
                        .cronSchedule("0 0/5 * * * ?")
                        .inTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"))
                        .withMisfireHandlingInstructionDoNothing())
                .build();
    }
}
~~~

Quartz cron `0 0/5 * * * ?` means run at second 0 every 5 minutes. The `?` in the day-of-week field avoids specifying both day-of-month and day-of-week simultaneously. The time zone is bound explicitly to the `Trigger` rather than relying on the host server's default. For time zones with daylight saving time, design and test schedules across clock transitions.

`withMisfireHandlingInstructionDoNothing()` chooses to **skip missed firings** and wait for the next cron slot. This suits a reconciliation job that sweeps all `PENDING` records on every run. If business rules require catching up every historical period, you need a different strategy (such as `FireAndProceed`, a period state table, and a backfill job)—never assume a single catch-up firing covers every missed period.

### 4.3. Operational Flow

~~~mermaid
flowchart TD
    A[Spring Boot starts up] --> B[Read spring.quartz.*]
    B --> C[Create SchedulerFactoryBean]
    C --> D[Apply customizers]
    D --> E[Register JobDetail and Trigger]
    E --> F{Cron due?}
    F -- No --> F
    F -- Yes --> G[Quartz invokes PartnerReconcileJob]
    G --> H[Service reads PENDING records]
    H --> I[Call partner API with timeout]
    I --> J[Update result, idempotency, logs/metrics]
    J --> F
~~~

In a JDBC cluster, Quartz persists job/trigger data in a shared database and coordinates trigger acquisition across nodes. If one node shuts down, another node can pick up work via Quartz recovery/misfire rules; business logic must still tolerate an API call succeeding right before the process dies without recording the result.

## 5. Common Misconfiguration Scenarios

**1. Restart wipes all triggers.** If using `memory`, state exists only in RAM. If using `jdbc` with `initialize-schema: always` and default scripts, Quartz tables may be dropped and recreated. Clarify schedule persistence requirements before picking a job store; use DDL migrations and `never` in persistent environments.

**2. Changing cron in code leaves the JDBC schedule unchanged.** With `overwrite-existing-jobs=false`, schedules already persisted in the database are preserved. You can explicitly call `Scheduler.rescheduleJob(...)` via a controlled migration; only set `overwrite-existing-jobs=true` if startup configuration is intentionally meant to overwrite persisted jobs/triggers.

**3. Two pods unexpectedly run the same task.** Verify they genuinely share the same database and `QRTZ_*` tables, `scheduler-name`, `isClustered=true`, and distinct `instanceId`s. Two independent `memory` schedulers will both fire schedules; scaling replicas alone does not form a Quartz cluster.

**4. Setting `spring.task.execution.pool.*` does not change Quartz threads.** Spring's general async task pool is not Quartz's thread pool by default. Use `org.quartz.threadPool.threadCount` for Quartz's default pool, or explicitly pass a Spring executor via `setTaskExecutor(...)` in a customizer and size it deliberately.

**5. Overlapping runs, timeouts, or duplicate side effects.** Apply `@DisallowConcurrentExecution` scoped to the `JobKey`; enforce timeouts on HTTP clients; record request idempotency keys or use an outbox. Avoid holding a DB transaction open during slow HTTP calls without a strict transactional need.

**6. Jobs fire right after deploy before dependencies are ready.** Use `startup-delay`, or set `auto-startup=false` and call `Scheduler.start()` after readiness checks pass. Both approaches need scheduler state monitoring; never treat a fixed delay as a health check.

**7. Assuming job errors retry infinitely automatically.** `JobExecutionException` notifies Quartz of a failure; immediate refiring still depends on the `refireImmediately` flag, trigger behavior, and business policies. Design bounded retries, backoff, DLQs/error tables, and distinguish transient errors from permanent data errors.

## 6. Verifying Configuration and Observing Deployments

Key checkpoints to verify in live environments:

1. **Scheduler:** name, started/standby state, active job store, and thread pool metadata. Inject `Scheduler` and inspect `getMetaData()`; never assume JDBC is active from YAML alone.
2. **Persistence:** `QRTZ_*` tables exist and are accessible; restart the app and confirm `JobKey`/`TriggerKey` survive. With JDBC, test interrupting a running job mid-execution.
3. **Cluster:** run at least two instances against the same database, verify only one instance claims a given firing under normal conditions, then test failover. Monitor cluster check-ins, DB latency, and node clock skew.
4. **Misfires:** intentionally stop the scheduler across several cron slots and verify the chosen `DoNothing` or catch-up behavior matches requirements.
5. **Observability:** logs include `jobKey`, `triggerKey`, scheduled/actual fire times, duration, and outcome; metrics track errors, timeouts, backlogs, misfires, and active jobs. For integrations, link Quartz runs with idempotency/correlation IDs in HTTP, DB, or broker layers.

Example test checking schedule registration (with Spring context):

~~~java
@Autowired
Scheduler scheduler;

@Test
void partnerReconcileJobIsRegistered() throws SchedulerException {
    JobKey key = JobKey.jobKey("partner-reconcile", "integration");
    assertNotNull(scheduler.getJobDetail(key));
}
~~~

Required imports: `org.quartz.Scheduler`, `org.quartz.SchedulerException`, `org.quartz.JobKey`, `org.springframework.beans.factory.annotation.Autowired`, `org.junit.jupiter.api.Test`, and static `org.junit.jupiter.api.Assertions.assertNotNull`. When running tests that should not execute live jobs, set `spring.quartz.auto-startup=false` in the test profile. With a JDBC store, integration tests must point to an isolated database/schema so production schedules are never altered.

### Integration Design Reminders

- `spring.quartz.*` is where Spring Boot configures scheduler-level lifecycle, storage, and behavior.
- `spring.quartz.properties.*` passes native `org.quartz.*` properties to Quartz; watch units and avoid duplicating factory settings.
- `SchedulerFactoryBeanCustomizer` handles specialized factory setters, notably executors, listeners, and job factories, without creating a second scheduler.
- A JDBC cluster coordinates trigger firing across instances but **does not guarantee exactly-once business side effects**. Data contracts, idempotency, transactions, retries, and observability must still be designed across the integration flow.

## References

- [Spring Boot Reference — Quartz Scheduler](https://docs.spring.io/spring-boot/reference/io/quartz.html)
- [Spring Boot — Common Application Properties, Quartz group](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Boot 3.x API — SchedulerFactoryBeanCustomizer](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/quartz/SchedulerFactoryBeanCustomizer.html)
- [Spring Boot 4.x API — SchedulerFactoryBeanCustomizer](https://docs.spring.io/spring-boot/4.2/api/java/org/springframework/boot/quartz/autoconfigure/SchedulerFactoryBeanCustomizer.html)
- [Spring Framework API — SchedulerFactoryBean](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/quartz/SchedulerFactoryBean.html)
