# Distinguishing Process Variables, IDE Options, and .env Files Not Automatically Loaded by Boot

## 1. The issue to understand

When learning **Spring Boot Externalized Configuration**, learners frequently encounter three actions that look similar:

1. Setting an environment variable in a terminal and running `java -jar app.jar`.
2. Entering an environment variable in an IDE's **Run/Debug Configuration**.
3. Creating a `.env` file in the project directory, for instance writing `DEMO_MESSAGE=hello`.

All three can appear in a development workflow, yet **they are not mechanically equivalent**.

- **Process environment variable** is a name–value pair actually supplied by the operating system or launcher to the Java process.
- **IDE option** is configuration the IDE uses **when spawning a run or debug process**. An "Environment variables" field causes the IDE to pass variables into the Java process; whereas "VM options" and "Program arguments" are different channels.
- **`.env` file** is merely a convention-based text file supported by various tools. **Spring Boot does not by default scan and automatically load `.env` files as process environment variables.**

The key point is: **Spring Boot reads the configuration sources actually supplied to the application; it does not infer environment variables merely because a file named `.env` exists.**

Consider a project:

```text
my-app/
├── .env
├── build.gradle
└── src/main/resources/application.yml
```

`.env` file:

```dotenv
DEMO_MESSAGE=Hello from .env
SPRING_PROFILES_ACTIVE=dev
```

If you simply create that file and run:

```bash
java -jar build/libs/my-app.jar
```

you **cannot conclude** Spring Boot will receive `DEMO_MESSAGE` and profile `dev` from that file. Another tool must read `.env` and pass values to the Java process, or the application must be configured to load data through a supported mechanism.

## 2. Which process does an environment variable actually belong to?

### 2.1. What is the process environment?

Each process has its own **execution environment**, containing the set of environment variables passed down by its parent process or launcher when creating the child process.

Illustrative diagram:

```text
Terminal / shell
    |
    | export DEMO_MESSAGE="Hello"
    |
    +--> java -jar app.jar
              |
              +--> JVM process receives DEMO_MESSAGE=Hello
                        |
                        +--> System.getenv("DEMO_MESSAGE")
                        |
                        +--> Spring Environment
                                 |
                                 +--> demo.message
```

In an ordinary Java program, you can read it directly:

```java
String value = System.getenv("DEMO_MESSAGE");
System.out.println(value);
```

If the Java process has this variable, `System.getenv("DEMO_MESSAGE")` returns the corresponding value. If not, the result is `null`.

Spring Boot normally exposes OS environment variables in `Environment` so properties can be accessed using Spring-style configuration keys, such as `demo.message`.

### 2.2. A shell variable is not necessarily exported to child processes

In Bash or POSIX-compatible shells, these two operations **differ**:

```bash
# Creates only a variable in the current shell
DEMO_MESSAGE="Hello"

# Prints the shell variable
echo "$DEMO_MESSAGE"
```

The `echo` command prints `Hello`, yet that **does not prove** the variable is passed to a Java program launched afterward. To export the variable to child processes, use `export`:

```bash
export DEMO_MESSAGE="Hello"
java -jar app.jar
```

Or set the variable for one command only:

```bash
DEMO_MESSAGE="Hello" java -jar app.jar
```

The second approach is convenient when testing without leaving the variable in the shell environment for subsequent commands.

You can check exported variables in the current terminal:

```bash
printenv DEMO_MESSAGE
```

If you only typed `DEMO_MESSAGE=Hello` without `export`, `printenv` may not show the value even though `echo "$DEMO_MESSAGE"` does.

### 2.3. Terminals do not automatically share changes

Suppose you open two terminals, A and B:

- In A: `export DEMO_MESSAGE=A`.
- In B: run `java -jar app.jar`.

You cannot assume the application launched from B receives `A`. Each shell is a process with its own environment; changes in one running shell do not propagate retroactively to another already-existing shell.

Similarly, changing a variable in a terminal **after the JVM has started** does not change the environment of the running JVM. With standard Spring Boot configuration, you must restart the application after changing input variables.

This is the root cause of "I exported it, yet the app still doesn't see it": verify **which terminal or tool actually spawns the Java process**.

## 3. How does Spring Boot map environment variables to properties?

A common point of confusion is that environment variable names and Spring property names can be written differently.

Examples:

| Environment variable supplied to JVM | Spring Boot property typically received |
| --- | --- |
| `SERVER_PORT` | `server.port` |
| `SPRING_PROFILES_ACTIVE` | `spring.profiles.active` |
| `SPRING_DATASOURCE_URL` | `spring.datasource.url` |
| `DEMO_MESSAGE` | `demo.message` |
| `MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE` | `management.endpoints.web.exposure.include` |

Spring Boot supports **relaxed binding** for many key representations. For canonical configuration properties, the standard rule to convert to environment variables is usually:

1. Replace dots `.` with underscores `_`.
2. Remove hyphens `-` inside property names.
3. Convert letters to uppercase.

For example, `spring.main.log-startup-info` corresponds to environment variable form `SPRING_MAIN_LOGSTARTUPINFO` per that standard naming rule. Therefore, do not insert underscores arbitrarily between every word assuming Spring Boot's binder will resolve every property correctly.

In this lesson, we use the simple property `demo.message`, whose mapping is easily observed as `DEMO_MESSAGE`.

**Note:** environment variable names can be case-sensitive depending on the operating system, while property name mapping depends on Spring `Environment` and the binder. Using standard names from Spring Boot documentation avoids surprises when moving between Windows and Linux.

## 4. A runnable Spring Boot example

Suppose we want to display a greeting configured outside the application.

### 4.1. File application.yml

Create `src/main/resources/application.yml`:

```yaml
demo:
  message: "Default greeting in YAML"
  retries: 2
```

Here `demo.message` and `demo.retries` are two illustrative properties.

### 4.2. Java component to inspect value sources

In an application that already has `@SpringBootApplication`, add:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class EnvironmentPrinter implements ApplicationRunner {

    private final Environment environment;

    public EnvironmentPrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String rawEnvironmentValue = System.getenv("DEMO_MESSAGE");
        String springValue = environment.getProperty("demo.message");

        System.out.println("OS DEMO_MESSAGE = " + rawEnvironmentValue);
        System.out.println("Spring demo.message = " + springValue);
        System.out.println("Spring demo.retries = "
                + environment.getProperty("demo.retries", Integer.class));
    }
}
```

Observation points:

- `System.getenv("DEMO_MESSAGE")` answers: **did this JVM receive an environment variable named exactly `DEMO_MESSAGE`?**
- `environment.getProperty("demo.message")` answers: **which value did Spring choose for `demo.message` after considering configuration sources?**
- The two results can differ if a higher-priority Spring source overrode it, or if the environment variable does not exist yet YAML supplies a value.

### 4.3. Case A: no environment variable supplied

Run:

```bash
java -jar app.jar
```

Assuming no `DEMO_MESSAGE` in the JVM environment and no other overriding source:

```text
OS DEMO_MESSAGE = null
Spring demo.message = Default greeting in YAML
Spring demo.retries = 2
```

Spring still reads the value from the configuration file, even with no environment variable present.

### 4.4. Case B: variable supplied via shell

Bash:

```bash
DEMO_MESSAGE="Greeting from terminal" java -jar app.jar
```

Expected output:

```text
OS DEMO_MESSAGE = Greeting from terminal
Spring demo.message = Greeting from terminal
Spring demo.retries = 2
```

The environment value overrides the same key in `application.yml` when no higher-priority source exists.

### 4.5. Case C: command-line argument added

```bash
DEMO_MESSAGE="From environment" java -jar app.jar --demo.message="From command line"
```

The two reads can produce:

```text
OS DEMO_MESSAGE = From environment
Spring demo.message = From command line
Spring demo.retries = 2
```

There is no contradiction: `System.getenv` only reads environment variables, whereas Spring `Environment` checks multiple sources. In typical Spring Boot configurations, `--demo.message=...` has higher priority than environment variables.

From here, you can distinguish **whether the variable reached the JVM** from **which value is effective in the Spring application**.

## 5. IDE Run/Debug options are not a .env file

When clicking **Run** or **Debug** in an IDE like IntelliJ IDEA, Eclipse, or VS Code, the IDE or Java runner is usually the tool spawning the application process. What Java receives depends on **that run configuration**.

There are usually three important option groups.

| Run configuration item | Example input | How Java/Spring receives it |
| --- | --- | --- |
| Environment variables | `DEMO_MESSAGE=from-ide` | Process environment, `System.getenv("DEMO_MESSAGE")` |
| VM options / JVM arguments | `-Ddemo.message=from-jvm` | Java system property, `System.getProperty("demo.message")` |
| Program arguments / Application arguments | `--demo.message=from-cli` | Application arguments, Spring Boot command-line properties |

Exact field labels vary by IDE and Run/Debug configuration type. However, **the nature of the three channels is distinct**.

### 5.1. Environment variables in an IDE

If you add the variable:

```text
DEMO_MESSAGE=Hello from IDE
```

into the **Environment variables** section of the application run configuration, the IDE passes that variable into the newly spawned Java process. Then:

```java
System.getenv("DEMO_MESSAGE")
```

can return `Hello from IDE`, and Spring can bind it to `demo.message`.

That is still a **real Java process environment variable**. The difference is that **the IDE supplies the value instead of a terminal**.

### 5.2. VM options in an IDE

If you enter:

```text
-Ddemo.message=HelloFromJvm
```

into **VM options**, that is a **Java system property**, not an environment variable named `DEMO_MESSAGE`.

Therefore:

```java
System.getProperty("demo.message")
```

can have value `HelloFromJvm`, whereas:

```java
System.getenv("DEMO_MESSAGE")
```

will not magically have a value just because this `-D` option was set.

Spring Boot usually reads `demo.message` from the Java system property, since Java system properties are also a supported configuration source.

### 5.3. Program arguments in an IDE

If you enter:

```text
--demo.message=HelloFromArguments
```

into **Program arguments**, the IDE passes that string into the application argument list. Spring Boot supports property argument syntax starting with `--` by default.

This is also **not** a JVM environment variable. `System.getenv("DEMO_MESSAGE")` will not reflect this value, while Spring `Environment` can read `demo.message=HelloFromArguments`.

### 5.4. The IDE runner has its own environment

A subtle mistake:

1. Open the IDE from the desktop launcher.
2. Later open a separate terminal and run `export DEMO_MESSAGE=updated`.
3. Click **Run** in the IDE.
4. Notice the application does not receive `updated`.

Reason: running `export` in a terminal **does not modify the environment of the already-running IDE process**. To ensure values apply, enter them in the Run/Debug Configuration, or launch the IDE from an environment already configured properly.

Some IDEs provide features to load environment files, `.env` support plugins, or an `envFile` setting. Those are **features of the IDE/extension/runner**, not proof that Spring Boot has a built-in `.env` auto-scanner.

## 6. What is a .env file really?

A `.env` file is typically a plain text file containing name–value lines:

```dotenv
DEMO_MESSAGE=Hello from dotenv
DEMO_RETRIES=5
SPRING_PROFILES_ACTIVE=dev
```

It can be used by Docker, Docker Compose, task runners, other frameworks, or dotenv libraries. Essentially, however, merely creating the file on disk **does not turn its lines into environment variables for any process**.

Distinguish three steps:

```text
1. A .env file exists on disk
           |
           | no effect guaranteed yet
           v
2. A tool reads .env and puts data into the process environment
           |
           | JVM is spawned with the passed variables
           v
3. Spring Boot reads environment variables from JVM/Environment
```

If **step 2 does not occur**, Spring Boot cannot deduce values merely from the file's existence.

Example directory:

```text
my-app/
├── .env
├── pom.xml
└── src/main/resources/
    └── application.yml
```

`.env` file:

```dotenv
DEMO_MESSAGE=From dotenv
```

`application.yml` file:

```yaml
demo:
  message: "From YAML"
```

If you run the Java application directly with no tool reading `.env` and no `DEMO_MESSAGE` variable in the JVM environment, Spring will use `From YAML` in this example.

Placing `.env` in the project root, in `src/main/resources`, or beside the JAR **does not automatically make it a configuration file loaded by Spring Boot by default**.

## 7. How to use data from .env so Spring Boot actually sees it

To use values in `.env`, choose an explicit mechanism. There are several ways, each with a different scope.

### 7.1. Simplest approach: pass variables directly at launch

Bash:

```bash
DEMO_MESSAGE="From process environment" java -jar app.jar
```

Or:

```bash
export DEMO_MESSAGE="From process environment"
java -jar app.jar
```

Here no `.env` file is needed. Spring Boot reads the variables the JVM process receives.

### 7.2. Use a runner that supports env files

Some IDEs or task runners allow specifying a path to `.env`. That tool is responsible for:

1. Reading the file.
2. Parsing its contents according to the tool's syntax.
3. Setting the appropriate variables when spawning the Java process.

Spring Boot then receives variables through the standard mechanism. If you switch to running `java -jar` directly without going through that tool, the values may vanish because the file-loading step no longer runs.

Therefore, in project instructions, specify **which tool is responsible for reading `.env`** and which setting enables that feature.

### 7.3. Use Docker with --env-file

Example `.env` file:

```dotenv
DEMO_MESSAGE=Hello from Docker
SPRING_PROFILES_ACTIVE=prod
```

Run a container running the Java application:

```bash
docker run --rm --env-file .env my-spring-app:local
```

The `--env-file` option is a **Docker CLI** feature: Docker reads the file and injects the corresponding variables into the container environment. Spring Boot only sees what was supplied to the JVM process **inside the container**.

The command above assumes the image `my-spring-app:local` exists and is configured to run the application.

**Syntax warning:** an env file for Docker CLI does not necessarily accept all quoting or interpolation rules of Bash, Docker Compose, or dotenv libraries. Author it in the exact format required by the tool reading the file.

### 7.4. Use a genuine Spring Boot configuration file

If the goal is **loading an application configuration file**, a direct option is using `application-local.properties` or `application-local.yml` via Config Data:

```properties
# config/application-local.properties
demo.message=Hello from local properties
demo.retries=4
```

For instance, after placing the file in an appropriate config location and activating the `local` profile:

```bash
java -jar app.jar --spring.profiles.active=local
```

This is **profile-based Spring Boot configuration**, distinct from creating `.env`. It follows Config Data's own file selection, location, and precedence rules.

Another approach is pointing to Properties/YAML resources via `spring.config.import` or `spring.config.additional-location` where suitable. However, do not implicitly equate dotenv syntax with YAML or Properties in every scenario: tools may have different parsing rules.

## 8. Be careful when sourcing a .env file in Bash

You may encounter this trick:

```bash
set -a
. ./.env
set +a
java -jar app.jar
```

Mechanism:

- `. ./.env` tells the shell to read and execute the file contents as **shell code**.
- `set -a` marks variables assigned during that block to be automatically exported to child processes.
- `set +a` restores normal shell variable assignment behavior.

This is **only suitable when the file uses valid shell syntax and is trusted**. Dotenv files formatted for other tools may contain quoting, whitespace, interpolation, or comment conventions not fully compatible with Bash.

In particular, `source` or `.` **executes the file contents**, so never use it on untrusted files just to load a few variables. In production systems, prefer direct environment configuration, an env-file reader with well-defined syntax, or an appropriate secret management service.

Do not write quick scripts that load `.env` by splitting lines at the first `=` without accounting for special characters, quotes, whitespace, or multiline values; that approach routinely breaks on non-trivial configurations.

## 9. Distinguishing Docker Compose's .env file from container variables

Docker Compose commonly uses a `.env` file for **variable interpolation inside the Compose file**. However, Compose reading `.env` on the tooling side **does not mean every variable in it automatically appears inside the application process in the container**.

Example:

```dotenv
# .env
DEMO_MESSAGE=Value from dotenv
```

And:

```yaml
# compose.yaml
services:
  app:
    image: my-spring-app:local
```

In this configuration, nothing instructs Compose to pass `DEMO_MESSAGE` to the container. Having a `.env` file next to `compose.yaml` is **not enough** to conclude the application receives that variable.

To pass it into the container, you can use `env_file`:

```yaml
services:
  app:
    image: my-spring-app:local
    env_file:
      - .env
```

Or use `environment` with interpolation:

```yaml
services:
  app:
    image: my-spring-app:local
    environment:
      DEMO_MESSAGE: ${DEMO_MESSAGE}
```

In both examples, Docker Compose is responsible for supplying variables to the container through the respective mechanism. Spring Boot reads the Java process's variables and maps `DEMO_MESSAGE` to `demo.message`.

Key distinction:

| Component | Role |
| --- | --- |
| `.env` file for Compose | Supplies input data to Compose, commonly used for interpolation |
| `env_file:` in `compose.yaml` | Tells Compose to read a file and populate the container environment |
| `environment:` in `compose.yaml` | Sets specific variables for the container |
| `Environment` in Spring Boot | Reads actual property sources of the Java application inside the container |

If you run the same JAR from an IDE or terminal outside Docker, Compose's `env_file` configuration has no effect on that run.

## 10. Precedence rules: having a variable does not mean it is the final value

Spring Boot has multiple configuration property sources. In common scenarios, the relative precedence among several sources is:

```text
Application argument --demo.message=...
       >
SPRING_APPLICATION_JSON (if supplying the matching property)
       >
Java system property -Ddemo.message=...
       >
Environment variable DEMO_MESSAGE
       >
Config Data: application.yml / application.properties
```

This is a simplified diagram and does not list specialized sources such as test configuration, servlet/JNDI, DevTools, or application-added sources.

Example:

```bash
DEMO_MESSAGE="env" java -Ddemo.message=jvm -jar app.jar --demo.message=cli
```

In a standard example:

```text
System.getenv("DEMO_MESSAGE")      = env
System.getProperty("demo.message") = jvm
Spring Environment demo.message    = cli
```

There is no bug here. Three different value-passing mechanisms coexist; Spring chooses the highest-priority value for `demo.message`.

Therefore, when someone says "my environment variable isn't working", split it into two questions:

1. **Did the variable actually reach the JVM?** Check `System.getenv("DEMO_MESSAGE")`.
2. **If it reached the JVM, which source is winning in Spring?** Check `Environment#getProperty("demo.message")` and relevant `PropertySource` entries.

The first question cannot be explained by precedence order alone. The second question cannot be explained by simply looking inside a `.env` file.

## 11. Distinguishing terminal, IDE, Maven, and Gradle

A Spring Boot project can be launched via multiple commands, and each launch has a different parent process.

| Launch method | Who spawns the Java process? | Where to inspect? |
| --- | --- | --- |
| `java -jar app.jar` in terminal | Shell/terminal | Exported shell environment |
| Run/Debug from IDE | IDE or IDE runner | Environment variables in Run Configuration |
| `mvn spring-boot:run` | Maven and Spring Boot Maven Plugin | Maven process environment and plugin configuration |
| `./gradlew bootRun` | Gradle and `bootRun` task | Environment where Gradle runs and task customizations |
| Docker container | Docker or Compose | `--env`, `--env-file`, `environment`, `env_file` |
| CI/CD | Runner, job, or orchestrator | Variable/secret settings at the process-launch step |

Maven/Gradle can launch or manage the Java process with their own settings. In projects with daemons, run profiles, or custom tasks, do not assert that every variable in a terminal reaches the application process without verifying the launch flow.

A practical check is temporarily printing **one non-sensitive variable** with `System.getenv` inside the application to confirm it reached the JVM. This is often more reliable than running `printenv` in a terminal that may not be the one spawning the Java process.

In an IDE, also verify you selected **the right Run Configuration**. One project can have multiple run configurations—such as `Application`, `Spring Boot`, a JUnit configuration, and a Gradle task—each with its own environment variables.

## 12. Scenario with IntelliJ IDEA

Suppose the application reads `demo.message` and you want to assign:

```text
DEMO_MESSAGE=Hello from IntelliJ
```

General workflow:

1. Open **Run → Edit Configurations**.
2. Select the Spring Boot application configuration actually used to run.
3. Locate **Environment variables** and declare `DEMO_MESSAGE`.
4. Save the configuration and rerun the application.
5. Check `System.getenv("DEMO_MESSAGE")` and `environment.getProperty("demo.message")`.

If you only put:

```text
-Ddemo.message=HelloFromJvm
```

in **VM options**, the value arrives via Java system property, not the `DEMO_MESSAGE` environment variable.

If you only put:

```text
--demo.message=HelloFromArgs
```

in **Program arguments**, Spring receives an application argument, not an environment variable.

If the project uses a plugin or feature supporting `.env` files, check that the plugin is enabled for **the exact run configuration**. Do not assume every IDE installation includes the same feature or automatically reads every `.env` file in the project directory.

## 13. Scenario with VS Code and tools supporting envFile

Some VS Code launch configurations or extensions allow declaring an `envFile` path. For instance, a Java launch configuration supported by an extension might use:

```json
{
  "type": "java",
  "name": "Run Spring Boot",
  "request": "launch",
  "mainClass": "com.example.demo.DemoApplication",
  "envFile": "${workspaceFolder}/.env"
}
```

This is only **an example of one launch configuration style supporting `envFile`**, not an immutable Java configuration across every extension and version.

The key responsibility sits with **the runner**:

- The runner reads the `.env` file.
- The runner injects variables into the Java process.
- Spring Boot reads the received environment variables.

If you switch to launching the JAR directly with `java -jar` outside that runner, Boot does not automatically use VS Code's `envFile` setting.

Hence, when guiding a development team, state the exact IDE, extension, and run configuration style rather than saying loosely "Spring Boot has `envFile`".

## 14. An environment-configured example without .env

To make the distinction clear, you can configure a web application through real environment variables.

`application.yml` file:

```yaml
server:
  port: 8080

demo:
  message: "Default message"
```

Run with Bash environment variables:

```bash
SERVER_PORT=9090 DEMO_MESSAGE="Hello local" java -jar app.jar
```

Assuming no higher-priority source overrides them:

```text
server.port  = 9090
demo.message = Hello local
```

No `.env` file is involved. The process environment supplied both values in place of YAML defaults.

Similarly with PowerShell:

```powershell
$env:SERVER_PORT = "9090"
$env:DEMO_MESSAGE = "Hello local"

java -jar app.jar

Remove-Item Env:SERVER_PORT
Remove-Item Env:DEMO_MESSAGE
```

Removing the variables at the end avoids side effects on subsequent commands in the same PowerShell session.

Do not use `setx` on Windows to quickly test a variable for **the current process**: `setx` writes values for future sessions rather than updating the currently running shell's environment the way `$env:...` does in PowerShell.

## 15. Configuration secrets and safety when using env

Many teams choose environment variables to pass usernames, passwords, or tokens to applications. For example, Spring Boot can accept:

```text
SPRING_DATASOURCE_URL
SPRING_DATASOURCE_USERNAME
SPRING_DATASOURCE_PASSWORD
```

However, remember:

- **Environment variables are not automatically a secure secret vault.** They can be exposed through logs, dumps, process management UIs, diagnostic info, or tools permitted to inspect the environment.
- **Never commit `.env` containing real secrets to Git.** Use a `.env.example` file containing only key names and non-sensitive sample values if the team needs setup documentation.
- **Do not print passwords or tokens for diagnostics.** Test with a dummy key like `DEMO_MESSAGE`, or check only whether a secret is present without printing its value.
- In CI/CD or production infrastructure, prefer appropriate secret management mechanisms and inject values into the process at launch time.
- Variables set in a local IDE or terminal are not automatically deployed to servers or containers.

Distinguish **not storing secrets in committed configuration files** from **secrets being fully protected**. Access control, secret lifecycle, preventing log leaks, and delivery to the application remain essential.

## 16. Diagnosing when .env is set yet the application ignores it

If a team reports: "I added `DEMO_MESSAGE` to `.env`, yet Spring Boot still picks the default value", investigate in order.

### Step 1: identify the actual launch command

Was the application started via:

- terminal `java -jar`;
- IDE Run/Debug button;
- Maven/Gradle;
- Docker/Docker Compose;
- another runner or deployment environment?

Do not assume the user is launching through a `.env`-aware tool merely because the file exists.

### Step 2: identify which tool read .env

Ask for technical evidence: Does the Run Configuration set `envFile`? Does Docker pass `--env-file`? Does Compose use `env_file` or `environment`? Does a startup script export the variables?

If the answer is no, `.env` has very likely **never been converted into JVM environment variables**.

### Step 3: inspect directly inside the Java process

Temporarily add code for a non-sensitive key:

```java
System.out.println("DEMO_MESSAGE present? "
        + (System.getenv("DEMO_MESSAGE") != null));
```

If it prints `false`, the JVM does not have an environment variable named exactly `DEMO_MESSAGE`. Fix the variable delivery channel instead of trying to alter Spring Config Data precedence.

### Step 4: check the Spring property

```java
System.out.println("demo.message = "
        + environment.getProperty("demo.message"));
```

If `System.getenv` has the variable yet `Environment` returns a different value, a higher-priority source—such as command-line arguments—may exist.

### Step 5: check run config and restart

Verify you edited the right Run Configuration, right container, right process, and right variable name. Ensure the application was **restarted** after changing inputs.

### Step 6: verify name and value formatting

For key `demo.message`, use standard name `DEMO_MESSAGE`. Check whitespace, double quotes, equals signs, newlines, and whether your dotenv reader applies unexpected parsing rules.

### Step 7: do not confuse "profile inactive" with "variable ignored"

If `.env` contains `SPRING_PROFILES_ACTIVE=prod` yet the `prod` profile does not activate, verify this variable exists in the JVM environment. If absent, `application-prod.yml` files or `on-profile: prod` documents will not activate just from `.env` existing.

## 17. Comparison table of the three approaches

| Question | Process environment variable | Environment variables in IDE | Standalone `.env` file |
| --- | --- | --- | --- |
| Seen immediately by JVM at launch? | Yes, if properly passed to the process | Yes, if Run/Debug config passes it to JVM | **Not automatically** |
| Readable by `System.getenv`? | Yes | Yes, if IDE actually supplies the variable | No, unless loaded by a tool |
| Usable by Spring `Environment`? | Yes, with matching key mapping | Yes, when JVM receives the variable | Only once data is loaded via an actual mechanism |
| Depends on the launcher tool? | Yes: terminal/runner must pass variable | Yes: depends on IDE configuration | Yes: needs a loader, script, Docker, or explicit config |
| Can override `application.yml`? | Yes, per source precedence order | Yes, if passed as an environment variable | Not merely by existing on disk |
| Needs restart for new values? | Typically yes | Typically yes | Once loader and environment update, typically needs rerun |

This table focuses on **mechanisms**. A single run can combine multiple channels, such as an IDE passing environment variables while also passing `--demo.message=...` arguments. In that case, evaluate both variable existence and Spring source precedence.

## 18. Practice exercises

### Exercise A: only .env present

Structure:

```text
demo/
├── .env
└── src/main/resources/application.yml
```

`.env` file:

```dotenv
DEMO_MESSAGE=from-dotenv
```

`application.yml` file:

```yaml
demo:
  message: "from-yaml"
```

Run `java -jar app.jar` with no loader and no `DEMO_MESSAGE` variable in the environment.

**Question:** what is the value of `demo.message`?

**Answer:** `from-yaml`. The existence of `.env` does not cause Spring Boot to load it by default.

### Exercise B: shell variable vs. exported variable

In Bash:

```bash
DEMO_MESSAGE=first
java -jar app.jar
```

Then:

```bash
export DEMO_MESSAGE=second
java -jar app.jar
```

**Question:** why might the first run not pass `DEMO_MESSAGE` to the application, while the second does?

**Answer:** assigning a variable in the shell does not export it to child processes. `export` marks the variable to be forwarded to programs spawned from that shell.

### Exercise C: IDE with multiple parameter types

In Run Configuration:

```text
Environment variables:
  DEMO_MESSAGE=env

VM options:
  -Ddemo.message=jvm

Program arguments:
  --demo.message=cli
```

Assuming no special source alters precedence, predict:

| Lookup | Result |
| --- | --- |
| `System.getenv("DEMO_MESSAGE")` | `env` |
| `System.getProperty("demo.message")` | `jvm` |
| `environment.getProperty("demo.message")` | `cli` |

**Explanation:** different delivery channels; Spring chooses the application argument for the final value due to higher precedence.

### Exercise D: Docker Compose has .env but lacks variable forwarding

Given:

```dotenv
# .env
DEMO_MESSAGE=compose-value
```

And:

```yaml
services:
  app:
    image: my-spring-app:local
```

**Question:** can we be sure the JVM inside the container receives `DEMO_MESSAGE=compose-value`?

**Answer:** No. To pass values into the container environment, configure an appropriate setting such as `env_file:` or `environment:`, or another variable-delivery mechanism. A `.env` file used for Compose interpolation does not automatically inject every variable into containers.

### Exercise E: spotting the mistake in a sequence of actions

A developer:

1. Opens the IDE in the morning.
2. In the afternoon, opens a new terminal and runs `export SPRING_PROFILES_ACTIVE=prod`.
3. Clicks Run in the existing IDE window.
4. Sees the application still running under a different profile.

**Question:** what should be checked first?

**Answer:** the actual environment of the Java process spawned by the IDE. A variable exported in a separate terminal does not automatically update the environment of an already-open IDE. Put the variable in the right Run Configuration, or ensure the IDE is launched with the desired environment.

## 19. Key takeaways

- **Process environment** is real data passed to the JVM process; `System.getenv` shows whether the JVM received a specific variable.
- **IDE Environment variables** become JVM environment variables when the IDE launches the application. They differ from **VM options** (Java system properties) and **Program arguments** (application arguments).
- **`.env` files are not automatically loaded by Spring Boot by default.** An explicit tool or mechanism must read the file and pass appropriate values, or the application must be configured to load resources through a supported mechanism.
- **Terminals, IDEs, Docker, and CI/CD do not automatically share environments across all processes.** Pinpoint who spawns the Java process and which variables were supplied.
- **A value in `System.getenv` is not guaranteed to be Spring's effective value**: `Environment` also considers command-line arguments, system properties, and Config Data sources.
- Use `spring.profiles.active`, `spring.config.import`, and profile-specific configuration for their intended purpose; do not assume putting them in `.env` suffices if no loader reads `.env`.
- For secrets, avoid committing `.env` files containing real data, avoid printing sensitive values, and use an appropriate secret-provisioning tool for deployment environments.
