# 4.2. OAuth2 Client Dependencies for a Servlet Application

## 1. Purpose and Scope

For a **Spring Boot application using the Servlet stack** to log in via OAuth 2.0/OpenID Connect (OIDC), obtain tokens from an Authorization Server, and call external APIs on behalf of the user, you first need to put the right **Spring Security OAuth2 Client** libraries on the classpath.

This lesson focuses on **setting up dependencies**: choosing the starter for the right Spring Boot version, understanding the libraries pulled in, minimal configuration to verify integration, and avoiding confusion with a Resource Server or WebFlux application.

After this lesson, you should be able to distinguish:

- An **OAuth2 Client** application initiates login or requests an Access Token to call another system.
- A **Resource Server** application receives an Access Token and protects its own API.
- An **Authorization Server** application issues Authorization Codes, Access Tokens, or ID Tokens.
- A **Servlet web application** uses Spring MVC, Servlet Filters, and `SecurityFilterChain`; a **reactive web application** uses WebFlux, `SecurityWebFilterChain`, and the corresponding reactive APIs.

**One application can simultaneously be an OAuth2 Client and a Resource Server**, but those are two separate responsibilities; you do not need to add the Resource Server starter if you only want to log in with an OIDC provider.

## 2. Choosing the Right Dependencies by Spring Boot Version

Spring Boot provides *starters*: a dependency bundling commonly needed libraries, along with version management so you do not have to list individual Spring Security modules.

### 2.1. Quick Selection Table

| Context | Servlet/MVC Starter | OAuth2 Client Starter | Notes |
| --- | --- | --- | --- |
| **Spring Boot 3.x** | `org.springframework.boot:spring-boot-starter-web` | `org.springframework.boot:spring-boot-starter-oauth2-client` | Familiar starter naming set in Boot 3 |
| **Spring Boot 4.x** | `org.springframework.boot:spring-boot-starter-webmvc` | `org.springframework.boot:spring-boot-starter-security-oauth2-client` | Boot 4 splits/renames many starters for modularity; the two corresponding Boot 3 names are marked deprecated in Boot 4 |

Choosing **Boot 3 or Boot 4** must be based on your project's actual plugin/parent/BOM version. Do not arbitrarily mix starters from the two branches in a single build.

The examples below assume the project already has a Spring Boot Maven parent or Spring Boot Gradle plugin with matching dependency management/BOM. **Do not pin separate versions** for Spring Boot starters and individual Spring Security modules within the same managed version set.

### 2.2. Gradle Groovy DSL — Spring Boot 3.x

In `build.gradle` of a **Spring Boot 3.x project with plugin and dependency management configured**:

~~~groovy
dependencies {
    // Run HTTP server with Spring MVC + embedded Servlet container.
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // OAuth 2.0 Login, OIDC Login, and OAuth2 Client to call downstream APIs.
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // Testing (not included in the runtime artifact).
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

If the project already has `spring-boot-starter-web`, **keep the existing declaration** and just add the OAuth2 Client starter. You do not need to declare `spring-security-oauth2-client` and its transitive modules manually when using the starter.

### 2.3. Gradle Kotlin DSL — Spring Boot 3.x

In `build.gradle.kts`:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
~~~

The parentheses in Kotlin DSL are just different syntax from Gradle Groovy DSL; the dependency semantics are unchanged.

### 2.4. Maven — Spring Boot 3.x

In `pom.xml` with a Spring Boot parent or imported dependency management BOM:

~~~xml
<dependencies>
    <!-- Spring MVC, Servlet stack, embedded container -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <!-- OAuth2/OIDC Client -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>

    <!-- Test-only dependencies -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

When versions are managed via the Spring Boot parent/BOM, do not put `<version>` on each starter. If the project does not use the Spring Boot parent, import the BOM properly in `dependencyManagement`; otherwise, Maven may report missing dependency versions.

### 2.5. Gradle — Spring Boot 4.x

In a **Spring Boot 4.x** project with matching dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-security-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-security-test'
}
~~~

Boot 4 provides additional specialized test starters, such as `spring-boot-starter-security-oauth2-client-test`, when tests need corresponding OAuth2 Client test support.

Equivalent in **Gradle Kotlin DSL**:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webmvc")
    implementation("org.springframework.boot:spring-boot-starter-security-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-starter-security-test")
}
~~~

### 2.6. Maven — Spring Boot 4.x

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security-oauth2-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

**Note when migrating Boot 3 → Boot 4:** `spring-boot-starter-oauth2-client` and `spring-boot-starter-web` are kept as old names but are deprecated in Boot 4. For new Boot 4 projects, use the new starter names to avoid depending on deprecated artifacts later. Upgrading Spring Boot/Spring Security must be done consistently across the stack rather than changing one dependency and mixing versions.

## 3. Why Are Both the Servlet Web Starter and OAuth2 Client Starter Needed?

A Servlet-style OIDC login application typically has **two functional layers**:

~~~mermaid
flowchart TB
    P["Spring Boot Servlet Application"] --> W["Spring MVC / embedded Servlet container"]
    P --> S["Spring Security Filter Chain"]
    S --> O["OAuth2 Client / OIDC Login"]
    W --> C["Controller, view, session"]
    O --> AR["Authorization Request / Callback"]
    O --> TOK["ClientRegistration + AuthorizedClient + Tokens"]
    AR --> IDP["Authorization Server / OIDC Provider"]
    TOK --> API["External Resource Server"]
~~~

The **Servlet web starter** provides Spring MVC, HTTP request/response handling, and an embedded Servlet container (usually Tomcat), which are needed for UI endpoints and the login callback. The **OAuth2 Client starter** provides authorization, callback, token, and OIDC user data handling at the Spring Security layer.

Typical components included when using Spring Security OAuth2 Client:

| Component | Role |
| --- | --- |
| `spring-security-oauth2-client` | APIs and implementations for OAuth2 Client, OAuth2 Login, and OIDC Login |
| `spring-security-oauth2-core` | Core OAuth2 types such as Access Token, Authorization Grant, and protocol errors |
| `spring-security-oauth2-jose` | Support for JWT/JWS/JWK processing required by OAuth2/OIDC features |
| `spring-security-web` | Filters, filter chains, and web security mechanisms |
| `spring-security-config` | `HttpSecurity` DSL and configuration for Spring Security mechanisms |
| Spring Boot auto-configuration | Automatically creates/customizes beans based on classpath and `spring.security.oauth2.client.*` |

The exact transitive dependency list depends on the chosen version and starter; this is a functional relationship, **not a list to declare manually**. With Spring Boot 4, the new OAuth2 Client starter brings along the security components managed by Boot.

### When Is a Separate `spring-boot-starter-security` Needed?

You may declare the Spring Security starter to express your overall security intent clearly, but do not add it reflexively if the OAuth2 Client starter already pulls in the needed components. On Boot 4, the new OAuth2 Client starter already depends on the Spring Security starter. What you should inspect is the project's **actual dependency graph**, rather than assuming "more starters means more complete".

### Dependencies Usually Not Required

| Dependency | When should it be added? | Required for Servlet OAuth2 Login? |
| --- | --- | --- |
| `spring-boot-starter-thymeleaf` | Rendering login/profile pages with Thymeleaf templates | No; Spring Security can generate a default login page |
| `spring-boot-starter-actuator` | Health checks, metrics, operations | No |
| `spring-boot-starter-validation` | Validating request DTOs | No |
| `spring-boot-starter-oauth2-resource-server` (Boot 3) / `spring-boot-starter-security-oauth2-resource-server` (Boot 4) | The application **receives** bearer tokens and protects its own API | No, if it is only an OAuth2 Client |
| Corresponding Authorization Server starter | The application issues authorization codes/tokens to other clients | No |
| `spring-boot-starter-webflux` | Building a reactive app or needing `WebClient` per chosen design | Not just for configuring Servlet OAuth2 Client |
| `spring-security-test` or Boot 4's security test starter | Testing security filters, OAuth2 login, mock users | Test scope only |

## 4. Servlet Stack and Reactive Stack Are Two Different Models

Spring Security OAuth2 Client supports both Servlet and Reactive, but their classes and configurations are different.

| Criterion | Servlet / Spring MVC | Reactive / WebFlux |
| --- | --- | --- |
| Processing model | Servlet request, Spring MVC | Reactive pipeline |
| Security configuration | `SecurityFilterChain`, `HttpSecurity` | `SecurityWebFilterChain`, `ServerHttpSecurity` |
| Request context | `HttpServletRequest` and corresponding Spring SecurityContext | `ServerWebExchange` and Reactor Context |
| Authorized client manager | `DefaultOAuth2AuthorizedClientManager` / `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Reactive authorized client manager |
| OAuth2 Client login | `oauth2Login()` on `HttpSecurity` | `oauth2Login()` on `ServerHttpSecurity` |
| Common HTTP client | `RestClient` or `RestTemplate`; `WebClient` can be used if desired | `WebClient` |

**"OAuth2 Client" does not mean "Reactive Client".** For example, an application using `@RestController`, Spring MVC, and Tomcat can still be a complete OAuth2 Client. If you add both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot typically prioritizes the Servlet model when both are present, but you should not create a hybrid configuration just to try OAuth2.

When learning Servlet Client, import:

~~~java
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
~~~

Do not use `ServerHttpSecurity` or `SecurityWebFilterChain` in the same example.

## 5. From Dependencies to a Minimal OIDC Login Application

Starters only provide classes and auto-configuration. To run login, you also need to **register the client at an identity provider** and configure `ClientRegistration`.

### 5.1. Registering the Application at the OIDC Provider

Example Servlet backend running at `http://localhost:8080`:

| Setting | Example Value |
| --- | --- |
| Client type | Confidential web application (backend can keep a client secret) |
| Authorization grant | Authorization Code |
| Client ID | `demo-web` |
| Client secret | Configured locally or in a secret manager |
| Redirect URI | `http://localhost:8080/login/oauth2/code/demo` |
| Scope | `openid profile email` |
| Issuer | `https://id.example.com/realms/demo` |

The name `demo` is **Spring Security's registrationId**; `demo-web` is the **client ID registered at the provider**. The two values do not have to be identical. The provider must publish a real issuer and corresponding endpoints; the URLs in this lesson are illustrative.

### 5.2. Configuring `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          demo-provider:
            issuer-uri: https://id.example.com/realms/demo
~~~

When `issuer-uri` is set and the provider supports OIDC discovery, Spring can discover the authorization, token, UserInfo, and JWKS endpoints from the provider's metadata. **You do not need to manually declare every endpoint** if discovery works.

Notes:

- Load `client-id` / `client-secret` from environment variables or a secret management system; never commit secrets.
- `issuer-uri` must match the exact issuer published by the provider. Example paths will not work as-is for every provider.
- `openid` activates OIDC semantics; without `openid`, OAuth2 Login may still work with some providers, but you cannot assume an ID Token will be returned.
- `redirect-uri` must match the registered redirect URI (including scheme, host, port, and path).
- Running locally over HTTP is only for development if permitted by the provider; production should use HTTPS.

### 5.3. Configuring `SecurityFilterChain`

Example for Servlet-style Spring Security:

~~~java
package com.example.demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

`oauth2Login()` handles user login via authorization code/OIDC. `oauth2Client()` configures OAuth2 Client capabilities when you need to manage and use authorized clients to call APIs. An application that only uses client credentials in backend jobs without user login will need a different authorized-client manager flow; do not enable `oauth2Login()` as a mandatory requirement for every client.

You do not need to add `@EnableWebSecurity` just to run the example when Spring Boot already auto-configures the web/security components properly; use `SecurityFilterChain` to express URL protection policies.

### 5.4. Controller Reading the Verified OIDC Principal

~~~java
package com.example.demo.web;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {
    @GetMapping("/")
    public String home() {
        return "Open /me to start OIDC login";
    }

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getIssuer().toString(),
            "subject", user.getSubject()
        );
    }
}
~~~

When accessing `/me` without a login session, Spring Security sends the user into the appropriate login flow. If the application has multiple registrations, the default login page may display the options; you can also start directly at `/oauth2/authorization/demo`.

Because the scope contains `openid`, the authenticated principal is typically an `OidcUser`. If performing OAuth2 Login **without OIDC**, the principal may be an `OAuth2User`; do not cast unconditionally to `OidcUser` in every OAuth2 scenario.

**Security note:** the controller only returns the issuer and subject for illustration—never expose `id_token`, `access_token`, `refresh_token`, or secrets in responses.

## 6. How Far Do the Dependencies Run During a Login Request?

The main components can be visualized in the following diagram:

~~~mermaid
sequenceDiagram
    actor User as Browser
    participant MVC as Spring MVC / Servlet
    participant Filter as Spring Security Filter Chain
    participant AS as OIDC Provider
    User->>MVC: GET /me
    MVC->>Filter: Request passes through security filters
    Filter-->>User: 302 to /oauth2/authorization/demo
    User->>Filter: GET /oauth2/authorization/demo
    Filter-->>User: 302 to authorization endpoint
    User->>AS: User authenticates and grants consent
    AS-->>User: 302 callback?code=...&state=...
    User->>Filter: GET /login/oauth2/code/demo?code=...
    Filter->>AS: POST token endpoint
    AS-->>Filter: ID Token + Access Token
    Filter->>Filter: Verify tokens; create Authentication
    Filter-->>User: Redirect back to original URL
    User->>MVC: GET /me with session
    MVC-->>User: JSON issuer + subject
~~~

In practice, the **Servlet Filter Chain** runs before controllers, so the URLs dedicated to OAuth2 authorization and callback are handled by Spring Security rather than manually created controllers.

Key default endpoints:

| Path | Role |
| --- | --- |
| `/oauth2/authorization/{registrationId}` | Initiates the authorization request and redirects to the provider |
| `/login/oauth2/code/{registrationId}` | Receives the default Authorization Code callback |
| `/login` | Default login page, if Spring Security generates and configures one for that scenario |
| `/logout` | Application logout mechanism in Spring Security; logging out at the OIDC Provider may require separate configuration |

The `registrationId` in the URL must match the key declared under `spring.security.oauth2.client.registration`.

## 7. Dependencies Serving Each Responsibility

Not every application needs every OAuth2 feature in one project:

| Task | Main Starter | Implementation Point |
| --- | --- | --- |
| Users log in with Google, Keycloak, or an OIDC Provider | OAuth2 Client starter + MVC starter | `oauth2Login()`, client registration, session |
| Servlet backend calls external APIs on behalf of the logged-in user | OAuth2 Client starter + MVC starter | `OAuth2AuthorizedClient` and appropriate HTTP client |
| Backend batch job requests tokens using Client Credentials | OAuth2 Client starter; web starter depending on needs | `OAuth2AuthorizedClientManager` for contexts without a Servlet request |
| Own API verifies Bearer Access Tokens | Resource Server starter (Servlet or Reactive depending on API) | `oauth2ResourceServer()` and JWT/opaque configuration |
| System issues tokens and manages authorization endpoints | Authorization Server starter/separate configuration | Token issuance, client management, policies |
| Same app both logs in via OIDC and protects an internal API | Appropriate Client starter and Resource Server starter | Needs clear separation/definition of security chains, request matchers, and policies |

### Does Client Credentials Need a Servlet Starter?

**Not necessarily.** A batch process that only calls APIs as an OAuth2 Client may not need Spring MVC or a Servlet container. However, this lesson's topic is **OAuth2 Client for a Servlet application**, so the web login example needs the corresponding web starter. Choose dependencies based on application architecture, not solely on a protocol name.

## 8. Version Management and the Dependency Graph

### 8.1. Why Should You Not Pick Individual Versions Yourself?

The Spring Boot BOM manages groups of libraries—Spring Security, Spring Framework, Jackson, Tomcat, and many other dependencies—as a set tested together. If you declare directly:

~~~groovy
// Not recommended: mixing an independent version with the active BOM.
implementation 'org.springframework.security:spring-security-oauth2-client:SOME_OTHER_VERSION'
~~~

you can create an incompatible combination with `spring-security-config`, `spring-security-web`, or Spring Framework. Errors may surface at runtime as `NoSuchMethodError` / `ClassNotFoundException`, even though parts of the code compiled cleanly.

In a Boot-managed project, using starters is **not only concise but also keeps versions consistent**. Only override a version when there is a specific reason and you have evaluated its impact on the dependency tree.

### 8.2. Commands to Inspect Actual Dependencies

Gradle in the project directory:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-oauth2-client --configuration runtimeClasspath
~~~

On Windows you can use the wrapper:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-security-oauth2-client --configuration runtimeClasspath
~~~

Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.security
~~~

These commands are for **inspecting the dependency graph**, not runtime OAuth2 configuration operations. If `spring-security-oauth2-client` is missing from the runtime classpath, the project likely has not added the right starter to the executable application module or the dependency scope is misconfigured.

### 8.3. Distinguishing Compile, Runtime, and Test Scopes

For OAuth2 Login, the starter must be on the application's **runtime classpath**:

- Gradle: use `implementation`, not `testImplementation`.
- Maven: use default compile scope, do not put `<scope>test</scope>`.
- `spring-security-test` or the security test starter belongs in **test scope**.

In a multi-module build, add the dependency to **the application module that needs OAuth2 Client**, or via a convention/plugin configured so that module receives the runtime dependency. Adding it only to a library module that is not packaged into the executable JAR will not fix the runtime classpath of the actual running app.

## 9. Auto-Configuration Activated by Dependencies

When Spring Boot detects the OAuth2 Client library and `spring.security.oauth2.client.*` properties, Boot can automatically create components such as `ClientRegistrationRepository`. In a Servlet application, Spring Security uses them to orchestrate login and authorized clients.

| Component | Meaning |
| --- | --- |
| `ClientRegistration` | A single client configuration: client ID, grant type, redirect URI, scopes, provider endpoints |
| `ClientRegistrationRepository` | Collection of client registrations |
| `OAuth2AuthorizedClient` | Result of an authorized client for a principal; holds an Access Token and optionally a Refresh Token |
| `OAuth2AuthorizedClientRepository` | Stores/loads authorized clients in a Servlet context |
| `OAuth2AuthorizedClientService` | Abstraction for storing/loading authorized clients at the service layer |
| `OAuth2AuthorizedClientManager` | Coordinates acquiring/refreshing tokens based on provider and state |
| `OAuth2AuthenticationToken` | Authentication representing a successful OAuth2 Login |
| `OidcUser` | OIDC user principal when logging in with `openid` and tokens have been verified |

You **do not need to manually define the default beans just because you added the starter**. When the standard login flow works, rely on the built-in mechanisms; only configure custom beans if you need custom storage, providers, token refresh, or policies.

To call downstream APIs, `oauth2Client()` and `OAuth2AuthorizedClientManager` can be used depending on context. **The dependency does not automatically attach Bearer tokens to every HTTP request**; you must use an HTTP client/integration configured to look up the authorized client, select the right registration, and attach the token for the intended resource server.

## 10. Common Errors When Setting Up Dependencies

### 10.1. Missing `OAuth2AuthorizedClient` or `OidcUser` Classes

**Symptom:** IDE reports it cannot import `org.springframework.security.oauth2.client.OAuth2AuthorizedClient` or `org.springframework.security.oauth2.core.oidc.user.OidcUser`.

**Check:** whether the right starter is in the application module; whether the dependency is in `implementation` / compile scope; whether Gradle/Maven was synced after editing the build file. With Spring Boot 4, use the new starter names if creating a new project.

### 10.2. Accidentally Using WebFlux in a Servlet Application

**Symptom:** configuring `ServerHttpSecurity` while the program runs Tomcat/Spring MVC, and the bean does not apply as expected.

**Cause:** imported reactive APIs instead of `HttpSecurity` / `SecurityFilterChain`. Pick the right stack; do not add the WebFlux starter just to make an import compile.

### 10.3. Adding Only `spring-boot-starter-security`

**Symptom:** the application protects URLs with form login or Basic Authentication, but lacks OAuth2 Client APIs/registrations as expected.

**Cause:** the core Security starter does not replace the OAuth2 Client starter. Add the OAuth2 Client starter for your Boot version.

### 10.4. Using the Resource Server Starter Instead of the OAuth2 Client Starter

**Symptom:** only JWT Bearer token validation is available, with no redirect flow to the IdP and callback.

**Cause:** Resource Server protects APIs; OAuth2 Client initiates login/acquires tokens. Choose the starter matching the responsibility; add both only if the app truly performs both roles.

### 10.5. Startup Failure Loading OIDC Metadata

**Symptom:** exceptions related to `issuer-uri`, discovery, HTTPS connection, TLS, or metadata responses when building client registrations.

**Cause:** wrong issuer, provider unavailable, network/certificate issues, or mismatched metadata. This is usually a **provider configuration** error after dependencies are already correct, not a missing OAuth2 Client starter.

### 10.6. Redirect URI Mismatch

**Symptom:** the provider returns `redirect_uri_mismatch`, `invalid_redirect_uri`, or a similar error code.

**Cause:** the URI configured at the provider differs from the URI Spring Security sends. Check scheme, hostname, port, context path, reverse proxy, and `{baseUrl}`. In proxied environments, only enable forwarded headers with a trusted proxy and appropriate policy.

### 10.7. Dependencies Added but No OAuth2 Login Occurs

**Symptom:** users are redirected to default Basic/form login, or no provider link appears.

**Check:** whether a registration (`client-id`, provider, scope, redirect URI) exists; whether `SecurityFilterChain` configures `oauth2Login()` properly; whether the login initiation URL matches `/oauth2/authorization/{registrationId}`; whether another custom chain intercepts the request first.

### 10.8. Boot 4 Project Copying Boot 3 Starter Guides Verbatim

**Symptom:** the project uses old artifact names with deprecation warnings, or documentation and the dependency graph are hard to reconcile.

**Resolution:** on new Boot 4 projects, prefer `spring-boot-starter-webmvc` and `spring-boot-starter-security-oauth2-client`. Do not manually override Spring Security versions to "match" starters.

### 10.9. Legacy `javax`/`jakarta` Errors

Spring Boot 3/4 is built on the **Jakarta** ecosystem, such as `jakarta.servlet.http.HttpServletRequest`. If you copy code using `javax.servlet.*` from Spring Boot 2.x, the app may hit import errors or runtime conflicts. Migrate APIs to match the Spring Boot version; do not add old servlet APIs to patch over incompatibilities.

## 11. Minimal Testing the Application Should Support

When the project runs against a test IdP or appropriate test setup, you can observe this sequence:

| Action | Expected Result |
| --- | --- |
| Open `http://localhost:8080/` | Public page returns content |
| Open `http://localhost:8080/me` while logged out | Browser starts the authentication flow |
| Open `http://localhost:8080/oauth2/authorization/demo` | Redirects to the provider's authorization endpoint |
| Successfully log in at the provider | Browser returns to `/login/oauth2/code/demo`, app creates Authentication/session |
| Call `/me` again | Returns verified issuer/subject from the OIDC principal |
| Login succeeds, but calling an external API returns `401`/`403` | Investigate Access Token/audience/scopes for the API, not just dependencies |

In test code, Spring Security can mock principals using `spring-security-test` / the corresponding test starter; do not run real Internet logins across all unit tests. End-to-end integration tests can target a test IdP or a separately configured integration environment.

**These signs only confirm functional setup of the flow** and do not prove the application meets all production security requirements. Production systems also require controls for HTTPS, session cookies, CSRF, secret rotation, proxies, logout, and API authorization.

## 12. Dependency Selection Examples by Requirement

### Scenario A — MVC Web App with Enterprise OIDC Login

The application has controllers and a profile page; users log in through a provider. Choose the Servlet web starter + OAuth2 Client starter, declare a registration with `openid`, and configure `oauth2Login()`. You can add Thymeleaf if template-based UI is needed.

### Scenario B — Servlet Backend That Both Logs In and Calls APIs on Behalf of Users

Keep the dependency set from Scenario A, and use `OAuth2AuthorizedClient` and an authorized client manager to acquire Access Tokens when calling APIs. **Ensure the token has the right audience/scopes for the target API**; a successful OIDC login does not automatically make the token valid for every downstream system.

### Scenario C — Your Own API Only Accepts Bearer JWTs

If the application never needs to redirect browsers to an IdP or request tokens to call other systems, the OAuth2 Client starter may be unnecessary. This role fits the Resource Server starter.

### Scenario D — Scheduled Job Calling an API with Client Credentials

If there is no web UI, the Servlet web starter is usually unnecessary. Use the OAuth2 Client starter with a `client_credentials` registration and a manager suited for a service/background context, without configuring `oauth2Login()` as a mandatory step.

### Scenario E — Upgrading from Boot 3 to Boot 4

Update Spring Boot/Java/build tool versions per upgrade requirements, then use the new starter names for MVC and OAuth2 Client. Check compatibility of other dependencies under the BOM, replace any leftover `javax.servlet` imports, and re-verify login configuration. Renaming starters is one part of migration, not a substitute for the full upgrade process.

## 13. References

- **Spring Boot — Build Systems / Starters:** https://docs.spring.io/spring-boot/reference/using/build-systems.html
- **Spring Boot — Spring Security and OAuth2 Client auto-configuration:** https://docs.spring.io/spring-boot/reference/web/spring-security.html
- **Spring Security — Servlet OAuth2 Client / OAuth2 Login:** https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html
- **Spring Boot — Modularizing Spring Boot (starter renames in Boot 4):** https://spring.io/blog/2025/10/28/modularizing-spring-boot

## 14. Practical Conclusion

For a **Spring Boot Servlet OAuth2/OIDC Client**, the minimal dependency configuration is **Servlet MVC starter + OAuth2 Client starter for your Boot branch**:

~~~text
Spring Boot 3:
  spring-boot-starter-web
  spring-boot-starter-oauth2-client

Spring Boot 4:
  spring-boot-starter-webmvc
  spring-boot-starter-security-oauth2-client
~~~

Once dependencies are in place, the application still needs a **Client Registration**, an **Authorization Server/OIDC Provider**, appropriate **scopes**, and a **SecurityFilterChain** for Servlet. Starters bring the right libraries and default configuration onto the classpath; the application remains responsible for designing permissions, login sessions, token storage, and endpoints according to real requirements.
