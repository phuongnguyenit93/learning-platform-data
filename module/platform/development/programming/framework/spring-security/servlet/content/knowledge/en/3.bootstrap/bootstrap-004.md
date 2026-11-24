# Default Behavior of Spring Security Servlet: Account, Generated Password, and Login Page

## 1. The Big Picture When Adding Spring Security to Spring Boot

In a **Spring Boot Servlet** application using Spring MVC, adding the `spring-boot-starter-security` dependency usually changes HTTP behavior even before the developer writes a `SecurityFilterChain` or a login form.

In the typical case — the Security starter is on the classpath, and the application provides neither a web security configuration nor its own authentication system — Spring Boot/Spring Security sets up:

1. **Protection of HTTP endpoints by default:** requests to normal application resources require authentication before access is granted.
2. **Two default authentication mechanisms:** form login for browser flows and HTTP Basic for suitable clients. How an unauthenticated client receives a response depends on how the request is handled and content negotiation.
3. **One in-memory account:** the default username is `user`, typically with role `USER` and a strong password randomly generated at application startup.
4. **A Spring Security-generated login page:** if form login is enabled and no custom page is declared, visiting `GET /login` returns framework-generated HTML without writing a controller, JSP, or Thymeleaf template.

This is a **starter and development convenience configuration**, not a complete user account system for production. The sections below focus on default mechanisms, how to verify them yourself, common points of confusion, and when to switch to explicit configuration.

**Version scope:** examples use Spring Boot 3.3.x, Spring Security 6.x, and Java 17 or newer (Jakarta Servlet). Different versions, additional starters, or application-provided configurations can alter behavior; do not treat these symptoms as immutable across every Spring project.

## 2. Distinguishing Two Important “Default” Layers

Even though both appear after adding the starter, **HTTP request protection** and the **login account source** are two separate conditional auto-configuration decisions.

| Component | Purpose | When does Boot typically provide the default? |
| --- | --- | --- |
| Web `SecurityFilterChain` configuration | Defines which requests require authentication; enables form login and HTTP Basic | When the Servlet application does not provide its own `SecurityFilterChain` bean to replace Boot's default |
| In-memory `UserDetailsService` | Supplies one user for testing authentication | When Boot finds no application-declared authentication beans of types that cause the default user configuration to back off, such as `UserDetailsService`, `AuthenticationProvider`, `AuthenticationManager`, or an equivalent mechanism |

**Consequence:** adding a custom `SecurityFilterChain` bean causes Boot's default HTTP configuration to back off, but **does not automatically remove** the `user` account. Conversely, providing your own `UserDetailsService` replaces the account source without automatically disabling the require-authentication policy for all requests. You must check **the filter chain configuration** and **the authentication source** separately.

Without a custom web configuration, Boot's conceptual structure is equivalent to:

```java
// Illustrates default logic, not a file to add to the application.
http
    .authorizeHttpRequests(requests ->
        requests.anyRequest().authenticated())
    .formLogin(Customizer.withDefaults())
    .httpBasic(Customizer.withDefaults());
```

This is a **configuration illustration**, not a standalone Java class; it shows three main ideas: every remaining protected request must be authenticated, login page/form is supported, and HTTP Basic is supported. Spring Security still maintains its own rules so login endpoints function properly. Details like CSRF, sessions, error handling, and choosing the authentication entry point remain managed by the framework.

## 3. The `user` Account and Auto-Generated Password

### 3.1. Where Does the Password Come From?

When the default user is active, Spring Boot creates an in-memory user, typically with:

- **Username:** `user`.
- **Password:** a random string generated on startup, printed in the startup log if the relevant logger permits the message.
- **Role:** `USER` (corresponding to authority `ROLE_USER` under Spring Security's role convention).

The log usually shows **“Using generated security password”** along with the actual value, plus a reminder to use this mechanism only during development. The password is **not** a fixed string from documentation and must **not** be assumed to stay the same across restarts. If you do not see the message, do not guess the password: the application may have declared its own account or provider, set a password via properties, changed configuration, or disabled/changed log levels.

**Why log it?** Because the random value was not chosen by a user and there is no account-creation UI, Boot needs a way for the developer to log in the first time. It is sensitive data: do not screenshot it, paste it into public issues, put it in documentation, or share logs containing this password outside development.

### 3.2. Where Does the User Live?

In the default case, Spring Boot creates an `InMemoryUserDetailsManager` holding that account. It does **not** create a `users` database table, does not persist passwords in a durable repository, and has no registration flow or forgot-password feature. This explains why the setup is good for quick testing yet insufficient for real identity management.

When changing the password via properties, the user can still reside in memory. **Setting a fixed username/password is not equivalent to integrating a database, LDAP, OAuth2/OIDC, or an identity provider.**

### 3.3. Distinguishing Random Password Generation from Password Encoding

The “generated security password” message describes the **origin and creation time of the password**. It is not the same as a JWT, access token, session ID, or another login protocol.

Meanwhile, Spring Security verifies passwords using `PasswordEncoder`/the active authentication configuration; do not infer that a string printed in the startup log is a password hash you should type into the form. The user enters the **raw password value** generated in the log, and the application is responsible for verifying the credential. When building a production user source, you must select an appropriate password storage and encoding mechanism.

## 4. How Does the `/login` Page Appear?

When `formLogin` is enabled and **no custom login page is provided**, Spring Security can use `DefaultLoginPageGeneratingFilter` to generate an HTML login page. It lives inside the **security filters** flow, so:

- No `@GetMapping("/login")` is needed to serve the default page.
- No `login.html` template or separate frontend is needed just to test.
- A browser visiting `GET /login` is presented with a form containing username/password; when the form is POSTed, the framework processes authentication as configured.
- The default form includes CSRF token integration when CSRF protection is active; crafting manual POST requests must account for the token under current configuration.

The URL `/login` is the typical default for form login. If you change `loginPage(...)`, `loginProcessingUrl(...)`, or replace `SecurityFilterChain` in a way that omits form login, do not assume this HTML page will still appear.

### 4.1. Unauthenticated Browser

A browser requests a protected resource, e.g., `GET /hello` with `Accept: text/html`. When determined to be unauthenticated, Spring Security typically **redirects to the login page**. The browser follows the redirect to `/login` and renders the framework-generated HTML.

After the user submits `user` and the right password, Spring Security performs authentication, sets the appropriate security context, and typically maintains the login state via an **HTTP session/cookie** in form login flows. After successful authentication, it can send the user back to the previously intercepted request or to a default landing page, depending on context and configuration.

### 4.2. Unauthenticated API / HTTP Basic Client

For clients expecting HTTP Basic, the server can return **`401 Unauthorized`** with a `WWW-Authenticate: Basic ...` header instead of an HTML redirect. The client sends username/password in an `Authorization: Basic ...` header on the next request. Having both form login and HTTP Basic enabled does not force every client to receive the same response type: Spring Security selects an appropriate authentication entry point and can consider media types/`Accept`.

Note: **HTTP Basic only Base64-encodes the username/password pair; it does not encrypt transport**. Only send credentials over HTTPS in real environments; the `http://localhost` examples below are strictly for local learning.

### 4.3. Conceptual Processing Chain

```text
HTTP request
    |
    v
Servlet filter chain
    |
    v
Spring Security (DelegatingFilterProxy -> FilterChainProxy)
    |
    +-- Matching public resource, e.g. GET /login when form login is enabled
    |       -> Security filter can generate the login page
    |
    +-- Resource requiring authentication
            |
            +-- Unauthenticated
            |       -> HTML browser: usually redirects to /login
            |       -> Basic/API: usually 401 challenge
            |
            +-- Authenticated
                    -> check authorization
                    -> controller/servlet
```

The diagram only illustrates main branches, not an exact list of every filter. Spring Security's **`SecurityFilterChain`** represents a set of filters and matchers for a request; **`jakarta.servlet.FilterChain`** is the contract for continuing processing at the servlet layer. They relate to each other but are not the same type.

## 5. Minimal Practice: A Spring Boot App with a Protected Endpoint

This example runs standalone with **JDK 17+, Gradle**, and internet access to download dependencies on the first build. We intentionally **omit** `SecurityFilterChain`, `UserDetailsService`, `AuthenticationProvider`, and `spring.security.user.*` so we can observe the real defaults.

Directory structure:

```text
security-default-demo/
├── build.gradle
├── settings.gradle
└── src/main/java/example/
    ├── DemoApplication.java
    └── HelloController.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'security-default-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

File `src/main/java/example/DemoApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

File `src/main/java/example/HelloController.java`:

```java
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from protected endpoint";
    }
}
```

Use a Gradle 8.x version compatible with Spring Boot 3.3.x, such as Gradle 8.5. Inside the project directory, if a Gradle wrapper is already present, run `./gradlew bootRun` on macOS/Linux or `.\gradlew.bat bootRun` on Windows PowerShell. If you only have the files from the layout above and a compatible Gradle installed, use:

```bash
gradle bootRun
```

**Observe on startup:** the application usually logs the auto-generated password. Read the value directly from the running terminal and keep it private. Do not copy passwords into source code to test. Because the password is random and logs vary by timestamp/port, this guide **does not show a purported exact stdout**.

### 5.1. Testing the Browser Flow

1. Open `http://localhost:8080/hello` in an unauthenticated browser session. With an HTML flow, the browser is typically redirected to `http://localhost:8080/login`.
2. On the default login form, enter username `user` and the password printed in the startup terminal.
3. Log in successfully and visit `/hello` again. The HTTP body is the text:

```text
Hello from protected endpoint
```

If the browser navigates to `/` after login when the example only defines `/hello`, you may see **404** on `/` even though authentication succeeded. Reopen `/hello` to check the endpoint; do not conclude that a 404 is always a password failure.

### 5.2. Testing HTTP Basic with curl

In another terminal, try a normal request:

```bash
curl -i -H "Accept: application/json" http://localhost:8080/hello
```

With this default setup, an unauthenticated client requesting JSON typically receives `401 Unauthorized`; specific headers and body may vary depending on how the framework selects the entry point. If requesting HTML, the result can be `302 Found` with `Location: .../login`.

Next, send credentials with HTTP Basic. Use `--user user` **without a colon and password** so curl prompts interactively, avoiding recording credentials in shell history:

```bash
curl -i --user user http://localhost:8080/hello
```

When curl prompts for a password, enter the value generated in the startup log. On successful authentication, the response typically returns `HTTP 200` with body:

```text
Hello from protected endpoint
```

**Windows PowerShell:** use `curl.exe` instead of `curl` if your environment has a PowerShell alias instead of the real curl binary:

```powershell
curl.exe -i --user user http://localhost:8080/hello
```

Do not use existing production passwords when testing over plain HTTP. The goal of this exercise is to observe default request protection on `localhost`.

### 5.3. Why Is No Security Config Needed?

The `spring-boot-starter-security` dependency activates the relevant auto-configuration ecosystem. Spring Security inserts security filters into the Servlet filter chain; Spring Boot provides a default web chain and default in-memory user **as long as the applicability conditions hold**.

The controller only knows how to return content when invoked. Redirecting, Basic challenging, or blocking requests happens **before the controller executes**, not because `@GetMapping` checks passwords on its own.

## 6. Changing Name or Password via Properties: What Actually Changes

Spring Boot provides commonly used properties for the **default user**:

```properties
spring.security.user.name=learner
spring.security.user.password=local-demo-password
spring.security.user.roles=USER
```

In an application with no custom user source, this configuration gives the default user the name `learner` with the configured password. Consequently Boot **no longer needs to generate a random password** for this same configuration, and the “Using generated security password” message may disappear. `roles=USER` is the common default role; listed here to illustrate the property.

**Use the values above only for local learning environments.** In real projects, do not commit plaintext passwords to a repository, do not print them to logs or docs, and do not share a single account across everyone. If you genuinely need configured secrets, use an appropriate secret management / environment configuration mechanism. For real user management, provide a `UserDetailsService`, authentication provider, or identity solution matching system requirements.

**Distinguishing behavior:**

- Changing `spring.security.user.name` / `password` alters credentials of the **default user**; it does not automatically create new authorization policies.
- Adding a custom `UserDetailsService` causes Boot's default user mechanism to back off; the properties above do not force other providers to use them.
- Adding a `SecurityFilterChain` can change which URLs require protection or how login works; it does not automatically remove the in-memory user if no separate authentication source is configured.
- Removing `spring-boot-starter-security` or altering auto-configuration is not the right way to define an intentional security policy for a production application.

## 7. What Changes When You Declare a `SecurityFilterChain` Yourself?

Suppose you need to add a public endpoint. Then the application can declare its own security filter chain. The following file is an **optional alternative configuration**, not present in section 5's application; to run it separately, add `src/main/java/example/WebSecurityConfig.java` to the project:

```java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain appSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated());

        http.formLogin(Customizer.withDefaults());
        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

The example only configures protection policy; if you want `/public` to return data, the application still needs a corresponding controller/mapping. `requestMatchers("/public").permitAll()` **does not create an endpoint by itself**.

When an application-provided `SecurityFilterChain` bean is present, Boot's default **web security chain** backs off. In the class above, we **explicitly re-enabled** `formLogin` and `httpBasic` to retain both mechanisms; if you omit `formLogin(...)`, do not expect the default login page to still be generated just because the Security dependency is present.

This configuration **does not declare a `UserDetailsService`**, so Boot can still supply `user` and an auto-generated password under the relevant authentication conditions. This is a direct illustration of the independence between the **HTTP chain** and the **user store**.

## 8. CSRF, Sessions, and Distinguishing Response Codes

### 8.1. What Effect Does Default-Enabled CSRF Have?

In a standard Servlet application using Spring Security, **CSRF protection** is enabled by default. State-changing HTTP methods, such as `POST`, `PUT`, `PATCH`, or `DELETE`, typically require a valid CSRF token unless intentionally exempted.

- Spring Security's generated login form is capable of including a token field matching the CSRF configuration.
- Sending `POST /login` via `curl` without the matching CSRF token/cookie can return **403 Forbidden** before password verification even runs.
- Sending an API `POST` without a CSRF token can also return 403; that does not prove the username/password is wrong.
- Do not disable CSRF application-wide just to make one `POST` example work; understand the session, cookie, and CSRF threat model before changing configuration.

In the `GET /hello` example, observing Basic authentication avoids dealing with CSRF tokens and keeps focus on default behavior.

### 8.2. Form Login Is Usually Paired with Sessions

When authenticating via form login, Spring Security can store the login state associated with an HTTP session so users do not have to re-enter passwords on every request. The browser sends a session cookie (typically `JSESSIONID` in Servlet apps), and the application loads the security context on subsequent requests according to the security context configuration.

HTTP Basic usually sends credentials on **every request** and is not synonymous with session-based login. Yet do not automatically assume every configuration supporting Basic is completely stateless: that still depends on `SessionCreationPolicy` and how the application manages context.

### 8.3. Quick-Reference Table When Testing

| Test case | Typical outcome with default configuration | Key point to understand |
| --- | --- | --- |
| `GET /login` via browser | HTTP 200 and HTML form | Security-generated page when form login is enabled and no custom login page exists |
| `GET /hello`, unauthenticated, prefers HTML | `302` redirect to `/login` | Unauthenticated; browser follows redirect |
| `GET /hello`, unauthenticated, suitable API client | HTTP `401`, usually with Basic challenge | Differs from HTML redirect due to entry point selection |
| `GET /hello`, valid Basic credentials | HTTP `200`, body `Hello from protected endpoint` | Filter lets request reach controller |
| `GET /hello`, invalid Basic credentials | HTTP `401` or equivalent entry point handling | Authentication failed; not a “broken controller” |
| State-changing `POST`, missing CSRF token | Usually `403` | CSRF can block before controller logic |

These are **common behaviors**, not a guaranteed snapshot of every header, cookie, redirect URL, or status across every configuration. To draw conclusions on a real case, record request method, URL, `Accept`, cookie state, security config, and logs.

## 9. Common Errors and Cause-Based Diagnosis

**1. “I just added the Security starter and every endpoint requires login.”** That is usually the default `anyRequest().authenticated()` policy. Check whether a custom `SecurityFilterChain` is configured and whether any public endpoints need `permitAll()`. Do not disable all security just to expose one health/public endpoint.

**2. “Cannot find the generated password in the logs.”** Check the full startup log, logger settings, `spring.security.user.password`, and authentication beans like `UserDetailsService` / `AuthenticationProvider`. If the authentication source is provided by the application, there may be no default generated password to look for.

**3. “Why is there still a login page when I have no `/login` controller?”** The page may be generated and returned by `DefaultLoginPageGeneratingFilter` in the filter chain. That is framework behavior, not Spring MVC discovering a view file.

**4. “Visiting `/login` gives 404 or has no form.”** Check whether you created a `SecurityFilterChain` and forgot `formLogin(...)`, whether you changed the login page/login URL, or whether the setup only uses HTTP Basic or OAuth2/resource server. Do not assume every app with the Security starter uses form login.

**5. “The browser redirects with `302`, while curl gets `401`.”** This can be expected because the framework distinguishes HTML interactions from API clients. Compare `Accept`, `Content-Type`, cookies, login state, and the `WWW-Authenticate` header; do not treat two different responses as contradictory.

**6. “Login credentials are valid, yet POST still returns `403`.”** Check the CSRF token and corresponding session/cookie, especially when sending POST manually or from an API client. HTTP `403` does not mean wrong password; inspect which security filter decided the response.

**7. “After changing `SecurityFilterChain`, the default user still exists.”** Because the default web chain and the default user service are governed by different auto-configurations. To replace the user store, define an appropriate authentication source.

**8. “Logged in, yet visiting `/` returns 404.”** The application may not have mapped `/`. 404 means route not found, distinct from 401/403; visit the actual endpoint and check saved-request redirects.

**9. “The old password stopped working after restart.”** If you are using a new generated password on each startup, this behavior is expected. Do not save or reuse a previous run's password as a static credential.

**10. “Want to use the default user for production.”** That is a learning setup lacking account lifecycle management, secure password changes, real access policies, and other administrative controls. Design explicit authentication/authorization for the target environment.

## 10. Quick Verification Workflow When Starting a Servlet Security Module

1. Verify the application truly includes `spring-boot-starter-security` and runs on the **Servlet** stack, not confused with Spring WebFlux.
2. Check whether a custom `SecurityFilterChain` bean or another library's security configuration exists; if so, default web behavior may have changed.
3. Check for a custom `UserDetailsService`, `AuthenticationProvider`, `AuthenticationManager`, or authentication source; if present, do not assume `user` is active.
4. If the default user is created, read the password from the **current startup's** log; never commit it to Git or share terminal logs.
5. Open a known-existing endpoint in an unauthenticated browser, then inspect `/login`; compare with a `curl` request sending `Accept: application/json`.
6. Log in using `user` and the logged password; verify the endpoint returns the expected content after authentication.
7. When debugging `401`/`302`/`403`/`404`, distinguish **unauthenticated**, **starting login flow**, **CSRF/authorization denied**, and **no mapping found**.

## 11. Self-Check Questions

**Question 1.** Why can merely adding the Security dependency cause a `/hello` controller to require login?

**Answer:** Boot auto-configures a web `SecurityFilterChain` when none is supplied by the application; by default it requires HTTP requests to be authenticated and enables form login and HTTP Basic.

**Question 2.** Does the default username/password come from a database? Is the old password guaranteed to still work after a restart?

**Answer:** The default user usually lives in `InMemoryUserDetailsManager`, not a database. A generated password can change on restart, so it must not be treated as a fixed credential.

**Question 3.** Is it mandatory to write a `@GetMapping("/login")` controller to see the default page?

**Answer:** No. When form login is enabled and no custom page exists, Spring Security can generate the page itself via a security filter.

**Question 4.** Does creating a custom `SecurityFilterChain` guarantee the `user` account disappears?

**Answer:** No. The web chain and default user source have separate back-off conditions. Replacing the chain does not automatically replace the user store.

**Question 5.** Why does `curl` return `401` while a browser redirects to `/login` for the same endpoint?

**Answer:** Spring Security can select an authentication entry point based on request type and media type; an HTTP Basic challenge and a form login redirect are both valid ways to initiate authentication.

**Question 6.** When a manual login POST gets `403`, can you conclude the entered password was wrong?

**Answer:** No. Check the CSRF token/cookie first. CSRF can reject the request before the framework even processes credentials.

## 12. Takeaways

- Spring Boot Servlet default web security is typically **authenticated requests + form login + HTTP Basic**, provided no custom `SecurityFilterChain` replaces it.
- The default authentication user typically has **username `user`, role `USER`, and a generated password printed in the startup log**, provided it has not been replaced by a custom account/provider configuration.
- **`/login` can be filter-generated**; no custom view/controller is needed in the default example.
- HTML browsers may receive redirects while API clients may receive HTTP Basic challenges; **302, 401, 403, and 404** must be distinguished in context.
- Setting `spring.security.user.*` helps local testing; production configurations require properly designed account sources, credential storage, and access policies.
