# Distinguishing Gradle Arguments, JVM Properties, and Application Arguments in Spring Boot 3.3

## 1. Why Does the Same `-D` or `--` Produce Different Results?

When learning Spring Boot Externalized Configuration, developers often see commands like:

```bash
./gradlew bootRun -PdeployRegion=ap-southeast-1
./gradlew bootRun -Ddemo.region=ap-southeast-1
./gradlew bootRun --args='--demo.region=ap-southeast-1'
java -Ddemo.region=ap-southeast-1 -jar app.jar
java -jar app.jar --demo.region=ap-southeast-1
```

On the surface, all of them mention "region." Yet they **do not go to the same place** and are not processed by **the same program**:

- Gradle's `-P...` sets a **Gradle project property** for the build process.
- `-D...` placed after `gradlew` sets a **system property for the JVM running Gradle**, not automatically for the application JVM launched by `bootRun`.
- `--args='...'` on the `bootRun` task passes an argument string to **the application's `main(String[] args)` method**.
- `-D...` placed **before** `-jar` in the `java` command sets a **Java system property on the application JVM**.
- `--demo.region=...` placed **after** the JAR name is an **application argument**, which Spring Boot converts by default into a property in `Environment`.

A command can start successfully while the application keeps using the old configuration, simply because the value was mistakenly sent to **Gradle** instead of to the **Spring Boot application**.

This is the topic "Distinguishing Gradle arguments, JVM properties, and application arguments," part of the **Configuration Deployment** group under **Spring Boot Externalized Configuration**.

### Objectives

After this lesson, you will be able to:

1. Explain the boundaries between terminal/shell, Gradle, the application JVM, and Spring Boot.
2. Distinguish `-P`, `-D`, `--args`, `args`, `jvmArgs`, `systemProperty`, environment variables, and `--key=value`.
3. Write correct commands for `bootRun` and `java -jar` on Unix or PowerShell.
4. Understand why `-D` on a Gradle command does not propagate to the child JVM by default.
5. Intentionally bridge a Gradle project property to a Java system property or application argument when truly needed.
6. Explain how Spring Boot picks the final value when files, system properties, environment variables, and CLI supply the same key.
7. Use `System.getProperty`, `ApplicationArguments`, and `Environment` to diagnose actual values.
8. Avoid using `org.gradle.jvmargs` as a substitute for application JVM options.
9. Test on Gradle/CI and avoid exposing secrets in startup arguments.

Examples target **Java 17+**, **Spring Boot 3.3.x**, the project's Gradle Wrapper, and the Spring Boot Gradle plugin 3.3.x.

## 2. Four-Layer Diagram: Shell → Gradle → Application JVM → Spring Boot

A `bootRun` command passes through multiple layers:

```text
Bash / PowerShell / cmd
    |
    | parses quotes, environment variables, special characters
    v
./gradlew (or gradlew.bat)
    |
    | parses -P, -D, --offline, --info, task name
    v
Gradle build process / Gradle Daemon JVM
    |
    | reads build.gradle, gradle.properties, task configuration
    | executes bootRun task
    v
bootRun / JavaExec
    |
    | spawns application JVM (separate Java process)
    | sets jvmArgs, systemProperty, environment, args
    v
Application JVM
    |
    | receives -D..., -Xmx... before main class/JAR
    | System.getProperties()
    v
Spring Boot main(String[] args)
    |
    | receives --demo.region=... and other arguments
    | SpringApplication prepares Environment
    v
Spring Environment / Binder
    |
    +-- application JVM system properties
    +-- application OS environment variables
    +-- application.properties / YAML
    +-- application command-line properties
    |
    v
@Value / @ConfigurationProperties / Environment
```

With a direct `java -jar` command, there is no Gradle layer:

```text
Shell → Java launcher → Application JVM → Spring Boot
```

Therefore, ask before choosing syntax:

> Do I want to change the behavior of the **Gradle build**, the **JVM running the application**, or **Spring Boot configuration**?

The answer determines whether to use `-P`, `-D`, `--args`, or `--spring.some-key=value`.

## 3. Quick Comparison Table

| Syntax | Who handles it first? | Primary effect |
| --- | --- | --- |
| `./gradlew build --offline` | Gradle | Runs build without using network to fetch new dependencies |
| `./gradlew bootRun --info` | Gradle | Increases Gradle's log level |
| `./gradlew bootRun -Pstage=qa` | Gradle | Sets project property `stage` for the build |
| `./gradlew bootRun -Ddemo.mode=qa` | JVM/Gradle | Sets a Java system property on the Gradle side |
| `./gradlew bootRun --args='--demo.mode=qa'` | `bootRun` task | Passes `--demo.mode=qa` to the app's `main` |
| `java -Ddemo.mode=qa -jar app.jar` | Java launcher | Sets a system property on the **application JVM** |
| `java -Xmx512m -jar app.jar` | Java launcher | Limits the application JVM heap |
| `java -jar app.jar --demo.mode=qa` | Spring Boot | Receives an app option and puts it in `Environment` |
| `DEMO_MODE=qa java -jar app.jar` | Shell/OS | Sets an environment variable for the app process |
| `tasks.named("bootRun") { systemProperty(...) }` | Gradle task config | Configures a Java system property for the JVM spawned by `bootRun` |
| `tasks.named("bootRun") { jvmArgs(...) }` | Gradle task config | Configures JVM arguments for the application JVM |
| `tasks.named("bootRun") { args(...) }` | Gradle task config | Configures application arguments for the application JVM |

**Common trap:** both Gradle and Java use `-D` syntax, but the program **before `-D`** and how Gradle spawns processes decide which JVM owns that property.

## 4. First Layer: The Shell Parses the Command First

Before Gradle or Java sees the parameters, the terminal processes:

- Single or double quotes.
- Spaces and splitting into arguments.
- Environment variable expansion.
- Special characters such as `$`, `&`, `;`, `|`, `*`, `?`.
- Line continuation syntax.

Example in Bash:

```bash
./gradlew bootRun --args='--demo.message=hello world'
```

Outer quotes protect the space so `--args` receives a single string. The `bootRun` task parses that string and forwards the contents as application arguments according to Gradle's mechanism.

In PowerShell:

```powershell
.\gradlew.bat bootRun '--args=--demo.message=hello world'
```

This is passed by PowerShell as a single argument for Gradle. If you want to guarantee that an **application value containing spaces** stays a single argument after Gradle parses it, you must control **both quoting layers**: the shell layer and Gradle's parsing layer.

When spaces are tricky, a more reliable approach is configuring the argument list directly on the task:

```groovy
tasks.named("bootRun") {
    args("--demo.message=hello world")
}
```

Here `args(...)` takes **one element** of the application arguments list, avoiding nested quoting syntax inside a string.

### 4.1. Quotes are not part of the received value

When the shell runs:

```bash
export DEMO_MESSAGE='hello world'
```

the quotes normally only protect the string in the shell. The environment variable's value is `hello world`, without single-quote characters.

Similarly, in:

```bash
java -jar app.jar '--demo.message=hello world'
```

the application receives one argument with content `--demo.message=hello world`.

### 4.2. Do not reuse the exact same syntax across every shell

The command:

```bash
DEMO_MODE=qa java -jar app.jar
```

works in Unix shells like Bash, but is not valid environment variable assignment syntax in Windows PowerShell.

PowerShell:

```powershell
$env:DEMO_MODE = 'qa'
java -jar .\app.jar
```

Identify which shell you are running before copying examples from documentation.

## 5. Gradle Command-Line Options: `--info`, `--offline`, `-P`, `-D`

When you type:

```bash
./gradlew bootRun --info
```

`--info` asks Gradle for more verbose build logging. It does **not** automatically set:

```properties
logging.level.root=INFO
```

for the Spring Boot application. Similarly:

```bash
./gradlew bootRun --debug
```

requests debug logging for **Gradle**, and is not equivalent to:

```bash
java -jar app.jar --debug
```

which Spring Boot can interpret at the application layer.

Common Gradle options:

| Option | Meaning |
| --- | --- |
| `tasks` | Lists Gradle tasks |
| `build` | Runs the build task |
| `bootRun` | Task that runs Spring Boot inside Gradle |
| `--offline` | Restricts Gradle from using the network when resolving dependencies |
| `--info` / `--debug` | Increases Gradle's logging level |
| `--stacktrace` | Displays stack traces for Gradle errors |
| `--no-daemon` | Requests a Gradle run without reusing a long-lived daemon |
| `--max-workers=N` | Limits Gradle build workers |
| `-Pname=value` | Sets a Gradle project property |
| `-Dname=value` | Sets a system property for the Gradle JVM |
| `--args=...` with `bootRun` | Task option passing application arguments to the app process |

Do not conclude that `--max-workers=2` limits a business service's worker threads; it controls **Gradle build** concurrency, not Spring Boot thread pool configuration.

## 6. `-P` Is a Gradle Project Property

Example:

```bash
./gradlew bootRun -PdeployRegion=ap-southeast-1
```

The value `deployRegion` goes into **Gradle's project properties model**. The build script can read:

```groovy
def region = project.findProperty("deployRegion")
println("Gradle project property = " + region)
```

Or the Provider API:

```groovy
def region = providers.gradleProperty("deployRegion")
```

**However, Spring Boot does not automatically receive** `deployRegion` just because `-PdeployRegion=...` appeared on the command line.

By default, Java application code does not receive a Spring property named `deployRegion` from a Gradle project property. To pass it to the app, you need an **explicit bridge** in the `bootRun` task or via the deployment environment.

### 6.1. `-P` works even when the task does not run the app

Example:

```bash
./gradlew test -PtestGroup=smoke
```

The build script can use `testGroup` to select a test suite or configure the build. A project property belongs to the build scope and does not necessarily spawn an application JVM.

Do not use `-P` to represent production configuration that the artifact needs to read after deployment, unless the build/deployment has an explicit contract bringing that value into runtime.

### 6.2. Project properties can also come from `gradle.properties`

For example:

```properties
deployRegion=ap-southeast-1
```

in `gradle.properties` makes the Gradle project see `deployRegion`. That **does not turn it into** `app.region` in Spring `Environment`.

A project property can also be supplied via Gradle-supported forms such as:

```bash
./gradlew bootRun -Dorg.gradle.project.deployRegion=eu-west-1
```

or the corresponding Gradle environment variable:

```text
ORG_GRADLE_PROJECT_deployRegion
```

This mechanism only gives Gradle the corresponding project property; it does not automatically turn it into a Spring Boot property. Do not confuse the `org.gradle.project.` prefix with the `spring.*` configuration prefix.

## 7. `-D` After `gradlew` Belongs to Gradle's JVM

Example:

```bash
./gradlew bootRun -Ddemo.region=eu-central-1
```

Under Gradle's CLI rules, `-D` sets a **Java system property for the JVM executing Gradle**.

You can verify this in build logic:

```groovy
println("Gradle sees: " + System.getProperty("demo.region"))
```

However, the Spring Boot Gradle Plugin's `bootRun` task is a `JavaExec` task that launches the application in a **separate Java process**. It does not guarantee copying all of Gradle's `System.getProperties()` to the child JVM.

Therefore, inside the application JVM:

```java
System.getProperty("demo.region")
```

may return `null` even though Gradle saw `eu-central-1`, unless the task/launcher forwarded the value by another mechanism.

### 7.1. Comparing two commands that look alike

```bash
./gradlew bootRun -Ddemo.region=qa
```

Primary effect:

```text
Gradle build JVM: demo.region=qa
Boot application JVM: not guaranteed automatically
```

Whereas:

```bash
java -Ddemo.region=qa -jar app.jar
```

Primary effect:

```text
JVM directly running the app: demo.region=qa
Spring Environment: can usually read demo.region=qa
```

**The `-D` flag alone does not determine the target; the context of the Java launcher or Gradle launcher determines the target.**

### 7.2. `systemProp.*` in `gradle.properties`

For example:

```properties
systemProp.demo.region=qa
```

sets a system property in the Gradle environment. It is **not equivalent** to configuring:

```properties
demo.region=qa
```

in `application.properties`.

If `bootRun` needs this property, define explicit forwarding rather than relying on matching names across two ecosystems.

## 8. The Gradle Daemon Is a Separate JVM

Many Gradle setups use the **Gradle Daemon**, a persistent JVM that runs builds and can be reused.

A simplified model:

```text
Terminal
   |
   v
Gradle client / wrapper
   |
   v
Gradle daemon JVM
   |
   +-- reads build script
   +-- compiles, resolves dependencies
   +-- spawns process for bootRun
                |
                v
           Spring Boot JVM
```

Thus, Gradle can be using a 2 GB heap while the Java application launched by `bootRun` runs with a 512 MB heap limit, or vice versa.

### 8.1. `org.gradle.jvmargs` is for Gradle, not the application

In `gradle.properties`:

```properties
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
```

configures JVM arguments for the **Gradle Daemon** via Gradle's configuration mechanism.

It **does not replace**:

```bash
java -Xmx2g -jar app.jar
```

and does not mean the `bootRun` application's heap defaults to 2 GB.

If the application runs out of heap, increasing `org.gradle.jvmargs` may only give the **build** more memory without changing the Spring Boot process's memory limit.

### 8.2. How to set the application heap via `bootRun`

Groovy DSL:

```groovy
tasks.named("bootRun") {
    jvmArgs("-Xms128m", "-Xmx512m")
}
```

Or via the `JavaExec` API:

```groovy
tasks.named("bootRun") {
    minHeapSize = "128m"
    maxHeapSize = "512m"
}
```

These settings apply to the **application** process spawned by `bootRun`, not to the Gradle Daemon.

Note that multiple ways of configuring JVM args can interact; do not simultaneously specify conflicting options like `-Xmx512m` and `maxHeapSize="1g"` without understanding the final outcome. Keep one consistent convention.

### 8.3. `JAVA_TOOL_OPTIONS` and `JDK_JAVA_OPTIONS`

Java launcher environment variables can affect multiple Java processes started in that environment, including Gradle and the application JVM in certain scenarios.

Do not treat `JAVA_TOOL_OPTIONS` as a Gradle project property or a Spring application argument. It operates at the **Java tooling/launcher** layer. Because of its broad scope, use caution when setting it in shared CI terminals.

## 9. `bootRun` Spawns the Application JVM: The `JavaExec` API

In Spring Boot 3.3, the `bootRun` task is of type `BootRun`, which extends Gradle's `JavaExec`.

Accordingly, it has dedicated configuration groups:

| Task API | Affects |
| --- | --- |
| `args(...)` | Arguments passed to the app's `main(String[] args)` |
| `setArgs(...)` | List of application arguments |
| `jvmArgs(...)` | JVM arguments for the app process |
| `systemProperty(name, value)` | Java system property of the app process |
| `environment(name, value)` | Environment variable for the app process |
| `minHeapSize`, `maxHeapSize` | Heap of the application JVM |
| `workingDir` | Working directory of the app process |

These options are unlike `-P` or `-D` at the Gradle CLI level; they are defined **inside the task** to control the Java process that the task launches.

### 9.1. Configuring a system property for the application JVM

In `build.gradle` Groovy DSL:

```groovy
tasks.named("bootRun") {
    systemProperty("demo.region", "ap-southeast-1")
}
```

When `bootRun` runs, the application JVM can see:

```java
System.getProperty("demo.region")
```

and Spring Boot can look up:

```java
environment.getProperty("demo.region")
```

In this case, the task passes the property directly to the child JVM; it is not because a Gradle `-D` flag passed through on its own.

### 9.2. Configuring arguments for the application

```groovy
tasks.named("bootRun") {
    args("--demo.mode=qa", "--spring.profiles.active=dev")
}
```

These two strings are **two elements of application arguments**.

By default, Spring Boot converts `--demo.mode=qa` and `--spring.profiles.active=dev` into `Environment`, so beans see mode `qa` and profile `dev`.

### 9.3. Configuring environment variables for the application

```groovy
tasks.named("bootRun") {
    environment("DEMO_REGION", "ap-southeast-1")
}
```

This is an **environment variable of the application process**, different from:

```groovy
systemProperty("demo.region", "ap-southeast-1")
```

Both sources can be read by Spring Boot, though they differ in direct APIs:

```java
System.getenv("DEMO_REGION")
System.getProperty("demo.region")
```

Within Spring Boot, `Environment` also applies relaxed binding to environment variable names.

## 10. Using `--args` to Pass Runtime Arguments via `bootRun`

A common approach without editing the build script:

```bash
./gradlew bootRun --args='--demo.region=ap-southeast-1'
```

Here `--args` is a **task option of JavaExec/bootRun** used to pass an argument string to the application.

Equivalent in purpose to:

```bash
java -jar app.jar --demo.region=ap-southeast-1
```

Both place `--demo.region=...` into application arguments. It is not because Gradle accepted `-P` or the JVM accepted `-D`.

### 10.1. Multiple arguments

Bash:

```bash
./gradlew bootRun \
  --args='--demo.mode=qa --demo.worker-count=4 --spring.profiles.active=dev'
```

PowerShell:

```powershell
.\gradlew.bat bootRun '--args=--demo.mode=qa --demo.worker-count=4 --spring.profiles.active=dev'
```

Both examples pass **a single value** to the `--args` task option, containing three application arguments.

### 10.2. `--args` does not mean every string becomes a Spring property

If the application receives:

```text
--demo.mode=qa
```

Spring Boot reads it by default as an option property.

But if the application receives:

```text
job-123
```

that is a **non-option argument**. Spring Boot does not automatically interpret `job-123` as a `demo.job-id` property.

You can read such arguments via:

```java
ApplicationArguments#getNonOptionArgs()
```

or via `main(String[] args)`, depending on design.

### 10.3. `--args` belongs to the task, not the JVM runtime

Do not run a direct Java command like:

```bash
java -jar app.jar --args='--demo.mode=qa'
```

expecting the Java launcher to unwrap `--args`. Java has no built-in equivalent to the `bootRun --args` task option.

In a `java -jar` command, pass them directly:

```bash
java -jar app.jar --demo.mode=qa
```

## 11. Using `-P` and Deliberately Forwarding Values to the Application

This is an explicit Gradle pattern when a team wants a named project property for a run workflow.

### 11.1. Groovy DSL

In `build.gradle`:

```groovy
tasks.named("bootRun") {
    def region = providers.gradleProperty("deployRegion")
            .orElse("local")
            .get()

    systemProperty("demo.region", region)
}
```

Run:

```bash
./gradlew -PdeployRegion=eu-west-1 bootRun
```

Flow:

```text
Gradle -PdeployRegion=eu-west-1
             |
             v
providers.gradleProperty("deployRegion")
             |
             v
bootRun.systemProperty("demo.region", "eu-west-1")
             |
             v
Application JVM System.getProperty("demo.region")
             |
             v
Spring Environment demo.region
```

Here `-P` **does not reach the application on its own**. The `systemProperty(...)` call in the build script built the bridge.

### 11.2. Kotlin DSL

In `build.gradle.kts`:

```kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named<BootRun>("bootRun") {
    val region = providers.gradleProperty("deployRegion")
        .orElse("local")
        .get()

    systemProperty("demo.region", region)
}
```

The command remains:

```bash
./gradlew -PdeployRegion=eu-west-1 bootRun
```

The difference lies in Gradle's task configuration syntax. Do not copy Groovy DSL verbatim into `build.gradle.kts`.

### 11.3. When should you use this bridge?

Appropriate when:

- The build pipeline already has a centrally managed Gradle project property.
- The run task needs to forward a build-time value into runtime for a local test environment.
- You want to define a default for `bootRun` in the build script.
- You want to map a build-side property name to a different Spring Boot key.

Do not use project properties as a place to store long-lived secrets. `-Ppassword=...` can show up in command history, process lists, or CI logs.

## 12. Using `-P` and Forwarding to Application Arguments

Besides `systemProperty`, you can bridge a Gradle project property to an application argument.

Groovy DSL:

```groovy
tasks.named("bootRun") {
    def stage = providers.gradleProperty("deployStage")
            .orElse("local")
            .get()

    args("--demo.stage=${stage}")
}
```

Run:

```bash
./gradlew -PdeployStage=qa bootRun
```

The application JVM receives an argument:

```text
--demo.stage=qa
```

This mechanism differs in precedence from `systemProperty`:

- `systemProperty("demo.stage", "qa")` places the value into Spring's **Java system properties** source.
- `args("--demo.stage=qa")` places the value into Spring Boot's default **application command-line properties** source.

Under standard Spring Boot 3.3 precedence, command-line properties usually take precedence over Java system properties and config data.

### Caution when combining `args(...)` and `--args`

If the build script sets default application arguments and the caller also passes `bootRun --args='...'`, the task option may replace the argument list depending on how Gradle processes it. Do not build an application contract assuming the two argument sources **always concatenate automatically** without verifying.

If you need to merge arguments from multiple places, design an explicit rule in the build script and test what actually arrives in `ApplicationArguments`.

## 13. JVM Properties in the `java -jar` Command

When running the built artifact:

```bash
java -Ddemo.region=ap-southeast-1 -jar app.jar
```

`-Ddemo.region=...` appears **before** `-jar`, so the Java launcher handles it as a Java system property of the application JVM.

In Java:

```java
System.getProperty("demo.region")
```

returns the string if the property was set and not modified by other code.

Spring Boot also includes Java system properties in `Environment`, so:

```java
environment.getProperty("demo.region")
```

can receive the same value when no higher-precedence configuration source exists.

### 13.1. Relative order before `-jar`

JVM options appear before `-jar`:

```bash
java -Xms128m -Xmx512m -Ddemo.region=qa -jar app.jar
```

or:

```bash
java -Ddemo.region=qa -Xmx512m -jar app.jar
```

both set JVM options for the application, provided they sit where the Java launcher accepts JVM options.

Do not put `-D` **after** the JAR name and expect the Java launcher to process it:

```bash
java -jar app.jar -Ddemo.region=qa
```

In this command, `-Ddemo.region=qa` after the JAR is passed into **application arguments**. It is no longer a JVM `-D` flag in the Java launcher sense. Nor does Spring Boot automatically treat a single-dash `-D...` option as `--demo.region=...`.

### 13.2. Why is a Java system property different from an environment variable?

Java system property:

```java
System.getProperty("demo.region")
```

OS environment variable:

```java
System.getenv("DEMO_REGION")
```

are two different APIs.

`-Ddemo.region=qa` does not create an environment variable `DEMO_REGION`.

`DEMO_REGION=qa` does not automatically create an entry in `System.getProperties()` named `demo.region`.

Spring Boot can read **both sources** through `Environment`, then apply precedence and relaxed binding rules.

## 14. Application Arguments After the JAR

Another command:

```bash
java -jar app.jar --demo.region=qa
```

Here `--demo.region=qa` is **not** interpreted by the Java launcher as a system property. Java passes it as an argument to `main`, and `SpringApplication` by default collects options starting with `--` to place into `Environment`.

Example:

```java
SpringApplication.run(Application.class, args);
```

If you have not explicitly disabled command-line properties, you can use:

```java
environment.getProperty("demo.region")
```

to read `qa`.

If you only call:

```java
System.getProperty("demo.region")
```

it may return `null` because the application received the value from the **command-line property source**, not Java system properties.

### 14.1. Command-line properties can be disabled

Spring Boot allows:

```java
SpringApplication application =
        new SpringApplication(Application.class);

application.setAddCommandLineProperties(false);
application.run(args);
```

When using this setting, `--demo.region=qa` arguments can still exist in `ApplicationArguments`, but are **no longer automatically added** to `Environment` as a command-line property source.

Therefore, any precedence rule stating that CLI `--key=value` beats other sources must be understood as applying **with `SpringApplication`'s default configuration**.

### 14.2. Positional arguments

Example:

```bash
java -jar app.jar import orders.csv
```

`import` and `orders.csv` are non-option arguments, not equivalent to:

```properties
demo.import=orders.csv
```

If the application is a CLI tool, you can parse them yourself with `ApplicationArguments` or a dedicated CLI library.

## 15. Comparing Both `-D` Forms with the Same Key

Given a property:

```text
demo.stage
```

Four cases:

| Command | Gradle JVM sees it? | App JVM sees it as a System property? |
| --- | --- | --- |
| `./gradlew bootRun -Ddemo.stage=qa` | Likely yes | Not guaranteed automatically |
| `./gradlew bootRun --args='--demo.stage=qa'` | Not needed | No; app receives command-line argument |
| `java -Ddemo.stage=qa -jar app.jar` | No Gradle involved | Yes |
| `java -jar app.jar --demo.stage=qa` | No Gradle involved | Not necessarily; Spring Environment receives it |

A diagnostic rule:

```text
System.getProperty("demo.stage") != null?
    Yes -> A Java system property exists in the application JVM.
    No -> Not necessarily missing Spring config.
          Check command-line, env, YAML, profile.
```

And:

```text
environment.getProperty("demo.stage")
```

is the way to observe the value **effective for Spring**. Do not substitute one API for the other when distinguishing sources.

## 16. How Spring Boot Externalized Configuration Selects the Final Value

Suppose `application.properties` has:

```properties
demo.region=file-region
demo.mode=file-mode
```

And the application JVM is run with:

```bash
java -Ddemo.region=jvm-region -jar app.jar --demo.region=cli-region
```

In standard Spring Boot 3.3 configuration:

- The value in the configuration file is loaded.
- Java system property `demo.region=jvm-region` has higher precedence than config data.
- Command-line property `demo.region=cli-region` has higher precedence than the system property.

Therefore:

```java
System.getProperty("demo.region")
```

returns `jvm-region`, whereas:

```java
environment.getProperty("demo.region")
```

returns `cli-region`.

This is a very important example: **in the same application, two APIs return two different values, and both are correct according to their contracts**.

### 16.1. Simplified precedence order

For common sources, the typical relationship is:

```text
Spring Boot command-line properties
                |
                v higher precedence than
Application JVM Java system properties
                |
                v higher precedence than
Application OS environment variables
                |
                v higher precedence than
Config Data (application.properties/YAML)
                |
                v higher precedence than
Default properties
```

Spring Boot has many other sources such as JNDI, servlet parameters, `SPRING_APPLICATION_JSON`, test properties, DevTools, and custom sources. Do not treat this simplified diagram as a complete list for every environment.

When checking a specific value, inspect all active `PropertySources` and active profiles, not just one YAML file.

### 16.2. Gradle `-P` does not appear in this order

`-PdeployRegion=qa` is a Gradle project property, **not a Spring Boot `PropertySource` by default**.

It enters this diagram only when the build script **explicitly forwards** it to a system property, application argument, environment variable, or another appropriate delivery mechanism.

## 17. Complete Example: An Application Displaying Values at Each Layer

Create a small application to observe the different ways values are passed.

### 17.1. `application.properties`

`src/main/resources/application.properties`:

```properties
spring.application.name=gradle-jvm-args-demo

demo.region=from-file
demo.mode=default-mode
demo.worker-count=2
```

### 17.2. Spring Boot class and ApplicationRunner

`src/main/java/example/argslab/ArgsLabApplication.java`:

```java
package example.argslab;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ArgsLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ArgsLabApplication.class, args);
    }

    @Bean
    ApplicationRunner inspect(
            Environment environment,
            ApplicationArguments applicationArguments
    ) {
        return runnerArgs -> {
            String sysRegion = System.getProperty("demo.region");
            String envRegion = System.getenv("DEMO_REGION");
            String springRegion =
                    environment.getProperty("demo.region");

            System.out.println("System.getProperty(demo.region)="
                    + sysRegion);
            System.out.println("System.getenv(DEMO_REGION)="
                    + envRegion);
            System.out.println("Spring Environment demo.region="
                    + springRegion);

            System.out.println("Spring Environment demo.mode="
                    + environment.getProperty("demo.mode"));

            System.out.println("Spring Environment demo.worker-count="
                    + environment.getProperty("demo.worker-count"));

            List<String> cliRegions =
                    applicationArguments.getOptionValues("demo.region");
            System.out.println("CLI option demo.region=" + cliRegions);

            System.out.println("Source args="
                    + String.join(" ", applicationArguments.getSourceArgs()));
        };
    }
}
```

This class distinguishes:

1. `System.getProperty(...)`: Java system property **of the app JVM**.
2. `System.getenv(...)`: OS environment variable **of the app process**.
3. `environment.getProperty(...)`: effective value per Spring `PropertySources`.
4. `ApplicationArguments`: arguments **passed to `main`**, not necessarily properties.
5. `getSourceArgs()`: list of application arguments, excluding JVM `-D` flags already consumed by the launcher.

Printed lines contain only sample values. In real applications **do not print all arguments or secrets**; for example, `String.join` can leak passwords if the CLI contains credentials.

### 17.3. Running the app without overrides

```bash
./gradlew bootRun
```

When no other source supplies `demo.region`:

```text
System.getProperty(demo.region)=null
System.getenv(DEMO_REGION)=null
Spring Environment demo.region=from-file
Spring Environment demo.mode=default-mode
Spring Environment demo.worker-count=2
CLI option demo.region=null
```

This is illustrative output. Actual environment variables from the machine/CI can change the output.

## 18. Experiment 1 — `bootRun --args`

Bash:

```bash
./gradlew bootRun --args='--demo.region=from-args'
```

Expected in a clean environment:

```text
System.getProperty(demo.region)=null
System.getenv(DEMO_REGION)=null
Spring Environment demo.region=from-args
CLI option demo.region=[from-args]
```

Reason:

- `--args` passes the value to `main`.
- Spring Boot adds `--demo.region=from-args` as a command-line property.
- `System.getProperty` does not change automatically.

PowerShell:

```powershell
.\gradlew.bat bootRun '--args=--demo.region=from-args'
```

### Trying multiple options

```bash
./gradlew bootRun \
  --args='--demo.region=eu-west-1 --demo.mode=qa --demo.worker-count=4'
```

Inside the app:

```text
Spring Environment demo.region=eu-west-1
Spring Environment demo.mode=qa
Spring Environment demo.worker-count=4
```

Those values are received by the app as **command-line properties**.

## 19. Experiment 2 — `bootRun -D` Without a Bridge

Run:

```bash
./gradlew -Ddemo.region=from-gradle bootRun
```

If the build script does not forward this property to the application, the app environment may still see:

```text
System.getProperty(demo.region)=null
Spring Environment demo.region=from-file
CLI option demo.region=null
```

This does not prove Gradle ignored `-D`; it shows that a **Gradle JVM system property does not become an app JVM system property by default**.

Only if you previously configured in `build.gradle`:

```groovy
tasks.named("bootRun") {
    systemProperty("demo.region",
            System.getProperty("demo.region", "from-task-default"))
}
```

can `-Ddemo.region=from-gradle` affect the app via the **bridge specified by the build script**.

Distinguish the two scenarios so you do not draw false conclusions during code review.

## 20. Experiment 3 — `java -D... -jar`

First build the executable JAR with the Gradle task:

```bash
./gradlew bootJar
```

The actual JAR path depends on `group`, `version`, `archiveFileName`, module, and build config, usually under:

```text
build/libs/
```

Then run a specific JAR name, for example:

```bash
java -Ddemo.region=from-jvm -jar build/libs/argslab.jar
```

Replace `argslab.jar` with the generated artifact.

Illustrative output:

```text
System.getProperty(demo.region)=from-jvm
Spring Environment demo.region=from-jvm
CLI option demo.region=null
```

If the app has an environment variable or higher-precedence source, Spring `Environment` may select another value. The Java system property remains `from-jvm` unless code changes it inside the JVM.

### Trying `-D` in the wrong position

```bash
java -jar build/libs/argslab.jar -Ddemo.region=from-jvm
```

`-Ddemo.region=from-jvm` here **comes after the JAR**. That is an application argument, not a Java system property. Do not expect:

```java
System.getProperty("demo.region")
```

to return `from-jvm`.

If you want Spring Boot to receive a CLI setting, use:

```bash
java -jar build/libs/argslab.jar --demo.region=from-cli
```

## 21. Experiment 4 — JVM Property and Application Argument Together

Run:

```bash
java \
  -Ddemo.region=from-jvm \
  -jar build/libs/argslab.jar \
  --demo.region=from-cli
```

Expected:

```text
System.getProperty(demo.region)=from-jvm
Spring Environment demo.region=from-cli
CLI option demo.region=[from-cli]
```

In default Spring Boot 3.3, command-line properties beat Java system properties for the same key.

This is a great test to distinguish:

- What **data sources are present** in the JVM?
- What **value after precedence** does Spring select?

When using `@ConfigurationProperties`:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(String region) {}
```

The Binder receives the value from Spring `Environment`, so it typically sees `from-cli`, not because it reads `System.getProperty` directly.

## 22. Gradle Groovy DSL: Setting Values for bootRun

In `build.gradle`:

```groovy
tasks.named("bootRun") {
    systemProperty("demo.region", "from-task-system")
    environment("DEMO_MODE", "from-task-environment")
    jvmArgs("-Xms128m", "-Xmx512m")
    args("--demo.worker-count=5")
}
```

Meaning:

| Configuration | Target |
| --- | --- |
| `systemProperty("demo.region", ...)` | Application JVM; `System.getProperty` |
| `environment("DEMO_MODE", ...)` | App OS environment; `System.getenv` |
| `jvmArgs("-Xms128m", "-Xmx512m")` | JVM heap settings for the app |
| `args("--demo.worker-count=5")` | `ApplicationArgs` and Spring Boot CLI |

With the configuration above:

```text
demo.region=from-task-system
demo.mode=from-task-environment
demo.worker-count=5
```

can be the effective Spring values if no higher-precedence source overrides them.

**Note:** setting a fixed task default for `demo.region` can override a developer's YAML file and cause surprise. Only do this if the team truly wants `bootRun` to follow a dedicated convention. If you want a true fallback, consider supplying the value via a common config file or controlling precedence.

## 23. Gradle Kotlin DSL: Equivalent Configuration

In `build.gradle.kts`:

```kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named<BootRun>("bootRun") {
    systemProperty("demo.region", "from-task-system")
    environment("DEMO_MODE", "from-task-environment")
    jvmArgs("-Xms128m", "-Xmx512m")
    args("--demo.worker-count=5")
}
```

The methods correspond to `JavaExec`, though call syntax, task type, and the Provider API differ from Groovy DSL.

When reading examples online, check whether the project's file is:

```text
build.gradle     (Groovy DSL)
build.gradle.kts (Kotlin DSL)
```

Avoid mixing:

```groovy
systemProperty "demo.region", "qa"
```

into `.kts` because that is Groovy syntax, not Kotlin.

## 24. Rules for Gradle Project Properties in CI

Suppose a pipeline runs:

```bash
./gradlew -PdeployRegion=eu-west-1 bootRun
```

If the build script reads `deployRegion` and assigns:

```groovy
systemProperty("demo.region",
        providers.gradleProperty("deployRegion").get())
```

then the application receives the value via a Java system property.

But when building the executable JAR:

```bash
./gradlew -PdeployRegion=eu-west-1 bootJar
```

**it does not mean** the generated JAR will automatically carry `eu-west-1` region configuration everywhere it runs later.

This is the major difference between:

- **Build-time data**: used to configure tasks, artifact names, versions, compiler.
- **Run-time data**: read when the application runs in a container, VM, or Kubernetes.

A workflow may intentionally bake a value into the artifact at build time, but that is a deliberate design decision. Spring Boot externalized configuration usually aims to **keep the same artifact** across many environments, passing values via runtime sources at deployment time.

### Example deployment keeping the artifact immutable

Build:

```bash
./gradlew clean bootJar
```

Staging:

```bash
java -jar app.jar --spring.profiles.active=staging
```

Production:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Or supply environment variables from the container platform. The same JAR can run in both environments with different configuration, without rebuilding just to change a property.

## 25. Spring Profiles via Three Paths

A typical example is activating the `dev` profile.

### 25.1. Direct application argument

```bash
java -jar app.jar --spring.profiles.active=dev
```

This is a Spring Boot CLI property.

### 25.2. Application JVM system property

```bash
java -Dspring.profiles.active=dev -jar app.jar
```

This is a Java system property read by Spring Boot from `Environment`.

### 25.3. bootRun task option

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

This is how you pass a Spring Boot CLI property to the JVM launched by `bootRun`.

### 25.4. Be careful with this form

```bash
./gradlew bootRun -Dspring.profiles.active=dev
```

This sets `spring.profiles.active` on Gradle's JVM; it is **not by default** a way to enable the Spring Boot application's profile in the process spawned by `bootRun`.

If a project has a bridge in the build script, this command might work, but that is the result of **custom task configuration** and must not be described as the default for every project.

## 26. Application Environment Variables Are Not Gradle Properties

A value:

```text
DEMO_REGION=ap-southeast-1
```

can be recognized by Spring Boot relaxed binding under the name:

```text
demo.region
```

In Bash:

```bash
DEMO_REGION=ap-southeast-1 java -jar app.jar
```

Or with `bootRun`:

```bash
DEMO_REGION=ap-southeast-1 ./gradlew bootRun
```

In PowerShell:

```powershell
$env:DEMO_REGION = 'ap-southeast-1'
.\gradlew.bat bootRun
```

With standard `JavaExec` configuration, the application process can inherit environment variables from the launching process or receive those explicitly configured on the task. Still, do not equate:

```text
DEMO_REGION
```

with:

```text
ORG_GRADLE_PROJECT_deployRegion
```

The first targets a Spring Boot environment property under the corresponding naming rule; the second is a way for Gradle to receive a **project property**.

### 26.1. Canonical naming rule for Spring Boot

A key:

```text
demo.worker-count
```

typically maps to the environment variable:

```text
DEMO_WORKERCOUNT
```

Environment variable name-binding rules:

1. Replace `.` with `_`.
2. Remove `-`.
3. Convert to uppercase.

Do not assume `DEMO_WORKER_COUNT` is completely equivalent to `demo.worker-count` across all Binder rules; clearly distinguish hyphens within a segment from hierarchy dots.

### 26.2. Clean up environment variables after experimenting

PowerShell:

```powershell
Remove-Item Env:DEMO_REGION
```

Bash:

```bash
unset DEMO_REGION
```

Avoid leaving an environment variable from a previous experiment silently overriding config files on the next run.

## 27. Spring Boot Properties and JVM Options Can Live at Different Layers

Example:

```bash
java -Xmx512m -Duser.timezone=UTC -jar app.jar --server.port=8081
```

In which:

- `-Xmx512m`: JVM heap option.
- `-Duser.timezone=UTC`: Java system property affecting JVM/Java API timezone settings.
- `--server.port=8081`: Spring Boot application property controlling the embedded server port if the app has a web server.

Changing `server.port` is not changing a JVM option. Changing `-Xmx` is not a property for the Binder to convert into `DataSize`.

Some Java system properties are also meaningful to Spring Boot because Spring includes them in `Environment`. However, not every JVM option has a corresponding Spring property key.

For example, `-XX:+UseG1GC` is processed by the JVM; it cannot be replaced with:

```properties
spring.jvm.use-g1-gc=true
```

unless you wrote a very specialized mechanism yourself, and even then many JVM flags must be set **before the JVM starts**.

## 28. Distinguishing `-D` and `--` in Spring Boot

Suppose the same key:

```text
demo.timeout
```

Command A:

```bash
java -Ddemo.timeout=5s -jar app.jar
```

Command B:

```bash
java -jar app.jar --demo.timeout=5s
```

With `@ConfigurationProperties`:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(Duration timeout) {}
```

both A and B can make the Binder receive `Duration.ofSeconds(5)`.

However, **the represented sources differ**:

- A goes through Java system properties.
- B goes through the Spring Boot command-line property source.

If both are present with different values:

```bash
java -Ddemo.timeout=5s -jar app.jar --demo.timeout=8s
```

then Spring Boot by default prefers the command-line property `8s`.

If code calls:

```java
System.getProperty("demo.timeout")
```

it still only sees `5s`, not Spring's merged value.

## 29. Do Not Confuse Gradle Task Options with Spring Boot Application Options

Compare the pair of commands:

```bash
./gradlew bootRun --debug
```

and:

```bash
./gradlew bootRun --args='--debug'
```

The first uses `--debug` for **Gradle** logging.

The second passes `--debug` into **Spring Boot** application arguments. Spring Boot can enable debug mode depending on application capabilities and related configuration.

Similarly:

```bash
./gradlew bootRun --info
```

is not equivalent to:

```bash
./gradlew bootRun --args='--logging.level.root=INFO'
```

The first affects Gradle logging; the second affects a Spring Boot logging property.

### What about `--stacktrace`?

`--stacktrace` is a Gradle error-diagnostic option; it does not automatically make the Java app print stack traces under an equivalent rule.

When diagnosing the app, inspect startup logs and the app's logging configuration; when diagnosing task/build failures, use Gradle's `--stacktrace`, `--info`, and `--debug` as needed.

## 30. Comparing Commands on Bash and PowerShell

| Purpose | Bash/Unix | PowerShell/Windows |
| --- | --- | --- |
| Run Gradle | `./gradlew bootRun` | `.\gradlew.bat bootRun` |
| App CLI region | `./gradlew bootRun --args='--demo.region=qa'` | `.\gradlew.bat bootRun '--args=--demo.region=qa'` |
| Gradle property | `./gradlew -PdeployRegion=qa bootRun` | `.\gradlew.bat -PdeployRegion=qa bootRun` |
| Gradle JVM system property | `./gradlew -Ddemo.region=qa bootRun` | `.\gradlew.bat -Ddemo.region=qa bootRun` |
| App JVM property | `java -Ddemo.region=qa -jar app.jar` | `java -Ddemo.region=qa -jar .\app.jar` |
| App CLI property | `java -jar app.jar --demo.region=qa` | `java -jar .\app.jar --demo.region=qa` |
| Environment variable | `DEMO_REGION=qa java -jar app.jar` | `$env:DEMO_REGION='qa'; java -jar .\app.jar` |

For strings containing spaces, special characters, or JSON values, add quoting appropriate to the shell. Do not conclude a Gradle command is wrong just because Unix syntax was copied verbatim into PowerShell.

## 31. `spring.config.location` and When It Is Read

Some Spring Boot properties are consumed **very early**, before or during Config Data preparation:

```text
spring.config.name
spring.config.location
spring.config.additional-location
```

Therefore, when you want to change where Spring Boot searches for configuration files, you can use a runtime argument:

```bash
java -jar app.jar \
  --spring.config.location=optional:file:./config/
```

or an application JVM system property:

```bash
java \
  -Dspring.config.location=optional:file:./config/ \
  -jar app.jar
```

With `bootRun`, the explicit form is:

```bash
./gradlew bootRun \
  --args='--spring.config.location=optional:file:./config/'
```

**Do not assume** that:

```bash
./gradlew bootRun \
  -Dspring.config.location=optional:file:./config/
```

will make the Spring Boot app read the right location, because Gradle's `-D` is not guaranteed to be forwarded to the app JVM.

### `spring.config.location` and relative paths

The path `./config/` is resolved relative to the **application's working directory**, not necessarily the directory you had in mind.

`bootRun` has a working directory determined by the Gradle task; when running a JAR from a terminal, the working directory is usually the current directory. If the same relative path produces different results, check:

```java
System.getProperty("user.dir")
```

inside the application JVM, along with task `workingDir` if specially configured.

## 32. `SPRING_APPLICATION_JSON` Is Yet Another Source

Spring Boot allows passing JSON configuration via an environment variable or system property:

Bash:

```bash
SPRING_APPLICATION_JSON='{"demo":{"region":"qa","worker-count":3}}' \
  java -jar app.jar
```

Or:

```bash
java \
  -Dspring.application.json='{"demo":{"region":"qa","worker-count":3}}' \
  -jar app.jar
```

Or:

```bash
java -jar app.jar \
  --spring.application.json='{"demo":{"region":"qa","worker-count":3}}'
```

These commands can all deliver JSON data into Spring `Environment`, though through distinct specific sources.

### Why avoid JSON when it is unnecessary?

When a simple scalar key can be passed via:

```bash
java -jar app.jar --demo.region=qa
```

that is much easier to read than nested JSON inside quotes. `SPRING_APPLICATION_JSON` is useful when an environment or deployment tool makes dotted keys or lists awkward, but it carries quoting overhead and debugging difficulty.

`null` in JSON also does not work by default as a command to erase values from lower-precedence sources; `PropertySourcesPropertyResolver` treats a `null` property as missing in many cases.

## 33. Building the JAR and Running the JAR Are Two Separate Things

Separate the two deployment steps:

### Build

```bash
./gradlew clean bootJar
```

Creates the executable JAR. Gradle project properties, `org.gradle.jvmargs`, the Gradle daemon, and the build environment participate in executing the task.

### Run

```bash
java -jar build/libs/app.jar --spring.profiles.active=prod
```

Starts the application. Spring Boot properties are read according to this command's **runtime environment**.

Between build and run there can be:

- Two different terminals.
- Two different machines.
- A CI server and a container.
- A developer and a production host.
- Two users with different environment variables.

Therefore:

```bash
./gradlew -Pstage=prod bootJar
```

is not equivalent to:

```bash
java -jar app.jar --spring.profiles.active=prod
```

unless the build script actively encoded the profile into the artifact or a deployment script supplies the profile at runtime. Do not implicitly assume that across the entire project.

## 34. `bootRun` Is Convenient for Development, Not a Full Replica of Packaged Deployment

`bootRun` typically runs the application using the `main` source set's runtime classpath without requiring an executable JAR to be created first.

When running the JAR:

```bash
java -jar build/libs/app.jar
```

classpath, working directory, packaged resources, and deployment environment may differ. Therefore, the same property may come from a different source if you do not keep configuration aligned.

Possible differences include:

- External config files outside the JAR.
- Working directory and relative paths.
- Shell/CI/container environment variables.
- JVM options from the launcher or task.
- Runtime profile.
- Application arguments.
- Whether built source resources are up to date.
- Presence of DevTools or development-only dependencies.

When a bug only appears in the packaged JAR, check these differences before concluding the Binder mechanism changed.

## 35. Gradle `-Dorg.gradle.jvmargs` Does Not Replace App `jvmArgs`

Pair of examples:

```bash
./gradlew bootRun -Dorg.gradle.jvmargs='-Xmx2g'
```

and in `build.gradle`:

```groovy
tasks.named("bootRun") {
    jvmArgs("-Xmx2g")
}
```

Do not treat these two as equivalent.

The first relates to how Gradle configures the JVM for the **build/daemon process**. The second configures the JVM that `bootRun` uses for the **application**.

In practice, Gradle may have to spawn a new daemon when JVM settings change; exact behavior depends on Gradle configuration. What remains critical is the **process boundary**.

For the JAR's runtime heap, use:

```bash
java -Xmx2g -jar app.jar
```

For heap during `bootRun`, use `JavaExec` task configuration or an appropriate app launch mechanism.

## 36. Distinguishing System Properties from Gradle Project Properties in build.gradle

In Groovy DSL:

```groovy
def projectValue = project.findProperty("demoRegion")
def gradleSystemValue = System.getProperty("demo.region")

println("projectValue=" + projectValue)
println("gradleSystemValue=" + gradleSystemValue)
```

With:

```bash
./gradlew -PdemoRegion=eu-west-1 -Ddemo.region=qa help
```

the two values differ:

```text
projectValue=eu-west-1
gradleSystemValue=qa
```

Yet both are data **inside the Gradle process**, not proof that the Spring Boot app received them.

### Provider API

Gradle can access project properties and system properties lazily:

```groovy
providers.gradleProperty("demoRegion")
providers.systemProperty("demo.region")
```

These providers are suitable when wiring Gradle values into task configuration. Do not mistake `providers.systemProperty(...)` for a Spring `Environment` API.

## 37. Testing Precedence with a Hands-On Matrix

Using the application from Section 17, test these sources:

| `application.properties` | OS env | App JVM `-D` | Spring app `--` | Effective Spring value (default) |
| --- | --- | --- | --- | --- |
| `from-file` | None | None | None | `from-file` |
| `from-file` | `from-env` | None | None | `from-env` |
| `from-file` | `from-env` | `from-jvm` | None | `from-jvm` |
| `from-file` | `from-env` | `from-jvm` | `from-cli` | `from-cli` |
| `from-file` | None | `from-jvm` | `from-cli` | `from-cli` |

This matrix applies to the listed sources and Spring Boot 3.3's default order; custom `PropertySource`s, test properties, `SPRING_APPLICATION_JSON`, servlet/JNDI, or special configurations can yield different results.

**Do not put Gradle `-P` or `-D` into the matrix as automatic Spring inputs.** If you want to test them, add a separate row only when the build script has a bridge.

## 38. Common Errors and Fixes

| Symptom | Typical cause | Fix |
| --- | --- | --- |
| `-PdemoRegion=qa` yet app still gets default | Gradle project property does not auto-forward to app | Use `--args` or task `systemProperty`/`args` |
| `./gradlew bootRun -Ddemo.region=qa` has no effect | `-D` was set on the Gradle JVM | Use `--args` or an explicit bridge |
| `System.getProperty` is null yet Spring `Environment` has value | Value came from CLI/YAML/env, not Java system property | Use `Environment`/Binder to inspect Spring values |
| `java -jar app.jar -Ddemo.region=qa` has no effect | `-D` came after the JAR | Move `-D` before `-jar` |
| `--info` does not raise Spring log level | `--info` is a Gradle option | Use `--args='--logging.level.root=INFO'` |
| `--debug` increases Gradle logs but not Boot debug | Option applied to Gradle | Use `bootRun --args='--debug'` |
| `org.gradle.jvmargs=-Xmx2g` yet app still lacks heap | Configured Gradle JVM, not app | Use `bootRun.jvmArgs` or `java -Xmx2g` |
| Passing `--spring.profiles.active=dev` via `-P` has no effect | Build property does not become runtime property | Use Spring CLI directly |
| Profile-specific YAML not seen | Active profile was not supplied to app JVM | Check `Environment#getActiveProfiles()` |
| Build script gets project property but app does not | Missing bridge or task not running as expected | Check `bootRun` configuration |
| Command line with spaces corrupts value | Shell and Gradle parse arguments differently | Quote properly or configure `args` as a list |
| Works in CI, fails on developer machine | Different env vars, JDK, `workingDir`, artifact | Compare runtime layer, not just Gradle options |
| `System.getenv` differs from Spring `Environment` | Multiple sources with precedence | Inspect all `PropertySources` |
| Java heap differs from expectation | Confused Gradle daemon with app JVM | Inspect app JVM and how it is launched |
| App arguments are right yet Spring ignores them | `setAddCommandLineProperties(false)` | Check `SpringApplication` configuration |
| External config file not found | Different relative path/working directory | Check `user.dir`/`workingDir` |
| Config overridden by CLI despite valid file | CLI has higher precedence | Verify final value; avoid futile file edits |
| `-D` missing in a custom `JavaExec` task | Task did not configure `systemProperty` | Explicitly set `systemProperty`/`jvmArgs` on that task |

## 39. Diagnosing Layer by Layer Instead of Guessing Randomly

When Spring Boot does not pick up a property, check in order.

### Step 1 — Did the shell split the command correctly?

- Are quotes properly placed around arguments with spaces?
- Are `$` or `&` characters being interpreted by the shell beforehand?
- Are you running Bash, zsh, PowerShell, or cmd?
- Is `--args` actually a task option of `bootRun` in the command used?

### Step 2 — Did the value stop at Gradle or reach the app JVM?

- Was `-P` read by the build script?
- Was Gradle `-D` forwarded?
- Does the `bootRun` task configure `systemProperty`, `jvmArgs`, and `args` properly?
- Are you running `java -jar` directly or a `JavaExec` task?

### Step 3 — Are the Java system property and environment variable present?

Inside the app JVM:

```java
System.getProperty("demo.region")
System.getenv("DEMO_REGION")
```

Do not print all properties or secrets. Only inspect one non-sensitive sample key.

### Step 4 — Which source did Spring Environment select?

```java
environment.getProperty("demo.region")
```

If it differs from `System.getProperty`, check CLI, environment variables, Config Data, and other sources.

### Step 5 — Did Binder and validation succeed?

Even if the final value is right, the config might have the wrong type:

```properties
demo.worker-count=abc
```

or the right type but an invalid value:

```properties
demo.worker-count=-1
```

This is a conversion and validation issue, no longer Gradle property forwarding.

### Step 6 — Are there other runtime dependencies?

For example, a valid endpoint may point to an unreachable external service, or the right port may already be occupied by another process. Do not treat every startup error as a Gradle argument mistake.

## 40. Experimenting with `ApplicationArguments`

`ApplicationArguments` is useful because it shows the arguments **that actually reached `main`**.

Example:

```java
@Bean
ApplicationRunner printArgs(ApplicationArguments applicationArguments) {
    return args -> {
        System.out.println(
                applicationArguments.getOptionNames());
        System.out.println(
                applicationArguments.getNonOptionArgs());
    };
}
```

Place this method inside a `@Configuration` or `@SpringBootApplication` class.

With:

```bash
java -jar app.jar --demo.region=qa job-123
```

you can observe:

```text
optionNames contains demo.region
nonOptionArgs contains job-123
```

`-Ddemo.region=qa` placed before `-jar` does not appear in `ApplicationArguments`, because the Java launcher already consumed it to create a system property before invoking `main`.

Conversely, if `-Ddemo.region=qa` is placed after the JAR, it may end up in non-option args or be handled by custom CLI code, without becoming a JVM system property.

## 41. Avoiding Errors When Using the Gradle Wrapper

In a project that already includes the Gradle Wrapper, use:

Bash/Unix:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

Instead of relying on a globally installed Gradle whose version differs from the project's:

```bash
gradle bootRun
```

The Wrapper selects the Gradle version configured by the project, keeping results largely consistent between developers and CI.

However, the Wrapper does not automatically synchronize the **JDK in use**, OS environment variables, secrets, working directory, or CI-supplied properties. When diagnosing runtime configuration, still verify actual inputs.

## 42. Passing Properties Containing Spaces and Special Characters

Illustrative value:

```text
demo.message=hello Spring Boot
```

With a direct JAR in Bash:

```bash
java -jar app.jar '--demo.message=hello Spring Boot'
```

In PowerShell:

```powershell
java -jar .\app.jar '--demo.message=hello Spring Boot'
```

In `bootRun`, a clean approach is:

```groovy
tasks.named("bootRun") {
    args("--demo.message=hello Spring Boot")
}
```

This creates a single argument element, so callers do not have to construct multi-layer escaped strings.

If you want to control it via Gradle CLI, pass the `--args` task value per shell and Gradle parser rules. For complex/JSON values, consider an external configuration file, environment variables, or `SPRING_APPLICATION_JSON` if appropriate.

**Do not put passwords or tokens in command-line examples or logs.** Operating systems, shell history, or monitoring tools can record process arguments.

## 43. Deployment Design for Containers and Kubernetes

In containers, many setups do not include Gradle in the runtime image. The build happens beforehand:

```bash
./gradlew bootJar
```

The runtime image contains only the Java runtime and the JAR, then runs:

```bash
java -jar app.jar
```

or uses environment variables supplied by the container platform:

```text
SPRING_PROFILES_ACTIVE=prod
DEMO_REGION=ap-southeast-1
```

In this model:

- Gradle `-P` only has meaning during the build phase.
- `org.gradle.jvmargs` has no effect on the container runtime if Gradle does not run there.
- JVM flags for the app process can be placed in a controlled entrypoint/launcher.
- Spring Boot configuration should come from environment variables, Config Data, volumes/config trees, or args per deployment conventions.

Using the same JAR across multiple environments reduces artifact drift, though you still need to control final configuration and security policies.

### 43.1. Two-stage CI pipeline

Example:

```text
CI build stage
    ./gradlew test bootJar -PbuildFlavor=release
            |
            v
    artifact: app.jar
            |
            v
Deploy stage
    java -Xmx512m -jar app.jar --spring.profiles.active=prod
```

`buildFlavor` can affect the build if the build script uses it. `spring.profiles.active` in the deploy step is read by the app at runtime. Do not infer a production profile merely because the build included the word `release`.

## 44. Exercise 1 — Classifying 10 Parameters

Given these strings:

```text
-Pstage=qa
-Ddemo.region=qa
--offline
--info
--args=--demo.region=qa
jvmArgs("-Xmx512m")
systemProperty("demo.region", "qa")
args("--demo.region=qa")
java -Ddemo.region=qa -jar app.jar
java -jar app.jar --demo.region=qa
```

**Task:** classify each as Gradle build input, Gradle task forwarding, app JVM option, or application argument.

**Answer:**

- `-Pstage=qa`, `-Ddemo.region=qa` after `gradlew`, `--offline`, `--info`: belong to Gradle.
- `bootRun`'s `--args`, `args(...)`: pass application arguments to the app.
- `jvmArgs(...)`, `systemProperty(...)` inside `bootRun`: configure JVM options/system properties for the app process.
- `java -D... -jar`: app Java system property.
- `java -jar ... --demo.region=qa`: Spring Boot application argument.

## 45. Exercise 2 — Gradle Daemon and Heap

In `gradle.properties`:

```properties
org.gradle.jvmargs=-Xmx3g
```

**Question:** Is the application JVM during `bootRun` guaranteed a 3 GB max heap?

**Answer:** No. That property configures the JVM for Gradle. The app JVM spawned by `bootRun` can have different JVM options and heap settings. To control app heap, configure `bootRun.jvmArgs`, `maxHeapSize`, or the corresponding runtime Java launcher flags.

## 46. Exercise 3 — Profile Not Activated

Command:

```bash
./gradlew bootRun -Dspring.profiles.active=prod
```

Yet the application still uses the default profile.

**Question:** What is the likely cause?

**Answer:** `-D` was passed to the Gradle JVM. The `bootRun` task does not automatically copy all system properties to the application JVM. Use:

```bash
./gradlew bootRun --args='--spring.profiles.active=prod'
```

or configure:

```groovy
tasks.named("bootRun") {
    systemProperty("spring.profiles.active", "prod")
}
```

## 47. Exercise 4 — `System.getProperty` and Environment Differ

Command:

```bash
java -Ddemo.region=jvm -jar app.jar --demo.region=cli
```

**Question:** What do the two APIs return?

**Answer:**

```text
System.getProperty("demo.region") -> jvm
environment.getProperty("demo.region") -> cli
```

with default Spring Boot command-line properties and no unusual higher-precedence source.

## 48. Exercise 5 — Gradle `-P` Does Not Reach Runtime

Command:

```bash
./gradlew -PdeployRegion=ap-southeast-1 bootRun
```

The Java app still reads `demo.region=from-file`.

**Question:** Is there a Binder bug?

**Answer:** There is no evidence of a Binder bug. A Gradle project property does not automatically map to `demo.region`. A bridge is needed:

```groovy
tasks.named("bootRun") {
    systemProperty("demo.region",
            providers.gradleProperty("deployRegion").get())
}
```

Or pass:

```bash
./gradlew bootRun --args='--demo.region=ap-southeast-1'
```

## 49. Exercise 6 — Putting `-D` After the JAR

Command:

```bash
java -jar app.jar -Ddemo.mode=qa
```

**Question:** Is `System.getProperty("demo.mode")` guaranteed to be `qa`?

**Answer:** No. The Java launcher already encountered `-jar` and the JAR name; strings after it are application arguments, not JVM options. Put `-Ddemo.mode=qa` before `-jar`, or use `--demo.mode=qa` after the JAR if you want a Spring Boot application property.

## 50. Exercise 7 — Environment Variable or Gradle Property?

Given two variables:

```text
DEMO_MODE=qa
ORG_GRADLE_PROJECT_deployStage=qa
```

**Question:** Which targets Spring Boot runtime, and which targets a Gradle project property?

**Answer:** `DEMO_MODE` is an environment variable that Spring Boot can bind to `demo.mode`. `ORG_GRADLE_PROJECT_deployStage` is a way for Gradle to receive project property `deployStage`; it does not automatically become `demo.stage` in Spring `Environment`.

## 51. Exercise 8 — Logger

Command:

```bash
./gradlew bootRun --debug
```

**Question:** Is the Spring Boot application guaranteed to log at DEBUG level?

**Answer:** No. The `--debug` flag belongs to Gradle. If you want Spring Boot to receive `--debug`, use:

```bash
./gradlew bootRun --args='--debug'
```

or set the appropriate `logging.level.*` settings for the application.

## 52. Exercise 9 — Storing Secret Values

A team proposes:

```bash
./gradlew -PapiPassword=very-secret bootRun
```

and forwarding it to a Java system property.

**Question:** Should this approach be used for production secrets?

**Answer:** Do not use exposed CLI arguments or Gradle project properties this way as a default solution. They can appear in shell history, process lists, and build logs. Prefer a secret manager, protected file mounts, or platform-managed secret delivery, with proper access control and without logging values.

## 53. Exercise 10 — Application in CI

CI runs:

```bash
./gradlew -Pstage=production bootJar
```

then deploys:

```bash
java -jar app.jar
```

**Question:** Does the application definitely have `spring.profiles.active=production`?

**Answer:** No. `-Pstage` belongs to the build; runtime only gets the production profile if another configuration source or bridge logic provides it. To be explicit:

```bash
java -jar app.jar --spring.profiles.active=prod
```

or supply `SPRING_PROFILES_ACTIVE=prod` in the deployment environment.

## 54. Checklist Before Running a Spring Boot App

- [ ] Is the command running `gradlew bootRun` or `java -jar`?
- [ ] Is the parameter meant for Gradle, the application JVM, or Spring Boot?
- [ ] For a Gradle project property, is there an explicit bridge to the app?
- [ ] For Gradle `-D`, are you confusing the Gradle JVM with the child JVM?
- [ ] For Java `-D`, is it placed before `-jar`?
- [ ] For `bootRun`, did you use `--args` when wanting application CLI args?
- [ ] For JVM heap/GC, did you configure the right application process?
- [ ] Is the current shell Bash, PowerShell, or cmd?
- [ ] Are strings with spaces/special characters properly quoted?
- [ ] Are environment variables actually passed to the real application process?
- [ ] Is configuration overridden by any higher-precedence source?
- [ ] Are active profiles correct?
- [ ] Are external files outside the JAR resolved from the right working directory?
- [ ] Are `System.getProperty`, `System.getenv`, and `Environment` being used interchangeably by mistake?
- [ ] Are tokens, passwords, or full arguments accidentally logged?
- [ ] Have you tested running the packaged JAR in a deployment-like environment?
- [ ] Have you verified actual outputs of `bootRun` and `java -jar` instead of inferring solely from the build script?

## 55. Summary

The key is **identifying the exact process and the exact parser of each parameter**:

```text
./gradlew -PdeployRegion=qa bootRun
      |
      v
Gradle project property (build logic)

./gradlew -Ddemo.region=qa bootRun
      |
      v
System property on the Gradle JVM

./gradlew bootRun --args='--demo.region=qa'
      |
      v
Application arguments to Spring Boot main

tasks.named("bootRun") {
    systemProperty("demo.region", "qa")
}
      |
      v
Application JVM Java system property

java -Ddemo.region=qa -jar app.jar
      |
      v
Application JVM Java system property

java -jar app.jar --demo.region=qa
      |
      v
Spring Boot command-line property
```

Remember these five rules:

1. **`-P` and `-D` on Gradle commands belong to the build layer**, and do not automatically become Spring Boot properties.
2. **`bootRun --args` passes application arguments**, while `bootRun.systemProperty`/`jvmArgs` control the child JVM launched by the task.
3. **`java -D... -jar` and `java -jar ... --...` are two different sources**, though both can be read by Spring Boot `Environment`.
4. **Spring Boot applies `PropertySource` precedence**, so `Environment#getProperty` can return a different value than `System.getProperty`.
5. **Build-time and runtime must be kept distinct**, especially when building a JAR in CI and running it in another container or server.

If an application "ignores a parameter," do not immediately rewrite the Binder or YAML file. First verify whether the parameter reached the right stage of **shell → Gradle → application JVM → Spring Boot**. Many configuration bugs become obvious as soon as this boundary is identified accurately.

## References

- Spring Boot 3.3 — Externalized Configuration and PropertySource Order: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Running Your Application with Gradle / `bootRun`: https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html
- Spring Boot 3.3 — Gradle Plugin Reference: https://docs.spring.io/spring-boot/3.3/gradle-plugin/index.html
- Gradle — Command-Line Interface (`-P`, `-D`, task options): https://docs.gradle.org/current/userguide/gradle_command_line.html
- Gradle — Build Environment Configuration (project/system properties): https://docs.gradle.org/current/userguide/build_environment.html
- Gradle JavaExec API — `args`, `systemProperty`, `jvmArgs`, `environment`: https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/JavaExec.html
- Spring Boot 3.3 — ApplicationArguments API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
