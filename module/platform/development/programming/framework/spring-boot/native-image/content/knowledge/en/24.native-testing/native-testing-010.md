# Collecting Results, Logs, and Exit Codes to Verify Failures in CI

> **Chapter: Native Testing.** The **SPRING_BOOT_NATIVE_IMAGE** module compiles a Spring Boot application into a GraalVM Native Image using Spring AOT to evaluate startup time, memory footprint, and operability. In CI, a final log line or a green build badge is not enough to conclude native tests succeeded. This lesson explains how to collect exit codes, logs, test reports, and container states to pinpoint the exact failing stage and preserve evidence for investigation.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish exit codes from builds, native tests, native executables, and containers.
2. Capture stdout, stderr, build logs, and JUnit reports without losing the original exit code.
3. Identify compile errors, Native Image generation errors, test assertions, startup failures, timeouts, and OS-terminated processes.
4. Ensure CI marks a job as failed when native tests or smoke tests fail.
5. Archive logs, test reports, environment details, and exit codes as downloadable artifacts after the job finishes.
6. Use readiness checks and container inspection to distinguish an unready application from an application running yet failing requests.
7. Design clear pass/fail criteria, avoiding false positives caused by skipped tests, missing reports, or shells masking errors.

## 2. Why Collect Multiple Types of Evidence?

Native Image involves several independent stages. A pipeline can compile the executable successfully yet fail native tests; tests may pass yet the application fails to start inside a container; the application may start yet business endpoints return errors.

| Stage | Evidence to Retain | Questions to Answer |
|---|---|---|
| Dependency resolution and Spring AOT | Build logs, dependencies/versions, AOT logs | Were configuration and dependencies prepared properly? |
| Native Image compilation | Native build logs, compiler output, exit code | Did GraalVM produce an executable? |
| Native tests | JUnit XML, HTML test reports, test logs, exit code | Which tests passed, failed, errored, or were skipped? |
| Running the executable | stdout, stderr, exit code, startup duration | Did the process start and terminate properly? |
| Container smoke test | Container logs, health status, inspect output, exit code | Does the image run in the deployment environment? |
| CI job | Job summary, artifacts, stage statuses | Does the pipeline accurately reflect every failure? |

**Exit codes indicate whether a process finished successfully or failed; logs and test reports explain why.** Store all three. Do not infer tests passed merely because the native build finished or because `BUILD FAILED` did not appear in a truncated log excerpt.

## 3. Exit Codes Are the Primary Failure Signal

On Unix/Linux shells, processes return an exit code upon termination. Common conventions:

| Exit Code | Common Meaning | How to Investigate |
|---:|---|---|
| `0` | Process reported successful completion | Also verify test reports and business conditions |
| `1` | General error from app, build tool, or script | Read logs near the failure and stack traces |
| `2` | Syntax/argument error in certain programs | Inspect command line and configuration |
| `124` | GNU `timeout` terminated the command due to timeout | Check whether startup/test hung or timeout was too short |
| `134` | Typically process terminated by `SIGABRT` | Look for fatal errors, native assertions, or library aborts |
| `137` | Typically corresponds to `SIGKILL` | Check OOM, container limits, or terminated runner |
| `139` | Typically corresponds to `SIGSEGV` | Investigate native crash, JNI, native libraries, or memory bugs |
| `143` | Typically corresponds to `SIGTERM` | Check timeouts, cancellations, or container stop operations |

The signal codes above follow the Unix shell convention `128 + signal number`; they are not absolute rules across every OS and CI provider. In particular, exit code `137` does not by itself prove an Out Of Memory event. It only indicates the process typically received `SIGKILL`; inspect container status, memory limits, and runner logs to identify the root cause.

Exit code `0` alone is also insufficient to prove the system is healthy. For instance, a test task might be configured to ignore failures, discover zero tests, or fail to run native tests as intended. Verify exit codes alongside test counts and JUnit reports.

## 4. Capturing stdout, stderr, and Exit Codes in Shell Scripts

A common mistake is running a command in a pipeline and capturing only `tee`'s exit code. A simple, controllable approach is redirecting output to a file, capturing the exit code immediately after the command, and then printing the log:

```bash
#!/usr/bin/env bash
set -u

mkdir -p ci-artifacts

set +e
./gradlew nativeTest --no-daemon --console=plain --stacktrace \
    > ci-artifacts/native-test.log 2>&1
test_rc=$?
set -e

cat ci-artifacts/native-test.log
printf 'nativeTest_exit_code=%s\n' "$test_rc" \
    > ci-artifacts/native-test-exit-code.txt

exit "$test_rc"
```

In this example, stdout and stderr are merged into one file to preserve message ordering. To analyze both streams separately, use:

```bash
set +e
./gradlew nativeTest --no-daemon --console=plain --stacktrace \
    > ci-artifacts/native-test.stdout.log \
    2> ci-artifacts/native-test.stderr.log
test_rc=$?
set -e

printf 'nativeTest_exit_code=%s\n' "$test_rc" \
    > ci-artifacts/native-test-exit-code.txt
exit "$test_rc"
```

Place `set +e` right before the command whose exit code you want to capture so the shell does not exit before assigning `test_rc`. Once the exit code is saved, you can re-enable `set -e`. At the end of the script, return the exact failure code so CI marks the step/job as failed.

### 4.1. When `tee` Is Needed

`tee` is useful when you want both live log streaming in CI and a saved file. Enable `pipefail` and disable `errexit` around the captured section:

```bash
set +e
set -o pipefail

./gradlew nativeTest --no-daemon --console=plain --stacktrace \
    2>&1 | tee ci-artifacts/native-test.log
test_rc=$?

set -e
printf 'nativeTest_exit_code=%s\n' "$test_rc" \
    > ci-artifacts/native-test-exit-code.txt
exit "$test_rc"
```

`pipefail` makes a pipeline return a non-zero status if any command in the pipeline fails. Without `pipefail`, a standard pipeline returns the exit code of the last command (`tee`); when Gradle fails yet `tee` writes the file cleanly, the shell can report `0` and CI mistakenly treats it as passing.

### 4.2. Never Let Scripts Swallow Errors Accidentally

The following patterns can make CI report success even though native tests failed:

```bash
# Wrong: echo is the last command so the status is usually 0.
./gradlew nativeTest
echo "Native test finished"

# Wrong: forces the exit code to 0.
./gradlew nativeTest || true

# Risks losing the exit code without pipefail enabled.
./gradlew nativeTest 2>&1 | tee native-test.log
```

If you need to run a log-collection step after a test fails, save the exit code first, run the collection step, and then return the original exit code. Never use `|| true` on a test gate; reserve it strictly for cleanup or optional collection steps whose outcome does not determine pass/fail.

## 5. Collecting Logs and Reports from Gradle

In projects configured with the GraalVM Native Build Tools Gradle plugin, the `nativeTest` task runs tests on Native Image. You can run:

```bash
./gradlew nativeTest --no-daemon --console=plain --stacktrace
```

For deeper investigation, add `--info`; enable `--debug` only when truly necessary because logs become massive and may contain sensitive configuration details.

Gradle report files are typically located in:

| Type | Common Path |
|---|---|
| JUnit XML | `build/test-results/nativeTest/` |
| HTML test report | `build/reports/tests/nativeTest/` |
| Console log | File created by CI redirection or `tee` |

Task names and report directories can change if the project renames source sets/tasks or customizes test report settings. Inspect the actual task outputs in your project; do not create an empty report directory and treat it as evidence tests ran.

Native Image compilation of the application is typically performed by the `nativeCompile` task. This task only verifies building the executable; run `nativeTest` or smoke tests on the executable to verify behavior:

```bash
./gradlew nativeCompile --no-daemon --console=plain --stacktrace
./gradlew nativeTest --no-daemon --console=plain --stacktrace
```

If `nativeTest` handles the required compilation steps itself, you do not necessarily need to run `nativeCompile` separately beforehand. Keep both tasks only when the pipeline requires both the application binary and the test report.

## 6. Collecting Logs and Reports from Maven

In Spring Boot projects configured with the native profile, a common way to run native tests is:

```bash
./mvnw -PnativeTest test -e
```

The `nativeTest` profile must be declared so the Maven Native Build Tools plugin binds the goal that runs tests via the native executable. Exact profile names and lifecycles depend on project configuration. Verify logs show that tests actually executed on the native executable rather than only running Surefire on the JVM.

Maven Surefire reports are typically located in:

| Type | Common Path |
|---|---|
| JUnit XML and dumps | `target/surefire-reports/` |
| Build log | File created by CI redirection or `tee` |
| Native executable/build output | Per `native-maven-plugin` and Spring Boot plugin configuration |

To diagnose plugin or lifecycle behavior, use `-X` to capture Maven debug logs. Enable it only when needed because the logs are huge and may expose internal URLs, environment variables, or configuration parameters. Inspect and redact before archiving long-lived artifacts.

A Maven command returning `0` must be cross-checked against the Surefire report: tests run, failures, errors, and skipped counts. If tests were skipped due to environment conditions or a wrong profile, the pipeline must handle it according to an explicit policy rather than assuming native tests passed.

## 7. Recording Each Stage's Results Separately

Do not rely on a single overall exit code for the whole pipeline without knowing which step produced it. Write a status file per stage:

```text
ci-artifacts/
  native-build.log
  native-build-exit-code.txt
  native-test.log
  native-test-exit-code.txt
  application-smoke.log
  application-smoke-exit-code.txt
  container-inspect.json
  container-logs.log
  test-reports/
```

Example script running build and tests:

```bash
#!/usr/bin/env bash
set -u

mkdir -p ci-artifacts

set +e
./gradlew nativeCompile --no-daemon --console=plain --stacktrace \
    > ci-artifacts/native-build.log 2>&1
build_rc=$?
set -e

printf '%s\n' "$build_rc" > ci-artifacts/native-build-exit-code.txt
cat ci-artifacts/native-build.log

if [ "$build_rc" -ne 0 ]; then
    exit "$build_rc"
fi

set +e
./gradlew nativeTest --no-daemon --console=plain --stacktrace \
    > ci-artifacts/native-test.log 2>&1
test_rc=$?
set -e

printf '%s\n' "$test_rc" > ci-artifacts/native-test-exit-code.txt
cat ci-artifacts/native-test.log

exit "$test_rc"
```

The script stops if native compilation fails because tests cannot run on an unbuilt binary. If the build succeeds yet tests fail, the script returns the test exit code. CI still needs an artifact upload step running under `always()` or `if: always()` so logs and reports are saved even when the script exits non-zero.

If the pipeline has multiple independent steps, record each step's exit code separately and aggregate the final verdict according to gate policy. Never overwrite the build status file with the test status.

## 8. Testing the Native Executable Directly

The native test task tests the test suite. Some failures only surface when running the application executable with production-like configuration, so a separate smoke test is required:

```bash
mkdir -p ci-artifacts
set +e
timeout --signal=TERM --kill-after=10s 120s \
    ./build/native/nativeCompile/orders-service \
    > ci-artifacts/application-smoke.log 2>&1
app_rc=$?
set -e

printf 'application_exit_code=%s\n' "$app_rc" \
    > ci-artifacts/application-smoke-exit-code.txt
cat ci-artifacts/application-smoke.log
exit "$app_rc"
```

The executable path in the example is illustrative; use the actual output path from your Gradle/Maven build. GNU `timeout` returns `124` upon timing out and may return `137` if the process is killed after the grace period. If the binary is a long-running web server, do not use the command above as a complete test because a healthy server will not exit on its own; use readiness checks and smoke requests instead.

### 8.1. Readiness Check for a Spring Boot Application

For an application with an Actuator readiness endpoint, a simple smoke test workflow:

```bash
#!/usr/bin/env bash
set -u

mkdir -p ci-artifacts
./orders-service > ci-artifacts/application.log 2>&1 &
app_pid=$!

ready=0
for attempt in $(seq 1 30); do
    if curl --fail --silent --show-error \
        http://127.0.0.1:8080/actuator/health/readiness; then
        ready=1
        break
    fi
    sleep 2
done

if [ "$ready" -ne 1 ]; then
    cat ci-artifacts/application.log
    kill "$app_pid" 2>/dev/null || true
    wait "$app_pid" 2>/dev/null || true
    exit 1
fi

curl --fail --silent --show-error \
    http://127.0.0.1:8080/api/orders/health-check
smoke_rc=$?

kill "$app_pid" 2>/dev/null || true
wait "$app_pid"
app_rc=$?

cat ci-artifacts/application.log
printf 'smoke_exit_code=%s\n' "$smoke_rc" \
    > ci-artifacts/application-smoke-exit-code.txt
printf 'application_exit_code=%s\n' "$app_rc" \
    > ci-artifacts/application-exit-code.txt

if [ "$smoke_rc" -ne 0 ]; then
    exit "$smoke_rc"
fi
if [ "$app_rc" -ne 0 ] && [ "$app_rc" -ne 143 ]; then
    exit "$app_rc"
fi
```

Adjust the example to your actual endpoints, ports, authentication, and how the application handles `SIGTERM`. The readiness endpoint must be enabled and accessible in the test environment. If the application requires a database or cache, the readiness check and smoke request should verify those dependencies are ready.

Do not treat a single failed `curl` right after process launch as a broken application; the server needs time to start. Conversely, do not wait indefinitely: bound the wait time and preserve logs to see whether the app failed to bind its port, hit a configuration error, or could not connect to dependencies.

## 9. Collecting Logs and Exit Codes from Docker Containers

For a container running a finite (one-shot) task, keep the container after completion to inspect logs and state:

```bash
set +e
docker run --name orders-native-ci orders-native:ci \
    > ci-artifacts/container-run.log 2>&1
docker_rc=$?

docker inspect orders-native-ci \
    > ci-artifacts/container-inspect.json
inspect_rc=$?

docker logs orders-native-ci \
    > ci-artifacts/container-logs.log 2>&1
logs_rc=$?

docker rm orders-native-ci
rm_rc=$?

printf 'docker_run_exit_code=%s\n' "$docker_rc" \
    > ci-artifacts/container-exit-code.txt

if [ "$docker_rc" -ne 0 ]; then
    exit "$docker_rc"
fi
if [ "$inspect_rc" -ne 0 ] || [ "$logs_rc" -ne 0 ]; then
    exit 1
fi
if [ "$rm_rc" -ne 0 ]; then
    exit "$rm_rc"
fi
```

Do not pass `--rm` in this example because you need to inspect the container after the process exits. If cleanup is needed in all cases, place `docker rm` in a trap or CI cleanup step. For background server containers, use `docker run -d`, verify health/readiness, send requests, and collect `docker logs` and `docker inspect` before stopping/removing the container.

Key fields in `docker inspect`:

- `State.Status`: container status.
- `State.Running`: whether the container is still running or stopped.
- `State.ExitCode`: exit code of the container's main process.
- `State.OOMKilled`: whether Docker recorded the container as OOM-killed.
- `State.Error`: runtime error when creating or starting the container.
- `State.Health.Status`: health check status if the image defines a health check.

The exit code of the `docker run` command, `State.ExitCode`, and the exit code of `docker inspect` are three separate values. Save them under distinct names to avoid confusion. For server containers, `Running` alone does not prove endpoints are ready; inspect health status or send real requests.

## 10. Classifying Failures from Logs and Reports

| Symptom | Likely Failing Stage | Evidence to Inspect |
|---|---|---|
| `UnsupportedFeatureError`, missing registration, or reachability error | Native Image analysis/build | Native build log, stack trace, Runtime Hints, and metadata |
| Compiler error or linker error | Native compilation | GraalVM compiler output, toolchain, OS/architecture |
| JUnit failure/error | Native tests | XML report, test name, assertion, and test log |
| Process exits before logging `Started` | Startup/runtime initialization | Native stderr, stack trace, config, resources, and dependencies |
| Process starts yet readiness is never reached | Startup or dependencies | Application log, health details, DB/cache/network status |
| HTTP smoke request returns 4xx/5xx | Application behavior | Request/response, security config, server logs, and correlation ID |
| Container exit `137` or `OOMKilled=true` | Container/runtime resources | Docker inspect, memory limits, runner/container events |
| Container exit `139` | Native crash | stderr, core dump if available, JNI/native libraries, and architecture |
| Test report does not exist | Tests did not run or wrong report path | CI command, task execution log, and test report config |
| Exit code `0` yet test count is 0 | Wrong test discovery/profile/filter | JUnit XML, Gradle/Maven summary, and test selectors |

Do not simply `grep` for the keyword `FAILED` and jump to conclusions. A log may contain the word `failed` inside a retry message while tests ultimately pass; conversely, a process can be killed before printing `BUILD FAILED`. Use exit codes and structured reports as primary signals, and logs to explain why.

## 11. Saving Test Reports and Artifacts Even When Jobs Fail

CI systems normally skip subsequent steps once a step returns non-zero. If the artifact upload step is also skipped, vital logs are lost. Configure the upload step to always run:

```yaml
steps:
  - name: Run native tests
    shell: bash
    run: |
      set +e
      ./gradlew nativeTest --no-daemon --console=plain --stacktrace \
        > native-test.log 2>&1
      test_rc=$?
      cat native-test.log
      printf '%s\n' "$test_rc" > native-test-exit-code.txt
      exit "$test_rc"

  - name: Upload native test diagnostics
    if: always()
    uses: actions/upload-artifact@v4
    with:
      name: native-test-diagnostics
      if-no-files-found: warn
      path: |
        native-test.log
        native-test-exit-code.txt
        build/test-results/nativeTest/
        build/reports/tests/nativeTest/
```

This example is for GitHub Actions. On other CI providers, use the equivalent `always()`/`finally` condition to upload reports after a test failure. The upload condition must never turn the test step green; the test step itself must still return its original exit code.

Artifacts should contain:

- Native build and native test logs.
- Exit codes from each stage.
- JUnit XML and HTML reports.
- stdout/stderr logs of the executable or container.
- `docker inspect` output or equivalent runtime status.
- GraalVM JDK, Native Build Tools, Spring Boot, OS/architecture, and commit metadata.

Set retention appropriate for investigation needs. Logs can contain internal endpoints, usernames, queries, or test data; redact tokens/passwords and avoid storing secrets inside artifacts. If deeper logging is needed, enable it in a dedicated diagnostic pipeline with restricted access.

## 12. Pass/Fail Criteria for Native CI

A native test job should pass only when all mandatory conditions are met:

1. Native Image build completes with exit code `0`.
2. Native test task/goal actually executes and returns exit code `0`.
3. Test report is generated at the expected location, tests ran, and there are zero failures/errors.
4. No critical tests were skipped outside documented policy.
5. Native executable starts within the allowed time budget.
6. Readiness endpoint and business smoke requests return expected results.
7. Container was not OOM-killed or crashed; exit code and health state are appropriate.
8. Logs, reports, and exit codes were uploaded even when the job fails.

Example gate matrix:

| Condition | Pass | Fail |
|---|---|---|
| Native build | Exit code `0` | Non-zero or timeout |
| Native tests | Exit code `0`, valid report | Assertion/error or tests did not run |
| Test report | XML present, test count greater than 0 | Missing report, empty report, or parse failure |
| Startup | Readiness reached before deadline | Process exited or readiness timed out |
| Smoke request | HTTP status and body match expectations | Request failed or unexpected response |
| Container | No OOM/crash, appropriate state | OOMKilled, runtime error, or unexpected exit |
| Diagnostics | Artifacts archived | Missing logs/reports for investigation |

If a project intentionally lacks native tests for a dependency or an environment does not support containers, document the `Not Applicable` condition explicitly and require an approved replacement gate in the pipeline design. Never automatically treat skipped tests as passing.

## 13. Hands-on Exercise

Set up a CI job for a Spring Boot service that already has a native build:

1. Run `nativeCompile` and save `native-build.log` along with `native-build-exit-code.txt`.
2. Run `nativeTest`, saving logs, JUnit XML, and HTML reports.
3. Intentionally make a test fail to verify the command returns non-zero and the pipeline transitions to failed.
4. Intentionally use a short timeout to verify logs and exit code `124` are captured.
5. Run the native executable with a readiness check and a smoke request.
6. Package/run the container, saving `docker logs`, `docker inspect`, and exit codes.
7. Configure artifact uploads to run even when tests/builds fail.
8. Test a skipped-test or zero-test-count case and verify the gate does not report pass.

Report template:

| Evidence | File or Value | Result |
|---|---|---|
| Native build log | `native-build.log` | Present/Missing |
| Native build exit code | `native-build-exit-code.txt` | `0`/non-zero |
| Native test log | `native-test.log` | Present/Missing |
| JUnit report | XML/HTML | Test count, failures, skipped |
| Application log | `application-smoke.log` | Startup/readiness |
| Container inspect | `container-inspect.json` | Status, exit code, OOM |
| CI artifact | Artifact name and retention | Uploaded/Not yet |
| Job result | Pass/Fail | Accurately reflects simulated failure? |

## 14. Self-Check Questions

1. Why must exit codes and logs be saved together?
2. Why can `tee` lose Gradle's exit code if `pipefail` is not enabled?
3. Does a successful `nativeCompile` prove native tests pass?
4. Where are Gradle native test reports typically located, and why must you verify the actual path?
5. How can CI still upload JUnit reports after a test step returns non-zero?
6. What does exit code `137` prove, and what does it not prove?
7. Why does a `Running` container not mean the application is ready?
8. When should you use a timeout for a native executable versus a readiness check?
9. Why must a test count of 0 be treated as a problem?
10. What data must be redacted before archiving CI artifacts?

## Key Takeaways

**CI can only verify failures reliably when exit codes, logs, and test reports from every stage are preserved intact.** Capture output without masking shell errors, distinguish build/test/startup/container stages, use readiness checks for servers, inspect container states, and upload artifacts even when jobs fail. A successful native build is a necessary signal; final verdicts must rest on native tests and real smoke tests.

## References

- [Gradle — Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html): test tasks, JUnit XML, and HTML reports.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): console output, stacktrace, and task execution.
- [GraalVM Native Build Tools — Gradle Plugin](https://graalvm.github.io/native-build-tools/latest/gradle-plugin): `nativeTest`, `nativeCompile`, and native build configuration.
- [GraalVM Native Build Tools — Maven Plugin](https://graalvm.github.io/native-build-tools/latest/maven-plugin.html): native test goal and Maven configuration.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): testing Spring Boot applications.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): health endpoints and readiness state.
- [Docker — Run containers](https://docs.docker.com/reference/cli/docker/container/run/): exit status and running containers.
- [Docker — Inspect containers](https://docs.docker.com/reference/cli/docker/container/inspect/): status, exit code, and runtime info.
- [GitHub Actions — Store and share data with workflow artifacts](https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts): uploading and storing artifacts after a job finishes.
