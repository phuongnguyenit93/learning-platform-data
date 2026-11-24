# Reading `effective-pom`, `effective-settings`, and Interpolated Properties in Maven/Spring Boot

## 1. Why Must You Inspect the Computed Maven Configuration?

A Spring Boot project's `pom.xml` usually declares only part of the build configuration. Maven also pulls from the **Super POM**, parent POMs, `dependencyManagement`/BOMs, plugin management, active profiles, command-line properties, and host settings in `settings.xml`. Consequently, reading a module's POM file alone may not answer:

- Why does `spring-boot-starter-web` omit a version yet Maven still resolves one?
- Why is the Maven Compiler Plugin version or Java level different from what you expected?
- Why does machine A use a different mirror/repository than machine B when `pom.xml` is identical?
- Why does passing `-Pprod` produce a differently named artifact?
- What are the actual values of `${project.version}`, `${java.version}`, a profile-defined property, or an environment variable?

The **Apache Maven Help Plugin** offers three complementary tools:

| Goal | Question Answered | Primary Content |
|---|---|---|
| `help:effective-pom` | "What final project model does Maven see?" | POM combining inheritance, configurations, and active profiles |
| `help:effective-settings` | "Which machine/user settings is Maven using?" | Settings combining global/user configs, mirrors, servers, profiles, local repository... |
| `help:evaluate` | "What does Maven evaluate a given expression/property to?" | Value of one expression, handy for inspection or scripts |

Combine these with `help:active-profiles` to see which **Maven profiles** are active, and `dependency:tree` to inspect **actual resolved dependencies**. The effective POM is **not** the full dependency tree, nor does it guarantee showing every value evaluated lazily when a plugin goal executes.

## 2. How Do Source POM, Effective POM, and Settings Differ?

```text
                  Maven Super POM
                            |
                    Parent POMs (possibly multi-level)
                            |
                Current module's POM
                            |
             + Active Maven profiles
             + Applied properties/interpolation
             + Dependency/plugin management
                            |
                            v
                   EFFECTIVE POM
                   (project model)

  Global settings.xml + User settings.xml
                 + Maven settings profiles
                            |
                            v
                EFFECTIVE SETTINGS
            (Maven environment config)

  effective model + CLI -D + environment + plugin
                            |
                            v
       Evaluated expression / actual goal execution
```

The **POM** is project configuration, normally stored in Git. **`settings.xml`** is environment or user configuration: mirrors, proxies, repositories, server credentials, and settings profiles. Settings entries can **affect build behavior**, without turning `<servers>` or `<mirrors>` into elements inside the effective POM.

Typically:

- Global settings: `${maven.home}/conf/settings.xml` (inside the active Maven distribution).
- User settings: `${user.home}/.m2/settings.xml` (usually `~/.m2/settings.xml` on Linux/macOS, and `%USERPROFILE%\.m2\settings.xml` on Windows).
- User settings take precedence over conflicting global settings per Maven's merge rules.
- Maven Wrapper (`mvnw`/`mvnw.cmd`) picks the project's Maven version; Help Plugin still reads the POM and settings for that Maven invocation.

Note: **Spring profiles** (`spring.profiles.active`) control **Spring application config at runtime**. **Maven build profiles** (`-Pprod`) alter the **build model**. The two profile systems are independent unless you explicitly wire build-to-runtime forwarding.

## 3. Quick Inspection Commands on Linux/macOS and Windows

Run in the project directory containing `pom.xml` and Maven Wrapper. On Linux/macOS:

```bash
# Final POM after inheritance and Maven profiles
./mvnw help:effective-pom

# Write to a file for easier search/comparison (created in current directory)
./mvnw help:effective-pom -Doutput=effective-pom.xml

# Include comments hinting at element origins (supported Help Plugin versions)
./mvnw help:effective-pom -Dverbose -Doutput=effective-pom.xml

# Effective settings configuration
./mvnw help:effective-settings -Doutput=effective-settings.xml

# Active profiles
./mvnw help:active-profiles

# Read a single value
./mvnw -q help:evaluate -Dexpression=project.version -DforceStdout
```

On Windows PowerShell, use `mvnw.cmd`:

```powershell
.\mvnw.cmd help:effective-pom -Doutput=effective-pom.xml
.\mvnw.cmd help:effective-pom -Dverbose -Doutput=effective-pom.xml
.\mvnw.cmd help:effective-settings -Doutput=effective-settings.xml
.\mvnw.cmd help:active-profiles
.\mvnw.cmd -q help:evaluate -Dexpression=project.version -DforceStdout
```

On Command Prompt, use `mvnw.cmd`; if the project lacks a Wrapper and Maven is installed, use `mvn`. Running `help:...` commands may download the Maven Help Plugin and required POMs/metadata on the first run.

**Main flags explained:**

| Flag | Purpose |
|---|---|
| `-Doutput=effective-pom.xml` | Writes help goal output to an XML file instead of printing everything to the terminal |
| `-Dverbose` | With `help:effective-pom`, adds XML comments showing configuration origins; supported since Maven Help Plugin 3.2.0 |
| `-Dexpression=project.version` | Selects the Maven expression to evaluate; **do not wrap** in `${...}` |
| `-q` | Quiet: suppresses most Maven logs |
| `-DforceStdout` | Tells `help:evaluate` to print the value even when `-q` is passed; useful in CI/scripts |
| `-Pprod` | Activates the **Maven build profile** named `prod` |
| `-Dkey=value` | Passes a Maven user property for that invocation |
| `-s path/to/settings.xml` | Uses a custom user settings file instead of the default path |
| `-gs path/to/global-settings.xml` | Uses a custom global settings file instead of the default path |

To pin the **Maven Help Plugin** version itself, invoke the goal by full coordinates. For example:

```bash
./mvnw org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose -Doutput=effective-pom.xml
```

Maven Help Plugin `3.5.2` is a concrete version illustrating syntax; real version choice must match Maven/JDK and build conventions. When invoking shorthand `help:effective-pom`, the plugin version resolves from project/repository settings, so do not assume it is identical across all environments.

## 4. Spring Boot 3.x Example: Parent, Profiles, and Interpolated Properties

The complete example below pins **Java 17** and **Spring Boot 3.5.0** as illustrative versions and uses Maven Wrapper or installed Maven. Do not treat this example as claiming Spring Boot 3.5.0 is the latest release.

Create `pom.xml` in the root directory:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo-service</artifactId>
    <version>0.1.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <finalName>demo-service-${build.channel}</finalName>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>local</id>
            <activation>
                <activeByDefault>true</activeByDefault>
            </activation>
            <properties>
                <build.channel>local</build.channel>
            </properties>
        </profile>
        <profile>
            <id>prod</id>
            <properties>
                <build.channel>prod</build.channel>
            </properties>
        </profile>
    </profiles>
</project>
```

Create `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

This is a Spring Boot application **without the web starter**; running it does not open an HTTP endpoint by default. Because it has the Spring Boot parent and declares the Spring Boot Maven Plugin, `package` runs `repackage` per parent config and creates an executable JAR. Application startup logs vary by environment, so do not assume fixed stdout.

### 4.1. Default Case: `local` Profile

At the project root, run:

```bash
./mvnw help:active-profiles
./mvnw -q help:evaluate -Dexpression=project.version -DforceStdout
./mvnw -q help:evaluate -Dexpression=build.channel -DforceStdout
./mvnw -q help:evaluate -Dexpression=project.build.finalName -DforceStdout
./mvnw help:effective-pom -Dverbose -Doutput=effective-pom.xml
```

With this exact POM and no other settings/CLI overriding profiles or properties, **each `evaluate` command individually** returns:

```text
0.1.0
```

```text
local
```

```text
demo-service-local
```

These three blocks are **outputs of three separate `help:evaluate` invocations**, not a single run printing all three lines. In the effective POM, you will find:

```xml
<finalName>demo-service-local</finalName>
```

Other elements of the effective POM are inherited from `spring-boot-starter-parent` and the Super POM; they do not appear verbatim in the `pom.xml` you wrote.

Build and run the artifact:

```bash
./mvnw clean package
java -jar target/demo-service-local.jar
```

`clean package` requires appropriate Maven/JDK and permission to download plugins/dependencies if uncached. Actual build results are verified via logs and output files, not assumed from filenames alone.

### 4.2. Enabling Maven Profile `prod`

```bash
./mvnw -Pprod help:active-profiles
./mvnw -Pprod -q help:evaluate -Dexpression=build.channel -DforceStdout
./mvnw -Pprod -q help:evaluate -Dexpression=project.build.finalName -DforceStdout
./mvnw -Pprod help:effective-pom -Doutput=effective-pom-prod.xml
```

Corresponding `evaluate` outputs are:

```text
prod
```

```text
demo-service-prod
```

Because `local` is an `activeByDefault` profile **in the same POM**, activating `prod` deactivates `local` by default (assuming no other activation rule applies). In the `-Pprod` effective POM, `<finalName>` becomes `demo-service-prod`. Building yields:

```bash
./mvnw -Pprod clean package
java -jar target/demo-service-prod.jar
```

`-Pprod` here **only changes build parameters and the artifact name**. It does not automatically set the Spring runtime profile to `prod`. To enable the Spring runtime profile, configure the app or pass runtime flags explicitly, such as:

```bash
java -jar target/demo-service-prod.jar --spring.profiles.active=prod
```

The Java command above passes the argument to the **Spring application**. That is a separate decision from Maven choosing profile `prod` during the build.

### 4.3. Overriding Properties via Maven CLI

With `-Dbuild.channel=staging`, Maven receives a user property for that invocation. Example:

```bash
./mvnw -q help:evaluate -Dexpression=build.channel -Dbuild.channel=staging -DforceStdout
```

The printed value is:

```text
staging
```

In this example, the CLI user property takes high precedence for this expression. However, profile activation, plugin parameters, or special configurations can yield non-obvious behavior; whenever discrepancies occur, run `help:active-profiles`, `help:evaluate`, and `effective-pom` **with the exact same flags** used for the real build.

## 5. Reading the Effective POM Properly

### 5.1. Tracing Where a Setting Comes From

When a project inherits `spring-boot-starter-parent`, many defaults such as Java compilation, plugin versions, and plugin configs are not repeated in the child POM. Run:

```bash
./mvnw help:effective-pom -Dverbose -Doutput=effective-pom.xml
```

Open the file and inspect in order:

- `<parent>`: which parent and version are inherited.
- `<properties>`: final properties in the model.
- `<dependencyManagement>`: dependency versions that are **managed**.
- `<dependencies>`: dependencies **actually declared** in the current model.
- `<pluginManagement>`: default versions/configs for plugins.
- `<build><plugins>`: plugins actually configured in the build and their executions.
- `<finalName>`, `<sourceDirectory>`, `<resources>`: output names and directories.

With `-Dverbose`, the Maven Help Plugin inserts comments noting **source declaration locations** so you can trace entries back to a parent POM or module POM. Not every Help Plugin version supports verbose mode; modern versions support it from `3.2.0` onward.

**Key rule:** `<dependencyManagement>` or a Spring Boot BOM managing a version **does not automatically add** that dependency to the application. Seeing a library managed in the effective POM is not proof that it is on the classpath.

### 5.2. Knowing the Limits of Effective POM

The effective POM represents the project model after inheritance, interpolation, and profiles. It is **not**:

1. A full list of **transitive dependencies** and their final resolved versions. For that, use `dependency:tree`.
2. A snapshot of all plugin parameters at **goal execution time**. Some expressions inside plugin configurations are evaluated later and may still appear as `${...}` in the effective POM view.
3. A list of every server Maven definitely contacted. Settings/mirrors, repositories, cache, and dependency resolution govern actual network access.
4. Proof that a JAR/WAR packaged cleanly. You must build, inspect the artifact, and test running it.

Additional commands:

```bash
./mvnw dependency:tree
./mvnw help:active-profiles
./mvnw -X validate
```

`-X` enables debug logs to reveal extra Maven/plugin details when needed, though logs may expose local paths and environment details; never share raw logs if they contain sensitive data.

## 6. Effective Settings: Inspecting Machine and CI Configuration

Maven uses settings to control where artifacts come from and various environment options. Key sections to check in effective settings:

| Element | Meaning | Related Issues |
|---|---|---|
| `<localRepository>` | Path to Maven local repository | Build uses a different cache than expected |
| `<mirrors>` | Maps repository IDs/patterns to mirror URLs | Maven redirected through a broken mirror or missing artifacts |
| `<servers>` | Connection/authentication settings by server ID | 401/403 when accessing repositories |
| `<proxies>` | Proxies and non-proxy host rules | Unable to download dependencies/plugins |
| `<profiles>` | Repositories, pluginRepositories, properties configured in settings profiles | Machine A and B resolve from different repos or see different properties |
| `<activeProfiles>` | Settings profiles activated by default | Expected profile is not applied |

Commands:

```bash
./mvnw help:effective-settings -Doutput=effective-settings.xml
./mvnw help:active-profiles
```

Effective settings **merge global settings with user settings** and active runtime settings. For example, if a machine has an internal mirror configured, the POM may list only Maven Central while Maven actually routes requests to the mirror; check `<mirrors>` and repository IDs in effective settings.

**Security:** by default `help:effective-settings` **redacts passwords** (`showPasswords=false`). Never pass `-DshowPasswords=true` when sharing logs with others. Even with passwords masked, the output can contain internal hostnames, usernames, filesystem paths, or infrastructure details. Never commit `effective-settings.xml` to a repository or post it publicly without reviewing it.

### 6.1. Using an Alternative Settings File to Reproduce an Environment

When diagnosing differences between local and CI, you can run with an appropriately authorized settings file:

```bash
./mvnw -s ci-settings.xml help:effective-settings -Doutput=effective-settings-ci.xml
./mvnw -s ci-settings.xml help:active-profiles
./mvnw -s ci-settings.xml help:effective-pom -Doutput=effective-pom-ci.xml
```

`ci-settings.xml` here is an **example path**; the file must actually exist when running the commands. These commands do not generate new settings files. `-s` overrides the user settings location for that run; `-gs` overrides global settings. Always compare using the **same Maven/JDK/profiles/properties** and note which settings file was used.

Inside `settings.xml`, profiles support a **limited** set of elements (such as `repositories`, `pluginRepositories`, and `properties`); it is not the place to rewrite `<build><plugins>` of a POM. Plugin executions belong in POMs, parents, or plugin management.

## 7. Interpolated Properties: Syntax and How to Inspect Them

**Property interpolation** substitutes references like `${...}` with their values while Maven builds the model or when a plugin evaluates expressions. Not every reference is resolved at the same stage.

| Expression in POM/Plugin | Common Meaning | Verification Command |
|---|---|---|
| `${project.groupId}` | Project Group ID | `help:evaluate -Dexpression=project.groupId` |
| `${project.artifactId}` | Artifact ID | `help:evaluate -Dexpression=project.artifactId` |
| `${project.version}` | Project version | `help:evaluate -Dexpression=project.version` |
| `${project.basedir}` | Root directory of the POM/module | `help:evaluate -Dexpression=project.basedir` |
| `${project.build.finalName}` | Final artifact name (without extension) | `help:evaluate -Dexpression=project.build.finalName` |
| `${java.version}` | Property declared by project/parent/profile, if present | `help:evaluate -Dexpression=java.version` |
| `${env.JAVA_HOME}` | Environment variable of the Maven process | `help:evaluate -Dexpression=env.JAVA_HOME` |
| `${settings.localRepository}` | Local repository used by Maven | `help:evaluate -Dexpression=settings.localRepository` |
| `${build.channel}` | Custom property from the example POM | `help:evaluate -Dexpression=build.channel` |

Examples on Linux/macOS:

```bash
./mvnw -q help:evaluate -Dexpression=project.artifactId -DforceStdout
./mvnw -q help:evaluate -Dexpression=java.version -DforceStdout
./mvnw -q help:evaluate -Dexpression=project.build.finalName -DforceStdout
```

For the POM in Section 4, these three evaluate to `demo-service`, `17`, and `demo-service-local` when no overrides are present.

**Distinguishing three expression layers:**

- `${project.version}` and `${project.build.finalName}` depend on the active **Maven model**.
- `${env.JAVA_HOME}` depends on shell/CI **environment variables when Maven launches**. These can differ across IDEs, terminals, and pipelines.
- `${my.property}` comes from POM/parent/profile/settings or `-D`; the final value depends on sources and precedence rules.

Never pass `-Dexpression=${project.version}`: `help:evaluate` expects the expression name **without** `${...}`. Also do not assume every `${...}` inside Spring Boot resource config files is automatically evaluated by Maven: **Maven resource filtering** must be enabled and configured explicitly to rewrite resource files at build time. Spring Boot supports its own resource placeholder delimiter convention, whereas Spring runtime property resolution is a separate mechanism.

### 7.1. When Is a Property Left Uninterpolated?

You may see `${some.property}` still in XML or a goal reporting an invalid expression. Check:

1. Is the property name spelled accurately (dots and case matter)?
2. Is it defined in the **current POM, parent, active profile, settings profile, or CLI**?
3. Are you looking at the **child POM before interpolation** instead of the effective POM?
4. Is the expression inside a **plugin configuration** that the plugin evaluates only when the goal executes?
5. Are there differences in Maven/JDK/profiles/settings/CLI between the inspection command and the actual build command?
6. Is that key a **Spring runtime** property, such as `spring.profiles.active`, rather than a Maven model property?
7. Are you trying to interpolate a POM property inside `settings.xml`? Settings has its own scope and interpolation rules and cannot arbitrarily read POM properties.

Use `help:evaluate` to verify individual values, then inspect **actual goal behavior** when a plugin evaluates expressions or configs later.

## 8. Precedence, Profiles, and Environment: A Comparison Method

A specific configuration value can be influenced by:

- **Parent POM/Super POM:** provides defaults when the child POM omits them.
- **Child POM:** overrides allowed elements relative to the parent.
- **Active Maven profiles:** contribute properties, repositories, plugins, or dependencies per profile type.
- **CLI user properties (`-D...`):** usually take high precedence for supported expressions/properties.
- **Settings & environment:** configure mirrors, proxies, local repository, and settings profiles, and supply environment variables.
- **Plugin execution:** reads parameters, Java environment, or config when the goal runs.

There is **no single linear precedence table** covering every element. Inheritance rules for plugins, dependency management, profile activation, and repository mirrors differ. The reliable approach is running with the exact same flags and reading the computed output.

Example comparing two builds:

```bash
# Default environment:
./mvnw help:active-profiles
./mvnw help:effective-pom -Doutput=effective-pom-local.xml

# Enable Maven profile prod:
./mvnw -Pprod help:active-profiles
./mvnw -Pprod help:effective-pom -Doutput=effective-pom-prod.xml

# Compare differences using diff on Linux/macOS:
diff -u effective-pom-local.xml effective-pom-prod.xml
```

On Windows, open both files in a text diff tool. Remember files can differ in XML element ordering, absolute paths, or environment metadata; focus on the elements that actually affect the build.

In a **multi-module project**, each module can have its own effective POM, parent, and version. If module `orders-api` is a reactor member, target it with a Maven project selector:

```bash
./mvnw -pl :orders-api help:effective-pom
```

This illustrative command requires `orders-api` to actually exist in the reactor; if your module has another name, use its exact `artifactId`. Because `help:effective-pom` is an aggregator goal, read the output carefully when multiple projects are included instead of assuming the XML you are viewing belongs to the desired module.

## 9. Diagnosing Common Confusions

| Symptom | First Check | Resolution |
|---|---|---|
| Starter omits `<version>` yet still builds | Effective POM `dependencyManagement` and Spring Boot parent/BOM | Distinguish managed versions from declared dependencies |
| Maven uses a plugin version from an unclear source | `help:effective-pom -Dverbose`; `pluginManagement` section | Trace to the parent/plugin management defining it |
| Local uses a different repository than CI | `help:effective-settings` with same flags; check `<mirrors>`, `<profiles>` | Align settings/mirrors and access credentials |
| `build.channel` stays `local` even with `-Pprod` | `help:active-profiles`, `help:evaluate`, `-D...` flags | Verify profile activation and CLI overrides |
| Expression remains unresolved | `help:evaluate -Dexpression=...` and plugin config | Confirm property exists, is in right scope, and timing matches |
| `mvn help:effective-pom` differs from `./mvnw help:effective-pom` | `mvn -version` vs. `./mvnw -version`; settings/JDK | Use the project's Maven Wrapper and compare configurations |
| Dependency is "managed" yet missing at runtime | `dependency:tree`, runtime classpath, final artifact | Check actual `<dependencies>` declaration and scope |
| `-Pprod` does not activate `application-prod.yml` | Distinguish Maven profile from Spring runtime profile | Configure `spring.profiles.active` separately |
| Plugin behaves differently than effective POM appears | Plugin execution, goal/configuration, and debug logs | Check when the plugin evaluates its parameters |
| Help Plugin fails to download | Plugin repositories, mirrors, offline mode/cache | Inspect settings and network before blaming the POM |
| Unclear which module's output is shown | Reactor and `-pl`/`-f` | Target the exact module/POM and regenerate effective POM |

**Diagnostic exercise:** on one of your Spring Boot Maven projects, save the effective POM and effective settings (keeping diagnostic files out of commits), verify `project.version`, `java.version`, and `project.build.finalName`. Next, enable a Maven profile that sets a property and compare. If dependencies appear to conflict, run `dependency:tree`; if repositories fail, read `effective-settings`. This connects project configuration directly to the environment and real build behavior.

## 10. Checklist When Inspecting Merged Maven Configuration

- [ ] Run from the right POM/module using the project's Maven Wrapper and JDK.
- [ ] Use `help:effective-pom` to inspect parent, properties, plugin management, and active profile contributions.
- [ ] Use `-Dverbose` when tracing an element back to a parent POM or module.
- [ ] Run `help:active-profiles` with the exact `-P`/`-D`/settings used by the build command.
- [ ] Run `help:effective-settings` when suspecting mirror, proxy, local repository, or settings profile differences between hosts.
- [ ] Run `help:evaluate -Dexpression=name -q -DforceStdout` to read expression values; never pass `${name}` inside `expression`.
- [ ] Distinguish managed versions in `dependencyManagement` from dependencies actually on the classpath.
- [ ] Distinguish Maven `-P...` from Spring `spring.profiles.active`.
- [ ] Never treat the effective POM as a runtime dependency tree or proof of a valid executable JAR; inspect goals and artifacts separately.
- [ ] Keep effective settings, logs, and diagnostic files confidential when they contain internal URLs or environment info.

**Takeaway:** `effective-pom` answers **how Maven merged the build model**; `effective-settings` answers **which machine/user configuration Maven is running with**; `help:evaluate` answers **what value a property or expression resolves to**. Combine all three with active profiles and dependency trees to explain any gap between the `pom.xml` you see and real build results.

## Official References

- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven Help Plugin — effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html)
- [Apache Maven Help Plugin — evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html)
- [Maven POM Reference](https://maven.apache.org/pom.html)
- [Maven Settings Reference](https://maven.apache.org/settings.html)
- [Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)