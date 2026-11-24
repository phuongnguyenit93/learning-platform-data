# Retaining Reports, Logs, and Evidence When CI Fails

When a test fails on a developer's machine, the author can inspect the console, debugger, and environment state immediately. In CI, jobs often terminate right after printing a `BUILD FAILED` line; if reports, logs, and diagnostic data are not saved as artifacts, reproducing the failure becomes much harder. Therefore, a Spring testing pipeline must prepare outputs that remain readable after the job finishes, even when the test command exits with a non-zero code.

Retaining evidence should cover test framework results, application logs, environment details, and additional data suited to the test type. Artifacts must be tied to the exact run, uploaded even when tests fail, and protected against accidentally exposing sensitive data.

## 1. Evidence Worth Retaining

A single stack trace line is rarely enough to explain a CI failure. Identify which types of evidence answer the questions: which test failed, which assertion did not hold, how the Spring context was constructed, what requests were sent, and how the environment differed from a passing run.

| Evidence type | Contents | Common sources |
|---|---|---|
| Test report | Test names, pass/fail/skip status, duration, exceptions, and stack traces | JUnit XML, Surefire/Failsafe, Gradle test reports |
| HTML report | Summary and per-test details for reading in a browser | Gradle HTML report or reporting plugins |
| Test output | `System.out`, `System.err`, logs written by tests | Gradle test logging, Maven Surefire output files |
| Application log | Logs from Spring Boot, controllers, services, repositories, and HTTP clients | Logback/Log4j2, test log files |
| Context diagnostics | `ApplicationContext` loading/caching/closing, condition evaluation | Spring TestContext logs, Spring Boot diagnostics |
| Request/response evidence | Method, URL, filtered headers, status, and redacted bodies | Mock servers, WebTestClient, MockMvc, client logging |
| UI evidence | Screenshots, videos, browser console, and network traces | Browser testing frameworks |
| Runtime diagnostics | Thread dumps, JVM crash logs, heap dumps when needed | `jstack`, `jcmd`, JVM flags |
| External service logs | Containers, databases, message brokers, or mock services | Docker/Testcontainers and CI service logs |
| Run metadata | Commit, branch, JDK, OS, build tool, test filters, retries, and matrix dimensions | CI variables and build metadata |

Not every test needs every artifact type. Unit tests usually need only reports and logs; integration tests may additionally need container/service logs; UI tests may need screenshots or videos; hanging tests may need thread dumps.

## 2. Distinguish Test Reports from Logs

Test reports answer *which tests ran and what their outcomes were*. Logs provide context on *what happened while tests were running*.

JUnit XML typically contains test cases, durations, failures/errors, and stack traces. CI can parse XML to display failed tests directly in pull request UIs. HTML reports let developers browse detailed results without reading raw XML.

Logs can show which endpoint a request hit, which profile Spring selected, whether the context cache was reused, or where a service threw an error. Logs do not replace test reports: logs may not flush if a JVM is killed, whereas XML may be written after each test or after each fork depending on the runner.

With Maven, Surefire typically stores unit test results in `target/surefire-reports/`; Failsafe stores integration test results in `target/failsafe-reports/`. With Gradle, results typically live in `build/test-results/test/` and HTML reports in `build/reports/tests/test/`. Paths may change if the project configures custom tasks or report destinations.

## 3. Retain JUnit XML and HTML Reports

### Maven Surefire and Failsafe

Surefire runs unit tests; Failsafe typically runs integration tests through the `integration-test` and `verify` phases. When tests fail, Maven can still generate reports before returning a non-zero exit code. CI should upload the report directories after the build command.

You can configure Surefire to save each test's stdout/stderr to files:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <redirectTestOutputToFile>true</redirectTestOutputToFile>
    </configuration>
</plugin>
```

Apply the same setting to `maven-failsafe-plugin` if you want to save integration test output. XML reports and per-test output files make reviewing failures possible without digging through the entire Maven console log.

Default paths typically needing upload:

```text
target/surefire-reports/
target/failsafe-reports/
```

For multi-module Maven projects, use globs such as `**/target/surefire-reports/**` and `**/target/failsafe-reports/**` to collect reports from every module.

### Gradle Test

Gradle generates JUnit XML and HTML reports for `Test` tasks. You can configure test logging to show full exceptions and standard streams in the console:

```groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()

    testLogging {
        events "failed", "skipped"
        exceptionFormat "full"
        showStandardStreams = true
    }
}
```

`showStandardStreams` helps when tests write to `System.out` or `System.err`, though you should not use `println` as the application's primary logging mechanism. A logging framework provides clearer log levels, formatting, and output routing.

Default directories typically needing upload:

```text
build/test-results/test/
build/reports/tests/test/
```

For integration tests run by a dedicated task such as `integrationTest`, also collect `build/test-results/integrationTest/` and `build/reports/tests/integrationTest/`. Check the actual task names in the project rather than assuming every test runs under the `test` task.

## 4. Configure Useful Logging for Spring Test

When a Spring context fails during startup, default logs sometimes show only an exception at the end of a chain. Enable targeted logging to see which contexts Spring creates, reuses, or closes.

Example in `src/test/resources/application-test.properties`:

```properties
logging.level.org.springframework.test.context=DEBUG
logging.level.org.springframework.test.context.cache=DEBUG
logging.level.org.springframework.boot.test.context=DEBUG
```

Or YAML:

```yaml
logging:
  level:
    org.springframework.test.context: DEBUG
    org.springframework.test.context.cache: DEBUG
    org.springframework.boot.test.context: DEBUG
```

These loggers are useful when investigating context caching, bootstrapping, and context loading errors. Enable DEBUG level only in test profiles or diagnostic jobs when needed, as verbose logs can grow large and slow down CI.

If the project does not use Spring Boot, configure loggers in `src/test/resources/logback-test.xml` or the equivalent config file for your logging framework. Ensure the test configuration loads on the test runtime classpath; a config file existing only in main resources may not suit test-specific diagnostics.

With Spring Boot, `debug=true` can print a condition evaluation report in some startup contexts. It helps identify which auto-configurations applied, though it does not replace test context logs or full stack traces.

## 5. Make Logs Correlatable to the Running Test

When multiple tests run in parallel, logs from multiple threads can interleave. Each log line should include timestamp, level, thread name, and logger so readers know where events originated.

Example Logback pattern for tests:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

If logs need to be tied to a test method, add a test identifier to MDC inside a JUnit extension or listener and include `%X{testId}` in the pattern. Always clear MDC in `afterEach`/`finally` because threads can be reused for subsequent tests.

Do not dump all environment variables or system properties into logs. They can contain access tokens, passwords, private endpoints, or internal details. Log only the non-sensitive values necessary to reproduce the environment.

## 6. Collect Spring `ApplicationContext` Diagnostics

For Spring Test failures, the following details are typically very useful:

- The test class and method loading the context.
- Active profiles and test property sources.
- Relevant context customizers or initializers.
- Context cache hits/misses and whether a context was marked dirty.
- The root cause in the exception chain, especially the innermost exception beneath wrappers like `Failed to load ApplicationContext`.
- The bean or configuration class causing dependency injection failure.

When a context fails, preserve the entire stack trace rather than only the final exception line. Many Spring errors are wrapped in `BeanCreationException`, `UnsatisfiedDependencyException`, or `ApplicationContextException`; the root cause usually sits deeper in the `Caused by` chain.

Do not turn on DEBUG logging for all of `org.springframework` upfront unless necessary. Start with test context packages or specific beans to reduce noise, then broaden if needed.

## 7. Keep Request/Response Diagnostics Safe

With MockMvc, WebTestClient, or HTTP client tests, requests and responses can be crucial evidence. However, bodies and headers sometimes contain personal data, session cookies, bearer tokens, or credentials.

Log fields useful for diagnosis:

- HTTP method and path (omitting sensitive query parameters if needed).
- Status code, content type, and processing duration.
- A non-secret correlation ID or test case ID.
- Relevant header names with redacted values.
- A filtered portion of the response body when it contains no sensitive data.

Illustrative example of token-redacted logging:

```text
request method=POST path=/api/orders testId=create-order-42
request header Content-Type=application/json
request header Authorization=[REDACTED]
response status=201 contentType=application/json durationMs=34
```

Never store raw `Authorization`, `Cookie`, passwords, private keys, or production payloads. If bodies are needed for reproduction, use synthetic data and apply redaction before writing artifact files.

## 8. Screenshots, Videos, and Browser Evidence

For browser-based end-to-end tests, screenshots or videos can show the UI at the moment of failure. Capture screenshots on failure or right before steps likely to fail, name them after the test case, and store them in a dedicated artifact directory.

Example structure:

```text
build/test-artifacts/
  screenshots/
    checkout-should-show-validation-error.png
  videos/
    checkout-flow.webm
  browser/
    console.log
    network-summary.json
```

Browser console logs and network traces may contain cookies, tokens, internal URLs, or user data. Collect only what is necessary and redact sensitive values before uploading. For screenshots, consider masking personal details or test account data.

Not every backend test needs screenshots. Enable this evidence type only for UI or browser-automation tests.

## 9. Thread Dumps, Heap Dumps, and JVM Crash Logs

When CI times out or tests hang, test reports may only record a timeout without showing where threads are blocked. Thread dumps reveal the stacks of all threads at capture time.

In environments with process access, you can use:

```bash
jcmd <pid> Thread.print
```

Or:

```bash
jstack <pid>
```

For `OutOfMemoryError`, the JVM can be configured to produce heap dumps:

```text
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=build/test-artifacts/heapdump.hprof
```

JVM crash logs can be written via `-XX:ErrorFile=...` or appear as `hs_err_pid*.log`, depending on JVM settings.

Thread dumps and heap dumps can be large and contain sensitive data such as request payloads, credentials, or object state. Capture them only when justified, limit capture frequency, restrict access permissions, and set retention policies. Heap dumps typically do not need to be uploaded on every test run.

## 10. Collect Container and Supporting Service Logs

Integration tests may use PostgreSQL, Kafka, Redis, WireMock, or services started with Testcontainers. When a test fails, logs from the test process alone may not explain errors inside a container.

Save:

- Container or service names and image tags/versions.
- Container logs during the test execution window.
- Port mappings or endpoints with sensitive data redacted.
- Health status and container startup timing.
- Testcontainers startup logs when failures occur during container creation.

Example of fetching container logs with Docker:

```bash
docker logs <container-name>
```

When using Testcontainers, configure a log consumer or collect container logs in teardown/failure hooks. Make sure collection does not alter test state or leak service authentication credentials.

## 11. Create a Consistent Artifact Directory

Gather test-generated evidence into a purposeful directory such as `build/test-artifacts/`. This lets CI upload via a clean pattern and avoids accidentally collecting files from the source tree.

Example overall layout:

```text
build/
  test-results/
    test/
      TEST-*.xml
  reports/
    tests/
      test/
        index.html
  test-artifacts/
    run-metadata.txt
    application.log
    screenshots/
    browser/
    containers/
    dumps/
```

Metadata should record commit SHA, branch, build/run ID, attempt/retry, JDK, OS, build tool version, test task or test filter, and matrix dimensions. Do not record secrets or the entire environment.

Include the run ID and attempt in artifact names to avoid confusion between initial runs and retries. If CI runs a matrix, include OS/JDK/module in the artifact name.

## 12. Upload Artifacts Even When Tests Fail

This is the most important step in the pipeline. A test command returning a non-zero exit code usually skips subsequent steps by default. The upload step must use an always-run condition or a run-on-failure condition.

GitHub Actions example with Gradle:

```yaml
name: test
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Run tests
        run: ./gradlew test

      - name: Upload test evidence
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: test-evidence-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            **/build/test-results/**
            **/build/reports/tests/**
            **/build/test-artifacts/**
          if-no-files-found: warn
          retention-days: 14
```

`always()` allows the upload step to run after the test step fails. If you only want to keep artifacts when a job fails, you can use `if: ${{ failure() }}`. Use `always()` when you also want reports from passing runs for baseline comparison; use `failure()` when you want to reduce storage usage.

GitHub Actions example with Maven:

```yaml
- name: Run Maven verification
  run: ./mvnw --batch-mode verify

- name: Upload Maven test reports
  if: ${{ always() }}
  uses: actions/upload-artifact@v4
  with:
    name: maven-test-evidence-${{ github.run_id }}-${{ github.run_attempt }}
    path: |
      **/target/surefire-reports/**
      **/target/failsafe-reports/**
      **/target/test-artifacts/**
    if-no-files-found: warn
    retention-days: 14
```

For Maven integration tests, use `verify` when Failsafe is configured in the standard lifecycle. Running `test` alone may run only Surefire and skip the integration-test/verify phases.

If a pipeline has multiple jobs or a matrix, upload artifacts in the job that generates the reports. An aggregation job can download artifacts from child jobs to build a combined report, but it should not wait until aggregation to attempt accessing another runner's build directory.

## 13. Collect Extra Diagnostics When a Job Fails or Times Out

Standard reports and logs should be uploaded on every run. Heavy data such as thread dumps, container logs, or heap dumps can be collected only on failure or timeout.

Example conditional diagnostics step in GitHub Actions:

```yaml
- name: Capture JVM diagnostics
  if: ${{ failure() }}
  shell: bash
  run: |
    mkdir -p build/test-artifacts/diagnostics
    ps -ef > build/test-artifacts/diagnostics/processes.txt
    docker ps -a > build/test-artifacts/diagnostics/containers.txt
```

To capture a thread dump, the pipeline needs the PID of the test JVM. When Gradle forks test workers, the Gradle daemon PID is not necessarily the PID of the hanging worker. You can configure the test worker to write its PID to a metadata file on startup or use the test runner's timeout hook to capture dumps from the exact process.

If a job is force-canceled or a runner dies, final upload steps may not run. When such failures matter, configure reasonable CI timeouts, diagnostic capture prior to process termination, and log streaming to external storage.

## 14. Make Artifacts Easy to Find and Read

A directory containing thousands of files helps little if you cannot tell which file belongs to the failing test. Use stable names and link them to test cases:

- Screenshot filenames include the class/method or test ID.
- Logs record timestamps, threads, and test IDs.
- Metadata records commit SHA, run ID, and attempt.
- XML reports preserve test case names and failure messages.
- Dump files include timestamps and PIDs.
- Artifact names include module, task, OS/JDK matrix, and retry if applicable.

Example non-sensitive metadata:

```text
commit=8f2a6c1
branch=feature/order-validation
run_id=48291
run_attempt=2
java=21
os=ubuntu-latest
build_tool=gradle
task=integrationTest
test_filter=com.example.OrderControllerIT
```

If a test is retried, retain reports from each attempt or at least clearly identify the final attempt. Retries can make intermittent failures disappear; the first attempt's report remains valuable for investigation.

## 15. Retention, Access Control, and Sensitive Data

Test artifacts can contain data closer to production than developers assume. Request bodies, database snapshots, heap dumps, browser traces, and logs can include emails, tokens, cookies, addresses, or customer information.

Apply these principles:

- Use synthetic data or dedicated test accounts.
- Redact tokens, passwords, cookies, authorization headers, and personal data before writing artifacts.
- Never upload `.env` files, private keys, credential stores, or the runner's entire home directory.
- Restrict artifact read permissions according to repository/project access controls.
- Set retention periods aligned with investigation needs and storage policies.
- Use shorter retention for heap dumps, database dumps, and browser traces containing sensitive data.
- Never paste sensitive artifacts into pull request comments or public build logs.

The 14-day retention period in the examples is illustrative only. Projects should choose retention durations based on internal policy, storage volume, and investigation requirements.

## 16. When Reports Are Missing or Not Generated

Not every failure mode produces complete reports:

| Symptom | Possible cause | Resolution |
|---|---|---|
| No JUnit XML | Test task never ran, reporting disabled, or process killed too early | Verify the task actually executed and report output is enabled |
| HTML report exists but no XML | XML reporting disabled or custom task configuration | Enable JUnit XML so CI can parse machine-readable results |
| XML exists but application logs are missing | Logging writes only to console or log file is outside artifact paths | Route test logs into the artifact directory and upload that directory |
| Upload step skipped after test failure | Step uses the default condition running only after prior success | Use `always()` or `failure()` as appropriate |
| Artifact reports no files found | Wrong glob, different module path, or reports not generated | Check working directory and actual paths; use `if-no-files-found: warn` |
| Test times out with no stack trace | Runner kills JVM before reports finish writing | Capture thread dumps before timeout or increase grace/diagnostic window |
| Artifacts too large | Uploading heap dumps, videos, or unbounded DEBUG logs | Collect conditionally, compress, or cap count and retention |
| Logs cannot identify which test caused an entry | Parallel tests lack thread/test IDs | Add timestamps, thread names, and test identifiers |

## 17. Workflow for Handling a CI Failure

When a job reports a test failure, follow this sequence:

1. Open the JUnit XML or HTML report to pinpoint the exact failing class, method, and assertion.
2. Read the full stack trace and find the first root cause rather than stopping at the outer wrapper exception.
3. Locate logs matching the timestamp/test ID to understand what the request, Spring context, and service did.
4. If the failure involves context loading, inspect active profiles, context cache logs, and the bean creation chain.
5. For integration tests, check container/service logs and endpoint/port metadata.
6. If the test hung or timed out, inspect thread dumps and process diagnostics.
7. Compare run metadata against a passing run: commit, JDK, OS, matrix, test filter, and retry count.
8. Reproduce the failure with the same test filter and closest possible environment.

Do not conclude the cause from a single `Tests failed` line. Use reports to identify the test, logs to understand what transpired, and metadata to verify the run's environment.

## 18. Example Logging and Reporting Setup for the `test` Profile

With Spring Boot, you can create `src/test/resources/application-test.properties` to enable diagnostic logging:

```properties
logging.level.org.springframework.test.context=DEBUG
logging.level.org.springframework.test.context.cache=DEBUG
logging.level.org.springframework.boot.test.context=DEBUG
```

Test class activating the profile:

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderIntegrationTests {
    // Test uses logging configuration and beans for the test profile.
}
```

In CI, add a step writing metadata to `build/test-artifacts/run-metadata.txt` before running tests. When the job fails, upload metadata, JUnit XML, HTML reports, and application logs in a single artifact or clearly related artifacts.

## 19. Takeaways

To investigate CI failures effectively, retain JUnit XML/HTML reports, stdout/stderr, application logs, Spring context diagnostics, and run metadata. Integration or UI tests may also require container logs, request/response evidence, screenshots, or thread dumps. Place reports in stable directories, upload artifacts using conditions that still run after test failures, tag artifacts with run ID/attempt, and keep appropriate retention. Redact credentials and personal data before saving. When sufficient reports, logs, and metadata are available, developers can identify the failing test, understand what happened, and reproduce the bug without re-running CI solely to gather evidence.

