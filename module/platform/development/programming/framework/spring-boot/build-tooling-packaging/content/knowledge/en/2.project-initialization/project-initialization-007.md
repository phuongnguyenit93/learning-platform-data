# Running Your First Spring Boot Build from the Command Line on Windows and Linux

## 1. Objectives and Target Outcome

After this lesson, you will be able to open a terminal at the root directory of a newly initialized Spring Boot project, verify the JDK, run a build using the Gradle Wrapper or Maven Wrapper on Windows and Linux, interpret success/failure outputs, and locate the packaged file. You will also know how to test-run the application after building if the project is configured to produce an executable JAR.

A **build** is the process of using project configuration to fetch dependencies, compile code, process resources, run configured checks, and create artifacts. **Running the application** is a separate step: a successful build command does not prove the application can start in the current environment.

This lesson assumes you have already created or downloaded a Java Spring Boot project (for example, from Spring Initializr) containing source code, build configuration files, and the corresponding Wrappers. You do not need to open an IDE to follow along.

## 2. Identifying the Project and Preparing the Environment

Open the project root directory where the build configuration file resides. Do not run commands from the `src` folder alone or an arbitrary directory.

| Indicators in the Root Directory | Build Tool | Wrapper on Windows | Wrapper on Linux |
| --- | --- | --- | --- |
| `build.gradle` or `build.gradle.kts`, `settings.gradle[.kts]`, `gradlew`, `gradlew.bat` | Gradle | `gradlew.bat` | `./gradlew` |
| `pom.xml`, `mvnw`, `mvnw.cmd`, `.mvn/wrapper/` | Maven | `mvnw.cmd` | `./mvnw` |

A project chooses one of the two tools. **Only run the command set matching the project's build files**; do not run Maven commands on a Gradle-only project or vice versa.

Minimum prerequisites:

1. Install a **JDK**, not just a JRE. For Spring Boot 3.x, Java 17 is the minimum; check the Java/toolchain version your actual project requires. A newer project or specific organization may specify another JDK, such as 21.
2. The terminal can invoke `java` and `javac`. Set `JAVA_HOME` and `PATH` to the JDK in use if they are not configured properly.
3. Access to the Internet or an organization's cache/mirror so the Wrapper can download Gradle/Maven and dependencies on the first run.
4. The project directory contains the Wrapper scripts and corresponding Wrapper configuration files. The Wrapper ensures the exact build tool version declared by the project is used, without requiring a global Gradle/Maven installation.

Verify from any terminal:

~~~text
java -version
javac -version
~~~

The output should show available Java/Javac versions matching the desired JDK version. **Do not copy version numbers blindly from examples:** the right version is dictated by your project's configuration.

If you need to inspect environment variables:

~~~powershell
# Windows PowerShell
$Env:JAVA_HOME
Get-Command java
Get-Command javac
~~~

~~~bash
# Linux (bash)
printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
~~~

`JAVA_HOME` typically points to the JDK root directory (not the `bin` folder). After changing environment variables, open a new terminal and check again. If the project uses a Gradle Java toolchain, the JDK running Gradle and the JDK compiling code may differ by configuration; read specific error messages carefully.

## 3. Using the Wrapper Instead of Relying on a Pre-Installed Build Tool

The Wrapper is a launcher script for the Gradle/Maven version configured in the project:

- **Gradle:** `gradlew`, `gradlew.bat`, and `gradle/wrapper/gradle-wrapper.properties` (plus the Wrapper JAR).
- **Maven:** `mvnw`, `mvnw.cmd`, and `.mvn/wrapper/maven-wrapper.properties`.

On the first run, the Wrapper may download the distribution and dependencies and cache them; subsequent runs are usually faster. If the network is slow, pausing at a `Downloading` step is not automatically a Java error.

In **Windows PowerShell**, use Windows' `.\` prefix instead of `./` to invoke a script in the current directory: for example `.\gradlew.bat` or `.\mvnw.cmd`. In **Command Prompt (cmd.exe)** you can invoke `gradlew.bat` or `mvnw.cmd` directly. On **Linux**, use `./gradlew` or `./mvnw`; the `./` prefix is required when the current directory is not in `PATH`.

## 4. Your First Build with Gradle

Follow this section when the project has a `build.gradle` or `build.gradle.kts` file.

### 4.1 Windows PowerShell

Assuming the project directory is `C:\work\demo`; replace with your actual path:

~~~powershell
cd C:\work\demo
java -version
javac -version
.\gradlew.bat --version
.\gradlew.bat clean build
Get-ChildItem .\build\libs\
~~~

`--version` shows the Gradle version and JVM the Wrapper is actually using. `clean` removes old build outputs in the project's output folder; `build` runs the build lifecycle tasks, usually including compilation, tests, and packaging for typical Java/Spring Boot projects.

If using Windows **Command Prompt** instead of PowerShell:

~~~bat
cd /d C:\work\demo
gradlew.bat --version
gradlew.bat clean build
dir build\libs
~~~

`cd /d` also allows switching drive letters when needed.

### 4.2 Linux (bash)

~~~bash
cd ~/work/demo
java -version
javac -version
./gradlew --version
./gradlew clean build
ls -lh build/libs/
~~~

If the shell returns `Permission denied` when invoking the script, confirm you are in the right directory and grant execute permission **once**:

~~~bash
chmod +x gradlew
./gradlew clean build
~~~

If `build/libs/` does not exist, inspect the actual task output: library projects, parent modules, or custom builds may output artifacts elsewhere or lack a `bootJar` task.

### 4.3 Reading Gradle Output

An example of a successful build may end with:

~~~text
> Task :compileJava
> Task :test
> Task :bootJar

BUILD SUCCESSFUL in ...
~~~

This is an **illustrative log**, not fixed stdout. Displayed tasks depend on the project, Gradle may print `UP-TO-DATE` or `FROM-CACHE`, and durations will vary. What matters is the `BUILD SUCCESSFUL` line along with a zero exit code.

With standard Spring Boot Gradle plugin and Java plugin configuration, the `bootJar` task creates an executable JAR in `build/libs/`; there may also be a `-plain.jar` lacking the dependencies needed to run as a Spring Boot executable JAR. Pick the exact artifact generated rather than assuming every JAR name runs with `java -jar`.

## 5. Your First Build with Maven

Follow this section when the project has a `pom.xml`. The commands below are an **alternative** to Gradle, not an extra step required after Gradle.

### 5.1 Windows PowerShell

~~~powershell
cd C:\work\demo
java -version
javac -version
.\mvnw.cmd --version
.\mvnw.cmd clean package
Get-ChildItem .\target\
~~~

With **Command Prompt**:

~~~bat
cd /d C:\work\demo
mvnw.cmd --version
mvnw.cmd clean package
dir target
~~~

### 5.2 Linux (bash)

~~~bash
cd ~/work/demo
java -version
javac -version
./mvnw --version
./mvnw clean package
ls -lh target/
~~~

If you need to grant execute permission to the script:

~~~bash
chmod +x mvnw
./mvnw clean package
~~~

`clean` deletes old Maven outputs (usually `target/`). `package` runs preceding Maven lifecycle phases, typically including compilation and unit tests, and then creates the artifact. `verify` goes further than `package` in the lifecycle; `install` places the artifact into the local Maven repository and is **unnecessary for a first build**.

### 5.3 Reading Maven Output

Example tail of a successful build:

~~~text
[INFO] --- maven-compiler-plugin:...:compile ...
[INFO] --- maven-surefire-plugin:...:test ...
[INFO] --- maven-jar-plugin:...:jar ...
[INFO] BUILD SUCCESS
~~~

This only **illustrates log structure**; actual plugins, order, and line counts depend on `pom.xml`. When `spring-boot-maven-plugin` is configured to perform `repackage`, the main JAR in `target/` can be an executable Spring Boot JAR. If the plugin is not declared or not bound to the lifecycle, a Maven-generated `.jar` may be a standard Java JAR that cannot run standalone via `java -jar`.

## 6. Verifying Results: Successful Build, Artifact, and Test Run

Three layers of verification to distinguish:

| Level | Evidence | Conclusion |
| --- | --- | --- |
| 1. Build | Gradle shows `BUILD SUCCESSFUL` or Maven shows `BUILD SUCCESS`, process exits with code `0` | The build workflow completed per configuration and configured checks ran |
| 2. Artifact | A valid JAR/WAR file exists in `build/libs/` or `target/` (if the project packages one) | Packaged artifact was produced |
| 3. Runtime (optional) | Application starts and logs contain no startup errors | The artifact can run with the current configuration/environment |

To **test-run the executable JAR**, list artifacts first and replace the filename in the command below with the **actual name** observed. These are example filenames, not fixed paths for every project:

~~~powershell
# Windows PowerShell: choose one of the two, depending on Gradle or Maven project
java -jar .\build\libs\demo-0.0.1-SNAPSHOT.jar
java -jar .\target\demo-0.0.1-SNAPSHOT.jar
~~~

~~~bash
# Linux: choose one of the two, depending on Gradle or Maven project
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar
java -jar target/demo-0.0.1-SNAPSHOT.jar
~~~

**Run only the matching command.** Do not use `java -jar build/libs/*.jar` as a universal command across Windows and Linux: wildcards may not expand the way you expect in every shell, and the directory may contain both a plain JAR and a Boot JAR.

If the project is a Spring Boot web app with an embedded server and no custom port configured, you will usually see a startup success message and the server listening on port 8080. However, an app without a web starter may finish and exit, and a web app without a `/` route defined may return HTTP 404 even while the server is running. Test an endpoint **actually declared**; stop a running app with `Ctrl+C`.

You can run in development mode without building a JAR file using Gradle `bootRun` or Maven `spring-boot:run`, provided the corresponding plugin is applied:

~~~powershell
# Windows PowerShell: choose one
.\gradlew.bat bootRun
.\mvnw.cmd spring-boot:run
~~~

~~~bash
# Linux: choose one
./gradlew bootRun
./mvnw spring-boot:run
~~~

These are **application run commands**, not replacements for verifying `clean build` or `clean package`. A multi-module project may need to run the task/goal on a specific application module.

## 7. Common Errors During the First Build

| Symptom | Common Cause | Verification / Fix |
| --- | --- | --- |
| Windows: `java` not recognized; Linux: `java: command not found` | JDK not installed or wrong `PATH` | Install the right JDK, fix `JAVA_HOME` and `PATH`, open a new terminal; test `java -version`, `javac -version` |
| Wrapper not found | Wrong directory or project has no Wrapper | Return to the directory with `pom.xml`/`build.gradle`; check `mvnw.cmd`/`gradlew.bat` or `mvnw`/`gradlew`; only consider a pre-installed Maven/Gradle of the right version if the project provides no Wrapper |
| Linux: `Permission denied` | Script lacks execute permission | `chmod +x gradlew` or `chmod +x mvnw`, then re-run |
| Linux: `/bin/sh^M` or `bad interpreter` | Shell script had line endings converted to CRLF | Restore standard script file with LF from project source; check Git line-ending settings, do not tamper with the Wrapper JAR |
| `JAVA_HOME is set to an invalid directory`, `invalid source release`, JVM/Gradle incompatibility error | `JAVA_HOME`, toolchain, or Gradle/JDK version mismatch | Compare `java -version`, Wrapper `--version`, and project Java settings; use the compatible versions declared by the project |
| `Could not resolve`, `Connection timed out`, distribution/dependency download failure | Network, DNS, proxy, mirror, or blocked repository | Check Internet/proxy, Wrapper URL, repositories, and cache; do not default to blaming source code |
| `Compilation failed` / `COMPILATION ERROR` | Source code, dependency, or compiler configuration error | Read the first error line with file, line number, and cause; fix and rebuild |
| `There were failing tests` / `Tests run: ..., Failures: ...` | Failing tests or missing test environment | Inspect `build/reports/tests/test/` or `target/surefire-reports/`, fix test/fixture or config; do not treat skipping tests as a fully verified build |
| JAR exists but `no main manifest attribute` or `ClassNotFoundException` | Picked plain JAR by mistake, missing Spring Boot packaging plugin, or missing main class | Use the right Boot JAR and check `bootJar`/Spring Boot Maven `repackage` plus main class |
| Build succeeds, but running reports `Port 8080 was already in use` or missing env var | Runtime/configuration error, not a compilation error | Change port, stop the process holding the port, or provide required configuration; re-verify via startup logs |

When an error happens, keep the full error message and distinguish **environment setup → dependency download → compile → test → package → runtime**. With Gradle you can run `./gradlew build --stacktrace` on Linux or `.\gradlew.bat build --stacktrace` on Windows for more stack trace detail; Maven uses `./mvnw -e package` or `.\mvnw.cmd -e package`. Do not change multiple versions wholesale because of an unclassified error.

## 8. Practice Exercise and Self-Check Criteria

1. Choose **one** Spring Boot project with a Wrapper. Record the build tool, required JDK, and root directory.
2. Open PowerShell/cmd on Windows or bash on Linux; run `java -version`, `javac -version`, then the Wrapper's `--version`.
3. Run the right first-time command: **Gradle:** `clean build`; **Maven:** `clean package`. Observe tool/dependency downloads and the compile/test/package steps.
4. Only consider the build successful when you see the success message and exit code `0`. If it fails, identify which step failed using error/test reports rather than marking it successful.
5. List `build/libs/` or `target/`; clearly identify the main artifact, avoiding `plain` JARs or `original` backup files.
6. If an executable Spring Boot JAR is produced and the app needs no missing infrastructure, test-run it with `java -jar`, read the logs, and stop with `Ctrl+C`.

You have completed this lesson when you can **repeat the workflow on both operating systems**, explain why a Wrapper is needed, identify the right artifact, and distinguish a build result from running the application.

## Official Reference Documentation

- [Gradle Wrapper User Guide](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Apache Maven Wrapper](https://maven.apache.org/tools/wrapper/)
- [Spring Boot Gradle plugin: Running Your Application](https://docs.spring.io/spring-boot/gradle-plugin/running.html)
- [Spring Boot Gradle plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
- [Spring Boot Maven plugin documentation](https://docs.spring.io/spring-boot/maven-plugin/)