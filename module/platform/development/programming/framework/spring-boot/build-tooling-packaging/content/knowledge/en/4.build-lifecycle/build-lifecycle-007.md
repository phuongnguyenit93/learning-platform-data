# Reading Execution Plans Using Maven Help and Gradle --dry-run

## 1. Why read the plan before running a build?

A seemingly simple command like **mvn package** or **./gradlew build** can actually trigger a lot of work: processing resources, compiling, running unit tests, quality checks, creating a JAR, and packaging an executable JAR for Spring Boot. When a project has multiple modules or plugins that add tasks automatically, developers often do not know exactly which steps will be invoked and why.

**Reading the execution plan** means determining, before letting the build actually run:

- Is the target command a Maven **phase/goal** or a Gradle **task**?
- Which steps are scheduled, and which are pulled in as dependencies?
- What is the expected order and which plugin added each step?
- Can the command compile, run tests, delete outputs, create a JAR, write to a repository, or deploy?
- Does the plan change when enabling profiles, passing properties, selecting modules, or excluding tasks?

This skill is very useful when analyzing a slow Spring Boot build, explaining why **repackage** runs, checking whether a pipeline invokes tests, or inspecting the scope of a new command before trying it on a real project.

**Key difference to remember:** Gradle has a general **--dry-run** option (short form **-m**) to display the planned selected tasks without running task actions. Maven has no equivalent global **--dry-run** option for the whole lifecycle. With Maven, you must piece together information from the **lifecycle**, **effective POM**, **active profiles**, and individual plugin help to predict the goal sequence.

## 2. Understanding "the plan" properly: phase, goal, and task

| Question | Maven | Gradle |
| --- | --- | --- |
| Unit users normally invoke | Lifecycle **phase** like `package`, `verify`; or plugin **goal** like `spring-boot:repackage` | **Task** like `compileJava`, `test`, `bootJar`, `build` |
| How execution steps are formed | Bindings from packaging and plugin executions; lifecycle phase order | Task dependency relationships, task ordering, and task graph configured by plugins/build scripts |
| Commands to inspect config | `help:effective-pom`, `help:active-profiles`, `help:describe` | `tasks`, `help --task`, `properties` |
| Command to view planned steps without running actions | No global dry-run in Maven CLI | `./gradlew build --dry-run` |
| What still needs checking | Goals bound per phase, plugin config, active profiles, directly invoked goals | Task configuration logic, `onlyIf` conditions, task graph, excluded tasks, runtime environment |

### 2.1. Maven: a phase is not a plugin goal

**package** is a phase of the default lifecycle. When invoking **mvn package**, Maven executes the preceding phases in the same lifecycle and the plugin goals bound to the relevant phases. For standard **jar** packaging, some default bindings may include:

~~~text
process-resources  -> resources:resources
compile            -> compiler:compile
process-test-resources -> resources:testResources
test-compile       -> compiler:testCompile
test               -> surefire:test
package            -> jar:jar
~~~

This is a diagram **illustrating common bindings**, not verbatim output of a Maven command. Every project can also add goals to phases via plugins, parent POMs, profiles, extensions, or other packaging types. Some phases bind no goals and do no significant work. Steps of `clean`, `default`, and `site` belong to separate lifecycles; **mvn clean package** runs `clean` and then the phases leading to `package`.

### 2.2. Gradle: task graph is not synonymous with the declared task list

**build** is a task typically provided by the Java plugin; it depends on other tasks. When invoking **./gradlew build**, Gradle constructs a graph of requested tasks and transitive dependencies, then schedules execution according to constraints. Depending on plugins, tasks like **compileJava**, **processResources**, **classes**, **jar**, **assemble**, **test**, **check**, **build**, along with Spring Boot tasks such as **bootJar**, may appear.

**./gradlew tasks** lists tasks existing in the project. It does not fully answer "if I run build, which tasks will actually be selected?". To inspect the plan of a specific command, use **--dry-run** with that exact task.

## 3. Gradle: three layers of observing the plan

### 3.1. Discovering available tasks

Run in the root directory of a project with a Gradle Wrapper:

~~~bash
./gradlew tasks
./gradlew tasks --all
./gradlew help --task build
./gradlew help --task bootJar
~~~

- **tasks**: lists grouped tasks and descriptions provided by plugins/build scripts.
- **tasks --all**: provides a broader list, including tasks omitted from the default listing.
- **help --task build**: shows the path, task type, description, and options of the task named `build`.
- **help --task bootJar**: useful when the application applies the Spring Boot Gradle Plugin and creates the `bootJar` task. In a module without that plugin, the task may not exist.

In a multi-module project, you can inspect a module's task by specifying its path, for example **:app:bootJar**; the name **app** here is just an example, replace it with the actual project name. A path starting with **:** is a Gradle task path, not Maven syntax.

Help commands tell you **what a task is**, while dry-run shows **which tasks belong to the plan for a specific target**.

### 3.2. Previewing scheduled tasks with `--dry-run`

~~~bash
./gradlew build --dry-run
./gradlew test -m
./gradlew bootJar --dry-run
./gradlew clean bootJar --dry-run
~~~

Both **--dry-run** and **-m** tell Gradle to disable **task actions** and print the tasks that would be selected. They do not run compilation, tests, or packaging like a real build.

**Illustrative** example of a Spring Boot Gradle project with the Java plugin: running **./gradlew bootJar --dry-run** may show lines similar to:

~~~text
> Task :compileJava SKIPPED
> Task :processResources SKIPPED
> Task :classes SKIPPED
> Task :resolveMainClassName SKIPPED
> Task :bootJar SKIPPED

BUILD SUCCESSFUL
~~~

This is not fixed output: task counts, paths, order, and task names vary by Gradle version, Spring Boot plugin, configuration, and modules. From this sequence we infer **`bootJar` depends on the steps needed to create the archive**. We must **not** infer that Java compiled successfully, tests ran, or the JAR was created.

**The word `SKIPPED` in dry-run means task actions were skipped due to plan preview mode**; it does not mean the task will always be skipped in a real run. Similarly, **BUILD SUCCESSFUL** in dry-run only indicates Gradle could build/configure the plan under those conditions; it does not confirm compilation, test, or runtime results.

### 3.3. Viewing the graph more clearly when Gradle supports it

Gradle versions with **--task-graph** (an option introduced in Gradle 9.1) can print dependency graph information beyond the dry-run display. Check **./gradlew --version** and **./gradlew --help** before using it, because many Spring Boot projects pinned to Gradle 8.x will **not have** this option.

Even with only **--dry-run**, the printed task order is still helpful for reading the expected sequence. However, a linear list **does not display all dependency edges**: seeing B after A does not directly prove B `dependsOn` A. To confirm relationships, inspect the build script, plugin documentation, and task graph provided by Gradle.

## 4. Practical Gradle example: previewing without running actions

To observe a small graph, create a Gradle project with **settings.gradle**:

~~~groovy
rootProject.name = 'task-plan-demo'
~~~

And **build.gradle**:

~~~groovy
plugins {
    id 'base'
}

tasks.register('prepareDemo') {
    group = 'demo'
    description = 'Prepare demo data'
    doLast {
        println('prepare executed')
    }
}

tasks.register('packageDemo') {
    group = 'demo'
    description = 'Package demo'
    dependsOn('prepareDemo')
    doLast {
        println('package executed')
    }
}
~~~

This is a **standalone Gradle Groovy DSL configuration for the demo**, not a Java class; you need a compatible Gradle installation and **Gradle Wrapper** if you want to run the **./gradlew** commands below. The **base** plugin comes built into Gradle and does not download Spring Boot. Both tasks are custom tasks, so they do not depend on a specific Spring Boot version.

First inspect the info:

~~~bash
./gradlew tasks --all
./gradlew help --task packageDemo
./gradlew packageDemo --dry-run
~~~

Dry-run reports that both **prepareDemo** and **packageDemo** are in the plan; it does not print the two strings **prepare executed** and **package executed** because those strings are inside **doLast actions**. Expected output format (showing only the two main task lines):

~~~text
> Task :prepareDemo SKIPPED
> Task :packageDemo SKIPPED
~~~

If run for real:

~~~bash
./gradlew packageDemo
~~~

The two tasks execute in order, **prepareDemo** before **packageDemo**, and the `doLast` blocks print the exact messages from the example:

~~~text
prepare executed
package executed
~~~

Gradle may print additional lines about tasks, timing, and build status; the snippet above excerpts only the **two `doLast` lines**. Use **--dry-run** to answer "which tasks are scheduled?", and only run for real when you need to confirm a task's actual effect.

**Important experiment:** remove **dependsOn('prepareDemo')** in `packageDemo`, then rerun **./gradlew packageDemo --dry-run**. Then the planned list contains only **packageDemo** (unless another configuration adds a dependency). This shows dry-run reflects the **actual configured graph** rather than running every declared task whenever one task is invoked.

## 5. Maven: reading the plan via lifecycle and help tools

### 5.1. Maven has no global `--dry-run` like Gradle

Do not instruct users to run **./mvnw package --dry-run** as a standard way to print all plugin goals without executing them. In the Maven CLI, **--dry-run** is not a global lifecycle option like in Gradle. Some **individual plugin goals** may have a **dryRun** parameter, but its effect applies **only to that goal** as specified by that plugin's documentation; it does not cancel execution of other goals in the lifecycle.

Do not use **-DdryRun=true** and assume the entire Maven build will only simulate. That is simply a user property; if no goal reads it, the build can still run normally, including tests, writing files, installing artifacts, or deploying.

**The right approach:** learn the lifecycle of the target command, read the **effective POM** accounting for inheritance/profiles, inspect plugin executions, and look up goal details. When you truly must observe the logged sequence of plugin goals, Maven must run the command with an appropriate scope; that is **no longer a dry-run**.

### 5.2. Checking which version and options Maven uses

~~~bash
./mvnw --version
./mvnw --help
~~~

**--version** identifies the running Maven/JDK version; **--help** displays supported options. In a project using Maven Wrapper on Windows, invoke **mvnw.cmd** accordingly. Using the Wrapper standardizes the Maven version, though it does not by itself guarantee plugins and JDKs match across all environments.

### 5.3. Reading the effective POM instead of looking only at root `pom.xml`

~~~bash
./mvnw help:effective-pom
./mvnw help:effective-pom -Dverbose=true
./mvnw help:active-profiles
~~~

- **help:effective-pom** shows the POM configuration after Maven merges parent, super POM, profiles, and inherited configuration.
- **-Dverbose=true** adds comments on the origin of elements in the effective POM (when using a Maven Help Plugin version that supports it); very useful for seeing whether an execution comes from the parent or the module itself.
- **help:active-profiles** shows which profiles are currently active, explaining extra plugins/dependencies/configs.

For example, if the real pipeline runs **./mvnw -Pci verify -DskipITs=true**, then when inspecting configuration you must include **-Pci** and the relevant properties:

~~~bash
./mvnw -Pci help:active-profiles
./mvnw -Pci help:effective-pom -Dverbose=true -DskipITs=true
~~~

If properties/profiles differ between inspection and execution, inferred details may not describe the real build accurately. Help commands normally do not invoke compile/test/package, yet they can still download plugin/dependency metadata into cache, and offer no absolute guarantee of zero external side effects.

**Important limitation:** the effective POM shows **configuration**, not a log listing every goal in runtime order. Default bindings per **packaging**, goals forked by plugins, runtime plugin logic, or directly invoked goals require further analysis. Do not read plugins in XML order and conclude that is the complete execution sequence.

### 5.4. Checking what a plugin goal does

~~~bash
./mvnw help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Dgoal=repackage -Ddetail=true
./mvnw help:describe -Dplugin=org.apache.maven.plugins:maven-surefire-plugin -Dgoal=test -Ddetail=true
~~~

**help:describe** displays the goal, purpose, parameters, and properties published by the plugin descriptor. For example:

- **spring-boot:repackage**: repackages a JAR/WAR to support Spring Boot execution.
- **surefire:test**: executes unit tests according to Maven Surefire Plugin configuration.
- **jar:jar**: creates a standard Java JAR.

This information helps understand "what does that plugin goal do?", yet describing a goal **does not prove the goal is bound to the `package` phase of the current project**. To know whether it is in the plan, combine lifecycle, packaging, and the **executions** section of the effective POM.

You can use the Spring Boot plugin's own help if the project has configured the plugin:

~~~bash
./mvnw spring-boot:help -Dgoal=repackage -Ddetail=true
~~~

The **help:describe** and **spring-boot:help** commands are purely plugin lookup tools; they do not run repackage.

## 6. Maven example for Spring Boot: predicting the `package` command

Suppose a project has a **pom.xml** using **spring-boot-starter-parent**, **jar** packaging, and declaring **spring-boot-maven-plugin**:

~~~xml
<!-- Illustrative snippet inside a complete pom.xml -->
<packaging>jar</packaging>

<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

This is a **POM snippet**, not a standalone runnable XML file: a real project must have **project**, **modelVersion**, **groupId/artifactId/version**, **parent**, and required dependencies. **spring-boot-starter-parent** provides a conventionally configured **repackage** execution; when not using this parent, verify whether the project binds the repackage goal to the lifecycle.

Suppose you intend to run:

~~~bash
./mvnw clean package
~~~

How to read the plan:

1. **clean** belongs to the clean lifecycle: its purpose is to remove previous build outputs (typically via **clean:clean**).
2. **package** belongs to the default lifecycle: Maven steps through preceding phases; with **jar** packaging, typical items involve resources, compile, test, and **jar:jar**.
3. The Spring Boot Maven Plugin has **repackage** bound to `package` by the parent/project configuration: after the original JAR is created, this goal repackages it into an executable JAR per Spring Boot conventions.
4. Custom plugins with executions in other phases, or active profiles, can add goals; check the effective POM and lifecycle bindings.
5. Because this is **not a dry-run**, actually running **./mvnw clean package** executes those plugin goals and may create/delete files, run tests, and update caches.

You can visualize the inspection diagram **conceptually**:

~~~text
User: ./mvnw clean package
       |
       +--> clean lifecycle: clean:clean
       |
       +--> default lifecycle up to package
                 |
                 +--> resources:resources
                 +--> compiler:compile
                 +--> resources:testResources
                 +--> compiler:testCompile
                 +--> surefire:test
                 +--> jar:jar
                 +--> spring-boot:repackage (if execution is bound)
~~~

The sequence above shows **typical goals**, omitting phases without bound goals and other plugins. In practice, final contents and order depend on packaging, Maven version, parent POM, custom executions, profiles, and invocation.

Steps to inspect without running `package`:

~~~bash
./mvnw help:active-profiles
./mvnw help:effective-pom -Dverbose=true
./mvnw help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Dgoal=repackage -Ddetail=true
~~~

Then look in the effective POM for **spring-boot-maven-plugin**, its **executions**, **goals**, **phase** (if declared), parent/plugin management, and implicit packaging bindings. If a repackage execution exists, verify whether it is actually active at the `package` phase in the plugin version being used. With a standard Spring Boot starter parent, the repackage goal is preconfigured once the plugin is declared.

## 7. Distinguishing "viewing help", "dry-run", and "real execution"

| Command | What can you read? | What must not be concluded? |
| --- | --- | --- |
| **./gradlew tasks --all** | Which tasks exist | Which tasks will definitely run when invoking build |
| **./gradlew help --task bootJar** | Description/path/options of `bootJar` | All transitive dependencies of `bootJar` |
| **./gradlew bootJar --dry-run** | Which tasks Gradle selects, expected display order | That Java compiled, tests passed, or JAR was generated |
| **./mvnw help:effective-pom** | POM after inheritance and active profiles | A complete runtime-ordered list of every goal |
| **./mvnw help:describe ...** | What a goal does and its parameters | That the goal is definitely invoked in the project |
| **./mvnw package** | Actually runs lifecycle up to `package` | Safe if you only wanted to read the plan |
| **./gradlew build** | Actually runs tasks per graph and state | Safe if you only wanted to view the task graph |

**Note on side effects:** Gradle's "dry-run" disables **task actions**, yet beforehand Gradle still needs to initialize, evaluate settings/build scripts, apply plugins, and construct the graph. If a build script or plugin performs I/O, network calls, or side effects during the **configuration phase**, using **--dry-run** alone will not prevent all such side effects. Therefore, do not call this an "absolute sandbox mode".

Additionally, dry-run may not accurately reflect **UP-TO-DATE**, **FROM-CACHE**, or test outcomes during a real run. Conditions or tasks created/adjusted based on environment and inputs can change the plan when those inputs change.

## 8. Reading plans accurately in multi-module projects

### 8.1. Gradle multi-project

Suppose settings has two Gradle subprojects **api** and **batch** (example names only). To view the Boot JAR packaging plan for **api** alone:

~~~bash
./gradlew :api:bootJar --dry-run
~~~

To compare with the overall build:

~~~bash
./gradlew build --dry-run
~~~

The second command may select more projects or tasks depending on how Gradle resolves task names and the root graph. Observe **task paths** in output: **:api:compileJava** differs from **:batch:compileJava** and from **:compileJava** at root. You cannot assume every subproject will build solely from the word `build`.

When needing to filter out a task:

~~~bash
./gradlew :api:build -x :api:test --dry-run
~~~

The new graph reflects that tests are excluded from this command. Do **not** use that result to conclude the pipeline skips tests if the real pipeline does not pass **-x**. Skipping tests can remove quality checks; the command only serves to observe plan changes.

### 8.2. Maven multi-module

Maven relies on the reactor and module selection options. For example:

~~~bash
./mvnw -pl api help:effective-pom
./mvnw -pl api help:active-profiles
~~~

**-pl api** selects the project/module using the appropriate reactor selector. To inspect the plan for a module that also depends on other projects in the reactor, consider **-am** (also-make) when invoking the real build. In practice, the exact way to scope modules also depends on module identifiers and `pom.xml` structure; verify with **./mvnw --help** and Maven reactor documentation.

With Maven multi-module, the plan must consider **lifecycle goals within each module**, packaging of each POM, reactor order by dependency relationships, inherited plugin executions, and active profiles. This analysis cannot be replaced by a single generic **--dry-run** line.

## 9. Reading logs and resolving mismatches between plan and execution

### Signs to watch out for

| Symptom | Possible explanation | How to verify |
| --- | --- | --- |
| Gradle dry-run includes **:bootJar** but real run produces no JAR | Task disabled, earlier task failed, output config, or task did not succeed | Read real logs, task conditions, and `build/libs` |
| Gradle output shows **SKIPPED** for every task in dry-run | Normal behavior of `--dry-run` | Do not report build/test PASS based on it |
| Gradle shows extra tasks from plugins | Plugins add dependencies to the graph | `help --task`, `build.gradle`, plugin docs |
| Maven runs **repackage** unexpectedly | Parent POM or execution binds goal to `package` | `help:effective-pom -Dverbose=true`, goal descriptor |
| Maven does not run repackage on `package` | Missing plugin/execution declaration, changed parent, or profile | Effective POM, goal binding |
| Maven executes goal in an unexpected phase | Execution specifies a custom phase or different default phase; different lifecycle/packaging | Plugin executions + lifecycle reference |
| CI runs more tasks/goals than laptop | Different active profiles/properties, wrapper version, module selectors, or JDK | Record the exact CI command and compare with identical flags |
| Gradle runs scripts/plugins and downloads data despite `--dry-run` | Configuration phase still executes | Inspect build scripts/plugins, caches, and logs |
| Command has **-DdryRun=true** in Maven yet still deletes/builds | Property is not a global Maven dry-run | Check the specific plugin's docs for `dryRun` support |

### Two common Spring Boot scenarios

**Scenario A: "I just want to see which steps `bootJar` will pull in."**

Use:

~~~bash
./gradlew help --task bootJar
./gradlew bootJar --dry-run
~~~

The first command checks that the task exists and its purpose. The second shows the planned task sequence. If you want to prove the artifact actually runs, you then need to **run a real build and `java -jar`** in an appropriate environment; dry-run does not prove that.

**Scenario B: "Why does `mvn package` automatically run Spring Boot repackage?"**

Use:

~~~bash
./mvnw help:effective-pom -Dverbose=true
./mvnw help:describe -Dplugin=org.springframework.boot:spring-boot-maven-plugin -Dgoal=repackage -Ddetail=true
~~~

Look for the parent, plugin execution, and binding to `package`. If the project inherits **spring-boot-starter-parent** and declares the Spring Boot Maven Plugin, the repackage execution is normally managed by the parent. There is no reason you have to run **mvn package** just to inspect this configuration preliminarily.

## 10. Practical workflow to avoid misreading plans

A short workflow applicable even when project configuration is unfamiliar:

**Step 1 — Record the exact target command.** For example, **./gradlew clean bootJar --no-daemon** or **./mvnw -Pci clean verify**. Flags, module selectors, and active profiles are part of the plan; omitting them changes the result.

**Step 2 — Check the tools.** Run **./gradlew --version** or **./mvnw --version**. Match task/goal names against the exact plugin version; do not mechanically apply examples from another Gradle/Maven version.

**Step 3 — Query with the right tools.**
- Gradle: **tasks**, **help --task**, then **--dry-run** for the **exact target command**.
- Maven: **help:active-profiles**, **help:effective-pom**, **help:describe**, combined with lifecycle/packaging bindings and plugin executions.

**Step 4 — Explain relationships.** When seeing an "unexpected" task/goal, identify whether it was triggered by direct command, dependency/binding, plugin, parent, or profile. Check the right module in multi-module projects.

**Step 5 — Label limitations clearly.** Label dry-run/config help output as **"planned execution"**, not build/test results. Any tasks that write/delete artifacts or touch external environments should be reviewed before running for real.

**Step 6 — Verify when needed.** Run the actual build in an authorized, suitable environment; compare real logs, test results, and generated JAR/image against predictions. The plan tells you "what it intends to do"; logs and artifacts tell you "what it actually did".

## 11. Self-check knowledge questions

**Question 1.** You run **./gradlew bootJar --dry-run**, and the output shows **:compileJava SKIPPED** and **:bootJar SKIPPED**. Which conclusion is correct?

**Answer:** `compileJava` and `bootJar` are in the plan, with task actions skipped. You must not conclude that code compiled, tests passed, or a JAR was created.

**Question 2.** You run **./mvnw help:effective-pom** and see Spring Boot Maven Plugin. Is it certain **mvn package** will run repackage?

**Answer:** Not certain from the plugin name alone. You must check that the **repackage** goal is bound in executions/lifecycle (in projects using **spring-boot-starter-parent**, the binding is usually present), along with packaging and active profiles.

**Question 3.** Can **./mvnw package -DdryRun=true** guarantee Maven will not delete files or run tests?

**Answer:** No. **dryRun** is not a global Maven lifecycle flag. Only a goal with such a parameter interprets that property according to its own rules; other goals can still execute.

**Question 4.** Why does **./gradlew tasks --all** not fully answer "what will `./gradlew build` run?"

**Answer:** A list of declared tasks is not the same as the set of tasks selected for a specific command. You need **./gradlew build --dry-run** to see the task graph constructed for that command.

**Question 5.** Does using Gradle's **--dry-run** strictly guarantee zero I/O access or side effects?

**Answer:** No. Gradle still evaluates configuration and plugins; poorly structured scripts can perform work outside task actions during the configuration phase.

## 12. Takeaways and official documentation

- For **Gradle**, inspect in the order **tasks → help --task → task --dry-run**. Treat the output as the **plan of the task graph**, not a build result. If your version supports **--task-graph**, use it for clearer dependency inspection.
- For **Maven**, inspect in the order **lifecycle/packaging → active profiles → effective POM → plugin executions/goal help**. Maven does not have a global lifecycle dry-run like Gradle.
- When analyzing **Spring Boot packaging**, inspect Gradle's **bootJar** or Maven's **repackage** goal, along with how the plugin is applied/bound in the project.
- Always distinguish **planned steps**, **actually executed steps**, and **real artifacts**.

### Official references

- Gradle — Command-Line Interface, Execution options and --dry-run: https://docs.gradle.org/current/userguide/command_line_interface.html
- Gradle — Understanding Tasks and help tasks: https://docs.gradle.org/current/userguide/more_about_tasks.html
- Gradle — Configuration Cache, dry-run during configuration phase: https://docs.gradle.org/current/userguide/configuration_cache_adoption.html
- Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven — Running Apache Maven: https://maven.apache.org/run.html
- Maven Help Plugin — Goals, effective POM and describe: https://maven.apache.org/plugins/maven-help-plugin/plugin-info.html
- Maven Help Plugin — Effective POM: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Maven Help Plugin — Configuring describe: https://maven.apache.org/plugins/maven-help-plugin/examples/describe-configuration.html
- Spring Boot Maven Plugin — Using the Plugin: https://docs.spring.io/spring-boot/maven-plugin/using.html
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html