# Finalize an operational configuration with signal reading and incident response guides

## 1. Operational configuration must support decisions

A service starting successfully does not mean users are being served well. A process may be alive yet unable to reach the inventory system; health may report UP while most requests are slow; the management port may respond even when the business port is in trouble.

The goal of this lab is combining Spring Boot Actuator capabilities into a configuration that can be explained, verified, and handed over to operations. After this exercise, you should be able to answer four questions:

1. Does the process need to be restarted?
2. Should this application instance receive new requests?
3. To what extent are users experiencing errors or latency?
4. In what order should evidence be gathered and impact mitigated?

Three complementary signal layers:

| Layer | Core question | Limitation |
| --- | --- | --- |
| Health and probes | Is it alive, ready, and which component reports errors? | A status snapshot does not describe the full user experience |
| Operational metrics | How do errors, latency, load, and resources change over time? | Aggregated data usually cannot pinpoint a single offending request |
| Logs, and traces if configured | What happened during a specific execution? | Missing time context or insufficient sampling can lead to wrong conclusions |

Actuator provides endpoints to read status and metrics. Retaining history, evaluating alerts, and handling incidents still require monitoring systems and operational processes outside the application.

## 2. Scope and access diagram

The example below is a standalone Servlet application using Java 21 and Spring Boot 3.3.0 to pin behavior for the lesson. It uses Maven and Spring Security. Do not substitute Spring Boot 4.x configuration directly into this example. When applying to a real project, use organization-vetted patch releases, review version changes, and re-run the checks below.

The application includes a simulated business GET API, a simulated inventory health indicator, two probes on the business port, and a separate management port.

~~~text
Callers / load balancer
        |
        v
8080: /api/demo, /livez, /readyz
        |
        +-- GET only on allowed paths

Operator on the same host or network namespace
        |
        v
127.0.0.1:9091/actuator
        +-- health: status only, open for probing
        +-- metrics: HTTP Basic + OPS role
~~~

In this model, port 9091 listens only on loopback. Tools on another machine or another Pod cannot reach it via the host's network address. If remote scraping is needed, intentionally change the bind address, configure private networking/firewalls, authentication, and TLS at the proper layers; separating port numbers alone creates no security boundary.

The two paths `/livez` and `/readyz` route probes through port 8080 serving business traffic. A passing probe still does not prove every API, dependency connection, and service quality target are healthy.

The `/api/demo` API is intentionally public for this lab. Business authentication policies for real services must be designed separately.

## 3. Create a standalone runnable application

Directory structure:

~~~text
actuator-operations/
├── pom.xml
└── src/main/
    ├── java/example/ops/
    │   ├── OperationsApplication.java
    │   └── OperationsSecurity.java
    └── resources/application.yml
~~~

### 3.1. Declare libraries

Contents of `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>actuator-operations</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
~~~

The Actuator starter provides endpoints and metrics integration. It does not automatically add every metrics exporter, such as Prometheus, merely because you list an endpoint name in exposure.

### 3.2. Create the simulated business API and dependency

Contents of `OperationsApplication.java`:

~~~java
package example.ops;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class OperationsApplication {

    private final boolean inventoryUp;
    private final long delayMillis;

    public OperationsApplication(
            @Value("${demo.dependency-up:true}") boolean inventoryUp,
            @Value("${demo.delay-ms:0}") long delayMillis) {
        if (delayMillis < 0 || delayMillis > 2000) {
            throw new IllegalArgumentException("demo.delay-ms must be 0..2000");
        }
        this.inventoryUp = inventoryUp;
        this.delayMillis = delayMillis;
    }

    public static void main(String[] args) {
        SpringApplication.run(OperationsApplication.class, args);
    }

    @Bean(name = "inventory")
    HealthIndicator inventory() {
        return () -> inventoryUp
                ? Health.up().build()
                : Health.down().build();
    }

    @GetMapping("/api/demo")
    ResponseEntity<Map<String, String>> demo() throws InterruptedException {
        Thread.sleep(delayMillis);
        if (!inventoryUp) {
            return ResponseEntity.status(503)
                    .body(Map.of("result", "inventory-unavailable"));
        }
        return ResponseEntity.ok(Map.of("result", "ok"));
    }
}
~~~

Both simulation flags are read at startup. To change scenarios, stop and restart the process with different environment variables. There is no public API to mutate health.

The `inventory` indicator only returns the simulation flag; it does not actually check an inventory server. In a real service, replace it with a check that has a timeout, reasonable cost, and clear semantics. Never perform business writes inside a health check.

Thread.sleep here intentionally adds bounded latency for observation. That is not how remote services are called in real business code.

### 3.3. Restrict access with two filter chains

Contents of `OperationsSecurity.java`:

~~~java
package example.ops;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class OperationsSecurity {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService operationsUsers(
            PasswordEncoder encoder,
            @Value("${ops.user:ops}") String username,
            @Value("${ops.password}") String password) {
        if (password.isBlank()) {
            throw new IllegalArgumentException("OPS_PASSWORD must not be blank");
        }
        return new InMemoryUserDetailsManager(
                User.withUsername(username)
                        .password(encoder.encode(password))
                        .roles("OPS")
                        .build());
    }

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
                            .permitAll()
                        .anyRequest().hasRole("OPS"))
                .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET,
                                "/livez", "/readyz", "/api/demo").permitAll()
                        .anyRequest().denyAll());
        return http.build();
    }
}
~~~

The first chain applies only to Actuator endpoints. Health is open for probing; other management endpoints require the OPS role. The second chain allows only the lab's GET paths and denies all remaining paths.

When declaring custom SecurityFilterChain beans, you take full responsibility for access policy; do not continue assuming Boot's default Actuator protection still applies as if no custom config existed.

In-memory accounts let the example run standalone. Real systems need identity management and authorization aligned with operational policy, including credential rotation and revocation procedures. HTTP Basic does not encrypt credentials; over a network, TLS is required. Never place passwords in Git, metric labels, URLs, or logs.

## 4. Finalize application.yml and explain every decision

Contents of `application.yml`:

~~~yaml
spring:
  application:
    name: actuator-operations
  lifecycle:
    timeout-per-shutdown-phase: 30s

server:
  port: 8080
  shutdown: graceful

ops:
  user: ${OPS_USER:ops}
  password: ${OPS_PASSWORD}

demo:
  dependency-up: ${DEMO_DEPENDENCY_UP:true}
  delay-ms: ${DEMO_DELAY_MS:0}

management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include:
          - health
          - metrics
  endpoint:
    health:
      show-details: never
      show-components: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include:
            - livenessState
        readiness:
          include:
            - readinessState
            - inventory
  metrics:
    tags:
      application: ${spring.application.name}

logging:
  level:
    root: INFO
~~~

Key points to understand before use:

| Decision | Operational meaning |
| --- | --- |
| Expose only health and metrics | Small allowlist matching the lesson's goal |
| Avoid `exposure.include=*` | Prevents unintentionally expanding management surface when adding libraries or new endpoints |
| `show-details/show-components=never` | Probers receive status without internal structure or dependency details |
| Enable probes explicitly | Provides liveness/readiness even when running outside Kubernetes |
| `add-additional-paths=true` | Exposes `/livez` and `/readyz` on the main port, even when management uses a different port |
| Liveness includes only `livenessState` | Inventory failures do not turn into reasons to restart the process |
| Readiness includes `readinessState` and `inventory` | In this example, without inventory the instance cannot serve business requests |
| Fixed `application` tag | Distinguishes the service with bounded cardinality |
| Graceful shutdown with 30s timeout | Allows shutdown phase to finish in-flight requests within the configured bound |

Whether readiness includes an external dependency is an architectural decision. If a shared dependency outage makes every instance unready at once, the entire service can be pulled from load balancing. Put a dependency in readiness only when shedding traffic makes sense; weigh fallback responses, partial degradation, and load balancer behavior.

Graceful shutdown duration does not configure Kubernetes or load balancer timeouts automatically. You must align unready detection time, traffic draining, in-flight request execution, and the timeout before the OS forcefully kills the process.

Do not confuse three conditions: whether an endpoint is created/enabled, whether it is exposed over HTTP, and whether the caller is authorized. Adding a name to exposure does not create an endpoint whose library is missing.

## 5. Start up and verify the normal path

The commands below use Bash with Maven on PATH and JDK 21. The first build downloads libraries from Maven repositories.

In the `actuator-operations` directory, enter a password for the lab without hardcoding a real value in the example:

~~~bash
read -r -s -p "OPS password: " OPS_PASSWORD
printf '\n'
export OPS_PASSWORD

mvn clean package
java -jar target/actuator-operations-1.0.0.jar
~~~

Keep this terminal running; open another terminal to run the curl commands. Wait for logs confirming startup completed before evaluating readiness. Use `curl.exe` if running equivalent commands in PowerShell to avoid colliding with another tool's alias.

~~~bash
curl -i http://localhost:8080/api/demo
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -i http://127.0.0.1:9091/actuator/health
curl -i http://127.0.0.1:9091/actuator/health/liveness
curl -i http://127.0.0.1:9091/actuator/health/readiness
~~~

Once ready, with default simulation values:

| Request | Expected HTTP | Content to verify |
| --- | --- | --- |
| GET /api/demo on 8080 | 200 | result is ok |
| GET /livez on 8080 | 200 | status is UP |
| GET /readyz on 8080 | 200 | status is UP |
| GET /actuator/health on 9091 | 200 if other contributors are healthy too | status is UP, no details leaked |
| GET /actuator/health/liveness on 9091 | 200 | status is UP |
| GET /actuator/health/readiness on 9091 | 200 | status is UP |

With minimal setup and free disk space, overall health is normally UP. If `diskSpace` or a library-added contributor reports DOWN, overall health can differ from the two chosen groups. Do not adjust expectations by ignoring real failures.

Check metrics authentication:

~~~bash
curl -i http://127.0.0.1:9091/actuator/metrics
curl -i -u ops http://127.0.0.1:9091/actuator/metrics
~~~

The first command must require authentication, typically returning 401 in this configuration. On the second command, curl prompts interactively for the password; enter the same password used to start the app. Expect 200 with a `names` list. If `OPS_USER` was set to something other than `ops`, replace the username in the command.

Also test an unlisted request, such as `GET /private` on 8080. It must be denied by policy, with no unexpected public API appearing. Do not use this single negative check to prove the entire security configuration is sound.

The tables above describe verification criteria; do not expect HTTP headers, JSON property order, startup duration, or meter counts to be identical across machines.

## 6. Read metrics by question, not as isolated numbers

Generate a little traffic before looking up HTTP meters:

~~~bash
for i in $(seq 1 10); do
  curl -sS -o /dev/null http://localhost:8080/api/demo
done

curl -sS -u ops \
  http://127.0.0.1:9091/actuator/metrics/http.server.requests
~~~

A meter may appear only after matching requests occur. Inspect `availableTags` to see actual tag keys and values, then filter the right group:

~~~bash
curl -sS -u ops --get \
  http://127.0.0.1:9091/actuator/metrics/http.server.requests \
  --data-urlencode 'tag=uri:/api/demo' \
  --data-urlencode 'tag=method:GET'
~~~

An HTTP timer typically provides `COUNT`, `TOTAL_TIME`, and `MAX`; read `baseUnit` instead of assuming units. For timers reported in seconds, `TOTAL_TIME/COUNT` is the mean duration of the aggregated set, not p95/p99.

Illustrative calculation with hypothetical numbers on the same un-restarted application instance:

~~~text
At t0: COUNT = 100, TOTAL_TIME = 12 seconds
At t1: COUNT = 160, TOTAL_TIME = 30 seconds
Measurement interval: 60 seconds

Average throughput = (160 - 100) / 60 = 1 request/second
Average duration = (30 - 12) / (160 - 100) = 0.3 seconds
~~~

If there were 6 5xx responses out of 60 new requests with the same filter scope, the 5xx rate is 10%. Measure over the same window and tag set; never divide one route's error count by another route's total requests.

Cautions when interpreting:

- `COUNT` and `TOTAL_TIME` are cumulative; never compute rate from a single read. Restarts break continuity of cumulative per-process series.
- `MAX` may be a registry time-windowed maximum; do not assume it is the all-time maximum since process startup.
- A low mean can hide a small subset of very slow requests. To evaluate quantiles, configure appropriate distribution data and use storage/query tools that support it.
- `availableTags` confirms existing tag values, not all theoretically possible values.
- An API returning 503 does not necessarily throw an exception. This example explicitly returns `ResponseEntity` 503, so watch `status`, not just the `exception` tag.
- Never use order IDs, user IDs, tokens, full URLs with varying parameters, or exception messages as tags. High tag-combination growth consumes heavy resources in the metrics system.

Meters to cross-check if present in `names`:

| Meter | Used to inspect | Reading cautions |
| --- | --- | --- |
| http.server.requests | Throughput, status codes, processing time | Slice by route/method/status; exclude probe traffic from business metrics when appropriate |
| process.uptime | How long the process has been running | Unusually low values can suggest a recent restart; cross-check deployment events |
| process.cpu.usage | Process CPU share | Interpret per JVM/OS capability; not automatically identical to every OS tool's CPU percentage |
| jvm.memory.used, jvm.memory.max | Memory by area/pool | Compare within the same pool and check whether max is defined; do not arbitrarily add or divide different areas |
| jvm.gc.pause | GC pause events | Correlate timing and frequency with latency; a single GC does not prove a memory leak |
| jvm.threads.live | Live JVM thread count | Not the count of busy HTTP threads or queued requests |

Actuator `/metrics` is a point-in-time diagnostic tool, not a historical store. For persistent charts and alerts, you need an appropriate registry/exporter, collector, and storage backend.

If choosing Prometheus, add `io.micrometer:micrometer-registry-prometheus`, also expose `prometheus`, and configure authenticated scraping. Meter names in `/metrics` such as `http.server.requests` differ from Prometheus exposition names; never copy dotted names verbatim into queries without checking actual exported output.

## 7. Practice dependency failure: alive yet unready

Stop the application with Ctrl+C. In the launch terminal where `OPS_PASSWORD` is still set, restart with:

~~~bash
DEMO_DEPENDENCY_UP=false \
java -jar target/actuator-operations-1.0.0.jar
~~~

After startup finishes, check again:

~~~bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/api/demo
curl -i http://127.0.0.1:9091/actuator/health
~~~

Expectations under the lesson's configuration:

| Signal | Result | Interpretation |
| --- | --- | --- |
| /livez | 200, UP | Process is still viable; inventory failure is excluded from liveness |
| /readyz | 503, DOWN | Readiness group includes inventory, so instance is unready for traffic |
| /api/demo | 503, result is inventory-unavailable | Direct callers still reach the app and get the simulated business error |
| /actuator/health | 503, DOWN | Overall health has the inventory contributor reporting DOWN |

Readiness does not block controllers automatically. It supplies a signal for platforms/load balancers to decide whether to route requests to this instance. Direct calls to the application port still reach the API as shown above.

Operational takeaway: if the real inventory system fails, restarting every instance usually cannot fix inventory, and can cause connection storms that slow recovery. First check dependency status, network paths, timeouts, fallback responses, and user impact.

In this simulation, recover by stopping the app and restarting without `DEMO_DEPENDENCY_UP=false`. That is a lab flag toggle, not a recommendation to restart applications to cure external dependency outages.

## 8. Practice slow responses: health remains UP

Stop the failure-simulation process. Restart with a healthy dependency and a 400 ms delay:

~~~bash
DEMO_DEPENDENCY_UP=true DEMO_DELAY_MS=400 \
java -jar target/actuator-operations-1.0.0.jar
~~~

Wait for readiness, then run:

~~~bash
curl -i http://localhost:8080/readyz
curl -sS -o /dev/null -w 'HTTP=%{http_code} seconds=%{time_total}\n' \
  http://localhost:8080/api/demo
~~~

Readiness is expected UP and the API returns 200, yet response time will be roughly 0.4 seconds plus processing/network/scheduling overhead. Do not treat `0.400000` seconds as fixed stdout.

Read the uri-filtered HTTP timer after several requests. Compare externally observed latency with server-side duration. The two measurements have different scopes: caller-side time also includes DNS, connection setup, proxies, and network transit.

When applied to real incidents, distinguish:

1. Slowness from load exceeding capacity: queues, thread pools, or connection pools hitting limits.
2. Slowness from dependencies: DB, remote services, DNS, or slow network responses.
3. Slowness from resources: CPU, GC, memory, disk.
4. Slowness from a release: new queries, algorithm changes, timeouts, or config changes.

Do not enlarge pools or raise timeouts merely because latency is high. If the DB is already overloaded, adding connections can worsen contention; raising timeouts can hold more threads and connections in a waiting state.

## 9. Set alerts based on impact and duration

An alert needs scope, evaluation window, data conditions, and follow-up actions. The values below are design-practice examples, not universal thresholds for all systems:

| Hypothetical condition | Window | How to verify before acting |
| --- | --- | --- |
| 5xx rate > 5% on business API, at least 100 requests | 5 minutes | Confirm route set, total traffic, and error codes; check for recent deploys |
| p95 > 800 ms | 10 minutes | Use only when quantile/histogram data is properly configured; compare with service targets |
| Consecutive readiness failures | Per probe and platform policy | Determine single instance vs. whole service; check shared dependencies |
| Increasing restart count | Defined time window | Read exit reasons, OOM events, probes, and deployment history |

When traffic is very low, a single failed request can spike error rates dramatically. When data is missing, do not assume zero errors. Monitoring must distinguish service errors, collector failures, and stale/stopped data.

Add an alert only when there is a clear owner and a concrete verification action. Avoid firing many separate alerts for one root cause without grouping.

## 10. Incident response workflow from symptom to recovery

### Step 1: Identify impact and timeline

Record start time, timezone, environment, service name, release version, affected instances, failing routes, and affected users/requests if measurable. Check whether the incident coincides with a deployment or configuration change.

Align clocks and measurement windows before correlating charts with logs. Do not conclude “after deployment therefore caused by deployment” without evidence.

### Step 2: Check reachability before reading payloads

Verify URL, port, path, and caller location. Distinguish:

- Connection refused: no matching listener or connection rejected; check process, bind address, and port.
- Timeout: could be network, queues, overloaded app, or intermediate-layer deadlines.
- TLS error: check hostname, certificate, CA, and TLS termination point.
- HTTP returned: move on to analyzing status codes and access permissions.

Never use `curl -k` to mask certificate errors and consider TLS verification passed.

### Step 3: Correlate status with user signals

Read liveness, readiness, overall health, and run a small safe business check. Next inspect throughput, 5xx, and latency over time. The same `UP` can accompany very different user experiences.

If readiness fails on one instance while others serve cleanly, prefer draining traffic from that instance per procedure. If all fail together, check shared changes and shared dependencies first.

### Step 4: Collect just enough evidence

Read logs around the failure window, looking for root exceptions, timeouts, connection errors, or pool exhaustion. If trace/correlation IDs exist, use them to inspect a single execution; adding the Actuator starter does not by itself guarantee full trace export.

When CPU, threads, or GC behave abnormally, use diagnostics permitted by operational policy. Thread dumps and heap dumps can be resource-heavy and contain sensitive data; collect them only with clear purpose, storage location, and authorized access. Never expose `heapdump` publicly for convenience.

### Step 5: Mitigate with verifiable changes

Pick one hypothesis-driven action: rollback release, shed load, disable/limit a failing feature, restore a dependency, or restart an instance when justified. Record timestamp, operator, scope, expectation, and rollback plan.

Prefer one change at a time when the situation allows. Changing pool sizes, timeouts, and replica counts simultaneously makes it hard to tell what actually helped.

### Step 6: Confirm recovery both technically and functionally

Do not close an incident solely because `/health` returned to UP. Verify real traffic has resumed, error rates and latency stabilize over a reasonable window, queues drain, and critical business flows succeed. Verify recovered instances are receiving traffic properly again.

Reset temporarily elevated log levels, revoke temporary diagnostic permissions, and document known and unknown root causes. If only impact was mitigated, state that clearly in handoff.

## 11. Quick lookup table when endpoints misbehave

| Symptom | Check first | Appropriate action |
| --- | --- | --- |
| /metrics returns 401 | Were valid Basic username/password sent? | Fix client credentials; do not set permitAll on metrics as a workaround |
| Returns 403 | OPS role, matched filter chain, HTTP method; CSRF for state-changing ops | Fix scoped policy; do not disable security app-wide |
| Returns 404 | Right port/base-path; is endpoint enabled and exposed; hidden by proxy or security chain? | Check effective configuration and mappings, not only the source YAML file |
| No /prometheus | Is Prometheus registry present and `prometheus` exposed? | Add the right library/config, then verify access permissions |
| HTTP meter missing yet | Have matching requests completed; checked `names`/`availableTags`? | Generate sample traffic, use exact meter names and actual tags |
| Readiness DOWN, liveness UP | What is in the readiness group; one instance or all affected? | Inspect serving capacity and dependencies, avoid fleet-wide restarts |
| Management port fine, API slow | Both ports can respond independently at some layers; is API waiting on pools/DB? | Check main-port probes and business signals |
| Constant restarts with DB root error | Was DB put in liveness or probe timeouts set too tight? | Fix probe design; use logs/events to confirm restart cause |
| Health UP yet users see errors | Does health cover actual serving conditions; ingress/proxy errors? | Compare 5xx, latency, and synthetic external transactions |
| Metric value “suddenly dropped” | Did the process restart, tags/pools change, or is it a windowed MAX? | Re-identify the time series before computing deltas |

HTTP 503 from a health endpoint is a status-evaluation outcome, not an authentication failure. Conversely, 401/403 does not prove an underlying contributor is DOWN.

## 12. Temporary diagnostics must have an end point

The baseline configuration exposes only health and metrics. Endpoints such as loggers, threaddump, heapdump, env, or configprops must be evaluated separately; never open them in bulk just to troubleshoot one incident conveniently.

If log levels must be read or changed via `loggers`:

1. Define the exact package to observe, time window, and responsible operator.
2. Expose the endpoint only inside protected management scope; re-verify permissions.
3. Record initial configured and effective levels.
4. When using POST, handle CSRF requirements per chosen security policy; this lab's configuration does not disable CSRF.
5. Raise log levels for that exact package; monitor log volume and data-exposure risk.
6. Restore the original configuration, including inherited (`null`) level state if no explicit level was set before.
7. Remove temporary exposure/permissions per procedure and verify.

Changing a logger in a running process does not persist to config files or apply across all instances. A restart can also wipe temporary changes. Likewise, masking values in `env`/`configprops` is not a reason to open those endpoints broadly.

## 13. Operational handover runbook

Prepare a concise guide accompanying each release. It should give an on-call engineer who did not write the app enough information to read signals and act:

- Port/path diagram: API, probes, and management; what may be called from where.
- Exposed endpoint list, auth mechanism, roles, secret storage location, and revocation procedure.
- Liveness/readiness members, what each check means, and platform behavior when probes fail.
- Per-environment effective config, override sources, and release identifier; never copy secret values into docs.
- Key charts/alerts, route scope, units, windows, thresholds, and handling for missing data.
- Where to inspect logs/traces, retention, timezone, and how to search by correlation ID if available.
- Playbooks for dependency outages, slow responses, endpoint access failures, crash loops, and rollbacks.
- Owners, recovery criteria, where evidence is stored, and how to hand off incidents without a full root-cause fix yet.

Do not list every Spring property in the handover doc. Document the decisions that directly govern access, diagnosis, and recovery.

## 14. Self-check before considering configuration complete

Repeat on the target environment, not only on a personal laptop:

1. Start with valid config; missing required secrets or invalid simulation values must fail loudly and clearly.
2. Verify ports and bind scopes; unauthorized locations must not reach the management port.
3. Confirm health/probes expose only chosen detail level; metrics require proper identity and role.
4. Send business traffic, verify meters appear with exact tags/units and correlate with logs.
5. Simulate dependency outage: liveness stays UP, readiness switches DOWN as designed, platform drains traffic properly.
6. Simulate slowness: health may stay UP while external timings and timers reflect the slowdown.
7. Test graceful shutdown; verify in-flight requests, drain timing, and platform termination grace limits.
8. After recovery, verify business flows, error rates/latency, and monitoring data; clean up all temporary diagnostic settings.
9. Have someone else walk through the handover doc and note anything unclear.

Two final self-assessment questions: if readiness is DOWN while liveness is UP, what do you plan to do and based on what evidence? If all health checks report UP yet p95 triples, which additional signals will you inspect before changing configuration?
