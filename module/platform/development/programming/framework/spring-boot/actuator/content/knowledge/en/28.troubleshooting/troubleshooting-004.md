# Troubleshooting health DOWN, UNKNOWN, and Responses Without Details

## 1. A Health Response Has Three Layers of Information

When `/actuator/health` returns `DOWN`, you cannot immediately conclude the Java process is dead. When it returns HTTP 200, you cannot immediately conclude every business function is working. You must read the health status, the HTTP status code, and the scope of exposed data together.

| Layer | Examples | Question to answer |
| --- | --- | --- |
| Health status | `UP`, `DOWN`, `OUT_OF_SERVICE`, `UNKNOWN` | How are the checks evaluating the system? |
| HTTP status code | 200, 503 | How has the health status been mapped to the protocol? |
| Visible content | `components`, `details`, or only `status` | How much is the caller allowed to see, and did the indicator produce details? |

Simplified processing model:

```text
HealthIndicator / HealthContributor tree
  -> select components belonging to the called health group
  -> StatusAggregator aggregates statuses
  -> HttpCodeStatusMapper maps status to HTTP code
  -> apply display policy for components and details
  -> return response to caller
```

These are logical responsibilities, not a guarantee of statement-by-statement execution order. Each `HealthEndpointGroup` has its own aggregator, mapper, and display policy. Therefore, root health, readiness, and a custom group can return different results while still being correctly configured. [HealthEndpointGroup contract](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthEndpointGroup.html).

This lesson focuses on troubleshooting with Spring Boot 3.3.13, Java 21, and Spring MVC/Servlet. The status and group concepts are also useful with WebFlux, though the Servlet security configuration in the example cannot be copied verbatim to WebFlux.

## 2. Interpreting DOWN and UNKNOWN Within Their True Scope

### 2.1. DOWN Is an Evaluation Result, Not the Name of One Cause

`DOWN` indicates that at least one condition is evaluated as unhealthy according to the rules of the current indicators and aggregator. In a real system, that condition could be a failed database connection, low disk space, rejected access to a downstream dependency, or a failing custom check.

Drill down to the failing component instead of immediately overriding the root status:

```json
{
  "status": "DOWN",
  "components": {
    "catalog": {
      "status": "DOWN",
      "details": {
        "dependency": "catalog-stub",
        "reason": "simulated_unavailable"
      }
    }
  }
}
```

This is an illustrative data shape for the lab below. Do not infer real service names, connection addresses, or production failures from a sample JSON. In Actuator V3 data, `status` at the root is the overall result; `components.<id>.status` is the component's status, and `components.<id>.details` is that component's details. Not all details sit in a `details` field directly under root. [Health V3 response structure](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

### 2.2. UNKNOWN Means No Conclusion Expressible Under Current Rules

`UNKNOWN` is neither synonymous with `DOWN` nor another way of spelling `UP`. Check two layers:

- Is an indicator intentionally returning `UNKNOWN` because it has no samples yet, is not ready to evaluate, or has not set a status?
- Are child statuses recognized by the aggregator, especially when custom codes such as `DEGRADED` exist?

With the default `SimpleStatusAggregator` in version 3.3.13 specifically, the precedence order is `DOWN`, `OUT_OF_SERVICE`, `UP`, `UNKNOWN`; statuses listed earlier take precedence. The aggregator ignores codes absent from the order and picks the highest-priority recognized status; if no recognized code is present, it returns `UNKNOWN`.

| Input child statuses | Default aggregated result |
| --- | --- |
| `UP` and `DOWN` | `DOWN` |
| `UP` and `UNKNOWN` | `UP` |
| Only `UNKNOWN` | `UNKNOWN` |
| Only `DEGRADED`, order not declared | `UNKNOWN` |
| `UP` and `DEGRADED`, order not declared | `UP` |

Important note: this is not voting by indicator count; many `UP` components do not outvote one `DOWN` component. Also, do not read a custom order example in documentation and mistake it for the default order. [SimpleStatusAggregator 3.3.13 source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java).

Do not infer "no components are visible, so there must be no indicators and root must be UNKNOWN." Hiding data is separate from indicator registration. Moreover, a root endpoint with no contributing results at all has a branch returning `UP` by default in this version; do not equate that case with a set of unrecognized child statuses. [Root result handling in HealthEndpointWebExtension](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointWebExtension.java).

### 2.3. HTTP Code and Health Status Are Two Distinct Values

With Spring Boot 3.3's default mapping:

| Health status | Default HTTP | How to read it |
| --- | --- | --- |
| `UP` | 200 | Participating checks produced this result |
| `DOWN` | 503 | Aggregator evaluated as unhealthy |
| `OUT_OF_SERVICE` | 503 | Out of service/operating scope according to checks |
| `UNKNOWN` | 200 | No clear health conclusion yet; 200 does not turn it into UP |

`HttpCodeStatusMapper` maps the health status to an HTTP status code. The mapping policy can be replaced, so inspect both effective configuration and the JSON during investigation. [SimpleHttpCodeStatusMapper API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

An HTTP 503 accompanied by health JSON `DOWN` shows an evaluation was received from the endpoint, unlike a 401/403 rejected by security or a 503 generated by a proxy when it cannot reach the application. Check the origin of the response; do not read only the number 503 on a monitoring dashboard.

## 3. Why Are components or details Missing?

Distinguish component names, detail payloads, and URL access permissions:

| Configuration | What it controls |
| --- | --- |
| `management.endpoint.health.show-components` | Whether to expose the component tree in the response |
| `management.endpoint.health.show-details` | Whether to expose indicator detail data |
| `management.endpoint.health.roles` | Roles allowed to view when policy uses `when-authorized` |
| Rules in `SecurityFilterChain` | Whether the caller is allowed to access the health URL at all |

Both visibility policies accept `never`, `when-authorized`, `always`. `show-details` defaults to `never`; when `show-components` is not set separately, component visibility follows the details policy. With `when-authorized`, if a roles list is set, the caller must hold at least one role in the list; if no roles are set, any authenticated user can view. [Spring Boot 3.3 health visibility policy](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

Situations that are not necessarily bugs:

- Seeing only `{"status":"DOWN"}`: all checks may still have run in full, while the caller is not authorized to see the tree and details.
- Seeing `components.catalog.status` without `details`: component visibility may be enabled while details are hidden.
- Having permission to view details yet an indicator only returns `Health.up().build()`: that indicator creates no extra data to display.
- Root response has no `details` while child components do: the data structure is valid; read at the proper nesting level.

`HealthIndicator.getHealth(includeDetails)` allows keeping or omitting details while still returning the health status. Therefore, enabling visibility does not fix a failing check; hiding details does not stop checks from running either. [HealthIndicator contract](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html).

Controlled configuration commonly used for investigation:

```properties
management.endpoint.health.show-components=when-authorized
management.endpoint.health.show-details=when-authorized
management.endpoint.health.roles=OPS
```

Here `roles=OPS` controls data visibility; it does not impose a URL protection rule by itself. If the URL allows public access, an unauthenticated caller can still receive the aggregated status without details. Conversely, setting `always` does not bypass a security rule blocking the URL.

Do not expose all details publicly just to identify a root cause. Indicator payloads can contain hostnames, paths, database names, or exception messages. During investigation, use an authorized account and collect only the needed data.

## 4. Diagnosing DOWN: Find the Failing Check, Then Fix the Condition

### Step 1: Identify the Exact Endpoint and Timestamp

Record the URL, management port, profile, application version, instance/pod, and sampling timestamp. Root `/actuator/health`, `/actuator/health/readiness`, and `/actuator/health/liveness` can use different sets of components.

If there is a proxy or load balancer, two consecutive GETs may hit two different instances. When investigating an intermittent failure, correlate each response with its exact instance and inspect logs from the same timestamp.

### Step 2: Fetch Component Status with Appropriate Permissions

Read health using an account allowed to view details. Locate the `DOWN` component, then inspect `reason`, `error`, or whatever fields the indicator actually emits. For composite contributors, continue drilling down into nested children.

You can query a single component via `/actuator/health/<component-id>` when the component exists and policy permits. Do not guess IDs from Java class names: IDs are derived from bean names according to registration rules. When `show-components` disallows it, the component path may return 404 even while root still returns a status. [Component scope check in HealthEndpointSupport](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/HealthEndpointSupport.java).

### Step 3: Check Dependencies from the Same Runtime Environment as the App

| Component showing DOWN | What to verify |
| --- | --- |
| Database | DNS/host/port, network path, TLS, credentials, connection limits, ability to borrow a connection, and the specific check |
| Disk space | Actual partition/path, remaining space, threshold, and mounted volumes in the container |
| Cache or message broker | Effective endpoint and authentication, ACLs, TLS, connectivity, and resources required by the check |
| Custom indicator | Status-returning rules, input data, timeouts, and exceptions of the check itself |

Being able to connect from your local laptop does not prove the container can connect. Also do not rotate passwords, increase pool sizes, or change timeouts solely because you saw `DOWN`; every change must be tied to concrete evidence.

### Step 4: Distinguish Dependency Failures from Check Bugs

An indicator may probe the wrong address, use stale credentials, require overly broad permissions, or treat an acceptable condition as a critical failure. In such cases, fix the check or its configuration rather than altering a healthy service.

When using `AbstractHealthIndicator`, exceptions thrown from `doHealthCheck` are converted to `DOWN` per that class's contract. Do not generalize that exceptions from every `HealthIndicator` implementation are handled identically. [AbstractHealthIndicator API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/AbstractHealthIndicator.html).

Do not catch every exception and return `UP` just to make dashboards green again. Decide clearly which conditions render the system unable to serve traffic and which are degradations handleable via fallbacks.

### Step 5: Check Execution Time

If the endpoint responds slowly or clients time out, examine connect, read, and resource-wait durations inside each indicator. Slow-indicator warning logs are only diagnostic signals; the log threshold does not impose a deadline or cancel network calls. Configure real timeouts on dependency clients and keep checks lightweight without business write operations.

### Step 6: Verify After Fixing

Re-read the same group, same instance, and same account. Confirm the failing component has recovered before checking the aggregated status and HTTP code. Cross-check with a representative business test: health only knows what its checks actually observe.

## 5. Diagnosing UNKNOWN: Find the Source of Missing Conclusions

Proceed in this order:

1. Open the component tree with proper permissions; determine whether `UNKNOWN` originates in one indicator or only in the aggregated result.
2. If an indicator returns `UNKNOWN`, read the status-setting logic and prerequisite data before evaluation. Is this status intentional, or did code forget to set `UP`/`DOWN`?
3. If components use custom codes, check `management.endpoint.health.status.order` and any `StatusAggregator` beans applied.
4. Check the member set of the queried group, active profiles, and bean registration conditions. Do not infer from intended config that an indicator was definitely registered.
5. Check how your monitoring policy handles `UNKNOWN`. Do not treat UNKNOWN's HTTP 200 as proof of a positive conclusion.

If business requirements demand treating `UNKNOWN` as more severe than `UP`, define and test that policy explicitly. Changing the aggregation order affects every participating status, not just one UI label.

For custom statuses, two independent things must be addressed: whether the code is recognized during aggregation, and how the aggregated code maps to HTTP. Adding only `http-mapping.degraded=503` does not make the aggregator recognize `DEGRADED`.

Example of an intentional policy treating UNKNOWN as more severe than UP:

```properties
management.endpoint.health.status.order=degraded,down,out-of-service,unknown,up
management.endpoint.health.status.http-mapping.degraded=503
management.endpoint.health.status.http-mapping.down=503
management.endpoint.health.status.http-mapping.out-of-service=503
management.endpoint.health.status.http-mapping.unknown=503
```

This is an illustrative policy choice, not the default configuration. When declaring custom HTTP mappings with this configuration, you must re-declare `DOWN` and `OUT_OF_SERVICE` if you want to preserve their default 503 mapping. Simply mapping `DOWN` to HTTP 200 does not fix the condition making it DOWN.

## 6. Standalone Practice: Reproducing Statuses and Detail Visibility Permissions

### 6.1. Lab Scope

The example has exactly one custom indicator named `catalog`. It simulates results and makes no network connection to a real service. We disable default auto-configured indicators in this project so `UNKNOWN` is not altered by another `UP` indicator during aggregation.

Use Java 21, Maven 3.6.3 or later, and Python 3. Maven needs access to dependency repositories if not already cached. Project structure:

```text
health-diagnosis-lab/
├── pom.xml
├── verify.py
└── src/main/
    ├── java/example/health/HealthDiagnosisLab.java
    └── resources/application.properties
```

### 6.2. Build and Application Configuration

File pom.xml:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>health-diagnosis-lab</artifactId>
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
```

File src/main/resources/application.properties:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.health.defaults.enabled=false
management.endpoint.health.show-components=when-authorized
management.endpoint.health.show-details=when-authorized
management.endpoint.health.roles=OPS
lab.mode=DOWN
```

File src/main/java/example/health/HealthDiagnosisLab.java:

```java
package example.health;

import jakarta.servlet.DispatcherType;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.AbstractHealthIndicator;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class HealthDiagnosisLab {
    public enum Mode { UP, DOWN, UNKNOWN, DEGRADED, THROW }

    public static void main(String[] args) {
        SpringApplication.run(HealthDiagnosisLab.class, args);
    }

    @Bean
    HealthIndicator catalogHealthIndicator(@Value("${lab.mode:DOWN}") Mode mode) {
        return new AbstractHealthIndicator() {
            @Override
            protected void doHealthCheck(Health.Builder builder) {
                builder.withDetail("dependency", "catalog-stub");
                switch (mode) {
                    case UP -> builder.up().withDetail("reason", "simulated_ok");
                    case DOWN -> builder.down()
                        .withDetail("reason", "simulated_unavailable");
                    case UNKNOWN -> builder.unknown()
                        .withDetail("reason", "not_evaluated");
                    case DEGRADED -> builder.status("DEGRADED")
                        .withDetail("reason", "partial_capacity");
                    case THROW -> throw new IllegalStateException("simulated probe failure");
                }
            }
        };
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer").password("{noop}viewer-pass")
                .roles("VIEWER").build(),
            User.withUsername("ops").password("{noop}ops-pass")
                .roles("OPS").build()
        );
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
            .requestMatchers(EndpointRequest.to("health")).permitAll()
            .anyRequest().denyAll()
        );
        http.httpBasic(withDefaults());
        return http.build();
    }
}
```

`catalogHealthIndicator` is the bean name, while the displayed component ID is `catalog` after stripping the `HealthIndicator` suffix. The viewer account can call the URL but lacks the OPS role to see details. The ops account has that role. Allowing `DispatcherType.ERROR` avoids blocking error response rendering; it does not grant access to direct requests to `/error`.

Hardcoded passwords and `{noop}` are strictly for loopback labs. Real environments require proper identity management and HTTPS for HTTP Basic. Never put sample account configurations verbatim into public services.

Build from the project root directory:

```shell
mvn package
```

Because this project has Spring Boot dependencies, it cannot be compiled completely by running `javac` on the Java file alone. After building, start the app:

```shell
java -jar target/health-diagnosis-lab-1.0.0.jar
```

Keep the application running and open a second terminal in the same directory. Ensure port 8080 is not already used by another application.

### 6.3. Script to Verify Status, HTTP Code, and Data Visibility

The file verify.py uses the Python standard library. Its arguments are expected root status, expected HTTP code, and expected catalog component status:

```python
import base64
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

URL = "http://127.0.0.1:8080/actuator/health"


def read_health(credentials=None):
    headers = {"Accept": "application/json"}
    if credentials is not None:
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        headers["Authorization"] = "Basic " + encoded
    request = Request(URL, headers=headers, method="GET")
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        return response.code, json.loads(response.read())


def main():
    if len(sys.argv) != 4:
        raise SystemExit("Usage: python verify.py ROOT_STATUS HTTP_CODE COMPONENT_STATUS")
    root_status, http_code, component_status = sys.argv[1:]
    http_code = int(http_code)
    cases = [
        ("anonymous", None, False),
        ("viewer", "viewer:viewer-pass", False),
        ("ops", "ops:ops-pass", True),
    ]
    for label, credentials, visible in cases:
        code, body = read_health(credentials)
        assert code == http_code, (label, code, body)
        assert body["status"] == root_status, (label, body)
        assert ("components" in body) == visible, (label, body)
        visibility = "visible" if visible else "hidden"
        print(f"{label}: HTTP={code}, status={body['status']}, components={visibility}")
        if visible:
            component = body["components"]["catalog"]
            assert component["status"] == component_status, component
            assert component["details"]["dependency"] == "catalog-stub", component
            print(f"catalog: status={component['status']}, dependency=catalog-stub")


if __name__ == "__main__":
    main()
```

With the project's default configuration, run:

```shell
python verify.py DOWN 503 DOWN
```

Exact stdout:

```text
anonymous: HTTP=503, status=DOWN, components=hidden
viewer: HTTP=503, status=DOWN, components=hidden
ops: HTTP=503, status=DOWN, components=visible
catalog: status=DOWN, dependency=catalog-stub
```

Same status and same HTTP code, yet the three callers see different amounts of data. Adding an OPS account only lets you observe the cause; it does not make health switch to UP.

You can inspect raw responses with the following commands. Use `curl.exe` on Windows if `curl` points to another command:

```shell
curl -i -H "Accept: application/json" http://127.0.0.1:8080/actuator/health
curl -i -u ops:ops-pass -H "Accept: application/json" http://127.0.0.1:8080/actuator/health
```

Do not add `-f` and discard errors when you need to read a 503 body. Failing health responses still contain useful evidence.

### 6.4. Reproducing UNKNOWN and Recovering UP

Stop the current process with Ctrl+C before each restart. Run each mode and its corresponding verification command in the second terminal:

| Mode | Startup command | Verification command | Key outcome |
| --- | --- | --- | --- |
| Not evaluated | `java -jar target/health-diagnosis-lab-1.0.0.jar --lab.mode=UNKNOWN` | `python verify.py UNKNOWN 200 UNKNOWN` | Root UNKNOWN still pairs with default HTTP 200 |
| Healthy evaluation | `java -jar target/health-diagnosis-lab-1.0.0.jar --lab.mode=UP` | `python verify.py UP 200 UP` | Both status and HTTP reflect expected outcome |
| Unrecognized code | `java -jar target/health-diagnosis-lab-1.0.0.jar --lab.mode=DEGRADED` | `python verify.py UNKNOWN 200 DEGRADED` | Component DEGRADED yet root UNKNOWN |
| Exception in check | `java -jar target/health-diagnosis-lab-1.0.0.jar --lab.mode=THROW` | `python verify.py DOWN 503 DOWN` | AbstractHealthIndicator turns exception into DOWN |

In THROW mode, server logs contain a warning and simulated exception; that is not stdout from verify.py. When detail visibility is allowed, the indicator's error data can appear in the response.

### 6.5. Recognizing Custom Codes and Testing Mapping

Run the app with DEGRADED and explicitly declare the order along with HTTP mappings. The command below is written on one line for compatibility across terminals:

```shell
java -jar target/health-diagnosis-lab-1.0.0.jar --lab.mode=DEGRADED --management.endpoint.health.status.order=degraded,down,out-of-service,up,unknown --management.endpoint.health.status.http-mapping.degraded=503 --management.endpoint.health.status.http-mapping.down=503 --management.endpoint.health.status.http-mapping.out-of-service=503
```

Verify:

```shell
python verify.py DEGRADED 503 DEGRADED
```

This time root is DEGRADED and HTTP is 503. Comparing with the DEGRADED mode in the earlier table shows the difference between indicator data, aggregation rules, and HTTP mapping. The order in this command only prepends DEGRADED while keeping UP before UNKNOWN; do not confuse it with the policy in section 5 where UNKNOWN is more severe than UP.

### 6.6. Showing Components While Hiding Details

Stop the previous process, then run:

```shell
java -jar target/health-diagnosis-lab-1.0.0.jar --management.endpoint.health.show-components=always --management.endpoint.health.show-details=never
```

Now both unauthenticated callers and OPS can see the catalog component and its DOWN status, but not the catalog's details field. Observe with curl; do not reuse the verification script from section 6.3 as-is because that script checks the initial `when-authorized` policy.

If switching in the opposite direction to `show-details=always` on a public URL, evaluate what data will be exposed. Do not use visibility changes as a remediation for health DOWN.

## 7. When Root Health and Probes Produce Different Results

A health group is a set of checks chosen for a specific purpose. Root may be DOWN because of catalog, while readiness excludes catalog and therefore remains UP. What needs investigation is the member set and intended operational decision, not merely two differing status strings.

For probes, distinguish:

- Liveness evaluates whether the application can stay alive. A failing external dependency is usually not solved by restarting all application instances en masse.
- Readiness supports deciding whether to route traffic to an instance. Include a dependency in this group only when its failure truly means the instance should not receive work.
- Whether a dependency has a fallback or is shared by all instances affects the decision to put it in readiness.

Do not add every external dependency to liveness, and do not remove indicators from root/readiness just to silence alerts. Every membership change must have a rationale and a test under dependency failure.

Check three additional practical points:

1. Are probe groups enabled in the running environment? Do not assume based on an intended deployment environment.
2. Does group configuration override visibility, status order, or HTTP mapping compared to root?
3. Are probes hitting the right web infrastructure of the application? A separate management port responding well does not prove the business port still accepts connections.

If a project uses a separate management port, an additional probe path can be designed on the main port and its access rules tested. Do not alter ports or security rules during investigation without tracking the impact on the probe caller.

## 8. Fixes That Produce Misleading Signals

| Approach | Why it misleads | Sound handling |
| --- | --- | --- |
| Immediately disable an indicator showing DOWN | Loses the signal while the failure condition may remain | Verify whether the check reflects serving requirements; fix the cause or intentionally adjust scope |
| Always return UP in catch | Masks both real failures and check bugs | Clear failure classification and health rules |
| Map every status to HTTP 200 | Monitors checking only HTTP status may report false green | Align HTTP and health status contracts with consumers |
| Enable always to "fix" DOWN | Changes only how much data is revealed | Use proper viewing permissions, then address the failing condition |
| Set a low slow-indicator-threshold and treat it as a timeout | Log threshold does not cancel checks | Configure real call timeouts and bound check cost |
| Look only at root UP | Can miss ignored custom codes, child UNKNOWN, or unmeasured business paths | Check observation scope and required component statuses |
| Compare two responses from two instances | Can mistake distributed failures for visibility config bugs | Tie evidence to instance, group, timestamp, and caller identity |

## 9. Reasoning Check Exercises

1. HTTP 200 yet JSON shows UNKNOWN: is that enough to mark business functionality healthy?
2. One component is UP and one component is UNKNOWN: what is the default root status in 3.3.13? Which layer do you edit if you want a different outcome?
3. Only component DEGRADED exists, yet root is UNKNOWN: is adding only http-mapping.degraded=503 sufficient?
4. Anonymous and OPS both see DOWN, yet only OPS sees details: is this necessarily an authentication bug?
5. show-details=always, yet an indicator still has no details: what should you check in the indicator code?
6. Database failure makes root DOWN while readiness stays UP: should you inspect group membership or map every HTTP status to 200?

Reference guide: question 1 lacks sufficient evidence; question 2 root is UP, and changing the policy requires adjusting the aggregator/order; question 3 DEGRADED must be recognized in aggregation before mapping the result; question 4 may be expected per visibility policy; question 5 check whether the indicator adds details and whether group config overrides it; question 6 verify group membership alongside the purpose of readiness.

A worthwhile diagnostic result must identify which component produced the status, which rule aggregated it, which HTTP mapping applies, what the caller is permitted to see, and what evidence demonstrates the failing condition has been resolved.
