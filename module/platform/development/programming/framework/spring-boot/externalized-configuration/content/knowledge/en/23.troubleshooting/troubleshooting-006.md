# Troubleshooting Config Data Location and Resource Not Found Errors in Spring Boot

When starting a Spring Boot application, you sometimes encounter **Config Data** errors such as:

~~~text
ConfigDataLocationNotFoundException
ConfigDataResourceNotFoundException
ConfigDataNotFoundException
~~~

The message is usually accompanied by a location like `file:./config/custom.yml`, `classpath:/settings.yml`, `configtree:/etc/secrets/`, or an import address supported by a third-party library. These errors occur **very early in startup**, while Spring Boot is reading configuration to build `Environment`, before most `@ConfigurationProperties` and application beans are created.

This is not the same category of error as a property that was loaded yet has the wrong data type (such as binding `"abc"` to `int`), or a `@Value` bean missing a property. This lesson aims to accurately distinguish **location not found**, **resolved resource not found**, **resource readable yet malformed content**, and **resource exists yet effective property differs from expectations**.

This lesson uses **Spring Boot 3.3.x and Java 21**. The error messages below are illustrative examples: exception wording, failure analysis, and stack traces can vary by version, resolver, and operating system.

## 1. Config Data Loading Flow and Where Errors Occur

In Spring Boot, configuration can come from:

- `application.properties`, `application.yml`, or `application.yaml` on the classpath.
- Files outside the JAR, such as `./config/application.yml`.
- Locations specified by `spring.config.location` or `spring.config.additional-location`.
- Resources imported via `spring.config.import`.
- `configtree:` configuration directories, often used with Kubernetes ConfigMap/Secret volumes.
- Sources implemented by custom libraries through `ConfigDataLocationResolver` and `ConfigDataLoader`.

Conceptual flow:

~~~text
SpringApplication.run(...)
           |
           v
Prepare Environment
           |
           v
ConfigDataEnvironmentPostProcessor
           |
           v
Determine Config Data locations
           |
           v
ConfigDataLocationResolver
           |
           +-- Location does not exist?
           |      -> ConfigDataLocationNotFoundException
           |
           v
ConfigDataResource
           |
           v
ConfigDataLoader
           |
           +-- Resource does not exist?
           |      -> ConfigDataResourceNotFoundException
           |
           +-- File exists yet parse fails?
           |      -> Other format/read error
           |
           v
ConfigData containing PropertySource
           |
           v
Environment / Binding / Validation
           |
           v
ApplicationContext
~~~

**Key takeaway:** if the system fails during the Config Data phase, adding a `@Bean` or `@PostConstruct` to "create the config file at startup" will be **too late**. Config Data loading typically happens before Spring instantiates those beans.

## 2. How Do the Two Main Exceptions Differ?

### 2.1. ConfigDataLocationNotFoundException

Full name:

~~~java
org.springframework.boot.context.config.ConfigDataLocationNotFoundException
~~~

This is a subclass of `ConfigDataNotFoundException`. It indicates a **`ConfigDataLocation` could not be found**. For example, a configuration requested loading a file at a non-existent location.

Reproducible scenario:

~~~properties
spring.config.import=file:./config/missing.yml
~~~

If the requested file is absent, Config Data loading can fail with a not-found family exception, including `ConfigDataLocationNotFoundException` depending on which stage the resolver detects it.

### 2.2. ConfigDataResourceNotFoundException

Full name:

~~~java
org.springframework.boot.context.config.ConfigDataResourceNotFoundException
~~~

This exception also extends `ConfigDataNotFoundException`, yet applies when **a resolved `ConfigDataResource` is not found when needed**.

For example, a custom resolver turns `team-config:orders` into a resource representing the `orders` document. When the loader checks the backend and that document does not exist, it can throw `ConfigDataResourceNotFoundException`.

For standard file sources, the exact final exception depends on how the resolver/loader detects the missing resource. **Do not make absolute assumptions** that "missing file is always LocationNotFound" or "missing remote is always ResourceNotFound": read the actual exception, location, and resource reported.

### 2.3. ConfigDataNotFoundException

This is the common superclass of the two cases above. It provides APIs describing the referenced item that could not be found. When seeing a wrapper exception, look for the **root cause** or specific subclass.

| Error | Missing target | First investigation step |
| --- | --- | --- |
| `ConfigDataLocationNotFoundException` | A `ConfigDataLocation` | Address, scheme, path, import declaration site |
| `ConfigDataResourceNotFoundException` | A `ConfigDataResource` | Resolved resource, actual file/backend/document |
| `UnsupportedConfigDataLocationException` | No resolver matches the location | Scheme, dependencies, `spring.factories` |
| YAML/Properties parser error | Resource may exist yet content is invalid | Syntax, encoding, format |
| `BindException` / conversion error | Property was found yet cannot bind | Key name, Java type, value |
| `BindValidationException` / validation | Value has valid type yet violates constraint | `@Validated`, Bean Validation |

Exact class names in stack traces can vary across versions. This table categorizes **failure phases** rather than asserting a single exception for every case.

## 3. How Can a Missing Error Appear?

Example:

~~~yaml
spring:
  config:
    import: "file:./config/private.yml"
~~~

When launched without the file existing, Spring Boot usually halts startup. Failure analysis may state:

~~~text
Description:

Config data location 'file:./config/private.yml' does not exist

Action:

Check that the value 'file:./config/private.yml' is correct,
or prefix it with 'optional:'
~~~

This is **illustrative content** close to how Spring Boot explains the error, not guaranteed word-for-word identical across every version.

How to read it:

1. **Location in the message**: what exact address is Spring Boot trying to read?
2. **Source specifying the location**: `spring.config.import`, `spring.config.location`, `spring.config.additional-location`, or custom resolver?
3. **Required or optional**: does the location have the `optional:` prefix?
4. **In the running environment**, does the resource exist at that exact path?
5. **Resource kind**: file, directory, classpath, config tree, or remote?
6. **Is it genuinely missing or a different error**: if connection was refused or YAML syntax is broken, do not treat it as missing merely because startup failed.

Do not randomly edit `@ConfigurationProperties` beans when logs indicate failure occurred right inside the Config Data loader.

## 4. When Does a Missing File Not Cause an Error?

Spring Boot has **default search locations** for application config. An application is not required to have every file in every default directory; the absence of `application.yml` in one default search directory does not mean startup must fail.

Conversely, when **an explicit required location is specified**, for example:

~~~bash
java -jar app.jar --spring.config.location=file:./missing/
~~~

Spring Boot may report an error unable to find that location.

Distinction to remember:

~~~text
No application.yml in a default search location
    -> Can be completely valid.

Declared spring.config.import=file:./must-exist.yml
yet file does not exist
    -> Can halt startup.

Declared spring.config.import=optional:file:./maybe.yml
yet file does not exist
    -> Spring Boot can skip it.
~~~

Do not use `optional:` as an automatic cure for every file. First ask: **is this file mandatory for the application to work correctly and safely?**

## 5. Short 8-Step Diagnostic Workflow

When hitting a not-found error, proceed in this order:

1. **Capture the original exception and failure analysis**; record the exact location/resource. If messages contain credentials, mask them before sharing.
2. **Find the property declaring the source**: `spring.config.import`, `spring.config.location`, `spring.config.additional-location`, or custom scheme.
3. **Classify the scheme**: `classpath:`, `file:`, `configtree:`, or plugin scheme.
4. **Identify the real runtime**: running via Maven, Gradle, JAR, Docker, Kubernetes, or CI? What are the working directory and classpath?
5. **Check exact path and kind**: file vs. directory, trailing slash, extension, filename, letter casing.
6. **Check active profiles**: is there an `application-prod.yml` variant or an import declared in a document active only for a certain profile?
7. **Pick the policy**: fix the location if required; use `optional:` if genuinely allowed to be absent; avoid global ignore settings.
8. **Re-run in the same environment** and verify critical properties actually hold expected values.

When someone says "the file exists on the machine," ask **which machine, which directory, and inside which process/container**. A file on a developer's laptop does not mean it exists inside a Docker image or Kubernetes Pod.

## 6. Distinguish classpath: and file:

Two prefixes most easily confused:

~~~text
classpath:/config/extra.yml
file:./config/extra.yml
~~~

### classpath:

`classpath:` searches for resources on the application's **classpath**.

For example:

~~~text
src/main/resources/config/extra.yml
~~~

after building is usually copied into:

~~~text
target/classes/config/extra.yml
~~~

or with Gradle:

~~~text
build/resources/main/config/extra.yml
~~~

When packaged as a Spring Boot executable JAR, application resources typically live under:

~~~text
BOOT-INF/classes/config/extra.yml
~~~

To import:

~~~yaml
spring:
  config:
    import: "classpath:/config/extra.yml"
~~~

If you only place the file at `./config/extra.yml` outside the JAR without adding it to the classpath, `classpath:` will not find it automatically.

### file:

`file:` targets a path on the filesystem of the environment running the process.

~~~yaml
spring:
  config:
    import: "file:./config/extra.yml"
~~~

`./config/extra.yml` is a relative path. It resolves against **the process's working directory**, not automatically against the directory holding the JAR.

For example:

~~~bash
cd /opt/myapp
java -jar app.jar
~~~

the relative path usually resolves to:

~~~text
/opt/myapp/config/extra.yml
~~~

If launched via:

~~~bash
cd /tmp
java -jar /opt/myapp/app.jar
~~~

then `file:./config/extra.yml` resolves to:

~~~text
/tmp/config/extra.yml
~~~

This is a frequent root cause of "works from the IDE, fails when run as a service/cron/container."

### Selection Table

| Situation | Appropriate prefix |
| --- | --- |
| Resource packaged in `src/main/resources` | `classpath:` |
| File mounted at deployment | `file:` |
| File supplied from launch working directory | `file:./...` |
| Kubernetes Secret/ConfigMap with one file per key | `configtree:` |
| Custom cloud/config store source | Scheme supported by extension |

Do not "fix" by switching `file:` to `classpath:` if the file is not actually packaged inside the artifact.

## 7. Inspecting Resources Inside the JAR

If configured:

~~~properties
spring.config.import=classpath:/config/payment.yml
~~~

yet hitting not-found, inspect the **running artifact**.

With Maven:

~~~bash
./mvnw clean package
~~~

With Gradle:

~~~bash
./gradlew clean bootJar
~~~

List resources in the actual JAR:

~~~bash
jar tf target/myapp.jar
~~~

Or Gradle:

~~~bash
jar tf build/libs/myapp.jar
~~~

Look for entry:

~~~text
BOOT-INF/classes/config/payment.yml
~~~

The JAR name `myapp.jar` is just an example. Substitute the actual artifact name.

If the file is missing from the JAR:

- Check whether the file is placed in `src/main/resources/config/payment.yml`.
- Check whether the build tool excludes resources.
- Check whether the module containing the resource is actually an application dependency.
- Check that you are running the newly built JAR, not an older cached one.
- If located in `src/test/resources`, do not expect it in the production JAR.

If the resource exists in the JAR yet is not found, check the declared classpath path, letter casing, and slashes. Do not fix by assuming every JAR has the same layout.

## 8. Checking Working Directory and Files on the Filesystem

### Linux/macOS

~~~bash
pwd
ls -l ./config/
ls -l ./config/extra.yml
~~~

Check the actual directory at launch:

~~~bash
cd /opt/myapp
java -jar app.jar --spring.config.import=file:./config/extra.yml
~~~

### Windows PowerShell

~~~powershell
Get-Location
Test-Path -LiteralPath .\config\extra.yml
Resolve-Path -LiteralPath .\config\extra.yml
~~~

For Java `-jar` running as a Windows service, the working directory may differ from the project folder. Do not rely solely on seeing the file in Explorer.

### Docker

Suppose the Dockerfile sets:

~~~dockerfile
WORKDIR /app
COPY target/app.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
~~~

And the app imports `file:./config/extra.yml`. That file must appear inside the container at `/app/config/extra.yml`, such as via COPY or a volume:

~~~bash
docker run --rm   --mount type=bind,src=/host/config,dst=/app/config,readonly   myapp:latest
~~~

`/host/config` is an illustrative host path, not a default path existing on every machine.

Verify inside the container:

~~~bash
docker exec <container-id> sh -c 'pwd; ls -la /app/config'
~~~

If the image/container lacks `/app/config`, Spring Boot cannot read a resource existing only outside the container even if the host has the file.

### Kubernetes

With ConfigMap/Secret volumes, verify:

- Does the Pod declare the volume and volumeMount correctly?
- Does the mount path inside the container match `file:` or `configtree:`?
- Are the namespace and ConfigMap/Secret names right?
- Does the container have read permissions on the directory?
- Did the app start before the resource was properly provisioned?

Use `kubectl describe pod`/`kubectl exec` when authorized and in the right namespace. Never print secret contents into logs just to verify paths.

## 9. Files and Directories Are Handled Differently

`spring.config.location` accepts **specific files** or **directories containing application config**.

File example:

~~~bash
java -jar app.jar --spring.config.location=file:./config/custom.yml
~~~

The `custom.yml` file is referenced directly, and Spring Boot can consider matching profile variants.

Directory example:

~~~bash
java -jar app.jar --spring.config.location=file:./config/
~~~

For a **directory location**, Spring Boot appends the name derived from `spring.config.name`, defaulting to `application`, and looks for files with supported extensions.

A trailing slash is needed:

~~~text
file:./config/        correct for directory
file:./config         should not be used to represent a directory
~~~

If the file is `./config/custom.yml` while the location points to **directory** `./config/` with default basename `application`, do not expect Boot to load every YAML file with arbitrary names. You can:

- Rename it to `application.yml`.
- Set `spring.config.name=custom` from an early bootstrap source.
- Or reference the specific file via `file:./config/custom.yml`.

### spring.config.name

~~~bash
java -jar app.jar --spring.config.name=custom
~~~

Then the application looks for file variants with basename `custom` in the relevant locations. This property is used **very early**, so supply it via environment, system property, or CLI—not inside a file that Boot cannot find yet because of its own filename.

## 10. spring.config.location and spring.config.additional-location

The two properties have different effects:

### spring.config.location

~~~bash
java -jar app.jar   --spring.config.location=optional:file:./config/
~~~

**Replaces the default configuration search locations** with the list you provide. If `application.yml` was previously loaded from the classpath yet you replace the list without including classpath, that config may no longer be loaded.

This is a frequent mistake: a developer wants to "read one extra file" yet uses `spring.config.location`, unintentionally dropping default locations.

### spring.config.additional-location

~~~bash
java -jar app.jar   --spring.config.additional-location=optional:file:./config/
~~~

**Appends** locations while keeping the default search locations. Additional sources can take higher precedence than default sources.

### Shell and Escaping Notes

In Bash, the semicolon `;` separates commands; when using location group separators, wrap the value in appropriate quotes. In PowerShell, quotes preserve special characters in arguments.

Do not copy a multi-line command into a shell that uses a different line-continuation syntax. The commands above illustrate Bash; Windows PowerShell has its own line-continuation syntax.

## 11. spring.config.import: Locations Declared Inside a Document

`spring.config.import` imports additional configuration, for example:

~~~yaml
spring:
  config:
    import: "file:./config/orders.yml"
~~~

If `orders.yml` is missing and the import is mandatory, Spring Boot can halt before the context initializes.

Replace with:

~~~yaml
spring:
  config:
    import: "optional:file:./config/orders.yml"
~~~

only when that file is **genuinely allowed to be absent**.

### Relative vs. Fixed Imports

Spring Boot distinguishes:

- **Fixed location:** has a URL-like prefix such as `file:`, `classpath:`, or starts with `/`. Independent of where the import document was declared.
- **Import-relative location:** has no fixed prefix; resolved relative to the file that declared the import.

Example:

~~~text
/demo/application.properties
/demo/core/core.properties
/demo/core/extra/extra.properties
~~~

In `/demo/application.properties`:

~~~properties
spring.config.import=optional:core/core.properties
~~~

When `core.properties` has:

~~~properties
spring.config.import=optional:extra/extra.properties
~~~

the second address resolves relative to the directory containing `core.properties`, not automatically relative to the JAR directory or project root.

The `optional:` prefix **does not decide** whether an import is fixed or relative.

### Common Mistake

If you write:

~~~properties
spring.config.import=optional:extra/extra.properties
~~~

in a different document than you assumed, the import can point to a different directory. Identify **the parent resource declaring the import**, especially with nested import chains.

## 12. Extensionless Files and Extension Hints

Spring Boot normally detects format from extensions like `.properties`, `.yml`, or `.yaml`. Some container volume mounts have extensionless files, such as:

~~~text
/etc/config/mysettings
~~~

If the file contains YAML without an extension, import:

~~~yaml
spring:
  config:
    import: "file:/etc/config/mysettings[.yaml]"
~~~

The `[.yaml]` part is an **extension hint** telling Spring Boot how to parse the content.

Do not rename files on a volume if the platform enforces extensionless names. Use the hint syntax supported by Spring Boot.

If an extension is missing and no hint is provided, the error may fall into **unsupported resource/format**, not necessarily missing file. Check the actual exception instead of adding `optional:` to hide the error.

### File Has an Extension Yet Invalid Content

An existing `config.yml` containing broken YAML syntax causes a parser error, not a not-found error. Likewise, a `config.properties` with invalid formatting must have its contents fixed.

## 13. configtree: and Secret Directories

Spring Boot supports importing a directory of files where **filename becomes key** and file content becomes value.

Kubernetes mount example:

~~~text
/etc/config/
└── myapp/
    ├── username
    └── password
~~~

Import:

~~~yaml
spring:
  config:
    import: "configtree:/etc/config/"
~~~

Can produce properties `myapp.username` and `myapp.password`.

If you want key names to be just `username` and `password`, use:

~~~yaml
spring:
  config:
    import: "configtree:/etc/config/myapp/"
~~~

### Errors to Investigate

- Mount directory does not exist inside the container.
- Using `file:/etc/config/` expecting it to auto-convert filenames into keys.
- Importing `configtree:/etc/config/myapp` when the actual path/mount differs from assumptions.
- Volume not attached to the Pod/container in the right namespace.
- Expecting `myapp.username` while importing the subdirectory produces a different key name.
- Secret lacks a required key even though the config tree directory exists.

**Distinction:** if the config tree directory exists while a specific key file is missing, importing the directory can still succeed. The failure may surface **later** as a missing property or validation failure. That is not necessarily a Config Data location not-found error.

### Optional Config Tree

~~~yaml
spring:
  config:
    import: "optional:configtree:/etc/config/"
~~~

Use when the directory is allowed not to exist, such as in local development. Never accidentally mark mandatory production secret directories as optional.

### Wildcard Config Tree

~~~yaml
spring:
  config:
    import: "configtree:/etc/config/*/"
~~~

Spring Boot can load immediate subdirectories of the parent folder. If specific precedence order is required, declare locations individually rather than relying solely on wildcards.

## 14. Wildcard Locations: Syntax and Limitations

Spring Boot supports wildcards for certain **external filesystem locations**.

Example:

~~~text
file:./config/*/
file:/etc/myapp/*/application.yml
~~~

Important rules:

- A wildcard contains **a single `*`** in a path.
- For directory search, the pattern must end with `*/`.
- For file search, it can take the form `*/filename`.
- Wildcard locations work only with **external directories**.
- Never use wildcards in `classpath:` locations.
- Wildcard locations are expanded and ordered alphabetically by absolute path.

Invalid or unsupported syntax can cause location resolution errors, **not proof the resource does not exist**.

If a file sits at `/etc/myapp/redis/application.yml`, a `file:/etc/myapp/*/` wildcard scans immediate subdirectories. If nested deeper than one directory level, that pattern will not recursively scan every nested folder.

## 15. Profile-Specific Config Data and the "Missing File" Misconception

When active profile is `prod`, Spring Boot can consider:

~~~text
application.yml
application-prod.yml
~~~

Depending on location and precedence, the profile file overrides the common file for shared keys.

Example:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

If `application-prod.yml` does not exist in a default search location, **that is not automatically an error**. An application can have only `application.yml` and still run with the `prod` profile if the needed config is already present.

### When a Profile Triggers a Mandatory Import

~~~yaml
# application-prod.yml
spring:
  config:
    import: "file:/etc/myapp/production-secrets.yml"
~~~

When the `prod` profile is enabled, the import becomes active. An unmounted secret file can trigger Config Data not-found.

With the `dev` profile, the prod document is not loaded, so that import does not trigger in the same way.

Investigate in order:

1. Which profile is actually active?
2. Which file/document declares `spring.config.import`?
3. Is that document profile-specific or activated via `spring.config.activate.on-profile`?
4. Is the import fixed, relative, or optional?
5. Does the resource exist in that profile's runtime environment?

### Multi-Document YAML

~~~yaml
app:
  mode: normal

---
spring:
  config:
    activate:
      on-profile: prod
    import: "file:/etc/myapp/prod-extra.yml"
~~~

The second document participates only when `prod` matches. If a missing imported file fails only when prod is enabled, that is the expected outcome of conditional configuration.

### Active and Default Profiles

When no active profiles are set, Spring uses default profiles (defaulting to `default`). That can affect `application-default.yml`. Do not infer solely from an environment string `SPRING_PROFILES_ACTIVE`; profiles can also come from CLI, groups, and configuration.

## 16. Location Groups and Precedence Order

When using multiple locations:

~~~bash
java -jar app.jar   --spring.config.location=classpath:/cfg/,classpath:/ext/
~~~

locations are processed in order, with later locations able to override values from earlier ones.

Spring Boot also has **location groups**, separated by semicolons `;`:

~~~bash
java -jar app.jar   '--spring.config.location=classpath:/cfg/;classpath:/ext/'
~~~

Groups alter how precedence and profile-specific files are processed. An unexpected final value can be caused by order/groups rather than a missing file.

**Not-found errors and precedence errors are two separate issues:**

- If Spring Boot reports a file cannot be found, verify the address exists.
- If there is no error yet the key gets a value from another source, inspect property source order, profiles, and groups.

Do not misuse `optional:` to address precedence problems.

## 17. What Is spring.config.on-not-found=ignore?

Spring Boot provides a broad option to handle Config Data not-found errors:

~~~properties
spring.config.on-not-found=ignore
~~~

Spring Boot 3.3 documentation notes setting this property **from a very early available source**, such as:

~~~bash
java -Dspring.config.on-not-found=ignore -jar app.jar
~~~

Or via environment variable:

~~~bash
export SPRING_CONFIG_ON_NOT_FOUND=ignore
java -jar app.jar
~~~

Or programmatically via `SpringApplication.setDefaultProperties(...)` before running.

### Why Avoid Using It by Default?

It can hide multiple missing-location errors instead of allowing only one specific source to be absent. In production, this is dangerous when the skipped source contains:

- Database URLs.
- Credentials or signing secrets.
- Critical endpoint lists.
- Payment policies or transaction limits.
- Security configuration.
- Mandatory values for a profile.

**Prefer `optional:` on each individual address allowed to be missing**, instead of enabling global ignore.

### Do Not Treat ignore as a Cure for Every Startup Error

Even with not-found ignored, broken YAML syntax, invalid config values, conversion/validation failures, or application bugs can still fail startup.

This property does not make Spring Boot create missing files. It only affects how one supported error class is handled.

## 18. Where Can optional: Be Used?

Per Spring Boot 3.3 docs, the `optional:` prefix works with:

- `spring.config.import`.
- `spring.config.location`.
- `spring.config.additional-location`.

Import example:

~~~yaml
spring:
  config:
    import: "optional:file:./local-dev.yml"
~~~

CLI example:

~~~bash
java -jar app.jar   --spring.config.additional-location=optional:file:./overrides/
~~~

Multiple locations example:

~~~properties
spring.config.import=optional:file:./a.yml,optional:file:./b.yml
~~~

**Prefix each optional location individually.** If a list includes a mandatory location, do not assume `optional:` on the first entry automatically applies to the whole list.

### When to Use It?

- A local override file for developers.
- Additional configuration mounted only in certain environments.
- A secret/configtree genuinely unneeded when a module is safely disabled via configuration.
- Profile-specific resources that are truly non-mandatory.

### When Not to Use It?

- Mandatory file containing production credentials.
- Database configuration required to protect transactional data.
- File containing mandatory security policies.
- Remote configuration acting as the single source of truth that is currently unreachable.
- Cases where the error is 403, parse error, or misconfiguration rather than missing.

## 19. Mapping Error Messages to Common Causes

| Symptom | Possible cause | First action |
| --- | --- | --- |
| Cannot find `classpath:/config/extra.yml` | Resource not on classpath/JAR | Check `src/main/resources` and `jar tf` |
| Cannot find `file:./config/extra.yml` | Wrong working directory | Check `pwd`, `Get-Location` |
| Cannot find `file:/etc/app/extra.yml` | File not mounted or wrong path | Check inside container |
| Cannot find directory with `spring.config.location` | Missing trailing slash or directory absent | Use `file:./config/` and verify |
| Unrecognized `remote:` scheme | Missing resolver/plugin dependency | Check classpath and `spring.factories` |
| Works in dev, fails in prod | Import exists only in prod document | Check profile and mounts |
| File exists yet Boot still errors | Path casing, extension, stale artifact | Check exact path and JAR |
| No error yet property missing | File not loaded or wrong key | Check prefix, profile, precedence |
| YAML parser error | Invalid file content | Fix YAML; do not add optional |
| Cannot open file due to permissions | Permissions or security policy | Check permissions/owner; do not assume missing |
| Config tree exists yet secret key missing | Key file absent in tree | Check filename and Bean Validation |
| Location has classpath wildcard | Unsupported wildcard type | Use valid file location or explicit paths |

Avoid jumping straight to "wrong path" when the message could originate from a custom resolver or missing scheme-support dependency.

## 20. An End-to-End Error Analysis Example

### Scenario

In `application.yml`:

~~~yaml
spring:
  config:
    import: "file:./config/credentials.yml"

app:
  remote:
    enabled: true
~~~

Application launches:

~~~bash
cd /srv/app
java -jar build/app.jar
~~~

Yet the real file sits at:

~~~text
/srv/app/secrets/credentials.yml
~~~

### Analysis

1. `file:./config/credentials.yml` resolves against working directory `/srv/app`.
2. The path Spring Boot searches is `/srv/app/config/credentials.yml`.
3. Actual file is `/srv/app/secrets/credentials.yml`, so they mismatch.
4. Because the import is required, startup reports a not-found error.
5. The fix is updating the import to `file:./secrets/credentials.yml` or mounting the file at the declared path.

### Do Not Fix Like This

~~~yaml
spring:
  config:
    import: "optional:file:./config/credentials.yml"
~~~

if credentials are truly required. Doing so merely hides a broken path; the service can still fail later or fall back to unsafe defaults.

### Better Fix

Set the right location and keep it mandatory:

~~~yaml
spring:
  config:
    import: "file:./secrets/credentials.yml"
~~~

Then re-test with the exact working directory, file read permissions, and profile.

## 21. Example: Classpath Resource Missing After Packaging JAR

### Scenario

Resource in project:

~~~text
src/test/resources/config/mock-clients.yml
~~~

Production application:

~~~yaml
spring:
  config:
    import: "classpath:/config/mock-clients.yml"
~~~

Tests run via the IDE can see the resource on the test classpath. However, the production JAR omits `src/test/resources`, causing not-found.

### Fix

If the file is genuinely application config, move it to:

~~~text
src/main/resources/config/mock-clients.yml
~~~

and repackage. If it is only for tests, **never import it in production config**. Instead import it only in `application-test.yml` or use a test-specific mechanism when the test profile is active.

Example:

~~~yaml
# src/test/resources/application-test.yml
spring:
  config:
    import: "classpath:/config/mock-clients.yml"
~~~

Test class:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class ClientIntegrationTest {
}
~~~

Files in `src/test/resources` can be found on the test classpath, yet are not included in the production artifact by default.

## 22. An Error Related to Profile Filename Mismatch

### Scenario

Developer names the file:

~~~text
src/main/resources/application-production.yml
~~~

yet runs:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Spring Boot searches for the `application-prod.yml` variant by convention for profile `prod`; it does not automatically treat `prod` as `production`.

When the profile-specific file is not loaded, keys inside it are absent. This **may not throw ConfigDataNotFoundException**, because Spring Boot does not require profile files to exist.

### Diagnosis

- Check the actual active profile.
- Compare filename and profile.
- Check whether `spring.config.import` lives inside a profile document.
- Check effective property values in Environment (without printing secrets).

### Fix

Pick a consistent convention:

~~~text
Profile: prod
File: application-prod.yml
~~~

Or change the activated profile to `production` if all configuration actually uses that name.

## 23. Custom Config Data Sources and Error Classification

Spring Boot lets libraries implement:

~~~java
ConfigDataLocationResolver<R extends ConfigDataResource>
ConfigDataLoader<R extends ConfigDataResource>
~~~

Example:

~~~yaml
spring:
  config:
    import: "team-config:orders"
~~~

The resolver must:

1. Recognize `team-config:` via `isResolvable(...)`.
2. Resolve the address into a resource via `resolve(...)`.
3. If profile-aware, create appropriate resources via `resolveProfileSpecific(...)`.

The loader must:

1. Check loadability via `isLoadable(...)` when needed.
2. Execute `load(...)` returning `ConfigData`.

If no resolver is registered or none recognizes the scheme, the error can be **UnsupportedConfigDataLocationException**, not resource not-found. The `optional:` prefix cannot compensate for missing implementation support for a location.

If the resolver recognizes the scheme yet the backend lacks the document, the loader can throw `ConfigDataResourceNotFoundException` semantically.

### Example Handling Missing in a Custom Loader

~~~java
@Override
public ConfigData load(
        ConfigDataLoaderContext context,
        TeamConfigResource resource) throws IOException {

    TeamDocument document = client.fetch(resource.id());

    if (document == null) {
        throw new ConfigDataResourceNotFoundException(resource);
    }

    Map<String, Object> values = document.toPropertyMap();

    return new ConfigData(List.of(
            new MapPropertySource("team-config[" + resource.id() + "]",
                    values)));
}
~~~

`TeamConfigResource`, `TeamDocument`, and `client` are user-defined abstractions, not built-in Spring Boot APIs; the snippet illustrates the handling principle.

### Do Not Convert Every Error to Not-Found

Flawed design:

~~~java
try {
    return loadFromRemote();
} catch (Exception ex) {
    throw new ConfigDataResourceNotFoundException(resource, ex);
}
~~~

A remote request can fail due to:

- HTTP 401: invalid/expired token.
- HTTP 403: access denied.
- HTTP 429: rate limited.
- HTTP 500/503: backend unavailable.
- Network timeout.
- Malformed response schema.

These errors differ from "document does not exist." If all are wrapped as not-found, `optional:` or ignore policies can mask infrastructure and security failures. Classify and handle according to the real data source contract.

## 24. Debug Logs for Config Data

To observe startup, Spring Boot supports package-level logging:

~~~bash
java -jar app.jar   --logging.level.org.springframework.boot.context.config=TRACE
~~~

You can add:

~~~bash
java -jar app.jar --debug
~~~

`--debug` enables certain Spring Boot diagnostic reports, yet does not mean every Config Data step prints in detail. When needing to trace location resolution, the log level on `org.springframework.boot.context.config` is usually a more targeted starting point.

**Note:** errors occur very early when logging may not be fully initialized; exact log output depends on version, environment, and startup path.

In production, avoid enabling TRACE indiscriminately if logs might expose secret locations, property values, or excessive infrastructure details. When sharing logs for support, redact credentials, tokens, and sensitive paths as needed.

### Reading Logs Sequentially

Focus on:

1. Which line reports the import/location being processed.
2. Which group the root exception belongs to.
3. Which location and resource are referenced.
4. Whether the optional flag is present.
5. Whether profile-specific resolution occurred.
6. What action failure analysis recommends.

Do not overlook the final cause simply because many `SpringApplication` frames sit above it in the stack trace.

## 25. Using Environment to Verify After Fixing

Once the application starts, you can use `ApplicationRunner` to inspect a **non-sensitive** value:

~~~java
package com.example.configdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
public class ConfigDebugConfiguration {

    @Bean
    ApplicationRunner inspectEnvironment(Environment environment) {
        return args -> {
            String origin = environment.getProperty("demo.origin");
            System.out.println("demo.origin=" + origin);
        };
    }
}
~~~

If the import loaded and contains `demo.origin`, the value will be read from Environment per precedence order.

**Never print passwords, tokens, or all PropertySources** just to verify an import. For secrets, confirm only **presence** or validation status without logging real values.

### Actuator

If the project enables Spring Boot Actuator, the `env` or `configprops` endpoints can help locate property sources after startup, provided access controls and sensitive-data masking are properly configured.

If startup fails during the Config Data stage, Actuator never gets a chance to run. In that case rely on bootstrap logs and inspect the filesystem/classpath.

## 26. Property Exists Yet Is Overridden: Not a Not-Found Error

Example:

`application.yml`:

~~~yaml
app:
  worker:
    count: 4
~~~

`extra.yml`:

~~~yaml
app:
  worker:
    count: 8
~~~

When importing `extra.yml`, imported data can take precedence over the document declaring the import.

Yet if run with:

~~~bash
java -jar app.jar --app.worker.count=20
~~~

the final value can be 20 because CLI has higher precedence than standard Config Data.

If a test sees `count=20` and assumes the import did not run, that conclusion can be wrong. Separate two questions:

- **Did the resource load successfully?**
- **What is the effective value across all sources?**

A resource can load cleanly while its property is overridden by another source.

## 27. Wrong Path or Missing Read Permissions?

Not every file-opening failure is "does not exist." For example on Linux:

~~~bash
ls -l /etc/myapp/config.yml
~~~

the file may exist yet the Java process lacks read permissions. The root cause can be `AccessDeniedException`, `FileSystemException`, or another appropriate exception.

Check:

- User/UID of the Java process.
- Permissions on the file and all parent directories.
- Container/Pod security context.
- Whether a read-only mount affects reading (read-only files are normally readable).
- SELinux/AppArmor or filesystem policies if enforced by the environment.
- Whether the path has a symlink pointing to a missing target.

Do not add `optional:` when the file exists yet is unreadable. That does not fix permission errors and can produce unpredictable behavior if the exception is classified differently from missing.

## 28. Broken YAML and Unresolved Placeholders

### Broken YAML

Example:

~~~yaml
app:
  client:
    timeout: [1s
~~~

The file may exist, yet YAML syntax is invalid. Parser errors at the Config Data stage are not fixed merely by `optional:`.

### Missing Placeholder

Example:

~~~yaml
app:
  client:
    endpoint: "${REMOTE_ENDPOINT}"
~~~

The file still loads, yet when a bean queries this property, the placeholder can fail to resolve as intended and fail later.

The issue here is not a missing location/resource, rather an unsupplied **value** or **configuration dependency**. Placeholder defaults can be used where appropriate:

~~~yaml
app:
  client:
    endpoint: "${REMOTE_ENDPOINT:http://localhost:8080}"
~~~

However, for credentials or mandatory production endpoints, unsafe defaults can mask misconfiguration. Choose validation to fail fast when data must be present.

## 29. How to Reproduce and Test Missing Config Data

A manual test suite is very useful to verify policy.

### Case A: Required import missing

Create `application.yml`:

~~~yaml
spring:
  config:
    import: "file:./not-existing-demo.yml"
~~~

Ensure `not-existing-demo.yml` does not exist in the working directory, then run the app.

**Expected:** Spring Boot reports a not-found error and stops, assuming no broader ignore config is set.

### Case B: Optional import missing

~~~yaml
spring:
  config:
    import: "optional:file:./not-existing-demo.yml"
~~~

**Expected:** missing file alone does not fail startup. Beans/application can still fail if they require a mandatory property provided only by that file.

### Case C: Required import exists

Create `local-extra.yml`:

~~~yaml
demo:
  origin: local-extra
~~~

Import:

~~~yaml
spring:
  config:
    import: "file:./local-extra.yml"
~~~

**Expected:** resource loads, `demo.origin=local-extra` can be read unless overridden by a higher source.

### Case D: Profile-specific variant

Create:

~~~text
src/main/resources/application.yml
src/main/resources/application-dev.yml
~~~

Run `--spring.profiles.active=dev` and verify expected properties from the dev variant. If `application-dev.yml` is removed, check whether a missing error occurs or it simply falls back to values from the common file.

### Case E: Classpath mismatch

Put `extra.yml` in `src/test/resources` while importing `classpath:/extra.yml` in production config. Compare running tests against running the packaged JAR and observe the classpath difference.

## 30. Automating Tests by Running the Real Process

Because Config Data is processed very early, testing **the full bootstrap** is more reliable than unit-testing only a `@ConfigurationProperties` bean.

A CI scenario can:

1. Build the executable JAR.
2. Create a clean test directory.
3. Run the JAR with `--spring.config.import=file:./missing.yml`.
4. Assert non-zero exit code and logs show a not-found error group.
5. Re-run with `optional:file:./missing.yml`.
6. Assert missing file is no longer the cause of failure.
7. Create `missing.yml` containing a sentinel property.
8. Run the mandatory import again.
9. Verify the application sees the sentinel, without printing secrets.
10. Run with the `dev` profile and verify variants.

Do not assert solely against a verbatim exception string, as wording can change across patch versions. Focus on behavior: **fail fast when required is missing, proceed when optional is missing, load accurately when resource exists**.

### TestContext and @SpringBootTest

`@SpringBootTest` starts a Spring context for integration testing. However, `spring.config.import` must be present from **the Config Data bootstrap stage**; a property added too late may not take effect as expected.

For tests verifying `spring.config.location`, `spring.config.name`, and custom resolver discovery, use startup command/system properties or a test harness that genuinely controls Environment preparation instead of merely calling `Environment.setProperty` after context creation.

## 31. Decision Flowchart for Rapid Triage

~~~text
Spring Boot startup fails
             |
             v
Is it ConfigData...NotFoundException?
   | yes                              | no
   v                                  v
Check location / resource     Analyze other error:
   |                          parser, bind, validation,
   v                          permission, unsupported...
What is the scheme?
   |
   +-- classpath:  -> Check JAR/classpath/resources
   |
   +-- file:       -> Check working dir, path, mount
   |
   +-- configtree: -> Check volume directory, key files
   |
   +-- custom:     -> Check resolver/loader/backend
   |
   v
Is the resource genuinely allowed to be absent?
   | yes                             | no
   v                                 v
Add optional: to exact location  Fix path/mount/build/dependency
   |                                 |
   +---------------+-----------------+
                   |
                   v
Re-run in the right environment
                   |
                   v
Verify effective properties / validation
~~~

If a classpath resource is missing from the JAR, turning the import optional can let the app start missing data. If a file is mounted wrong, fixing the mount is the right action. If a remote source returns 403, fix permissions rather than calling it missing.

## 32. Rules to Remember for Production

1. **Fail fast on required configuration.** If a secret/database URL or mandatory policy is missing, a clear startup failure is far better than running half-configured.
2. **Mark only genuinely optional sources as optional.** Put `optional:` on specific locations; avoid unconditional global ignore.
3. **Ensure paths are runtime paths.** Containers/CI/services have different filesystems and working directories than laptops.
4. **Distinguish classpath from filesystem.** Resources in `src/test/resources` are not in the production JAR by default.
5. **Keep profile names and filenames consistent.** `prod` is not `production`; missing profile-specific files do not necessarily throw not-found.
6. **Do not conflate distinct errors.** Parsing, conversion, validation, auth, permissions, and not-found need different fixes.
7. **Keep logs safe.** Never log Secret/ConfigMap contents or URLs containing credentials.
8. **Check precedence order.** An import can succeed while its effective value is overridden by another source.
9. **Test both missing and optional cases.** Do not test only the happy path.
10. **Do not rely on beans creating files too late.** Config Data executes before most application beans.

## 33. Practice Exercises

### Exercise 1 — Distinguish Location and Resource

Explain why `ConfigDataLocationNotFoundException` and `ConfigDataResourceNotFoundException` both belong to `ConfigDataNotFoundException` yet represent two different stages.

**Answer:** location is the address to be resolved; resource is the concrete source object already identified by the resolver for the loader to load.

### Exercise 2 — Classpath

The file sits at `src/main/resources/config/rules.yml`. Write the correct import and inspect its path inside the executable JAR.

**Answer:** `classpath:/config/rules.yml`; inspect with `jar tf`.

### Exercise 3 — Relative File

The application runs from `/tmp` while the JAR sits in `/opt/app`. Where does `file:./config/extra.yml` point?

**Answer:** `/tmp/config/extra.yml` per the working directory, not automatically to the JAR's directory.

### Exercise 4 — Directory

The target file is named `custom.yml` inside `./config/`. With `spring.config.location=file:./config/` and default `spring.config.name`, why might the file not load?

**Answer:** directory search normally looks for basename `application`; specify the exact file, rename it, or supply `spring.config.name=custom` at the right bootstrap time.

### Exercise 5 — Optional and Required

A `dev-overrides.yml` file may not exist on CI. A `prod-secrets.yml` file must exist in production. Design the two locations and explain why only the first should be optional.

### Exercise 6 — Extension Hint

A volume has an extensionless file `/etc/config/appsettings` containing YAML. Write the import syntax with a hint.

**Answer:** `file:/etc/config/appsettings[.yaml]`.

### Exercise 7 — Config Tree

A volume contains `/run/secrets/db.password`. You need to read key `db.password`. Which scheme should you use?

**Answer:** `configtree:/run/secrets/`, with volume and read permissions configured properly.

### Exercise 8 — Wrong Profile

A file is named `application-production.yml`, yet active profile is `prod`. How do you diagnose? Why does `ConfigDataNotFoundException` not necessarily occur?

### Exercise 9 — Remote Config

A `ConfigDataLoader` calls a remote API and gets HTTP 403. Should it convert this into `ConfigDataResourceNotFoundException`?

**Answer:** no; handle authorization failure rather than pretending the resource does not exist.

### Exercise 10 — Checking Precedence

An import supplies `app.worker.count=5`, yet CLI has `--app.worker.count=20`. Why does the app receiving 20 not prove the import is missing?

**Answer:** property sources have precedence order; CLI can override Config Data values.

### Exercise 11 — Missing File Yet App Still Starts

An app lacks `application-prod.yml` yet runs with active profile `prod`. Must it fail?

**Answer:** no, profile-specific files in default search locations are not necessarily required to exist. Failures may come from an explicit import activated only in prod.

### Exercise 12 — Reading Logs

Create a non-existent location, run the app, and identify three facts: the source property that declared the location, the runtime path used, and whether the failure occurred in location resolution or resource loading.

## 34. Summary

When Spring Boot reports Config Data not found, **do not just see the word "missing" and slap on `optional:`**. First distinguish:

- **`ConfigDataLocationNotFoundException`**: the Config Data address could not be found.
- **`ConfigDataResourceNotFoundException`**: the already-resolved resource could not be found.
- **`UnsupportedConfigDataLocationException`**: no handler exists for the location/scheme.
- **Parse, permission, conversion, or validation errors**: different causes and different fixes.

Your best diagnostic tools are **the original location + actual runtime environment + Config Data precedence rules + profiles**. Check classpath/JAR for `classpath:`, filesystem and working directory for `file:`, volume mounts for `configtree:`, and resolvers/loaders/backends for custom schemes.

Use `optional:` for genuinely non-mandatory resources; limit `spring.config.on-not-found=ignore` because it can mask missing config across many places. After fixing, re-run in a production-equivalent environment and verify required properties have valid values, rather than merely concluding "the exception is gone."

## References

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — ConfigDataLocationNotFoundException API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataLocationNotFoundException.html)
- [Spring Boot 3.3 — ConfigDataResourceNotFoundException API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataResourceNotFoundException.html)
- [Spring Boot 3.3 — ConfigDataNotFoundException API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataNotFoundException.html)
- [Spring Boot 3.3 — ConfigDataEnvironmentPostProcessor API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataEnvironmentPostProcessor.html)
- [Spring Boot 3.3 — ConfigDataLocationResolver API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataLocationResolver.html)
- [Spring Boot 3.3 — ConfigDataLoader API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/config/ConfigDataLoader.html)
