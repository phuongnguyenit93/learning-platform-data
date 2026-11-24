# Adding git.properties with the Appropriate Plugin for Commit Traceability in Spring Boot

## 1. Why embed the Git commit into the artifact?

A Spring Boot microservice may report `UP` at `/actuator/health`, yet when an incident happens the operations team still has to answer: **which commit was this JAR built from?** Two builds sharing version `1.0.0` do not necessarily share the same source code if they came from two different Git revisions, or if one was rebuilt from an uncommitted working tree.

Git commit information inside an artifact helps:

- Match running processes to a source revision and release pipeline.
- Pinpoint the exact commit that introduced a change to production or staging.
- Compare pods/nodes of the same service to spot inconsistent rollouts.
- Link incident logs, issues, pull requests, and CI builds to a source revision.
- Verify that the **deployed executable JAR** actually carries metadata for the newly built commit rather than relying on filenames or CI console logs.
- Support rollbacks, regression investigations, and additional evidence for release provenance.

The standard Maven solution is to use **Git Commit Id Maven Plugin** (current coordinates `io.github.git-commit-id:git-commit-id-maven-plugin`) to generate `git.properties` on the output classpath, which Spring Boot can read into a `GitProperties` bean and expose appropriately on Actuator `/actuator/info`.

This lesson belongs to **Build Metadata** under **Spring Boot Build Tooling Packaging**. After this lesson, you will be able to:

1. Understand `git.properties` and where the file must sit in plain JARs vs. Spring Boot executable JARs.
2. Configure the Maven plugin with an explicit version, appropriate phase, output path, and metadata allowlist.
3. Build a Java 17+/Spring Boot application with an endpoint reading the commit and Actuator `info`.
4. Inspect metadata in `target/classes` and **inside `BOOT-INF/classes/git.properties` of the packaged JAR**.
5. Compare the commit recorded in the archive against `git rev-parse HEAD` and explain discrepancies caused by shallow clones, detached HEAD, or dirty working trees.
6. Avoid leaking unnecessary details when exposing Git metadata over HTTP or distributing the JAR.
7. Distinguish `git.properties` from `build-info.properties`, Maven version, artifact checksums, and signing/release evidence.
8. Design a fail-fast CI step when Git metadata is missing or generated metadata does not match the commit.

**Illustration stack:** Java `17`, Spring Boot `3.5.16`, Maven `3.9+`, and Git Commit Id Maven Plugin `10.0.1`. This combination is chosen to explain the configuration, not to require every project to upgrade immediately. Plugin `10.0.1` is on Maven Central; major version 10 raised the requirement to Maven `3.9+`, so **check your project's build tool before upgrading**.

## 2. What is git.properties and when is it used?

`git.properties` is a Java Properties resource holding metadata extracted from the **Git repository at build time**. **Illustrative** example:

~~~properties
git.branch=main
git.commit.id=0123456789abcdef0123456789abcdef01234567
git.commit.id.abbrev=0123456
git.commit.time=2025-06-10T08:30:00Z
~~~

**The values in this example are not from a learner's project commit.** When the real plugin runs, the ID/branch/commit time are read from the current repository; they depend on the commit, checkout mode, and plugin configuration. Never copy a fake SHA into `src/main/resources/git.properties` to simulate traceability.

Key structure:

| Property | Meaning | Stability and limitations |
| --- | --- | --- |
| `git.commit.id` | Full Git object ID of the checked-out commit | The most important traceability key; typically 40 hex chars in SHA-1 repos, longer in SHA-256 repos |
| `git.commit.id.abbrev` | Abbreviated Git commit ID | Convenient for display but can collide; use full ID for exact matching |
| `git.commit.time` | Commit timestamp per Git | Not deployment time or JVM start time |
| `git.branch` | Branch name per checkout metadata | May differ between local and CI; under detached HEAD it may not be the release branch name |
| `git.dirty` | Working tree state at build if enabled | Useful to warn about non-commit builds; **does not replace** direct Git status checks before release |
| `git.build.time` | Timestamp when the plugin ran | Changes on every build; consider reproducibility requirements |

In the main example, we intentionally retain only **commit ID, abbreviated ID, commit time, and branch**. Fields such as committer email, full commit message, build user name, hostname, or remote URL are **unnecessary** for identifying the service's revision and could leak sensitive information if embedded into the artifact.

### 2.1. git.properties is not build-info.properties

| Resource | Typical producer | Primary focus | Provided by Spring Boot |
| --- | --- | --- | --- |
| `git.properties` at **classpath root** | `git-commit-id-maven-plugin` or equivalent Git plugin | Git revision, branch, commit time... | `GitProperties`, Actuator `GitInfoContributor` |
| `META-INF/build-info.properties` | Spring Boot Maven `build-info` goal or Gradle `bootBuildInfo` | Name, group, version, and build time | `BuildProperties`, Actuator `BuildInfoContributor` |
| `META-INF/MANIFEST.MF` | JAR/WAR archiver and Spring Boot repackage | `Main-Class`, `Start-Class`, manifest attributes | Used to launch/inspect archive |
| Artifact SHA-256 | Hashing tool on the **actual JAR file** | Byte-level identity of the artifact | Not automatically created by the Git plugin |

The Git commit is the **source revision identifier**, whereas the artifact checksum is the **byte-level identifier of the released file**. Two builds from the same commit can still produce different artifacts if timestamps, dependencies, or compiler behavior are uncontrolled. Generating `git.properties` **does not by itself make builds reproducible**.

### 2.2. Where does the file appear?

In a standard Maven Spring Boot project:

~~~text
Git repository + pom.xml
             |
             v
git-commit-id-maven-plugin:revision
             |
             v
target/classes/git.properties
             |
             v
Maven jar + spring-boot:repackage
             |
             v
target/commit-trace-demo-1.0.0.jar
  BOOT-INF/classes/git.properties
  BOOT-INF/classes/demo/Application.class
  BOOT-INF/classes/demo/VersionController.class
  BOOT-INF/lib/...
~~~

The `BOOT-INF/classes` path applies to the standard **Spring Boot executable JAR layout**. For an executable WAR, application classpath resources typically sit at `WEB-INF/classes/git.properties`. Merely seeing a file generated under `target/` without verifying it inside the archive is not proof that the runtime will receive Git metadata.

## 3. Choosing the right Maven plugin and understanding coordinate changes

### 3.1. Plugin used in this lesson

Use coordinates:

~~~text
groupId    : io.github.git-commit-id
artifactId : git-commit-id-maven-plugin
version    : 10.0.1
goal       : revision
~~~

This plugin extracts Git repository information and can write `git.properties`. The project documentation illustrates `<generateGitPropertiesFile>true</generateGitPropertiesFile>` along with `<generateGitPropertiesFilename>${project.build.outputDirectory}/git.properties</generateGitPropertiesFilename>`.

Version 10.x requires Maven `3.9+` (and a sufficiently recent Java version for the plugin); Java 17 in this example satisfies the Java requirement. If your project uses an older Maven version, check the compatibility matrix and release notes to pick an **appropriate plugin version** or upgrade Maven/Wrapper deliberately instead of copying this version blindly.

### 3.2. What if you encounter the older plugin coordinates?

You may run into earlier coordinates such as:

~~~xml
<groupId>pl.project13.maven</groupId>
<artifactId>git-commit-id-plugin</artifactId>
~~~

This was the previous group/artifact name used in older projects—not a separate plugin to install alongside the new one out of habit. If both appear in the effective POM, determine which execution is active so two executions do not overwrite `git.properties` unpredictably.

Modern versions of Spring Boot's `spring-boot-starter-parent` also provide managed plugin configuration. Spring Boot docs show you can simply **declare the plugin** when using the parent; in this example we specify version and configuration explicitly to make field filtering clear. **Do not add two duplicate `revision` executions** if the parent already configures an execution; inspect `mvn help:effective-pom` when using complex parents or profiles.

### 3.3. Why not just run git manually and append to a file?

You could write a script calling `git rev-parse HEAD`, but that script would have to handle shell quoting, detached HEAD, working trees, shallow clones, Windows vs. POSIX differences, encoding, missing repositories, and output resource placement. A dedicated plugin integrates directly into the Maven lifecycle and properties generation. Using a plugin minimizes custom code, **though it does not eliminate** verifying the final Git metadata and handling CI/environment edge cases.

## 4. Input requirement: build from a Git repository with a commit

For the plugin to generate meaningful metadata, build from a **Git working tree with a commit** whose metadata the plugin version can read. With only source files and no `.git`, the plugin cannot determine a trustworthy SHA on its own.

In a repo that already has commits:

~~~bash
git rev-parse HEAD
git status --short
git branch --show-current
mvn -version
java -version
~~~

Explanation:

- `git rev-parse HEAD` prints the **currently checked-out commit**, serving as the reference value to compare with `git.commit.id`.
- `git status --short` lists tracked/untracked changes; releases needing full traceability should verify a clean working tree or report all uncommitted edits clearly.
- `git branch --show-current` may print nothing under detached HEAD — completely normal in CI.
- `mvn -version` displays the Maven version and the JVM Maven is running on.
- `java -version` shows the terminal's Java; if multiple JDKs exist, verify the Maven JVM/toolchains too.

If you create a brand-new source folder without running `git init` and `git commit`, no valid commit ID exists to generate. In the standalone exercise in Section 5, **create a commit first** before running the Maven build.

**Note on worktrees/submodules:** `.git` can be a **file pointing to the actual Git directory** rather than a subdirectory. Avoid blindly hardcoding `${project.basedir}/.git` when modules or worktrees use different layouts; let the plugin locate Git metadata via its built-in resolution and verify in the real environment.

## 5. Complete example: Maven + Spring Boot + git.properties

This example is a small Spring Boot HTTP application. Learners will create a Git commit, build an executable JAR, inspect the Git file inside the artifact, and call an endpoint returning the commit.

### 5.1. Structure

~~~text
commit-trace-demo/
  pom.xml
  VerifyGitProperties.java
  src/
    main/
      java/
        demo/
          Application.java
          VersionController.java
      resources/
        application.properties
~~~

After running `git init`/`git commit`, Git repository metadata will also be present. `VerifyGitProperties.java` sits at the **project root** as a standalone QA utility run via the Java 17 source-file launcher and is not compiled into the Spring Boot JAR.

### 5.2. Complete pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example.learning</groupId>
    <artifactId>commit-trace-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>io.github.git-commit-id</groupId>
                <artifactId>git-commit-id-maven-plugin</artifactId>
                <version>10.0.1</version>
                <configuration>
                    <generateGitPropertiesFile>true</generateGitPropertiesFile>
                    <generateGitPropertiesFilename>${project.build.outputDirectory}/git.properties</generateGitPropertiesFilename>
                    <commitIdGenerationMode>flat</commitIdGenerationMode>
                    <includeOnlyProperties>
                        <includeOnlyProperty>^git.commit.id$</includeOnlyProperty>
                        <includeOnlyProperty>^git.commit.id.abbrev$</includeOnlyProperty>
                        <includeOnlyProperty>^git.commit.time$</includeOnlyProperty>
                        <includeOnlyProperty>^git.branch$</includeOnlyProperty>
                    </includeOnlyProperties>
                    <failOnNoGitDirectory>true</failOnNoGitDirectory>
                    <failOnUnableToExtractRepoInfo>true</failOnUnableToExtractRepoInfo>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Why is this configuration meaningful?**

- `spring-boot-starter-parent` manages Spring Boot dependency/plugin versions and pre-configures the Git Commit Id Plugin. Declaring the plugin in `<build><plugins>` uses the `revision` configuration inherited from the parent; **you do not necessarily need to add an explicit execution manually** in a POM with this parent.
- `<version>10.0.1</version>` pins a specific plugin version for Maven 3.9+/Java 17. On systems with older Maven, adjust the plugin and parent per compatibility requirements.
- `generateGitPropertiesFile=true` makes the plugin **write the file** rather than only creating Maven project properties for resource filtering.
- `generateGitPropertiesFilename` points to the **classpath output root** `target/classes/git.properties`, so Spring Boot can auto-discover it via `classpath:/git.properties`.
- `commitIdGenerationMode=flat` emits the key `git.commit.id` (instead of `git.commit.id.full`). In this plugin, the `full` option changes the key name to `git.commit.id.full` to support nested JSON structures; `flat` does **not** mean keeping only the short SHA. For `GitProperties.getCommitId()` in this example, we want the explicit `git.commit.id` key.
- `includeOnlyProperties` is a list of **regexes for property names**, restricting output. This control prevents accidentally embedding emails, remote URLs, commit messages, or usernames. `^` and `$` anchor exact key matching.
- `failOnNoGitDirectory`/`failOnUnableToExtractRepoInfo` are set to `true` so a release build **cannot silently ship a JAR missing Git metadata**. If a pipeline builds from a source archive without `.git`, design another trusted commit identity source and verify it instead of silently disabling failure checks.
- `spring-boot-maven-plugin` together with the Boot parent packages the executable JAR in the `package` phase. The Git file is generated before packaging so it lands in `BOOT-INF/classes`.

**Note on parent vs. no-parent:** If a POM does not inherit `spring-boot-starter-parent`, you must explicitly configure the `initialize` phase/`revision` goal for the Git plugin as well as the `repackage` goal of the Spring Boot plugin. That standalone snippet is shown in Section 9.

### 5.3. Application.java

Create `src/main/java/demo/Application.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

This is a valid main class for a Spring MVC/Spring Boot application.

### 5.4. VersionController.java

Create `src/main/java/demo/VersionController.java`:

~~~java
package demo;

import org.springframework.boot.info.GitProperties;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VersionController {

    private final GitProperties gitProperties;

    public VersionController(GitProperties gitProperties) {
        this.gitProperties = gitProperties;
    }

    @GetMapping(value = "/version",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String version() {
        String commit = gitProperties.getCommitId();
        if (commit == null || commit.isBlank()) {
            throw new IllegalStateException(
                    "git.commit.id was not packaged");
        }
        return "git.commit.id=" + commit + "\n";
    }
}
~~~

The `GitProperties` bean is auto-configured by Spring Boot when `git.properties` is present at the **classpath root** and matching auto-configuration applies. Because the controller requires constructor injection, **if the `GitProperties` bean is missing, the application fails to start** — an intentional fail-fast choice for this demo.

`getCommitId()` returns the commit ID from metadata; there is no need to invoke Git inside the deployed app. Runtime containers/images **do not need `.git`** once `git.properties` is packaged at build time.

The example `/version` endpoint returns only the SHA to avoid exposing unnecessary details. The response is **one line**, e.g.:

~~~text
git.commit.id=<actual commit SHA of the checkout>
~~~

The part inside `<...>` is a descriptive placeholder, not literal stdout. The exact value depends on the repository and can be confirmed with `git rev-parse HEAD`. Never invent a fake SHA and present it as verified output.

### 5.5. application.properties

Create `src/main/resources/application.properties`:

~~~properties
management.endpoints.web.exposure.include=health,info
management.info.git.enabled=true
server.address=127.0.0.1
server.port=8085
~~~

Explanation:

- `management.endpoints.web.exposure.include=health,info` widens Actuator HTTP exposure so `/actuator/info` can be called in the demo environment. By default, Actuator typically exposes only `health` over web.
- `management.info.git.enabled=true` enables the Git info contributor; when `git.properties` is at the right path, Boot exposes metadata.
- `server.address=127.0.0.1` binds the demo app to loopback to avoid exposing endpoints externally.
- `server.port=8085` reduces port conflicts with other servers on 8080; if the port is busy, pass `--server.port=...` when running.

For production, **do not conclude that Actuator `info` should always be public**. Enabling exposure must go hand in hand with network policies, authentication/authorization, and an assessment of exposed data.

## 6. Creating a Git commit and building the executable JAR

### 6.1. If the exercise directory is not yet a Git repository

From the root containing `pom.xml` and the created files:

~~~bash
git init
git add pom.xml src/main/java/demo/Application.java src/main/java/demo/VersionController.java src/main/resources/application.properties
git -c user.name="Demo Author" -c user.email="demo@example.invalid" commit -m "Add Git metadata demo"
~~~

`git init` creates the repository. `git add` stages only the **necessary files**, avoiding `target/` or secrets. `git -c user.name=... -c user.email=... commit` sets an identity solely for the demo commit without altering global Git configuration; `example.invalid` is a reserved documentation domain.

If the directory already has Git history, **do not re-run `git init`/commit just for the exercise**. Simply confirm `git rev-parse HEAD` points to the revision you intend to release and that the working tree is clean per policy.

### 6.2. Confirming inputs

~~~bash
git rev-parse HEAD
git status --short
mvn -version
~~~

In a freshly committed exercise directory, `git status --short` normally prints nothing if the working tree is clean. `git rev-parse HEAD` outputs a repo-specific commit hash that **cannot be predetermined**. `mvn -version` should report a Maven version compatible with plugin 10.0.1 and a Java version compatible with Spring Boot 3.5.

### 6.3. Build

~~~bash
mvn clean package
~~~

Key outputs to verify:

~~~text
target/classes/git.properties
target/commit-trace-demo-1.0.0.jar
~~~

`target/classes/git.properties` shows the plugin generated metadata on the output classpath. `target/commit-trace-demo-1.0.0.jar` is the executable archive built by the Boot plugin in the `package` lifecycle. If Maven Wrapper is configured in the repo, use `./mvnw clean package` on Linux/macOS or `.\mvnw.cmd clean package` in PowerShell; the Wrapper should also pin a compatible Maven version.

You can inspect the Git file in the build output:

~~~bash
cat target/classes/git.properties
~~~

In PowerShell:

~~~powershell
Get-Content .\target\classes\git.properties
~~~

**Do not expect keys to appear in any fixed order**; Java Properties makes no guarantee about ordering for business semantics. Verify the field names and commit value rather than comparing text line-by-line by order.

## 7. Verifying git.properties is actually inside the executable JAR

Seeing `target/classes/git.properties` alone is not enough, because packaging or exclusion rules can still omit the file from the final JAR. Verify with the JDK:

~~~bash
jar tf target/commit-trace-demo-1.0.0.jar
~~~

The Spring Boot JAR archive entry list should include:

~~~text
BOOT-INF/classes/git.properties
BOOT-INF/classes/demo/Application.class
BOOT-INF/classes/demo/VersionController.class
BOOT-INF/lib/...
~~~

The list above is an **abbreviated illustration**, not verbatim `jar tf` output. `git.properties` sits on the application classpath inside Boot's nested archive. It is a **build-time packaged file**, not something regenerated from Git at runtime.

### 7.1. Standalone Java 17 validator and deterministic output

Create `VerifyGitProperties.java` at the project root:

~~~java
import java.io.InputStream;
import java.nio.file.Path;
import java.util.Properties;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

public class VerifyGitProperties {

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java VerifyGitProperties.java "
                    + "<jar-path> <expected-commit>");
        }

        Path path = Path.of(args[0]);
        String expected = args[1].trim();
        String entryName =
                "BOOT-INF/classes/git.properties";

        try (ZipFile zip = new ZipFile(path.toFile())) {
            ZipEntry entry = zip.getEntry(entryName);
            if (entry == null) {
                throw new IllegalStateException(
                        "Missing JAR entry: " + entryName);
            }

            Properties properties = new Properties();
            try (InputStream in = zip.getInputStream(entry)) {
                properties.load(in);
            }

            String actual = properties.getProperty(
                    "git.commit.id");
            if (actual == null || actual.isBlank()) {
                throw new IllegalStateException(
                        "git.commit.id is missing");
            }
            if (!expected.equals(actual)) {
                throw new IllegalStateException(
                        "Commit mismatch: expected=" + expected
                                + ", actual=" + actual);
            }

            System.out.println(
                    "git.properties.present=true");
            System.out.println(
                    "git.commit.id.matches=true");
        }
    }
}
~~~

This program uses only the **Java Standard Library**, with no Spring imports. It reads the ZIP entry `BOOT-INF/classes/git.properties` directly from the **packaged JAR file** and compares `git.commit.id` against the supplied commit. If the file is missing, the property is missing, or the SHA mismatches, it throws an exception and the Java launcher exits non-zero.

Run on Linux/macOS or a POSIX shell:

~~~bash
java VerifyGitProperties.java \
  target/commit-trace-demo-1.0.0.jar \
  "$(git rev-parse HEAD)"
~~~

You can write this on **one line** if your shell does not support `\` line continuations. On Windows PowerShell:

~~~powershell
$commit = (git rev-parse HEAD).Trim()
java VerifyGitProperties.java .\target\commit-trace-demo-1.0.0.jar $commit
~~~

With the **correct file and matching commit**, exact stdout is:

~~~text
git.properties.present=true
git.commit.id.matches=true
~~~

These two lines contain no specific SHA, so the output is deterministic before knowing the commit. If the SHA differs, the validator FAILS and prints expected vs. actual so you can trace wrong files, Git checkouts, plugin settings, or stale artifacts.

**Key point:** compare `git.commit.id` inside the JAR against Git `HEAD` at build checkout. Never just check that `git.properties` "exists," because a stale metadata file can be copied into the archive and corrupt all traceability.

### 7.2. If the target is a WAR instead of a JAR

In a Spring Boot executable WAR, application resources typically live at `WEB-INF/classes/git.properties` rather than `BOOT-INF/classes/git.properties`. Update `entryName` accordingly in the validator while keeping the commit comparison logic. External servlet containers also read `git.properties` from the application classpath, though WAR startup mechanics differ from an executable JAR.

Never write a validator that checks `target/classes` and then automatically reports PASS for the final WAR/JAR; always verify the **exact artifact that will be released**.

## 8. Runtime verification: /version and /actuator/info

### 8.1. Running the executable JAR

From the project root:

~~~bash
java -jar target/commit-trace-demo-1.0.0.jar
~~~

The app listens on port 8085 and binds to loopback per the demo config. Once Spring Boot finishes starting, call from another terminal:

~~~bash
curl -fsS http://127.0.0.1:8085/version
curl -fsS http://127.0.0.1:8085/actuator/info
~~~

For `/version`, the body looks like:

~~~text
git.commit.id=<full Git commit ID>
~~~

The value in `<...>` **varies by repository**, so it is an illustrative placeholder rather than literal stdout. Compare it with `git rev-parse HEAD` from the build checkout. When done testing, stop the Java process in the first terminal.

### 8.2. Actuator Git information

Spring Boot Actuator provides `GitInfoContributor`, auto-configured from the `GitProperties` bean. When `git.properties` is at the classpath root, `management.info.git.enabled=true`, and the `info` endpoint is exposed over HTTP, `GET /actuator/info` includes a `git` branch with allowed properties.

With the file in Section 5, the response can include `branch`, `commit.id`, and `commit.time`. **Do not hardcode a verbatim JSON response**: SHA, branch, and time are real data, and serialization/exposure depend on the Spring Boot version and configuration.

Per Spring Boot docs, the default Git contributor exposes only a compact subset such as `git.branch`, `git.commit.id`, and `git.commit.time` when present. Setting:

~~~properties
management.info.git.mode=full
~~~

exposes all properties in `git.properties`, but **should not be enabled by habit** because full metadata may include emails, hostnames, remote URLs, or commit messages. This lesson's example already allowlists fields in the plugin to avoid sensitive data.

**Having Actuator in Spring Boot does not mean `info` is exposed over the web by default.** Check `management.endpoints.web.exposure.include=health,info` and security/access policies. If the endpoint returns `404`, `401`, or `403`, the issue may be exposure or security rather than a missing Git file.

### 8.3. Reading GitProperties directly in application code

When the `GitProperties` bean exists, application code can call:

~~~java
String revision = gitProperties.getCommitId();
String shortRevision = gitProperties.getShortCommitId();
String branch = gitProperties.getBranch();
java.time.Instant commitTime = gitProperties.getCommitTime();
~~~

This is a **snippet inside a bean/controller with `gitProperties` injected**, like `VersionController`, not a standalone Java file. Getters may return `null` if the corresponding property is absent; application logic or logging should handle missing data per policy.

`getCommitTime()` parses the commit timestamp into an `Instant` when formatted properly; if a file uses an unusual time format, check plugin `dateFormat`/`dateFormatTimeZone` and Spring Boot's parser. Spring Boot docs recommend supported ISO-8601 timestamp formats. **Do not confuse commit time with deployment time**.

## 9. Maven lifecycle: why must the file be generated before packaging?

The lab relies on the Spring Boot starter parent, which already configures the plugin. Logically, the desired order is:

~~~text
Git metadata available in build workspace
        |
        v
Maven initialize: Git revision information
        |
        v
git.properties generated into target/classes
        |
        v
Maven compile/resources/package
        |
        v
Spring Boot repackage executable JAR
        |
        v
BOOT-INF/classes/git.properties
        |
        v
Runtime GitProperties + Actuator/info
~~~

If the plugin writes the file to `target/git.properties` without adding it as a resource, the JAR may miss it. If the plugin is bound **after** `package`, it runs too late to include metadata in that build's executable archive. If customizing the Maven lifecycle heavily, inspect the effective plugin execution order.

### 9.1. No-parent POM: explicit execution

If you do **not** use `spring-boot-starter-parent`, configure the goal/phase explicitly. This is a **Maven plugin fragment** (not a complete POM):

~~~xml
<plugin>
    <groupId>io.github.git-commit-id</groupId>
    <artifactId>git-commit-id-maven-plugin</artifactId>
    <version>10.0.1</version>
    <executions>
        <execution>
            <id>git-revision</id>
            <phase>initialize</phase>
            <goals>
                <goal>revision</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <generateGitPropertiesFile>true</generateGitPropertiesFile>
        <generateGitPropertiesFilename>${project.build.outputDirectory}/git.properties</generateGitPropertiesFilename>
        <commitIdGenerationMode>flat</commitIdGenerationMode>
    </configuration>
</plugin>
~~~

You will also need to manage versions/dependencies, compiler, resources, and the `spring-boot:repackage` goal in a no-parent project. Do not copy this fragment into the sample POM **if an equivalent execution is already supplied by the parent**, as it can trigger two executions or unpredictable output. For multi-module builds, see Section 11.

### 9.2. Keep the feature clean without manual text filtering

You **do not need** to place a `git.properties` template in `src/main/resources` and enable `<filtering>true</filtering>` across resources. The plugin can **generate the file itself** directly into the output classpath. Mixing automatic generation with resource filtering can overwrite the file, cause inconsistent SHAs, or accidentally substitute placeholders in files that should not be filtered.

If a project already has a manual `src/main/resources/git.properties`, remove it or establish a **single source of truth** to avoid two files competing for the same path in the output archive.

## 10. CI requirements: is Git metadata real and matching the commit?

A trustworthy release build should verify:

1. Check out the exact commit requested by CI (not just a branch name).
2. Repository metadata `.git` or a trusted provenance source is accessible during file generation.
3. `git status --porcelain` is clean if policy requires building from committed source; untracked files must be evaluated per policy.
4. Maven actually runs the plugin's `revision` goal before packaging.
5. `git.properties` is created on the output classpath and enters the right JAR/WAR.
6. The commit in the **final archive** matches `git rev-parse HEAD` of the build checkout.
7. The runtime service reads the right commit from the JAR; with multiple pods, check each instance or release identity.
8. The pipeline publishes the **exact same artifact** that was verified, without rebuilding or copying a different file after checks.

Example POSIX CI script at project root:

~~~bash
set -eu

commit=$(git rev-parse HEAD)
status=$(git status --porcelain)

if [ -n "$status" ]; then
  echo "Working tree is not clean" >&2
  exit 1
fi

mvn -B -ntp clean package

java VerifyGitProperties.java \
  target/commit-trace-demo-1.0.0.jar \
  "$commit"
~~~

This script illustrates fail-fast checks on a CI system that **already has Git, Maven 3.9+, Java 17, and full source files checked out**. `git status --porcelain` also catches unignored untracked files; if the project generates untracked files prior to the status check, enforce this check at the appropriate step.

**Do not use `git branch --show-current` as a release identifier.** CI often checks out a detached HEAD so the branch name may be empty. `git rev-parse HEAD` is the value to compare for commit traceability, paired with repo URL and CI source provenance. `git.branch` is supplementary metadata that can be absent or vary across environments.

### 10.1. Shallow clones and detached HEAD

Many CI systems check out with `depth=1` for speed. As long as the Git object for `HEAD` is present, the plugin can still extract the commit ID; however, features relying on history/tags (`git describe`, closest tag, commit count, branch inference) may lack data. When using those features, choose an appropriate checkout depth and tags rather than silently accepting incomplete metadata.

Under detached HEAD, do not assume a branch `HEAD` means uncommitted code. The SHA itself is the stable identifier. Two builds from the **same SHA** on different refs/branches may record different `git.branch` values, so branch metadata can also prevent artifacts from being **byte-for-byte identical** across builds. When strict reproducibility is the goal, consider embedding only revision-invariant fields like full commit ID and commit time, keeping branch/deploy environment in external provenance.

### 10.2. Building from a source archive without .git

A multi-stage Docker build might `COPY src pom.xml` into the builder without copying `.git`. The plugin cannot extract Git revision without Git metadata. **Do not copy the entire `.git` directory into the final runtime image** to work around this.

Sensible options:

- Run Maven packaging in the CI workspace where Git metadata exists, then copy **only the built JAR** into the runtime image.
- If building in an isolated context without `.git`, pass the SHA from the trusted CI system and **generate the properties file through a verified process**, never treating unverified user-supplied arguments as commit proof.
- Only allow builds without Git metadata in clearly defined development profiles; release pipelines should fail when provenance is missing.

Do not set `failOnNoGitDirectory=false` across all environments and conclude "the plugin succeeded" when the output lacks a SHA, because the entire purpose here is **commit traceability**.

### 10.3. Dirty working tree is a provenance trap

`git.commit.id` describes the `HEAD` commit; it **does not prove** all files used in the build match that commit. If the source tree contains uncommitted edits, the JAR may run code different from `HEAD` even though `git.properties` records `HEAD`'s SHA.

For releases, enforce `git status --porcelain` or build from a clean checkout per policy; `git.dirty` can be added as a CI-internal field, but never treat it as a complete substitute for source integrity or artifact hashes. Keep commit SHA, artifact checksum, and CI build identifier to link all pieces of evidence.

## 11. Multi-module Maven: repo commit vs. per-service metadata

In a multi-module monorepo:

~~~text
platform/
  pom.xml
  .git/
  common/
    pom.xml
  service-a/
    pom.xml
  service-b/
    pom.xml
~~~

If the plugin runs on the aggregator/parent module and only generates `git.properties` in `platform/target/classes`, that file **will not automatically appear** inside the executable JARs of `service-a` or `service-b`. Output paths are relative to the **active project**; determine which modules need metadata and which executions are running.

How to check:

~~~bash
mvn -pl service-a -am clean package
jar tf service-a/target/service-a-1.0.0.jar
~~~

This artifact name is illustrative if `service-a` uses `artifactId=service-a`, `version=1.0.0`, and Boot repackage. Look for `BOOT-INF/classes/git.properties` inside **`service-a`'s JAR**, not only in `common/target` or `platform/target`.

A Git repository typically has one shared `HEAD` across the monorepo, though builds with nested Git repositories/submodules/worktrees can have different source revisions per module. Avoid inferring from branch names and do not force the plugin to run on POM-only modules that produce no runtime artifact. Check `skipPoms` or per-module execution settings for your plugin version and adopt a consistent design.

**Do not** make every module publish its own `git.properties` inside shared libraries so nested JARs collide on the classpath. Each executable application should have one clear metadata source at the classpath root of **the application module itself**, sharing a Git revision only when source scope actually aligns.

## 12. Security and data that should not be embedded

Git metadata aids diagnostics, but without content filtering, a plugin can emit:

- `git.commit.user.email` or author names.
- `git.remote.origin.url`, which can expose internal hosts or private repository paths.
- `git.commit.message.full`, which can contain internal issue details or sensitive notes.
- `git.build.user.name`, hostnames, build paths, or CI worker details.
- Tags, internal branch names, release directories, dirty state, or other business specifics.

**Two separate leak surfaces:**

1. **Artifact JAR**: anyone given the file can open `BOOT-INF/classes/git.properties`, regardless of whether Actuator is disabled.
2. **HTTP endpoints**: if `/actuator/info` or a custom endpoint is public, allowed properties can be fetched over the network.

Therefore, control data **at generation time** with `includeOnlyProperties`, and also control **endpoint exposure** via Actuator/Spring Security/network policies. Do not set `management.info.git.mode=full` if the metadata file contains fields clients should not see. Likewise, do not have custom endpoints dump all `Properties` solely for debugging convenience.

**A commit SHA is generally not a secret** like a password, but it can help fingerprint versions, link to non-public repositories, or reveal deployment cadence. Exposure policies still depend on the app/environment. Consider exposing commit IDs only on internal endpoints or controlled logs.

If sensitive metadata is accidentally embedded in a distributed artifact, disabling the HTTP endpoint alone **does not** remove that data from the already-released JAR. Fix the allowlist, rebuild, and handle the exposed artifact per security incident procedures.

## 13. git.properties and reproducible builds

Generating Git metadata affects JAR bytes. If properties include the **current build time**, machine name, or an unstable branch name, two builds of the same commit will produce different bytes. This matters for **byte-for-byte reproducible JARs**.

Distinguish:

| Metadata type | Stable per commit? | Recommendation when reproducibility is needed |
| --- | --- | --- |
| Full commit ID | Yes, for the same Git object ID | Keep |
| Commit time | Yes, in commit object metadata | Keep if format/timezone are fixed |
| Commit author | Yes, in commit, though may contain PII | Keep only if policy allows |
| Current branch | Not guaranteed: detached HEAD, multiple branches can share one SHA | Do not treat as commit-invariant |
| `git.build.time` | No, if using wall-clock time | Omit or replace with deterministic value |
| Build host/user | Unstable across machines | Omit from artifact |
| `git.dirty` | Varies with working tree | Enforce clean builds; consider omitting field |

Maven offers `project.build.outputTimestamp` to reduce non-determinism in archive entry timestamps; **it does not automatically turn `git.build.time` into commit time** nor control every plugin's metadata. For two JARs to have identical bytes, you must also lock JDK, dependencies, Maven plugins, ZIP ordering, encoding, resources, and generated inputs.

You can add a deterministic archive timestamp:

~~~xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

This illustrative fragment must be **merged into existing `<properties>`** using a stable milestone per release policy, rather than copying one fixed date forever across all releases. If using Source Date Epoch / commit timestamps, verify your build plugins actually support that mechanism.

A strong verification pipeline tracks two identifiers:

~~~text
Source revision: git.commit.id from the JAR
Artifact bytes : SHA-256 of the tested/published JAR
~~~

They complement each other. **Matching source SHAs do not guarantee identical JAR bytes**, and **matching JAR checksums** do not prove an application is secure or free of vulnerable dependencies. The Git plugin does not replace code signing, provenance attestations, or SBOMs.

## 14. Gradle equivalent: do not put a Maven plugin into Gradle

For Spring Boot builds using Gradle, do not add `git-commit-id-maven-plugin` to `build.gradle`. Per Spring Boot docs, a Gradle equivalent is `com.gorylenko.gradle-git-properties`, e.g. Groovy DSL fragment:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'com.gorylenko.gradle-git-properties' version '2.4.1'
}
~~~

This is an **illustrative plugin block**, not a complete Gradle project. A web project also needs dependencies, repositories, and Gradle/Java versions supported by the Spring Boot plugin. You can configure exported properties per the Gradle plugin's docs; do not assume it uses the **same XML parameter names** as Maven.

After a Gradle build, check `git.properties` in classpath outputs and specifically **inside `BOOT-INF/classes/git.properties` of `bootJar`**. On the Spring Boot side, `GitProperties`/Actuator `info` still depend on filename and classpath location; they do not require Maven at runtime.

Similarly, `springBoot { buildInfo() }` in Gradle generates `build-info.properties`, which is **distinct** from the Git file. If both are needed, configure and verify both resources independently. Never substitute `build-info` for Git revision.

## 15. Common failure cases and troubleshooting

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Maven reports Git directory not found | Built from source archive/Docker context without `.git`; different Git path | Use a checkout with Git metadata or a verified trusted SHA source |
| Plugin did not run during `package` | Declared only in `pluginManagement`; execution/parent not active | Check `mvn help:effective-pom`, `mvn -X` if needed, and plugin execution logs |
| `target/classes/git.properties` missing | `generateGitPropertiesFile` disabled, wrong output path, or lifecycle goal skipped | Check POM, plugin logs, and exact filename |
| JAR lacks `BOOT-INF/classes/git.properties` | File written outside output classpath, excluded by packaging, wrong JAR checked | `jar tf` on the exact executable archive |
| Spring Boot reports missing `GitProperties` bean | File not at **classpath root**, plugin did not run, or app ran wrong artifact | Check JAR entry, startup logs, and auto-configuration |
| `/actuator/info` returns 404 | Endpoint not exposed, different path, or missing Actuator starter | `management.endpoints.web.exposure.include`, dependencies, base path |
| `/actuator/info` returns 401/403 | Spring Security/endpoint access policy blocking | Check authorization before touching the Git plugin |
| `/actuator/info` returns `{}` | InfoContributor disabled or missing matching metadata | Check `git.properties`, `management.info.git.enabled`, and output |
| `git.commit.id` is null | Plugin emitted `git.commit.id.full` in `full` mode, filtered out, or wrong file | Use `commitIdGenerationMode=flat` for `git.commit.id` and inspect file content |
| Commit in JAR does not match `HEAD` | Artifact from another build, stale plugin/file, or checkout moved after package | Compare file paths, `git rev-parse HEAD` at build, and archived SHA |
| Local has branch, CI lacks branch | Detached HEAD or shallow fetch | Treat commit ID as primary identifier; do not require branch in CI |
| Git metadata differs for same commit | Build time, branch, dirty state, or timezone/format changed | Allowlist stable fields and apply a reproducibility policy |
| Short SHA caused release confusion | Used `git.commit.id.abbrev` when matching | Use full `git.commit.id` in CI |
| Multi-module only puts Git file in parent | Plugin ran on wrong module/output folder | Check the target service JAR, execution, and output path |
| JAR contains sensitive metadata | Plugin generated too many fields | Tighten `includeOnlyProperties`, rebuild, and assess exposure risk |
| Running `git rev-parse HEAD` inside runtime container fails | Runtime image lacks `.git` or Git binary | Read build-generated `git.properties`; never run Git at runtime |

When investigating, follow this sequence: **Git source state → Maven plugin execution → `target/classes/git.properties` → executable JAR entry → runtime `GitProperties`/Actuator → deployed file identity**. This isolates which stage failed instead of changing configs blindly.

## 16. Acceptance procedure and self-check questions

### 16.1. Pre-release checklist

- [ ] Build runs from a verified commit/repository; working tree is clean per policy.
- [ ] Maven/Java/plugin versions are compatible and deliberately managed.
- [ ] The Git plugin actually **executes**, not merely declared in `pluginManagement`.
- [ ] The plugin writes `git.properties` at the output classpath root.
- [ ] The plugin exports only needed fields; no remote URLs/emails/secrets enter the artifact.
- [ ] `git.commit.id` holds the full SHA and matches `git rev-parse HEAD` of the build checkout.
- [ ] Final archive contains `BOOT-INF/classes/git.properties` (or `WEB-INF/classes` for WAR).
- [ ] Java validator runs against the **exact JAR to be released** and returns `git.commit.id.matches=true`.
- [ ] Runtime reads `GitProperties`, and `/version` operates under the security policy.
- [ ] Actuator `info` is exposed only when needed, with appropriate access controls.
- [ ] CI detached HEAD/shallow clones are handled properly; branch is not treated as immutable identity.
- [ ] Release records store both commit SHA **and artifact SHA-256**, without conflating them.
- [ ] Publish the exact verified artifact rather than rebuilding in another workspace and silently deploying that.

### 16.2. Self-check

**Question 1.** Why use a plugin if you just want to see `HEAD`'s SHA during the build?

**Answer:** You can run Git manually, but the plugin integrates with the Maven lifecycle, writes the properties file to the exact output classpath, and works seamlessly with Spring Boot auto-configuration. You still must verify the final artifact.

**Question 2.** Is putting `git.properties` into `target/` enough for Spring Boot to read it?

**Answer:** Not yet. The file must be at the **classpath root** of the app, e.g. `target/classes/git.properties` and `BOOT-INF/classes/git.properties` inside the executable JAR.

**Question 3.** Why might plugin `full` mode make `git.commit.id` missing?

**Answer:** `commitIdGenerationMode=full` outputs `git.commit.id.full` instead of `git.commit.id` from `flat` mode. Configuration, code, and allowlists must stay aligned.

**Question 4.** `git.commit.id` in the JAR matches `HEAD`, yet the source had uncommitted changes. Can we conclude the artifact matches the commit?

**Answer:** No. The SHA only reflects `HEAD`; the build contents can include uncommitted edits. Releases require clean checkouts and artifact byte evidence.

**Question 5.** If CI builds a detached HEAD and `git.branch` is empty or differs from local, was the wrong commit built?

**Answer:** No. Detached HEAD has no conventional branch checked out. Compare the full `git.commit.id` against the expected SHA; branch is supplementary metadata.

**Question 6.** Should `management.info.git.mode=full` be enabled on a public endpoint?

**Answer:** Generally no by default. The file can contain remote URLs, emails, commit messages, and hostnames. Restrict data at generation time and control endpoint exposure/security.

**Question 7.** Are two JARs containing the same `git.commit.id` guaranteed to be byte-identical?

**Answer:** No. ZIP timestamps, generated resources, dependency contents, build tools, or differing environments can produce different files. Compare SHA-256 checksums of **both artifacts** if byte identity is required.

## 17. Official documentation

- Spring Boot 3.5 — How-to Build: Generate Git Information: https://docs.spring.io/spring-boot/3.5/how-to/build.html
- Spring Boot 3.5 — Actuator Endpoints and Git Commit Information: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Spring Boot 3.5.16 — GitProperties API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/info/GitProperties.html
- Git Commit Id Maven Plugin — Repository, setup, minimum requirements: https://github.com/git-commit-id/git-commit-id-maven-plugin
- Git Commit Id Maven Plugin — Configuration and Properties: https://github.com/git-commit-id/git-commit-id-maven-plugin/blob/master/docs/configuration-and-properties.md
- Git Commit Id Maven Plugin — Releases (including 10.0.1 and breaking changes): https://github.com/git-commit-id/git-commit-id-maven-plugin/releases
- Maven Central — Git Commit Id Maven Plugin 10.0.1: https://central.sonatype.com/artifact/io.github.git-commit-id/git-commit-id-maven-plugin/10.0.1
- Spring Boot Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Java 17 — ZipFile API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html
- Git — rev-parse manual: https://git-scm.com/docs/git-rev-parse
- Git — status manual: https://git-scm.com/docs/git-status

**Remember:** The plugin must generate `git.properties` at the **classpath root** at build time before Spring Boot can consume `GitProperties` at runtime. For reliable commit traceability, verify the **full Git commit ID inside the executable JAR against `HEAD` of the build checkout**, export only necessary metadata, record the artifact checksum alongside it, and protect `/actuator/info` according to environment policy.