# Using EndpointRequest to Match Endpoints in Servlet Applications

## 1. The Problem: Protecting Actuator Functionality or a URL String?

Suppose an application needs to allow health-checking tools to read health, while only operators may view other management endpoints.

An easy idea that comes to mind is writing a rule for `/actuator/**`. However, that rule matches a URL prefix. If the Actuator path changes to `/manage`, if health is mapped to a different name, or if the application uses a separate management port, keeping raw path strings scattered across security code becomes harder to control.

`EndpointRequest` helps express intent in terms of **Actuator endpoints**: health, info, or all mapped endpoints, instead of manually assembling URLs from memory.

This article uses **Spring Boot 3.3.x, Spring MVC, and Spring Security 6.x**. The hands-on lab pins Spring Boot 3.3.13 with Java 21; the APIs used belong to the Servlet branch. Do not apply this code verbatim to WebFlux.

After this lesson, you should be able to explain three things:

- Which set of requests a matcher recognizes.
- Whether the matcher is placed to select an entire security chain or only an authorization rule within a chain.
- Where unmatched requests go.

## 2. What Is EndpointRequest and What Does It Not Do Automatically?

In a Servlet application, the right import is:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
```

This class provides factory methods for creating `RequestMatcher` objects targeting HTTP locations of Actuator endpoints. A matcher answers the question: **does the current request belong to the set I recognize?**

It does not yet answer what permissions the caller has. Permissions come from rules like `permitAll()`, `authenticated()`, `hasRole(...)`, or `denyAll()` paired with the matcher. [EndpointRequest 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html)

Separate the responsibilities:

| Component | Responsibility |
| --- | --- |
| Endpoint enable/exposure config | Determines which features are provided over HTTP |
| EndpointRequest | Recognizes requests by endpoint mapping |
| SecurityFilterChain | Defines the filter chain and applied policies |
| Authorization rules | Decides whether a matched request may proceed |
| Authentication mechanism | Verifies identity and supplies caller authorities |

`EndpointRequest` does not automatically enable endpoints, add dependencies, expose endpoints, create accounts, filter IPs, or open network ports. Nor is it an automatic scanner for all business controllers.

For example, putting `EndpointRequest.to("info")` in configuration does not mean `info` is already exposed over HTTP. You still must configure exposure separately. [Spring Boot 3.3: Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing)

## 3. Choosing a Matcher by Intent

The short Java snippets in this section are illustrative expressions/configuration fragments; the full program is in the hands-on section.

### 3.1. Matching by Endpoint ID

```java
EndpointRequest.to("health")
EndpointRequest.to("health", "info")
```

The strings passed in are **endpoint IDs**, not URLs and not Java method names.

For health:

- Right: `"health"`.
- Wrong intent: `"/actuator/health"`.
- Wrong intent after renaming the path: using the new path name as the ID.

If health is mapped to `/manage/ready`, the ID is still `health`.

### 3.2. Matching by Endpoint Class

```java
EndpointRequest.to(HealthEndpoint.class)
EndpointRequest.to(HealthEndpoint.class, InfoEndpoint.class)
```

The corresponding classes need to be imported:

```java
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.boot.actuate.info.InfoEndpoint;
```

This approach lets the compiler check class names. It still targets the endpoint identifier and does not require the HTTP path to match the class name.

The class passed in must be an appropriate Actuator endpoint class. Do not pass a regular `@RestController` class expecting it to become an Actuator endpoint.

### 3.3. Matching All Endpoints and Discovery

```java
EndpointRequest.toAnyEndpoint()
```

This matcher recognizes Actuator endpoint paths in the current mappings and also includes the discovery path at the base path. With base path `/manage`, discovery is typically at `/manage`.

Discovery is what provides links to endpoints. It should not be overlooked just because security rules protect sub-URLs.

### 3.4. Matching Discovery Alone

```java
EndpointRequest.toLinks()
```

Use this when you want a separate policy for discovery, such as disallowing access to the links page while still letting tools call an authorized endpoint directly.

If you change discovery configuration or base path, you must re-verify what endpoints are actually provided. A matcher matching a path does not guarantee there is always a resource at that path returning success.

### 3.5. Excluding Endpoints or Discovery From a Matcher

```java
EndpointRequest.toAnyEndpoint().excluding(HealthEndpoint.class)
EndpointRequest.toAnyEndpoint().excluding("health", "info")
EndpointRequest.toAnyEndpoint().excludingLinks()
```

`excluding(...)` changes the set of requests the matcher recognizes. `excludingLinks()` excludes the discovery portion. These methods do not remove endpoints from the application and do not mean permitting or forbidding callers.

In the 3.3 API, exclusion methods return a new matcher. So you must use the return value, for example:

```java
var allEndpoints = EndpointRequest.toAnyEndpoint();
var endpointsWithoutHealth = allEndpoints.excluding(HealthEndpoint.class);
```

Calling `allEndpoints.excluding(...)` and discarding the result does not mutate the `allEndpoints` variable. [EndpointRequestMatcher 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.EndpointRequestMatcher.html)

## 4. Understanding the Scope of Matched Paths

### 4.1. Matching an Endpoint Is Not Just Matching One Root URL

An endpoint can have subpaths. For example, health can have groups like liveness; metrics can have a path for a metric name.

When applying `EndpointRequest.to(HealthEndpoint.class)`, understand that the policy targets health and the subpaths covered by the matcher. If you set `permitAll()`, do not assume only the exact `/manage/health` string is public.

The hands-on lab will enable health groups and test a subpath to observe this. If production wants to permit a narrower group or operation, add corresponding matchers.

### 4.2. toAnyEndpoint Is Not a /manage/** Pattern

The matcher relies on endpoint mappings. It does not treat every arbitrary path under the management prefix as an existing endpoint.

For example, when metrics is not exposed, do not infer that `/manage/metrics` falls under the management policy just because it has the `/manage` prefix. A request not belonging to the recognized endpoint set continues to be evaluated by the remaining chains/rules.

This also explains why there must be a policy for the rest of the application. `PathMappedEndpoints` provides paths by ID and may return nothing for an ID not in the mapped set. [PathMappedEndpoints 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/PathMappedEndpoints.html)

### 4.3. An Endpoint Matcher Does Not Automatically Restrict HTTP Methods

A matcher recognizing an endpoint is not a “GET only” rule. For endpoints with both read operations and state-changing operations, a broad policy can apply to both.

If you only want to grant access to GET on an endpoint, you can combine the endpoint matcher with a method condition. Illustrative example, requiring Spring Security imports:

```java
RequestMatcher readOnlyLoggers = new AndRequestMatcher(
    EndpointRequest.to("loggers"),
    request -> "GET".equals(request.getMethod())
);
```

Here `RequestMatcher` and `AndRequestMatcher` belong to `org.springframework.security.web.util.matcher`. The condition restricts only to GET; if you want to allow HEAD or other methods, decide explicitly.

This is only the matcher to select requests. Afterward you still must pair permissions and a policy for unmatched requests. For write operations, checks like CSRF remain a separate layer; endpoint matching does not disable them.

## 5. Two Places to Put a Matcher in Security Configuration

### 5.1. securityMatcher Selects the Scope of the Entire Chain

```java
http.securityMatcher(EndpointRequest.toAnyEndpoint());
```

This line says: the chain being built only handles requests matching the Actuator set recognized by the matcher.

An unmatched business API request will not be handled by that chain. It needs another chain or a clearly defined infrastructure policy.

### 5.2. requestMatchers Selects Authorization Rules Inside the Chain

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
    .anyRequest().hasRole("OPS")
);
```

In this snippet, the health matcher selects the rule for health **among requests that have entered the chain**.

If the chain is narrowed by `securityMatcher(EndpointRequest.toAnyEndpoint())`, `anyRequest()` here means the remaining requests within the management chain's scope. It does not automatically protect all application APIs.

If the chain has no narrowing matcher, the initial scope is broader; the same `anyRequest()` will have a different effect. That is why you must read the whole chain configuration, not just a single rule line. [HttpSecurity 6.3 API](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/config/annotation/web/builders/HttpSecurity.html)

### 5.3. Chain Order and Rule Order Are Two Layers

```text
HTTP Request
  → evaluate chains in order
  → pick the first chain with a matching matcher
  → evaluate authorization rules in that chain in order
  → permit or deny
```

All chains are not combined to produce one final permission set. A catch-all chain placed first can prevent a specialized Actuator chain from ever being selected. [Spring Security: Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)

Inside a chain, placing specific health rules before the catch-all rule clearly expresses the exception.

## 6. Complete Example: Two Chains, Two Permission Groups

### 6.1. Lab Policy

The application uses base path `/manage`, exposing health and info:

| Path/request group | Policy |
| --- | --- |
| Health and configured subpaths | Permit without login |
| Discovery and other Actuator endpoints | Require OPS role |
| Remaining application requests | Require authenticated user |

There are two lab accounts:

| Account | Lab password | Role |
| --- | --- | --- |
| reader | reader-lab-only | USER |
| operator | operator-lab-only | OPS |

These credentials are for local hands-on practice only. The article uses HTTP on loopback; over a real network you need TLS and proper identity/secret management.

### 6.2. Create a Standalone Project

Use Java 21 and Maven 3.9+, with structure:

```text
endpoint-request-lab/
├── pom.xml
└── src/main/
    ├── java/lab/EndpointMatcherApplication.java
    ├── java/lab/EndpointSecurityConfig.java
    └── resources/application.yml
```

Contents of `pom.xml`:

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
    <groupId>lab</groupId>
    <artifactId>endpoint-request-lab</artifactId>
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

Maven resolves the matching Spring Security version from Boot's dependency management; do not pin a different Security version separately in the lab.

Contents of `src/main/java/lab/EndpointMatcherApplication.java`:

```java
package lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class EndpointMatcherApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointMatcherApplication.class, args);
    }

    @GetMapping("/api/ping")
    public String ping() {
        return "api-pong\n";
    }
}
```

Contents of `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include:
          - health
          - info
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
      show-components: never
```

Enable probes so there is a health subpath to use in the tests. Wait for the application to finish starting before checking readiness or overall status.

### 6.3. Servlet Security Configuration

Contents of `src/main/java/lab/EndpointSecurityConfig.java`:

```java
package lab;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class EndpointSecurityConfig {
    @Bean
    @Order(1)
    SecurityFilterChain managementEndpoints(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
            .requestMatchers(EndpointRequest.toLinks()).hasRole("OPS")
            .anyRequest().hasRole("OPS")
        );
        http.httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain remainingRequests(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
        http.httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-lab-only"))
            .roles("USER")
            .build();

        var operator = User.withUsername("operator")
            .password(encoder.encode("operator-lab-only"))
            .roles("OPS")
            .build();

        return new InMemoryUserDetailsManager(reader, operator);
    }
}
```

Explanation across the two layers:

1. `@Order(1)` is evaluated first. The chain's matcher recognizes Actuator, including discovery.
2. Inside that chain, health is permitted first; discovery and the rest of management require OPS.
3. Business APIs do not match the first chain, so they reach `@Order(2)`.
4. The second chain has no narrowed scope and requires authentication for the remainder.
5. Both chains declare HTTP Basic so tests do not depend on a form login page.

The `toLinks()` line currently has the same permission as `anyRequest()`, but is written explicitly to show where to place an independent discovery policy.

`roles("OPS")` creates the authority by convention `ROLE_OPS`; use `hasRole("OPS")`, do not prepend `ROLE_` again.

When declaring custom chain beans, Boot's default security configuration backs off. The article therefore declares both the Actuator paths and the remainder, rather than waiting for Boot to fill in a missing chain. [ManagementWebSecurityAutoConfiguration 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/ManagementWebSecurityAutoConfiguration.html)

### 6.4. Package and Start

Run at the project root directory:

```bash
mvn clean package
java -jar target/endpoint-request-lab-1.0.0.jar
```

This is a Spring Boot program with dependencies, so use Maven to compile/package instead of standalone `javac` on one file. The first run needs to download dependencies from the Maven repository.

Keep the JVM running in the first terminal. Ensure no other application uses port 8080. Subsequent verification commands use Bash and curl; in PowerShell you can invoke `curl.exe` with appropriate syntax.

## 7. Verifying the Request Set and Permissions

### 7.1. Helper Function Printing Only HTTP Status

In the second terminal, define the function:

```bash
http_status() {
  curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
    -H 'Accept: application/json' "$@"
}
```

The function preserves passed arguments, discards the body, and prints status. It does not follow redirects and does not send credentials unless `-u` is provided.

### 7.2. Testing health, info, discovery, and Business API

```bash
http_status http://127.0.0.1:8080/manage/health

http_status http://127.0.0.1:8080/manage/health/liveness

http_status http://127.0.0.1:8080/manage/info

http_status -u reader:reader-lab-only \
  http://127.0.0.1:8080/manage/info

http_status -u operator:operator-lab-only \
  http://127.0.0.1:8080/manage/info

http_status -u reader:reader-lab-only \
  http://127.0.0.1:8080/manage

http_status -u operator:operator-lab-only \
  http://127.0.0.1:8080/manage

http_status http://127.0.0.1:8080/api/ping

http_status -u reader:reader-lab-only \
  http://127.0.0.1:8080/api/ping
```

With a healthy application, valid credentials, and startup complete, expected stdout in exact order:

```text
200
200
401
403
200
403
200
401
200
```

Meaning of each group:

- The two health requests show the health matcher covers both the root path and the liveness group path.
- Anonymous info receives 401; reader authenticates but lacks OPS and receives 403; operator receives 200.
- Discovery is not forgotten: reader receives 403, operator receives 200.
- Business API is protected by the second chain: anonymous receives 401, valid reader receives 200.

You can check the API body with:

```bash
curl --noproxy '*' -sS -u reader:reader-lab-only \
  http://127.0.0.1:8080/api/ping
```

Stdout:

```text
api-pong
```

Health can return a different code if the application is unhealthy; when a connection error occurs and curl prints `000`, that is not an HTTP status returned by the endpoint. Check the process, port, and curl errors before drawing conclusions about the matcher.

### 7.3. Adding an Exposed Endpoint Without Editing the Matcher

In the initial configuration, metrics is not yet in include. With a valid account, try:

```bash
http_status -u reader:reader-lab-only \
  http://127.0.0.1:8080/manage/metrics
```

Expected stdout:

```text
404
```

The request is not recognized by the Actuator chain as an exposed endpoint; the remaining chain still authenticates reader, and then the application has no matching HTTP mapping.

Stop the JVM, then restart with the new exposure list:

```bash
java -jar target/endpoint-request-lab-1.0.0.jar \
  --management.endpoints.web.exposure.include=health,info,metrics
```

Do not edit Java. Wait for the application to be ready and try:

```bash
http_status -u reader:reader-lab-only \
  http://127.0.0.1:8080/manage/metrics

http_status -u operator:operator-lab-only \
  http://127.0.0.1:8080/manage/metrics
```

Expected stdout:

```text
403
200
```

Metrics is now exposed, so it falls into the recognized management set. The first chain's OPS rule applies to it without having to add a metrics URL into security code.

This is not a reason to open `include: "*"` indiscriminately. Choosing which endpoints to provide and choosing who may call them remain two separate decisions.

## 8. Verifying When Changing Base Path and Endpoint Path Mapping

Stop the JVM from the previous section. This time restart with a different base path and map health to `ready`:

```bash
java -jar target/endpoint-request-lab-1.0.0.jar \
  --management.endpoints.web.base-path=/ops \
  --management.endpoints.web.path-mapping.health=ready
```

Each startup only uses arguments written in the current command; CLI arguments from an earlier process do not persist automatically. The YAML file still exposes health and info.

HTTP path structure in this run:

| Feature | New path | ID used in matcher |
| --- | --- | --- |
| Health | /ops/ready | health |
| Liveness group | /ops/ready/liveness | Still belongs to health |
| Info | /ops/info | info |
| Discovery | /ops | Use toLinks or toAnyEndpoint |

Changing base path/path mapping is a Spring Boot configuration contract; code using IDs/classes does not have to change for the new path names. [Spring Boot 3.3: Monitoring over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)

Reuse the `http_status` function:

```bash
http_status http://127.0.0.1:8080/ops/ready

http_status http://127.0.0.1:8080/ops/ready/liveness

http_status -u reader:reader-lab-only \
  http://127.0.0.1:8080/ops/info

http_status -u operator:operator-lab-only \
  http://127.0.0.1:8080/ops/info

http_status -u operator:operator-lab-only \
  http://127.0.0.1:8080/ops

http_status -u operator:operator-lab-only \
  http://127.0.0.1:8080/manage/health
```

Expected stdout, when the application is healthy:

```text
200
200
403
200
200
404
```

The last command uses valid credentials to observe that the old path is no longer mapped. If calling the old path anonymously, the fallback chain may return 401 before routing; 401 does not prove the old path is still the health endpoint.

Do not change the matcher to `EndpointRequest.to("ready")`: `ready` is the mapped path name, not the endpoint ID.

## 9. Watch Out for excluding and Gaps Between Chains

Suppose the first chain's scope is changed to:

```java
http.securityMatcher(
    EndpointRequest.toAnyEndpoint().excluding("info")
);
```

Info is still exposed. This change only keeps it from entering that management chain.

With the lab's second chain requiring `authenticated()`, reader can read info because the request falls into the general authenticated policy, no longer requiring OPS. If there is no other matching chain, the request can even end up outside the protection of declared Spring Security chains.

Similarly:

```java
http.securityMatcher(
    EndpointRequest.toAnyEndpoint().excludingLinks()
);
```

If you only change that, a `toLinks()` rule placed inside the first chain will never receive discovery: the outer scope excluded it first.

To forbid discovery in the lab configuration, the direct approach is to **keep discovery within the chain scope**, then change the authorization rule itself:

```java
.requestMatchers(EndpointRequest.toLinks()).denyAll()
```

This line replaces the existing rule, not a standalone configuration to append after `anyRequest()`.

Distinguish three actions:

| Intent | Appropriate configuration type |
| --- | --- |
| Do not provide an endpoint over HTTP | Exposure or endpoint enable/disable configuration |
| Disallow a group of callers from an endpoint | Authorization rule |
| Exclude an endpoint from a matcher's recognition set | excluding, then define which policy handles it next |

Do not use `excluding` as a synonym for `denyAll`.

## 10. Context Path, Management Port, and Servlet Scope

### 10.1. With a Context Path

If running on a shared port with `server.servlet.context-path=/training`, external URLs will include the context path, for example:

```text
http://127.0.0.1:8080/training/manage/health
```

The ID is still `health`. When using an endpoint matcher, do not manually prepend `/training` to the ID or class name.

You must distinguish the URL seen by callers from the path portion used within the Servlet application. If adding a proxy or changing the servlet path beyond the usual model, verify with real requests instead of guessing from a configuration string.

### 10.2. With a Separate Management Port

When using a `management.server.port` different from the main port, Actuator has a corresponding management web context. Matching must tie to the right context; you cannot simply see `/manage` on the main port and conclude it is a management endpoint.

In the 3.3.13 implementation, `EndpointRequest` handles the management context when the port is separated. The matcher also initializes based on the application context, not just a pure URL string comparison. [EndpointRequest source 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.java)

If moving the lab model to a separate port, you must verify:

- Endpoints on the right management port.
- Business APIs on the main port.
- Which chain is selected in each context.
- Listen addresses, firewalls, and paths through proxies.
- Health probes/collectors calling the right address, port, and path.

Do not infer network policy from the matcher matching endpoints properly.

### 10.3. Differences With WebFlux and JMX

This article uses `EndpointRequest` in the `security.servlet` package, matching Servlet requests.

WebFlux has its corresponding reactive security API and matcher; do not use this article's `HttpSecurity`/`SecurityFilterChain` as-is. JMX is a different channel and is not protected by this HTTP Servlet matcher.

## 11. Common Mistakes When Reading or Writing Rules

| Mistake | Consequence | How to check |
| --- | --- | --- |
| Importing reactive EndpointRequest into Servlet config | Wrong matcher/API type | Check package imports and web stack |
| Passing /actuator/health into to(String...) | Confusing URL with ID | Use health or HealthEndpoint.class |
| Passing a business controller class | Class is not an appropriate Actuator endpoint | Identify the component type being secured |
| Having only a securityMatcher(toAnyEndpoint()) chain | Leaves the rest of the app uncovered | Inventory chains covering unmatched requests |
| Placing a catch-all chain before the Actuator chain | Specialized chain is never selected | Check Order and matcher of each chain |
| Placing a broad rule before the health exception | Exception is not applied as intended | Check rule order within the chain |
| Treating toAnyEndpoint like /manage/** | Misunderstands non-endpoint requests | Test an unmapped path with valid credentials |
| Treating excluding as denying access | Endpoint falls through to another policy | Trace which chain is selected next |
| Discarding the return value of excluding | Original matcher is still used | Use the returned matcher value |
| Forgetting discovery | Leaks links page outside intended policy | Test the base path with each identity |
| Permitting health while thinking only of root URL | Overlooks groups or subpaths | Test actual provided health paths |
| Using a matcher as proof an endpoint is exposed | Confuses recognition with exposure | Check endpoints/mappings and HTTP config |
| Thinking a valid matcher means POST must be permitted | Ignores roles, CSRF, and supported methods | Check each layer and each operation |

When diagnosing 401/403, test with anonymous callers, wrong credentials, valid users missing roles, and users with sufficient roles. Do not test only with operator and conclude the entire configuration is right.

When diagnosing 404, verify the right port, context path, base path, path mapping, and exposure. Test with valid credentials so an authentication rejection does not mask routing results.

## 12. Practice Exercises

### Exercise 1: One Endpoint, Two Ways to Identify

Write two matchers both targeting health: one by ID, one by class. Then map health to `ready`.

**Self-check criteria:** both still express the health endpoint; do not change the ID to `ready`. Test the new path to confirm permissions were not unintentionally altered.

### Exercise 2: Predict the Request Path

Keep the two lab chains, and only exclude info from the first chain's matcher. Reader calls info with valid credentials.

**Analysis:** info is evaluated in the second chain, which only requires authentication. If the requirement is still that only OPS may read it, that exclusion change does not meet the requirement.

### Exercise 3: Separate the Discovery Policy

You want health public, info for OPS, and discovery forbidden for everyone. Which outer matcher must be kept and which rule changed?

**Analysis:** keep `toAnyEndpoint()` so discovery enters the management chain, and place `toLinks().denyAll()` before the remaining rule. If you want to disable the discovery resource rather than merely denying HTTP access by permission, that is a different configuration decision.

### Exercise 4: Design a Matrix When Infrastructure Changes

Switch to a separate management port or add a context path. Tabulate caller source, port, actual path, expected chain, and results by identity.

**Self-check criteria:** include root endpoint, subpath, discovery, business API, and a non-existent path. Every request not matching the Actuator chain has a clearly explained subsequent policy.
