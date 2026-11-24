# Distinguishing JVM Options, Build-Tool Options, and Application Arguments

When running a Spring Boot application, a single command line can contain options intended for the **Java Virtual Machine (JVM)**, the **build tool (Gradle)**, and **the application itself**. These three groups are processed at different times. Putting the right value in the wrong position can cause a setting to have no effect or be interpreted as an ordinary argument.

Goal of this lesson: identify **who receives each parameter**, **which process it affects**, **how to pass them via `java -jar`, `bootRun`, and IDE**, and verify the values actually reaching the application.

## 1. How Do the Three Parameter Groups Differ?

| Group | Receiver and Processing Time | Examples | Typical Effect |
| --- | --- | --- | --- |
| **JVM options** (VM options) | Java launcher/JVM receives **before** calling `main` of the target process | `-Xmx512m`, `-Ddemo.mode=fast`, `--add-opens=...` | Heap size, system properties, certain JVM behaviors |
| **Build-tool options** (build-tool options/properties) | Gradle receives when processing the build/task command | `--offline`, `--stacktrace`, `-PdemoMode=fast`, `-Dorg.gradle.jvmargs=...` | How Gradle configures the project, downloads dependencies, runs tasks, and runs Gradle's JVM |
| **Application arguments** (application/program arguments) | Application's `main(String[] args)` receives, which Spring Boot may then parse | `--server.port=9090`, `--spring.profiles.active=dev`, `input.csv` | Spring Boot configuration via command line or application-specific input data |

**Core point:** `-Ddemo.mode=fast` is *JVM system property syntax* when placed in a `java` command before the main class/`-jar`. However, `-Ddemo.mode=fast` in a `gradlew` command affects the **JVM running Gradle**; it is not automatically forwarded to the JVM that `bootRun` spawns. Likewise, `-PdemoMode=fast` only creates a **Gradle project property** unless the build script explicitly forwards that value to the application.

Processing model when using Gradle:

~~~text
Shell / IDE
  └─ gradlew / Gradle: reads Gradle options, -P, and Gradle -D
       └─ bootRun task (JavaExec type): spawns the application Java process
            ├─ JVM reads VM options and JVM system properties configured for bootRun
            └─ main(String[] args) receives program arguments
                 └─ SpringApplication.run(..., args)
                      ├─ ApplicationArguments parses arguments
                      └─ Environment can receive --key=value as a configuration property
~~~

With `java -jar`, there is no Gradle layer in between; the Java launcher directly receives VM options and starts the application.

## 2. `java` and `java -jar`: Position Determines Meaning

Common syntax:

~~~text
java [VM options] -jar <jar-path> [application-arguments...]
java [VM options] <MainClassName> [application-arguments...]
~~~

Example running a Spring Boot JAR (replace `demo.jar` with the JAR produced in your project):

~~~bash
java -Xms128m -Xmx512m -Ddemo.mode=fast -jar build/libs/demo.jar --spring.profiles.active=dev --server.port=9090 input.csv
~~~

Reading each part:

- `-Xms128m`: initial heap size handled by the JVM.
- `-Xmx512m`: maximum heap limit of the JVM.
- `-Ddemo.mode=fast`: sets a JVM system property; readable via `System.getProperty("demo.mode")`.
- `-jar build/libs/demo.jar`: instructs the Java launcher to run this JAR.
- `--spring.profiles.active=dev` and `--server.port=9090`: **application arguments**, which Spring Boot converts by default into `Environment` properties.
- `input.csv`: non-`--key=value` application argument; the application decides how to use it.

### Try Directly with Java 17+

Create a file `LaunchArgsDemo.java` containing all of the following program; this example uses only the JDK, helping clarify the boundary before adding Spring Boot:

~~~java
import java.util.Arrays;

public class LaunchArgsDemo {
    public static void main(String[] args) {
        System.out.println("systemProperty="
                + System.getProperty("demo.mode", "<unset>"));
        System.out.println("args=" + Arrays.toString(args));
    }
}
~~~

Compile and run:

~~~bash
javac LaunchArgsDemo.java
java -Ddemo.mode=fast -Xmx512m LaunchArgsDemo --server.port=9090 input.csv
~~~

Exact two lines printed by the program:

~~~text
systemProperty=fast
args=[--server.port=9090, input.csv]
~~~

Move `-D` to **after** the class name:

~~~bash
java LaunchArgsDemo -Ddemo.mode=fast
~~~

When no other source sets `demo.mode`, the program prints:

~~~text
systemProperty=<unset>
args=[-Ddemo.mode=fast]
~~~

Because in that position `-Ddemo.mode=fast` is merely an element of `args`, not a JVM option. The same rule applies after the JAR name: `java -jar demo.jar -Xmx512m` passes `-Xmx512m` as an application argument; it does **not** set the heap limit. Depending on how the application parses arguments, a misplaced string may be ignored or cause an error.

## 3. Gradle: Distinguishing Build-Tool Options from `bootRun` Parameters

`./gradlew` (on Windows typically `gradlew.bat`) is the **Gradle Wrapper**. Gradle parses its own options, configures the project, and executes tasks.

Example:

~~~bash
./gradlew --offline -PtargetEnv=local bootJar
~~~

Here `--offline` tells Gradle to avoid network repository access; `-PtargetEnv=local` creates a project property for the build script; `bootJar` is the packaging task. This command **does not launch the application**, so there is no application `main(String[] args)` to receive arguments.

### Passing Application Arguments via `bootRun`

The Spring Boot plugin provides the `bootRun` task based on `JavaExec`. Gradle accepts the task option `--args`, and forwards its contents as arguments to the Java process running the application:

~~~bash
./gradlew bootRun --args="--spring.profiles.active=dev --server.port=9090 input.csv"
~~~

On Windows:

~~~powershell
gradlew.bat bootRun --args="--spring.profiles.active=dev --server.port=9090 input.csv"
~~~

`--args` is an option processed by Gradle; the strings **inside** its value are the arguments the application receives. As a result, the application's `main(String[] args)` sees `--spring.profiles.active=dev`, `--server.port=9090`, and `input.csv`.

### Passing VM Options to the Right `bootRun` JVM

In `build.gradle` using Groovy DSL, configure the task directly:

~~~groovy
tasks.named('bootRun') {
    jvmArgs '-Xmx512m'
    systemProperty 'demo.mode', project.findProperty('demoMode') ?: 'default'
}
~~~

Then run:

~~~bash
./gradlew -PdemoMode=fast bootRun --args="--server.port=9090 input.csv"
~~~

Value flow:

1. Gradle reads project property `demoMode=fast` from `-PdemoMode=fast`.
2. The `bootRun` configuration explicitly forwards that value as **system property `demo.mode=fast` of the application JVM**.
3. `jvmArgs '-Xmx512m'` applies the heap limit to the **application JVM**.
4. `--args="..."` passes arguments into `main(String[] args)`.

If you omit the `systemProperty ...` line in `build.gradle`, `-PdemoMode=fast` does **not automatically appear** as `demo.mode` inside the application. This is an explicit forwarding mechanism; the project property name and system property name can differ.

### Watch Out for `-D` and Gradle Memory

- `./gradlew -Ddemo.mode=fast bootRun`: `-D` sets a system property in **Gradle's** environment; do not assume `System.getProperty("demo.mode")` inside the application receives `fast`. Configure `bootRun.systemProperty(...)` if you want to pass it to the application.
- `org.gradle.jvmargs=-Xmx2g` in `gradle.properties`: configures the JVM memory of the **Gradle daemon**, not the application JVM launched by `bootRun`.
- `./gradlew bootRun --args="--server.port=9090"`: configures **application arguments**, not VM options.
- `./gradlew --stacktrace bootRun`: instructs Gradle to print a stack trace for build execution errors; this is not an option to print stack traces for application Java code.

Because `bootRun` spawns a separate Java process, distinguishing the two JVMs explains why increasing Gradle's heap does not necessarily fix an `OutOfMemoryError` inside the application, and vice versa.

## 4. What Does Spring Boot Receive from `main(String[] args)`?

A main source class of a Spring Boot project might look like this. This is **code inside a project that already has Spring Boot dependencies**, not the standalone JDK program from the earlier section:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class RuntimeParametersApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeParametersApplication.class, args);
    }

    @Bean
    ApplicationRunner printParameters(Environment environment) {
        return arguments -> {
            System.out.println("profiles="
                    + arguments.getOptionValues("spring.profiles.active"));
            System.out.println("port="
                    + environment.getProperty("server.port"));
            System.out.println("jvmMode="
                    + System.getProperty("demo.mode", "<unset>"));
            System.out.println("nonOptions="
                    + arguments.getNonOptionArgs());
        };
    }
}
~~~

After packaging an appropriate executable JAR and running:

~~~bash
java -Ddemo.mode=fast -jar build/libs/demo.jar --spring.profiles.active=dev --server.port=9090 input.csv
~~~

The lines **printed by the `ApplicationRunner` bean** (apart from normal Spring Boot startup logs) are:

~~~text
profiles=[dev]
port=9090
jvmMode=fast
nonOptions=[input.csv]
~~~

Differences between the APIs:

| API | Kind of Data Read | Example |
| --- | --- | --- |
| `main(String[] args)` | Raw argument array passed by the Java launcher to the application | `["--server.port=9090", "input.csv"]`, plus `--spring.profiles.active=dev` |
| `ApplicationArguments.getOptionValues("spring.profiles.active")` | Values of an argument in `--name=value` form | `[dev]` |
| `ApplicationArguments.getNonOptionArgs()` | Arguments not in `--...` option form | `[input.csv]` |
| `System.getProperty("demo.mode")` | JVM system property | `fast` if the application JVM received `-Ddemo.mode=fast` |
| `Environment.getProperty("server.port")` | Spring configuration value after aggregating sources | `9090` |

By default, Spring Boot adds `--key=value` arguments to `Environment` as a command-line property source. It does **not automatically convert** ordinary arguments like `input.csv` into named properties. If code calls `SpringApplication.setAddCommandLineProperties(false)`, adding command-line arguments to `Environment` is disabled, although the arguments can still be accessed via `ApplicationArguments`.

### Same Property Name, Different Storage

Consider the command:

~~~bash
java -Ddemo.mode=jvm -jar build/libs/demo.jar --demo.mode=cli
~~~

Under Spring Boot's default configuration:

- `System.getProperty("demo.mode")` returns `jvm` because it reads only JVM system properties.
- `Environment.getProperty("demo.mode")` returns `cli` because command-line properties have higher precedence than JVM system properties in the default configuration hierarchy.
- `ApplicationArguments.getOptionValues("demo.mode")` returns the list `[cli]` because it reads `--...` arguments.

Therefore, a property can share the same name yet return different values across APIs. Check the **right source** before concluding an option was ignored. OS environment variables (for example `SPRING_PROFILES_ACTIVE=dev`) are another configuration source; they do not automatically become elements of `main(String[] args)`.

## 5. Configuration in the IDE

IDEs such as IntelliJ IDEA or Eclipse typically offer corresponding fields:

| Run Configuration Field | What to Put There | Who Receives It |
| --- | --- | --- |
| **VM options / JVM arguments** | `-Xmx512m -Ddemo.mode=fast` | JVM running the application |
| **Program arguments / Application arguments** | `--spring.profiles.active=dev --server.port=9090 input.csv` | `main(String[] args)`, then Spring Boot |
| **Gradle tasks/arguments** (when running via Gradle) | `bootRun`, `-PdemoMode=fast`, `--offline` | Gradle; to forward to JVM/app, configure or use `--args` properly |
| **Environment variables** | `SPRING_PROFILES_ACTIVE=dev` | Process environment; Spring Boot can read via `Environment` |

When running the `main` class directly from the IDE, no `gradlew` command is processing parameters. When choosing to run via Gradle, the IDE may spawn a Gradle process and the `bootRun` task; verify which fields affect Gradle and which affect the application process.

## 6. Common Mistakes and How to Fix Them

| Confusing Usage | Why It Misses the Intent | Correct Usage |
| --- | --- | --- |
| `java -jar demo.jar -Xmx512m` intending to increase heap | `-Xmx512m` comes after the JAR, becoming an application argument | `java -Xmx512m -jar demo.jar` |
| `java -jar demo.jar -Ddemo.mode=fast` intending to set a system property | `-D...` comes after the JAR | `java -Ddemo.mode=fast -jar demo.jar` |
| `./gradlew -PdemoMode=fast bootRun` expecting `System.getProperty("demo.mode")` to get `fast` | `-P` only sets a Gradle project property | Use `bootRun.systemProperty('demo.mode', project.findProperty('demoMode'))` |
| Increasing `org.gradle.jvmargs` to increase application heap | That setting adjusts Gradle's JVM | Set `bootRun.jvmArgs '-Xmx...'` or VM options of `java`/IDE |
| Putting `--spring.profiles.active=dev` in VM options | This is a Spring Boot argument/property, not a Java launcher VM option | Put it in Program arguments or `bootRun --args` |
| Using `System.getProperty("server.port")` to check `--server.port=9090` | Command-line arguments go into `Environment` by default, not JVM system properties | Use `Environment.getProperty("server.port")` or `ApplicationArguments` |

## 7. Checklist When the Application Does Not Receive a Parameter

1. **Identify the launch method:** `java -jar`, running `main` in an IDE, or `./gradlew bootRun`? This determines whether a Gradle process sits in between.
2. **Identify the intended target:** do you need to change heap/JVM system properties, Gradle configuration, or a value Spring Boot reads in the application?
3. **Check position and forwarding:** place VM options before `-jar`/main class; with `bootRun`, use `jvmArgs`/`systemProperty` for the target JVM and `--args` for application arguments; `-P` only reaches the application when mapped.
4. **Read with the right API:** `System.getProperty` for JVM; `ApplicationArguments` for arguments; `Environment` for Spring properties; `project.findProperty` in the build script for Gradle.
5. **Check precedence on name collisions:** a `--key=value` value can win over `-Dkey=value` when read via `Environment`, while `System.getProperty` retains the JVM value.

**Practice exercise:** Before running, predict the two lines `LaunchArgsDemo` will print for (a) `java -Ddemo.mode=fast LaunchArgsDemo a.txt` and (b) `java LaunchArgsDemo -Ddemo.mode=fast a.txt`. Then run both to verify. In a Spring Boot project, compare `Environment.getProperty("demo.mode")` and `System.getProperty("demo.mode")` when passing both `-Ddemo.mode=jvm` and `--demo.mode=cli`. If you can explain the output by **right process, right position, right API**, you can clearly distinguish all three parameter categories.

### References

- Spring Boot — Running Your Application with Gradle: https://docs.spring.io/spring-boot/gradle-plugin/running.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Gradle — Build Environment Configuration: https://docs.gradle.org/current/userguide/build_environment.html
