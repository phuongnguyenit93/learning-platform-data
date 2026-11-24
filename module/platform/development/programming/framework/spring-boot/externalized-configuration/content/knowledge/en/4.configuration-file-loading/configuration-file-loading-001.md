# Default `application.properties` and `application.yaml` Search Locations in Spring Boot

## 1. Objectives and Context

Spring Boot allows an application to use configuration packaged inside the JAR as well as configuration located outside the JAR. Therefore, an `application.yaml` file in the source code is not necessarily the only place providing values, and an `application.properties` file placed next to the JAR is not guaranteed to be read if the process is started from a different directory.

This lesson belongs to the **File Discovery and Loading** group of **Spring Boot Externalized Configuration**. The focus is on the **default file search locations** of the Config Data mechanism in Spring Boot 3.3.x. This is one part of Externalized Configuration; sources such as environment variables, Java system properties, and command-line arguments can also affect the effective value, though they are not default file search locations.

After practicing, you will be able to:

- Name the five locations where Spring Boot searches for `application.properties`, `application.yaml`, and `application.yml` when no custom location is set.
- Distinguish between classpath paths, working-directory-relative paths, and wildcard paths.
- Predict which file overrides when multiple locations define the same key.
- Understand why the same JAR running in two different directories can receive different configuration.
- Write an application that inspects `Environment` and run repeatable experiments.
- Explain the different effects of `spring.config.name`, `spring.config.location`, and `spring.config.additional-location`.
- Identify common mistakes involving file names, profiles, working directories, and precedence order.

## 2. The Five Default Locations

Spring Boot searches for files with the default base name `application` in the following locations, in the order they are processed:

| Order | Location | Example File |
| --- | --- | --- |
| 1 | `classpath:/` | `classpath:/application.yaml` |
| 2 | `classpath:/config/` | `classpath:/config/application.properties` |
| 3 | `file:./` | `./application.properties` |
| 4 | `file:./config/` | `./config/application.yaml` |
| 5 | `file:./config/*/` | `./config/team-a/application.yaml` |

**Order matters:** within this default set of files, a location processed later can override values for the same key from an earlier location. For example, if a key appears in both a file inside the JAR and `./config/application.yaml`, the external value normally wins when no higher-precedence configuration source or special location setting is present.

Do not interpret the table above as five mandatory files. Any location may not exist; Spring Boot can still start. If multiple files are loaded, non-overlapping keys are combined. When keys collide, precedence order determines the effective value.

```text
      CLASSPATH SOURCES                        SOURCES OUTSIDE THE JAR
      -----------------                        -----------------------
        classpath:/                                file:./
        classpath:/config/                         file:./config/
                                                   file:./config/*/
                    \                              /
                     \                            /
                      +------ Config Data --------+
                                   |
                                   v
                         Spring Environment
                                   |
                                   v
                      Values used by application
```

### 2.1. What is `classpath:/`?

This is the root of the Spring Boot process classpath. In a typical Gradle or Maven project, the file:

```text
src/main/resources/application.yaml
```

is placed onto the classpath after building. In a standard Spring Boot executable JAR, application resources typically reside at:

```text
BOOT-INF/classes/application.yaml
```

`src/main/resources` is a **development-time path**, not a runtime location that Spring Boot scans by that name. When running the JAR, Spring Boot reads resources through the classpath.

### 2.2. What is `classpath:/config/`?

If the project contains:

```text
src/main/resources/config/application.properties
```

then this file becomes a resource at the location:

```text
classpath:/config/application.properties
```

and is typically packaged at `BOOT-INF/classes/config/application.properties`. Placing configuration inside the `config` directory under resources is still **packaged inside the application**; it is different from a `config` directory outside the JAR.

In the default order table, `classpath:/config/` comes after `classpath:/`. When both places contain the same key and there is no stronger source, the file at `classpath:/config/` can determine the effective value.

### 2.3. What is `file:./`?

`file:` refers to a file or directory on the filesystem. The dot `.` means the **working directory of the running process**.

For example:

```bash
cd /srv/run
java -jar /opt/apps/my-app.jar
```

Spring Boot will look for `file:./application.properties` corresponding to:

```text
/srv/run/application.properties
```

rather than automatically switching to `/opt/apps/application.properties` just because the JAR is located there.

This is a major source of operational confusion: IDEs, Gradle `bootRun`, terminals, Docker, and systemd can all set different working directories. Check the value of `user.dir` or the launcher's working directory configuration.

### 2.4. What is `file:./config/`?

If the process has working directory `/srv/run`, Spring Boot can read:

```text
/srv/run/config/application.properties
/srv/run/config/application.yaml
/srv/run/config/application.yml
```

This is a common way to place configuration outside the JAR. Files can be edited per environment without repackaging the application code. However, after editing a file, the application in this lesson needs to be **restarted** to reload config data; hot reload is not enabled by default.

### 2.5. What is `file:./config/*/`?

`*` is a wildcard symbol that expands **direct subdirectories** of `./config/`. For example:

```text
working-dir/
└── config/
    ├── team-a/
    │   └── application.yaml         # searched
    ├── team-b/
    │   └── application.properties   # searched
    └── team-c/
        └── nested/
            └── application.yaml     # not searched directly
```

By default, the wildcard only descends one directory level beneath `./config/`; it does not scan recursively without limit. This wildcard location mechanism applies to sources outside the classpath. If there are multiple subdirectories, wildcard locations are sorted alphabetically by their absolute path. Avoid declaring duplicate keys across multiple subdirectories unless you intentionally manage their precedence order.

## 3. Recognized File Names and Formats

The default base name is `application`. Supported common file names are:

```text
application.properties
application.yaml
application.yml
```

`application.properties` uses key-value syntax:

```properties
lab.origin=packaged-root
lab.retry-count=3
lab.feature-enabled=true
```

`application.yaml` represents the same data:

```yaml
lab:
  origin: packaged-root
  retry-count: 3
  feature-enabled: true
```

Both can be loaded into `Environment`. However, when both `.properties` and YAML exist at the **same location**, Spring Boot gives precedence to `.properties`. Use one primary format per location and avoid having two files declare the same key.

When a profile is activated, for example `dev`, Spring Boot also considers profile-specific files using the same location search mechanism:

```text
application-dev.properties
application-dev.yaml
application-dev.yml
```

The name `application-dev.yaml` does not automatically activate `dev`. You need to configure the active profile, for instance when running:

```bash
java -jar app.jar --spring.profiles.active=dev
```

When multiple profiles or multiple location groups are used, precedence can be more complex than the basic five-row list. This lesson keeps a single profile and the default location group to focus on file discovery.

## 4. Example of How Files Are Combined

Suppose the same key `lab.origin` appears in five files:

| File | Value of `lab.origin` |
| --- | --- |
| `classpath:/application.yaml` | `packaged-root` |
| `classpath:/config/application.yaml` | `packaged-config` |
| `file:./application.properties` | `external-root` |
| `file:./config/application.yaml` | `external-config` |
| `file:./config/team-a/application.properties` | `external-team-a` |

If using the default locations with no active profile or other overriding sources, the expected result is:

```text
lab.origin = external-team-a
```

A source at a location evaluated later overrides **duplicate keys**. Other properties can still come from earlier files. For example, if only `classpath:/application.yaml` defines `lab.retry-count=3`, that value can still be used even though `lab.origin` comes from an external file.

The key point to remember is that **file discovery** and **effective value resolution** are two related but distinct stages. Do not conclude that a file was ignored just because one of its properties was overridden by another source.

## 5. Creating a Sample Application to Observe Locations

We will create a minimal console application named `config-locations`. It uses Java 21, Spring Boot 3.3.x, and Gradle. The application prints the working directory, active profiles, the effective value of `lab.origin`, and the names of the `PropertySource`s that can provide this key. No HTTP endpoint is needed.

Structure:

```text
config-locations/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    └── main/
        ├── java/dev/example/configlocations/
        │   └── ConfigLocationsApplication.java
        └── resources/
            ├── application.yaml
            └── config/
                └── application.yaml
```

You can generate the skeleton with Spring Initializr, choosing Java, Gradle, and a Spring Boot version compatible with 3.3.x; keep the Gradle Wrapper generated by the project. File `settings.gradle`:

```groovy
rootProject.name = 'config-locations'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

If you are inside a repository that manages plugin versions centrally, use the versions and Gradle structure of that repository.

### 5.1. Code to Print Evidence from `Environment`

`src/main/java/dev/example/configlocations/ConfigLocationsApplication.java`:

```java
package dev.example.configlocations;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@SpringBootApplication
public class ConfigLocationsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigLocationsApplication.class, args);
    }

    @Bean
    ApplicationRunner inspect(ConfigurableEnvironment environment) {
        return args -> {
            String key = "lab.origin";

            System.out.println("=== CONFIG LOCATIONS ===");
            System.out.println("workingDirectory = "
                    + System.getProperty("user.dir"));
            System.out.println("activeProfiles = "
                    + Arrays.toString(environment.getActiveProfiles()));
            System.out.println("effectiveValue = "
                    + environment.getProperty(key, "<missing>"));

            System.out.println("Matching property sources:");
            for (PropertySource<?> source
                    : environment.getPropertySources()) {

                // Skip the composite adapter to focus on the
                // specific underlying PropertySources.
                if ("configurationProperties".equals(source.getName())) {
                    continue;
                }

                Object value = source.getProperty(key);
                if (value != null) {
                    System.out.println("- " + source.getName()
                            + " => " + value);
                }
            }
        };
    }
}
```

Two types of output must be distinguished:

- `effectiveValue` is the value Spring `Environment` returns for `lab.origin`.
- `Matching property sources` are the sources that return a value when looking up this key directly, in iteration order.

Source display names may vary by packaging and version. This observer serves **the three simple configuration patterns in the lab**; it is not a complete tracing tool for all cases of relaxed binding, placeholders, imports, or custom configuration sources. Because it only prints the mock key `lab.origin`, the sample code will not accidentally leak secrets from the application.

### 5.2. Two Files on the Classpath

`src/main/resources/application.yaml`:

```yaml
spring:
  main:
    web-application-type: none

lab:
  origin: packaged-root
  retry-count: 3
```

`src/main/resources/config/application.yaml`:

```yaml
lab:
  origin: packaged-config
```

Setting `web-application-type: none` allows the console application to finish and exit without needing an HTTP port.

From the project root directory, run:

macOS/Linux:

```bash
./gradlew bootJar
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootJar
.\gradlew.bat bootRun
```

If there are no external files with the same configuration name in the root directory and no higher-precedence sources, the expected output is:

```text
effectiveValue = packaged-config
```

Because `classpath:/config/` is evaluated after `classpath:/`. In the printed output, the corresponding sources may contain both `packaged-root` and `packaged-config`, but the effective value is `packaged-config`.

## 6. Experiments with the Same JAR

For each change below, launch a **new Java process**. Keep the generated JAR unchanged to prove that external configuration changes without rebuilding.

### Step A — change the working directory

Inside the project, create an empty `lab-run` directory.

macOS/Linux:

```bash
mkdir -p lab-run
cd lab-run
java -jar ../build/libs/config-locations-0.0.1-SNAPSHOT.jar
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force lab-run | Out-Null
Push-Location lab-run
java -jar ..\build\libs\config-locations-0.0.1-SNAPSHOT.jar
```

When there are no external configuration files in `lab-run` yet, the prediction is:

```text
workingDirectory = .../config-locations/lab-run
effectiveValue = packaged-config
```

This result proves that files on the classpath are still loaded even when Java is not run from the source directory.

### Step B — add a file at `file:./`

Inside `lab-run`, create `application.properties`:

```properties
lab.origin=external-root
```

Run `java -jar ...` again from `lab-run`. Expectation:

```text
effectiveValue = external-root
```

The `file:./` location now points to the `lab-run` directory. The external file takes precedence over the classpath value under the default rules.

### Step C — add a file at `file:./config/`

Create `lab-run/config/application.yaml`:

```yaml
lab:
  origin: external-config
```

Structure:

```text
lab-run/
├── application.properties
└── config/
    └── application.yaml
```

Run the same JAR again. Expectation:

```text
effectiveValue = external-config
```

Point to distinguish: the result comes from the **order of two different locations**. Do not misapply the rule that `.properties` beats YAML in the same location: here one file is at `./`, and the other is at `./config/`.

### Step D — add a file in a subdirectory of `config`

Create `lab-run/config/team-a/application.properties`:

```properties
lab.origin=external-team-a
```

Directory tree:

```text
lab-run/
├── application.properties
└── config/
    ├── application.yaml
    └── team-a/
        └── application.properties
```

Run again:

```text
effectiveValue = external-team-a
```

This source is loaded because `team-a/` is a direct subdirectory recognized by the `file:./config/*/` wildcard.

### Step E — verify the one-level limit of the wildcard

Add the file:

```text
lab-run/config/team-b/nested/application.properties
```

Content:

```properties
lab.origin=deeply-nested
```

Run again without imports or additional locations:

```text
effectiveValue = external-team-a
```

The file in `team-b/nested/` is not automatically discovered by `file:./config/*/`, because the wildcard only takes Spring Boot one level down into direct subdirectories of `config`.

### Step F — `.properties` and YAML in the same location

Temporarily move `lab-run/config/team-a/application.properties` outside `lab-run/config/` so there is no wildcard source overriding it. Keep `lab-run/config/application.yaml` from Step C and also create:

`lab-run/config/application.properties`:

```properties
lab.origin=properties-at-same-location
```

Both files in `file:./config/`:

```text
lab-run/config/
├── application.properties
└── application.yaml
```

Run again:

```text
effectiveValue = properties-at-same-location
```

This is the situation where **`.properties` takes precedence over YAML in the same location**.

### Results Log Table

| Step | Different Input | Expected `lab.origin` | Observed Value |
| --- | --- | --- | --- |
| A | Only files on the classpath | `packaged-config` | Fill in yourself |
| B | Add `./application.properties` | `external-root` | Fill in yourself |
| C | Add `./config/application.yaml` | `external-config` | Fill in yourself |
| D | Add `./config/team-a/application.properties` | `external-team-a` | Fill in yourself |
| E | Add file in `team-b/nested` | `external-team-a` | Fill in yourself |
| F | Remove `team-a` source; add `.properties` next to YAML in `./config/` | `properties-at-same-location` | Fill in yourself |

Whenever the value differs from the expected column, first check `workingDirectory`, `activeProfiles`, the names of the actual files present, and then the `Matching property sources` lines. Avoid editing multiple files at once while investigating the cause.

On Windows PowerShell, after practicing, you can use `Pop-Location` to return to the directory before entering `lab-run`.

## 7. Trying a Profile-Specific File

After cleaning up the duplicate-key files in wildcard directories and keeping only the base file `lab-run/config/application.yaml`, create:

`lab-run/config/application-dev.yaml`:

```yaml
lab:
  origin: external-config-dev
```

Run:

```bash
java -jar ../build/libs/config-locations-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev
```

On Windows, replace the JAR path separator with `\`.

When there is no higher-precedence source, the predicted output is:

```text
activeProfiles = [dev]
effectiveValue = external-config-dev
```

Spring Boot searches for profile-specific files in matching locations, and profile-specific values can override base values. Without passing `--spring.profiles.active=dev`, `application-dev.yaml` is not automatically activated merely by existing.

One thing to avoid is placing `spring.profiles.active` inside a YAML document dedicated to the profile you are trying to activate. The profile-selection property must be supplied in a valid place before profile-specific configuration documents are selected.

## 8. Customizing File Discovery

The `spring.config.*` group below is used when the default convention-based configuration does not meet your requirements.

### 8.1. `spring.config.name`: changing the base name

By default, Spring Boot looks for files with the base name `application`. If you want to look for `service.properties` or `service.yaml`, pass:

```bash
java -jar app.jar --spring.config.name=service
```

At this point, the set of file names searched changes. Do not assume that properties present only in the old `application.yaml` will still be loaded. If the app needs `spring.main.web-application-type=none`, place it in a source that will be loaded or pass it from an appropriate source.

Changing `spring.config.name` is **different** from adding a location; it changes the base name Spring Boot searches for at the locations.

### 8.2. `spring.config.location`: replacing the default location set

For example:

```bash
java -jar app.jar --spring.config.location=optional:file:./ops/
```

This is how you specify a location set to replace the default location list. If you do not include the classpath in the new list, default files on the classpath may no longer be loaded. Use this when you genuinely want explicit control over where configuration is read from.

The `optional:` prefix allows a location to be absent without failing the application for that location. For a **directory** location, end it with `/` so Spring Boot can append the file names to search for.

### 8.3. `spring.config.additional-location`: adding locations

If you want to keep using the default files and also read `./ops/`, pass:

```bash
java -jar app.jar --spring.config.additional-location=optional:file:./ops/
```

Suppose `./ops/application.yaml` contains:

```yaml
lab:
  origin: from-ops
```

and no other source has higher precedence, the effective value can be `from-ops`. Configuration at the default locations still contributes the remaining properties.

The `spring.config.additional-location` property is suitable when operations want to add a configuration directory outside the JAR while retaining the packaged base configuration.

### 8.4. Why must these properties be set early?

Spring Boot needs to know **where to look for files** before reading those files. Therefore `spring.config.name`, `spring.config.location`, and `spring.config.additional-location` are read at an early stage, typically via command-line arguments, environment variables, or Java system properties. Do not place them inside a file that has not yet been discovered and expect that file to tell Spring Boot to find itself.

If multiple locations are passed, `,` and `;` separators have meaning for **location groups**, especially when profile-specific files are also present. Do not generalize the simple rules from this lab to every custom location combination.

### 8.5. When to use `spring.config.import`?

`spring.config.import` can import additional config data from another file or source declared inside configuration that has already been loaded. This is a separate mechanism suited for intentional imports. It is not a sixth default location. When debugging, if a value appears from a path outside the five locations, check whether any import or additional source has been declared.

## 9. Distinguishing Code-Time, Build-Time, and Runtime Paths

A consolidated example:

```text
CODE TIME
project/
└── src/main/resources/application.yaml
                         |
                         | Gradle build
                         v
INSIDE EXECUTABLE JAR
app.jar!/BOOT-INF/classes/application.yaml
                         |
                         | java -jar /opt/apps/app.jar
                         | working directory = /srv/run
                         v
EXTERNAL CONFIGURATION
/srv/run/application.properties
/srv/run/config/application.yaml
/srv/run/config/team-a/application.yaml
```

Three path levels must be viewed separately:

1. **Source path:** `src/main/resources` exists during development.
2. **Runtime classpath:** resources are packaged and accessed via `classpath:/`.
3. **Runtime filesystem:** files outside the JAR are searched via `file:./` and locations relative to the working directory.

If you move the JAR to another directory while keeping the same working directory, `file:./...` locations are still resolved from the working directory. If you change the working directory while keeping the same JAR, the default external files may change. That is why two machines running the same artifact can receive different values without any packaging bug.

## 10. Common Errors and How to Find the Cause

**"I placed `application.properties` right next to the JAR, but the value doesn't show up."** Check the process's `user.dir`. A file next to the JAR is only found via the default locations if it also matches the working directory, or if an external location is configured to point there.

**"There is a file in `src/main/resources`, but production doesn't have this directory."** That is normal: resources are packaged onto the classpath. Inspect the build artifact instead of looking for a `src/main/resources` path on the machine running the JAR.

**"There is `settings.yaml` or `config-prod.yaml`, but the application doesn't read it automatically."** The default name is `application`. Rename the file according to convention, change `spring.config.name`, or configure the appropriate import/location. An arbitrary YAML file is not automatically loaded just because it sits in `./config`.

**"There is `application-dev.yaml`, but `activeProfiles` is still empty."** Enable the `dev` profile from a valid source; merely creating the file is not enough. Also check whether another source overrides the value after the profile is activated.

**"The file in `config/team-a/nested` has no effect."** The default wildcard location expands only one level from `config`. To read deeper, a dedicated location/import mechanism is needed.

**"Both YAML and properties files are in `./config`, but the value differs from what was expected."** Check whether `.properties` and `.yaml` are in the same location, and whether there is a higher-precedence file in `./config/<subdirectory>/`.

**"I edited the YAML and sent a new request, but the application didn't change."** Externalized configuration is loaded at startup by default. Restart the application to verify in this lab, unless the system uses a specially designed refresh mechanism.

**"There are multiple `config` subdirectories, and it's unclear which key wins."** List the directories expanded by the wildcard, the profile-specific file names, and all sources containing that key; reduce duplication or use an explicit location in operations.

**"`spring.config.location` caused some base values to disappear."** This property **replaces** the default locations. If you intend to keep the defaults, use `spring.config.additional-location` or explicitly list every needed location.

**"The value from the file still loses even though the file is at the last location."** This lesson only describes precedence among the default file locations. Check environment variables, system properties, CLI arguments, tests, imports, and additional sources that have higher precedence or different behavior.

## 11. Practice Questions

Before reading the hints, try answering on your own:

1. What are the five default locations in Spring Boot 3.3?
2. When running `java -jar /apps/app.jar` from `/home/service`, where does `file:./config/` point?
3. Is `src/main/resources/config/application.yaml` loaded from the filesystem outside the JAR or from the classpath?
4. Is a file at `./config/team-a/application.yaml` searched? What about `./config/team-a/nested/application.yaml`?
5. If only the file on the classpath sets `lab.retry-count=3`, while the external file only sets `lab.origin`, is the `retry-count` key lost?
6. Why can having both `application.properties` and `application.yaml` in the same location cause confusion?
7. Does an `application-dev.yaml` file automatically activate the `dev` profile?
8. When you want to add `./ops/` while keeping the base files inside the JAR, which property do you use?
9. When you want to replace the entire default location set, which property do you use?
10. After editing an external file, what action ensures the next run actually reloads the file?

**Hints:**

1. `classpath:/`, `classpath:/config/`, `file:./`, `file:./config/`, `file:./config/*/`.
2. `/home/service/config/`.
3. From the classpath, because source files are packaged as runtime resources.
4. The file in `team-a` is searched; the deeper file in `nested` is not discovered directly via the default wildcard.
5. No, non-overlapping keys can still come from another loaded source.
6. `.properties` takes precedence over YAML when in the same location.
7. No; the profile must be activated via a valid source.
8. `spring.config.additional-location`.
9. `spring.config.location`.
10. Restart the process with a controlled working directory and profile.

## 12. Real-World Application and Safety Principles

In real environments, keep non-sensitive base configuration inside the artifact, while environment-specific configuration should come from managed operational sources. Control the working directory, file read permissions, profiles, and `spring.config.*` properties of the deployed process. Do not expose passwords, tokens, or all environment variables in endpoints or logs just to inspect configuration precedence.

This lab uses `lab.origin` as a safe dummy value. The goal is not to memorize every Spring Boot property, but to build a workflow for tracing the source of a specific key: **identify the working directory → inventory the five default locations → identify file names and profiles → compare the effective value with PropertySources → find the overriding source → re-test with a fresh process**. This workflow helps explain why the same JAR can behave differently across a developer machine, CI, and production.