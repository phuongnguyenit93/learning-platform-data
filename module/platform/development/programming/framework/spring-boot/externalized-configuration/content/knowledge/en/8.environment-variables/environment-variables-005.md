# Passing JVM Properties with -D and Placing Them Before -jar

When deploying a Spring Boot application as a JAR file, there are several ways to pass configuration into the Java process: writing it in `application.properties` or `application.yml`, setting environment variables, passing Spring Boot `--key=value` arguments, or passing **JVM system properties** via `-Dkey=value` parameters. Among these approaches, `-D` has a particularly important syntax rule: **it must be placed in the `java` command's options section, meaning before `-jar` and the JAR filename**.

This lesson explains `-D` syntax, its position in the startup command, the difference between JVM system properties and OS environment variables, how Spring Boot puts those values into `Environment`, override rules, how to pass it in shells/IDEs/Gradle/containers, and a troubleshooting workflow when `-D` does not take effect.

## 1. Visualizing the path of a JVM property

~~~text
Terminal / script / container runtime
      |
      |  java -Dserver.port=9091 -jar app.jar
      v
Java launcher
      |
      |  receives -Dserver.port=9091 before -jar
      v
JVM system properties
      |
      |  System.getProperty("server.port") -> "9091"
      v
Spring Boot prepares Environment
      |
      |  Java system properties is a PropertySource
      v
Environment.getProperty("server.port") -> "9091"
      |
      v
Spring Boot binds value to web server configuration
      |
      v
Application serves HTTP on port 9091
~~~

Two main points:

1. **`-D` is a Java launcher/JVM option.** Java must process it before handing control to the application.
2. **Spring Boot reads system properties as a configuration source.** When a key matches one consumed by Spring Boot or application code, its value can affect the application.

Not every arbitrary key triggers behavior on its own. For example, `-Dapp.feature.enabled=true` merely supplies a value; the application must have code or a bean reading `app.feature.enabled` for the corresponding feature to change.

## 2. Exact syntax of -D

Basic form:

~~~bash
java -Dproperty.name=value -jar path/to/application.jar
~~~

Spring Boot example:

~~~bash
java -Dserver.port=9091 -jar order-service.jar
~~~

The `-D` flag sits immediately before the key name, with `=` between the key and value, and no spaces around `=` within the same argument.

Several valid examples:

~~~bash
java -Dspring.profiles.active=dev -jar order-service.jar

java -Dserver.port=9091 -Dspring.application.name=order-service -jar order-service.jar

java -Dapp.client.connect-timeout=2s -Dapp.feature.audit-enabled=true -jar order-service.jar
~~~

Each `-Dkey=value` is a separate JVM option. They are usually placed consecutively before `-jar`, though they can also be interspersed with other valid JVM options as long as all of them are parsed by the Java launcher **before** selecting the application to run.

The command structure can be illustrated as:

~~~text
java [JVM options] -jar <jar-file> [application arguments]
     ^^^^^^^^^^^^^      ^^^^^^^^^^  ^^^^^^^^^^^^^^^^^^^^^
      -D position        JAR name   e.g., --server.port=9091
~~~

In standard usage, `-jar` tells Java to execute the application whose entry point is in the JAR. **Everything after the JAR name is passed as arguments to the program**, no longer treated as JVM options handled by the Java launcher as in the preceding section.

## 3. Position before -jar: right and wrong

### Right: Java receives -D before running the JAR

~~~bash
java -Dserver.port=9091 -jar order-service.jar
~~~

Java sets the system property `server.port` to the string `9091`. Spring Boot can read that property and configure the HTTP port, provided the application has an appropriate embedded web server and is not overridden by a higher-priority source.

### Wrong: placing -D after the JAR name

~~~bash
java -jar order-service.jar -Dserver.port=9091
~~~

Here, `-Dserver.port=9091` sits in the **application arguments** area. The Java launcher does not use it to set a JVM system property. `System.getProperty("server.port")` will not receive `9091` from this position just because the argument starts with `-D`.

By default, Spring Boot accepts option arguments in **double-dash** `--key=value` form. Therefore, if you want to set Spring Boot configuration **after the JAR**, use:

~~~bash
java -jar order-service.jar --server.port=9091
~~~

That is a **Spring Boot command-line property**, not a JVM system property. The following two commands can produce the same Spring Boot configuration value in simple scenarios, yet are handled by **two different mechanisms**:

~~~bash
# JVM system property: -D before -jar
java -Dserver.port=9091 -jar order-service.jar

# Spring Boot application argument: -- after the JAR name
java -jar order-service.jar --server.port=9091
~~~

If a framework or application code has custom logic that parses `-D...` arguments after the JAR, that is behavior specific to that program; do not rely on it as a general rule of Java or Spring Boot.

### Another easy mistake: placing -D right after -jar

~~~bash
java -jar -Dserver.port=9091 order-service.jar
~~~

In this form, the slot immediately after `-jar` is reserved for the **JAR filename**. This is not how `-D` is passed to the JVM; the command may fail because Java misinterprets the execution target. The clear approach is placing `-Dserver.port=9091` before `-jar`.

## 4. Multiple -D flags can be used in the same command

There is no need to combine multiple properties into one long string in properties syntax:

~~~bash
java \
  -Dspring.profiles.active=prod \
  -Dserver.port=9091 \
  -Dapp.client.connect-timeout=1500ms \
  -Dapp.feature.audit-enabled=true \
  -jar order-service.jar
~~~

The trailing `\` at the end of lines above is Unix-like shell line continuation, **not standalone Java syntax**. The equivalent single-line command is:

~~~bash
java -Dspring.profiles.active=prod -Dserver.port=9091 -Dapp.client.connect-timeout=1500ms -Dapp.feature.audit-enabled=true -jar order-service.jar
~~~

If using PowerShell, you can write it on one line as shown above. When breaking lines in PowerShell, the line-continuation character is PowerShell's backtick, not Bash's `\`. Windows Command Prompt uses yet another line-continuation syntax. Therefore, single-line examples are easier to copy and less shell-dependent.

Properties can serve different purposes:

| System property | Who consumes it | Illustration |
| --- | --- | --- |
| `spring.profiles.active` | Spring Boot profile handling | `dev`, `prod` |
| `server.port` | Spring Boot web server configuration | `9091` |
| `spring.application.name` | Spring Boot/application metadata | `order-service` |
| `app.client.connect-timeout` | Application's own configuration bean | `1500ms` |
| `user.timezone` | Java/JDK components related to default time zone | `UTC` |

Not every property starting with `java.`, `user.`, or `app.` is handled the same way by Spring Boot. JVM/JDK keys can affect the runtime even when Spring Boot code does not read them directly.

## 5. -D and environment variables are not the same mechanism

In application configuration contexts, three sources are often mentioned together:

1. **OS environment variables**: names and values inherited by the process from its execution environment.
2. **JVM system properties**: key/value pairs belonging to `System.getProperties()` of the Java process, typically set with `-D`.
3. **Spring Boot application arguments**: `--key=value` parameters passed into `main(String[] args)` and read by Spring Boot.

Example all aiming to set port 9091:

~~~bash
# A. Linux/macOS: environment variable
SERVER_PORT=9091 java -jar order-service.jar

# B. JVM system property
java -Dserver.port=9091 -jar order-service.jar

# C. Spring Boot command-line argument
java -jar order-service.jar --server.port=9091
~~~

All three approaches can make a Spring Boot application use port 9091, but where the value is stored and how it is read differ.

| Aspect | Environment variable | JVM -D | Spring Boot -- |
| --- | --- | --- | --- |
| Example | `SERVER_PORT=9091` | `-Dserver.port=9091` | `--server.port=9091` |
| Received first by | Process environment | Java launcher/JVM | main method/application |
| Plain Java reads with | `System.getenv("SERVER_PORT")` | `System.getProperty("server.port")` | `args[]` or custom parser |
| Spring Boot reads in Environment | Yes, as system environment | Yes, as Java system properties | Yes, if command-line properties are enabled |
| Position relative to -jar | Outside Java command or supplied by shell | Before `-jar` | After JAR name |

Understand this clearly: **`System.getenv("SERVER_PORT")` does not read the value created by `-Dserver.port=9091`**. Conversely, **`System.getProperty("server.port")` does not automatically read `SERVER_PORT`**. Spring Boot provides `Environment` to unify lookups across sources according to its mechanism.

Environment variables named like `SERVER_PORT` are mapped by Spring Boot according to environment variable property naming rules. For complex configuration groups, prefer canonical `kebab-case` key names in properties and follow Spring Boot's documented environment variable naming conventions.

## 6. What is a Java system property?

Every JVM process has a set of system properties represented by `java.lang.System`. You can read a key with:

~~~java
String port = System.getProperty("server.port");
System.out.println(port);
~~~

In a plain Java program without Spring, try this example:

~~~java
public class SystemPropertyDemo {
    public static void main(String[] args) {
        System.out.println("server.port = "
            + System.getProperty("server.port"));
        System.out.println("feature = "
            + System.getProperty("app.feature.enabled"));
    }
}
~~~

Compile:

~~~bash
javac SystemPropertyDemo.java
~~~

Run:

~~~bash
java -Dserver.port=9091 -Dapp.feature.enabled=true SystemPropertyDemo
~~~

Illustrative output:

~~~text
server.port = 9091
feature = true
~~~

When running by class name instead of JAR, `-D` must likewise stay in the Java options section **before the main class name**:

~~~bash
java -Dserver.port=9091 -cp build/classes/java/main com.example.demo.Main
~~~

If you place `-Dserver.port=9091` after `com.example.demo.Main`, it becomes a program argument, not a Java launcher option. Thus the general rule is **`-D` must come before the run target**: main class name, module name, or `-jar` depending on the `java` command form used.

### How does it differ from Spring Boot configuration values?

`System.getProperty("server.port")` reads **JVM system properties** directly. It does not go through all Spring Boot configuration sources. Meanwhile, `Environment.getProperty("server.port")` reads the effective value according to the `PropertySource` order established by Spring.

Consequently, when a key is declared in `application.yml` without a JVM `-D` flag, you can observe:

~~~text
System.getProperty("server.port")      -> null
Environment.getProperty("server.port") -> "8080"
~~~

That is normal behavior: Spring Boot loads YAML files into `Environment`, without any requirement to automatically copy every YAML key into `System.getProperties()`.

Conversely, when passing `-Dserver.port=9091`, `System.getProperty("server.port")` may return `9091`, whereas `Environment` may return a different value if a higher-priority property source exists, such as Spring Boot argument `--server.port=8085`.

## 7. Spring Boot example reading properties from -D

Suppose `src/main/resources/application.properties` has:

~~~properties
spring.application.name=order-service
server.port=8080

app.client.connect-timeout=3s
app.feature.audit-enabled=false
~~~

Create a component that reads effective configuration:

~~~java
import java.time.Duration;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RuntimeSettingsReader {
    private final Environment environment;

    public RuntimeSettingsReader(Environment environment) {
        this.environment = environment;
    }

    public Duration clientTimeout() {
        return environment.getProperty(
            "app.client.connect-timeout", Duration.class);
    }

    public boolean auditEnabled() {
        return Boolean.TRUE.equals(environment.getProperty(
            "app.feature.audit-enabled", Boolean.class, false));
    }
}
~~~

Run the JAR:

~~~bash
java -Dserver.port=9091 -Dapp.client.connect-timeout=1s -Dapp.feature.audit-enabled=true -jar order-service.jar
~~~

Provided no higher-priority source overrides them, the keys Spring Boot sees are:

| Key | application.properties | JVM -D | Effective value |
| --- | --- | --- | --- |
| `server.port` | `8080` | `9091` | `9091` |
| `app.client.connect-timeout` | `3s` | `1s` | `1s` |
| `app.feature.audit-enabled` | `false` | `true` | `true` |

Note: `-Dapp.feature.audit-enabled=true` **only has business effect when the application consumes this property**. For `server.port`, Spring Boot's web server has built-in handling in appropriate web application types. For `app.*` keys, you must define the consumer yourself.

## 8. Reading a group of -D properties with @ConfigurationProperties

For a group of keys sharing a prefix, a typed bean avoids scattering string names throughout the code:

~~~properties
# application.properties
app.client.base-url=https://api.example.test
app.client.connect-timeout=3s
app.client.max-retries=2
~~~

Declaration:

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
    URI baseUrl,
    Duration connectTimeout,
    int maxRetries
) {}
~~~

Register the configuration bean in the application:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderServiceApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderServiceApplication.class, args);
    }
}
~~~

Run:

~~~bash
java -Dapp.client.base-url=https://internal.example.test -Dapp.client.connect-timeout=500ms -Dapp.client.max-retries=5 -jar order-service.jar
~~~

The Binder can map canonical keys like `base-url`, `connect-timeout`, and `max-retries` to `baseUrl`, `connectTimeout`, and `maxRetries`. Values like `500ms` or `5` are converted into `Duration` and `int` accordingly. The `ClientProperties` object represents the **effective values**, not merely the data from the default file.

The `-D` syntax itself carries no `Duration` or `boolean` type. Values enter system properties as strings; Spring Boot performs type conversion when binding them to Java properties.

## 9. -Dspring.profiles.active: selecting profiles before loading profile-specific configuration

A very common use case is passing the active profile at startup time:

~~~bash
java -Dspring.profiles.active=dev -jar order-service.jar
~~~

Spring Boot then knows to consider the `dev` profile. If `application-dev.yml` or Config Data documents activated by `dev` exist, they can be loaded according to the configuration mechanism.

Base file example:

~~~yaml
# application.yml
app:
  client:
    base-url: https://api.example.test
    connect-timeout: 3s
~~~

Profile-specific file:

~~~yaml
# application-dev.yml
app:
  client:
    base-url: http://localhost:8090
    connect-timeout: 500ms
~~~

Run:

~~~bash
java -Dspring.profiles.active=dev -jar order-service.jar
~~~

If no higher-priority source overrides the client keys, the application uses the values for `dev`. The JVM argument `-Dspring.profiles.active=dev` is a valid way to determine the profile from a **startup source**, avoiding placing `spring.profiles.active` inside profile-specific documents themselves.

An equivalent in intent for Spring Boot is:

~~~bash
java -jar order-service.jar --spring.profiles.active=dev
~~~

However, the second approach is a **Spring Boot application argument**. If the application needs to read `System.getProperty("spring.profiles.active")` directly, passing `--spring.profiles.active=dev` alone does not guarantee the JVM system property has a value. For most Spring Boot code, using `Environment.getActiveProfiles()` or bound configuration is more appropriate.

## 10. Precedence rules when multiple sources set the same key

Suppose `application.yml` has:

~~~yaml
server:
  port: 8080
~~~

The process has an environment variable:

~~~bash
SERVER_PORT=8081
~~~

And is launched with:

~~~bash
java -Dserver.port=8082 -jar order-service.jar --server.port=8083
~~~

In a normal Spring Boot run, without special property source ordering customization, the precedence chain makes the effective value **8083**:

| Source | `server.port` value | Role in example |
| --- | --- | --- |
| `application.yml` | `8080` | Application default value |
| Environment variable `SERVER_PORT` | `8081` | Overrides file configuration |
| Java system property `-Dserver.port` | `8082` | Overrides environment variable |
| Spring Boot argument `--server.port` | `8083` | Overrides the sources above |

This table illustrates common sources, not the complete Spring Boot precedence list. Test properties, `SPRING_APPLICATION_JSON`, DevTools, imported configs, and other mechanisms can participate where applicable.

Key takeaway: **`-D` has higher priority than regular configuration files, yet is not always the final source that beats every value**. If `--key=value` arguments carry higher priority, `Environment` can return a different value from `System.getProperty(key)`.

## 11. Spaces and quotes when a value contains multiple words

`-Dkey=value` must be passed by the shell as **a single argument** to the Java launcher. If the value contains spaces, quote the whole option:

~~~bash
java "-Dapp.display-name=Order Service" -jar order-service.jar
~~~

This is straightforward and works in common shells. In Bash, single quotes can be used to protect contents from shell expansions:

~~~bash
java '-Dapp.display-name=Order Service' -jar order-service.jar
~~~

In PowerShell, the quoted form also expresses the intent of passing a value containing whitespace:

~~~powershell
java '-Dapp.display-name=Order Service' -jar order-service.jar
~~~

Java receives key `app.display-name` and value `Order Service` after the shell processes quoting according to its rules.

Do not insert spaces around `=` in the basic form:

~~~bash
# Not a single valid JVM option
java -Dserver.port = 9091 -jar order-service.jar
~~~

The shell may split it into multiple arguments, causing Java to receive an unexpected option or misinterpret the application target.

### Be careful with special characters

Characters such as `$`, `&`, `;`, `*`, quotes, backslashes, and many others can carry special meaning in the shell. The following command may not pass the value you expect if unquoted:

~~~bash
java -Dapp.url=https://example.test/search?x=1&y=2 -jar order-service.jar
~~~

In some shells, `&` acts as a process-control operator. A safer way is quoting the argument using your current shell's syntax:

~~~bash
java '-Dapp.url=https://example.test/search?x=1&y=2' -jar order-service.jar
~~~

Choose quoting rules appropriate for Bash, PowerShell, CMD, or your actual deployment tool. In container YAML configurations, elements of command/args arrays are usually passed directly as arguments without going through a shell, unless you explicitly invoke `sh -c` or a similar wrapper.

## 12. Passing via Bash and PowerShell scripts

### Bash: setting variables in a script and passing -D

~~~bash
#!/usr/bin/env bash

APP_PORT=9091
APP_PROFILE=dev

java "-Dserver.port=$APP_PORT" "-Dspring.profiles.active=$APP_PROFILE" -jar order-service.jar
~~~

The shell expands `APP_PORT` and `APP_PROFILE` before invoking Java. The Java launcher only sees arguments such as `-Dserver.port=9091` and `-Dspring.profiles.active=dev`. These are still **system properties**, even though their original values were stored in shell variables.

If you want to use **environment variables directly**, you can export `SERVER_PORT` or `SPRING_PROFILES_ACTIVE` and run Java without `-D`. These are two different paths, both of which Spring Boot can read.

### PowerShell: creating variables and invoking Java

~~~powershell
$appPort = "9091"
$appProfile = "dev"

java "-Dserver.port=$appPort" "-Dspring.profiles.active=$appProfile" -jar order-service.jar
~~~

Strings inside double quotes undergo variable interpolation in PowerShell. After interpolation, Java receives each `-Dkey=value` as a single argument. If you need to pass literals containing special characters in PowerShell, adjust quoting accordingly.

### Windows CMD: single-line example

~~~bat
java "-Dserver.port=9091" "-Dspring.profiles.active=dev" -jar order-service.jar
~~~

CMD has different quoting and environment variable rules from Bash and PowerShell. When running inside a batch file, variables follow `%NAME%` syntax; do not copy `$NAME` verbatim from Bash to CMD.

## 13. Passing -D in an IDE: JVM arguments differ from program arguments

Many IDEs provide two separate boxes when configuring Java or Spring Boot run configurations:

- **VM options / JVM arguments:** parameters sent to the Java launcher/JVM.
- **Program arguments / application arguments:** parameters sent to `main(String[] args)`.

If you want `-Dserver.port=9091`, put it in **VM options**, for example:

~~~text
-Dserver.port=9091
-Dspring.profiles.active=dev
~~~

If you want Spring Boot command-line properties `--server.port=9091`, put them in **Program arguments**:

~~~text
--server.port=9091
--spring.profiles.active=dev
~~~

Putting `-D...` inside Program arguments is equivalent to putting it after the JAR name: the JVM will not turn it into a system property automatically.

An IDE run configuration example can be represented as:

| Configuration area | Value |
| --- | --- |
| Main class | `com.example.orders.OrderServiceApplication` |
| VM options | `-Dserver.port=9091 -Dspring.profiles.active=dev` |
| Program arguments | `--app.client.connect-timeout=500ms` |

In this case, port and profile come from JVM system properties, while timeout comes from Spring Boot application arguments. Effective values still obey configuration precedence if the same key is defined in multiple sources.

## 14. Passing -D when running with Gradle bootRun

When running a JAR directly with `java -jar`, parameter order is easy to observe. With the Spring Boot Gradle plugin's `bootRun`, **Gradle is a process that launches a separate application JVM** per task configuration, so you must distinguish Gradle's JVM options from the application's JVM options.

Example:

~~~bash
./gradlew -Dserver.port=9091 bootRun
~~~

This line sets the system property `server.port` on the JVM running Gradle. **Do not assume** that property is automatically forwarded to the application JVM forked by `bootRun`. The result depends on whether the task/plugin is configured to forward system properties.

A clearer way if you want to pass a **Spring Boot application argument** through bootRun is:

~~~bash
./gradlew bootRun --args='--server.port=9091'
~~~

The command above passes program argument `--server.port=9091` to Spring Boot, not a JVM `-D` option.

If you genuinely need to set **JVM system properties** for the JVM launched by `bootRun`, you can configure the task's JVM arguments in Gradle Groovy DSL:

~~~groovy
tasks.named('bootRun') {
    jvmArgs '-Dserver.port=9091'
    jvmArgs '-Dspring.profiles.active=dev'
}
~~~

When Gradle runs the `bootRun` task, the `-D` options are passed as JVM arguments to the application. This is an illustrative example of configuring a `JavaExec`/`BootRun` task; a project's actual Gradle setup may follow its own conventions, so place the DSL block in the right project/module owning the task.

Do not confuse Gradle's `--args='--...'` with Gradle's `-D...`. One passes arguments to the program, while the other sets JVM properties for the Gradle process unless forwarded by the task.

## 15. Using -D with Docker or containers

For a JAR running in Docker, JVM options can be placed directly in the array-form `ENTRYPOINT`:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app

COPY build/libs/order-service.jar /app/order-service.jar

ENTRYPOINT ["java", "-Dserver.port=9091", "-Dspring.profiles.active=prod", "-jar", "/app/order-service.jar"]
~~~

The exec/array form passes each element as a separate argument. `-Dserver.port=9091` and `-Dspring.profiles.active=prod` appear **before `-jar`**, so the Java launcher processes them.

If you accidentally write:

~~~dockerfile
ENTRYPOINT ["java", "-jar", "/app/order-service.jar", "-Dserver.port=9091"]
~~~

then `-Dserver.port=9091` is passed as an application argument; it is not a system property set by the Java launcher.

For containers deployed across multiple environments, hardcoding profiles or ports inside the image can make the same image harder to reuse. An alternative is supplying the environment at runtime:

~~~bash
docker run --rm -e SERVER_PORT=9091 -e SPRING_PROFILES_ACTIVE=prod order-service:latest
~~~

Spring Boot receives these environment variables through the system environment if the container/image launches the application properly. This mechanism is separate from JVM `-D`; there is no need to add `-D` just for environment variables to take effect.

In Kubernetes, `command`/`args` can specify arguments for the container runtime. If the list starts with `java`, ensure `-D...` elements appear before `-jar`. If you only specify `args` while the image already defines an `ENTRYPOINT`, check the exact final command constructed before concluding where `-D` ends up.

## 16. JAVA_TOOL_OPTIONS, JDK_JAVA_OPTIONS, and JAVA_OPTS

You may encounter variable names like `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS`, or `JAVA_OPTS` in deployment documentation. They **do not mean the same thing**.

- **`JAVA_TOOL_OPTIONS`:** certain JVM options, including `-D` system properties, can be picked up by the JVM from this environment variable. Scope and restrictions depend on how the JVM is initialized.
- **`JDK_JAVA_OPTIONS`:** on supported JDK versions, the Java launcher can accept additional options from this environment variable, with restrictions on options that select the application target.
- **`JAVA_OPTS`:** this is **not** a mechanism automatically read by the `java` command itself under any universal standard. Many scripts, images, or deployment tools follow a convention of reading this variable name, but it only takes effect if the system's entrypoint/script explicitly interpolates its contents into the Java command.

For example, an operator might set:

~~~bash
export JAVA_TOOL_OPTIONS='-Duser.timezone=UTC'
java -jar order-service.jar
~~~

In supported JVM environments, `user.timezone` can be injected into the JVM without writing it directly on the command line. However, for a lesson focused on **mastering `-D` placement before `-jar`**, the explicit form below is easier to observe and debug:

~~~bash
java -Duser.timezone=UTC -jar order-service.jar
~~~

Do not pass secret variable names or password values via a mechanism just because it supports `-D`. Values in command lines, scripts, container configs, or logs can be exposed via process inspection tools or command history. Use proper secrets management systems and access controls in real deployments.

## 17. Can system properties be changed after the JVM starts?

System properties can be read and modified via Java APIs:

~~~java
System.setProperty("app.feature.enabled", "true");
String value = System.getProperty("app.feature.enabled");
~~~

This **does not mean Spring Boot will automatically re-initialize already-bound configuration beans**. A `@ConfigurationProperties` bean is normally bound during initialization, and profile-based Config Data loading happens during startup. If you change a system property after the application is running, `System.getProperty` calls or a consumer reading `Environment` freshly might observe the change under appropriate conditions, but previously applied bean or configuration decisions are not automatically recomputed.

Also distinguish system properties within **the same JVM process**. If two Java applications run in two independent processes, each process has its own `System.getProperties()`. `-D` configuration on process A does not directly override process B.

For JDK properties read very early, changing them after startup may not alter already-initialized behavior. Therefore, treat `-D` as intentional startup configuration, not as a dynamic update mechanism for the whole application.

## 18. Common mistakes and fixes

### Mistake 1 — Placing -D after the JAR

~~~bash
# Wrong if you want a JVM system property
java -jar order-service.jar -Dserver.port=9091
~~~

**Fix:**

~~~bash
java -Dserver.port=9091 -jar order-service.jar
~~~

If the goal is simply supplying a property to Spring Boot, you can choose:

~~~bash
java -jar order-service.jar --server.port=9091
~~~

### Mistake 2 — Space after -D

~~~bash
# Invalid option form
java -D server.port=9091 -jar order-service.jar
~~~

**Fix:** write `-Dserver.port=9091` without spaces, rather than splitting it into two arguments.

### Mistake 3 — Confusing system property keys and environment variables

~~~bash
java -DSERVER_PORT=9091 -jar order-service.jar
~~~

This command creates a **system property named `SERVER_PORT`**, not an environment variable `SERVER_PORT`. Do not assume it equals `-Dserver.port=9091` just because the two spellings look similar. When passing system properties to Spring Boot, prefer canonical names:

~~~bash
java -Dserver.port=9091 -jar order-service.jar
~~~

When using environment variables, name variables according to system environment rules:

~~~bash
SERVER_PORT=9091 java -jar order-service.jar
~~~

### Mistake 4 — Using -D with Gradle and assuming bootRun always receives it

~~~bash
./gradlew -Dspring.profiles.active=dev bootRun
~~~

This line configures the JVM used by Gradle; it does not prove the JVM running Spring Boot receives the property. **Fix:** pass `--spring.profiles.active=dev` via `bootRun --args` or configure `jvmArgs` on `bootRun`.

### Mistake 5 — Putting -D into IDE Program arguments

VM options and Program arguments are two different fields. **Fix:** move `-D...` to VM options, or switch to `--key=value` in Program arguments if the goal is a Spring Boot property.

### Mistake 6 — Not quoting values with spaces or shell special characters

~~~bash
java -Dapp.display-name=Order Service -jar order-service.jar
~~~

The shell may split `Service` into a separate argument, causing the command to be misinterpreted. **Fix:**

~~~bash
java "-Dapp.display-name=Order Service" -jar order-service.jar
~~~

### Mistake 7 — Overridden by another source

~~~bash
java -Dserver.port=9091 -jar order-service.jar --server.port=9092
~~~

Even though `System.getProperty("server.port")` may return `9091`, Spring Boot `Environment` in this example normally uses `9092` because the command-line property takes higher precedence. **Fix:** inspect all sources and precedence rules instead of concluding `-D` was not read by Java.

### Mistake 8 — Passing an application key without a consumer

~~~bash
java -Dapp.feature.special-mode=true -jar order-service.jar
~~~

Nothing automatically makes a `special-mode` feature appear if the application has no code, condition, or bean reading that key. **Fix:** identify the consumer and its corresponding binding mechanism.

### Mistake 9 — Passing a value of the wrong type

~~~bash
java -Dserver.port=not-a-port -jar order-service.jar
~~~

The command may be valid Java syntax, yet Spring Boot cannot convert that string into a valid network port. **Fix:** use a value with the right type and range, such as a valid TCP port number.

## 19. Self-verification with System.getProperty and Environment

An exercise to tell whether an issue lies in the Java launcher or Spring Boot.

Add a bean in a test application:

~~~java
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration
public class PropertyProbeConfiguration {

    @Bean
    CommandLineRunner printPortSources(Environment environment) {
        return args -> {
            System.out.println("JVM system property server.port = "
                + System.getProperty("server.port"));
            System.out.println("Spring Environment server.port = "
                + environment.getProperty("server.port"));
        };
    }
}
~~~

Only probe non-sensitive keys. Do not print all `System.getProperties()` or all `Environment` properties into production logs: they can contain tokens, paths, system details, or secret data.

### Experiment A — file value only

~~~properties
# application.properties
server.port=8080
~~~

Run:

~~~bash
java -jar order-service.jar
~~~

Output may be:

~~~text
JVM system property server.port = null
Spring Environment server.port = 8080
~~~

This shows Spring Boot reads `server.port` from the file even though the JVM has no system property with that name.

### Experiment B — -D in the right position

~~~bash
java -Dserver.port=9091 -jar order-service.jar
~~~

Illustrative output:

~~~text
JVM system property server.port = 9091
Spring Environment server.port = 9091
~~~

### Experiment C — -D placed after the JAR

~~~bash
java -jar order-service.jar -Dserver.port=9091
~~~

If `application.properties` still contains `server.port=8080`, illustrative output is:

~~~text
JVM system property server.port = null
Spring Environment server.port = 8080
~~~

The output shows the Java launcher does not accept `-D` in the application arguments area. The actual value still depends on any other sources present in the process.

### Experiment D — two competing sources

~~~bash
java -Dserver.port=9091 -jar order-service.jar --server.port=9092
~~~

Illustrative output:

~~~text
JVM system property server.port = 9091
Spring Environment server.port = 9092
~~~

Table A–D lets you pinpoint exactly where a difference originates: whether the JVM received `-D`, whether Spring Boot read another source, and how precedence determined the final value.

## 20. Self-practice questions

**Question 1.** Which command is correct for the JVM to receive system property `spring.profiles.active=prod`?

~~~bash
# A
java -jar app.jar -Dspring.profiles.active=prod

# B
java -Dspring.profiles.active=prod -jar app.jar
~~~

**Answer:** B. `-D` is before `-jar`.

**Question 2.** Do the following two commands create the same type of configuration source?

~~~bash
java -Dserver.port=9091 -jar app.jar
java -jar app.jar --server.port=9091
~~~

**Answer:** No. The first creates a JVM system property; the second creates a Spring Boot application argument. In a standard Spring Boot application, both can result in port 9091 if no overriding source exists, yet their sources differ.

**Question 3.** Why is this command not equivalent to passing environment variable `SERVER_PORT`?

~~~bash
java -DSERVER_PORT=9091 -jar app.jar
~~~

**Answer:** It sets a system property named `SERVER_PORT`. Environment variables belong to `System.getenv` and are supplied by the OS/process mechanism.

**Question 4.** `application.properties` contains `app.client.connect-timeout=3s`; startup command:

~~~bash
java -Dapp.client.connect-timeout=500ms -jar app.jar
~~~

Assuming no higher-priority source, what does `Environment.getProperty("app.client.connect-timeout")` return?

**Answer:** `500ms`. Spring Boot reads the system property and places that source higher than normal configuration files.

**Question 5.** If `--app.client.connect-timeout=1s` is appended to the end of the command above, what is the expected effective value?

**Answer:** `1s` in a default Spring Boot setup, because command-line properties have higher priority than JVM system properties.

**Question 6.** Why is `./gradlew -Dserver.port=9091 bootRun` not proof that Spring Boot listens on port 9091?

**Answer:** `-D` may be targeting Gradle's JVM; the `bootRun` task runs the application in a separate JVM. You must pass JVM args to `bootRun` or use `bootRun --args='--server.port=9091'`.

**Question 7.** With plain Java run by class name, is this syntax correct?

~~~bash
java -Dapp.mode=test -cp out com.example.Main
~~~

**Answer:** Correct; `-D` stands before the main class name, while `-cp out` supplies the classpath.

**Question 8.** Which call reads a JVM system property directly?

~~~java
System.getProperty("server.port");
System.getenv("SERVER_PORT");
~~~

**Answer:** The first call. The second call reads an OS environment variable.

## 21. Quick reference table

| Need | Pattern |
| --- | --- |
| Pass a JVM property when running a JAR | `java -Dkey=value -jar app.jar` |
| Pass multiple system properties | `java -Da=1 -Db=2 -jar app.jar` |
| Select a Spring profile via JVM | `java -Dspring.profiles.active=prod -jar app.jar` |
| Set port via JVM | `java -Dserver.port=9091 -jar app.jar` |
| Pass Spring Boot argument after JAR | `java -jar app.jar --server.port=9091` |
| Read JVM property in Java | `System.getProperty("server.port")` |
| Read environment variable in Java | `System.getenv("SERVER_PORT")` |
| Read effective value in Spring | `environment.getProperty("server.port")` |
| Pass via IDE VM options | `-Dserver.port=9091` |
| Pass via IDE program arguments | `--server.port=9091` |
| Pass argument to bootRun | `./gradlew bootRun --args='--server.port=9091'` |
| Pass -D to bootRun JVM | Configure `jvmArgs '-Dserver.port=9091'` in the task |
| Set -D in Docker ENTRYPOINT | `["java", "-Dserver.port=9091", "-jar", "/app/app.jar"]` |

Rule you can apply immediately when reading a run command:

> **To have the Java launcher set a system property, write `java -Dkey=value -jar app.jar`. To have Spring Boot receive an application argument, write `java -jar app.jar --key=value`. To verify, compare `System.getProperty(key)` with `Environment.getProperty(key)` and examine source precedence.**

When you clearly separate **environment variables**, **JVM system properties**, and **Spring Boot command-line properties**, you can choose the right configuration channel, put parameters in the right position, and pinpoint the root cause if the application fails to pick up expected values.
