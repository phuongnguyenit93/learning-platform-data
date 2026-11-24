# The Role of spring.config.import and Differences from spring.config.location in Spring Boot

## Objectives

Spring Boot supports loading configuration from many places: **application.properties**, **application.yml**, profile-specific files, directories outside the JAR, and additional integrated configuration sources. Two similarly named properties, **spring.config.import** and **spring.config.location**, are often mistaken for equivalent ways of writing the same thing, resulting in files not being loaded, default configuration disappearing, or the final value differing from expectations.

This lesson explains the **Config Data** process at application startup, the role of **spring.config.import**, how to distinguish it from **spring.config.location** and **spring.config.additional-location**, path resolution, precedence, profiles, handling missing sources, and common real-world deployment scenarios.

After studying this lesson, readers will be able to:

- Use **spring.config.import** to load additional configuration from a file or a supported source.
- Choose appropriately between **import**, **location**, and **additional-location** based on deployment goals.
- Explain which file is searched first and which file can override values from another file.
- Distinguish **classpath:**, **file:**, relative paths, and the **optional:** prefix.
- Know at which stage **spring.config.location** must be configured, and why placing it in application.yml usually does not have the expected effect.
- Diagnose errors related to missing files, profiles, property overrides, and paths when running via a JAR or container.

## 1. What is Config Data?

In Spring Boot, **Config Data** is the mechanism for locating, reading, and merging configuration documents early during startup. Those documents are typically `.properties` or `.yml`/`.yaml` files, though this mechanism can also accept other location types if the application adds an appropriate location resolver.

When no alternative location is specified, Spring Boot searches the default application configuration locations, typically including places such as:

- The classpath root.
- The **config/** directory in the classpath.
- The current working directory.
- The external **config/** directory outside the application.
- Immediate subdirectories of the external **config/** directory, following the default search rules.

The default file name is tied to **spring.config.name**, usually **application**. Therefore, Spring Boot can look for **application.properties**, **application.yml**, profile-specific variants such as **application-dev.yml**, and other environment-matching configurations.

You should not imagine this process as a single read operation followed by closing the file. A document can declare **spring.config.import** to open additional documents. Those documents are then added to Spring's configuration property sources according to specific precedence rules.

Here is a simple diagram:

~~~text
Startup command / environment variables / JVM properties
                    |
                    v
    Determine Config Data name and locations
                    |
                    v
      Load discovered application.yml
                    |
                    +-- spring.config.import --> extra.yml
                    |
                    v
       Create property sources (PropertySource)
                    |
                    v
          Spring Environment and Binder
                    |
                    v
       Application beans receive configuration
~~~

Here, **import** expands the set of documents starting from an already discovered document. Conversely, **location** controls **where Spring Boot starts searching for configuration**. That is the core difference.

## 2. What is spring.config.import used for?

**spring.config.import** declares additional configuration locations to load when Spring Boot processes a Config Data document. It is usually written directly inside `application.yml` or `application.properties`.

For example, an application has:

~~~yaml
# src/main/resources/application.yml
spring:
  application:
    name: order-service
  config:
    import: "optional:file:./config/order-overrides.yml"

order:
  processing:
    timeout: 5s
~~~

External file:

~~~yaml
# ./config/order-overrides.yml
order:
  processing:
    timeout: 15s
    retries: 4
~~~

When run from a directory containing **./config/order-overrides.yml**, the application loads `application.yml` and then processes the declared import location. In the default Config Data mechanism, an imported document **has higher precedence than the document that declares the import**, so the **order.processing.timeout** value from the additional document can win over the **5s** value in the original document.

Expected results for the two keys in the example:

| Property | application.yml | Imported file | Effective value between the two documents |
| --- | --- | --- | --- |
| order.processing.timeout | 5s | 15s | **15s** |
| order.processing.retries | Not declared | 4 | **4** |

The **optional:** keyword is used because the additional file is optional. If it does not exist, the application can still start and use **5s** for the timeout, provided there are no other configuration errors.

In a `.properties` file, the equivalent content is:

~~~properties
spring.application.name=order-service
spring.config.import=optional:file:./config/order-overrides.yml
order.processing.timeout=5s
~~~

Spring Boot supports reading compatible configuration file formats under the Config Data mechanism, so the main file and the imported file do not have to share the same file extension.

### 2.1. Import is not a Java import statement

**spring.config.import** is a property used by the Spring Boot startup process, not Java's **import** syntax or a text concatenation of two files.

Spring processes each document as Config Data with its own location and precedence order. An imported file can declare the same property name as the original file; when that happens, precedence rules apply. Loading an additional document does not mean two YAML trees are merged by appending lines into the same mapping.

### 2.2. A single document can declare multiple imports

Example:

~~~yaml
spring:
  config:
    import:
      - "classpath:/shared/common.yml"
      - "optional:file:./config/site.yml"
      - "optional:file:./config/local.yml"
~~~

This list allows bringing shared configuration, site-specific configuration, and local configuration into the same flow. Another compact syntax in `.properties`:

~~~properties
spring.config.import=classpath:/shared/common.yml,optional:file:./config/site.yml,optional:file:./config/local.yml
~~~

When multiple imports are declared together, Spring Boot processes the precedence of the loaded documents; if these imports define the same key, **an import listed later can override an earlier import** according to standard Config Data rules.

An imported location may only be loaded once even if declared repeatedly. Therefore, do not rely on repeating the same location to force Spring to "load it a second time" at a new precedence position.

### 2.3. An imported document can itself declare further imports

Example:

~~~text
application.yml
  |
  +-- import: ./config/common.yml
                    |
                    +-- import: feature.yml
~~~

This creates a configuration dependency chain. For large configurations, keep this chain short, easy to trace, and governed by clear file ownership conventions. Operators need to know which file is the starting point and which files are referenced by another document, rather than guessing where files are automatically scanned.

## 3. Distinguishing import, location, and additional-location

These three properties address three distinct needs:

| Property | Role | Where is it usually declared? | Effect on default locations? |
| --- | --- | --- | --- |
| **spring.config.import** | Loads additional documents from locations declared by the current document | application.yml, application.properties, or another Config Data document | Does not by itself replace the default location set |
| **spring.config.location** | Specifies the set of locations used to search for Config Data at startup | Environment variable, JVM system property, or command-line argument | **Replaces** the default location set |
| **spring.config.additional-location** | Adds extra search locations to the default set | Environment variable, JVM system property, or command-line argument | **Keeps** the default locations and adds new locations |

Comparison diagram:

~~~text
Default:
  [Default config search locations] --> application.yml

With spring.config.import in application.yml:
  [Default locations] --> application.yml --> imported file

With spring.config.location at startup:
  [Locations specified via location] --> files at those locations

With spring.config.additional-location at startup:
  [Default locations + additional locations] --> discovered documents
~~~

### 3.1. When to choose import?

Use **spring.config.import** when an already loaded document **needs to depend on or extend itself with** another configuration.

Examples:

- `application.yml` always declares an import for an additional billing module file.
- Profile-specific configuration needs to load the configuration file of a specific integration.
- A configuration file imports a configuration tree mounted into a container.
- The application uses an added resolver, allowing import of a specialized configuration source.

The advantage is that the dependency relationship lives right inside the main configuration file. Anyone reading `application.yml` can see what else the application needs to load.

### 3.2. When to choose location?

Use **spring.config.location** when operators need to decide that the application **only looks for configuration files in the provided set of locations**, instead of the defaults.

Example:

~~~bash
java -jar demo.jar --spring.config.location=optional:file:./deployment/application.yml
~~~

Here, the default location set is replaced. You should not expect the `application.yml` packaged inside the JAR to still load automatically if it is not within the new location set and is not imported by an already loaded document.

This can be useful when the deployment environment manages all configuration as a self-contained bundle. However, if the application relies on default values in the classpath, changing **location** carelessly can cause those values to disappear.

### 3.3. When to choose additional-location?

Use **spring.config.additional-location** when you want to **keep the configuration packaged inside the JAR** while allowing the deployment environment to add or override certain properties:

~~~bash
java -jar demo.jar --spring.config.additional-location=optional:file:./deployment/
~~~

The trailing **/** indicates that this is a directory location. Spring Boot uses the active configuration name, typically **application**, to search for files inside the directory.

Files in `additional-location` can override default configuration according to the precedence rules between locations. This approach fits well when sharing a single JAR across multiple environments: the JAR holds defaults, while the deployment path holds overrides.

## 4. Why must location be set early?

Consider the following idea:

~~~yaml
# src/main/resources/application.yml
spring:
  config:
    location: "file:./my-runtime/"
~~~

The author's goal is to tell Spring Boot to look for configuration in **my-runtime/**. However, this creates a circular dependency: to read the value of **spring.config.location**, Spring must find and load **application.yml** first, while **location** itself decides where to look for `application.yml`.

Therefore, **spring.config.location**, **spring.config.additional-location**, and **spring.config.name** are properties that control the search process very early. They need to be supplied **before Config Data is loaded**, typically via:

- Application argument: **--spring.config.location=...**
- JVM system property: **-Dspring.config.location=...**
- Environment variable: **SPRING_CONFIG_LOCATION=...**

Correct example:

~~~bash
java -Dspring.config.location=optional:file:./my-runtime/ -jar demo.jar
~~~

Or:

~~~bash
SPRING_CONFIG_ADDITIONAL_LOCATION=optional:file:./deployment/ java -jar demo.jar
~~~

On Windows PowerShell:

~~~powershell
$env:SPRING_CONFIG_ADDITIONAL_LOCATION = "optional:file:./deployment/"
java -jar demo.jar
~~~

In contrast, **spring.config.import** is designed to be declared *inside* a Config Data document that Spring has already found, and then expand the loading process. This is why these two properties are configured at different points in the startup lifecycle.

## 5. Does location point to a file or a directory?

A location can describe a specific file or a search directory. This distinction matters most with **spring.config.location** and **spring.config.additional-location**.

### 5.1. Specifying a file

~~~bash
java -jar demo.jar --spring.config.location=optional:file:./deployment/worker.yml
~~~

This location points to a file with an explicit name. If the path exists, Spring Boot can read the corresponding file. If multiple files or location groups are declared, each location is processed according to the corresponding precedence mechanism.

### 5.2. Specifying a directory

~~~bash
java -jar demo.jar --spring.config.additional-location=optional:file:./deployment/
~~~

Because the location ends with **/**, it is a directory. Spring Boot combines it with **spring.config.name** to look for names such as **application.properties** or **application.yml**, along with profile variants when applicable.

If you use:

~~~bash
java -jar demo.jar --spring.config.name=myapp --spring.config.additional-location=optional:file:./deployment/
~~~

Spring Boot searches for the corresponding **myapp** configuration name, not just any arbitrary file name in the directory. A directory containing **custom.yml** will not be loaded simply because it sits inside **deployment/**, unless the search name or another import/location declaration points to that file.

### 5.3. Commas and semicolons in location

Spring Boot allows declaring multiple locations when setting paths. A **,** typically separates locations in sequence; a **;** represents a **location group**, in which locations are treated at the same level when evaluating profile-specific configuration precedence.

Example illustrating the two styles:

~~~text
classpath:/defaults/,file:./deployment/
classpath:/defaults/;file:./deployment/
~~~

The two strings can produce different precedence orders when profile-specific files exist in multiple locations. When a complex location group affects the result, inspect **spring.config.name**, active profiles, and group ordering rather than only reading standard file order.

In a shell, **;** can be a command separator character. Wrap the argument value in quotes appropriate for your shell to avoid unintentionally splitting the command.

## 6. Path resolution for spring.config.import

When declaring an import, distinguish between a **fixed location** and an **import-relative location**.

### 6.1. Fixed location

A location starting with an explicit scheme such as **classpath:** or **file:** is treated as a fixed location.

~~~yaml
spring:
  config:
    import:
      - "classpath:/shared/settings.yml"
      - "optional:file:./deployment/extra.yml"
~~~

- **classpath:/shared/settings.yml** points to a resource in the application classpath at the specified path.
- **file:./deployment/extra.yml** is a file path relative to the process's working directory, with the **file:** scheme prefix; in deployment scenarios, the working directory must be clearly defined.
- **optional:** allows skipping a non-existent location that would otherwise cause a loading error.

Do not assume **file:./...** means "relative to the `application.yml` file inside the JAR". File system paths do not automatically reside in the same directory as classpath resources.

### 6.2. Import-relative location

When there is no fixed location scheme or marker, an import can be resolved **relative to the document that declares it**.

For example, the file:

~~~text
classpath:/features/application.properties
~~~

contains:

~~~properties
spring.config.import=feature-flags.properties
~~~

Then the location **feature-flags.properties** can be resolved relative to the declaring file, corresponding to the resource in the same area:

~~~text
classpath:/features/feature-flags.properties
~~~

Similarly, if a file outside the JAR declares a relative import, the location of the file declaring the import participates in determining the target path.

Rule of thumb: **use relative paths to keep two configuration files together; use classpath: or file: when you want the target location stated explicitly**. Do not mix these two meanings in the same example and infer behavior from the working directory.

### 6.3. Extensionless locations

Some deployment systems mount configuration files with names that have no extension, such as **/etc/myapp/config**. Spring Boot can use an **extension hint** to know the format:

~~~properties
spring.config.import=file:/etc/myapp/config[.yaml]
~~~

The **[.yaml]** part instructs the loader to parse the content as YAML; it is not a requirement to rename the file on the filesystem. If a file is mounted from a Secret or ConfigMap without an extension, this mechanism may be necessary.

Distinguish the extension hint for a single file from loading **configtree:** from a directory, which is covered later.

## 7. Optional and handling missing locations

Not every location has the same requirement level.

### 7.1. Mandatory import

~~~yaml
spring:
  config:
    import: "file:./config/service.yml"
~~~

If the file does not exist or the location cannot be found by the corresponding loader, Spring Boot may halt startup with an error in the **ConfigDataLocationNotFoundException** family or a message indicating a location could not be found.

A path error at startup is different from "the application still runs but the value is empty": in this situation, Config Data loading may fail to complete.

### 7.2. Optional import

~~~yaml
spring:
  config:
    import: "optional:file:./config/service.yml"
~~~

If the file does not exist, Spring Boot can skip that location. Configuration already loaded from other sources is preserved.

**optional:** only handles the missing-location case under supported rules. It **does not mean** that YAML content errors, parse errors, binding errors, remote service authentication errors, or access errors are swallowed. Do not use `optional:` to mask configuration that the system strictly requires.

### 7.3. Applying optional to location

Example:

~~~bash
java -jar demo.jar --spring.config.additional-location=optional:file:./site-config/
~~~

If the **site-config/** directory does not exist, the application can still proceed with the default configuration. This suits development environments that do not have separate deployment files.

For production environments, consider whether external configuration is mandatory. If the file contains service addresses or essential security settings, omitting `optional:` can help errors surface early when deployment is misconfigured.

You may encounter **spring.config.on-not-found=ignore** to change global handling when Config Data is not found; this is a broad setting and should not be enabled merely to avoid fixing a wrong import path.

## 8. Precedence when one document imports another

This is a common source of confusion. Consider two files:

~~~yaml
# application.yml
spring:
  config:
    import: "classpath:/config/extra.yml"

demo:
  mode: standard
  timeout: 10s
~~~

~~~yaml
# config/extra.yml on the classpath
demo:
  mode: enhanced
  retries: 3
~~~

With these two documents, the imported file has higher precedence than the importing document for conflicting keys. Result from Config Data:

~~~properties
demo.mode=enhanced
demo.timeout=10s
demo.retries=3
~~~

Because imports are inserted according to Config Data document precedence rules, **the physical position of the spring.config.import line at the top or bottom of the file does not decide which wins**. There is no need to move the import line above `demo.mode` expecting to change the result.

Now add an application argument:

~~~bash
java -jar demo.jar --demo.mode=cli
~~~

In the standard source order, command-line properties have higher precedence than Config Data; **demo.mode** is now **cli**. Therefore, saying "an import beats the original file" only describes the relationship between the Config Data documents under consideration, **it does not mean the imported file beats every other source in the Spring Environment**.

### 8.1. Multiple imports declared together

~~~properties
spring.config.import=classpath:/config/base-extra.properties,classpath:/config/team-extra.properties
~~~

If both documents contain **demo.mode**, the import listed later can have higher precedence than the earlier import. Keep the ordering expressive of intent: from general configuration to environment- or team-specific overrides.

When a project has multiple profile-specific documents or location groups, the actual ordering is more complex than a two-file example. When debugging, identify the list of loaded documents and check the highest-precedence source containing that key.

### 8.2. Imports do not append lists additively

If both the original file and the imported file declare a list, do not assume the list in the imported file will be appended to the end of the original file's list.

Example:

~~~yaml
# application.yml
app:
  nodes:
    - alpha
    - beta
~~~

~~~yaml
# extra.yml
app:
  nodes:
    - gamma
~~~

When binding lists from Config Data sources, Spring Boot rules generally treat the list from the higher-precedence source as the active list, rather than combining elements one by one as in manual YAML merging. If you want all three elements, declare all three in the winning source or design a custom merging mechanism in the application.

For Maps, binding rules can combine different keys from multiple sources. Therefore, do not extrapolate how nested structures, lists, and maps behave from a single scalar example alone.

## 9. Imports and profiles

Spring Boot supports profile-specific files such as **application-dev.yml**, **application-prod.properties**, and conditional YAML documents using **spring.config.activate.on-profile**.

Example:

~~~yaml
# application.yml
spring:
  config:
    import: "optional:file:./config/payment.yml"
payment:
  mode: sandbox
~~~

If the **prod** profile is activated, the Config Data mechanism can also consider profile-specific variants of the imported locations, such as **payment-prod.yml** if present and supported at the corresponding location.

Base imported file:

~~~yaml
# config/payment.yml
payment:
  timeout: 2s
  endpoint: "https://sandbox.example.test"
~~~

Profile variant:

~~~yaml
# config/payment-prod.yml
payment:
  timeout: 5s
  endpoint: "https://payments.example.test"
~~~

When the `prod` profile is active, you must also consider profile-specific documents to determine the final value. Do not just read `payment.yml` and conclude that `timeout` is always `2s`.

### 9.1. Importing inside a conditionally activated document

A YAML file can be split into multiple documents using **---**:

~~~yaml
spring:
  application:
    name: demo
demo:
  stage: default

---
spring:
  config:
    activate:
      on-profile: dev
    import: "optional:file:./config/dev-overrides.yml"
demo:
  stage: development
~~~

The second document applies only when the profile condition matches. Consequently, the import belonging to that document may only be processed when the `dev` profile is active.

This situation differs from placing **spring.config.location** in a profile document: `location` determines the initial file search step and should not be placed inside a document that is only known after the file search step has already happened.

### 9.2. Active profiles must be known at the right time

Typically, profiles can be activated via an argument:

~~~bash
java -jar demo.jar --spring.profiles.active=prod
~~~

Or via an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar demo.jar
~~~

Active profiles affect which config data documents are selected; imports within activated documents can also bring additional configuration into the application.

Do not use **spring.profiles.active** inside a profile-specific document or a document activated via **spring.config.activate.on-profile**; Spring Boot restricts where profile activation properties can be declared. A cleaner design is to use startup arguments or a profile-independent base document to specify profiles.

## 10. Importing configtree from a directory mounted into a container

A special case is **configtree:**. Instead of reading a single YAML file containing many keys, Spring Boot can treat files inside a directory as configuration entries.

Suppose the deployment system mounts the directory:

~~~text
/run/secrets/service/
├── username
└── password
~~~

Where the **username** file contains the account name and the **password** file contains the password. You can declare:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/service/"
~~~

Spring Boot uses the config tree mechanism to place the corresponding entries into the Environment. This is a familiar pattern when deploying on platforms that mount Secrets or ConfigMaps as individual files.

If you want property names to have clear prefixes, arrange the directory structure accordingly or declare the `configtree` path according to actual platform conventions. Do not assume a **username** file in a file tree will automatically become **spring.datasource.username** without the proper structure or mapping.

**configtree:** differs from:

~~~yaml
spring:
  config:
    import: "file:/run/secrets/service/"
~~~

The second path only uses **file:** pointing to a directory and does not state that each file inside should become a property. To read a configuration tree, you must use the **configtree:** prefix and an appropriate directory structure.

Do not put real secret data into examples, commits, or logs. Config Data's ability to read secrets does not replace the need to restrict file permissions and management endpoints.

## 11. Importing remote configuration sources

**spring.config.import** is conceptually not limited to files in the JAR and files on disk. Spring Boot provides extension points **ConfigDataLocationResolver** and **ConfigDataLoader** so other integrations can provide ways to load Config Data.

For example, in an application with a compatible version of **Spring Cloud Config Client** installed, you might see:

~~~properties
spring.config.import=optional:configserver:
~~~

The **configserver:** prefix is not a default URL/file import in every plain Spring Boot application. It requires the appropriate library and integration mechanism. Without the necessary dependency, simply adding that import line will not automatically establish a connection to a config server.

Similarly, prefixes for secret management systems or external configuration systems only work when the project has the corresponding resolver/loader.

The key takeaway is:

- **Import** specifies an additional data source using a location protocol understood by the application.
- **Location** selects the initial Config Data search locations.
- A prefix outside the project's capabilities can cause a location or resolver error, not an error caused by missing quotes in `.properties` or YAML.

If a remote source is mandatory, clearly define how the application reacts when it cannot connect. The `optional:` prefix does not carry the same meaning for every kind of network, authentication, or format error.

## 12. Practical comparison scenarios

Suppose the JAR packages:

~~~yaml
# classpath:/application.yml
app:
  banner: "bundled"
  timeout: 4s
~~~

And the deployment machine has the file:

~~~yaml
# ./deployment/application.yml
app:
  banner: "deployed"
  retries: 3
~~~

### Scenario A: using spring.config.location

~~~bash
java -jar demo.jar --spring.config.location=file:./deployment/
~~~

The file from the specified location is found and loaded. Because the default location set is replaced, you cannot rely on the **timeout: 4s** default from the classpath file. If the external configuration lacks `timeout` and no other source declares it, this property may not be provided.

This approach fits when the deployment file manages configuration as a complete standalone set.

### Scenario B: using spring.config.additional-location

~~~bash
java -jar demo.jar --spring.config.additional-location=file:./deployment/
~~~

The default locations are kept and the deployment location is added. According to standard precedence rules between these locations, the external configuration can override **app.banner** to **deployed**, while **app.timeout** still receives **4s** if not replaced by another source.

This approach fits when you want to use defaults in the JAR and override per environment.

### Scenario C: using spring.config.import in application.yml

Change the packaged file to:

~~~yaml
spring:
  config:
    import: "optional:file:./deployment/application.yml"
app:
  banner: "bundled"
  timeout: 4s
~~~

No location needs to be passed at startup. The packaged file is found via the default mechanism, and then the import declaration causes the deployment file to be loaded as well. In the relationship between the two documents, the imported file takes precedence for **app.banner**, while **app.timeout** is kept from the original file.

This approach lets the application itself state that it supports an additional configuration file. If the imported file is mandatory, remove **optional:**.

### Scenario D: adding a command-line argument

Whether choosing approach B or C, a command such as:

~~~bash
java -jar demo.jar --app.banner=command-line
~~~

can cause **app.banner** to receive **command-line**, because application arguments generally have higher precedence than Config Data documents. Do not confuse the precedence order between the original file and the imported file with the full Spring `PropertySource` order.

## 13. Common errors and how to identify them

### 13.1. Imported file not found

**Symptom:** the application stops at startup with a message stating the location could not be found.

**Check:** path, `.yml`/`.yaml`/`.properties` extension, working directory, actual classpath, case sensitivity on the OS, and whether **optional:** is used intentionally.

**Example:**

~~~yaml
spring:
  config:
    import: "file:./config/runtime.yml"
~~~

If the JAR is run from another directory, **./config/runtime.yml** may not point where you expect. Before switching to `optional`, determine the file's actual location.

### 13.2. Default file is no longer loaded

**Symptom:** numerous values previously present in `application.yml` disappear after changing the startup command.

**Check:** whether **spring.config.location** was used to point to a new file/directory. Because `location` replaces the default set, consider switching to **spring.config.additional-location** if the real goal is only to override.

### 13.3. Placing spring.config.location in application.yml

**Symptom:** the author sees the property in the file, but Spring does not search for configuration at that path.

**Explanation:** properties controlling the search must be available before the file loading step. Pass `location` via command-line arguments, environment variables, or JVM system properties.

### 13.4. Importing an empty file or one with wrong keys

**Symptom:** the application still runs, but expected values do not change.

**Check:** whether the file has the exact key names, whether YAML indentation levels are correct, whether a profile-specific document is activated, and whether a higher-precedence source overrides it. A successful import does not mean every property in the file is valid for the target bean.

### 13.5. Repeated imports in multiple places

**Symptom:** assuming that declaring the same imported file twice will create two override layers.

**Explanation:** Config Data avoids importing the same location multiple times. If you need two independent sets of values, create two distinct locations with clear ordering and responsibilities.

### 13.6. Confusing a directory with a file in location

**Symptom:** specifying **file:./deployment** to look for **application.yml** inside it without success.

**Resolution:** if it is a directory location, write the trailing **/** explicitly, such as **file:./deployment/**. If it is a file, specify the exact file name and extension.

### 13.7. Confusing a relative path with the declaring file

**Symptom:** an imported file sits next to an external configuration file, yet the program looks in a different place.

**Resolution:** distinguish **import-relative** (no fixed prefix) from **file:./...** (file path relative to the working directory), and use one consistent style suitable for your packaging model.

### 13.8. A value is wrong only in the production profile

**Symptom:** the value is right in `dev` but different in `prod`.

**Check:** active profiles, **spring.config.activate.on-profile** documents, profile-specific files for imported locations, and group/location ordering. Also check production-specific environment variables and command-line arguments.

### 13.9. Path was found, but YAML is invalid

**Symptom:** the application reports a YAML parser error or binding error after importing.

**Explanation:** **optional:** cannot fix invalid file content. Fix the YAML syntax, duplicate keys, wrong data types, or target types of `@ConfigurationProperties`.

## 14. How to diagnose which configuration Spring Boot is using

When a runtime value differs from expectations, follow a concrete procedure:

1. **Write down the property name to inspect**, for example **app.timeout**.
2. **Record the exact startup command**: are **--spring.config.location**, **--spring.config.additional-location**, or **--spring.config.name** present?
3. **Identify the initial files Spring can find** according to the specified location or default locations.
4. **Read the `spring.config.import` entries in loaded files**, following the relevant dependency branches.
5. **Check profiles**, profile-activated YAML documents, and profile-specific variant files.
6. **Identify higher-precedence sources**, such as command-line args, JVM system properties, or environment variables.
7. **Inspect the Spring Environment or configuration bean result**, avoiding conclusions drawn solely from files.

Illustrative snippet that reads only an ordinary property:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ConfigDataProbe implements ApplicationRunner {
    private final Environment environment;

    ConfigDataProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("app.timeout = "
                + environment.getProperty("app.timeout"));
    }
}
~~~

The result of **Environment.getProperty(...)** shows the value seen by Spring's configuration resolution system at call time. It does not by itself tell you the source file; to find provenance, inspect the `PropertySource` entries or corresponding diagnostic tools.

An example listing source names:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

ConfigurableEnvironment env = /* provided Spring environment */;
for (PropertySource<?> source : env.getPropertySources()) {
    System.out.println(source.getName());
}
~~~

In real code, you can inject **ConfigurableEnvironment** into a suitable bean and iterate over it as above. Do not print the entire contents of every `PropertySource` to logs: imported files and `configtree` directories can contain deployment secrets.

If Spring Boot Actuator is used and properly secured, the `env` endpoint can help inspect properties and sources; sensitive data can be masked. Do not expose management endpoints publicly just to check a single import line.

### 14.1. Observing the Config Data loading process

In development environments, you can adjust the log level for the Config Data processing group when you need to understand file loading order. Exact logger names may vary across Spring Boot versions, so prefer verifying against actual logs and information in the running version.

Note also that **logging.config** and properties controlling very early startup have their own lifecycle characteristics; avoid placing them in sources that are only loaded after the system already needs them.

## 15. Practice exercises: choosing the right mechanism

### Exercise 1: Keep defaults in the JAR and override at deployment

Requirement: the application has an `application.yml` with a default timeout, and the production environment needs to override certain keys without modifying the JAR.

Appropriate command:

~~~bash
java -jar demo.jar --spring.config.additional-location=optional:file:./deployment/
~~~

Alternative: if you want the application itself to describe the additional file, declare an appropriate **spring.config.import** in `application.yml`. Both approaches preserve the base configuration; they differ in where the loading relationship is defined.

Do not choose **spring.config.location** just because you want to "add a file": it replaces the default search locations.

### Exercise 2: External configuration set outside the JAR as the sole source

Requirement: when running the JAR, use only configuration files in a centrally managed directory, without relying on default `application.yml` files inside the JAR.

Illustrative command:

~~~bash
java -jar demo.jar --spring.config.location=file:./managed-config/
~~~

With this directory, searched file names depend on **spring.config.name** and profiles. If a default file from the JAR must be kept, explicitly include it in the location set or configure an appropriate import.

### Exercise 3: Import only when an override file exists

~~~yaml
spring:
  config:
    import: "optional:file:./local-overrides.yml"
demo:
  feature-enabled: false
~~~

If `local-overrides.yml` does not exist, the application can continue using **demo.feature-enabled=false**. If the file exists and declares `true`, the imported value can beat the declaring file. If the command line specifies **--demo.feature-enabled=false**, the command-line value can still beat the files under default source ordering.

### Exercise 4: Analyzing precedence

Existing sources:

~~~yaml
# application.yml
spring:
  config:
    import: "classpath:/extra.yml"
demo:
  retries: 1
~~~

~~~yaml
# extra.yml
demo:
  retries: 2
~~~

And the application is started with:

~~~bash
DEMO_RETRIES=3 java -Ddemo.retries=4 -jar demo.jar --demo.retries=5
~~~

Under the standard source mechanism in this example, the candidate values are **1**, **2**, **3**, **4**, **5**, and the effective value is **5**. If you omit the command-line argument, the JVM system property **4** wins; if you also omit **-D**, the environment variable **3** wins; if you also omit the environment variable, the imported document **2** beats the original document **1**.

This exercise shows that an import has its own precedence within Config Data, yet still sits inside Spring Boot's overall `PropertySource` order.

## 16. Quick decision table

| What do you want to do? | Mechanism to consider | Why |
| --- | --- | --- |
| `application.yml` needs to pull in a specific extra file | **spring.config.import** | The dependency relationship is declared directly in the document |
| Deployment config needs to supplement JAR defaults | **spring.config.additional-location** | Keeps default locations and allows overrides |
| Replace everywhere Spring searches for default config | **spring.config.location** | The search location set is replaced |
| Change basename from `application` to custom | **spring.config.name** | Controls file names searched inside directories |
| Imported file may not exist on dev machines | **optional:** on the specific location | Avoids halting due to a missing location |
| Import individual secret files in a directory | **configtree:** | Exposes files in the tree as properties |
| Import a config source supported by another library | **spring.config.import** with the matching resolver | Loading mechanism is extended via dependencies |
| Change config per profile | Profile-specific files or `activate.on-profile` documents | Keeps environment configuration separated |
| Inspect actual runtime values | Spring `Environment` and `PropertySource` | Shows results after applying precedence |

## 17. Key takeaways

**spring.config.import** enables a Config Data document to load additional documents, and the imported document usually has higher precedence than the document that declared it. It is well suited for describing configuration dependencies directly in `application.yml` or `application.properties`.

**spring.config.location** controls the set of locations searched for Config Data at startup; it **replaces** the default locations. This property must be provided early during startup, typically via CLI, JVM system properties, or environment variables.

**spring.config.additional-location** extends the default location set rather than replacing it, making it a common choice when you only want external files outside the JAR to override some defaults.

**optional:** controls how missing locations are handled; **classpath:**, **file:**, and import-relative determine how paths are resolved; **configtree:** allows loading a file tree through a specialized mechanism.

Finally, the value the application actually uses also depends on profiles, import order, location groups, configuration sources outside Config Data, and binding into Java types. When an error occurs, trace the path **search locations → loaded documents → imported documents → PropertySource precedence → consuming bean** to pinpoint the exact cause.
