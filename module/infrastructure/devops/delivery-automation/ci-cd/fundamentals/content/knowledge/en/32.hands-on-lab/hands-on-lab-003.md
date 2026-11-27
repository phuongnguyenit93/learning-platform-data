# Running the Same Verification Command Locally and on a Clean Runner

## Lab Objectives

After completing this lab, you will be able to:

- Select a standard verification command for a project and run it from your local machine.
- Configure a pipeline so that a clean runner executes the exact same set of verification tasks.
- Align the JDK version, build tool, and required inputs across both environments.
- Analyze cases where a local machine passes while CI fails, or vice versa.

This lab uses a Java project built with Gradle as an example. The same principle applies to Maven or other build tools: the project must provide a verification entry point callable from the command line, and the pipeline simply prepares the environment and invokes that entry point.

## Why Use the Same Verification Command?

A change is typically checked in multiple places: on a developer's machine, in a pull request, and before creating an artifact. If each place runs a different set of commands, results easily conflict. A local machine might run only a subset of tests in an IDE, while CI also runs formatting checks, static analysis, or packaging. When CI detects an error, the team struggles to tell whether the error comes from the source code or from two places checking different things.

We choose one standard command, store the build definition in the repository, and run the same set of tasks everywhere. For a Gradle project with the Java plugin, for example:

~~~bash
./gradlew --no-daemon clean check
~~~

**gradlew** is the Gradle Wrapper included with the project. The wrapper selects the Gradle version declared in **gradle/wrapper/gradle-wrapper.properties**; runners do not need a matching global Gradle installation. **clean** deletes stale build outputs in the workspace. **check** invokes the verification task group configured by the project and its plugins, typically including automated tests and other verification steps.

On Windows PowerShell, use the corresponding launcher:

~~~powershell
.\gradlew.bat --no-daemon clean check
~~~

The launcher name differs by OS, but both commands invoke the same Gradle Wrapper, the same Gradle version, and the same **clean check** task set. If a team wants a shorter, more stable command, they can create a project **verify** script that invokes the Wrapper; that same script must be used both locally and in CI.

Do not use an IDE's Build button or a personal IDE run configuration as the standard verification gate. An IDE remains useful for quickly running a single test during development, but the check result before submitting changes must come from the repository's command.

## Preparing the Project

Before running, verify that the repository has the required components:

| Component | Role |
|---|---|
| gradlew and gradlew.bat | Launchers for Linux/macOS and Windows |
| gradle/wrapper/gradle-wrapper.jar | Wrapper executable archive |
| gradle/wrapper/gradle-wrapper.properties | Declares the Gradle distribution version |
| build.gradle or build.gradle.kts | Declares plugins, dependencies, and build/check tasks |
| settings.gradle or settings.gradle.kts | Declares project structure and modules |

The Wrapper files must be committed alongside the source code. Do not require team members to install Gradle globally or pick their own Gradle version. For Java repositories, the team must also agree on the JDK version. The example in this lab uses JDK 21; if your project specifies another version, update the number in both the CI configuration and the project's toolchain configuration so they match.

Before running for the first time, open a terminal at the repository root. Check the Java version and the version used by the Wrapper:

~~~bash
java -version
./gradlew --version
~~~

On Windows, replace **./gradlew** with **.\gradlew.bat**. The output confirms the machine is using the expected JDK and Wrapper. If the build declares a Java toolchain, ensure that toolchain can also be installed or located in the execution environment.

## Exercise 1: Running the Verification Gate Locally

1. Clone or pull the source code and navigate to the repository root.
2. Confirm that the change to be checked is in the working tree. If you want an exact comparison with CI, commit the change or record the commit SHA to be pushed.
3. Run the standard command:

   ~~~bash
   ./gradlew --no-daemon clean check
   ~~~

4. Wait for all tasks to finish. The build is considered passing only when the process returns exit code **0** and Gradle reports **BUILD SUCCESSFUL**. If any task fails, read the task name and error message before editing code.
5. Re-run the command after fixing. Because **clean** is included, the result does not depend on leftover output files from the previous build.

**--no-daemon** instructs Gradle not to reuse a long-lived background daemon across invocations. Gradle may still spawn a single-use daemon process under certain JVM configurations; the purpose here is to reduce differences caused by daemon state lingering from a prior session.

Note: **clean** only deletes the project's build outputs. It does not delete the JDK, environment variables, the dependency cache in the user's Gradle directory, running services, or files untracked by Git. Therefore, this command produces a clean build within the workspace, but does not by itself prove the project can build on a completely fresh machine.

## Exercise 2: Running the Exact Verification Gate on a Clean Runner

A runner is the machine or environment that executes a CI job. A clean runner must check out the source code of the commit under test, install the matching JDK, and invoke the Wrapper from the root directory. Example minimal GitHub Actions workflow:

~~~yaml
name: Verify

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Run the project verification command
        run: ./gradlew --no-daemon clean check
~~~

The JDK version in the example must match the project's actual requirement. When applying this to a real repository, follow your organization's action version pinning policy.

The workflow performs three clear actions: fetch the exact commit, prepare the JDK, and invoke the repository's verification command. Linux runners use **./gradlew**; Windows machines use **gradlew.bat**. The **clean check** task set remains identical. Do not rewrite a separate test list or custom build command inside the workflow, as that fragments verification rules between the source code and the pipeline.

A clean runner helps uncover accidental local-machine dependencies: uncommitted files, stale build directories, IDE settings, machine-specific environment variables, or manually installed software. On a newly provisioned runner for a job, the workspace starts from a checkout of the commit. If CI restores caches, the workspace may still be clean while tool or dependency caches are reused; these two concepts should be distinguished.

During initial setup, run the pipeline without adding custom build caches. Once the basic flow is stable, you can add dependency caching to reduce download times. Caching is strictly a performance optimization: when investigating hard-to-reproduce failures, retry without restoring caches or use a fresh cache key. Never allow correctness to depend on an output directory cached from a previous job.

## Comparing the Two Environments

For a meaningful comparison, the local machine and the runner must receive the same inputs. Use the following table when a run produces different results:

| Factor | Local Machine | CI Runner |
|---|---|---|
| Source code | Commit or working tree being checked | Clean checkout of exact commit SHA |
| Java | JDK and toolchain per project requirement | Same JDK/toolchain major version |
| Build tool | Gradle Wrapper in repository | Same Wrapper and config files |
| Tasks | clean check | clean check |
| Working directory | Repository root | Repository root |
| Configuration | Declared environment variables and parameters | Matching declarations in the job |
| Workspace state | May contain uncommitted files | Clean checkout of the commit |

Not every machine needs the same operating system, though OS differences can expose bugs involving file paths, case sensitivity, execute permissions, or shell scripts. If the project supports multiple operating systems, add jobs testing on those operating systems instead of assuming a single Linux runner proves everything.

For sensitive information such as tokens to access test services, use CI's secrets store and configure matching environment variables when running locally. Never commit secrets to the repository, never print secrets to logs, and never create a dummy value that causes tests to accidentally skip authentication branches. If tests do not require an external service, prefer fixtures or mock services that can be initialized repeatably.

## When Local and CI Results Differ

First, record the commit SHA, the command executed, the Java version, the Gradle version, and the failing task. You can gather this info with:

~~~bash
git rev-parse HEAD
java -version
./gradlew --version
~~~

Then categorize the situation:

| Outcome | Investigation Path |
|---|---|
| Local fails, CI fails | Prioritize fixing source code, tests, or build configuration; inspect the first failing task. |
| Local passes, CI fails | Compare commit, JDK, toolchain, environment variables, file permissions, OS, and uncommitted files. Try a fresh clone or clean worktree locally. |
| Local fails, CI passes | Check local JDK, personal configuration, stale caches, and environment variables. Confirm local is testing the exact same commit. |
| Both pass intermittently | Look for tests depending on timing, execution order, network ports, shared data, or external services. Make tests independent with deterministic inputs. |

When more trace detail is needed, re-run the same tasks with **--stacktrace** to view the stack trace:

~~~bash
./gradlew --no-daemon clean check --stacktrace
~~~

Keep the task set unchanged during diagnosis so results remain comparable. Avoid altering the workflow into a different command sequence just to make CI temporarily green; if you discover the project is missing a necessary check step, put that step into the standard build configuration and let both local and CI call the verification gate again.

## Self-Directed Exercise

1. Choose a Java repository with a Gradle Wrapper and identify the JDK version required by the project.
2. Run **./gradlew --no-daemon clean check** on your local machine (or the corresponding launcher command on Windows). Record the commit SHA and result.
3. Create a CI workflow that checks out the code, sets up the same JDK, and runs that exact verification command.
4. Push a change accompanied by tests. Open a pull request and verify that the check job runs on the corresponding commit.
5. Temporarily introduce a test-detectable defect, run locally, and observe CI failing. Then fix the defect, re-run locally, and verify CI turns green.
6. If local and CI yield different results, use the comparison table above to find the difference and document the root cause.

## Completion Criteria

- [ ] The repository has the Gradle Wrapper and tool version configuration committed.
- [ ] The local machine can run clean check using the Wrapper from the root directory.
- [ ] The runner checks out the exact commit and sets up the matching JDK.
- [ ] The pipeline invokes the exact same clean check task set as the local machine.
- [ ] The job fails when checks fail and succeeds when all checks pass.
- [ ] You can explain at least two reasons why local and runner results might differ.

Once complete, the team has a repeatable verification gate traceable from commit to CI result. This forms the foundation for later steps covering artifact management, environment deployment, and setting quality gates based on trustworthy test results.
