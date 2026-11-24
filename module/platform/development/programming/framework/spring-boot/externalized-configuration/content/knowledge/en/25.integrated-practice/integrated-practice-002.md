# Experimenting with One Key Across Files, Environment Variables, JVM, and Command Line in Spring Boot

## 1. Scenario and Questions to Answer

In a Spring Boot project, a property can be declared in multiple places at the same time:

```properties
# application.properties
lab.message=from-file
```

```bash
# Operating system environment variable
LAB_MESSAGE=from-env
```

```bash
# Java system property
-Dlab.message=from-jvm
```

```bash
# Spring Boot command-line argument
--lab.message=from-cli
```

If all of them exist simultaneously, **which value does the application use?** Why can a value in a file be overridden without modifying source code? And how can you tell whether `-D` was actually passed to the JVM running the application rather than only to Gradle executing the build command?

This practice uses **a single key**:

```text
lab.message
```

and four source groups: **configuration files, OS environment variables, Java system properties, and application command-line arguments**.

The goal is not to memorize a fixed answer and guess by intuition. You will launch the **same JAR** with various combinations of sources, record which value wins in each run, and compare against Spring Boot 3.3's `PropertySource` precedence rules.

This lab belongs to the **Integrated Practice** group of the **Spring Boot Externalized Configuration** topic.

### What You Will Learn

1. Distinguish **Java source code**, **files packaged inside the JAR**, and **configuration files outside the JAR**.
2. Understand how `Environment` aggregates multiple `PropertySource` instances and how a duplicate key is resolved.
3. Override configuration files using the `LAB_MESSAGE` environment variable.
4. Override environment variables using `java -Dlab.message=...`.
5. Override a JVM system property using `--lab.message=...` placed **after** the JAR filename.
6. Use `Environment`, `@ConfigurationProperties`, and `@Value` to read the same effective value.
7. Distinguish `System.getenv()`, `System.getProperty()`, and Spring's property resolution mechanism.
8. Understand why `./config/application.properties` can be auto-discovered by Boot.
9. Run the experiment with Java 21 / Gradle / Spring Boot 3.3 without depending on any external server.
10. Identify unexpected sources when running via an IDE, `bootRun`, Docker, or Kubernetes.
11. Recognize the boundaries of the experiment: precedence has exceptions when adding JSON, test property sources, DevTools, or other integrations.
12. Build a repeatable verification matrix useful for CI and incident troubleshooting.

**Illustrative versions:** Java 21, Spring Boot 3.3.13, Gradle. Values `from-file`, `from-env`, `from-jvm`, and `from-cli` are purely training labels; never use real passwords, tokens, or secrets.

---

## 2. Expected Results to Prove Before Running

In a standard Spring Boot 3.3 setup, considering only the four assigned source layers, the precedence order **from highest to lowest** is:

```text
         HIGHEST PRIORITY
                 |
                 v
     --lab.message=from-cli
                 |
                 v
     -Dlab.message=from-jvm
                 |
                 v
     LAB_MESSAGE=from-env
                 |
                 v
     Config Data: application.properties / application.yaml
                 |
                 v
          LOWER PRIORITY
```

Within Config Data, an external configuration file **outside the JAR** at a default location can override a baseline file **packaged inside the JAR**.

Therefore, the predicted matrix is:

| Sources providing `lab.message` | Effective value |
| --- | --- |
| Packaged file in JAR only | `from-classpath` |
| Plus `./config/application.properties` | `from-file` |
| External file + environment variable | `from-env` |
| External file + environment variable + JVM `-D` | `from-jvm` |
| All four: file, env, JVM `-D`, and CLI `--` | `from-cli` |
| Remove CLI, keep JVM `-D` | `from-jvm` |
| Also remove JVM `-D`, keep env | `from-env` |
| Also remove env, keep external file | `from-file` |
| Delete/rename external file, keep packaged file | `from-classpath` |

**Note:** this table covers only the lab's sources. In a real application, other sources may exist, such as `SPRING_APPLICATION_JSON`, Servlet/JNDI, test properties, profile-specific Config Data, `@PropertySource`, default properties, and remote providers. Do not extrapolate "CLI always wins over everything in every circumstance" to tests or systems that customize `PropertySources` without verifying the context.

### 2.1. A Source Without the Key Does Not Compete

If `LAB_MESSAGE` is not set, the OS environment source does not provide a value for `lab.message`, so Spring continues searching lower-priority sources.

Similarly:

- No `-Dlab.message=...` means Java system properties do not supply this key.
- No `--lab.message=...` means the command-line `PropertySource` does not supply this key.
- When the external file is absent, Boot can fall back to the file packaged in the JAR.

Precedence decides **among sources that define the same key**; it does not mean every source must be declared for the app to run.

### 2.2. The Final Value Is Not String Concatenation

If the four sources are:

```text
from-classpath
from-file
from-env
from-jvm
from-cli
```

the result is not:

```text
from-classpath-from-file-from-env-from-jvm-from-cli
```

For a **scalar String**, Spring picks one effective value for the property. Merge/replacement rules for `List` or complex object binding are separate topics and are not needed to explain this scalar key.

---

## 3. Spring Boot Components Participating in the Experiment

Overview diagram:

```text
         Java process
              |
              v
      SpringApplication.run(...)
              |
              v
          Environment
              |
      +-------+--------+----------------+----------------+
      |                |                |                |
  commandLineArgs   systemProperties  systemEnvironment  Config Data
      |                |                |                |
      |            -Dlab.message    LAB_MESSAGE       application.*
      |                                                 |
      +--------------------+----------------------------+
                           |
                           v
              Resolve "lab.message"
                           |
           +---------------+----------------+
           |               |                |
           v               v                v
  Environment.getProperty  @Value      @ConfigurationProperties
           |               |                |
           +---------------+----------------+
                           |
                           v
                  Console output
```

Each piece has a specific role:

- **Property sources** supply configuration data and have a precedence order.
- **Environment** provides the lookup API for configuration data.
- **`@Value`** resolves placeholders when the bean is created.
- **`@ConfigurationProperties`** binds a typed configuration group, supporting relaxed binding and conversion.
- **ApplicationRunner** prints the results after the context is created; it does not decide precedence itself.

### 3.1. `System.getenv()` Differs from `Environment.getProperty()`

```java
System.getenv("LAB_MESSAGE")
```

queries only **OS environment variables**. It knows nothing about `-Dlab.message` or `--lab.message`.

Meanwhile:

```java
environment.getProperty("lab.message")
```

queries **Spring's `Environment`**, which aggregates multiple sources.

If you set:

```text
LAB_MESSAGE=from-env
-Dlab.message=from-jvm
--lab.message=from-cli
```

then:

```text
System.getenv("LAB_MESSAGE")               -> from-env
System.getProperty("lab.message")          -> from-jvm
Environment.getProperty("lab.message")     -> from-cli
```

There is no contradiction. The three calls answer three different questions.

### 3.2. `System.getProperty()` Is Not `Environment` Either

```java
System.getProperty("lab.message")
```

reads the **Java system properties** of the running JVM. It does not look up YAML files or environment variables automatically.

A JVM system property is typically passed with `-D`:

```bash
java -Dlab.message=from-jvm -jar app.jar
```

A different command:

```bash
java -jar app.jar --lab.message=from-cli
```

passes the option to **application arguments**, and Spring Boot can add them as a high-priority `PropertySource`.

**Argument placement matters.**

---

## 4. Initializing a Gradle Project to Observe One Key

Minimal project structure:

```text
config-source-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── config/                            # created during the experiment
│   └── application.properties        # external file outside JAR
└── src/
    ├── main/
    │   ├── java/dev/example/configlab/
    │   │   ├── ConfigSourceLabApplication.java
    │   │   └── LabProperties.java
    │   └── resources/
    │       └── application.yaml
    └── test/
        └── java/dev/example/configlab/
            └── LabPropertiesTest.java
```

Create the project using Spring Initializr with Java 21, Gradle, Spring Boot 3.3.x, and the basic starter. Keep the Gradle Wrapper (`gradlew` and `gradlew.bat`) generated with the project.

This is a **console application** that opens no HTTP port. Each run prints one report and exits. No database, Docker, Kubernetes, Vault, or Spring Cloud Config Server is needed for this experiment.

### 4.1. `settings.gradle`

```groovy
rootProject.name = 'config-source-lab'
```

### 4.2. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter` provides the core application dependencies and supports reading YAML through Boot's standard mechanism. No custom type-conversion library is needed for `String`.

The project pins a fixed version for reproducibility. When upgrading Spring Boot in a real project, check the corresponding Java/Gradle requirements and release notes.

### 4.3. `application.yaml` Packaged in the JAR

Create file:

`src/main/resources/application.yaml`

```yaml
spring:
  application:
    name: config-source-lab
  main:
    web-application-type: none
    banner-mode: "off"

lab:
  message: "from-classpath"
```

This value acts as a **fallback**. It is packaged inside the artifact when running `bootJar`.

**Distinguish two meanings of "file":**

1. `src/main/resources/application.yaml`: a resource packaged inside the JAR.
2. `./config/application.properties`: an external file outside the artifact, located in the **working directory** when the process starts.

With only file (1), the initial result is:

```text
from-classpath
```

When file (2) is added, you will observe that Spring Boot selects:

```text
from-file
```

even though the Java code and JAR have not changed.

---

## 5. `@ConfigurationProperties`: Bean Receiving the Selected Value

Create `src/main/java/dev/example/configlab/LabProperties.java`:

```java
package dev.example.configlab;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "lab")
public record LabProperties(String message) {}
```

The Spring Boot Binder looks up keys under prefix `lab`, then binds the `message` component from property `lab.message`.

Because this is a single-constructor Java record, Spring Boot 3.3 uses constructor binding by convention without requiring class-level `@ConstructorBinding`.

Do not annotate the record with `@Component`; it will be registered via `@ConfigurationPropertiesScan` on the main class.

### 5.1. Why Use a Simple Record?

Because the lab isolates **source precedence**, not complex converter syntax.

With:

```java
public record LabProperties(String message) {}
```

there are no extra variables like:

- `Duration` or `DataSize` conversion.
- Nested records.
- List/Map merge rules.
- Custom validation.
- Profile-specific binding logic.

The result can be compared directly against the raw text value from each source.

### 5.2. Could `@Value` Be Used Instead?

Yes, but here we use **all three observation mechanisms** (`Environment`, `@Value`, and `@ConfigurationProperties`) to prove they all receive the effective value from the same property source hierarchy at startup.

If a result is unexpected, separate property resolution errors from bean registration or binding errors.

---

## 6. Main Class Printing Both Effective Values and Per-Channel Data

Create `src/main/java/dev/example/configlab/ConfigSourceLabApplication.java`:

```java
package dev.example.configlab;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigSourceLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigSourceLabApplication.class, args);
    }

    @Bean
    ApplicationRunner showResolvedValue(
            Environment environment,
            LabProperties properties,
            @Value("${lab.message}") String injected) {

        return (ApplicationArguments args) -> {
            System.out.println("=== ONE KEY / FOUR SOURCES ===");

            System.out.println("resolved.environment = "
                    + environment.getProperty("lab.message"));

            System.out.println("resolved.configprops = "
                    + properties.message());

            System.out.println("resolved.value = "
                    + injected);

            System.out.println("raw.osEnvironment = "
                    + System.getenv("LAB_MESSAGE"));

            System.out.println("raw.jvmSystemProperty = "
                    + System.getProperty("lab.message"));

            System.out.println("raw.cliOption = "
                    + args.getOptionValues("lab.message"));

            System.out.println("==============================");
        };
    }
}
```

The `resolved.*` lines represent Spring Boot's **final result** for the key under test:

```text
resolved.environment
resolved.configprops
resolved.value
```

The three `raw.*` lines inspect the **individual channels**:

```text
raw.osEnvironment
raw.jvmSystemProperty
raw.cliOption
```

If a channel is not supplied, the API may return `null`. If a CLI option is provided, `args.getOptionValues("lab.message")` returns a list of its values. This lab always passes a single `--lab.message=...` option per run.

**Note:** The program intentionally prints the full value of a **dummy, non-sensitive key**. Never copy this pattern for passwords, tokens, private keys, connection URLs with credentials, or personal data. In production, log only approved source metadata, validity status, or configuration versions.

### 6.1. Expected Initial Output

With no `LAB_MESSAGE`, no JVM `-Dlab.message`, no CLI `--lab.message`, and no external file:

```text
=== ONE KEY / FOUR SOURCES ===
resolved.environment = from-classpath
resolved.configprops = from-classpath
resolved.value = from-classpath
raw.osEnvironment = null
raw.jvmSystemProperty = null
raw.cliOption = null
==============================
```

This is the baseline for comparing subsequent runs.

### 6.2. Why Run a Separate Application Instance Each Time?

`ApplicationRunner` executes after beans have been created and bound. Each `java -jar` command starts an independent process, so `-D`, environment variables, and command-line args apply from the very beginning.

Changing a value while an application is already running is a **refresh** problem, not this basic startup precedence experiment. Plain Spring Boot does not automatically reload files and recreate all beans when sources change.

---

## 7. Package the JAR Once, Run It Many Times

To avoid mixing Gradle daemon configuration with the application JVM, build the JAR first:

**macOS/Linux:**

```bash
./gradlew clean bootJar
```

**Windows PowerShell:**

```powershell
.\gradlew.bat clean bootJar
```

With this build, the artifact path is typically:

```text
build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Once built, every experiment run uses **that exact JAR**.

macOS/Linux:

```bash
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Windows PowerShell:

```powershell
java -jar .\build\libs\config-source-lab-0.0.1-SNAPSHOT.jar
```

Run commands from the **project root directory**, because several runs rely on `./config/application.properties`. If run from a different working directory, Boot looks for `./config/` relative to the **process's current directory**, not necessarily the directory containing the JAR.

### 7.1. Why Use `java -jar` for This Experiment?

The command:

```bash
./gradlew bootRun -Dlab.message=from-jvm
```

is not a reliable demonstration of passing a system property to the **application JVM**. `-D` on the Gradle command line can be treated as a system property of the **Gradle process**, while `bootRun` uses a JavaExec task to launch the application. Passing system properties to the app through Gradle requires configuring the task/`jvmArgs` explicitly.

With:

```bash
java -Dlab.message=from-jvm -jar app.jar
```

`-D` is unambiguously in the **JVM arguments** running the application itself.

Meanwhile:

```bash
java -jar app.jar --lab.message=from-cli
```

places `--lab.message=...` in **application arguments**. These are the two channels to distinguish.

### 7.2. Verify Java

```bash
java -version
```

Expect Java 21 or a runtime supported by the artifact. If multiple Java installations exist on your machine, verify that `java` in the current terminal points to the right one. The Gradle build toolchain and the Java runtime executing the JAR are two separate things to verify.

---

## 8. Run 1 — Packaged File in JAR Only

Conditions:

- No `config/application.properties` exists in the working directory yet.
- `LAB_MESSAGE` is not set.
- `-Dlab.message` is not passed.
- `--lab.message` is not passed.

Run:

```bash
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Expected:

```text
resolved.environment = from-classpath
resolved.configprops = from-classpath
resolved.value = from-classpath
raw.osEnvironment = null
raw.jvmSystemProperty = null
raw.cliOption = null
```

**Explanation:** `src/main/resources/application.yaml` was packaged into the JAR and Spring Boot loads Config Data from the classpath. With no higher-priority source supplying `lab.message`, the effective value is `from-classpath`.

If your result differs:

1. Check whether an external config file is being loaded.
2. Check whether `LAB_MESSAGE` is set in the process environment.
3. Check which system properties the JVM was launched with.
4. Check whether CLI args are being passed by a wrapper script or IDE.
5. Check whether `SPRING_APPLICATION_JSON` or an active profile is set.

Do not change code before verifying runtime data sources.

---

## 9. Run 2 — Configuration File Outside the JAR

By default, Spring Boot 3.3 searches for `application.properties` or `application.yaml` in several locations outside the JAR, including `./config/` in the working directory. In this lab, use:

```text
./config/application.properties
```

**macOS/Linux:**

```bash
mkdir -p config
printf 'lab.message=from-file\n' > config/application.properties
```

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force -Path .\config | Out-Null
Set-Content -LiteralPath .\config\application.properties `
    -Encoding ASCII -Value 'lab.message=from-file'
```

Because the example uses ASCII characters only, PowerShell `-Encoding ASCII` avoids an unwanted BOM in `.properties` files on Windows PowerShell 5.1. For real applications needing Unicode, choose an encoding explicitly supported by your build/runtime.

Run the **same JAR** again:

```bash
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Expected:

```text
resolved.environment = from-file
resolved.configprops = from-file
resolved.value = from-file
raw.osEnvironment = null
raw.jvmSystemProperty = null
raw.cliOption = null
```

### 9.1. What to Observe

You changed:

```text
External config source
```

without modifying:

```text
Java source
Gradle build
JAR artifact
```

The value changed because **external Config Data outside the JAR** was loaded and takes higher precedence than the packaged resource inside the JAR under default configuration.

You did not need:

- `@PropertySource` for the default `application.properties`.
- A custom `EnvironmentPostProcessor`.
- Spring Cloud Config Server.
- `@RefreshScope`.
- Separate `@Value` fields for each source.

### 9.2. If the External File Does Not Win

Check:

- Is `config/application.properties` under the current working directory?
- Is the filename exactly `application.properties`, not `applications.properties`?
- Is the property spelled `lab.message`?
- Was the file saved as `application.properties.txt` on Windows?
- Is a higher-precedence source defining the same key?
- Is `spring.config.location` altering the search locations?
- Is a profile-specific file or another import taking effect?

Do not conclude an external file was ignored solely because the final value differs; it may have been loaded and overridden by a higher-priority source.

### 9.3. Comparing Packaged YAML and External Properties

Within the same experiment:

```yaml
# Packaged application.yaml
lab:
  message: from-classpath
```

and:

```properties
# External config/application.properties
lab.message=from-file
```

Even though the two files use **different formats**, they represent the exact same canonical property key `lab.message`.

Precedence does not give `.yaml` or `.properties` universal dominance everywhere. **Location, Config Data groups, profiles, imports, and external sources** all factor in. This experiment intentionally puts the two files in **two different locations** to demonstrate external vs. packaged precedence, not `.properties` vs. YAML at the same location.

---

## 10. Run 3 — OS Environment Variable Overrides File

Keep the external file:

```properties
lab.message=from-file
```

**Bash/macOS/Linux:**

```bash
LAB_MESSAGE=from-env \
  java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Placing the variable inline before the command sets `LAB_MESSAGE` only for the **launched process** without exporting it permanently in the shell.

**Windows PowerShell:**

```powershell
$env:LAB_MESSAGE = 'from-env'
java -jar .\build\libs\config-source-lab-0.0.1-SNAPSHOT.jar
Remove-Item Env:LAB_MESSAGE
```

Expected:

```text
resolved.environment = from-env
resolved.configprops = from-env
resolved.value = from-env
raw.osEnvironment = from-env
raw.jvmSystemProperty = null
raw.cliOption = null
```

**Explanation:** `systemEnvironment` contributes `LAB_MESSAGE`; Spring Boot applies its lookup and relaxed binding rules to resolve `lab.message`. The OS environment source has higher precedence than standard Config Data, so `from-file` is overridden.

### 10.1. Why Use `LAB_MESSAGE` Instead of `lab.message` as the Variable Name?

On many operating systems and shells, environment variable names are restricted to letters, digits, and underscores. Spring Boot defines how to map canonical property names to environment variables:

1. Replace dots `.` with `_`.
2. Remove dashes `-`.
3. Convert to uppercase.

Here:

```text
lab.message -> LAB_MESSAGE
```

A more complex example:

```text
my.main-project.person.first-name
    -> MY_MAINPROJECT_PERSON_FIRSTNAME
```

Do not arbitrarily turn dashes into underscores. For relaxed binding into `@ConfigurationProperties`, follow Spring Boot's environment variable naming rules.

### 10.2. Environment Variables Do Not Automatically Create Java System Properties

Seeing:

```text
raw.osEnvironment = from-env
```

and:

```text
raw.jvmSystemProperty = null
```

is **correct**. You did not pass `-Dlab.message`, so `System.getProperty("lab.message")` is `null`.

Spring `Environment` unifies multiple sources for lookup and binding; it **does not copy environment variables into `System.getProperties()`**.

### 10.3. When `LAB_MESSAGE` Still Has No Effect

- The IDE run configuration does not have the variable set.
- You set the variable in one terminal and ran the JAR in another.
- Your PowerShell session removed the variable before launching.
- The variable is set inside a container while you are inspecting a host process.
- `-Dlab.message` or `--lab.message` has higher precedence.
- The environment variable name does not match the canonical property being read.

In the lab, printing `System.getenv("LAB_MESSAGE")` (only with dummy values) is a better check than guessing which shell passed the variable.

---

## 11. Run 4 — JVM `-D` Overrides Environment Variable

Keep the external file `from-file`. At the same time, set:

```text
LAB_MESSAGE=from-env
```

and:

```text
-Dlab.message=from-jvm
```

**Bash/macOS/Linux:**

```bash
LAB_MESSAGE=from-env \
  java -Dlab.message=from-jvm \
  -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

**Windows PowerShell:**

```powershell
$env:LAB_MESSAGE = 'from-env'
java -Dlab.message=from-jvm `
  -jar .\build\libs\config-source-lab-0.0.1-SNAPSHOT.jar
Remove-Item Env:LAB_MESSAGE
```

Expected:

```text
resolved.environment = from-jvm
resolved.configprops = from-jvm
resolved.value = from-jvm
raw.osEnvironment = from-env
raw.jvmSystemProperty = from-jvm
raw.cliOption = null
```

### 11.1. Line-by-Line Explanation

- `LAB_MESSAGE` **still exists**, so `System.getenv()` continues returning `from-env`.
- JVM system property `lab.message` holds `from-jvm`.
- When `Environment` resolves `lab.message`, Java system properties beat OS environment variables in Boot's default order for these sources.
- `@Value("${lab.message}")` resolves against the effective value, receiving `from-jvm`.
- Record `LabProperties` binds the same effective value, receiving `from-jvm`.

The lesson is not that "the env var was deleted", but that **the env var still exists yet loses in precedence competition**.

### 11.2. `-D` Must Come Before `-jar`

Correct:

```bash
java -Dlab.message=from-jvm -jar app.jar
```

Because `-D...` is a **JVM launcher option**.

Do not use:

```bash
java -jar app.jar -Dlab.message=from-jvm
```

to demonstrate a Java system property, because when placed after the JAR filename, it becomes a plain application argument. `System.getProperty("lab.message")` will not be set by that syntax.

Misplacing it prevents Spring Boot from reading `lab.message` from system properties, and the app only sees an argument lacking the `--key=value` format Boot uses for command-line properties.

### 11.3. Gradle `-D` vs. Application `-D`

A command like:

```bash
./gradlew bootRun -Dlab.message=from-jvm
```

is typically handled on the Gradle side; do not assume the property was forwarded to the separate JVM running the application.

If you want to run the app through Gradle and set JVM properties, configure the `JavaExec`/`BootRun` task explicitly, for example in Gradle:

```groovy
tasks.named('bootRun') {
    systemProperty 'lab.message', 'from-jvm'
}
```

However, putting the property **in the build script** can affect subsequent experiment runs. That is why this lab uses `java -D... -jar` to isolate sources without editing the build script between runs.

---

## 12. Run 5 — CLI `--` Overrides JVM Property

This run uses **all four sources**:

1. External file `lab.message=from-file`.
2. OS environment `LAB_MESSAGE=from-env`.
3. JVM system property `-Dlab.message=from-jvm`.
4. Application argument `--lab.message=from-cli`.

**Bash/macOS/Linux:**

```bash
LAB_MESSAGE=from-env \
  java -Dlab.message=from-jvm \
  -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar \
  --lab.message=from-cli
```

**Windows PowerShell:**

```powershell
$env:LAB_MESSAGE = 'from-env'
java -Dlab.message=from-jvm `
  -jar .\build\libs\config-source-lab-0.0.1-SNAPSHOT.jar `
  --lab.message=from-cli
Remove-Item Env:LAB_MESSAGE
```

Expected:

```text
resolved.environment = from-cli
resolved.configprops = from-cli
resolved.value = from-cli
raw.osEnvironment = from-env
raw.jvmSystemProperty = from-jvm
raw.cliOption = [from-cli]
```

### 12.1. Direct Proof of Precedence

You observe **three source values still present**, while **one effective value** is selected:

```text
OS environment:   from-env
JVM system prop:  from-jvm
CLI option:       from-cli
Spring resolved:  from-cli
```

The external file still contains `from-file` and the packaged file still contains `from-classpath`, but they are overridden by higher-priority sources.

This demonstrates:

```text
Different sources can define the same key simultaneously.
The highest-priority source among those supplying the key wins.
Lower sources are not deleted from the system.
```

### 12.2. Application Command-Line Args vs. Java Launcher Args

Distinguish:

```bash
java -Dlab.message=from-jvm -jar app.jar --lab.message=from-cli
```

Here:

- `-Dlab.message=from-jvm`: handled by the JVM launcher.
- `-jar app.jar`: selects the artifact to execute.
- `--lab.message=from-cli`: passed to the application's `main(String[] args)`, and Spring Boot adds this option as a property source by default.

If you invoke:

```bash
java -Dlab.message=from-jvm --lab.message=from-cli -jar app.jar
```

then `--lab.message` appears in the **Java launcher option** position and will likely be rejected by the JVM. Application arguments must come **after** `-jar app.jar`.

### 12.3. What Does `ApplicationArguments` Tell Us?

Spring Boot creates `ApplicationArguments`, where `args.getOptionValues("lab.message")` returns the list of values for that application option if present.

Thus, calling:

```java
args.getOptionValues("lab.message")
```

confirms that `--lab.message=from-cli` actually reached the application.

However, `ApplicationArguments` is not an API for listing all property sources; it only inspects the arguments of the current launch.

---

## 13. Run 6 — Remove Sources One by One to Watch Precedence Step Back

After proving all four sources together, remove them one at a time to observe which source takes over next.

### 13.1. Drop CLI, Keep JVM and Env

**Bash:**

```bash
LAB_MESSAGE=from-env \
  java -Dlab.message=from-jvm \
  -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Expected:

```text
resolved.environment = from-jvm
```

**Explanation:** with the top source (CLI) removed, the JVM system property is the highest remaining source.

### 13.2. Drop JVM `-D`, Keep Env

**Bash:**

```bash
LAB_MESSAGE=from-env \
  java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Expected:

```text
resolved.environment = from-env
```

**Explanation:** OS environment overrides external Config Data.

### 13.3. Drop Environment Variable, Keep External File

**Bash:**

```bash
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Expected:

```text
resolved.environment = from-file
```

**Explanation:** with no env, JVM system property, or CLI option, the external file provides the highest remaining value.

### 13.4. Drop External File, Fall Back to Classpath

**Bash:**

```bash
mv config/application.properties config/application.properties.off
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

**Windows PowerShell:**

```powershell
Rename-Item -LiteralPath .\config\application.properties `
    -NewName 'application.properties.off'
java -jar .\build\libs\config-source-lab-0.0.1-SNAPSHOT.jar
```

Expected:

```text
resolved.environment = from-classpath
```

Restore the file when you need to continue testing:

```bash
mv config/application.properties.off config/application.properties
```

PowerShell:

```powershell
Rename-Item -LiteralPath .\config\application.properties.off `
    -NewName 'application.properties'
```

### 13.5. Why Stepping Backwards Matters

A table stating "CLI > JVM > env > file" is easy to memorize. **Removing each source one by one** proves that:

- Lower values were never erased from where they were declared.
- The winning value shifts based on **which sources are present**.
- Config files continue serving as fallbacks when runtime overrides are absent.
- You can switch between local/staging/production without rebuilding the JAR for small configuration changes.

This is the core benefit of **externalized configuration**.

---

## 14. Full Experimental Verification Table

Fill out this table after running each command:

| Run | Classpath YAML | External file | `LAB_MESSAGE` | JVM `-D` | CLI `--` | Expected result |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `from-classpath` | — | — | — | — | `from-classpath` |
| 2 | `from-classpath` | `from-file` | — | — | — | `from-file` |
| 3 | `from-classpath` | `from-file` | `from-env` | — | — | `from-env` |
| 4 | `from-classpath` | `from-file` | `from-env` | `from-jvm` | — | `from-jvm` |
| 5 | `from-classpath` | `from-file` | `from-env` | `from-jvm` | `from-cli` | `from-cli` |
| 6 | `from-classpath` | `from-file` | `from-env` | `from-jvm` | — | `from-jvm` |
| 7 | `from-classpath` | `from-file` | `from-env` | — | — | `from-env` |
| 8 | `from-classpath` | `from-file` | — | — | — | `from-file` |
| 9 | `from-classpath` | — | — | — | — | `from-classpath` |

In each run, compare the three lines:

```text
resolved.environment
resolved.configprops
resolved.value
```

For a valid scalar key and properly registered bean, all three lines should match. If they differ, do not immediately blame source ordering; you may have a wrong placeholder, wrong prefix, multiple contexts, or a bean initialized at a different point.

### 14.1. Conditions for the Table to Hold

- Run the **exact same JAR** for every step.
- Use the correct working directory.
- Do not activate unintended profiles.
- Do not have `SPRING_APPLICATION_JSON` containing `lab.message`.
- Do not let a wrapper or IDE inject extra `-D` or CLI options.
- Do not edit files inside the JAR between runs.
- Do not add a custom `@PropertySource` for the same key.
- Do not have Spring Cloud, Vault, or Consul providers overriding the key.
- Do not run inside a test harness applying high-priority test property sources.

If any of those conditions change, analyze the result against **all** active sources, not just the four in the table.

---

## 15. Inspecting `Environment` and `PropertySource` Directly

To make it even clearer why one key wins, you can inspect Spring's `PropertySource` list at runtime. This is a tool **for local labs with non-sensitive keys only**.

You can replace `Environment` in the runner with `ConfigurableEnvironment`:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
```

Then, inside the runner:

```java
for (PropertySource<?> source : environment.getPropertySources()) {
    Object candidate = source.getProperty("lab.message");

    if (candidate != null) {
        System.out.println("candidate.source = "
                + source.getName());
        System.out.println("candidate.value = "
                + candidate);
    }
}
```

**Important note:** `Environment` can contain adapted or composite sources such as `configurationProperties`, so not every entry maps 1-to-1 to a physical file. Sources can also use different property-naming representations. Use this snippet as an **observation aid**, not as proof that the first printed entry is always the sole physical origin of the property.

In standard source order, you will typically see names related to:

```text
commandLineArgs
systemProperties
systemEnvironment
Config resource 'file [.../config/application.properties]'
Config resource 'class path resource [application.yaml]'
```

Exact display names depend on the Spring Boot version, loading configuration, and environment. Record the **meaning** of the source rather than relying on exact string matches.

### 15.1. `Environment` Resolves by Precedence

Calling:

```java
environment.getProperty("lab.message")
```

is the API to use when you want the **effective value** at lookup time.

Looping over `PropertySource` entries is a secondary aid to see candidates. If a source wraps or aliases another, a candidate value might appear to repeat; that does not mean two values are being bound.

### 15.2. Origin Tracking Provides Additional Detail

Spring Boot Config Data can attach origin metadata for properties loaded from files. Tools like Actuator `/env` can help investigate sources and file paths, subject to endpoint exposure, security, and sanitization settings.

Never start a production incident investigation by opening `/actuator/env` publicly or logging all `PropertySources`. In this lab we only print a single dummy key. For real secrets, even key names and file paths can be sensitive.

### 15.3. Still Distinguish "Candidate" from "Effective Value"

For example:

```text
file candidate:       from-file
environment candidate: from-env
system JVM candidate:  from-jvm
CLI candidate:         from-cli
```

gives:

```text
effective value:       from-cli
```

Comparing multiple candidates helps reveal **which sources were overridden**, not only which source won.

---

## 16. Testing the Same Key via `application.properties` and `application.yaml`

You used:

```yaml
# Packaged application.yaml
lab:
  message: "from-classpath"
```

and:

```properties
# External config/application.properties
lab.message=from-file
```

These are two equivalent representations of the **same canonical key**.

In YAML:

```yaml
lab:
  message: "hello"
```

flattens to the property path:

```text
lab.message
```

In `.properties`:

```properties
lab.message=hello
```

There are no separate `lab` and `message` variables here; `lab` is the prefix and `message` is the nested field.

### 16.1. Why Not Put Both `application.yaml` and `application.properties` in the Same Folder?

Spring Boot has its own precedence rules when both `.properties` and YAML exist at the same location. According to documentation, some Boot versions prioritize `.properties`. Mixing **format precedence** and **source precedence** at the same time leads to confusing results.

In this lab:

- YAML is packaged inside the JAR.
- Properties live in `./config/` outside the JAR.
- Each location has only one relevant file.
- One key and five distinct labels.

This setup cleanly isolates **value provenance**.

### 16.2. If You Want to Use External YAML

Replace the external file with:

```yaml
# ./config/application.yaml
lab:
  message: "from-file"
```

Conceptually, external Config Data still overrides the packaged file. Keep only one file format per location during this experiment to avoid an extra format-precedence race.

---

## 17. Trying an Explicitly Specified File via `spring.config.additional-location`

In the main lab, `./config/application.properties` is discovered by Spring Boot at default locations. You can also point to another directory explicitly.

For example, create:

```text
./overrides/application.properties
```

with:

```properties
lab.message=from-file
```

Then run:

```bash
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar \
  --spring.config.additional-location=optional:file:./overrides/
```

**PowerShell:**

```powershell
java -jar .\build\libs\config-source-lab-0.0.1-SNAPSHOT.jar `
  --spring.config.additional-location=optional:file:./overrides/
```

With the file at that location, Boot loads the additional external Config Data. `additional-location` **adds** search locations alongside defaults. By contrast, `spring.config.location` changes where Boot searches (and can replace default search locations), so misusing it can accidentally drop the packaged file you rely on as a fallback.

Distinguish:

```text
spring.config.location
spring.config.additional-location
spring.config.import
```

All three control Config Data loading, but they do not behave identically.

### 17.1. The Trailing Slash on a Directory Matters

When configuring a **directory** with `spring.config.location` or `spring.config.additional-location`, Spring Boot typically requires a trailing `/` to distinguish a directory from a file.

For example:

```text
file:./overrides/
```

is a directory location.

While:

```text
file:./overrides/application.properties
```

is a specific file location.

Do not pass raw Windows backslashes in a `file:` URI string without accounting for escaping/URI syntax; URL-style forward slashes `/` are generally more portable in Spring Boot config locations.

### 17.2. Specifying Search Locations via Environment Variables

Example:

```bash
SPRING_CONFIG_ADDITIONALLOCATION=optional:file:./overrides/ \
  java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Follow the environment naming rule of removing dashes and replacing dots with underscores. `spring.config.additional-location` affects **configuration discovery very early**, so set it via OS environment, JVM system property, or command-line args—not inside a file that Boot can only find after knowing the location.

For the pure single-key `lab.message` experiment, section 17 is an **optional extension** and does not belong in the baseline matrix.

---

## 18. Profile-Specific Files Can Add Another Layer of Competition

Suppose alongside the base file, you create:

```text
./config/application-dev.properties
```

with:

```properties
lab.message=from-dev-file
```

and activate:

```bash
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=dev
```

Within Config Data, a profile-specific file can override the base file per Spring Boot's profile rules.

However, if you also set:

```bash
LAB_MESSAGE=from-env
```

then **OS environment still takes precedence over standard Config Data** for the same key, even when the file is profile-specific.

### 18.1. Profiles Select Config Data; They Do Not Promote a File to CLI Priority

`application-dev.properties` is still a **config file**.

Having `dev` in its filename does not elevate it to Java system property or CLI precedence. Profiles control which files/documents are active and how Config Data documents compete within their own tier.

Mental model:

```text
CLI -> JVM -> Environment -> Config Data
                              |
                              +-- profile-specific
                              +-- external vs packaged
                              +-- imports / document ordering
```

Exact rules inside Config Data are richer than this sketch, but they do not alter the basic comparison across the four sources in this lab.

### 18.2. Why Not Enable Profiles in the Five Baseline Runs?

The goal is to **hold every variable constant except the one source being added or removed**. Enabling a profile changes the Config Data set, making it harder to isolate which source won.

Complete the baseline matrix first, then experiment with profiles as an add-on.

---

## 19. `SPRING_APPLICATION_JSON` Is Outside the Four Sources, Yet Important to Know

Spring Boot supports a special `SPRING_APPLICATION_JSON` source containing JSON supplied via an environment variable or system property as supported by the framework.

Example:

```bash
SPRING_APPLICATION_JSON='{"lab":{"message":"from-json"}}' \
  java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar
```

Among standard sources in Spring Boot 3.3, `SPRING_APPLICATION_JSON` has **higher** precedence than Java system properties and regular OS environment variables, but **lower** precedence than command-line arguments.

So if your CI or platform sets this variable without your knowledge, the four-source table will not match predictions.

Do not inject JSON during runs 1–5 before finishing the main exercise; it acts as **a fifth source** and breaks single-variable isolation.

### 19.1. `null` in JSON Does Not Delete a Lower-Priority Property

According to Spring Boot documentation, keys with `null` values are added to the JSON property source, yet `PropertySourcesPropertyResolver` can treat `null` as a missing value. Therefore, setting `null` in `SPRING_APPLICATION_JSON` is not a reliable way to "unset" a value defined in a lower-priority source.

To disable a feature, use an explicit boolean or enum property with a clear contract, such as:

```properties
lab.enabled=false
```

instead of relying on `null` as a special override command.

---

## 20. Spring Boot Command-Line Properties Can Be Disabled

By default, Spring Boot adds arguments of the form:

```text
--name=value
```

into `Environment`.

However, an application can configure:

```java
SpringApplication app =
        new SpringApplication(ConfigSourceLabApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
```

When disabled, the command-line property source is **no longer added by default**, even though `ApplicationArguments` can still inspect the options.

This illustrates that **the matrix assumes standard application configuration**. Do not apply this change to the main lab class; if you want to test it, create a separate branch or copy and restore the main class afterward.

A CLI value failing to win does not automatically mean the CLI parser is broken; the application itself may have disabled command-line properties.

---

## 21. Can This Be Run with `bootRun`?

Yes. The Spring Boot Gradle plugin provides the `bootRun` task, where you can pass application arguments:

```bash
./gradlew bootRun --args='--lab.message=from-cli'
```

**PowerShell:**

```powershell
.\gradlew.bat bootRun --args="--lab.message=from-cli"
```

This command works well for testing a **CLI option** via Gradle.

However, when the goal is to distinguish **application Java system properties** from **Gradle Java system properties**, running the JAR directly is much clearer:

```bash
java -Dlab.message=from-jvm -jar app.jar
```

### 21.1. Two JVMs May Be Involved

A `bootRun` invocation can involve:

```text
Gradle client / daemon JVM
          |
          v
BootRun / JavaExec task
          |
          v
Application JVM
```

Do not assume every `-D` flag on the Gradle command line reaches the application JVM.

To pass a property intentionally through `bootRun`, configure the Gradle task explicitly:

```groovy
tasks.named('bootRun') {
    systemProperty 'lab.message', 'from-jvm'
}
```

Or use `jvmArgs` per the task API. That modifies the build definition, however, and affects subsequent runs if you forget to remove it.

### 21.2. Watch Gradle's Environment Too

When you set an environment variable in the shell running Gradle, `bootRun` generally inherits it for the spawned process. Still, an IDE, daemon, or container wrapper can alter the environment. If results look surprising, compare the `raw.osEnvironment` line printed by the **application itself**, rather than checking only the shell variables.

---

## 22. A Binding Integration Test, and Its Limitations

Create `src/test/java/dev/example/configlab/LabPropertiesTest.java`:

```java
package dev.example.configlab;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "lab.message=from-test"
})
class LabPropertiesTest {

    @Autowired
    LabProperties properties;

    @Test
    void bindsCanonicalProperty() {
        assertEquals("from-test", properties.message());
    }
}
```

Run:

**Bash:**

```bash
./gradlew test
```

**PowerShell:**

```powershell
.\gradlew.bat test
```

This test verifies **`@ConfigurationProperties` registration and binding**, not the four-source precedence experiment. `@SpringBootTest(properties=...)` injects **test-specific properties** with their own priority, so `from-test` does not contradict the `java -jar` startup matrix.

To automate the matrix itself, use an **integration script that runs the JAR multiple times with controlled environment variables and JVM args**.

### 22.1. Why Not Use a JUnit Test Calling `System.setProperty()` for Every Scenario?

You can write dedicated tests for system properties, but you would have to manage:

- When the Spring application context is created.
- Spring Test context caching.
- Test framework property precedence.
- Cleanup of JVM-global system properties.
- Whether parallel tests share global state.
- Whether external `./config` files affect the test's working directory.

Without controlling those factors, tests can behave differently from a normal `java -jar` process. This practice uses **one process per run** to avoid ambiguity.

---

## 23. Automating with a Bash Script on macOS/Linux

After running the steps manually, you can create `scripts/run-matrix.sh` to repeat them quickly in Bash. The script uses one JAR, writes the external file, and checks the resolved value.

```bash
#!/usr/bin/env bash
set -euo pipefail

JAR="build/libs/config-source-lab-0.0.1-SNAPSHOT.jar"

if [[ ! -f "$JAR" ]]; then
  echo "Build the JAR first: ./gradlew bootJar" >&2
  exit 1
fi

mkdir -p config
printf 'lab.message=from-file\n' > config/application.properties

run_case() {
  local expected="$1"
  shift

  local output
  output="$("$@")"

  printf '%s\n' "$output" |
    grep -F "resolved.environment = $expected" >/dev/null || {
      printf 'Expected: %s\n' "$expected" >&2
      printf '%s\n' "$output" >&2
      return 1
    }

  printf 'PASS: %s\n' "$expected"
}

# Run 2: external file.
run_case from-file java -jar "$JAR"

# Run 3: environment variable.
run_case from-env env LAB_MESSAGE=from-env \
  java -jar "$JAR"

# Run 4: JVM system property.
run_case from-jvm env LAB_MESSAGE=from-env \
  java -Dlab.message=from-jvm -jar "$JAR"

# Run 5: CLI argument.
run_case from-cli env LAB_MESSAGE=from-env \
  java -Dlab.message=from-jvm -jar "$JAR" \
  --lab.message=from-cli
```

Run:

```bash
chmod +x scripts/run-matrix.sh
./scripts/run-matrix.sh
```

The script uses dummy data and requires no credentials. It checks the **effective value** printed to stdout.

### 23.1. Note on Isolation

If your shell already exports `LAB_MESSAGE` or `SPRING_APPLICATION_JSON`, file-only runs may be affected. For reproducible results, use a clean shell/container or clear the relevant variables beforehand.

You can run:

```bash
unset LAB_MESSAGE
unset SPRING_APPLICATION_JSON
```

in a dedicated test shell, but do not run that blindly in a terminal holding critical operational environment variables. Real processes may require other variables, so do not run `env -i` unless you know which `PATH`/`JAVA_HOME` variables are needed.

### 23.2. This Script Is a Deployment Check, Not a Unit Test

An integration script spawning processes and checking stdout verifies:

- The JAR artifact runs.
- External Config Data files are loaded.
- Env vars and JVM/CLI args reach the process.
- Spring Boot resolves properties as expected.

It does not replace unit tests for business logic, nor does it cover every possible profile or provider.

---

## 24. Automating with PowerShell on Windows

In Windows PowerShell, you can run each case sequentially:

```powershell
$jar = '.\build\libs\config-source-lab-0.0.1-SNAPSHOT.jar'

New-Item -ItemType Directory -Force -Path '.\config' | Out-Null
Set-Content -LiteralPath '.\config\application.properties' `
    -Encoding ASCII -Value 'lab.message=from-file'

# File only:
Remove-Item Env:LAB_MESSAGE -ErrorAction SilentlyContinue
java -jar $jar

# Environment:
$env:LAB_MESSAGE = 'from-env'
java -jar $jar

# JVM property:
java -Dlab.message=from-jvm -jar $jar

# CLI takes higher precedence:
java -Dlab.message=from-jvm -jar $jar --lab.message=from-cli

# Clean up test environment afterward:
Remove-Item Env:LAB_MESSAGE -ErrorAction SilentlyContinue
```

Observe `resolved.environment` after each run:

```text
from-file
from-env
from-jvm
from-cli
```

One notable difference between Bash and PowerShell is that:

```bash
LAB_MESSAGE=from-env java -jar app.jar
```

is Bash syntax for **a single process**; PowerShell uses:

```powershell
$env:LAB_MESSAGE = 'from-env'
java -jar app.jar
Remove-Item Env:LAB_MESSAGE
```

Typing only:

```powershell
LAB_MESSAGE=from-env
```

is not standard PowerShell syntax for passing an environment variable to a child process.

### 24.1. Why Use `-ErrorAction SilentlyContinue` When Removing the Variable?

When the variable does not exist yet, `Remove-Item` otherwise throws an unnecessary error. Use this option in the lab solely to clean up the dummy variable you set.

Never use cleanup scripts to wipe arbitrary environment variables in a production terminal.

---

## 25. Debugging Unexpected Results

### 25.1. External File Outside JAR Is Not Loaded

**Symptom:** expected `from-file`, got `from-classpath`.

Check:

1. The current working directory of the process.
2. Does a `./config/` directory exist there?
3. Is the file named `application.properties` without an accidental extra extension?
4. Does the file contain the exact `lab.message` key?
5. Are you running an older JAR from a previous build?
6. Did `spring.config.location` replace the default locations?
7. Is a profile-specific document or another import changing the value?

You can enable trace logging specifically for Config Data loading when needed:

```bash
java -jar build/libs/config-source-lab-0.0.1-SNAPSHOT.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
```

Never log the entire environment or secrets in production just to debug source loading. Enable TRACE only temporarily and control where logs are stored.

### 25.2. `LAB_MESSAGE` Set, but Value Did Not Change

**Symptom:** `raw.osEnvironment` is `null`.

Possible causes:

- The variable was not exported to the process.
- The terminal/IDE running the app is not the one where you set the variable.
- PowerShell used invalid syntax.
- Docker/Kubernetes manifest did not inject the variable into the target container.
- Case mismatch in the environment variable name.

If `raw.osEnvironment = from-env` yet the resolved value is not `from-env`, a **higher-priority source** such as JVM `-D` or a CLI option is likely supplying the same key.

### 25.3. `-D` Appears to Have No Effect

**Symptom:** `raw.jvmSystemProperty` is `null`.

Check:

- Is `-D` placed **before** `-jar`?
- Are you passing `-D` to Gradle instead of the application JVM?
- Are you using the `java` launcher as shown?
- Did you mistype `-Dlab.message` as `-Dlab-message`?
- Is a wrapper script rewriting or stripping JVM arguments?

If `raw.jvmSystemProperty` is right yet the resolved value differs, check for a CLI option or higher-precedence source.

### 25.4. CLI Does Not Win

**Symptom:** `--lab.message=from-cli` is present, yet the effective value differs.

Check:

- Does the option appear **after** the JAR filename?
- Does it use two dashes `--`?
- Does the main class call `SpringApplication.run(...)` with the original `args`?
- Did the application call `setAddCommandLineProperties(false)`?
- Is a test framework or custom code altering property sources?
- Was the same option passed multiple times with unexpected ordering?

In the lab, `raw.cliOption = [from-cli]` confirms the application received the option properly.

### 25.5. `@Value` Differs from `@ConfigurationProperties`

Possible causes:

- The placeholder differs from the canonical key.
- Wrong prefix or unregistered record.
- A bean was created earlier than assumed.
- Data changed after context startup and only one source was updated.
- Different converters or custom binding logic.
- One place reads `System.getenv()` instead of Spring `Environment`.

In this lab with one scalar key, a single startup, and no refresh mechanism, all three `resolved.*` lines must match.

### 25.6. `System.getProperty` Remains Null Even Though `Environment` Is Correct

This is **expected behavior** when the value comes from an OS env var or a file. There is no reason for JVM system properties to be populated from Config Data.

### 25.7. Using `config/application.properties` with a Conflicting Format

If you also place `config/application.yaml` at the same location with the same key, precedence between `.properties` and YAML in the same directory can affect the outcome. Do not place a second format in the same location when testing source precedence.

### 25.8. File Edited, Running Process Still Prints Old Value

In this lab, every command starts a fresh process. If you edit a file **while a Spring Boot process is already running**, there is no automatic live refresh by default. Config Data is normally loaded at startup; applying file changes requires a restart or an explicit reconfiguration mechanism.

This is not a precedence bug; it is part of the **configuration reload lifecycle**.

---

## 26. Mapping to IDE Run Configurations

When running the project in IntelliJ IDEA, Eclipse, or VS Code, Run Configurations usually expose fields like:

```text
Environment variables
VM options
Program arguments
Working directory
```

These four fields map directly to the lab's channels:

| IDE field | Lab source | Example |
| --- | --- | --- |
| Environment variables | OS environment | `LAB_MESSAGE=from-env` |
| VM options | JVM system property | `-Dlab.message=from-jvm` |
| Program arguments | Application CLI args | `--lab.message=from-cli` |
| Working directory | External file search root | Folder containing `config/application.properties` |

If you put `-Dlab.message=from-jvm` into **Program arguments**, it will not become a JVM system property.

If you put `--lab.message=from-cli` into **VM options**, the Java launcher will not pass it as a Spring Boot application argument.

If the working directory points to a different module, `./config/application.properties` at the project root will not be found.

### 26.1. Quick Comparison Check

Run the exact same configuration via your IDE and via `java -jar`. If results differ, inspect:

- Working directory.
- VM options.
- Program arguments.
- Environment variables.
- Active profiles.
- Artifact/classpath and which code version is running.
- Whether the IDE uses DevTools restart or auto-build.

Never assume precedence changed just because you switched launchers.

---

## 27. Mapping to Docker

If you package the JAR into a container image:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/config-source-lab-0.0.1-SNAPSHOT.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Docker can inject environment variables:

```bash
docker run --rm -e LAB_MESSAGE=from-env \
  config-source-lab:demo
```

The app will then see `LAB_MESSAGE` inside the process.

To add a CLI option alongside it:

```bash
docker run --rm -e LAB_MESSAGE=from-env \
  config-source-lab:demo \
  --lab.message=from-cli
```

Note that with `ENTRYPOINT ["java","-jar","/app/app.jar"]`, Docker arguments after the image name are appended to **ENTRYPOINT** and become application CLI args. To pass `-D` before `-jar`, adjust the `ENTRYPOINT`/wrapper script or use `JAVA_TOOL_OPTIONS` carefully (remembering that the JVM reads `JAVA_TOOL_OPTIONS` and logs a notice).

Inside a container, the model remains the same:

```text
Image/JAR            -> code and packaged application.yaml
Environment          -> LAB_MESSAGE
JVM arguments        -> -Dlab.message
Application arguments -> --lab.message
Mounted config files -> ./config/application.properties or configtree
```

Running inside a container does not suddenly invert the order of the four standard sources.

### 27.1. Avoid Putting Secrets on Command Lines

Values passed via CLI args or `-D` can show up in process listings, diagnostics, and deployment manifests. Environment variables can also be exposed via infrastructure, logs, or diagnostics if permissions are overly broad.

For production secrets, use a secret manager or protected volume—never pass raw secrets in precedence experiments or print them to stdout like this lab does.

---

## 28. Mapping to Kubernetes

A Kubernetes Pod can configure:

```yaml
env:
  - name: LAB_MESSAGE
    value: "from-env"
```

Inside the application:

```java
System.getenv("LAB_MESSAGE")
```

sees the value given to the container at creation time.

At the same time, a ConfigMap can be mounted into a directory containing `application.properties`, or data can be supplied via `configtree:`. These participate in Config Data according to how the application is configured.

### 28.1. Source Precedence vs. Rollout Order

Updating a Kubernetes ConfigMap does not automatically update environment variables or rebind files inside an already-running JVM. An existing Pod keeps its own environment snapshot.

Source precedence answers:

> "When Spring Boot loads and resolves properties, which source wins?"

Deployment mechanics answer:

> "When an external source changes, does the running process pick up and apply the update?"

These are two different questions. For critical configuration, a controlled rolling restart is usually the cleanest way to ensure new processes read the latest configuration revision.

### 28.2. Using Both a ConfigMap and an Env Var

Suppose:

```text
ConfigMap mounted file: lab.message=from-file
Pod environment:      LAB_MESSAGE=from-env
```

under standard ordering, the OS environment variable overrides the Config Data file.

If an engineer edits the ConfigMap yet the app still sees `LAB_MESSAGE`, they might mistakenly think the volume mount is broken. Before debugging mounts, check whether **the same key is supplied by multiple sources**.

---

## 29. Caution When Adding Spring Cloud Config, Consul, or Vault

The baseline lab is **Boot-only**. When adding a remote provider, `spring.config.import` can introduce new property sources into `Environment`:

```yaml
spring:
  config:
    import: "optional:configserver:"
```

or Consul/Vault imports depending on dependencies and setup.

When that happens:

- `lab.message` may live in a remote Config Data document.
- Precedence depends on import ordering, provider-specific behavior, and override settings.
- Multiple contexts, profiles, or labels may be involved.
- Updating the backend does not automatically refresh beans inside running processes.
- Secret management introduces separate access control and audit requirements.

Do not blindly apply the four-source file/env/JVM/CLI matrix to a multi-provider system without checking which property sources are active.

### 29.1. Why Learn the Four Core Sources First?

Because the four core sources run **with no network and no external services**. You master `Environment` and precedence before introducing Config Server, Consul, Vault, Kubernetes Secrets, or Spring Cloud Refresh.

This also narrows down variables when debugging production: first verify whether JVM/OS/CLI overrides the key locally before investigating remote backends.

---

## 30. Default and Override Policies in Real Applications

A clean layered model is:

```text
Packaged application.yaml:
  safe, non-sensitive defaults

External file / profile:
  environment-specific deployment settings

OS environment:
  platform-injected overrides

JVM system property:
  launcher / runtime overrides (if used)

Application CLI:
  explicit launch-time overrides
```

However, a source having higher precedence does not mean it **should be permitted** to override every key under organizational policy.

For example:

- Production security settings may need to be locked down by pipelines or admission policies.
- Database credentials should not be casually overridden via CLI by unauthorized operators.
- Flags affecting data schemas require reviewed rollouts rather than ad-hoc environment flips.
- Overly permissive defaults can misbehave if higher-priority sources are absent.

**Governance of configuration changes** sits outside Boot's property lookup order. Combine RBAC, secrets management, CI/CD approvals, and startup checks.

### 30.1. Do Not Rely on "CLI Always Wins" as Governance

If multiple teams modify the same key across different sources, they create hard-to-audit conflicts. Document ownership clearly:

```text
lab.message:
  owner = learning-team
  default = application.yaml
  allowed overrides = dev/test/CI
  forbidden = real secret
```

In production, every critical property group needs an owner, a primary source, override rules, and a rollback plan.

---

## 31. Extended Exercises

### Exercise A — Predict Output Before Running

Given:

```properties
# file outside JAR
lab.message=A
```

```text
LAB_MESSAGE=B
```

```text
-Dlab.message=C
```

```text
--lab.message=D
```

Write down:

1. Value of `Environment.getProperty("lab.message")`.
2. Value of `System.getenv("LAB_MESSAGE")`.
3. Value of `System.getProperty("lab.message")`.
4. Result of `ApplicationArguments.getOptionValues("lab.message")`.

Then run the application with all four sources to verify.

### Exercise B — Remove Sources One by One

Starting from Exercise A, remove `--lab.message`, then `-Dlab.message`, then `LAB_MESSAGE`, and then the external file. Record the output at each step and explain why the JAR never needed to be rebuilt.

### Exercise C — Misplaced JVM Argument

Compare:

```bash
java -jar app.jar -Dlab.message=from-jvm
```

against:

```bash
java -Dlab.message=from-jvm -jar app.jar
```

Explain the difference. Determine in which case `System.getProperty("lab.message")` has a value.

### Exercise D — Wrong IDE Run Configuration Fields

In your IDE, put `--lab.message=from-cli` in VM options and `-Dlab.message=from-jvm` in Program arguments. What happens? Move them back to the proper fields and compare.

### Exercise E — Change Current Working Directory

Build the JAR once, place `./config/application.properties` at the project root, and launch the JAR from another directory. Why is the external file missed? Use `--spring.config.additional-location=...` to point to the location explicitly.

### Exercise F — Environment Variables and Relaxed Binding

Replace the key with:

```text
demo.main-project.display-name
```

Derive the environment variable name using Spring Boot's rules. Then write a record and verify whether the binder picks it up.

### Exercise G — Packaged File Only

Delete or rename the external file, clear the environment variable in your shell, and omit `-D` and CLI args. Run again. Which value serves as the fallback? If no fallback exists at all, how should the system handle a required setting?

### Exercise H — Add `SPRING_APPLICATION_JSON`

Supply a fifth value `from-json` via JSON while keeping `LAB_MESSAGE=from-env` and `-Dlab.message=from-jvm`. Under default Boot 3.3 ordering, which source wins without CLI? Which wins with CLI?

### Exercise I — Compare Bean and `Environment`

Update the runner to also print `LabProperties.message()`. Across all startup cases, does it agree with `Environment.getProperty("lab.message")`? If not, inspect bean registration and property naming.

### Exercise J — Kubernetes Scenario

Suppose a mounted ConfigMap file has `from-file`, while the Deployment env sets `LAB_MESSAGE=from-env`. In a new Pod, which key takes precedence? After editing the ConfigMap, why might a running Pod still keep `from-env`?

### Exercise K — When the Key Is a Secret

If `lab.message` were changed to `payment.gateway-token`, how would you change logging, provisioning, and access controls? Why should you never pass tokens via `-D` or CLI and print them to stdout for debugging?

### Exercise L — Write an Automated Verification Script

Write a Bash or PowerShell script running the same JAR across all four cases: file, env, JVM, and CLI. The script must assert each expected output and exit non-zero if any check fails.

---

## 32. Self-Check Questions

**1.** What is the default precedence order among CLI options, JVM system properties, OS environment variables, and standard Config Data in Spring Boot 3.3?

**2.** Why can the same JAR run with two different configuration values?

**3.** Can `System.getenv("LAB_MESSAGE")` read `-Dlab.message`?

**4.** Does `System.getProperty("lab.message")` automatically read `application.yaml`?

**5.** How does `Environment.getProperty("lab.message")` differ from those two Java APIs?

**6.** In `java -jar`, should `-Dlab.message` go before or after `-jar`?

**7.** Should `--lab.message` go before or after the JAR filename?

**8.** What is the environment variable name corresponding to `lab.message`?

**9.** Why can `lab.message` in an external file override packaged YAML?

**10.** If a key exists in both env and a file, does `Environment` concatenate the two Strings?

**11.** Is Cloud Config Server required for Boot to read an external `application.properties`?

**12.** Do you need a custom converter for `String message`?

**13.** In this lab, what does `ApplicationArguments` show?

**14.** Why doesn't `-D...` on a Gradle command always prove the property reached the application JVM?

**15.** If `System.getenv()` returns `from-env` while Spring resolves `from-cli`, was the env var deleted?

**16.** Can `SPRING_APPLICATION_JSON` affect this matrix?

**17.** If you edit external YAML while a process is running, does Boot automatically rebind beans immediately?

**18.** Does `application-dev.properties` have the exact same precedence tier as a CLI option?

**19.** Why check the working directory when the file sits in `./config/`?

**20.** Should you print raw API token values in production to prove source precedence?

### Suggested Answers

1. CLI is highest, followed by JVM system properties, OS environment variables, and Config Data.
2. Because runtime sources can supply or override values without changing the binary.
3. No; it reads only the OS environment.
4. No; it reads only JVM system properties.
5. Spring `Environment` merges multiple property sources in precedence order.
6. Before `-jar`.
7. After the JAR filename.
8. `LAB_MESSAGE`.
9. Because external Config Data at a default location takes higher precedence than packaged resources.
10. Not for scalar Strings; the higher-priority source wins.
11. No; Boot core includes Config Data support.
12. No.
13. The application options received through `main(String[] args)`.
14. `-D` may apply only to Gradle's JVM, not the application's JVM.
15. No; the env var still exists, but the higher-priority source was selected.
16. Yes; it is a source with its own precedence tier.
17. Not by default; an explicit restart or refresh mechanism is required.
18. No; it is still Config Data.
19. Relative locations resolve against the process's working directory.
20. No; use dummy data or controlled presence/origin checks.

---

## 33. Checklist for Applying This Method at Work

Before concluding a property comes from the wrong source:

- [ ] Record the exact canonical key being investigated.
- [ ] Check the effective value Spring reads without exposing secrets.
- [ ] List every source that could define this key.
- [ ] Verify the CLI arguments the application process actually received.
- [ ] Verify the application process's JVM system properties, not Gradle's.
- [ ] Verify the OS environment passed into the process/container.
- [ ] Check Config Data files inside and outside the JAR.
- [ ] Check the working directory and custom config locations.
- [ ] Check profile-specific documents and imports, if any.
- [ ] Check `SPRING_APPLICATION_JSON` or test-specific properties.
- [ ] Check the `@ConfigurationProperties` prefix, record registration, and `@Value` placeholders.
- [ ] Do not confuse editing a file with a running process refreshing its data.
- [ ] Never print secrets or the entire `Environment` to logs.
- [ ] When remote providers are present, verify their precedence and refresh semantics as well.
- [ ] Change only one variable per run when comparing outcomes.
- [ ] Use the exact same JAR artifact across verification scenarios.
- [ ] Record expected/actual results in a repeatable matrix.
- [ ] For CI verification, run each scenario in an isolated process/environment.
- [ ] Establish ownership and override rules for critical keys.
- [ ] Define safe fallbacks and validation when a source is missing.

## 34. Conclusion

The single-key experiment yields clear, observable evidence:

```text
Packaged file:     lab.message=from-classpath
External file:     lab.message=from-file
OS environment:    LAB_MESSAGE=from-env
JVM property:      -Dlab.message=from-jvm
CLI option:        --lab.message=from-cli

If all exist simultaneously in a standard startup:
Effective value:   from-cli
```

Remove the top source, and the next source in precedence takes over. **Overridden sources still exist**; Spring Boot simply selects the effective value according to `PropertySource` precedence.

Keep the APIs clear:

```text
System.getenv()         -> queries OS environment only
System.getProperty()    -> queries JVM system properties only
ApplicationArguments    -> describes app CLI arguments
Environment.getProperty -> resolves across Spring property sources
@ConfigurationProperties -> binds effective values into typed objects
@Value                  -> resolves placeholders via the bean container
```

With the same source/binary, you can vary configuration per environment or launch without touching code. That is the foundational benefit of **Spring Boot Externalized Configuration**.

However, do not turn "CLI has high precedence" into an informal operations habit: define owners, override permissions, secret security, restart/refresh procedures, and additional sources before going to production.

### References

1. [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): `PropertySource` list and precedence order, Config Data, locations, `SPRING_APPLICATION_JSON`, command-line args, and relaxed binding.
2. [Spring Boot 3.3 — Accessing Command Line Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.command-line-args): `--key=value` and `SpringApplication.setAddCommandLineProperties(false)`.
3. [Spring Boot 3.3 — Config Data Files](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.files): YAML/properties files, default locations, packaged vs. external.
4. [Spring Boot 3.3 — Binding from Environment Variables](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding.environment-variables): dot/underscore/kebab-case rules and env vars.
5. [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): `@ConfigurationProperties`, constructor binding, `@Value`.
6. [Spring Boot Gradle Plugin — Running your Application](https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html): `bootRun` and passing arguments via Gradle.
7. [Oracle Java 21 Tool Documentation — java Launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `-Dproperty=value`, `-jar`, VM options, and application arguments.
