# 4.5. Project Structure, Profiles, and Environment-Specific Configuration

## 1. The Challenge of Bringing an OAuth 2.0/OIDC Client to a Real Project

A Spring Boot application using **Spring Security OAuth 2.0 Client** typically runs across multiple environments:

- **Local**: developers run the app on their machine, connecting to a development Identity Provider (**IdP**).
- **Development/Integration**: multiple services run together to test login flows and API calls.
- **Staging**: a production-like environment for pre-release testing.
- **Production**: real users log in via OIDC, and the app uses OAuth 2.0 access tokens to call protected APIs.

The login logic may be identical across all four environments, but configuration values differ: **issuer URI**, **client ID**, **client secret**, **redirect URI**, API addresses, HTTPS, cookies, proxies, logging, and session storage mechanisms.

Hardcoding values in Java code or mixing environment settings inside a security class makes deployment difficult to manage. This lesson establishes how to **organize the project**, **use Spring Profiles**, and **load environment-specific configuration**, while safeguarding OAuth Client secrets and ensuring OIDC callbacks work properly.

> Illustrative examples use **Java 17+, Spring Boot 3, and Spring Security 6**, a server-side web application (MVC/BFF) named **Employee Portal**, a registration ID of **company**, and an **Orders API** that Portal calls on behalf of users. All hostnames, client IDs, secrets, and endpoints are illustrative values, not live services.

## 2. Three Design Principles

**One application codebase, multiple configuration sets.** The same artifact can run in local, staging, and production. Differences lie mainly in properties, environment variables, secrets, and infrastructure; there is no need to duplicate source code per environment.

**Separate layer responsibilities.** Security configuration decides which requests require authentication and uses OIDC login. OAuth2 Client configuration describes the Authorization Server/client registration. Controllers and services handle business logic; HTTP clients call APIs using the user's access token.

**Never store secrets in Git.** Client secrets, refresh tokens, private keys, passwords, and introspection credentials do not belong in committed configuration files. YAML files in the repository should only contain structure, variable names, non-sensitive values, and safe defaults.

These principles are especially critical for OAuth 2.0/OIDC because a single misconfiguration can break callbacks, send tokens to the wrong recipient, or leak credentials.

## 3. Recommended Directory Structure

A Spring Boot application acting as an **OIDC Relying Party + OAuth 2.0 Client** can be organized as:

~~~text
employee-portal/
├── build.gradle
├── settings.gradle
├── gradlew
├── gradlew.bat
├── .gitignore
├── .env.example                    # variable names/sample values, contains no real secrets
├── README.md
├── src/
│   ├── main/
│   │   ├── java/com/example/portal/
│   │   │   ├── PortalApplication.java
│   │   │   ├── config/
│   │   │   │   ├── SecurityConfig.java
│   │   │   │   └── OrdersApiProperties.java
│   │   │   ├── web/
│   │   │   │   ├── HomeController.java
│   │   │   │   └── OrdersController.java
│   │   │   ├── service/
│   │   │   │   └── OrdersService.java
│   │   │   └── client/
│   │   │       └── OrdersApiClient.java
│   │   └── resources/
│   │       ├── application.yml
│   │       ├── application-local.yml
│   │       ├── application-staging.yml
│   │       ├── application-prod.yml
│   │       ├── static/
│   │       └── templates/
│   └── test/
│       ├── java/com/example/portal/
│       │   └── web/
│       │       └── HomeControllerTest.java
│       └── resources/
│           └── application-test.yml
└── deployment/
    ├── README.md                   # environment variable and redirect URI guide
    └── ...                         # deployment manifests or docs for the chosen stack
~~~

This is **a suggested structure**, not a mandatory Spring Boot layout. In smaller projects, some classes can be combined; in larger projects, you can organize by feature rather than technical layer. What matters is keeping responsibilities clearly identifiable:

| Location | Responsibility |
|---|---|
| **PortalApplication** | Bootstraps Spring Boot, component scanning, and properties binding |
| **config/SecurityConfig** | **SecurityFilterChain**, **oauth2Login()**, **oauth2Client()**, URL policies |
| **config/OrdersApiProperties** | Binds application-specific properties into Java types |
| **client/OrdersApiClient** | Calls Orders API over HTTP using issued access tokens |
| **service/OrdersService** | Orchestrates business logic; contains no configuration secrets |
| **web/** | Endpoints displaying OIDC identity, calling services, or returning BFF data |
| **application.yml** | Shared environment-independent configuration |
| **application-{profile}.yml** | Environment-specific overrides |
| **test/** | Tests endpoints and security with dedicated test configuration |
| **deployment/** | Documents runtime inputs, secrets, callback URIs, and infrastructure |

**Do not create a copy of SecurityConfig per environment** if only the issuer, client ID, or hostname differs; those differences belong in configuration properties.

## 4. Minimal Dependencies for Portal

Gradle example:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0' // choose a version supported by the project
    id 'io.spring.dependency-management' version '1.1.6'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**spring-boot-starter-oauth2-client** provides what is needed for OAuth 2.0 Client and OIDC login. When Portal is a server-side session application, you do not need to add the OAuth2 Resource Server starter unless **Portal itself also needs to receive and validate bearer access tokens at its own endpoints**. The Resource Server protecting Orders API is typically a separate application.

Spring Boot manages compatible versions for most dependencies via its BOM. In real projects, use a Boot version selected by your organization and apply security updates on schedule; the version numbers in the snippet only illustrate syntax.

## 5. Understanding Spring Profiles and Configuration Data

A **Spring Profile** is a logical name used to activate configuration or beans suited for a specific runtime context. Common profiles are **local**, **test**, **staging**, and **prod**.

Spring Boot reads **application.yml** as the shared configuration source. When the **local** profile is active, Boot also loads **application-local.yml** if the file exists. The same property in a profile-specific file can override the property in the shared file according to Spring Boot's precedence rules.

~~~text
application.yml
      │
      ├── active profile = local
      │       └── application-local.yml
      │
      ├── active profile = staging
      │       └── application-staging.yml
      │
      └── active profile = prod
              └── application-prod.yml

Runtime environment variables / CLI arguments
      └── can override values from configuration files
~~~

In practice, **Spring Boot has multiple PropertySources** with a specific precedence order. In typical cases, **command-line arguments** can override values in YAML files; **OS environment variables** can also override properties in YAML. Never treat a profile file as having absolute precedence.

Example:

~~~yaml
# application.yml
server:
  port: 8080
~~~

~~~yaml
# application-staging.yml
server:
  port: 8085
~~~

When running with the **staging** profile, the app uses port **8085** unless a higher-precedence configuration source overrides it, such as **SERVER_PORT=9000**.

Key points to remember:

- If no active profile is specified, Spring uses the **default** profile.
- **SPRING_PROFILES_ACTIVE=local** or **--spring.profiles.active=local** are ways to specify a profile.
- Multiple profiles can be enabled, such as **local,debug**, but ordering and overrides must be managed carefully; avoid accidentally activating **prod** alongside a test profile.
- Do not declare **spring.profiles.active** inside **application-local.yml** or inside a document activated only by a profile. Set the active profile in the runtime environment or a profile-independent configuration source.
- Multi-document YAML files with **spring.config.activate.on-profile** can group multiple profiles in one file, though separate **application-{profile}.yml** files are often easier for learners to read.

**Profiles only select configuration. Profiles do not create security boundaries by themselves.** Do not assume that running with the **prod** profile makes TLS, access control, secrets, and IdP configuration secure if they were not set up properly.

## 6. `application.yml`: Shared OAuth 2.0/OIDC Client Configuration

First, define common properties and use placeholders to accept environment-dependent values:

~~~yaml
# src/main/resources/application.yml
spring:
  application:
    name: employee-portal
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - orders.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}

server:
  servlet:
    session:
      cookie:
        http-only: true
        same-site: lax

app:
  orders:
    base-url: ${ORDERS_API_BASE_URL}
~~~

Explanation of key parts:

| Property | Role |
|---|---|
| **spring.security.oauth2.client.registration.company** | Declares an OAuth Client registration with ID **company** |
| **provider: company** | Links the registration to the corresponding provider configuration |
| **client-id** | Application identifier issued by the IdP; can differ across local/staging/prod |
| **client-secret** | Secret of a **confidential client**; must not be committed to Git |
| **client-authentication-method** | Method the client uses to authenticate at the token endpoint; must match the IdP |
| **authorization-grant-type** | Uses **authorization_code** for web apps logging in via redirect |
| **redirect-uri** | Callback URL template; **{baseUrl}** and **{registrationId}** are expanded by Spring Security |
| **scope: openid** | Requests OIDC login; other scopes depend on app requirements and IdP policy |
| **provider.company.issuer-uri** | Issuer identifier of the OpenID Provider; used for discovery and issuer validation |
| **app.orders.base-url** | Application-specific business property for Portal to call Orders API |

**issuer-uri** is not the authorization endpoint or token endpoint. It must match the exact issuer published in the IdP's discovery document. With providers supporting standard discovery, Spring Security can obtain metadata for the authorization endpoint, token endpoint, JWKS, and user-info endpoint from the issuer.

The **registration ID** (**company**) is the internal name of the client registration within the application, distinct from the **client-id** issued by the IdP. Spring Security uses the registration ID in default URLs:

~~~text
Initiate login: /oauth2/authorization/company
Callback:       /login/oauth2/code/company
~~~

The redirect value registered at the IdP must match the actual URL the browser returns to. Typically **each environment has its own client registration at the IdP** so client secrets, allowed redirect URIs, and authorization policies remain independent.

**openid** is required for OIDC login. The **orders.read** scope is an example permission to call Orders API; the IdP must support issuing scopes/tokens with the appropriate **audience** for that API. Adding a scope to YAML does not cause the Authorization Server to grant extra permissions on its own.

## 7. `application-local.yml`: Local Machine Development

The local file only holds what differs from the shared configuration:

~~~yaml
# src/main/resources/application-local.yml
server:
  port: 8080

app:
  orders:
    base-url: http://localhost:8081

logging:
  level:
    root: INFO
    org.springframework.security: INFO
~~~

The example above assumes Orders API runs on **localhost:8081**. Client ID, secret, and issuer still come from environment variables, since local development may connect to a dedicated IdP and must still protect credentials.

The redirect URI generated from the base URL when Portal runs locally is:

~~~text
http://localhost:8080/login/oauth2/code/company
~~~

Register this exact URI in the client configuration of the IdP used for local development. An IdP may permit HTTP for loopback callbacks during development, but production must use HTTPS and redirect URIs complying with provider policies.

You do not need to put **spring.profiles.active: local** in this file. The local profile is selected via launch command or environment variables.

## 8. `application-staging.yml` and `application-prod.yml`

In staging and production, Portal usually runs behind a reverse proxy, API gateway, or ingress providing HTTPS and a public hostname.

### 8.1. Staging

~~~yaml
# src/main/resources/application-staging.yml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

logging:
  level:
    root: INFO
    org.springframework.security: INFO
~~~

Example corresponding environment variables:

~~~text
SPRING_PROFILES_ACTIVE=staging
OIDC_ISSUER_URI=https://login.staging.example.test/realms/company
OIDC_CLIENT_ID=employee-portal-staging
OIDC_CLIENT_SECRET=<secret-from-secret-store>
ORDERS_API_BASE_URL=https://orders.staging.example.test
~~~

Callback that the staging IdP must allow, assuming Portal is publicly accessed via **https://portal.staging.example.test**:

~~~text
https://portal.staging.example.test/login/oauth2/code/company
~~~

### 8.2. Production

~~~yaml
# src/main/resources/application-prod.yml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
  error:
    include-message: never
    include-stacktrace: never

logging:
  level:
    root: INFO
    org.springframework.security: INFO
~~~

Example variables the deployment must supply:

~~~text
SPRING_PROFILES_ACTIVE=prod
OIDC_ISSUER_URI=https://login.example.test/realms/company
OIDC_CLIENT_ID=employee-portal-prod
OIDC_CLIENT_SECRET=<secret-from-secret-store>
ORDERS_API_BASE_URL=https://orders.example.test
~~~

In production, **OIDC_CLIENT_SECRET** is injected from a secret manager or deployment platform secret store—never write real values in YAML, Dockerfiles, publicly visible command lines, or documentation. The **<secret-from-secret-store>** placeholders above are descriptive markers, not usable secrets.

**Note on HTTPS behind a proxy:** **server.forward-headers-strategy: framework** enables Spring to process forwarded headers to infer the external scheme/host. Trust those headers only when the reverse proxy **strips arbitrary Forwarded/X-Forwarded-* headers sent by clients** and supplies canonical headers from a trusted proxy. Otherwise, an attacker could influence URLs generated by the application.

When users reach Portal over HTTPS while traffic between the proxy and app runs over HTTP, proper forwarded headers configuration is essential so **{baseUrl}** builds redirect URIs like **https://portal.example.test/...** instead of an internal hostname or **http://...**.

## 9. Environment Configuration Comparison Table

| Factor | Local | Staging | Production |
|---|---|---|---|
| Active profile | **local** | **staging** | **prod** |
| Public Portal URL | **http://localhost:8080** | **https://portal.staging.example.test** | **https://portal.example.test** |
| Issuer | Development IdP | Staging IdP or realm | Production IdP/realm |
| Client registration | Local client ID | Staging client ID | Prod client ID |
| Client secret | Dev secret, stored securely locally only | Secret from staging infrastructure | Secret from production secret manager |
| Redirect URI | Loopback callback | HTTPS staging callback | HTTPS production callback |
| Orders API URL | **http://localhost:8081** | Staging API | Production API |
| Session cookie **Secure** | Depends on local HTTP/HTTPS | **true** when served over HTTPS | **true** |
| Forwarded headers | Usually unnecessary for direct access | Needed behind a trusted proxy | Needed behind a trusted proxy |
| Security logging | Controlled level sufficient for debugging | INFO | INFO, per logging policy |

Do not share client secrets between local and production for "deployment convenience". Separating client registrations allows revoking, rotating secrets, and restricting redirect URIs independently across environments.

## 10. How to Run the Application with a Selected Profile

### 10.1. PowerShell on Windows

Example in a developer's terminal session:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = 'local'
$env:OIDC_ISSUER_URI = 'https://login.dev.example.test/realms/company'
$env:OIDC_CLIENT_ID = 'employee-portal-local'
$env:OIDC_CLIENT_SECRET = '<local-dev-client-secret>'

./gradlew.bat bootRun
~~~

The **app.orders.base-url** property is loaded from **application-local.yml**, so passing **ORDERS_API_BASE_URL** is unnecessary in this example. If you want to override it via an environment variable:

~~~powershell
$env:ORDERS_API_BASE_URL = 'http://localhost:8099'
~~~

Environment variables normally take higher precedence than values in **application-local.yml**, so Portal will use the new URL. The secret values in examples are placeholders: use the actual secret issued for that environment, and never paste real secrets into documentation or shared outputs.

### 10.2. Bash or Linux/macOS Terminal

~~~bash
export SPRING_PROFILES_ACTIVE=local
export OIDC_ISSUER_URI=https://login.dev.example.test/realms/company
export OIDC_CLIENT_ID=employee-portal-local
export OIDC_CLIENT_SECRET='<local-dev-client-secret>'

./gradlew bootRun
~~~

### 10.3. Specifying a Profile When Running a JAR

~~~bash
java -jar build/libs/employee-portal.jar --spring.profiles.active=prod
~~~

The JAR filename depends on your build configuration. Provide **OIDC_ISSUER_URI**, **OIDC_CLIENT_ID**, **OIDC_CLIENT_SECRET**, and **ORDERS_API_BASE_URL** via the runtime environment or a secure configuration source before startup.

### 10.4. Why Should You Not Default to `local` in `application.yml`?

If you add:

~~~yaml
spring:
  profiles:
    active: local
~~~

to the shared configuration, a deployment that accidentally omits a profile could run with local settings. It is safer to require deployment environments to select a profile explicitly, especially in production. If started without a profile and missing required placeholders, the application should fail fast so operators immediately know configuration is incomplete.

## 11. Organizing a Shared `SecurityFilterChain` Across All Profiles

When all environments share the same OIDC flow and endpoint protection policy, only one Spring Security configuration is needed:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/assets/**", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .build();
    }
}
~~~

This configuration:

1. Allows access to the declared public page and static assets.
2. Requires authentication for all remaining endpoints.
3. Enables **oauth2Login()** for OIDC login via the Authorization Code Flow. By default, Spring Security initiates login from **/oauth2/authorization/company** and handles the callback at **/login/oauth2/code/company**.
4. Enables **oauth2Client()** to provide the foundation for using authorized clients when calling APIs.
5. Preserves default **CSRF protection** for a web application using session cookies; do not disable CSRF globally just to make frontend requests "easier to run".

A client registration with the **openid** scope activates appropriate OIDC login handling. The application needs an Identity Provider compatible with the declared configuration; YAML examples do not create an IdP on their own.

### 11.1. Avoid Checking Profiles to Arbitrarily Alter Security Policies

The following pattern is hard to control safely:

~~~java
// Approach to avoid:
// if ("local".equals(activeProfile)) {
//     http.authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
// }
~~~

If a staging/prod environment accidentally receives the wrong profile, or a configuration branch is misdeployed, endpoints could be left open. Share the core security policy and vary only environment properties. When a specialized SecurityFilterChain is truly needed for tests, isolate it strictly in test configuration rather than shipping security bypass branches in production artifacts.

## 12. Grouping Application Configuration with `@ConfigurationProperties`

Beyond built-in Spring Security properties, applications often have custom properties such as an API base URL. Instead of scattering **@Value** across many classes, use a typed configuration class:

~~~java
package com.example.portal.config;

import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.orders")
public record OrdersApiProperties(URI baseUrl) {
}
~~~

Enable configuration properties scanning on the main class:

~~~java
package com.example.portal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class PortalApplication {

    public static void main(String[] args) {
        SpringApplication.run(PortalApplication.class, args);
    }
}
~~~

Then **app.orders.base-url** from the YAML files binds to **OrdersApiProperties.baseUrl()** as a **URI**. Services can inject this bean via constructor; this pattern is easy to validate and extend when adding timeouts, API paths, or feature flags.

Example client calling Orders API:

~~~java
package com.example.portal.client;

import com.example.portal.config.OrdersApiProperties;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class OrdersApiClient {

    private final RestClient restClient;

    public OrdersApiClient(RestClient.Builder builder,
                           OrdersApiProperties properties) {
        this.restClient = builder
            .baseUrl(properties.baseUrl().toString())
            .build();
    }

    public String getOrders(String accessToken) {
        return restClient.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);
    }
}
~~~

With Spring Security OAuth 2.0 Client, a controller can obtain the current user's access token via the authorized client:

~~~java
package com.example.portal.web;

import com.example.portal.client.OrdersApiClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    private final OrdersApiClient ordersApiClient;

    public OrdersController(OrdersApiClient ordersApiClient) {
        this.ordersApiClient = ordersApiClient;
    }

    @GetMapping("/bff/orders")
    public String orders(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient
    ) {
        return ordersApiClient.getOrders(
            authorizedClient.getAccessToken().getTokenValue());
    }
}
~~~

**Important point:** the registration name **company** stays constant across profiles, while **client ID**, **secret**, **issuer**, and **Orders API URL** can vary by environment. As a result, controller/service logic does not need to know whether the app is running locally or in prod.

The example above uses a synchronous `RestClient` to keep the flow simple. Real applications should add timeouts, 401/403 error handling, appropriate retries, access token refresh when supported, and log protection for tokens. **OAuth2AuthorizedClientManager** can manage token re-acquisition based on configuration and context, avoiding manual refresh logic.

## 13. `.env` Files, Environment Variables, and Secret Managers

### 13.1. Using `.env.example` to Document Inputs

You can place an **.env.example** file in the repository:

~~~dotenv
# Names and examples only, DO NOT put real secrets here
SPRING_PROFILES_ACTIVE=local
OIDC_ISSUER_URI=https://login.dev.example.test/realms/company
OIDC_CLIENT_ID=employee-portal-local
OIDC_CLIENT_SECRET=REPLACE_WITH_LOCAL_SECRET
ORDERS_API_BASE_URL=http://localhost:8081
~~~

Note: **Spring Boot does not automatically read `.env` files just because they exist**. The launcher (IDE, Docker Compose, script, environment loader, or explicitly configured config import) must load those variables into the Java process environment. Running the app in an IDE may require setting environment variables in the Run Configuration.

Files containing real secrets, such as **.env.local**, must never be committed. Example:

~~~gitignore
.env
.env.*
!.env.example
~~~

These rules are only an example for `.env` files; review your repository's overall `.gitignore` conventions carefully, especially if non-secret `.env` files are intentionally tracked.

### 13.2. Secrets in Staging and Production

In deployments, use platform-native mechanisms such as:

- Kubernetes Secrets with least-privilege access, or your cloud provider's secret manager.
- Environment variables injected at runtime by the deployment platform, without printing them into configuration logs.
- Mounted secret files/config trees if the platform uses file-based injection with proper access controls.

Never place secrets in Docker images, Git repositories, frontend bundles, URL query parameters, logs, or error messages. Have a **rotation** process: update credentials at the IdP, update runtime secrets, perform a controlled rollout/restart of workloads, and revoke old credentials.

### 13.3. Direct Environment Variables for Spring Security

Spring Boot also supports **relaxed binding** from environment variable names to properties, for example:

~~~text
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_ID
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_SECRET
SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_COMPANY_ISSUER_URI
~~~

However, using **${OIDC_CLIENT_ID}**, **${OIDC_CLIENT_SECRET}**, and **${OIDC_ISSUER_URI}** in the shared YAML groups project inputs into short, stable names that are easy to document for deployment. Pick one clear convention and avoid having too many equivalent names, which makes it hard to tell which source wins when settings are overridden.

## 14. Redirect URIs and Reverse Proxies: Common Errors When Changing Environments

In the OAuth 2.0 Authorization Code Flow, the browser goes to the IdP, logs in, and returns to Portal's **redirect URI** with an authorization code. The IdP typically verifies that the redirect URI is in its allowlist.

Suppose production traffic flows through:

~~~text
Browser
  -> https://portal.example.test
  -> Reverse proxy / ingress (TLS termination)
  -> http://portal-service:8080
  -> Spring Boot Portal
~~~

If Portal derives **{baseUrl}** from the internal request, it may construct the wrong callback:

~~~text
http://portal-service:8080/login/oauth2/code/company
~~~

While the IdP has registered:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

In that case, the IdP may return a **redirect_uri mismatch** error, or the callback may point to an address the browser cannot reach.

Remediation steps:

1. Register the **exact** public callback in the IdP's OAuth client configuration.
2. Ensure the proxy forwards the scheme/host/port/prefix headers that Spring needs.
3. Configure **server.forward-headers-strategy** to match your infrastructure and trust forwarded headers only from controlled proxies.
4. Verify the login request generates **redirect_uri=https://portal.example.test/login/oauth2/code/company** in that environment.
5. If the app sits under a path prefix like **/portal**, account for that prefix in the base URL/callback and configure the proxy consistently.

You can pin **redirect-uri** via an environment variable when infrastructure makes reconstructing the base URL difficult, for example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: ${OIDC_REDIRECT_URI}
~~~

However, when the same codebase serves multiple hosts, the **{baseUrl}** template with proper proxy configuration is usually more flexible. Whichever approach you choose, **the actual redirect value must match the IdP's allowlist**. Never use arbitrary wildcard redirect URIs.

## 15. Sessions, Cookies, SameSite, and Multi-Instance Environments

A successful OIDC login typically creates a **SecurityContext** bound to Portal's HTTP session. In a server-side web application:

~~~text
Browser --session cookie--> Portal
Portal  --access token----> Orders API
~~~

The session cookie is not the OAuth access token, and the access token does not need to be exposed to browser JavaScript to call BFF endpoints.

Cookie attributes to review:

- **HttpOnly**: prevents JavaScript from reading the session cookie directly.
- **Secure**: sends the cookie only over HTTPS; enable in environments with actual HTTPS.
- **SameSite**: **Lax** generally works well with OIDC redirects via top-level GETs, whereas callback modes like **response_mode=form_post**, iframe embedding, or special cross-site flows may require **SameSite=None** combined with **Secure** per security design.
- **Domain, Path**: must align with the public hostname/path; avoid unnecessarily broad cookie scopes.
- **CSRF protection**: keep enabled or design appropriately for state-changing endpoints authenticated by session cookies.

When running multiple replicas/instances, consider how sessions and **OAuth2AuthorizedClient** are stored:

| Issue | Impact | Resolution |
|---|---|---|
| Session lives only in one instance's RAM | Requests routed to another node lose login state | Use shared session storage such as Spring Session with a supported backend, or infrastructure session affinity per policy |
| Authorized client/tokens stored locally only | Another node lacks the token to call APIs | Choose an **OAuth2AuthorizedClientService/Repository** matching your storage and lifecycle needs |
| Different secrets/issuers across replicas | Inconsistent login and token refresh behavior | Deploy the exact same configuration version across a deployment |
| Application is redeployed | Held sessions/tokens may be lost or expire | Re-initiate authorization/login or persist state per requirements |

Do not assume Spring Boot provides distributed sessions and durable token repositories automatically. Choose storage, sensitive-data protection, and lifetimes based on your actual architecture.

## 16. Handling Multiple OIDC Providers or Multiple Client Registrations

An application can allow users to log in through multiple providers, such as **company** and **partner**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${COMPANY_OIDC_CLIENT_ID}
            client-secret: ${COMPANY_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile]
          partner:
            provider: partner
            client-id: ${PARTNER_OIDC_CLIENT_ID}
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: ${COMPANY_OIDC_ISSUER_URI}
          partner:
            issuer-uri: ${PARTNER_OIDC_ISSUER_URI}
~~~

This is an **alternative example** replacing the **company** registration configuration in section 6, not a snippet to append verbatim to the previous YAML.

Each registration has its own login initiation URL:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

Correspondingly, default callbacks follow each registration ID:

~~~text
/login/oauth2/code/company
/login/oauth2/code/partner
~~~

In multi-tenant or multi-IdP systems, manage issuers, callbacks, principal mapping, permissions, and audiences carefully. Never assume two users with the same email from two different issuers represent the same internal identity. A reliable identifier usually combines **issuer** and **subject** according to application policy.

## 17. Testing Profile-Based Configuration

The **test** profile can be used in the test suite, but unit/integration tests should not rely on a live production IdP on every run. Common approaches:

- **Spring Security Test** to mock an OIDC principal when testing controllers or endpoint policies.
- **Stubs/WireMock** for discovery metadata and authorization/token/user-info/JWKS endpoints in integration tests simulating an IdP.
- Testcontainers or a dedicated IdP environment for end-to-end tests that require a real identity provider.
- Place **application-test.yml** with test endpoints/credentials isolated from production. Test configuration still needs valid client settings for Spring Boot to initialize the context, even when requests use mock principals.

For example, first create an endpoint that only reads the OIDC principal without calling an external API:

~~~java
package com.example.portal.web;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {
    @GetMapping("/me")
    Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of("sub", user.getSubject());
    }
}
~~~

Then test it using **spring-security-test**:

~~~java
package com.example.portal.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class ProfileControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void authenticatedOidcUserCanAccessProtectedEndpoint() throws Exception {
        mockMvc.perform(get("/me").with(oidcLogin()
                .idToken(token -> token.claim("sub", "employee-42"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sub").value("employee-42"));
    }
}
~~~

To run **@SpringBootTest**, the **test** profile must still provide or mock a valid **ClientRegistrationRepository**; if the provider configuration uses **issuer-uri**, you may need to stub the discovery endpoint during context startup. **oidcLogin()** only simulates an authenticated user in MockMvc and does not provide a test Authorization Server itself. These tests do not prove the IdP issues tokens properly in a real environment; end-to-end checks still need to confirm redirect URI, issuer, audience, scopes, token refresh, logout, and session state on the target infrastructure.

## 18. Common Configuration Errors

| Symptom | Common Cause | Troubleshooting Approach |
|---|---|---|
| Startup fails due to missing **OIDC_CLIENT_SECRET** or issuer | Environment variables not loaded; `.env` file not read | Verify runtime source, active profile, and placeholders; never log secrets |
| IdP reports **invalid_redirect_uri** | Actual redirect does not match allowlist | Check hostname, scheme, port, path, and IdP registration |
| Login redirects to **http://internal-host** | Proxy not sending or Spring not trusting forwarded headers | Configure trusted proxy, forwarded headers, and base URL |
| Login works locally, fails in staging | Wrong issuer/client ID/secret/callback for environment | Compare non-secret config and client registration on staging IdP |
| **invalid_client** when exchanging authorization code | Wrong client secret or client authentication method | Verify registration and deployed credentials |
| **invalid_scope** or API returns **403** | Scope not granted or authority mapping mismatch | Check granted permissions, actual scopes, and Resource Server rules |
| API returns **401** even though Portal login succeeded | Access token expired, wrong issuer/audience, or invalid | Check token lifecycle and Resource Server config; never use ID Token as access token |
| Login cookie not sent after redirect | Incorrect Secure/SameSite/domain/path or TLS/proxy setup | Inspect cookie attributes and callback mode |
| Login is flaky with multiple instances | Session/authorized client lacks shared storage | Review session and token storage strategy across instances |
| **application-prod.yml** exists but is not applied | **prod** profile not enabled or overridden by another source | Check active profiles and higher-precedence property sources |
| Login endpoint does not appear | Missing OAuth2 Client dependency, registration, or SecurityFilterChain | Verify starters, beans, and registration ID name |

When investigating, enable verbose logging only in controlled environments, for short durations, and after identifying what data may appear. **Never log authorization codes, access tokens, refresh tokens, client secrets, or session cookies to shared logs.**

## 19. Rollout Process for a New Environment

Suppose you need to add a **preprod** environment. You can proceed sequentially:

1. **Create client at preprod IdP**: provision client ID, authentication method, secret; register exact callback; enable **authorization_code** grant, required OIDC/API scopes, and PKCE policy if required.
2. **Create `application-preprod.yml`** with only non-sensitive differences such as forwarded headers, cookies, logging, and required features; keep shared security logic intact.
3. **Supply runtime variables**: **SPRING_PROFILES_ACTIVE=preprod**, **OIDC_ISSUER_URI**, **OIDC_CLIENT_ID**, **OIDC_CLIENT_SECRET**, **ORDERS_API_BASE_URL**.
4. **Set up HTTPS, proxy, and DNS**: browsers must reach the public URL; Spring must generate **{baseUrl}** matching the external path.
5. **Verify the corresponding Resource Server**: preprod Orders API accepts access tokens with the right issuer, audience, and scopes; Portal does not modify access tokens itself.
6. **Verify actual behavior**: login redirect, callback, session cookie, API calls with user token, 401/403 handling, expiration/refresh, logout, and multi-instance behavior if applicable.
7. **Document operational inputs**: variable names, redirect URLs, secret rotation process, and owners/teams responsible for the IdP and infrastructure.

These steps let you add a new environment mainly through configuration and IdP registration while reusing business logic and `SecurityFilterChain`.

## 20. Summary of the Relationship Between Project Structure, Profiles, and OAuth 2.0/OIDC

A Spring Boot OAuth 2.0/OIDC Client operates reliably when three layers are cleanly separated:

1. **Source code** expresses common behavior: protecting URLs, OIDC login, obtaining authorized clients, and calling APIs on behalf of users.
2. **Configuration Data + Spring Profiles** select environment-appropriate values: issuer, client registration, API addresses, proxies, cookies, and logging.
3. **Infrastructure/secret manager** supplies secrets, HTTPS hostnames, session storage, and truly sensitive runtime inputs.

With that structure, the same Portal can run in local, staging, and production without duplicating the security layer. The core takeaway is to **keep registration IDs and business flows stable**, vary environment details through deliberately managed properties, and always verify that **issuer + client ID/secret + redirect URI + TLS/proxy + API permissions** work properly in every environment.
