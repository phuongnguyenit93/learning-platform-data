# Managing Release Versions, SNAPSHOTs, and Classifiers When Publishing Spring Boot/Maven

## 1. The Problem: Same Application Name, Which Artifact Is Actually Released?

In Spring Boot, saying "version 1.4.0 has been deployed" is not enough to trace the artifact. A single Maven module can produce:

- `release-demo-1.4.0.jar`: plain JAR, used as the **main artifact** in the dependency graph.
- `release-demo-1.4.0-exec.jar`: JAR repackaged by Spring Boot, containing the loader and nested dependencies to run `java -jar`.
- `release-demo-1.4.0-sources.jar` and `release-demo-1.4.0-javadoc.jar`: supplementary artifacts.
- `release-demo-1.5.0-SNAPSHOT-exec.jar`: local artifact name during development; when deployed to a snapshot repository, the remote file may carry a timestamp/build number.
- An OCI image containing the executable JAR, with an **image digest** completely different from Maven coordinates and JAR SHA-256.

If a pipeline picks the plain JAR by mistake, running `java -jar` can fail. If a project consumes a Spring Boot executable JAR as a library, the classpath usually cannot see application classes located under `BOOT-INF/classes`. If staging uses a SNAPSHOT and production also references a SNAPSHOT, the same logical version can resolve to new bytes at different times.

This lesson belongs to **Artifact Publication** under **Spring Boot Build Tooling Packaging**. After this lesson, you will know how to:

1. Read Maven GAV coordinates and `type`/`extension`/`classifier` modifiers accurately.
2. Distinguish `-SNAPSHOT` development versions from fixed releases, including timestamped snapshots in remote repositories.
3. Use `spring-boot-maven-plugin` to generate both a plain JAR and an executable JAR with classifier `exec` under the same Maven version.
4. Write and run a complete Java 17+/Spring Boot Maven application, inspecting both artifacts using the Java 17 standard library.
5. Understand the effects of `mvn package`, `mvn install`, `mvn deploy`, `distributionManagement`, and `settings.xml`.
6. Transition from a SNAPSHOT version to a committed/tagged release and move to the next SNAPSHOT via a controlled workflow.
7. Avoid publishing duplicate release versions, mixing repository policies, missing classifiers, or publishing artifacts that have not passed QA.
8. Design CI to record the Git revision, POM version, classifier, byte checksum, and repository coordinates of **every published file**.

**Demo setup:** Java `17`, Spring Boot `3.5.16`, compatible Maven, module `com.example.release:release-demo:1.4.0-SNAPSHOT`. Version `1.4.0-SNAPSHOT` is learning data only; do not infer from it that a real system currently has a 1.4.0 release. No production repository connection is required to practice the build and inspection steps.

## 2. Maven Coordinates: Version, Packaging, and Classifier Do Not Replace One Another

A Maven artifact is primarily identified by:

~~~text
groupId : artifactId : version
~~~

In practical artifact consumption, there are also **extension/type** and **classifier**. For the example:

~~~text
groupId    = com.example.release
artifactId = release-demo
version    = 1.4.0-SNAPSHOT
type       = jar
classifier = (none) or exec
~~~

Common fields:

| Component | Example | Meaning |
| --- | --- | --- |
| `groupId` | `com.example.release` | Organization/artifact group namespace |
| `artifactId` | `release-demo` | Module identifier within the group |
| `version` | `1.4.0` or `1.4.0-SNAPSHOT` | Logical version of the module |
| `packaging` | `jar`, `war`, `pom` | Maven lifecycle and default artifact type produced by the project |
| `extension` / dependency `type` | `jar`, `war`, `pom`, `zip`... | Artifact format or how Maven interprets the artifact in a dependency |
| `classifier` | `exec`, `sources`, `javadoc`, `tests`... | Artifact variant sharing the **same GAV** and corresponding extension/type |

**Key point:** a classifier is part of the artifact identity and **does not create a new version**. `release-demo:1.4.0:jar:exec` and the main `release-demo:1.4.0:jar` belong to the same logical release, yet are **two different files**. The `-exec` suffix in the filename represents the classifier, not part of `artifactId` or `version`.

In Maven dependency XML, these are two distinct requests:

~~~xml
<!-- Main JAR: no classifier -->
<dependency>
    <groupId>com.example.release</groupId>
    <artifactId>release-demo</artifactId>
    <version>1.4.0</version>
</dependency>
~~~

~~~xml
<!-- Explicit classifier, when a consumer ACTUALLY needs the exec variant -->
<dependency>
    <groupId>com.example.release</groupId>
    <artifactId>release-demo</artifactId>
    <version>1.4.0</version>
    <type>jar</type>
    <classifier>exec</classifier>
</dependency>
~~~

The second snippet demonstrates how to select an artifact with a classifier, **not a recommendation to use a Spring Boot executable JAR as a normal dependency**. Application classes inside an executable JAR live under `BOOT-INF/classes`, so dependent modules usually **cannot** load them via the standard classpath. When an API/library is needed, use a plain JAR or split out a library module.

### 2.1. Coordinate Formats in Tools and Repository Paths

In traditional Maven display syntax, you may see:

~~~text
groupId:artifactId:packaging:version
groupId:artifactId:packaging:classifier:version
~~~

Some tools use different notations or write `type` instead of `packaging`. Do not guess a CLI's `classifier`/`version` parameter order solely from filename format. For a POM, **dependency XML** is explicit, while the repository path is evidence of published artifacts.

Maven repository layout typically looks like:

~~~text
com/example/release/release-demo/1.4.0/
  release-demo-1.4.0.pom
  release-demo-1.4.0.jar
  release-demo-1.4.0-exec.jar
~~~

If sources/Javadoc are attached, the same version directory also holds `-sources.jar` and `-javadoc.jar`. This layout does not require changing `artifactId` or creating a separate version per classifier.

### 2.2. finalName Does Not Change Maven GAV

In `pom.xml`, `<build><finalName>service</finalName></build>` affects local filenames such as `target/service.jar` or `target/service-exec.jar`. It does **not** change `groupId:artifactId:version` in the repository upon install/deploy. If operators look only at filenames, it is very easy to misidentify the release.

Therefore, a release manifest should record **Maven GAV + classifier + extension + SHA-256 + Git revision**, not just `target/service.jar`.

## 3. SNAPSHOT: A Logical Version for Changing Builds

In Maven convention, the **` -SNAPSHOT `** suffix (no space in the POM) represents an **in-development version**, for example:

~~~xml
<version>1.4.0-SNAPSHOT</version>
~~~

Locally, after `mvn clean package`, the filenames are typically:

~~~text
target/release-demo-1.4.0-SNAPSHOT.jar
target/release-demo-1.4.0-SNAPSHOT-exec.jar
~~~

These two names reflect the **logical base version**. If the same version is deployed to a snapshot repository multiple times, the repository can store **timestamped unique snapshots** to distinguish publish runs:

~~~text
com/example/release/release-demo/1.4.0-SNAPSHOT/
  release-demo-1.4.0-20261109.031405-3.jar
  release-demo-1.4.0-20261109.031405-3-exec.jar
  release-demo-1.4.0-20261109.031405-3.pom
  maven-metadata.xml
~~~

`20261109.031405-3` is an **illustrative example**, not a timestamp generated by running this lesson. The `20261109.031405` part follows the UTC timestamp format `yyyyMMdd.HHmmss` and `3` is the build number managed by repository metadata. Do not manually enter that timestamp/build number into the project `<version>`; the logical version in the POM remains `1.4.0-SNAPSHOT`.

### 3.1. Maven Metadata Maps Logical SNAPSHOT to Actual Binary

In a remote snapshot repository's version directory, `maven-metadata.xml` may contain:

~~~xml
<metadata>
    <groupId>com.example.release</groupId>
    <artifactId>release-demo</artifactId>
    <version>1.4.0-SNAPSHOT</version>
    <versioning>
        <snapshot>
            <timestamp>20261109.031405</timestamp>
            <buildNumber>3</buildNumber>
        </snapshot>
        <snapshotVersions>
            <snapshotVersion>
                <extension>jar</extension>
                <value>1.4.0-20261109.031405-3</value>
            </snapshotVersion>
            <snapshotVersion>
                <classifier>exec</classifier>
                <extension>jar</extension>
                <value>1.4.0-20261109.031405-3</value>
            </snapshotVersion>
        </snapshotVersions>
    </versioning>
</metadata>
~~~

The fragment above is **abbreviated for learning**; real metadata also includes `updated`, `lastUpdated`, and elements matching the repository/plugin version. The core point: Maven can resolve both the **main JAR** and the **`exec` JAR** via the same logical SNAPSHOT version but with different `classifier + extension` pairs.

### 3.2. Why SNAPSHOTs Are Unsuitable as Immutable Release Keys

The same dependency:

~~~xml
<dependency>
    <groupId>com.example.release</groupId>
    <artifactId>release-demo</artifactId>
    <version>1.4.0-SNAPSHOT</version>
</dependency>
~~~

at two different times can resolve to **two different deployment snapshots**, depending on repository metadata, cache, mirrors, and update policy. The `mvn -U ...` command can force Maven to check for updated snapshots/release metadata per resolver capabilities, but **does not turn a logical SNAPSHOT into an immutable release**.

Using SNAPSHOTs for continuous integration is reasonable if consumers accept changes; for production, deploy/pin a **specific release artifact and accepted checksum/digest**, rather than treating a mutable SNAPSHOT as a fixed release.

### 3.3. -SNAPSHOT Differs from Pre-Release Qualifiers

Maven does not enforce Semantic Versioning across all projects. Names like `1.4.0-RC1`, `1.4.0-beta.1`, and `1.4.0` are **different version strings**; only the `-SNAPSHOT` suffix carries Maven semantics for snapshot resolution/deployment. A release candidate **is not automatically a SNAPSHOT** unless it uses that suffix.

A team may define a SemVer policy, such as major for breaking APIs, minor for backward-compatible features, and patch for bug fixes. However, that policy is **a project release convention**, not something Maven enforces or verifies automatically on your behalf.

## 4. Release Version: Preserving Identity and Bytes After Publication

A typical Maven release:

~~~xml
<version>1.4.0</version>
~~~

differs from `1.4.0-SNAPSHOT`. When a release is published, the version directory is typically:

~~~text
com/example/release/release-demo/1.4.0/
  release-demo-1.4.0.pom
  release-demo-1.4.0.jar
  release-demo-1.4.0-exec.jar
~~~

A reliable release requires two policy layers:

1. **Version identity:** `1.4.0` is tied to a specific source commit/tag, dependency graph, POM, JDK/toolchain, and pipeline.
2. **Artifact integrity:** each published file has its own SHA-256/signature/provenance, and the repository **disallows overwriting** published releases.

Do not modify code and `mvn deploy` the exact same `1.4.0` version again to "hotfix" a public artifact. If a repository allows overwrites, consumers can see different bytes for the same coordinate, breaking rollbacks and investigations. Release a new version (such as `1.4.1`) or use an audited release correction process rather than silently replacing an old artifact.

### 4.1. Version Numbering and Rollback

A common strategy:

~~~text
1.4.0-SNAPSHOT    1.4 line development
1.4.0-RC1         release candidate test build (per team policy)
1.4.0             published stable release
1.4.1             bugfix release after 1.4.0
1.5.0-SNAPSHOT    continued feature development on 1.5 line
~~~

Production rollback does not mean switching back to `<version>1.4.0</version>` and running a new build. It should **redeploy the exact saved artifact bytes of 1.4.0**, typically via an immutable repository coordinate/checksum or image registry digest.

A Maven project version does not automatically record the commit ID, build timestamp, or OCI digest. When exact traceability is needed, combine Git revision, artifact hashes, and a CI release manifest. Readable versions help coordination, while checksums verify actual files.

## 5. Classifiers in Spring Boot: Keeping Plain JAR and Executable JAR

### 5.1. Default repackage Without a Classifier

If Spring Boot Maven Plugin `repackage` runs **without a `classifier`**, it usually replaces the main JAR with the executable JAR, while the original archive may be saved with a `.original` suffix. This model is convenient for applications deployed solely via `java -jar`, but unsuitable when the module is consumed as a **normal dependency JAR**.

Reason: application classes in the executable JAR reside under `BOOT-INF/classes`, and runtime dependencies under `BOOT-INF/lib`. A dependent project using a standard classpath does not treat `BOOT-INF/classes` as the root `demo/`.

### 5.2. Using the exec Classifier

Per the Spring Boot Maven Plugin, configuring:

~~~xml
<configuration>
    <mainClass>demo.Application</mainClass>
    <classifier>exec</classifier>
    <attach>true</attach>
</configuration>
~~~

keeps **the normal main artifact** and creates a secondary executable archive `-exec.jar`. `attach=true` (the goal's default) attaches the artifact so Maven installs/deploys it to the repository **under the same GAV**.

When no artifact with classifier `exec` exists from an earlier packaging step, the Boot plugin uses the main JAR as its source and creates the classifier-attached executable archive. If a plugin **already created an artifact with classifier exec** earlier, the repackage goal may use that as source and replace that variant; therefore, inspect the effective POM and verify actual output files.

Several cases to distinguish:

| repackage configuration | Primary result | Things to watch out for |
| --- | --- | --- |
| No `classifier` | Executable JAR replaces main JAR | Other modules using it as a dependency normally cannot read classes like a plain JAR |
| `classifier=exec`, `attach=true` | Plain main JAR + executable `exec` artifact | Both can be `install`ed/`deploy`ed |
| `classifier=exec`, `attach=false` | Executable output may exist locally but is not attached for install/deploy | Do not assume remote has `-exec.jar` |
| `skip=true` | Skips the repackage goal | No Boot executable archive is generated by that goal |
| `<build><finalName>...` | Renames local output file | Does not change GAV/classifier in the Maven repository |

**Do not append `-exec` to `artifactId`** to simulate a classifier, because that becomes a different module/repository coordinate. Use a classifier when you want variants belonging to the same component/version, and split modules when the API/lifecycle truly differs.

## 6. Complete Hands-On Lab: One POM Producing Two JARs

### 6.1. Project Structure

~~~text
release-demo/
  pom.xml
  InspectReleaseArtifacts.java
  src/
    main/
      java/
        demo/
          Application.java
~~~

`InspectReleaseArtifacts.java` is placed at the **project root**, outside `src/main/java`, as a standalone artifact inspection tool. It is not packaged into the plain/executable JAR.

### 6.2. pom.xml Using Java 17 + Spring Boot 3.5

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

    <groupId>com.example.release</groupId>
    <artifactId>release-demo</artifactId>
    <version>1.4.0-SNAPSHOT</version>
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
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <executions>
                    <execution>
                        <id>repackage</id>
                        <configuration>
                            <mainClass>demo.Application</mainClass>
                            <classifier>exec</classifier>
                            <attach>true</attach>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Why is it configured this way?**

- `<version>1.4.0-SNAPSHOT</version>` is the version of **both artifacts**, not just the executable JAR.
- `<packaging>jar</packaging>` instructs Maven to create a normal main JAR.
- `spring-boot-starter-parent` manages plugin/dependency versions and already configures the `repackage` goal execution with id `repackage`. When **inheriting this parent**, the `<execution><id>repackage</id>` block in the example POM **customizes the inherited execution** rather than adding a second repackage goal.
- `classifier=exec` tells Boot to generate an executable JAR with classifier `exec`. `attach=true` allows publishing it alongside the main artifact.
- `mainClass=demo.Application` prevents ambiguity if multiple Java main classes appear later.
- `java.version=17` sets the compile target via the Boot parent; an actual JDK new enough to build is required.
- There is no distributionManagement or credentials in the example POM. Learners can build/install **locally** without needing access to a remote repository.

**In projects not using the Spring Boot starter parent**, you must explicitly configure the plugin version and bind/define the `repackage` goal execution. You cannot simply copy an `<execution><id>repackage</id>` **without a goal** and expect Maven to know what to invoke if the parent does not define that execution.

### 6.3. Application.java

Create `src/main/java/demo/Application.java`:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @Bean
    CommandLineRunner report() {
        return args -> System.out.println("release-demo:ok");
    }
}
~~~

The application uses Spring Boot starter (no embedded web server), prints one line, and the Spring application context normally has no server thread to keep it running long. For the following commands, **the line printed by the application code** is:

~~~text
release-demo:ok
~~~

Spring logs and Maven build logs are separate output and do not count toward the `System.out.println` line itself.

### 6.4. Build and Check Filenames

At the root containing `pom.xml`:

~~~bash
mvn -B -ntp clean verify
~~~

After a successful build, the project creates two main artifacts:

~~~text
target/release-demo-1.4.0-SNAPSHOT.jar
target/release-demo-1.4.0-SNAPSHOT-exec.jar
~~~

**Do not expect the executable archive to be named `release-demo-exec-1.4.0-SNAPSHOT.jar`**: Maven naming convention normally places the classifier **after the version**. Besides the two JARs, `target/` may contain other build directories and metadata.

Run the executable JAR:

~~~bash
java -jar target/release-demo-1.4.0-SNAPSHOT-exec.jar \
  --spring.main.banner-mode=off \
  --logging.level.root=OFF
~~~

This command uses POSIX shell line continuation. On Windows PowerShell, run it on a single line:

~~~powershell
java -jar .\target\release-demo-1.4.0-SNAPSHOT-exec.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

The line explicitly printed by the program:

~~~text
release-demo:ok
~~~

**Do not use `java -jar target/release-demo-1.4.0-SNAPSHOT.jar` as a PASS criterion**, because it is a **plain JAR** without the launcher/dependencies of an executable Boot archive. Plain JARs are used via normal classpath/dependency graphs, not to serve as a standalone full application.

### 6.5. Inspect with jar tf

~~~bash
jar tf target/release-demo-1.4.0-SNAPSHOT.jar
jar tf target/release-demo-1.4.0-SNAPSHOT-exec.jar
~~~

Expected characteristics:

| Entry or indicator | Plain main JAR | `exec` Boot JAR |
| --- | --- | --- |
| `demo/Application.class` at classpath root | Yes | Not at root |
| `BOOT-INF/classes/demo/Application.class` | No | Yes |
| `BOOT-INF/lib/...jar` | No | Yes |
| `org/springframework/boot/loader/...` | No | Yes |
| `Main-Class` is Boot `JarLauncher` | No | Yes |
| `Start-Class: demo.Application` | Not a required manifest contract | Yes |

This is a difference in **artifact contents**, not just filename suffix. When `repackage` has properly attached `exec`, `mvn install` and `mvn deploy` can publish both variants under the same GAV.

## 7. Writing a Java 17 Validator to Avoid Confusing Plain and Executable JARs

Create `InspectReleaseArtifacts.java` at the project root:

~~~java
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public class InspectReleaseArtifacts {

    private static void check(boolean condition, String detail) {
        if (!condition) {
            throw new IllegalStateException(detail);
        }
    }

    private static String attribute(JarFile jar, String name)
            throws Exception {
        Manifest manifest = jar.getManifest();
        if (manifest == null) {
            return null;
        }
        Attributes attrs = manifest.getMainAttributes();
        return attrs.getValue(name);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java InspectReleaseArtifacts.java "
                            + "<plain.jar> <exec.jar>");
        }

        try (JarFile plain = new JarFile(
                    Path.of(args[0]).toFile());
             JarFile exec = new JarFile(
                    Path.of(args[1]).toFile())) {

            check(plain.getEntry("demo/Application.class") != null,
                    "Main JAR lacks root application class");
            check(plain.getEntry(
                    "BOOT-INF/classes/demo/Application.class") == null,
                    "Main JAR unexpectedly has Boot layout");

            check(exec.getEntry(
                    "BOOT-INF/classes/demo/Application.class") != null,
                    "Exec JAR lacks packaged application class");
            check(exec.stream().anyMatch(e ->
                    e.getName().startsWith("BOOT-INF/lib/")
                            && e.getName().endsWith(".jar")),
                    "Exec JAR lacks nested runtime libraries");

            String main = attribute(exec, "Main-Class");
            String start = attribute(exec, "Start-Class");

            check("org.springframework.boot.loader.launch.JarLauncher"
                    .equals(main),
                    "Unexpected Boot launcher: " + main);
            check("demo.Application".equals(start),
                    "Unexpected Start-Class: " + start);

            System.out.println("plain.jar.layout=PASS");
            System.out.println("exec.jar.layout=PASS");
            System.out.println("classifier.exec=PASS");
        }
    }
}
~~~

This is a Java 17 standard library program that **requires no Spring imports**. It reads **the exact built ZIP/JAR files**: verifying that the plain JAR has the class at root, and the executable JAR contains `BOOT-INF/classes`/`BOOT-INF/lib` and a Boot 3.5 manifest with the proper launcher. On failure, it throws an exception and the Java launcher returns a nonzero exit code, making it suitable for CI use.

After `mvn clean verify`, run:

~~~bash
java InspectReleaseArtifacts.java \
  target/release-demo-1.4.0-SNAPSHOT.jar \
  target/release-demo-1.4.0-SNAPSHOT-exec.jar
~~~

In PowerShell, use a single line:

~~~powershell
java InspectReleaseArtifacts.java .\target\release-demo-1.4.0-SNAPSHOT.jar .\target\release-demo-1.4.0-SNAPSHOT-exec.jar
~~~

With the example POM/code above, the exact stdout **printed by the validator on PASS** is:

~~~text
plain.jar.layout=PASS
exec.jar.layout=PASS
classifier.exec=PASS
~~~

**Scope note:** This check targets the Spring Boot 3.5 `JAR` layout, not every Spring Boot version or `layout=ZIP/WAR/NONE`. When using another layout, the launcher/paths differ; adjust conditions to match the real artifact contract. This lesson does not claim these commands were already executed on your machine, and instead provides the code/expected output for your practice.

### 7.1. Checking the Checksum of Each Artifact

POSIX:

~~~bash
sha256sum target/release-demo-1.4.0-SNAPSHOT.jar
sha256sum target/release-demo-1.4.0-SNAPSHOT-exec.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\target\release-demo-1.4.0-SNAPSHOT.jar -Algorithm SHA256
Get-FileHash .\target\release-demo-1.4.0-SNAPSHOT-exec.jar -Algorithm SHA256
~~~

Having **different hashes is normal**, because the plain and exec JARs are two files with different structures and dependencies. Do not compare the two hashes to conclude one is a "wrong release." What needs verification is that each file has the right role/classifier and its corresponding checksum is recorded.

## 8. package, install, and deploy: Three Distinct Boundaries

| Command | Primary effect | Writes to remote repository? |
| --- | --- | --- |
| `mvn package` | Builds artifact in `target/` per lifecycle | No |
| `mvn verify` | Runs lifecycle through verify; typically includes tests/package and bound verification plugins | No |
| `mvn install` | Runs lifecycle through install, placing main/attached artifacts in Maven **local repository** | No |
| `mvn deploy` | Runs lifecycle through deploy, uploading artifacts to the repository configured by the deployment plugin | Yes, if pointing remote; or file repository if configured with file: |

**`mvn install` is not deploying the application to Tomcat, Kubernetes, or production**. It makes the artifact available in `~/.m2/repository` (or the configured local repository path) for other Maven builds in the same environment.

For the `1.4.0-SNAPSHOT` example, after:

~~~bash
mvn -B -ntp clean install
~~~

the local Maven repo may contain:

~~~text
~/.m2/repository/com/example/release/release-demo/1.4.0-SNAPSHOT/
  release-demo-1.4.0-SNAPSHOT.pom
  release-demo-1.4.0-SNAPSHOT.jar
  release-demo-1.4.0-SNAPSHOT-exec.jar
~~~

The path `~/.m2/repository` is a common default, not a constant: Maven `settings.xml` can override `localRepository`. On Windows, the path is typically under user home `.m2\repository`.

With `attach=true`/`classifier=exec` and a valid build, the install/deploy goals are aware of both the main artifact and the attached artifact. Conversely, if `attach=false` and you still see `-exec.jar` locally, do not assume it was published to the Maven repository.

### 8.1. The Deploy Phase May Re-run the Lifecycle

If you run `mvn clean verify`, smoke-test JAR A, and then run `mvn deploy`, Maven can re-execute the phases prior to deploy, including packaging/repackage. The resulting JAR B **may differ in bytes** due to timestamps/generated metadata or workspace changes. Therefore, never casually claim "since file A was tested, file A is definitely what got deployed."

A rigorous release pipeline should:

- Place appropriate verification gates **before deploy** within the same lifecycle/build orchestration, or use a **staging repository** with post-upload verification/promotion steps.
- If using multiple jobs, pass artifact bytes through an intermediate store with checksums and re-verify before publishing.
- After deploy, inspect remote artifact coordinates/classifiers and file hashes before promoting/announcing.
- Never run another Maven build and silently upload a replacement file while keeping the same release version.

## 9. distributionManagement: Specifies Where to Publish, Holds No Passwords

The Maven Deploy Plugin uses `distributionManagement` in the POM to know the target repository. A **configuration illustration** example, not a real deployment URL:

~~~xml
<distributionManagement>
    <repository>
        <id>demo-releases</id>
        <url>https://repo.example.invalid/repository/releases</url>
    </repository>
    <snapshotRepository>
        <id>demo-snapshots</id>
        <url>https://repo.example.invalid/repository/snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

The `repo.example.invalid` address is intentionally an example domain **not for real uploads**. In a real project, the repo manager (Nexus/Artifactory/equivalent Maven registry) and operations team provide the exact HTTPS URL and authorization. Do not guess endpoints from a company name.

When the POM version ends with `-SNAPSHOT`, Maven normally uses `snapshotRepository`; for non-SNAPSHOT releases, it uses `repository`. If `snapshotRepository` is omitted, fallback behavior depends on deploy/plugin configuration; declare both explicitly to avoid mixing policies, and check target repo logs during deployment.

### 9.1. Repository Server IDs and Credentials

Credentials **do not belong in the POM**. Maven `settings.xml` can declare matching server IDs:

~~~xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <servers>
        <server>
            <id>demo-releases</id>
            <username>release-publisher</username>
        </server>
        <server>
            <id>demo-snapshots</id>
            <username>snapshot-publisher</username>
        </server>
    </servers>
</settings>
~~~

**This snippet only shows ID mapping**, intentionally omitting passwords/tokens because secrets should not be written in Knowledge lessons. In CI, credentials must be supplied by secret management/appropriately managed settings; never commit `settings.xml` containing passwords/tokens to Git or print them in public logs. Newer Maven versions offer credential origin binding mechanisms; when upgrading Maven/enterprise mirrors, consult the exact version's settings documentation.

`<id>` in `distributionManagement` must match `<server><id>` so Maven can locate credentials. HTTP 401/403 errors are typically token/permission/server ID issues, not `1.4.0-SNAPSHOT` version or classifier errors.

### 9.2. Dependency Repository Differs from Publishing Repository

In a POM, `<repositories>`/`<pluginRepositories>` describe where to **resolve/download** dependencies/plugins; `<distributionManagement>` specifies where to **upload the project's artifacts**. Do not add a publish-capable repository into `<repositories>` and expect `mvn deploy` to know where to upload.

A repository manager also enforces policies for snapshots vs releases, permissions, retention, and overwrite protection. Having a URL in the POM does not grant permission by itself. All real publish operations must go through CI/approval and authorized repositories.

## 10. Practicing Local File Repository Publishing Without Touching Remote Production

If you want to observe the deploy layout **without needing a repository account**, you can use the Maven Deploy Plugin with `altDeploymentRepository` pointing to a **local file repository for this lab**.

Illustrative command from the project root, with a modern Maven Deploy Plugin:

~~~bash
mvn -B -ntp clean deploy \
  -DaltDeploymentRepository=lab::file:./target/lab-maven-repo
~~~

This command **actually runs the deploy goal**, but the upload target is `file:./target/lab-maven-repo`, not a production HTTP server. It generates repository files/metadata inside the test working directory, depending on the Maven deploy-plugin version and resolved paths. This is a lab exercise; if running in real CI, ensure proper local paths and cleanup, and never accidentally point `-DaltDeploymentRepository` at a release repository.

**Plugin version note:** the `id::url` syntax applies to Maven Deploy Plugin 3.x. Some older 2.x plugins used `id::layout::url`. With a Spring Boot parent managing versions, check the effective POM/plugin version before using the command in another project.

Afterward, inspect the repository filesystem under `target/lab-maven-repo/com/example/release/release-demo/` and read `maven-metadata.xml` if present. Snapshot deployments may receive timestamped filenames instead of the local `-SNAPSHOT` name. Do not hardcode timestamps or build numbers when writing QA checks.

**Do not call this a production release.** A file repository only helps demonstrate the role of `deploy`/metadata; production repositories require HTTPS/authentication, immutability, auditing, artifact scanning, and dedicated promotion policies.

### 10.1. Maven deploy-file Differs from Maven deploy

`mvn deploy` publishes **project artifacts** (main artifact, POM, attached classifiers) per the lifecycle. `mvn deploy:deploy-file` is a separate goal typically used to upload a prebuilt artifact or third-party binary, requiring you to supply the file, coordinates, repository/pom, and optionally additional files/classifiers per plugin configuration.

If you use `deploy-file` only for `-exec.jar` and forget the `main JAR`/POM or use the wrong classifier, consumers may face dependency resolution errors. Therefore, for projects built normally by Maven, **prefer `mvn deploy`/staging workflows** so Maven handles the complete set of project artifacts. Use `deploy-file` only when you know the exact files to publish and verify repository metadata.

## 11. Controlled Transition from SNAPSHOT to Release

### 11.1. Manual Workflow Using Maven Versions Plugin

Suppose the repository is at `1.4.0-SNAPSHOT` and the team decides to release `1.4.0`. Use the Maven Versions Plugin from the project root (real projects should pin the plugin version in build governance):

~~~bash
mvn versions:set -DnewVersion=1.4.0 -DgenerateBackupPoms=false
git diff -- pom.xml
~~~

`versions:set` updates the project version in the POM. It does **not** automatically fix application compatibility, create a Git tag, or publish. In multi-module builds, check flags to update parent/child versions consistently.

Once code is frozen and QA completes:

~~~bash
mvn -B -ntp clean verify
java InspectReleaseArtifacts.java \
  target/release-demo-1.4.0.jar \
  target/release-demo-1.4.0-exec.jar
java -jar target/release-demo-1.4.0-exec.jar \
  --spring.main.banner-mode=off \
  --logging.level.root=OFF
~~~

The validator in section 7 takes filenames matching the current version; main/executable layout does not change just by dropping the `-SNAPSHOT` suffix. The line printed by `Application` remains `release-demo:ok`.

After gates pass and the commit is approved, record the Git revision alongside the POM version. Example SCM operations:

~~~bash
git add pom.xml
git commit -m "Release 1.4.0"
git tag v1.4.0
~~~

These commands **illustrate a workflow for a valid Git repository**, not commands to run in every team. Teams may use signed tags, protected branches, and automation. Only tag once the Git working tree/permissions/branch policy are confirmed; never create tags or push without authorization.

### 11.2. Releasing and Returning to the Development Line

After release `1.4.0` is published/approved (and **without** overwriting bytes under the same version), you can open the next version:

~~~bash
mvn versions:set \
  -DnewVersion=1.5.0-SNAPSHOT \
  -DgenerateBackupPoms=false
git diff -- pom.xml
~~~

Choose `1.5.0-SNAPSHOT` only when it fits the versioning plan; if the team continues on a `1.4.x` patch branch, the development version could be `1.4.1-SNAPSHOT`. Releasing `1.4.0` does not mandate that the next minor must be 1.5.0.

**Do not automatically execute version updates/releases/SCM operations against production solely because of this example.** Real systems have approval gates, versioning policies, protected tags, CI credentials, and staging/promotion.

### 11.3. Maven Release Plugin

The Maven Release Plugin provides the `release:prepare` and `release:perform` goals. Per the documentation:

- `prepare` can check for uncommitted changes/SNAPSHOT dependencies, change POM versions, run checks, commit/tag, and bump to the next development version.
- `perform` can check out the release tag and execute publishing per configuration.
- Requires proper SCM configuration, Git credentials/permissions, distributionManagement, and plugin versions.
- The plugin can **modify source/POM/tags/remote artifacts**; do not experiment with it on a real repository without understanding its impact.

This is a stateful release workflow, not a simple drop-in replacement for `mvn package`. In CI systems with their own release orchestrator, an alternative approach may be used as long as identity/provenance and artifact immutability are verified.

## 12. SNAPSHOT Policy, Consumer Resolution, and Dependency Hygiene

### 12.1. Consumer Pointing to a SNAPSHOT

A consumer using `1.4.0-SNAPSHOT` can receive a new artifact whenever the resolver refreshes snapshot metadata. This is useful for integration environments, but dangerous if the consumer needs deterministic rollback.

Controls:

- Do not use mutable SNAPSHOTs in production without an explicitly approved exception policy.
- For integration builds, record the **resolved snapshot timestamp/build number** and binary SHA-256, not just the logical version.
- Manage `updatePolicy`/mirrors and dependency caches; understand the effect of `mvn -U` on resolution.
- Do not enable snapshot resolution on a release repository without reason, or conversely point a release build at a snapshot-accepting repository.
- When a release needs a locked dependency graph, prefer non-SNAPSHOT versions and artifact integrity verification.

### 12.2. Classifiers Belong to Each Snapshot Artifact

In remote metadata, `snapshotVersions` distinguishes artifacts by **extension** and **classifier**. If the repository has the main `jar` but lacks the `exec` `jar`, a consumer requesting `classifier=exec` can fail to resolve even though `1.4.0-SNAPSHOT` logically exists.

When deploying, verify **both files** and their metadata mappings before declaring the full release set ready. In CI, you can query the repository API to confirm the exact artifacts and compare checksums from the upload rather than relying solely on Maven `BUILD SUCCESS`.

### 12.3. SNAPSHOT and dependencyManagement/BOM

The Spring Boot parent/BOM manages versions of many dependencies, but **does not automatically turn the project's own version into a release**. A project can remain `1.4.0-SNAPSHOT` while all external dependencies are stable releases.

Conversely, a project carrying version `1.4.0` that depends on `some-lib:2.0-SNAPSHOT` still carries the risk of using mutable binaries. Release policies should inspect both the **project version** and the **resolved dependency tree**, not just the string in the root POM.

Similarly, plugin versions must be managed; releasing application code does not prevent a Maven plugin from being upgraded automatically via ranges or missing version declarations in another POM.

## 13. Source JAR, Javadoc JAR, and Test JAR: Which Classifiers Should Be Published?

Alongside `exec`, Maven commonly has attached artifacts:

| Classifier | Typical purpose | Who uses it |
| --- | --- | --- |
| *(empty)* | Main binary JAR for compile/runtime dependencies | Other projects consuming it as a library |
| `exec` | Boot executable JAR packaging nested dependencies | Runtime deployment/CLI |
| `sources` | Source archive | IDE/source browsing, source repository |
| `javadoc` | API documentation | IDE, docs, certain publishing policies |
| `tests` | Test classes (if the project explicitly attaches a test JAR) | Test utilities, not a runtime dependency by default |

Classifiers **should not be used to hide breaking APIs**. If `exec` and the main JAR of the same GAV contain significantly different application behavior/contracts, revisit the artifact design and module boundaries.

To publish sources/Javadocs, the Maven Source Plugin/Javadoc Plugin with appropriate executions are typically used; do not assume `mvn deploy` generates `-sources.jar` and `-javadoc.jar` if the POM does not declare them. Some public repositories (such as Maven Central) enforce specific metadata, source/Javadoc, and signing policies; internal Nexus/Artifactory instances may have different requirements.

When a module is strictly a Spring Boot application with no API intended as a library, you may **not need** to publish the plain JAR as a consumable dependency. However, if a team has a requirement for both a library and a runnable program, classifier `exec` cleanly separates the two roles, provided the dependency graph and packaging have been tested.

## 14. Multi-Module: Version and Classifier Must Be Consistent Across the Reactor

A Maven monorepo:

~~~text
project/
  pom.xml            (packaging=pom, parent/aggregator)
  api/
    pom.xml          (library jar)
  service/
    pom.xml          (Spring Boot application jar)
~~~

One strategy:

- `api` publishes the main library artifact with the release version or per its own versioning policy.
- `service` builds an executable JAR with classifier `exec` if the main JAR needs to be preserved.
- Parent/BOM manages versions and plugin executions, but only modules actually having a main class run `repackage` for the application.
- A parent with `packaging=pom` has no executable JAR to run; do not force repackage on every module.
- If child versions inherit from the parent, check during release bumps that parent references and internal dependency versions are updated properly.

In the reactor, for example:

~~~bash
mvn -pl service -am clean verify
~~~

` -pl service -am ` (type `-pl` without a leading space) selects the service module and the projects it depends on within the reactor. Output paths are typically `service/target/...jar`, not `target/...jar` at the repo root. For artifacts in different modules, `groupId`/`artifactId` may differ even if they share the same version.

When publishing a reactor with `mvn deploy`, inspect the output of each module/classifier and repository permissions. Avoid wildcard uploading `target/*.jar` across multiple modules, as that can mix plain, executable, sources, and stale artifacts.

### 14.1. Dependency with Classifier exec in Another Module

If `api` or `service-b` needs to call a Java class from `service`, use the **main JAR** of `service` if the contract allows; better yet, place shared APIs/logic in the `api` module. **Do not use the executable `-exec.jar` as a library just because the filename contains dependencies**.

A Spring Boot executable JAR is a product meant to **boot**, not an assembly replacing dependency management. Uploading an executable JAR to a Maven repository **does not** automatically turn nested libraries into transitive Maven dependencies for consumers as they might expect.

## 15. Publishing the Right Artifact via CI/CD

A release pipeline can record the following gates:

~~~text
1. Check out the exact Git commit/tag
2. Confirm clean source and POM project version
3. Resolve dependencies/toolchain/parent versions
4. mvn -B -ntp clean verify
5. Verify plain JAR + exec JAR match expected version/classifier
6. java -jar exec JAR and run real smoke tests
7. Record separate SHA-256 hashes for plain/exec/POM/source artifacts
8. Stage/publish per Maven repository policy
9. Verify uploaded artifacts + snapshot/release metadata + hashes
10. Promote/announce immutable release (or CI snapshot artifact)
11. Record revision + GAV + classifier + SHA + repository URL
12. Deploy the exact verified artifact
~~~

**Do not push a release solely because `mvn clean package` reported success.** Check file layout, runtime behavior, source commit/working tree, dependency scopes/versions, and repository bytes after upload. Use repository staging/promotion when you need a gate before the release becomes visible to consumers.

### 15.1. Minimal Release Manifest

An illustrative record:

~~~text
SCM revision:       Git commit SHA verified by CI
Maven GAV:          com.example.release:release-demo:1.4.0
Main artifact:      release-demo-1.4.0.jar
Main classifier:    (none)
Executable artifact:release-demo-1.4.0-exec.jar
Exec classifier:    exec
Packaging:          jar
JDK:                Java 17 (pinned toolchain version)
Repository:         authorized release repository
Hash main:          SHA-256 from published file
Hash exec:          SHA-256 from published file
QA:                 artifact inspect + runnable smoke PASS
~~~

This is a **field template**, containing no fake SHAs. In practice, populate real checksums from the artifacts and attach CI job ID/timestamp, source revision, and dependency lock/provenance as required by policy.

### 15.2. Git Tags and Artifact Names Do Not Replace Checksums

The `v1.4.0` Git tag indicates a source reference; Maven `1.4.0` is a logical version; `release-demo-1.4.0-exec.jar` is an artifact file; the file's SHA-256 is its byte fingerprint. All four **serve different roles**.

A tag can be moved if the repository is unprotected; the same source can rebuild into different JAR bytes if timestamps/plugins/dependencies are non-deterministic. Therefore, CI should protect tags, store checksums, pin tools/repositories, and record details of published artifacts.

### 15.3. Reproducibility Does Not Equal Release Policy

`project.build.outputTimestamp` can help Maven plugins produce archives with deterministic timestamps:

~~~xml
<properties>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

This illustrative fragment must be merged into existing properties and set to a timestamp matching your **release policy**, not copying the 2024 date for every build. Yet a fixed timestamp alone does not prove Maven release 1.4.0 was published from the right source, or that transitive dependencies are completely immutable.

Conversely, a repo manager forbidding release overwrites does not automatically guarantee JARs are byte-for-byte reproducible from source. These are two complementary concerns: **integrity/immutability of the published artifact** and **the ability to rebuild identical bytes**.

## 16. Gradle maven-publish and Classifiers: Equivalent Model

Although the main example uses Maven, the Spring Boot Gradle Plugin also provides `bootJar` (executable) and `jar` (plain) with an archive classifier property. In a Gradle Groovy DSL project with compatible Java/Spring Boot plugins, you can explicitly configure:

~~~groovy
tasks.named('bootJar') {
    archiveClassifier = 'exec'
}

tasks.named('jar') {
    archiveClassifier = ''
}
~~~

This is a **fragment**, not a standalone `build.gradle`. Confirm syntax/property style per Gradle version; in Kotlin DSL, `archiveClassifier.set("exec")` and `archiveClassifier.set("")` are typically used.

To publish the right artifacts with `maven-publish`, you must create a `MavenPublication` and **attach the right bootJar artifact** per the project's task/artifact configuration, rather than assuming that two tasks succeeding means both were uploaded. Version `1.4.0-SNAPSHOT` in Gradle also carries Maven snapshot semantics when published to a Maven-compatible repository, though resolution/publishing plugins, repository credentials, and classifiers are declared using Gradle's own DSL.

Do not paste Maven Spring Boot plugin `<classifier>exec</classifier>` XML into `build.gradle` hoping it will work; the two plugins have different configuration structures. When using Gradle, apply the same principles: **main vs executable artifact, snapshot vs release, version identity vs bytes, remote repository policy**.

## 17. Common Errors and Diagnostics

| Symptom | Possible cause | Proper check |
| --- | --- | --- |
| `java -jar release-demo-1.4.0.jar` reports missing main manifest | Running the **plain main JAR** | Pick `-exec.jar`; inspect manifest/classpath |
| `ClassNotFoundException` when consumer uses `-exec.jar` as dependency | App classes are inside `BOOT-INF/classes` | Use plain JAR or split out an `api` module |
| Only one JAR after package | `classifier` not applied to the right execution, repackage did not run | Effective POM, parent `repackage` execution id, build logs |
| Only main JAR appears in repository | `attach=false` or classifier was not attached | Boot plugin `attach`, Maven install/deploy logs, and remote files |
| Two JARs have different versions | Different POMs/modules/profiles/jobs | `mvn help:evaluate`, selected module, build revision |
| Cannot resolve `classifier=exec` | Remote repo missing attached artifact or classifier metadata | `maven-metadata.xml`, artifact paths, and repository permissions |
| SNAPSHOT resolves differently from yesterday | Remote metadata now points to newer deployment, local cache/update policy | Snapshot timestamp/buildNumber, `mvn -U`, checksums |
| Release repo rejects SNAPSHOT | Repository policy rejects snapshots | Check `distributionManagement.snapshotRepository` |
| Snapshot repo rejects release | Repository policy rejects non-SNAPSHOTs | Check `distributionManagement.repository` |
| `mvn deploy` reports missing distributionManagement | POM lacks target repository and no alt deployment config given | POM/effective POM, deploy-plugin docs |
| HTTP 401/403 on deploy | Credentials/server ID/permission mismatch | Maven settings, credential store, repository policy |
| HTTP 400/409 on release deploy | Version already exists or repository rejects overwrite/policy | Inspect response and release a new version when needed |
| `mvn install` succeeds but others cannot see artifact | Only local repository was updated | Use approved remote deploy/publish |
| `versions:set` does not update modules | Parent/child references or scope not handled | Versions Plugin args, inspect all POM diffs |
| Repo has `-sources.jar` but lacks exec | Attachments managed by different plugins | Spring Boot `classifier=exec`/`attach` and execution |
| `finalName` changed, Maven consumer cannot find file | Confused local filename with GAV/repository naming | Check publication coordinates |
| Same release version but SHA changed | Rebuilt/overwritten artifact, uncontrolled dependencies/plugins/time | Repo immutability, provenance, checksums |
| Snapshot timestamp has `-3` while POM version stays SNAPSHOT | Normal unique snapshot behavior | Repository metadata mapping |
| CI tested JAR A but uploaded JAR B | `mvn deploy` re-ran lifecycle or separate build jobs | Hash before/after, stage artifact, and verify remote |
| Parent `packaging=pom` has no exec JAR | Parent is only aggregator/BOM | Only repackage service modules with a main class |
| Gradle bootJar builds green but does not publish | Publication missing `bootJar` task artifact | `maven-publish` configuration, remote contents |

When diagnosing errors, investigate in order: **effective POM/version → classifier target → local target artifacts → manifest/layout → install/deploy logs → repository files/metadata → runtime artifact hash**. Do not randomly change `classifier` or pin a timestamped snapshot as the project version just to bypass a resolver error.

## 18. Checklist and Self-Check Questions

### Pre-Release Checklist

- [ ] Confirm exact `groupId`, `artifactId`, `version`, `packaging`.
- [ ] Clearly decide which artifact is the **main JAR**, which is the **exec JAR**, and which type consumers use.
- [ ] If both are needed, `repackage` uses `classifier=exec` with `attach=true`.
- [ ] Build cleanly; inspect manifest/`BOOT-INF` and run the exact `-exec.jar`.
- [ ] Record separate SHA-256 hashes for main, exec, and sources/Javadocs if published.
- [ ] Use SNAPSHOT only for appropriate development flows, never as an immutable production key.
- [ ] Protect release versions against overwrites, tied to Git commit/tag and artifact bytes.
- [ ] Match repository `snapshotRepository`/`repository` and permissions to the version type.
- [ ] Keep credentials only in secrets/settings, never commit tokens into POM.
- [ ] Understand local `mvn install` differs from remote `mvn deploy`; do not use it in place of app deployment.
- [ ] For multi-module builds, keep versions and executions/classifiers consistent per module.
- [ ] Have CI verify **the exact file to be published**, cross-checking repository artifacts after deploy.
- [ ] Plan rollbacks using **immutable artifacts** rather than rebuilding the same version.

### Self-Check

**Question A.** Are `1.4.0-SNAPSHOT` and `1.4.0` the same Maven version?

**Answer:** No. They are two different version identifiers. `-SNAPSHOT` enables resolution/deployment via snapshot metadata, whereas releases are usually governed by separate immutability rules.

**Question B.** Does the local file `release-demo-1.4.0-SNAPSHOT-exec.jar` necessarily keep this exact name on a remote repository?

**Answer:** No. A remote snapshot repository can use a unique timestamped filename such as `release-demo-1.4.0-20261109.031405-3-exec.jar`, while the POM logical version remains `1.4.0-SNAPSHOT`.

**Question C.** Why isn't a Spring Boot executable JAR with classifier `exec` a normal dependency JAR?

**Answer:** Application classes reside in `BOOT-INF/classes` and nested dependencies in `BOOT-INF/lib`, loaded by the Boot launcher during `java -jar`. Dependent modules using a normal Java classpath should use a plain JAR or an API module.

**Question D.** Does `attach=false` affect local files or the repository?

**Answer:** The repackaged JAR may still be generated in local target, but it is not attached for install/deploy as a classifier artifact. Inspect actual output and remote contents.

**Question E.** Does changing `<finalName>app</finalName>` create a Maven artifactId of `app`?

**Answer:** No. It changes the local filename, while Maven GAV still follows `groupId`, `artifactId`, and `version` in the POM.

**Question F.** Why are the same Git tag and release version insufficient to prove the published artifact has the exact bytes that were tested?

**Answer:** Two builds from one commit can differ in timestamps/dependencies, and the deploy phase can re-run packaging. Checksums of the exact artifact and remote download/promotion must be stored and verified.

**Question G.** Does `mvn install` make the new application appear on the production server?

**Answer:** No. It only installs artifacts into the local Maven repository. Publishing to a repository uses `deploy`; deploying the application to runtime is a separate workflow.

**Question H.** What does `maven-metadata.xml` in a SNAPSHOT repo use the classifier for?

**Answer:** Metadata distinguishes variants via `classifier + extension` when mapping a logical SNAPSHOT to a timestamped version. Main JAR and `exec` JAR are two separate sub-artifacts despite sharing the same base version.

## 19. Official Documentation

- Maven — POM Reference (coordinates, packaging, distributionManagement): https://maven.apache.org/pom.html
- Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven — Maven Repository Layout (classifier and extension): https://maven.apache.org/repository/layout.html
- Maven — Maven Repository Metadata: https://maven.apache.org/repositories/metadata.html
- Maven — Repository Metadata Model (timestamp, buildNumber, snapshotVersion): https://maven.apache.org/ref/3-LATEST/maven-repository-metadata/repository-metadata.html
- Maven — Deploy Plugin Usage: https://maven.apache.org/plugins/maven-deploy-plugin/usage.html
- Maven — Deploy Plugin Network/Local Staging: https://maven.apache.org/plugins/maven-deploy-plugin/examples/deploy-network-issues.html
- Maven — Settings Reference (servers, credentials and repositories): https://maven.apache.org/settings.html
- Maven — Maven Release Plugin / Prepare a Release: https://maven.apache.org/maven-release/maven-release-plugin/usage/prepare-release.html
- Maven — Versions Plugin (set project version): https://www.mojohaus.org/versions/versions-maven-plugin/set-mojo.html
- Spring Boot 3.5 — Packaging Executable Archives (repackage, classifier, attach): https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Maven Plugin: https://docs.spring.io/spring-boot/3.5/maven-plugin/
- Java 17 — JarFile API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarFile.html

**Conclusion:** `version` answers **which release this is**, `-SNAPSHOT` signals **this is a changeable development version**, and `classifier` distinguishes **artifact variants** within the same GAV. With Spring Boot, `classifier=exec` keeps the main JAR as a library and the executable JAR as the runnable product. Inspect **both files**, publish only to the right snapshot/release repository per policy, record checksums/commits, and ensure production deploys **the exact accepted bytes**, not just a memorable version name.