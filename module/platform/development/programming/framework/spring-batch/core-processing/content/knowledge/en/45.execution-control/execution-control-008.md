# `JobRegistry`: Finding Jobs in Spring Batch

In a Spring Batch application with many jobs, the control layer usually should not depend directly on each individual `Job` bean: a scheduler receives the name `importOrders`, an operations page requests running `archiveLogs`, or a service needs to list launchable jobs. **`JobRegistry`** provides a central place to register and look up **job definitions present in the application** by name, enabling the control layer to work with a `Job` selected at runtime.

Conceptual illustration:

```text
Scheduler / CLI / API: "Run job importOrders"
                 |
                 v
           JobRegistry
          getJob("importOrders")
                 |
                 v
          Job importOrders
                 |
        +--------+---------+
        |                  |
        v                  v
    JobLauncher         JobOperator
   run(job, params)   manages execution
        |                  |
        +--------+---------+
                 v
          JobRepository
        persists JobExecution
```

**Key point:** `JobRegistry` helps **find a `Job` definition**; it does not store job run history and does not execute jobs itself. Launching jobs belongs to `JobLauncher`/`JobOperator`; `JobInstance`, `JobExecution`, and `StepExecution` history belongs to `JobRepository`, which can be queried through `JobExplorer`.

## 1. Distinguishing `JobRegistry` from Other Control Components

| Component | Answers the Question | Managed Data |
| --- | --- | --- |
| `Job` | Which steps/flows and rules make up this batch job? | Execution process definition |
| `JobRegistry` | Which job definitions can currently be found by name? | Jobs registered at runtime |
| `JobLauncher` | How do we launch a `Job` with `JobParameters`? | Initiating/coordinating execution |
| `JobOperator` | How do we operate jobs (start/stop/restart) via an admin API? | Control operations using multiple underlying Batch components |
| `JobRepository` | Which runs have been recorded and what are their statuses? | Persistent metadata for job/step executions |
| `JobExplorer` | How do we read back persisted metadata? | Querying `JobInstance`, `JobExecution`, `StepExecution` |
| `ApplicationContext` | Which Spring beans are defined in this context? | Spring bean lifecycle and dependencies |

Three scenarios illustrate the differences:

1. The `importOrders` job ran yesterday, yet the current application no longer registers that job definition. `JobExplorer` can still find its **history**, while `JobRegistry.getJob("importOrders")` cannot find a **definition** to re-run it.
2. The `archiveLogs` job was just added to the application context and registered. `JobRegistry` can immediately return that `Job`, even though zero `JobExecution` rows exist in the database.
3. Two runs of the same `Job` with different `JobParameters` have two `JobInstance`s; the registry still needs only one `Job` definition by name.

`JobRegistry` acts as a directory at the **runtime configuration level**. Never use it to determine whether a job completed or is running; obtain status from execution metadata.

## 2. The `JobRegistry` API in Spring Batch 5.2.x

In **Spring Batch 5.2.x**, `JobRegistry` lives in package `org.springframework.batch.core.configuration`. It extends the lookup interfaces `JobLocator` and `ListableJobLocator`.

Key methods:

| Method | Result | Notes |
| --- | --- | --- |
| `getJob(String name)` | Returns `Job` by name | Throws `NoSuchJobException` if missing |
| `getJobNames()` | Collection/set of registered names | Not the set of jobs that ever ran in the repository |
| `register(JobFactory factory)` | Registers a definition via a factory | Throws `DuplicateJobException` on duplicate names |
| `unregister(String jobName)` | Unregisters a job name | Does not delete `JobExecution` records |

The standard implementation is **`MapJobRegistry`** (`org.springframework.batch.core.configuration.support.MapJobRegistry`), storing a thread-safe in-memory mapping from job name to factory. In Spring Batch 5.2, `register(...)` accepts a **`JobFactory`**, not a `Job` directly. Once you have a `Job` instance, wrap it with `ReferenceJobFactory`.

Standalone example independent of a Spring application context:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.configuration.JobRegistry;
import org.springframework.batch.core.configuration.support.MapJobRegistry;
import org.springframework.batch.core.configuration.support.ReferenceJobFactory;
import org.springframework.batch.core.job.SimpleJob;
import org.springframework.batch.core.launch.NoSuchJobException;

import java.util.Set;

public class JobRegistryLookupExample {

    public static void main(String[] args) throws Exception {
        JobRegistry registry = new MapJobRegistry();

        // SimpleJob here only illustrates registration and lookup.
        // Real execution requires configuring steps and Batch infrastructure.
        Job importOrders = new SimpleJob("importOrders");
        Job archiveLogs = new SimpleJob("archiveLogs");

        registry.register(new ReferenceJobFactory(importOrders));
        registry.register(new ReferenceJobFactory(archiveLogs));

        Set<String> names = registry.getJobNames();
        System.out.println(names);  // Contains importOrders, archiveLogs.

        Job found = registry.getJob("importOrders");
        System.out.println(found.getName()); // importOrders

        registry.unregister("archiveLogs");
        System.out.println(registry.getJobNames()); // Only importOrders remains.

        try {
            registry.getJob("archiveLogs");
        } catch (NoSuchJobException ex) {
            System.out.println("Job is not registered: archiveLogs");
        }
    }
}
```

The snippet demonstrates **registering, looking up, listing, and unregistering**. No job is executed and no `JobRepository` is used. `getJobNames()` does not guarantee a deterministic display order; sort the names before displaying in a UI or CLI.

### Duplicate Name Errors on `register`

The registry enforces unique job names:

```java
JobRegistry registry = new MapJobRegistry();
Job first = new SimpleJob("importOrders");
Job another = new SimpleJob("importOrders");

registry.register(new ReferenceJobFactory(first));

// Throws DuplicateJobException because the name already exists:
registry.register(new ReferenceJobFactory(another));
```

`DuplicateJobException` is a runtime definition-registration error. It differs from `JobInstanceAlreadyCompleteException`, which pertains to the execution history of an already-completed `JobInstance` in `JobRepository`.

## 3. Configuring `JobRegistry` with `@EnableBatchProcessing`

In Spring Batch 5.2.x, configuration using `@EnableBatchProcessing` provides `JobRegistry` and infrastructure that registers singleton `Job`s into the registry. When an application already uses standard Batch configuration, normally **inject the existing registry** rather than creating a second `MapJobRegistry` and wondering why its job list is empty.

Example Spring configuration defining a minimal runnable job. This example assumes the application already configures a valid `DataSource`, `JobRepository`, and `PlatformTransactionManager` for Spring Batch:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.EnableBatchProcessing;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
@EnableBatchProcessing
public class ImportOrdersBatchConfig {

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager) {
        return new StepBuilder("importOrdersStep", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    System.out.println("Processing orders...");
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
    }

    @Bean
    public Job importOrdersJob(
            JobRepository jobRepository,
            Step importOrdersStep) {
        return new JobBuilder("importOrders", jobRepository)
                .start(importOrdersStep)
                .build();
    }
}
```

The Spring bean is named `importOrdersJob`, while the `Job` has the logical name **`importOrders`** set by `new JobBuilder("importOrders", ...)`. Because registration and group-naming mechanisms can affect exposed names, when controlling jobs via the registry check the **actual names returned by `getJobNames()`** and use them consistently in schedulers or APIs. In project configurations, keep bean names and job names clear to avoid confusion.

Reading the registry from a Spring bean:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.configuration.JobRegistry;
import org.springframework.batch.core.launch.NoSuchJobException;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class AvailableJobs {

    private final JobRegistry jobRegistry;

    public AvailableJobs(JobRegistry jobRegistry) {
        this.jobRegistry = jobRegistry;
    }

    public List<String> names() {
        return jobRegistry.getJobNames().stream()
                .sorted()
                .toList(); // Java 16+
    }

    public Job require(String name) throws NoSuchJobException {
        return jobRegistry.getJob(name);
    }
}
```

Typical lifecycle:

```text
Spring initializes application context
        |
        +--> Creates Job beans
        |
        +--> Registrar populates Job into JobRegistry
        |
        v
ApplicationContext ready
        |
        v
Service/scheduler calls getJobNames() or getJob(name)
```

In Spring Batch 5.2, the right mechanism for auto-registration is **`JobRegistrySmartInitializingSingleton`**: it runs after singletons are initialized, reducing premature bean creation issues. If the application does **not** use Batch infrastructure that pre-creates a registry and must configure it manually, you can declare:

```java
@Bean
JobRegistry jobRegistry() {
    return new MapJobRegistry();
}

@Bean
JobRegistrySmartInitializingSingleton jobRegistrar(JobRegistry jobRegistry) {
    return new JobRegistrySmartInitializingSingleton(jobRegistry);
}
```

The imports are `org.springframework.batch.core.configuration.support.MapJobRegistry` and `org.springframework.batch.core.configuration.support.JobRegistrySmartInitializingSingleton`. This applies to **contexts that do not already provide equivalent beans**; do not copy it verbatim into a context using `@EnableBatchProcessing` and accidentally create duplicate beans or duplicate job registrations. `JobRegistryBeanPostProcessor` is the legacy mechanism, **deprecated since Spring Batch 5.2**, and should not be used alongside `JobRegistrySmartInitializingSingleton`.

## 4. Looking Up by Name Before Running a Job

A practical *Execution control* scenario is a service receiving a job name from a scheduler or operations system. The service can use the registry to resolve the job, then invoke `JobLauncher` with explicit parameters:

```java
import java.time.LocalDate;
import java.util.Set;

import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.configuration.JobRegistry;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.stereotype.Service;

@Service
public class NamedJobDispatcher {

    private final JobRegistry registry;
    private final JobLauncher launcher;

    public NamedJobDispatcher(JobRegistry registry, JobLauncher launcher) {
        this.registry = registry;
        this.launcher = launcher;
    }

    // Spring Batch 5.2.x example.
    public JobExecution launch(String jobName, LocalDate businessDate)
            throws Exception {
        // Allow only jobs explicitly exposed through this interface.
        if (!Set.of("importOrders").contains(jobName)) {
            throw new IllegalArgumentException("Job is not allowed: " + jobName);
        }

        Job job = registry.getJob(jobName); // May throw NoSuchJobException.

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString())
                .toJobParameters();

        return launcher.run(job, parameters);
    }
}
```

From this example, responsibilities separate cleanly:

1. **Select job:** `getJob(jobName)` verifies whether the definition is registered.
2. **Identify the run:** `JobParameters` defines inputs and identifying values for `JobInstance`.
3. **Control launch:** `JobLauncher.run(...)` starts or coordinates execution and uses `JobRepository` to manage metadata.
4. **Monitor:** use the returned `JobExecution` or query via `JobExplorer`/`JobRepository`. If the launcher runs asynchronously, the returned `JobExecution` may not yet hold its final status.

The example uses `throws Exception` to keep focus on the registry's role. In real applications, handle specific Batch exceptions such as `NoSuchJobException`, `JobInstanceAlreadyCompleteException`, `JobExecutionAlreadyRunningException`, `JobRestartException`, and invalid-parameter errors per the control system's API contract.

Because job names may arrive from outside, **do not expose the entire registry as an endpoint allowing arbitrary launches**. A real operations API must enforce authorization, restrict the allowlist of launchable jobs, and validate `JobParameters`; a job existing in the registry does not prove the caller is allowed to run it.

### How Does Lookup Differ from Restart?

Suppose the `importOrders` job failed. To restart via a control API, two things are needed:

- The `Job` definition **must still be locatable** at runtime (e.g., from the registry).
- Metadata of the failed run **must still exist** in `JobRepository`, and the job/steps must be designed for restart.

If the job was removed from the registry while a failed execution still exists in the database, a name-based restart command may fail to find the definition to execute. Conversely, having only the definition in the registry cannot reconstruct checkpoints from a prior run.

## 5. Using `JobOperator` for Operational Control

When you need more operations than `JobLauncher.run(...)`—such as start, stop, restart, or viewing execution info—Spring Batch provides `JobOperator`.

In **Spring Batch 5.2.x**, several `JobOperator` APIs operate by job name:

```java
// Example in a service layer with JobOperator injected.
Set<String> available = jobOperator.getJobNames();

Properties parameters = new Properties();
parameters.setProperty("businessDate", "2025-01-15");

Long executionId = jobOperator.start("importOrders", parameters);
```

This snippet requires importing `java.util.Set`, `java.util.Properties`, and the `org.springframework.batch.core.launch.JobOperator` bean. How `Properties` are converted into `JobParameters` is defined by the corresponding API; if the application needs special data types or identifying flags, pass parameters formatted for your active version and converter. Wrap in `try/catch` or declare the exceptions thrown by `start(...)`.

In Spring Batch 5.2's default setup, `JobOperator` can use `JobRegistry` to resolve job names alongside `JobExplorer`, `JobRepository`, and `JobLauncher` for its operations. Consequently, **a job existing in `JobRepository` while missing from `JobRegistry`** is a classic cause to check when name-based `start`/`restart` fails.

> In Spring Batch 6.x, legacy `JobOperator` overloads such as `start(String, Properties)` are marked deprecated; use the control APIs taking `Job` and `JobParameters`, paired with `JobRegistry` to look up the `Job` when input starts as a name. Version details are in section 9.

## 6. Dynamic Registration and Independent Job Modules

A large Batch application can group multiple sets of jobs:

```text
Main ApplicationContext
  |
  +-- JobRegistry (central)
  |
  +-- Child context: sales
  |     +-- importOrders Job
  |     +-- reader, writer, step...
  |
  +-- Child context: finance
        +-- reconcilePayments Job
        +-- reader, writer, step...
```

Each child context can reuse **internal bean names** like `reader` or `writer` without collisions, while the central registry manages public jobs. Spring Batch 5.2 includes `AutomaticJobRegistrar` to create/manage child contexts via `ApplicationContextFactory` and `JobLoader`, registering jobs from those contexts.

This pattern helps when:

- Modules deploy independent job definitions plugged into a single control application.
- A group of jobs is loaded or unloaded with the lifecycle of a child application context.
- A system has many jobs and needs a consistent lookup point instead of manually scanning beans across contexts.

Do not treat `JobRegistry` as a distributed discovery service. `MapJobRegistry` is an **in-process / single-application-context registry**; one application instance registering a job does not sync that list to other instances. If different nodes deploy different jobs, the scheduler/gateway must route to the right node or rely on an external orchestrator.

With multi-group contexts, establish naming conventions to avoid `DuplicateJobException`. Group-naming mechanisms at the registration layer can distinguish job origins, yet **the name used to look up a job must match the actual registered name**—never assume a bean name or module label always equals the registry job name.

### Registration and Unregistration Lifecycle

```text
Context/module initialized
       |
       v
Job definition beans created
       |
       v
register(...) -> JobRegistry contains job name
       |
       v
Control layer looks up and launches when appropriate
       |
       v
Context/module shuts down or is unloaded
       |
       v
unregister(...) -> job name removed from registry
```

`unregister` only changes **runtime job definition lookup**. It does not delete history and does not issue a stop command to running jobs. To stop an active execution, use Spring Batch's stop control API and wait for the batch to process the stop signal. Never unregister a running job assuming that will roll back or cancel the process.

## 7. Testing Job Lookup and Error Handling

When testing only registration/lookup logic, a unit test can use `MapJobRegistry` directly with no database or real job execution. JUnit Jupiter example for **Spring Batch 5.2.x**:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.configuration.DuplicateJobException;
import org.springframework.batch.core.configuration.JobRegistry;
import org.springframework.batch.core.configuration.support.MapJobRegistry;
import org.springframework.batch.core.configuration.support.ReferenceJobFactory;
import org.springframework.batch.core.job.SimpleJob;
import org.springframework.batch.core.launch.NoSuchJobException;

import static org.junit.jupiter.api.Assertions.*;

class JobRegistryTest {

    @Test
    void findsJobByNameAndUnregistersIt() throws Exception {
        JobRegistry registry = new MapJobRegistry();
        Job job = new SimpleJob("importOrders");

        registry.register(new ReferenceJobFactory(job));

        assertTrue(registry.getJobNames().contains("importOrders"));
        assertSame(job, registry.getJob("importOrders"));

        registry.unregister("importOrders");

        assertFalse(registry.getJobNames().contains("importOrders"));
        assertThrows(NoSuchJobException.class,
                () -> registry.getJob("importOrders"));
    }

    @Test
    void rejectsDuplicateJobNames() throws Exception {
        JobRegistry registry = new MapJobRegistry();

        registry.register(
                new ReferenceJobFactory(new SimpleJob("importOrders")));

        assertThrows(DuplicateJobException.class, () ->
                registry.register(
                        new ReferenceJobFactory(new SimpleJob("importOrders"))));
    }
}
```

`SimpleJob` in the test only acts as a named holder to verify lookup. It lacks step configuration to run a meaningful Batch flow. When you need to test `JobLauncher` or `JobOperator` actually executing the right job, move to an integration test with real jobs/steps and a test `JobRepository`.

With a Spring context, another simple test is injecting `JobRegistry` and asserting expected names appear **after context initialization**. This catches missing auto-registrars, registering into the wrong registry, or job name conflicts.

Test scenarios to consider:

| Scenario | Expected Outcome |
| --- | --- |
| Registered name | Returns the matching `Job` definition |
| Non-existent name | Clear error or not-found value per the active version |
| Two jobs with the same name | Registration is rejected |
| Unregister then look up | No longer found |
| Context with multiple jobs | Lists all actually queryable names accurately |
| Launch job via service | Finds the right job, passes right `JobParameters`; status persisted in repository |

## 8. Common Issues When `JobRegistry` Cannot Find a Job

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `NoSuchJobException` in Spring Batch 5.x | Name is absent from registry | Print `getJobNames()` to verify actual names; confirm the job bean is registered |
| Registry is empty despite `Job` beans in Spring | Created a separate unpopulated `MapJobRegistry`, or registered in wrong context | Inject the Batch-provided registry; configure registrar in the right place |
| `DuplicateJobException` on startup | Two definitions share a name, or two registrars register the same job | Fix naming rules; avoid running duplicate registration mechanisms together |
| Bean name `importOrdersJob` works while `importOrders` does not, or vice versa | Confusion among Spring bean name, logical `Job` name, and group naming | Inspect `getJobNames()` output; standardize public names |
| Job has DB history but definition cannot be found | `JobRepository` holds metadata from an older deployment; current registry lacks the job | Check version/deployment and registration; restore a compatible definition if restart is needed |
| `JobInstanceAlreadyCompleteException` after finding the job | Re-running the same job name and identifying parameters of a completed instance | Distinguish definition lookup from `JobInstance` creation/restart policy |
| Job fails to run on the node receiving the request | This node's registry lacks a job deployed on a different node | Route/orchestrate to the node owning the definition; do not treat registry as a distributed store |
| Unregistered a job yet execution keeps running | Unregistering does not issue a stop signal | Use Batch's stop API; check execution status |
| Displayed list of names changes order | `getJobNames()` has no ordering contract | Sort names before rendering to UI/CLI |

To diagnose, check in order: **did the context load the job → is the registration mechanism active → is the injected registry the right instance → what is the exact name in the registry → does the remaining error belong to job launch or the repository**. Separating these checks avoids confusing configuration lookup errors with execution control errors.

## 9. Notable Differences Between Spring Batch 5.2 and 6.x

Spring Batch 6 changes the `JobRegistry` API, so lookup/registration code must match the target version.

| Aspect | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| `getJob(name)` when missing | Throws `NoSuchJobException` | Returns `null` (`@Nullable` API) |
| Manual registration | `register(JobFactory)`; typically `new ReferenceJobFactory(job)` | `register(Job)` directly |
| `JobLocator`/`ListableJobLocator` | Superinterfaces extended by `JobRegistry` | Legacy interfaces deprecated; prefer `JobRegistry` directly |
| `MapJobRegistry` | Requires a populator like `JobRegistrySmartInitializingSingleton` | Auto-registers `Job` beans in `ApplicationContext` via `SmartInitializingSingleton` |
| `JobRegistrySmartInitializingSingleton` | Replacement for `JobRegistryBeanPostProcessor` | Deprecated; usually only a `MapJobRegistry` bean is needed |
| `JobOperator.start(String, Properties)` | Supports name-based operations | Deprecated; prefer APIs accepting `Job` and `JobParameters` |

Example of manual lookup and registration in **Spring Batch 6.x**:

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.configuration.JobRegistry;
import org.springframework.batch.core.configuration.support.MapJobRegistry;
import org.springframework.batch.core.job.SimpleJob;

JobRegistry registry = new MapJobRegistry();
Job job = new SimpleJob("importOrders");

registry.register(job); // 6.x: accepts Job directly.

Job resolved = registry.getJob("importOrders");
if (resolved == null) {
    throw new IllegalArgumentException("Unknown job: importOrders");
}

System.out.println(resolved.getName());
```

This example only illustrates lookup; running a real job still requires step configuration and execution infrastructure. `SimpleJob` in Spring Batch 6 belongs to `org.springframework.batch.core.job.SimpleJob`; APIs of other Batch types may have moved packages or changed signatures, so follow your project's exact dependencies and documentation.

In Spring Batch 6, a `MapJobRegistry` inside a Spring context can automatically discover `Job` beans once singletons are ready. For a registry instantiated directly with `new` outside a Spring context as shown above, call `register(job)` manually because there is no Spring lifecycle to scan beans. If swapping in a custom `JobRegistry` implementation, ensure a compatible population mechanism as well.

**Do not copy 5.x code and only bump the dependency to 6.x**: `register(new ReferenceJobFactory(job))`, assuming `getJob` throws `NoSuchJobException`, or `JobRegistrySmartInitializingSingleton` configs from older examples may no longer apply. Separating version-specific code makes migration issues obvious.

## 10. Design Practices for the Execution Control Layer

When using `JobRegistry` in a multi-job batch orchestration app, keep the contract clear:

1. **Job name is a contract:** choose stable, unique, searchable names; publish the names returned by the registry. Renaming a job can impact schedulers and restart procedures.
2. **Register before controlling:** accept launch requests only after the context/registrar is ready; with dynamic registration, there may be a startup window before a job appears.
3. **Separate lookup from launch:** one method to locate the `Job` and another to validate/launch keeps error handling crisp.
4. **Do not use the registry as a monitoring store:** `STARTED`, `FAILED`, `COMPLETED` statuses, run history, and restarts come from `JobRepository`/`JobExplorer`.
5. **Do not confuse job name with instance:** the same job name can have many runs across different `JobParameters`.
6. **Restrict control permissions:** do not let callers pick arbitrary internal jobs just because they exist in the registry; authorize by target job and operational scenario.
7. **Track status for asynchronous runs:** the execution returned right when calling the launcher is not always the final state; read final outcomes from metadata.
8. **Manage registrations with lifecycle:** when unloading a module/child context, clean up registrations properly while managing active executions through separate controls.

## 11. References

- [Spring Batch 5.2 — Advanced Metadata Usage: JobRegistry, AutomaticJobRegistrar, JobOperator](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html)
- [Spring Batch 5.2 API — JobRegistry](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/configuration/JobRegistry.html)
- [Spring Batch 5.2 API — MapJobRegistry](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/configuration/support/MapJobRegistry.html)
- [Spring Batch 5.2 API — JobRegistrySmartInitializingSingleton](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/configuration/support/JobRegistrySmartInitializingSingleton.html)
- [Spring Batch 5.2 API — JobOperator](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/launch/JobOperator.html)
- [Spring Batch 6 — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html)
- [Spring Batch 6 API — JobRegistry](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/configuration/JobRegistry.html)
- [Spring Batch 6 API — MapJobRegistry](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/configuration/support/MapJobRegistry.html)

When a system needs to **find a job by name to drive execution control**, `JobRegistry` bridges Batch configuration and the operations layer. Use the registry to fetch available `Job` definitions, `JobLauncher`/`JobOperator` to run or manage executions, and `JobRepository`/`JobExplorer` to inspect real history. At the same time, distinguish Spring Batch 5.2 and 6.x APIs, because `getJob` and `register` themselves changed between the two versions.
