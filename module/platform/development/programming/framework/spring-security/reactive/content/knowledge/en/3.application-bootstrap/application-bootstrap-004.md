# Spring Boot Default Security Configuration and Auto-Generated Development Account

> **Scope:** Spring Boot 3.3.x, Spring WebFlux, Spring Security 6.x, Java 17+. This lesson explains what happens **when you first add Spring Security to a WebFlux application**, how to use the temporary development account, how to tell that auto-configuration is active, and when you must replace the default configuration.

## 1. Why does the API require login right after adding the dependency?

A plain Spring Boot WebFlux application can serve requests without authentication. When you add `spring-boot-starter-security`, Spring Boot detects Spring Security on the classpath and automatically configures security components if the application has not provided a replacement configuration.

For a minimal WebFlux application, the typical outcome is:

- HTTP paths require an **authenticated user**; this applies to the API paths you wrote yourself, not just a login page.
- **HTTP Basic** is available for clients/APIs and **form login** for browsers; how unauthenticated requests receive responses may depend on `Accept`/content negotiation.
- A default login/logout page, HTTP security headers, and CSRF protection are enabled per Spring Security's configuration.
- Spring Boot creates **an in-memory account** so you can test immediately during development: default username `user`, with a randomly generated password at startup.
- A WebFlux application uses reactive mechanisms, including `SecurityWebFilterChain` and `ReactiveUserDetailsService`. Do not confuse them with Servlet-style `SecurityFilterChain` and `UserDetailsService`.

The purpose of the defaults is to avoid accidentally exposing endpoints as soon as a developer adds the security library. It is only a starting point, **not a complete authorization policy** for production.

### When does it activate?

The actual condition requires **a WebFlux application and the security dependency**. A Gradle example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Adding only the WebFlux starter does not create a Spring Security account. Adding only OAuth2 client/Resource Server libraries can change the user source auto-configuration conditions; you need to re-verify which authentication type is actually configured.

## 2. Two independent auto-configuration parts to understand

In Spring Boot 3.3, two branches commonly mentioned are:

1. **`ReactiveSecurityAutoConfiguration`:** integrates security at the WebFlux layer, providing the foundation for Spring Security to insert `WebFilter`s into the request processing chain. If there is no custom security configuration, the default rule requires authentication.
2. **`ReactiveUserDetailsServiceAutoConfiguration`:** provides an in-memory reactive user store (`ReactiveUserDetailsService`) when no suitable authentication infrastructure has been provided by the application. This is where the development account and randomly generated password come from.

You can picture it as:

```text
GET /api/message
       |
       v
WebFlux / ServerWebExchange
       |
       v
SecurityWebFilterChain
       |-- Check whether the request is permitted?
       |-- Choose form login / HTTP Basic when appropriate
       |-- Authenticate username/password
       |           |
       |           +--> ReactiveUserDetailsService
       |                    +--> user (password generated at startup)
       v
Controller -> Mono/Flux -> HTTP response
```

**Separate the two questions:**

- *Which endpoints can be accessed?* — decided by `SecurityWebFilterChain`/`ServerHttpSecurity`, matchers, and authorization rules.
- *How are users found and authenticated?* — decided by `ReactiveUserDetailsService`, `ReactiveAuthenticationManager`, and the corresponding authentication mechanism.

Changing path rules does not mean you replaced the user store; replacing the user store does not automatically make endpoints public either.

### Configuration change scenarios

| What you additionally configure | Normally expected behavior |
|---|---|
| No custom security beans, `starter-security` present | WebFlux is protected by default, with an auto-generated development account |
| Create a custom `SecurityWebFilterChain` | Your application's HTTP rules replace the default web config; the auto-generated account **may still exist** if you have not replaced the authentication component |
| Create a custom `ReactiveUserDetailsService` | The app uses the user source you provided; by default no additional development account is created in that branch |
| Create a custom `ReactiveAuthenticationManager` | The branch that auto-creates `ReactiveUserDetailsService` may back off per auto-configuration conditions |
| Add OAuth2 Client/Resource Server | The default user creation branch may not activate; identify the intended authentication mechanism |
| Configure both chain and authentication | The entire policy and identity source are explicitly defined by the application |

"Back off" conditions are **conditional** auto-configuration behaviors, not a rule that writing any bean turns off all of Spring Security.

## 3. Auto-generated development account: username, password, role, lifecycle

When Spring Boot actually has to create the default user, typically:

| Property | Value/meaning |
|---|---|
| Username | `user` |
| Password | Random string generated when the application context starts |
| Where to see the password | WARN message in startup logs, if the logging level allows |
| Default role | `USER` (corresponding authority `ROLE_USER`) |
| Where the user is stored | In-memory reactive user store, not a database user table |
| Purpose | Helps test the app during development; not for use as a production account |

Example **illustrating the log format**, not a real password to copy:

```text
Using generated security password: <random-secret>
This generated password is for development use only.
Your security configuration must be updated before running your application in production.
```

The log is usually emitted by the `org.springframework.boot.autoconfigure.security` group at WARN level in Spring Boot 3.3. If you do not see this line, **do not conclude the application has no security**: you may have defined your own authentication source, set a password via configuration, the log level may hide WARN, or the auto-configuration mechanism may have changed due to dependencies.

The auto-generated password **is not stable across independent restarts**. Do not hardcode it into source code, shared test scripts, or CI. Do not treat log output as a secure credential distribution channel.

### Why does a role name not equal permission on a resource?

`ROLE_USER` is just an authority that lets a policy match, such as `hasRole("USER")`. An account with role USER **is not automatically permitted to view every other user's data**. This lesson focuses on default configuration; when building real APIs, you must still enforce resource-level authorization in services/repositories.

## 4. Minimal runnable Spring Boot WebFlux example

This example **intentionally omits** declaring `SecurityWebFilterChain` or `ReactiveUserDetailsService` to observe real auto-configuration. Assume the machine has JDK 17+ and a Gradle version compatible with Spring Boot 3.3.

Structure:

```text
default-security-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/reactive/DefaultSecurityApplication.java
```

**settings.gradle**:

```groovy
rootProject.name = 'default-security-demo'
```

**build.gradle**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.reactive'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

**src/main/java/demo/reactive/DefaultSecurityApplication.java**:

```java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class DefaultSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(DefaultSecurityApplication.class, args);
    }

    @GetMapping("/api/public")
    public Mono<String> publicMessage() {
        return Mono.just("public endpoint");
    }

    @GetMapping("/api/hello")
    public Mono<String> hello() {
        return Mono.just("hello from WebFlux");
    }
}
```

In the initial state, the name `/api/public` **does not make it public**. No `permitAll()` has been declared, so both URLs require authentication.

### Run and observe

In the project directory:

```bash
gradle bootRun
```

If the project already has a compatible Gradle wrapper, you can use `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Read the startup log and grab the randomly generated password **from that run**.

From another terminal:

```bash
# No credentials: JSON API request
curl -i -H "Accept: application/json" http://localhost:8080/api/hello

# With HTTP Basic: replace GENERATED_PASSWORD with the string just seen in the log
curl -i -H "Accept: application/json" \
  -u "user:GENERATED_PASSWORD" \
  http://localhost:8080/api/hello

# An endpoint named public is still blocked if permitAll is not configured
curl -i -H "Accept: application/json" http://localhost:8080/api/public
```

Key results to verify:

| Request | Expected HTTP | Explanation |
|---|---|---|
| `GET /api/hello` without credentials, `Accept: application/json` | `401 Unauthorized` | Unauthenticated |
| `GET /api/hello` with account `user` and newly generated password | `200 OK`, body `hello from WebFlux` | Authenticated |
| `GET /api/public` without credentials | `401 Unauthorized` | Endpoint name does not create an exception |
| Accessing `/api/hello` via browser with `Accept: text/html` | Usually redirects `302` to `/login` | Form login/content negotiation |

HTTP status codes matter more than HTML content/error messages, because bodies and headers can vary by client, version, and configuration. In a browser, the default login page appears if the browser is not logged in. Avoid interpreting a `302` redirect as "the API is unprotected".

> **Tip:** Try a wrong password to confirm `401`. Try logging in successfully and then opening a second URL to see how session/form login differs from sending HTTP Basic on every request. In applications using cookie/form login, state-changing requests must comply with CSRF protection.

## 5. Replacing the default username/password during development

Spring Boot provides the `spring.security.user.*` property group. Example for a local environment **still using the default user source**:

**application.yml**:

```yaml
spring:
  security:
    user:
      name: local-user
      password: ${LOCAL_DEV_PASSWORD}
      roles: USER
```

Before running, set the `LOCAL_DEV_PASSWORD` environment variable in your shell. PowerShell example:

```powershell
$env:LOCAL_DEV_PASSWORD = "local-only-change-me"
gradle bootRun
```

The line above is only a demonstration password on a personal machine; do not commit it to Git and do not use it in shared systems. When a password property is provided by you, you should no longer expect the **random password** log line from the previous example. The policy blocking all URLs **remains**, only the credentials change.

If configured via `application.properties`, the equivalent syntax is:

```properties
spring.security.user.name=local-user
spring.security.user.password=${LOCAL_DEV_PASSWORD}
spring.security.user.roles=USER
```

You do not need to declare both YAML and properties at the same time; use one approach. This configuration is only convenient for short experiments. For production, prefer a proper identity/authentication system and dedicated secret management; **a single shared account is still not a complete user management model**.

### When does the property above not work as expected?

`spring.security.user.*` serves the user auto-configured by Boot. If you have written a `@Bean ReactiveUserDetailsService`, `ReactiveAuthenticationManager`, or switched to OAuth2/JWT mechanisms, the authentication source and user creation conditions may have changed. In that case, changing `spring.security.user.name` may not modify the user actually being used. Inspect the active authentication beans rather than endlessly tweaking properties.

## 6. Actively changing URL rules: custom SecurityWebFilterChain

When security is first added, every URL requires login. Suppose you want `/api/public` readable without logging in while `/api/hello` remains protected.

Add **one more Java file** in the same project, keeping `DefaultSecurityApplication.java` unchanged:

**src/main/java/demo/reactive/WebFluxSecurityConfig.java**:

```java
package demo.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class WebFluxSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

This is a **custom configuration**, so the results after restarting will differ from the default example:

| Path | Without credentials | With valid credentials |
|---|---|---|
| `GET /api/public` | `200`, body `public endpoint` | `200` |
| `GET /api/hello` with `Accept: application/json` | `401` | `200` |
| Other undeclared paths | Still require authentication per `anyExchange().authenticated()` | Does not automatically guarantee the route exists |

Notes:

1. `pathMatchers(HttpMethod.GET, "/api/public")` only exempts **GET** from authentication; it does not exempt POST/PUT/DELETE.
2. `anyExchange().authenticated()` covers all remaining exchanges; if this condition is missing, you must deliberately evaluate unmatched paths to avoid accidentally leaving routes open.
3. **A custom filter chain does not automatically replace the development account.** If you do not add another authentication source, Boot can still create `user` and a password.
4. `@EnableWebFluxSecurity` is not mandatory in this Spring Boot example because Boot auto-configuration already integrates WebFlux Security. When writing plain Spring Security configuration without Boot, the annotation may be needed depending on project structure.
5. Do not call `csrf().disable()` just to simplify a GET demo. If a UI uses cookies/sessions and write requests, CSRF must be evaluated properly according to the authentication model.
6. For operational/Actuator endpoints, when adding a custom chain you must re-check their separate policy, especially if there are specific matchers or a management port.

## 7. Replacing the development account with an application authentication source

When real accounts are needed, Spring Security reactive can use:

- A custom `ReactiveUserDetailsService` implementation or `MapReactiveUserDetailsService` for demos/tests with a finite list.
- `ReactiveAuthenticationManager` if the authentication flow needs customization.
- OAuth2 Login or OAuth2 Resource Server/JWT if the application architecture uses an identity/token provider.

Core principle: **declaring the authentication source** and **declaring access rules** are two separate concerns.

Code example *illustrating a development environment*, replacing the random user store with an application user; this part is an **optional configuration replacing the auto-generated user mechanism**, no need to add it to the default demo unless you want to try this branch.

**src/main/java/demo/reactive/LocalUsersConfig.java**:

```java
package demo.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;

@Configuration(proxyBeanMethods = false)
public class LocalUsersConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails developer = User.withUsername("developer")
            .password(encoder.encode("demo-only-password"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(developer);
    }
}
```

In this state, use `developer`/`demo-only-password` (on localhost) instead of `user`/randomly generated password. This is a fixed example for learning beans and `PasswordEncoder`: **do not put password literals into production applications**; obtain credentials from a secret management source or identity provider. `BCryptPasswordEncoder` stores/compares a hash rather than storing the raw password in the user object, though the demo code still contains a plaintext string in source. With real users, you should not use an in-memory store to replace a full identity management system.

If only `LocalUsersConfig` is present without a custom `SecurityWebFilterChain`, URLs still require authentication by default. If only `WebFluxSecurityConfig` is present without `LocalUsersConfig`, the auto-generated `user` account may still work. This is a good way to verify the two layers are not mixed up.

## 8. Common pitfalls when bootstrapping an application

### 8.1 "The endpoint is unreachable so WebFlux is broken"

Adding the Security starter is a valid behavioral change: requests are rejected due to missing credentials. Read the status/`WWW-Authenticate` or `Location: /login` before editing controllers. Accessing `/error` may also be subject to default protection.

### 8.2 "No generated password visible, security must be off"

False. Common reasons: WARN logs from `org.springframework.boot.autoconfigure.security` are filtered out; a password was set in configuration; a `ReactiveUserDetailsService`/`ReactiveAuthenticationManager` was provided; or OAuth2 dependencies caused the auto-generated user branch to back off. Inspect dependencies and beans rather than guessing from a single log line.

### 8.3 "Added a chain so the auto-generated user will disappear"

A custom `SecurityWebFilterChain` changes request policies. It does not guarantee that the default `ReactiveUserDetailsService` is replaced. Configure a separate authentication source if you want to remove the development user.

### 8.4 "WebFlux uses SecurityFilterChain like MVC"

In the reactive stack:
- HTTP security filter chain: `SecurityWebFilterChain` + `ServerHttpSecurity`.
- User store: `ReactiveUserDetailsService`.
- Authentication manager: `ReactiveAuthenticationManager`.
- Web request: `ServerWebExchange`.

Servlet stack type names cannot directly substitute for their corresponding reactive types.

### 8.5 "Changing name/password is enough for production"

A single in-memory account lacks user lifecycle, resource-level authorization, key management, auditing, credential revocation, MFA, rate limiting, and session management capabilities. Use a proper authentication source, TLS, secret policies, authorization, and testing before deploying.

### 8.6 "Since it's just an API, all default mechanisms can be turned off"

HTTP Basic, form login, CSRF, and sessions serve different purposes. For a pure bearer-token API, you can design a different policy, but you must explicitly configure authentication and evaluate CSRF/CORS against actual credentials. **Do not disable all security just to make requests return 200.**

### 8.7 "Logs can be used to recover old passwords"

The generated password is created for that startup run; if you restart, the old value usually stops working. Do not build workflows relying on log history to distribute credentials. Logs containing dev passwords must also have restricted access.

## 9. Checklist before moving from demo to a real application

| Question | What to confirm |
|---|---|
| Does the project run WebFlux or MVC? | Right reactive starter and security chain type |
| Why is a URL requiring login? | Security starter is present and which chain applies |
| Where does user data come from? | Generated user, custom reactive user service, auth manager, or IdP |
| Are temporary credentials still present? | No auto-generated user/password or hardcoded passwords in production |
| Which endpoints are public and protected? | Matchers + fallback rule + method-level/object-level authorization |
| Do browsers send cookies or do APIs use bearer tokens? | CSRF, session, and CORS policies designed accordingly |
| Are secrets/tokens leaking into logs? | Masked, log viewing permissions checked, and credential lifecycle managed |
| Are negative test cases covered? | No credentials, wrong password, wrong role, unauthorized route |
| Are Actuator and operational endpoints covered? | Properly protected or network-restricted |

You should have at least four starter tests: (1) unauthenticated requests are rejected for protected APIs; (2) valid credentials are allowed in; (3) intentionally public endpoints are accessible without credentials; (4) accounts lacking permissions are rejected on role-restricted routes.

## 10. Self-check exercises

1. Start the demo **without** `WebFluxSecurityConfig`, note the `401` status on both endpoints. Find the "Using generated security password" line, and log in using `user`.
2. Add `WebFluxSecurityConfig`, restart, and verify `GET /api/public` changes from `401` to `200` while unauthenticated `GET /api/hello` remains `401`.
3. Add only `LocalUsersConfig`, observe that the `developer` account works, and the random user is no longer the default source for the demo branch.
4. Set `spring.security.user.name` in local config **without** `LocalUsersConfig`; then compare with `LocalUsersConfig` present to understand the auto-configuration back-off mechanism.
5. Test a browser with `Accept: text/html` and curl with `Accept: application/json`; describe why unauthenticated cases can differ between redirect and challenge.
6. Explain: why does "having declared a custom `SecurityWebFilterChain`" not prove that `ReactiveUserDetailsService` was replaced?

Once you can answer these six questions, you have distinguished **default web security**, **auto-generated account source**, and **application-configured rules**—three things commonly confused when first integrating Spring Security into WebFlux.

## Reference documentation

- Spring Boot 3.3, Spring Security (especially the **WebFlux Security** section): https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Security, **Getting Started with WebFlux Applications**: https://docs.spring.io/spring-security/reference/6.3/reactive/getting-started.html
- Spring Security, **WebFlux Security Configuration**: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
