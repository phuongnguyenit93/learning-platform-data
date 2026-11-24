# Customizing Details, Roles, Status Order, and HTTP Status per Group

## 1. What Questions Should a Health Group Answer?

A health group is a set of health checks selected for a specific purpose. For example, a `traffic` group provides a signal for traffic routing components, while an `ops` group serves operators performing diagnostics. Two groups can use the same `HealthIndicator` yet apply different response policies.

Four questions should be separated:

| Question | Controlling configuration or component |
| --- | --- |
| Who is allowed to send requests to the URL? | Spring Security, via `SecurityFilterChain` |
| To what extent can the caller see component names and diagnostic data? | The group's `show-components`, `show-details`, `roles` |
| How are multiple component statuses combined into one status? | The group's `status.order` or `StatusAggregator` |
| Which HTTP code does the aggregated status become? | The group's `status.http-mapping` or `HttpCodeStatusMapper` |

For example, an unauthenticated caller might be allowed to receive HTTP 503 and `{"status":"DOWN"}`, while a caller with an operator role also receives the failing component. Basic health status and diagnostic information serve two distinct needs.

This lesson uses Spring Boot **3.3.13**, Java **21**, and Spring MVC for illustration. Group policies belong to Actuator; the `HttpSecurity` configuration in the example is for Servlet applications. WebFlux applications require the corresponding WebFlux security configuration.

A group has its own contract consisting of membership, status aggregator, HTTP mapper, and visibility policy. These components are represented in the [HealthEndpointGroup API of Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthEndpointGroup.html).

## 2. Processing Flow: Status, HTTP, and Content Are Three Distinct Outputs

For an authorized request to the health endpoint, you can picture it as:

```text
GET /actuator/health/ops
    -> Select group ops
    -> Select contributors belonging to the group
    -> Collect Health from each contributor
    -> StatusAggregator chooses the overall status
    -> HttpCodeStatusMapper chooses the HTTP status code
    -> Visibility policy decides components/details for the caller
    -> Return response
```

This is a model of responsibilities, not a guarantee of internal invocation order or how many times a check executes.

Important consequences to remember:

- Hiding details does not remove a check's membership and does not turn `DOWN` into `UP`.
- Changing the HTTP status code does not change the `status` field in JSON.
- Adding a mapping for `DEGRADED` does not teach the aggregator that status's priority.
- Putting a contributor in a group does not exclude that contributor from overall health.
- There is no contract that two requests to two groups share a single snapshot of results. Real checks may observe different states between calls.

Therefore, when testing, verify **the HTTP code, JSON status, and level of data shown** together.

## 3. Identifying Configuration Scope and Inheritance Rules Correctly

The common prefix is:

```properties
management.endpoint.health
```

The specific prefix for a group named `ops` is:

```properties
management.endpoint.health.group.ops
```

The default path to read the group is:

```text
/actuator/health/ops
```

Groups are declared under the health endpoint; there is no need to add `ops` to the exposed endpoints list. With the default path, exposing the `health` endpoint is sufficient:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
```

This exposure is still subject to the application's endpoint enablement and security configuration.

In Boot 3.3 auto-configuration, a group that does not declare its own policy uses the corresponding common policy. Three points are easily misunderstood:

1. A group-specific `status.order` list, when non-empty, creates a dedicated aggregator; it does not automatically append trailing entries from the common list.
2. A group-specific `status.http-mapping` map, when non-empty, creates a dedicated mapper; it does not automatically merge individual keys with the common map.
3. A non-empty group-specific `roles` set replaces the common role set. In this version, an empty group-specific set still falls back to the common set; do not use `roles: []` to try to remove a role restriction configured at the common level.

Additionally, a `StatusAggregator` or `HttpCodeStatusMapper` bean with a qualifier matching the group name takes precedence over property configuration for that component. This is the behavior in [Boot 3.3.13 group auto-configuration code](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/health/AutoConfiguredHealthEndpointGroups.java).

## 4. Customizing Visibility Level

### 4.1. Distinguishing components from details

An illustrative response has the following structure:

```json
{
  "status": "DEGRADED",
  "components": {
    "catalog": {
      "status": "DEGRADED",
      "details": {
        "mode": "simulated"
      }
    },
    "ping": {
      "status": "UP"
    }
  }
}
```

- Outermost `status`: the aggregated result of the group.
- `components`: the visible components along with their respective statuses.
- `details`: additional diagnostic data provided by a check.

`show-components` controls display of the component tree. `show-details` controls detailed data. Component names alone can reveal architecture even when `details` are hidden.

Both use these values:

| Value | Meaning for the corresponding information |
| --- | --- |
| `never` | Do not show |
| `when-authorized` | Show when the caller meets authorization conditions |
| `always` | Show to any caller who has passed the access-control layer |

By default, `show-details` is `never`. If `show-components` is not specified after resolving inherited configuration, component visibility is based on `show-details`. To avoid subtle effects from common configuration, the examples below specify both explicitly.

### 4.2. Two Common Policies

A machine-facing group that only needs the status:

```yaml
management:
  endpoint:
    health:
      group:
        traffic:
          include: [catalog, ping]
          show-components: never
          show-details: never
```

A group for authorized operators:

```yaml
management:
  endpoint:
    health:
      group:
        ops:
          include: [catalog, ping]
          show-components: when-authorized
          show-details: when-authorized
          roles: [OPS]
```

The YAML snippets in the explanation sections are alternative or incremental settings in their proper locations; do not paste multiple duplicate `management` keys into the same YAML document. The hands-on section provides one complete file.

If you need to expose each component's status while hiding diagnostic data, you can choose `show-components: always` and `show-details: never`. You should intentionally accept exposing component names.

## 5. Roles for Viewing Details Differ from URL Access Control

With `when-authorized`, Actuator determines whether the caller is allowed to see details based on the security context. When no effective roles are configured, any authenticated caller can see them; when a list of roles is configured, matching at least one role is sufficient. The security context contract consists of the current principal and role checks, described in [Actuator SecurityContext](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/SecurityContext.html).

For example:

```properties
management.endpoint.health.group.ops.roles=OPS,SUPPORT
```

This means a caller with role `OPS` **or** `SUPPORT` qualifies, when visibility modes are set to `when-authorized`.

These properties do not:

- Create users or passwords.
- Authenticate an HTTP request.
- Automatically generate `hasRole(...)` rules to block URLs.
- Guarantee callers lacking the role receive HTTP 403.

If the security filter chain allows anonymous callers to reach the group, they can still receive status-only JSON. The response status code is then decided by health status and the HTTP mapper.

In typical Servlet configuration, `User.withUsername(...).roles("OPS")` creates the authority `ROLE_OPS`; the example in this lesson uses `roles: [OPS]` accordingly. Systems using JWTs or custom authorities must map authorities to roles matching the application's checking mechanism, rather than guessing from claim names.

If you want to **block the ops URL itself**, the path rule must precede the general health permit rule:

```java
// Snippet replacing the authorizeHttpRequests section in SecurityFilterChain;
// this is not a standalone runnable Java class.
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/actuator/health/ops", "/actuator/health/ops/**")
        .hasRole("OPS")
    .requestMatchers("/actuator/health", "/actuator/health/**")
        .permitAll()
    .anyRequest().denyAll());
```

This changes the access contract: unauthorized requests may be blocked before receiving a health result. It must be tested against the actual authentication mechanism. Matcher ordering and first-match-wins behavior are explained in [Spring Security request authorization docs](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).

## 6. Status Order Is the Aggregation Policy

### 6.1. Earlier Elements Have Higher Priority

The default of `SimpleStatusAggregator` in Boot 3.3.13 is:

```text
DOWN -> OUT_OF_SERVICE -> UP -> UNKNOWN
```

This is the precedence order for choosing the combined result when multiple statuses are present, not the execution order of checks or JSON key sorting order.

For example, with `{UP, DOWN}`, the result is `DOWN`; with `{UP, UNKNOWN}`, the default result is `UP`.

A custom list can place `UNKNOWN` before `UP` so that a signal with missing information beats a healthy signal. When choosing that policy, a group may report not ready simply because one component has an undetermined status.

### 6.2. Custom Statuses Must Have a Position in the List

For example:

```yaml
management:
  endpoint:
    health:
      group:
        ops:
          status:
            order:
              - DOWN
              - OUT_OF_SERVICE
              - DEGRADED
              - UNKNOWN
              - UP
```

In this policy, `DEGRADED` represents impaired operation rather than complete outage.

The list is used as a complete replacement. Configuring only `[DEGRADED, UP]` can cause `DOWN` to be omitted from the statuses considered by the aggregator. This is a serious error even though the YAML is valid.

`SimpleStatusAggregator` only picks among statuses present in its known order. If none of the input statuses are known, the result is `UNKNOWN`. Thus, a check returning `DEGRADED` while the list only knows the default statuses can be ignored when another component returns `UP`. Align the check's status set with the policy of every group that uses it, including overall health. This default behavior and filtering are shown in [SimpleStatusAggregator 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.java).

### 6.3. Two Groups Can Prioritize Differently

Suppose one group prioritizes unknown over degraded, and the other prioritizes degraded over unknown:

| Group | Relevant order | Hypothetical inputs | Result |
| --- | --- | --- | --- |
| `traffic` | `DOWN, OUT_OF_SERVICE, UNKNOWN, DEGRADED, UP` | `DEGRADED`, `UNKNOWN` | `UNKNOWN` |
| `ops` | `DOWN, OUT_OF_SERVICE, DEGRADED, UNKNOWN, UP` | `DEGRADED`, `UNKNOWN` | `DEGRADED` |

This is a policy choice and needs an operational rationale. Keep `DOWN` and `OUT_OF_SERVICE` first if they must always win over all other statuses. Do not reorder them just to make a monitoring dashboard turn green.

## 7. Mapping Status to HTTP

### 7.1. Mapping Uses Only the Aggregated Status

After computing the group status, the mapper converts the health status code into an HTTP status code. The default API provides a mapper based on a table of status names to numbers: [SimpleHttpCodeStatusMapper](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

In the default configuration:

| Status | HTTP |
| --- | --- |
| `DOWN` | 503 |
| `OUT_OF_SERVICE` | 503 |
| `UP` | 200 |
| `UNKNOWN` | 200 |
| Unmapped status | 200 |

Do not assume `UNKNOWN` defaults to 503. If the consumer requires "unknown means do not receive traffic", configure it explicitly.

### 7.2. Redeclare All Cases You Want to Keep

For example, a diagnostic group treats `DEGRADED` as a successfully readable response:

```yaml
management:
  endpoint:
    health:
      group:
        ops:
          status:
            http-mapping:
              down: 503
              out-of-service: 503
              degraded: 200
              unknown: 503
              up: 200
```

When providing your own map, you must explicitly retain mappings such as `down` and `out-of-service` if you still want them to return 503. Adding only `degraded: 200` does not preserve the default mappings.

Do not use HTTP 401/403 as a signal for a failing check. Those codes are for authentication/authorization; a group not ready to serve traffic typically uses 503. Even though arbitrary numbers can be assigned, the HTTP contract must make sense to the consumer.

### 7.3. Same Status, Different HTTP

Two groups that both aggregate to `DEGRADED` can return:

| Group | JSON | HTTP | Meaning in the example |
| --- | --- | --- | --- |
| `ops` | `{"status":"DEGRADED"}` | 200 | Diagnostic tools must read the status field to alert |
| `traffic` | `{"status":"DEGRADED"}` | 503 | Traffic routing components do not consider the group ready |

The 200 code for the `ops` group is a decision for this example, not a universal rule for degraded status. If a tool only treats HTTP 2xx as "healthy", it will miss this condition. Agree upfront whether tools read the HTTP code, the JSON field, or both.

## 8. Complete Hands-On Practice: Two Groups and Two Access Levels

### 8.1. Preparing the Standalone Project

The example requires no database or external services. The `catalog` check returns a simulated status from a startup property, allowing you to observe policies without causing real outages.

Use JDK 21 and Maven 3.6.3 or later. Create a separate project directory with this structure:

```text
health-group-demo/
  pom.xml
  src/main/java/example/HealthGroupApplication.java
  src/main/resources/application.yml
```

The `pom.xml` file:

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
  <artifactId>health-group-demo</artifactId>
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

### 8.2. Application and Test Users

The `src/main/java/example/HealthGroupApplication.java` file:

```java
package example;

import java.util.Locale;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
public class HealthGroupApplication {

    public static void main(String[] args) {
        SpringApplication.run(HealthGroupApplication.class, args);
    }

    @Bean
    HealthIndicator catalogHealthIndicator(
            @Value("${demo.catalog-status:DEGRADED}") String configuredStatus) {
        String code = configuredStatus.trim().toUpperCase(Locale.ROOT);
        return () -> Health.status(code)
                .withDetail("mode", "simulated")
                .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("operator")
                        .password("{noop}operator-pass")
                        .roles("OPS")
                        .build(),
                User.withUsername("viewer")
                        .password("{noop}viewer-pass")
                        .roles("VIEWER")
                        .build());
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/actuator/health", "/actuator/health/**")
                    .permitAll()
                .anyRequest().denyAll());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

The `catalogHealthIndicator` bean has the health ID `catalog`; the `HealthIndicator` suffix is stripped when determining the ID. The check builds a `Health` with a status and illustrative detail data; the result builder API is described in [Health 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Health.html).

The accounts and passwords above are only for local execution. `{noop}` simplifies the experiment setup; real systems require proper password storage and transport security. The `mode` data is simulated and contains no connection details or secrets.

The security rule permits reading all health paths so we can observe that lacking a role only hides information. HTTP Basic still processes sent credentials, allowing callers with the `OPS` role to be recognized.

### 8.3. Complete Configuration

The `src/main/resources/application.yml` file:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-components: never
      show-details: never
      status:
        order: [DOWN, OUT_OF_SERVICE, UNKNOWN, DEGRADED, UP]
        http-mapping:
          down: 503
          out-of-service: 503
          unknown: 503
          degraded: 503
          up: 200
      group:
        traffic:
          include: [catalog, ping]
          show-components: never
          show-details: never
        ops:
          include: [catalog, ping]
          show-components: when-authorized
          show-details: when-authorized
          roles: [OPS]
          status:
            order: [DOWN, OUT_OF_SERVICE, DEGRADED, UNKNOWN, UP]
            http-mapping:
              down: 503
              out-of-service: 503
              unknown: 503
              degraded: 200
              up: 200
```

Here:

- `traffic` inherits the common status order and HTTP mapping table.
- `ops` has its own status order and HTTP mapping table.
- Both use `catalog` and the Boot auto-configured `ping` check.
- Overall health also recognizes `DEGRADED`, avoiding ignoring the custom status when combined with `UP`.
- Other auto-configured components may appear in overall health, but do not belong to the two groups because `include` explicitly restricts them.

Enabling/disabling endpoints, selecting members, and exposing over HTTP are separate decisions. Group syntax, visibility conditions, and default mappings are covered in [Boot 3.3 health endpoint documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.health).

### 8.4. Compiling and Running

From the directory containing `pom.xml`:

```shell
mvn package
java -jar target/health-group-demo-1.0.0.jar
```

Maven downloads dependencies if they are not already cached. This example has Spring dependencies, so compile and package with Maven; do not run `javac HealthGroupApplication.java` on its own without setting up the classpath.

Wait for the application to finish starting before testing. The commands below use `curl` in Bash; in PowerShell, invoke `curl.exe` to avoid alias confusion. The JSON responses below are formatted with whitespace for readability; key order is not a contract.

Reading the `ops` group unauthenticated:

```shell
curl -s -i http://localhost:8080/actuator/health/ops
```

The HTTP status code is **200**, JSON body:

```json
{"status":"DEGRADED"}
```

Reading the same group with a user lacking the operator role:

```shell
curl -s -i -u viewer:viewer-pass http://localhost:8080/actuator/health/ops
```

The HTTP status code is still **200**, JSON body still contains only:

```json
{"status":"DEGRADED"}
```

Reading with a user having the `OPS` role:

```shell
curl -s -i -u operator:operator-pass http://localhost:8080/actuator/health/ops
```

The HTTP status code is **200**; JSON includes components and diagnostic data:

```json
{
  "status": "DEGRADED",
  "components": {
    "catalog": {
      "status": "DEGRADED",
      "details": {
        "mode": "simulated"
      }
    },
    "ping": {
      "status": "UP"
    }
  }
}
```

Finally, reading the `traffic` group:

```shell
curl -s -i http://localhost:8080/actuator/health/traffic
```

The HTTP status code is **503**, JSON:

```json
{"status":"DEGRADED"}
```

Even when sending the `operator` account to `traffic`, that group still hides components and details because both policies are `never`.

To print only the HTTP status code in Bash:

```shell
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/actuator/health/ops
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/actuator/health/traffic
```

Exact stdout of the two commands when the application is running with the configuration above:

```text
200
503
```

In PowerShell on Windows, use `curl.exe` and replace `/dev/null` with `NUL` for commands that print only the HTTP code.

### 8.5. Testing Real Failure and Unknown Cases

Stop the process with Ctrl+C, then re-run with:

```shell
java -jar target/health-group-demo-1.0.0.jar --demo.catalog-status=DOWN
```

Once startup finishes, both `ops` and `traffic` must report status `DOWN` and HTTP **503**. This verifies that `ops`'s custom table still preserves the mapping for severe failures.

Stop and re-run:

```shell
java -jar target/health-group-demo-1.0.0.jar --demo.catalog-status=UNKNOWN
```

Both groups must report status `UNKNOWN` and HTTP **503**, because both effective orders place `UNKNOWN` before `UP`. That is the example's policy, differing from the default where `UP` precedes `UNKNOWN`.

Verification matrix:

| Catalog status | Group | Caller | Group status | HTTP | components/details |
| --- | --- | --- | --- | --- | --- |
| `DEGRADED` | `ops` | Anonymous | `DEGRADED` | 200 | No |
| `DEGRADED` | `ops` | `viewer` | `DEGRADED` | 200 | No |
| `DEGRADED` | `ops` | `operator` | `DEGRADED` | 200 | Yes |
| `DEGRADED` | `traffic` | `operator` or anonymous | `DEGRADED` | 503 | No |
| `DOWN` | Both | Any permitted caller | `DOWN` | 503 | Per policy and role |
| `OUT_OF_SERVICE` | Both | Any permitted caller | `OUT_OF_SERVICE` | 503 | Per policy and role |
| `UNKNOWN` | Both | Any permitted caller | `UNKNOWN` | 503 | Per policy and role |
| `UP` | Both | Any permitted caller | `UP` | 200 | Per policy and role |

Use only the statuses defined for the experiment. An unfamiliar string like `CUSTOM_X` not present in the list may be ignored by the aggregator when paired with `ping=UP`; the HTTP mapping for `CUSTOM_X` will not be used either because the group status is not `CUSTOM_X`.

## 9. When Do You Need Group-Specific Beans?

Properties work well when the policy is a fixed priority list and mapping table. If you need a different algorithm, you can register a bean with a qualifier matching the group name.

The example below is an **alternative configuration** for the `ops` group's status policy, not a mandatory step of the experiment. If applied, place this class in the same `example` package; do not simultaneously expect the `ops.status` properties to remain the source of truth for the two components replaced by beans.

```java
package example;

import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.actuate.health.HttpCodeStatusMapper;
import org.springframework.boot.actuate.health.SimpleHttpCodeStatusMapper;
import org.springframework.boot.actuate.health.SimpleStatusAggregator;
import org.springframework.boot.actuate.health.StatusAggregator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OpsHealthPolicy {

    @Bean
    @Qualifier("ops")
    StatusAggregator opsStatusAggregator() {
        return new SimpleStatusAggregator(
                "DOWN", "OUT_OF_SERVICE", "DEGRADED", "UNKNOWN", "UP");
    }

    @Bean
    @Qualifier("ops")
    HttpCodeStatusMapper opsHttpCodeStatusMapper() {
        return new SimpleHttpCodeStatusMapper(Map.of(
                "DOWN", 503,
                "OUT_OF_SERVICE", 503,
                "DEGRADED", 200,
                "UNKNOWN", 503,
                "UP", 200));
    }
}
```

The two beans above intentionally use built-in implementations to show how policies are scoped by group. The constructor and aggregation method are described in the [SimpleStatusAggregator API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleStatusAggregator.html).

The qualifier name must match `ops`. Avoid accidentally registering an unscoped bean that alters the common policy. If writing a custom algorithm, define and test empty sets, unknown statuses, and multiple simultaneous failures.

## 10. Applying to Liveness and Readiness

Liveness and readiness are also health groups, so they can receive their own visibility, ordering, and mapping policies. However, preserve their operational meanings:

- Liveness reflects whether the process can continue running; an external service outage does not automatically mean the application needs a restart.
- Readiness reflects the ability to accept traffic under the application's contract.
- `OUT_OF_SERVICE` for readiness must be recognized by the aggregator and mapped to an appropriate failing HTTP code; avoid letting it fall back to 200 when replacing the mapping table.
- The `traffic` group name in the example does not automatically configure Kubernetes probes. The routing component must be explicitly pointed to the intended URL.

Example addition to the existing configuration when enabling built-in probes locally:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: [readinessState]
          show-components: never
          show-details: never
          status:
            order: [DOWN, OUT_OF_SERVICE, UNKNOWN, UP]
            http-mapping:
              down: 503
              out-of-service: 503
              unknown: 503
              up: 200
```

This is a dedicated policy for the `readiness` group; it does not alter `ApplicationAvailability` states. If you decide to add a dependency to readiness, determine whether that dependency is essential for serving requests and how the system handles widespread outages.

## 11. Common Mistakes and How to Isolate Them

| Symptom | Cause to check | How to handle |
| --- | --- | --- |
| Anonymous user can read status despite setting `roles` | `roles` only controls detail visibility; the URL is permitted | If the URL must be blocked, add a Spring Security rule |
| Authorized user still cannot see components | Effective `show-components` is `never`, wrong role, or authentication failed | Check both visibility settings and actual authorities |
| JSON lacks `details` even when authorized | Check adds no detail data, or policy hides it | Check the `Health` result and `show-details` |
| `DOWN` returns 200 | Custom HTTP map lacks `down`, or aggregated status is no longer `DOWN` | Check JSON first, then the effective mapping table |
| One component is `DOWN` yet group is `UP` | Custom list omitted `DOWN`, or component is not in the group | Check membership and the entire `status.order` |
| Adding `DEGRADED` mapping has no effect | That status did not participate or did not win aggregation | Declare the order and test with a concrete status set |
| Changing order leaves HTTP unchanged | Both statuses map to the same code | Also compare the `status` field in JSON |
| YAML changes yet behavior does not change | Wrong profile, higher-priority config source, or group bean overriding policy | Check effective configuration and qualifiers |
| Receiving 401/403 instead of a health response | Request blocked by security mechanism | Check authentication and matchers before investigating the aggregator |
| Startup error when declaring `include` | Wrong contributor ID or nonexistent contributor | Fix the ID; do not disable membership validation just to hide errors |

## 12. Check Your Understanding

1. Why does `show-details: never` not guarantee that component names are also hidden?
2. How will a group with `roles: [OPS]` and URL `permitAll()` respond to a user with role `VIEWER`?
3. What happens if the priority list only contains `[DEGRADED, UP]` while one component returns `DOWN` and another returns `UP`?
4. Why can a map containing only `degraded: 200` lose the desired HTTP 503 for `DOWN`?
5. If the `ops` group returns HTTP 200 with JSON `DEGRADED`, what must an alerting tool inspect?
6. Why must `OUT_OF_SERVICE` be re-tested after customizing the readiness policy?

Reference answers:

1. `show-components` can be configured independently and may still allow display.
2. The request reaches the group, but lacks authorization to view details; the HTTP status code still follows the group status.
3. With `SimpleStatusAggregator`, `DOWN` is not recognized in that list; `UP` may be selected.
4. A custom map replaces the default map; unmapped statuses fall back to 200.
5. It must read the JSON status per the agreed contract rather than looking only at HTTP 2xx.
6. To ensure the traffic-refusing status still wins aggregation and becomes an HTTP code that the probe treats as failure.
