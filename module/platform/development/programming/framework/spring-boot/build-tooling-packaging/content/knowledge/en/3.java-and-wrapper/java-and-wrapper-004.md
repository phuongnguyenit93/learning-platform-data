# Using the Maven Wrapper via mvnw and mvnw.cmd

## 1. What Is the Maven Wrapper?

**Maven Wrapper** is a set of scripts stored alongside your source code that lets you run the project with the **exact Apache Maven version specified by the project itself**. The two main scripts are:

- `mvnw`: used on Linux/macOS or environments with a POSIX-compatible shell.
- `mvnw.cmd`: used on Windows with Command Prompt or PowerShell.

Normally, `mvn clean package` requires Maven to be installed on the machine and configured on `PATH`. With the wrapper, the project can run `./mvnw clean package` (Linux/macOS) or `.\mvnw.cmd clean package` (Windows PowerShell). The wrapper looks for an already-downloaded Maven distribution or downloads the exact version required before invoking Maven. Arguments like `clean`, `package`, `verify`, and `-D...` are forwarded directly to Maven.

**Important limitation:** Maven Wrapper selects/provides **Maven**; it does not install a JDK and does not determine dependency versions inside `pom.xml`. The machine still needs a JDK compatible with both the project and the chosen Maven version. In modern Spring Boot contexts, JDK 17+ is common; exact requirements depend on the Spring Boot version.

```text
Checkout source code (pom.xml + wrapper files)
             |
             v
 ./mvnw ...       or       .\mvnw.cmd ...
             |
             v
Read .mvn/wrapper/maven-wrapper.properties
             |
             v
Locate or download configured Maven distribution
             |
             v
Run actual Maven with passed goals/phases
             |
             v
Resolve dependencies -> compile -> test -> package/verify
```

Using the wrapper ensures newcomers and CI systems run the **same Maven version**, reducing "it works on my machine because of a different Maven version" issues. Still, build reproducibility also depends on the JDK, plugins, dependencies, repositories, and environment.

## 2. Maven Wrapper Files in a Project

A Maven project with the wrapper typically has this layout:

```text
my-app/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
└── src/
    └── main/
        └── java/
```

| Component | Function |
|---|---|
| `pom.xml` | Declares artifacts, dependencies, plugins, and Maven build configuration |
| `mvnw` | Wrapper script for Unix-like shells |
| `mvnw.cmd` | Wrapper script for Windows |
| `.mvn/wrapper/maven-wrapper.properties` | Configures the URL/version of Maven to use, optionally with checksums |
| `.mvn/wrapper/maven-wrapper.jar` | Present only in **certain wrapper types** |
| `.mvn/wrapper/MavenWrapperDownloader.java` | May appear when using the Java-source bootstrap wrapper type |

**Not every project has `maven-wrapper.jar`.** The current Apache Maven Wrapper Plugin defaults to generating the `only-script` type: the script downloads the Maven distribution directly without needing a wrapper JAR. Older projects or those using other types may include the JAR or Java downloader. Do not delete them arbitrarily without knowing which wrapper type the project uses.

Wrapper scripts and configuration should be committed to Git so anyone cloning the repository can use them immediately. On Linux/macOS, `mvnw` also needs **execute permission**; Git can store the executable bit for that file.

## 3. Running the Wrapper After Cloning a Project

Open a terminal at the **root directory containing `pom.xml` and `mvnw`/`mvnw.cmd`**. Corresponding commands:

| Task | Linux/macOS | Windows PowerShell |
|---|---|---|
| Check Maven | `./mvnw -version` | `.\mvnw.cmd -version` |
| Compile main code | `./mvnw compile` | `.\mvnw.cmd compile` |
| Run unit tests | `./mvnw test` | `.\mvnw.cmd test` |
| Clean old outputs and package | `./mvnw clean package` | `.\mvnw.cmd clean package` |
| Run up to the verify phase | `./mvnw verify` | `.\mvnw.cmd verify` |
| Build in CI mode | `./mvnw -B -ntp clean verify` | `.\mvnw.cmd -B -ntp clean verify` |

In **Windows Command Prompt** (`cmd.exe`), invoke the batch file directly:

```bat
mvnw.cmd -version
mvnw.cmd clean package
mvnw.cmd verify
```

In **Windows PowerShell**, prepend `.\` because PowerShell does not search the current directory by default:

```powershell
.\mvnw.cmd -version
.\mvnw.cmd clean package
.\mvnw.cmd verify
```

On **Linux/macOS**:

```bash
./mvnw -version
./mvnw clean package
./mvnw verify
```

`-B` enables batch mode, suitable for CI; `-ntp` reduces download progress lines. `-version`/`-v` prints the **actual Maven version used by the wrapper**, along with Java and OS details. Do not assume `mvn -version` matches `./mvnw -version`: `mvn` runs Maven from `PATH`, whereas the wrapper selects the Maven version from the project configuration.

If you encounter `Permission denied` on Unix, try `chmod +x mvnw` and save the executable bit in Git. If the file has Windows CRLF line endings causing the shell to report `/bin/sh^M` or "bad interpreter", restore LF line endings on the `mvnw` script. This fixes file permissions or formatting only; it does not resolve JDK, network, or dependency issues.

## 4. Generating the Wrapper for a Project That Lacks One

**Maven must already be installed for the initialization step**, since the project does not yet have a script to call. For a project with `pom.xml`, run from the root:

```bash
mvn -N wrapper:wrapper -Dmaven=3.9.9 -Dtype=only-script
```

Meaning:

- `wrapper:wrapper`: goal of the **Apache Maven Wrapper Plugin** that generates or updates wrapper files.
- `-N` (`--non-recursive`): runs only on the current project; useful at the root of a multi-module project.
- `-Dmaven=3.9.9`: example **pinning Maven 3.9.9**; this is a real illustrative version, not a claim that it is the latest. Choose a version suited to your project.
- `-Dtype=only-script`: lightweight script wrapper without adding a wrapper JAR to the repository.

After generation, verify:

```bash
chmod +x mvnw
./mvnw -version
./mvnw clean verify
```

On Windows, after generating the wrapper, use `mvnw.cmd -version` in Command Prompt or `.\mvnw.cmd -version` in PowerShell. For a project that already has a wrapper, **you do not need to re-run `wrapper:wrapper` on every build**. Use the existing scripts directly; generating/updating the wrapper is build configuration maintenance.

Add the necessary files to version control (illustrative commands in your own repository):

```bash
git add pom.xml mvnw mvnw.cmd .mvn/wrapper
git commit -m "Add Maven Wrapper"
```

### Wrapper Types to Distinguish

| Type | Bootstrap Mechanism | Key Point to Remember |
|---|---|---|
| `only-script` | `mvnw`/`mvnw.cmd` directly downloads the Maven distribution | Default when newly generated by the current plugin; no wrapper JAR used |
| `bin` | Wrapper JAR provided inside `.mvn/wrapper` | Usually requires committing `maven-wrapper.jar` |
| `script` | Script downloads the wrapper JAR when needed and runs it | Different download mechanism from `only-script` |
| `source` | Includes Java source to download the wrapper JAR | Adds a Java downloader source file |

The exact set of files can depend on the plugin/wrapper version. If switching types, run `wrapper:wrapper` with `-Dtype=...` and inspect all generated files; do not modify or delete bootstrap files at random.

## 5. End-to-End Runnable Java 17 Example

The plain Java example below helps distinguish the wrapper's role from the `java` command. Create the project:

```text
maven-wrapper-demo/
├── pom.xml
└── src/main/java/vn/example/wrapper/WrapperDemo.java
```

Complete `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>maven-wrapper-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/vn/example/wrapper/WrapperDemo.java`:

```java
package vn.example.wrapper;

public class WrapperDemo {
    public static void main(String[] args) {
        System.out.println("Maven Wrapper OK");
    }
}
```

After creating the files and generating the wrapper as in Section 4, with JDK 17+ on Linux/macOS:

```bash
./mvnw clean package
java -cp target/classes vn.example.wrapper.WrapperDemo
```

Windows PowerShell:

```powershell
.\mvnw.cmd clean package
java -cp target/classes vn.example.wrapper.WrapperDemo
```

**Exact stdout of the `java -cp ...` command** (excluding Maven logs from the preceding build command):

```text
Maven Wrapper OK
```

You can also compile directly with JDK 17 to clearly see that the wrapper only serves **Maven commands** and is not needed to run compiled Java:

```bash
javac -d out src/main/java/vn/example/wrapper/WrapperDemo.java
java -cp out vn.example.wrapper.WrapperDemo
```

Running it also prints `Maven Wrapper OK`. `-d out` places bytecode under `out/vn/example/wrapper`; `-cp out` puts that root folder on the classpath.

After `package`, Maven produces `target/maven-wrapper-demo-1.0.0.jar`. This is a **plain library JAR**: this example does not add `Main-Class` to the manifest, so `java -jar target/maven-wrapper-demo-1.0.0.jar` cannot run by default. To run with `java -jar`, configure an appropriate manifest or use Spring Boot's executable JAR mechanism.

## 6. Using the Maven Wrapper in Spring Boot Projects

For a Spring Boot Maven project that already has a wrapper, invoking Maven uses the same goals/phases, only with the wrapper script:

```bash
# Linux/macOS
./mvnw clean package
./mvnw verify
./mvnw dependency:tree
./mvnw spring-boot:run
```

```powershell
# Windows PowerShell
.\mvnw.cmd clean package
.\mvnw.cmd verify
.\mvnw.cmd dependency:tree
.\mvnw.cmd spring-boot:run
```

- `clean package`: removes prior build outputs and runs phases up to `package`, including compilation and tests as configured.
- `verify`: runs up to the artifact verification phase; in some projects this also includes integration tests/additional checks.
- `dependency:tree`: prints the dependency tree to diagnose versions or conflicts.
- `spring-boot:run`: goal of the **Spring Boot Maven Plugin**, running the application from the project when the plugin and startup class are configured.

Example `pom.xml` snippet for a project using `spring-boot-starter-parent`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

This is **only the `<build>` snippet inserted into a Spring Boot POM with an appropriate parent**, not a standalone POM. When the plugin and `repackage` execution are configured, `package` can produce an executable JAR runnable via `java -jar`. If using a POM that does not inherit the Spring Boot parent, declare the plugin version and execution configuration explicitly.

**The Maven Wrapper does not turn a plain JAR into a Spring Boot executable JAR.** Packaging is the job of plugins and build configuration; the wrapper only selects the Maven version to execute. Nor does it add a web starter, web controller, or open an HTTP port.

## 7. Maven Version Configuration and Cache Locations

`.mvn/wrapper/maven-wrapper.properties` contains `distributionUrl`, for example:

```properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
```

The URL above is an example pinning **Maven 3.9.9**. In a real project, pick a version tested by your team, then verify again with `./mvnw -version` or `.\mvnw.cmd -version`. You can update the wrapper via the `wrapper:wrapper` goal or controlled edits to `distributionUrl`. When updating an existing wrapper, the plugin typically preserves the previous distribution type unless `-Dtype` is passed.

Distinguish these paths:

| Location | What Does It Contain? |
|---|---|
| `.mvn/wrapper/maven-wrapper.properties` | Wrapper configuration **committed** in the project |
| `~/.m2/wrapper/dists` | Downloaded and extracted Maven distributions for the wrapper |
| `~/.m2/repository` | Maven local repository storing dependencies, plugins, parent POMs, artifacts |
| `target/` | Files generated by the current build; typically cleaned by the `clean` phase |

On the first run, the wrapper may download the Maven distribution, and Maven then downloads the required dependencies and plugins. Subsequent runs can reuse the cache. **Having Maven cached does not guarantee an offline build will succeed**: the local repository can still lack dependencies or Maven plugins.

Some wrapper versions support `distributionSha256Sum` to verify the downloaded distribution; wrapper-JAR types can use `wrapperSha256Sum`. Hashes must come from trusted release sources, not invented placeholder values. Use HTTPS and trusted repositories/mirrors; if a checksum fails to match, investigate the cause rather than disabling verification.

The wrapper pins Maven, while:
- **JDK**: installed on the machine/CI, optionally standardized via toolchains or project conventions.
- **Dependencies**: declared in `pom.xml`, parent/BOM, and dependency management.
- **Maven plugins**: managed by the POM, parent, and plugin management.
- **Wrapper scripts/bootstrap**: source-controlled files in the project; they have their own version separate from the Maven distribution.

## 8. Using the Maven Wrapper in CI

For consistent builds across developer machines and CI:

1. Commit `mvnw`, `mvnw.cmd`, `.mvn/wrapper`, and `pom.xml` to the repository.
2. Preserve the executable bit of `mvnw` in Git so Linux runners can execute it.
3. Configure the proper JDK; use the wrapper as the main Maven command.
4. Ensure the environment has access to the Maven distribution and dependency repositories (or has cache/mirrors ready).
5. Run `verify` or an equivalent test target before publishing artifacts.

Example GitHub Actions workflow for a Java 17 project with the wrapper, saved at `.github/workflows/build.yml`:

```yaml
name: Java build

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Build with Maven Wrapper
        run: ./mvnw -B -ntp verify
```

`setup-java` provides the JDK; `mvnw` provides the project's Maven version. Caching the local Maven repository saves time, though it does not replace pinning the Maven version or verifying artifacts. This example assumes `mvnw`'s executable bit is properly stored in the repository.

## 9. Common Errors and Diagnosis

| Symptom | Concept to Check | Resolution |
|---|---|---|
| `./mvnw: Permission denied` | Unix script execute permission | `chmod +x mvnw`; save executable bit in Git |
| `./mvnw: No such file or directory` | Wrong directory, missing script, shebang/CRLF | Run from root; inspect files and LF line endings |
| PowerShell does not recognize `mvnw.cmd` | Current-directory execution rule | Use `.\mvnw.cmd` |
| `JAVA_HOME is not defined correctly` or Java not found | JDK/`JAVA_HOME`/`PATH` | Check `java -version`, `javac -version`, and compatible JDK |
| Maven distribution download fails | `distributionUrl`, proxy, network, TLS/mirror | Verify URL, connectivity, and network configuration |
| Maven starts but `Could not resolve ...` | Dependencies/plugins/repositories | Check `pom.xml`, `settings.xml`, repositories, and dependency cache |
| `mvn -version` differs from `./mvnw -version` | System Maven vs pinned Maven | Check `distributionUrl` and project configuration |
| Reports missing `maven-wrapper.jar` | Missing bootstrap file or wrong wrapper type | Check `bin`/`script`/`source` type and accompanying files |
| Checksum mismatch | Downloaded file differs from expected checksum | Cross-check URL and hash from trusted source; do not bypass verification |
| Offline run fails | Missing distribution or dependencies in cache | Populate cache/mirror and retry after downloading everything needed |
| `java -jar` reports no main manifest attribute | JAR was not packaged as an executable JAR | Check `Main-Class` or Spring Boot `repackage` |

When diagnosing, you can enable Maven debug logging:

```bash
./mvnw -X validate
```

To print extra **wrapper bootstrap** diagnostics on Linux/macOS:

```bash
MVNW_VERBOSE=true ./mvnw -version
```

Or in Windows PowerShell:

```powershell
$env:MVNW_VERBOSE = 'true'
.\mvnw.cmd -version
Remove-Item Env:MVNW_VERBOSE
```

Debug logs may contain internal repository URLs or environment variables; review them before sharing.

## 10. Post-Lesson Self-Check

- Confirm `mvnw`, `mvnw.cmd`, `.mvn/wrapper/maven-wrapper.properties`, and `pom.xml` are all present in the project root.
- Use the right script for the OS from the project root; in PowerShell remember `.\`.
- `-version` shows the pinned Maven version; the JDK fits the application.
- `clean verify` or `clean package` succeeds without bootstrap, dependency, or compilation errors.
- Commit wrapper files and execute permission in Git so the whole team and CI share them.
- For Spring Boot, configure the packaging plugin if you want `java -jar` to launch an executable JAR.

**How to remember it:** `mvnw` and `mvnw.cmd` are two ways to launch the **project-configured Maven**. They standardize Maven across machines; meanwhile the JDK, dependencies, plugins, classpath, and artifact type remain governed by the environment and POM.

**Official documentation:**
- [Apache Maven Wrapper](https://maven.apache.org/tools/wrapper/)
- [Maven Wrapper Plugin — Usage](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html)
- [Maven Wrapper Plugin — wrapper goal](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/wrapper-mojo.html)
