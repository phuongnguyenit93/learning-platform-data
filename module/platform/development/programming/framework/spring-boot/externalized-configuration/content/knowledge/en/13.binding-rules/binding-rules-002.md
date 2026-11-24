# Comparing kebab-case, camelCase, and underscore across Spring Boot Configuration Sources

## Objectives

A Spring Boot application can declare the same configuration property in multiple forms:

~~~properties
# application.properties
app.http.read-timeout=5s
~~~

~~~yaml
# application.yml
app:
  http:
    readTimeout: 5s
~~~

~~~bash
# Environment variable
APP_HTTP_READTIMEOUT=5s
~~~

~~~bash
# Command-line argument
java -jar demo.jar --app.http.read-timeout=5s
~~~

These differently formatted names can be bound by **Spring Boot relaxed binding** to the same **readTimeout** field in a **@ConfigurationProperties** bean. However, **not every underscore is equivalent to a hyphen**, and not every property-reading API applies the exact same mechanism.

This topic explains how to compare **kebab-case**, **camelCase**, **underscore**, and **UPPER_UNDERSCORE** across sources: **.properties**, **YAML**, **environment variables**, **JVM system properties**, and **command-line arguments**. The lesson also clarifies the boundaries between name recognition, source precedence, object binding, list and map handling, and common deployment mistakes.

After studying this lesson, readers will be able to:

- Choose a **canonical property name** as the configuration contract.
- Write the corresponding environment variable accurately without guessing from camelCase.
- Distinguish the three naming forms in configuration files from the OS uppercase form.
- Understand why **app.http.read-timeout** and **app.http.read.timeout** should not be conflated.
- Know when to use **@ConfigurationProperties**, **@Value**, and **Environment**.
- Diagnose why an environment variable exists yet the bean does not receive its value.
- Control name collisions and overrides when the same property has multiple representations.

## 1. Vocabulary: four easily confused styles

First, distinguish the **logical property name**, **name presentation**, and **value source**.

| Name style | Example | Characteristics |
| --- | --- | --- |
| **kebab-case** | read-timeout | Lowercase, words separated by a hyphen |
| **camelCase** | readTimeout | First word lowercase, subsequent words start uppercase |
| **underscore / snake_case** | read_timeout | Lowercase, words separated by an underscore |
| **UPPER_UNDERSCORE** | READ_TIMEOUT | Uppercase, parts separated by an underscore |

In Spring Boot configuration, a property typically also uses **dots** to express a multi-level path:

~~~text
app.http.read-timeout
|   |    |
|   |    +-- property name at the http level
|   +------- http configuration level
+----------- app prefix
~~~

**read-timeout** is a compound name at the same level. **app.http** represents two distinct levels.

The dot **.** and the hyphen **-** do not have the same meaning. The underscore **_** plays a role that depends on the **configuration source**. In environment variables specifically, underscores are primarily used to represent **level boundaries** after conversion from the canonical property name.

### 1.1. Canonical property name

In Spring Boot documentation and configuration, use **canonical kebab-case** names:

~~~text
app.http.read-timeout
app.mail.retry-count
spring.main.log-startup-info
integration.catalog.base-url
~~~

This convention is typically:

- Lowercase.
- Dots separating each level.
- Hyphens separating words within a single property name.
- A prefix expressing functional scope, such as **app.http** or **integration.catalog**.

The canonical name is a **stable reference point** from which to write the corresponding names in YAML, `.properties`, environment variables, JVM options, and CLI arguments.

### 1.2. Java field names are not env var names

Java typically uses camelCase:

~~~java
public record HttpProperties(
        java.time.Duration readTimeout,
        int maxConnections
) {}
~~~

If the prefix is **app.http**, the two corresponding canonical properties are:

~~~text
app.http.read-timeout
app.http.max-connections
~~~

The canonical environment variable name is not simply inserting underscores before every uppercase letter in the Java field. Instead, convert the **full canonical name** according to the specific rules for environment variables.

## 2. A Java model used throughout the examples

Suppose the application declares:

~~~java
package example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(
        Http http,
        Mail mail
) {
    public record Http(
            Duration readTimeout,
            Duration connectTimeout,
            int maxConnections
    ) {}

    public record Mail(
            String senderName,
            int retryCount,
            boolean enabled
    ) {}
}
~~~

Register the configuration bean via scanning:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**@ConfigurationPropertiesScan** must cover the package containing the `AppProperties` record. **@EnableConfigurationProperties(AppProperties.class)** can be used if explicit registration is desired.

Full names to be bound:

| Java record path | Canonical property path |
| --- | --- |
| http().readTimeout() | app.http.read-timeout |
| http().connectTimeout() | app.http.connect-timeout |
| http().maxConnections() | app.http.max-connections |
| mail().senderName() | app.mail.sender-name |
| mail().retryCount() | app.mail.retry-count |
| mail().enabled() | app.mail.enabled |

This example will be used to compare sources. Importantly: **binding outcomes depend on both name and type**, so **5s** is converted to **Duration**, and **12** is converted to **int**.

## 3. Quick comparison table across sources

Taking the canonical key **app.http.read-timeout**:

| Source | Recommended spelling | Other spellings the relaxed binder may accept |
| --- | --- | --- |
| application.properties | app.http.read-timeout=5s | app.http.readTimeout=5s, app.http.read_timeout=5s |
| application.yml | app → http → read-timeout: 5s | app → http → readTimeout: 5s, app → http → read_timeout: 5s |
| JVM system property | -Dapp.http.read-timeout=5s | -Dapp.http.readTimeout=5s, -Dapp.http.read_timeout=5s |
| Command-line argument | --app.http.read-timeout=5s | Name variants may appear in the source, but canonical is preferred |
| Environment variable | **APP_HTTP_READTIMEOUT=5s** | Do not treat APP_HTTP_READ_TIMEOUT as the standard conversion formula |
| Java field/record component | **readTimeout** | This is a Java identifier, not file property syntax |

For `.properties` files, YAML, and Java system properties, Spring Boot supports **camelCase**, **kebab-case**, and **underscore notation** in relaxed binding contexts.

For **environment variables**, Spring Boot defines its own rules because variable names are managed by the operating system and deployment platform. Do not extrapolate directly from file formats to env vars.

Note two distinct levels:

1. **Canonical name for writing and documentation:** use kebab-case in property keys.
2. **Forms recognized by the relaxed binder:** may be more flexible depending on the source and reading API.

Flexibility during binding is not a recommendation to create multiple names for the same key in one file.

## 4. application.properties: kebab-case, camelCase, underscore

Canonical configuration example:

~~~properties
app.http.read-timeout=5s
app.http.connect-timeout=2s
app.http.max-connections=25
app.mail.sender-name=Operations
app.mail.retry-count=3
app.mail.enabled=true
~~~

When binding to `AppProperties`, Spring Boot locates the corresponding Java components. With this style of reading, variants like the following can be recognized:

~~~properties
app.http.readTimeout=5s
app.http.connectTimeout=2s
app.http.maxConnections=25
app.mail.senderName=Operations
app.mail.retryCount=3
app.mail.enabled=true
~~~

Or:

~~~properties
app.http.read_timeout=5s
app.http.connect_timeout=2s
app.http.max_connections=25
app.mail.sender_name=Operations
app.mail.retry_count=3
app.mail.enabled=true
~~~

These are examples of **relaxed binding at the @ConfigurationProperties layer**; it does not mean you should mix all three styles in a real file.

### 4.1. Why choose kebab-case in files?

A consistent file is easier to read:

~~~properties
app.http.read-timeout=5s
app.http.connect-timeout=2s
app.http.max-connections=25
~~~

compared to a mixed file:

~~~properties
app.http.readTimeout=5s
app.http.connect_timeout=2s
app.http.max-connections=25
~~~

Both can express the desired properties, but the second file makes it harder for readers to tell the official convention. When refactoring Java classes or writing operations documentation, the canonical name serves as a stable contract.

### 4.2. Do not declare equivalent name forms at the same time

Example to avoid:

~~~properties
app.http.read-timeout=5s
app.http.readTimeout=8s
app.http.read_timeout=10s
~~~

These are not three separate business parameters. They are three spellings likely to be bound by the binder to the same **readTimeout** field. Such a file creates ambiguity, making the outcome depend on how sources and the binder handle logically duplicate keys.

The operational rule should be **one logical property, one canonical name** per source. If there are genuinely three different values, define three paths expressing three distinct meanings.

### 4.3. Distinguish underscores in files from underscores in env vars

In a properties file, **read_timeout** is a compound-name variant that the binder can understand as **readTimeout**.

In environment variables, the canonical rule for the same key **app.http.read-timeout** is **APP_HTTP_READTIMEOUT**, not converting every word separator into an underscore.

Do not use `.properties` file conventions to guess environment variable names.

## 5. YAML: key syntax and indentation structure

The same values can be declared in YAML in canonical form:

~~~yaml
app:
  http:
    read-timeout: 5s
    connect-timeout: 2s
    max-connections: 25
  mail:
    sender-name: "Operations"
    retry-count: 3
    enabled: true
~~~

Or in camelCase:

~~~yaml
app:
  http:
    readTimeout: 5s
    connectTimeout: 2s
    maxConnections: 25
  mail:
    senderName: "Operations"
    retryCount: 3
    enabled: true
~~~

Or in underscore form:

~~~yaml
app:
  http:
    read_timeout: 5s
    connect_timeout: 2s
    max_connections: 25
  mail:
    sender_name: "Operations"
    retry_count: 3
    enabled: true
~~~

With **@ConfigurationProperties**, these forms are designed to bind flexibly into the corresponding Java model. Even so, using **kebab-case** in long-lived YAML documentation is usually easier to read and matches canonical names.

### 5.1. Indentation is not a naming style

Consider:

~~~yaml
app:
  http:
    read-timeout: 5s
~~~

The path is **app.http.read-timeout**.

But if written as:

~~~yaml
app:
  http:
    read:
      timeout: 5s
~~~

the path becomes **app.http.read.timeout**. Although they may sound similar, these are two different structures: one is a compound field name **readTimeout**, and the other is a nested object **read** containing a **timeout** field.

Another mistake:

~~~yaml
app:
  http:
    read-timeout: 5s
  connect-timeout: 2s
~~~

The **connect-timeout** field is now under **app**, no longer under **app.http**. The Binder does not automatically move it to **http.connectTimeout**.

**Separate two kinds of checks:** relaxed binding resolves **name variants of the same property**; it does not fix path structure errors caused by incorrect YAML indentation.

### 5.2. YAML keys are not Java fields

The syntax:

~~~yaml
app:
  http:
    max-connections: 25
~~~

does not require Java to have a field named with a hyphen. The Java field remains **maxConnections**. When Spring Boot binds, the configuration name is matched against the Java model by the binder mechanism.

Hyphens in YAML are not carried literally into variable names in Java source code.

### 5.3. Use YAML quotes in the right places

If a key or value contains special characters, YAML has its own parser rules. For example, Map keys with bracket notation must be quoted:

~~~yaml
app:
  tenants:
    "[tenant.eu]":
      endpoint: "https://eu.example.test"
~~~

YAML quotes do not alter the relaxed binding algorithm for ordinary keys, but they determine whether the YAML parser reads the key and value properly.

## 6. Environment variables: three canonical conversion steps

This is the most error-prone area when deploying via shell, Docker, or Kubernetes.

To convert from a canonical property name to an environment variable name according to Spring Boot's rules:

1. **Replace dots (.) with underscores (_).**
2. **Remove hyphens (-).**
3. **Convert the remaining name to uppercase.**

Step-by-step example:

~~~text
app.http.read-timeout
  |
  | "." to "_"
  v
app_http_read-timeout
  |
  | remove "-"
  v
app_http_readtimeout
  |
  | uppercase
  v
APP_HTTP_READTIMEOUT
~~~

Canonical result:

~~~bash
APP_HTTP_READTIMEOUT=5s java -jar demo.jar
~~~

### 6.1. Common conversion table

| Canonical property | Environment variable |
| --- | --- |
| server.port | SERVER_PORT |
| spring.profiles.active | SPRING_PROFILES_ACTIVE |
| spring.datasource.url | SPRING_DATASOURCE_URL |
| spring.main.log-startup-info | SPRING_MAIN_LOGSTARTUPINFO |
| management.endpoints.web.exposure.include | MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE |
| app.http.read-timeout | APP_HTTP_READTIMEOUT |
| app.http.connect-timeout | APP_HTTP_CONNECTTIMEOUT |
| app.http.max-connections | APP_HTTP_MAXCONNECTIONS |
| app.mail.sender-name | APP_MAIL_SENDERNAME |
| app.mail.retry-count | APP_MAIL_RETRYCOUNT |
| app.mail.enabled | APP_MAIL_ENABLED |
| integration.catalog.base-url | INTEGRATION_CATALOG_BASEURL |
| integration.catalog.retry.max-attempts | INTEGRATION_CATALOG_RETRY_MAXATTEMPTS |

In particular, **spring.main.log-startup-info** converts to **SPRING_MAIN_LOGSTARTUPINFO**, not **SPRING_MAIN_LOG_STARTUP_INFO**, if you follow the canonical conversion.

### 6.2. Underscores in environment variables typically represent levels

Compare:

~~~text
app.http.read-timeout
     --> APP_HTTP_READTIMEOUT

app.http.read.timeout
     --> APP_HTTP_READ_TIMEOUT
~~~

In the second example, the dot between **read** and **timeout** creates a separate level, so the env name contains an additional underscore.

This is why you cannot simply "convert camelCase to UPPER_SNAKE_CASE" without reading the property structure. The Java field **readTimeout** usually corresponds to **read-timeout**; the two words **read** and **timeout** are not automatically two levels in Spring's Environment.

### 6.3. One env name can correspond to multiple canonical spellings

Because hyphens are removed, the following names yield the same env name:

~~~text
app.service.max-retries
    -> APP_SERVICE_MAXRETRIES

app.service.maxretries
    -> APP_SERVICE_MAXRETRIES
~~~

This creates a **name collision risk**. If a configuration model intentionally declares two properties that differ only in hyphen placement, supplying them via environment variables may make them indistinguishable.

Avoid designing keys like that. Instead, use names with distinct meanings and clear level structures.

### 6.4. Variable set properly yet the application still does not receive it?

A variable declared on a machine is not necessarily passed to the running Java process. Causes include:

- Setting the variable in a different terminal from the one running the application.
- The IDE or service manager uses a separate environment configuration.
- A Docker entrypoint script does not forward the environment properly.
- A Kubernetes ConfigMap exists but is not referenced in the Pod.
- The variable name does not follow the canonical conversion or has the wrong prefix.
- A higher-precedence source such as a JVM system property/CLI argument overrides the value.
- The value is present but cannot be converted to the Java type.

To verify accurately, inspect the process environment, the Spring Environment, and the bound bean—not just a single line in a deployment YAML.

## 7. JVM system properties: preserve regular property names

A JVM system property is supplied with **-D**, placed before **-jar**:

~~~bash
java -Dapp.http.read-timeout=7s -jar demo.jar
~~~

With the example configuration, Spring Boot can bind this value to **readTimeout**.

Relaxed binding for **system properties** supports name forms such as:

~~~text
app.http.read-timeout
app.http.readTimeout
app.http.read_timeout
~~~

However, when writing run commands, use the canonical name:

~~~bash
java -Dapp.http.read-timeout=7s -jar demo.jar
~~~

**Note:** JVM system properties and OS environment variables are two separate sources:

~~~bash
APP_HTTP_READTIMEOUT=5s java -Dapp.http.read-timeout=7s -jar demo.jar
~~~

In the command above:

- **APP_HTTP_READTIMEOUT** is an environment variable of the process.
- **app.http.read-timeout** is a JVM system property.
- In Spring Boot's standard source order, the system property **7s** has higher precedence than the environment variable **5s**.

The fact that two sources can bind to the same Java field does not make them a single source.

### 7.1. Do not confuse -DUPPER_UNDERSCORE with environment variables

The command:

~~~bash
java -DAPP_HTTP_READTIMEOUT=5s -jar demo.jar
~~~

puts the name **APP_HTTP_READTIMEOUT** into the JVM system properties list; it does **not** create an OS environment variable of that name. Java can read the literal name via **System.getProperty("APP_HTTP_READTIMEOUT")**, but you should not design a configuration contract around using env-var style as a JVM property.

Choose the right mechanism for the deployment source: **-Dapp.http.read-timeout** or **APP_HTTP_READTIMEOUT**.

## 8. Command-line arguments: prefer canonical kebab-case

Spring Boot typically reads application arguments of the form:

~~~bash
java -jar demo.jar --app.http.read-timeout=9s
~~~

The value enters Spring's command-line property source. The Binder can bind that key to the **readTimeout** field.

Although some name variants may still be recognized during binding, the recommended CLI style is:

~~~text
--app.http.read-timeout=9s
--app.http.max-connections=30
--app.mail.retry-count=4
~~~

This aligns with `application.yml`/`.properties` and deployment documentation.

### 8.1. CLI arguments are not the same as JVM options

Correct way to pass a JVM property:

~~~bash
java -Dapp.http.read-timeout=7s -jar demo.jar
~~~

Correct way to pass a Spring Boot application argument:

~~~bash
java -jar demo.jar --app.http.read-timeout=9s
~~~

Placing **-D** after the JAR name may cause it to be treated as an ordinary application argument rather than a JVM option. Do not rely on a value accidentally interpreted by a specific app to conclude that sources are equivalent.

### 8.2. Do not apply env var rules to CLI names

For example:

~~~text
--APP_HTTP_READTIMEOUT=9s
~~~

is not the canonical syntax of a Spring Boot option. When running commands, use **--app.http.read-timeout=9s**. The **--** prefix does not make Spring automatically treat every uppercase-with-underscore name through the same lookup path as an OS environment variable.

## 9. Comparing the same property across sources

Suppose the packaged file is:

~~~yaml
app:
  http:
    read-timeout: 5s
~~~

At the same time, the operator supplies:

~~~bash
APP_HTTP_READTIMEOUT=8s java -Dapp.http.readTimeout=10s -jar demo.jar   --app.http.read-timeout=12s
~~~

Under the standard source mechanism:

| Source | Name used | Value |
| --- | --- | --- |
| YAML | app.http.read-timeout | 5s |
| Environment variable | APP_HTTP_READTIMEOUT | 8s |
| JVM system property | app.http.readTimeout | 10s |
| CLI argument | app.http.read-timeout | **12s** |

With **@ConfigurationProperties**, the corresponding keys are understood by the binder as the same logical property. The final value of **readTimeout** is **12 seconds** if no higher-precedence PropertySource exists beyond those considered.

This is a combination of **two independent mechanisms**:

1. **Relaxed binding:** recognizes names corresponding to the Java field.
2. **PropertySource precedence:** selects the effective value across sources.

If you want to test relaxed binding in isolation, supply only one value source at a time. Supplying all four sources at once reflects precedence as well.

## 10. Do not confuse a property level with a compound word

This is essential to understand before converting between kebab-case, camelCase, and underscore.

The three representations below can target the same Java field **readTimeout** inside a nested `Http`:

~~~text
app.http.read-timeout
app.http.readTimeout
app.http.read_timeout
~~~

But the path:

~~~text
app.http.read.timeout
~~~

represents a different configuration branch. It aligns with a model like:

~~~java
public record Http(Read read) {
    public record Read(java.time.Duration timeout) {}
}
~~~

rather than:

~~~java
public record Http(java.time.Duration readTimeout) {}
~~~

### 10.1. Mistakes from manually splitting camelCase

Seeing the Java field **maxConnections**, an author might automatically produce:

~~~text
APP_HTTP_MAX_CONNECTIONS
~~~

This name is closer to the path **app.http.max.connections**.

For a single field **maxConnections**, the canonical name is usually **app.http.max-connections**, and the canonical environment variable is:

~~~text
APP_HTTP_MAXCONNECTIONS
~~~

**Correct workflow:** determine the property tree → write the canonical name → convert to env. Do not start from uppercase letters in Java names and guess the structure.

### 10.2. Java nested classes and YAML nested mappings

Java:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(Http http) {
    public record Http(java.time.Duration readTimeout) {}
}
~~~

Correct YAML:

~~~yaml
app:
  http:
    read-timeout: 5s
~~~

If YAML is written as:

~~~yaml
app:
  http:
    read:
      timeout: 5s
~~~

it creates an extra **read** level. Relaxed binding does not automatically merge those two levels to populate the `readTimeout` field. When troubleshooting, inspect the prefix and object tree, not only the final key name.

## 11. @ConfigurationProperties is the canonical relaxed binding context

A configuration bean:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
        Duration readTimeout,
        Duration connectTimeout,
        int maxConnections
) {}
~~~

Files can use kebab-case, camelCase, or underscore according to source rules, while Java stays camelCase.

YAML example:

~~~yaml
app:
  http:
    read-timeout: 5s
    connect-timeout: 2s
    max-connections: 25
~~~

And env:

~~~bash
APP_HTTP_READTIMEOUT=8s APP_HTTP_MAXCONNECTIONS=40 java -jar demo.jar
~~~

Binding result in a typical setup:

~~~text
readTimeout    = Duration 8 seconds
connectTimeout = Duration 2 seconds
maxConnections = 40
~~~

The record itself does not need to define fields named **READTIMEOUT**, **read_timeout**, or **read-timeout**. The binder mechanism maps property names to the Java structure.

### 11.1. Prefixes should be canonical

When using **@ConfigurationProperties(prefix = "app.http")**, write the prefix cleanly in canonical kebab-case with dots. A prefix is not a place to arbitrarily turn into an environment variable name or capitalize freely.

Example of a prefix with a compound name:

~~~java
@ConfigurationProperties(prefix = "integration.catalog-client")
public record CatalogClientProperties(String baseUrl) {}
~~~

Canonical property:

~~~text
integration.catalog-client.base-url
~~~

Environment variable name:

~~~text
INTEGRATION_CATALOGCLIENT_BASEURL
~~~

The two hyphens in the canonical name are removed when converting to env; the dots become underscores.

### 11.2. Relaxed binding does not guarantee valid values

Example:

~~~bash
APP_HTTP_MAXCONNECTIONS=not-a-number java -jar demo.jar
~~~

The name is right, but the Java field is `int`. The Binder cannot convert **not-a-number** into an integer. This error belongs to **type conversion/binding**, not a naming rule error.

For `Duration`, use values such as **250ms**, **5s**; for `boolean`, use formats supported by the converter. Getting the property name right is only one step.

## 12. @Value and placeholders have differences

When retrieving a single property, applications often use:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
class HttpSettings {

    @Value("${app.http.read-timeout:5s}")
    private String readTimeout;
}
~~~

Spring Boot recommends using **canonical kebab-case placeholder names** in `@Value`. When the name is written canonically, Boot's lookup mechanism can apply name-variant rules similar to configuration binding.

Avoid writing:

~~~java
@Value("${app.http.readTimeout:5s}")
private String readTimeout;
~~~

and assuming every source will be searched identically to how the `@ConfigurationProperties` binder handles canonical names. A placeholder is not an arbitrary alias for every possible name format appearing in all PropertySources.

### 12.1. @Value does not replace @ConfigurationProperties

`@Value` is suitable when only a few values are needed. If there are dozens of nested fields or Lists/Maps, many `@Value` annotations repeat the prefix, are hard to validate, and reduce modeling clarity.

Example:

~~~java
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
        java.time.Duration readTimeout,
        int maxConnections
) {}
~~~

is generally easier to maintain than two `@Value` fields scattered across multiple services. Validation and tests can be added directly on the record.

### 12.2. Placeholders have defaults, which do not fix wrong names

~~~java
@Value("${app.http.read-timeout:5s}")
private String timeout;
~~~

If the environment variable is given a non-matching name, the placeholder may pick **5s**. The application running without error does not prove the override variable was picked up.

To diagnose, try a clearly distinguishable non-default value, read `Environment`, and compare with the bound bean. Do not rely on "no error reported" as proof of correct binding.

## 13. Environment.getProperty and direct reading APIs

There are three direct reading paths to distinguish:

~~~java
String directEnv = System.getenv("APP_HTTP_READTIMEOUT");
String systemProperty = System.getProperty("app.http.read-timeout");
String springProperty = environment.getProperty("app.http.read-timeout");
~~~

- **System.getenv** reads only the process's environment variables by the exact passed name.
- **System.getProperty** reads JVM system properties.
- **Environment.getProperty** looks up through the Spring `Environment` and the application's PropertySources.

Alongside these, **@ConfigurationProperties** uses a dedicated binder to bind structures and convert types.

You cannot assume a camelCase, underscore, or UPPER_UNDERSCORE name will be resolved identically by all of the APIs above. They use different lookup and name-processing logic.

### 13.1. Environment is not synonymous with calling the binder

Example:

~~~java
String a = environment.getProperty("app.http.read-timeout");
String b = environment.getProperty("app.http.readTimeout");
~~~

In some circumstances and sources, these two queries may yield different results. For Spring Boot configuration, use the **canonical name** in property-lookup code and verify the actual source.

If you need to bind a whole group of fields, **@ConfigurationProperties** is the API designed for relaxed binding and nested objects.

### 13.2. Printing configuration values safely

A bean that inspects non-sensitive values:

~~~java
import java.time.Duration;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ConfigProbe implements ApplicationRunner {

    private final Environment environment;
    private final HttpProperties http;

    ConfigProbe(Environment environment, HttpProperties http) {
        this.environment = environment;
        this.http = http;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("env raw = "
                + System.getenv("APP_HTTP_READTIMEOUT"));
        System.out.println("spring property = "
                + environment.getProperty("app.http.read-timeout"));
        Duration timeout = http.readTimeout();
        System.out.println("bound Duration = " + timeout);
    }
}
~~~

Depending on which source supplies the value, the three lines may differ. A `Duration` of **8s** printed from Java may display as **PT8S**, differing from the original string while representing the same duration.

Do not print passwords, API tokens, or the entire contents of PropertySources for debugging. For secrets, verify configuration via non-sensitive metadata.

## 14. Environment variables across operating systems and deployment platforms

### 14.1. Linux / macOS shell

~~~bash
export APP_HTTP_READTIMEOUT=8s
export APP_HTTP_MAXCONNECTIONS=40
java -jar demo.jar
~~~

Or set for a single command:

~~~bash
APP_HTTP_READTIMEOUT=8s APP_HTTP_MAXCONNECTIONS=40 java -jar demo.jar
~~~

In Unix shells, variable names can be case-sensitive. Standardize on uppercase to avoid having both **APP_HTTP_READTIMEOUT** and **app_http_readtimeout** in the environment with unclear meaning.

### 14.2. Windows PowerShell

~~~powershell
$env:APP_HTTP_READTIMEOUT = "8s"
$env:APP_HTTP_MAXCONNECTIONS = "40"
java -jar demo.jar
~~~

The variables must exist in the environment of the actual JVM process. Changing a variable in another terminal after the JVM has started generally does not update already-bound beans.

### 14.3. Docker

~~~bash
docker run --rm   -e APP_HTTP_READTIMEOUT=8s   -e APP_HTTP_MAXCONNECTIONS=40   example/demo:latest
~~~

Docker injects environment variables into the container at runtime. Spring Boot uses the env names to resolve properties. Choosing the exact canonical names lets the image be reused across environments without modifying the YAML inside the JAR.

### 14.4. Kubernetes

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: demo
  template:
    metadata:
      labels:
        app: demo
    spec:
      containers:
        - name: demo
          image: example/demo:latest
          env:
            - name: APP_HTTP_READTIMEOUT
              value: "8s"
            - name: APP_HTTP_MAXCONNECTIONS
              value: "40"
~~~

Kubernetes does not know that the Java record has a **readTimeout** field. It only passes env names and values into the process. Spring Boot handles binding, conversion, and source ordering.

A ConfigMap or Secret must be referenced via **env**, **envFrom**, or an appropriate mount mechanism for data to reach the application. Do not treat the existence of a resource in the cluster as proof that the Java process received the right variable.

### 14.5. Why should you not try multiple env variants at once?

An ineffective debugging habit is setting simultaneously:

~~~text
APP_HTTP_READTIMEOUT
APP_HTTP_READ_TIMEOUT
app_http_readTimeout
~~~

with different values to "see which one Spring picks up". This makes configuration unpredictable and dependent on the OS or how the binder chooses among similar keys.

Instead, identify **app.http.read-timeout** as canonical, set **only APP_HTTP_READTIMEOUT**, restart, and inspect the result.

## 15. List: indexes and underscores have additional rules

For lists, properties look like:

~~~text
app.clients[0].base-url
app.clients[1].base-url
~~~

Because a List contains indexed elements, the environment variable conversion surrounds the index with underscores:

~~~text
APP_CLIENTS_0_BASEURL
APP_CLIENTS_1_BASEURL
~~~

YAML example:

~~~yaml
app:
  clients:
    - name: catalog
      base-url: "https://catalog.example.test"
      retry-count: 2
    - name: billing
      base-url: "https://billing.example.test"
      retry-count: 4
~~~

Java:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record ClientCollection(List<Client> clients) {
    public record Client(
            String name,
            String baseUrl,
            int retryCount
    ) {}
}
~~~

Canonical env names for the fields:

~~~text
APP_CLIENTS_0_NAME
APP_CLIENTS_0_BASEURL
APP_CLIENTS_0_RETRYCOUNT
APP_CLIENTS_1_NAME
APP_CLIENTS_1_BASEURL
APP_CLIENTS_1_RETRYCOUNT
~~~

### 15.1. Underscores play two roles in List env names

In **APP_CLIENTS_0_BASEURL**:

- The underscore between `APP` and `CLIENTS` represents a dot in the path.
- The **_0_** part represents the **[0]** index of the List.
- **BASEURL** comes from the compound name **base-url**, with the hyphen removed.

Do not write **APP_CLIENTS_0_BASE_URL** and treat it as the canonical conversion of **app.clients[0].base-url**. It has an extra underscore that does not come from a dot or an index in the canonical property.

### 15.2. Lists across multiple sources can be replaced

A note independent of naming: when multiple PropertySources configure the same List, Spring Boot generally uses the list from the higher-precedence source rather than appending all elements.

Setting **APP_CLIENTS_0_NAME** can change how the binder constructs the List rather than necessarily updating only one field of element 0 while preserving all other elements from YAML. When overriding a complex List via env vars, verify the entire bound result and supply configuration for all desired elements.

## 16. Maps and dynamic keys: relaxed binding is not an unconditional transformation

Suppose the application has a Map:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record RegionProperties(Map<String, Region> regions) {
    public record Region(String endpoint, int weight) {}
}
~~~

YAML:

~~~yaml
app:
  regions:
    asia:
      endpoint: "https://asia.example.test"
      weight: 50
    europe:
      endpoint: "https://europe.example.test"
      weight: 25
~~~

Paths:

~~~text
app.regions.asia.endpoint
app.regions.asia.weight
app.regions.europe.endpoint
app.regions.europe.weight
~~~

Here **asia** and **europe** are **dynamic Map keys**, not fixed fields of the `RegionProperties` record.

### 16.1. When a Map key contains a dot

If the actual key is **tenant.eu**, bracket notation may be needed:

~~~yaml
app:
  tenants:
    "[tenant.eu]":
      endpoint: "https://eu.example.test"
~~~

In `.properties`:

~~~properties
app.tenants.[tenant.eu].endpoint=https://eu.example.test
~~~

Square brackets indicate that **tenant.eu** should be preserved as the Map key. Without them, the dot could become a nested path boundary, depending on the Map type being bound.

### 16.2. When a Map key contains special characters

A key with slashes such as **/internal/path** can be expressed as:

~~~yaml
app:
  headers:
    "[/internal/path]": "enabled"
~~~

There is no simple rule converting **arbitrary keys with dots, uppercase letters, and slashes** to env vars that guarantees preserving every character. For Maps with non-standard dynamic keys, use YAML/properties configuration with bracket notation or a source that supports expressing keys per contract.

### 16.3. Separating canonical keys from Map data

A name like **app.regions.asia.endpoint** contains:

- **app.regions**: fixed path.
- **asia**: data key in the Map.
- **endpoint**: field of the value object.

Do not assume the binder normalizes Map key values identically to camelCase fields. Preserving keys in a Map is a separate concern, especially with `Map<String, Object>` and `Map<String, String>`.

## 17. Other sources can also contain properties

Beyond the basic sources, Spring Boot can read **Config Data imports**, profile-specific files, configtree, Java system properties, command-line arguments, and custom PropertySources added by applications or libraries.

Import example:

~~~yaml
spring:
  config:
    import: "optional:file:./config/override.yml"
~~~

If `override.yml` contains:

~~~yaml
app:
  http:
    read-timeout: 15s
~~~

then it contributes another Config Data document with the canonical name **app.http.read-timeout**. An imported file does not require new key names; relaxed binding still applies when its properties are bound to Java.

Similarly, a configtree that mounts secrets as files named after properties does not alter the `@ConfigurationProperties` prefix. Distinguish how a source represents keys from the binder rules that resolve names.

Third-party resolvers or loaders can insert keys into Spring's Environment with their own conventions. Do not guess that a key from a custom source necessarily follows all OS env var transformation rules; verify the actual name placed into the PropertySource.

## 18. Source precedence does not change naming rules

Suppose the same property appears in both a file and the environment:

~~~yaml
# application.yml
app:
  http:
    read-timeout: 5s
~~~

~~~bash
APP_HTTP_READTIMEOUT=8s java -jar demo.jar
~~~

In a standard Spring Boot setup, env overrides Config Data, so `readTimeout = 8 seconds`.

If you add:

~~~bash
APP_HTTP_READTIMEOUT=8s java -Dapp.http.read-timeout=10s -jar demo.jar
~~~

then the JVM system property `10s` can beat env `8s`.

If you add:

~~~bash
APP_HTTP_READTIMEOUT=8s java -Dapp.http.read-timeout=10s -jar demo.jar   --app.http.read-timeout=12s
~~~

then CLI `12s` can beat both.

| Operation | Question it answers |
| --- | --- |
| Convert kebab-case ↔ camelCase ↔ underscore | Which names can bind to the field? |
| Convert canonical to UPPER_UNDERSCORE | What should the environment variable be named? |
| PropertySource precedence | Across multiple sources, which value wins? |
| Type conversion | Which Java type will the String value become? |
| Validation | Is the bound value valid? |

Do not confuse a **wrong variable name** error with **another source winning**. Both can cause the application to receive an unexpected value, but the troubleshooting approach is different.

## 19. Uppercase, lowercase, and portability across environments

In configuration files, canonical names use lowercase. In Java, fields use camelCase. In OS env, the canonical rule converts to uppercase.

~~~text
app.worker.max-retries  // canonical
maxRetries             // Java component
APP_WORKER_MAXRETRIES  // OS environment variable
~~~

On many Unix systems, env var names are case-sensitive; on Windows, different rules apply. Do not design configurations that rely on two variables differing only in casing existing simultaneously.

In addition, some deployment tools enforce constraints on environment variable names, particularly allowed characters. Spring Boot's **UPPER_UNDERSCORE** form is widely compatible with shells and orchestration systems.

For keys containing special characters, do not try to invent arbitrary environment variable names that violate platform rules. Move them to a config file or another structured data source.

## 20. Practical conversion table for multiple properties

A reference table for writing operations documentation:

| Java path | Canonical | Recommended app.properties/YAML | Env var |
| --- | --- | --- | --- |
| http.readTimeout | app.http.read-timeout | app.http.read-timeout | APP_HTTP_READTIMEOUT |
| http.connectTimeout | app.http.connect-timeout | app.http.connect-timeout | APP_HTTP_CONNECTTIMEOUT |
| http.maxConnections | app.http.max-connections | app.http.max-connections | APP_HTTP_MAXCONNECTIONS |
| mail.senderName | app.mail.sender-name | app.mail.sender-name | APP_MAIL_SENDERNAME |
| mail.retryCount | app.mail.retry-count | app.mail.retry-count | APP_MAIL_RETRYCOUNT |
| mail.enabled | app.mail.enabled | app.mail.enabled | APP_MAIL_ENABLED |
| security.tokenTtl | app.security.token-ttl | app.security.token-ttl | APP_SECURITY_TOKENTTL |
| cache.timeToLive | app.cache.time-to-live | app.cache.time-to-live | APP_CACHE_TIMETOLIVE |
| client.pool.maxSize | app.client.pool.max-size | app.client.pool.max-size | APP_CLIENT_POOL_MAXSIZE |
| batch.jobs[0].maxItems | app.batch.jobs[0].max-items | app.batch.jobs[0].max-items | APP_BATCH_JOBS_0_MAXITEMS |

In the file column, YAML can use a nested tree rather than writing the whole key on one line, while the logical path stays the same.

This table can be expressed as a deployment guideline: **developers publish the canonical property; operations take names from the env var column; do not invent conversions from programming-language habits**.

## 21. Four typical variable-naming mistakes

### 21.1. Confusing READ_TIMEOUT with READTIMEOUT

Java has `readTimeout`. Canonical:

~~~text
app.http.read-timeout
~~~

Canonical name:

~~~text
APP_HTTP_READTIMEOUT
~~~

Wrongly guessed name by splitting camelCase:

~~~text
APP_HTTP_READ_TIMEOUT
~~~

Fix: start from the canonical name, not from the Java field by inserting underscores between words.

### 21.2. Forgetting prefix levels

Java:

~~~java
@ConfigurationProperties(prefix = "integration.catalog")
public record CatalogProperties(String baseUrl) {}
~~~

Canonical is **integration.catalog.base-url**, not **catalog.base-url**.

Canonical env:

~~~text
INTEGRATION_CATALOG_BASEURL
~~~

If you use **CATALOG_BASEURL**, the binder will not infer the missing prefix part.

### 21.3. Adding a dot inside a compound name

Intended:

~~~text
app.mail.retry-count
~~~

But the file says:

~~~properties
app.mail.retry.count=3
~~~

This is a different path. If Java has a `retryCount` field directly inside `Mail`, fix the property name to match the structure instead of just turning camelCase into underscores.

### 21.4. Thinking defaults hide every mistake

Bean uses:

~~~java
@Value("${app.mail.retry-count:3}")
private int retryCount;
~~~

A misnamed env var can cause the default `3` to be used. That does not prove the override worked. Try reading **Environment.getProperty("app.mail.retry-count")** and inspecting the source data.

If the property is found but its value is **abc**, the default will not fix an `int` conversion error either.

## 22. Data errors that are not naming errors

### 22.1. Incompatible value type

~~~bash
APP_HTTP_MAXCONNECTIONS=many java -jar demo.jar
~~~

The name is right, but **many** cannot convert to `int`. Fix the value or verify the appropriate Java type.

### 22.2. Confusing empty strings with undeclared properties

~~~bash
APP_MAIL_SENDERNAME='' java -jar demo.jar
~~~

An empty string is a value that can exist in the environment. It is not automatically identical to an absent variable. If a required value cannot be blank, use validation.

### 22.3. Null in YAML does not always erase other sources

~~~yaml
app:
  mail:
    sender-name: null
~~~

A `null` scalar behaves according to Config Data loading and how the PropertySource provides data. Do not assume `null` necessarily erases a value coming from a lower-precedence source.

When you want to disable a feature, use an explicit flag like **enabled: false**. When a field is required, use validation to catch missing data.

### 22.4. Only one environment fails

If `dev` works but `prod` fails, do not jump to concluding `prod` has a different YAML parser. Check:

- Active profiles.
- Profile-specific files, locations, and imports.
- Environment variables in the production process.
- JVM options and command-line args.
- Spring `Environment` and `@ConfigurationProperties` outputs.
- Configuration files with the same logical name written in different styles.

In particular, environment variables often appear in production via Docker/Kubernetes, so a naming-conversion bug easily surfaces only upon deployment.

## 23. Diagnostic: trace source → canonical key → Java field

When a Java field receives the wrong value, trace it in order:

1. **Identify the Java field and prefix.** For example, `HttpProperties` record has prefix `app.http` and field `readTimeout`.
2. **Write the canonical name.** `app.http.read-timeout`.
3. **Identify sources that might contain the key.** `.properties`, YAML, env, JVM, CLI, imports, and profiles.
4. **Compare the spelling per source.** Env must be `APP_HTTP_READTIMEOUT`.
5. **Check the process environment.** Did the variable actually reach the JVM?
6. **Read the Environment value.** Use the canonical key to observe the resolved value.
7. **Read the `@ConfigurationProperties` bean.** Did the Binder convert the type properly and assign the right field?
8. **Check validation/conversion if errors occur.** A correctly named value of the wrong type must be addressed at the data layer.
9. **Check PropertySource order.** A higher-precedence source may decide the result.

A snippet to inspect non-sensitive sources:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@Component
class PropertySourceNames implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    PropertySourceNames(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(org.springframework.boot.ApplicationArguments args) {
        System.out.println("app.http.read-timeout = "
                + environment.getProperty("app.http.read-timeout"));

        for (PropertySource<?> source : environment.getPropertySources()) {
            System.out.println(source.getName());
        }
    }
}
~~~

Print only PropertySource names and non-sensitive sample keys. Do not log all values because configuration sources can contain passwords, tokens, or private data.

### 23.1. When should you look inside the Binder?

If `Environment` already has the right property yet `@ConfigurationProperties` does not receive it, the cause may lie in:

- Wrong prefix.
- Nested structure at the wrong level.
- Missing configuration bean registration.
- Failed conversion.
- Constructor binding or setter binding incompatible with the class.
- Validation rejecting the value.
- List/Map having an unexpected structure.

Do not try to "fix" env naming when the root cause is the Java structure or data type.

## 24. Example configuration class with validation

A way to combine naming with validation:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
        @NotNull Duration readTimeout,
        @NotNull Duration connectTimeout,
        @Min(1) int maxConnections
) {}
~~~

Configuration:

~~~yaml
app:
  http:
    read-timeout: 5s
    connect-timeout: 2s
    max-connections: 25
~~~

Environment variables:

~~~bash
APP_HTTP_READTIMEOUT=10s APP_HTTP_MAXCONNECTIONS=40 java -jar demo.jar
~~~

If a compatible validation provider is configured, constraints help detect missing timeouts or invalid `maxConnections` at startup.

Validation annotations do not change naming rules; they only validate **values after the binder processes them**. For a Spring Boot project using Jakarta Validation, include the appropriate dependency for constraints to take effect.

## 25. Practice exercise 1: convert canonical names to env vars

Given the list:

~~~text
1. server.port
2. spring.main.log-startup-info
3. app.mail.retry-count
4. app.http.read-timeout
5. app.cache.time-to-live
6. integration.billing.connect-timeout
7. app.servers[0].base-url
~~~

Answers according to Spring Boot's conversion rules:

~~~text
1. SERVER_PORT
2. SPRING_MAIN_LOGSTARTUPINFO
3. APP_MAIL_RETRYCOUNT
4. APP_HTTP_READTIMEOUT
5. APP_CACHE_TIMETOLIVE
6. INTEGRATION_BILLING_CONNECTTIMEOUT
7. APP_SERVERS_0_BASEURL
~~~

This exercise forces you to distinguish dots, hyphens, and List indexes. If your answer contains **_RETRY_COUNT**, **_READ_TIMEOUT**, or **_BASE_URL**, go back to the three canonical steps instead of inserting underscores between English words.

## 26. Practice exercise 2: three styles in files, one Java field

Java:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(String senderName, int retryCount) {}
~~~

Three `application.properties` versions, each used independently:

~~~properties
# A - kebab-case
app.mail.sender-name=Team A
app.mail.retry-count=2
~~~

~~~properties
# B - camelCase
app.mail.senderName=Team B
app.mail.retryCount=3
~~~

~~~properties
# C - underscore
app.mail.sender_name=Team C
app.mail.retry_count=4
~~~

In `@ConfigurationProperties` relaxed binding, all versions target the same two fields **senderName** and **retryCount**, with different values in each file.

Question: when choosing one version as the repository standard, which should you choose? **A**, because canonical kebab-case is easy to document and convert to other sources.

Do not place A, B, and C in the same file and use the result to infer a "naming-style precedence" order. That is not the purpose of relaxed binding.

## 27. Practice exercise 3: distinguish one level from two levels

Two paths:

~~~text
app.task.max-retries
app.task.max.retries
~~~

Env conversion:

~~~text
APP_TASK_MAXRETRIES
APP_TASK_MAX_RETRIES
~~~

Write the appropriate Java model for each case.

Single compound field case:

~~~java
@ConfigurationProperties(prefix = "app.task")
public record TaskProperties(int maxRetries) {}
~~~

Nested level case:

~~~java
@ConfigurationProperties(prefix = "app.task")
public record TaskProperties(Max max) {
    public record Max(int retries) {}
}
~~~

Purpose: understand that **the underscore between MAX and RETRIES** in the env name appears when the canonical name contains a **dot**, not when it only contains a hyphen.

## 28. Practice exercise 4: reading values across multiple sources

`application.yml`:

~~~yaml
app:
  mail:
    retry-count: 2
~~~

Environment variable and argument:

~~~bash
APP_MAIL_RETRYCOUNT=4 java -Dapp.mail.retryCount=6 -jar demo.jar   --app.mail.retry-count=8
~~~

Questions:

- What does `System.getenv("APP_MAIL_RETRYCOUNT")` return?
- What does `System.getProperty("app.mail.retryCount")` return?
- What does `MailProperties.retryCount()` receive, assuming standard source order?

Answers:

~~~text
System.getenv(...)       -> "4"
System.getProperty(...)  -> "6"
MailProperties.retryCount() -> 8
~~~

The first two APIs read their respective sources directly; the binder receives the winning value from the PropertySources, in this case CLI `8`.

## 29. Practice exercise 5: from nested YAML to environment variables

Given the configuration:

~~~yaml
integration:
  catalog-client:
    http:
      connect-timeout: 3s
      read-timeout: 7s
    retry:
      max-attempts: 5
~~~

Canonical names:

~~~text
integration.catalog-client.http.connect-timeout
integration.catalog-client.http.read-timeout
integration.catalog-client.retry.max-attempts
~~~

Env names:

~~~text
INTEGRATION_CATALOGCLIENT_HTTP_CONNECTTIMEOUT
INTEGRATION_CATALOGCLIENT_HTTP_READTIMEOUT
INTEGRATION_CATALOGCLIENT_RETRY_MAXATTEMPTS
~~~

Explain why **CATALOGCLIENT** and **CONNECTTIMEOUT** do not contain underscores: because the corresponding canonical names use hyphens, and the environment variable conversion rule requires **removing** them.

## 30. Practice exercise 6: troubleshooting a Kubernetes deployment

An application has:

~~~java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(int maxTasks) {}
~~~

Base YAML:

~~~yaml
app:
  worker:
    max-tasks: 5
~~~

Pod declaration:

~~~yaml
env:
  - name: APP_WORKER_MAX_TASKS
    value: "20"
~~~

The operator wants `maxTasks` to be 20, yet the application still receives 5. Steps to resolve:

1. Identify the canonical property as **app.worker.max-tasks**.
2. Apply canonical-to-env conversion → **APP_WORKER_MAXTASKS**.
3. Fix the env `name` field in the Pod.
4. Redeploy so the Java process receives the new variable.
5. Inspect `Environment` and `WorkerProperties` to confirm the value 20 when no higher-precedence source exists.

Fix example:

~~~yaml
env:
  - name: APP_WORKER_MAXTASKS
    value: "20"
~~~

Do not create a second variable just to test, leaving both present at runtime.

## 31. Practice exercise 7: identify naming vs precedence

Two scenarios:

**Scenario A:**

~~~text
File: app.http.read-timeout=5s
Env:  APP_HTTP_READ_TIMEOUT=8s
Result: 5s
~~~

Check **naming** first, because the env var is not the recommended canonical conversion.

**Scenario B:**

~~~text
File: app.http.read-timeout=5s
Env:  APP_HTTP_READTIMEOUT=8s
CLI:  --app.http.read-timeout=12s
Result: 12s
~~~

Here the env var already uses the right name. The `12s` result comes from **precedence**, because CLI beats Config Data and env in a standard setup.

This exercise shows two problems that look similar externally—the env value does not show up—but have completely different fixes.

## 32. Configuration conventions for a Spring Boot project

When a project involves developers, DevOps, and multiple deployment environments, agree on a shared contract:

| Component | Convention | Example |
| --- | --- | --- |
| Java field | camelCase | maxConnections |
| Java ConfigurationProperties prefix | canonical kebab-case | app.http |
| Property in `.properties` | canonical kebab-case | app.http.max-connections |
| YAML mapping key | kebab-case, nested by level | http → max-connections |
| JVM `-D` | canonical kebab-case | -Dapp.http.max-connections=25 |
| Spring Boot CLI | canonical kebab-case | --app.http.max-connections=25 |
| Environment variable | uppercase, underscore for levels, drop hyphens | APP_HTTP_MAXCONNECTIONS |
| List index in env | `_0_`, `_1_`... | APP_SERVERS_0_HOST |
| Special Map key | bracket notation in appropriate sources | app.tenants.[tenant.eu] |

Publishing canonical properties alongside env names in the README prevents two teams from inventing two different conventions.

### 32.1. Sample configuration contract table

| Canonical key | Type | Sample value | Env var | Meaning |
| --- | --- | --- | --- | --- |
| app.http.read-timeout | Duration | 5s | APP_HTTP_READTIMEOUT | Read time limit |
| app.http.connect-timeout | Duration | 2s | APP_HTTP_CONNECTTIMEOUT | Connection time limit |
| app.http.max-connections | int | 25 | APP_HTTP_MAXCONNECTIONS | Maximum connections |
| app.mail.retry-count | int | 3 | APP_MAIL_RETRYCOUNT | Send retry count |
| app.mail.enabled | boolean | true | APP_MAIL_ENABLED | Enable mail sending |
| app.cache.time-to-live | Duration | 10m | APP_CACHE_TIMETOLIVE | Cache time-to-live |

When adding a new field, update the table above and the sample config in the same source-code change. Do not wait until production deployment to discover that the env name differs from the property name.

### 32.2. Do not let tools generate names arbitrarily

A script might convert camelCase to SNAKE_CASE, whereas Spring Boot defines conversion from a **canonical key** containing dots and hyphens. If generating env names automatically, the script must take the **canonical property path** as input and apply the corresponding conversion rule.

If a Java field name changes while the canonical key is intentionally kept stable through modeling/binding, a script depending on Java field names can break the operators' contract.

## 33. Checklist before concluding configuration is right

When converting between kebab-case, camelCase, and underscore, verify step by step:

1. Has the canonical name been determined?
2. Is the prefix at the right level?
3. Is a hyphen merely part of a compound name, or is a nested level truly needed?
4. In `.properties` or YAML files, is one consistent convention used?
5. For env vars, were dots replaced with underscores, hyphens removed, and letters uppercased?
6. For Lists, are indexes represented as **_0_**, **_1_**?
7. For Maps, are there dynamic keys with special characters requiring bracket notation?
8. Is the env var actually passed to the running JVM?
9. Is another higher-precedence source declaring the same logical property?
10. Can the value be converted to the Java type and pass validation?
11. Is `@ConfigurationProperties` properly scanned/enabled?
12. Have you verified the actual value in the bean rather than merely seeing the app start?

Each question checks an independent cause. This workflow avoids changing property names blindly when the real issue is in a profile file, source precedence, or type conversion.

## 34. Key takeaways

**In `.properties` and YAML**, Spring Boot relaxed binding supports variants such as **read-timeout**, **readTimeout**, and **read_timeout** when binding to the corresponding Java field. Despite this flexibility, **kebab-case** is the form to standardize on.

**In JVM system properties**, similar name variants can be bound by the binder; in deployment, use canonical kebab-case with **-Dapp.http.read-timeout=...**.

**In command-line arguments**, use **--app.http.read-timeout=...** for consistency and to reduce ambiguity.

**In environment variables**, the canonical name is built from the canonical path in three steps: **dot → underscore; remove hyphen; uppercase**. Thus **app.http.read-timeout → APP_HTTP_READTIMEOUT**.

**Dots create levels; hyphens stay inside compound names**. The two paths **app.http.read-timeout** and **app.http.read.timeout** should not be treated as the same model. Their corresponding environment variables also differ: **APP_HTTP_READTIMEOUT** and **APP_HTTP_READ_TIMEOUT**.

**Relaxed binding, precedence, conversion, and validation are separate steps.** The right name does not guarantee the value wins; the winning value does not guarantee a valid type. When troubleshooting, trace **source → canonical name → PropertySource → binder → Java field** rather than switching randomly between spellings.
