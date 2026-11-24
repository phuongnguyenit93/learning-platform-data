# Comparing Environment Variables, JVM System Properties, and Command-Line Arguments in Spring Boot

## Objectives

When a Spring Boot application runs on a developer's machine, server, or container, the same configuration property can be declared in multiple places. For example, the value of **app.report.timeout** can appear in application.yml, an operating system environment variable, a JVM system property, or an argument passed to the application at startup. To troubleshoot configuration issues, you need to answer three questions: where does the value come from, which source wins when keys collide, and how do you verify the value Spring Boot actually uses.

After this lesson, learners will be able to:

- Distinguish between an environment variable, a Java system property (JVM system property), and an application command-line argument (Spring Boot command-line argument).
- Predict the effective value when multiple sources declare the same key.
- Write the right configuration-passing syntax on Linux/macOS, Windows PowerShell, and deployment environments.
- Understand how Spring Boot maps environment variable names to properties via relaxed binding.
- Diagnose cases where the value in Spring Environment differs from values read directly from the JVM or operating system.

## 1. Three Configuration Sources Are Three Different Mechanisms

| Source | Who owns the value? | Typical syntax | Direct access API | Scope |
| --- | --- | --- | --- | --- |
| Environment variable | Operating system, shell, container, or orchestrator | APP_REPORT_TIMEOUT=30s | System.getenv("APP_REPORT_TIMEOUT") | The process given the variable and inherited child processes |
| JVM system property | The Java Virtual Machine of the current process | -Dapp.report.timeout=45s | System.getProperty("app.report.timeout") | One JVM |
| Spring Boot command-line argument | Argument received by the application after launching the JAR | --app.report.timeout=60s | ApplicationArguments and Spring Environment | One application run |

**Environment variables** are set before or when creating a process. Platforms such as Docker, Kubernetes, CI/CD, and application hosting services usually provide a mechanism to pass them without modifying the JAR package.

A **JVM system property** is a key/value pair managed by Java inside the process. It can be passed with the **-D** option when invoking the **java** command, or set with System.setProperty(...) in code. It is not an operating system environment variable.

A **Spring Boot command-line argument** is an argument of the form **--property.name=value** passed into the main(String[] args) method. By default, SpringApplication converts these option arguments into a PropertySource so Spring Environment can look them up.

Key point: **System.getenv**, **System.getProperty**, and **Environment.getProperty** are not three equivalent calls. The first two read one specific kind of source directly; the last searches in precedence order across the PropertySources that Spring has assembled.

## 2. Example Comparing the Same Key

Suppose the application has a default configuration:

~~~yaml
# src/main/resources/application.yml
app:
  report:
    timeout: 15s
~~~

Run on Linux/macOS:

~~~bash
APP_REPORT_TIMEOUT=30s java -Dapp.report.timeout=45s -jar demo.jar --app.report.timeout=60s
~~~

All four sources supply the logical key **app.report.timeout**. In a typical Spring Boot run, the result is as follows:

| Source | Value | Outcome |
| --- | --- | --- |
| application.yml | 15s | Overridden |
| Environment variable APP_REPORT_TIMEOUT | 30s | Overridden |
| JVM property -Dapp.report.timeout | 45s | Overridden |
| Application argument --app.report.timeout | 60s | **Effective value** |

If you remove **--app.report.timeout=60s**, the effective value becomes **45s**. If you also remove **-Dapp.report.timeout=45s**, the value becomes **30s**. Without all three external sources, the application gets **15s** from application.yml.

Java configuration example:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.report")
public record ReportProperties(Duration timeout) {
}
~~~

When this configuration is registered via **@ConfigurationPropertiesScan** or **@EnableConfigurationProperties(ReportProperties.class)**, the timeout property is bound as a Duration corresponding to **60 seconds** in the run above. A valid key name can also be accessed via **Environment.getProperty("app.report.timeout")**, without needing to know which source it came from.

Let's inspect Java and Spring directly:

~~~java
@Component
public class ConfigurationProbe implements ApplicationRunner {
    private final Environment environment;

    public ConfigurationProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("OS: " + System.getenv("APP_REPORT_TIMEOUT"));
        System.out.println("JVM: " + System.getProperty("app.report.timeout"));
        System.out.println("Spring: " + environment.getProperty("app.report.timeout"));
        System.out.println("CLI: " + args.getOptionValues("app.report.timeout"));
    }
}
~~~

In the run above, the four lines show **30s**, **45s**, **60s**, and a list containing **60s**, respectively. This explains why printing System.getProperty(...) to "check Spring configuration" can lead to wrong conclusions: the winning value lives in Spring Environment, not necessarily in JVM system properties.

## 3. Precedence Order: Which Source Overrides Which?

For the main sources in this lesson, considering the same property name in a normal Spring Boot startup:

~~~text
Spring Boot command-line argument (--key=value)
                  higher than
JVM system property (-Dkey=value)
                  higher than
OS environment variable (KEY=value)
                  higher than
Configuration in application.properties / application.yml
~~~

Spring Boot has many other configuration sources beyond these four groups, so this is the order **among the sources being compared**, not the entire precedence order in every context. For example, **SPRING_APPLICATION_JSON** is a special source that can rank higher than standard system properties and environment variables; test-specific sources or DevTools settings also have their own positions. Profile-specific files, external files outside the JAR, and multi-document YAML files also have precedence rules *within the config data group*.

Spring iterates through the PropertySource collection by precedence to find the value for the requested key. When two sources contain an equivalent logical key, the higher-precedence source determines the outcome. This override does not modify the original application.yml file, environment variable, or JVM system property.

You can see this through an elimination test removing one source at a time:

~~~bash
# File config only: default 15s
java -jar demo.jar

# Environment variable beats file: 30s
APP_REPORT_TIMEOUT=30s java -jar demo.jar

# JVM beats environment variable: 45s
APP_REPORT_TIMEOUT=30s java -Dapp.report.timeout=45s -jar demo.jar

# Spring Boot argument beats JVM: 60s
APP_REPORT_TIMEOUT=30s java -Dapp.report.timeout=45s -jar demo.jar --app.report.timeout=60s
~~~

**Scope note:** If an application actively adds a custom PropertySource with a different precedence, or disables accepting command-line properties, the result must be evaluated according to the application's actual configuration. The examples above use Spring Boot's default behavior.

## 4. Correct Placement of -D and -- When Running a JAR

This command has three distinct parts:

~~~text
[ENV_VARS] java [JVM_OPTIONS] -jar [JAR_NAME] [APP_ARGS]
~~~

Correct example:

~~~bash
SERVER_PORT=8081 java -Dserver.port=8082 -jar demo.jar --server.port=8083
~~~

- **SERVER_PORT=8081** supplies an environment variable to the Java process.
- **-Dserver.port=8082** comes before **-jar**, so the JVM receives it as a system property.
- **--server.port=8083** comes after the JAR name, so Spring Boot receives it as an application argument.
- The final HTTP port will be **8083**, assuming the application uses the default Spring Boot web server and no higher-precedence source intervenes.

The following command is very easy to misread:

~~~bash
java -jar demo.jar -Dserver.port=8082
~~~

Because **-Dserver.port=8082** sits after the JAR, it is an application argument, not a JVM option. Spring Boot by default accepts command-line properties using the **--server.port=8082** syntax (two dashes), so a **-D...** argument in this position does not configure the property as expected.

In Windows PowerShell, the syntax for setting environment variables differs from Bash:

~~~powershell
$env:APP_REPORT_TIMEOUT = "30s"
java -Dapp.report.timeout=45s -jar demo.jar --app.report.timeout=60s
~~~

A variable set with **$env:** persists in the current PowerShell session and is passed to processes launched from that session. If you want to verify a run without that variable, remove it from the shell session's environment before the next run.

## 5. Environment Variable Names and Relaxed Binding

Names in application.yml typically use lowercase letters, dots, and dashes, whereas environment variable names typically use uppercase letters and underscores. Spring Boot supports **relaxed binding** to bind corresponding forms to configuration properties.

For canonical configuration names, the conversion rule to environment variables is:

1. Replace dots **.** with underscores **_**.
2. Remove dashes **-** inside each name segment.
3. Convert all letters to uppercase.

Examples:

| Spring Boot Property | Corresponding Environment Variable |
| --- | --- |
| server.port | SERVER_PORT |
| spring.profiles.active | SPRING_PROFILES_ACTIVE |
| spring.datasource.url | SPRING_DATASOURCE_URL |
| app.report.timeout | APP_REPORT_TIMEOUT |
| app.payment.retry-count | APP_PAYMENT_RETRYCOUNT |

The last example is particularly notable: **app.payment.retry-count** turns into **APP_PAYMENT_RETRYCOUNT** per the official rule for environment variables. Do not assume that every dash must turn into a new underscore. For custom configuration, use canonical lowercase kebab-case names so binding stays clear and consistent.

When binding lists, indices are typically surrounded by underscores; for example, the environment variable **MY_SERVICE_0_OTHER** can correspond to **my.service[0].other** when bound to an appropriate structure.

**Caveat to remember:** Relaxed binding maps naming styles, rather than turning any arbitrary name into the same property. In particular, map keys, list indices, and non-standard characters must be evaluated under the binding rules for that data structure. When in doubt, inspect the value that the **@ConfigurationProperties** bean actually receives.

## 6. Distinguishing Configuration Reads Across Three APIs

The snippet below illustrates the same key accessed from three APIs:

~~~java
String fromOs = System.getenv("APP_REPORT_TIMEOUT");
String fromJvm = System.getProperty("app.report.timeout");
String fromSpring = environment.getProperty("app.report.timeout");
~~~

- **System.getenv(...)** only returns the process's environment variable; it knows nothing about application.yml, **-D**, or **--**.
- **System.getProperty(...)** only returns the JVM system property; it does not apply Spring's precedence order.
- **Environment.getProperty(...)** searches across registered PropertySources, thereby reflecting Spring's precedence at read time.
- **@Value** and **@ConfigurationProperties** use Spring's configuration resolution mechanism; with **@ConfigurationProperties**, binding also supports type conversions such as Duration, DataSize, boolean, and nested structures.

For instance, when reading **Environment.getProperty("app.report.timeout")** and comparing it with **ReportProperties.timeout()**, the string value and the Duration object differ in representation type yet share the same meaning if binding succeeds. Check both the value and the data type when debugging conversion errors.

When a program calls System.setProperty(...) itself at runtime, the new value can affect subsequent Environment lookups if system properties are being used as a PropertySource. However, configuration beans already created and bound earlier are not automatically rebound. You should not treat mutating a system property after startup as a safe hot-reload mechanism.

## 7. Passing Configuration in Containers and Pipelines

With Docker, the parameter groups retain the same nature as running directly on a host machine:

~~~bash
docker run --rm -e APP_REPORT_TIMEOUT=30s demo-image
~~~

This variable is attached to the environment of the process inside the container. If the image's entrypoint runs **java -jar demo.jar**, Spring Boot can bind **APP_REPORT_TIMEOUT** just like an environment variable on a physical machine.

In Kubernetes, a container's **env** section plays the same role:

~~~yaml
containers:
  - name: demo
    image: demo-image
    env:
      - name: APP_REPORT_TIMEOUT
        value: "30s"
~~~

When the container is simultaneously launched with **-Dapp.report.timeout=45s** or the application argument **--app.report.timeout=60s**, precedence still follows Spring Boot's PropertySources. Docker/Kubernetes only determines how values are supplied to the process and does not alter Spring's precedence order.

For sensitive configuration, do not put real passwords or tokens in command examples, commits, or logs. Depending on the platform, command-line arguments and environment variables can show up in process monitoring tools or deployment manifests. Use a proper secrets management mechanism and restrict permissions to view configuration data.

## 8. Real-World Scenarios That Easily Cause Discrepancies

### 8.1. An Environment Variable Is Set, Yet the Application Receives a Different Value

First check whether **-D** or **--** sets the same key. The existence of an environment variable does not mean it has the highest precedence. With a launcher or startup script, inspect the arguments the script actually passes to the JVM and the application.

### 8.2. Placing -D After -jar

That is the position for application arguments, not JVM options. Move **-Dkey=value** before **-jar**, or use **--key=value** after the JAR if you want to leverage Spring Boot's command-line properties mechanism.

### 8.3. Entering the Environment Variable Name Incorrectly

Match the canonical name against relaxed binding rules; distinguish dots between segments, dashes within names, and list indices. When configuration is bound into a class, verify the class's prefix and field names.

### 8.4. Passing --key=value Without Seeing Any Change

By default SpringApplication adds command-line properties; however, the application may call **SpringApplication.setAddCommandLineProperties(false)** to disable that mechanism. Also verify whether the arguments actually reach **main(String[] args)** or are intercepted earlier by a script/launcher.

### 8.5. Two Sources Have the Same Value

If both the file and the environment variable specify **30s**, looking only at the final value cannot prove which source won. To identify the source, inspect the PropertySource collection or diagnostic tools that show configuration origin.

### 8.6. An Empty Value Is Not the Same as Being Undeclared

An environment variable assigned an empty value may still count as a supplied configuration value. For some properties, this can result in an empty result or conversion error instead of automatically falling back to the value in application.yml. Clearly distinguish an **absent** variable, a variable that **exists but is empty**, and a variable with a **value**.

### 8.7. Configuration Used Too Early

Keys such as **spring.config.location**, **spring.config.additional-location**, and **spring.config.name** affect the phase where Spring Boot locates and loads configuration files. These values should come from sources available early at startup, such as environment variables, system properties, or command-line arguments. You cannot expect a file that is only discovered thanks to such a key to instruct Spring Boot how to find itself.

### 8.8. Running Spring Boot Tests

In a test environment, **@SpringBootTest(properties = ...)**, **@TestPropertySource**, and **@DynamicPropertySource** can add PropertySources with precedence different from a normal JAR run. Therefore, test results do not necessarily prove the exact order across all sources in a production deployment.

## 9. How to Diagnose Effective Configuration

The first step is to pick **one specific key** causing trouble, such as **app.report.timeout**, and record how the application is launched. Then check in order:

1. **Configuration files:** Do application.yml, application.properties, and active profile files declare that key?
2. **Process environment variables:** Was the name converted properly according to relaxed binding and does it actually exist in the application process?
3. **JVM options:** Is **-Dapp.report.timeout=...** placed before **-jar** or inside the launcher's JVM configuration?
4. **Application arguments:** Is **--app.report.timeout=...** in the args received by SpringApplication?
5. **Spring Environment:** What does **environment.getProperty("app.report.timeout")** actually return?
6. **Consuming bean:** When does the bean read it, does it bind to another type, or does it have custom post-processing logic after receiving the configuration?

When the application includes Spring Boot Actuator with endpoints configured and secured appropriately, the **/actuator/env** endpoint or property-specific lookup path can help find values and origins. Sensitive data may be masked; the endpoint not displaying the full value does not mean the configuration is missing. Do not expose the env endpoint publicly just to debug a single variable.

When you need to inspect PropertySources in code, you can iterate over source names without printing all values:

~~~java
@Component
class PropertySourceInspector implements ApplicationRunner {
    private final ConfigurableEnvironment environment;

    PropertySourceInspector(ConfigurableEnvironment environment) {
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

The order and list of sources in a specific application explain why a declared configuration was not chosen. To look up the exact source containing a key, consider possible key name normalization and custom handling by PropertySources; printing all of their contents risks leaking secrets, so use only safely filtered data.

## 10. Hands-On Exercise: Predict Then Observe

Keep **app.report.timeout=15s** in application.yml and create a run with three external sources:

~~~bash
APP_REPORT_TIMEOUT=20s java -Dapp.report.timeout=25s -jar demo.jar --app.report.timeout=30s
~~~

Predict the results read from **System.getenv("APP_REPORT_TIMEOUT")**, **System.getProperty("app.report.timeout")**, and **Environment.getProperty("app.report.timeout")**. Then remove just **--app.report.timeout=30s**, run again, and compare. Finally, also remove **-Dapp.report.timeout=25s** and repeat the measurement.

Expected results under default behavior:

| Run | System.getenv | System.getProperty | Spring Environment |
| --- | --- | --- | --- |
| All three external sources present | 20s | 25s | **30s** |
| Omit -- argument | 20s | 25s | **25s** |
| Omit both -- and -D | 20s | null | **20s** |
| Also omit environment variable | null | null | **15s** |

This exercise highlights an overarching principle: **you cannot determine a Spring Boot configuration value by looking at a single environment variable or JVM property in isolation; you must consider all participating sources and their precedence**. Once you understand these three input types and know how to check Spring Environment, you can explain most "I configured it but the application didn't pick it up" issues without changing business code.