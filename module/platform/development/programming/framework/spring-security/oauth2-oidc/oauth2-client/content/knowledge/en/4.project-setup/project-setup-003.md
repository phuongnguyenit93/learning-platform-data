# 4.3. OAuth2 Client Dependencies for a WebFlux Application

## 1. Purpose of the Setup Step

When building a **Spring Boot WebFlux** application that lets users log in via OAuth 2.0/OpenID Connect (OIDC), you must put the right libraries on the classpath so Spring Security can:

1. Initialize and manage an **OAuth 2.0 Client** (client ID, client secret, authorization endpoint, token endpoint, scopes).
2. Redirect the browser to the Authorization Server/OpenID Provider for login.
3. Receive the callback containing the **authorization code**, exchange the code for tokens, and create a login session in the reactive application.
4. Verify the **ID Token** when the request includes the `openid` scope.
5. If needed, attach an access token to outgoing HTTP requests using `WebClient`.

Choosing the right dependencies is crucial because **WebFlux uses a reactive programming model**, with components such as `ServerHttpSecurity`, `SecurityWebFilterChain`, `Mono`, `Flux`, and `WebClient`. Servlet-style security configuration examples using `HttpSecurity`, `SecurityFilterChain`, `HttpServletRequest`, or the Servlet `OAuth2AuthorizedClientManager` cannot be copied directly into a WebFlux application.

This lesson focuses on **dependencies and the minimal configuration required to start an OAuth2/OIDC Client on WebFlux**. External servers — the Authorization Server and the API/Resource Server — are separate systems and do not need to be implemented in the same application.

## 2. Three Core Dependency Groups

For a Spring Boot WebFlux application acting as an OAuth2/OIDC Client, you typically need:

| Group | Spring Boot Dependency | Purpose |
|---|---|---|
| Reactive web stack | `spring-boot-starter-webflux` | Provides Spring WebFlux, Reactor, and a reactive web runtime (typically Reactor Netty). |
| Spring Security | `spring-boot-starter-security` | Provides authentication infrastructure, HTTP protection, and Spring Security integration. |
| OAuth 2.0 / OIDC Client | The OAuth2 Client starter matching your Boot version | Provides OAuth2 Client and OIDC login components, registrations, and token handling. |

**The OAuth2 Client starter name changes by Spring Boot line:**

- **Spring Boot 3.x:** `org.springframework.boot:spring-boot-starter-oauth2-client`.
- **Spring Boot 4.x:** `org.springframework.boot:spring-boot-starter-security-oauth2-client` is recommended. The old name `spring-boot-starter-oauth2-client` is kept in Boot 4.0 but marked **deprecated**.

This change relates to **Spring Boot** starter artifact names, not a change in the OAuth 2.0 standard or how OIDC login works. Use the **one** OAuth2 Client starter matching the Boot line your project uses; do not declare both the old and new starters together.

**Do you need to declare `spring-boot-starter-security` explicitly?** The OAuth2 Client starter typically pulls in the relevant Security components transitively; in a learning project or production application, declaring the Security starter explicitly makes clear that the application actively uses HTTP security protection. When optimizing real-world dependencies, inspect the dependency graph to avoid misinterpreting transitive dependencies.

## 3. Gradle Configuration for Spring Boot 3.x

### 3.1. Gradle Groovy DSL — `build.gradle`

When the project has already been created with the Spring Boot Gradle plugin and corresponding dependency management, the basic `dependencies` block can look like:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Each line means:

- `spring-boot-starter-webflux` sets up the HTTP server/reactive controllers and `Mono`/`Flux` response types.
- `spring-boot-starter-security` enables registering reactive HTTP security filter chains and handling authentication and authorization.
- `spring-boot-starter-oauth2-client` adds OAuth2 login, token exchange, client registration, and OIDC support.
- `spring-boot-starter-test` supports Spring Boot application testing (not required for OAuth2 login to work at runtime).
- `reactor-test` provides reactive testing utilities such as `StepVerifier`.
- `spring-security-test` supports testing security, principals, and the security context.

**Do not add separate versions** to individual Spring starters when the project uses the Spring Boot plugin/BOM for dependency version management. Declaring Spring Security versions incompatible with Spring Boot can cause classpath and bean creation errors.

If the project only needs to run the application and has no tests yet, the first three `implementation` dependencies are the core of this lesson. Test dependencies are helpful additions for development.

### 3.2. Gradle Kotlin DSL — `build.gradle.kts`

If the project uses Kotlin DSL instead of Groovy DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

This is the exact same dependency set, only in Gradle Kotlin DSL syntax. Pick the DSL matching your build file; do not create both `build.gradle` and `build.gradle.kts` with duplicate declarations for one project.

## 4. Gradle Configuration for Spring Boot 4.x

Spring Boot 4 reorganizes some starter names by feature. For OAuth2 Client, use the **`spring-boot-starter-security-oauth2-client`** artifact instead of the deprecated name.

### 4.1. Gradle Groovy DSL — Boot 4.x

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-security-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-webflux-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-security-oauth2-client-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Feature-scoped test starters are part of Spring Boot 4's new dependency organization; depending on your test scope, you may also need `spring-security-test`. They are **not required** to run the OAuth2 Client web application.

### 4.2. Gradle Kotlin DSL — Boot 4.x

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-security-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-webflux-test")
    testImplementation("org.springframework.boot:spring-boot-starter-security-oauth2-client-test")
    testImplementation("io.projectreactor:reactor-test")
}
~~~

You do not need to add both `spring-boot-starter-security-oauth2-client` and `spring-boot-starter-oauth2-client`. When upgrading from Boot 3 to Boot 4, renaming the dependency is a simple and clear step; follow the Spring Boot upgrade guide for other changes across the project.

> **Version scope:** The Boot 3.x and Boot 4.x examples represent two dependency lines. Do not mix Boot 3 plugin/BOM versions with Boot 4 starters, or vice versa. Pick the Spring Boot line your application uses and let that line's BOM/plugin manage library versions.

## 5. Corresponding Maven Configuration

When the application is built with Maven, similar dependencies live in `pom.xml`.

### 5.1. Maven — Spring Boot 3.x

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This example assumes the project uses `spring-boot-starter-parent` or imports the corresponding Spring Boot BOM, so `<version>` is not written manually on each dependency.

### 5.2. Maven — Spring Boot 4.x

When using Boot 4.x, the two application dependencies `webflux` and `security` stay the same; change the OAuth2 Client starter as follows:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security-oauth2-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security-oauth2-client-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Maven does not require a separate "OAuth2 OIDC Client starter": Spring Security's OAuth2 Client library supports both OAuth 2.0 and OpenID Connect login. Whether OIDC or plain OAuth2 is used is determined by **client registration, scopes, and provider configuration**, not by a second OIDC dependency.

## 6. Which Dependencies Sit Underneath the Starters?

A starter is a curated set of dependencies designed to work together. In a WebFlux + OAuth2 Client application, key modules that may appear in the dependency tree include:

| Module | Role |
|---|---|
| `spring-webflux` | HTTP server/reactive web framework, handlers, routers, `WebClient`. |
| `reactor-core` | Reactive types `Mono` and `Flux`, asynchronous programming operators. |
| `reactor-netty` | Non-blocking network runtime typically pulled in by default by the WebFlux starter. |
| `spring-security-config` | Spring Security configuration APIs, including reactive security support. |
| `spring-security-web` | Web security infrastructure; reactive classes and web integration. |
| `spring-security-oauth2-core` | Core OAuth 2.0 models and data types. |
| `spring-security-oauth2-client` | Client registration, OAuth2 Login, and client/token workflows. |
| `spring-security-oauth2-jose` | JWT/JWS/JWK support used in OAuth2/OIDC scenarios, including ID Token handling. |

You do not need to re-declare each module directly when the starter already manages them. Dropping starters to assemble modules manually means the developer must manage version compatibility and missing components; that is an advanced option rarely needed at project setup.

### 6.1. Without Spring Boot

A plain Spring WebFlux application (without Boot) can declare modules directly, such as `spring-webflux`, `spring-security-config`, `spring-security-web`, `spring-security-oauth2-client`, and required token/JOSE dependencies. However, **there is no Spring Boot auto-configuration or default property binding**, so you must explicitly define beans like `ReactiveClientRegistrationRepository`, the security filter chain, and authorized client storage.

When starting a project to learn Spring Security, using Spring Boot starters is usually clearer and requires less boilerplate.

## 7. Dependencies Alone Do Not Turn an App into a Complete OAuth2 Client

Adding the OAuth2 Client starter only puts **processing capabilities** onto the classpath. To actually log in, the application needs at least:

- A **client registration** specifying the provider, client ID, secret or client authentication method, scopes, and redirect URI.
- A real **Authorization Server/OpenID Provider** to issue codes and tokens.
- A **reactive security chain** configuration tailored for WebFlux, if the application customizes paths or authorization rules.

With Spring Boot, registrations are typically declared in `application.yml` or `application.properties`. Boot can create a `ReactiveClientRegistrationRepository` from those properties, helping Spring Security connect the client and provider.

## 8. Example `application.yml` for a WebFlux OIDC Client

Suppose the application runs at `https://app.example.com` and logs in via a provider with issuer `https://id.example.com`. The client registration ID is `demo`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          demo-provider:
            issuer-uri: https://id.example.com
~~~

`OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` should be supplied via environment variables or a suitable secret management mechanism. Never write real secrets into the repository.

### 8.1. Meaning of Each Configuration Group

| Property | Role |
|---|---|
| `registration.demo` | Names the registration; uses `demo` in the default initiation and callback URLs. |
| `provider: demo-provider` | Links the client registration to the declared OpenID Provider details. |
| `client-id` | Client identifier issued by the provider. |
| `client-secret` | Confidential client secret, stored on the server. |
| `client-authentication-method` | How the client authenticates at the token endpoint in this example. |
| `authorization-grant-type` | Selects `authorization_code`, suitable for browser-based user login. |
| `redirect-uri` | Callback URL where the provider redirects the browser after issuing the code. |
| `scope` | `openid` enables OIDC, while `profile`/`email` request extra claims if supported by the provider. |
| `issuer-uri` | OP identifier and starting point for OIDC metadata discovery. |

When the issuer supports OIDC Discovery, Spring Security can resolve the authorization endpoint, token endpoint, JWK Set URI, UserInfo endpoint, and related metadata from `issuer-uri`. If the provider only supports plain OAuth2 without corresponding discovery, declare the appropriate endpoints manually.

### 8.2. Redirect URI Must Match the Provider

With registration `demo`, the default callback is:

~~~text
https://app.example.com/login/oauth2/code/demo
~~~

This path must be registered for the client at the provider. When running locally on `localhost:8080`, the callback can be:

~~~text
http://localhost:8080/login/oauth2/code/demo
~~~

Providers may allow HTTP localhost callbacks for development; in real deployments, use HTTPS and a public host. If the app runs behind a reverse proxy, configure trusted forwarded headers so `{baseUrl}` resolves to the correct external scheme/host/port.

### 8.3. OAuth2 Client Differs from OIDC Client by Scope

A registration requesting only API scopes like `read:orders` can be a pure OAuth2 Client. When the request includes `openid`, Spring Security handles it as **OIDC Login**, using the ID Token to authenticate the user's identity.

**You do not need an extra dependency named "OIDC starter"** just to receive an ID Token. The OAuth2 Client starter already provides OIDC support; the provider must actually support OIDC and return a compliant ID Token.

## 9. Minimal Reactive Spring Security Configuration

In WebFlux, the central bean is **`SecurityWebFilterChain`**, configured via **`ServerHttpSecurity`**. This is the reactive model—do not use `SecurityFilterChain` and `HttpSecurity` from Servlet applications.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Explanation:

- `@EnableWebFluxSecurity` enables web security support for WebFlux; the application has explicit security configuration and control over the filter chain.
- `SecurityWebFilterChain` replaces the servlet `SecurityFilterChain`.
- `authorizeExchange(...)` defines which URLs require authentication.
- `oauth2Login(...)` enables browser-based user login via OAuth2/OIDC.
- `oauth2Client(...)` enables support for OAuth2 authorized clients when the app needs to acquire/attach access tokens to call external APIs.
- `build()` constructs the chain for WebFlux to use.

If the app only requires OIDC Login and makes no outbound API calls yet, configuring only `oauth2Login(...)` may suffice. `oauth2Client(...)` adds support for working with authorized clients; the two APIs serve different roles and can be combined.

**Why not use the Servlet example?**

| WebFlux/reactive | Servlet/MVC |
|---|---|
| `ServerHttpSecurity` | `HttpSecurity` |
| `SecurityWebFilterChain` | `SecurityFilterChain` |
| `authorizeExchange` | `authorizeHttpRequests` |
| `ReactiveClientRegistrationRepository` | `ClientRegistrationRepository` |
| `ReactiveOAuth2AuthorizedClientManager` | `OAuth2AuthorizedClientManager` |
| `WebFilter` / reactive security chain | Servlet Filter / servlet security chain |
| `WebClient` with reactive authorized-client filter | `RestClient` or suitable integrated client for Servlet |

Mixing up types from this table easily leads to compilation errors, missing beans, or the application actually running on the servlet stack.

## 10. Once Dependencies Are Present, Where Does the Login Flow Go?

With Spring Security WebFlux configured as above, a typical OIDC login flow looks like:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Browser
    participant W as Spring Boot WebFlux
    participant OP as OIDC Provider
    participant API as Resource Server

    U->>W: GET /private
    W-->>U: Redirect to initiate login
    U->>W: GET /oauth2/authorization/demo
    W-->>U: 302 to authorization endpoint
    U->>OP: Authorization request
    OP->>U: Login / consent
    OP-->>U: 302 callback?code=...&state=...
    U->>W: GET /login/oauth2/code/demo?code=...&state=...
    W->>OP: POST token endpoint (exchange code)
    OP-->>W: Access token + ID Token
    Note over W: Validate token, create reactive Authentication
    W-->>U: Application login session
    W->>API: WebClient + Bearer access token
    API-->>W: Data
    W-->>U: Page content / response
~~~

Common endpoints:

| Path/Endpoint | Owner | Function |
|---|---|---|
| `/oauth2/authorization/demo` | Spring WebFlux Application | Initiates the authorization request via the provider with registration ID `demo`. |
| Authorization endpoint, e.g., `https://id.example.com/authorize` | OP/Authorization Server | Receives login/consent requests. |
| `/login/oauth2/code/demo` | Spring WebFlux Application | Receives the authorization code and continues authentication. |
| Token endpoint, e.g., `https://id.example.com/token` | OP/Authorization Server | Exchanges code for tokens, authenticates the client, and validates protocol conditions. |
| `https://api.example.com/...` | Resource Server | Validates the access token sent by `WebClient`. |

**Dependencies only give Spring Security the ability to execute the flow**; they do not replace registering the client with the provider, configuring callbacks, provisioning secrets, or defining scopes.

## 11. Reading the Logged-In User Reactively

When OIDC Login completes, Spring Security stores the principal in the reactive security context. A simple controller reading `OidcUser`:

~~~java
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal OidcUser user) {

        return Map.of(
            "subject", user.getSubject(),
            "issuer", user.getIssuer().toString()
        );
    }
}
~~~

This example only applies when `/me` is protected and the user logged in via OIDC. If the `openid` scope is absent or the principal is another OAuth2 type, do not blindly cast to `OidcUser`.

A WebFlux controller method can return `Mono<T>`, `Flux<T>`, or a plain value when the operation is immediate. Reading a few in-memory claims does not need to be wrapped artificially in `Mono`. When accessing a database, calling an API, or performing I/O, use appropriate reactive drivers/APIs and avoid blocking the event loop.

To reduce data exposure risk, return only the claims needed; do not return raw ID Tokens, access tokens, or refresh tokens to the browser just to prove login succeeded.

## 12. Why Is `WebClient` Needed and How Does It Relate to OAuth2 Client?

Spring WebFlux includes **`WebClient`**, an HTTP client built on reactive streams. When the application needs to call APIs protected by Bearer tokens, Spring Security provides `ServerOAuth2AuthorizedClientExchangeFilterFunction` to attach an authorized client's token to outgoing requests.

Example `WebClient` configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfig {

    @Bean
    WebClient apiWebClient(
            ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {

        var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
            authorizedClientManager
        );

        return WebClient.builder()
            .baseUrl("https://api.example.com")
            .filter(oauth2)
            .build();
    }
}
~~~

A service using the configured `WebClient`:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

@Service
public class ProfileApiClient {

    private final WebClient apiWebClient;

    public ProfileApiClient(WebClient apiWebClient) {
        this.apiWebClient = apiWebClient;
    }

    public Mono<String> fetchProfile() {
        return apiWebClient.get()
            .uri("/v1/profile")
            .attributes(clientRegistrationId("demo"))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

`clientRegistrationId("demo")` selects the client configuration Spring Security uses to look up the authorized client/token in the current context. This example assumes the user has logged in and the corresponding authorized client can be retrieved. With the `authorization_code` grant, an initial interactive authorization flow is required; you cannot automatically fetch a user-delegated token from a background job that has no principal/authorization context.

When calling APIs with **client credentials** (not on behalf of a user), the authorized client manager, principal, and registration must be configured appropriately for service-to-service communication; do not use user OIDC login configuration as a workaround.

### 12.1. Remember the Separation of Responsibilities

- `spring-boot-starter-webflux` brings in `WebClient`, but knows nothing about client IDs or OAuth2 tokens.
- The OAuth2 Client starter provides the authorized-client infrastructure, but does not automatically decide which APIs need access tokens.
- `ServerOAuth2AuthorizedClientExchangeFilterFunction` bridges `WebClient` and OAuth2 authorized client management.
- The Resource Server/API still validates the access token and checks permissions; a user's successful login on the client does not bypass API authorization checks.

## 13. Do Not Confuse OAuth2 Client with Resource Server or Authorization Server

This is a common dependency-selection mistake when getting started with Spring Security OAuth2.

| What does the app need to do? | Feature Group Needed | Boot 3.x Starter | Boot 4.x Starter |
|---|---|---|---|
| Log users in via an OP; exchange code for tokens; call APIs on users' behalf | **OAuth2/OIDC Client** | `spring-boot-starter-oauth2-client` | `spring-boot-starter-security-oauth2-client` |
| Accept Bearer access tokens from callers and protect its own API | **OAuth2 Resource Server** | `spring-boot-starter-oauth2-resource-server` | `spring-boot-starter-security-oauth2-resource-server` |
| Issue authorization codes and access tokens itself, and run authorization endpoints | **Authorization Server** | Version-matching Spring Authorization Server starter or module | `spring-boot-starter-security-oauth2-authorization-server` |

One application can play multiple roles when genuinely required, but **this lesson only needs OAuth2 Client** for OIDC login through an external provider.

For example: WebFlux application A lets users log in with IdP B and then calls API C.

~~~text
[Browser]
      |
      v
[WebFlux A] ------- OAuth2 authorization code --------> [IdP B]
  OAuth2 Client <------- ID / access tokens ------------
      |
      | Bearer access token
      v
[API C: Resource Server]
~~~

WebFlux A does not need `oauth2-resource-server` just because it **sends** an access token to API C. It only needs resource-server capabilities if A itself must **receive and validate** Bearer tokens from incoming callers.

Similarly, WebFlux A does not need to run its own Authorization Server just because it redirects the browser to IdP B.

## 14. Reactive WebFlux vs. Servlet MVC: Choosing the Right Web Stack

### 14.1. Do Not Add the Servlet Web Starter If Your Target Is Reactive WebFlux

In Spring Boot 3.x, the traditional MVC starter is `spring-boot-starter-web`; Spring Boot 4.x recommends `spring-boot-starter-webmvc`. If both MVC and WebFlux starters are added to a project, Spring Boot may choose **Servlet web application** through standard precedence/auto-configuration, preventing WebFlux security configuration from applying as expected.

Therefore, when designing an end-to-end WebFlux application, the foundational dependencies should be:

~~~text
spring-boot-starter-webflux
spring-boot-starter-security
OAuth2 Client starter for your Spring Boot version
~~~

Only add the MVC starter when the project genuinely targets the Servlet stack. An MVC application **can** use `WebClient` for non-blocking HTTP calls without becoming a WebFlux server application. Having `WebClient` on the classpath does not prove the server runs reactively.

### 14.2. Quick Comparison

| Characteristic | Spring WebFlux | Spring MVC |
|---|---|---|
| Web server programming model | Reactive/non-blocking across appropriate APIs and pipelines | Servlet request/response |
| Security chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Security configuration | `ServerHttpSecurity` | `HttpSecurity` |
| Common HTTP client | `WebClient` | `RestClient`, `WebClient`, or other clients |
| Authorization request repository | Reactive/`ServerWebExchange`-based | Servlet/HTTP session-based |
| Authorized client manager | `ReactiveOAuth2AuthorizedClientManager` | `OAuth2AuthorizedClientManager` |
| Principal in controller | Injectable from reactive security context | Injectable from servlet security context |

**The OAuth2 Client starter works for both web models**; whether Spring Security selects reactive or Servlet classes depends on the application type and configuration chain.

## 15. Common Dependency and Configuration Errors

### 15.1. Adding Only the WebFlux Starter Without the OAuth2 Client Starter

**Symptom:** no OAuth2 login configuration APIs are available, no client registration beans exist, or `/oauth2/authorization/demo` does not work as expected.

**Cause:** `spring-boot-starter-webflux` does not provide OAuth2 Client infrastructure on its own.

**Resolution:** add the OAuth2 Client starter matching your Spring Boot version. Verify the app has a client registration and security config.

### 15.2. Adding Only the Resource Server Starter

**Symptom:** the application is configured to validate incoming Bearer JWTs, with no OIDC client login redirect flow.

**Cause:** Resource Server and OAuth2 Client are two distinct roles.

**Resolution:** an app acting as a login client needs the OAuth2 Client starter and `oauth2Login()`, not `oauth2ResourceServer()`.

### 15.3. Using Spring Boot 4 While Copying Boot 3 Starters

**Symptom:** the build may still work because the old name exists, but `spring-boot-starter-oauth2-client` is deprecated in Boot 4.

**Resolution:** with Boot 4, switch to `spring-boot-starter-security-oauth2-client`; do not declare both.

### 15.4. Declaring `HttpSecurity` in a WebFlux Project

**Symptom:** security configuration mismatches, missing bean errors, or security rules do not behave as expected.

**Cause:** code uses Servlet APIs instead of reactive APIs.

**Resolution:** use `ServerHttpSecurity`, `SecurityWebFilterChain`, and `authorizeExchange`.

### 15.5. Using the Wrong `OAuth2AuthorizedClientManager` Type

**Symptom:** `WebClient` configuration does not match constructor/filter function signatures or Spring cannot find a suitable bean.

**Cause:** imported the Servlet `OAuth2AuthorizedClientManager` instead of `ReactiveOAuth2AuthorizedClientManager`.

**Resolution:** use the reactive manager and `ServerOAuth2AuthorizedClientExchangeFilterFunction`.

### 15.6. Missing Registration or Wrong `issuer-uri`

**Symptom:** the app cannot build a `ReactiveClientRegistrationRepository`, login fails to start, or metadata discovery fails at startup/request time.

**Cause:** `spring.security.oauth2.client.registration.*` is undeclared, the issuer is wrong, or the provider does not support OIDC Discovery.

**Resolution:** verify `client-id`, `scope`, `provider`, and `issuer-uri`; if the provider does not support discovery, declare endpoints explicitly per the provider's documentation.

### 15.7. Wrong Redirect URI

**Symptom:** the OP reports `invalid_redirect_uri` or redirects back to the wrong host/protocol.

**Cause:** callback configured at the provider does not match `{baseUrl}`, a proxy sends the wrong scheme/host, or the registration ID differs from the URL path.

**Resolution:** register the exact `/login/oauth2/code/demo` URI, configure trusted proxy/headers, and use HTTPS in production.

### 15.8. OAuth2 Login Works, but No ID Token Is Received

**Symptom:** only an OAuth2 principal is received, without an OIDC-specific user.

**Cause:** missing the `openid` scope, or the provider does not support OIDC.

**Resolution:** use a valid OIDC provider, request the `openid` scope, and use OIDC Login.

### 15.9. Adding Blocking HTTP Libraries onto the Event Loop

**Symptom:** the application slows down or latency spikes under high load despite using WebFlux.

**Cause:** calling `RestTemplate`, blocking JDBC, or `.block()` arbitrarily inside reactive pipelines.

**Resolution:** use appropriate reactive APIs/drivers. If you must call a blocking library, isolate it off the event loop with an appropriate scheduling strategy; the OAuth2 Client dependency does not automatically make all application I/O non-blocking.

### 15.10. Forgetting Environment-Specific Secrets and Scopes

**Symptom:** startup or token exchange fails with `invalid_client`; OIDC Login fails to produce the expected principal.

**Cause:** unset environment variable placeholders, wrong secret, wrong client authentication method, or scopes not granted by the provider.

**Resolution:** supply secrets through an approved mechanism, verify the client registration against the IdP, and ensure the `openid` scope is present for OIDC login.

## 16. Inspecting the Classpath and Detecting Duplicate Dependencies

To see what starters brought in, use your build system's dependency inspection tools.

### Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

On Windows:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

To trace a specific dependency:

~~~bash
./gradlew dependencyInsight --dependency spring-security-oauth2-client --configuration runtimeClasspath
~~~

### Maven

~~~bash
mvn dependency:tree
~~~

These commands reveal whether `spring-security-oauth2-client` is present, which version was selected, and whether multiple starters pull different parts onto the classpath. They are especially useful when upgrading Boot or when another library unexpectedly introduces Servlet/MVC dependencies.

Architecturally, verify three separate things: **having the OAuth2 Client module**, **running the app on WebFlux**, and **having registered the provider/client to perform login**. Having all dependencies ready does not equal having login fully configured.

## 17. Example WebFlux OAuth2/OIDC Client Project Structure

A minimal project can be organized as:

~~~text
spring-webflux-oidc-client/
├── build.gradle
├── settings.gradle
└── src/
    └── main/
        ├── java/com/example/oidc/
        │   ├── OidcClientApplication.java
        │   ├── SecurityConfig.java
        │   ├── MeController.java
        │   └── WebClientConfig.java
        └── resources/
            └── application.yml
~~~

- `OidcClientApplication` contains `@SpringBootApplication` and the `main` method.
- `SecurityConfig` defines the WebFlux `SecurityWebFilterChain`.
- `MeController` demonstrates reading the OIDC principal in an authenticated route.
- `WebClientConfig` is only needed when the application calls external APIs with tokens.
- `application.yml` defines OAuth2 client registrations, providers, and required properties.

Example main class:

~~~java
package com.example.oidc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcClientApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcClientApplication.class, args);
    }
}
~~~

You can start from Spring Initializr by selecting **Spring Reactive Web**, **Spring Security**, and **OAuth2 Client**. After generating the project, verify artifact names against your Boot version, especially the OAuth2 Client starter rename in Boot 4.

## 18. What Should You Expect When Running the Project?

With a properly configured provider, the application allows initiating login via:

~~~http
GET /oauth2/authorization/demo HTTP/1.1
Host: localhost:8080
~~~

Spring Security redirects to the OP's authorization endpoint. After the user authenticates and consents, the OP redirects the browser back to:

~~~text
/login/oauth2/code/demo?code=...&state=...
~~~

Spring Security uses the saved authorization request to validate the callback and exchanges the code at the token endpoint. For OIDC, the client also validates the ID Token, creates the principal, and stores the authenticated session. Upon returning to the protected route, the user uses the application-managed session.

In the browser, you typically observe **redirects** and callbacks; the backend's token endpoint request is not a browser-initiated `fetch()` call in the confidential web client model.

Without an IdP or without proper client ID/secret/redirect URI configuration, the application may build cleanly while login still fails. That is the difference between **dependency readiness** and **OAuth2/OIDC integration readiness**.

## 19. Takeaways When Choosing Dependencies

| If your goal is… | You need to prepare |
|---|---|
| Build a reactive HTTP server | `spring-boot-starter-webflux`. |
| Protect application routes using the reactive model | `spring-boot-starter-security` and `SecurityWebFilterChain`. |
| Let users log in via OAuth 2.0/OIDC through an external provider | OAuth2 Client starter matching your Spring Boot line, registration, and `oauth2Login()`. |
| Call APIs using an access token | `WebClient` and appropriate authorized client management components, such as `ReactiveOAuth2AuthorizedClientManager`. |
| Protect your own API with inbound Bearer tokens | Add Resource Server capabilities per your requirements. |
| Run your own IdP/Authorization Server | Add Authorization Server capabilities in a dedicated service, not as a default client requirement. |

For a **Spring Boot WebFlux OAuth2/OIDC Client**, the three most important dependency groups are **WebFlux + Spring Security + OAuth2 Client**. The version-specific points to remember are:

- **Boot 3.x:** `spring-boot-starter-oauth2-client`.
- **Boot 4.x:** `spring-boot-starter-security-oauth2-client`.

Then use **`ServerHttpSecurity` and `SecurityWebFilterChain`** for the reactive app, declare **`spring.security.oauth2.client.registration`** with a real provider, and include the **`openid`** scope when the goal is OIDC Login. When calling downstream APIs, integrate **`WebClient`** with the OAuth2 authorized-client infrastructure.

## Official References

- [Spring Security — OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/) — scope of OAuth2 Login and OAuth2 Client in WebFlux.
- [Spring Boot — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html) — starter list across modern Spring Boot lines.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide) — starter name changes in Spring Boot 4.
- [Spring Security — Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/index.html) — reactive security configuration and related components.
