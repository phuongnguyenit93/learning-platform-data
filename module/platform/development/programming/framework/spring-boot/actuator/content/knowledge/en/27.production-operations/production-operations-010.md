# Reviewing Endpoint, Configuration, and Library Changes When Upgrading Spring Boot

> Scope: reviewing operability of applications with Spring Boot Actuator. The two concrete version examples are Prometheus changes moving from Boot 3.2 to 3.3 and endpoint permission changes moving from Boot 3.3 to 3.4. They illustrate how to analyze an upgrade, not a recommendation to pick a single target version for every project.

## 1. Which Contracts Does an Upgrade Change?

An upgraded application can compile and start up successfully yet the metrics collector can no longer read data, health probes point to the wrong path, or a diagnostic endpoint widens permissions beyond expectations.

With Actuator, look at three layers together:

| Layer | What can change | Who is affected? |
| --- | --- | --- |
| Endpoints | Availability, paths, operations, access permissions, content types, response structure | Health checkers, operators, automation tools |
| Configuration | Renamed keys, deprecated keys, defaults, binding behavior, and override sources | Application, deployment config, operational policies |
| Libraries | Actual versions, packages/APIs, auto-configuration conditions, data export protocols | Java code, registries, exporters, collectors, dashboards, and alerts |

These are operational contracts: which application behaviors other systems depend on. The goal of the review is to identify which changes are intentional, which break contracts, and what evidence suffices to accept the new release.

Do not use every endpoint returning 200 as the success criterion. Protected endpoints must keep denying unauthorized callers; endpoints not serving operational needs should not appear just because a new release added them.

## 2. Locking Down Source Version, Target Version, and Baseline Data

Before changing versions, record a reproducible baseline:

- Source and target Spring Boot versions down to the exact patch.
- JDK used to compile and run, Gradle Wrapper, Servlet or Reactive application type.
- Running artifact and effective deployment configuration set.
- Resolved dependency graph, version overrides, and external integration libraries.
- Endpoint set, caller policies, health groups, and observability data actually in use.

The source version is not just a number in build.gradle. BOMs, dependency constraints, shared plugins, or resolution rules can make the runtime version differ from what you read on a single declaration line.

Measure source and target with the same test data, equivalent configuration, and enough traffic to populate the meters to check. If you change version, test data, and environment configuration at once, isolating the cause of a difference becomes very hard.

### Freeze Expectations, Not Every Byte

Save response parts that serve contracts, such as the status field, required label sets, or metric names used by alerts. Exclude volatile values from verbatim comparison: timestamps, uptime, memory readings, label order, and per-call traceIds.

This does not mean ignoring measurements. Structure and names must be verified against contracts; latency, resource usage, and error counts need evaluation with separate measurements.

## 3. Reading Documentation Along the Exact Upgrade Path

Start with the upgrade section in the target release notes, then check intermediate releases if skipping multiple versions. Spring Boot instructs reading release notes of skipped versions as well. [Spring Boot upgrade guide](https://docs.spring.io/spring-boot/3.3/upgrading.html).

For each relevant change, record:

| Item to verify | Specific question |
| --- | --- |
| Compatibility | Have JDK/build tool requirements changed? |
| Configuration | Was the key renamed, deprecated, removed, or did only its default change? |
| Endpoints | Which operations are created or no longer created? Which responses changed? |
| Dependencies | Which library used directly by the app or tools did the BOM change? |
| Integrations | Do collectors, related Spring libraries, or exporters support the new combination? |

Also read the configuration changelog and documentation for Micrometer, Spring Security, or libraries that actually changed. Do not use another version's page to infer that the same property or default applies to the running release.

Patch, minor, and major guide review scope, yet do not replace evidence. A patch release can still change important behavior through bug fixes; a minor release can upgrade a library your direct API depends on.

## 4. Checking Actual Libraries Before Editing Code

Spring Boot manages a set of dependency versions designed to work together. When using Boot's dependency management, many dependencies do not need explicit versions. Overrides still need to be inventoried and re-evaluated on upgrades. [Spring Boot Gradle dependency management](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html).

In a standalone Gradle application project with a runtimeClasspath configuration, you can use:

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency micrometer-registry-prometheus --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency opentelemetry-sdk --configuration runtimeClasspath
```

In a multi-project build, invoke tasks on the verified application subproject rather than assuming this configuration exists at root. The commands above are graph-investigation examples, not instructions to change versions of the listed libraries.

dependencies shows the chosen graph; dependencyInsight helps explain what pulled a library in and why a version was selected. Compare outputs between both releases, including transitive dependencies. [Gradle dependency inspection tools](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html).

Important questions:

1. Do the Boot plugin and BOM intend the same version?
2. Is an observability library forced to an older version by another constraint or plugin?
3. Are there overlapping bridges, registries, or exporters causing data to be sent twice?
4. Does custom code use a specific registry class rather than the common API?
5. Must integration libraries maintained by the project team be upgraded together?

Do not fix NoSuchMethodError or NoClassDefFoundError by randomly adding a JAR. First verify the library combination and the API the caller was actually compiled against.

### Example: Prometheus When Upgrading from Boot 3.2 to 3.3

Boot 3.3 brings Prometheus Java client 1.x support into the Prometheus registry. Release notes point out changes that can affect exported data. Therefore, the prometheus endpoint still returning 200 is not enough to conclude observability behavior stayed the same. [Spring Boot 3.3 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.3-Release-Notes#prometheus-client-1x).

In Micrometer 1.13, the micrometer-registry-prometheus module moved its base package from io.micrometer.prometheus to io.micrometer.prometheusmetrics. Code directly using PrometheusMeterRegistry must have its imports and corresponding APIs checked:

```java
// Registry using the new client in Micrometer 1.13
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
```

This is an illustrative import snippet, not a standalone Java program. If the application only uses the MeterRegistry provided by Boot, no import edits may be needed, yet metric output must still be verified.

Scrape changes may also differ only in representation, such as counts from 1.0 to 1, or differ in names/types. Classify differences by semantics, rather than treating every textual diff as a bug or ignoring everything because it still parses. [Micrometer 1.13 Migration Guide](https://github.com/micrometer-metrics/micrometer/wiki/1.13-Migration-Guide).

The old simpleclient module was provided as a deprecated transition path. If using a temporary bridge, document scope and removal plan; do not treat it as a permanent contract across all future releases.

## 5. Reviewing Configuration in Both Files and Deployment Environments

Inventory keys related to:

- Endpoints enabled, exposed over HTTP/JMX, and permitted operation levels.
- Management port, base path, path mapping, and reverse proxy configuration.
- Health groups, probes, HTTP status mappings, and exposed detail levels.
- Metric tags, filtered meters, histograms/buckets, and data export.
- Tracing, sampling, exporters, and collection system addresses.
- Log levels, sensitive content, and file rotation settings.

Read environment variables, command-line arguments, profiles, and external config as well. Changing a key in application.yml is not enough if deployment still overrides with the old name or another source.

For each key, clearly distinguish:

| Status | How to handle |
| --- | --- |
| Renamed with equivalent meaning | Migrate config sources and verify effective value |
| Deprecated yet still supported | Plan migration; do not assume the key was already removed |
| Removed | Replace with new capability or remove ineffective config |
| Unchanged name yet changed default | Check operational intent and configure explicitly if needed |
| Changed meaning | Redesign policy and test behavior, not just rename strings |

Configuration metadata helps identify properties and config info published for developer tools. An IDE suggesting a key does not replace checking runtime, profiles, and override sources. [Spring Boot configuration metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html).

### Migration Helper Tools Are Only Part of the Evidence

When supported by the target version, you can temporarily add the properties migrator module to help detect and migrate properties known to the tool:

```groovy
runtimeOnly 'org.springframework.boot:spring-boot-properties-migrator'
```

The dependency snippet assumes the project already manages versions appropriately with Boot. Read output in a test environment, fix original config sources, then remove the module when done. It does not prove every custom key, late-loaded configuration, or semantic change has been handled. [Properties migrator and documented limits](https://docs.spring.io/spring-boot/3.3/upgrading.html#upgrading.from-2x).

### Comparing Auto-Configuration Conditions

If a registry, exporter, or endpoint bean disappears, inspect conditions instead of immediately declaring a bean yourself to compensate. Classpath, properties, custom beans, and the new version's conditions may lead to a different choice.

In a controlled test environment, you can view the conditions report with the debug option. For a standalone Boot project with the bootRun task:

```powershell
.\gradlew.bat bootRun --args='--debug'
```

Find why configuration matched or did not match for the component under investigation. The report is a diagnostic tool and should be treated as operational data, not a reason to widen endpoint permissions in production. [Spring Boot conditions report](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).

## 6. Semantic Change Example: Endpoint Permissions from Boot 3.3 to 3.4

In Boot 3.3, the enable/disable model uses management.endpoints.enabled-by-default and management.endpoint.<id>.enabled. Example enabling only health and prometheus:

```yaml
# Example for Spring Boot 3.3
management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: health,prometheus
  endpoint:
    health:
      enabled: true
    prometheus:
      enabled: true
```

Boot 3.4 introduces access with levels none, read-only, and unrestricted; the old enabled keys are marked deprecated. The new model also has max-permitted to cap operations across all endpoints. [Endpoint changes in Boot 3.4 release notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes#controlling-access-to-actuator-endpoints).

An intentional policy on Boot 3.4 to allow reading only two selected endpoints:

```yaml
# Example for Spring Boot 3.4
management:
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: health,prometheus
  endpoint:
    health:
      access: read-only
    prometheus:
      access: read-only
```

Do not copy the 3.4 configuration block into a 3.3 application and assume it enforces the new model. The two illustrative blocks must be matched to the exact version running.

Points to verify when migrating:

- `enabled=true` previously did not automatically mean read-only intent. Endpoints such as `loggers` have both read and config-change operations.
- `max-permitted` can cap each endpoint's level even if that endpoint is declared `unrestricted`.
- Access decides which endpoint operations are provided; exposure decides publication channels; Spring Security decides which callers can reach them.
- `read-only` does not mean public or harmless data: a read operation on diagnostic data can still return sensitive content.

For endpoints declared with @Endpoint, the read level binds to @ReadOperation. This is not a user role name or JWT scope. [Actuator 3.4 access model](https://docs.spring.io/spring-boot/3.4/reference/actuator/endpoints.html#actuator.endpoints.access).

Merely renaming properties without testing read/write operations can break an operational tool, or leave the policy different from the original intent.

## 7. Testing Endpoints Against a Contract Matrix

For each endpoint in use, verify simultaneously:

| Check dimension | What to compare |
| --- | --- |
| Location | ID, base path, management port, path through proxy |
| Availability | Endpoint creation conditions and provided operations |
| Callers | Anonymous, metrics-only reader, on-call responder, or specifically authorized principal |
| Protocol | HTTP method, status, Content-Type, and content negotiation |
| Response | Required fields, status semantics, and permitted detail level |
| Channel | Actual HTTP/JMX channels in use, not just one access path |

For health, test both healthy state and defined degraded scenarios. Verify liveness/readiness membership, status mapping, and behavior during startup or shutdown. A probe pointing to the right URL yet checking the wrong semantics can still drive wrong operational decisions.

For sensitive endpoints, test denials as well. Do not use a 404 result to conclude for certain an endpoint is disabled: a proxy, wrong path, or security filter can make results look similar.

If a custom SecurityFilterChain exists, compare matchers, order, and scope of the chains. Declaring security chains yourself shifts configuration responsibility compared to Boot defaults; do not assume the new release fills in missing rules for you. [Endpoint availability and protection in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

For @Endpoint or custom extensions, check operation annotations, parameter/return types, and data conversion that callers depend on. Avoid relying on internals of an auto-configuration instead of published extension points.

## 8. Checking the Entire Observability Pipeline to Where It Is Consumed

Trace along the path:

```text
Application produces measurements/observations
    -> registry or tracing bridge
    -> scrape endpoint or exporter
    -> collector/storage system
    -> recording rules, dashboards, and alerts
```

At each stage, verify:

1. **At the application:** is data generated under test traffic; are duplicate records emitted?
2. **At the output:** are names, metric types, labels, units, and buckets still accurate?
3. **At the collector:** can it parse the format and receive complete data from all instances?
4. **At queries:** do filters still match and do denominators remain complete?
5. **At alerts:** do conditions work for good data, bad data, and missing data?

A dashboard reporting no syntax errors can still be empty because names or labels changed. An SLI can look better merely because part of the denominator is no longer collected.

For histograms, verify the boundaries used by queries across all instances of the new release. For tracing, verify context propagation, chosen sampling, log correlation info, and permitted export fields.

Compare dynamic values under matching test conditions. Do not require before-and-after counts to match identically if test call counts or runtimes differed. Nor ignore unit changes simply because both responses contain numbers.

### Spring Tests Do Not Replace Collector Tests

Use ApplicationContext tests to verify beans, configuration, and HTTP permissions. Use integration tests with real registries/exporters and collectors for contracts depending on the export pipeline.

Verify observability configuration in tests: Spring Boot has specific behaviors for @SpringBootTest and slice tests. A test using an in-memory registry does not prove production exporters work. [Testing Spring Boot applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).

## 9. Java Example: Evaluating Changes Against Explicit Expectations

The following program illustrates part of the comparison approach. Snapshots are hypothetical collected data; it makes no HTTP calls and does not read Prometheus responses itself. Two violations are intentionally placed into the candidate: heapdump readable by an anonymous caller and one required metric name missing.

Do not interpret this hypothetical data as a claim that an actual Boot release opens heapdump itself or drops HTTP meters.

File UpgradeContractDemo.java:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class UpgradeContractDemo {
    record Probe(String name, Set<Integer> allowedStatuses) {
        Probe {
            allowedStatuses = Set.copyOf(allowedStatuses);
        }
    }

    record Snapshot(Map<String, Integer> statuses, Set<String> metricNames) {
        Snapshot {
            statuses = Map.copyOf(statuses);
            metricNames = Set.copyOf(metricNames);
        }
    }

    static List<String> violations(
            List<Probe> contract, Set<String> requiredMetrics,
            Snapshot snapshot) {
        List<String> problems = new ArrayList<>();
        for (Probe probe : contract) {
            Integer status = snapshot.statuses().get(probe.name());
            if (status == null) {
                problems.add(probe.name() + ": missing result");
            }
            else if (!probe.allowedStatuses().contains(status)) {
                problems.add(probe.name() + ": unexpected HTTP " + status);
            }
        }
        requiredMetrics.stream().sorted()
            .filter(name -> !snapshot.metricNames().contains(name))
            .forEach(name -> problems.add("missing metric: " + name));
        return List.copyOf(problems);
    }

    public static void main(String[] args) {
        List<Probe> contract = List.of(
            new Probe("health:anonymous", Set.of(200)),
            new Probe("prometheus:collector", Set.of(200)),
            new Probe("heapdump:anonymous", Set.of(401, 403, 404))
        );
        Set<String> requiredMetrics = Set.of(
            "http_server_requests_seconds_count",
            "jvm_memory_used_bytes"
        );
        Snapshot baseline = new Snapshot(
            Map.of("health:anonymous", 200,
                   "prometheus:collector", 200,
                   "heapdump:anonymous", 404),
            requiredMetrics
        );
        Snapshot candidate = new Snapshot(
            Map.of("health:anonymous", 200,
                   "prometheus:collector", 200,
                   "heapdump:anonymous", 200),
            Set.of("jvm_memory_used_bytes")
        );

        List<String> oldProblems = violations(contract, requiredMetrics, baseline);
        List<String> newProblems = violations(contract, requiredMetrics, candidate);
        System.out.println("baselineViolations=" + oldProblems.size());
        System.out.println("candidateViolations=" + newProblems.size());
        newProblems.forEach(System.out::println);
        System.out.println("candidateAcceptable=" + newProblems.isEmpty());
    }
}
```

Compile and run with JDK 21 or later:

```powershell
javac --release 21 -encoding UTF-8 UpgradeContractDemo.java
java UpgradeContractDemo
```

Stdout:

```text
baselineViolations=0
candidateViolations=2
heapdump:anonymous: unexpected HTTP 200
missing metric: http_server_requests_seconds_count
candidateAcceptable=false
```

The program does not compare response bytes. It checks what was written as a contract: whether callers get the right access outcomes and whether required data exists.

The 401/403/404 set in the example only describes acceptable denial results for an anonymous check. Proving an endpoint is disabled, protected by the right role, or returns the right content requires adding corresponding checks.

In real tools, parse content with a suitable parser, check schema/semantics, and extract metric names from parsed data. Do not treat finding a string in a comment or HELP line as proof that real metric samples exist.

The example does not yet check Content-Type, health payload, labels, data types, or query results. Those parts must be included in the project's test suite according to the defined contract.

## 10. Classifying Differences Before Making a Release Decision

| Observed difference | How to evaluate |
| --- | --- |
| JSON field order or label order changed | If order is not part of the contract, normalize when comparing |
| Count formatted as 1 instead of 1.0 | Parse numerically; verify consumers accept it properly |
| Endpoint no longer allows needed write operation | Cross-check access, exposure, and permission policies; do not open everything as a quick fix |
| Sensitive endpoint returns data to unauthorized caller | Permission violation; do not accept candidate release yet |
| A metric or label changed unexpectedly | Fix export point or update consumers per a tested plan |
| Exporter bean disappeared due to new conditions | Investigate graph/config/conditions; re-verify end-to-end |
| Deprecated key still present in deployment | Migrate config sources and re-test when compatibility layer is removed |

For an intentional change, update the contract and consumers together with evidence. Do not update the whole snapshot just to make the test suite turn green.

## 11. Deployment and Rollback Must Include Configuration

Before production, complete builds and appropriate tests on the artifact to be released, with configuration equivalent to the target environment. Record sources, resolved versions, and comparison results to avoid testing one combination and releasing another.

During a limited rollout, observe both user-serving behavior and the monitoring pipeline of the new release. If old and new versions run together, ensure version/instance tagging supports comparison without causing alerts to lose part of their data.

Prepare rollback capability as a compatible bundle of artifact, configuration, and related integrations. Downgrading the JAR to an old version while keeping configuration keys exclusive to the new version can prevent rollback from behaving as expected.

Separately evaluate hard-to-reverse changes, such as external data or changed consumer protocols. Do not assume every dependency change can be rolled back by a single version swap.

Evidence to retain for an upgrade:

- Source/target versions, JDK, Wrapper, and tested artifact.
- Runtime graph and remaining override list.
- Configuration matrix: old source, new source, semantics, and effective values.
- Endpoint test results by caller and operation.
- Scrape/export results, queries, dashboards, and key alerts.
- Accepted differences, verification limits, and verified rollback procedure.

## 12. Self-Practice

1. The prometheus endpoint returns 200 after an upgrade, yet dashboards have no data left. List the stages to inspect before concluding the endpoint failed.
2. An application moving from Boot 3.3 to 3.4 uses loggers to read and change log levels. Explain why replacing enabled=true with access=read-only does not preserve both capabilities.
3. Add a prometheus:anonymous check to the Java program. Choose the result set per your policy and verify a candidate opening unexpectedly is detected.
4. A dependency in build.gradle specifies no version, yet runtime still uses an old Micrometer version. Use dependencyInsight to identify the kinds of causes to investigate.
5. Name one configuration or consumer change that must be accounted for when rolling back an old artifact; explain why keeping only the old JAR is not enough.

The review achieves its goal when you can explain where each important change came from, whom it affects, and which operational contract verified it.
