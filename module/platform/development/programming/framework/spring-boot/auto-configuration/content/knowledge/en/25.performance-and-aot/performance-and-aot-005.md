# Measuring Startup Time Before and After Changes with Identical Dependencies and Configuration

When optimizing Spring Boot, a number like "Started in 4.2 seconds" is meaningful only when we know where the clock starts and stops, whether the two runs share identical conditions, and whether the measurement is repeatable. A change may reduce ApplicationContext creation time without improving when the service actually accepts traffic. Conversely, lazy initialization may make startup faster while shifting part of the work to the first request.

The goal of a before/after measurement is to determine **how much a code change reduced the time from launching the process until the application is ready to serve**, while dependencies, configuration, JVM, host machine, and packaging are held constant.

Measure two complementary layers:

- **Process-to-ready:** time from spawning the JVM process until the readiness endpoint returns HTTP 200. This is the primary metric for evaluating the startup time a deployment platform must wait for.
- **Spring startup steps:** internal Spring steps such as preparing the Environment, creating beans, and refreshing the context. This data helps pinpoint where changes come from.

Do not add the two durations together. Startup steps explain the overall measurement; they are not an independent metric replacing process-to-ready time.

## 1. Define Exact Start and End Milestones

There are at least three milestones commonly grouped together as "startup time":

| Milestone | Start | End | Includes |
| --- | --- | --- | --- |
| JVM process-to-ready | Before spawning the java process | Readiness probe returns 200 OK | JVM initialization, class loading, Spring, embedded server, runners, and traffic-accepting point. |
| SpringApplication startup | When SpringApplication starts running | ApplicationReadyEvent or readiness event | Internal Spring work; excludes full JVM time before entering Spring. |
| Context refresh | When ApplicationContext refresh begins | ContextRefreshedEvent/context refresh finishes | Part of Spring's process; excludes full JVM, web server, and runners. |

For web services, use readiness as the end milestone. Spring Boot emits ApplicationStartedEvent after context refresh, yet before running ApplicationRunner and CommandLineRunner. ApplicationReadyEvent is emitted after runners; immediately afterward readiness transitions to ACCEPTING_TRAFFIC. Therefore, readiness more accurately reflects when the application can serve traffic.

If you only record ContextRefreshedEvent, tasks in runners may still be executing. If you look only at the "Started ..." log, remember that log reflects the SpringApplication lifecycle and does not accurately measure process spawn to when a real request is accepted.

For non-web applications, there is no HTTP readiness endpoint. You can record System.nanoTime() at the start of main and at ApplicationReadyEvent, or use a dedicated readiness signal observable by the benchmark process. Explicitly note that the measurement starts after the JVM has invoked main, so it does not include full JVM initialization time.

## 2. Keep Conditions Identical Between Both Runs

Before running, clearly define which variable is allowed to change. If measuring the impact of a code change, change only the code within the experiment scope. Keep constant:

| Category | Must Hold Constant |
| --- | --- |
| Dependencies | Identical groupId:artifactId:version, scopes, and transitive dependencies; identical Spring Boot/Spring Framework. |
| Application configuration | Identical application.properties/YAML, profiles, environment variables, system properties, and command-line arguments. |
| JVM | Identical JDK vendor/version, JVM flags, heap -Xms/-Xmx, GC, and JAVA_TOOL_OPTIONS. |
| Packaging | Identical artifact type and launch command, e.g., both using executable JAR with java -jar. |
| Machine | Identical CPU, RAM, OS, container CPU/memory limits, and storage. |
| Dependent services | Identical database, broker, cache, DNS, network, seed data, and service state. |
| Logging/instrumentation | Identical log level, Actuator, readiness probe, startup instrumentation, and polling interval. |

Do not measure the baseline with mvn spring-boot:run and the updated version with java -jar. The two launch modes have different classpaths, launchers, and preparation work. Package both and use the exact same launch command.

Check the dependency tree before and after:

```powershell
mvn dependency:tree -DoutputFile=target/dependency-tree.txt
```

Save each version's dependency tree file and compare:

```powershell
Compare-Object (Get-Content artifacts/dependencies-before.txt) (Get-Content artifacts/dependencies-after.txt)
```

If there is no output, both text files are identical. If there are differences, identify which dependency changed before attributing startup results to the code change. The dependency tree does not prove identical runtime configuration; still save and compare profiles, config files, environment variables, and JVM flags.

If the goal of the change is adding/removing a dependency, separate that into its own experiment. The conclusion is then the impact of changing the dependency graph, not the pure impact of code.

## 3. Use ApplicationStartup to Find Time-Consuming Spring Steps

Spring Framework provides ApplicationStartup and StartupStep to record startup sequence. Spring Boot provides BufferingApplicationStartup, which stores steps with timestamps and durations in a buffer. This is useful for finding which bean or phase changed after optimization.

Configuration example in a Java 17 / Spring Boot 3.3 application:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class StartupLabApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupLabApplication.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(4096)
        );

        application.run(args);
    }
}
```

Capacity 4096 is the buffer capacity, not a measurement duration. Choose it large enough for the application's startup step count; if the buffer fills up, new steps may not be recorded.

To read the data via Actuator, add the dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

And configure for the benchmark environment:

```properties
server.address=127.0.0.1
server.port=18080

management.endpoint.health.probes.enabled=true
management.endpoints.web.exposure.include=health,startup
```

When the application runs:

- GET /actuator/health/readiness is the signal the benchmark waits on for application readiness.
- GET /actuator/startup returns a snapshot of recorded startup steps.
- The startup endpoint has data only when SpringApplication is configured with BufferingApplicationStartup.
- By default, only the health endpoint is exposed over HTTP; the include setting above adds startup.

Use GET to read a snapshot. POST /actuator/startup drains the buffer, so do not use POST if you only want to observe data without emptying the buffer. Expose Actuator endpoints only on loopback or protect them with appropriate security; do not open the startup diagnostic endpoint to the public Internet.

Key fields in the JSON:

- timeline.startTime: timeline start timestamp.
- timeline.events[].startupStep.name: step name, e.g., bean instantiation step.
- timeline.events[].duration: duration of the step.
- timeline.events[].startupStep.tags: additional info such as bean name.
- parentId: relationship between parent and child steps.

Compare steps with the same name and tags between the two versions. Steps with sharp duration increases usually point to the area to investigate. Some steps are nested; **do not sum all durations** to infer total startup because parent and child step durations can overlap.

## 4. Create a Measurable Sample Application

Minimal example using Maven, Java 17, and Spring Boot 3.3.5. Keep this exact POM for both the baseline and post-change versions.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>startup-lab</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

In a real project, keep all existing dependencies; do not replace the production POM with this minimal POM just to benchmark. The sample POM only shows dependencies needed to run a standalone example.

If Actuator is not yet in the application, you can add it to **both** benchmark builds to provide readiness and startup endpoints. Adding Actuator changes the dependency set and introduces slight measurement overhead; therefore it must be added identically to both versions. If you want final numbers reflecting production when production lacks Actuator, run an additional uninstrumented pass using a readiness signal already present in the application.

## 5. Measure Process-to-Ready with an External Launcher

An external benchmark will:

1. Launch a new Java process with the same JAR and same JVM.
2. Start the clock before spawning the process.
3. Poll the readiness endpoint at a fixed interval.
4. Stop the clock upon first receiving HTTP 200.
5. Save the process log and startup JSON snapshot.
6. Shut down the process before starting the next run.
7. Discard warm-up runs and compute median, min, and max from measured runs.

Create file benchmark/StartupBenchmark.java:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

public final class StartupBenchmark {

    private static final Duration STARTUP_TIMEOUT =
            Duration.ofSeconds(120);

    private static final Duration REQUEST_TIMEOUT =
            Duration.ofSeconds(1);

    private static final long POLL_INTERVAL_MILLIS = 50;

    public static void main(String[] args) throws Exception {
        if (args.length < 5 || args.length > 6) {
            System.err.println(
                    "Usage: java StartupBenchmark <jar> <label> "
                    + "<warmups> <runs> <readiness-url> [startup-url]"
            );
            System.exit(2);
        }

        Path jar = Path.of(args[0]).toAbsolutePath();
        if (!Files.isRegularFile(jar)) {
            throw new IllegalArgumentException("JAR not found: " + jar);
        }

        String label = args[1].replaceAll("[^A-Za-z0-9._-]", "_");
        int warmups = Integer.parseInt(args[2]);
        int measuredRuns = Integer.parseInt(args[3]);

        if (warmups < 0 || measuredRuns < 1) {
            throw new IllegalArgumentException(
                    "warmups must be >= 0 and runs must be >= 1"
            );
        }

        URI readinessUri = URI.create(args[4]);
        URI startupUri = args.length == 6
                ? URI.create(args[5])
                : null;

        Path resultsDirectory = Path.of("startup-results");
        Files.createDirectories(resultsDirectory);

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(1))
                .build();

        List<Long> measurements = new ArrayList<>();

        for (int run = 1; run <= warmups + measuredRuns; run++) {
            Path logFile = resultsDirectory.resolve(
                    label + "-run-" + run + ".log"
            );

            long startedAt = System.nanoTime();

            Process process = new ProcessBuilder(
                    javaExecutable(),
                    "-jar",
                    jar.toString()
            )
                    .redirectErrorStream(true)
                    .redirectOutput(logFile.toFile())
                    .start();

            try {
                waitUntilReady(process, client, readinessUri, logFile);

                long elapsedNanos = System.nanoTime() - startedAt;
                double elapsedMillis = elapsedNanos / 1_000_000.0;

                if (run <= warmups) {
                    System.out.printf(
                            "%s warmup=%d startup_ms=%.3f%n",
                            label, run, elapsedMillis
                    );
                } else {
                    measurements.add(elapsedNanos);
                    System.out.printf(
                            "%s measured=%d startup_ms=%.3f%n",
                            label, run - warmups, elapsedMillis
                    );
                }

                if (startupUri != null) {
                    saveStartupTimeline(
                            client,
                            startupUri,
                            resultsDirectory.resolve(
                                    label + "-run-" + run + "-startup.json"
                            )
                    );
                }
            } finally {
                process.destroy();
                if (!process.waitFor(10, TimeUnit.SECONDS)) {
                    process.destroyForcibly();
                    process.waitFor();
                }
            }

            Thread.sleep(300);
        }

        measurements.sort(Long::compareTo);

        int size = measurements.size();
        double medianMillis;

        if (size % 2 == 1) {
            medianMillis = measurements.get(size / 2) / 1_000_000.0;
        } else {
            medianMillis = (
                    measurements.get(size / 2 - 1)
                    + measurements.get(size / 2)
            ) / 2_000_000.0;
        }

        double minMillis = measurements.get(0) / 1_000_000.0;
        double maxMillis = measurements.get(size - 1) / 1_000_000.0;

        System.out.printf(
                "%s summary runs=%d median_ms=%.3f min_ms=%.3f max_ms=%.3f%n",
                label, size, medianMillis, minMillis, maxMillis
        );
    }

    private static String javaExecutable() {
        boolean windows = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT)
                .contains("win");

        String executable = windows ? "java.exe" : "java";

        return Path.of(
                System.getProperty("java.home"),
                "bin",
                executable
        ).toString();
    }

    private static void waitUntilReady(
            Process process,
            HttpClient client,
            URI readinessUri,
            Path logFile
    ) throws Exception {

        long deadline = System.nanoTime() + STARTUP_TIMEOUT.toNanos();

        HttpRequest request = HttpRequest.newBuilder(readinessUri)
                .timeout(REQUEST_TIMEOUT)
                .GET()
                .build();

        while (System.nanoTime() < deadline) {
            if (!process.isAlive()) {
                throw new IllegalStateException(
                        "Application exited with code "
                        + process.exitValue()
                        + ". Check log: " + logFile
                );
            }

            try {
                HttpResponse<Void> response = client.send(
                        request,
                        HttpResponse.BodyHandlers.discarding()
                );

                if (response.statusCode() == 200) {
                    return;
                }
            } catch (IOException ignored) {
                // Server has not opened port or is not accepting requests yet.
            }

            Thread.sleep(POLL_INTERVAL_MILLIS);
        }

        throw new IllegalStateException(
                "Readiness timeout at " + readinessUri
                + ". Check log: " + logFile
        );
    }

    private static void saveStartupTimeline(
            HttpClient client,
            URI startupUri,
            Path output
    ) throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder(startupUri)
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        if (response.statusCode() == 200) {
            Files.writeString(output, response.body());
        } else {
            System.out.printf(
                    "startup endpoint returned HTTP %d%n",
                    response.statusCode()
            );
        }
    }
}
```

The program uses the same JDK running the benchmark to launch the child JAR. Each run is a fresh JVM process. Stdout/stderr logs are saved in startup-results; startup JSON is fetched **after stopping the clock**, so downloading JSON does not add to process-to-ready time.

The readiness URL in the example is http://127.0.0.1:18080/actuator/health/readiness. If the application uses another port or management base path, pass the actual URL. If Actuator is protected by Spring Security, configure the benchmark client to send test-environment-only credentials; do not disable production security just to run measurements.

## 6. Create Two Comparable Artifacts

Assume both versions produce target/startup-lab-1.0.0.jar. Save the baseline artifact before building the updated version. PowerShell example:

```powershell
New-Item -ItemType Directory -Force artifacts | Out-Null

mvn clean package
mvn dependency:tree -DoutputFile=target/dependency-tree.txt

Copy-Item target/startup-lab-1.0.0.jar artifacts/before.jar
Copy-Item target/dependency-tree.txt artifacts/dependencies-before.txt
```

After switching to the revision containing the change to measure, rebuild with the same JDK, Maven, and profile:

```powershell
mvn clean package
mvn dependency:tree -DoutputFile=target/dependency-tree.txt

Copy-Item target/startup-lab-1.0.0.jar artifacts/after.jar
Copy-Item target/dependency-tree.txt artifacts/dependencies-after.txt

Compare-Object (Get-Content artifacts/dependencies-before.txt) (Get-Content artifacts/dependencies-after.txt)
```

Keep both JARs, dependency trees, and revision info. Do not let the second build overwrite the baseline artifact. If the dependency tree differs, halt pure code comparison until the difference is explained.

You can record the environment with these commands:

```powershell
java -version
mvn -version
git rev-parse HEAD
```

Record JVM flags, profiles, and environment variables affecting Spring. `java -version` should report the exact same JDK vendor and version for both runs.

## 7. Run Repeated Benchmarks

Compile the launcher with JDK 17:

```powershell
javac benchmark/StartupBenchmark.java
```

Measure baseline with three warm-up runs and ten measured runs:

```powershell
java -cp benchmark StartupBenchmark artifacts/before.jar before 3 10 http://127.0.0.1:18080/actuator/health/readiness http://127.0.0.1:18080/actuator/startup
```

Measure the updated version with the exact same arguments:

```powershell
java -cp benchmark StartupBenchmark artifacts/after.jar after 3 10 http://127.0.0.1:18080/actuator/health/readiness http://127.0.0.1:18080/actuator/startup
```

Each run starts a process, waits for readiness HTTP 200, records elapsed time, saves logs, and fetches the startup timeline. The program computes median, min, and max of the ten measured runs; the first three runs only warm OS caches and are excluded from statistics.

For a more rigorous measurement:

- Run multiple batches and alternate order, e.g., ABBA order: baseline → after → after → baseline, to reduce effects of machine load or CPU temperature drift over time.
- Keep the same port, same data, and same dependent service state.
- Do not run builds, test suites, or other heavy tasks concurrently with the benchmark.
- Use the same timeouts, 50 ms polling interval, and same health group.
- Keep the same JAVA_TOOL_OPTIONS, -Xms, -Xmx, GC, and JVM flags.
- If cold start with a cold page cache must be measured, separately define and control how caches are cleared. Spawning a new process does not mean the OS has cleared the filesystem cache.

Three warm-up runs here produce a measurement of a **fresh JVM process with potentially warm OS caches**. This is the common repeatable scenario when restarting a service on a running host. Do not call this result an OS-wide cold boot.

## 8. Read Metrics and Draw Conclusions

Use median as the primary metric because a single unusually slow run can skew the mean high. Min/max show dispersion; retain all raw samples so others can inspect them.

Formulas:

```text
delta_ms = median_after - median_before

improvement_percent =
    (median_before - median_after) / median_before * 100
```

- Negative delta_ms: the updated version starts faster.
- Positive improvement_percent: duration decreased.
- Negative improvement_percent: duration increased.

Do not conclude a change helps just because one run was faster. If the median difference is smaller than run-to-run variance, the result is not strong enough; increase batch count or reduce environmental noise before concluding.

Once an overall difference is observed, open the corresponding *-startup.json files and look for:

1. Which startup step increased/decreased in duration the most?
2. Which bean has a beanName tag and takes a long time to instantiate?
3. Is time spent in component scan, configuration parsing, bean instantiation, server startup, or runners?
4. Were extra database connection, migration, broker, or external HTTP call steps added?
5. Did the number of beans/steps change unexpectedly?

Do not look solely at Started ... seconds in the logs. The log is a useful quick indicator, while the readiness probe provides a consistent end milestone for external benchmarks.

If the change enables lazy initialization, startup may drop because beans are created later. Spring Boot also notes that lazy initialization can delay detection of configuration errors until a bean is used. In that case, also measure latency of the first request or first business operation. Otherwise, shifting cost to the first request can be mistaken for an overall optimization.

## 9. Distinguish Code-Change Measurements from AOT Measurements

AOT is a distinct build/runtime variant. Spring Boot process-aot analyzes the application at build time and generates optimized code; for native image, AOT is a mandatory step. During this process, conditions and profiles may be evaluated at build time.

When benchmarking AOT:

- Keep dependency graph, business configuration, profiles, and data equivalent between both versions.
- Configure profiles/properties used to evaluate Conditional annotations accurately right in the process-aot step.
- Record GraalVM/native-image version, build flags, target OS/architecture, and resource limits.
- Compare standard JVM with JVM AOT, or baseline native image with updated native image as clearly labeled test pairs.
- If comparing JVM with native image, treat it as comparing two different runtime modes; do not attribute the entire difference to a code change.
- Separate build time (AOT/native compilation) from runtime process-to-ready. The two measurements answer two different questions.

A build-time AOT configuration can fix beans based on profiles or conditions. Do not toggle runtime properties to enable/disable a bean if that decision was already baked into the AOT artifact; rebuild with the corresponding AOT environment instead.

## 10. Common Mistakes That Invalidate Results

| Mistake | Why It Skews Results | Fix |
| --- | --- | --- |
| Comparing one before run and one after run | Noise from CPU, disk cache, network, and GC can exceed the improvement | Use warm-ups, multiple runs, and median. |
| Dependency tree changed | Unclear whether speedup/slowdown comes from code or dependencies | Keep the graph identical or separate into a dependency benchmark. |
| Different profiles or configs | Number of created beans and integrations may differ | Fix profiles, properties, env, and command line. |
| Running spring-boot:run for one version and java -jar for the other | Different launchers and classpaths | Use identical artifact type and launch command. |
| Measuring only until ContextRefreshedEvent | May miss runners and readiness | Measure until readiness/traffic-accepting. |
| Using ApplicationReadyEvent as process start | This event happens after most of startup | Use an external clock or explicitly note measuring only Spring internals. |
| Changing log level or enabling --debug on one version | Logging and condition reports add extra work | Keep log level and instrumentation identical. |
| Adding Actuator only to the updated version | Dependency and bean sets change | Add identically to both or use an existing endpoint. |
| Measuring startup without measuring the first request | Lazy init may shift time to the first request | Measure readiness and first-request latency separately. |
| Summing all startup step durations | Parent/child steps may overlap | Compare corresponding steps; do not sum blindly. |
| Calling startup endpoint before stopping the clock | Adds diagnostic request into the measurement | Stop the clock at readiness 200, then GET startup JSON. |
| Calling POST startup to inspect data | POST drains the buffer | Use GET snapshot to read. |

## 11. Checklist Before Publishing Results

- [ ] Both versions use identical JDK, Maven, Spring Boot, and dependency tree.
- [ ] Identical profiles, config files, env, system properties, and JVM flags.
- [ ] Identical artifact type and launch command.
- [ ] Identical host/container, CPU/RAM limits, and dependent services.
- [ ] Readiness signal has the exact same meaning in both versions.
- [ ] Startup instrumentation and Actuator match identically.
- [ ] Warm-ups and sufficient runs performed; all samples retained.
- [ ] Reported median, min, max, and improvement percentage.
- [ ] Retained logs, startup JSON, dependency tree, and revision for traceability.
- [ ] If lazy initialization is used, first request was measured.
- [ ] If AOT/native is used, build-time profiles, runtime mode, and toolchain are explicitly documented.

**Takeaway:** A measurement is valid when both versions differ only in what is being tested. Use an external clock to measure to readiness, use BufferingApplicationStartup and Actuator to find time-consuming Spring steps, repeat across fresh processes, and report median along with dispersion. When testing AOT/native, keep dependencies and configuration equivalent while separately reporting runtime mode and build-time environment.

### Official References

- Spring Boot 3.3 — SpringApplication, application events, readiness, and startup tracking: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Actuator endpoints and exposure/security: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 — Startup endpoint API: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html
- Spring Boot 3.3 — Maven plugin AOT processing: https://docs.spring.io/spring-boot/3.3/maven-plugin/aot.html
- Spring Boot — AOT conditions and build-time profiles: https://docs.spring.io/spring-boot/how-to/aot.html