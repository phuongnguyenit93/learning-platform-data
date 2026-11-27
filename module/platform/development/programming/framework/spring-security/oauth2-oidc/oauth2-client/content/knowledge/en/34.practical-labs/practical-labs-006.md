# 34.6. Background Jobs Using Client Credentials and the Authorized Client Store

In OAuth2/OIDC Client labs for **web applications**, users normally log in through `oauth2Login()`, the application obtains an `Authentication`, and it uses the issued Access Token to call APIs on the user's behalf. **Background jobs** present a different scenario: the task runs automatically on a schedule, with no browser, no login session, no authorization redirect, and no `HttpServletRequest` carrying a user principal.

For example, a Spring Boot service needs to run a task every five minutes:

> Read inventory data from the internal Inventory API, synchronize the data into the company's system, record the count of processed records, and raise an alert if the task fails.

The Inventory API requires an **OAuth 2.0 Access Token**. The OpenID Provider/Authorization Server has registered a dedicated **confidential client** for the job, enabling the **`client_credentials`** grant type and the `inventory.read` scope. This is **machine-to-machine (M2M)**: the authorized party is the **client application**, not a user who signed in via OIDC.

This lab combines:

- **Spring Boot Scheduling** with `@EnableScheduling` and `@Scheduled`.
- **Spring Security OAuth2 Client** with a property-configured `ClientRegistration`.
- **`AuthorizedClientServiceOAuth2AuthorizedClientManager`** suited for handling OAuth2 outside HTTP requests.
- **`OAuth2AuthorizedClientProvider`** for `client_credentials`.
- **`OAuth2AuthorizedClientService`** to store and retrieve the authorized client.
- A **stable technical principal** to reuse tokens for the same logical job.
- **`WebClient`** sending the Bearer Access Token to the right Resource Server destination.
- **Unit/integration tests**, handling expiration, 401/403/5xx, multiple replicas, durable storage, observability, and credential protection.

This lab presents a **minimal runnable implementation when paired with a contract-compliant Authorization Server and Inventory API**, along with production extensions. The `example.test` addresses, client IDs, secrets, and tokens in the examples are strictly **illustrative data**, not live services.

> **Key takeaway:** For browserless jobs, **do not use session-aware `DefaultOAuth2AuthorizedClientManager` as if an `HttpServletRequest` existed**. Use a service-backed manager, define a stable technical principal, and let the manager/provider find an existing valid token or request a new one when needed.

---

## 1. Learning Objectives

Upon completing this lab, you should be able to explain and implement:

1. The difference between **Authorization Code/OIDC login** and the **Client Credentials grant**.
2. Configuring `registrationId`, `client-id`, `client-secret`, `token-uri`, and `scope` for a service client.
3. Creating an `OAuth2AuthorizedClientManager` independent of requests/sessions.
4. Using `OAuth2AuthorizeRequest` with a **stable principal** for background tasks.
5. Looking up `OAuth2AuthorizedClient` and extracting a valid Access Token.
6. Calling a Resource Server with `Authorization: Bearer ...`.
7. Never sending a machine token to an API requiring user-delegated permissions.
8. Storing authorized clients in memory or a persistent store per policy.
9. Handling expired tokens, token endpoint errors, API 401/403, rate limits, and retries.
10. Avoiding duplicate job execution across multiple pods/replicas.
11. Writing isolated tests without production secrets or tokens.
12. Recognizing the limits of the demo and what must be added before production operation.

## 2. Architecture to Build

```mermaid
sequenceDiagram
    autonumber
    participant S as Spring Scheduler
    participant J as InventorySyncJob
    participant M as AuthorizedClientServiceOAuth2AuthorizedClientManager
    participant R as OAuth2AuthorizedClientService
    participant AS as Authorization Server
    participant C as InventoryApiClient + WebClient
    participant API as Inventory Resource Server

    S->>J: Trigger on schedule
    J->>C: fetchSnapshot()
    C->>M: authorize(registration=inventory-job, principal=job:inventory-sync)
    M->>R: loadAuthorizedClient(registration, principal)
    alt No token yet or token needs re-issuance
        M->>AS: POST /oauth2/token grant_type=client_credentials
        AS-->>M: Access Token + expires_in + scope
        M->>R: saveAuthorizedClient(...)
    else Token is still valid
        R-->>M: Existing authorized client
    end
    M-->>C: OAuth2AuthorizedClient
    C->>API: GET /v1/inventory/snapshot with Bearer Access Token
    API-->>C: 200 + Inventory JSON
    C-->>J: InventorySnapshot
    J->>J: Process/persist data per business logic
```

**Observation:** There is no browser, `state`, `nonce`, ID Token, or `/login/oauth2/code/...` callback in this diagram. Those belong to interactive user login flows, not `client_credentials`.

### 2.1. OAuth2 Roles

| Role | Component in This Lab |
|---|---|
| **Client** | Spring Boot inventory-sync job. |
| **Authorization Server (AS)** | Service issuing OAuth2 Access Tokens to the confidential client. |
| **Resource Server (RS)** | Inventory API validating Access Tokens, scope/audience, and permissions. |
| **Resource Owner** | No interactive user in this grant; access is granted to the client per AS policy. |
| **Authorized client store** | Spring Boot-side store caching issued token state. |

### 2.2. Different Goals Between Client Credentials and OIDC Login

| Criterion | Browser `oauth2Login()` | Background `client_credentials` |
|---|---|---|
| Is a user logging in? | Yes. | No. |
| Uses Authorization Code? | Yes, in standard flows. | No. |
| Browser redirects and callbacks? | Yes. | No. |
| `state`/PKCE/`nonce`? | Yes, when applicable. | Not part of this grant. |
| ID Token for user login? | Yes, with OIDC. | Typically no. |
| Token represents | User authorizing client for granted permissions. | Application/service client. |
| Suitable manager | HTTP or reactive web manager per stack. | Service-backed manager without HTTP requests. |
| Principal key | Appropriate user identity. | A stable technical principal. |
| Typical scopes | `openid`, `profile`, API scopes. | API scopes such as `inventory.read`. |

**Do not add the `openid` scope just to "turn" `client_credentials` into an OIDC user login.** A machine Access Token does not create an `OidcUser` or user session.

## 3. Assumed Contract of This Lab

Assume an Authorization Server supporting the OAuth2 Client Credentials Grant:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <base64-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
```

Illustrative response:

```json
{
  "access_token": "synthetic-access-token",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "inventory.read"
}
```

And the Inventory API:

```http
GET /v1/inventory/snapshot HTTP/1.1
Host: api.example.test
Authorization: Bearer synthetic-access-token
Accept: application/json
```

Illustrative response:

```json
{
  "items": [
    {
      "sku": "SKU-001",
      "available": 25
    },
    {
      "sku": "SKU-002",
      "available": 0
    }
  ]
}
```

These endpoints/tokens merely illustrate the protocol. To run against real services, substitute **a test AS and API you control** with an authorized client registration. Offline simulation using stub servers is covered in the testing sections.

### 3.1. Why Must the Scope Be Exact?

`inventory.read` represents permission to read inventory granted by the Authorization Server. An application does not automatically acquire permission simply by knowing a `client-id`/`client-secret`.

The Resource Server may also require:

- Exact **audience** or resource indicator.
- Exact issuer.
- Unexpired token of the right token type.
- Allowed client identity.
- Specific scope for the endpoint.
- mTLS, private network, or organizational policies.

Adding a scope to YAML **does not force** the AS to grant it. Final policy resides at the AS and RS.

### 3.2. Never Use Client Credentials for User-Delegated Business Logic

If an API returns "orders of the currently logged-in user", using a machine token simply because the job has no user breaks the authorization model. You must design dedicated delegated/offline access or a machine-specific service/API contract.

This lab assumes the **Inventory API exposes an explicit M2M endpoint** permitted by both the AS and the Resource Server.

## 4. Project Setup

A minimal structure:

```text
inventory-sync/
├── build.gradle.kts
├── src/main/java/com/example/inventorysync/
│   ├── InventorySyncApplication.java
│   ├── config/
│   │   ├── OAuth2JobConfiguration.java
│   │   ├── InventoryHttpConfiguration.java
│   │   └── EndpointSecurityConfiguration.java
│   ├── client/
│   │   ├── InventoryApiClient.java
│   │   └── InventorySnapshot.java
│   └── job/
│       └── InventorySyncJob.java
├── src/main/resources/
│   └── application.yml
└── src/test/java/com/example/inventorysync/
    ├── InventoryApiClientTest.java
    ├── InventorySyncJobTest.java
    └── OAuth2ManagerIntegrationTest.java
```

To demo both a scheduled job and a monitoring HTTP endpoint, the example uses **Spring MVC**. Adding the WebFlux starter is **only for `WebClient`** and does not switch the server to Reactive WebFlux while `spring-boot-starter-web` remains the selected web application type. The service-backed manager remains the right choice because the job runs outside HTTP requests.

If deploying **completely headless** (`spring.main.web-application-type=none`), you can drop the Spring MVC server, but you must verify that the `ClientRegistrationRepository` and authorized client service are initialized properly for your application type and Boot version. Do not assume a web-only auto-configuration still runs in a non-web context.

## 5. Gradle Dependencies

Example `build.gradle.kts` snippet for a project already managing the Spring Boot plugin/BOM and compatible JDK:

```kotlin
dependencies {
    // Spring MVC + health/admin endpoints when needed
    implementation("org.springframework.boot:spring-boot-starter-web")

    // Spring Security core and OAuth2 Client
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    // WebClient for outbound HTTP
    implementation("org.springframework.boot:spring-boot-starter-webflux")

    // Health/metrics as operational extension
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Unit/integration tests
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("io.projectreactor:reactor-test")
}

tasks.test {
    useJUnitPlatform()
}
```

This is a **dependency fragment**, not a standalone complete Gradle file. Select the Spring Boot plugin/version via your project's build management and let the BOM align Spring Security and Reactor versions.

### 5.1. Why Are Both Web and WebFlux Starters Included?

- `starter-web` provides Spring MVC/Servlet server, sufficient for Actuator HTTP endpoints and setting the web application type.
- `starter-webflux` provides `WebClient` and the Reactor Netty HTTP client.
- The job uses `WebClient` as an **HTTP client**, while the scheduler itself is not a WebFlux server.
- If a project needs no MVC endpoints, you can trim dependencies and design a headless worker explicitly.

Never copy a `SecurityWebFilterChain` configuration into a Servlet application just because `WebClient` is on the classpath.

### 5.2. Maven Equivalent

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
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
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
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
```

Assumes `pom.xml` already defines the Spring Boot parent/BOM. For a reactive-only project, configure dependencies and server setup accordingly.

## 6. Configuring Client Credentials with YAML

`src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-job:
            provider: inventory-authorization-server
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          inventory-authorization-server:
            token-uri: https://auth.example.test/oauth2/token

inventory:
  api:
    base-url: https://api.example.test
  sync:
    initial-delay-ms: 10000
    fixed-delay-ms: 300000

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

This is a **configuration template**. Replace domains with real approved endpoints. Environment variables `INVENTORY_CLIENT_ID` and `INVENTORY_CLIENT_SECRET` must come from secret management/deployment; never commit real secrets to the repository.

### 6.1. Meaning of Each Property

| Property | Role |
|---|---|
| `registration.inventory-job` | Spring's internal registration key. |
| `provider` | References the AS metadata configuration. |
| `client-id` | Application identifier at the AS. |
| `client-secret` | Confidential client secret credential. |
| `client-authentication-method` | How the client authenticates at the token endpoint. |
| `authorization-grant-type` | `client_credentials`, not `authorization_code`. |
| `scope` | API permissions requested by the client. |
| `provider.*.token-uri` | Address for executing OAuth2 token requests. |
| `inventory.api.base-url` | Resource Server URL called by `WebClient`. |
| `fixed-delay-ms` | Wait interval after one run finishes, not a cron timestamp. |

### 6.2. Why Is `redirect-uri` Not Declared?

The Client Credentials Grant performs no browser navigation, so **there is no OAuth2 authorization callback**. Fields typically seen in `oauth2Login()`, such as:

```yaml
redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
authorization-grant-type: authorization_code
scope: [openid, profile]
```

do not belong to this client credentials use case.

### 6.3. Are `issuer-uri` or OIDC Discovery Required?

Not required. This lab uses an explicit `token-uri` because the token endpoint is already approved by the operator.

If the AS supports OAuth2/OIDC discovery and the app manages the issuer securely, discovery can be used per version/configuration. However, **never accept a dynamic issuer URL from job inputs or an unapproved tenant**, because discovery metadata could point token/JWKS/UserInfo calls to an untrusted host, causing SSRF or credential exfiltration.

### 6.4. Choosing the Client Authentication Method

This example uses `client_secret_basic`—sending the client ID/secret to the token endpoint via HTTP Basic as required by the AS.

Other AS setups may require `client_secret_post`, `private_key_jwt`, or mTLS. Never change the authentication method merely to make code compile; the AS and security policy dictate valid methods.

In particular, never pass `client_secret` as a URL query parameter.

### 6.5. Environment and Secret Rotation

Production should provision credentials via:

- Secret manager, Kubernetes Secret, or appropriate CI secret injection.
- Restricted read permissions scoped to the service account.
- Planned secret rotation.
- Proper TLS and CA trust.
- Separate client registrations for staging/test vs. production.

Never log `client-secret` in debug properties or Actuator outputs.

## 7. Enabling Scheduling

`InventorySyncApplication.java`:

```java
package com.example.inventorysync;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class InventorySyncApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            InventorySyncApplication.class,
            args
        );
    }
}
```

`@EnableScheduling` enables Spring to process `@Scheduled` methods on Spring-managed beans.

### 7.1. Why Not Instantiate `new InventorySyncJob(...)` Manually?

A class that is not a Spring bean or is created with `new` outside the container will not have its scheduling annotations registered by the framework.

Ensure the job is Spring-managed (e.g., `@Component`) and use dependency injection instead of manual instantiation.

### 7.2. `fixedDelay` vs. `fixedRate`

| Schedule | Meaning |
|---|---|
| `fixedDelay` | Waits a fixed duration **after the previous run completes** before starting again. |
| `fixedRate` | Schedules based on the interval between start times, which can build up pressure if runs take long. |
| `cron` | Runs according to a configured schedule expression and timezone. |

This lab chooses `fixedDelay` for clarity and to prevent overlapping runs in a simple single-scheduler setup. **It does not guarantee single-instance execution across a cluster** when running multiple replicas.

## 8. OAuth2 Client Components Created by Spring Boot

When the OAuth2 Client starter and registration properties are present in a Servlet app, Spring Boot can auto-configure `ClientRegistrationRepository` from:

```yaml
spring.security.oauth2.client.registration.*
spring.security.oauth2.client.provider.*
```

In this lab, we expect to inject:

```java
ClientRegistrationRepository registrations
```

so the manager can resolve `inventory-job`.

### 8.1. Do Not Assume Custom Beans and Boot Beans Coexist

If the app defines its own:

```java
@Bean
ClientRegistrationRepository clientRegistrationRepository() {
    // custom registrations
}
```

Boot's auto-configured repository from YAML will typically **back off**. If your custom repository omits `inventory-job`, the job will fail to find the registration.

Before operating, verify the actual bean and loaded registration IDs rather than assuming YAML entries are active.

### 8.2. Testing Registration Should Not Hit the Token Endpoint

Initializing a registration from an explicit `token-uri` does not execute a Client Credentials Grant at bean creation time. Token requests happen only when the manager authorizes a request.

Tests can verify registration config without reaching the production AS.

## 9. Creating `OAuth2AuthorizedClientService`

We explicitly declare an **in-memory** store so the demo is clear:

```java
package com.example.inventorysync.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration(proxyBeanMethods = false)
public class AuthorizedClientStoreConfiguration {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            ClientRegistrationRepository registrations) {

        return new InMemoryOAuth2AuthorizedClientService(
            registrations
        );
    }
}
```

**This is a demo store**, suitable for learning and very small single-instance use cases. Tokens are lost when the process restarts and are not shared across multiple instances.

### 9.1. What Is an Authorized Client?

An `OAuth2AuthorizedClient` associates:

```text
registrationId = inventory-job
principalName = job:inventory-sync
accessToken = <opaque or JWT bearer token>
accessTokenExpiry = <Instant>
refreshToken = typically absent for client_credentials
```

Key methods of the service store:

```java
loadAuthorizedClient(registrationId, principalName)
saveAuthorizedClient(authorizedClient, principal)
removeAuthorizedClient(registrationId, principalName)
```

**`OAuth2AuthorizedClientService` is not `ClientRegistrationRepository`**:

- Registration repository: **client** metadata and configuration.
- Authorized client service: **issued token state** for a client and principal.

### 9.2. Why Is a Principal Needed in M2M?

Spring Security's interface uses the principal name as part of the **storage key**. Client credentials have no end-user, yet we still provide a **technical principal** to partition the authorized client entry.

This name **does not turn the token into a user token**; it is strictly a logical application-side key for the manager/store to identify the authorization.

## 10. Choosing the Right Manager for Browserless Jobs

Create `AuthorizedClientServiceOAuth2AuthorizedClientManager`:

```java
package com.example.inventorysync.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration(proxyBeanMethods = false)
public class OAuth2JobConfiguration {

    @Bean
    OAuth2AuthorizedClientManager jobAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );

        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
```

This is the core component of the lab.

### 10.1. Why Not Use `DefaultOAuth2AuthorizedClientManager`?

The two classes have similar names but serve different contexts:

| Manager | Suitable Context |
|---|---|
| `DefaultOAuth2AuthorizedClientManager` | Servlet HTTP request/response; typically paired with `OAuth2AuthorizedClientRepository` and browser flows. |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Outside `HttpServletRequest`, such as scheduled jobs, service-layer automation, or CLI workers. |
| `ReactiveOAuth2AuthorizedClientManager` and implementations | Reactive/WebFlux, using Reactor `Mono` and reactive repositories/services. |

`DefaultOAuth2AuthorizedClientManager` expects an HTTP request context, so using it in a requestless job causes principal/repository errors or broken context assumptions.

### 10.2. Why Enable Only `clientCredentials()`?

This lab only has a `authorization-grant-type: client_credentials` registration. There is no need to add:

```java
.authorizationCode()
.refreshToken()
.password()
```

just to "support every grant".

A **client credentials** Access Token is normally **not issued with a Refresh Token** under this grant. When the token nears expiry, the client requests a **new Access Token** using the same grant and client credentials. Do not describe this as Refresh Token rotation.

### 10.3. Version-Dependent Defaults

How authorized clients are persisted after `authorize(...)`, failure handling, clock skew, and internally created token clients can have varying extension points across Spring Security versions.

The example above **explicitly defines the manager and provider**, reducing reliance on implicit Boot defaults. When upgrading major versions, verify behaviors and APIs against that version's documentation.

### 10.4. When Multiple Manager Beans Exist

If an app has both a request-scoped manager and a job manager, inject using `@Qualifier`:

```java
@Qualifier("jobAuthorizedClientManager")
OAuth2AuthorizedClientManager manager
```

Never let Spring accidentally wire the browser manager into a scheduled job or slap `@Primary` on one carelessly.

## 11. Selecting a Stable Technical Principal

Convention:

```java
private static final String PRINCIPAL = "job:inventory-sync";
private static final String REGISTRATION_ID = "inventory-job";
```

On every run, the manager receives the same pair:

```text
(inventory-job, job:inventory-sync)
```

and can look up the cached token.

### 11.1. Why Not Set the Principal to a Fresh UUID on Every Run?

Wrong:

```java
String principal =
    "job:" + UUID.randomUUID();
```

If every invocation creates a new key, the authorized client store **never finds the previous run's token**, forcing the app to request a new token every time and leaking unnecessary records.

### 11.2. Why Not Use a Human User's Name?

The job runs as the **application**, not on behalf of a user. Never use:

```text
principal = currentUsername
principal = emailFromLastLogin
principal = oidcSubFromSomeSession
```

without an explicit delegated authorization design.

### 11.3. When to Use Multiple Technical Principals?

When the same registration serves multiple tasks needing partitioned storage or auditing:

```text
job:inventory-sync
job:pricing-rebuild
job:nightly-report
```

However, if those tasks share **the same client credentials and scopes**, distinct principal keys only create separate store entries—they do not automatically restrict permissions.

Actual permissions must be enforced via **client registration, scopes, and audience** at the AS/RS, not merely by the principal name in Spring's store.

### 11.4. Multi-Tenant Principal Keys

If a job runs for multiple tenants where each tenant has its own authorization boundary, the identity key may need to include the **verified** tenant ID, registration, and policy; never construct keys from raw untrusted tenant strings.

Storage optimizations must never compromise token isolation across tenants.

## 12. Building `OAuth2AuthorizeRequest`

Whenever a token is needed, build the request:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("inventory-job")
        .principal("job:inventory-sync")
        .build();
```

Then:

```java
OAuth2AuthorizedClient authorized =
    manager.authorize(request);
```

### 12.1. What Does `authorize(...)` Do?

By contract, the manager can:

1. Look up any stored authorized client for `registrationId` + principal.
2. Invoke the provider matching the grant type.
3. If the token is still valid, return the existing authorized client.
4. If absent or needing re-issuance, send a Client Credentials token request.
5. Persist the newly issued authorized client via the service.
6. Return the result or throw an authorization exception.

Exact internals depend on the Spring Security manager, provider, version, and handlers. The key rule is that **the application does not manage a token map in a static variable**.

### 12.2. `authorize(...)` Can Return `null`

Spring Security's manager contract allows returning `null` if no provider can authorize the request under the active configuration/grant rules. Therefore, handle null explicitly rather than chaining immediately:

```java
manager.authorize(request)
    .getAccessToken();
```

in all cases.

### 12.3. Never Attach a Fake End-User `Authentication`

A technical principal string used as a storage key is not proof of a logged-in user. Never construct a `UsernamePasswordAuthenticationToken` with admin authorities just to satisfy the manager.

## 13. Configuring `WebClient` to Call the Right Resource Server

`InventoryHttpConfiguration.java`:

```java
package com.example.inventorysync.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class InventoryHttpConfiguration {

    @Bean("inventoryWebClient")
    WebClient inventoryWebClient(
            WebClient.Builder builder,
            @Value("${inventory.api.base-url}") String baseUrl) {

        return builder
            .baseUrl(baseUrl)
            .build();
    }
}
```

When `WebClient` is on the classpath, Spring Boot typically auto-configures an injectable `WebClient.Builder`.

### 13.1. Use the Approved API Base URL

`inventory.api.base-url` must be an **approved Resource Server**. Never take this URL from:

- Browser query parameters.
- Unvalidated webhook payloads.
- OAuth2 token responses.
- Any inbound `X-Forwarded-Host` header.
- Unvetted/un-allowlisted tenant metadata.

If an attacker controls the destination, Bearer tokens can be exfiltrated to a hostile host.

### 13.2. Do Not Configure a Default Bearer Token on a Shared `WebClient`

Wrong:

```java
// Never use in a singleton/shared WebClient:
WebClient.builder()
    .defaultHeader("Authorization", "Bearer " + someToken)
    .build();
```

A token set from an earlier run can expire or be sent to the wrong API if the client is reused.

We attach the token **per request** right after the manager returns the valid authorized client.

## 14. DTO for the Inventory JSON API

`InventorySnapshot.java`:

```java
package com.example.inventorysync.client;

import java.util.List;

public record InventorySnapshot(
        List<InventoryItem> items) {

    public record InventoryItem(
            String sku,
            int available
    ) {}
}
```

Example response:

```json
{
  "items": [
    {"sku": "SKU-001", "available": 25},
    {"sku": "SKU-002", "available": 0}
  ]
}
```

Jackson is included by the Spring Boot starter in this demo project. For production, add schema validation, payload size limits, pagination support, and domain validation before writing to the database.

### 14.1. DTOs Must Not Contain Access Tokens

Tokens exist strictly for the HTTP `Authorization` header when calling the API, never as fields of `InventorySnapshot`. Never expose tokens in logs, JSON responses, or business tables.

## 15. Client Obtaining the Token and Calling the API

`InventoryApiClient.java`:

```java
package com.example.inventorysync.client;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
public class InventoryApiClient {

    private static final String REGISTRATION_ID =
        "inventory-job";

    private static final String TECHNICAL_PRINCIPAL =
        "job:inventory-sync";

    private static final Duration API_TIMEOUT =
        Duration.ofSeconds(20);

    private final OAuth2AuthorizedClientManager manager;
    private final WebClient webClient;

    public InventoryApiClient(
            @Qualifier("jobAuthorizedClientManager")
            OAuth2AuthorizedClientManager manager,
            @Qualifier("inventoryWebClient")
            WebClient webClient) {

        this.manager = manager;
        this.webClient = webClient;
    }

    public InventorySnapshot fetchSnapshot() {

        OAuth2AuthorizeRequest authorizeRequest =
            OAuth2AuthorizeRequest
                .withClientRegistrationId(REGISTRATION_ID)
                .principal(TECHNICAL_PRINCIPAL)
                .build();

        OAuth2AuthorizedClient authorizedClient =
            manager.authorize(authorizeRequest);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "No authorized client for inventory job"
            );
        }

        String token =
            authorizedClient.getAccessToken().getTokenValue();

        InventorySnapshot response =
            webClient.get()
                .uri("/v1/inventory/snapshot")
                .headers(headers ->
                    headers.setBearerAuth(token)
                )
                .retrieve()
                .bodyToMono(InventorySnapshot.class)
                .block(API_TIMEOUT);

        if (response == null) {
            throw new IllegalStateException(
                "Inventory API returned an empty body"
            );
        }

        return response;
    }
}
```

This is the core of the lab.

### 15.1. Step-by-Step Explanation

1. Build `OAuth2AuthorizeRequest` with a fixed registration ID.
2. Provide the stable technical principal.
3. Call the service-backed manager to obtain a valid authorized client.
4. Fail explicitly if the manager cannot authorize.
5. Extract the Access Token **strictly within method scope**.
6. Set `Authorization: Bearer ...` on that exact API request.
7. Parse the JSON response into the DTO.
8. Bound how long the API call can wait.
9. Never log tokens or place them into responses.

### 15.2. Why Call `block(...)` Here?

`WebClient` returns a reactive `Mono`, while `@Scheduled` in this example is a **synchronous Java method** running on the scheduler thread. Blocking at this boundary keeps the lab clear and enforces a timeout.

**Never call `block()` directly inside a Reactor Netty event loop or a reactive security/request pipeline.** If a job is built fully reactive, return/compose `Mono` along its lifecycle or subscribe via a managed orchestrator/scheduler instead of blocking the event loop.

### 15.3. API-Layer Timeout Differs from Token-Layer Timeout

`block(Duration.ofSeconds(20))` bounds waiting for the reactive HTTP response body in the API call. It **does not cover the synchronous token request** executed earlier inside `manager.authorize(...)`.

In production, configure:

- HTTP connection timeouts.
- Token client response/read timeouts.
- WebClient connect/response timeouts.
- Job execution budgets.
- Scheduler graceful shutdown behavior.
- Bounded API retries.

Never mistake a single `block(Duration)` for a timeout covering the whole authorization pipeline.

### 15.4. If the API Returns `204 No Content`

This example treats an empty body as an error because the API contract requires JSON. For endpoints legitimately returning `204`, design the method to return `Mono<Void>`/`ResponseEntity` or a dedicated response type rather than relying on null checks as a universal rule.

### 15.5. Do Not Request a Fresh Token on Every HTTP Call Manually

Simply call `manager.authorize(...)` whenever a token is needed; **the manager/provider decides** whether a new token must be fetched. Posting to the token endpoint manually at the start of every job defeats the authorized client store.

## 16. The Scheduled Job

`InventorySyncJob.java`:

```java
package com.example.inventorysync.job;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import com.example.inventorysync.client.InventoryApiClient;
import com.example.inventorysync.client.InventorySnapshot;

@Component
public class InventorySyncJob {

    private static final Logger log =
        LoggerFactory.getLogger(InventorySyncJob.class);

    private final InventoryApiClient client;

    public InventorySyncJob(InventoryApiClient client) {
        this.client = client;
    }

    @Scheduled(
        initialDelayString =
            "${inventory.sync.initial-delay-ms:10000}",
        fixedDelayString =
            "${inventory.sync.fixed-delay-ms:300000}"
    )
    public void run() {

        InventorySnapshot snapshot = client.fetchSnapshot();

        List<InventorySnapshot.InventoryItem> items =
            snapshot.items() == null
                ? List.of()
                : snapshot.items();

        // Demo: confirm data was received.
        // Production: validate and perform idempotent DB writes.
        log.info(
            "inventory_sync_completed itemCount={}",
            items.size()
        );
    }
}
```

When the application starts, the scheduling infrastructure invokes `run()` after the initial delay and repeats per the fixed delay.

### 16.1. Why Not Catch Exceptions and Swallow Them?

Code like:

```java
try {
    client.fetchSnapshot();
} catch (Exception ignored) {
    // Do nothing
}
```

hides every failure. Production jobs need:

- Failure metrics and alerts.
- Error codes/categories logged **without tokens**.
- Explicit retry or wait-until-next-run decisions.
- Never marking a sync as successful when data was not persisted.
- Traceability via correlation IDs.

Spring scheduling has default error handling depending on config/version; never rely solely on console stack traces for production monitoring.

### 16.2. DB Synchronization Must Be Idempotent

If a run is retried or two replicas execute concurrently, writes must avoid duplication.

Options include:

- Upsert by `sku` + tenant/source.
- Use source version/`updatedAt` timestamps when available.
- Compare checkpoints or snapshot IDs.
- Wrap atomic units of work in transactions.
- Never increment inventory blindly via addition when the API returns **absolute stock quantities**.
- Define policies for deleted/missing SKUs.

Because this lab focuses on OAuth2, DB persistence is kept as a separate extension so it does not obscure the token architecture.

## 17. Protecting the Worker's HTTP Endpoints

Because the demo includes `starter-web`, the app starts an HTTP server. Even though the job needs no browser login, we must not accidentally expose application endpoints.

Illustrative security chain:

```java
package com.example.inventorysync.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class EndpointSecurityConfiguration {

    @Bean
    SecurityFilterChain workerEndpoints(
            HttpSecurity http) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().denyAll()
            )
            .build();
    }
}
```

This is a **minimal demo policy**: only the health endpoint is permitted; all other HTTP routes are denied.

In production, also configure actuator/management exposure, reverse proxies, network ACLs, and authentication for sensitive management endpoints. `permitAll()` on `/actuator/health` does not mean exposing detailed health internals publicly.

### 17.1. Why Not Enable `oauth2Login()`?

The worker has no browser user. Enabling browser OAuth2 Login just to get Spring Security OAuth2 Client causes anonymous HTTP requests to redirect needlessly to the OP.

`OAuth2AuthorizedClientManager` and `ClientRegistrationRepository` do not require browser login to use client credentials.

### 17.2. HTTP Security Chain vs. Outbound OAuth2

`SecurityFilterChain` governs **inbound HTTP requests**. The manager and `WebClient` handle **outbound OAuth2 token and API requests**.

Do not confuse:

```text
anyRequest().denyAll()
```

with blocking Spring Boot from calling outbound token endpoints or APIs. Those are two different boundaries.

### 17.3. Non-Web Workers

If you convert the worker to headless, you can remove the Servlet server completely. Verify auto-configured beans, scheduling lifecycles, health/status reporting, and operational tooling. Never keep an HTTP server running just to get `ClientRegistrationRepository` when you can configure the repository cleanly for a headless architecture.

## 18. First-Run Flow

First run:

```text
(1) @Scheduled triggers
    |
(2) manager.authorize(inventory-job, job:inventory-sync)
    |
(3) AuthorizedClientService has no stored authorized client
    |
(4) clientCredentials provider calls AS token endpoint
    |
(5) AS validates client-id/client-secret and grants scopes
    |
(6) manager saves OAuth2AuthorizedClient in service
    |
(7) InventoryApiClient calls Inventory API with Access Token
    |
(8) API returns data
    |
(9) Job processes data and records metrics/log metadata
```

This is the expected behavior when everything is configured and AS/RS are reachable.

### 18.1. No Refresh Token in the Standard Flow

Client Credentials token responses typically omit `refresh_token`. When the token expires, the client uses its client credentials to obtain a new Access Token. Consequently, concepts like "refresh token rotation" are **not central to this lab**.

### 18.2. Tokens May Be JWT or Opaque

The client does not need to parse a JWT just to attach the token string to the Bearer header. The Resource Server is responsible for validating the token appropriately.

Never have the job base64-decode a JWT payload and trust an unverified `scope` claim as authorization proof.

## 19. Second-Run Flow: Reusing Tokens

If the previous run saved:

```text
registrationId = inventory-job
principalName = job:inventory-sync
accessToken = token-A
expiresAt = 11:00
```

and the job runs again at 10:05, the manager/provider returns the cached authorized client **without hitting the token endpoint again** as long as the token satisfies expiry policy.

### 19.1. What Does the Authorized Client Store Accomplish?

- Cuts down unnecessary token requests.
- Reduces load on the Authorization Server.
- Associates the token with its logical principal and registration.
- Helps the manager decide when to re-authorize.
- Centralizes failure cleanup and observability.
- Enables sharing across instances when backed by shared storage.

### 19.2. Do Not Assume a Token Works Until the Exact Second of Expiry

Managers/providers typically factor in **clock skew** to avoid sending tokens right on the edge of expiration. For example, a token expiring at 11:00 may be re-issued slightly before 11:00 according to skew settings.

Furthermore, a Resource Server can revoke a token before its expiry. A non-expired timestamp **does not guarantee the RS will accept it**.

### 19.3. Measure Token Issuance Counts

In demos, observe the test stub token endpoint:

```text
Job run #1: token endpoint calls = 1
Job run #2 (token still valid): calls remain = 1
Job run #3 (token needs re-issuance): calls increment
```

Verify this caching behavior explicitly rather than only checking that the API returns 200.

## 20. Why Not Keep the Token in a `static` Variable?

Anti-pattern:

```java
private static String accessToken;
```

and:

```java
if (accessToken == null) {
    accessToken = callTokenEndpointManually();
}
```

This fails to handle:

- Token expiry and clock skew.
- Multiple registrations.
- Per-principal/per-tenant isolation.
- Concurrent jobs and replicas.
- Refresh/re-authentication failures.
- Persistent storage.
- Cleanup and revocation.
- Token type, scope, and expiry metadata.
- Clean unit testing.

Use `OAuth2AuthorizedClient`/service/manager for proper lifecycle management instead of inventing a custom token cache.

## 21. Comparing Authorized Client Stores

| Store | Pros | Limitations |
|---|---|---|
| `InMemoryOAuth2AuthorizedClientService` | Easy config, fast, great for tests/local. | Lost on restart; each replica has its own cache. |
| JDBC-backed service | Survives restarts; shared across replicas. | Needs schema, DB ACLs/encryption, concurrency handling. |
| Custom Redis-backed service | Flexible TTL, caching, distributed access. | Must define serialization, consistency, key/secret protection. |
| Custom encrypted store/KMS | Strict compliance with org credential policies. | Higher complexity; requires key rotation and HA design. |
| No token storage; fetch every time | Simple for very infrequent jobs. | Increases token endpoint traffic and rate-limit risk. |

**There is no single best store for every system.** A once-a-day job receiving a short-lived token on a single instance may not need persistent storage. A multi-service/multi-pod platform aiming to minimize token requests will benefit from a shared store.

### 21.1. Do Not Confuse Session Repositories with Service Repositories

In Servlet apps, `OAuth2AuthorizedClientRepository` is tied to HTTP request/response lifecycles and often uses `HttpSession`.

`OAuth2AuthorizedClientService` stores by registration and principal name without needing a Servlet request.

For scheduled jobs, a service-backed manager is the right fit.

## 22. Using the JDBC Authorized Client Service

Spring Security provides **`JdbcOAuth2AuthorizedClientService`** in supported versions.

Example bean replacing the in-memory store:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Bean
OAuth2AuthorizedClientService authorizedClientService(
        JdbcOperations jdbc,
        ClientRegistrationRepository registrations) {

    return new JdbcOAuth2AuthorizedClientService(
        jdbc,
        registrations
    );
}
```

**Replace**—do not keep the in-memory `authorizedClientService` bean from Section 9 alongside this unless you explicitly manage qualifiers or `@Primary`.

### 22.1. What Else Must Be Added?

- `spring-boot-starter-jdbc` or appropriate JDBC dependencies.
- A `DataSource` with securely managed credentials.
- Schema matching the **SQL scripts for your exact Spring Security version and database dialect**.
- A migration tool such as Flyway or Liquibase if used by your organization.
- Transaction/locking and connection error handling.
- Database backups, encryption, and retention policies.
- Least-privilege DB permissions for the service account.
- Cleanup/handling for stale tokens when registration IDs or principal keys change.

**Do not assume Boot auto-creates the OAuth2 authorized client table just because you added `JdbcOAuth2AuthorizedClientService`.**

### 22.2. The Authorized Client Store Holds Sensitive Credentials

An Access Token is a bearer credential. If an AS issues a Refresh Token in an extended flow, the sensitivity is even higher.

Databases, snapshots, replicas, exports, and admin consoles must all be secured. Storage-layer encryption at rest helps, yet it does not stop anyone with DB query privileges from reading plaintext tokens; if required by your threat model, add application/KMS-level encryption and strict key access isolation.

### 22.3. Do Not Write the Schema from Memory

The JDBC service schema can vary across versions and dialects. Use the official schema for your exact version and test migrations rather than copying a `CREATE TABLE` statement from a different version.

### 22.4. When Renaming a Registration ID

The store may hold records keyed by `inventory-job`. If a later upgrade renames it to `inventory-scheduler`, old records will no longer match.

When renaming keys, plan an explicit migration or accept fetching fresh tokens and cleaning up legacy rows per policy.

## 23. Redis/Custom Stores with Multiple Replicas

A custom `OAuth2AuthorizedClientService` can persist authorized clients in Redis. When doing so, define:

- Key format: registration ID + technical principal + optional trusted tenant.
- Safe, versioned serialization without relying on arbitrary Java object serialization.
- TTL aligned with Access Token expiry.
- Atomic updates/CAS/locking during concurrent re-issuance.
- Redis ACLs, network isolation, TLS, and encryption.
- Cleanup on client revocation or secret rotation.
- Backups/retention per policy.
- Tests for stale data and failover.

### 23.1. Never Key the Cache by Registration Alone

If one registration serves multiple principals or tenants, a key like:

```text
inventory-job
```

can mix up authorized clients. Use a complete key `(registrationId, principalName)`, plus a trusted tenant boundary where needed.

### 23.2. TTL Must Not Break Manager Logic

If the store evicts a record before token expiry, the manager simply fetches a token early—often acceptable if accounted for.

If the store retains a record **past token expiry**, the manager/provider must still detect expiration and re-authorize; never attach an expired token just because it is still in Redis.

### 23.3. A Shared Token Is Not Distributed Scheduling

Two pods sharing an authorized client store **can still run the inventory sync job simultaneously**. Sharing cached tokens does not prevent duplicate business execution.

You need separate orchestration or locking.

## 24. Multiple Replicas and Execution Overlap

Suppose three replicas are deployed:

```text
Kubernetes deployment
  ├── pod A: @Scheduled InventorySyncJob
  ├── pod B: @Scheduled InventorySyncJob
  └── pod C: @Scheduled InventorySyncJob
```

Each pod runs its own scheduler. Without coordination, every pod executes the same job.

### 24.1. How to Prevent Duplicate Work

- Run a single dedicated worker replica if suitable.
- Use a Kubernetes `CronJob` with an appropriate concurrency policy.
- Use a distributed lock (DB/Redis/coordination service).
- Use a queue + consumer-group/lease pattern.
- Make upserts idempotent to tolerate retries.
- Persist checkpoints/lock leases and handle crashes/retries.

### 24.2. Distributed Locks Do Not Replace Token Security

A lock only ensures (within its implementation guarantees) that one worker executes the task. It does not validate Access Token audience/scopes or partition the authorized client store.

### 24.3. Token Re-Issuance Races

If three pods simultaneously notice the token needs re-issuance:

```text
pod A -> token endpoint -> token-A
pod B -> token endpoint -> token-B
pod C -> token endpoint -> token-C
```

With `client_credentials`, an AS may issue multiple concurrent Access Tokens; while not always a protocol error, it wastes quota and risks rate limits.

A shared store with coordination/locking mitigates thundering herds. Do not assume Spring Security automatically acquires a JDBC row lock across all deployments and versions.

### 24.4. Why Does This Differ from Refresh Token Rotation?

In browser/delegated clients, concurrent refreshes race because Refresh Tokens are rotated/revoked. With standard client credentials, the client requests a fresh Access Token directly with its credentials **without a Refresh Token**; the race mainly impacts efficiency, rate limits, and store consistency depending on AS policy.

## 25. Expiration and Clock Skew

Access Token responses carry `expires_in`; Spring Security represents expiry as an `Instant` on `OAuth2AccessToken`.

Example:

```text
issuedAt:  10:00:00
expiresAt: 11:00:00
clockSkew: 60 seconds

Authorize at 10:30 -> token likely reusable
Authorize at 10:59 -> manager/provider may reissue
```

### 25.1. Why Re-Issue Before Exact Expiry?

- Clock drift between client, AS, and RS.
- Network latency.
- Time spent processing the API request.
- Different leeway settings on the RS.
- Requests started before expiry arriving at the RS after expiry.

Never wait until the exact second of expiration to fetch a new token.

### 25.2. Do Not Parse JWTs Manually for Expiry When Metadata Already Exists

`authorizedClient.getAccessToken().getExpiresAt()` provides the expiry metadata used by the manager. Never decode a JWT manually and trust unverified claims just to manage caching.

### 25.3. Adjusting Skew per API/Version

Some `OAuth2AuthorizedClientProvider` implementations expose clock skew configuration. When customizing it, check the builder/provider API for your exact Spring Security version and test the behavior.

Never copy a nonexistent setter or change system-wide clocks just to pass an expiry test.

## 26. Token Endpoint Errors

Token acquisition can fail due to:

| Error | Likely Cause | Response |
|---|---|---|
| `invalid_client` | Wrong Client ID/secret/method or expired secret. | Check client registration and secret rotation; never retry endlessly. |
| `unauthorized_client` | Grant not permitted for client. | Verify AS registration policy. |
| `invalid_scope` | Scope not authorized. | Fix scope contract; never request overly broad scopes. |
| HTTP 429 | AS rate limit. | Bounded backoff, reduce token requests, monitor. |
| HTTP 5xx | AS unavailable. | Bounded retries / circuit breaker; record job failure state. |
| TLS/certificate error | Trust, cert, or proxy mismatch. | Fix TLS; never disable verification. |
| Timeout | Slow AS or network. | Bounded timeout, retry policy, and alerts. |
| Malformed JSON | Response/protocol mismatch. | Fail closed, log safe metadata. |
| Missing expiry or wrong `token_type` | Contract/provider mismatch. | Verify AS behavior against OAuth2 client implementation. |

### 26.1. Never Use a Catch-All Fallback Machine Token

Wrong:

```java
try {
    return manager.authorize(request);
} catch (Exception ex) {
    return cachedTokenFromAnotherClient;
}
```

Reusing a token from another client or tenant creates severe cross-boundary authorization bugs.

### 26.2. Never Log Client Secrets on 401

Some HTTP libraries offer debug/wire logging. When diagnosing `invalid_client`, always redact `Authorization: Basic` headers and form parameters.

### 26.3. Never Send Token Requests Over Plaintext HTTP

Production requires HTTPS with proper certificate and hostname verification. Never disable TLS verification to bypass staging certificate errors.

## 27. Inventory API Errors: 401, 403, and 5xx

Even after acquiring a token, the API may reject the request. Distinguish:

| Status | Common Meaning | Action |
|---|---|---|
| **401 Unauthorized** | Expired, invalid, or wrong-audience/issuer token, or different auth required. | Safely inspect `WWW-Authenticate`/error codes; evict/reissue token per policy. |
| **403 Forbidden** | Token recognized, but lacks required scope/permission. | Never retry token acquisition infinitely; check AS/RS policy. |
| **429 Too Many Requests** | Rate limit hit. | Back off per header/policy with bounded attempts. |
| **500/502/503/504** | Resource Server or gateway failure. | Bounded retries if idempotent; alert if persistent. |
| **400** | Invalid request contract. | Fix payload/path; do not request a new token. |
| **404** | API route/snapshot does not exist. | Check version/path; do not assume token failure. |

### 27.1. API 401 Is Not `invalid_client`

`invalid_client` occurs during client authentication at the **token endpoint**. An API 401 happens later at the Resource Server.

Keep these two distinct in monitoring and retry logic.

### 27.2. Bound Retries on 401

One conditional approach:

1. Receive 401.
2. Check whether the error indicates a revoked/expired token.
3. If policy permits, remove the authorized client for **that exact registration + technical principal**.
4. Fetch a new token on the next scheduled run or retry **at most once**.
5. If 401 persists, fail and alert rather than looping endlessly.

Never wipe all tokens across all users/registrations when a single API returns 401.

### 27.3. 403 Usually Cannot Be Fixed by Fetching a New Token

If the AS only grants `inventory.read` and the API demands `inventory.write`, fetching another token with the same scope will still return 403.

Fix the contract/permissions through an approved review rather than blindly adding `inventory.write` when the job does not need it.

### 27.4. Never Log Raw Error Bodies or Headers

API error responses can contain PII or sensitive internals. Restrict logs to:

```text
event=inventory_api_failed
registration=inventory-job
httpStatus=401
operation=snapshot-read
correlationId=<non-secret>
```

Never print Bearer tokens or Basic client secrets.

## 28. Controlled Removal of an Authorized Client

`OAuth2AuthorizedClientService` provides:

```java
authorizedClientService.removeAuthorizedClient(
    "inventory-job",
    "job:inventory-sync"
);
```

Use it when:

- The client was revoked.
- The API/AS returns an error confirming the authorized client is invalid.
- The client registration was rotated or disabled.
- An operator/system requests invalidation per policy.
- The token store contains a corrupted entry.

### 28.1. Do Not Call Remove After Every Successful Run

If every run removes the record:

```text
authorize -> call API -> remove authorized client
```

there is nothing left to reuse next time, defeating the cache.

### 28.2. Local Removal Does Not Necessarily Revoke the Token at the AS

`removeAuthorizedClient(...)` removes the entry from the application's store. The issued Access Token may remain valid until expiry unless explicitly revoked at the AS.

If immediate revocation is required by policy, verify whether the AS provides a revocation endpoint and integrate that workflow.

### 28.3. Never Remove the Wrong Technical Principal

When a token store holds multiple technical principals, remove only the exact targeted key. Never let user input choose which record to delete.

## 29. Retries and Idempotency

Retries can absorb transient network blips, but must be strictly bounded:

- Maximum attempt count.
- Backoff with jitter.
- Overall timeout budget.
- Retryable status codes.
- HTTP operation idempotency.
- Token endpoint rate limits.
- Distinction between 401/403 and 5xx.
- Interaction with the next scheduled trigger.

### 29.1. Reading Snapshots Is Safer to Retry Than Mutations

`GET /v1/inventory/snapshot` is a read operation; bounded retries on connection/5xx errors are generally acceptable within API contract and resource limits.

`POST /v1/inventory/adjust-stock` has side effects and must never be retried blindly without an idempotency key or transaction semantics.

### 29.2. Retry Token Requests Cautiously

A Client Credentials token endpoint may mint a new Access Token on every request. Retrying after a timeout when the AS already issued a token creates extra tokens and consumes quota.

Apply bounded retries/backoff, monitor rate limits, and favor token reuse.

### 29.3. Never Swallow Errors and Report Success

If the API fails, the job must never emit:

```text
inventory_sync_completed=true
```

when no data was synchronized. Track `attempted`, `succeeded`, `failed`, and `partial` separately.

## 30. Observing the Job and Token Lifecycle

Recommended metrics:

| Metric / Event | Purpose |
|---|---|
| `inventory_sync_started` | Counts scheduled starts. |
| `inventory_sync_succeeded` | Job completed cleanly. |
| `inventory_sync_failed` | Categorized job failures. |
| `inventory_sync_duration` | Total execution duration. |
| `oauth2_token_acquisition_failed` | AS/token endpoint failures. |
| `oauth2_authorized_client_cache_hit` | With proper instrumentation, reflects token reuse. |
| `inventory_api_http_status` | Grouped Resource Server status codes. |
| `inventory_sync_items_processed` | Business items processed. |
| `inventory_sync_last_success_timestamp` | Detects stalled or delayed jobs. |

### 30.1. Never Use Access Tokens as Metric Labels

Wrong:

```text
oauth2_token{token="eyJ..."} = 1
```

Metric labels can be retained long-term and exported to external observability systems. Use only safe registration aliases, environments, operations, status/error families, and correlation IDs.

### 30.2. Never Log Raw `OAuth2AuthorizedClient`

Some `toString()` outputs or debuggers expose token metadata or credentials. Never dump the full object during production incidents.

### 30.3. Alert on SLOs

For a job running every 5 minutes, alert when no successful run occurs within an agreed SLO window rather than paging on every single transient error. However, `invalid_client`/revoked-secret errors may warrant immediate alerting.

## 31. AS and Resource Server Authorization

A valid machine token must satisfy all of the following:

1. Authorization Server identifies the client.
2. Token is issued under the right grant and scopes.
3. Resource Server validates the token.
4. API business policy permits that client/service to access the resource.
5. Only authorized tenant/resource data is returned.

### 31.1. Scopes Are Not User Roles

`inventory.read` is an API token permission. Never map it to `ROLE_ADMIN` on a browser login principal.

### 31.2. Audience Can Matter More Than Scope Alone

A token with `scope=inventory.read` and `aud=billing-api` must be rejected by the Inventory API. The Resource Server must enforce the proper audience/resource.

How audience/resource is requested at token issuance depends on AS protocol extensions and policy (e.g., resource indicators or provider-specific parameters). Never blindly tack on an `audience` form field assuming every AS supports it.

### 31.3. Least Privilege

Giving the job a dedicated client registration with only `inventory.read` shrinks the blast radius compared to a "super client" holding every scope.

If the job needs `inventory.write` in the future, add it through a security review rather than pre-provisioning it upfront.

### 31.4. Network Restrictions Complement OAuth2

For internal APIs, combine OAuth2 with private network routing, mTLS, ingress authentication, and outbound egress allowlists. Never treat OAuth2 tokens as a reason to drop network segmentation.

## 32. Protecting Client Secrets

`client_secret_basic` is a client authentication method, not a shield that hides the secret from all components.

### 32.1. Avoid Hardcoding in Source

Wrong:

```yaml
client-secret: very-real-production-secret
```

Right direction:

```yaml
client-secret: ${INVENTORY_CLIENT_SECRET}
```

with the secret injected from a controlled environment or secret manager.

### 32.2. Avoid Exposing via Command Line

Passing secrets directly in command-line arguments can leak them in process listings, shell history, or CI logs. Prefer secret managers or controlled process environments over plaintext CLI credentials.

### 32.3. Secret Rotation

When the AS supports client secret rotation:

1. Generate the new secret.
2. Ensure the AS accepts the new secret at cutover time.
3. Update the secret store and deployment.
4. Monitor token acquisition success.
5. Revoke the old secret on schedule.
6. Account for cached authorized clients.
7. Never dump secrets or tokens into logs.

Cached tokens may remain valid until expiry per AS policy; do not assume secret rotation automatically revokes all previously issued Access Tokens.

### 32.4. Secretless Alternatives

Where infrastructure allows, consider mTLS, workload identity federation, or `private_key_jwt` per AS support/policy to eliminate static shared secrets.

This is a dedicated design choice; never alter the authentication method in code without updating the registration and AS contract.

## 33. Testing the API Client Layer Without a Real Authorization Server

You can unit-test `InventoryApiClient` using:

- A mocked `OAuth2AuthorizedClientManager` returning an authorized client fixture.
- A `WebClient` backed by a mock `ExchangeFunction`.
- Assertions checking the token header and target destination.
- Zero open HTTP sockets.
- Zero real credentials.

### 33.1. Creating `ClientRegistration` and `OAuth2AuthorizedClient` Fixtures

```java
import java.time.Instant;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

ClientRegistration registration =
    ClientRegistration.withRegistrationId("inventory-job")
        .clientId("synthetic-test-client")
        .clientSecret("synthetic-test-secret")
        .authorizationGrantType(
            AuthorizationGrantType.CLIENT_CREDENTIALS
        )
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC
        )
        .tokenUri("https://auth.example.test/oauth2/token")
        .scope("inventory.read")
        .build();

OAuth2AccessToken token = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "synthetic-access-token",
    Instant.parse("2026-01-01T00:00:00Z"),
    Instant.parse("2030-01-01T00:00:00Z")
);

OAuth2AuthorizedClient authorizedClient =
    new OAuth2AuthorizedClient(
        registration,
        "job:inventory-sync",
        token
    );
```

This fixture **never calls the token endpoint** and does not verify JWTs; it simply models an authorized client returned by the manager.

### 33.2. Full Header and Response Test

```java
package com.example.inventorysync;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;

import com.example.inventorysync.client.InventoryApiClient;

import reactor.core.publisher.Mono;

class InventoryApiClientTest {

    @Test
    void usesMachineTokenOnlyForApprovedInventoryApi() {

        ClientRegistration registration =
            ClientRegistration
                .withRegistrationId("inventory-job")
                .clientId("test-client")
                .clientSecret("synthetic-secret")
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS
                )
                .tokenUri("https://auth.example.test/token")
                .build();

        OAuth2AccessToken token = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "fixture-access-token",
            Instant.parse("2026-01-01T00:00:00Z"),
            Instant.parse("2030-01-01T00:00:00Z")
        );

        OAuth2AuthorizedClient client =
            new OAuth2AuthorizedClient(
                registration,
                "job:inventory-sync",
                token
            );

        OAuth2AuthorizedClientManager manager =
            mock(OAuth2AuthorizedClientManager.class);

        when(manager.authorize(
            any(OAuth2AuthorizeRequest.class)
        )).thenReturn(client);

        ExchangeFunction fakeTransport = request -> {
            assertThat(request.url().toString()).isEqualTo(
                "https://api.example.test/v1/inventory/snapshot"
            );

            assertThat(request.headers().getFirst(
                HttpHeaders.AUTHORIZATION
            )).isEqualTo("Bearer fixture-access-token");

            return Mono.just(
                ClientResponse.create(HttpStatus.OK)
                    .header(
                        HttpHeaders.CONTENT_TYPE,
                        MediaType.APPLICATION_JSON_VALUE
                    )
                    .body(
                        "{\"items\":["
                        + "{\"sku\":\"SKU-001\",\"available\":25}"
                        + "]}"
                    )
                    .build()
            );
        };

        WebClient webClient = WebClient.builder()
            .baseUrl("https://api.example.test")
            .exchangeFunction(fakeTransport)
            .build();

        InventoryApiClient api =
            new InventoryApiClient(manager, webClient);

        var snapshot = api.fetchSnapshot();

        assertThat(snapshot.items()).hasSize(1);
        assertThat(snapshot.items().get(0).sku())
            .isEqualTo("SKU-001");
    }
}
```

This is an **isolated unit test**: it proves the code asks the manager for an authorized client, attaches the right token, and parses JSON from the HTTP client abstraction.

### 33.3. What Does This Test Not Prove?

- That a real AS issued the token.
- That `client_credentials` sent the right `grant_type`.
- That the manager reuses tokens from the store.
- That the real Resource Server accepts the token's audience/scope.
- That TLS/certificates to the AS/API are valid.
- That token endpoint errors are handled properly.
- Distributed storage and scheduler concurrency.

Those belong to tests at different boundaries.

### 33.4. Testing Principal and Registration Parameters

Use Mockito `ArgumentCaptor<OAuth2AuthorizeRequest>`:

```java
var captor =
    ArgumentCaptor.forClass(OAuth2AuthorizeRequest.class);

verify(manager).authorize(captor.capture());

assertThat(captor.getValue().getClientRegistrationId())
    .isEqualTo("inventory-job");

assertThat(captor.getValue().getPrincipal().getName())
    .isEqualTo("job:inventory-sync");
```

Verify the technical principal **does not change across runs**.

## 34. Testing When the Manager Returns No Authorized Client

A negative test should stub:

```java
when(manager.authorize(
    any(OAuth2AuthorizeRequest.class)
)).thenReturn(null);
```

Then:

```java
assertThatThrownBy(api::fetchSnapshot)
    .isInstanceOf(IllegalStateException.class)
    .hasMessageContaining("No authorized client");
```

This verifies **fail-closed** behavior: without a token, **do not call the API with another user's session cookie** or an empty Bearer header.

### 34.1. Never Fall Back to the Last Access Token

If the manager returns `null`, never fall back to a static token from a prior run or a token from a different registration just to "give it a try".

### 34.2. Never Include Secrets in Exception Messages

Report only the registration alias or job operation, never token strings or client secrets in exception messages or stack traces.

## 35. Testing Token Reuse in the Authorized Client Store

To test the manager and store without calling a production AS, create a **fake `OAuth2AuthorizedClientProvider`** that mints a new token only when no valid authorized client exists:

```java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.oauth2.client.*;
import org.springframework.security.oauth2.client.registration.*;
import org.springframework.security.oauth2.core.*;

ClientRegistration registration =
    ClientRegistration.withRegistrationId("inventory-job")
        .clientId("test-client")
        .clientSecret("test-secret")
        .authorizationGrantType(
            AuthorizationGrantType.CLIENT_CREDENTIALS
        )
        .tokenUri("https://auth.example.test/token")
        .build();

ClientRegistrationRepository registrations =
    new InMemoryClientRegistrationRepository(registration);

OAuth2AuthorizedClientService store =
    new InMemoryOAuth2AuthorizedClientService(registrations);

AtomicInteger grants = new AtomicInteger();

OAuth2AuthorizedClientProvider fakeProvider = context -> {
    OAuth2AuthorizedClient old =
        context.getAuthorizedClient();

    if (old != null &&
        old.getAccessToken().getExpiresAt()
            .isAfter(Instant.now().plusSeconds(60))) {
        return null;
    }

    grants.incrementAndGet();

    var token = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "token-fixture-" + grants.get(),
        Instant.now(),
        Instant.now().plusSeconds(3600)
    );

    return new OAuth2AuthorizedClient(
        context.getClientRegistration(),
        context.getPrincipal().getName(),
        token
    );
};

var manager =
    new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        registrations,
        store
    );

manager.setAuthorizedClientProvider(fakeProvider);

var request = OAuth2AuthorizeRequest
    .withClientRegistrationId("inventory-job")
    .principal("job:inventory-sync")
    .build();

var first = manager.authorize(request);
var second = manager.authorize(request);

assertThat(first).isNotNull();
assertThat(second).isNotNull();
assertThat(grants.get()).isEqualTo(1);
```

This is a **test fragment** needing JUnit/AssertJ imports and setup. The fake provider performs no HTTP calls and models the policy "if the token is still valid, do not mint a new one".

### 35.1. What Does This Test Highlight?

- The authorized client is persisted by registration and principal.
- On the second call, the manager loads the stored client.
- The fake provider does not issue a new token while the current one is valid.
- Changing the technical principal changes the storage key.

### 35.2. It Does Not Prove Real HTTP Token Exchange

The fake provider skips sending `grant_type=client_credentials` and client authentication. Add an **integration test with a token endpoint stub** to verify serialization and authentication methods.

### 35.3. Token Expiry Tests Need Controlled Time

To test expiration, supply an already-expired token fixture or inject a `Clock` into the fake provider. Avoid depending on wall-clock timing in assertions, which causes flaky tests.

## 36. Integration Testing with an Authorization Server Stub

A rigorous lab tests the HTTP boundary without calling a production OP/AS.

Use a mock HTTP server on localhost with a dynamic port (e.g., WireMock, `MockWebServer`, or another test server) implementing the contract:

```text
POST http://127.0.0.1:<dynamic-port>/oauth2/token

Content-Type: application/x-www-form-urlencoded
Authorization: Basic <synthetic-client-credentials>

Body:
  grant_type=client_credentials
  scope=inventory.read
```

Stub response:

```json
{
  "access_token": "stub-inventory-token",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "inventory.read"
}
```

Point the test registration to the dynamic token URL, then call the manager:

```java
var authorized = manager.authorize(
    OAuth2AuthorizeRequest
        .withClientRegistrationId("inventory-job")
        .principal("job:inventory-sync")
        .build()
);
```

Assert:

- HTTP token request carries `grant_type=client_credentials`.
- Client credentials are sent using the method expected by the test AS.
- Scope is accurate.
- No browser or authorization code redirect occurs.
- Authorized client is saved in the service store.
- Access Token has expiry metadata.
- A second `authorize` call while the token is valid does not hit the token endpoint unnecessarily.

### 36.1. Why Use a Stub Instead of a Real AS?

- Uses no real client secrets.
- Does not depend on Internet connectivity, MFA, or production token quotas.
- Deterministically reproduces `invalid_client`, 429, and 5xx errors.
- Counts exact token requests.
- Controls `expires_in` and response formats.
- CI can run offline.

### 36.2. Never Hardcode Test Ports

When CI runs jobs in parallel, fixed ports collide. Bind the stub to localhost on an OS-assigned dynamic port.

### 36.3. Token Client Implementations May Vary Across Versions

Spring Security provides implementations for sending Client Credentials token requests over HTTP; extension points can evolve across release lines. When customizing HTTP clients, timeouts, proxies, or mTLS, consult the APIs for your exact Spring Security version.

Never assume a single `Default...TokenResponseClient` class is the only API across every major version.

## 37. Integration Testing with a Resource Server Stub

Next, stand up an Inventory API stub:

```http
GET /v1/inventory/snapshot HTTP/1.1
Authorization: Bearer stub-inventory-token
```

Return:

```json
{
  "items": [
    {"sku": "SKU-001", "available": 25}
  ]
}
```

Verify:

- URL targets the **approved API host**.
- Exact `Authorization: Bearer` header.
- No client secret or Refresh Token in the request.
- 200 JSON parses accurately.
- 401/403/429/503 responses are classified properly.
- Redirects to untrusted hosts never carry the token.
- Raw tokens never appear in logs.

### 37.1. Test Requests Against Other Hosts

If the service could ever accept an absolute URL influenced by input, verify it cannot send a Bearer token to an unapproved host. Prefer client APIs accepting only relative paths, a fixed base URL, and an outbound destination allowlist.

### 37.2. A Stub Does Not Replace Resource Server Validation

A stub may accept any Bearer token fixture. Test token signature/audience/scope enforcement separately against the Resource Server JWT/introspection layer.

## 38. Why Not Use `@WithMockUser` or `oidcLogin()`?

Helpers such as:

```java
@WithMockUser
```

and:

```java
mockMvc.perform(get("/account")
    .with(oidcLogin()));
```

exist to **simulate authentication inside an HTTP request**.

A client credentials job **has no browser login principal**. Testing the job with a mock user hides architectural bugs because the code might accidentally rely on `SecurityContextHolder` or a user token.

Tests should invoke directly:

```java
inventoryApiClient.fetchSnapshot();
```

against a mock manager/store/HTTP boundary.

### 38.1. If a Job Can Be Triggered from an Admin Endpoint

Some systems let an admin click "Run now". The admin's request is authenticated to authorize starting the job, yet **the token the job uses to call the M2M API must still be the machine token** if the API contract requires machine authentication.

Separate:

```text
Inbound: admin authenticated + authorized to start job
Outbound: job's client_credentials token
```

Never pass the admin's token to the background job simply because the trigger request had a `SecurityContext`.

## 39. Reactive Variant: Do Not Use the Servlet Manager

If a worker is built entirely with Reactor/WebFlux, consider:

- `ReactiveClientRegistrationRepository`.
- `ReactiveOAuth2AuthorizedClientService`.
- Appropriate `ReactiveOAuth2AuthorizedClientManager`.
- `ReactiveOAuth2AuthorizedClientProvider` with Client Credentials.
- Reactor `Mono<OAuth2AuthorizedClient>` and `WebClient`.

Conceptual example:

```java
ReactiveOAuth2AuthorizeRequest authorizeRequest =
    ReactiveOAuth2AuthorizeRequest
        .withClientRegistrationId("inventory-job")
        .principal("job:inventory-sync")
        .build();
```

**Note:** In common Spring Security versions, the actual request class for the reactive manager is still `OAuth2AuthorizeRequest`, while the manager returns `Mono<OAuth2AuthorizedClient>`. Never copy the conceptual snippet above as runnable code without checking your version's API; below is the pattern matching the actual type contract:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("inventory-job")
        .principal("job:inventory-sync")
        .build();

Mono<OAuth2AuthorizedClient> result =
    reactiveAuthorizedClientManager.authorize(request);
```

In Spring Security Reactive, repository/service/provider wiring differs from Servlet. Never use `DefaultOAuth2AuthorizedClientManager` and never call `block()` inside a reactive event loop.

### 39.1. Why Do Names Differ While Ideas Match?

Even across different stacks, the logical key `(registrationId, principalName)`, token grants, and isolation remain the same. The difference lies in lifecycle, cancellation, context, and reactive storage.

### 39.2. Testing with `StepVerifier`

```java
StepVerifier.create(
    reactiveAuthorizedClientManager.authorize(request)
)
.assertNext(client -> {
    assertThat(client.getClientRegistration()
        .getRegistrationId()).isEqualTo("inventory-job");
})
.verifyComplete();
```

This fragment requires a reactive manager bean and fixtures. Never treat `StepVerifier` running against a fake manager as proof that a real HTTP token endpoint was called.

## 40. Never Put Credentials in URLs, Logs, or Exceptions

### 40.1. Places to Avoid Completely

Never construct:

```text
https://api.example.test/snapshot?access_token=...
https://auth.example.test/token?client_secret=...
```

Query strings easily leak into access logs, browser history, tracing, or `Referer` headers.

### 40.2. Never Enable HTTP Wiretapping by Default in Production

Reactor Netty wiretaps or HTTP client debugging can log headers and bodies depending on configuration. Redact:

- `Authorization`.
- `Proxy-Authorization`.
- `Cookie`/`Set-Cookie`.
- `client_secret`.
- `access_token`/`refresh_token`.
- Token responses.
- Sensitive API payloads.

### 40.3. Logging Safe Metadata

Example:

```text
event=inventory_sync_token_error
registrationId=inventory-job
grantType=client_credentials
errorCode=invalid_client
environment=staging
correlationId=job-run-opaque-id
```

Never log `OAuth2AuthorizedClient` objects or raw exception response bodies if they may contain credentials.

## 41. Resource Isolation and Multi-Tenancy

A system might run jobs for:

```text
tenant alpha -> inventory-alpha client
tenant beta  -> inventory-beta client
```

If all tenants share:

```text
registrationId = inventory-job
principal = job:inventory-sync
```

while tokens are issued per tenant, there is a risk of storing or reusing the wrong tenant's token.

### 41.1. Two Clear Strategies

**Strategy A — Dedicated registrations:**

```text
inventory-alpha
inventory-beta
```

Each registration has its own client credentials and AS policy.

**Strategy B — Shared registration, isolated by trusted principal/tenant:**

```text
registrationId = inventory-job
principal = job:inventory-sync:tenant-alpha
principal = job:inventory-sync:tenant-beta
```

Only appropriate when the AS/RS genuinely issues tokens scoped to a trusted tenant context and the application controls the mapping. Changing the principal name **does not change the token's audience or scope**; if both use identical client credentials without extra authorization semantics, both tokens hold the same permissions.

### 41.2. Never Trust Tenant IDs from Input

Tenant-to-registration mappings must come from a catalog or internal authorization policy, never from arbitrary query parameters or headers.

### 41.3. Avoid Global Default Authorized Clients

An OAuth2 filter that automatically attaches a default token to every request can send Tenant A's token to Tenant B's API.

In this lab, explicit registration + technical principal + fixed API base URL reduces that risk.

## 42. Job Credentials and Principle of Least Privilege

Recommended controls:

1. Dedicated client ID for inventory sync.
2. Only `client_credentials` grant when interactive login is unneeded.
3. Read-only inventory scope when the task only reads.
4. Token audience restricted to Inventory API when supported by the AS.
5. Sufficiently short expiry per policy.
6. AS rate limiting and bounded retries.
7. No web application admin roles granted.
8. Client secret protected in a secret manager.
9. TLS/mTLS and destination allowlists.
10. Authorized client store protects credentials and isolates tenants.
11. Auditing/alerts without logging raw tokens.
12. Separate environments and service accounts.
13. Revoke/rotate credentials if a job is compromised.
14. Only approved API endpoints accept the machine token.

### 42.1. Never Authorize by Store Principal Name

`"job:inventory-sync"` is a client-side key. It is **not a claim verified by the Resource Server**.

Never write a Resource Server rule like "if the token comes from a job with that principal string, treat it as admin" when the token lacks a verified authority.

### 42.2. AS Service Identity May Differ from Technical Principal

The Authorization Server may represent the client ID in the token via `client_id`, `sub`, `azp`, or another claim depending on token profile and provider. Never assume Spring's store principal name appears in the JWT.

## 43. Deploying as a Kubernetes CronJob

For strictly scheduled work, an alternative to `@Scheduled` is a **Kubernetes CronJob** launching a process/job run on schedule.

Benefits:

- Schedule lives in the control plane.
- Built-in concurrency policy.
- Job run history.
- Can run a non-web worker image.
- Eliminates running schedulers on every app replica.

However, keep in mind:

- Each CronJob execution starts a fresh process, so in-memory authorized clients **do not survive across runs**.
- A shared store helps only if it reduces token requests or supports coordination policy.
- If token lifetime is shorter than the interval between jobs, persistent caching adds little value.
- Secrets, network isolation, and pod identity still need protection.
- Concurrency must still be handled if schedules overlap or jobs retry.

### 43.1. Where Should Scheduling Live?

| Approach | Best Fit |
|---|---|
| Spring `@Scheduled` in a worker process | Continuously running service with simple schedules. |
| Kubernetes CronJob | Periodic jobs where containers are created/destroyed per run. |
| Queue + workers | Large workloads, partitioned tasks, durable retries. |
| Workflow orchestrator | Multi-step pipelines, conditions, approvals, dependencies. |

Choose based on operational needs; the OAuth2 Client Credentials flow inside the job remains the same.

### 43.2. Do Not Run Both CronJob and `@Scheduled` Together

If a Kubernetes CronJob launches a container that runs an infinite `@Scheduled` loop, execution behavior will break expectations. For one-shot workers, expose an entry point that executes the task once and exits rather than leaving Spring's scheduler running forever.

## 44. Headless Worker Model

If no HTTP server is needed:

```yaml
spring:
  main:
    web-application-type: none
```

This is **only a property**; it will not automatically create a `ClientRegistrationRepository` if your Boot version's auto-configuration depends on a web application context.

### 44.1. Two Options for Headless

1. Verify Boot still auto-configures the registration/service in your stack/version, then inject as shown.
2. Explicitly define a `ClientRegistrationRepository` bean from trusted config without depending on Servlet or WebFlux server lifecycles.

### 44.2. Never Use an HTTP Request-Bound Manager

A headless worker has no `HttpServletRequest` or browser session. A service-backed authorized client manager is the right fit.

### 44.3. Process Exit

A one-shot CLI/CronJob should use an `ApplicationRunner`/`CommandLineRunner` and close the Spring context upon completion. Never just enable `@Scheduled` in a non-web app expecting it to exit automatically per orchestrator schedules.

## 45. Extended Exercise: Separating Token Acquisition and API Client

Currently `InventoryApiClient` both requests the authorized client and calls the API. In larger applications, split them:

```text
MachineTokenProvider
  -> OAuth2AuthorizedClientManager
  -> authorized client service

InventoryApiClient
  -> MachineTokenProvider
  -> WebClient

InventorySyncJob
  -> InventoryApiClient
  -> InventoryRepository
```

Benefits:

- Unit-test token lifecycle independently.
- API client only asks for a token via an interface.
- Job remains unaware of AS registration internals.
- Each API uses a specific registration and permission set.
- Alerts and auditing have a single central point.

### 45.1. Do Not Build an Unrestricted Token Provider

A method `MachineTokenProvider.getToken(String registrationId)` accepting arbitrary registrations from user input can let callers obtain unauthorized tokens.

Wrap specific use cases or enforce allowlists/internal service authorization, for example:

```java
inventoryTokenProvider.accessToken();
billingTokenProvider.accessToken();
```

rather than exposing an endpoint that fetches tokens by arbitrary client ID.

### 45.2. Never Expose Machine Tokens to the Browser

Even if an admin REST endpoint triggers "Run inventory sync", the response should return only a job ID/status, never the Access Token.

## 46. Minimum Regression Test Suite

| ID | Scenario | Expected Outcome |
|---|---|---|
| T01 | Registration `inventory-job` exists | Uses `client_credentials`, exact token URI, and scope. |
| T02 | No authorized client yet | Manager requests token from AS stub. |
| T03 | Token still valid | Reuses authorized client without redundant token calls. |
| T04 | Token needs re-issuance | Requests new Access Token via client credentials. |
| T05 | Principal changes | Uses a different store key; catches accidental changes. |
| T06 | Wrong client secret | Token endpoint returns `invalid_client`; job fails clearly. |
| T07 | Invalid scope | AS rejects; never falls back to broader scope. |
| T08 | AS 429 | Bounded backoff; no retry storm. |
| T09 | AS timeout/5xx | Job reports failure without hanging threads forever. |
| T10 | Manager returns null | Never calls API with empty or wrong token. |
| T11 | API GET 200 | Parses DTO and reports success. |
| T12 | API 401 | Handles invalid token per policy; no infinite retries. |
| T13 | API 403 | Reports permission issue; never requests admin scope. |
| T14 | API 503 | Bounded retry if idempotent. |
| T15 | API returns malformed body | Fails/alerts rather than treating empty snapshot as success. |
| T16 | Unapproved API host | Bearer token is never sent. |
| T17 | Authorization header | Token sent on exact request, absent from responses/logs. |
| T18 | Job runs twice | DB writes are idempotent, no double-counting. |
| T19 | Multiple pods run concurrently | Lock/orchestration verified. |
| T20 | Shared authorized client store | No cross-registration, cross-principal, or cross-tenant reuse. |
| T21 | App restart | In-memory vs. persistent store behaves as designed. |
| T22 | Secret rotation | AS/RS behavior and retry policy verified. |
| T23 | Token expired while DB row remains | Manager never blindly sends an expired token. |
| T24 | Production logging | Zero client secrets, access tokens, or Authorization headers logged. |

### 46.1. One Monolithic Test Does Not Need to Cover Everything

Split tests by layer:

- **Unit tests**: mocked manager, DTOs, scheduler orchestration.
- **Manager/store tests**: fake provider, persistence, principal keys.
- **HTTP integration tests**: AS/RS stubs, grant serialization, status handling.
- **Deployment tests**: secrets, TLS, proxy/egress, multiple replicas.
- **Security regression**: least privilege and tenant isolation.

## 47. Common Issues and Troubleshooting

| Symptom | Likely Cause | Resolution |
|---|---|---|
| `No qualifying bean of type ClientRegistrationRepository` | Auto-config mismatch or missing headless config. | Check dependencies, Boot app type, or explicit bean. |
| `No client registration for inventory-job` | Wrong `registrationId` or custom repo overriding properties. | Inspect active repository and keys. |
| `manager.authorize(...)` returns null | Provider lacks grant support or registration mismatch. | Ensure `clientCredentials()` and grant config align. |
| Token endpoint 401 `invalid_client` | Wrong ID/secret/client auth method. | Verify AS registration and secret rotation. |
| Token endpoint returns `invalid_scope` | Scope not authorized. | Adjust client permissions per policy. |
| Job starts but never executes | Missing `@EnableScheduling` or unmanaged bean. | Verify scheduling config and bean lifecycle. |
| Job runs multiple times concurrently | Multiple pods or scheduler instances. | Add distributed lock, CronJob, or idempotency. |
| AS receives excessive token requests | Changing principal, non-reusing store, or tiny TTL. | Use stable technical principal; check cache/provider. |
| Tokens not shared across pods | Per-replica in-memory store. | Use shared store or accept per-pod re-issuance per policy. |
| `block()` fails on reactive thread | Called from an event loop. | Switch to reactive composition; never block event loops. |
| API 401 immediately after getting token | Audience, issuer, token type, or config mismatch. | Align AS/RS contract; never blindly escalate scopes. |
| API 403 | Missing scope or permission. | Check resource authorization; never retry endlessly. |
| API 429/503 | Rate limit or availability issue. | Apply bounded backoff and monitoring. |
| Token sent to wrong host | Dynamic WebClient destination or default Bearer config. | Use fixed base URL, per-request headers, and allowlists. |
| Memory leak in token cache | Principal key generates a new UUID every run. | Use stable keys, TTL, and cleanup. |
| DB has record yet manager fetches new token | Principal/registration mismatch, expiry/skew, serialization. | Inspect storage keys and provider policy. |
| JDBC store errors | Missing schema, DB credentials, or serialization issue. | Use version-exact schema and test migrations. |
| User logout does not affect job | Machine token is independent of user sessions. | Expected separation; revoke client credentials via separate policy. |
| No ID Token found | Client Credentials is not an OIDC user login. | Do not require `OidcUser`/ID Token for jobs. |
| Metrics contain raw Bearer tokens | Misconfigured logging/interceptor. | Redact immediately and execute incident response. |
| Tests pass, production fails TLS | Stub did not simulate CA/proxy networking. | Run deployment integration/TLS validation. |

### 47.1. Layer-by-Layer Debugging

```mermaid
flowchart TD
    A["Job runs but API data does not update"] --> B{"Is @Scheduled invoked?"}
    B -->|No| C["@EnableScheduling, Bean, scheduler configuration"]
    B -->|Yes| D{"Does registration exist?"}
    D -->|No| E["Boot properties / ClientRegistrationRepository"]
    D -->|Yes| F{"Does manager return authorized client?"}
    F -->|No| G["client_credentials provider, AS token endpoint, secret"]
    F -->|Yes| H{"Correct registration and valid token?"}
    H -->|No| I["principal key, store, expiry, clock skew"]
    H -->|Yes| J{"API request targets right host with Bearer?"}
    J -->|No| K["WebClient config, URI, header selection"]
    J -->|Yes| L{"API status?"}
    L -->|401| M["Audience/issuer/expiry/revocation"]
    L -->|403| N["Scopes, client permission, tenant policy"]
    L -->|429 or 5xx| O["Retry policy, rate limit, uptime"]
    L -->|200| P["DTO parsing, idempotent DB write, checkpoint"]
```

Never fix every error by wiping caches or repeatedly requesting tokens. Isolate **scheduling, registration, authorization, token store, HTTP client, Resource Server, and business writes**.

## 48. When Is a Persistent Authorized Client Store Unnecessary?

A job running **once per day** with a 30-minute token expiry will almost always need a fresh token anyway, even with DB storage. In that case:

- An in-memory store for process lifetime may suffice.
- A shared persistent store adds more operational complexity than value.
- A one-shot CronJob can simply acquire a token per run under policy.
- Holding tokens longer than necessary adds unnecessary security exposure.

Conversely, a service making 10 requests/second across multiple pods with 1-hour tokens and AS rate limits benefits greatly from token reuse and coordinated storage.

**Choose persistence based on frequency, lifetime, concurrency, availability, and threat model**, not on the assumption that "more caching is always better".

## 49. Hands-On Exercises

### Exercise A — Observe Token Reuse

1. Configure a local token stub returning `expires_in=3600`.
2. Run `InventorySyncJob` twice consecutively in a test.
3. Assert the token endpoint is called only on the first run.
4. Assert the Inventory API receives the same token fixture.
5. Change the principal name on the second call and observe the cache miss.
6. Explain why the principal must stay stable.

### Exercise B — Handle Expired Tokens

1. Issue an already-expired or near-expiry token fixture.
2. Call `manager.authorize`.
3. Assert the client credentials token endpoint is called again.
4. Assert the service persists the newly issued authorized client.
5. Verify the old Access Token is not sent to the API.

### Exercise C — API 401 and 403

1. Have the API stub return 401 and record the error metric.
2. Implement a policy allowing at most one eviction/re-issuance when a token is confirmed invalid.
3. If the API stub still returns 401 after retry: fail the job rather than looping forever.
4. Switch the stub to 403.
5. Assert the job does not wastefully retry the token endpoint for missing permissions.

### Exercise D — Replace In-Memory Store with JDBC

1. Add JDBC dependencies and a test DB.
2. Initialize the schema matching your Spring Security version.
3. Replace the service bean with `JdbcOAuth2AuthorizedClientService`.
4. Save an authorized client fixture and restart the test application context.
5. Assert the record loads by principal and registration.
6. Verify DB permissions, encryption/retention, and cleanup.
7. Evaluate concurrent writes.

### Exercise E — Multi-Tenant Isolation

1. Define two registrations/tenants from a trusted catalog.
2. Run the job for alpha.
3. Run the job for beta.
4. Assert alpha's token is sent only to alpha's API.
5. Assert beta's token cannot be retrieved using alpha's key.
6. Assert identical emails or identical `sub` values across two issuers never auto-link accounts.
7. Verify the job never accepts arbitrary registration IDs from untrusted input.

## 50. Pre-Production Checklist

**OAuth2 Registration and Tokens**

- [ ] `client_credentials` is permitted by the AS.
- [ ] Client ID/secret or client authentication method matches AS requirements.
- [ ] Token endpoint is an approved host over valid HTTPS/TLS.
- [ ] Scopes and audience are minimal for the Inventory API.
- [ ] Registration IDs match across YAML, manager, and code.
- [ ] Machine tokens and user-delegated tokens are cleanly separated.
- [ ] Zero dependence on browser `SecurityContext`/`HttpSession`.

**Authorized Client Manager and Store**

- [ ] Service-backed manager is used for jobs without HTTP requests.
- [ ] `clientCredentials()` provider is enabled.
- [ ] Technical principal is stable, never a per-run random UUID.
- [ ] Tokens are stored and reused under the right registration/principal.
- [ ] Token expiration, clock skew, and re-issuance are tested.
- [ ] In-memory vs. persistent store chosen intentionally for the workload.
- [ ] If persistent, stored tokens are protected with cleanup and rotation policies.
- [ ] If multi-instance, duplicate token request mitigation is in place.

**Job and Inventory API**

- [ ] `@EnableScheduling` and `@Scheduled` are configured properly.
- [ ] Job does not execute redundantly across cluster replicas.
- [ ] API base URL is fixed/allowlisted.
- [ ] Bearer token is attached per request only where needed.
- [ ] Tokens are never exposed via controllers, DTOs, logs, or URLs.
- [ ] Timeouts/retries are bounded; 401/403/429/5xx are classified cleanly.
- [ ] Business DB writes are idempotent with checkpoints as needed.
- [ ] Metrics and alerts cover failed runs and missed schedules.
- [ ] Client secret rotation and failure runbooks are documented.

**Testing and Operations**

- [ ] Unit tests cover manager requests and token headers.
- [ ] Token reuse is tested with a fake provider/store.
- [ ] Token endpoint integration is tested with a synthetic AS stub.
- [ ] Resource Server API integration is tested with a stub.
- [ ] Negative tests cover wrong registration, tenant, and host.
- [ ] Zero production credentials in CI or test fixtures.
- [ ] Logs and monitoring exclude credentials.
- [ ] Rollback/restart plan exists for token-store schema changes.

## 51. References

- [OAuth 2.0 Authorization Framework — Client Credentials Grant, RFC 6749 §4.4](https://www.rfc-editor.org/rfc/rfc6749#section-4.4)
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700)
- [OAuth 2.0 Bearer Token Usage — RFC 6750](https://www.rfc-editor.org/rfc/rfc6750)
- [Spring Security Reference — OAuth2 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security Reference — Core Interfaces and Classes (OAuth2 Client)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html)
- [Spring Security Reference — Client Credentials](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
- [Spring Security API — OAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html)
- [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html)
- [Spring Security API — OAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientService.html)
- [Spring Security API — InMemoryOAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/InMemoryOAuth2AuthorizedClientService.html)
- [Spring Security API — JdbcOAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/JdbcOAuth2AuthorizedClientService.html)
- [Spring Security API — OAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html)
- [Spring Security API — OAuth2AuthorizeRequest](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizeRequest.html)
- [Spring Boot Reference — OAuth2 Client](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Boot Reference — Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Security Reference — OAuth2 Client (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html)
- [Spring Security Reference — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

## 52. Summary

This lab built a **Spring Boot scheduled job** using the **OAuth 2.0 Client Credentials Grant** to call an Inventory API **without a browser or user session**:

1. Configured client registration `inventory-job` with `client_credentials` and scope `inventory.read`.
2. Used `AuthorizedClientServiceOAuth2AuthorizedClientManager` with `OAuth2AuthorizedClientProviderBuilder.clientCredentials()`.
3. Stored tokens via `OAuth2AuthorizedClientService`, starting with `InMemoryOAuth2AuthorizedClientService`.
4. Invoked `manager.authorize(...)` with a stable technical principal `job:inventory-sync`.
5. Attached the Access Token to the **exact** `WebClient` request targeting the Inventory API.
6. Scheduled execution with `@Scheduled` while keeping business writes idempotent.
7. Distinguished token reuse from re-issuance on expiry; **`client_credentials` normally does not use Refresh Tokens**.
8. Extended the authorized client store to JDBC/Redis when frequency, multiple instances, and policy demand it.
9. Added bounded timeouts/retries, monitoring, secret protection, scope/audience checks, and anti-token-leak controls.
10. Tested with fake managers/providers and local AS/API stubs without touching production credentials.

**Most important lesson:** `OAuth2AuthorizedClientManager` manages tokens for a **client registration and principal context**, but in an M2M job the principal is an **application-controlled technical key**, not an `OidcUser`. Pick a manager independent of HTTP requests, store and reuse authorized clients within the proper scope, never turn a machine token into a user token, and never conflate **token caching**, **job scheduling**, and **authorization policy**. Keeping these three responsibilities separate lets background jobs run reliably, test cleanly, and protect credentials properly.
