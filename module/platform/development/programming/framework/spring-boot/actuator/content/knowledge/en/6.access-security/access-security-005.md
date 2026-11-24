# Configuring Endpoint Matchers and SecurityWebFilterChain in Reactive Applications

## 1. Objectives and Mental Model to Understand

A Spring WebFlux application can serve both business APIs and Actuator operational endpoints. These two groups usually have different policies: health checkers need to read `health` without logging in, while operators need separate permissions to read metrics.

In Spring Security, **authentication** answers “who is sending the request”; **authorization** answers “is that caller allowed to perform this action”. **A matcher** determines which requests belong to a policy. **A security filter chain (`SecurityWebFilterChain`)** contains the security steps applied to the selected requests.

After this lesson, you should be able to do three things:

- Select the right Actuator endpoints using `EndpointRequest` from the Reactive branch.
- Separate Actuator and API policies using two `SecurityWebFilterChain`s, with ordering and a fallback chain covering the rest.
- Verify the policies using WebTestClient and HTTP commands, even after changing Actuator paths.

Examples use **Java 21, Spring Boot 3.3.13, and Spring Security 6.3.x managed by Boot**. This is a standalone Maven project for learning the mechanics; you do not need to copy build configurations from another project. Use the exact 3.3 documentation when cross-referencing because package names and some properties can differ in newer Boot generations.

## 2. Choosing the Right API Stack for WebFlux

Reactive applications use `WebFilter` filters, not Servlet Filter chains. The corresponding pairs of types are:

| Role | Spring WebFlux in this article | Spring MVC/Servlet |
| --- | --- | --- |
| Security builder | `ServerHttpSecurity` | `HttpSecurity` |
| Security chain bean type | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Matcher type | `ServerWebExchangeMatcher` | `RequestMatcher` |
| Authorization rules | `authorizeExchange` | `authorizeHttpRequests` |
| Explicit config annotation | `@EnableWebFluxSecurity` | `@EnableWebSecurity` |

In Boot 3.3, the right import for Reactive Actuator is:

```java
import org.springframework.boot.actuate.autoconfigure.security.reactive.EndpointRequest;
```

The Servlet and Reactive `EndpointRequest` classes share the same simple name. Importing the `.servlet` branch by mistake produces the wrong matcher type even though method names look similar.

The sample project uses `spring-boot-starter-webflux`, `spring-boot-starter-actuator`, and `spring-boot-starter-security`. Do not add `spring-boot-starter-web` to the example: when both web starters are present, you must verify which model the application actually runs under. The `spring.main.web-application-type: reactive` property below makes the lab's choice explicit. See [Boot 3.3 WebFlux configuration](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html#web.security.spring-webflux).

## 3. Two Matching Layers: Chain Selection First, Authorization Second

Read the configuration in this order:

```text
HTTP Request
    |
    +-- Evaluate SecurityWebFilterChains by ascending @Order
    |       |
    |       +-- first matching securityMatcher -> select exactly one chain
    |
    +-- Inside the selected chain:
            authenticate if credentials are present
            check relevant filters, such as CSRF
            apply matching authorizeExchange rules
            permit or deny
```

### 3.1. securityMatcher Defines the Scope of the Entire Chain

`securityMatcher(EndpointRequest.toAnyEndpoint())` scopes the chain to the Actuator endpoints recognized by the matcher. It does not by itself require login or grant roles.

The `@Order(1)` chain is evaluated before `@Order(2)`. Once a chain has been selected, the request does not continue into a later chain to look for a more permissive rule. Therefore, an account denied inside the Actuator chain will not “fall through” to the API chain to try again.

### 3.2. authorizeExchange Decides Permissions Inside the Chain

Specific rules must come before `anyExchange()`. In this article's Actuator chain:

1. Matching the `health` endpoint permits access without login.
2. Other requests **already claimed by the Actuator chain** must have the `OPS` role.

`anyExchange()` here only covers the remainder of the selected chain, not every URL in the entire application.

The second chain does not declare `securityMatcher`, so it claims all remaining requests. It permits `GET /api/ping`, while other requests must be authenticated. This is the chain covering the rest, commonly called the **fallback**.

If you put the catch-all chain first, the Actuator chain never gets a chance to be selected. If you only declare a chain with a narrow matcher and omit the fallback chain, you can leave out-of-scope URLs unprotected by any Spring Security chain. Do not rely on assuming Boot will automatically create a supplemental policy once you have declared a custom chain.

Ordered single-chain selection is described in [Spring Security Multiple Chains Support](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html#_multiple_chains_support); the example below pins dependencies to Boot 3.3 to avoid accidentally using newer APIs.

## 4. EndpointRequest Versus Hardcoded Paths

`EndpointRequest` uses Actuator endpoint location metadata, fitting when you want policies tied to **endpoints**, rather than a hardcoded URL string.

| How to build the matcher | Meaning |
| --- | --- |
| `EndpointRequest.toAnyEndpoint()` | Actuator endpoints, including the discovery links endpoint at the base path |
| `EndpointRequest.to(HealthEndpoint.class)` | The `health` endpoint |
| `EndpointRequest.to("health", "info")` | Select by endpoint ID, not URL |
| `EndpointRequest.toLinks()` | Only the discovery links endpoint |
| `EndpointRequest.toAnyEndpoint().excluding(HealthEndpoint.class)` | Exclude `health` from this matcher's scope |
| `EndpointRequest.toAnyEndpoint().excludingLinks()` | Exclude the discovery links endpoint from this matcher's scope |

`to("health")` takes the ID `health`, not `"/actuator/health"`. Do not use an endpoint ID as proof that the endpoint is enabled or exposed over HTTP: that is separate configuration.

`pathMatchers("/actuator/**")` can be appropriate when intentionally protecting a URL namespace. However, if you change the base path to `/manage`, that fixed rule does not automatically move to the new URL. `EndpointRequest` lets policies follow endpoint mappings. Nor is it synonymous with “every URL prefixed with /actuator”: a non-existent URL under that prefix may be claimed by another chain.

A common trap is excluding `health` from `securityMatcher` to try making it public. **Excluding from a matcher is not granting permission**: `health` will be evaluated by the next chain; if that chain requires login, it remains protected. The main example keeps `health` inside the Actuator scope and grants `permitAll()` right inside that chain.

An endpoint matcher should also not be assumed to match only a single leaf URL. When making `health` public, account for subpaths/health groups that the application actually exposes. If policy only permits a very specific probe path, design a detailed matcher and also test subpaths that must stay restricted.

Method definitions are in [Boot 3.3 Reactive EndpointRequest Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/reactive/EndpointRequest.html).

## 5. Complete Example: Public Health, Metrics Requiring OPS

Policy to achieve:

| Resource | Unauthenticated | reader account, USER role | ops account, OPS role |
| --- | --- | --- | --- |
| `GET /actuator/health` | Readable | Readable | Readable |
| `GET /actuator/info` | 401 | 403 | Readable |
| `GET /actuator/metrics` | 401 | 403 | Readable |
| `GET /actuator` | 401 | 403 | Links readable |
| `GET /api/ping` | Readable | Readable | Readable |
| `GET /api/private` | 401 | Readable | Readable |

Columns with accounts assume correct passwords. Sending wrong credentials can be rejected by the authentication filter even on `permitAll()` resources; `permitAll()` does not disable authentication filters.

### 5.1. Project Structure

```text
reactive-actuator-security/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/
    │   │   ├── DemoApplication.java
    │   │   └── SecurityConfig.java
    │   └── resources/application.yml
    └── test/java/example/
        ├── SecurityPolicyTest.java
        └── RemappedEndpointTest.java
```

### 5.2. pom.xml

Use Maven 3.6.3+ and JDK 21. Boot manages Spring versions; do not manually assign a different Spring Security version for this project.

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
    <artifactId>reactive-actuator-security</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

### 5.3. src/main/resources/application.yml

```yaml
spring:
  main:
    web-application-type: reactive

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: never
      show-components: never
```

The configuration above only exposes `health`, `info`, `metrics` over HTTP. **Exposing an endpoint (exposure) is different from granting access**: the include list enables HTTP accessibility; the security chains decide who can access them. By default, only `health` is exposed over HTTP.

`show-details: never` and `show-components: never` keep the health response at an aggregate level. Making an endpoint public does not mean making internal structure public. If you change these two properties, re-evaluate what data unauthenticated callers will receive. See [Boot 3.3 Exposing Endpoints and Health Information](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### 5.4. src/main/java/example/DemoApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @RestController
    static class ApiController {
        @GetMapping("/api/ping")
        Mono<String> ping() {
            return Mono.just("pong");
        }

        @GetMapping("/api/private")
        Mono<String> privateMessage() {
            return Mono.just("private-ok");
        }
    }
}
```

Two small APIs provide proof that the fallback chain is working: one public API, one API requiring login. `Mono.just` here only creates in-memory data; there are no blocking calls or database queries.

### 5.5. src/main/java/example/SecurityConfig.java

```java
package example;

import org.springframework.boot.actuate.autoconfigure.security.reactive.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {
    @Bean
    @Order(1)
    SecurityWebFilterChain actuatorChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeExchange(exchanges -> exchanges
                        .matchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
                        .anyExchange().hasRole("OPS"))
                .httpBasic(withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain applicationChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/ping").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var ops = User.withUsername("ops")
                .password(encoder.encode("ops-pass"))
                .roles("OPS")
                .build();
        var reader = User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(ops, reader);
    }
}
```

Read this configuration by each responsibility:

- `actuatorChain` only claims Actuator requests. `health` is public; metrics, info, and discovery links require `OPS`.
- `applicationChain` claims the remaining requests. The `GET /api/ping` rule does not grant access to other HTTP methods on the same path.
- `httpBasic(withDefaults())` is configured on **both chains** because both scopes need to handle Basic credentials. An authentication mechanism in one chain does not automatically appear in another chain.
- `MapReactiveUserDetailsService` provides two in-memory users for the lab. PasswordEncoder generates hashed passwords; the hashed strings can differ on every startup due to random salts.
- `.roles("OPS")` creates the authority `ROLE_OPS`; `.hasRole("OPS")` checks that authority. If using `hasAuthority`, the corresponding value is `"ROLE_OPS"`.

Usernames and passwords in code are only for running the example on a learning machine. When applying to a real system, use appropriate identity sources and secret management; Basic must go over HTTPS to protect credentials in transit. Base64 encoding of Basic is not security encryption.

The configuration does not disable CSRF and does not enable form login. The main tests use GET, so no CSRF token is needed. Declaring custom security chains replaces the default access policy with an application-owned policy; it does not mean every default authentication service automatically disappears. Here, the `MapReactiveUserDetailsService` bean makes the user source explicit.

## 6. Run the Application and Verify Over HTTP

In the directory containing `pom.xml`:

```bash
mvn clean test
mvn spring-boot:run
```

Keep the application process running, then open a second terminal. Or package and run the JAR:

```bash
mvn package
java -jar target/reactive-actuator-security-1.0.0.jar
```

Run only one approach at a time to avoid port 8080 conflicts. This is a Spring program with dependencies, so use Maven to compile and resolve the classpath; invoking `javac DemoApplication.java` alone will not download the libraries.

### 6.1. Observing Simple Responses

The commands below use Bash. If running PowerShell on Windows, use `curl.exe` to avoid aliases; for the commands discarding response bodies in the next section, change `/dev/null` to `NUL`.

```bash
curl -s http://localhost:8080/actuator/health
```

In the sample project, when the application status is UP, the JSON content is:

```json
{"status":"UP"}
```

This is the HTTP response body, not stdout from the `main` method. Do not assume a real system is always UP: health status depends on the checked components.

Public API:

```bash
curl -s http://localhost:8080/api/ping
```

```text
pong
```

API requiring login:

```bash
curl -s -u reader:reader-pass http://localhost:8080/api/private
```

```text
private-ok
```

`curl` does not add trailing newlines to these bodies; the code fences only present the content.

### 6.2. Checking Status Codes

Run the six commands below in order:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/actuator/metrics
curl -s -o /dev/null -w "%{http_code}\n" -u reader:reader-pass http://localhost:8080/actuator/metrics
curl -s -o /dev/null -w "%{http_code}\n" -u ops:ops-pass http://localhost:8080/actuator/metrics
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/private
curl -s -o /dev/null -w "%{http_code}\n" -u reader:reader-pass http://localhost:8080/api/private
curl -s -o /dev/null -w "%{http_code}\n" -u ops:ops-pass http://localhost:8080/actuator
```

Expected results:

```text
401
403
200
401
200
200
```

The first three lines distinguish authentication and authorization:

1. No valid identity: 401, authentication required.
2. Valid identity but missing role: 403, permission denied.
3. Has `OPS` role: 200.

If you see a 302 redirect, check whether another chain enables form login or custom error handling exists. This sample uses HTTP Basic and does not enable form login.

The `/actuator/metrics` response contains a list of metric names; the exact list depends on timing and environment. Do not use a fixed list as a test assertion.

## 7. Integration Testing with WebTestClient

The following two files load the full WebFlux Spring Boot context using a MOCK environment: WebTestClient sends simulated HTTP requests in-process without opening a network port. Requests still pass through WebFilters, matchers, Basic authentication against the application's user source, and authorization; logged-in identities are not mocked.

### 7.1. src/test/java/example/SecurityPolicyTest.java

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class SecurityPolicyTest {
    @Autowired
    WebTestClient client;

    @Test
    void healthIsPublic() {
        client.get().uri("/actuator/health").exchange()
                .expectStatus().isOk()
                .expectBody().jsonPath("$.status").isEqualTo("UP");
    }

    @Test
    void metricsRequiresAuthentication() {
        client.get().uri("/actuator/metrics").exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCannotReadMetrics() {
        client.get().uri("/actuator/metrics")
                .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void opsCanReadMetrics() {
        client.get().uri("/actuator/metrics")
                .headers(headers -> headers.setBasicAuth("ops", "ops-pass"))
                .exchange().expectStatus().isOk()
                .expectBody().jsonPath("$.names").isArray();
    }

    @Test
    void discoveryLinksRequireOps() {
        client.get().uri("/actuator")
                .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
                .exchange().expectStatus().isForbidden();
        client.get().uri("/actuator")
                .headers(headers -> headers.setBasicAuth("ops", "ops-pass"))
                .exchange().expectStatus().isOk();
    }

    @Test
    void fallbackProtectsApplication() {
        client.get().uri("/api/ping").exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
        client.get().uri("/api/private").exchange()
                .expectStatus().isUnauthorized();
        client.get().uri("/api/private")
                .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("private-ok");
    }

    @Test
    void unexposedEndpointIsStillAbsentAfterAuthentication() {
        client.get().uri("/actuator/env")
                .headers(headers -> headers.setBasicAuth("ops", "ops-pass"))
                .exchange().expectStatus().isNotFound();
    }

    @Test
    void wrongPasswordFailsAuthentication() {
        client.get().uri("/actuator/metrics")
                .headers(headers -> headers.setBasicAuth("ops", "wrong-pass"))
                .exchange().expectStatus().isUnauthorized();
    }
}
```

`readerCannotReadMetrics` is an important test: if Actuator accidentally falls into a chain requiring only `authenticated()`, user `reader` would receive 200 and the test would fail.

The `unexposedEndpointIsStillAbsentAfterAuthentication` test uses a valid account to observe 404 for `env`, because that endpoint is not exposed in the sample configuration. If testing this URL unauthenticated, the fallback chain may return 401 before the application reaches handler lookup. Therefore, do not conclude an endpoint exists from a 401 code alone, nor conclude 403 is always a missing role.

### 7.2. src/test/java/example/RemappedEndpointTest.java

The second test changes the base path and remaps health specifically without editing `SecurityConfig`.

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK,
        properties = {
                "management.endpoints.web.base-path=/manage",
                "management.endpoints.web.path-mapping.health=live"
        })
@AutoConfigureWebTestClient
class RemappedEndpointTest {
    @Autowired
    WebTestClient client;

    @Test
    void healthMatcherFollowsEndpointMapping() {
        client.get().uri("/manage/live").exchange()
                .expectStatus().isOk();
        client.get().uri("/actuator/health")
                .headers(headers -> headers.setBasicAuth("ops", "ops-pass"))
                .exchange().expectStatus().isNotFound();
    }

    @Test
    void roleRuleAlsoFollowsNewBasePath() {
        client.get().uri("/manage/metrics")
                .headers(headers -> headers.setBasicAuth("reader", "reader-pass"))
                .exchange().expectStatus().isForbidden();
        client.get().uri("/manage/metrics")
                .headers(headers -> headers.setBasicAuth("ops", "ops-pass"))
                .exchange().expectStatus().isOk();
    }
}
```

Re-run:

```bash
mvn test
```

The example suite has 10 test methods: 8 in `SecurityPolicyTest`, 2 in `RemappedEndpointTest`. Success means zero failures/errors; there is no need to match the entire startup log.

If you only invoke controllers directly or use a client that bypasses Spring Security chains, you may see 200 and mistakenly think the policy is right. In-process tests here verify application configuration, endpoint mappings, and security chains. The curl commands in section 6 supplement this by testing the running HTTP server; MOCK tests do not prove port binding, proxies, or TLS.

## 8. Changing Paths and Boundaries to Maintain

### 8.1. Changing Actuator Paths

For manual testing, keep the other properties and add **inside the existing `management.endpoints.web` block**, without creating a duplicate `management` key:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
      path-mapping:
        health: live
      exposure:
        include: health,info,metrics
```

Then use `/manage/live`, `/manage/metrics`, and `/manage`. Endpoint-based matcher policies must still hold: health public, metrics requiring OPS. For authenticated callers, the old `/actuator/health` URL no longer has a handler and returns 404 in this example.

If the application has `spring.webflux.base-path`, a separate management port, a path-rewriting proxy, or a separate management context, test the actual URLs and actual ports in that configuration. The main example uses a single port and does not automatically prove every deployment setup. Separating the management port also does not replace authentication, authorization, or network access control.

### 8.2. Do Not Confuse Public Health With Public Health Data

A matcher based on `HealthEndpoint` can cover the endpoint's subpaths as well. When adding health groups or exposing individual component statuses, check the response of each such URL as an unauthenticated caller. The two detail-hiding properties in the sample are an intentional choice, not an effect of `permitAll()`.

The discovery links endpoint at `/actuator` also has its own policy in the sample: it belongs to `toAnyEndpoint()` and requires OPS. Making health public does not imply making the links page public.

### 8.3. Access Permissions Do Not Replace CSRF

For state-changing requests such as a POST to the `loggers` endpoint, having the right account and role can still return 403 when missing a CSRF token. Distinguish CSRF errors from authorization errors before changing roles.

The sample keeps default CSRF. Do not disable CSRF for the entire application just to make one POST command work. Adjusting CSRF must be based on the authentication mechanism, how browsers send credentials, and chain scope; using HTTP Basic does not automatically eliminate all CSRF risks. See [CSRF in WebFlux environments](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html).

### 8.4. Keep the Reactive Thread Non-Blocking

`ServerWebExchangeMatcher` returns results in a Reactive manner. If you write a custom matcher or authentication service, do not call `block()`, sleep the thread, or run synchronous JDBC queries directly on the request thread. The built-in matchers are sufficient for this lesson; there is no need to add manual URL-checking algorithms or manually decode Basic headers.

## 9. Common Mistakes and Troubleshooting Guide

| Symptom | What to check |
| --- | --- |
| Does not compile when passing EndpointRequest | Check whether the import is `.security.reactive.EndpointRequest`; whether the builder is `ServerHttpSecurity` |
| health unexpectedly requires login | Check chain order, permitAll rule, and whether health was excluded from securityMatcher |
| reader can read metrics | Check whether a catch-all chain sits before the Actuator chain; whether the rule only uses authenticated |
| OPS still gets 403 on GET metrics | Check actual authorities; hasRole("OPS") needs ROLE_OPS, not authority OPS |
| Permissions break only after changing base-path | Look for hardcoded path matchers; check path-remapping tests |
| Non-Actuator APIs lose protection | Check whether a fallback chain exists and has a final catch-all policy |
| Metrics not visible despite valid login | Check Actuator dependency, enablement, exposure, and actual URL before editing permissions |
| POST gets 403 while GET works | Check CSRF, HTTP method, and permissions for that specific operation |
| A permitAll resource still returns 401 | Try omitting invalid login headers; authentication filters still run |
| /actuator/env returns 401 when hidden from exposure | The security chain may block before handler lookup; test with a valid identity to check 404 |

When diagnosing, trace a specific request through three questions: **which chain is selected, which identity is authenticated, and which authorization rule applies**. Only then check the handler and response body. You can enable security logging in a learning environment to observe, but never log credentials or tokens.

## 10. Self-Check Practice Exercises

1. Run both test classes. Explain why `reader` can read `/api/private` but cannot read `/actuator/metrics`.
2. Temporarily swap the order of the two chains in the lab project. Predict what happens to health and metrics read access, then confirm with tests. Restore the order after testing.
3. Change the base path and health mapping as in section 8. Prove that authorization policies hold without editing URL names in `SecurityConfig`.
4. Try excluding health from the Actuator chain's matcher. Explain which chain claims it and why excluding from a matcher is not equivalent to permitAll.
5. Try accessing an unexposed Actuator URL anonymously and then with a valid account. Explain why the two status codes can differ.

You understand the configuration properly when you can predict each request's path through **chain selection → authentication → authorization**, and prove your prediction using HTTP tests on the actual configuration.
