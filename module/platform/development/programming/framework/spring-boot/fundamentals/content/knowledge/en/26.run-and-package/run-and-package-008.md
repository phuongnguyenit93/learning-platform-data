# Working Directory, Relative Paths, and External Configuration

A Spring Boot application may run fine inside an IDE yet fail when packaged as an executable JAR and launched via systemd, Docker, or Kubernetes. Auxiliary config files go missing, log directories appear elsewhere, upload paths point into non-writable directories, or `application-prod.yml` is not loaded even though it sits right next to the JAR file. Many errors like this stem from confusing three concepts:

- **Working directory (current working directory, CWD):** the directory a Java process uses as the root for relative filesystem paths.
- **JAR location and classpath:** where the program and its bundled resources live; this does not necessarily match the CWD.
- **External configuration locations:** files or directories that Spring Boot is instructed to search when building the Environment, with dedicated rules for search locations, precedence, and profiles.

This lesson distinguishes these concepts, explains relative vs. absolute paths, how to use Spring `Resource`, how Spring Boot locates `application.yml` and `application-prod.yml`, how to load configuration outside the JAR, and how to deploy safely across IDEs, terminals, services, and containers.

## 1. Three Types of Locations Easily Confused

Suppose a server has this layout:

~~~text
/opt/order-service/
├── order-api.jar
└── resources/
    └── seed.csv

/etc/order-service/
└── application-prod.yml

/var/lib/order-service/
└── uploads/

/var/log/order-service/
└── application.log
~~~

You are in the `/tmp` directory and run:

~~~bash
cd /tmp
java -jar /opt/order-service/order-api.jar
~~~

In this example:

| Location | Role | Necessarily the CWD? |
|---|---|---|
| /tmp | Working directory of the process launched from the shell | Yes, in the scenario above |
| /opt/order-service/order-api.jar | Artifact location | No |
| /etc/order-service/application-prod.yml | Deployment configuration | No |
| /var/lib/order-service/uploads | Runtime data to persist | No |
| /var/log/order-service/application.log | Configured log output | No |

If code uses:

~~~java
Path.of("uploads/order.csv");
~~~

that path is interpreted relative to the CWD, which in the case above is:

~~~text
/tmp/uploads/order.csv
~~~

It **does not automatically resolve to**:

~~~text
/opt/order-service/uploads/order.csv
~~~

just because the JAR file resides in `/opt/order-service`.

Here is the foundational rule: **relative filesystem paths do not automatically take the directory containing the executable JAR as their root**.

## 2. How Is a Java Process's Working Directory Determined?

The working directory is typically determined by the launch environment:

- Terminal: the current directory when invoking the command.
- IDE: the working directory field in the run configuration, or the IDE default.
- Gradle `bootRun`: the Java process's working directory as configured by the task.
- systemd: the `WorkingDirectory=` setting in the unit, or the service manager default.
- Docker: the image `WORKDIR` or the `working_dir` setting at runtime.
- Kubernetes: the container `workingDir` or `WORKDIR` inherited from the image.
- CI/CD: the execution directory of the job/runner according to pipeline configuration.

Therefore, the exact same JAR file and the exact same relative path can read from or write to completely different locations.

### 2.1. Reading `user.dir` and Converting a `Path` to Absolute

Java provides the **user.dir** system property, which typically reflects the JVM's working directory.

~~~java
import java.nio.file.Path;

public class WorkingDirectoryDemo {
    public static void main(String[] args) {
        String workingDirectory =
                System.getProperty("user.dir");

        Path relative = Path.of("data/input.csv");

        System.out.println("Working directory: "
                + workingDirectory);
        System.out.println("Relative path: " + relative);
        System.out.println("Absolute path: "
                + relative.toAbsolutePath().normalize());
    }
}
~~~

For example, if the process starts from `/srv/my-app`:

~~~text
Working directory: /srv/my-app
Relative path: data/input.csv
Absolute path: /srv/my-app/data/input.csv
~~~

This is an illustrative example; actual output depends on the operating system and process configuration.

### 2.2. Do Not Treat `user.dir` as Permanent Data Storage

**user.dir** helps diagnose the CWD. It does not by itself guarantee:

- That the directory is writable.
- That data survives when a container is replaced.
- That replicas see the same directory.
- That the disk has sufficient space.
- That the directory is an appropriate place for secrets, uploads, or logs.

If you need to store long-lived data, configure an **explicit data directory** and ensure infrastructure provides appropriate volumes, permissions, and backups.

### 2.3. Changing `user.dir` at Runtime Is Not a Reliable Way to Switch CWD

Example of what not to use as a solution:

~~~java
System.setProperty("user.dir", "/another/path");
~~~

APIs, libraries, and filesystem mechanisms may already have initialized or resolved paths beforehand. Mutating this property is not a contract guaranteed to switch the true working directory of the entire process.

Establish the CWD **at launch time**, or better yet, use an explicit base directory and resolve application paths from it.

## 3. Relative Paths, Absolute Paths, and Normalization with `Path`

Java NIO provides **Path** for working with the filesystem.

~~~java
Path a = Path.of("data/input.csv");
Path b = Path.of("/var/lib/my-app/data/input.csv");
~~~

On Linux, `a` is relative and `b` is absolute. On Windows, absolute path syntax usually includes a drive letter such as **C:\data\input.csv** or a UNC path; let `Path` handle OS-specific syntax rather than concatenating separators manually with `String`.

### 3.1. `isAbsolute`, `resolve`, and `normalize`

~~~java
import java.nio.file.Path;

Path base = Path.of("/var/lib/my-app");
Path child = Path.of("reports/../input/order.csv");

Path resolved = base.resolve(child).normalize();

System.out.println(child.isAbsolute());
System.out.println(resolved);
~~~

Result on a Unix system:

~~~text
false
/var/lib/my-app/input/order.csv
~~~

- **resolve** appends a child path onto a base directory.
- **normalize** removes redundant syntactic elements such as `.` and `dir/..` pairs according to lexical normalization rules.
- **toAbsolutePath** converts a relative path into an absolute path based on the current context.

### 3.2. `normalize` Does Not Verify That a File Exists

~~~java
Path location = Path.of("/missing/folder/../file.txt")
        .normalize();
~~~

The `Path` above can be constructed and normalized even if the file does not actually exist. Existence checks, read permissions, or open operations still need to happen separately.

### 3.3. `toRealPath` Differs from `normalize`

~~~java
Path real = path.toRealPath();
~~~

**toRealPath** interacts with the filesystem and can resolve symbolic links, verify file existence (depending on options), or throw `IOException`.

**normalize** only manipulates path syntax at the character level; it does not inspect symlinks and does not guarantee the path remains inside an allowed directory after symlinks are resolved.

This distinction is critical when handling paths originating from untrusted users.

### 3.4. Avoid Manual Path Concatenation with Slashes

For example:

~~~java
String filename = "orders.csv";
String path = baseDir + "/" + filename;
~~~

can produce malformed paths if `baseDir` already ends with a separator, when running cross-platform, or when `filename` contains unexpected path components.

Prefer:

~~~java
Path file = baseDir.resolve(filename);
~~~

When working with APIs that accept `Path`, prefer `Path` operations over manual `String` concatenation.

## 4. Classpath Resources Are Not Filesystem Paths

When Spring Boot packages an application:

~~~text
src/main/resources/
├── templates/
│   └── invoice.txt
└── data/
    └── countries.csv
~~~

these files are placed onto the runtime classpath.

Reading with Spring:

~~~java
import java.io.IOException;
import java.io.InputStream;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

public class ResourceReader {
    public byte[] readCountries() throws IOException {
        Resource resource =
                new ClassPathResource("data/countries.csv");

        try (InputStream in = resource.getInputStream()) {
            return in.readAllBytes();
        }
    }
}
~~~

**ClassPathResource** searches for data on the classpath, not relative to `user.dir`.

### 4.1. Why Not Use `src/main/resources` at Runtime?

Incorrect for packaged applications:

~~~java
Path path = Path.of(
        "src/main/resources/data/countries.csv");
~~~

In an IDE, this path may exist by coincidence because the CWD matches the source project root.

When running an executable JAR, the file may sit inside:

~~~text
order-api.jar
└── BOOT-INF
    └── classes
        └── data
            └── countries.csv
~~~

There is not necessarily a copy under a **src/main/resources** directory on the server.

### 4.2. `Resource.getFile()` Does Not Always Work

For example:

~~~java
File file = new ClassPathResource(
        "data/countries.csv").getFile();
~~~

may work in the IDE when the resource sits in a classes directory, yet fail if it sits inside a JAR without a standalone filesystem file.

Use:

~~~java
try (InputStream in = new ClassPathResource(
        "data/countries.csv").getInputStream()) {
    // Process bytes from the classpath.
}
~~~

If a library strictly requires a real `Path`/`File`, you must have a policy to extract it to a temporary file or configure the resource outside the JAR, with appropriate cleanup and security controls.

### 4.3. `ResourceLoader` Understands Multiple Location Types

Spring provides:

~~~java
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

Resource resource =
        resourceLoader.getResource(
                "classpath:data/countries.csv");
~~~

Familiar prefixes:

~~~text
classpath:data/countries.csv
file:/var/lib/my-app/data/countries.csv
https://example.invalid/data/countries.csv
~~~

Paths prefixed with **classpath:** reference the classpath; the **file:** prefix indicates a file URL/location; network URLs carry their own latency and security risks.

Do not pass an unchecked location string straight from a user HTTP request into `ResourceLoader`, as doing so can introduce internal file disclosure or SSRF risks.

## 5. Packaged Data vs. External Mutable Data Outside the JAR

These two categories of data should be handled differently:

| Data type | Appropriate location | Rationale |
|---|---|---|
| Fixed templates, small reference data tied to code version | Classpath inside the JAR | Travels with the artifact; builds remain reproducible. |
| User-uploaded files | Data directory/volume/object storage | Must persist and be managed independently of code deploys. |
| Environment-specific configuration | External Config Data, environment, secret manager | Same artifact can serve multiple environments. |
| Runtime secrets | Secret store or secure secret-delivery mechanism | Never bundle credentials in source code or JARs. |
| Log files on a VM | Configured logging directory with rotation | Has clear permissions and retention rules. |
| Logs in containers | Usually stdout/stderr → log collector | Avoids relying on ephemeral container filesystems. |
| Temporary processing files | Temporary directory with quota/cleanup | Short-lived and cleaned up upon completion. |

Do not use classpath locations for content that must be updated at runtime: entries inside a JAR are generally not suitable targets for in-place editing.

### 5.1. An Executable JAR's Directory Is Not a Default Config Folder

Example:

~~~text
/opt/my-app/app.jar
/opt/my-app/application-prod.yml
~~~

If you run from:

~~~bash
cd /tmp
java -jar /opt/my-app/app.jar --spring.profiles.active=prod
~~~

Spring Boot **does not automatically** look for `application-prod.yml` next to the JAR merely because both files sit in the same directory. External config discovery depends on the Config Data search locations and any explicitly configured locations.

You can:

- Run with an appropriate CWD and rely on default external locations.
- Specify **spring.config.additional-location**.
- Specify **spring.config.location** when you want full control over the location list.
- Use **spring.config.import** from a valid configuration document.

These options have distinct semantics; do not swap them interchangeably without checking.

## 6. Spring Boot Config Data: Where Is Configuration Searched?

In modern Spring Boot, the **Config Data** system handles loading `application.properties`, `application.yml`, and related configuration sources during startup.

Under typical default configuration, search locations include:

~~~text
classpath:/
classpath:/config/
file:./
file:./config/
file:./config/*/
~~~

Where:

- **classpath:/** is the classpath root, which can hold `application.yml` packaged inside the JAR.
- **classpath:/config/** is the `config` directory on the classpath.
- **file:./** refers to the process's working directory.
- **file:./config/** is the `config` subdirectory under the working directory.
- **file:./config/*/** covers direct subdirectories under `config` on the filesystem via Boot's supported wildcard location mechanism.

### 6.1. The Dot in `file:./` Is the CWD, Not the JAR Directory

Example:

~~~bash
cd /srv/order-api
java -jar /opt/releases/order-api.jar
~~~

Here the default location **file:./config/** corresponds to:

~~~text
/srv/order-api/config/
~~~

rather than:

~~~text
/opt/releases/config/
~~~

If you run the exact same JAR from a different CWD, the discovered external configuration set can change.

### 6.2. Config Files Are Recognized by Name

By default, Spring Boot looks for base files whose basename is typically **application**, along with profile-specific variants, such as:

~~~text
application.properties
application.yml
application.yaml
application-prod.yml
application-staging.properties
~~~

Giving a file an arbitrary name such as **custom-settings.yml** inside `./config` does not guarantee it will be picked up automatically by default search. In that case, choose an appropriate import/location/name mechanism.

### 6.3. External Configuration Can Override Packaged Configuration

Example:

~~~yaml
# application.yml packaged inside the JAR
app:
  greeting: Hello from packaged config
~~~

And in the CWD you have:

~~~yaml
# ./config/application.yml
app:
  greeting: Hello from external config
~~~

With default Config Data locations and no higher-precedence property source, values in the external config typically win over the corresponding values in the packaged config.

This makes a single artifact reusable across environments. However, **external config does not automatically beat command-line arguments, system properties, or environment variables**. To know the final value, inspect the resolved `Environment`.

### 6.4. Do Not Only Check Whether a File Exists

A file in a valid search location may be loaded yet have its keys overridden by a higher-precedence source. Conversely, the absence of a file does not mean the corresponding profile is inactive.

Distinguish among:

1. Does the file exist?
2. Did the Config Data loader locate and load the file?
3. Do the document/profile conditions in the file match?
4. What is the final property value in `Environment`?
5. Does the `@ConfigurationProperties` or `@Value` bean actually consume that value?

## 7. `spring.config.location`: Redefining Config Search Locations

**spring.config.location** lets you specify the Config Data locations Spring Boot searches at startup. In the typical model, this option **replaces the default search locations** rather than merely adding another directory.

Example:

~~~bash
java -jar app.jar --spring.config.location=optional:file:/etc/order-api/
~~~

The command above specifies `/etc/order-api/` as the place to look for configuration. When instructing Spring Boot to use locations like this, do not assume `application.yml` packaged inside the JAR is still loaded via the replaced default locations.

### 7.1. Specifying a Directory with a Trailing Slash

A directory location requires appropriate trailing syntax:

~~~text
file:/etc/order-api/
~~~

Spring Boot can append config basenames to a directory location, such as `application.yml`, or `application-prod.yml` when the `prod` profile is active.

Compare:

~~~text
file:/etc/order-api/
file:/etc/order-api/custom.yml
~~~

The first is a **directory location**; the second specifies an **explicit file**. How Spring Boot resolves profile-specific variants and handles basenames can differ between the two forms. When profile-based loading is needed, using proper directory location syntax avoids confusion.

### 7.2. Specifying an Explicit Configuration File

~~~bash
java -jar app.jar --spring.config.location=file:/etc/order-api/custom.yml
~~~

An explicit file location does not require the file to be named `application.yml`. In this situation, whether profile-specific variants load depends on Config Data rules for file locations and active profiles.

Inspect the location form in use rather than only checking filenames in the directory.

### 7.3. When Should You Use `spring.config.location`?

Appropriate when:

- You want strict control over the entire set of search locations.
- The artifact must only run with configuration managed outside the JAR.
- Operations require strictly separating packaged defaults from external deployment config.

Be careful: if `application.yml` inside the JAR holds essential defaults and you supply a replacement location, those defaults may no longer load. That can cause startup failures or unexpected default values.

If your intent is to **keep packaged configuration and add external overrides**, the option in the next section is usually closer to what you need.

## 8. `spring.config.additional-location`: Appending External Directories

**spring.config.additional-location** adds locations to the default search set instead of discarding all default locations.

Example:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:/etc/order-api/
~~~

On a single line:

~~~bash
java -jar app.jar --spring.config.additional-location=optional:file:/etc/order-api/
~~~

Spring Boot can load `application.yml` from inside the JAR, followed by matching external config files in `/etc/order-api/` according to Config Data precedence order.

Example:

~~~yaml
# application.yml inside the JAR
app:
  retry:
    max-attempts: 3
  payment:
    endpoint: https://placeholder.example.invalid
~~~

~~~yaml
# /etc/order-api/application-prod.yml
app:
  payment:
    endpoint: https://payments.production.internal
~~~

When `prod` is active and `additional-location` is configured properly, the application can receive:

~~~text
app.retry.max-attempts = 3
app.payment.endpoint = https://payments.production.internal
~~~

That is, the external configuration replaces `payment.endpoint`, while `retry.max-attempts` continues using the default packaged in the JAR.

### 8.1. Comparing `location` and `additional-location`

| Aspect | `spring.config.location` | `spring.config.additional-location` |
|---|---|---|
| Primary meaning | Selects a new set of Config Data locations | Appends locations to the default search |
| Default locations | Normally replaced | Preserved |
| Best suited for | Tightly controlling configuration sources | Overriding selected keys per deployment |
| Risk when misused | Fails to load packaged defaults | Unexpected key overrides when multiple sources define the same key |

### 8.2. Use `optional:` for Locations That May Be Absent

Example:

~~~text
optional:file:/etc/order-api/
~~~

The **optional:** prefix allows skipping a missing location under the Config Data mechanism.

If you omit `optional:` for a required location and it does not exist, Spring Boot may fail startup with a **ConfigDataLocationNotFoundException**-related error.

Do not slap `optional:` onto everything just to suppress startup failures. If production configuration is mandatory to avoid connecting to the wrong system, **fail-fast** is usually safer than booting with unsuitable defaults.

### 8.3. Configuring Multiple Locations

Multiple search locations can be declared:

~~~text
optional:file:/etc/order-api/,optional:file:/etc/shared-config/
~~~

In complex setups, Spring Boot also supports **location groups** and precedence rules across groups. Commas and semicolons can carry different grouping semantics.

Design location ordering deliberately, especially when multiple directories contain `application-prod.yml`. Never rely on incidental filesystem ordering.

## 9. `spring.config.location` Is Evaluated Very Early

Properties that determine **where to search for Config Data** must be available very early during startup.

Unsuitable example:

~~~yaml
# application.yml intended to reside in a yet-unknown location
spring:
  config:
    additional-location: file:/other-location/
~~~

To decide where to read `application.yml`, Spring Boot must know the search locations **before** finishing reading those files. Consequently, keys like **spring.config.name**, **spring.config.location**, and **spring.config.additional-location** are typically supplied via environment variables, system properties, or command-line arguments at launch time.

Example:

~~~bash
java -jar app.jar --spring.config.additional-location=file:/etc/order-api/
~~~

or environment variable:

~~~text
SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/order-api/
~~~

### 9.1. Do Not Expect `@PropertySource` to Be Processed Early Enough

~~~java
@Configuration
@PropertySource("classpath:locations.properties")
class LocationConfiguration {
}
~~~

`@PropertySource` on a `@Configuration` class is processed during context construction, after Spring Boot already needed most Config Data locations. Therefore it is not a reliable mechanism for pointing to initial `application.yml` locations.

### 9.2. Do Not Confuse Configuration Location with Configuration Values

**spring.config.additional-location** answers: "Where should Spring Boot look for configuration files?"

**app.payment.endpoint** answers: "Which endpoint will the application call?"

These two properties serve different roles and often must be supplied at different stages. Do not assume every key can come from any source at any startup phase.

## 10. `spring.config.name`: Changing the Search Filename Basename

By default, Spring Boot looks for files with basename **application**.

If a deployment uses:

~~~text
/etc/order-api/order-config.yml
~~~

you can choose the basename with:

~~~bash
java -jar app.jar --spring.config.name=order-config --spring.config.additional-location=file:/etc/order-api/
~~~

When changing `spring.config.name`, remember that it affects the filenames basename search looks for across locations. Depending on intent, you may stop loading files named `application.yml` via default basename search.

If you only want to load **an extra differently named file** alongside the default configuration, **spring.config.import** may express that more cleanly:

~~~yaml
spring:
  config:
    import: optional:file:/etc/order-api/order-config.yml
~~~

### 10.1. File Extensions and Parsers

Config Data supports common formats such as `.properties`, `.yml`, and `.yaml`. If a file source has no extension yet contains YAML content, an extension hint via the supported Config Data mechanism may be required in some cases.

Do not drop an arbitrary JSON file next to `application.yml` and assume Boot will automatically load it like YAML. The resource must be supported by a Config Data loader, have matching import/format configuration, or use an extended loader.

## 11. `spring.config.import`: Importing a Specific Source

**spring.config.import** is declared inside a Config Data document to pull in additional configuration sources.

Example packaged `application.yml`:

~~~yaml
spring:
  application:
    name: order-api
  config:
    import: optional:file:/etc/order-api/extra.yml

app:
  feature:
    audit-enabled: false
~~~

If `/etc/order-api/extra.yml` exists, Boot can load it during Config Data processing.

Example imported content:

~~~yaml
app:
  feature:
    audit-enabled: true
~~~

Under standard Config Data import rules, values from the imported document can take higher precedence than the document declaring the import for the same key. Still, account for other higher-precedence property sources and overall location groups.

### 11.1. Import Is Not a Simple "YAML Copy/Paste"

Imports follow Config Data's own semantics:

- Can import files or directories/data trees through supported loaders.
- Can use `optional:` for non-mandatory sources.
- Are processed during startup rather than a post-`ApplicationContext`-ready file read.
- Follow rules to avoid needlessly importing the same location repeatedly.
- Can interact with profile-specific variants and `on-profile` documents.

Therefore, the import location, active profiles, and document ordering can all affect final values.

### 11.2. Relative Imports vs. Fixed Imports

Config Data locations support more than one form of relative path:

~~~yaml
spring:
  config:
    import: optional:extras.yml
~~~

An import without a fixed location prefix can be resolved **relative to the location of the document declaring the import**, according to Spring Boot's relative import rules.

Meanwhile:

~~~yaml
spring:
  config:
    import: optional:file:./extras.yml
~~~

the **file:** prefix makes a fixed filesystem location explicit; **./** is interpreted against the working directory for that file location form.

Do not assume every relative import uses the CWD as its base. Distinguish how Boot resolves **relative Config Data locations** versus **filesystem paths** used by Java `Path`.

### 11.3. Importing External Sources Needs an Operational Policy

If `/etc/order-api/extra.yml` is required in production, marking it `optional:` can allow the process to boot even if the file wasn't mounted. That can be hazardous if packaged defaults point toward staging or local targets.

Decide explicitly:

- Should missing the file fail startup?
- Who creates/mounts the file?
- Is a profile-specific variant needed?
- Should mandatory fields be checked with `@ConfigurationProperties` validation?
- Does the file hold secrets requiring restricted permissions?

## 12. Profile-Based Configuration with External Files

Suppose:

~~~text
/etc/order-api/
├── application.yml
├── application-dev.yml
└── application-prod.yml
~~~

`application.yml`:

~~~yaml
app:
  payment:
    timeout: 3s
    endpoint: https://placeholder.example.invalid
~~~

`application-prod.yml`:

~~~yaml
app:
  payment:
    endpoint: https://payments.production.internal
~~~

Run:

~~~bash
java -jar app.jar --spring.profiles.active=prod --spring.config.additional-location=file:/etc/order-api/
~~~

In a typical setup, **application.yml** supplies `timeout`, while the `prod`-specific file supplies the production endpoint.

### 12.1. An Active Profile Does Not Prove the File Was Loaded

When:

~~~text
spring.profiles.active=prod
~~~

Boot can still activate `prod` even if `application-prod.yml` does not exist in the searched locations. The application may then fall back to values from `application.yml`, external imports, environment variables, or code defaults.

To confirm production configuration took effect, verify:

1. Does `Environment.getActiveProfiles()` include `prod`?
2. Is the file location correct?
3. Was the Config Data document loaded?
4. What is the bound value of `app.payment.endpoint`?
5. Are the beans/services actually using that value?

### 12.2. Multiple Active Profiles Can Override One Another

~~~bash
java -jar app.jar --spring.profiles.active=dev,prod
~~~

Both `dev` and `prod` can be activated. If both files declare `app.payment.endpoint`, profile ordering along with Config Data precedence determines the final value.

**Spring profiles do not mutually exclude environments by themselves.** Never leave `dev` and `prod` active simultaneously assuming `prod` automatically wins every setting.

### 12.3. `on-profile` Inside a Single YAML Document

~~~yaml
app:
  payment:
    timeout: 3s

---
spring:
  config:
    activate:
      on-profile: prod
app:
  payment:
    endpoint: https://payments.production.internal
~~~

This is a way to place a profile-specific document inside the same file.

**spring.config.activate.on-profile** is an activation condition for that document, not a command activating `prod`.

Do not place **spring.profiles.active** inside a document gated by `on-profile`; Boot restricts profile activation properties inside profile-specific documents.

## 13. Config Tree for Secrets and File-Mounted Data

In Kubernetes or some secret stores, configuration may be mounted as individual files:

~~~text
/run/secrets/order-api/
├── app.payment.api-key
├── app.payment.merchant-id
└── app.storage.password
~~~

The filename is the property name, and the file content is the value. Spring Boot supports **configtree:** imports to read a directory in this format.

Example:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/order-api/
~~~

When paths and files follow Boot's config tree convention, the application can access the corresponding properties via `Environment` or property binding.

Example:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        String merchantId,
        String apiKey) {
}
~~~

Register `PaymentProperties` using `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

### 13.1. Config Tree Does Not Automatically Protect Secrets

Using `configtree:` does not encrypt secrets on disk or enforce access control by itself.

You still need:

- Filesystem permissions allowing only the intended process to read.
- Never putting secrets into source code or JARs.
- Never logging the entire `Environment` or properties beans.
- Policies for provisioning, rotating, and revoking secrets.
- A clear strategy for restarts/reloads when mounted secrets change.

If a secret is mandatory, `optional:` may be inappropriate. Consider fail-fast validation and verify the deployment's secret provisioning.

### 13.2. Config Tree Does Not Automatically Watch Files

When a secret file updates inside a volume, Spring Boot does not by default re-run all Config Data loading, rebind every bean, and replace existing connections.

Applications typically need a restart/rollout or a dedicated, managed refresh/rotation mechanism. Do not equate "the mount updated" with "clients are now using the new credentials."

## 14. Precedence: There Is No Single "Most Important File" for All Cases

When the same key appears in multiple places, Spring `Environment` picks an effective value according to property source precedence.

Example:

~~~yaml
# application-prod.yml
app:
  payment:
    endpoint: https://payments.production.internal
~~~

Yet the launch command passes:

~~~bash
java -jar app.jar --spring.profiles.active=prod --app.payment.endpoint=http://localhost:8099
~~~

Under default configuration, the command-line property **app.payment.endpoint** has high priority and overrides the value from `application-prod.yml`.

Outcome: **the `prod` profile is active, yet the effective endpoint is still `localhost`**.

### 14.1. Common Configuration Sources

| Source | Example | Notes |
|---|---|---|
| Packaged Config Data | `application.yml` in JAR | Serves defaults bundled with the code version. |
| External Config Data | `./config/application-prod.yml` | Can override packaged config per Boot rules. |
| Imported Config Data | `spring.config.import` | Follows import-specific precedence rules. |
| Environment variable | `APP_PAYMENT_ENDPOINT` | Can override Config Data files. |
| JVM system property | `-Dapp.payment.endpoint=...` | Supplied by the JVM, independent of CWD config files. |
| Command-line argument | `--app.payment.endpoint=...` | Typically very high priority in default Boot apps. |
| `@SpringBootTest`/test property source | test properties | Can override values during test runs. |

Do not use this table as a complete precedence chart for every source, since Boot also supports additional property sources and test/devtools mechanisms.

When you need to know **for sure** which key won, read the final resolved value via `Environment`/`@ConfigurationProperties` and inspect property sources/origin.

### 14.2. A Missing Key Value Differs from an Unfound File

If `app.payment.endpoint` returns `null`, possible causes include:

- The file was not loaded because the location was wrong.
- The file loaded, but the key is absent.
- The profile document condition did not match.
- The prefix/key is misspelled.
- The import/secret was not mounted.

If the value is non-null yet wrong, a higher-precedence source may have overridden it. These two failure modes call for different diagnostic steps.

## 15. Placing Filesystem Paths in `@ConfigurationProperties`

An operationally friendly pattern is extracting runtime data paths into dedicated properties instead of hard-coding the CWD or JAR location.

`application.yml`:

~~~yaml
app:
  storage:
    upload-directory: /var/lib/order-api/uploads
~~~

Properties record:

~~~java
package com.example.orders.config;

import java.nio.file.Path;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        @NotNull Path uploadDirectory) {
}
~~~

Spring Boot's Binder can convert a `String` property into a `Path` via standard conversion support. For validation to run, a Bean Validation provider must be on the classpath, typically via `spring-boot-starter-validation`.

Registering configuration properties:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApiApplication.class, args);
    }
}
~~~

Placing `StorageProperties` under `com.example.orders` lets default `@ConfigurationPropertiesScan` discover and register it.

### 15.1. A `Path` from Configuration Can Still Be Relative

If YAML contains:

~~~yaml
app:
  storage:
    upload-directory: data/uploads
~~~

then `uploadDirectory` can be a relative `Path`. When opening/writing files there, it still depends on the CWD.

Do not assume `@ConfigurationProperties` automatically converts paths to absolute paths or selects a durable data directory.

### 15.2. Normalizing the Base Directory in One Place

~~~java
import java.nio.file.Path;
import org.springframework.stereotype.Component;

@Component
public class StorageLocation {

    private final Path root;

    public StorageLocation(StorageProperties properties) {
        this.root = properties.uploadDirectory()
                .toAbsolutePath()
                .normalize();
    }

    public Path root() {
        return root;
    }
}
~~~

In this example, consumers of `StorageLocation.root()` get a resolved base path. Still, if the original property was relative, `toAbsolutePath` remains anchored to the CWD. A better production policy is **requiring an absolute path** once deployment provides a standard data directory.

### 15.3. Failing Fast When Production Requires an Absolute Path

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StorageInitializationRunner
        implements ApplicationRunner {

    private final StorageProperties properties;

    public StorageInitializationRunner(
            StorageProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args)
            throws Exception {

        Path root = properties.uploadDirectory();

        if (!root.isAbsolute()) {
            throw new IllegalStateException(
                    "app.storage.upload-directory must be absolute");
        }

        Files.createDirectories(root);

        if (!Files.isDirectory(root)
                || !Files.isWritable(root)) {
            throw new IllegalStateException(
                    "Upload directory is not usable");
        }
    }
}
~~~

Runners execute before Spring Boot publishes `ApplicationReadyEvent` during normal startup. If the required directory cannot be created or written to, the exception fails startup instead of reporting ready and failing on the first request.

**`Files.isWritable()` only checks permissions at a single point in time**; it does not guarantee all subsequent write operations will succeed. You still must handle `IOException` when creating, writing, or renaming files.

### 15.4. Never Hard-Code Developer Paths

Do not tie a shared application to a path on a developer's Desktop.

If the application runs inside a Linux container, a Windows path will not mean what was intended. In YAML, quoting and backslash syntax also have rules worth noting.

Supply paths appropriate to each deployment environment. The same codebase can use different values:

~~~text
local: /home/dev/order-api/uploads
staging: /mnt/order-staging/uploads
prod: /var/lib/order-api/uploads
~~~

The paths above merely illustrate naming; real paths are provisioned by infrastructure.

## 16. Creating Files in a Data Directory Without Relying on Client Filenames

If a user uploads a file named **orders.csv**, do not append `originalFilename` directly onto a filesystem path.

A safer pattern is generating server-controlled filenames:

~~~java
package com.example.orders.storage;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class UploadStorageService {

    private final Path uploadRoot;

    public UploadStorageService(StorageLocation location) {
        this.uploadRoot = location.root();
    }

    public Path store(InputStream source)
            throws IOException {

        String storageName = UUID.randomUUID() + ".bin";
        Path destination = uploadRoot.resolve(storageName);

        try (InputStream in = source) {
            Files.copy(in, destination);
        }

        return destination;
    }
}
~~~

The method above **takes ownership** of the `InputStream` because it closes the passed-in stream. If a caller API only lends the stream, do not close it on the caller's behalf; adjust the method contract or let the caller manage closing.

The example assumes `uploadRoot` was validated and exists. In a real system, also add:

- Maximum file size and file type policies.
- Tightly scoped directory/file permissions.
- Protections against overwriting existing files; use `OpenOption` such as `CREATE_NEW` when appropriate.
- Cleanup if copying fails midway.
- Metadata or database records linking storage IDs to user files.
- Path traversal defenses if an API accepts client-supplied path names.

In particular, checking with `normalize()` and `startsWith()` is only a lexical safeguard; if symlinks or race conditions are possible, use filesystem verification and secure directory operations suited to your threat model.

### 16.1. `InputStream` Ownership Conventions

APIs accepting `InputStream` should state clearly who is responsible for closing it. If code calls `MultipartFile.getInputStream()` during a request, the controller normally opens the stream and should close it once the service finishes reading. If the service is designed to take ownership, the method can use `try-with-resources` as shown.

Never return a closed `InputStream` from a method, and never hand a request-scoped `MultipartFile` to background work if its backing temporary storage may be cleaned up after the request ends.

## 17. `@Value Resource`: Configuring Sources with Explicit Prefixes

Beyond `Path` configuration, Spring can inject a `Resource` from a location property.

Example `application.yml`:

~~~yaml
app:
  template:
    location: classpath:templates/invoice.txt
~~~

Service:

~~~java
package com.example.orders.template;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;

@Service
public class InvoiceTemplateService {

    private final Resource template;

    public InvoiceTemplateService(
            @Value("${app.template.location}")
            Resource template) {
        this.template = template;
    }

    public String load() throws IOException {
        try (InputStream in = template.getInputStream()) {
            return new String(
                    in.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
~~~

Using **classpath:** or **file:** prefixes in the property lets the service maintain the exact same contract across environments.

External configuration example:

~~~yaml
app:
  template:
    location: file:/etc/order-api/templates/invoice.txt
~~~

Here the template source sits outside the JAR; operators must mount the file properly and grant read permissions.

### 17.1. `Resource` vs. `Path`

**Resource** represents an asset that may reside on the classpath, filesystem, or another source type. It fits well when you only need to open a stream for reading.

**Path** represents a filesystem path under a provider's semantics. It fits well when you need to create directories, move, delete, inspect permissions, or manage application-written files.

If you only read a packaged template, `Resource.getInputStream()` is usually a cleaner choice than requiring `File`/`Path`. If you manage uploaded files on a volume, `Path`/`Files` are usually easier to work with.

## 18. Log Files and Temp Directories Also Depend on the Working Directory

Business data files are not the only ones affected by the CWD.

Example:

~~~yaml
logging:
  file:
    name: logs/order-api.log
~~~

When file logging is enabled this way, **logs/order-api.log** is a relative path and may resolve against the process's working directory.

The same executable JAR:

~~~bash
cd /srv/order-api
java -jar /opt/releases/order-api.jar
~~~

may write logs under `/srv/order-api/logs`, whereas if a service manager uses a different CWD, the file can end up elsewhere.

### 18.1. Logging in Containers

In container environments, `stdout`/`stderr` are usually the right destination because the platform already collects logs per process/pod.

If you do need to write log files:

- Specify a dedicated directory.
- Grant write permissions.
- Ensure a volume exists with retention/rotation configured.
- Avoid writing heavily into the container's writable layer.

Never treat a relative `logging.file.name` as durable default log storage.

### 18.2. Temporary Files and `java.io.tmpdir`

Some libraries use **java.io.tmpdir** for temporary files or intermediate upload operations. That directory is distinct from the working directory and distinct from long-term data storage.

Example:

~~~java
String tempDirectory =
        System.getProperty("java.io.tmpdir");
~~~

Many `File.createTempFile` or `Files.createTempFile` calls default to an appropriate temporary directory, yet you should never assume temporary files sit next to the JAR.

If large uploads or temporary file processing happen frequently, ensure adequate capacity, permissions, and cleanup in the temp directory.

### 18.3. Multipart Temp Location vs. Final Data Location

Spring Boot provides properties for multipart uploads, such as **spring.servlet.multipart.location**, which configures where intermediate data is buffered by the supported stack.

This is **not automatically the final storage directory** of your application. Once the request finishes, temporary resources may be deleted.

If files must outlive the request, the application must actively copy/persist them to a storage location whose lifecycle it manages.

## 19. Running from the Terminal: Same JAR, Different CWD

Suppose the artifact resides at:

~~~text
/opt/releases/order-api.jar
~~~

and configuration sits at:

~~~text
/srv/order-api/config/application-prod.yml
~~~

Run:

~~~bash
cd /srv/order-api
java -jar /opt/releases/order-api.jar --spring.profiles.active=prod
~~~

Under default external config search, Boot can find the file under **./config/**, i.e., `/srv/order-api/config`.

If you change the CWD:

~~~bash
cd /tmp
java -jar /opt/releases/order-api.jar --spring.profiles.active=prod
~~~

then **./config/** becomes `/tmp/config`, not `/srv/order-api/config`.

### 19.1. Running Without Depending on CWD

If configuration must always come from `/srv/order-api/config`, specify the location explicitly:

~~~bash
java -jar /opt/releases/order-api.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/srv/order-api/config/
~~~

Now Config Data lookup at that additional location no longer relies on CWD. However, **other property values may still hold relative paths**, such as `app.storage.upload-directory=data/uploads`, and those paths still depend on CWD.

Therefore, manage **two groups of paths**:

1. Paths pointing to where configuration files live.
2. Paths declared **inside** configuration files where the application reads/writes runtime data.

Making group 1 absolute does not automatically make group 2 absolute.

### 19.2. Running on Windows PowerShell

Example:

~~~powershell
Set-Location 'C:\deploy\order-api'
Get-Location
java -jar 'C:\releases\order-api.jar' --spring.profiles.active=prod
~~~

With that working directory, a relative path **data\input.csv** resolves from `C:\deploy\order-api` following Windows path handling.

When you need an absolute Config Data location on Windows, use file location syntax compatible with Spring Boot/Java URLs and check shell escaping/quoting. A simple way to avoid mistakes is placing config inside a `config` directory under an intentionally chosen CWD.

### 19.3. Shell Scripts and Symlinks

A launch script can be invoked from any directory. If the script uses relative paths without setting the CWD, behavior depends on where the caller ran it from.

If you want to execute from a fixed base directory:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

cd /srv/order-api
exec java -jar /opt/releases/order-api.jar \
  --spring.profiles.active=prod
~~~

This is a Linux example. The script needs proper permissions, and the paths must match the deployment environment.

**Note:** the script's own directory, any symlink to the JAR, the caller's shell CWD, and paths passed to the JVM are independent concepts. Do not assume that placing a script next to a JAR makes relative paths automatically resolve from the script's folder.

## 20. Running via systemd: What Role Does `WorkingDirectory` Play?

Linux systemd lets a service declare `WorkingDirectory` explicitly.

Illustrative unit file:

~~~ini
[Unit]
Description=Order API
After=network.target

[Service]
Type=simple
User=order-api
WorkingDirectory=/srv/order-api
Environment=SPRING_PROFILES_ACTIVE=prod
Environment=SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/order-api/
ExecStart=/usr/bin/java -jar /opt/order-api/order-api.jar
Restart=on-failure

[Install]
WantedBy=multi-user.target
~~~

In this example:

- **WorkingDirectory=/srv/order-api** sets the CWD of the Java process when the service runs.
- **ExecStart** selects the executable and JAR.
- **SPRING_PROFILES_ACTIVE** sets the profile.
- **SPRING_CONFIG_ADDITIONAL_LOCATION** adds an external config directory.
- **User** controls the OS account used by the process.

These settings are independent. Changing `ExecStart` to point to a different JAR **does not automatically change the CWD** while `WorkingDirectory` remains the same.

### 20.1. Service Account Permissions

If the service runs under user `order-api`, it needs:

- Read permission for the JAR and configuration under `/etc/order-api`.
- Write permission if the app uses `/var/lib/order-api` or a custom log directory.
- Network permissions per security policy.

A process launched from an administrator's terminal may read a file cleanly yet fail with **AccessDeniedException** under a service account. Do not work around this by running the whole service as `root` when you can grant exact permissions on the required resources.

### 20.2. `EnvironmentFile` Is Not a Java Properties File

systemd offers **EnvironmentFile=** to load environment variables for a service. That is systemd syntax—it does not mean Spring Boot treats an arbitrary file placed beside the JAR as `application.properties`.

If an `EnvironmentFile` declares `SPRING_PROFILES_ACTIVE` or `SPRING_CONFIG_ADDITIONAL_LOCATION`, systemd passes them into the process, and Spring Boot receives them as environment variables.

For sensitive secrets, evaluate your infrastructure's secret-provisioning mechanisms rather than placing unprotected credentials in unit files or world-readable files.

### 20.3. Hardening Directives Can Block File Writes

Even when `Files.isWritable` on a path looks promising, the service manager may enforce sandboxing or read-only filesystem restrictions.

If hardening options such as `ProtectSystem` are enabled, writable directories may need to be declared using administrator-approved systemd directives. Verify effective permissions from **the running process**, not only via `chmod`.

## 21. Docker: `WORKDIR` Is Not the Artifact Location

Illustrative Dockerfile:

~~~dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app

COPY order-api.jar /app/order-api.jar

USER 10001

ENTRYPOINT ["java", "-jar", "/app/order-api.jar"]
~~~

In this example:

- The JAR is placed at `/app/order-api.jar`.
- Docker's **WORKDIR /app** sets the default working directory.
- A relative filesystem property like `data/input.csv` typically resolves under `/app/data/input.csv`.

If the container is replaced, data written to the writable layer may not survive. Hence **/app should not by default serve as durable upload storage**.

### 21.1. Mounting External Config via Volumes

Example container run:

~~~bash
docker run --rm \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/order-api/ \
  -v /host/order-config:/etc/order-api:ro \
  -v /host/order-data:/var/lib/order-api \
  order-api:latest
~~~

Assumptions:

- `/host/order-config` contains `application-prod.yml` or matching Config Data files.
- The container has permission to read `/etc/order-api`.
- `/host/order-data` has ownership/permissions for the application's UID.
- `app.storage.upload-directory` is configured to `/var/lib/order-api/uploads` or another provisioned location.

Docker bind-mount syntax depends on the host and Docker runtime; the command above illustrates a Linux host.

### 21.2. Running a Container with a Different Working Directory

Docker allows overriding the CWD via the appropriate option:

~~~bash
docker run --rm -w /work order-api:latest
~~~

The JAR is still launched by absolute path `/app/order-api.jar` in `ENTRYPOINT`, while relative filesystem paths inside the Java process move to `/work`.

This shows that **executable path and working directory remain two independent settings**.

### 21.3. Read-Only Root Filesystem

In hardened containers, the root filesystem may be read-only. If code tries to write:

~~~text
./logs/application.log
./uploads/order.csv
~~~

without those paths mounted writable, write operations will fail. Instead of disabling protections across the entire container when avoidable:

- Write logs to `stdout`/`stderr`.
- Mount a data volume at an explicit path.
- Configure absolute data paths.
- Grant minimal write permissions to the running user.

## 22. Kubernetes: `workingDir`, ConfigMap, Secret, and Volumes

In Kubernetes, the JAR is usually already packaged inside the image. The runtime environment can provide:

- Container **workingDir**.
- Environment variables.
- ConfigMaps mounted as files.
- Secrets mounted as files or delivered through deployment mechanisms.
- `PersistentVolumeClaim` for persistent data.
- `emptyDir` for scratch data tied to the Pod lifecycle.

Illustrative Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      containers:
        - name: order-api
          image: registry.example.invalid/order-api:1.0.0
          workingDir: /work
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
            - name: SPRING_CONFIG_ADDITIONAL_LOCATION
              value: file:/etc/order-api/
          volumeMounts:
            - name: configuration
              mountPath: /etc/order-api
              readOnly: true
            - name: data
              mountPath: /var/lib/order-api
      volumes:
        - name: configuration
          configMap:
            name: order-api-config
        - name: data
          persistentVolumeClaim:
            claimName: order-api-data
~~~

Assume ConfigMap **order-api-config** contains `application-prod.yml` and the data volume has appropriate read/write permissions.

When the container runs:

- **workingDir=/work** anchors relative filesystem paths.
- **/etc/order-api/** is the external location added by Spring Boot to Config Data search.
- **/var/lib/order-api/** is the data area backed by a dedicated volume.
- The image may store the JAR at another path; it does not have to match `/work`.

### 22.1. Caution When Scaling Multiple Replicas

The example declares one replica and one PVC for illustration. If multiple pods scale out and write to the same volume simultaneously, concurrent mounting and consistency depend on access modes and the storage backend.

In many systems, user uploads belong in object storage or a shared storage service built for multi-replica access, rather than assuming all pods write to a local directory.

### 22.2. Do ConfigMap or Secret Updates Auto-Reload Spring?

Do not assume so. Kubernetes can update mounted volume contents on its own schedule, yet Spring Boot does not by default recreate `Environment`, rebind all beans, or replace already-initialized clients just because a file changed on disk.

You need a restart/rollout policy or a dedicated dynamic configuration/secret-rotation mechanism.

### 22.3. Kubernetes `workingDir` Must Exist and Be Accessible

If `workingDir` points to a non-existent directory or one the container lacks access to, the process may fail to start.

When deploying, verify `workingDir`, the image filesystem, `volumeMounts`, and `securityContext`/UID on an **actual running pod**. An un-applied YAML manifest proves nothing about what the live runtime uses.

## 23. Inspecting Working Directory and Effective Config at Startup

When the application cannot find a file or calls the wrong endpoint, do not only inspect config files in the repository. Read data reported by the **running process**.

An `ApplicationRunner` can log:

~~~java
package com.example.orders.diagnostics;

import java.nio.file.Path;
import java.util.Arrays;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class StartupEnvironmentInspector
        implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(
                    StartupEnvironmentInspector.class);

    private final Environment environment;

    public StartupEnvironmentInspector(
            Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        Path cwd = Path.of("").toAbsolutePath().normalize();

        log.info("Working directory: {}", cwd);
        log.info("Active profiles: {}",
                Arrays.toString(
                        environment.getActiveProfiles()));

        log.info("Data directory: {}",
                environment.getProperty(
                        "app.storage.upload-directory"));
    }
}
~~~

In this example, only selected non-secret values are logged.

### 23.1. Never Log the Entire `Environment`

`Environment` can contain:

- Database passwords and credentials.
- External API tokens.
- Values mounted from Secrets.
- Sensitive system metadata.

A statement dumping all property sources can leak confidential data. For sensitive keys, verify only presence or validity via approved mechanisms.

### 23.2. Why Might Logs Inside `ApplicationRunner` Not Appear?

`ApplicationRunner` executes after the context refreshes. If the process fails earlier due to:

- `ConfigDataLocationNotFoundException`.
- Invalid YAML syntax.
- Profile-specific configuration not found as expected.
- Property binding/validation errors.
- Required bean creation failures.

the runner may never be invoked.

In that situation, read **Spring Boot startup logs**, the launch command, environment variables, and config locations passed prior to context initialization. Do not treat missing runner logs as evidence of a specific CWD.

### 23.3. Logging Relative vs. Resolved Paths for Comparison

If `app.storage.upload-directory` is configured relatively, a useful diagnostic is:

~~~java
String value = environment.getProperty(
        "app.storage.upload-directory");

if (value != null) {
    Path configured = Path.of(value);
    Path effective = configured.toAbsolutePath().normalize();

    log.info("Storage path is absolute: {}",
            configured.isAbsolute());
    log.info("Effective storage path: {}", effective);
}
~~~

This clearly reveals why a property configured as **uploads** ended up looking under `/tmp/uploads`.

## 24. Finding Which Source Provides a Property in `Environment`

Knowing the right CWD is not enough. If two config files exist or a command-line override is active, you need to know **which property source supplied the final value**.

Spring provides `ConfigurableEnvironment`:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public class ConfigOriginInspector {

    public static void showCandidates(
            ConfigurableEnvironment environment,
            String key) {

        System.out.println("Effective: "
                + environment.getProperty(key));

        for (PropertySource<?> source
                : environment.getPropertySources()) {

            if (source.containsProperty(key)) {
                System.out.println("Candidate source: "
                        + source.getName());
            }
        }
    }
}
~~~

Use this helper only with non-sensitive keys such as:

~~~text
app.storage.upload-directory
app.payment.endpoint
spring.application.name
~~~

In a standard `Environment`, property sources follow an order of precedence. Iterating `containsProperty` over each source only shows **candidate sources**; it does not by itself capture every case of relaxed binding, placeholder resolution, and config origin metadata.

### 24.1. Actuator Helps Inspect Configuration

Spring Boot Actuator exposes helpful endpoints:

| Endpoint | Purpose |
|---|---|
| **/actuator/env** | Inspect `Environment`, active profiles, and property source/origin details when supported. |
| **/actuator/configprops** | Inspect bound `@ConfigurationProperties` beans. |
| **/actuator/beans** | Verify actually registered beans. |
| **/actuator/conditions** | View Boot's auto-configuration conditions report. |

Not all endpoints are exposed by default. If exposing `env` or `configprops` over HTTP, enforce proper **authentication, authorization, and redaction**; never expose internal configuration publicly.

### 24.2. Tracing Config Data Loading with Logs

When unsure which files were searched or loaded, you can raise Config Data logging for a diagnostic startup run:

~~~bash
java -jar app.jar --logging.level.org.springframework.boot.context.config=TRACE
~~~

Detailed logs reveal processed locations, skipped files, and configuration milestones. Use `TRACE` selectively because it produces heavy output.

### 24.3. A Spring Profile Cannot Replace Configuration Verification

A log line like:

~~~text
The following 1 profile is active: "prod"
~~~

only indicates the active profile in startup flow. It **does not prove**:

- `/etc/order-api/application-prod.yml` was mounted.
- `app.payment.endpoint` received its production value.
- The target database is actually production.
- Beans are using the intended configuration or external resources are readable.

To verify an environment, confirm active profiles, effective properties, and the actual beans/resources in use.

## 25. Testing Path Logic with `@TempDir`

A way to test without relying on paths from a developer's machine is **JUnit 5 `@TempDir`**.

Suppose a `Path`-handling class:

~~~java
package com.example.orders.storage;

import java.nio.file.Path;

public class RelativePathResolver {

    private final Path baseDirectory;

    public RelativePathResolver(Path baseDirectory) {
        this.baseDirectory =
                baseDirectory.toAbsolutePath().normalize();
    }

    public Path resolve(String relativeName) {
        Path result = baseDirectory
                .resolve(relativeName)
                .normalize();

        if (!result.startsWith(baseDirectory)) {
            throw new IllegalArgumentException(
                    "Path escapes storage directory");
        }

        return result;
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class RelativePathResolverTests {

    @TempDir
    Path tempDir;

    @Test
    void resolvesChildInsideBaseDirectory() {
        RelativePathResolver resolver =
                new RelativePathResolver(tempDir);

        Path resolved = resolver.resolve("reports/orders.csv");

        assertThat(resolved)
                .isEqualTo(tempDir
                        .resolve("reports/orders.csv")
                        .toAbsolutePath()
                        .normalize());
    }

    @Test
    void rejectsEscapingRelativePath() {
        RelativePathResolver resolver =
                new RelativePathResolver(tempDir);

        assertThatThrownBy(
                () -> resolver.resolve("../outside.txt"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

This test verifies **lexical path resolution**. It does not fully protect against symlinks, race conditions, or permissions on a real filesystem. When paths come from untrusted user input, add filename restrictions, symlink policies, and secure file operations matched to your threat model.

### 25.1. Why Avoid Testing with a Hard-Coded Path?

For example:

~~~java
Path.of("/home/developer/project/data/input.csv");
~~~

may not exist on CI agents or Windows. `@TempDir` creates a runtime sandbox directory so `Path` logic can be verified independently of a developer machine's layout.

### 25.2. Testing Real File Operations

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

@Test
void readsUtf8FileFromTempDirectory(
        @TempDir Path tempDir) throws Exception {

    Path file = tempDir.resolve("note.txt");
    Files.writeString(
            file, "Run from any directory",
            StandardCharsets.UTF_8);

    String text = Files.readString(
            file, StandardCharsets.UTF_8);

    assertThat(text)
            .isEqualTo("Run from any directory");
}
~~~

This tests filesystem paths and charset handling, not Spring Boot Config Data precedence. Each concern should be tested in its appropriate scope.

### 25.3. Never Mutate JVM-Wide `user.dir` Just for Tests

For example:

~~~java
System.setProperty("user.dir", "/temporary/place");
~~~

is not a reliable way to isolate CWD in a multithreaded test suite and can corrupt other tests.

Pass a base `Path` into the component under test, or spawn a child process with an explicit working directory when you truly need to verify CWD behavior.

## 26. Testing External Configuration at the Integration Level

For Config Data, testing a `@ConfigurationProperties` bean is important yet insufficient to verify that an external file is loaded from the right location.

There are two directions:

### 26.1. Testing Binding When Property Values Are Known

With:

~~~java
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(Path uploadDirectory) {
}
~~~

you can use `ApplicationContextRunner` to stand up a focused context:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class StoragePropertiesBindingTests {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(StorageProperties.class)
    static class TestConfiguration {
    }

    @Test
    void bindsAbsoluteStoragePath() {
        new ApplicationContextRunner()
                .withUserConfiguration(TestConfiguration.class)
                .withPropertyValues(
                        "app.storage.upload-directory=/var/lib/order-api")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    StorageProperties props =
                            context.getBean(StorageProperties.class);

                    assertThat(props.uploadDirectory())
                            .isEqualTo(Path.of("/var/lib/order-api"));
                });
    }
}
~~~

This example uses a Unix-style `Path` to illustrate a config value. On Windows, use an absolute `Path` valid for the test's OS.

This test checks **binding**, though it does not by itself prove that an external `application-prod.yml` directory is loaded by the Config Data loader.

### 26.2. Startup Testing with Actual External Configuration

If the goal is to verify external file discovery itself, an integration test can:

1. Create a temporary directory.
2. Write `application.yml` or `application-test.yml` into that directory.
3. Launch a **separate `SpringApplication` process** with `spring.config.additional-location` pointing to the temporary directory.
4. Read `Environment` or check a `@ConfigurationProperties` bean.
5. Verify the value loaded from the external file.
6. Terminate the process and clean up temporary data.

Isolating the process or using a controlled startup harness helps because several Config Data options are evaluated **very early** and can be affected by JVM-wide system properties/global state.

### 26.3. `@SpringBootTest(properties=...)` Does Not Test File Location Resolution

Example:

~~~java
@SpringBootTest(properties = {
        "app.payment.endpoint=https://test.example.invalid"
})
~~~

proves the code receives the effective property inside the test context. Yet the value is injected directly via test properties, not as proof that Config Data found the real environment's external file.

To avoid confusion, name tests after what they actually verify: **binding test**, **Config Data loading test**, or **runtime deployment smoke test**.

## 27. Packaging a JAR Does Not Automatically Bundle External Files

When building a Spring Boot executable JAR via Gradle or Maven, files inside **src/main/resources** are normally packaged as classpath resources.

Example project:

~~~text
order-api/
├── src/
│   └── main/
│       └── resources/
│           ├── application.yml
│           └── data/
│               └── countries.csv
├── runtime/
│   └── application-prod.yml
└── build/
    └── libs/
        └── order-api.jar
~~~

The file `runtime/application-prod.yml` in the example sits **outside `src/main/resources`**. Do not assume it gets packaged into the JAR merely because it sits in the same repository.

After building:

- `application.yml` can be found on the classpath.
- `data/countries.csv` can be read with `ClassPathResource`.
- `runtime/application-prod.yml` must be deployed/mounted separately or explicitly included in the artifact via build configuration.

This is not necessarily a drawback. For a single JAR promoted across dev/staging/prod, **separating external configuration from the artifact** is usually the intended design.

### 27.1. Build Artifacts and Deployment Packages Are Two Different Concepts

A release might contain:

~~~text
release/
├── order-api.jar
├── config/
│   └── application-prod.yml
└── start.sh
~~~

This is a **deployment bundle**; it does not mean the config file lives inside the executable JAR. If `start.sh` runs under a different CWD, the `config` folder in the bundle is not automatically discovered by relative path.

Therefore, deployment documentation should explicitly state:

- Working directory at launch.
- Artifact path.
- External Config Data location.
- Active profiles.
- Data/log/temp directories.
- Filesystem permissions for the service account.

### 27.2. Never Inspect Resources via Source Project Paths

Incorrect example:

~~~java
Path path = Path.of(
        "src/main/resources/application.yml");
~~~

This path only makes sense in limited dev/build scenarios whose CWD happens to match the source tree root. When running the executable JAR on a server, the application should query **Spring `Environment`** for resolved configuration rather than probing source-tree paths.

If you only need to read a non-configuration classpath resource, use `ClassPathResource`.

### 27.3. `application.yml` Inside a JAR Cannot Be Updated by Editing Source Files

Once a file is packaged inside a JAR, modifying the source file on a developer machine does not change values inside a process already running on a server.

You must rebuild/deploy a new artifact or supply an external configuration with higher precedence, combined with an appropriate restart/refresh mechanism.

Never attempt to open a packaged classpath resource inside a JAR for direct writing from business code.

## 28. Common Errors When Running and Packaging

### 28.1. Runs in the IDE, but the JAR Cannot Find the File

**Symptom:** `NoSuchFileException` referencing `src/main/resources/...` or `data/...`.

**Cause:** the IDE runs with the repository as its working directory; the JAR runs elsewhere and the resource may reside inside the artifact.

**Fix:** for bundled data, use classpath `Resource.getInputStream()`; for runtime files, configure explicit external paths.

### 28.2. Placed `application-prod.yml` Next to the JAR, Yet It Is Ignored

**Symptom:** `prod` is active, yet endpoints/configs still fall back to defaults.

**Cause:** Boot looks for external Config Data using the CWD and search locations, not automatically anchored to the JAR's folder.

**Fix:** set the CWD appropriately or use an absolute `spring.config.additional-location`/`file:` location, then check effective values.

### 28.3. Used `spring.config.location` When You Only Wanted an Override

**Symptom:** the application loses packaged defaults or many properties become unset.

**Cause:** `spring.config.location` normally replaces default search locations.

**Fix:** if you still want configuration inside the JAR, use `spring.config.additional-location` or explicitly include matching location groups.

### 28.4. Missing Trailing Slash on a Directory Location

**Symptom:** Boot fails to find files as expected or interprets the location differently than intended.

**Cause:** a directory location and an explicit file location have distinct syntax and semantics.

**Fix:** use directory form such as `file:/etc/order-api/` when searching a folder for `application.yml` and profile-specific files.

### 28.5. Missing `optional:` Causes Startup Failure

**Symptom:** `ConfigDataLocationNotFoundException` or a missing-configuration error at startup.

**Cause:** Spring Boot was asked to load a required location that does not exist.

**Fix:** verify paths and mounts; only add `optional:` if missing the location is acceptable. For mandatory production config, failing fast may be the right behavior.

### 28.6. Adding `optional:` Lets the System Boot with the Wrong Config

**Symptom:** the app starts even though `/etc/order-api/application-prod.yml` is missing, then calls an unintended endpoint.

**Cause:** the missing external location is silently skipped and packaged/default values take over.

**Fix:** classify mandatory settings, remove `optional:` where needed, add `@ConfigurationProperties` validation, and enforce target-environment sanity guards.

### 28.7. Configuring Windows Absolute Paths on Linux

**Symptom:** data gets written to strange locations or raises `InvalidPathException`.

**Cause:** the path uses OS-specific syntax while the artifact executes on another OS.

**Fix:** let deployment supply platform-appropriate paths; use the `Path` API instead of string concatenation; avoid hard-coding developer paths.

### 28.8. Calling `normalize()` and Assuming Complete Path Traversal Protection

**Symptom:** files can still be read/written outside the intended directory via symlinks or races.

**Cause:** `normalize()` only cleans path characters; it does not check actual filesystem state or symlinks.

**Fix:** restrict filenames, anchor to a trusted base directory, inspect canonical/real paths, and apply secure file operations suited to your threat model; never let raw user-controlled locations be opened freely.

### 28.9. Log Files Appear in an Unexpected Directory

**Symptom:** `logs/application.log` appears in `/tmp` or `/` instead of `/opt/app`.

**Cause:** the relative logging path resolved against the service/container CWD.

**Fix:** log to `stdout` in containers; if writing files, configure absolute paths and write permissions.

### 28.10. Service Runs Under a Different User and Cannot Read Config

**Symptom:** `AccessDeniedException` even though developers can open the file manually.

**Cause:** the systemd/container service account differs from a developer's terminal user.

**Fix:** check the effective UID/GID and mount permissions; grant minimal required permissions rather than defaulting to `root`.

### 28.11. Kubernetes ConfigMap Edited, Yet App Still Uses Old Values

**Symptom:** the updated mount shows new values, yet beans or HTTP clients still use previous ones.

**Cause:** Config Data bound at context startup; updating a mount does not automatically re-instantiate beans.

**Fix:** perform a rollout/restart or adopt a managed dynamic configuration mechanism.

### 28.12. Different Pods Use Different Values

**Symptom:** within the same deployment, some requests hit staging while others hit production.

**Cause:** inconsistent rollout, differing images/config mounts, or un-restarted older pods.

**Fix:** inspect image digests, active profiles, `Environment`, and property origins on each serving instance.

### 28.13. `application-dev.yml` Ignored Due to Profile Name Mismatch

**Symptom:** the file exists in the Config Data location, yet base config values remain active.

**Cause:** active profile name mismatch (e.g., `production` instead of `prod`), or an `on-profile` condition mismatch.

**Fix:** inspect `Environment.getActiveProfiles()` and compare against filenames/conditions rather than checking `spring.profiles.active` in a single file.

### 28.14. Config File Has Values, Yet `@ConfigurationProperties` Still Holds Defaults

**Symptom:** `Environment` or Config Data logs show the file loaded, yet the bean has `null`/default values.

**Cause:** mismatched prefix or property name, type conversion failure, unregistered bean, or an overriding source.

**Fix:** compare effective `Environment` against the bound object, verify `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties`, validation, and source precedence.

### 28.15. Files Written to the Container Layer Disappear After Deploy

**Symptom:** uploads exist before restart yet vanish when a pod/container is replaced.

**Cause:** data was written to an ephemeral writable container layer instead of durable storage.

**Fix:** use appropriate volumes or object storage; never treat the JAR directory/`WORKDIR` as durable storage.

### 28.16. Wrong Filename or Wrong Basename

**Symptom:** `application.yml` loads, yet `custom-settings.yml` in the same folder is ignored.

**Cause:** default Config Data search looks for basename `application`, not arbitrary YAML files.

**Fix:** configure `spring.config.name`, Config Data `import`, or an explicit file location matching your goal.

### 28.17. Confusing an External File with a Classpath Resource

**Symptom:** `ClassPathResource("config/application.yml")` fails to read a file located in `/etc/order-api/`.

**Cause:** `ClassPathResource` searches the runtime classpath, not arbitrary filesystem directories.

**Fix:** use `FileSystemResource`/`Path` for external files; for application configuration, let Spring Boot's Config Data loader handle configured locations.

### 28.18. CWD-Dependent Job Accidentally Runs from Another Directory

**Symptom:** cron, systemd, or batch jobs write to the wrong folder while manual terminal runs behave fine.

**Cause:** the launcher changed the current directory or omitted an explicit `WorkingDirectory`.

**Fix:** set the CWD explicitly in the service/job or resolve every business data path from a configured base directory.

## 29. Two Illustrative Scenarios to Separate Root Causes

### 29.1. Case A: CSV File Is Inside the JAR Yet Cannot Be Read

Source:

~~~text
src/main/resources/data/tax-codes.csv
~~~

Code:

~~~java
Files.readString(
        Path.of("src/main/resources/data/tax-codes.csv"));
~~~

In the IDE the code may run because the project root is the CWD. On a server, the source tree does not exist.

**Cause:** the code used a source filesystem path to read a classpath resource.

**Proper fix:**

~~~java
Resource resource =
        new ClassPathResource("data/tax-codes.csv");

try (InputStream in = resource.getInputStream()) {
    String csv = new String(
            in.readAllBytes(),
            StandardCharsets.UTF_8);
}
~~~

This properly reads the packaged resource; there is no need to alter the CWD merely to prop up source-tree path assumptions.

### 29.2. Case B: External `application-prod.yml` Is Not Applied

Deployment:

~~~text
/opt/order-api/app.jar
/opt/order-api/config/application-prod.yml
~~~

Command:

~~~bash
cd /tmp
java -jar /opt/order-api/app.jar \
  --spring.profiles.active=prod
~~~

The app reports `prod` active, yet the endpoint is wrong.

**Likely cause:** default `./config/` points to `/tmp/config` rather than `/opt/order-api/config`.

**Fix:**

~~~bash
java -jar /opt/order-api/app.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=file:/opt/order-api/config/
~~~

Then inspect the effective `app.payment.endpoint` from `Environment` and confirm the file loaded. If it is still wrong, check environment variables and command-line property overrides.

Both cases look superficially like "cannot read file", yet their root causes differ:

- Case A: **confusing a classpath resource with a source filesystem path**.
- Case B: **confusing the CWD/default external Config Data location with the JAR directory**.

Consequently, never try to patch every file error by adding `../` segments to paths.

## 30. Common Misconceptions

**"Running `java -jar /opt/app/app.jar` makes `/opt/app` the working directory."**  
No. The CWD is normally inherited from the launcher or configured by the service/container. Passing an absolute path to the JAR does not change the CWD.

**"`Path.of('data/input.csv')` looks for the file next to the JAR."**  
No. That is a relative filesystem path, normally resolved from the working directory.

**"Files under `src/main/resources` always exist as ordinary files on the server."**  
No. When packaged as an executable JAR, resources normally reside on the classpath inside the JAR without necessarily having copies on disk.

**"`ClassPathResource.getFile()` always works."**  
No. A resource may reside inside a JAR and lack a standalone filesystem `File`.

**"The JAR directory and the CWD must always match."**  
No. They can differ; what matters is configuring and resolving paths intentionally.

**"Spring Boot automatically reads every YAML file next to the executable JAR."**  
No. It searches default Config Data locations plus configured locations/imports, applying basename and profile rules.

**"`./config/` always means a `config` folder right beside the JAR."**  
No. The dot in `file:./config/` refers to the process's CWD.

**"`spring.config.location` and `spring.config.additional-location` do the same thing."**  
No. One primarily replaces the search locations; the other appends locations to the default list.

**"Having `application-prod.yml` means the `prod` profile is active."**  
No. Profiles must be activated via `Environment`/startup through a valid mechanism.

**"`prod` active means all values come from `application-prod.yml`."**  
No. External imports, environment variables, JVM properties, and command-line arguments can override the final value.

**"`optional:` is just a nicer syntax for every config location."**  
No. It changes how missing locations are handled. Skipping mandatory configuration can be dangerous.

**"A relative import file is always resolved from the CWD."**  
Not necessarily. Relative Config Data imports follow resolution rules relative to the declaring document/location; distinguish them from fixed file locations.

**"Using `@PropertySource` completely replaces `spring.config.additional-location`."**  
No. `@PropertySource` runs later in the lifecycle and does not replace startup Config Data discovery.

**"Binding a `Path` with `@ConfigurationProperties` makes it an absolute path."**  
No. The Binder performs type conversion, yet a relative value stays relative until resolved.

**"`normalize()` makes user-supplied paths completely safe."**  
No. Symlinks, race conditions, and filesystem permissions must be addressed separately.

**"The upload directory and multipart temp directory are the same."**  
No. Multipart temp data may be purged by the framework after the request; data meant to survive needs its own lifecycle-managed storage.

**"A relative log file path is always durable log storage."**  
No. CWD and volume/container policies govern where logs land and whether they persist.

**"Docker `WORKDIR` must match where the JAR is stored."**  
No. `ENTRYPOINT` can invoke the JAR using an absolute path while `WORKDIR` is chosen independently.

**"Editing a ConfigMap/Secret makes Spring Boot update every bean immediately."**  
No. Config Data is normally evaluated at startup; dynamic refresh/secret rotation requires dedicated mechanisms.

**"A unit test with `@SpringBootTest(properties=...)` proves external `application.yml` discovery works."**  
No. Test property overrides verify binding/behavior inside the test context, not deployment location resolution.

**"As long as files exist, the app will read the right values."**  
No. Path, permissions, format, profile, precedence, and evaluation timing must all align.

**"Logging `prod` active is enough to prove we aren't touching the staging database."**  
No. Verify the effective datasource URL, target system identity, and actual configured beans/values.

## 31. Pre-Deployment Verification Checklist

To minimize mismatches between the IDE and JAR execution, check in order:

### Step 1 — Classify the Resource

Is the resource **packaged with the code** or must it **exist independently outside the artifact**?

- Travels with code version and read-only → classpath `Resource`.
- Adjusted per environment → external Config Data or environment/secret source.
- Application-written data → data directory or object storage with its own lifecycle.

### Step 2 — Identify the CWD per Launcher

Record explicitly:

~~~text
IDE working directory:
Terminal working directory:
systemd WorkingDirectory:
Docker WORKDIR:
Kubernetes workingDir:
~~~

If any of these relies on vague defaults, declare it explicitly or switch business data paths to absolute locations.

### Step 3 — Separate the Three Path Roles

~~~text
JAR path:             /opt/order-api/app.jar
Config Data path:     /etc/order-api/
Application data:     /var/lib/order-api/
~~~

Do not collapse all three into a single folder out of convenience; they have distinct permissions, lifecycles, and backup policies.

### Step 4 — Pick the External Config Loading Mechanism

- Want to retain packaged defaults and add per-deploy overrides → `additional-location`.
- Want full control over all search locations → `location`.
- Want to import a specific file or config tree from Config Data → `import`.
- Want to change the `application` basename → config name.

Verify whether `optional:` matches whether the file is mandatory.

### Step 5 — Verify Active Profiles

Do not merely check filenames. Verify:

~~~java
environment.getActiveProfiles();
~~~

If no active profiles are set, remember that default profiles may still apply.

### Step 6 — Verify Effective Properties and Beans

For keys governing critical behavior:

- Data directory.
- Database URL/identity.
- External service endpoints.
- Sandbox/live mode.
- Feature flags.
- Mandatory credentials (without logging secret values).

Confirm the resolved value and source, then confirm beans/services use that exact configuration.

### Step 7 — Verify Filesystem and Storage

Does the process have read permission for configs and write permission for data? Is the volume properly provisioned with sufficient space? Does persisted data survive restarts/redeploys?

### Step 8 — Fail Fast on Missing Critical Conditions

If a mandatory config file or data directory is absent, the app should fail explicitly rather than silently proceeding with risky defaults.

`ApplicationRunner`, `@ConfigurationProperties` validation, and startup checks help here. Never downgrade fatal misconfigurations to warnings if the app cannot serve safely.

### Step 9 — Test in Realistic Conditions

Running the JAR from outside the project root, testing in a container with a read-only root filesystem, and running an external-config startup test in a temp directory expose bad assumptions early.

Do not rely exclusively on IDE runs with default working directories.

## 32. Self-Study Exercises

### Exercise 1: Predict the Resolved Path

Suppose:

~~~bash
cd /tmp/run-321
java -jar /opt/demo/demo.jar
~~~

In code:

~~~java
Path path = Path.of("reports/output.txt");
~~~

Question: where is the output file expected to resolve?

**Hint:** apply `Path.toAbsolutePath().normalize()` against the corresponding CWD.

**Conceptual answer:** `/tmp/run-321/reports/output.txt` on Unix, not automatically `/opt/demo/reports/output.txt`.

### Exercise 2: Distinguish Classpath and External Files

An application has:

~~~text
src/main/resources/templates/report.txt
~~~

Question: after building an executable JAR, which reading approach depends least on the working directory?

**Answer:** `ClassPathResource("templates/report.txt").getInputStream()` or `ResourceLoader` with the `classpath:` prefix.

### Exercise 3: Loading an Additional Production File

You have a packaged `application.yml` and want to add:

~~~text
/etc/demo/application-prod.yml
~~~

without dropping packaged defaults.

**Guided answer:** activate the `prod` profile and set `spring.config.additional-location=file:/etc/demo/`, then inspect effective properties in the running process.

### Exercise 4: Investigating an Unexpected Override

`application-prod.yml` contains:

~~~yaml
app:
  endpoint: https://prod.example.invalid
~~~

Yet the process runs with:

~~~bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --app.endpoint=http://localhost:9000
~~~

Question: can you deduce which endpoint the app uses solely from seeing profile `prod` active?

**Answer:** no. Command-line properties can override Config Data. Under default configuration, the effective `app.endpoint` will be `http://localhost:9000`.

### Exercise 5: Choosing Upload Storage

An application runs 3 Kubernetes replicas and must retain uploaded files across rollouts.

Question: should files be written to `./uploads` inside the container or to storage with an independent lifecycle?

**Guided answer:** you need durable storage supporting multiple replicas, typically object storage or properly designed shared storage. Never treat the CWD or container writable layer as durable data storage.

## Key Takeaways

**The working directory is the root for relative filesystem paths**, not the directory holding the JAR. Even a command using an absolute JAR path can still resolve `./data` and `./config` relative to the directory from which the process was launched. IDEs, terminals, systemd, Docker, and Kubernetes can supply different CWDs, causing the same artifact to behave differently.

**Classpath resources and external files are two distinct source types.** Files under `src/main/resources` are normally packaged inside the JAR; read them via `ClassPathResource` or `Resource.getInputStream()`, without relying on the source tree or assuming `Resource.getFile()` always succeeds. For files that must be written or updated across deploys, use an external `Path`/`Resource`, proper filesystem permissions, and suitable storage.

**Spring Boot Config Data has its own search locations and precedence.** Default external locations such as **file:./config/** are anchored to the CWD. **spring.config.location** replaces locations; **spring.config.additional-location** appends locations; **spring.config.import** loads declared sources; **spring.profiles.active** selects profiles without guaranteeing every property comes from profile-specific files. Before concluding configuration is right, verify the CWD, active profiles, Config Data locations, effective property values, and the beans consuming them.

The most resilient design **cleanly separates the artifact, deployment configuration, and runtime data**, chooses paths deliberately, avoids implicit reliance on the working directory, protects secrets, and fails fast when critical configuration is missing. When you do this, the exact same Spring Boot JAR runs and packages consistently from developer machines to real production deployments.
