# Avoiding Tool Lock-In When Designing Core Build and Test Commands

## 1. Why Separate Core Commands from the CI Tool?

A project may run builds and tests on a developer's machine, in CI, inside a container, or on a standalone build server. If build and test logic exists only inside a single CI platform's configuration, reproducing runs in another environment becomes difficult.

For example, a pipeline may contain dozens of shell steps, dependency install commands, branch conditions, test argument assembly, and artifact packaging rules. A developer trying to reproduce a failure must dig through the CI UI to locate the right steps, copy commands, and guess which environment variables the pipeline supplied.

A durable design places core build and test commands inside the repository, using build tools and wrappers managed alongside the source code. CI merely orchestrates those commands: checking out source, preparing the environment, supplying credentials, running commands, storing results, and deciding the next release step.

The goal is for the exact same command to run on a developer's machine and in CI with the same meaning. The CI platform can change while the project's build/test process remains usable.

Within the scope of **DEVOPS_CI_CD_FUNDAMENTALS**, this approach supports pipeline as code, reproducibility, traceability, and pre-release testing. It also helps distinguish project bugs from issues caused by a runner, plugin, or platform-specific CI configuration.

## 2. Distinguishing Project Logic from Orchestration Logic

Not every step in a pipeline belongs in the repository. Separate two groups of responsibilities.

| Group | Responsibility | Example |
|---|---|---|
| Core project commands | Define how to build, test, lint, package, and verify quality | `mvnw verify`, `gradlew check`, `npm test` |
| CI orchestration | Choose when to run, runners, matrices, permissions, caches, and artifact transfers | PR trigger, provision JDK, upload reports, wait for approval |
| Release operations | Deploy, verify, roll back, and record release records | Deploy artifact digest, canary, smoke tests |
| CI infrastructure | Provide workers, networking, credentials, and supporting services | Runner images, secret stores, concurrency groups |

A helpful rule:

- If a step determines the quality or correctness of the source code, put that logic in the repository or the project's build tool.
- If a step decides when and where to run, which permissions are granted, or where outputs are stored, that is usually an orchestration responsibility.
- If an operation modifies a real environment, isolate it into a command/deployment workflow with an explicit contract and permissions.

For example, running unit tests should be a build tool task. Running that task on every pull request is a CI decision. Uploading JUnit reports is a CI integration with results produced by the build tool.

## 3. Designing a Clear Command Contract

A core command is the interface between the repository, developers, and automation systems. That interface must be stable and easy to understand.

A command contract should define:

1. **Name and purpose:** what the command does and does not do.
2. **Working directory:** which directory it runs from.
3. **Inputs:** arguments, environment variables, configuration files, and toolchain versions.
4. **Outputs:** artifacts, reports, logs, and intermediate files.
5. **Exit codes:** success and failure conditions.
6. **Side effects:** whether it writes files, makes network calls, modifies databases, or deploys.
7. **Time and resources:** whether timeouts, concurrency, or memory limits apply.
8. **Repeatability:** whether re-running creates invalid state or duplicates data.

Example contract for a Java verification command:

~~~text
Command: ./mvnw -B -ntp verify

Working directory:
  repository root directory

Inputs:
  source code, pom.xml, Maven Wrapper, declared JDK

Outputs:
  target/*.jar (if packaging is configured)
  target/surefire-reports/
  target/failsafe-reports/ (if integration tests are configured)

Exit code:
  0: phases through verify completed
  non-zero: build or a verification step failed

Side effects:
  creates files under target/
  downloads dependencies if absent from local cache
~~~

A command does not need dozens of flags to be flexible. Keep common options simple to invoke, while special cases can be expressed as clearly named tasks or profiles.

## 4. The Repository Is the Source of Truth for Build and Test

The rules needed to reproduce a build should be versioned inside the repository:

- Build descriptors such as `pom.xml`, `build.gradle.kts`, or `package.json`.
- Wrappers and build tool version configurations.
- Required JDK/toolchain or runtime configuration.
- Dependency lockfiles and dependency verification rules.
- Supporting scripts that can execute standalone.
- Appropriate test configurations, fixtures, and test data.
- Formatter, linter, static analysis, and coverage configurations.
- Standard command documentation in project docs.

If commands exist only in a Jenkinsfile or a single vendor's workflow config, developers may not know how to run them properly locally. CI then becomes the sole place that knows how to build the project.

CI still needs its own configuration, yet the core build/test logic should be readable, reviewable, versioned, and runnable outside CI.

## 5. Using Wrappers Instead of Relying on Globally Installed Tools

Wrappers let the repository control the build tool version used by the project. Runners do not need the exact Maven or Gradle version installed globally.

For Maven, use the Maven Wrapper:

- Unix-like: `./mvnw`
- Windows: `.\mvnw.cmd`

For Gradle, use the Gradle Wrapper:

- Unix-like: `./gradlew`
- Windows: `.\gradlew.bat`

Wrappers typically download the configured distribution if not already present locally. Therefore, version-control the wrapper files and verify distribution URLs/checksums where supported by the tool.

For repositories running on Unix-like systems, preserve the executable bit on `mvnw` in Git so users can invoke it directly. Enable distribution checksum verification if supported by the wrapper, and review wrapper updates as toolchain changes affecting the entire build.

Do not assume every machine has `mvn`, `gradle`, or the exact same version. Invoking a global tool might pass on a preconfigured runner yet fail on a fresh machine or pick up a different version.

### 5.1. Pinning Toolchain Versions

Wrappers control the build tool version, not the entire environment. Also manage:

- JDK or runtime versions.
- Compiler target/release levels.
- Node.js, Python, or auxiliary tools if present.
- Formatter, linter, and scanner versions.
- Dependency and plugin versions.
- Container image digests if builds are container-based.

With Gradle Java toolchains, you can declare:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
~~~

With Maven, configure the compiler plugin to set the appropriate release level and use Maven Toolchains when a specific JDK must be selected. Ensure both CI and developer machines can provide the declared toolchain.

Do not rely blindly on `JAVA_HOME` pointing to whatever JDK happens to sit on the runner without verifying the version before building.

## 6. Naming Tasks by Purpose Rather Than by CI Platform

Commands should describe what the project needs to do:

~~~text
./mvnw test
./mvnw verify
./gradlew test
./gradlew check
./gradlew build
~~~

Task names should make sense to people working on the project. Avoid naming core tasks `jenkinsBuild`, `githubActionTest`, or `azureReleaseCheck` when the real goal is compiling, testing, linting, or packaging.

If composite commands are needed, define standard tasks:

- `check`: run quality checks and required tests.
- `test`: run the configured test suite.
- `build`: produce artifacts and run build checks.
- `integrationTest`: run a dedicated integration test suite if configured.
- `verify`: perform verification steps before an artifact is accepted.

Exact names and semantics depend on the build tool. Clearly document which tasks the project defines and which tasks CI must invoke.

## 7. Keep Logic in Build Tools or Reusable Scripts

A maintainable pipeline typically invokes a small number of commands already defined in the repository.

For example, instead of writing multiple separate Maven commands in a workflow:

~~~yaml
steps:
  - run: ./mvnw -B -ntp clean
  - run: ./mvnw -B -ntp compile
  - run: ./mvnw -B -ntp test
  - run: ./mvnw -B -ntp package
~~~

you can use a single composite command if that is the project's build contract:

~~~yaml
steps:
  - run: ./mvnw -B -ntp verify
~~~

This reduces the risk of the pipeline skipping a phase or running steps in a different order than developers test locally.

A single command is not always best. Integration tests needing databases or supporting services may need to run in a separate job. In that case, define an explicit task in the build tool and let CI provision the dependencies and invoke that task.

## 8. Avoid Depending on CI-Specific Environment Variables

A build script should not silently rely on variables that exist only on one platform, such as a CI vendor's branch name, run number, or workspace path.

Instead:

- Pass required parameters via command-line arguments or project-defined environment variables.
- Provide safe defaults where possible.
- Validate required inputs and surface clear error messages.
- Do not infer deployment environments from runner hostnames.
- Do not alter test logic merely because a CI variable happens to exist.

For example, if integration tests need a service URL:

~~~text
APP_BASE_URL=http://localhost:8080 ./mvnw -B -ntp -Pintegration verify
~~~

On Windows PowerShell:

~~~powershell
$env:APP_BASE_URL = "http://localhost:8080"
.\mvnw.cmd -B -ntp -Pintegration verify
~~~

The environment variable name is defined by the project and has meaning outside CI. The pipeline simply supplies the corresponding value.

If a command needs to know it is running in CI to adjust logging or report paths, use an optional variable with documented behavior. Never let it silently alter test semantics.

## 9. Write Portable Scripts and Control the Shell

A script that runs only on Bash may fail on PowerShell or another runner's default shell. Common differences include:

- How environment variables are set.
- How commands are chained.
- Quoting and escaping rules.
- Exit code handling.
- Path separators.
- Wildcard expansion.
- Working directories.
- Encoding and line endings.

If shell scripts are required, explicitly choose and declare the shell inside the script. If multiple operating systems must be supported, provide separate POSIX and PowerShell scripts sharing the same contract, or use a cross-platform language like Python/Node once the runtime is managed.

Avoid embedding complex multi-line scripts inside multi-layered YAML quoting. Moving logic into dedicated files makes it easier to lint, test, and review.

### 9.1. Handling Paths and Working Directories

Avoid hard-coding runner-supplied absolute paths such as `C:/agent/work/project` or `/home/runner/work/project`. Use paths relative to the repository root or resolve the root from the script's location.

Principles:

- Use language path-handling APIs instead of manually concatenating OS-specific separators.
- Quote paths that may contain spaces.
- Explicitly define whether commands run from the repository root or a module directory.
- Do not rely on implicit shell wildcard expansion.
- Do not assume a clean workspace if CI may reuse runners.

Every standard command must have a documented working directory. In a monorepo, each module can define its own commands while a root command coordinates modules.

## 10. Exit Codes Are a Machine-Readable Contract

CI usually determines pass/fail from exit codes. Therefore, commands must return exit codes matching their actual outcomes.

Standard convention:

- `0`: success.
- Non-zero: an error or unmet condition.

A script must never print "Tests failed" and still exit with code `0`. Similarly, never discard a child command's exit code by overwriting the final result.

Shell example:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

./mvnw -B -ntp verify
~~~

For a PowerShell script:

~~~powershell
& .\mvnw.cmd -B -ntp verify
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
~~~

These examples show how to propagate failures from the build tool to the caller. With Bash, understand how `set -e` behaves inside conditionals, pipelines, and command substitutions; do not treat it as complete error handling for every situation.

Do not use `|| true` to force a pipeline green when tests or scanners fail, unless that result is explicitly classified as non-blocking and still recorded.

## 11. Separate Test Tiers by Cost and Purpose

Not every run needs the entire test suite. However, release pass criteria must be explicit.

A tiered breakdown:

| Tier | Contents | When Usually Run |
|---|---|---|
| Fast checks | Formatting, linting, compiling, fast unit tests | Local and every PR |
| Integration tests | Databases, queues, APIs, or supporting services | Relevant PRs and CI |
| Contract tests | API/event compatibility between producers and consumers | PR/release |
| End-to-end tests | Cross-system business flows | Pre-release CI or test environments |
| Security/quality checks | SAST, SCA, secret scanning, licenses, and policies | PR, merge, scheduled, or release |
| Smoke tests | Verify running artifact after deployment | Post-deployment |

Local commands should allow running each tier individually. Pipelines can group tiers into jobs or stages based on time and resource budgets.

Do not lump all tests into one monolithic script with no way to select subsets. Equally, avoid creating too many overlapping commands that confuse users about which command is standard.

## 12. Tests Must Be Order- and Environment-Independent

A sound test suite avoids depending on:

- Test execution order chosen by the runner.
- Leftover files from previous runs.
- Shared databases that concurrent tests can mutate.
- Hardcoded ports already occupied by another process.
- Uncontrolled system clocks or timezones.
- Unmanaged external network services.
- Personal secrets residing on a developer's machine.

Create reproducible fixtures, clean up resources after tests, and isolate data per test or worker. For tests requiring supporting services, document how dependencies are started and how readiness is verified.

Flaky tests must not be masked by infinite retries. Bounded retries may be used to classify infrastructure errors, provided both the retries and initial failure results are recorded so the team fixes the root cause.

## 13. Manage Dependencies and Caches Without Corrupting Results

Dependency caches speed up builds, but must never be a prerequisite for build correctness.

Principles:

- Version-control dependency declarations.
- Use lockfiles when supported by the ecosystem.
- Pin plugin/tool versions.
- Use dependency verification/checksums where appropriate.
- Key caches using toolchain and dependency state.
- Ensure builds succeed from an empty cache.
- Never store secrets in caches.
- Never use caches to store release artifacts.

Cache is a performance optimization, not a source of truth. If a build succeeds only while a stale cache exists, the process is not sufficiently reproducible.

CI should periodically run clean or cache-miss builds to catch undeclared dependencies, without necessarily wiping caches on every job and slowing down pipelines.

## 14. Control Outputs: Artifacts and Reports

Core commands should produce outputs in stable locations and formats.

Examples:

- Maven: `target/`.
- Gradle: `build/`.
- JUnit XML: report paths configured by the plugin/build tool.
- Coverage: JaCoCo or equivalent format.
- Packages: JAR, WAR, ZIP, or container images.

CI can upload reports or artifacts, yet should not have to infer paths by scanning the entire workspace when the project can publish a clear output contract.

Distinguish:

- **Temporary output:** reproducible files, typically cleaned after build.
- **Test evidence:** reports retained per retention policy.
- **Release artifact:** immutable output published and identified by version/digest.
- **Cache:** reproducible data used to speed up execution.

Do not rebuild in each environment if the goal is to deploy the exact tested artifact. Build once, publish by digest, then promote that artifact across environments.

## 15. Do Not Mix Build, Test, and Deploy into One Ambiguous Command

A single release command may sound convenient, yet if it builds, tests, publishes, and deploys to production all at once, it becomes hard to tell what happened when a failure occurs partway through.

Separate responsibilities:

~~~text
validate:
  compile + lint + unit/integration checks

package:
  build artifact from verified source

publish:
  push immutable artifact to repository

deploy:
  deploy approved artifact digest

verify:
  smoke tests and post-deploy signal checks
~~~

You can create a wrapper command to invoke these steps in one environment, while each step must still maintain its own status, outputs, and errors.

In particular, core build/test commands must never deploy to production or mutate cloud resources simply because an environment variable happens to be set. Release side effects require a dedicated workflow with separate permissions and approvals.

## 16. Pass Configuration and Secrets Through Explicit Interfaces

Build/test commands sometimes need tokens to download private dependencies or connect to test services. Never hardcode credentials in scripts or commit them to the repository.

Best practices:

- Read secrets from a secrets manager or CI-injected environment variables.
- Validate required variables before running.
- Never print secret values to logs.
- Avoid passing secrets as command-line arguments where process lists or logs might expose them.
- Use credentials with minimal scope and lifetime.
- Distinguish non-sensitive configuration from secrets.
- Support local runs by supplying personal/dev credentials according to security guidelines.

A command should report the name of a missing variable without ever printing a variable's value. Core tests should also use fake credentials or mock services when real system access is unnecessary.

## 17. Java Example with Maven Wrapper

A Maven project can define standard commands like this:

~~~text
# Run unit tests
./mvnw -B -ntp test

# Run all verification phases through verify
./mvnw -B -ntp verify

# Windows PowerShell
.\mvnw.cmd -B -ntp verify
~~~

`-B` enables batch mode, suited for automated environments. `-ntp` suppresses transfer progress in Maven versions supporting this flag (Maven 3.6.1 and later), keeping logs cleaner.

Maven Surefire typically runs unit tests during the `test` phase. If the project configures Maven Failsafe, integration tests typically run during the `integration-test` and `verify` phases. Invoking `verify` executes integration tests when plugins and lifecycles are properly configured.

Compiler plugin configuration should explicitly set the Java release level. Plugin versions should be managed in `pom.xml` rather than relying on environment-dependent defaults.

Do not use `-DskipTests` in release gates when tests are required to run. That flag skips test execution; `maven.test.skip` can even skip compiling tests depending on usage. If a diagnostic compile/package-only job exists, name and classify it clearly so its result is never mistaken for a full quality gate.

## 18. Java Example with Gradle Wrapper

With Gradle, you can use:

~~~text
# Run tests
./gradlew test

# Run standard checks attached to check
./gradlew check

# Build artifacts
./gradlew build

# Windows PowerShell
.\gradlew.bat check
~~~

Gradle Wrapper defines the distribution version in `gradle/wrapper/gradle-wrapper.properties`. Version-control both the wrapper scripts and this properties file.

The `check` task depends on verification tasks registered by plugins and build scripts, typically including the Java plugin's `test` task. If the project has a separate integration test source set, wire its task and dependencies into the lifecycle appropriately.

Do not assume `check` automatically runs every check the team expects. Read the build script and verify the task graph, test reports, and exit codes. You can use `./gradlew tasks` or `./gradlew check --dry-run` to inspect task structure; never use a dry run as proof that tests actually ran.

## 19. Example Pipeline That Only Orchestrates Repository Commands

A generic pipeline can be expressed as:

~~~yaml
jobs:
  verify_and_package:
    steps:
      - checkout_source
      - setup_declared_jdk
      - restore_dependency_cache
      - run: ./mvnw -B -ntp verify
      - upload: target/surefire-reports/
      - upload_if_present: target/failsafe-reports/
      - publish: target/*.jar
~~~

This is illustrative pseudocode YAML explaining responsibilities, not syntax for a specific CI vendor. Maven's `verify` phase already executes `package`, so this example publishes the artifact from the same job as `verify`. If publishing needs to be a separate job, pass the built artifact to that job; do not rebuild from source a second time.

If `verify` fails, CI should still collect already-generated test reports before the job ends. Configuring upload-on-failure or an equivalent mechanism belongs to the platform, while report formats and paths belong to the repository's output contract.

A clean design invokes commands defined inside the repository. CI is responsible for provisioning runners, caches, secrets, triggers, uploading reports, and storing artifacts.

## 20. Making Commands Repeatable and Easy to Diagnose

Core commands should support diagnostics when failures occur:

- Logs show which step is executing.
- Toolchain versions can be printed without leaking secrets.
- Errors include context and point to relevant files/tasks.
- Reports are preserved even when tests fail.
- Exit codes are propagated accurately.
- Temporary outputs are managed cleanly.
- A verbose mode is available when investigating issues.
- The exact same command can be rerun with the same inputs.

Avoid relying on secret setup steps present only on CI runners. If temporary configuration files are needed, let the script generate them from explicit inputs and clean them up properly.

When an error appears only in CI, compare commands, toolchains, environments, dependency states, working directories, and access permissions. Never blame the CI platform before attempting to reproduce with the exact same command.

## 21. Testing Tool Independence

You can evaluate build/test independence with a straightforward test:

1. Clone the repository into a clean machine or container.
2. Do not install global build tools if the project provides a wrapper.
3. Install only the declared runtime/toolchain.
4. Run the documented command from the repository root.
5. Run it again with an empty dependency cache.
6. Check exit codes and reports.
7. Compare artifact digests when inputs are identical and builds are designed to be deterministic.
8. Run the exact same command on a CI runner.
9. Verify that output paths and reports remain consistent.
10. Confirm no CI UI access or CI-specific variables are required to complete the build/test.

Not every build is bit-for-bit reproducible due to timestamps, archive metadata, or toolchains. If deterministic builds are not yet achieved, document the varying factors while still recording artifact digests to identify the exact released binary.

## 22. Common Anti-Patterns

| Anti-Pattern | Consequence | Improvement |
|---|---|---|
| Build logic lives only in CI YAML | Hard to run locally and hard to migrate platforms | Move logic into build tools or scripts inside the repo |
| Calling global Maven/Gradle | Different machines may use different versions | Use a versioned wrapper |
| Hardcoding runner workspace paths | Command fails on other machines | Use repository-relative paths |
| Depending on CI vendor variables in tests | Tests cannot run standalone | Use named inputs and a project contract |
| Overly long YAML scripts | Hard to lint, test, and review | Move logic into script files or build tasks |
| Swallowing exit codes | False green pipelines | Propagate exit codes and verify results |
| Using `\|\| true` on failed tests | Hides quality failures | Classify non-blocking checks explicitly and record decisions |
| Making cache mandatory | Clean builds fail | Ensure cache is purely an optimization |
| Rebuilding per environment | Artifacts can differ across environments | Build once, promote by digest |
| Build command deploys to production | Mixes privileges and side effects | Separate deploy workflows with approvals |
| Omitting working directory expectations | Failures depend on where command was invoked | Standardize on repository root/module root |
| Order- or stale-data-dependent tests | Flaky and hard to reproduce | Isolated fixtures and explicit cleanup |
| Single command blurring test and package | Hard to tell which stage succeeded | Define tasks by clear purpose |

## 23. Checklist for Designing Core Build and Test Commands

**Command contract**

- [ ] Standard documented commands exist.
- [ ] Working directories and inputs are defined.
- [ ] Exit codes accurately reflect outcomes.
- [ ] Output and report paths are stable.
- [ ] Side effects and network requirements are stated clearly.

**Toolchain and dependencies**

- [ ] Versioned wrappers are present.
- [ ] Runtime/JDK versions are declared.
- [ ] Critical plugins and dependencies are version-pinned.
- [ ] Lockfiles or dependency verification are used where appropriate.
- [ ] Builds still succeed with an empty cache.

**Independence and reproducibility**

- [ ] Core commands run outside CI.
- [ ] No reliance on runner-specific paths or variables.
- [ ] Scripts handle paths, quoting, and exit codes properly.
- [ ] Tests do not depend on execution order or leftover state.
- [ ] CI failures can be reproduced using the exact same command.

**CI and releases**

- [ ] CI invokes commands defined in the repository.
- [ ] CI primarily orchestrates runners, secrets, caches, and reports.
- [ ] Unit/integration/contract/e2e tiers are separated.
- [ ] Tests are never skipped in release gates.
- [ ] Artifacts are identified and promoted by digest.
- [ ] Deploy and rollback are separate steps with appropriate permissions.

## 24. Conclusion

Core build and test commands belong to the repository, with an explicit command contract that runs outside any single CI platform. Wrappers, pinned toolchains, managed dependencies, portable paths, accurate exit codes, and consistent reports enable teams to reproduce results both locally and in CI.

CI remains essential, yet its primary role is orchestration: selecting triggers, provisioning runners and credentials, invoking commands, storing evidence, and gating releases. When build/test logic is decoupled from platform specifics, projects can switch CI providers more easily, investigate failures faster, and prove that artifacts were produced by the exact process that was reviewed and tested.
