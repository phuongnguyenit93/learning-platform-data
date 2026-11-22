# Machine-Dependent Scripts in Java Tooling

## 1. What is this anti-pattern?

A **machine-dependent script** is a script that only runs properly on the author's machine because it silently relies on configurations, software, paths, permissions, or state specific to that machine.

Common examples:

- Calling `mvn` from `PATH` and accidentally using a Maven version only installed on the author's machine.
- Hardcoding `C:/Users/An/...`, `/Users/an/...`, or `/home/an/...`.
- Assuming the current directory is always the repository root directory.
- Relying on the JDK selected by the IDE, while CI uses a different JDK.
- Reading configuration files from the Desktop, home directory, or a directory outside the repository without declaring it.
- Using environment variables that exist on a personal machine but are not configured in CI.
- Depending on a shell profile, alias, global package, or manually installed executable.
- Relying on caches, temporary files, services, or credentials left over from a previous run.

A script may run successfully for months on one machine and fail immediately when a teammate clones the repository, CI spins up a new runner, or the project moves to another Windows/Linux machine.

The goal of fixing this anti-pattern is to make inputs, tools, paths, and execution conditions explicitly declared, verifiable, and reproducible.

## 2. Warning signs

A script risks being machine-dependent if any of the following signs appear:

| Sign | Why it is risky |
|---|---|
| Path contains a username | Other machines have different home directories. |
| Calling `mvn`, `java`, or `node` without checking the version | `PATH` may pick a different executable. |
| Using relative paths from the current directory | Results vary depending on where the script is invoked. |
| Reading files outside the repository | The file may not exist on a new machine or in CI. |
| Relying on `~/.m2/settings.xml` for required information | CI or other machines do not have the same configuration. |
| Not declaring encoding, timezone, or locale | Output may differ by operating system and environment. |
| Only works after having already built once | It may be relying on stale output/cache. |
| Requires running with Administrator/root privileges | It may be writing to system directories or using overly broad permissions. |
| Using secrets in local files | Other machines lack the secret, or the secret gets exposed if committed. |

A strong indicator is the answer to the question: "If you clear the cache, clone the repository into a new directory with spaces in its name, and run it on a fresh runner, will the script still work?"

## 3. Types of hidden dependencies

| Dependency type | Example | How to handle |
|---|---|---|
| User identity | `user.name`, home directory | Do not use to locate fixed source or output paths. |
| Working directory | `.` or `../config` | Determine the project root from the script's location or pass it as an argument. |
| Tool installation | Globally installed Maven/JDK | Maven Wrapper, JDK version policy, and Toolchains. |
| PATH precedence | Multiple `java` installations | Check `JAVA_HOME`, version, and the selected executable. |
| Shell | Bash, PowerShell, cmd | Choose the shell explicitly and provide appropriate scripts. |
| Operating system | Windows/Linux/macOS | Use path APIs and test across OSes. |
| Encoding | ANSI, UTF-8, default charset | Specify UTF-8 in source, build, and file I/O. |
| Locale/timezone | Decimal separator, dates, UTC offset | Use explicit locale and timezone. |
| File system | Case sensitivity, permissions | Standardize filenames and test on target OSes. |
| Network | Proxy, repository credentials | Declare mirrors and inject credentials. |
| Local state | Cache, temp files, daemon | Cache is only an optimization; the build must run from a clean state. |

## 4. Inventory the environment before fixing

First, record what the script actually uses. Do not guess from the author's machine.

On Windows PowerShell:

~~~powershell
$PSVersionTable.PSVersion
Get-Command java, javac, mvn, git -ErrorAction SilentlyContinue |
    Select-Object Name, Source
java -version
javac -version
if ($env:JAVA_HOME) { Write-Output $env:JAVA_HOME }
Get-Location
Get-Culture
Get-TimeZone
~~~

On Bash:

~~~bash
printf 'shell=%s\n' "$SHELL"
command -v java
command -v javac
command -v mvn
java -version
javac -version
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
pwd
locale
date +%Z
~~~

In Java, you can print useful system properties for diagnostics:

~~~java
System.out.println("java.version=" + System.getProperty("java.version"));
System.out.println("java.vendor=" + System.getProperty("java.vendor"));
System.out.println("os.name=" + System.getProperty("os.name"));
System.out.println("os.arch=" + System.getProperty("os.arch"));
System.out.println("user.dir=" + System.getProperty("user.dir"));
System.out.println("user.home=" + System.getProperty("user.home"));
System.out.println("file.separator=" + System.getProperty("file.separator"));
System.out.println("path.separator=" + System.getProperty("path.separator"));
~~~

Only log non-sensitive information. Do not dump the entire environment, as that could expose tokens or credentials.

## 5. Do not hardcode home directories and usernames

Non-portable example:

~~~powershell
$project = "C:/Users/An/source/payment-service"
$java = "C:/Program Files/Java/jdk-17/bin/java.exe"
$config = "C:/Users/An/Desktop/release.properties"
~~~

On Linux, similar paths might be `/home/an/...`; on macOS, they might be `/Users/an/...`. There is no reason for a repository to depend on those values.

Distinguish between three types of paths:

- **Project path:** derived from the repository or script location.
- **User configuration path:** obtained from an environment variable or home directory when it is genuinely user-specific configuration.
- **Temporary path:** obtained from an OS API or environment variable.

Do not replace one personal path with another absolute path and call it portable. `C:/Java/jdk-17` or `/opt/jdk-17` is still a machine-specific assumption if hardcoded into a shared POM or script.

## 6. Determine the project root from the script location

The current working directory is where the process is invoked from, not necessarily where the script resides.

A Bash script can be invoked from any directory. Determine the directory containing the script and then derive the project root:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

"$PROJECT_ROOT/mvnw" -B -ntp -f "$PROJECT_ROOT/pom.xml" clean verify
~~~

In this example, `build.sh` is in `scripts/`, while `pom.xml` is in the parent directory.

All variables are quoted so that paths with spaces remain a single argument. `CDPATH=` prevents the shell profile from altering the result of `cd`.

If the script can be invoked via a symbolic link, decide explicitly whether the link needs to be resolved to its real location. Do not assume every repository is invoked through the same type of path.

## 7. Use `$PSScriptRoot` in PowerShell

PowerShell provides `$PSScriptRoot` to get the directory containing the script file.

~~~powershell
$ErrorActionPreference = "Stop"

$scriptDirectory = $PSScriptRoot
$projectRoot = Split-Path -Parent $scriptDirectory
$pom = Join-Path $projectRoot "pom.xml"
$wrapper = Join-Path $projectRoot "mvnw.cmd"

if (-not (Test-Path -LiteralPath $pom)) {
    throw "POM not found: $pom"
}

Push-Location $projectRoot
try {
    & $wrapper -B -ntp clean verify
    if ($LASTEXITCODE -ne 0) {
        throw "Maven failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
~~~

`Join-Path` builds paths according to the operating system. `Push-Location` and `Pop-Location` ensure the current directory is restored even if the build fails.

`$ErrorActionPreference = "Stop"` makes PowerShell stop on cmdlet errors. Native commands like `java.exe` or `mvnw.cmd` have their own exit codes; you must check `$LASTEXITCODE`.

## 8. Distinguish project path, user home, and current directory in Java

Java provides different system properties:

| Property | Meaning |
|---|---|
| user.dir | Working directory of the process. |
| user.home | Home directory of the running user. |
| user.name | Account name of the process. |
| java.home | Runtime home of the JVM. |
| file.separator | Path component separator. |
| path.separator | Classpath element separator. |
| line.separator | Line separator of the environment. |
| os.name, os.arch | Operating system and architecture. |

`user.dir` can vary across terminals, IDEs, services, and CI. Therefore, do not assume project files always live under `user.dir`.

`user.home` is appropriate for user-specific configuration/cache data when the application genuinely needs to store it there. Do not use it to locate source code or required project files.

If the application needs a configuration file, accept the path via a CLI option or environment variable. If a resource is packaged inside a JAR, read it from the classpath using `getResource` instead of looking for a file next to the working directory.

## 9. Use `Path` and `Files` instead of path string concatenation

Do not construct paths using string concatenation:

~~~java
String output = System.getProperty("user.home") + "/build/output.txt";
~~~

This approach depends on the file separator and the home directory.

Use Java NIO:

~~~java
import java.nio.file.Path;

Path project = Path.of("project");
Path output = project.resolve("build").resolve("output.txt");
Path normalized = output.toAbsolutePath().normalize();
~~~

`Path.resolve` combines path components according to the file system's rules. `normalize` removes redundant `.` and `..` elements lexically; it does not replace permission or symbolic link checks.

For file I/O, specify the charset:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("build", "result.txt");
Files.createDirectories(file.getParent());
Files.writeString(file, "Build complete\n", StandardCharsets.UTF_8);

String content = Files.readString(file, StandardCharsets.UTF_8);
System.out.println(content);
~~~

In a real application, input paths must be validated against the allowed write scope. Do not allow a user-controlled path to escape the intended output directory.

## 10. Pin the Maven version with Maven Wrapper

Do not require every developer to install Maven manually and add an arbitrary version to `PATH`.

Maven Wrapper stores the Maven version in the repository and provides scripts for Unix and Windows. When the corresponding distribution is not yet present, the wrapper downloads and installs it into the user's cache.

Initialize the wrapper using the Maven Wrapper Plugin:

~~~bash
mvn org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.12 -Dtype=only-script
~~~

Important files:

~~~text
.mvn/
  wrapper/
    maven-wrapper.properties
mvnw
mvnw.cmd
~~~

The `.mvn/wrapper/maven-wrapper.properties` file may contain:

~~~properties
wrapperVersion=3.3.4
distributionType=only-script
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.12/apache-maven-3.9.12-bin.zip
~~~

Usage:

~~~bash
./mvnw -B -ntp clean verify
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd -B -ntp clean verify
~~~

`only-script` uses wrapper scripts to download the Maven distribution. Other distribution types may bundle a wrapper JAR or downloader source.

Maven Wrapper pins Maven; it does not install a JDK automatically. The machine running the build must still have a compatible JDK. The distribution URL and checksum should be managed as input dependencies; you can declare `distributionSha256Sum` in the wrapper properties after obtaining the official SHA-256 of the distribution.

## 11. Verify the JDK instead of trusting `PATH`

On a machine with multiple JDKs, `java` and `javac` can come from different directories.

Windows:

~~~powershell
Get-Command java, javac | Select-Object Name, Source
$env:JAVA_HOME
java -version
javac -version
.\mvnw.cmd -version
~~~

Bash:

~~~bash
command -v java
command -v javac
printf '%s\n' "$JAVA_HOME"
java -version
javac -version
./mvnw -version
~~~

`JAVA_HOME` should point to the selected JDK. `PATH` should place that JDK's `bin` directory ahead of other versions.

Do not hardcode one developer's JDK path into a script. Each machine or CI runner may install the JDK in a different location.

## 12. Use Maven Enforcer to fail early

If a project requires JDK 17 or higher, declare that requirement in the POM instead of letting compiler errors appear mid-build.

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-enforcer-plugin</artifactId>
      <version>3.5.0</version>
      <executions>
        <execution>
          <id>require-supported-java</id>
          <goals>
            <goal>enforce</goal>
          </goals>
          <configuration>
            <rules>
              <requireJavaVersion>
                <version>[17,)</version>
              </requireJavaVersion>
            </rules>
          </configuration>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

`[17,)` accepts JDK 17 and above. If the build must run with the exact JDK 17 compiler, use the range `[17,18)` and configure Toolchains as shown in the next section.

`maven.compiler.release` controls the language level, bytecode target, and Java platform API that the compiler allows. It does not mean Maven itself is running on JDK 17.

## 13. Use Maven Toolchains when a specific compiler JDK is needed

Maven can run on one JDK while delegating the compiler and toolchain-aware plugins to another JDK.

In the POM, declare the logical requirement:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-toolchains-plugin</artifactId>
  <version>3.3.0</version>
  <executions>
    <execution>
      <goals>
        <goal>toolchain</goal>
      </goals>
      <configuration>
        <toolchains>
          <jdk>
            <version>[17,18)</version>
          </jdk>
        </toolchains>
      </configuration>
    </execution>
  </executions>
</plugin>
~~~

Each machine declares the JDK location in its own `~/.m2/toolchains.xml` file:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
      <vendor>temurin</vendor>
    </provides>
    <configuration>
      <jdkHome>/opt/jdks/temurin-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

`jdkHome` is the actual installation path on that specific machine. This file lives outside the repository; do not commit local paths into the POM.

In CI, the JDK setup action can generate a Maven Toolchains entry for the installed JDK. If no matching toolchain is found, the build should fail early with a clear error.

## 14. Pin dependencies and Maven plugins

A script can behave differently if Maven resolves different dependency or plugin versions on its own.

Rules:

- Declare explicit versions for plugins used in the build.
- Use `pluginManagement` in the parent POM to manage versions consistently.
- Use `dependencyManagement` to control dependency versions.
- Avoid version ranges, `LATEST`, `RELEASE`, and `SNAPSHOT` in stable releases.
- Use Maven Wrapper to pin the Maven distribution.
- Verify which repository/mirror is used to resolve dependencies.
- Review version updates and re-run CI.

Example of pinning the compiler plugin:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.13.0</version>
  <configuration>
    <release>17</release>
    <encoding>UTF-8</encoding>
  </configuration>
</plugin>
~~~

Do not rely on plugins installed globally in the local Maven directory. The build must resolve plugins from the configured repositories.

## 15. Separate application configuration from source code

Do not embed endpoints, output paths, account names, or credentials in Java source code and scripts.

Use CLI options or environment variables:

~~~powershell
$env:APP_MESSAGE = "portable build"
.\mvnw.cmd -B -ntp clean verify
java -jar target\portable-script-demo-1.0.0.jar build-output
~~~

~~~bash
export APP_MESSAGE="portable build"
./mvnw -B -ntp clean verify
java -jar target/portable-script-demo-1.0.0.jar build-output
~~~

The application should validate required variables on startup. If any are missing, report the name of the variable that needs to be configured and exit with a non-zero exit code.

Environment variables are suitable for runtime configuration and injected secrets. For complex configurations, use a config file passed via a CLI option such as `--config`; do not automatically search for files on the Desktop or in the home directory.

## 16. Manage secrets properly

Do not commit:

- Passwords, API tokens, or private keys.
- `settings.xml` files containing real credentials.
- Personal `.env` files.
- Certificates or private signing keys.
- Full environment dumps.

Use your CI's secret manager or your organization's secret management system. Grant permissions per job and pass secrets only to the steps that need them.

GitHub Actions example:

~~~yaml
- name: Publish package
  run: ./mvnw -B -ntp deploy
  env:
    PUBLISH_TOKEN: ${{ secrets.PUBLISH_TOKEN }}
~~~

In the script, read `PUBLISH_TOKEN` from the environment and check that it has a value. Do not print the token to logs and do not pass the token as a command-line argument if the process list can expose arguments.

If Maven credentials are required, generate `settings.xml` in CI's temporary workspace or use an action that configures Maven settings. Do not put credentials in the POM.

## 17. Do not assume the current working directory

The following snippet is error-prone:

~~~bash
mvn -f ../pom.xml clean verify
cp config/app.properties target/
~~~

The result depends on the directory from which the command is invoked.

Determine the project root once and use explicit paths:

~~~bash
PROJECT_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
"$PROJECT_ROOT/mvnw" -B -ntp -f "$PROJECT_ROOT/pom.xml" clean verify
cp "$PROJECT_ROOT/config/app.properties" "$PROJECT_ROOT/target/"
~~~

In GitHub Actions, you can declare `working-directory` for individual steps or the entire job. Even so, scripts reused outside CI should still locate the project root themselves or accept an explicit path.

## 18. Encoding, locale, and timezone

A script running on a personal machine may rely on the current default encoding, locale, or timezone.

With Java 17, the default encoding can depend on the environment. Specify UTF-8 in the POM:

~~~xml
<properties>
  <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

When reading/writing files, use `StandardCharsets.UTF_8`:

~~~java
Files.writeString(path, content, StandardCharsets.UTF_8);
String content = Files.readString(path, StandardCharsets.UTF_8);
~~~

When parsing/formatting non-user-facing data, use `Locale.ROOT` instead of the default locale. For timestamps used in logs or artifact metadata, prefer UTC and `Instant`/`ZoneOffset.UTC`.

Do not compare date/time strings formatted according to the machine's locale. Use ISO-8601 or an explicitly specified format.

## 19. Handling temporary files and permissions

Do not write to a fixed directory such as `/tmp/my-build`, `C:/temp/build`, or the user's Desktop. Two parallel runs can overwrite each other, and other machines may not have that directory.

Java provides APIs to create temporary directories:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;

Path temporaryDirectory = Files.createTempDirectory("java-build-");
Path temporaryFile = Files.createTempFile(temporaryDirectory, "report-", ".txt");
~~~

Use `try/finally` or an appropriate cleanup mechanism to delete temporary files when finished. If a file must persist after the process exits, save it in the passed-in output directory and document its location.

Do not require Administrator/root privileges unless necessary. The build should write to the workspace, `target/`, or a directory with explicitly granted permissions.

## 20. Quoting and passing arguments across shells

Shells have different parsing rules. Paths containing spaces, parentheses, or special characters are easily split into multiple arguments.

Bash:

~~~bash
java -jar "$PROJECT_ROOT/target/app.jar" "$APP_MESSAGE"
~~~

PowerShell:

~~~powershell
& java -jar $jarPath $Message
~~~

PowerShell uses the call operator `&` to invoke an executable via a path stored in a variable. When multiple dynamic options are needed, pass arguments as an array rather than concatenating a command string and running it through `Invoke-Expression`.

Avoid `eval`, `Invoke-Expression`, and string-built commands if inputs can contain special characters. Always quote variables in Bash and use `Join-Path` for Windows paths.

## 21. Line endings and the executable bit

Git can check out files with different line endings depending on configuration. Bash scripts typically require LF; `.cmd` and `.ps1` files are typically handled using Windows conventions.

You can add a `.gitattributes` file:

~~~gitattributes
* text=auto
*.sh text eol=lf
*.cmd text eol=crlf
*.ps1 text eol=crlf
~~~

On Unix, wrapper scripts need the executable bit:

~~~bash
chmod +x mvnw
git update-index --chmod=+x mvnw
~~~

Use `mvnw.cmd` in Windows PowerShell and `./mvnw` in Bash. If a Bash script reports `bad interpreter` or `^M` errors, check line endings and the executable bit before editing the script's content.

## 22. File system and architecture differences

Windows is generally case-insensitive for filenames by default, whereas Linux is generally case-sensitive.

For example, an import or resource lookup for `Config.properties` may work on Windows but fail on Linux if the actual file is `config.properties`.

In addition, pay attention to:

- Different path separators.
- Different file permissions and executable bits.
- Symlinks may require special permissions or configuration on Windows.
- Filenames may contain characters unsupported on some file systems.
- Native libraries must match the OS and architecture.
- Case-only renames may not be recorded as expected on case-insensitive file systems.

Java bytecode generally runs across multiple operating systems, but JNI/native executables and external non-Java tools can still be platform-dependent. If there are native dependencies, test on the exact target OS and architecture.

## 23. Network, proxy, and dependency repositories

A script might only work on a personal machine because that machine already has a proxy, VPN, credentials, or cached dependencies configured.

Clarify the following:

- Whether Maven Central or an internal mirror is the dependency source.
- Whether a proxy is required.
- Where repository credentials are injected.
- Whether the build requires internet access on every run.
- Which dependencies must be mirrored internally for long-term builds.
- Whether checksums/signatures are verified for downloaded tools.

Do not hardcode proxy hostnames, tokens, or repository passwords into scripts. Use Maven `settings.xml`, environment variables, or a secret manager.

An offline build only succeeds if all dependencies and plugins are already in the local repository. `mvn -o` is not a fix for a build missing dependencies; it is only useful after all inputs have been prepared.

## 24. Cache is an optimization, not a prerequisite

The Maven local repository is typically located in `~/.m2/repository`; the Gradle cache is typically in `~/.gradle/caches`.

Caches can be deleted, modified, or differ between machines. Therefore:

- A clean build must resolve dependencies from the declared repositories.
- Cache keys should depend on the OS, architecture, POM/Gradle files, and wrapper properties.
- A cache miss should only slow down the build, not change its output.
- Do not store the sole release output in a cache.
- Do not rely on stale files in `target/` to mask build failures.

To test cache independence, run a clean build on a fresh runner or with an empty local repository. You can use the Maven option `-Dmaven.repo.local=<temporary-path>` in a separate test run.

## 25. Containers and Dev Containers

When a team needs the same OS image, JDK, Maven, and system packages, containers or Dev Containers can be used.

Containers help package user-space tools and system dependencies. They do not automatically guarantee reproducible builds if image tags drift, dependencies are unpinned, or build scripts still read files from the host.

Best practices:

- Pin base images by version and digest.
- Explicitly specify JDK/Maven versions.
- Do not copy credentials into image layers.
- Mount the source workspace with a clear structure.
- Do not depend on personal files located on the host.
- Grant minimal permissions to the container.
- Keep caches in a separate volume that can be deleted and recreated.
- Test container builds in CI.

If using a Dev Container, `devcontainer.json` should be committed so the whole team shares the configuration. Machine-specific credentials are still provided outside the repository.

## 26. CI matrix to catch machine-specific dependencies

A build that only runs on Windows is not enough to prove that Bash scripts or Linux paths work. Use a CI matrix covering the operating systems and JDKs that need to be supported.

GitHub Actions example:

~~~yaml
name: Portable Java build

on:
  push:
  pull_request:

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: "17"
          cache: maven

      - name: Build on Unix
        if: runner.os != 'Windows'
        shell: bash
        env:
          APP_MESSAGE: portable build from CI
        run: ./scripts/build.sh

      - name: Build on Windows
        if: runner.os == 'Windows'
        shell: pwsh
        env:
          APP_MESSAGE: portable build from CI
        run: ./scripts/build.ps1
~~~

The example uses version tags for readability. Production workflows should pin actions to a reviewed full commit SHA. You can add a JDK matrix if the product supports multiple Java releases.

GitHub Actions allows configuring `shell` and `working-directory` explicitly. The default shell differs between Windows and Unix; do not rely on default behavior when a script needs to run across multiple operating systems.

## 27. Portable Maven project example

Project structure:

~~~text
portable-script-demo/
  .mvn/
    wrapper/
      maven-wrapper.properties
  scripts/
    build.sh
    build.ps1
  src/
    main/
      java/
        example/
          PortableDemo.java
  .gitattributes
  .gitignore
  mvnw
  mvnw.cmd
  pom.xml
~~~

Sample POM:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example.portable</groupId>
  <artifactId>portable-script-demo</artifactId>
  <version>1.0.0</version>

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
        <configuration>
          <release>17</release>
          <encoding>UTF-8</encoding>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
        <configuration>
          <archive>
            <manifest>
              <mainClass>example.PortableDemo</mainClass>
            </manifest>
          </archive>
        </configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-enforcer-plugin</artifactId>
        <version>3.5.0</version>
        <executions>
          <execution>
            <id>require-supported-java</id>
            <goals>
              <goal>enforce</goal>
            </goals>
            <configuration>
              <rules>
                <requireJavaVersion>
                  <version>[17,)</version>
                </requireJavaVersion>
              </rules>
            </configuration>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
~~~

The POM pins the compiler, JAR, and Enforcer plugins. `maven.compiler.release` specifies Java 17 as the target; Enforcer verifies that the JDK running Maven meets the minimum requirement.

## 28. Java program using passed-in environment and path

File `src/main/java/example/PortableDemo.java`:

~~~java
package example;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class PortableDemo {
    public static void main(String[] args) throws IOException {
        String message = System.getenv("APP_MESSAGE");
        if (message == null || message.isBlank()) {
            throw new IllegalStateException("APP_MESSAGE is required");
        }
        if (args.length != 1 || args[0].isBlank()) {
            throw new IllegalArgumentException("Pass an output directory");
        }

        Path outputDirectory = Path.of(args[0]).toAbsolutePath().normalize();
        Files.createDirectories(outputDirectory);
        Path outputFile = outputDirectory.resolve("build-info.txt");

        String expected = message + System.lineSeparator();
        Files.writeString(outputFile, expected, StandardCharsets.UTF_8);

        String saved = Files.readString(outputFile, StandardCharsets.UTF_8);
        if (!expected.equals(saved)) {
            throw new IOException("Output verification failed");
        }

        System.out.println("message=" + message);
        System.out.println("output=" + outputFile.getFileName());
    }
}
~~~

The program receives the message via an environment variable and the output directory via a CLI argument. `Path` handles paths according to the OS; `Files` creates the directory and file; UTF-8 is explicitly specified.

It does not look for output on the Desktop, in the home directory, or in the current working directory. The calling script passes the output path based on the project root.

## 29. Complete Bash script

File `scripts/build.sh`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

if ! printenv APP_MESSAGE >/dev/null; then
  echo "Set APP_MESSAGE before running this script." >&2
  exit 2
fi

"$PROJECT_ROOT/mvnw" -B -ntp -f "$PROJECT_ROOT/pom.xml" clean verify

java -jar \
  "$PROJECT_ROOT/target/portable-script-demo-1.0.0.jar" \
  "$PROJECT_ROOT/build-output"
~~~

Run:

~~~bash
APP_MESSAGE="portable build" ./scripts/build.sh
~~~

If the shell does not accept inline variable assignment before the command, export it beforehand:

~~~bash
export APP_MESSAGE="portable build"
./scripts/build.sh
~~~

The script finds the project root from its own location, invokes Maven Wrapper using an absolute path, quotes arguments, and stops if the build or Java process fails.

## 30. Complete PowerShell script

File `scripts/build.ps1`:

~~~powershell
param(
    [Parameter()]
    [string]$Message = $env:APP_MESSAGE
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($Message)) {
    throw "Set APP_MESSAGE or pass -Message before running this script."
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$wrapper = Join-Path $projectRoot "mvnw.cmd"
$jar = Join-Path $projectRoot "target\portable-script-demo-1.0.0.jar"
$outputDirectory = Join-Path $projectRoot "build-output"

if (-not (Test-Path -LiteralPath $wrapper)) {
    throw "Maven Wrapper is missing: $wrapper"
}

Push-Location $projectRoot
try {
    & $wrapper -B -ntp clean verify
    if ($LASTEXITCODE -ne 0) {
        throw "Maven Wrapper build failed with exit code $LASTEXITCODE"
    }

    $env:APP_MESSAGE = $Message
    & java -jar $jar $outputDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "Java application failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
~~~

Run:

~~~powershell
$env:APP_MESSAGE = "portable build"
.\scripts\build.ps1
~~~

Or pass directly:

~~~powershell
.\scripts\build.ps1 -Message "portable build"
~~~

The script uses `$PSScriptRoot`, `Join-Path`, `Push-Location`, and `Pop-Location`. Exit codes of native processes are checked explicitly.

## 31. Git attributes and ignore rules

File `.gitattributes`:

~~~gitattributes
* text=auto
*.sh text eol=lf
*.cmd text eol=crlf
*.ps1 text eol=crlf
~~~

File `.gitignore` may contain:

~~~gitignore
target/
build-output/
.env
.env.*
!.env.example
*.log
~~~

Do not ignore `.mvn/wrapper`, `mvnw`, `mvnw.cmd`, the POM, or required build scripts. Wrapper files and version configurations must be committed so others can use the same build tool.

## 32. Testing in a clean environment

A good test suite should check multiple conditions rather than only running on a development machine:

1. Clone the repository into a new directory.
2. Name the directory with spaces.
3. Invoke the script from a different working directory.
4. Use the exact declared JDK version.
5. Use Maven Wrapper, not global Maven.
6. Run `clean verify` to remove stale outputs.
7. Clear caches in a separate test run.
8. Verify that the script stops properly when required environment variables are missing.
9. Run on supported OSes/architectures.
10. Verify output files, encoding, permissions, and exit codes.
11. Re-run to detect state dependencies from the previous run.
12. Log tool versions and commit SHA in CI logs.

A single successful build with a warm cache only proves that specific environment currently works. A clean runner and a cache miss are what uncover hidden dependencies.

## 33. Diagnosing "works on my machine" failures

| Symptom | Common cause | Check |
|---|---|---|
| `mvn` runs locally, but CI cannot find it | Maven is only installed globally on a personal machine. | Commit Maven Wrapper and invoke `mvnw`. |
| Wrong Java version | `PATH` or `JAVA_HOME` points to a different JDK. | `java -version`, `javac -version`, `mvnw -version`. |
| File not found | Script assumes the current working directory. | Print `pwd`/`Get-Location`; use script root. |
| Works on Windows, fails on Linux | Paths, case sensitivity, permissions, or shell. | Test on an OS matrix and standardize filenames. |
| Garbled non-ASCII/Vietnamese text | Inconsistent default encoding. | UTF-8 in POM and file I/O. |
| Different timestamps | Default timezone or locale. | Use UTC and `Locale.ROOT`. |
| CI cannot download dependencies | Proxy, mirror, or credentials only exist locally. | Check Maven settings and secret injection. |
| Build only works on the second run | Relies on stale output/cache. | `clean verify` on a clean runner. |
| Bash reports `bad interpreter` | CRLF line endings or missing executable bit. | Check `.gitattributes`, LF, and `chmod +x`. |
| Output written to the wrong directory | Path based on `.` or `user.dir`. | Pass an explicit output path. |
| Windows picks the wrong executable | Multiple tool versions in `PATH`. | `Get-Command`, check `JAVA_HOME`. |
| Build depends on IDE | IDE configures JDK or profiles automatically. | Run the wrapper from a clean terminal and CI. |

## 34. Checklist for eliminating machine dependencies

- [ ] No personal usernames or home paths in source, POM, or scripts.
- [ ] Scripts determine the project root from their own location or accept an explicit path.
- [ ] Paths containing spaces are properly quoted.
- [ ] Maven Wrapper and Maven version are pinned.
- [ ] Minimum JDK version is enforced with Enforcer.
- [ ] Compiler JDK is selected with Toolchains when needed.
- [ ] Dependency and plugin versions are explicitly declared.
- [ ] `JAVA_HOME` and `PATH` are checked during diagnostics.
- [ ] Runtime configuration is passed via CLI/environment.
- [ ] Secrets are retrieved from a secret manager, never committed.
- [ ] Paths are constructed using `Path`/`Files` or `Join-Path`.
- [ ] UTF-8 encoding is explicitly specified.
- [ ] Locale and timezone are controlled.
- [ ] Temp files are created via OS APIs or temp directories.
- [ ] Shell, line endings, and executable bits are configured.
- [ ] Build does not require admin/root privileges beyond actual need.
- [ ] Network, proxy, and repositories are declared.
- [ ] Cache can be deleted and the build still succeeds.
- [ ] CI runs on all target OSes/JDKs.
- [ ] A clean build from a new directory produces the expected output.

## 35. Sample project verification results

The sample project was created in a temporary directory with spaces in its name. Maven Wrapper was generated using Maven Wrapper Plugin 3.3.4 and pinned to the Maven 3.9.12 distribution.

Wrapper verification:

~~~text
Apache Maven 3.9.12
Java version 17.0.15
~~~

The project was built with Amazon Corretto JDK 17.0.15, Maven Compiler Plugin 3.13.0, Maven JAR Plugin 3.4.2, and Maven Enforcer Plugin 3.5.0. `maven.compiler.release` was set to 17.

Both PowerShell and Git Bash invoked the scripts from a working directory different from the project root. Both scripts located the project root accurately, ran Maven Wrapper, built the JAR, and executed the Java program successfully.

PowerShell output:

~~~text
BUILD SUCCESS
message=portable build on Java 17
output=build-info.txt
~~~

Git Bash output:

~~~text
BUILD SUCCESS
message=portable bash build on Java 17
output=build-info.txt
~~~

The class file has major version 61, corresponding to Java 17. The JAR was executed with Amazon Corretto 17.0.15 and generated `build-info.txt` in UTF-8. The project path contained spaces and did not break argument passing.

This was an actual test on Windows 11 with PowerShell and Git Bash, using JDK 17.0.15. It confirms that both sample scripts work in that environment; CI must still run on Linux/macOS if those operating systems are within the project's support scope.

## 36. References

- Apache Maven Wrapper: https://maven.apache.org/tools/wrapper/
- Apache Maven Wrapper Plugin Usage: https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html
- Apache Maven Toolchains Guide: https://maven.apache.org/guides/mini/guide-using-toolchains
- Maven Toolchains Plugin Usage: https://maven.apache.org/plugins/maven-toolchains-plugin/usage.html
- Java SE 17 System Properties: https://docs.oracle.com/en/java/javase/17/docs/api/system-properties.html
- Java SE 17 Path API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html
- Java SE 17 Files API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Java SE 17 StandardCharsets: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html
- GitHub Actions Workflow Syntax: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- GitHub Actions setup-java: https://github.com/actions/setup-java
- Git Attributes: https://git-scm.com/docs/gitattributes

A portable script must explicitly describe its tools, configuration, paths, and execution conditions. Pin the appropriate Maven/JDK versions, determine the project root from the script, pass configuration via environment or CLI, use Java NIO for file system operations, and verify the build with CI in a clean environment.