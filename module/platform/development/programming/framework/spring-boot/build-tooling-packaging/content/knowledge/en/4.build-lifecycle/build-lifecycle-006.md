# Distinguishing Clean, Incremental Builds, and Task Reruns in Spring Boot Projects

## 1. Three operations address three different needs

When developing Spring Boot with Maven or Gradle, the same project can be built many times in a row. What needs to be distinguished is: **deleting old output state**, **reusing results that are still valid**, and **forcing work to re-execute even when inputs have not changed**.

| Concept | Primary purpose | Deletes build outputs? | Forces all work to re-execute? |
|---|---|---|---|
| **Clean** | Deletes generated files to start with a clean output directory | Normally yes: Maven deletes `target/`; Gradle deletes `build/` | Does not build again on its own; if combined with a build, caches outside the output directory may still be reused |
| **Incremental build** | Avoids recomputing results unaffected by changes | No, unless clean is invoked | No; only necessary work is re-executed |
| **Task rerun** | Forces a selected task or tasks to execute again | Not necessarily | Yes, within the scope of the rerun command/mechanism; skip conditions based on task characteristics still exist |

Two usages of terminology need to be distinguished:

- **Task-level incremental build**: the tool sees that a task's inputs/outputs are still valid and therefore **does not run** that task.
- **Incremental processing inside a task**: the task still runs, but the compiler or plugin only processes changed parts. For example, `compileJava` runs, yet incremental Java compilation may compile only a subset of sources and affected files.

There is no single unified `build` command across all tools. Maven uses **lifecycle phases/goals**; Gradle uses a **task graph**. Thus the same concepts have different controls and status displays.

## 2. Understanding clean: deletes outputs, not source code

### Maven

For a Spring Boot project using Maven, common commands are:

```bash
# Delete build outputs only
./mvnw clean

# Build according to the default lifecycle up to the package phase
./mvnw package

# Delete old outputs, then run phases up to package
./mvnw clean package
```

On Windows, use `mvnw.cmd` instead of `./mvnw`.

`clean` is a phase belonging to the separate **clean lifecycle**. Under standard configuration, the Maven Clean Plugin deletes the `target/` directory, including `target/classes`, test results, and packaged JAR/WARs. `package` belongs to the **default lifecycle**, so Maven steps through the required phases before `package` in order, including compiling source code, compiling tests, running tests, and packaging, depending on `packaging` and plugins.

`./mvnw clean` is **not** synonymous with `./mvnw clean package`: the first command only performs clean, without recreating the JAR. `clean` also **does not delete** downloaded libraries in the user's Maven cache (usually in `~/.m2/repository`). If a project configures outputs outside defaults, clean scope can be adjusted by the plugin.

### Gradle

For a Spring Boot project using Gradle:

```bash
# Delete the build directory only
./gradlew clean

# Execute the tasks that the build lifecycle task depends on
./gradlew build

# Delete the build directory first, then build
./gradlew clean build
```

On Windows, use `gradlew.bat` instead of `./gradlew`.

`clean` is normally a `Delete`-type task that deletes `build/` of the applied project. `build` normally depends on the artifact-producing group (`assemble`) and verification group (`check`), according to applied plugins. With Spring Boot, the `bootJar` or `bootWar` task provided by the Spring Boot plugin participates in the packaging process depending on project configuration. Do not assume every project produces the exact same set of artifacts.

**Key point:** `clean` deletes outputs inside the build directory, yet **does not necessarily delete the Gradle build cache**. If build cache is enabled and a task is eligible, after `clean` Gradle can still restore outputs from cache with status `FROM-CACHE`. Therefore, "clean then build" is not always equivalent to "re-executing every task from scratch".

Neither Maven nor Gradle requires `clean` every time a file is edited. Cleaning often slows down builds unnecessarily.

## 3. How does incremental build in Gradle work?

Gradle models a build as a task graph and dependency relationships. A typical task has:

- **Inputs**: Java sources, classpath, properties, configurations affecting output.
- **Outputs**: `.class` files, JARs, copied resource files, or generated documentation.
- **Task implementation**: how the task transforms inputs into outputs.

For tasks with proper state tracking, Gradle records fingerprints of inputs and outputs from the previous execution. When run again, Gradle compares the recorded state with the current state:

```text
Request: ./gradlew build
             |
             v
     Build task graph
             |
             v
  Does task meet execution conditions?
        /         \
       No         Yes
       |            |
  SKIPPED/...   Are inputs and outputs still valid?
                  /             \
                Yes             No
                 |                |
             UP-TO-DATE     Does cache have valid output?
                                /          \
                              Yes           No
                               |             |
                           FROM-CACHE    Execute task
                                        (may be incremental
                                         inside the task)
```

This diagram is conceptual: Gradle has many more conditions such as `NO-SOURCE`, untracked tasks, cache configuration, output checks, and plugin conditions. Not every task is cached or optimized identically.

Example running twice in a row, **without modifying files**:

```bash
./gradlew build --console=plain
./gradlew build --console=plain
```

On the second run, many eligible tasks may print `UP-TO-DATE`. Tasks without actions or outputs may display differently. Do not assume every task must show `UP-TO-DATE` for a build to be valid.

### Reading Gradle task statuses

| Status | Interpretation | Re-executes task actions? |
|---|---|---|
| `UP-TO-DATE` | Inputs/outputs have not changed compared to recorded state | No |
| `FROM-CACHE` | Outputs were restored from a valid build cache | No |
| `NO-SOURCE` | Source-processing task has no sources to process | No |
| `SKIPPED` | Task was skipped due to conditions or configuration | No |
| No skip outcome label | Task may have executed normally | Yes, depending on task type |
| `FAILED` | Task executed but encountered an error | Unsuccessful |

**Incremental build** and **build cache** are not identical:

- `UP-TO-DATE` usually means current outputs on the machine are still valid, no need to re-run.
- `FROM-CACHE` means current outputs were fetched from a stored entry matching the same inputs/implementation, even if previous outputs were deleted.
- `--build-cache` or `org.gradle.caching=true` can be used to enable the build cache depending on configuration. A task is only cached when eligible; enabling cache does not mean every task becomes `FROM-CACHE`.
- **Configuration cache** is a different optimization: it stores the result of the task graph configuration phase, not the outputs of `compileJava` or `test` themselves. It does not replace output validity checking.

There is another layer of optimization: **incremental compilation**. When editing a Java class, `compileJava` may re-run yet compile only affected sources; changes broadly impacting APIs/classpath may require a larger portion of code to be recompiled.

## 4. Does Maven have incremental builds like Gradle?

Maven organizes work into three main lifecycles: `default`, `clean`, and `site`. Phases are not Gradle tasks. When invoking:

```bash
./mvnw package
```

Maven activates the **plugin goals** bound to phases from the start up to `package`. Some plugins, like the Maven Compiler Plugin, have mechanisms to avoid recompiling when unnecessary or to process changes based on sources and outputs, depending on version and configuration. Other goals are still invoked and decide for themselves what work needs doing.

Therefore:

- A second `./mvnw package` can be faster than the first because outputs already exist, dependencies are downloaded, and plugins perform optimizations.
- **Maven core does not provide the same `UP-TO-DATE` / `FROM-CACHE` labeling model for every goal as Gradle does.** Do not conclude "not incremental" merely because Maven logs differ from Gradle logs.
- You cannot reuse Gradle's `--rerun-tasks` flag in Maven; it is not a Maven option.
- When comparing behavior, inspect which exact plugin is invoked, the plugin version, "Nothing to compile" messages, test reports, and output status.

In a Spring Boot Maven project, the Maven plugin that packages the executable JAR (for instance, `spring-boot-maven-plugin` with the `repackage` goal when configured) is a separate step from the Java compiler; avoid equating "did not recompile classes" with "did not perform JAR packaging".

## 5. Rerunning tasks: no need to clean unnecessarily

### Gradle: `--rerun-tasks`

Suppose you want to re-execute the tasks needed for tests, even though Gradle considers outputs valid:

```bash
./gradlew test --rerun-tasks --console=plain
```

By Gradle's design, `--rerun-tasks` forces tasks in the selected task graph (including dependent tasks) to re-run, bypassing normal up-to-date checks; **it does not delete the entire `build/` directory before running**. Because the flag applies to the task graph, it can cause `compileJava`, `compileTestJava`, and related tasks to re-run, not just `test` alone.

Still keep limitations in mind: `NO-SOURCE` tasks, disabled tasks, or skip conditions may prevent normal action execution. The flag also does not automatically fix bad dependencies, re-download all dependencies, or prove production code is correct.

To rerun packaging:

```bash
./gradlew bootJar --rerun-tasks --console=plain
```

The command above applies when the project has applied the Spring Boot plugin creating the `bootJar` task; in other projects, choose the corresponding task (`jar`, `bootWar`, or a module's task). To target a specific test in a project with appropriate test/JUnit configuration:

```bash
./gradlew test --tests "com.example.demo.OrderServiceTest" --rerun-tasks
```

The test name here is an **example**; it only runs when that class exists and the test tooling is configured.

### Maven: reinvoking phases/goals or cleaning when rebuilding from fresh outputs

Maven has no equivalent `--rerun-tasks` flag. To re-trigger the lifecycle up to the `test` phase:

```bash
./mvnw test
```

To ask Maven to re-test after clearing old outputs:

```bash
./mvnw clean test
```

To limit to a single test class with an appropriately configured Maven Surefire Plugin:

```bash
./mvnw -Dtest=OrderServiceTest test
```

Invoking the `test` phase allows bound goals to run according to the lifecycle, though **individual plugins** can still skip work or use optimization mechanisms. `clean test` is the stronger choice when stale classes/outputs are suspected, though it also forces recompiling and regenerating resources. Avoid invoking a standalone test goal directly and assuming fresh sources were compiled: invoking the `test` phase is usually safer because it runs preceding phases.

**Note:** `-DskipTests` is a way to ask Maven to skip running tests in many common configurations, not to "force tests to rerun". When investigating stale test failures, check skip properties before concluding tests executed.

## 6. Quick command comparison for Maven and Gradle

| Need | Maven Wrapper | Gradle Wrapper |
|---|---|---|
| Delete outputs | `./mvnw clean` | `./gradlew clean` |
| Compile/package, reusing existing state | `./mvnw package` | `./gradlew build` or `./gradlew bootJar` |
| Build from a clean output directory | `./mvnw clean package` | `./gradlew clean build` |
| Run the test stage | `./mvnw test` | `./gradlew test` |
| Run tests after deleting outputs | `./mvnw clean test` | `./gradlew clean test` |
| Ask Gradle to re-execute tests and dependencies | No direct equivalent flag | `./gradlew test --rerun-tasks` |
| Inspect details on why tasks ran/skipped | Plugin logs, `./mvnw -X package` when debugging | `./gradlew test --info` or `--debug`, used for diagnostics |
| Package Spring Boot executable JAR | `./mvnw package` when appropriate Boot plugin is configured | `./gradlew bootJar` when appropriate Boot plugin is applied |

**Do not mechanically substitute `mvn package` with `gradle build`** in every project. In Maven, `package` is the packaging phase; in Gradle, `build` also depends on verification tasks and graph structures determined by plugins. Choose commands based on your goal (testing, JAR, full verification) and project configuration.

## 7. Self-observation experiments on a Spring Boot project

You can use a project from Spring Initializr with Java 17+ (or a JDK compatible with the chosen Spring Boot version). Ensure a wrapper is present, the project builds cleanly, and tests can run. The exercises do not require changing plugin configuration.

### Experiment A — Without changing source code

**With Gradle:**

```bash
./gradlew clean test --console=plain
./gradlew test --console=plain
```

Observe the second run: tasks with stable inputs/outputs may become `UP-TO-DATE`. Tasks with no sources may be `NO-SOURCE`, and tasks without output tracking may still execute. Do not assume a specific number of tasks, as it depends on the project, Gradle version, and plugins.

**With Maven:**

```bash
./mvnw clean test
./mvnw test
```

Observe compiler/test plugin logs. You may see messages that the compiler does not need to recompile, but do not expect Maven to print `UP-TO-DATE` labels like Gradle.

### Experiment B — Editing a Java file

Edit a string, logic, or method inside `src/main/java`, then rerun `./gradlew test` or `./mvnw test`. Gradle will re-evaluate tasks whose inputs were affected. Maven triggers corresponding phases/goals; plugins decide what needs recompilation. A change to an API or dependency can cause broader recompilation than a change inside a method body.

If you only edit test sources in `src/test/java`, steps related to compiling and running tests will likely need to rerun; impact scope depends on tasks and plugins. If you edit a file that is not an input to any task (e.g., README), most compilation tasks will not need to rerun, unless the build declared that file as an input.

### Experiment C — Forcing a rerun without clean

**With Gradle:**

```bash
./gradlew test --rerun-tasks --console=plain
```

Compare statuses with the second run of Experiment A. Watch which tasks execute; `build/` is not deleted beforehand per the rerun flag's semantics. If there are no test sources or tasks are skipped by configuration, you may not see actual tests run.

**With Maven:**

```bash
./mvnw clean test
```

This experiment **deletes outputs and runs phases up to test**, not an exact replica of `--rerun-tasks`. That difference is precisely what to remember when switching between the two build tools.

### Experiment D — Inspecting outputs and build cache

With Gradle, when build cache is enabled and tasks are cacheable, after cleaning you may see `FROM-CACHE`:

```bash
./gradlew clean build --build-cache --console=plain
```

There is no guarantee all tasks are cacheable, produce cache hits, or share identical outputs across machines: cache key conditions, cache state, and build configuration govern the outcome. If you want to inspect why optimizations happened, use `--info`; do not conclude `FROM-CACHE` is an error simply because the task skipped running its action.

## 8. Which operation should you pick in real scenarios?

| Situation | Try first | Why |
|---|---|---|
| Editing Java or unit tests during development | Normal build/test, no clean | Keeps existing outputs to optimize around changes |
| Want to run only the test just edited | `test` or filter tests via plugin | Reduces scope of work |
| Gradle reports `UP-TO-DATE` but you need to re-verify test behavior | `test --rerun-tasks` | Forces tasks in the relevant graph to execute |
| Local outputs suspected corrupt, stale files left over, or unexplained results | `clean test` or `clean build/package` | Clears old outputs to rebuild |
| After switching branches or major build configuration changes | Normal build; clean if failure symptoms persist | Let the tool determine which inputs changed first |
| CI needs verification from clean outputs | Combine clean with verification phases/tasks per CI policy | Reduces reliance on outputs left from prior runs |
| Need to check if caching caused a discrepancy | Distinguish clean, rerun, and build cache; inspect status logs | Clean can still restore from cache; rerun does not delete outputs |
| Missing or wrong dependency resolution | Inspect repositories, resolution, and dependency caches separately | Cleaning outputs or rerunning tasks does not refresh dependencies |

In CI, even though using `clean` can be a good team policy, you still need to manage toolchains, dependency locking, plugin versions, secrets, and artifact provenance if you want reproducible builds. `clean` **does not by itself guarantee a reproducible build**.

## 9. Common misconceptions and errors

**"Every build must start with clean."** In practice, calling clean every time discards valid results and increases compile/test times. Prefer normal runs first; clean when suspecting output state or needing deliberate verification.

**"Clean always makes everything run from scratch."** It deletes configured outputs, but does not necessarily delete dependency caches or the build cache; Gradle can pull results from cache after clean.

**"If sources weren't touched, the task is guaranteed to be UP-TO-DATE."** Task inputs can include dependencies, toolchains, plugin configs, resources, environment, or property values. Deleted/modified outputs or tasks lacking standard input/output declarations also affect run decisions.

**"UP-TO-DATE, FROM-CACHE, and SKIPPED are all the same."** They indicate different skip reasons. `UP-TO-DATE` reuses existing outputs, `FROM-CACHE` restores cached outputs, and `SKIPPED` is usually due to execution conditions.

**"Rerun tasks means deleting the build directory."** `--rerun-tasks` does not need to delete `build/`; it targets execution decisions in the task graph. Conversely, `clean` only deletes outputs and does not rerun other tasks unless requested.

**"Gradle --rerun-tasks only runs the task named at the end of the command."** It applies to tasks in the required graph, including dependencies of the requested task. This can take more time than expected.

**"Maven rerunning the test phase is completely identical to Gradle --rerun-tasks."** Maven goals/plugins and Gradle tasks have different optimization mechanisms. When clean outputs are needed in Maven, choose `clean test`; when only re-invoking tests in the lifecycle, choose `test`, then read plugin logs.

**"When tests don't run, the build is broken."** The project may have no test sources yet, the test task may be disabled, tests may be skipped, or test results may be reused. Check logs, test configuration, and reports before concluding.

**"Running clean means new dependencies are re-downloaded."** Incorrect. Maven/Gradle manage dependency repositories/caches separately. If the problem lies in dependency resolution, diagnose that directly instead of just deleting `target/` or `build/`.

## 10. Checklist for diagnosing a build run

1. **What do you want?** Delete outputs, shorten build time, or verify a task re-executed?
2. **Which tool is used?** `mvnw`/`pom.xml` is Maven; `gradlew`/`build.gradle[.kts]` is Gradle.
3. **Which task/phase was requested?** `package`, `test`, `build`, and `bootJar` do not have identical scopes.
4. **Which inputs/outputs changed?** Sources, tests, resources, dependencies, plugins, Java toolchain, or deleted outputs.
5. **What does the log explain?** Gradle `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, `SKIPPED`; Maven compiler/test/packaging plugin messages.
6. **Is clean needed?** Only when you genuinely need clean outputs or are dealing with suspected stale state.
7. **Is forced execution needed?** In Gradle, consider `--rerun-tasks` for the selected task graph; in Maven, pick the appropriate phase and plugin mechanisms.
8. **Is the result verified?** Check test reports, JAR/WAR files, and command exit codes; do not conclude solely from execution duration.

### Official references

- [Gradle — Incremental build](https://docs.gradle.org/current/userguide/incremental_build.html)
- [Gradle — Incremental builds and build caching](https://docs.gradle.org/current/userguide/gradle_optimizations.html)
- [Gradle — Command-line interface, forcing tasks to execute](https://docs.gradle.org/current/userguide/command_line_interface.html)
- [Maven — Introduction to the build lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)

**Remember:** `clean` clears outputs; **incremental builds** avoid recomputing unnecessary work; **rerun** intentionally forces re-execution of a scoped set of work. In Spring Boot, choose phases/tasks according to your objective, read the build tool statuses, and only then decide whether to clean or force a rerun.