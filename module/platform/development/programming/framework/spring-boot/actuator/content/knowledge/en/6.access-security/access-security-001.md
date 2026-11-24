# Actuator Security Behavior with and without Spring Security

## 1. Starting from Two Different Questions

Actuator provides access points for monitoring and operating a Spring Boot application. An access point, or endpoint, can report operational health, application information, metrics, or support an administrative operation.

When inspecting an endpoint, you need to separate two questions:

1. **Does the application expose this endpoint over HTTP?**
2. **If so, who is allowed to call it and under what conditions?**

Spring Boot Actuator handles providing administrative capabilities. Spring Security adds authentication, authorization, and filters that protect HTTP requests. Having Actuator does not imply the application requires login; adding Spring Security also does not imply every security decision already matches operational needs.

This article uses **Spring Boot 3.3.x, Spring MVC, and Spring Security 6.x**. The hands-on lab pins Spring Boot 3.3.13, Java 21, and Maven 3.9+ to have a reproducible setup. This is a version chosen to study behavior, not a recommendation for choosing the latest version in production deployments.

Reading path: distinguish the control layers → compare with/without Spring Security → understand when default configuration backs off → run three scenarios → interpret HTTP results.

## 2. Three Layers That Must Not Be Conflated

### 2.1. Enabling Endpoint Functionality

In Spring Boot 3.3, properties of the form `management.endpoint.<id>.enabled` control whether an endpoint is enabled. If an endpoint requires additional libraries or supporting beans, those conditions must also be met.

For example, requesting to expose an endpoint cannot by itself create the integration library that the endpoint requires.

### 2.2. Exposing Over HTTP

`management.endpoints.web.exposure.include` selects endpoints exposed over HTTP; `exclude` removes them and takes precedence if an ID appears in both lists.

In the default configuration of Spring Boot 3.3, only `health` is exposed over HTTP. Therefore, without adding Spring Security, calling `/actuator/info` and receiving 404 does not prove that this endpoint is protected by login. It may simply not be exposed. [Spring Boot 3.3: Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing)

Example of intentional exposure:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
```

This YAML snippet does not declare accounts, passwords, or roles.

### 2.3. HTTP Access Permissions

When Spring Security is actually configured for the web application, requests can pass through filters before reaching the endpoint. The filters authenticate the caller, apply authorization rules, and enforce protections such as CSRF.

```text
HTTP request
  → network/proxy layers, if any
  → security filter chain applied to the request, if any
  → application HTTP mapping
  → Actuator endpoint
```

Because filters run before endpoint handling, a request can be rejected before the application determines whether that path exists. This is why a 401 status alone cannot be used to infer that an endpoint is exposed. [Spring Security: Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)

## 3. The Case Without Spring Security

Suppose the application only has the web and Actuator dependencies, without the required Spring Security libraries on the classpath, and without another authentication mechanism provided by the application or infrastructure.

In that case, Actuator does not automatically create a login layer for exposed endpoints. If a caller can connect to the application, that endpoint can be called without credentials.

Consider two configurations:

- **Default Actuator configuration:** health is exposed; info is not exposed.
- **Configuration additionally exposing info:** both health and info are exposed.

Typical GET results in a healthy application with no custom filters:

| Configuration | GET /actuator/health, anonymous | GET /actuator/info, anonymous |
| --- | --- | --- |
| Default exposure only | 200 | 404 |
| Expose health and info | 200 | 200 |

This table reflects the stated assumptions. If health reports an unhealthy state, the status code may differ from 200; if a gateway in front requires login, the result observed at the gateway will also differ.

### Things That Do Not Automatically Create Application Security

- Only adding `spring.security.user.name` and `spring.security.user.password` to YAML while lacking the corresponding Spring Security mechanism.
- Only renaming the `/actuator` path to a hard-to-guess name.
- Only changing the management port.
- Only hiding details or masking sensitive values in the response.

Each change has its own purpose. To prove authentication is enforced, you must test requests with missing credentials, wrong credentials, and valid credentials on an exposed endpoint.

If you intentionally protect via a gateway/firewall instead of in-application authentication, you must also verify paths that bypass the gateway. A single test through a domain name does not represent every path to the backend.

## 4. The Case With Spring Security and No Custom Filter Chain Yet

### 4.1. Conditions for Default Security

A common way to add Spring Security is the `spring-boot-starter-security` dependency. However, the actual condition is based on the classes/beans present in the application, not merely seeing a starter line in the build file. Another dependency can pull Spring Security in transitively.

In a Spring Boot 3.3 Servlet application, the default management security configuration requires the corresponding Spring Security classes and no application-provided `SecurityFilterChain` bean. [DefaultWebSecurityCondition 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/security/DefaultWebSecurityCondition.java)

The following sections assume auto-configuration has not been excluded and no OAuth2 configuration or alternative authentication mechanism alters the scenario.

### 4.2. Actuator Default Rules

Spring Boot 3.3.13's `ManagementWebSecurityAutoConfiguration`:

- Permits access to health without requiring login.
- Requires the caller to be authenticated for all remaining requests.
- Supports HTTP Basic and form login.

The “remaining requests” rule in the default chain also covers regular application requests; this should not be understood as only a password for a few Actuator paths. [Management security configuration source 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/security/servlet/ManagementWebSecurityAutoConfiguration.java)

Common point of confusion: the default rule requires being **authenticated**, without automatically requiring a role like `ADMIN` or `OPS`. If you want to distinguish business users from operators, you must define an appropriate authorization policy.

### 4.3. The Default Account Is a Development Tool

In a simple setup where no authentication mechanism is provided, Spring Boot creates an in-memory account, defaulting to username `user`, with a password generated at startup. The username/password can be configured with `spring.security.user.*`.

HTTP Basic versus redirecting to a login form is chosen via request content negotiation, including the `Accept` header. Because of this, a browser may receive a redirect, while an API request receives 401. [Spring Boot 3.3: Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html)

A generated development password is not a production identity management design. Do not copy passwords from logs into documentation, public data, or code repositories.

### 4.4. Comparison Table When Both health and info Are Exposed

Assumptions: healthy application, endpoint exists, using GET, no custom security chain yet. For anonymous requests requiring authentication, send `Accept: application/json` to observe API-style behavior.

| Request | Without Spring Security | Default Spring Security |
| --- | --- | --- |
| Health, no credentials sent | 200 | 200 |
| Info, no credentials sent | 200 | 401 |
| Info, wrong username/password sent | No Spring Security mechanism to verify those credentials | 401 |
| Info, valid account sent | 200, not because credentials were verified | 200 |
| Business API /api/ping, anonymous | 200 if controller exists | 401 |
| Info, valid account without OPS role | 200 | Still 200 because default does not require OPS |

Do not use the “wrong credentials” row of the without-Spring-Security case to infer that those credentials were accepted. They may simply be unused data.

## 5. What Does Public Health Mean?

Allowing anonymous health lets health-checking tools call it without an account. This is a convenient default; specific systems may want further restrictions.

You must separate **endpoint access permission** from **the level of detail in the returned payload**:

```yaml
management:
  endpoint:
    health:
      show-details: never
      show-components: never
```

This configuration keeps the health response concise; it does not require login and does not filter IP addresses. If you change to showing details by role, you must separately verify identity/roles and the actual returned payload.

Another note: `permitAll` is an authorization rule, not a command to bypass every filter. If a caller actively sends an invalid HTTP Basic header, the authentication filter can still return 401 even when the health path permits anonymous users. Therefore, when testing anonymous health, omit the credential header altogether instead of sending a wrong account. [Spring Security: Request Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)

In the hands-on lab, anonymous health commands do not send any credentials.

## 6. When Declaring a Custom SecurityFilterChain: Ownership Changes

### 6.1. Default Configuration Backs Off, Rather Than Adding an Invisible Layer

If the application declares its own `SecurityFilterChain` bean, you must no longer rely on Boot's default rules to protect the remaining paths. You must define the chains applied to Actuator and to business APIs yourself.

The following dangerous example is **a snippet illustrating an under-scoped configuration**, not a complete program:

```java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    http.authorizeHttpRequests(auth -> auth.anyRequest().authenticated());
    http.httpBasic(withDefaults());
    return http.build();
}
```

This chain only matches requests matching `/api/**`. If this is the only chain and there is no other protection layer, Actuator endpoints outside that scope are not protected by this chain. Creating a custom bean caused the default configuration to back off; Boot does not automatically create an additional chain to patch what was missed.

You must distinguish:

- `securityMatcher(...)`: selects which requests are handled by the entire chain.
- `requestMatchers(...)` inside `authorizeHttpRequests`: selects authorization rules within the already selected chain.

When there are multiple chains, only the first matching chain is applied; you must design their order and a chain covering the rest. [HttpSecurity 6.3 API](https://docs.spring.io/spring-security/site/docs/6.3.0/api/org/springframework/security/config/annotation/web/builders/HttpSecurity.html), [Spring Security: Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)

The hands-on lab uses a single chain covering all requests to make policy changes clear, without needing to split into multiple chains yet.

### 6.2. Customizing the Chain Differs From Customizing Account Storage

The two kinds of beans have different responsibilities:

| Component | Question It Answers |
| --- | --- |
| SecurityFilterChain | Which paths use which security mechanism, and what permissions do they require? |
| UserDetailsService | Where is account information for authentication loaded from? |
| PasswordEncoder | Which algorithm is used to hash/verify passwords? |

Merely adding a `UserDetailsService` does not mean every path is permitted. Conversely, merely adding a custom chain does not automatically disable the default account creation configuration. Auto-configuration for the account source has its own back-off conditions. [UserDetailsServiceAutoConfiguration 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/security/servlet/UserDetailsServiceAutoConfiguration.java)

## 7. Hands-On: Same Application, Three Security Scenarios

The shell commands below use Bash and `curl`; in PowerShell you can use `curl.exe` and adjust line-continuation syntax. All HTTP addresses in the lab are loopback. Credentials written in the examples are for lab use only; over a real network you must use TLS and proper secret management.

### 7.1. Create the Project Without Spring Security

Initial structure:

```text
actuator-security-lab/
├── pom.xml
└── src/main/
    ├── java/lab/ActuatorSecurityApplication.java
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
    <artifactId>actuator-security-lab</artifactId>
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

Contents of `src/main/java/lab/ActuatorSecurityApplication.java`:

```java
package lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ActuatorSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorSecurityApplication.class, args);
    }

    @GetMapping("/api/ping")
    public String ping() {
        return "pong\n";
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
      exposure:
        include:
          - health
          - info
  endpoint:
    health:
      show-details: never
      show-components: never
```

The application uses Spring Boot dependencies, so compile and package it with Maven instead of running standalone `javac` on a single file:

```bash
mvn clean package
java -jar target/actuator-security-lab-1.0.0.jar
```

The first run requires access to the Maven repository. Wait for the application to start successfully, ensuring no other process is using port 8080. Keep the application running in one terminal and use another terminal to send requests.

### 7.2. Scenario A: Without Spring Security

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/actuator/health

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/api/ping
```

With a healthy, properly configured application, stdout of the three commands in order:

```text
200
200
200
```

Call the API to fetch the body:

```bash
curl --noproxy '*' -sS http://127.0.0.1:8080/api/ping
```

Stdout:

```text
pong
```

To distinguish unexposed from authentication-required, test an endpoint not in the include list:

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/actuator/env
```

Expected stdout is `404`. The reason in this lab is that env is not exposed over HTTP, not that Spring Security protected it.

### 7.3. Scenario B: Add Spring Security, Keep Default Security

Stop the JVM with Ctrl+C. Add the following dependency **inside the `<dependencies>` section of the existing POM**:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

Do not create any security configuration class yet. Repackage and start with a fixed lab account:

```bash
mvn clean package
java -jar target/actuator-security-lab-1.0.0.jar \
  --spring.security.user.name=observer \
  --spring.security.user.password=lab-observer-only \
  --spring.security.user.roles=VIEWER
```

These arguments only help make the lab reproducible. Do not pass real passwords on the command line or store deployment credentials in a code repository.

Try five requests:

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/actuator/health

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  -u observer:wrong-password \
  http://127.0.0.1:8080/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  -u observer:lab-observer-only \
  http://127.0.0.1:8080/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/api/ping
```

Expected stdout, in exact order:

```text
200
401
401
200
401
```

What is observed:

1. Health can still be called without sending credentials.
2. Info is exposed, but requires authentication.
3. Sending wrong credentials does not pass authentication.
4. A valid account with role VIEWER can still read info because the default configuration only requires authentication.
5. The business API is also protected by the default chain.

To inspect headers, use `-i` instead of discarding the body. Do not add `-L` when you want to observe the initial redirect; that option can follow through to the login page and mask the initial 302 code.

### 7.4. Scenario C: Set OPS Role Requirement for Actuator

Stop the JVM. Keep the security dependency from scenario B, then create a new file `src/main/java/lab/LabSecurityConfig.java`.

Example policy:

- Health allows anonymous users.
- The remaining Actuator endpoints require the OPS role.
- Other requests require an authenticated user.
- Use HTTP Basic; keep default CSRF protection.
- Use two in-memory accounts to compare results.

```java
package lab;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class LabSecurityConfig {
    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
            .requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
            .anyRequest().authenticated()
        );
        http.httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService labUsers(PasswordEncoder encoder) {
        var observer = User.withUsername("observer")
            .password(encoder.encode("lab-observer-only"))
            .roles("VIEWER")
            .build();

        var operator = User.withUsername("operator")
            .password(encoder.encode("lab-operator-only"))
            .roles("OPS")
            .build();

        return new InMemoryUserDetailsManager(observer, operator);
    }
}
```

`roles("OPS")` creates the authority `ROLE_OPS`; `hasRole("OPS")` checks the authority following this convention. In the example, do not write `hasRole("ROLE_OPS")`.

The health matcher must come before the broad Actuator matcher so the policy for health is matched first. `EndpointRequest` recognizes endpoint paths; `toAnyEndpoint()` also includes the discovery path at the base path. This expresses intent more clearly than repeating path strings in multiple places. [EndpointRequest 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html)

`http` in the example does not have a `securityMatcher` narrowing its scope. Therefore `anyRequest().authenticated()` covers the rest, avoiding gaps where APIs are left out when customizing Actuator. This is the lab's policy; production may need finer-grained permissions per endpoint or API.

These two accounts are created by `labUsers`, not by Boot's default account configuration. Omit the `spring.security.user.*` arguments when starting scenario C:

```bash
mvn clean package
java -jar target/actuator-security-lab-1.0.0.jar
```

Verify again:

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/actuator/health

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  http://127.0.0.1:8080/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  -u observer:lab-observer-only \
  http://127.0.0.1:8080/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  -u operator:lab-operator-only \
  http://127.0.0.1:8080/actuator/info

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  -u observer:lab-observer-only \
  http://127.0.0.1:8080/api/ping
```

Expected stdout:

```text
200
401
403
200
200
```

This time, observer authenticates successfully but is denied reading info due to lacking OPS. Operator has OPS and is allowed to read it. Observer can still call the business API because the policy there only requires being authenticated.

What changed from B to C is **the authorization rules and the application-owned account source**, not whether info is exposed. The exposure list remains unchanged.

## 8. Why Does POST Still Return 403 Even With Valid Login?

Valid authentication is not enough for every request to be processed. A request may also have to satisfy roles, CSRF, HTTP method, and operation-specific conditions.

Spring Security enables CSRF by default for unsafe methods such as POST. A request missing a token can be rejected immediately at the CSRF filter. Therefore, you must not automatically conclude that 403 always means a wrong password or missing role. [Spring Security: CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)

### Separate Experiment With the loggers Endpoint in the Lab

To verify this behavior, stop scenario C and restart with an exposure list adding loggers:

```bash
java -jar target/actuator-security-lab-1.0.0.jar \
  --management.endpoints.web.exposure.include=health,info,loggers
```

In another terminal:

```bash
curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Accept: application/json' \
  -u operator:lab-operator-only \
  http://127.0.0.1:8080/actuator/loggers/lab

curl --noproxy '*' -sS -o /dev/null -w '%{http_code}\n' \
  -u operator:lab-operator-only \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  -X POST \
  --data '{"configuredLevel":"INFO"}' \
  http://127.0.0.1:8080/actuator/loggers/lab
```

With the stated configuration, expected stdout:

```text
200
403
```

GET proves the account can read the endpoint. The POST in the lab does not send a CSRF token, so it is rejected under the default configuration; no log level change occurs from that blocked request.

Do not fix this by disabling CSRF globally just to make a test return 2xx. You need to determine how callers authenticate, whether browsers/cookies or automatically attached credentials are used, and then decide how to issue tokens or define intentional exception scopes. “The API uses Basic” or “stateless without sessions” alone is not enough to conclude there is no CSRF risk.

After the experiment, stop the application and return to the required endpoint list. This article does not cover opening write access to loggers for real environments.

## 9. Reading 401, 403, 404, and 302 Correctly

| Observation | Appropriate Interpretation | What Not to Infer |
| --- | --- | --- |
| 401 with Basic/API | The request failed authentication at the error-returning layer | That the endpoint definitely exists |
| 403 | A layer denied authorization or protection such as CSRF | That the password is definitely wrong |
| 404 | No resource/mapping at the handled path, or an earlier layer hides that path | That login succeeded or the endpoint does not exist in any configuration |
| 302 to login page | Form-based login mechanism is requesting interaction | That Spring Security is inactive |
| 200 | The current request was served successfully | That every other caller has the same permissions |
| 503 from health | May reflect the application's health status | That the authentication mechanism is necessarily broken |

When you need to determine whether an endpoint is unexposed or just being blocked by a filter, use a valid account with appropriate roles, check the exposure configuration, and confirm the right port/base path.

For example: in scenario B, calling env anonymously may return 401 before reaching routing. Only after valid authentication, because env is still not exposed, can 404 be observed. Do not expose an endpoint to “fix” a 401 when the actual cause is missing credentials.

For anonymous health in the lab, accidentally sending credentials also changes the test. Check headers added automatically by tools or credentials cached by a browser/HTTP client from an earlier call.

## 10. What Changes Invalidate the Default Conclusions?

### 10.1. Actual Dependencies and Beans

“Not directly declaring starter-security” does not guarantee “no Spring Security”. You can inspect the Maven project's dependency relationships:

```bash
mvn dependency:tree -Dincludes=org.springframework.security:*
```

In shells that expand `*`, wrap the entire `-Dincludes=org.springframework.security:*` argument in quotes. Inspect the dependency tree and registered beans instead of looking only at a single POM file.

When diagnosing auto-configuration, you can run the lab with `--debug` and inspect the condition evaluation report in local logs. There is no need to expose the conditions endpoint over the network for this check.

### 10.2. Servlet and Reactive

The Java classes in this article use Spring MVC: `HttpSecurity`, `SecurityFilterChain`, and `EndpointRequest` in the `...security.servlet` package.

WebFlux applications use `ServerHttpSecurity`, `SecurityWebFilterChain`, and the corresponding matchers in the reactive package. Do not copy Servlet configuration verbatim into WebFlux and assume protection is complete. The goal of comparison remains identifying default security and custom parts, but configuration APIs and conditions must match the web stack.

### 10.3. Ports, Paths, and Infrastructure Layers

Using a separate management port can help separate network paths; it does not automatically create accounts or require roles. Changing the base path does not replace authorization checks either. [Spring Boot 3.3: Monitoring over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)

If a proxy returns 401 before the JVM, that result reflects the proxy policy. To draw conclusions about Spring Security configuration, you must know which layer the request reached; at the same time, ensure no direct backend path bypasses the intended protection layer.

### 10.4. Spring Boot Version

These examples use the 3.3.x configuration contract. Do not mix properties from another Boot generation and assume all default results are equivalent.

When upgrading versions, re-run the access matrix by identity and operation. The application starting successfully is not enough to prove security rules remained intact.

## 11. Misconceptions to Catch Yourself

| Misconception | How to Verify or Correct Thinking |
| --- | --- |
| Having Actuator automatically provides a password | Separate the Actuator dependency from the authentication mechanism; test an exposed endpoint without sending credentials |
| Not seeing info means it is already protected | Check the exposure list first |
| Including health,info means only administrators can call them | Include selects exposure, not identity |
| Having Spring Security means every endpoint requires ADMIN | Check actual rules; basic defaults only require authentication except health |
| Creating a chain for /api/** means Boot still protects Actuator | Check chain scope and auto-configuration backing off |
| Adding UserDetailsService means HTTP security is disabled | Separate the account source from path rules |
| permitAll bypasses all filters | It decides authorization; authentication or other protections can still reject |
| Valid account means POST must succeed | Check roles, CSRF, and operation requirements |
| Every 403 is caused by a missing role | Check both the CSRF filter and proxy layers |
| Masking sensitive values means all endpoints can be safely exposed | Evaluate structural data, administrative operations, and allowed caller scope |
| Protecting HTTP means JMX is also protected | Inventory the JMX channel separately if enabled; SecurityFilterChain is an HTTP Servlet mechanism |
| Testing only with an admin account is sufficient | Also test anonymous callers, wrong passwords, and authenticated callers lacking roles |

Do not reuse the lab's raw credentials or broad policies for production. The value of the example lies in how to test and explain the differences among the three scenarios.

## 12. Comprehension Exercises

### Exercise 1: Why Does Adding Security Not Make info Appear?

An application keeps default exposure, then adds starter-security. A user with a valid account still cannot read info.

**Analysis guide:** authentication only handles request permissions; it does not add info to the HTTP exposure list. You must verify the right port/path, endpoint list, and result with valid credentials before changing anything.

### Exercise 2: A Business User Can Read info

An application exposes health and info, with default Spring Security. A user with role CUSTOMER logs in successfully and reads info.

**Analysis guide:** this can be expected under the default policy that only requires being authenticated. If the requirement is that only OPS may read it, you must configure a custom policy and re-test with a user lacking OPS.

### Exercise 3: A Small Change Leaves Actuator Unprotected by Any Chain

The development team adds a single `SecurityFilterChain` with `securityMatcher("/api/**")`. Actuator remains exposed, but no other chain matches its requests.

**Analysis guide:** you must consider both Boot backing off and matcher scope. The solution is to define full ownership for all paths needing protection, using a covering chain or multiple chains with the right order/scope.

### Exercise 4: Build a Verification Matrix Before Changing Configuration

For each endpoint to be used, record:

- Whether the endpoint is enabled and exposed.
- Which chain matches the request.
- What anonymous users, wrong credentials, authenticated users lacking roles, and users with sufficient roles receive.
- Under what conditions GET and write operations differ.
- Whether a proxy/firewall changes the observation point.

**Self-check criteria:** you can explain each result by a specific configuration. Do not merely note “Spring Security is present” or “returned 403” and conclude that all of Actuator is properly secured.
