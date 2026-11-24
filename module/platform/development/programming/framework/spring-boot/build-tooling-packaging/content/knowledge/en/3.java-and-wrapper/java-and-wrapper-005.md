# Using the Gradle Wrapper via gradlew and gradlew.bat

## 1. Lesson Objectives

After this lesson, you will be able to:

- Explain what the **Gradle Wrapper** is used for and why Spring Boot projects should invoke the Wrapper instead of a globally installed `gradle` command.
- Distinguish and correctly run **`gradlew` on Linux/macOS** versus **`gradlew.bat` on Windows**, including PowerShell and Command Prompt terminals.
- Read the four-file Wrapper structure and know where the Gradle version is decided.
- Use the Wrapper to check Gradle info, list tasks, build, test, run Spring Boot, and produce an executable JAR.
- Understand how the Wrapper downloads/caches Gradle, handles the JDK, runs in CI, and safely upgrades the Gradle version.
- Diagnose errors involving paths, execute permissions, JDKs, networking, missing Wrapper files, and version incompatibilities.

**Context:** In a Spring Boot project using Gradle, `gradlew` and `gradlew.bat` are two project-supplied scripts that launch the **Gradle version specified by the project itself**. They serve the same purpose but target different operating systems and terminals.

## 2. How Are Gradle and the Gradle Wrapper Different?

**Gradle** is the build tool: it reads `settings.gradle` or `settings.gradle.kts` along with `build.gradle` or `build.gradle.kts`, resolves dependencies, schedules tasks (compile, test, package, etc.), and executes them.

**Gradle Wrapper** is the bootstrap layer bundled with the project. When you invoke the Wrapper, the script launches the Wrapper code in `gradle-wrapper.jar`; that code reads `gradle-wrapper.properties` to pick the exact Gradle distribution, downloads/extracts it if missing, and then forwards your arguments to Gradle.

~~~text
Developer / CI
        |
        | ./gradlew test      or     .\gradlew.bat test
        v
gradlew / gradlew.bat script
        |
        v
gradle/wrapper/gradle-wrapper.jar
        |
        | reads distributionUrl
        v
gradle/wrapper/gradle-wrapper.properties
        |
        | Gradle version cached? -> use it
        | missing? -> download ZIP and extract
        v
Project-specified Gradle
        |
        | reads build.gradle(.kts) + settings.gradle(.kts)
        v
Execute "test" task
~~~

Quick comparison:

| Invocation | Gradle Version Used | Prerequisites |
| --- | --- | --- |
| `gradle build` | `gradle` pre-installed / found on `PATH` | Machine or CI must have a suitable Gradle installed |
| `./gradlew build` | Version configured in the **project's** Wrapper | Wrapper files, compatible Java, and ability to fetch Gradle if uncached |
| `.\gradlew.bat build` | Also the version configured in the **project's** Wrapper | Run in Windows PowerShell with Java and Wrapper files |

**The core benefit** is avoiding situations where machine A uses Gradle 8, machine B uses Gradle 9, and CI uses another version simply because global Gradle installations differ. The Wrapper keeps the **Gradle version** consistent, but **it does not automatically align the JDK, plugin versions, dependencies, or environment configuration**: those components still need separate management.

## 3. The Four Files of the Gradle Wrapper

For a Gradle project generated from Spring Initializr, the structure typically looks like:

~~~text
my-spring-app/
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── settings.gradle             # Or settings.gradle.kts
├── build.gradle                # Or build.gradle.kts
└── src/
    ├── main/
    └── test/
~~~

| File | Role | Should Commit to Git? |
| --- | --- | --- |
| `gradlew` | Shell script launching the Wrapper on Linux/macOS and Unix-compatible environments | **Yes** |
| `gradlew.bat` | Batch script launching the Wrapper on Windows | **Yes** |
| `gradle/wrapper/gradle-wrapper.jar` | Bootstrap code that downloads/launches the exact Gradle version | **Yes** |
| `gradle/wrapper/gradle-wrapper.properties` | Configures URL, distribution type, version, and download options | **Yes** |

**All four Wrapper files are source components stored in the repository.** Do not put `gradle-wrapper.jar` in `.gitignore` just because it is a binary file: omitting it can prevent the scripts from working on a fresh checkout or in CI.

Distinguish these directories:

- `gradle/wrapper/` inside the **project** holds configuration and bootstrap files and is committed.
- `.gradle/` at the **project root** holds local state/caches and is normally ignored by Git.
- The Gradle user home directory, defaulting to `~/.gradle` on Linux/macOS or `.gradle` under the Windows user profile, stores distributions/caches shared across projects; it can be changed via `GRADLE_USER_HOME`.

The Wrapper reads the project's build files just like regular Gradle; `gradlew` and `gradlew.bat` **are not two different build systems** and do not produce different build outputs merely because the script names differ.

## 4. Choosing the Right Command by OS and Terminal

Open a terminal **at the root directory containing `gradlew` and `gradlew.bat`**.

### 4.1. Linux and macOS: Running gradlew

~~~bash
./gradlew --version
./gradlew tasks
./gradlew test
~~~

The `./` prefix tells the shell to run the script in the current directory. `gradlew` needs execute permission; if a checked-out repository lacks it, see the `Permission denied` troubleshooting entry.

### 4.2. Windows PowerShell: Running gradlew.bat

~~~powershell
.\gradlew.bat --version
.\gradlew.bat tasks
.\gradlew.bat test
~~~

PowerShell uses `.\` to run a file in the current directory; typing bare `gradlew.bat` may fail to be recognized because PowerShell does not search the current directory by default the way CMD does.

### 4.3. Windows Command Prompt (cmd.exe)

~~~bat
gradlew.bat --version
gradlew.bat tasks
gradlew.bat test
~~~

In CMD, you can usually run `gradlew.bat` directly when in the right directory. `.\gradlew.bat` may also work in CMD, though the examples show the most common invocation.

### 4.4. Git Bash, WSL, and IDE Integrated Terminals

- **Git Bash** on Windows provides a Unix-like shell and can run `./gradlew` if the shell, permissions, and Java fit; in PowerShell/CMD, prefer `gradlew.bat`.
- **WSL** is a Linux environment running inside Windows, so use `./gradlew` and a JDK installed/configured for WSL. Java installed on the Windows side is not automatically the JDK Gradle uses inside WSL.
- **IntelliJ IDEA/VS Code integrated terminals** depend on the selected shell. Check the prompt or shell profile to choose the right syntax.
- **When inside a subdirectory**, pass a relative path to the script at project root, e.g., `../gradlew tasks` when one level below root. For multi-module builds, usually run from root and address tasks by path, e.g., `./gradlew :service:build` if a `service` module actually exists.

Equivalent command table:

| Purpose | Linux/macOS | Windows PowerShell |
| --- | --- | --- |
| View running Gradle info | `./gradlew --version` | `.\gradlew.bat --version` |
| List available tasks | `./gradlew tasks` | `.\gradlew.bat tasks` |
| List all tasks (including less visible ones) | `./gradlew tasks --all` | `.\gradlew.bat tasks --all` |
| Run tests | `./gradlew test` | `.\gradlew.bat test` |
| Full build | `./gradlew build` | `.\gradlew.bat build` |
| Clean build outputs | `./gradlew clean` | `.\gradlew.bat clean` |
| Run Spring Boot application | `./gradlew bootRun` | `.\gradlew.bat bootRun` |
| Build Spring Boot executable JAR | `./gradlew bootJar` | `.\gradlew.bat bootJar` |

The `bootRun` and `bootJar` tasks require the project to apply the **Spring Boot Gradle plugin**. In a plain Java Gradle project without the Spring Boot plugin, not seeing those two tasks is completely normal.

## 5. Hands-On Example: Running a Spring Boot Project with the Wrapper

Suppose you generated a project via **https://start.spring.io** with **Project = Gradle – Groovy** (or Gradle – Kotlin), **Language = Java**, picked compatible Spring Boot/Java versions, and added **Spring Web** if you need HTTP endpoints. Extract the ZIP and open the root directory in a terminal.

### Step 1 — Verify the Wrapper and JDK

Linux/macOS:

~~~bash
java -version
javac -version
./gradlew --version
~~~

Windows PowerShell:

~~~powershell
java -version
javac -version
.\gradlew.bat --version
~~~

`java -version` checks the Java the terminal finds on `PATH` (or related settings). `./gradlew --version` confirms the **Gradle runtime** actually launched by the Wrapper and displays JVM/OS info. Do not assume the Gradle number in `gradle-wrapper.properties` took effect if the Wrapper command itself is failing.

**JDK and Gradle are two different versions.** For example, a project might compile Java 21 code via a 21 toolchain while the JVM running Gradle is another compatible JDK. Check the compatibility matrix across the JDK running Gradle, the Java toolchain, and the project's Spring Boot plugin.

### Step 2 — Inspect Tasks and Build

Linux/macOS:

~~~bash
./gradlew tasks
./gradlew clean test
./gradlew build
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat tasks
.\gradlew.bat clean test
.\gradlew.bat build
~~~

Explanation:

- `tasks` lists tasks provided by Gradle and applied plugins.
- `clean` deletes build outputs managed by the `clean` task in the project (usually `build/`); it **does not delete** the Gradle user home, Wrapper distributions, or the entire dependency cache.
- `test` runs tests per build configuration. If tests fail, the build may report `BUILD FAILED`; do not skip them to force a green build.
- `build` typically runs the build lifecycle, including verification and artifact creation per plugin config; exact tasks can vary by project.

On success, Gradle usually prints `BUILD SUCCESSFUL`, though task counts, timings, and log lines are **not fixed**. Do not treat `BUILD SUCCESSFUL` on the `help` task as proof that the application has been tested and runs properly.

### Step 3 — Run Spring Boot via bootRun

Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

`bootRun` runs the Spring Boot application using the Gradle plugin's runtime configuration. With **Spring Web** and default configuration, a servlet application typically listens for HTTP on port **8080**. However, the actual port may have been changed via `server.port` or environment variables, and an application without a web starter will not open an HTTP endpoint on its own.

Practical tips:

- To test an exposed endpoint, open a second terminal and hit the project's exact URL/port.
- To stop an application running interactively in the terminal, press **Ctrl+C**.
- If a port-in-use error appears, check which other process occupies that port or adjust `server.port` in the project.
- If missing or multiple main classes are reported, inspect the application class and `bootRun`/Spring Boot plugin settings; do not treat this as a Wrapper script error.

### Step 4 — Package the Application

Linux/macOS:

~~~bash
./gradlew bootJar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootJar
~~~

When the task finishes, the executable Spring Boot JAR is typically located in `build/libs/`. The exact filename depends on `archiveBaseName`, `archiveVersion`, and other settings. The Spring Boot Gradle plugin can generate both a **plain JAR** and an **executable Boot JAR**—for instance, a file ending in `-plain.jar` is usually the ordinary library JAR. When running the application, select the **Boot JAR with the executable manifest/launcher**, rather than guessing from file ordering in the directory.

Given an actual artifact named `my-spring-app-1.0.0.jar`, an illustrative run command is:

~~~bash
java -jar build/libs/my-spring-app-1.0.0.jar
~~~

This command only runs when a file with that exact name has been generated. If the version or name differs, use the **actual JAR name** inside `build/libs/`. `bootRun` and `java -jar` are two different execution modes: the first runs via a Gradle task, while the second runs the packaged artifact, so classpath or arguments may differ if the project has custom configuration.

## 6. Where Does the Wrapper Get the Gradle Version?

Open **`gradle/wrapper/gradle-wrapper.properties`**. An illustrative configuration:

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

**The values above are examples only**; a real project's file may use a different version and options. The key entries:

- **`distributionUrl`** points to the ZIP of the Gradle version to run. `gradle-9.9.0-bin.zip` in the example indicates **Gradle 9.9.0**, unrelated to Java 9 or Spring Boot 9.
- **`-bin`** is the runtime-only Gradle distribution, usually smaller to download.
- **`-all`** also includes sources/docs for development and IDE experience; not required for basic builds.
- **`distributionBase`, `distributionPath`, `zipStoreBase`, `zipStorePath`** control where the Wrapper stores distributions and ZIPs.
- Some projects also configure `distributionSha256Sum` to verify the ZIP checksum, network timeouts, or custom proxy settings.

When the matching distribution is missing, the Wrapper must download it, extract it, and run Gradle. Subsequent runs can reuse the cached copy. Therefore, **the first run requires network access** if the environment lacks the distribution (and may also need network access for project dependencies); offline execution only succeeds when every required resource is already present.

The Wrapper **does not install a JDK**. Some environments support Gradle Java toolchain provisioning if suitably configured, but that is a Gradle toolchain feature/configuration, not a default capability of the Wrapper.

## 7. Keeping the Project and CI Consistent

On a team, commit all four Wrapper files alongside the build files. When teammates clone the project, they run the project's Wrapper command instead of picking a global Gradle version. CI should also use the Wrapper to minimize environment drift.

Example basic build steps on a Linux runner that already has a suitable JDK:

~~~bash
java -version
./gradlew --version
./gradlew --no-daemon clean test
./gradlew --no-daemon bootJar
~~~

`--no-daemon` requests not using a long-lived Gradle Daemon for that invocation per Gradle's mechanism; spawning a dedicated JVM can still happen depending on JVM options. This flag is often considered in CI, though it is not a mandatory rule: it depends on the team's caching, memory, and runner strategy.

Equivalent when CI uses Windows PowerShell:

~~~powershell
java -version
.\gradlew.bat --version
.\gradlew.bat --no-daemon clean test
.\gradlew.bat --no-daemon bootJar
~~~

**Conditions for reproducible builds** do not stop at the Wrapper: CI also needs an appropriate JDK, reachable dependency repositories, controlled plugin/dependency versions, necessary environment variables, and test configurations. With dynamic dependencies or changing repositories, the same Gradle version can still yield different results.

On Linux/macOS, `gradlew` in Git must retain its executable bit. If it only works after manually running `chmod +x gradlew` on each machine, fix the file mode tracked by Git in the repository and commit that change.

## 8. Safely Upgrading the Gradle Wrapper Version

Upgrading Gradle can affect build scripts, plugins, the JDK running Gradle, and CI. **Before upgrading**, verify:

1. Whether the **Spring Boot Gradle plugin** version used by the project supports the target Gradle version.
2. Whether the JDK running Gradle and the Java toolchain fall within the target Gradle's compatibility matrix.
3. Whether third-party plugins and Gradle DSL syntax (Groovy/Kotlin) require changes.
4. Whether the team/CI requires pinning a specific Gradle line.

**Intentional example:** Suppose you confirmed Gradle **9.9.0** fits your project; on Linux/macOS run from root:

~~~bash
./gradlew :wrapper --gradle-version 9.9.0 --distribution-type bin
./gradlew :wrapper --gradle-version 9.9.0 --distribution-type bin
./gradlew --version
./gradlew clean test
~~~

In Windows PowerShell:

~~~powershell
.\gradlew.bat :wrapper --gradle-version 9.9.0 --distribution-type bin
.\gradlew.bat :wrapper --gradle-version 9.9.0 --distribution-type bin
.\gradlew.bat --version
.\gradlew.bat clean test
~~~

**Why run `:wrapper` twice?** Per Gradle documentation, the first invocation usually updates `gradle-wrapper.properties`; the second invocation refreshes `gradle-wrapper.jar` and the scripts to match the new Gradle version (if they need changes). Using `:wrapper` targets the root project's task in a multi-project build. The first run may cause the second run to download the new Gradle distribution; network access is needed if the distribution is not yet cached.

After upgrading, review changes in `gradlew`, `gradlew.bat`, `gradle-wrapper.jar`, and `gradle-wrapper.properties`, run the appropriate test/build suite, and commit all changed files together. If compatibility errors occur, analyze the error messages and Gradle/Spring Boot upgrade guides rather than randomly cycling through multiple versions.

**Do not hand-edit script contents or replace the JAR with a file from an unknown source.** You can edit `distributionUrl` manually in controlled situations, though running the `wrapper` task is preferred to keep generated files in sync.

## 9. Verifying Wrapper Integrity and Download Sources

The Wrapper downloads and executes build code, so both the bootstrap files and the `distributionUrl` must be trustworthy.

- **URL:** Prefer official distributions from `https://services.gradle.org/distributions/` or an organization-managed mirror. Review `distributionUrl` changes in pull requests.
- **Distribution checksum:** You can set `distributionSha256Sum` to the **official SHA-256 of the exact ZIP and exact version** to verify downloaded content. Never copy a checksum from another version. This checks the **Gradle ZIP**, which is separate from verifying `gradle-wrapper.jar`.
- **Wrapper JAR:** You can verify the checksum of `gradle/wrapper/gradle-wrapper.jar` against Gradle's published checksum list: https://gradle.org/release-checksums/ . Some CI systems also offer actions to validate the Wrapper JAR.
- **Never arbitrarily pass verification-skipping flags**, swap the distribution to untrusted HTTP, or download random JARs from third-party websites.

Example computing the SHA-256 of the Wrapper JAR on Linux/macOS (`sha256sum` may not be pre-installed on all macOS systems; `shasum -a 256` can be used):

~~~bash
shasum -a 256 gradle/wrapper/gradle-wrapper.jar
~~~

In Windows PowerShell:

~~~powershell
(Get-FileHash .\gradle\wrapper\gradle-wrapper.jar -Algorithm SHA256).Hash
~~~

Once you have the hash, compare it with the official checksum for the **Wrapper JAR**. The command only prints the hash; it does not declare the file safe on its own. Checksum verification is especially valuable when reviewing upgrades, unfamiliar repositories, or pipelines enforcing supply-chain trust.

## 10. Common Errors When Using gradlew/gradlew.bat

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `./gradlew: No such file or directory` | Running in the wrong folder or project lacks a Wrapper | Open root containing `gradlew`; verify it is a Gradle project with all four Wrapper files |
| PowerShell reports `gradlew.bat is not recognized` | Missing `.\` or wrong directory | Run `.\gradlew.bat tasks` at root |
| `Permission denied` on `./gradlew` | Script lacks execute permission | Run `chmod +x gradlew` and record the executable bit in Git |
| `Could not find or load main class org.gradle.wrapper.GradleWrapperMain` | Missing/corrupt `gradle-wrapper.jar` or incomplete Wrapper layout | Restore full Wrapper files from a trusted repository; do not download random JARs |
| `JAVA_HOME is set to an invalid directory` | `JAVA_HOME` points to the wrong place or JDK moved | Point `JAVA_HOME` to a valid JDK directory and verify `java -version` |
| `Unsupported class file major version` or unsupported JDK message | Gradle/plugins and JVM/JDK in use are incompatible | Inspect `--version`, IDE/CI JDK, and Java–Gradle–Spring Boot compatibility matrices |
| Download timeout, 403, SSL/PKIX error | Network/proxy/certificate/mirror broken or blocked | Check URL, proxy, SSL trust store, connectivity, and configured repositories |
| `Task 'bootRun' not found` | Project does not apply the Spring Boot Gradle plugin or wrong build/root selected | Run `tasks`; inspect `build.gradle(.kts)` and the module containing the Spring Boot app |
| `Task 'build' not found` or no build found | Wrong directory/project or misconfigured plugin/build scripts | Inspect `settings.gradle(.kts)`, `tasks --all`, and actual configuration error messages |
| Running `--offline` reports missing modules/distribution | Some dependencies or the Gradle distribution are not cached yet | Run online to populate cache first; `--offline` cannot substitute for missing cache |
| Wrapper upgraded yet scripts/JAR didn't update | `wrapper` task was only run once | Run `:wrapper` a second time with the approved version and inspect the diff |
| Build passes locally but fails on CI | Different JDK, script permissions, environment variables, or dependency access | Compare `java -version`, `./gradlew --version`, executable bit, and CI logs |

### Systematic Error Isolation

**Step A — Check the command invoked:** confirm you are at root, chose `./gradlew` or `.\gradlew.bat` appropriately, and that Wrapper files exist.

**Step B — Check bootstrap:** invoke `--version`. If this fails, resolve JDK, execute permissions, Wrapper files, or distribution download issues first. Do not speculate about Spring Boot code bugs yet.

**Step C — Check the Gradle build:** once `--version` works, run `tasks` and then `test`. If configuration fails, focus on plugins, repositories, dependencies, and JVMs.

**Step D — Check Spring Boot:** once Gradle runs, invoke `bootRun` or `bootJar`. If startup or HTTP fails, focus on application configuration, dependencies, ports, and Spring Boot code; at that stage the Wrapper has normally done its job.

Read the root cause in stack traces/logs; `--stacktrace` helps locate task failures, while `--info` or `--debug` provides extra logs if needed. Do not clear the entire Gradle cache by default: that forces re-downloading everything, can worsen network failures, and will not solve compatibility issues.

## 11. Self-Practice Questions and Checklist

**Scenario 1:** A project includes `gradlew`, but the machine does not have Gradle installed. Can `./gradlew test` run?

Yes, if the project has all Wrapper files, a compatible JDK, and the Gradle distribution is cached or downloadable via `distributionUrl`. No global Gradle install is needed.

**Scenario 2:** On a Windows machine with PowerShell, a learner runs `gradlew.bat build` and gets a command-not-recognized error. What should they try first?

Verify they are in the project root, then invoke `.\gradlew.bat build`. That is PowerShell's syntax for executing a program in the current directory.

**Scenario 3:** A team updates `distributionUrl` to a newer Gradle version; Java sources did not change, yet CI fails during build configuration. Why?

Because the new Gradle version may be incompatible with the JVM running Gradle, the Spring Boot plugin, other plugins, or the current build DSL. Inspect the logs and compatibility matrices instead of checking only Java sources.

**Scenario 4:** When should you use `./gradlew bootJar` and when `./gradlew bootRun`?

`bootRun` runs the application directly via Gradle for development/testing; `bootJar` creates an executable Boot JAR for later execution or distribution. Both require the Spring Boot Gradle plugin.

**Self-check:**

- [ ] Identify all four Wrapper files in a project and understand each file's function.
- [ ] Distinguish global `gradle` from project-pinned `gradlew`/`gradlew.bat`.
- [ ] Run `--version`, `tasks`, `test`, and `build` with the right syntax for your OS.
- [ ] Run `bootRun` or `bootJar` when the project applies the Spring Boot Gradle plugin.
- [ ] Explain `distributionUrl`, distribution caching, and the relationship with the JDK.
- [ ] Know how to upgrade the Wrapper via `:wrapper`, verify compatibility, and review the diff.
- [ ] Know how to handle wrong path, missing executable bit, JDK, JAR file, network, and missing task errors.

## Official Documentation

- Gradle Wrapper — usage, structure, upgrading, verification: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Gradle Wrapper Basics: https://docs.gradle.org/current/userguide/gradle_wrapper_basics.html
- Gradle Java compatibility: https://docs.gradle.org/current/userguide/compatibility.html
- Gradle release checksums: https://gradle.org/release-checksums/
- Spring Boot Gradle Plugin: https://docs.spring.io/spring-boot/gradle-plugin/index.html
- Spring Boot system requirements (check for your exact version): https://docs.spring.io/spring-boot/system-requirements.html

**Lesson outcome:** You can check out a Spring Boot Gradle project on Linux, macOS, or Windows and use its Wrapper to inspect versions, build, test, run the application, package it, and diagnose common environment errors.
