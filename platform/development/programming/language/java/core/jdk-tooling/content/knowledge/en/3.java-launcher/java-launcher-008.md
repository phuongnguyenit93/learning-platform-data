# System properties in the Java runtime

A **system property** is a string key–value pair that Java stores in the property set of the current JVM process. The JVM, JDK libraries, and applications can read these values to inspect environment information or receive startup configuration—for example, the Java version, operating system, working directory, and application run mode.

The Java launcher lets you set properties at JVM creation time using the `-Dkey=value` option. Application code can also read, add, modify, or remove properties at runtime through the `java.lang.System` class. System properties are well suited for string-based configuration passed to a single Java process, such as run mode, service URLs, timeout limits, or feature flags.

## 1. Distinguishing system properties, environment variables, and application arguments

These three kinds of values often appear together in a Java launch command, but they have different access mechanisms and lifecycles.

| Data type | Where it is set | Read in Java | Scope |
|---|---|---|---|
| System property | JVM option such as `-Dapp.mode=production`, or `System.setProperty` API | `System.getProperty("app.mode")` | A single JVM process |
| Environment variable | Operating system environment, e.g., `APP_MODE=production` | `System.getenv("APP_MODE")` | The process and child processes that inherit the environment |
| Application argument | Arguments after the class name, `-jar`, or target module | `String[] args` array of `main` | That application execution |

Example:

~~~sh
java -Dapp.mode=production -jar service.jar --port=8080
~~~

- `-Dapp.mode=production` is a JVM option that creates a system property with key `app.mode`.
- `service.jar` is the application being launched.
- `--port=8080` appears after the JAR name, so it is an application argument passed into `main(String[] args)`.

`System.getenv()` only reads the environment inherited by the process. Java does not provide a standard API to modify environment variables of the current OS process. Conversely, `System.setProperty()` only modifies system properties within the running JVM; it does not alter the OS environment or propagate changes back to other processes.

## 2. Setting properties from the Java launcher with -D

Basic syntax:

~~~sh
java -D<property-name>=<value> <class-name>
~~~

Example:

~~~sh
java -Dapp.mode=production -Dapp.region=ap-southeast-1 com.example.Main
~~~

The JVM is launched with two system properties: `app.mode=production` and `app.region=ap-southeast-1`. The `-D` option must be placed in the Java launcher options section, before the target class, `-jar`, or module. This placement is critical:

~~~sh
# Correct: -D is a JVM option
java -Dapp.mode=production -jar service.jar

# Incorrect if the goal is to set a system property:
java -jar service.jar -Dapp.mode=production
~~~

In the second command, the string `-Dapp.mode=production` comes after the JAR name, so it is passed to the application as an application argument. It does not set a system property.

Common launch forms:

~~~sh
# Run a class
java -Dapp.mode=production -cp app.jar com.example.Main

# Run an executable JAR
java -Dapp.mode=production -jar app.jar

# Run a main class in a module
java -Dapp.mode=production -m com.example.app/com.example.Main
~~~

When specifying multiple properties, pass each property with a separate `-D` option. If a value contains spaces, use quotes according to your OS shell syntax so that the entire `-Dkey=value` expression is passed as a single argument:

~~~sh
java "-Dapp.display-name=Java Learning Service" -jar app.jar
~~~

PowerShell, Command Prompt, Bash, and Zsh have different quoting rules. If a value contains special characters such as quotes, `$`, or `;`, check how the shell interprets them before concluding that the JVM received the wrong property.

`-D` is a Java launcher/JVM option, not syntax specific to Java source code. Values are supplied as strings; if the application needs numbers, booleans, lists, or other types, application code must convert and validate them.

## 3. Reading and manipulating system properties in Java

The `java.lang.System` class provides the main APIs:

| API | Purpose |
|---|---|
| `System.getProperty(key)` | Gets the value for the key; returns `null` if not present |
| `System.getProperty(key, defaultValue)` | Gets the value, or uses the default value if the key is not present |
| `System.setProperty(key, value)` | Adds or updates the value; returns the previous value if any |
| `System.clearProperty(key)` | Removes the key; returns the previous value if any |
| `System.getProperties()` | Gets the current `Properties` set of the JVM |
| `System.setProperties(properties)` | Replaces the current system properties set |

Example of reading a value with a default:

~~~java
String mode = System.getProperty("app.mode", "development");
~~~

If the Java launcher did not pass `-Dapp.mode=...`, the `mode` variable receives `development`. If it was passed, it receives the value provided at startup.

A property can be updated at runtime:

~~~java
String previous = System.setProperty("app.mode", "maintenance");
String current = System.getProperty("app.mode");
~~~

After `setProperty`, subsequent reads in the same JVM receive the new value, unless a library or component already read and cached the old value in its own state. This change does not automatically restart libraries, update other processes, or persist configuration to a file for future runs.

When calling `System.setProperty`, both key and value must be non-null; an empty key is invalid. These APIs may throw `SecurityException` in environments where a security policy restricts access to system properties. You should not rely on being able to modify every JVM property.

### Reading the entire property set

`System.getProperties()` returns a `java.util.Properties` object containing the current properties:

~~~java
Properties properties = System.getProperties();
String javaVersion = properties.getProperty("java.version");
~~~

You need to import `java.util.Properties` if referencing the `Properties` class name directly. You can iterate over keys for diagnostics, but avoid indiscriminately printing all properties to production logs: some values may expose paths, account names, internal configuration, or environment details.

`System.setProperties()` replaces the entire current property set. If you pass a `Properties` object missing standard properties, other code in the JVM may no longer be able to read keys it expects. Most applications should only use `System.setProperty()` for keys they manage themselves; do not replace the entire property set without a clear reason.

## 4. Common system properties

Java provides several standard properties for querying the runtime environment. Specific values depend on the JDK, vendor, operating system, and launch method.

| Property | Meaning |
|---|---|
| `java.version` | Java runtime version |
| `java.vendor` | Java distribution vendor |
| `java.home` | Java runtime installation directory |
| `java.class.path` | Application classpath |
| `java.library.path` | Locations where the JVM searches for native libraries |
| `os.name` | Operating system name |
| `os.version` | Operating system version |
| `os.arch` | Operating system architecture |
| `user.name` | User account name of the process |
| `user.home` | User home directory |
| `user.dir` | Current working directory when the JVM started |
| `file.separator` | OS directory separator character |
| `path.separator` | Separator character for path entries |
| `line.separator` | Platform line-ending character sequence |

You can quickly inspect a few values in your application:

~~~java
System.out.println("Java version: " + System.getProperty("java.version"));
System.out.println("OS: " + System.getProperty("os.name"));
System.out.println("Working directory: " + System.getProperty("user.dir"));
~~~

Do not assume values such as paths, OS names, or versions will be identical across development machines, CI, and production. If your application needs cross-platform behavior, use appropriate APIs such as `Path`, `File.separator`, or `System.lineSeparator()` instead of inferring from hardcoded strings.

Some properties have special semantics:

- `user.dir` describes the working directory used by the JVM at startup. Calling `System.setProperty("user.dir", "...")` is not a reliable way to change the actual working directory of the process.
- `java.class.path` reflects the classpath provided for a classpath-based application. For modular applications, module resolution also depends on the module path and JPMS configuration.
- `java.library.path` relates to native library lookup. Changing its value at runtime does not guarantee that an already-initialized class loader or library loader will search the new path.
- `file.encoding` relates to the default charset. Since JDK 18, UTF-8 is the default charset per JEP 400 in typical environments. Do not call `System.setProperty("file.encoding", ...)` in application code to try to change the default charset after JVM initialization; specify the charset explicitly in I/O APIs, such as `StandardCharsets.UTF_8`.

Internal properties with prefixes such as `sun.` or `jdk.` may serve specific JDK implementations. Do not treat them as stable APIs unless guaranteed by the Java SE documentation. Prefer standard properties or application-namespaced keys.

## 5. Complete example: reading, modifying, and clearing properties

Create `RuntimePropertiesDemo.java`:

~~~java
public class RuntimePropertiesDemo {
    public static void main(String[] args) {
        String mode = System.getProperty("app.mode", "development");
        String region = System.getProperty("app.region", "local");

        System.out.println("mode.before=" + mode);
        System.out.println("region=" + region);

        System.setProperty("app.mode", "runtime");
        System.out.println("mode.after=" + System.getProperty("app.mode"));

        System.clearProperty("app.region");
        System.out.println(
            "region.after.clear=" + System.getProperty("app.region", "local")
        );

        System.out.println("args.count=" + args.length);
    }
}
~~~

Compile and run:

~~~sh
javac RuntimePropertiesDemo.java
java -Dapp.mode=production -Dapp.region=ap-southeast-1 RuntimePropertiesDemo sample
~~~

Standard output:

~~~text
mode.before=production
region=ap-southeast-1
mode.after=runtime
region.after.clear=local
args.count=1
~~~

Explanation:

1. `System.getProperty("app.mode", "development")` receives `production` from the `-D` option.
2. `System.getProperty("app.region", "local")` receives `ap-southeast-1`.
3. `System.setProperty()` changes `app.mode` to `runtime`; the subsequent read sees the new value.
4. `System.clearProperty()` removes `app.region`; reading with the default value returns `local`.
5. `sample` appears after the class name, so it is placed into `args`, not into system properties.

If both `-D` options are omitted, the program still runs using the default values `development` and `local`. This is a useful pattern for providing local defaults while allowing deployment environments to override configuration.

## 6. Converting and validating values

System properties are always read as `String`. Do not cast or parse them assuming the input is always valid.

Example of reading a timeout in seconds:

~~~java
String timeoutText = System.getProperty("app.timeout-seconds", "30");

int timeoutSeconds;
try {
    timeoutSeconds = Integer.parseInt(timeoutText);
} catch (NumberFormatException exception) {
    throw new IllegalArgumentException(
        "app.timeout-seconds must be an integer", exception
    );
}

if (timeoutSeconds <= 0) {
    throw new IllegalArgumentException(
        "app.timeout-seconds must be greater than zero"
    );
}
~~~

If launched with:

~~~sh
java -Dapp.timeout-seconds=45 -jar app.jar
~~~

the application receives a timeout of 45 seconds. If `-Dapp.timeout-seconds=abc` is passed, `Integer.parseInt()` throws `NumberFormatException`; report a clear configuration error rather than silently falling back to an invalid state.

For booleans, `Boolean.parseBoolean(value)` returns `true` when the string matches `true` case-insensitively; any other value—including misspelled strings—returns `false`. If you need to distinguish `false`, missing values, and invalid values, validate the string explicitly before converting.

For lists, you can define a simple format such as comma-separated values and use `String.split()`, but be sure to define how whitespace, empty elements, and commas within values are handled. For complex, hierarchical, or reloadable configuration, configuration files and dedicated configuration libraries are usually more appropriate than a collection of system properties.

## 7. Observing properties and runtime diagnostics

The Java launcher can print the system properties that the JVM sees at startup:

~~~sh
java -XshowSettings:properties -version
~~~

This command displays various environment details along with the Java version. The output is useful for checking `java.home`, `java.version`, `os.name`, `user.dir`, or values received by the launcher. Because the output may contain file paths and usernames, review it before sharing logs.

For a running Java process, the JDK provides the `jcmd` tool to query JVM properties if the process allows attach and the caller has appropriate permissions:

~~~sh
jcmd <pid> VM.system_properties
~~~

Replace `<pid>` with the process ID of the JVM to inspect. This command returns the process's system properties at the time of the query. In containers, servers, or multi-user environments, attach capabilities may be restricted; run it from the appropriate user account and namespace.

When diagnosing issues, compare three sources:

- The expected value in the launch command or deployment configuration.
- The actual value read via `System.getProperty()` inside the application.
- The value reported by `jcmd` or `-XshowSettings:properties`.

If the values differ, check the placement of the `-D` option, launch scripts, IDE/build tool configuration, and any code calling `System.setProperty()` after the application starts.

## 8. Runtime impact and limitations

System properties are scoped to a single JVM. Two separate Java processes do not automatically share property changes, even when running the same JAR. When the JVM exits, in-memory changes are lost as well.

Modifying a property at runtime can affect code that reads the property afterward. However, many libraries read configuration only once during initialization and store it in fields or configuration objects. In those cases, changing a system property later will not automatically update already-initialized components. If runtime reconfiguration is needed, use the library's reload API or supported configuration mechanism.

Not every property should be modified:

- Prefer setting application properties with `-D` at launch time.
- Use a dedicated namespace, such as `com.example.billing.timeout-seconds`, to avoid key collisions with other libraries.
- Do not arbitrarily overwrite standard keys like `java.version`, `java.home`, `os.name`, or `file.encoding`.
- Do not use system properties as a secret store. JVM arguments can appear in process listings, startup logs, diagnostic reports, or monitoring tools.
- Do not replace the entire `System.getProperties()` map with a new set unless you understand the impact on the JVM and libraries.
- Do not assume a property updated after application startup will automatically refresh library caches.

For passwords, tokens, or access keys, use a secret manager or an appropriate platform secret-provisioning mechanism. If sensitive data must be passed through configuration, evaluate access permissions, logging, dumps, and process observability.

## 9. Integration with Gradle, Maven, and IDEs

Distinguish between the system properties of the JVM running the build tool and those of the JVM running the application.

For example, when running:

~~~sh
./gradlew -Dorg.gradle.logging.level=info build
~~~

the `-D` option is sent to the Gradle process. That does not mean every JVM spawned by Gradle to run the application or tests automatically receives the same set of system properties. For tasks that run the application, configure the task's JVM arguments, such as `JavaExec.jvmArgs`; for tests, use the `Test` task's system properties configuration.

Similarly, `mvn -Dname=value` sets a user/system property for the Maven process according to Maven's rules. When you need to pass values to a forked test JVM or an application JVM, use the corresponding plugin configuration (such as Maven Surefire/Failsafe or the application runner plugin), and verify from the target process itself.

In an IDE, there may be several separate configuration areas:

- **IDE runtime**: The JDK used to run the IDE itself.
- **Project SDK**: The JDK selected by the project for analysis and compilation.
- **Gradle JVM / Maven runner**: The JDK used to run the build tool.
- **Application run configuration**: VM options passed to the application's JVM.
- **Test run configuration**: VM options/system properties for the test process.

If the goal is to set a property for the application, enter `-Dapp.mode=production` in the **VM options** field of the application run configuration. Placing it in the **Program arguments** field makes it an argument to `main`, not a system property.

After changing configuration, verify from the exact process you intend to test. A successful build only proves that the build process succeeded; it does not prove that the application received the right system property.

## 10. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| `System.getProperty()` returns `null` | Property not set, wrong key name, or `-D` placed after class/JAR/module | Place `-Dkey=value` before the launch target and verify the exact key name |
| Application receives `-D...` string in `args` | Option placed after `-jar` or class name | Move `-D` into the JVM options section before the target |
| Value with spaces gets split | Shell splits the expression into multiple arguments | Quote the entire `-Dkey=value` expression according to shell rules |
| Runtime value differs from startup value | Other code called `System.setProperty()` or configuration was reloaded | Search for places modifying the same key; use clear namespaces and selective logging |
| Property changed but library still uses old value | Library cached configuration at initialization | Use a reload/reconfigure API or set the property before library initialization |
| Build tool receives property but application does not | Property set on the Gradle/Maven JVM rather than the application JVM | Pass VM options to the target process's task or run configuration |
| Parsing number or boolean fails | String value is invalid or malformed | Parse, validate, and report a specific configuration error |
| Internal property stops working after JDK upgrade | Key depends on JDK implementation or is not a guaranteed API | Use standard properties/public APIs; check version compatibility |

### Safe usage checklist

- [ ] Distinguish system properties from environment variables and application arguments.
- [ ] Place `-Dkey=value` before the target class, `-jar`, or module.
- [ ] Use `System.getProperty()` with sensible default values.
- [ ] Convert and validate string data before use.
- [ ] Use a dedicated namespace for application properties.
- [ ] Set configuration before libraries that depend on it are initialized.
- [ ] Pass properties to the exact JVM of the application or test.
- [ ] Do not store secrets on the command line or in system properties.
- [ ] Verify values inside the actual runtime process being tested.

Once you understand the placement of `-D`, the JVM-level scope, and the `System` APIs, system properties become a lightweight way to supply configuration to Java applications at startup and at runtime.