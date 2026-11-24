# Rules for Dots, Hyphens, and Uppercase When Binding Environment Variables in Spring Boot

## Goal

Spring Boot uses **externalized configuration** so an application can receive values from configuration files, environment variables, JVM system properties, command-line arguments, and many other sources. In Java, a property often has a name like **app.notification.retry-count**; in an operating system environment, operators usually configure a variable like **APP_NOTIFICATION_RETRYCOUNT**. They can bind to the same configuration value thanks to **relaxed binding**.

Problems arise when users habitually replace both dots and hyphens with underscores. Not every hyphen turns into an underscore. A mistyped variable may still exist in the container, yet the **@ConfigurationProperties** bean receives a default value or reports missing configuration.

This lesson clearly explains:

- The standard rule for converting Spring Boot property names to environment variable names.
- Why **dots**, **hyphens**, and **uppercase** are handled differently.
- How relaxed binding works from environment variables to Java classes.
- Differences between **System.getenv**, **Environment**, and **@ConfigurationProperties**.
- How to write variables for nested properties, lists, and certain map structures.
- Failure scenarios on Linux, Windows PowerShell, Docker, and Kubernetes.
- Methods to verify the configuration values actually bound.

## 1. From property name to environment variable name

In Spring Boot, property names in configuration files should follow **canonical kebab-case**: lowercase, with levels separated by dots and words within a segment separated by hyphens.

Example:

~~~properties
app.notification.retry-count=3
app.notification.send-timeout=5s
spring.main.log-startup-info=true
~~~

In YAML, the corresponding properties can be represented as a tree:

~~~yaml
app:
  notification:
    retry-count: 3
    send-timeout: 5s
spring:
  main:
    log-startup-info: true
~~~

Spring Boot can bind them to canonical environment variable names:

~~~text
APP_NOTIFICATION_RETRYCOUNT
APP_NOTIFICATION_SENDTIMEOUT
SPRING_MAIN_LOGSTARTUPINFO
~~~

The most important point to remember is the difference between the two punctuation marks:

- **Dot (.)** separates property name levels; when converted to an environment variable name, it becomes an **underscore (_)**.
- **Hyphen (-)** separates words within a name segment; when converted to an environment variable name by the canonical rule, it is **removed**.
- **Letters** are converted to **uppercase**.

Thus **app.notification.retry-count** becomes **APP_NOTIFICATION_RETRYCOUNT**, rather than a mechanical formula of "replacing all dots and hyphens with underscores".

## 2. Three canonical conversion steps

According to Spring Boot's rule for converting a canonical property name to an environment variable name:

1. Replace every dot **.** with an underscore **_**.
2. Remove every hyphen **-**.
3. Convert the remaining letters to **uppercase**.

Applying step by step to a property:

~~~text
app.mail.max-retries
         |
         | Step 1: "." to "_"
         v
app_mail_max-retries
         |
         | Step 2: remove "-"
         v
app_mail_maxretries
         |
         | Step 3: uppercase
         v
APP_MAIL_MAXRETRIES
~~~

Conversion table:

| Canonical property | Environment variable by canonical rule |
| --- | --- |
| server.port | SERVER_PORT |
| spring.profiles.active | SPRING_PROFILES_ACTIVE |
| spring.datasource.url | SPRING_DATASOURCE_URL |
| management.endpoints.web.exposure.include | MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE |
| spring.main.log-startup-info | SPRING_MAIN_LOGSTARTUPINFO |
| app.mail.max-retries | APP_MAIL_MAXRETRIES |
| app.mail.connect-timeout | APP_MAIL_CONNECTTIMEOUT |
| app.payment.retry-delay | APP_PAYMENT_RETRYDELAY |
| app.cache.time-to-live | APP_CACHE_TIMETOLIVE |
| app.http.client.read-timeout | APP_HTTP_CLIENT_READTIMEOUT |
| app.service-name | APP_SERVICENAME |
| my.service[0].other | MY_SERVICE_0_OTHER |

Two examples to verify the rule:

**Example A — dots only:**

~~~text
spring.datasource.username
=> spring_datasource_username
=> SPRING_DATASOURCE_USERNAME
~~~

**Example B — both dots and hyphens:**

~~~text
app.payment.max-retry-attempts
=> app_payment_maxretryattempts
=> APP_PAYMENT_MAXRETRYATTEMPTS
~~~

In example B, the **max-retry-attempts** segment produces **MAXRETRYATTEMPTS** when applying the canonical rule. If you manually convert it to **MAX_RETRY_ATTEMPTS**, that is a different form and should not be treated as the canonical name guaranteed by the conversion above.

## 3. Why not replace hyphens with underscores as well?

Consider the property:

~~~properties
app.client.read-timeout=10s
~~~

The environment variable name derived from the canonical rule:

~~~bash
APP_CLIENT_READTIMEOUT=15s java -jar demo.jar
~~~

A seemingly natural spelling is:

~~~text
APP_CLIENT_READ_TIMEOUT
~~~

However, that spelling inserts an underscore between **READ** and **TIMEOUT**, whereas in the canonical name, the hyphen between the two words is removed. Spring Boot supports various flexible name forms in certain contexts, but when configuring deployment environments or operational documentation, **derive names using the exact three canonical steps**, rather than relying on a variant that might happen to work with some binding mechanism.

Comparison:

| Intent | Name to use |
| --- | --- |
| Sub-level **client** in **app**, property **read-timeout** | APP_CLIENT_READTIMEOUT |
| Sub-level **client** with sub-level **read**, property **timeout** | APP_CLIENT_READ_TIMEOUT |

The following two property names have different structures:

~~~properties
app.client.read-timeout=10s
app.client.read.timeout=10s
~~~

The dot in the second name creates an additional level. When naming configuration classes, nested structures, and Java fields, this can lead to different binding.

**Maintainable convention:** use dots for the path of configuration levels, use kebab-case for property names within each level, and convert to environment variables via the three canonical steps.

## 4. How does relaxed binding work on the Spring side?

Spring Boot provides **relaxed binding**, allowing name forms used across different configuration sources to bind to the same field in a Java bean.

Java example:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        int maxRetries,
        Duration connectTimeout,
        boolean enabled
) {
}
~~~

File application.yml:

~~~yaml
app:
  mail:
    max-retries: 3
    connect-timeout: 5s
    enabled: true
~~~

When the application registers the MailProperties bean, such as via **@ConfigurationPropertiesScan** or **@EnableConfigurationProperties(MailProperties.class)**, the binder can link:

~~~text
app.mail.max-retries     -> maxRetries
app.mail.connect-timeout -> connectTimeout
app.mail.enabled         -> enabled
~~~

Set environment variables:

~~~bash
APP_MAIL_MAXRETRIES=7 APP_MAIL_CONNECTTIMEOUT=12s APP_MAIL_ENABLED=false java -jar demo.jar
~~~

In typical scenarios, values from environment variables have higher precedence than application.yml. The bean receives:

~~~text
maxRetries   = 7
connectTimeout = PT12S (Duration 12 seconds)
enabled      = false
~~~

This involves **two distinct steps**:

1. Spring Boot determines which environment variable corresponds to the property name in configuration.
2. The Binder converts the string value from the external source into the target Java type, such as **int**, **Duration**, or **boolean**.

Matching the name successfully does not guarantee type conversion will succeed. If you set **APP_MAIL_MAXRETRIES=abc**, the binder cannot convert **abc** into a valid integer. The application may then fail during configuration binding.

### 4.1. Registering ConfigurationProperties

One way to register it in a Spring Boot application:

~~~java
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

Place MailProperties under an appropriately scanned package. Then you can inject the MailProperties bean into a service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class MailJob {
    private final MailProperties properties;

    public MailJob(MailProperties properties) {
        this.properties = properties;
    }

    public String description() {
        return "retry=" + properties.maxRetries()
            + ", timeout=" + properties.connectTimeout()
            + ", enabled=" + properties.enabled();
    }
}
~~~

This example shows that the application does not need to call System.getenv manually for each variable. The centralized configuration bean reflects the result from the PropertySources selected by Spring.

## 5. System.getenv, Environment, and @ConfigurationProperties are different

Three APIs are frequently mistaken for equivalent:

~~~java
String osValue = System.getenv("APP_MAIL_MAXRETRIES");
String springValue = environment.getProperty("app.mail.max-retries");
MailProperties bound = mailProperties;
~~~

**System.getenv("APP_MAIL_MAXRETRIES")** reads the Java process's environment variable directly. It does not see values from application.yml, JVM system properties, or Spring Boot command-line arguments.

**Environment.getProperty("app.mail.max-retries")** looks up through the Spring Environment and the order of PropertySources. The same key can come from a file, environment variable, or other sources.

**@ConfigurationProperties** uses the binder to bind configuration names to Java objects and perform type conversion. Relaxed binding is explicitly designed for this path.

Example:

~~~yaml
# application.yml
app:
  mail:
    max-retries: 3
~~~

Run command:

~~~bash
APP_MAIL_MAXRETRIES=7 java -Dapp.mail.max-retries=9 -jar demo.jar --app.mail.max-retries=11
~~~

Assuming no higher-priority source than those in the example:

| Lookup method | Result |
| --- | --- |
| System.getenv("APP_MAIL_MAXRETRIES") | "7" |
| System.getProperty("app.mail.max-retries") | "9" |
| Environment.getProperty("app.mail.max-retries") | "11" |
| Bean MailProperties.maxRetries() | 11 |

Therefore, when diagnosing "I set the environment variable, yet the application still receives a different number", do not only print System.getenv. Spring Boot may be using a system property or command-line property with higher priority.

### 5.1. Uppercase names are not Java system property names

A JVM system property is usually passed like this:

~~~bash
java -Dapp.mail.max-retries=9 -jar demo.jar
~~~

The corresponding environment variable is usually provided like this:

~~~bash
APP_MAIL_MAXRETRIES=7 java -jar demo.jar
~~~

Both mechanisms are sources for Spring Environment, but they have different naming syntaxes and direct access APIs. Do not assume **-DAPP_MAIL_MAXRETRIES=7** is the same operation as **APP_MAIL_MAXRETRIES=7**.

A Java system property can be read by its exact name via System.getProperty(...). When designing configuration, keeping JVM system names in standard property format helps reduce confusion.

### 5.2. @Value uses canonical names

With Spring placeholders:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
class RetryCounter {
    @Value("${app.mail.max-retries:3}")
    private int maxRetries;
}
~~~

Using a **canonical kebab-case** placeholder name like **app.mail.max-retries** is the preferred choice so Spring Boot can apply appropriate flexible lookup. Writing placeholders in camelCase or uppercase environment variable style may resolve differently than intended across some sources.

For configuration groups with multiple fields, **@ConfigurationProperties** is usually clearer and easier to type-check than scattering many @Value annotations across classes.

## 6. Nested levels in YAML and the dot rule

YAML configuration:

~~~yaml
app:
  gateway:
    http:
      connect-timeout: 2s
      read-timeout: 10s
      max-connections: 50
~~~

Corresponding property paths:

~~~properties
app.gateway.http.connect-timeout=2s
app.gateway.http.read-timeout=10s
app.gateway.http.max-connections=50
~~~

Canonical environment variable names:

~~~text
APP_GATEWAY_HTTP_CONNECTTIMEOUT
APP_GATEWAY_HTTP_READTIMEOUT
APP_GATEWAY_HTTP_MAXCONNECTIONS
~~~

To make it easy to understand, separate **path** and **field name**:

~~~text
app.gateway.http.read-timeout
    |       |         |
    |       |         +-- read-timeout: a two-word field name
    |       +------------ http: a configuration level
    +-------------------- gateway: a configuration level
~~~

In YAML, indentation determines which level is a child of which. If you write:

~~~yaml
app:
  gateway:
    http:
      connect-timeout: 2s
    read-timeout: 10s
~~~

then read-timeout has moved to **app.gateway.read-timeout**. The canonical environment name also changes from **APP_GATEWAY_HTTP_READTIMEOUT** to **APP_GATEWAY_READTIMEOUT**.

A syntactically valid environment variable can still be ignored if it represents a **different property path** than the one the bean expects.

## 7. Uppercase and case sensitivity

In Spring Boot documentation, converting property names to environment variables uses **uppercase**. This convention is friendly across operating systems and deployment platforms.

Example:

~~~text
app.feature.enabled   -> APP_FEATURE_ENABLED
app.feature.batch-size -> APP_FEATURE_BATCHSIZE
~~~

In Unix/Linux shells, environment variable names are generally case-sensitive at the process level. For example, **APP_FEATURE_ENABLED** and **app_feature_enabled** can be two separate variables if the environment allows setting both. On Windows, OS environment variable naming rules differ; do not design application behavior around having two variables that differ only in letter case.

**Do not** set variables differing only by case at the same time to try to force precedence. That makes configuration platform-dependent and hard to diagnose. Standardize on a single uppercase name when putting variables into containers, scripts, or deployment files.

The uppercase rule also does not mean Java classes must have uppercase fields:

~~~java
public record FeatureProperties(boolean enabled, int batchSize) {}
~~~

Java fields still follow regular camelCase; the canonical property name is **app.feature.batch-size** and the standard environment variable name is **APP_FEATURE_BATCHSIZE**.

## 8. When two configuration names convert to the same environment variable

The **remove hyphens** step has an important consequence: in some naming designs, two different canonical names can convert to the same environment variable name.

Example:

~~~text
app.http.max-retries -> APP_HTTP_MAXRETRIES
app.http.maxretries  -> APP_HTTP_MAXRETRIES
~~~

From the perspective of someone writing a .properties file, **max-retries** and **maxretries** are two different strings. But when expressed as canonical environment variable names, they collide on the same name. Relaxed binding may also treat these spellings as equivalent during binding.

To avoid ambiguity:

- Give **each property one stable canonical name**.
- Do not simultaneously design two properties differing only in hyphen placement.
- Use a different level structure or a clearer name if two values carry different business meanings.
- Document exact environment variable names, especially for configurations exposed to operators.

For example, if you truly need two retry types:

~~~yaml
app:
  http:
    connect:
      retry-count: 2
    request:
      retry-count: 5
~~~

They have distinct environment variable names:

~~~text
APP_HTTP_CONNECT_RETRYCOUNT
APP_HTTP_REQUEST_RETRYCOUNT
~~~

Separating configuration levels avoids name collisions and clearly describes the scope of each parameter.

## 9. Binding environment variables to lists

A List in @ConfigurationProperties needs to account for **element indices**, not only field names.

Suppose YAML:

~~~yaml
app:
  clients:
    - name: catalog
      base-url: https://catalog.example.test
      retries: 2
    - name: billing
      base-url: https://billing.example.test
      retries: 4
~~~

Java:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record ClientsProperties(List<Client> clients) {
    public record Client(String name, String baseUrl, int retries) {}
}
~~~

According to the canonical rule for environment variables when binding lists, **the index is surrounded by underscores**. Example names:

~~~text
APP_CLIENTS_0_NAME
APP_CLIENTS_0_BASEURL
APP_CLIENTS_0_RETRIES
APP_CLIENTS_1_NAME
APP_CLIENTS_1_BASEURL
APP_CLIENTS_1_RETRIES
~~~

Indices **0** and **1** represent different elements of the list. For a property like **app.clients[0].base-url**, the corresponding conversion is:

~~~text
app.clients[0].base-url
=> app_clients_0_base-url
=> app_clients_0_baseurl
=> APP_CLIENTS_0_BASEURL
~~~

In a real example, if you declare:

~~~bash
APP_CLIENTS_0_NAME=catalog APP_CLIENTS_0_BASEURL=https://catalog.example.test java -jar demo.jar
~~~

the binder can bind the first element's information if the bean structure and data source match.

### 9.1. Common mistakes with indices

Do not write:

~~~text
APP_CLIENTS_0_BASE_URL
~~~

and assume it is definitely the canonical conversion of **app.clients[0].base-url**. By the canonical rule, the **base-url** segment becomes **BASEURL**.

Do not attach the index directly to the name arbitrarily:

~~~text
APP_CLIENTS0_BASEURL
~~~

because the canonical list conversion requires the index to be explicitly delimited by convention.

If a list is declared across multiple PropertySources such as application.yml and environment variables, Spring Boot's list-binding rules may select the list from the higher-priority source instead of automatically concatenating all elements. When overriding a complex list, inspect the final data the binder receives and supply all necessary elements.

## 10. Binding to Maps: do not generalize mechanically

Example bean:

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record RegionProperties(Map<String, String> endpoints) {
}
~~~

Configuration:

~~~yaml
app:
  endpoints:
    asia: https://asia.example.test
    europe: https://europe.example.test
~~~

With simple keys, environment variable names can be constructed from the property path:

~~~text
APP_ENDPOINTS_ASIA
APP_ENDPOINTS_EUROPE
~~~

However, **Map** keys are data, not always ordinary canonical Java name segments. If a key contains dots, slashes, brackets, meaningful uppercase letters, or other characters, turning everything into uppercase and underscores can alter the key or produce an unintended structure.

Spring Boot supports **bracket notation** in certain file sources to preserve Map keys containing special characters:

~~~yaml
app:
  headers:
    "[X-Trace-Id]": "example"
    "[/internal/path]": "enabled"
~~~

In such cases, square brackets and quotes are part of representing the key in YAML; there is no simple dot/hyphen/uppercase substitution that guarantees preserving every key character when using environment variables.

For special Map keys, consider configuring them with YAML, properly formatted properties, config trees, or a less ambiguous structure. If environment variables must be used, verify how your actual Spring Boot version's binder resolves each key.

### 10.1. Distinguishing Map from nested object

Suppose you have:

~~~yaml
app:
  regions:
    europe:
      endpoint: https://eu.example.test
~~~

If Java uses a nested record/class with a field **europe**, the structure can differ from Java using **Map<String, Region>**. Both can express the same property path in a simple example, but handling of dynamic keys, nested types, and non-standard data can differ.

Clearly determine the target type before creating environment variable names, especially for maps whose keys come from third parties.

## 11. Declaring on Linux and macOS

In Bash or compatible shells, you can pass variables for a single command:

~~~bash
APP_HTTP_CONNECTTIMEOUT=3s APP_HTTP_READTIMEOUT=20s java -jar demo.jar
~~~

These two variables exist in the environment of the java process launched by the command above.

You can use **export** so subsequent child commands inherit the variables:

~~~bash
export APP_HTTP_CONNECTTIMEOUT=3s
export APP_HTTP_READTIMEOUT=20s
java -jar demo.jar
~~~

When using export, remember variables can persist in the shell session. If running the application again with different configuration, check what old variables are being inherited:

~~~bash
printenv APP_HTTP_CONNECTTIMEOUT
printenv APP_HTTP_READTIMEOUT
~~~

Using **printenv** in examples is only appropriate for non-sensitive values like timeouts. Do not print passwords, tokens, or secrets to terminals or logs to verify binding.

### 11.1. Should values be placed in quotes?

Values containing spaces or special shell characters must be quoted according to shell rules. Example:

~~~bash
APP_LABEL='Order service - local' java -jar demo.jar
~~~

The variable name **APP_LABEL** remains a normal environment variable name. Quotes are shell syntax for passing a value with spaces, not part of the variable name.

## 12. Declaring on Windows PowerShell

In PowerShell, use the **$env:** syntax:

~~~powershell
$env:APP_HTTP_CONNECTTIMEOUT = "3s"
$env:APP_HTTP_READTIMEOUT = "20s"
java -jar demo.jar
~~~

To inspect the variable value:

~~~powershell
$env:APP_HTTP_READTIMEOUT
~~~

Configuration via **$env:** applies to the current PowerShell session environment and child processes spawned from that session according to OS behavior. It does not edit application.yml and is not a JVM option.

If you want to remove the variable from the shell session and run again, you can use:

~~~powershell
Remove-Item Env:APP_HTTP_READTIMEOUT
java -jar demo.jar
~~~

Distinguish the environment variable name from the Spring Environment value. A variable removed from the shell may allow the value from application.yml to appear, though if **-Dapp.http.read-timeout** or **--app.http.read-timeout** is still present, Spring may choose those sources.

## 13. How Docker and Kubernetes use the right variable names

### 13.1. Docker

Suppose an image runs a Spring Boot JAR:

~~~bash
docker run --rm -e APP_HTTP_CONNECTTIMEOUT=3s -e APP_HTTP_READTIMEOUT=20s demo-image
~~~

Docker provides variable names and values to the process inside the container. Spring Boot reads them through the PropertySource for environment variables.

If a Docker image uses an entrypoint script, ensure the script preserves or forwards the process environment properly. A variable name appearing in a docker run command does not by itself prove it reached the Java process if the launcher modified or filtered the environment.

### 13.2. Kubernetes

Pod configuration snippet:

~~~yaml
containers:
  - name: demo
    image: demo-image
    env:
      - name: APP_HTTP_CONNECTTIMEOUT
        value: "3s"
      - name: APP_HTTP_READTIMEOUT
        value: "20s"
~~~

Here the values sit in the container's **env** field. Kubernetes does not need to know whether the Java field is named **readTimeout** or whether application.yml uses **read-timeout**; name conversion and binding are Spring Boot's responsibility.

If using a ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: demo-runtime
data:
  APP_HTTP_CONNECTTIMEOUT: "3s"
  APP_HTTP_READTIMEOUT: "20s"
~~~

Then reference the ConfigMap in the container's env using the appropriate Kubernetes mechanism. A ConfigMap existing in the cluster does not automatically inject data into an application; there must be an explicit delivery path such as **env**, **envFrom**, or a volume mount.

For sensitive information, use Secrets and manage access permissions appropriately. Do not put real tokens into READMEs, test commands, or configuration screenshots.

### 13.3. Variable names in deployment YAML do not change binding rules

An easy mistake to make:

~~~yaml
env:
  - name: APP_HTTP_READ_TIMEOUT
    value: "20s"
~~~

While the canonical key is **app.http.read-timeout**. The author looks at the variable name and thinks it is right because words are separated by underscores. The safe approach is to take the canonical key and apply the three steps, yielding **APP_HTTP_READTIMEOUT**.

When using a non-standard variable name, the application may keep the value from the file or another source; a Pod starting successfully does not prove the configuration overrode anything.

## 14. Precedence order when both environment variables and files declare values

The renaming rule only answers **"Which variable name corresponds to which property name?"**. The question **"Which value gets selected?"** also depends on PropertySource order.

Example:

~~~yaml
# application.yml
app:
  cache:
    time-to-live: 30s
~~~

Environment variable:

~~~bash
APP_CACHE_TIMETOLIVE=45s java -jar demo.jar
~~~

With standard source behavior, **APP_CACHE_TIMETOLIVE** can override the **30s** value from application.yml, and the configuration bean receives **45s**.

Adding a JVM system property:

~~~bash
APP_CACHE_TIMETOLIVE=45s java -Dapp.cache.time-to-live=60s -jar demo.jar
~~~

Among the sources being compared, the system property **60s** takes higher priority than the environment variable **45s**.

Adding a command-line argument:

~~~bash
APP_CACHE_TIMETOLIVE=45s java -Dapp.cache.time-to-live=60s -jar demo.jar --app.cache.time-to-live=90s
~~~

When command-line properties are enabled by default, Spring receives **90s**.

Summary table:

| Source | Name/syntax | Value |
| --- | --- | --- |
| application.yml | app.cache.time-to-live | 30s |
| Environment variable | APP_CACHE_TIMETOLIVE | 45s |
| JVM system property | -Dapp.cache.time-to-live | 60s |
| Spring Boot command line | --app.cache.time-to-live | **90s** |

If you set the exact right environment variable name and see the value is still 90s, the problem is not necessarily relaxed binding. Check for sources with higher precedence.

This is the order **among the sources under consideration**. Spring Boot also has other PropertySources for JSON, tests, DevTools, or additional configuration. Avoid treating this table as an exhaustive list of all possible sources.

## 15. Common variable naming mistakes and how to fix them

### 15.1. Replacing hyphens with underscores too

Property:

~~~properties
app.mail.retry-count=5
~~~

Canonical converted name:

~~~text
APP_MAIL_RETRYCOUNT
~~~

What many people guess:

~~~text
APP_MAIL_RETRY_COUNT
~~~

**Fix:** identify the canonical key, convert dots to underscores, remove hyphens, and uppercase. Do not construct names just by reading the Java field in English.

### 15.2. Dropping underscores of nested levels

Property:

~~~text
app.mail.retry.count
~~~

Canonical name:

~~~text
APP_MAIL_RETRY_COUNT
~~~

If you use **APP_MAIL_RETRYCOUNT**, that name fits the key **app.mail.retry-count** instead. A configuration level and a compound word in a field are not always interchangeable.

### 15.3. Inconsistent letter casing

~~~text
app_mail_retrycount
App_Mail_RetryCount
APP_MAIL_RETRYCOUNT
~~~

In deployment documentation, choose **APP_MAIL_RETRYCOUNT**. Do not configure systems assuming every operating system or library normalizes all letter cases in the exact same way.

### 15.4. Correct name, but not supplied to the Java process

For example, a variable is set in another terminal window, while the application runs from an IDE or a separate service. The Java process's environment may not contain that variable.

**Fix:** check the environment configuration at the place actually launching the JVM: IDE Run Configuration, shell command, service manager, Docker entrypoint, or Pod specification.

### 15.5. Overridden by a higher-priority source

An environment variable has the right name, but the JVM has **-D** or the CLI has **--** for the same property. Spring Environment may return the value from the other source.

**Fix:** inspect Environment.getProperty(...) and the participating PropertySources, not just System.getenv(...).

### 15.6. Type conversion failure

~~~text
APP_MAIL_MAXRETRIES=many
~~~

If the Java field is **int maxRetries**, the value **many** cannot be converted into an integer. This error differs from not finding the variable.

**Fix:** inspect the binding/conversion exception, property name, and target type. Try a valid number like **3** or **7**.

### 15.7. @ConfigurationProperties prefix mismatch

Class:

~~~java
@ConfigurationProperties(prefix = "app.email")
public record EmailProperties(int retryCount) {}
~~~

The canonical name is **app.email.retry-count**, so the standard environment name is **APP_EMAIL_RETRYCOUNT**. If an operator sets **APP_MAIL_RETRYCOUNT**, Spring does not automatically infer that email and mail are synonyms.

### 15.8. Using @Value with a non-canonical name

Example:

~~~java
@Value("${app.mail.maxRetries:3}")
private int retries;
~~~

Writing a placeholder in camelCase may not resolve across all sources in the same way as the canonical **app.mail.max-retries**. For clarity, prefer:

~~~java
@Value("${app.mail.max-retries:3}")
private int retries;
~~~

For multiple related properties, grouping them into a **@ConfigurationProperties** class helps manage structure and data types better.

### 15.9. Key appearing twice due to different naming conventions

If the same configuration group has both **retry-count** and **retryCount**, the binder may treat them as variants of the same concept. When in different sources, the result depends on precedence; when in the same source, it can create ambiguity.

**Fix:** standardize configuration file names in kebab-case, give each key a clear meaning, and avoid defining two variables serving the same purpose under different variants.

### 15.10. Confusing an empty string with a missing variable

A variable assigned an empty value is still a value present in the process environment. During binding, it may trigger a conversion error or produce a different result than an undeclared variable.

~~~bash
APP_MAIL_MAXRETRIES='' java -jar demo.jar
~~~

Do not assume empty means "ignore and fall back to the default file". Depending on the PropertySource, data type, and binder, verify the specific case.

## 16. Checking variable names and values at runtime

A diagnostic snippet can focus on a single non-sensitive property:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ConfigInspector implements ApplicationRunner {
    private final Environment environment;
    private final MailProperties properties;

    ConfigInspector(Environment environment, MailProperties properties) {
        this.environment = environment;
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("OS env: "
            + System.getenv("APP_MAIL_MAXRETRIES"));
        System.out.println("Spring property: "
            + environment.getProperty("app.mail.max-retries"));
        System.out.println("Bound bean: "
            + properties.maxRetries());
    }
}
~~~

When running:

~~~bash
APP_MAIL_MAXRETRIES=7 java -jar demo.jar
~~~

assuming no higher-priority override, the expected output is:

~~~text
OS env: 7
Spring property: 7
Bound bean: 7
~~~

If **OS env** is 7, yet **Spring property** and **Bound bean** are not as expected, check higher-priority sources or binding behavior. If **OS env** is null, the variable is not yet present in the process environment under the exact queried name.

### 16.1. Listing PropertySource names

To see what kinds of sources Spring Environment is considering:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
class EnvironmentSources implements ApplicationRunner {
    private final ConfigurableEnvironment environment;

    EnvironmentSources(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        for (PropertySource<?> source : environment.getPropertySources()) {
            System.out.println(source.getName());
        }
    }
}
~~~

In a typical Spring Boot environment, the list may include the system environment variable source along with config data files and command-line arguments. The order in Environment shows how property lookup is organized at runtime.

Print only the **names** of the sources in examples, not all contents, because environment variables and configuration files may contain sensitive information.

### 16.2. Checking that the bean receives the right type

If the bean expects a Duration:

~~~java
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(java.time.Duration readTimeout) {}
~~~

and the variable:

~~~bash
APP_HTTP_READTIMEOUT=12s java -jar demo.jar
~~~

the value read from the bean is a Duration object representing 12 seconds, typically printed as **PT12S**. This differs from the original string **12s** but does not mean binding failed.

For integers, booleans, enums, and collections, always compare against the **target type** instead of just reading raw input characters.

### 16.3. Actuator and sensitive data

If the application already includes Spring Boot Actuator and endpoints are configured with secure access, environment inspection tools can help trace value origins. Many sensitive values are masked according to security policy.

Do not expose environment endpoints publicly just to see what variables are named; do not print passwords or tokens to the console during diagnostics. Pick dummy properties like timeouts and retry-count for testing.

## 17. Name conversion practice

### Exercise 1 — Converting properties to environment variables

Compute the canonical environment variable names for the following properties yourself:

~~~text
1. server.port
2. spring.profiles.active
3. app.mail.retry-count
4. app.payment.request-timeout
5. app.metrics.export-enabled
6. app.gateway.client.max-open-connections
7. app.items[0].display-name
~~~

Answers:

~~~text
1. SERVER_PORT
2. SPRING_PROFILES_ACTIVE
3. APP_MAIL_RETRYCOUNT
4. APP_PAYMENT_REQUESTTIMEOUT
5. APP_METRICS_EXPORTENABLED
6. APP_GATEWAY_CLIENT_MAXOPENCONNECTIONS
7. APP_ITEMS_0_DISPLAYNAME
~~~

In item 7, the list index **[0]** is converted to **_0_** according to the list environment variable rule.

### Exercise 2 — Distinguishing two easily confused keys

Two properties:

~~~properties
app.http.max-connections=20
app.http.max.connections=20
~~~

The canonical env names are respectively:

~~~text
APP_HTTP_MAXCONNECTIONS
APP_HTTP_MAX_CONNECTIONS
~~~

Explain why the two names differ. Answer: **max-connections** is a single compound two-word property name; **max.connections** is two configuration levels.

### Exercise 3 — Trying a YAML file override

Create the file:

~~~yaml
app:
  mail:
    max-retries: 2
    connect-timeout: 3s
~~~

Then run:

~~~bash
APP_MAIL_MAXRETRIES=5 APP_MAIL_CONNECTTIMEOUT=8s java -jar demo.jar
~~~

Use the MailProperties bean and Environment to observe the two values. Under standard source behavior, the values from environment are **5** and **8s**; the bean can receive **5** and a Duration of 8 seconds.

Also try:

~~~bash
APP_MAIL_MAXRETRIES=5 java -Dapp.mail.max-retries=6 -jar demo.jar --app.mail.max-retries=7
~~~

Read System.getenv, System.getProperty, and Environment.getProperty to see how three mechanisms can return three different values within the same process.

### Exercise 4 — Finding the wrong variable name

A Deployment file declares:

~~~yaml
env:
  - name: APP_PAYMENT_RETRY_DELAY
    value: "1s"
~~~

While the bean expects **app.payment.retry-delay**. State the name converted by the canonical rule and fix the configuration.

Answer:

~~~yaml
env:
  - name: APP_PAYMENT_RETRYDELAY
    value: "1s"
~~~

Reason: the dot between **app** and **payment** and the dot before **retry-delay** become underscores; the hyphen between **retry** and **delay** is removed.

### Exercise 5 — Binding a list

With keys:

~~~text
app.workers[0].max-tasks
app.workers[1].max-tasks
~~~

Canonical env names:

~~~text
APP_WORKERS_0_MAXTASKS
APP_WORKERS_1_MAXTASKS
~~~

Try creating a class containing **List<Worker>**, supply the two variables, and observe the element count and values of each element. If an element lacks a required field, handle it via validation or configuration structure, rather than arbitrarily altering the renaming rule.

## 18. Naming conventions for a project

When designing configuration for long-term use, a consistent convention ensures YAML files, environment variables, Java classes, and operational docs all describe the same key.

| Layer | Recommended convention | Example |
| --- | --- | --- |
| Property in .properties | lowercase, dots between levels, kebab-case for compound names | app.http.read-timeout |
| YAML | nested tree, kebab-case key names | app → http → read-timeout |
| Environment variable | uppercase, underscores for dots, remove hyphens | APP_HTTP_READTIMEOUT |
| Java class | PascalCase class name, camelCase fields | HttpProperties.readTimeout |
| JVM system property | canonical property name | -Dapp.http.read-timeout=5s |
| Spring Boot CLI argument | canonical property name | --app.http.read-timeout=5s |

Complete example:

~~~yaml
# application.yml
app:
  http:
    read-timeout: 5s
    connect-timeout: 2s
    max-connections: 25
~~~

~~~java
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
    java.time.Duration readTimeout,
    java.time.Duration connectTimeout,
    int maxConnections
) {}
~~~

~~~bash
APP_HTTP_READTIMEOUT=9s APP_HTTP_CONNECTTIMEOUT=4s APP_HTTP_MAXCONNECTIONS=40 java -jar demo.jar
~~~

This establishes a clear configuration contract: the official name at the Spring layer is **app.http.read-timeout**, and the name used in deployment environments is **APP_HTTP_READTIMEOUT**.

### 18.1. Document from canonical names, not from Java fields

When a class has field **maxConnections**, do not guess the variable name by splitting camelCase words into **MAX_CONNECTIONS**. Start from the full property:

~~~text
app.http.max-connections
=> APP_HTTP_MAXCONNECTIONS
~~~

This keeps documentation aligned with Spring Boot rules, especially when refactoring class names or adding configuration levels.

### 18.2. Env names are not the place to express units

For instance, a Duration property should accept values like **5s** or **250ms** if the binder supports it. The variable name stays **APP_HTTP_READTIMEOUT**; do not add a **_SECONDS** suffix unless that is actually a different property name designed by the application.

If you want to express the unit directly in the name, use a clear property name like **app.http.read-timeout-seconds**, and convert canonically to **APP_HTTP_READTIMEOUTSECONDS**. The bean must then use the corresponding type and interpretation.

## 19. Troubleshooting workflow when an environment variable fails to bind

When encountering "I set the env var, but Spring did not pick it up", follow these steps in order:

1. **Read the canonical key the bean needs.** Check the @ConfigurationProperties prefix and Java field names; write out the path like **app.mail.max-retries**.
2. **Apply the three canonical conversion steps.** Dots to underscores, remove hyphens, uppercase.
3. **Check the environment of the actual process.** Was the variable passed into the running JVM, or does it only exist in another terminal, Pod, or service?
4. **Check YAML/properties files.** Are there wrong nesting levels, wrong key names, or another spelling of the same property?
5. **Check higher-priority sources.** Are there -D, --, or custom PropertySources with the same key?
6. **Inspect what Spring Environment returns.** Use the canonical name to minimize ambiguity.
7. **Check bind/validation errors.** If the value is visible in Environment yet the bean fails to initialize, inspect data types and required constraints.
8. **For List/Map, check the structure.** Element indices and special keys need dedicated inspection, not just character replacement.
9. **After fixing, restart and observe.** Modifying variables in a shell after the JVM has started does not automatically update bound beans.

A correct env name resolves property identification, but the final configuration still needs valid values and source ordering.

## 20. Key takeaways

Spring Boot's canonical rule for transforming **canonical property name → environment variable name** consists of three operations: **dots become underscores, hyphens are removed, letters become uppercase**.

~~~text
app.feature.max-retries  -> APP_FEATURE_MAXRETRIES
app.feature.max.retries  -> APP_FEATURE_MAX_RETRIES
~~~

These two examples highlight the important difference between **a field with a compound name** and **two property levels**. For lists, indices are represented as **_0_**, **_1_** in the variable name.

**@ConfigurationProperties** uses relaxed binding and type conversion; **System.getenv** only reads environment variables directly; **Environment** applies Spring's PropertySource mechanism. The right name alone does not guarantee the value wins, since environment variables can be overridden by JVM system properties, command-line arguments, or higher-priority sources.

For real configurations, publish one canonical name, one official env name, and one clear data type. When troubleshooting, trace the chain **canonical property → env var → process environment → Spring Environment → target bean** to find the exact cause.
