# Narrowing Down Failures and Reproducing Builds Independently Outside the IDE

## 1. Goal

A Spring Boot application may run fine inside the IDE yet fail when built from the terminal or CI. Conversely, the IDE may report errors while the Gradle/Maven build succeeds. Causes usually lie in differences in JDKs, build tools, project models, dependency classpaths, annotation processing, profiles, environment variables, working directories, caches, or incremental compilation.

**Reproducing independently outside the IDE** means re-running the exact build via the Gradle/Maven Wrapper from the terminal, on the exact commit, with recorded inputs. The goal is to narrow the error down to a verifiable task/stage and establish a repeatable run showing whether the error persists or is resolved.

Workflow in this lesson:

1. Record the exact symptom, commit, task, and environment.
2. Classify the error: IDE import/sync, compile, test, packaging, dependency resolution, or runtime.
3. Run the build using the Wrapper outside the IDE, from the project root.
4. Compare the JDK running the build tool with the compiler toolchain and Java target.
5. Isolate effects of incremental outputs, build caches, dependency caches, and repositories.
6. Reproduce on a clean checkout or clean runner without deleting user data.
7. Minimize the failing task/module/configuration while preserving required conditions.
8. Record commands, logs, environment, and results so CI or another developer can rerun them.

**Illustrative versions:** Java 17, Spring Boot 3.3.13, Gradle 8.8, and Maven 3.9.9. These versions are used in examples, not claimed as the latest releases. When applying, use your repository's actual Wrapper and plugin versions.

## 2. Classify the Error Before Running Commands

Do not start by wiping all caches or upgrading the JDK. First identify which stage failed.

| Stage | Symptoms | First Question |
| --- | --- | --- |
| IDE import/sync | IDE fails to recognize modules, dependencies, or tasks | Does the Wrapper build succeed outside the IDE? |
| Configuration | Gradle/Maven fails to read build script/POM | Right root directory, Wrapper, and plugin versions? |
| Dependency resolution | Cannot download plugins/libraries, checksum or TLS failure | Do repository, proxy, credentials, and versions match CI? |
| Compile | Java/Kotlin compiler reports errors | Which JDK/compiler toolchain, source set, and annotation processors are used? |
| Test | Unit/integration tests fail or time out | Which test fails; does it depend on Docker/DB/timezone/ports? |
| Packaging | Fails to build executable Boot JAR or image | Are `repackage` task/goal, resources, and runtime dependencies right? |
| Runtime | Build passes, app fails to start | Do Java runtime, external config, classpath, and environment match deploy? |

Distinguish **IDE build** from **IDE run**. Many IDEs use their own compiler or IDE-managed classpath model; the Run button may launch the main class from output directories rather than the executable Boot JAR. Thus “works in the IDE” does not mean the JAR was packaged properly.

Conversely, if the Wrapper build passes outside the IDE yet the IDE underlines sources in red, check project sync, language level, annotation processing, and IDE JDK before editing the build script.

## 3. Recording a Comparable Reproduction

Before changing code/config, save these facts:

- Repository and commit SHA.
- Branch/tag, and whether the working tree has modifications.
- Full command, working directory, and exit code.
- Gradle/Maven Wrapper version.
- JDK vendor, full version, architecture, and JVM running the build tool.
- Compiler toolchain, release target, and test JVM if different.
- Relevant OS/architecture, locale, timezone, and encoding.
- Required profiles, system properties, and environment variables.
- Dependency lockfiles, verification metadata, and repositories/mirrors.
- Specific task/module and the first error log plus `Caused by`.

Basic Git commands:

~~~bash
git rev-parse HEAD
git status --short
git diff --stat
git diff
~~~

`git status` and `git diff` reveal whether the build ran on a modified working tree. Never put secret files or sensitive outputs into reports. To reproduce an exact released commit, use a clean checkout/separate branch instead of accidentally building uncommitted changes.

Do not use `git clean -xfd` as a default diagnostic step: that command deletes all untracked/ignored files and can destroy local data. Prefer a fresh checkout or dedicated worktree to preserve your active workspace.

## 4. Running Gradle Independently Outside the IDE

### 4.1. Always Start from the Gradle Wrapper

From the root directory containing `gradlew`:

~~~bash
./gradlew --version
./gradlew --no-daemon --console=plain --stacktrace clean test bootJar
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat --no-daemon --console=plain --stacktrace clean test bootJar
~~~

Explanation:

- `./gradlew` uses the exact Gradle distribution specified in `gradle/wrapper/gradle-wrapper.properties`.
- `--no-daemon` reduces reliance on long-lived daemons across runs; Gradle may still spawn a single-use daemon when JVM arguments require it.
- `--console=plain` makes logs readable and archive-friendly in CI.
- `--stacktrace` prints stack traces when builds fail.
- `clean test bootJar` verifies compile/test/package per the project's task graph.

In multi-module projects, target the exact module tasks, for example:

~~~bash
./gradlew --no-daemon --console=plain :service:clean :service:test :service:bootJar
~~~

`service` is an illustrative module name. Run `./gradlew projects` and `./gradlew tasks --all` to discover real project/task paths.

### 4.2. Isolating Tasks to Find the Failing Point

Instead of always running the full build, run layer by layer:

~~~bash
./gradlew --no-daemon --console=plain help
./gradlew --no-daemon --console=plain :service:compileJava
./gradlew --no-daemon --console=plain :service:test
./gradlew --no-daemon --console=plain :service:bootJar
~~~

How to read results:

- `help` fails: usually settings/build script, plugin resolution, or configuration.
- `compileJava` fails: focus on sources, JDK/toolchain, generated sources, and annotation processors.
- `test` fails: focus on test runtime, fixtures, external services, and test stability.
- `bootJar` fails after tests pass: inspect packaging, resources, duplicate entries, and task configuration.

Gradle configures the whole project before executing a task; thus a compile task failure does not guarantee the bug is in a Java file. Read the top of the log and stack trace to locate the first failing task/action.

### 4.3. Using Detailed Logs Appropriately

~~~bash
./gradlew --no-daemon --console=plain --stacktrace --info :service:compileJava
~~~

`--info` increases details about task execution and dependency resolution. Use `--debug` only when necessary because logs become massive and can expose paths, properties, or sensitive data. Never post raw logs publicly before reviewing for secrets, internal URLs, and tokens.

Gradle Build Scans can help analyze task graphs/performance, yet publishing a scan sends metadata to an external service. Enable only per your organization's security policy.

### 4.4. Forcing Task Re-Execution to Exclude Incremental/Cache Effects

~~~bash
./gradlew --no-daemon --console=plain --rerun-tasks --no-build-cache :service:test
~~~

- `--rerun-tasks` forces tasks to re-run instead of using up-to-date state.
- `--no-build-cache` prevents restoring task outputs from the Gradle build cache for this invocation.
- `clean` deletes project build outputs per the clean task; it does not wipe the entire Gradle User Home.

If the error occurs only under incremental compilation or cache, preserve the minimal reproducing command and inspect task inputs/outputs, generated sources, and plugin behavior. Do not assume “cache corruption” merely because a forced rerun passes once.

### 4.5. Checking Dependency Resolution Separately

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Replace `spring-core` with the suspected artifact. Check the selected version, conflict resolution reasons, constraints, BOM/platform, and repositories. If the error is a dependency download failure:

~~~bash
./gradlew --refresh-dependencies :service:compileJava
~~~

`--refresh-dependencies` instructs Gradle to re-verify dependency metadata/artifacts per cache policy; it is not a command to wipe all caches, nor can it fix misconfigured repositories/proxies. Use it only when stale metadata or artifact cache is suspected.

### 4.6. Offline Mode Is a Separate Test

~~~bash
./gradlew --offline :service:compileJava
~~~

If an offline build fails because a dependency is absent from the cache, that only proves the local cache is incomplete. It **does not prove** an online build will fail or that a dependency version is wrong. Use offline mode to test network/cache reliance, not as the standard build command when CI needs to download dependencies.

## 5. Running Maven Independently Outside the IDE

### 5.1. Maven Wrapper

From the root containing `mvnw`:

~~~bash
./mvnw --version
./mvnw -B -ntp -e clean verify
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd -B -ntp -e clean verify
~~~

Meaning:

- `./mvnw` pins the project's Maven distribution.
- `-B` enables batch mode, suitable for CI.
- `-ntp` reduces transfer progress noise.
- `-e` prints exception details.
- `clean verify` executes lifecycle phases up to `verify` per POM configuration.

If you only want to check compilation/packaging without running tests:

~~~bash
./mvnw -B -ntp -DskipTests package
~~~

`-DskipTests` skips running tests while typically still compiling test sources. `-Dmaven.test.skip=true` can skip test compilation as well; do not treat the two options as equivalent. Final release gates must still run tests per policy.

### 5.2. Separating Maven Phases

~~~bash
./mvnw -B -ntp validate
./mvnw -B -ntp -DskipTests compile
./mvnw -B -ntp test
./mvnw -B -ntp package
./mvnw -B -ntp verify
~~~

If `validate` fails, inspect POM/profiles/plugins. `compile` failure points to Java compiler/sources/generated code. `test` failure points to test runtime. `package` failure may point to Spring Boot `repackage`/packaging plugins. `verify` may run separately configured integration/quality gates.

### 5.3. Effective POM and Active Profiles

~~~bash
./mvnw -B -ntp help:active-profiles
./mvnw -B -ntp help:effective-pom -Doutput=target/effective-pom.xml
~~~

Effective POM shows configuration after parent inheritance, profiles, and plugin management. Compare local vs. CI to catch profiles auto-activating by JDK, OS, or properties. Effective POM files may contain internal URLs/properties; review before sharing.

### 5.4. Dependency Tree

~~~bash
./mvnw -B -ntp dependency:tree -Dscope=runtime
~~~

If a specific dependency resolves to an unexpected version, inspect dependency management, exclusions, BOM imports, and transitive paths. Do not upgrade dependencies en masse just to clean logs; pinpoint the conflicting artifact first.

### 5.5. Maven Debug Log

~~~bash
./mvnw -B -ntp -X -DskipTests compile
~~~

`-X` prints Maven/plugin/resolver debug details and may expose environment values, repository URLs, or properties. Run only in secure environments and review/redact before sending logs. Start with `-e`; enable `-X` when normal stack traces are insufficient.

## 6. Comparing JDKs of the IDE, Build Tool, and Compiler

A project can involve several Java installations simultaneously:

| Value | Meaning | How to Check |
| --- | --- | --- |
| IDE Project SDK | JDK used by the IDE to analyze/run code | IDE project settings |
| IDE Gradle JVM | JVM running Gradle when built from IDE | IDE Gradle settings |
| Gradle launcher/daemon JVM | JVM running the Gradle process outside IDE | `./gradlew --version` |
| Gradle Java toolchain | JDK selected by `JavaCompile`/`Test` tasks | `./gradlew javaToolchains` |
| Maven JVM | JVM running the Maven process | `./mvnw --version` |
| Maven compiler/toolchain | JDK used to compile when toolchain configured | POM and Maven Toolchains |
| Runtime JVM | JVM running the JAR/container after deploy | `java -version` or runtime diagnostics |

### 6.1. Gradle Toolchain and Release

Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Kotlin DSL:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

The toolchain selects the JDK for the task; `options.release` constrains Java APIs and bytecode targets. If the IDE uses its own compiler, configure the IDE to delegate build/run to Gradle or synchronize language levels/annotation processing so results do not diverge from the CLI.

### 6.2. Maven Compiler Release and Toolchains

In the POM:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

The `release` property does not install a JDK. Maven Compiler Plugin requires a JDK capable of supporting `--release 17`. If Maven runs on a different JDK, check Maven Toolchains Plugin and the runner's `toolchains.xml`. Never commit absolute developer-machine JDK paths to the repository.

### 6.3. Running an Independent Java Probe

Create `BuildEnvironmentProbe.java`:

~~~java
public final class BuildEnvironmentProbe {

    public static void main(String[] args) {
        System.out.println("java.feature=" + Runtime.version().feature());
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("java.vm.name=" + System.getProperty("java.vm.name"));
        System.out.println("os.name=" + System.getProperty("os.name"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("user.dir=" + System.getProperty("user.dir"));
        System.out.println("file.encoding=" + System.getProperty("file.encoding"));
    }
}
~~~

Compile/run with JDK 17:

~~~bash
javac --release 17 BuildEnvironmentProbe.java
java BuildEnvironmentProbe
~~~

Output looks like:

~~~text
java.feature=17
java.version=17.0.x
java.vendor=<vendor of running JDK>
java.vm.name=<JVM name>
os.name=<operating system name>
os.arch=<architecture>
user.dir=<working directory>
file.encoding=UTF-8
~~~

Values in `<...>` vary by environment; only `java.feature=17` is expected when running with Java 17. This is a standalone Java SE program independent of Spring Boot or the IDE. It checks the JVM executing the probe; it does not automatically detect the JDK picked by a Gradle toolchain unless run through that task.

## 7. Reproducing on a Clean Checkout

If an error may stem from generated files, stale outputs, or uncommitted changes, run on a fresh checkout. You can use a separate clone or a Git worktree.

Example creating an isolated worktree at the target commit:

~~~bash
git worktree add --detach ../repro-build <commit-sha>
cd ../repro-build
git status --short
./gradlew --no-daemon --console=plain clean test bootJar
~~~

`<commit-sha>` is the real commit to reproduce, not a copy-paste placeholder string. The worktree shares the Git object store while having its own working directory; Gradle/Maven caches may still be shared unless isolated separately.

To remove the worktree afterward:

~~~bash
git worktree remove ../repro-build
~~~

Run remove only after confirming the worktree is no longer needed and holds no changes worth keeping. Do not remove someone else's worktree or a directory not created for this reproduction.

### 7.1. Why Does a Clean Checkout Matter?

It rules out causes such as:

- IDE or developer generated uncommitted sources.
- Ignored local files read by the build script.
- Stale build outputs masking missing task dependencies.
- File path differences due to case sensitivity.
- Resources or configs present on disk yet absent from Git.
- Builds relying on uncommitted files or local plugins.

If the error reproduces only on a clean checkout, focus on build inputs tracked in version control or external dependencies. If it reproduces only in the old workspace, investigate ignored/generated files and specific caches instead of deleting the whole repository.

### 7.2. Isolating Gradle User Home

To test the effect of downloaded Gradle caches/distributions, create a dedicated Gradle User Home:

~~~bash
ISOLATED_GRADLE_HOME="$(mktemp -d)"
GRADLE_USER_HOME="$ISOLATED_GRADLE_HOME" ./gradlew --no-daemon --console=plain clean test bootJar
STATUS=$?
rm -rf "$ISOLATED_GRADLE_HOME"
exit "$STATUS"
~~~

This creates a fresh Gradle cache environment so the Wrapper may re-download the Gradle distribution and dependencies; network/repository access is required. If the shell uses `set -e`, adjust cleanup so it runs even when the build fails. Never point `GRADLE_USER_HOME` at a directory holding other user data.

### 7.3. Isolating Maven Local Repository

~~~bash
ISOLATED_M2="$(mktemp -d)"
./mvnw -B -ntp -Dmaven.repo.local="$ISOLATED_M2" clean verify
STATUS=$?
rm -rf "$ISOLATED_M2"
exit "$STATUS"
~~~

Maven will re-download artifacts into the temporary local repository. User/global `settings.xml`, mirrors, and environment can still influence it; this is not a completely hermetic environment. If the failure occurs only with the temporary repository, check access permissions, proxy, credentials, and repository policies.

Do not delete a developer's `~/.gradle` or `~/.m2` just to test a cache hypothesis. Temporary caches verify behavior without destroying existing data.

## 8. Where Do IDE Builds Differ from the Command Line?

### 8.1. IDE Import/Sync

The IDE builds its project model from Gradle/Maven. If sync fails while CLI builds pass, check:

- Does the IDE recognize the right root project and Wrapper?
- Which Gradle JVM/Maven JDK is the IDE using?
- Is the IDE in offline mode or using a different repository/mirror?
- Did the IDE import included builds/subprojects properly?
- Is annotation processing enabled with the right processor path?
- Are IDE caches/indexes stale after dependency/plugin updates?

Refresh/reimport the project model only after confirming the build script/Wrapper works outside the IDE. Do not modify source code to work around a pure IDE indexing issue.

### 8.2. IDE Compilation vs. Gradle/Maven Compilation

IDEs can use an internal compiler, separate output directories, and their own incremental compiler. If CLI fails while IDE passes, run the exact compile task outside the IDE and inspect annotation processors, generated sources, Java release, source sets, and compiler flags.

If CLI passes while IDE compile fails, compare Project SDK, language level, annotation processing, module classpaths, and IDE build delegation.

### 8.3. IDE Run vs. Executable JAR

The IDE can launch the main class from `build/classes`/`target/classes` with an IDE-managed classpath. To verify packaging, you must run:

~~~bash
java -jar build/libs/app.jar
~~~

or the corresponding Maven output. Never take IDE Run success as proof that `bootJar`/`repackage` works.

## 9. Minimizing the Failure Case Without Losing the Root Cause

A good reproducer is minimal while still preserving the conditions triggering the error. If you remove the dependency/config/plugin causing the failure, a passing reproducer no longer demonstrates the original problem.

Workflow:

1. **Lock the baseline:** record commit, command, JDK, OS, profile, and original error.
2. **Isolate phase:** configuration → dependency resolution → compile → test → package → runtime.
3. **Isolate module/task:** run tasks on the right module instead of the entire repository when only one module fails.
4. **Toggle one factor in a controlled way:** e.g., build cache, incremental task, or profile—changing only one factor at a time.
5. **Compare results:** keep commands and logs for both failing and passing states.
6. **Build a minimal reproducer:** keep only the classes, dependencies, config, and tasks needed to reproduce the error.
7. **Re-verify:** run the reproducer on a clean checkout/runner and document minimal conditions.

### 9.1. One Variable at a Time

For instance, an error occurs only under Gradle incremental compilation. Test sequentially:

~~~bash
./gradlew :service:compileJava
./gradlew --rerun-tasks :service:compileJava
./gradlew --rerun-tasks --no-build-cache :service:compileJava
./gradlew clean :service:compileJava
~~~

If only one command passes, record the cache/task state and inspect generated sources/plugin inputs. Do not jump immediately to blaming a Gradle compiler bug; a custom task may have incomplete input/output declarations.

### 9.2. Isolating Dependencies from Code

If compilation fails after upgrading a library:

~~~bash
./gradlew dependencyInsight --dependency library-name --configuration compileClasspath
~~~

Maven:

~~~bash
./mvnw dependency:tree -Dincludes=groupId:artifactId
~~~

Identify the selected version and transitive paths. Then test pinning the before/after version in a controlled way, using separate commits/lockfiles so you know which change introduced the failure.

### 9.3. Preserving Generated Sources and Annotation Processors

An error may appear only when Lombok, MapStruct, or annotation processors generate code. Inspect the annotation processor path, compiler plugin, generated-source directories, and IDE annotation processing. Do not strip required generated sources out of the reproducer; instead prove the task generating them runs properly from the CLI.

### 9.4. Multi-Module Projects

Gradle:

~~~bash
./gradlew projects
./gradlew :api:compileJava
./gradlew :service:test
./gradlew :service:bootJar
~~~

Maven:

~~~bash
./mvnw -pl service -am -DskipTests package
~~~

`-pl` selects the project/module; `-am` builds modules it depends on. Substitute real names for `api`/`service`. If a task fails only when running the root build, inspect shared convention plugins, root configuration, task ordering, and the project dependency graph.

## 10. Environment Variables, Profiles, and Working Directories

### 10.1. Spring Profiles

An IDE run configuration may automatically set `SPRING_PROFILES_ACTIVE=dev` while the terminal does not. Or the terminal may have `SPRING_CONFIG_LOCATION` pointing to a file absent in CI.

Print an allowlist of variables to inspect; do not dump the entire environment:

~~~bash
printf 'SPRING_PROFILES_ACTIVE=%s\n' "$SPRING_PROFILES_ACTIVE"
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
printf 'TZ=%s\n' "$TZ"
~~~

PowerShell:

~~~powershell
"SPRING_PROFILES_ACTIVE=$env:SPRING_PROFILES_ACTIVE"
"JAVA_HOME=$env:JAVA_HOME"
"TZ=$env:TZ"
~~~

If a variable is unset, the shell may print an empty string; distinguish empty from unset when application behavior differs. Never print passwords, access tokens, private keys, full Maven settings, or full environments to public CI logs.

### 10.2. Working Directory and Relative Files

The IDE may set the working directory to the module root while the CLI runs from the repository root. Relative paths like `./config/app.yml`, `./data/seed.json`, or `./certs/ca.pem` can therefore resolve differently.

Record `pwd`/`Get-Location`, inspect paths passed to the app, and decide which resources belong inside the JAR, in external config mounts, or in the working directory. Do not fix it by copying every local file to CI; define the required contract.

### 10.3. Locale, Timezone, and Encoding

A task can generate different output due to locale, timezone, default charset, or line endings. If outputs depend on these factors, standardize them explicitly in CI and test on the target OS. Do not assume Windows and Linux share path separators, case sensitivity, or permission semantics.

### 10.4. Proxy, TLS, and Repositories

If the IDE uses a separate proxy/certificate store while the CLI does not, dependency resolution can diverge. Check:

- Gradle/Maven repository URLs and mirror settings.
- Proxy variables and JVM proxy properties.
- Truststore/corporate CA configuration.
- DNS/firewall/registry access.
- Whether repository credentials are injected in CI.

Do not disable TLS verification or switch to HTTP just to “see if the build runs”. To test networking, use an approved mirror and proper CA configuration.

## 11. Distinguishing Build Failures from Runtime Failures

If `clean test bootJar` succeeds yet the application fails to run, that is a different failure phase. Inspect the JAR:

~~~bash
jar tf build/libs/app.jar
unzip -p build/libs/app.jar META-INF/MANIFEST.MF
java -version
java -jar build/libs/app.jar
~~~

An executable Spring Boot JAR typically contains `BOOT-INF/classes`, `BOOT-INF/lib`, launcher `Main-Class`, and application `Start-Class`. Read the actual manifest because loader class names can vary across Spring Boot versions.

If `UnsupportedClassVersionError` occurs, check `javap -verbose` on the offending class and the runtime Java. If a config error occurs, check active profiles/external files. If a DB connection fails, check URL, credentials, DNS, port, and schema. Do not change the compiler target when the real issue is missing runtime config.

For container images, check image ID/digest, entrypoint, user, port mapping, logs, and health endpoints. Host JDK/IDE settings do not determine the JVM packaged inside an image.

## 12. Saving Logs and Sharing Reproducers Safely

A useful bug report includes:

- Commit SHA and working-tree status.
- OS/architecture and JDK vendor/full version.
- Gradle/Maven Wrapper version.
- Full command, task/module, and exit code.
- First log section reporting task failure, stack trace, and `Caused by`.
- Active profile/config names, without secrets.
- Relevant dependency versions and effective POM/dependency insight if needed.
- Results on a clean checkout and CI runner.
- Results when toggling cache/incremental modes if relevant.

Before sharing logs:

- Redact tokens, passwords, authorization headers, and private URLs.
- Never send `settings.xml`, `gradle.properties`, keystores, or `.env` files containing credentials.
- Do not share private Build Scans/CI runs if the recipient lacks access.
- Keep details needed to reproduce: versions, tasks, modules, profiles, and dependency coordinates.

If the bug requires a reproducer, create a separate branch/commit containing only the minimal files. Do not send the entire repository when one class and a small build script suffice.

## 13. Using CI as an Independent Reproduction Standard

CI should execute the same Wrapper command from a clean checkout to establish a comparable baseline:

Gradle:

~~~bash
./gradlew --no-daemon --console=plain clean check bootJar
~~~

Maven:

~~~bash
./mvnw -B -ntp -C clean verify
~~~

Record commit SHA, Wrapper version, JDK version/vendor, runner OS/architecture, and command. If CI passes while local CLI fails, compare these inputs; if both fail identically, use stack traces/task graphs to narrow the cause.

Do not rebuild a separate artifact in the smoke/deploy step if the goal is to verify the exact built artifact. Upload/download the exact JAR, verify checksum, run the JAR outside the IDE, and record the digest. For images, verify and test the exact digest rather than just a mutable tag.

Build Scans, effective POMs, dependency trees, and CI logs aid diagnostics yet must comply with data policies. Do not grant publish/signing permissions to workflows executing untrusted pull request code.

## 14. Quick Troubleshooting

| Symptom | Common Cause | Next Action |
| --- | --- | --- |
| IDE passes, `./gradlew` fails | IDE uses different JDK/classpath/profile | Run Wrapper with `--version`, compare toolchain and profile |
| IDE reports errors, CLI passes | IDE sync/index/compiler differs | Reimport Wrapper properly, check Project SDK and annotation processing |
| Gradle `help` fails | Settings/plugin/configuration | Check root directory, plugin versions, and repositories |
| Maven `validate` fails | POM/profile/extension | Check effective POM and active profiles |
| Dependency resolution fails | Proxy/TLS/mirror/credentials/version | Check repository access and trust config |
| `compileJava` fails | Compiler JDK, API release, generated code | Check toolchain, `options.release`, processors |
| Tests fail only in CI | Timezone, ports, Docker, external services, race conditions | Check test assumptions and runner environment |
| `bootJar` fails while compile passes | Packaging/resources/manifest | Check Boot plugin, duplicate resources, and archive tasks |
| Build passes without `clean` | Stale outputs or wrong task inputs/outputs | Try clean checkout, `--rerun-tasks`, `--no-build-cache` |
| Build fails only when clean | Generated/ignored files or dependency cache | Check generated inputs, repositories, and task dependencies |
| Passes with cache, fails on empty cache | Relies on local cache or network/repository | Use isolated cache, check mirror and dependency versions |
| Gradle offline fails | Artifact not yet in cache | Do not treat as proof an online build will fail |
| Maven dependency version differs from IDE | Different profiles/BOM/settings | `help:active-profiles`, `effective-pom`, `dependency:tree` |
| Unexpected Java class major | Wrong compiler toolchain/release | Check `javap -verbose` and compiler configuration |
| Only a submodule fails | Project path/parent configuration | Use exact task path; `-pl ... -am` in Maven |
| JAR runs in IDE, `java -jar` fails | Missing repackage or runtime dependency | Inspect executable archive/manifest |
| Passes locally, fails on clean checkout | Untracked/ignored files or generated outputs | Create clean checkout and identify missing inputs |
| Linux fails, Windows passes | Case-sensitive paths, permissions, shell assumptions | Check filenames, executable bits, and native dependencies |
| Debug logs expose credentials | Excessive verbosity or environment dump | Redact logs, print only allowlisted diagnostics |

## 15. Practice Exercises with Answers

### Exercise 1 — IDE Passes, CLI Fails

The IDE runs the app yet `./gradlew clean test` reports a compile error. What do you check first?

**Answer:** `./gradlew --version`, Java toolchains, compiler release, annotation processors, source sets, and exact project root. The IDE may be using a different compiler/classpath.

### Exercise 2 — Gradle Task Up-To-Date

The build passes normally yet fails with `--rerun-tasks`. What does that suggest?

**Answer:** Incremental/cached tasks may be masking an issue, or a custom task has wrong input/output declarations. Preserve the failing command and check task outputs/generated sources; do not jump straight to cache corruption.

### Exercise 3 — Maven Profile

Passes locally yet fails in CI due to a missing database URL. How do you compare profiles?

**Answer:** Use `help:active-profiles` and `help:effective-pom`, and check environment/system properties and settings. Never put passwords in logs.

### Exercise 4 — JDK Mismatch

`./gradlew --version` shows Gradle 8.8 on JVM 21. The project compiles Java 17. Is the build definitely misconfigured?

**Answer:** No. The Gradle daemon can run on JDK 21 while a Java toolchain compiles with JDK 17. Check `javaToolchains` and `options.release`, then inspect bytecode.

### Exercise 5 — Build Fails Only on Clean Checkout

What are common causes?

**Answer:** The build relies on untracked/ignored files, generated sources not produced by a wired task, local configs, or cache-only dependencies. Identify the missing input instead of copying the whole workspace to CI.

### Exercise 6 — Maven `-DskipTests`

Does this command prove test compilation passes?

**Answer:** Maven Surefire normally skips running tests while still compiling test sources. `maven.test.skip=true` can skip test compilation too. Verify plugin behavior and use `verify` for release gates.

### Exercise 7 — Dependency Refresh

Gradle fails while downloading a dependency. Should you immediately run `--refresh-dependencies`?

**Answer:** First identify the artifact/version/repository and network error. Refresh only when stale metadata/artifact caches are suspected; the flag does not fix proxies/TLS/credentials or wrong dependency versions.

### Exercise 8 — Debug Logs

CI ran Maven `-X`; can you upload the full log publicly?

**Answer:** No. Debug logs can contain URLs, properties, and sensitive data. Review/redact and share only with authorized people.

### Exercise 9 — Multi-Module

Only the `service` module fails while the root build has 40 modules. How do you narrow it down?

**Answer:** Gradle uses `:service:compileJava`/`:service:test`; Maven uses `-pl service -am` to build the module and its required dependencies.

### Exercise 10 — Does `clean` Wipe All Caches?

**Answer:** No. Gradle/Maven `clean` clears project build outputs (`build/`/`target/`), not the entire Gradle User Home or Maven local repository. Use an isolated cache if testing a cache hypothesis.

## 16. Reproduction Checklist Before Opening a Bug/PR

- [ ] Recorded commit SHA, branch, and working-tree status.
- [ ] Recorded exact command, root directory, task/module, and exit code.
- [ ] Used the committed Gradle/Maven Wrapper, not a global build tool.
- [ ] Recorded JDK vendor/version, build-tool JVM, and compiler toolchain.
- [ ] Recorded OS/architecture, locale/timezone/encoding when relevant.
- [ ] Classified error as IDE sync, configuration, dependency, compile, test, packaging, or runtime.
- [ ] Collected stack trace and first meaningful `Caused by`.
- [ ] Isolated task/module to narrow scope.
- [ ] Changed only one factor at a time: cache, profile, JDK, dependency, or environment.
- [ ] Used a clean checkout/worktree to rule out local files and stale generated outputs.
- [ ] Used temporary Gradle User Home/Maven local repo if needed; did not wipe user caches.
- [ ] Checked effective POM, active profiles, dependency tree, or Gradle `dependencyInsight` when needed.
- [ ] Inspected the actual JAR/image if the build passes yet runtime fails.
- [ ] Redacted secrets before sharing logs, scans, or effective configurations.
- [ ] Created a minimal reproducer preserving the failure conditions.
- [ ] Confirmed others/CI can rerun the exact command and observe the same result.

**Conclusion:** To narrow down a build failure, first classify the failing phase and run the right Gradle/Maven Wrapper outside the IDE on the exact commit. Compare the JVM running the build tool with the compiler toolchain, separate dependency resolution from compile/test/package, and use a clean checkout or temporary cache to test hypotheses without breaking your workspace. A solid reproducer preserves the failure conditions, documents commands/environment, and repeats cleanly on CI or another machine.

## 17. Official Documentation

- Gradle — Command-Line Interface: https://docs.gradle.org/current/userguide/command_line_interface.html
- Gradle — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Dependency Management: https://docs.gradle.org/current/userguide/dependency_management.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Multi-Project Builds: https://docs.gradle.org/current/userguide/multi_project_builds.html
- Apache Maven — CLI Options: https://maven.apache.org/ref/current/maven-embedder/cli.html
- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — Profiles: https://maven.apache.org/guides/introduction/introduction-to-profiles.html
- Apache Maven — Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Apache Maven — Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains.html
- Spring Boot 3.3 — Gradle Plugin: https://docs.spring.io/spring-boot/3.3/gradle-plugin/
- Spring Boot 3.3 — Maven Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/

CLI options and IDE settings evolve across versions. Check documentation matching your pinned Wrapper/plugins, record exact reproduction commands, and avoid sharing logs/configs containing secrets.