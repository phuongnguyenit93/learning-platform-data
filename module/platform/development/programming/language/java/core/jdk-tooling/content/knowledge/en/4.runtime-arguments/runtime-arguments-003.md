# System Properties in Java

**System properties** are a collection of string key–value pairs used by the JVM and Java applications to exchange process-level configuration. They provide information about the runtime, operating system, and working directory, and allow passing configuration into an application at startup.

In Java, reading and managing system properties is primarily done through the `java.lang.System` and `java.util.Properties` classes.

For example, you can launch an application in production mode:

```bash
java -Dapp.mode=production -jar app.jar
```

Here, `app.mode` is a system property passed to the JVM by the user running the application.

## 1. What are system properties?

System properties are a set of global properties within a JVM. Each property has:

- **Key:** the property name, for example `app.mode`.
- **Value:** a `String` value, for example `production`.

Some properties are set by the JVM or the Java launcher at startup. An application can also read, add, modify, or remove properties at runtime.

Key characteristics to remember:

- System properties are scoped to a single JVM process.
- Values are represented as strings; the application converts them to numbers, booleans, or other required types.
- Properties can be passed at startup using the `-Dkey=value` option.
- They can be accessed using `System.getProperty()`, `System.setProperty()`, and `System.getProperties()`.
- Changes made in memory are not automatically written back to configuration files or persisted for subsequent runs.

System properties are commonly used for application configuration, runtime options, and environment information. They are not a mechanism for persistent data storage.

## 2. System properties vs. environment variables

System properties and environment variables can both pass configuration information into an application, but they are two distinct mechanisms.

| Criterion | System properties | Environment variables |
| --- | --- | --- |
| Access in Java | `System.getProperty()` | `System.getenv()` |
| Common way to pass | JVM option `-Dkey=value` | Process environment before startup |
| Scope | Current JVM | Process and child processes according to OS rules |
| Updating in Java | Modifiable via the `System` API | Read-only in the Java API; no standard API to modify the process environment |
| Naming convention | Typically `app.feature.option` | Typically uppercase with underscores, e.g., `APP_MODE` |
| Example | `app.mode=production` | `APP_MODE=production` |

Reading a system property:

```java
String mode = System.getProperty("app.mode");
```

Reading an environment variable:

```java
String mode = System.getenv("APP_MODE");
```

These two calls read from separate namespaces. Setting the `APP_MODE` environment variable does not automatically create an `app.mode` system property; the application must read the environment variable and decide how to use it.

When designing configuration, explicitly document which source takes precedence. For example, an application may specify that a system property overrides an environment variable, but that is a rule implemented by the application, not an automatic JVM precedence order.

## 3. Common system properties

The JVM provides many standard properties. Each property can be read using `System.getProperty()`.

| Property | Meaning |
| --- | --- |
| `java.version` | Java runtime version |
| `java.vendor` | Java distribution vendor |
| `java.home` | Java runtime installation directory |
| `java.vm.name` | Java Virtual Machine name |
| `java.vm.version` | JVM implementation version |
| `java.specification.version` | Java specification version |
| `java.class.path` | Application classpath |
| `java.io.tmpdir` | Default temporary directory |
| `os.name` | Operating system name |
| `os.version` | Operating system version |
| `os.arch` | Operating system/runtime architecture |
| `user.name` | User name of the runtime environment |
| `user.home` | User's home directory |
| `user.dir` | Current working directory |
| `file.separator` | File path separator character |
| `path.separator` | Classpath entry separator character |
| `line.separator` | Line separator string for the environment |
| `file.encoding` | Default charset used by certain I/O APIs |

Example of reading several properties:

```java
System.out.println("Java version: " + System.getProperty("java.version"));
System.out.println("Java home: " + System.getProperty("java.home"));
System.out.println("OS: " + System.getProperty("os.name"));
System.out.println("Architecture: " + System.getProperty("os.arch"));
System.out.println("Working directory: " + System.getProperty("user.dir"));
```

Values depend on the JDK, operating system, launch method, and process configuration. For example, `user.dir` is the current working directory, not necessarily the directory containing the source files. `java.class.path` describes the classpath, not the full list of modules on the module path.

**Note on `file.encoding`:** Since JDK 18, UTF-8 is the default charset under JEP 400 in standard configurations. On older JDKs, the default charset may depend on the environment. When reading or writing data with specific encoding requirements, explicitly specify the charset in I/O APIs instead of assuming the default value.

## 4. Passing system properties with the -D option

The `-D` option lets you set a system property when the JVM starts:

```bash
java -Dapp.mode=production -Dapp.region=ap-southeast-1 -cp . SystemPropertiesDemo
```

General syntax:

```text
java -Dproperty.name=value ClassName
```

You can pass multiple `-D` options in the same command. Each option sets a property for the running JVM.

For an application packaged as a JAR:

```bash
java -Dapp.mode=production -Dapp.debug=true -jar app.jar
```

**The position of `-D` matters:** JVM options must appear before the main class name or before `-jar`. If you place `-Dapp.mode=production` after the class name or after `-jar app.jar`, that string is passed to the program as a command-line argument rather than being processed by the Java launcher as a JVM option.

If the value contains spaces, quote the entire `-Dkey=value` pair according to your shell's syntax, for example:

```bash
java '-Dapp.display-name=Development Environment' -cp . SystemPropertiesDemo
```

## 5. Reading system properties in Java

The `System` class provides the commonly used methods:

| Method | Purpose |
| --- | --- |
| `System.getProperty(key)` | Retrieves the value; returns `null` if the key does not exist |
| `System.getProperty(key, defaultValue)` | Retrieves the value or returns the default value |
| `System.getProperties()` | Returns the `Properties` object containing the system properties |
| `System.setProperty(key, value)` | Adds or updates a property |
| `System.clearProperty(key)` | Removes a property |

### Getting values and default values

```java
String mode = System.getProperty("app.mode");
String region = System.getProperty("app.region", "local");
```

- If `app.mode` is not set, `mode` receives `null`.
- If `app.region` is not set, `region` receives `local`.

Using default values helps an application start in environments where not all configuration is provided. However, for required properties such as a production endpoint or security mode, the application should validate and report a clear error instead of silently falling back to an inappropriate value.

### Reading booleans and numbers

System property values are always strings, so conversion is required:

```java
boolean debug = Boolean.parseBoolean(
    System.getProperty("app.debug", "false")
);

int port = Integer.parseInt(
    System.getProperty("app.port", "8080")
);
```

`Boolean.parseBoolean()` returns `true` if the string equals `true` case-insensitively; any other value, including a typo, evaluates to `false`. For critical configuration, validate the input explicitly.

`Integer.parseInt()` can throw `NumberFormatException` if the value is not a valid integer. The application should validate both format and value range—for example, ensuring a network port is within the valid range.

## 6. Complete example: reading configuration from -D

Create the file **`SystemPropertiesDemo.java`**:

```java
public class SystemPropertiesDemo {
    public static void main(String[] args) {
        String mode = System.getProperty("app.mode", "development");
        String region = System.getProperty("app.region", "local");
        boolean debug = Boolean.parseBoolean(
            System.getProperty("app.debug", "false")
        );

        System.out.println("app.mode=" + mode);
        System.out.println("app.region=" + region);
        System.out.println("app.debug=" + debug);
    }
}
```

Compile:

```bash
javac SystemPropertiesDemo.java
```

Run with system properties:

```bash
java -Dapp.mode=production -Dapp.region=ap-southeast-1 -Dapp.debug=true -cp . SystemPropertiesDemo
```

Exact output:

```text
app.mode=production
app.region=ap-southeast-1
app.debug=true
```

If run without passing `-D`:

```bash
java -cp . SystemPropertiesDemo
```

Output:

```text
app.mode=development
app.region=local
app.debug=false
```

This example demonstrates that `System.getProperty(key, defaultValue)` uses the default value when the property has not been passed to the JVM.

## 7. Modifying and removing system properties at runtime

You can modify a property with `System.setProperty()`:

```java
String previous = System.setProperty("app.mode", "test");
System.out.println("Current mode: " + System.getProperty("app.mode"));
```

This method returns the previous value if the property already existed; otherwise, it returns `null`.

Removing a property:

```java
String previous = System.clearProperty("app.mode");
```

After removal, `System.getProperty("app.mode")` returns `null`, unless the application sets the property again.

These changes have JVM-wide scope. Other code, libraries, or threads in the same process can observe the new value. Therefore:

- Only modify properties when there is a clear reason.
- Avoid using system properties to store per-request or per-thread state.
- Do not modify standard JVM properties to spoof a different operating system or Java version.
- If multiple components read the same property, clearly define when and by whom it may be changed.

`System.getProperties()` returns the `Properties` object currently used as the system properties map. You can iterate over property names with:

```java
for (String key : System.getProperties().stringPropertyNames()) {
    System.out.println(key + "=" + System.getProperty(key));
}
```

Do not print all system properties in production logs, because values may contain internal paths, account names, or sensitive environment details.

`System.setProperties(properties)` replaces the entire system properties object. This is a high-impact operation and is usually unnecessary in normal applications. When you only need to change a single value, prefer `System.setProperty()`.

## 8. Reading configuration from a Properties file

System properties are not a configuration file. If an application needs to store multiple settings in a file, you can use `java.util.Properties` with a separate instance.

Example **`app.properties`** file:

```properties
app.mode=staging
app.region=ap-southeast-1
app.timeout.seconds=30
```

Reading the file as UTF-8 in Java 17:

```java
import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public class PropertiesFileDemo {
    public static void main(String[] args) throws IOException {
        Properties config = new Properties();

        try (Reader reader = Files.newBufferedReader(
                Path.of("app.properties"), StandardCharsets.UTF_8)) {
            config.load(reader);
        }

        String mode = config.getProperty("app.mode", "development");
        System.out.println("Mode: " + mode);
    }
}
```

With the file contents shown above, the output is:

```text
Mode: staging
```

Here, `config` is the application's own configuration object. Calling `config.load(reader)` does not automatically affect `System.getProperty()`.

A note on encoding:

- `Properties.load(InputStream)` uses ISO-8859-1 rules and supports Unicode escapes.
- `Properties.load(Reader)` reads characters from the `Reader` provided by the application.
- For UTF-8 files, you can use `Files.newBufferedReader(path, StandardCharsets.UTF_8)` and pass the `Reader` to `load()`.

If you want to load a file into system properties, you can operate on the object returned by `System.getProperties()`, but doing so places the configuration into JVM-wide scope. Only do this if the application design genuinely requires it; normally, keep application configuration in a dedicated object for better control.

## 9. Configuration precedence order

The JVM does not enforce a single global precedence order across all application configuration sources. An application may receive configuration from:

1. Default values in source code.
2. Configuration files.
3. Environment variables.
4. System properties passed via `-D`.
5. Command-line arguments.
6. Values set directly at runtime.

The application itself must define how these sources are merged. A common convention is that values passed explicitly at runtime override defaults, but the exact order must be documented by the application.

For example, if an application specifies that system properties take precedence over a configuration file, you can write:

```java
String mode = System.getProperty(
    "app.mode",
    config.getProperty("app.mode", "development")
);
```

This means:

- If the `app.mode` system property exists, use it.
- Otherwise, use the value in the `config` object.
- If neither is present, use `development`.

Note: the example above only illustrates an order chosen by the application. The JVM does not automatically read `app.properties` files and merge them with `-D`.

## 10. Naming conventions and configuration design

System properties should be named hierarchically, in lowercase, separated by dots:

```text
app.mode
app.http.port
app.http.connect-timeout-ms
app.logging.level
app.feature.new-checkout.enabled
```

Some helpful guidelines:

- Use a prefix specific to your application or organization to avoid name collisions.
- Use names that clearly convey the meaning and unit of the value.
- Define default values and behavior when configuration is missing.
- Validate values when converting strings to numbers, booleans, or enums.
- Document which properties are required, which are optional, and valid examples.
- Avoid using property names in JVM namespaces such as `java.*` for application-specific configuration.

System properties are JVM-wide global configuration. If you need different configuration per object, request, or thread, use an explicitly passed configuration object instead of mutating global properties.

## 11. Security when using system properties

System properties should not be treated as a secret store.

Avoid passing passwords, access tokens, private keys, or sensitive credentials via `-D`, because command-line values can appear in process lists, startup logs, monitoring tools, or diagnostic dumps.

In addition:

- Do not log all of `System.getProperties()` in production logs.
- Do not put secrets in configuration files committed to Git.
- Use a secret manager or secret management mechanism appropriate for your deployment platform.
- Check and restrict access permissions on configuration files.
- Validate configuration values before using them in network connections, file paths, or system operations.

A system property can typically be read by any code running in the same JVM. Do not use it to isolate secret data between libraries or modules.

## 12. Common errors

| Symptom | Cause | Solution |
| --- | --- | --- |
| `System.getProperty("app.mode")` returns `null` | `-Dapp.mode=...` was not passed or the application has not set the property | Check the launch command and provide a default value if appropriate |
| `-Dapp.mode=production` has no effect | The option was placed after the class name or after `-jar` | Move `-D` before the main class name or before `-jar` |
| Environment variable does not appear via `getProperty()` | Reading from the wrong configuration mechanism | Use `System.getenv()` or map environment variables to configuration |
| Boolean always evaluates to `false` | Value is not a valid `true` string | Check spelling and validate the value before conversion |
| Number conversion fails | Value is empty or not a number | Validate input and handle `NumberFormatException` |
| Application does not pick up changes from a file | Loaded into a separate `Properties` object but reading from `System.getProperty()` | Read from the right configuration object or design an explicit mapping step |
| Logs contain sensitive environment information | Printing all system properties | Log only allowlisted keys and redact sensitive values |

## 13. Key takeaways

- System properties are string key–value pairs scoped to a single JVM.
- Use `-Dkey=value` before the main class name or `-jar` to pass properties at startup.
- Use `System.getProperty()` to read, `System.setProperty()` to add/update, and `System.clearProperty()` to remove.
- Use `System.getenv()` to read environment variables; the two mechanisms do not automatically map to each other.
- Use `java.util.Properties` to manage configuration files; a separate `Properties` object is not the same as system properties.
- The application defines its own precedence order among files, environment variables, system properties, and command-line arguments.
- Do not store secrets in system properties or log all system properties.

When you need to configure the JVM or pass a few values at runtime, system properties are a simple and useful mechanism. For large configurations, secrets, or settings that must vary independently by environment, choose a dedicated configuration mechanism and clearly define how sources are merged.
