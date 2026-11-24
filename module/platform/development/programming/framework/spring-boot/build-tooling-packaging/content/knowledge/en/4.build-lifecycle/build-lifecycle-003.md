# Gradle's Task Model and Dependency Graph

## 1. Core mindset: Gradle executes a graph, not line-by-line sequentially through the build script

A **Task** is a unit of work in Gradle, such as `compileJava`, `test`, `jar`, `bootJar`, `check`, `build`, or a custom task for code generation, quality checks, packaging, and publishing artifacts. Each task has a name, a project path, a type, configuration, execution actions, relationships with other tasks, and input/output metadata if declared.

A **Task graph** is the set of tasks selected by Gradle for **a single build invocation**, plus the relationships that determine which tasks must appear and a valid order to run them. Gradle treats this as a **directed acyclic graph (DAG)**. When running `./gradlew build`, Gradle does not take every task in the project and run them in file order: it identifies the requested tasks, traverses the required relationships, and executes the relevant set of tasks. Tasks not in the graph normally do not run.

Example of an illustrative graph:

```text
prepareSources ──> compileSources ──> packageApp ──> release
       └───────> verifySources ────────────────────┘
```

The arrow convention `A ──> B` here means **B requires A to complete first**. `release` depends on both `packageApp` and `verifySources`, while the two branches after `prepareSources` have no fixed order relative to each other. Gradle may choose different valid execution orders, especially when parallel execution is enabled.

**Distinguish three concepts:**

- **Registered/defined task:** present in the build model; not necessarily fully configured or executed.
- **Task in the selected graph:** Gradle determined that this task belongs to the work required in the current build.
- **Task action actually executing:** only happens if not prevented by `SKIPPED`, `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, or other conditions. A task can be in the graph without performing new work.

This explains why a `build` invocation involves many related tasks, yet the next run can finish faster even though the graph structure is similar.

## 2. Where do tasks sit in the build lifecycle?

Gradle distinguishes these phases:

1. **Initialization:** reads project info from `settings.gradle` / `settings.gradle.kts`, determines the root project, subprojects, and build structure.
2. **Configuration:** applies plugins, evaluates build scripts, and defines/configures required tasks. Gradle computes the work graph for the command invocation, including dependencies and ordering.
3. **Execution:** runs actions of tasks in the graph according to established relationships, taking inputs/outputs, caches, and skip conditions into account.

Diagram:

```text
gradlew <requested-task>
        |
        v
 Initialization: identify projects
        |
        v
 Configuration: apply plugins, register/configure tasks,
                determine relationships and work graph
        |
        v
 Execution: execute/skip tasks according to the DAG
        |
        v
 Build result: SUCCESS or FAILED
```

Note that the **configuration cache** can store and restore configuration results: when the cache is valid, Gradle skips most traditional configuration work and restores the saved graph. Therefore, you must not design build logic assuming a block in the build script will definitely re-run every time.

In `build.gradle.kts`:

```kotlin
tasks.register("hello") {
    group = "demo"
    description = "Prints a greeting when the task is executed"

    doLast {
        println("Hello Gradle")
    }
}
```

`group` and `description` are **task configuration**. The `doLast { ... }` block adds an action to the task; `println` inside only executes when the action runs. The configuration block passed to `tasks.register` is deferred until the task needs to be configured. Do not put network calls, file writes, or artifact publishing directly at script top-level or inside configuration blocks, because they can occur even when just running `help` or while Gradle prepares the graph.

## 3. Standalone runnable Gradle Kotlin DSL example: dependency graph

Create an empty directory with two files:

**`settings.gradle.kts`**

```kotlin
rootProject.name = "task-graph-demo"
```

**`build.gradle.kts`**

```kotlin
val prepare = tasks.register("prepare") {
    group = "demo"
    description = "Prepare data before compilation"
    doLast {
        println("prepare")
    }
}

val compile = tasks.register("compileDemo") {
    group = "demo"
    description = "Simulate compilation step"
    dependsOn(prepare)
    doLast {
        println("compileDemo")
    }
}

tasks.register("packageDemo") {
    group = "demo"
    description = "Simulate packaging step"
    dependsOn(compile)
    doLast {
        println("packageDemo")
    }
}
```

This is a simple Gradle project, **requiring no Java sources or Spring Boot plugin**. You need a Gradle version compatible with the JVM in use. If the project has a Gradle Wrapper, use `./gradlew`; if there is no wrapper yet, you can use an installed Gradle binary via `gradle`, or generate a wrapper with `gradle wrapper` first and use the wrapper from then on.

Run:

```bash
gradle -q packageDemo
```

**Stdout of the actions in the example (with `-q` to suppress normal logs):**

```text
prepare
compileDemo
packageDemo
```

The three tasks run in sequence:

```text
:prepare --> :compileDemo --> :packageDemo
```

Although the command only requested `packageDemo`, Gradle included `compileDemo` and `prepare` in the graph because of the `dependsOn` relationships. Running `gradle -q prepare` alone prints only `prepare`. Running `gradle -q compileDemo` prints `prepare`, followed by `compileDemo`. You do not need to manually invoke all tasks in order on the CLI.

To inspect the execution plan **without running actions**:

```bash
gradle packageDemo --dry-run
```

The output displays selected tasks with statuses like `SKIPPED` due to dry run. Do not confuse `--dry-run` with a successfully executed build: it helps observe the graph, and does not verify that code compiles or tests run.

### If written in Groovy DSL

Equivalent to the example above in **`build.gradle`** (switch `settings.gradle.kts` to `settings.gradle` if you want consistent Groovy):

```groovy
def prepare = tasks.register('prepare') {
    group = 'demo'
    description = 'Prepare data'
    doLast {
        println 'prepare'
    }
}

def compile = tasks.register('compileDemo') {
    group = 'demo'
    dependsOn prepare
    doLast {
        println 'compileDemo'
    }
}

tasks.register('packageDemo') {
    group = 'demo'
    dependsOn compile
    doLast {
        println 'packageDemo'
    }
}
```

Choose **one** DSL language for build files; do not paste both examples into the same project.

## 4. Types of relationships that determine the graph

Not every method that looks like "run after" creates a dependency.

| API | When requesting only task B, does it automatically add A to the graph? | Meaning |
| --- | --- | --- |
| `B.dependsOn(A)` | **Yes** | B requires A to finish first; A is a true prerequisite. |
| `B.mustRunAfter(A)` | **No** | Only constrains ordering if both A and B are in the graph. |
| `B.shouldRunAfter(A)` | **No** | Soft ordering hint if both appear; may be ignored to avoid cycles or optimize parallelism. |
| `A.finalizedBy(B)` | **Yes**, when A is scheduled | B is a finalizer running after A, often used for cleanup even when A fails. |
| B's input taken from A's output via `Provider` | **Can infer A automatically** | Gradle recognizes the producer task via provider metadata; less manual `dependsOn` needed. |

### 4.1. `dependsOn`: mandatory dependency

`dependsOn` describes a **prerequisite**: running `packageDemo` requires doing `compileDemo` first. Task A is scheduled because task B needs its result, even though A might be marked `UP-TO-DATE` and not actually run its action.

The graph does not allow cycles such as:

```text
A dependsOn B
B dependsOn A
```

If you create a dependency cycle, Gradle reports a cycle error; there is no valid execution order.

### 4.2. `mustRunAfter` and `shouldRunAfter`: ordering, not dependency

Use the following separate example, added to the demo project's `build.gradle.kts` or a new project:

```kotlin
val audit = tasks.register("audit") {
    doLast {
        println("audit")
    }
}

tasks.register("publishDemo") {
    mustRunAfter(audit)
    doLast {
        println("publishDemo")
    }
}
```

When invoked alone:

```bash
gradle -q publishDemo
```

Output:

```text
publishDemo
```

`audit` **does not run** because `mustRunAfter` does not pull that task into the graph. When invoking both, even in reverse order on the command line:

```bash
gradle -q publishDemo audit
```

Output:

```text
audit
publishDemo
```

If changed to `shouldRunAfter(audit)`, Gradle normally prefers running `audit` before `publishDemo`, but that is **not an absolute guarantee**. Gradle may ignore a `shouldRunAfter` relationship if it causes an ordering cycle or to avoid idle workers during parallel execution. When B's data truly requires A's result, you must use `dependsOn` or wire inputs/outputs; `mustRunAfter` does not guarantee A will be executed.

A consequence regarding failures: even though `mustRunAfter` requires A to precede B if both are present, `--continue` can still let B run when A fails if the two tasks **have no data dependency on each other**. Only `dependsOn` expresses that A's success is required for B.

### 4.3. `finalizedBy`: performing cleanup after a task

`finalizedBy` is commonly used when a task opens temporary resources and needs a cleanup task to run afterward:

```kotlin
val runChecks = tasks.register("runChecks") {
    doLast {
        println("checks")
    }
}

val cleanTemporary = tasks.register("cleanTemporary") {
    doLast {
        println("cleanup")
    }
}

runChecks.configure {
    finalizedBy(cleanTemporary)
}
```

```bash
gradle -q runChecks
```

Output:

```text
checks
cleanup
```

Gradle automatically adds `cleanTemporary` to the graph because `runChecks` is scheduled; a finalizer usually still runs when the finalized task fails or is considered `UP-TO-DATE`. This is a task resource lifecycle management mechanism, though it cannot guarantee cleanup in all cases where the OS kills the process or the machine loses power. For services shared across multiple tests and parallel builds, consider Gradle Shared Build Services or suitable test fixtures instead of global script state.

### 4.4. Implicit dependency via producer/consumer

When task B declares an input taken from task A's output provider, Gradle can infer the relationship without manual `dependsOn`. This keeps data and execution order defined in one place, avoiding situations where B waits for A but reads the wrong file.

Conversely, if you connect via a hardcoded path to a file created by another task without carrying producer metadata, Gradle may not know about the dependency; running B standalone will fail with "file does not exist" or use stale data.

## 5. Example with real inputs/outputs: graph inferred automatically via Provider

This example **replaces the entire `build.gradle.kts` file of the demo** if you want to run it standalone; do not append it to an example with overlapping names. It defines two custom task types with explicit inputs/outputs:

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

abstract class GenerateGreeting : DefaultTask() {
    @get:Input
    abstract val message: Property<String>

    @get:OutputFile
    abstract val targetFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val file = targetFile.get().asFile
        file.parentFile.mkdirs()
        file.writeText(message.get() + "\n")
    }
}

abstract class PrintGreeting : DefaultTask() {
    @get:InputFile
    abstract val sourceFile: RegularFileProperty

    @TaskAction
    fun printMessage() {
        println(sourceFile.get().asFile.readText().trimEnd())
    }
}

val generateGreeting = tasks.register<GenerateGreeting>("generateGreeting") {
    message.set("Hello Gradle")
    targetFile.set(layout.buildDirectory.file("generated/greeting.txt"))
}

tasks.register<PrintGreeting>("printGreeting") {
    sourceFile.set(generateGreeting.flatMap { it.targetFile })
}
```

Run:

```bash
gradle -q printGreeting
```

**Exact stdout of the example:** `Hello Gradle`.

When `printGreeting` is selected, `generateGreeting` is also scheduled because the `sourceFile` property points to the provider of `generateGreeting.targetFile`. The generated file is under `build/generated/greeting.txt`. The `generateGreeting` task declared `@Input` and `@OutputFile`, so Gradle can determine whether it needs to re-execute; `printGreeting` declares no output, so since it only prints to the console, it normally still runs its action every time.

Run further:

```bash
gradle printGreeting --info
```

On the second run if inputs and outputs have not changed, the file-generating task typically shows `UP-TO-DATE`, while the printing task still executes. Status can change if the file is deleted, inputs change, action code changes, Gradle version changes, or build cache is enabled. The key point is that **the graph still describes producer → consumer, even when the producer's action is skipped due to input/output checks**.

### Why does the example use `Property` and `RegularFileProperty`?

- `Property<String>` allows inputs to be declared and lazily configured using `set`/`Provider`.
- `RegularFileProperty` represents an output/input file and carries producer metadata.
- `@TaskAction` keeps execution logic inside the task type rather than mixing it with configuration scripts.
- `@Input` / `@InputFile` / `@OutputFile` enable Gradle to track changes to avoid re-running and support caching on demand.

This is the more suitable design direction for important tasks, tasks reused in multiple places, or tasks needing **configuration cache** compatibility. Inside a task action, avoid accessing `project`, `gradle`, `rootProject` directly or reading mutable/global variables from the build script; use task property APIs and compatible services to describe needed data.

## 6. Task declaration, registration, and configuration avoidance

### Eager and lazy

Gradle supports APIs such as:

- `tasks.create("name")`: creates/configures a task eagerly, which can slow builds down if there are many unrelated tasks.
- `tasks.register("name")`: registers a task **lazily** and returns a `TaskProvider<T>`; Gradle only realizes/configures it when needed.
- `tasks.named("existingTask") { ... }`: lazily configures an already registered/existing task.
- `tasks.registering` and `tasks.existing`: common convenience delegates in Kotlin DSL.
- `tasks.getByName("name")` or `tasks.named("name").get()`: forces obtaining the task instance, which can cause eager realization; avoid when you can pass a `TaskProvider` directly.

Example to use when wiring a standard task to a custom task:

```kotlin
val validateDocs = tasks.register("validateDocs") {
    group = "verification"
    description = "Validate documentation before running check"
    doLast {
        println("docs checked")
    }
}

// Only applies if the 'java' plugin has created the 'check' task:
tasks.named("check") {
    dependsOn(validateDocs)
}
```

Declare the Java plugin at the top of `build.gradle.kts` for the snippet above to run in a standalone project:

```kotlin
plugins {
    java
}
```

When running `gradle check`, Gradle adds `validateDocs` to the graph; other test/check tasks created by the Java plugin may also appear. `tasks.named("check")` does not create the `check` task by itself: that task must exist from a plugin or another declaration.

**No need to call `get()` to wire a dependency:** writing `dependsOn(validateDocs)` or `dependsOn(tasks.named("validateDocs"))` is enough. Choosing providers avoids unnecessary eager configuration.

### Do not confuse configuration actions and execution actions

`tasks.register("x") { println("configured") }` puts the print statement in **configuration**; it may appear when Gradle realizes task x to compute the graph. `tasks.register("x") { doLast { println("executed") } }` puts the print statement in **execution**. With configuration cache, logs in configuration may disappear on cache-hit builds; this is not Gradle skipping the task.

Similarly, `doFirst { ... }` adds an action at the beginning of the task's action list and `doLast { ... }` adds one at the end. Actions within the same task run in action-list order, whereas the order **between tasks** is determined by the graph.

## 7. Java and Spring Boot task graphs are assembled from plugins

Plugins provide pre-built tasks and relationships:

- **Java plugin:** creates common tasks like `compileJava`, `processResources`, `classes`, `jar`, `test`, `check`, `assemble`, and `build`. Lifecycle tasks like `build` usually have no main action of their own: they **depend on** the tasks that do the actual work.
- **Spring Boot Gradle plugin:** adds `bootJar` for Java projects or `bootWar` with the War plugin, `bootRun` to run the application, and `bootBuildImage` to build an OCI image when plugin/task conditions apply. Task relationships depend on plugin version and configuration.
- **Project team plugins:** may add tasks for source generation, formatting/checkstyle, integration tests, SBOMs, image publishing, or deployment.

In a Spring Boot application, reading a task name is not enough to infer that `bootRun` must build an executable JAR before running: `bootRun` can use the source set's classes/resources directly. Similarly, do not assume `build` will publish to a registry or deploy to production. Publish/deploy steps only run when explicitly declared by plugins and build logic.

Example illustrating a custom quality gate task in a project with the Java plugin enabled:

```kotlin
plugins {
    java
}

val verifyPackaging = tasks.register("verifyPackaging") {
    group = "verification"
    description = "Run custom checks before the build completes"
    doLast {
        println("packaging verified")
    }
}

tasks.named("check") {
    dependsOn(verifyPackaging)
}
```

If you run `gradle -q check`, the line `packaging verified` will be printed when `verifyPackaging` executes. However, there will be other tasks in the `check` graph, and they may be `NO-SOURCE` if the project has no Java sources/tests yet. Do not assume a fixed complete stdout for all of `check`, because the graph depends on plugins, sources, and the project.

In a multi-module project:

```text
repo/
├── settings.gradle.kts
├── build.gradle.kts
├── core/build.gradle.kts
└── app/build.gradle.kts
```

A task has a unique path such as `:core:jar` or `:app:bootJar`. Module `app` depending on module `core` at the **project dependency** level can pull in producer tasks of module `core` via variants/artifacts. However, a Java project dependency (`implementation(project(":core"))`) **is not synonymous** with running the full `:core:build`; Gradle usually only needs the artifact and corresponding producer tasks. To know for sure, you must inspect the actual graph, as it also depends on plugins, variants, and the invoked task.

## 8. The task graph differs from the library dependency graph

Gradle has at least two types of relationships to distinguish:

1. **Task dependency graph:** `:app:compileJava` may need the output of a source-generation task or a producer in another module. This is the graph of **work to be performed**.
2. **Component/library dependency graph:** `spring-boot-starter-web` pulls in Spring Framework, logging, or a servlet stack depending on version; this is the graph of **modules/artifacts and versions** resolved from repositories.

The two graphs are related (resolving dependencies can lead to producer tasks when depending on projects/variants) but are not the same thing. When debugging:

```bash
gradle :app:build --dry-run
gradle :app:dependencies --configuration runtimeClasspath
```

The first command **observes scheduled tasks**; the second **prints the dependency tree of the `runtimeClasspath` configuration**. The second example is only valid when project `:app` has a `runtimeClasspath` configuration, usually provided by the Java/Java Library plugin. Do not read `dependencies` output and conclude that it represents task execution order.

An important nuance: Gradle can defer dependency resolution until artifacts are needed. When using configuration cache, much of the information needed to store the graph must be resolved while preparing the cache. Therefore, avoid forcing `configurations.runtimeClasspath.get().files` in top-level build scripts just to "peek" at dependencies: doing so can make configuration heavy and break laziness.

## 9. Task is selected but action does not run: UP-TO-DATE, FROM-CACHE, SKIPPED, NO-SOURCE

Common console statuses should not be interpreted as "the task is not in the graph".

| Status | Common meaning | What to check? |
| --- | --- | --- |
| `UP-TO-DATE` | Inputs, outputs, and tracked state meet conditions to skip re-running the action | Are inputs/outputs declared properly? Are output files intact? |
| `FROM-CACHE` | Gradle restored the result from a valid build cache | Is cache enabled, is the task cacheable, what is in the cache key? |
| `NO-SOURCE` | Task processes sources but has no sources to work on | Are source sets/paths right, are there sources/tests? |
| `SKIPPED` | Task skipped due to `onlyIf`, `enabled=false`, `--dry-run`, or another reason | Use `--info` to see the reason, check predicates |
| `FAILED` | Task action or execution encountered an error | Check task path, root cause, `--stacktrace`, `--info` |
| Not shown | Task was not included in this run's graph, or excluded by another task selection/configuration | Check requested tasks and `dependsOn` relationships |

**Build cache** and **configuration cache** are two different layers:

- Build cache stores/restores **task outputs** for eligible tasks based on inputs, implementation, and relevant conditions; it affects work during execution.
- Configuration cache stores/restores the **configured model, task graph, and task state** for a matching build invocation; it affects configuration cost.

Run to investigate performance (if supported by Gradle/plugins):

```bash
gradle build --build-cache --configuration-cache
gradle build --build-cache --configuration-cache
```

Do not conclude "the second run is guaranteed to be fast and all tasks UP-TO-DATE": build logic, environment inputs, plugins, non-cacheable tasks, or cache incompatibilities can change outcomes. Read the logs to see whether configuration was reused and whether each task was skipped/cached.

## 10. Controlling execution: onlyIf, enabled, failures, and parallel

### 10.1. `onlyIf` and `enabled`

A task can be selected into the graph while its action is skipped:

```kotlin
tasks.register("optionalReport") {
    val requested = providers.gradleProperty("withReport")
    onlyIf("requires -PwithReport") {
        requested.isPresent
    }
    doLast {
        println("report generated")
    }
}
```

`gradle optionalReport` usually reports `SKIPPED`; `gradle -q optionalReport -PwithReport` prints `report generated`. Use `onlyIf` to evaluate conditions close to task execution time, avoiding logic like "if file does not exist yet then register task" based on transient filesystem state during configuration.

`enabled = false` also prevents action execution, but **does not automatically remove all prerequisites from the graph**. If you want to disable an entire branch of work, organize task selection or conditional dependencies appropriately; do not assume disabling one task always makes all its dependencies disappear.

### 10.2. Task failures and `--continue`

By default, Gradle stops when encountering a failure and does not execute tasks that cannot validly proceed. With:

```bash
gradle build --continue
```

Gradle attempts to execute other tasks **that do not depend on the failed task**, in order to collect more errors in a single build. Dependents requiring the failed task still cannot be treated as successful. `--continue` does not turn a failed build into a success and does not guarantee every remaining task will run.

### 10.3. Parallel execution

The DAG defines **mandatory constraints**, without promising a single fixed order for independent tasks. `--parallel` allows Gradle to use additional parallelism when conditions permit; effectiveness depends on Gradle version, configuration cache, project setup, workers, and tasks. Do not write tasks that modify the same shared file, use the same fixed port, or rely on another task's output without declaring a dependency/input. "Sometimes pass, sometimes fail" errors when enabling parallel often suggest a missing dependency or unsafe shared state.

The order between `test` and `lint` if both run independently can vary; use `mustRunAfter` **only when** ordering is genuinely needed, or use `dependsOn` when there is a mandatory data/work relationship.

## 11. How to read the task graph on a real project

Start with the repository's Gradle Wrapper to keep the Gradle version consistent. The sample commands below use `./gradlew` (Windows: `gradlew.bat`).

| Need to know | Command | Explanation |
| --- | --- | --- |
| Which tasks can be invoked? | `./gradlew tasks` | Lists common grouped tasks of the current project. |
| What other tasks exist? | `./gradlew tasks --all` | Shows more tasks; not the dependency graph of a specific build. |
| What does this task do? | `./gradlew help --task bootJar` | Describes the task if it exists in the current project/plugins. |
| Which tasks will the build command schedule? | `./gradlew :app:build --dry-run` | Observes the task set for this invocation, without running actions. |
| Track down skip/configuration causes? | `./gradlew :app:build --info` | Provides extra details on task selection, inputs, skips, and caching. |
| Need stack trace on error? | `./gradlew :app:build --stacktrace` | Displays the exception chain. |
| Investigate dependent modules? | `./gradlew :app:dependencies --configuration runtimeClasspath` | Observes **library** dependencies, not the task DAG. |
| Check config cache compatibility? | `./gradlew :app:build --configuration-cache` | Detects tasks/build logic violating cache requirements. |

**`:app:build` is an example path:** only use it when there is a subproject named `app`. If it is a single-module project at root, replace it with `build`. Similarly, `bootJar` only exists when appropriate Spring Boot and Java plugins have created that task.

### Process for finding why a task runs "unexpectedly"

1. Identify the exact **invocation and task path** (`:app:test` differs from `:core:test`).
2. Run `--dry-run` with the **exact same CLI task set** to see which tasks are selected.
3. Read `dependsOn`, provider inputs/outputs, and plugin-added task relationships; looking only at `mustRunAfter` does not explain why a task appeared.
4. Run `--info` if a task is `UP-TO-DATE`, `SKIPPED`, or cached; identify the actual reason.
5. If a task runs unnecessarily, look for eager task creation, unnecessary dependencies, or overly broad lifecycle tasks. If a task does not run while a required file is missing, look for missing output wiring/`dependsOn`.
6. For hard-to-reproduce failures, try clean, disabling parallel, or disabling cache **only as an isolation step**, then fix the true input/output/dependency cause. Do not make disabling cache permanently the default solution.

## 12. Common misconceptions and how to fix them

**Misconception 1: "Every task in `build.gradle` runs in declaration order."** False. The build script creates the task model, while the graph and relationships determine order. Solution: `dependsOn` or producer/consumer providers, do not rely on line position.

**Misconception 2: "`mustRunAfter` makes task A run first."** Only true regarding **order when A is already in the graph**; it does not add A. When B truly needs A's artifact, use a dependency.

**Misconception 3: "`task.dependsOn(foo)` proves task foo executes its action in every build."** Foo may be in the graph yet `UP-TO-DATE`/`FROM-CACHE`/`SKIPPED`. Inspect outputs, inputs, and Gradle statuses.

**Misconception 4: "Putting work in a `tasks.register` block is the same as `doLast`."** Configuration and execution are two different phases. Work that creates files, runs commands, or sends requests must live in task actions or appropriate task types.

**Misconception 5: "Reading a file in task B at the same path as A's output is enough."** Gradle cannot reliably infer the producer from a disconnected path string. Wire B's input to the `TaskProvider`/A's output and declare input/output annotations; then use `--dry-run` to confirm the producer is actually scheduled.

**Misconception 6: "`tasks.getByName` and `tasks.register` have the same performance."** Fetching the task instance can realize the task early, slowing configuration or breaking configuration avoidance. Prefer `tasks.named` and `TaskProvider` when you only need to declare relationships.

**Misconception 7: "`--dry-run` passing means the code builds/tests cleanly."** Dry run does not execute actions. It is only a way to inspect scheduling; an actual build/test run is required to verify artifacts and behavior.

**Misconception 8: "`--continue` ignores errors so the build succeeds."** It only continues independent work where possible and still reports failure. Failed dependencies are not assumed to have produced valid outputs.

**Misconception 9: "Build cache and configuration cache are the same."** They cache two different layers; optimizing one does not automatically ensure the other. Read cache messages and fix tasks with missing inputs/outputs or improper configuration state access.

**Misconception 10: "`:app:build` always invokes `:core:build` because app depends on core."** In multi-project Gradle, Gradle may only need the tasks that produce the required artifact from core, not all of core's checks/tests/assemble. Check the actual graph and variant dependencies.

## 13. Task design checklist for Spring Boot projects

- **Right work:** identify whether a task is actionable (compile, check, package) or lifecycle/aggregate (grouping tasks under one entry point).
- **Right path:** use `:module:task` paths in multi-module projects; avoid accidentally referencing tasks of the same name at root and subprojects.
- **Right relationships:** mandatory data → `dependsOn` or output provider; conditional ordering → `mustRunAfter` / `shouldRunAfter`; cleanup → `finalizedBy`.
- **Right data:** declare `@Input`, `@InputFiles`, `@OutputFile`/`@OutputDirectory`, and path sensitivity characteristics where applicable. Do not hide inputs in environment variables or read undeclared files.
- **Right lifecycle:** side-effecting work belongs in task execution; lazy configuration via `tasks.register`/`named`.
- **Right reproducibility:** tasks must not rely on shared mutable variables, current time, or random ordering unless declared as appropriate inputs.
- **Right verification:** use `--dry-run` to inspect the graph, run an actual build, observe task outcomes via `--info`; re-run to evaluate incrementality and caching.
- **Right environment:** prefer Gradle Wrapper, verify Gradle/JDK/plugin versions, and evaluate configuration cache on the actual repository.

## 14. Official documentation

- Gradle User Manual – [Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html).
- Gradle User Manual – [Creating and Registering Tasks](https://docs.gradle.org/current/userguide/writing_tasks.html).
- Gradle User Manual – [Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html).
- Gradle User Manual – [Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html).
- Gradle User Manual – [Configuring Tasks Lazily](https://docs.gradle.org/current/userguide/lazy_configuration.html).
- Gradle User Manual – [Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html).
- Gradle User Manual – [Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html).
- Gradle API – [Task](https://docs.gradle.org/current/javadoc/org/gradle/api/Task.html).

**Key takeaway to remember:** a task is a unit of work, `dependsOn` and producer/consumer form mandatory work relationships, ordering APIs only adjust sequence where applicable, and the graph is an execution plan **specific to each Gradle invocation**. A task being in the graph does not mean its action always runs: Gradle also checks inputs/outputs, skips, caches, and execution conditions to decide what work truly needs to be done.