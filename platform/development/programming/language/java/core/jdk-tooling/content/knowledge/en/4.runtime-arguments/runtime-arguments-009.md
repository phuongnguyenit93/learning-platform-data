# Property Files in Java

## 1. What is a property file?

A property file is a text-based configuration file, typically with the **.properties** extension, used to store key-value pairs. Java provides the **java.util.Properties** class to read, retrieve, update, and write this type of configuration.

Example of an **app.properties** file:

~~~properties
# Application settings
app.name=Ứng dụng học Java
app.timeout.seconds=30
app.audit.enabled=true
server.host=localhost
server.port=8080
~~~

Each key represents a configuration property, such as the application name, timeout, feature state, or server address. The program reads values by key instead of having to modify source code every time the runtime environment changes.

Property files are suitable for simple configurations with a flat structure. They store values as strings; converting strings into numbers, booleans, enums, paths, or other data types is the program's responsibility. This format does not natively provide nested object structures, lists, or type checking like a schema.

It is important to distinguish three concepts often referred to collectively as "property":

- **Property file:** a text file containing key-value pairs.
- **Properties object:** a Java object of the java.util.Properties class, commonly used to hold content read from a file.
- **Java system property:** a global property of the JVM, accessed via System.getProperty and System.setProperty. This is a separate mechanism; reading a .properties file does not automatically put its keys into system properties.

## 2. Structure and syntax of a .properties file

A .properties file typically consists of blank lines, comment lines, and property declaration lines.

### Keys and values

Common valid separator forms:

~~~properties
server.host=localhost
server.port:8080
app.mode production
~~~

An equals sign, a colon, or whitespace can separate a key and a value. In practice, you should consistently use the equals sign to keep the file readable and less error-prone.

Key names usually use lowercase letters, dots for grouping, and clear, meaningful names:

~~~properties
database.url=jdbc:postgresql://localhost:5432/app
database.pool.maximum-size=20
feature.audit.enabled=true
http.client.connect-timeout-ms=3000
~~~

Key names are identifiers defined by application convention. Java does not automatically know that a **.enabled** suffix must be a boolean or **.timeout-ms** must be an integer.

### Comments and blank lines

A line starting with **#** or **!** after leading whitespace is a comment. Blank lines are ignored.

~~~properties
# HTTP server configuration
server.host=127.0.0.1

! The port used by the local server
server.port=8080
~~~

Comments help explain the purpose, units, valid values, and impact of changing a configuration. You should clearly state units in the key name or comment, for example whether a timeout is in milliseconds or seconds.

### Special characters and escaping

In a .properties file, the first unescaped separator (equals sign, colon, or whitespace) ends the key and begins the value. Once the parser has moved into the value part, equals signs and colons are ordinary characters; they do not need to be escaped in the value. If you want an equals sign or colon to be part of the key name itself, escape it in the key.

The backslash has special meaning. Use two backslashes to store a literal backslash; common control escapes are \t, \n, \r, \f, and Unicode escapes \uXXXX. Leading spaces in a value can be preserved by escaping that space. A trailing backslash at the end of a line indicates line continuation, so be careful when storing paths or strings ending with a backslash.

Example:

~~~properties
message=Hello World
display.label=Java: Runtime
endpoint=https://example.test:8443/api?mode=a=b
path=C:\\apps\\java
key\:with\:colon=value
key\=with\=equals=value
leading.space=\ value
~~~

After loading, the corresponding values are Java: Runtime, https://example.test:8443/api?mode=a=b, C:\apps\java, and value with a leading space. The last two keys contain colons and equals signs in their key names, respectively. When handling user-supplied input, inspect the value after loading with Properties.getProperty instead of guessing how the parser interprets escape sequences.

## 3. The java.util.Properties class

**Properties** is in the java.util package and extends Hashtable. This class is designed for property tables with string keys and values.

Commonly used methods:

| Method | Purpose |
|---|---|
| Properties() | Creates an empty property table. |
| Properties(Properties defaults) | Creates a table with a defaults table to look up when a key does not exist in the main table. |
| setProperty(key, value) | Sets a property with a String key and value. |
| getProperty(key) | Gets the String value; returns null if not found. |
| getProperty(key, defaultValue) | Gets the value or returns the default value if not found. |
| load(Reader) | Reads content from a character stream. |
| load(InputStream) | Reads content from a byte stream according to this API's encoding rules. |
| store(Writer, comments) | Writes properties to a character stream. |
| store(OutputStream, comments) | Writes properties to a byte stream according to this API's encoding rules. |
| stringPropertyNames() | Gets the set of keys where both key and value are String, including unoverridden default keys. |
| propertyNames() | Returns an Enumeration of keys in the table and unoverridden default keys. |

You should use **setProperty** and **getProperty** for regular configuration. Properties inherits the put/get methods from Hashtable so it can technically hold non-String objects, but such data is not suitable for standard property operations. getProperty only returns String values; stringPropertyNames only lists entries where both key and value are String.

### Default values

There are two common ways to provide default values:

The first way is to use the getProperty overload:

~~~java
String host = properties.getProperty("server.host", "localhost");
~~~

The second way is to create a defaults table:

~~~java
Properties defaults = new Properties();
defaults.setProperty("server.host", "localhost");
defaults.setProperty("server.port", "8080");

Properties properties = new Properties(defaults);
~~~

When calling getProperty, if the main table does not have the key, Properties looks it up in the defaults table. If the key is set in the main table, the value in the main table takes precedence. Default tables can be chained through other Properties objects.

One thing to keep in mind: store writes properties set directly in the main table; values that only exist in the defaults table are not automatically written to the file. If you need to save the merged configuration, explicitly decide which values should be materialized into the main table.

## 4. Reading a property file from the filesystem

Reading an external file is commonly used when operators need to change configuration without repackaging the application. Use Path, Files, and Reader to control both the path and encoding.

Example of reading a UTF-8 file:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public class PropertyFileDemo {
    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();

        Path configFile = Path.of("app.properties");
        try (var reader = Files.newBufferedReader(
                configFile, StandardCharsets.UTF_8)) {
            properties.load(reader);
        }

        String appName = properties.getProperty("app.name", "Unnamed");
        int timeoutSeconds = Integer.parseInt(
                properties.getProperty("app.timeout.seconds", "10"));

        if (timeoutSeconds <= 0) {
            throw new IllegalArgumentException(
                    "app.timeout.seconds must be positive");
        }

        String auditText = properties.getProperty(
                "app.audit.enabled", "false");
        if (!auditText.equalsIgnoreCase("true")
                && !auditText.equalsIgnoreCase("false")) {
            throw new IllegalArgumentException(
                    "app.audit.enabled must be true or false");
        }
        boolean auditEnabled = Boolean.parseBoolean(auditText);

        System.out.println("Application: " + appName);
        System.out.println("Timeout seconds: " + timeoutSeconds);
        System.out.println("Audit enabled: " + auditEnabled);
    }
}
~~~

Place the app.properties file in the current working directory:

~~~properties
app.name=Ứng dụng học Java
app.timeout.seconds=30
app.audit.enabled=true
~~~

Compile and run from the directory containing both files:

~~~bash
javac PropertyFileDemo.java
java PropertyFileDemo
~~~

Output:

~~~text
Application: Ứng dụng học Java
Timeout seconds: 30
Audit enabled: true
~~~

The example uses Files.newBufferedReader with UTF-8, so it can read Vietnamese directly. Path.of with a relative path is resolved against the process's current working directory, typically observed via the user.dir system property. If the application is launched from an IDE, service manager, or container, the working directory may differ from the directory containing the JAR file. For production configuration, pass an explicit path or use a well-defined configuration location.

Try-with-resources automatically closes the Reader even if load throws an error. IOException is propagated out of main in the example; real applications can catch the error at the startup boundary to add the filename, environment, and remediation guidance. Do not silently continue running with an empty configuration when a required file is missing or unreadable.

### Encoding: InputStream vs. Reader

This is a very common source of bugs with files containing Vietnamese diacritics:

- **load(InputStream)** interprets bytes as ISO-8859-1. Characters outside this set must be represented using Unicode escapes in the properties format.
- **load(Reader)** receives already-decoded character data. The application chooses the encoding when creating the Reader, such as UTF-8.
- **store(OutputStream, comments)** writes in a format compatible with load(InputStream), using ISO-8859-1 and escaping characters that cannot be represented.
- **store(Writer, comments)** writes characters to the Writer; the encoding depends on the Writer provided by the application.

Therefore, if a configuration file is saved as UTF-8 and contains Vietnamese, use a UTF-8 Reader when reading. When writing a UTF-8 file, create a UTF-8 Writer and then call store(Writer, comments). Do not assume that load(InputStream) automatically detects UTF-8.

## 5. Reading a .properties file from the classpath

Default configurations are often packaged with the application in resources, such as **src/main/resources/app.properties**. During the build, this file is placed on the classpath and can be read via Class or ClassLoader.

Example of reading a resource at the classpath root:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public class ClasspathProperties {
    public static Properties loadDefaults() throws IOException {
        Properties properties = new Properties();

        try (InputStream input = ClasspathProperties.class
                .getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing classpath resource: /app.properties");
            }

            try (var reader = new InputStreamReader(
                    input, StandardCharsets.UTF_8)) {
                properties.load(reader);
            }
        }

        return properties;
    }
}
~~~

With getResourceAsStream on Class, a leading slash in the path indicates a path relative to the classpath root. If the leading slash is omitted, the path is resolved relative to the class's package. With ClassLoader, resource paths typically do not start with a slash.

Classpath resources are suitable for default configurations or read-only resources. Once an application is packaged into a JAR, a resource inside the JAR is not a regular filesystem file that can be overwritten in place. If operators need to change configuration per environment, place the file externally and allow the application to accept that file's path.

A common organization pattern:

- A file packaged on the classpath provides safe default values.
- An external file provides deployment-environment-specific configuration.
- JVM system properties or environment variables provide values that need to be overridden at launch.

## 6. Merging multiple configuration sources

Java does not enforce a universal precedence order between property files, system properties, and environment variables. The application must define this order.

For example, a policy might be:

1. Default values in code or a defaults table have the lowest priority.
2. An app.properties file packaged on the classpath overrides default values.
3. An external configuration file overrides the classpath file.
4. A JVM system property passed with the -D option overrides files.
5. An environment variable explicitly mapped to a configuration key has the highest priority.

This is a policy chosen by the application, not an automatic behavior of the Properties class. When applying it, clearly document the convention for mapping environment variable names to keys, how empty values are handled, and which sources are permitted to provide secrets.

Example of merging two file sources and one system property:

~~~java
Properties config = new Properties();
config.setProperty("service.timeout.seconds", "10");

// Load the default configuration file first.
try (var reader = Files.newBufferedReader(
        Path.of("app-defaults.properties"), StandardCharsets.UTF_8)) {
    config.load(reader);
}

// Load the external file afterward; matching keys will override previous values.
try (var reader = Files.newBufferedReader(
        Path.of("app.properties"), StandardCharsets.UTF_8)) {
    config.load(reader);
}

// Only override keys that the application explicitly supports.
String timeoutOverride = System.getProperty("service.timeout.seconds");
if (timeoutOverride != null) {
    config.setProperty("service.timeout.seconds", timeoutOverride);
}
~~~

Environment variables can be read via System.getenv. For example, the application can define that SERVICE_TIMEOUT_SECONDS overrides the service.timeout.seconds key. There is no universal rule in Java that automatically converts underscores to dots; the mapping must be written explicitly.

Do not dump all of System.getProperties into the application's configuration table indiscriminately. The JVM has many internal system properties and properties belonging to other libraries. Only read or transfer keys that the application explicitly supports.

When multiple sources have the same key, the source loaded last or the last setProperty operation retains its value in the main table. Keep the loading order easy to understand and testable.

## 7. Java system properties and the -D option

Java system properties are values associated with the current JVM. They can be read via System.getProperty:

~~~java
String javaVersion = System.getProperty("java.version");
String userHome = System.getProperty("user.home");
~~~

Properties can be passed when launching the JVM using the -D option, placed before the class name or application launch options:

~~~bash
java -Dservice.timeout.seconds=45 -Dservice.mode=production Main
~~~

In the program, read it with:

~~~java
String mode = System.getProperty("service.mode", "development");
~~~

System.setProperty allows setting a system property at runtime. This change affects other parts of the application and libraries sharing that JVM, so it should only be used intentionally. System.clearProperty removes a key. System.setProperties replaces the entire system properties table and can break assumptions made by other libraries; normally it should not be used to load an application configuration file.

System properties are not automatically persisted after the JVM exits. They are also not synonymous with operating system environment variables: System.getenv reads environment variables, whereas System.getProperty reads system properties.

## 8. Writing and updating property files

Properties can write its content to a file using store. Example of writing UTF-8:

~~~java
try (var writer = Files.newBufferedWriter(
        Path.of("app-generated.properties"), StandardCharsets.UTF_8)) {
    properties.store(writer, "Generated application settings");
}
~~~

With a UTF-8 Writer, character content is written using the Writer's encoding. If store(OutputStream) is used, the format compatible with load(InputStream) and ISO-8859-1/escaping rules apply.

You should understand the following characteristics before writing:

- store adds a comment and a timestamp at the top of the file.
- Properties does not guarantee preserving the original order of keys.
- Original comments and formatting of the file are not preserved like in a configuration editor.
- Values in the defaults table are not automatically written as direct values.
- Writing a file typically replaces the target content; you need to handle backups, file permissions, and write errors if the file is an active operational configuration.

Therefore, store is suitable for generating configuration files owned by the program. If you need to edit a human-managed file while preserving comments, order, and formatting, Properties is not a structure-preserving text editor. Use a controlled update process or a parser suited to that requirement.

Java also supports loadFromXML and storeToXML for the XML format of Properties. This is another option if the system already uses XML; for simple configuration files, the .properties format is usually more concise and easier to work with.

## 9. Type conversion and configuration validation

Properties stores values as String, so they must be converted and validated before use.

Some common conversions:

- Integer: Integer.parseInt.
- Long: Long.parseLong.
- Floating-point: Double.parseDouble.
- Boolean: Boolean.parseBoolean.
- Enum: Enum.valueOf after normalizing the value according to convention.
- Path: Path.of.
- Duration: parse a number with a unit or use Duration according to a defined format.

Boolean.parseBoolean only returns true if the string equals true, case-insensitively; all other strings, including typos, return false. If a configuration only accepts true or false, validate the string before converting.

Configuration should be validated right at application startup:

1. Verify that required keys exist.
2. Convert to the expected type and report an error if invalid.
3. Validate value ranges, such as a port within a valid range or a timeout greater than 0.
4. Validate relationships between keys, such as requiring certificate configuration when TLS is enabled.
5. Create an immutable configuration object for other components to use.

Do not let configuration errors surface only in the middle of a request or after the application has started receiving traffic. Error messages should clearly state the key name and the condition to satisfy, without logging secret values.

## 10. Lifecycle, sharing, and concurrency

Properties extends Hashtable, so basic operations on the table are synchronized. However, a multi-step sequence of operations does not automatically become an atomic transaction. For example, checking a key and then updating its value can be interleaved by another thread between the two operations.

If multiple threads read the configuration concurrently, a simple approach is to load and validate the configuration once at startup, then share a read-only snapshot or an immutable configuration object. If the application supports reloading, create a new table, validate it completely, and then replace the configuration reference using an appropriate synchronized operation. Avoid mutating individual keys in a table currently used by multiple components if they could observe a partially updated state.

Properties does not automatically watch for file changes and does not automatically reload when a file is modified. If automatic reloading is needed, the application must implement a watching mechanism, a polling schedule, or an update signal handler, and define how to handle an invalid new file.

## 11. Security when using configuration files

Configuration files may contain sensitive information such as database passwords, tokens, private key paths, or internal connection details. Treat configuration file read permissions as part of application security.

- Do not commit secrets to public repositories or sample configuration files.
- Use a secret manager or the deployment platform's secret provisioning mechanism for sensitive data.
- If secrets must be stored on disk, restrict file access permissions and protect backups.
- Do not print the entire Properties object or all system properties to logs.
- Do not include secrets in parameter names, error messages, or diagnostic output.
- Avoid passing passwords via the command line if the environment may expose process lists or command history.
- Only load files from trusted paths and sources; control write permissions so unauthorized users cannot alter the configuration.

Environment variables are also not inherently a secure place to store secrets. Choose a mechanism based on protection capabilities, access control, auditing, and how the platform provisions secrets.

## 12. Common errors and troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| getProperty returns null | Wrong key name, file not loaded, or incorrect resource path. | Check the key, file location, and resource opening result. |
| Garbled Vietnamese characters | Used load(InputStream) on a UTF-8 file or Reader with wrong encoding. | Use a UTF-8 Reader with load(Reader). |
| Value is always the default | Misspelled key in the file or override source not loaded. | Check loading order and key names. |
| File not found | Relative path resolved from an unexpected working directory. | Print user.dir when diagnosing or pass an absolute/configured path. |
| NumberFormatException | Numeric value contains letters, invalid format, or exceeds type limits. | Validate input and report the offending key name. |
| Boolean is always false | Boolean.parseBoolean only accepts true; all other values become false. | Explicitly validate true/false before converting. |
| Old configuration is still used | Properties does not auto-reload files. | Implement a reload mechanism or restart according to procedure. |
| Comments lost after writing | store only writes property pairs and generated comments, not original comments. | Avoid using Properties to edit human-owned files if formatting must be preserved. |
| Key overridden unexpectedly | Loading multiple files or calling setProperty in an unclear order. | Define and test precedence. |

When diagnosing, you can print the list of key names instead of printing values:

~~~java
properties.stringPropertyNames().stream()
        .sorted()
        .forEach(System.out::println);
~~~

Do not use this approach to log values that may contain sensitive information.

## 13. Checklist for designing configuration with Properties

- [ ] Key names are clear, consistent, and include units when needed.
- [ ] Determined whether the file resides on the classpath or outside the application.
- [ ] Encoding is explicitly chosen; UTF-8 files are read with a UTF-8 Reader.
- [ ] Default values and required keys are identified.
- [ ] Precedence order between files, system properties, and environment variables is defined.
- [ ] Type conversion and range validation are performed at startup.
- [ ] Cases of missing files, wrong encoding, or lack of read permissions are handled.
- [ ] Avoided logging or committing secrets and sensitive values to repositories.
- [ ] Decided how to update, reload, and share configuration across threads.
- [ ] Determined whether a file is program-generated or human-managed before using store.

Property files and java.util.Properties provide a simple way to separate configuration from source code. When encoding, paths, default values, override order, type validation, and security are clearly controlled, configuration becomes easy to deploy consistently across development machines, CI, and production.