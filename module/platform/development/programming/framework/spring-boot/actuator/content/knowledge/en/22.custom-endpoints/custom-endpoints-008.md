# The Role of Parameter Name Metadata When Compiling with -parameters

In a custom Actuator endpoint, parameter names can become the input names that operations tools must send. With the method `inspect(String cacheName, int limit)`, Actuator needs to know which input is `cacheName` and which input is `limit`, before converting and passing values into the right positions.

This lesson explains why Java code that compiles cleanly can still prevent Actuator from initializing an operation, how to enable `-parameters`, and how to verify it on the `.class` file actually being run. Examples use Java 17 or higher; the illustrative application uses Spring Boot 3.3 with JDK 21.

## 1. Names in Source Code vs. Names Present at Runtime

Consider the following declaration; this is an illustrative method, not a standalone program:

```java
public String inspect(String cacheName, int limit) {
    return cacheName + ":" + limit;
}
```

There are three different pieces of information:

| Information | In the Example | Purpose |
| --- | --- | --- |
| Parameter position | First, second | Determines argument passing order |
| Parameter type | `String`, `int` | Type checking and input conversion |
| Parameter name | `cacheName`, `limit` | Matches named inputs to the corresponding parameter |

A direct Java call like `inspect("inventory", 5)` passes arguments by position. The JVM does not need the name `cacheName` to execute that call. Therefore, compiling cleanly and succeeding on a direct call does not prove the framework can read parameter names.

`-parameters` is an option of the **`javac` compiler**. It instructs `javac` to store formal parameter names of methods and constructors in the `.class` file metadata so Java Reflection can read them back. It is not an HTTP configuration option or an endpoint-enabling flag. The [JDK 21 javac documentation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) describes the purpose of this option.

At runtime, the APIs to note are:

- `Method.getParameters()`: retrieves objects describing the parameters.
- `Parameter.getName()`: retrieves the name read from the class or a synthesized name.
- `Parameter.isNamePresent()`: checks whether the class provides real names.

When real names are absent, `getName()` can still return strings like `arg0`, `arg1`. Therefore, merely checking that the name is non-null is not enough. You must check `isNamePresent()`. According to the [Java 21 Parameter API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html), synthesized names have the form `argN`; name presence is determined from the `MethodParameters` attribute.

## 2. Why Does Actuator Need This Information?

An endpoint with parameters is the bridge between two calling conventions: the outside supplies named data, while the Java method receives arguments by position. For example, the practice app below receives the request:

```http
GET /actuator/nameprobe?cacheName=inventory&limit=5
```

The flow to understand is:

```text
Names in source code: cacheName, limit
        |
        | javac -parameters
        v
Metadata in NameProbeEndpoint.class
        |
        | Actuator reads method descriptor
        v
Bind cacheName -> first parameter
Bind limit     -> second parameter
        |
        | convert string "5" to int
        v
inspect("inventory", 5)
```

**Finding names** and **converting types** are related but distinct tasks. Knowing the second parameter has type `int` does not tell Actuator to take its value from the `limit` key.

With `@ReadOperation`, the example uses query parameters. With `@WriteOperation`, top-level JSON properties can also be mapped by parameter name. `@Selector` marks path parameters, but it does not eliminate the requirement to retain name metadata. This input mechanism belongs to the endpoint model shared across HTTP/JMX; you should not copy Spring MVC controller parameter declarations wholesale into it. See [Receiving Input in the Actuator 3.3 documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.receiving-input).

**When metadata is missing, do not infer that sending `arg0` will work.** In Spring Boot 3.3, extracting parameter names for a Java operation can fail immediately during endpoint discovery. In that case, the application may fail to start before serving any requests. This differs from an already active endpoint where a caller forgets to send a parameter.

## 3. Standalone Java Experiment: With Flag, Without Flag, and With Only -g

Save the following program into the exact file `ParameterNamesDemo.java`. The program needs no Spring or external libraries:

```java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterNamesDemo {
    public static String inspect(String cacheName, int limit) {
        return cacheName + ":" + limit;
    }

    public static void main(String[] args) throws Exception {
        Method method = ParameterNamesDemo.class.getDeclaredMethod(
                "inspect", String.class, int.class);
        for (Parameter parameter : method.getParameters()) {
            System.out.printf("%s / present=%s%n",
                    parameter.getName(), parameter.isNamePresent());
        }
        System.out.println(inspect("inventory", 5));
    }
}
```

### 3.1. Compiling Without -parameters

Run from the directory containing the source file:

```shell
javac -encoding UTF-8 -d out-without ParameterNamesDemo.java
java -cp out-without ParameterNamesDemo
```

Stdout:

```text
arg0 / present=false
arg1 / present=false
inventory:5
```

The line `inventory:5` proves direct Java invocation still runs. The first two lines prove Reflection lacks the source names of the two parameters on the `inspect` method.

### 3.2. Compiling With -parameters

```shell
javac -encoding UTF-8 -parameters -d out-with ParameterNamesDemo.java
java -cp out-with ParameterNamesDemo
```

Stdout:

```text
cacheName / present=true
limit / present=true
inventory:5
```

The source code and business output did not change. What changed is the metadata enabling other components to read parameter names.

### 3.3. Enabling Only Debug Info with -g

```shell
javac -encoding UTF-8 -g -d out-debug ParameterNamesDemo.java
java -cp out-debug ParameterNamesDemo
```

Example stdout:

```text
arg0 / present=false
arg1 / present=false
inventory:5
```

`-g` can generate debugging information, including local variable information. That does not make Java Reflection treat the names of the two ordinary parameters in the example as present via `MethodParameters`.

Since Spring Framework 6.1, `LocalVariableTableParameterNameDiscoverer` has been removed. The framework no longer uses that mechanism to infer parameter names from local variable tables. Therefore, with the Spring Boot 3.3 line using Spring Framework 6.1, do not rely on `-g` to replace `-parameters`. The [Spring Framework 6.1 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes#parameter-name-retention) state this change clearly.

The commands write output to separate directories to avoid accidentally rerunning an old `.class` file. When changing compiler flags in a real project, also recompile the exact classes to be tested.

## 4. Practicing with an Actuator Endpoint

### 4.1. Preparing the Sample Application

This is a standalone practice project. The example pins Spring Boot `3.3.0` to reproduce behavior in the 3.3 line; this version number is not a claim about the latest release. Use JDK 21 and Gradle 8.x.

Create the structure:

```text
parameter-endpoint-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── ParameterEndpointApplication.java
    │   └── NameProbeEndpoint.java
    └── resources/
        └── application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'parameter-endpoint-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

When combined with the Java plugin, the Spring Boot plugin automatically adds `-parameters` to `JavaCompile` tasks; thus the sample project does not need to add the flag manually. The BOM in the example manages dependency versions. The [Gradle plugin 3.3 documentation](https://docs.spring.io/spring-boot/3.3/gradle-plugin/reacting.html#reacting-to-other-plugins.java) describes this automatic compiler configuration.

`src/main/java/demo/ParameterEndpointApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ParameterEndpointApplication {
    public static void main(String[] args) {
        SpringApplication.run(ParameterEndpointApplication.class, args);
    }

    @Bean
    NameProbeEndpoint nameProbeEndpoint() {
        return new NameProbeEndpoint();
    }
}
```

`src/main/java/demo/NameProbeEndpoint.java`:

```java
package demo;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;

@Endpoint(id = "nameprobe")
public class NameProbeEndpoint {
    @ReadOperation
    public Snapshot inspect(String cacheName, int limit) {
        return new Snapshot(cacheName, limit);
    }

    public record Snapshot(String cacheName, int limit) {
    }
}
```

The endpoint instance is registered via `@Bean`. `inspect` simply echoes the inputs to observe mapping; it does not access a real cache. `Snapshot` is a return type, not an object used to group input parameters.

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,nameprobe
```

This configuration serves local experimentation. The example does not add Spring Security; if applying the code to an application with security or a changed management port/path, access results also depend on that configuration.

### 4.2. Running and Sending Inputs

At the root directory of the sample project, you can generate the Gradle Wrapper using an installed Gradle 8.x:

```shell
gradle wrapper --gradle-version 8.5
```

On Windows PowerShell:

```powershell
.\gradlew.bat clean bootRun
```

On Linux/macOS:

```shell
./gradlew clean bootRun
```

After the application starts, open another terminal. On Windows use `curl.exe`; on Linux/macOS you can use `curl`:

```shell
curl.exe -s "http://127.0.0.1:8080/actuator/nameprobe?cacheName=inventory&limit=5"
```

JSON response body:

```json
{"cacheName":"inventory","limit":5}
```

The application returns HTTP 200. `limit` in the HTTP input is a string of characters; the method receives the integer `5`. When checking JSON, compare field values without depending on field order.

Two requests to test input errors:

```shell
curl.exe -i "http://127.0.0.1:8080/actuator/nameprobe?cacheName=inventory"
curl.exe -i "http://127.0.0.1:8080/actuator/nameprobe?cacheName=inventory&limit=abc"
```

With the exact sample application:

| Request | Result |
| --- | --- |
| With `cacheName=inventory&limit=5` | 200, echoes both values |
| Missing `limit` | 400, missing required parameter |
| `limit=abc` | 400, cannot convert to `int` |

Both parameters of `inspect` are required in this example. Do not rely on error body content because error formatting can vary across configurations.

### 4.3. Reproducing Missing Metadata in a Controlled Way

Only in the experimental project, you can append the following configuration to `build.gradle` to strip the flag added by the plugin:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.removeAll { it == '-parameters' }
}
```

Run `clean bootRun` again to ensure the endpoint class is recompiled. When discovering the `inspect(String, int)` method, Spring Boot 3.3 can throw an `IllegalStateException` with a message starting with:

```text
Failed to extract parameter names for
```

The full message also contains the method description; outer exceptions may be bean-creation errors. Read the root cause instead of looking only at the outer startup failure line.

After the experiment, remove the flag-stripping configuration and run a clean build again. Adding `?arg0=inventory&arg1=5` to the URL does not rescue an application that already failed during operation discovery.

## 5. Enabling the Flag at the Right Compilation Step

### Gradle: Applications and Libraries Can Differ

For a Java project not configured by the Spring Boot plugin, add the flag to the compile tasks of the **project that owns the endpoint class**:

```groovy
tasks.withType(JavaCompile).configureEach {
    if (!options.compilerArgs.contains('-parameters')) {
        options.compilerArgs.add('-parameters')
    }
}
```

This snippet appends the item to the existing list. Avoid reassigning all of `compilerArgs` just to add one flag, as it could inadvertently drop other options.

In a multi-module project, enabling the flag in the consuming application does not recompile classes already packaged in a library JAR. If `NameProbeEndpoint` is provided by a library module applying only `java-library`, that module must be configured and republished. Also check when shrinking or bytecode-transforming tools run after compilation.

### Maven: Distinguishing Parent and BOM

When inheriting from `spring-boot-starter-parent`, the compiler configuration includes `-parameters` out of the box. Merely importing `spring-boot-dependencies` as a BOM does not inherit the parent's plugin settings. The [Maven plugin 3.3 documentation](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html) distinguishes these two usages.

If the project manages `maven-compiler-plugin` itself, the corresponding configuration under `build/plugins` is:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
```

This is a configuration snippet to merge into a POM managing the appropriate plugin version and Java level, not a standalone POM. After changing configuration, run a clean build of the project and inspect the output classes.

### IDE and CI

IDEs may use their own compiler/settings instead of delegating to Gradle or Maven. Hence “runs in the IDE” and “runs from the CI JAR” are two different checks. A reliable confirmation is reading metadata from the class actually loaded by the running process, not merely checking options shown in the IDE.

## 6. Verifying on Class Files and Artifacts

For the standalone Java experiment in section 3, use the JDK's `javap` tool:

```shell
javap -p -v -classpath out-with ParameterNamesDemo
javap -p -v -classpath out-without ParameterNamesDemo
```

In the description of the `inspect` method in the flagged build, look for the `MethodParameters` attribute and the names `cacheName`, `limit`. In the unflagged build, there is no corresponding name table for this method.

Do not merely search for the string `cacheName` anywhere in the entire output: debug info or other members can also contain a string matching the target name. Nor should you infer every method in the class has proper names just from seeing one `MethodParameters` table; inspect the right method and each parameter.

If you suspect the wrong class is being run, you can temporarily check the class loading source in diagnostic code:

```java
System.out.println(
        NameProbeEndpoint.class.getProtectionDomain()
                .getCodeSource().getLocation());
```

The snippet above is for diagnostics, not a standalone program; the printed location depends on packaging and environment. It helps verify whether you are running the version in the build directory or a different library JAR.

With an executable JAR packaged by Spring Boot, application classes usually reside under `BOOT-INF/classes`, and libraries under `BOOT-INF/lib`. When using `javap`, extract the artifact to a temporary directory and point the classpath to the exact directory or JAR containing the class to inspect. Do not assume `javap -classpath app.jar` will automatically read application classes inside a nested JAR layout.

A useful verification sequence is:

```text
1. Identify which module produces the endpoint class.
2. Recompile that module with -parameters.
3. Inspect the target method in the output class.
4. Verify the class is packaged into the deployment artifact.
5. Confirm the running process uses the newly built artifact.
6. Test valid requests and missing/wrong-type parameter requests.
```

## 7. Distinguishing Metadata Errors from Other Endpoint Errors

| Symptom | What to Check First |
| --- | --- |
| Startup fails, cause says parameter names cannot be extracted | Metadata of the target method, compiler flags, JAR being loaded |
| Application starts but URL returns 404 | Endpoint registration/exposure, management path, port, and matching operation |
| Returns 401 or 403 | Authentication, authorization, and related security rules |
| Returns 400 when `limit` is missing or `limit=abc` is sent | Required input and type conversion |
| Reflection still sees `arg0`, `isNamePresent()=false` after fixing build | Stale class, config applied to wrong module, or metadata stripped post-compile |

The table is an investigation guide, not a rule for diagnosing solely from HTTP status codes. For example, a security layer or proxy may return a response before the request reaches the Actuator operation.

Adding `-parameters` does not register a bean, expose an endpoint, or grant access permissions. Conversely, opening exposure does not recreate missing metadata in a class file.

## 8. Parameter Names Are Part of the Input Contract

Suppose the endpoint initially accepts `cacheName`. An operations tool calls `?cacheName=inventory&limit=5`. If you rename the Java parameter to `cache` and recompile with `-parameters`, the inferred input name also changes.

Direct Java calls may continue to compile because parameter types and order have not changed. Operations tools sending the old name may fail for missing the new input. Therefore:

- Name parameters clearly before publishing operations.
- Treat renaming as a change that can affect HTTP/JMX callers.
- Test requests using public names, not only by calling Java methods in tests.
- Synchronize command examples, operational docs, and callers when changing the contract.

Do not treat `-parameters` as a business validation mechanism. For instance, `limit=-5` still converts to `int`; if that value is invalid for the real problem, the application must check it separately. The flag supplies name metadata, not allowed value ranges.

## 9. Self-Check

1. Why does `inspect("inventory", 5)` still run when Reflection only sees `arg0`, `arg1`?
2. In the example, does enabling `-g` make `isNamePresent()` return `true`?
3. Why does adding the flag in the application module fail to fix an endpoint class inside a precompiled library JAR?
4. Is a request missing `limit` returning 400 enough to conclude the project lacks `-parameters`?
5. If renaming `cacheName` to `cache`, what else must be checked besides a successful Java build?

Answer key:

1. Java passes arguments by position and type; direct calls do not need source parameter names.
2. No. For ordinary methods in the experiment, `-parameters` is required to preserve names for Reflection.
3. The application module does not recompile bytecode already inside dependencies; the build producing the class must be fixed.
4. No. That can be a missing-input error on an operation that was already discovered properly.
5. Check the input names operations tools send, retest HTTP/JMX, and update related documentation.

After this lesson, verify all three pieces of evidence on the same build: parameter names present in the class, operation discovered successfully, and requests with the right names mapped to the right parameters.
