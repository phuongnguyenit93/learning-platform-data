# Separating Security Rules for Business APIs and Management Endpoints

## 1. Two Functional Groups, Two Access Policies

Business APIs serve the application's core functionality: placing orders, reading invoices, updating profiles. Spring Boot Actuator's management endpoints provide operational capabilities: viewing health, metrics, application info, or adjusting certain components when the corresponding endpoint is used.

These two groups have different audiences and different impact levels. An account allowed to view orders should not automatically be allowed to view operational information; an on-call operations account should not automatically have permission to read business data either.

**Separating security rules** means clearly defining:

- Which requests belong to business APIs, and which belong to management.
- Which authentication mechanism each group accepts.
- After authentication, what permissions the caller needs.
- How requests outside the defined groups are handled.

This article uses **Spring Boot 3.3.x, Spring Security 6.3, and a Servlet/Spring MVC application**. Examples run with JDK 21 and Spring Boot 3.3.0. For WebFlux, the chain selection model is still useful, but the configuration types are `SecurityWebFilterChain` and `ServerHttpSecurity`; do not copy Servlet imports directly into a reactive application.

### The Policy to Build

The example has two accounts with independent roles:

- `apiuser` has role `API_USER`, for using business APIs.
- `opsuser` has role `OPS`, for using management endpoints.
- Unauthenticated callers may only view minimal health.

| Resource | Unauthenticated | Has API_USER | Has OPS |
| --- | --- | --- | --- |
| Minimal health | Permit | Permit | Permit |
| Info and other exposed Actuator endpoints | Deny | Deny | Permit |
| Business API `/api/**` | Deny | Permit | Deny |
| Paths outside defined scopes | Deny | Deny | Deny |

The `OPS` role in the example is not an implicit “superuser” role. If one person needs both functional groups, granting both roles must be an explicit decision.

## 2. Distinguishing Three Decision Layers

### 2.1. Is the Endpoint Exposed?

`management.endpoints.web.exposure.include` selects which endpoints are exposed over HTTP. It does not declare who is allowed to call them. Conversely, `permitAll()` does not automatically create an endpoint that is disabled or unexposed.

In Spring Boot 3.3, when you declare a custom `SecurityFilterChain`, Boot's default web security configuration yields to the application's configuration. You must not assume Boot will automatically add a chain to protect paths that the new configuration omits. [Securing Actuator Endpoints in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

### 2.2. Which Filter Chain Handles the Request?

`SecurityFilterChain` is a chain of security filters. `FilterChainProxy` checks registered chains in priority order and selects **the first chain that matches the request**.

```text
HTTP Request
  |
  +-- Matches Actuator endpoint? -- yes --> Management chain
  |                                  no
  +-- Matches /api/**? ------------ yes --> Business API chain
  |                                  no
  +---------------------------------------> Fallback chain: deny
```

If the management chain rejects the caller due to a missing role, the request is not forwarded to the API chain to “try again”. Chains do not stack into multiple authorization layers for a single chain selection. [SecurityFilterChain selection mechanism](https://docs.spring.io/spring-security/reference/servlet/architecture.html#servlet-securityfilterchain).

### 2.3. Which Rules Apply Inside the Chain?

| Configuration API | Role |
| --- | --- |
| `http.securityMatcher(...)` | Determines which requests belong to the scope of the entire chain |
| `authorizeHttpRequests(...).requestMatchers(...)` | Selects authorization rules inside the already selected chain |
| `anyRequest()` inside authorization | All remaining requests within the scope of that chain |
| `@Order` on chain bean | Evaluation order of chains; smaller numbers are evaluated first |

For example, `anyRequest().authenticated()` inside a chain with `securityMatcher("/api/**")` only applies to requests under `/api/**`. It does not automatically protect management paths or the rest of the application.

If no chain matches, that request is not protected by the Spring Security chains. Therefore, the example uses a final chain without a `securityMatcher` restriction, with a `denyAll()` policy. [Distinguishing securityMatcher and requestMatchers](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_choosing_securitymatcher_or_requestmatchers).

## 3. Identifying Actuator with EndpointRequest

Hardcoding `"/actuator/**"` makes configuration depend on the URL prefix. When the prefix changes to `/manage`, the old rule may no longer recognize requests properly.

Spring Boot provides `EndpointRequest` to build matchers based on actual endpoint locations:

```java
EndpointRequest.toAnyEndpoint()
EndpointRequest.to(HealthEndpoint.class)
```

- `toAnyEndpoint()` matches Actuator endpoints exposed over the web, including the discovery links page at the management base path.
- `to(HealthEndpoint.class)` selects the health endpoint; this rule can also match health subpaths, including health groups.
- An endpoint matcher is not a rule protecting any arbitrary URL sharing the same prefix. Paths not belonging to recognized endpoints must be handled by the remaining chains.

That is why the design includes both an Actuator matcher and a fallback chain. [Spring Boot 3.3 EndpointRequest API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html).

For a public health policy, you must decide the exact scope you truly want to open. The example below intentionally permits health and its subpaths while hiding details. If you only want to expose a specific health group publicly, you must narrow the matcher accordingly and test the remaining groups separately.

## 4. Building the Demo Application

### 4.1. Dependencies and Endpoint Configuration

Use a Gradle project with Wrapper 8.5, JDK 21. A minimal `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

File `settings.gradle`:

```groovy
rootProject.name = 'actuator-security-demo'
```

File `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
      show-components: never
```

Only health and info are selected for exposure in the experiment. Do not use `include: "*"` to test authorization. Health when healthy returns only overall status; component details are not shown in this configuration.

### 4.2. Business API

File `src/main/java/example/SplitSecurityApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SplitSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(SplitSecurityApplication.class, args);
    }

    @GetMapping("/api/orders")
    public String orders() {
        return "orders-ok";
    }
}
```

The `GET /api/orders` API returns a fixed string to keep focus on observing authorization. This is a demo API, without implementing actual order querying.

### 4.3. Three Security Chains

File `src/main/java/example/SecurityConfig.java`:

```java
package example;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain managementSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
                .anyRequest().hasRole("OPS"))
            .httpBasic(withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasRole("API_USER"))
            .httpBasic(withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().denyAll())
            .httpBasic(withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var api = User.withUsername("apiuser")
            .password(encoder.encode("api-lab-pass"))
            .roles("API_USER")
            .build();
        var ops = User.withUsername("opsuser")
            .password(encoder.encode("ops-lab-pass"))
            .roles("OPS")
            .build();
        return new InMemoryUserDetailsManager(api, ops);
    }
}
```

The two passwords in the example are for local experimentation only. `BCryptPasswordEncoder` hashes them before storing the users in memory. When building a real system, replace the demo accounts with your system's identity source and credential provisioning; HTTP Basic must be protected with HTTPS when transmitted over a network.

### 4.4. Reading the Configuration Within Proper Scope

**Management chain, order 1:**

- Only matches Actuator requests.
- Permits health without requiring login.
- Remaining requests in the chain require the `OPS` role.
- Enables HTTP Basic for this chain itself.

**API chain, order 2:**

- Only matches `/api/**`.
- Requires the `API_USER` role.
- Configures HTTP Basic on its own; it does not borrow authentication configuration from the first or last chain.

**Fallback chain, order 3:**

- Sets no `securityMatcher`, so it receives requests not claimed by earlier chains.
- Denies all requests in this portion.
- Enables HTTP Basic so unauthenticated response behavior is consistent with the experiment.

`roles("OPS")` creates the authority `ROLE_OPS`; `hasRole("OPS")` checks that authority. Do not pass `"ROLE_OPS"` to `hasRole`. If working directly with the full authority string, use `hasAuthority("ROLE_OPS")`.

The example shares one `UserDetailsService` across chains for reproducibility. Splitting chains does not automatically create two account stores, two token issuers, or two independent identity domains.

## 5. Run and Observe Both Allowed and Blocked Cases

### 5.1. Start the Application

In PowerShell, in the project directory:

```powershell
.\gradlew.bat bootRun
```

In Bash, use `./gradlew bootRun`. The application requires Spring dependencies, so use the project's build workflow rather than invoking `javac` directly without a classpath.

Open another PowerShell terminal and run each command below. Response codes assume the demo application is running with the right configuration, no extra filters, healthy status, and no cookies or credentials sent beyond what the commands show.

### 5.2. Health Without Credentials

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://localhost:8080/actuator/health
```

Result:

```text
200
```

If inspecting the response body, a healthy application returns `{"status":"UP"}`. A system with a failing health component may return a different status code; access permission and health status are two separate concerns.

### 5.3. API Account Calling Its Own Functional Group

```powershell
curl.exe -s -u "apiuser:api-lab-pass" http://localhost:8080/api/orders
```

Response body:

```text
orders-ok
```

When that account calls management info:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" -u "apiuser:api-lab-pass" http://localhost:8080/actuator/info
```

Result:

```text
403
```

Valid credentials do not substitute for the management role.

### 5.4. Operations Account Is Also Scope-Limited

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" -u "opsuser:ops-lab-pass" http://localhost:8080/actuator/info
```

Result:

```text
200
```

But when calling the business API:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" -u "opsuser:ops-lab-pass" http://localhost:8080/api/orders
```

Result:

```text
403
```

If real requirements genuinely need operations to call business APIs, that must be expressed by granting the permission or changing the policy; you should not infer permissions from a role name.

### 5.5. Full Verification Matrix

| GET Request | Unauthenticated | apiuser | opsuser |
| --- | --- | --- | --- |
| `/actuator/health` | 200 when healthy | 200 when healthy | 200 when healthy |
| `/actuator/info` | 401 | 403 | 200 |
| `/actuator` — links page | 401 | 403 | 200 |
| `/api/orders` | 401 | 200 | 403 |
| `/unmapped` — path outside both groups | 401 | 403 | 403 |

In the experiment:

- **401** appears when authentication is required and the request lacks valid credentials.
- **403** appears when the user is authenticated but does not satisfy the policy.
- A write request can also receive **403 due to CSRF** before the authorization step; do not conclude every 403 is due to the wrong role.

`permitAll()` is an authorization decision. It does not tell the authentication filter to ignore invalid credentials: sending a wrong password with HTTP Basic to health can still return 401, even though calling health without credentials is permitted.

## 6. Testing Resilience When Moving the Management Path

### 6.1. Changing the Prefix to /manage

Add to the `management.endpoints.web` branch in YAML:

```yaml
management:
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
```

This replaces the corresponding configuration branch; do not create a duplicate `management` key in the same YAML document. Keep the existing health configuration and restart.

Change the management URLs in the matrix to `/manage/health`, `/manage/info`, and `/manage`. Role rules must still hold without modifying the Java chains, because `EndpointRequest` detects endpoint locations instead of depending on the `"/actuator/**"` string. [EndpointRequest integration with management paths](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html#mvc-security).

### 6.2. When the Management Prefix Sits Inside the API Prefix

Try `management.endpoints.web.base-path=/api/manage`.

Now `/api/manage/info` is both under `/api/**` and is the info endpoint location. Because the Actuator chain has `@Order(1)`, the request is handled by the management chain:

- `apiuser` is still denied.
- `opsuser` can still call info.
- The request does not continue to the API chain after the management chain has matched.

This is a useful test for **precedence when scopes overlap**. If you reverse the order so an overly broad API chain runs first, management endpoints may get the wrong policy applied.

In real deployments, choose paths that clearly distinguish the two functional groups. The overlap test helps catch configuration bugs, not as a reason to intentionally overlap them.

### 6.3. Changing Ports Does Not Replace Authorization

A separate management port, bind address, and network rules help control access paths. They do not automatically create an `OPS` requirement or remove business user permissions.

The example runs on a single port to observe chain selection. If switching to a separate `management.server.port` or adding a proxy, you must re-test on the actual deployment port and path, covering both the main application and the management context. Do not infer that single-port testing proves every other deployment configuration.

These Servlet chains protect HTTP requests passing through them. They do not automatically authorize JMX; if JMX is used, that channel's policy must be defined separately.

## 7. CSRF, Sessions, and Authentication Must Not Be Assumed Shared

In the example, all three chains set `SessionCreationPolicy.STATELESS`: Spring Security does not use an HTTP session to retrieve or store `SecurityContext` under this policy. Every request protected by HTTP Basic must supply appropriate credentials.

**Stateless does not mean CSRF is unnecessary.** Browsers can automatically send credentials in certain mechanisms, including HTTP Basic. Therefore the example keeps default CSRF protection intact, focusing on GET requests to observe roles. [CSRF and stateless browser applications](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html#csrf-and-stateless-browser-applications).

For state-changing requests, such as an Actuator write operation when that endpoint is enabled and exposed, a user with the right role still has to satisfy the active CSRF policy. Do not disable CSRF across the whole application just to make a 403 go away. [CSRF protection in Servlet applications](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).

If extending the configuration so APIs use Bearer tokens and management uses HTTP Basic:

1. Configure token authentication in the API chain.
2. Configure HTTP Basic or the chosen management mechanism in the Actuator chain.
3. Review CSRF, session, CORS, and error handling in each chain.
4. Test that credentials meant for one group are not accidentally accepted as permissions for the other group.

The selected chain must contain all required configuration. Configuring `httpBasic()` on the fallback chain does not provide HTTP Basic for requests already claimed earlier by the Actuator chain.

If sharing the same authentication mechanism, session policy, and other protection requirements, a single chain with distinct authorization rules can also satisfy the design. Multiple chains are useful when separating both filter scope and security handling, not because having two roles mandates having two chains.

## 8. Configuration Mistakes to Recognize

### Management Chain Missing securityMatcher

If the `@Order(1)` chain only sets `anyRequest().hasRole("OPS")` without narrowing scope, it can match all requests before the business chain. API users will then be required to have the management role.

You must check the **entire chain's** matcher, not only read rules inside `authorizeHttpRequests`.

### Using Only authenticated Across All of Actuator

`authenticated()` accepts any authenticated identity satisfying the chain's mechanism. In the example, that would let `apiuser` pass management rules even without the `OPS` role.

Distinguish authentication (“who is the caller”) from authorization (“what is that caller allowed to do”).

### Placing a Catch-All Chain First

A chain matching all requests placed before the Actuator chain will shadow the Actuator chain. A method name like `managementSecurity` does not create priority; scope and `@Order` determine chain selection.

### Securing Only Actuator and Forgetting the Rest

After declaring a custom Actuator chain, do not expect the default configuration to automatically protect business APIs. There must be chains or rules handling APIs and remaining paths.

Do not use `web.ignoring()` to make health public if the goal is merely not requiring login. `permitAll()` still lets the request pass through the chain's security mechanisms; bypassing filters is a different decision.

### Misinterpreting Status Codes of Unexposed Endpoints

In the example, `env` is not in the exposure list. A request to `/actuator/env` may be rejected by the fallback chain before reaching handler lookup. Therefore, seeing 401 or 403 does not prove that endpoint is exposed.

To determine the cause, check separately: endpoint enabled config, exposure set, matching chain, authentication outcome, permissions, and other protective filters.

## 9. Boundary Verification Exercises

1. Keep both accounts, call both the business API and info with each account. Confirm each account can only use its granted functional group.
2. Change the management prefix to `/manage`, repeat the same matrix, and confirm no Java matcher edits are needed.
3. Test the `/api/manage` prefix to observe the role of chain order when two scopes overlap.
4. On a separate experimental configuration copy, replace `hasRole("OPS")` with `authenticated()`, then check how the API account passes the management rule. Restore the policy after observing.
5. Explain why a request that matched the management chain and was denied will not fall through to the API chain.

When evaluating a configuration, you should be able to point out **which chain receives the request, which mechanism authenticates the caller, and which rule decides access**. Testing blocked cases too helps prove the boundary between business APIs and management endpoints.
