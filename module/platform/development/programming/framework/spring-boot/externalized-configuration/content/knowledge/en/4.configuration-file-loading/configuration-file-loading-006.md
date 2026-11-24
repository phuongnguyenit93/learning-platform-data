# Rules for File Paths, Directories, and Trailing Slashes

## 1. The Problem: How Does Spring Boot Recognize a Path as a File or a Directory?

Spring Boot allows separating configuration from source code and the JAR. At startup, the application searches for **application.properties**, **application.yml**, profile-specific variants, and explicitly specified files.

One of the most common configuration mistakes is writing a path to a **directory** but forgetting the trailing slash **/**. In Spring Boot 3.3's **Config Data** system, the syntax used to express where to search directly affects how Spring Boot processes it:

- **Directory location**: a directory onto which Spring Boot appends the **configuration file names** to look for.
- **File location**: a specific file with an explicit name and extension; Spring Boot loads that exact file.
- **Classpath location**: a resource on the application's classpath, typically inside the JAR after building.
- **Filesystem location**: a real file/directory on the filesystem of the running process.

This lesson focuses on **spring.config.location**, **spring.config.additional-location**, relative/absolute paths, the trailing **/** character, wildcards, profiles, and cases easily confused with **spring.config.import**.

## 2. Default Configuration Search Locations

By default Spring Boot uses the base name **application**, so common names are:

~~~text
application.properties
application.yml
application.yaml
application-dev.properties
application-prod.yml
~~~

Spring Boot 3.3 searches for Config Data in the following default location groups:

| Location | Meaning |
| --- | --- |
| **classpath:/** | Classpath root |
| **classpath:/config/** | The `config` directory on the classpath |
| **file:./** | Current working directory |
| **file:./config/** | The `config` directory under the working directory |
| **file:./config/*/** | Direct subdirectories of the `config` directory outside the JAR |

Values in higher-precedence locations can override matching keys from earlier locations. Profile-named files, such as **application-prod.yml**, are evaluated when the corresponding profile is active.

For example, after building:

~~~text
myproject/
├── app.jar
├── config/
│   ├── application.yml
│   ├── application-prod.yml
│   └── mysql/
│       └── application.properties
└── logs/
~~~

When running inside **myproject/**, Spring Boot can see external files in **./config/** and **./config/mysql/** via the default search paths.

**Key point to remember:** **./** is resolved from the *working directory of the Java process*, not necessarily the directory containing **app.jar**. If the same JAR is run from another directory, the meaning of **file:./config/** changes as well.

## 3. Directory Detection Rules and Trailing `/`

For locations declared in **spring.config.location** or **spring.config.additional-location**, if the intent is to **specify a directory**, **end it with a `/`**. Spring Boot will append file names generated from **spring.config.name** when searching.

| Path String | Intent and Handling |
| --- | --- |
| **file:./settings/** | Directory outside the JAR; searches for application.properties, application.yml, ... |
| **classpath:/settings/** | Directory on the classpath; searches for files by configuration base name |
| **file:/etc/myapp/** | Absolute directory on a Unix system |
| **file:./settings/runtime.properties** | Specific file; loads runtime.properties directly |
| **classpath:/defaults/base.yml** | Specific file on the classpath |
| **file:./settings** | Missing trailing **/** for the intent "this is a directory" |
| **file:./settings/runtime.properties/** | Trailing **/** added after a file name, conflicting with pointing to a file |

Therefore, these two forms are **not equivalent**:

~~~text
--spring.config.additional-location=file:./external/
--spring.config.additional-location=file:./external
~~~

In the first command, **external/** is expressed as a directory. In the second command, the author omitted the trailing **/** indicator that Spring Boot expects for a directory location; the location may be misinterpreted and the application files inside will not be searched as intended.

This rule has nothing to do with whether Windows Explorer displays **\\** or Linux uses **/** as a directory separator. Here we are using the URL/URI-style location syntax defined by Spring Boot, so examples use **/** for clarity and consistency.

## 4. Directory Location: Spring Boot Appends File Names Automatically

Suppose you are in the **run/** directory:

~~~text
run/
├── app.jar
└── deploy-config/
    ├── application.properties
    ├── application-dev.properties
    └── application-prod.properties
~~~

Contents of **deploy-config/application.properties**:

~~~properties
app.banner=external-default
server.port=8080
~~~

Contents of **deploy-config/application-dev.properties**:

~~~properties
app.banner=external-development
server.port=8081
~~~

Contents of **deploy-config/application-prod.properties**:

~~~properties
app.banner=external-production
server.port=8080
~~~

Start up:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./deploy-config/ \
  --spring.profiles.active=dev
~~~

Spring Boot knows **file:./deploy-config/** is a directory and uses the default name **application** to search for matching files. With profile **dev**, the two relevant files are:

~~~text
./deploy-config/application.properties
./deploy-config/application-dev.properties
~~~

The **app.banner** key can receive **external-development** from the profile-specific version.

Switch to:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./deploy-config/ \
  --spring.profiles.active=prod
~~~

Spring Boot evaluates **application-prod.properties** and can receive **external-production**. Both runs use the **same JAR**.

If the default file name is not **application**, for example you want to use **orders.yml**, supply **spring.config.name=orders** at startup:

~~~bash
java -jar app.jar \
  --spring.config.name=orders \
  --spring.config.additional-location=optional:file:./deploy-config/
~~~

Then directory locations are searched using the base name **orders** instead of **application**. The **spring.config.name** parameter is not a directory name.

## 5. File Location: Spring Boot Loads the Exact File Named

An application can receive configuration from a file not named **application**:

~~~text
run/
├── app.jar
└── deploy-config/
    ├── runtime.properties
    └── runtime-prod.properties
~~~

**runtime.properties**:

~~~properties
app.banner=runtime-default
~~~

**runtime-prod.properties**:

~~~properties
app.banner=runtime-production
~~~

Command:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./deploy-config/runtime.properties \
  --spring.profiles.active=prod
~~~

This is a **file location**, so Spring Boot loads **runtime.properties** by its specific name. Appropriate profile variants of the file location are also evaluated; with profile **prod**, **runtime-prod.properties** can be loaded.

Compare clearly:

~~~text
file:./deploy-config/
  -> searches for files matching spring.config.name in the directory

file:./deploy-config/runtime.properties
  -> loads the explicitly named runtime.properties file directly
~~~

If you specify **runtime.properties**, changing **spring.config.name=orders** does not rename that explicitly specified file.

**Do not add a trailing /** after **runtime.properties**. The **.properties**, **.yml**, or **.yaml** extension helps the loader recognize standard file formats.

In the same location, when both **application.properties** and **application.yml** exist with the same base name, Spring Boot prioritizes **.properties** under document rules. To avoid ambiguity, it is best to standardize on one configuration format per application.

## 6. Distinguishing `classpath:` and `file:`

### 6.1. `classpath:` is for application resources

Suppose the source code has:

~~~text
src/main/resources/
├── application.yml
└── defaults/
    ├── application.yml
    └── base.properties
~~~

After building, these resources are typically packaged and accessible on the classpath:

~~~text
classpath:/application.yml
classpath:/defaults/
classpath:/defaults/base.properties
~~~

If you want Spring Boot to search for default-named files in **defaults/**:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=classpath:/defaults/
~~~

If you want to load a specific file inside the directory:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=classpath:/defaults/base.properties
~~~

**classpath:** does not mean "the directory alongside the JAR." Editing a file in **src/main/resources** after building does not change the resource already packaged inside the JAR earlier.

### 6.2. `file:` is for the current filesystem

Some examples:

~~~text
file:./config/                    relative directory
file:./config/application.yml     relative file
file:/etc/orders/                 absolute directory on Unix
file:/etc/orders/application.yml  absolute file on Unix
file:C:/apps/orders/config/       example URI syntax for a directory on drive C
~~~

A directory outside the JAR can be created by an operator, managed by the deployment system, or mounted into a container. The application must have read permissions for those locations.

For example:

~~~bash
cd /srv/orders
java -jar /opt/apps/orders.jar \
  --spring.config.additional-location=file:./config/
~~~

In this example **./config/** is **/srv/orders/config/**, not **/opt/apps/config/**, because the working directory is **/srv/orders**.

Docker **WORKDIR**, an IDE's working directory, and the **WorkingDirectory** option in a service manager can all determine where relative paths are resolved from.

## 7. How Do `spring.config.location` and `spring.config.additional-location` Differ?

### 7.1. `spring.config.location` replaces the default list

~~~bash
java -jar app.jar \
  --spring.config.location=optional:file:./site-config/
~~~

Spring Boot uses the locations listed in **spring.config.location** to replace the default search locations. If the application relies on an **application.yml** packaged inside the JAR that is not included in the new list, values present only there may no longer be loaded.

Use this mechanism when you intentionally want to control the entire set of locations to search.

### 7.2. `spring.config.additional-location` adds to the list

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./site-config/
~~~

Spring Boot still uses the default locations, then loads the provided additional locations. Values in additional locations can override matching keys in the default configuration.

This is usually the right choice when the JAR holds shared defaults and the deployment environment only adds environment-specific values.

### 7.3. Three properties must be supplied early enough

**spring.config.name**, **spring.config.location**, and **spring.config.additional-location** are used very early to decide which files to load. Supply them from a source available right at startup, such as:

~~~bash
java -jar app.jar --spring.config.name=orders
~~~

Or via an environment variable:

~~~bash
SPRING_CONFIG_ADDITIONAL_LOCATION="optional:file:./site-config/" \
  java -jar app.jar
~~~

Or a Java system property:

~~~bash
java -Dspring.config.additional-location=optional:file:./site-config/ \
  -jar app.jar
~~~

Do not place **spring.config.location** inside a file that needs that very property to be discovered and expect the system to restart discovery from the beginning.

## 8. Where Does a File Live When Using a Relative Path?

Look at two hypothetical layouts:

~~~text
/opt/myapp/app.jar
/srv/run/config/application.properties
~~~

If the operator starts it like this:

~~~bash
cd /srv/run
java -jar /opt/myapp/app.jar \
  --spring.config.additional-location=file:./config/
~~~

the path **file:./config/** points to **/srv/run/config/**. Spring Boot does not automatically switch to a location next to the JAR.

Therefore:

- On a developer machine, **./config/** usually depends on where the IDE or terminal is running from.
- In a container, **./config/** usually depends on **WORKDIR** and runtime configuration.
- For a service, the path can depend on the service manager's working directory setting.
- If the location must be fixed across runs, use an explicit absolute path, such as **file:/etc/myapp/**.

An absolute path must also make sense **inside the runtime environment**. A path on the host machine does not automatically exist inside a container unless it is mounted.

## 9. Multiple Locations: Commas and Semicolons

You can declare multiple locations:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./base/,optional:file:./overrides/
~~~

Both are directories because of the trailing **/**. When locations are processed sequentially, values in a later location can override matching keys from an earlier location.

Spring Boot also allows **location groups**: locations belonging to the same precedence tier are separated by **;**.

~~~text
classpath:/cfg/,classpath:/ext/
classpath:/cfg/;classpath:/ext/
~~~

These two forms can produce different results when using **multiple profiles** such as **prod,live**. Commas represent locations/location groups processed sequentially; semicolons group locations together so profile ordering applies at the same level.

Illustrative example from the Spring Boot documentation:

~~~text
/cfg/
  application-live.properties

/ext/
  application-prod.properties
  application-live.properties
~~~

With **classpath:/cfg/,classpath:/ext/**, files in **cfg/** are processed before files in **ext/**. With **classpath:/cfg/;classpath:/ext/**, profile-specific files in both directories are evaluated at the same level, so the override order can differ.

In shells, **;** can be a special character. When using groups, enclose the entire argument in quotes:

~~~bash
java -jar app.jar \
  "--spring.config.location=classpath:/cfg/;classpath:/ext/"
~~~

For a single location, there is no need to create complex groups.

## 10. Wildcards: When Configuration Sits in Multiple Subdirectories

Spring Boot supports a single **\*** character in wildcard locations. For example:

~~~text
workspace/
└── config/
    ├── mysql/
    │   └── application.properties
    ├── redis/
    │   └── application.properties
    └── queue/
        └── application.properties
~~~

The path:

~~~text
file:./config/*/
~~~

helps search for configuration files in the **direct subdirectories** of **./config/**. This is also one of Spring Boot's default search locations.

Limits to remember:

1. Each wildcard location may contain only **one asterisk**.
2. For a directory wildcard, the path must end with ***/**.
3. For a file wildcard, use ***/<filename>**, such as **file:./config/*/application.properties**.
4. Wildcards apply to **external locations**, not **classpath:**.
5. Expanded wildcard paths are sorted alphabetically by their absolute paths.

Wildcards are **not unlimited recursive searches**. **config/*/** focuses on one level of direct subdirectories, rather than scanning every nested level.

## 11. When a Path Does Not Exist: `optional:`

If a specified location does not exist, Spring Boot can throw **ConfigDataLocationNotFoundException** and refuse to start.

For example:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=file:./must-exist/
~~~

If **must-exist/** does not exist, the application can halt due to a missing required location.

If a missing directory is acceptable in some environments, prepend **optional:**:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./local-overrides/
~~~

**optional:** only says that if this location is missing, it may be skipped. It does not fix syntax errors in files, create directories, or guarantee that a required property has a value.

Valid patterns:

~~~text
optional:file:./config/
optional:file:./config/custom.properties
optional:classpath:/defaults/
~~~

Spring Boot also supports **spring.config.on-not-found=ignore** to ignore missing-location errors more broadly. When a specific location is allowed to be missing, **optional:** expresses the intent more clearly.

## 12. `spring.config.import` and Its Own Path Rules

**spring.config.import** is declared inside an already-loaded configuration document to pull in additional configuration data.

Example **application.properties**:

~~~properties
spring.config.import=optional:file:./config/extra.properties
~~~

Spring Boot will look for **extra.properties** at the specified path. Imported values can override matching keys in the document containing the import statement.

There are two styles of import paths:

- **Fixed location**: begins with **/** or a prefix such as **file:**, **classpath:**. It preserves the explicitly indicated location.
- **Import-relative location**: has none of those prefixes; the path is resolved relative to **the file that declared the import**.

For example:

~~~text
/demo/
├── application.properties
└── core/
    ├── core.properties
    └── extra/
        └── extra.properties
~~~

In **/demo/application.properties**:

~~~properties
spring.config.import=optional:core/core.properties
~~~

In **/demo/core/core.properties**:

~~~properties
spring.config.import=optional:extra/extra.properties
~~~

The second import points to **/demo/core/extra/extra.properties**, because it is resolved from where **core.properties** resides.

Conversely, if written as:

~~~properties
spring.config.import=optional:file:./extra/extra.properties
~~~

then the **file:** prefix makes the path a fixed location: **./extra/** is resolved against the working directory, not relative to **core.properties**'s directory. **optional:** does not alter this fixed/import-relative rule.

### Configuration trees are not like `application.*` directories

Some platforms mount many small files, each containing the value of one property:

~~~text
/etc/config/
└── db/
    ├── username
    └── password
~~~

If you want to turn file names into keys like **db.username** and **db.password**, Spring Boot provides:

~~~properties
spring.config.import=optional:configtree:/etc/config/
~~~

That is **configtree:**, which has its own rules. Simply declaring a directory location **file:/etc/config/** does not mean Spring Boot will read every small file in the tree and turn their names into properties.

## 13. Hands-On Verification with a Minimal Application

Suppose a Spring Boot 3.3 project includes **spring-boot-starter-web**. Create the controller below:

~~~java
package com.example.config;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConfigController {
    private final Environment env;

    public ConfigController(Environment env) {
        this.env = env;
    }

    @GetMapping("/config-banner")
    public String banner() {
        return env.getProperty("app.banner", "missing");
    }
}
~~~

In **src/main/resources/application.properties**:

~~~properties
app.banner=from-jar
server.port=8080
~~~

Build a JAR using the Gradle wrapper:

~~~bash
./gradlew bootJar
~~~

To try the commands below, name the actual JAR **app.jar** or replace **app.jar** in the commands with the real built file name. Prepare the directory:

~~~text
run/
├── app.jar
└── runtime/
    ├── application.properties
    ├── application-prod.properties
    └── custom.properties
~~~

**runtime/application.properties**:

~~~properties
app.banner=from-directory
~~~

**runtime/application-prod.properties**:

~~~properties
app.banner=from-prod
~~~

**runtime/custom.properties**:

~~~properties
app.banner=from-explicit-file
~~~

From inside **run/**, try the following cases in order.

**A. Packaged configuration only:**

~~~bash
java -jar app.jar
curl http://localhost:8080/config-banner
~~~

Illustrative output: **from-jar**.

**B. Specifying a proper directory location:**

~~~bash
java -jar app.jar \
  --spring.config.additional-location=file:./runtime/
~~~

Call the API and receive **from-directory**.

**C. Directory location and `prod` profile:**

~~~bash
java -jar app.jar \
  --spring.config.additional-location=file:./runtime/ \
  --spring.profiles.active=prod
~~~

Call the API and receive **from-prod**.

**D. Specifying an explicit file name:**

~~~bash
java -jar app.jar \
  --spring.config.additional-location=file:./runtime/custom.properties
~~~

Call the API and receive **from-explicit-file**.

**E. Omitting the trailing `/` on the directory path:**

~~~bash
java -jar app.jar \
  --spring.config.additional-location=file:./runtime
~~~

Observe that the path is no longer handled as the intended directory location; then fix it to **file:./runtime/** to load the **application** files.

**F. Testing an optional location:**

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./not-present/
~~~

When **not-present/** does not exist, the optional location is skipped; the application can still use other configuration sources, such as **from-jar**.

Stop the process before starting the next run because the examples all use port **8080**.

## 14. When a File Is Not Loaded, What Should You Check?

If the value differs from what you expect, check these in order:

1. **Did you mean a file or a directory?** A directory must end with **/**.
2. **Did you use the right prefix?** Resources inside the JAR use **classpath:**; external files use **file:**.
3. **What is the current working directory?** **./** is not automatically resolved from where the JAR sits.
4. **Is the file name right?** Directory locations search according to **spring.config.name**, defaulting to **application**.
5. **Is there a matching profile?** **application-prod.yml** is evaluated only when the **prod** profile is active in the loading mechanism.
6. **Did you accidentally replace the default locations?** **spring.config.location** replaces, whereas **spring.config.additional-location** adds.
7. **Does the location exist?** The **optional:** prefix can cause an absent location to be skipped without error.
8. **Is the wildcard valid?** Only one **\***, properly ending in ***/**, and not on the classpath.
9. **Is a file in a higher-precedence location overriding it?** Being loaded does not mean the final value comes from the file you are looking at.
10. **Are permissions and file syntax valid?** A valid path can still point to an unreadable file or malformed configuration data.

To inspect detailed Config Data loading logs in a development environment, you can enable:

~~~bash
java -jar app.jar \
  --logging.level.org.springframework.boot.context.config=TRACE
~~~

Do not print secrets or sensitive information when investigating issues. With Spring Boot Actuator, expose environment/configuration endpoints only to authorized users with appropriate security controls.

## 15. Technical Conclusions

- **file:./config/** is a directory; **file:./config/custom.yml** is a specific file.
- **The trailing /** is a crucial signal for **directory** paths in Config Data.
- **Directory locations** are combined with the configuration base name and profile variants; **file locations** load the named file and can also evaluate profile variants.
- **classpath:** and **file:** refer to two different source types.
- **./** relies on the process's working directory, not by default on the JAR's location.
- **spring.config.location** replaces the default locations, while **spring.config.additional-location** keeps the default locations and adds new ones.
- **optional:** allows a missing location, but does not fix formatting errors or invalid configuration values.
- The **file:./config/*/** wildcard allows scanning direct subdirectories outside the classpath.
- **spring.config.import** has its own fixed and import-relative rules, and **configtree:** is a separate mechanism for reading file-tree configuration.

Expressing paths accurately helps Spring Boot load configuration reliably, predictably, and deploy the same JAR cleanly across environments.

## References

- Spring Boot 3.3 — Externalized Configuration, *Config File Locations*, *Optional Locations*, *Wildcard Locations*, *Profile Specific Files*, and *Importing Additional Data*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html