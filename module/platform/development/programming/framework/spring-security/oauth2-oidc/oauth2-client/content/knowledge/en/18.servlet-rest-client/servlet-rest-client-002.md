# 18.2. Connecting the Interceptor with OAuth2AuthorizedClientManager

## 1. Context: RestClient Calling an API That Requires an Access Token

In a **Spring Security OAuth 2.0 OIDC Client** application running on the **Servlet stack**, after a user logs in via OIDC or a backend service is authorized via Client Credentials, the application often needs to send HTTP requests to a **Resource Server**: fetching profiles, reading reports, syncing data, or calling a partner API.

When calling an API protected by an OAuth 2.0 Bearer Token, each request must carry the **appropriate Access Token**:

~~~http
GET /v1/reports HTTP/1.1
Host: api.example.net
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

The challenge goes beyond adding an HTTP header. The application must determine:

- Which **client registration** should be used to obtain the token?
- Does the token belong to the **current user** or to the **service/application**?
- Is the Access Token already in the store?
- Has the Access Token expired, requiring a refresh or a new token?
- If the Resource Server returns `401 invalid_token` or `403 insufficient_scope`, should the old token record be removed?
- How do we prevent sending the Access Token to the wrong hostname or writing it to logs?

Spring Security provides **`OAuth2ClientHttpRequestInterceptor`** to connect the synchronous **`RestClient`** HTTP client with **`OAuth2AuthorizedClientManager`**. The interceptor obtains the authorized client via the manager and attaches the token to the request, instead of forcing every controller to handle Access Tokens manually.

**Lesson goal:** understand the flow interceptor → manager → authorized client store → Bearer header; configure Spring Security Servlet with the right APIs; choose registration/principal; handle failures and test behavior safely.

> **Version scope:** `RestClient` is available in Spring Framework 6.1 onward; `OAuth2ClientHttpRequestInterceptor` was introduced in **Spring Security 6.4** and continues in newer versions. If a project uses an older Spring Security branch, you cannot simply copy this class into your source and expect it to compile. The Java examples below follow Spring Boot 3.x/Spring Security 6.4+ and Servlet conventions.

## 2. Distinguishing RestClient, Interceptor, and Manager

Before configuring, separate four roles:

| Component | Responsibility | Not Responsible For |
| --- | --- | --- |
| **`RestClient`** | Executes synchronous HTTP requests to APIs | Does not understand OAuth2 grants on its own without integration |
| **`OAuth2ClientHttpRequestInterceptor`** | Intercepts outbound HTTP requests, resolves registration/principal, asks the manager for an authorized client, and attaches the Bearer Token | Does not authenticate OIDC users itself or act as a Token Endpoint |
| **`OAuth2AuthorizedClientManager`** | Loads existing authorized clients, coordinates authorization/re-authorization, requests or refreshes tokens per configured grants | Does not replace Resource Server authorization |
| **`OAuth2AuthorizedClientRepository` / `OAuth2AuthorizedClientService`** | Saves/loads/removes tokens by context and key | Does not call the Token Endpoint to refresh tokens itself |

There are also:

- **`ClientRegistrationRepository`**: configuration store of clients such as `company-login` or `reports-service`.
- **`OAuth2AuthorizedClientProvider`**: grant strategies such as `authorization_code`, `refresh_token`, `client_credentials`.
- **`Resource Server`**: the target API that validates the Access Token, scope, audience, and its own policies.

### 2.1. Basic Connection Diagram

~~~mermaid
flowchart TD
    A["Controller or service needing to call API"] --> B["RestClient.get/post(...)"]
    B --> C["OAuth2ClientHttpRequestInterceptor"]
    C --> D["Resolve clientRegistrationId and principal"]
    D --> E["OAuth2AuthorizedClientManager.authorize(...)"]
    E --> F{"Valid authorized client exists?"}
    F -->|"Yes"| G["Use stored Access Token"]
    F -->|"Missing/expired"| H["OAuth2AuthorizedClientProvider"]
    H --> I["Token Endpoint: issue/refresh per grant"]
    I --> J["Repository/Service saves new token"]
    J --> G
    G --> K["Attach Authorization: Bearer <token>"]
    K --> L["Execute outbound HTTP request"]
    L --> M["Resource Server validates token and policy"]
~~~

The diagram shows the **logical path**. The manager/provider may reuse a token, return `null`, or require initiating authorization depending on the grant and transaction state. Do not assume every `RestClient.get()` call must perform a Token Endpoint call.

### 2.2. Sequence Over Time

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Spring MVC Service
    participant RC as RestClient
    participant I as OAuth2ClientHttpRequestInterceptor
    participant M as OAuth2AuthorizedClientManager
    participant S as AuthorizedClient Store
    participant AS as Authorization Server
    participant RS as Resource Server
    App->>RC: get().uri("/v1/reports").attributes(...)
    RC->>I: Intercept outbound request
    I->>M: authorize(registrationId, principal)
    M->>S: Load OAuth2AuthorizedClient
    alt No token or new token needed
        M->>AS: Client Credentials or matching grant
        AS-->>M: New Access Token
        M->>S: Save/update authorized client
    else Existing token is still valid
        S-->>M: Stored authorized client
    end
    M-->>I: OAuth2AuthorizedClient
    I->>RC: Attach Bearer Access Token
    RC->>RS: GET /v1/reports + Authorization header
    RS-->>RC: HTTP response
    RC-->>App: Response body or error
~~~

In the actual flow, adding the header happens inside the interceptor when the request is processed. **The interceptor sends the Access Token, not the ID Token or Refresh Token** to the Resource Server.

## 3. How Spring Security Connects the Interceptor to the Manager

The direct integration point is the constructor:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

OAuth2ClientHttpRequestInterceptor interceptor =
    new OAuth2ClientHttpRequestInterceptor(authorizedClientManager);

RestClient restClient = RestClient.builder()
    .requestInterceptor(interceptor)
    .build();
~~~

This snippet assumes `authorizedClientManager` is provided by the Spring container or application. Tokens are not hard-coded into the interceptor: **the interceptor takes the manager**, and the manager knows how to look up/obtain tokens.

### 3.1. Minimal RestClient Bean Example

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Configuration
public class OAuth2RestClientConfig {

    @Bean
    RestClient oauth2RestClient(
            OAuth2AuthorizedClientManager authorizedClientManager) {

        OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(
                authorizedClientManager);

        return RestClient.builder()
            .requestInterceptor(oauth2)
            .build();
    }
}
~~~

This is the **core** configuration. To actually call an API, the request also needs to **select a client registration** (by default via request attributes), have a valid principal context, and use a manager configured with appropriate grants/stores.

### 3.2. Configuration Must Align Across All Three Layers

~~~text
spring.security.oauth2.client.registration.reports-service
   |
   | registrationId = "reports-service"
   v
RestClient request attributes
   |
   | clientRegistrationId("reports-service")
   v
OAuth2ClientHttpRequestInterceptor
   |
   v
OAuth2AuthorizedClientManager
   |
   +-- ClientRegistrationRepository: looks up "reports-service"
   +-- OAuth2AuthorizedClientService/Repository: looks up token
   +-- OAuth2AuthorizedClientProvider: executes matching grant
~~~

If the request sets `clientRegistrationId("reports-service")` while YAML registers `report-service`, the manager cannot find the right registration. **Registration names must match exactly** between code and configuration.

## 4. Selecting `clientRegistrationId` Per Outbound Request

`OAuth2ClientHttpRequestInterceptor` uses a **`ClientRegistrationIdResolver`** to know which client to use. By default, **`RequestAttributeClientRegistrationIdResolver`** reads the registration ID from the `RestClient` request attributes.

Spring Security provides a utility:

~~~java
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
~~~

In real Java code, a static import should be placed on **one line**:

~~~java
import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
~~~

Calling the API:

~~~java
String response = restClient.get()
    .uri("https://api.example.net/v1/reports")
    .attributes(clientRegistrationId("reports-service"))
    .retrieve()
    .body(String.class);
~~~

Here `clientRegistrationId(...)` sets an **internal RestClient request attribute**, **not** a query parameter sent to the Resource Server.

### 4.1. Why Are Request Attributes Needed?

An application can use multiple client registrations:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-service:
            provider: company-auth
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [reports.read]
          billing-service:
            provider: company-auth
            client-id: ${BILLING_CLIENT_ID}
            client-secret: ${BILLING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [billing.read]
        provider:
          company-auth:
            token-uri: https://auth.example.net/oauth2/token
~~~

With the same RestClient bean, requests to the Reports API need `reports-service`, while Billing API needs `billing-service`:

~~~java
String reportsJson = restClient.get()
    .uri("https://api.example.net/v1/reports")
    .attributes(clientRegistrationId("reports-service"))
    .retrieve()
    .body(String.class);

String billingJson = restClient.get()
    .uri("https://billing.example.net/v1/invoices")
    .attributes(clientRegistrationId("billing-service"))
    .retrieve()
    .body(String.class);
~~~

This example illustrates selecting a registration; in production you should **split RestClients per target API or restrict hostnames** to avoid sending tokens to user-determined URLs.

### 4.2. Do Not Use `registrationId` from a User-Controlled URL Without Controls

Anti-pattern:

~~~java
// DO NOT USE: user arbitrarily chooses registration and destination.
restClient.get()
    .uri(userSuppliedUrl)
    .attributes(clientRegistrationId(userSuppliedRegistrationId))
    .retrieve()
    .body(String.class);
~~~

Consequences can include:

- Sending a sensitive registration's Access Token to an untrusted URL.
- Accessing the wrong API/tenant.
- Using backend privileges for a request controlled by an unauthorized user.
- Creating SSRF and Bearer Token exposure risks.

**Registrations and Resource Servers must be chosen from a server-side allowlist** based on permitted features/tenants, not from arbitrary browser values.

### 4.3. Custom `ClientRegistrationIdResolver`

When all API requests of a RestClient always need the same registration, or need to derive the registration from a verified `Authentication`, you can replace the resolver:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;

oauth2.setClientRegistrationIdResolver(request -> {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

    if (auth instanceof OAuth2AuthenticationToken oauth2Login) {
        return oauth2Login.getAuthorizedClientRegistrationId();
    }
    return null;
});
~~~

This is a **way to choose a registration based on the OIDC/OAuth2 login session**. For Client Credentials running in the background, `SecurityContextHolder` may have no `Authentication`, so this approach is unsuitable for selecting a service registration.

A design mistake to avoid: automatically deriving the user login's registration and using that Access Token to call **every** downstream API. A login token should only be sent to APIs for which it is authorized with the right audience.

## 5. Choosing the Principal: User Token or Application Token?

This is the most critical part when connecting the interceptor and manager.

`OAuth2AuthorizedClient` is typically stored by the logical key:

~~~text
(clientRegistrationId, principalName)
~~~

The interceptor has a **`PrincipalResolver`** to determine the principal the manager uses. By default, **`SecurityContextHolderPrincipalResolver`** reads the current `Authentication` from `SecurityContextHolder`.

Two usage patterns must be kept distinct:

| Scenario | Selected Principal | Managed Token |
| --- | --- | --- |
| User logs in via OIDC and calls an API with their own permissions | Current user's `Authentication` | Delegated user token |
| Backend/scheduled job calls an API using Client Credentials | Fixed service/application principal name | Application token |
| Multi-tenant service with distinct client credentials | Policy-compliant namespaced principal and registration | Token matching each approved service/tenant |

### 5.1. Defaulting to Principal from `SecurityContextHolder`

In a Spring MVC request after OIDC Login:

~~~text
Browser session
  -> Spring Security Authentication: alice
  -> SecurityContextHolderPrincipalResolver
  -> principal = alice
  -> OAuth2AuthorizedClientManager
  -> ("company-login", "alice") authorized client
~~~

When configuring the interceptor as in Section 3, you may simply need:

~~~java
restClient.get()
    .uri("https://api.partner.example.net/v1/me")
    .attributes(clientRegistrationId("company-login"))
    .retrieve()
    .body(String.class);
~~~

**Conditions:** the request is executing in a flow with a valid `Authentication`, `company-login` is the registration tied to the user, and the Access Token is issued for that target API. Do not assume an OIDC Login token can call any arbitrary API.

### 5.2. Using `RequestAttributePrincipalResolver` for Client Credentials

With **Client Credentials**, you normally want all calls from the same service to reuse an authorized client tied to **one application-level principal**, rather than partitioning tokens by whichever user happens to have a browser open.

Spring Security provides:

~~~java
import org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver;
~~~

When configured:

~~~java
oauth2.setPrincipalResolver(
    new RequestAttributePrincipalResolver());
~~~

then requests must supply the principal via attributes:

~~~java
import static org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver.principal;

restClient.get()
    .uri("https://api.example.net/v1/reports")
    .attributes(clientRegistrationId("reports-service"))
    .attributes(principal("system-report-exporter"))
    .retrieve()
    .body(String.class);
~~~

`system-report-exporter` is a **logical service identifier key in the authorized client store**, not an OIDC-logged-in user account.

Setting a consistent principal allows the manager to reload the stored token instead of creating a separate authorized client for each HTTP request or web user.

### 5.3. Do Not Mix Application-Level Tokens and Delegated User Tokens

Suppose user Alice opens the reports page. A backend service holds a Client Credentials token with scope `reports.read.all`. If the application lets every logged-in user call the API using that token, **the Resource Server may not know which user requested the data**.

That is only safe if:

1. The backend fully enforces user/tenant authorization **before** using the service token.
2. The target endpoint is designed for service-level access.
3. The service token is never exposed to the browser.
4. Arbitrary parameters cannot be used to access another user's data.

When an API requires a **delegated user identity**, use the proper grant and token—never substitute Client Credentials to bypass policy.

## 6. Complete Example A: RestClient Calling an API via Client Credentials

The following example clearly separates **registration configuration**, **authorized client manager**, **RestClient interceptor**, and **API-calling service**.

### 6.1. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-service:
            provider: company-auth
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company-auth:
            token-uri: https://auth.example.net/oauth2/token
~~~

The address above is illustrative. The Client Secret must be supplied via a secret manager or secure environment configuration; never hard-code it in source code.

Client Credentials **does not need `redirect-uri`, `state`, PKCE, or browser login** for the basic grant.

### 6.2. Configuring the Manager for Service-to-Service

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class MachineClientManagerConfig {

    @Bean
    AuthorizedClientServiceOAuth2AuthorizedClientManager
            machineAuthorizedClientManager(
                    ClientRegistrationRepository registrations,
                    OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Because this is a **service manager**, no Servlet request/response is needed. `OAuth2AuthorizedClientService` can store state in memory or in a database depending on persistence and scale-out requirements.

If the project already has a manager bean for the same purpose, **do not declare a duplicate bean**. Reuse the existing manager or configure a separate one with an explicit qualifier.

### 6.3. Connecting RestClient with the Manager

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver;
import org.springframework.web.client.RestClient;

@Configuration
public class ReportsApiHttpConfig {

    @Bean
    RestClient reportsRestClient(
            RestClient.Builder builder,
            AuthorizedClientServiceOAuth2AuthorizedClientManager manager,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(manager);

        // For Client Credentials, use an application-specific principal.
        oauth2.setPrincipalResolver(
            new RequestAttributePrincipalResolver());

        // If the API reports the Bearer Token is no longer valid, consider removing
        // the old authorized client based on the OAuth2 error code.
        OAuth2AuthorizationFailureHandler failureHandler =
            OAuth2ClientHttpRequestInterceptor
                .authorizationFailureHandler(authorizedClients);
        oauth2.setAuthorizationFailureHandler(failureHandler);

        return builder
            .baseUrl("https://api.example.net")
            .requestInterceptor(oauth2)
            .build();
    }
}
~~~

This code assumes Spring Boot configures `RestClient.Builder` and the project has an appropriate manager/service. A fixed `baseUrl` prevents the API client from accepting full URLs from users.

**Failure handler behavior must be understood accurately:** the helper can remove the authorized client based on **OAuth2 error codes and matching conditions**, not delete every token on any HTTP 401/403. Removal mainly helps **the next request** obtain a new token; it does not guarantee the interceptor retries the failed request itself.

### 6.4. Calling the API from a Service

~~~java
package com.example.reports;

import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver.principal;

import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class ReportsGateway {

    private final RestClient reportsRestClient;

    public ReportsGateway(RestClient reportsRestClient) {
        this.reportsRestClient = reportsRestClient;
    }

    public String loadReportsJson() {
        return reportsRestClient.get()
            .uri("/v1/reports")
            .attributes(clientRegistrationId("reports-service"))
            .attributes(principal("system-report-exporter"))
            .retrieve()
            .body(String.class);
    }
}
~~~

What happens when `loadReportsJson()` is called:

1. RestClient builds an outbound GET to the Reports API.
2. The interceptor reads `clientRegistrationId=reports-service` from request attributes.
3. `RequestAttributePrincipalResolver` resolves principal `system-report-exporter`.
4. The manager looks up the `OAuth2AuthorizedClient` for the registration/principal pair.
5. If missing or a new token is needed, the `clientCredentials()` provider calls the Token Endpoint.
6. The manager saves the new token record via the service.
7. The interceptor attaches `Authorization: Bearer ...`.
8. The Resource Server validates the token and returns the response.

In this demo, the response is a raw JSON string to stay focused on OAuth2. Production applications typically deserialize JSON into schema-defined DTOs with validation and error handling.

### 6.5. Why Not Pass the Authorization Header in the Service?

Do not write:

~~~java
// ANTI-PATTERN when already using the OAuth2 interceptor:
String token = loadSomeTokenManually();
restClient.get()
    .uri("/v1/reports")
    .header("Authorization", "Bearer " + token)
    .attributes(clientRegistrationId("reports-service"))
    .retrieve()
    .body(String.class);
~~~

With an OAuth2 interceptor, manually setting a Bearer header while also asking the interceptor to attach a token can cause **overlapping headers or inconsistent token sources**. Only one component should be responsible for acquiring and setting credentials.

## 7. Example B: Calling an API Using the Access Token of an OIDC-Logged-In User

Not every RestClient call uses Client Credentials. A Spring MVC portal can authenticate users via OIDC and then call an API **on behalf of the current user**.

### 7.1. OIDC Login Configuration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company-login:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - reports.read
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

Scope `reports.read` is a provider-dependent example. Requesting this scope **does not automatically guarantee** the Access Token is accepted by the Resource Server; the provider must configure the right audience/resource.

### 7.2. `SecurityFilterChain` for Servlet

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

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

`oauth2Login()` handles the OIDC login transaction; `oauth2Client()` supports OAuth2 Client features in a Servlet application. **RestClient does not authenticate the browser itself** — it uses the `Authentication`/authorized client already managed by the system.

### 7.3. RestClient Using the Default Principal from `SecurityContext`

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Configuration
public class UserApiHttpConfig {

    @Bean
    RestClient userReportsRestClient(
            RestClient.Builder builder,
            OAuth2AuthorizedClientManager authorizedClientManager,
            OAuth2AuthorizedClientRepository authorizedClientRepository) {

        OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(
                authorizedClientManager);

        // DO NOT replace PrincipalResolver: default reads the current
        // Authentication from SecurityContextHolder.
        OAuth2AuthorizationFailureHandler failureHandler =
            OAuth2ClientHttpRequestInterceptor
                .authorizationFailureHandler(authorizedClientRepository);
        oauth2.setAuthorizationFailureHandler(failureHandler);

        return builder
            .baseUrl("https://reports.example.net")
            .requestInterceptor(oauth2)
            .build();
    }
}
~~~

A repository is used here because the application operates within a Servlet request with user `Authentication`. **Do not blindly switch to a service manager for delegated user tokens** if the application relies on a repository/session without an equivalent storage design.

### 7.4. Controller or Service Calling the API

~~~java
package com.example.web;

import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class MyReportsController {

    private final RestClient userReportsRestClient;

    public MyReportsController(RestClient userReportsRestClient) {
        this.userReportsRestClient = userReportsRestClient;
    }

    @GetMapping("/my-reports")
    public ResponseEntity<String> myReports() {
        String json = userReportsRestClient.get()
            .uri("/v1/my-reports")
            .attributes(clientRegistrationId("company-login"))
            .retrieve()
            .body(String.class);

        return ResponseEntity.ok(json);
    }
}
~~~

The logged-in browser's `Authentication` is read from **`SecurityContext`**; the interceptor and manager use the user's principal, not `principal("system-report-exporter")`.

**Architecture note:** the example returns raw JSON from the downstream API to keep the HTTP part simple. In real applications, control exposed fields, JSON parsing, privacy, and timeouts. Never blindly proxy every external API response directly to the browser.

## 8. Choosing the Right `OAuth2AuthorizedClientManager`

There are two common managers:

| Manager | Inputs/Store | When to Use |
| --- | --- | --- |
| `DefaultOAuth2AuthorizedClientManager` | `ClientRegistrationRepository` + `OAuth2AuthorizedClientRepository` | Inside a Servlet HTTP request, tied to Authentication/session |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | `ClientRegistrationRepository` + `OAuth2AuthorizedClientService` | Services, scheduled jobs, batch, or calls outside an HTTP request |

### 8.1. Why Does the Servlet Manager Need an HTTP Context?

The repository has methods taking `HttpServletRequest` and sometimes `HttpServletResponse`. Consequently, `DefaultOAuth2AuthorizedClientManager` must resolve the current request/response or be given a suitable context.

If a background worker without a Servlet request tries to use the Default manager, loading/saving tokens can fail due to missing context.

### 8.2. A Service Manager Does Not Automatically Represent an End-User

`AuthorizedClientServiceOAuth2AuthorizedClientManager` does not require a Servlet request, but that **does not mean** it can arbitrarily fetch another user's Access Token. The principal name/registration must come from an authorized workflow and access-control policy.

For Client Credentials, a stable service-level principal is the natural choice. For delegated user tokens outside an HTTP request, proper persistence and user consent mechanisms are required—never look up tokens by an arbitrary email address.

### 8.3. The Manager Automatically Saves New Tokens as Configured

Normally, managers have a default **authorization success handler** to persist the `OAuth2AuthorizedClient` after a successful grant or refresh:

~~~text
Manager.authorize(...)
  -> Provider obtains/refreshes token successfully
  -> OAuth2AuthorizationSuccessHandler
  -> saveAuthorizedClient via Repository or Service
~~~

**Do not replace the default success handler with a logging-only lambda** and forget the save step, or the interceptor may end up requesting a new token on every request or fail to store rotated Refresh Tokens.

### 8.4. No Need to Manually Feed Tokens to the Manager

To let RestClient work with the manager, you normally only need:

~~~java
new OAuth2ClientHttpRequestInterceptor(authorizedClientManager)
~~~

and the right request attributes. The application should not manually read Access Tokens from the database and stuff them into an interceptor via a global mutable variable.

## 9. How Is an Authorized Client Loaded, Refreshed, and Saved?

An `OAuth2AuthorizedClient` contains:

~~~text
ClientRegistration registration
String principalName
OAuth2AccessToken accessToken
OAuth2RefreshToken refreshToken (may be null)
~~~

When the interceptor calls the manager:

1. **Load:** look up the authorized client by registration/principal in the repository/service.
2. **Assess:** the provider/grant decides whether the current token can be reused or needs issuance/refresh.
3. **Authorize:** execute the appropriate grant, such as Refresh Token or Client Credentials.
4. **Persist:** the manager saves the updated client via the success handler.
5. **Apply:** the interceptor sends the Access Token in the Bearer header.

### 9.1. Authorization Code/OIDC with Refresh Token

If a delegated user token expires and the provider issued a Refresh Token, the manager can use the `refresh_token` grant when configured. When the Authorization Server returns a new Refresh Token, the manager must save the updated client.

Never send a Refresh Token as an API header. Refresh Tokens are only sent to the Token Endpoint per protocol.

### 9.2. Client Credentials Does Not Need a Refresh Token by Default

With Client Credentials, the Authorization Server typically **does not issue a Refresh Token**. When the Access Token expires, the manager requests a **new Access Token using the Client Credentials grant**, rather than performing an OIDC browser login.

Do not add `openid`, `offline_access`, or the `refresh_token` grant just because the backend wants a new Access Token.

### 9.3. Do Not Assume an Access Token Is Valid Indefinitely

`OAuth2AccessToken.getExpiresAt()`, when provided, indicates expiration time. The manager/provider can apply clock skew to proactively obtain/refresh tokens before expiry.

If the Resource Server revokes a token early, the manager may still consider it unexpired by timestamp. This is why `401 invalid_token` responses from the API must be handled with a proper failure handler.

### 9.4. Concurrent Requests and Token Rotation

Two concurrent HTTP requests may both notice an expired token. If refresh tokens are single-use rotated:

~~~text
Request A: old refresh token -> receives new token
Request B: old refresh token -> invalid_grant
Request A: saves new authorized client
Request B: failure handler processes error from stale request
~~~

Under high load, consider synchronizing by `registrationId + principalName`, optimistic locking, or storage coordination if there is a risk of overwriting or erroneously deleting records. Do not use a **global lock** across all authorized clients.

The interceptor frees the application from writing token-attachment logic, **but does not automatically solve all multi-node concurrency problems**.

## 10. Handling HTTP 401/403 from the Resource Server

Even a successful token exchange can still result in an error when calling the API:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Or:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.write"
~~~

### 10.1. Two Different Errors

| API Signal | Common Meaning | Response |
| --- | --- | --- |
| `401 invalid_token` | Token expired, revoked, wrong issuer/audience, or invalid | Investigate token/registration, possibly remove cached authorized client and obtain a new token |
| `403 insufficient_scope` | Token is recognized but lacks sufficient permissions for the operation | Do not self-elevate scopes; review API policy, another authorization may be needed |
| Other `403` | May be due to API tenant/ownership/policy | Do not automatically blame the token |
| `429` | Rate limit | Retry/backoff per API contract |
| `5xx` | Upstream error | Handle with timeouts/circuit breaker/bounded retry |

**Do not use HTTP status alone to delete every token.** Spring Security provides helpers that inspect OAuth2/Bearer codes to decide whether to remove the authorized client.

### 10.2. The Interceptor's Authorization Failure Handler

An extension point on the interceptor:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;

OAuth2AuthorizationFailureHandler failureHandler =
    OAuth2ClientHttpRequestInterceptor
        .authorizationFailureHandler(authorizedClientService);

interceptor.setAuthorizationFailureHandler(failureHandler);
~~~

When working in a Servlet context with a repository:

~~~java
OAuth2AuthorizationFailureHandler failureHandler =
    OAuth2ClientHttpRequestInterceptor
        .authorizationFailureHandler(authorizedClientRepository);

interceptor.setAuthorizationFailureHandler(failureHandler);
~~~

Here `authorizedClientService` and `authorizedClientRepository` are already-configured dependencies; the two snippets are **alternatives depending on the manager/store**—do not apply both to the same interceptor.

The helper creates a **`RemoveAuthorizedClientOAuth2AuthorizationFailureHandler`**-style failure handler that can remove the cached client when a Bearer error indicates the token is unusable. Exact removal behavior depends on the OAuth2 error code, rather than removing on every HTTP error by default.

### 10.3. Does the Interceptor Automatically Retry a Request That Just Received 401?

Do not assume so. Removing the cached authorized client primarily allows **the next call** to obtain a new token. The failing request can still be converted into an exception by `RestClient.retrieve()` per RestClient's error handler.

If the application wants to retry API calls:

- Retry only when the error is classified and the grant can recover.
- Bound the number of retries to avoid endless 401 loops.
- For POST/PATCH/DELETE, evaluate **idempotency** and duplicate side-effect risks.
- Never retry `403 insufficient_scope` by attempting to escalate permissions.
- Never send the new token to a different hostname to "test".

### 10.4. A Token Endpoint Error Differs from a Resource Server Error

~~~text
Interceptor -> Manager -> Token Endpoint
   invalid_client / invalid_scope / invalid_grant
   => OAuth2 authorization/token-client failure.

Interceptor -> RestClient -> Resource Server
   401 invalid_token / 403 insufficient_scope
   => API bearer-token failure.
~~~

`OAuth2ClientHttpRequestInterceptor.setAuthorizationFailureHandler(...)` primarily deals with **Resource Server** errors received by the interceptor. For Token Endpoint errors, the manager/provider has its own failure handling and exceptions. Do not collapse all OAuth2 errors into one handler.

## 11. Handling Exceptions When Using RestClient

`RestClient.retrieve()` normally throws exceptions when the Resource Server returns HTTP error statuses under its default error-handling policy.

A service can classify HTTP errors without exposing tokens:

~~~java
package com.example.reports;

import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver.principal;

import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Service
public class SafeReportsGateway {

    private final RestClient reportsRestClient;

    public SafeReportsGateway(RestClient reportsRestClient) {
        this.reportsRestClient = reportsRestClient;
    }

    public String getReports() {
        try {
            return reportsRestClient.get()
                .uri("/v1/reports")
                .attributes(clientRegistrationId("reports-service"))
                .attributes(principal("system-report-exporter"))
                .retrieve()
                .body(String.class);
        } catch (HttpClientErrorException.Unauthorized ex) {
            throw new IllegalStateException(
                "Reports API rejected the Access Token", ex);
        } catch (HttpClientErrorException.Forbidden ex) {
            throw new IllegalStateException(
                "Service lacks permission for Reports API", ex);
        } catch (RestClientResponseException ex) {
            throw new IllegalStateException(
                "Reports API returned an HTTP error", ex);
        }
    }
}
~~~

This snippet focuses on **HTTP response classification**, not a full retry mechanism. In production, choose an application exception hierarchy, safe error codes, timeouts, circuit breakers, and error observability policies.

Do not return `ex.getResponseBodyAsString()` directly to the browser or log full exceptions/request headers if there is any risk of containing sensitive information.

### 11.1. If the Manager Cannot Obtain a Token

Errors like `invalid_client`, `invalid_scope`, missing `ClientRegistration`, or insufficient authorization context occur **before the HTTP call to the Resource Server**. Classify them at the `OAuth2AuthorizedClientManager`/token-client layer.

If a grant requires interactive browser authorization while the service runs in the background, the manager may be unable to complete the flow. **Do not substitute Client Credentials for delegated-user authorization** just to skip a consent screen.

### 11.2. Security Context Missing on Other Threads

When requests execute in `@Async`, scheduled jobs, or worker threads, the `SecurityContext` from the HTTP thread is **not present by default**.

For delegated users:

- Have a secure context-propagation strategy if business logic must call an API on a user's behalf outside an HTTP request.
- Never pick the last user's principal from a global variable.
- Never copy Access Tokens into unmanaged thread-locals without lifecycle control.

For Client Credentials:

- Use `AuthorizedClientServiceOAuth2AuthorizedClientManager`.
- Use an application-level principal via `RequestAttributePrincipalResolver`.
- Do not depend on `SecurityContextHolder` from a browser request.

## 12. Configuring Storage So the Interceptor and Manager Stay Consistent

The RestClient interceptor can call the manager successfully, yet the next request still requests a new token if the **authorized client store** is not used consistently.

### 12.1. In-Memory Store

`InMemoryOAuth2AuthorizedClientService` fits demos or services that do not need tokens to survive restarts. Across multiple instances, node A's in-memory store is not automatically available on node B.

### 12.2. Using JDBC When Persistence Is Needed

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class AuthorizedClientStorageConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            JdbcTemplate jdbcTemplate,
            ClientRegistrationRepository registrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbcTemplate, registrations);
    }
}
~~~

This is a conceptual configuration requiring Spring JDBC, a datasource, proper schema migrations for your version, and database security. If Spring Boot already provides the service bean, avoid creating a duplicate bean.

### 12.3. Using the Same Store for Manager and Failure Handler

If the manager saves into service A while the interceptor's failure handler removes from service B, cache invalidation will not work properly.

~~~text
Manager
  -> AuthorizedClientService A
      key: (reports-service, system-report-exporter)

Interceptor FailureHandler
  -> MUST match store A and use the exact principal key
~~~

So when configuring:

~~~java
new OAuth2ClientHttpRequestInterceptor(machineManager)
~~~

and:

~~~java
OAuth2ClientHttpRequestInterceptor.authorizationFailureHandler(
    authorizedClients)
~~~

ensure `machineManager` and `authorizedClients` share the same backing store and principal strategy.

### 12.4. Removing a Local Token Is Not Revoking It at the Authorization Server

The failure handler can remove a cached authorized client so the next request asks for a new token. **This operation does not automatically revoke the token at the Authorization Server**. If revocation is required by policy, call the appropriate revocation endpoint per protocol (if supported by the provider).

Do not claim an old token has been revoked simply because a JDBC/session record was deleted.

## 13. Security When Placing an Interceptor on RestClient

### 13.1. Only Send Tokens to Trusted Endpoints

A RestClient with an OAuth2 interceptor should be dedicated to the **appropriate Resource Server**. For example:

~~~java
return builder
    .baseUrl("https://api.example.net")
    .requestInterceptor(oauth2)
    .build();
~~~

In a gateway/service, call controlled relative paths like `/v1/reports`. However, **`baseUrl` does not strictly block every absolute URI** passed to `.uri(...)`; code must still avoid accepting arbitrary URLs from users.

If users are allowed to input URLs to "fetch data", **do not reuse a RestClient with an OAuth2 interceptor** without a strict host/URI allowlist; doing so introduces SSRF and token exfiltration risks.

### 13.2. Do Not Attach Bearer Tokens of Every Request to Every Hostname

A `RestClient` built from a shared builder with multiple interceptors can accidentally apply the OAuth2 interceptor to unintended requests. Avoid globally registering the interceptor on a multi-purpose builder when API hosts differ.

Split beans:

~~~text
publicRestClient
  -> no OAuth2 interceptor

reportsApiRestClient
  -> OAuth2 interceptor for reports-service

billingApiRestClient
  -> OAuth2 interceptor for billing-service
~~~

When multiple RestClient beans exist, use `@Qualifier` or explicit bean names to inject the right client.

### 13.3. The Authorization Header Is Highly Sensitive

Do not log:

- `Authorization: Bearer ...`.
- Client Secret, JWT client assertions, or private keys.
- Access Tokens, Refresh Tokens, ID Tokens.
- Full HTTP requests/responses to the token endpoint.
- `OAuth2AuthorizedClient` in `toString()` or analytics.

An appropriate metric format:

~~~text
event=oauth2_resource_call
registration_id=reports-service
resource=reports-api
status=success
http_status=200
correlation_id=internal-trace-2f1a
~~~

This is an **illustrative** format, not automatic Spring Security logging. The correlation ID must be independent of tokens/secrets.

### 13.4. HTTPS and TLS Validation

Both the Token Endpoint and Resource Server must be accessed over HTTPS with TLS certificate and hostname verification. Never disable TLS checks just to "fix" communication errors. When using an enterprise proxy or private CA, configure a proper trust store.

### 13.5. Audience and Scopes

`OAuth2ClientHttpRequestInterceptor` attaching a Bearer Token **does not validate on behalf of** the Resource Server:

- The Resource Server must verify issuer, audience, expiration/signature, or introspection.
- Granted scopes must be sufficient for the API operation.
- Tenant/ownership/role policies may also be required.
- An Access Token meant for UserInfo does not automatically have the right audience for the Reports API.

An API request returning 403 can be completely valid behavior even when the interceptor worked properly.

### 13.6. Do Not Treat Request Attributes as Authorization Grants

`.attributes(clientRegistrationId(...))` and `.attributes(principal(...))` are **internal HTTP client configuration**, yet if code passes browser input straight into them, there is still a risk of selecting the wrong privilege.

Choose registrations/principals using **server-side rules**. Never let users arbitrarily pass `principal("admin")` to pull another principal's token from a shared service store.

## 14. Troubleshooting Table: RestClient Not Sending Token or API Returning Errors

| Symptom | What to Check | Resolution |
| --- | --- | --- |
| Outbound request lacks Bearer header | Interceptor not registered on the injected RestClient bean | Check `.requestInterceptor(oauth2)` and injected bean |
| Interceptor cannot find client registration | `clientRegistrationId(...)` not passed, or YAML name mismatch | Supply the attribute or configure a reliable resolver |
| Registration exists but principal is missing | `SecurityContext` absent in background job | For Client Credentials, configure `RequestAttributePrincipalResolver` and an application principal |
| Every HTTP request asks for a new Access Token | Principal name changes, store is not shared, or token TTL is too short | Stabilize registration/principal, check manager/service |
| Token Endpoint reports `invalid_client` | Wrong secret, client auth method, token URI, or disabled client | Fix config/secret rotation; do not retry infinitely |
| Token Endpoint reports `invalid_scope` | Scope not granted to the client | Check scope/grant policy; do not self-escalate permissions |
| Resource Server returns `401 invalid_token` | Token expired/revoked/wrong issuer/audience | Check token lifecycle, API config, consider failure handler |
| Resource Server returns `403 insufficient_scope` | Token lacks required scope | Review policy and grant; do not bypass permissions |
| 403 due to tenant/ownership | Business authorization error | Fix resource-level access control |
| Failure handler removed token yet request still 401s | Outbound call is not automatically retried | Implement bounded retry at the application layer if appropriate |
| Interceptor uses the wrong user's token | Misconfigured principal resolver or principal namespace | Check `Authentication` and authorized client keys |
| Works in controller, fails in scheduler | Using Servlet manager without HTTP context | Use service manager and application-level principal |
| Works locally, every pod fetches tokens after scale-out | In-memory store is not shared | Use shared persistence/coordination as needed |
| Adding tracing interceptor leaks Access Token | Request headers logged | Redact `Authorization` and OAuth2 data |
| API call goes to unexpected URL | URI taken from user input on a token-enabled RestClient | Fix/allowlist destination host; separate clients |
| RestClient receives 404 | Wrong baseUrl/path or API route does not exist | Check endpoint; do not assume OAuth2 failed |

### 14.1. A Practical Investigation Flow

~~~text
RestClient call to Resource Server fails
   |
   +-- Is the right RestClient bean with the OAuth2 interceptor being used?
   |
   +-- Does the request have a clientRegistrationId matching YAML?
   |
   +-- Does PrincipalResolver pick the right user/service identity?
   |
   +-- Is the Manager configured with the right grants/providers/store?
   |
   +-- Did the Token Endpoint issue a token or return an OAuth2 error?
   |
   +-- Is the Access Token being sent to the right API/audience?
   |
   +-- Did the API return 401, 403, 404, or time out?
   |
   +-- Is FailureHandler configured and using the right store?
   |
   +-- Are there concurrency issues, expired tokens, lost sessions, or scale-out effects?
~~~

Never print tokens to answer the questions above. Use flags like `has_access_token=true`, approved registration IDs, and HTTP statuses without revealing credentials.

## 15. Customizing the Interceptor vs. Writing One Manually

### 15.1. Why Prefer `OAuth2ClientHttpRequestInterceptor`?

Writing a custom `ClientHttpRequestInterceptor` like:

~~~java
// ANTI-PATTERN: lacks token lifecycle management and security.
(request, body, execution) -> {
    String token = globalTokenCache.get();
    request.getHeaders().setBearerAuth(token);
    return execution.execute(request, body);
};
~~~

This hand-rolled pattern fails to handle:

- Proper registration/principal/tenant selection.
- Token expiration and Refresh Tokens.
- Token rotation and authorized client persistence.
- Concurrency.
- Token Endpoint errors.
- HTTP 401 Bearer error invalidation.
- Credential security in caches/logs.

`OAuth2ClientHttpRequestInterceptor` is the standard integration point for RestClient; use it unless infrastructure requirements demand behavior unsupported by the framework.

### 15.2. When Is a Custom Resolver Needed?

You may need a custom `ClientRegistrationIdResolver` or `PrincipalResolver` if:

- Each API requires a specific registration and you want to omit passing attributes manually.
- The application has a multi-tenant policy selecting clients per authenticated tenant.
- The service's principal key is mapped from internal configuration.
- Not every request should depend on the current `SecurityContext`.

However, a custom resolver is **not** the place to inspect a user-supplied URL and pick the highest-privilege token. Control data sources and mappings.

### 15.3. Multiple Interceptors on One RestClient

`RestClient` may have tracing, retry, metrics, and OAuth2 interceptors. Interceptor ordering and scope must be planned carefully:

~~~text
RestClient
  -> Tracing/metrics (never log credentials)
  -> OAuth2 token interceptor
  -> HTTP transport
~~~

If a logging interceptor runs after OAuth2 attaches the header, **it must redact `Authorization`**. Do not rely solely on ordering to keep secrets out of logs; both logging and error handlers need redaction policies.

Full-request retries may invoke the interceptor again; ensure retry policies do not cause double-writes on POST/PATCH/DELETE or trigger token-issuance storms.

## 16. How Does `RestClient` Differ from `WebClient` and `RestTemplate`?

| HTTP Client | Programming Model | Typical OAuth2 Integration |
| --- | --- | --- |
| `RestClient` | Synchronous, fluent API for Spring MVC/Servlet-friendly code | **`OAuth2ClientHttpRequestInterceptor`** |
| `WebClient` | Reactive API, also usable from Servlet apps | `ServletOAuth2AuthorizedClientExchangeFilterFunction` |
| `RestTemplate` | Synchronous, legacy API | Custom bearer/interceptor configuration or compatible tooling; not the RestClient API |

Do not use:

~~~java
// Incompatible: a WebClient filter function is not a RestClient interceptor.
new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager)
~~~

as a `ClientHttpRequestInterceptor` for RestClient. The two HTTP clients follow different contracts.

If a project already uses `WebClient`, migrating to RestClient requires evaluating the blocking model, request context, retries, and thread usage. Just because both use `OAuth2AuthorizedClientManager` does not mean configuration can be copied 1:1.

### 16.1. Spring Security Prior to 6.4

If the application does not yet have `OAuth2ClientHttpRequestInterceptor`:

- Check the actual Spring Security version managed by your BOM.
- Upgrade versions via a compatibility plan if appropriate.
- Before upgrading, use an integration supported on your current version, such as WebClient Servlet integration or properly designed HTTP client code.
- Never copy source code from a newer Spring Security class into your project packages to "fake" API compatibility.

## 17. HTTP Service Clients Using a Configured RestClient

With Spring Framework HTTP Interfaces (`@HttpExchange`), you can build client proxies on top of a `RestClient` that already has the OAuth2 interceptor.

Example interface:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange("/v1/reports")
public interface ReportsHttpApi {

    @GetMapping
    String listReports();
}
~~~

If you build a proxy using `HttpServiceProxyFactory` and `RestClientAdapter` backed by the configured RestClient, outbound HTTP calls still flow through that RestClient's interceptors.

However, **how `clientRegistrationId(...)`/`principal(...)` request attributes are supplied from an HTTP interface** must be designed explicitly. If the proxy cannot set per-call attributes, use a dedicated RestClient with a policy-fixed resolver or a controlled adapter layer.

Do not assume every proxy method automatically picks the right OAuth2 client registration simply because the underlying RestClient has an interceptor.

## 18. Testing the Interceptor-to-Manager Connection

When testing the integration, separate three layers:

1. **Mapping unit tests:** resolvers return the expected registration ID and principal for the request.
2. **HTTP client tests:** a RestClient with the interceptor sets `Authorization: Bearer ...` when the manager returns a valid authorized client.
3. **Authorization integration tests:** a mock Token Endpoint/trust setup verifies the manager actually requests or refreshes tokens per grant.

**Do not use unit tests with dummy Access Tokens to conclude that OIDC ID Token validation or Token Endpoint client authentication is correct.** Those are separate layers.

### 18.1. Scenarios to Cover

| Scenario | Expected Outcome |
| --- | --- |
| Client Credentials, valid registration and principal | Interceptor obtains authorized client and attaches Bearer header |
| Request missing `clientRegistrationId` | Does not fall back to a high-privilege default client |
| Fixed application-level principal | Subsequent calls reload the authorized client under the same key |
| Different principal | Does not accidentally reuse the previous principal's token |
| Unexpired Access Token | Authorized client can be reused |
| Expired Access Token | Manager issues/refreshes token if grant and policy allow |
| Token Endpoint returns `invalid_client` | API call is not made with a bogus token |
| Token Endpoint returns `invalid_scope` | Does not self-escalate scope |
| Resource Server returns `401 invalid_token` | Failure handler handles invalid token per policy; no infinite retry |
| Resource Server returns `403 insufficient_scope` | Does not try to request admin scopes |
| API returns 404 | Does not wipe tokens when the error is not an OAuth2 token failure |
| Call to host outside allowlist | Token not attached; request blocked by policy |
| Background job without SecurityContext | Service principal resolver still works |
| Two client registrations exist | Reports token is not sent to Billing |
| Two instances share authorized clients | Behaves according to storage/coordination design |
| Logging enabled on RestClient | `Authorization` header does not appear in logs |

### 18.2. Mocking the HTTP Client and Manager

With Spring Framework, `MockRestServiceServer` can test requests built by RestClient; with Spring Security, you can inject a manager test double returning an `OAuth2AuthorizedClient` with a **dummy** Access Token.

Test diagram:

~~~text
RestClient request
  -> OAuth2ClientHttpRequestInterceptor(testManager)
  -> HTTP Mock Server
       assert request path = /v1/reports
       assert Authorization header = Bearer TEST_ONLY_TOKEN
       return mock JSON
~~~

A separate test should ensure the manager does not use a token for the wrong registration/principal. This test is distinct from a real integration test hitting an Authorization Server.

For OAuth2 error cases, mock the Token Endpoint/Resource Server to return the exact HTTP status and OAuth2 error body per contract; verify the handler classifies the error properly and does not delete tokens for unrelated errors.

### 18.3. Testing in the Servlet Runtime

For delegated user tokens, tests should prove:

- `SecurityContext` holds the expected logged-in `Authentication`.
- Registration `company-login` is selected accurately.
- The outbound API receives an Access Token **meant for that API**.
- The Access Token is never leaked in controller responses.
- User B never uses User A's authorized client.
- Logout or session expiration affects the token store according to policy.

If a test only mocks `@AuthenticationPrincipal` and bypasses the interceptor and manager, it has not verified the OAuth2 RestClient integration.

## 19. Practical Scenarios

### Scenario A — Service Uses Client Credentials, but Interceptor Cannot Find a Principal

A scheduled job uses RestClient; code sets `clientRegistrationId("reports-service")`, yet the default interceptor looks up the principal from an empty `SecurityContextHolder`.

**Solution:** use a service manager with `RequestAttributePrincipalResolver` and pass `principal("system-report-exporter")`. Never fabricate a fake user `Authentication` to work around missing context.

### Scenario B — One RestClient Calling Two APIs

Code calls both Reports and Billing, accidentally passing `reports-service` for both.

**Solution:** split RestClients/registrations along API boundaries or always assign request attributes via server-side mapping, never letting callers arbitrarily select high-privilege registrations.

### Scenario C — An OIDC-Logged-In User Wants to View Their Reports

The app has `company-login` and an Access Token issued for the delegated API.

**Solution:** use the interceptor with the default principal from `SecurityContext` and select `company-login`. Do not use the application-wide `reports-service` token instead of a user token when the API requires user context.

### Scenario D — RestClient Calls the Token Endpoint Repeatedly

Every `GET /reports` causes the manager to request a Client Credentials Access Token.

**How to investigate:** is the principal name changing? Do the manager and service use the same backing store? Is the Access Token TTL long enough? Are multiple pods using separate in-memory services? Do not blame the interceptor for "not caching" when the issue lies in authorized client storage.

### Scenario E — Resource Server Returns 401 Even Though the Token Has Not Expired

The API rejects the token due to wrong issuer/audience or early revocation.

**Solution:** inspect Resource Server policy, registration, and target audience. Configure an authorization failure handler to remove invalid tokens by error code. Do not assume exchanging a Refresh Token fixes a mismatched audience.

### Scenario F — Resource Server Returns 403 `insufficient_scope`

The client holds a `reports.read` token but calls an update API requiring `reports.write`.

**Solution:** do not retry by trying to self-escalate scopes; update policy/registration through an approved workflow if write permission is truly required.

### Scenario G — Adding a Logging Interceptor for Debugging

HTTP tracing logs all request headers, including the Bearer Token added by the OAuth2 interceptor.

**Solution:** redact `Authorization` and token request credentials across all logging/observability layers. Do not rely solely on changing interceptor order hoping tokens won't be logged.

### Scenario H — An Endpoint Accepts an Arbitrary URL from the User

The backend calls `restClient.get().uri(userUrl)` using a RestClient configured with an OAuth2 interceptor.

**Solution:** block URLs outside an allowlist and separate HTTP clients for public fetches from credentialed clients. Never send Bearer tokens to browser-chosen destinations.

### Scenario I — Worker Outside an HTTP Request Uses `DefaultOAuth2AuthorizedClientManager`

The token manager is configured with a Servlet repository, and the worker has no request/response.

**Solution:** use `AuthorizedClientServiceOAuth2AuthorizedClientManager` with `OAuth2AuthorizedClientService`. For Client Credentials, pass a stable app-level principal.

### Scenario J — The Interceptor Failure Handler Does Not Immediately Resolve a 401 Request

The Resource Server returns 401; the authorized client is removed per policy, yet the REST call still throws an exception.

**Solution:** understand that invalidation mainly affects the next call. If retry is a business requirement, implement a bounded retry policy with idempotency checks and clear error responses.

## 20. Common Mistakes

### 20.1. Hard-Coding a Bearer Token in the RestClient Bean

An Access Token has a limited lifetime. Putting a token into `defaultHeader("Authorization", ...)` when building the bean causes the stale token to be reused forever and sent for the wrong principal.

### 20.2. Confusing `clientRegistrationId` with `principal`

The registration identifies the client/provider configuration; the principal identifies whom the authorized client belongs to. They are distinct values and both are needed to pick the right token.

### 20.3. Using Client Credentials Instead of User Authorization Code

Client Credentials issues a service token; it does not inherently represent a user. A backend holding a broad service token must enforce user authorization itself when acting on a user's behalf under an approved architecture.

### 20.4. Not Handling Stale Tokens in Resource Server Responses

A token that appears unexpired on the client can still be rejected by the API. Distinguish invalid tokens from insufficient scopes and business policies.

### 20.5. Deleting Every Token on an HTTP 403

A 403 may be caused by tenant or data permissions. Never wipe authorized clients across users/registrations because one API call lacked permission.

### 20.6. Attaching the Interceptor to a General-Purpose RestClient

A RestClient bean with an OAuth2 interceptor calling arbitrary hostnames/URIs can leak Access Tokens. Split clients per API host and fix/allowlist destinations.

### 20.7. Using a Service Manager with a Browser-Supplied Principal

If code lets users specify a service principal name, it can read/overwrite the wrong authorized client in a shared store. Principals must come from server-side policy.

### 20.8. Assuming the Interceptor Supplies an ID Token

The interceptor attaches an **Access Token** to call APIs. The OIDC Login ID Token is used to authenticate the user to the client, not as a Bearer Token for APIs.

### 20.9. Mismatched Storage and Failure Handler

The manager saving into JDBC service A while the failure handler deletes from session/repository B leaves the bad token inside A. Use the same backing store and principal key.

### 20.10. Treating the Authorization Success Handler as an HTTP Request Logger

The manager can reuse tokens without issuing a new one. Do not count successful token issuances to measure API call volume; observe HTTP traffic at the client layer.

## 21. Pre-Production Design Checklist

| Question | Decision to Clarify |
| --- | --- |
| Which Spring Security version is in use? | Supports `OAuth2ClientHttpRequestInterceptor` (6.4+) |
| Which API does this RestClient call? | Controlled host/path, valid TLS |
| How is the registration selected? | Request attribute or allowlist-backed resolver |
| Does the token belong to a user or a service? | Right `PrincipalResolver`, no mixing of delegated/application identity |
| Which manager is used? | Default Servlet manager or `AuthorizedClientService` manager |
| Where is the authorized client stored? | Repository/service with matching backing store, suitable TTL/persistence |
| Which grants are permitted? | Authorization Code/Refresh Token or Client Credentials as needed |
| Are scopes/audience sufficient for the API? | Provider issues correctly; Resource Server validates |
| How are HTTP 401/403 handled? | Suitable failure handler, bounded retries |
| Is there multi-instance/concurrency? | Storage coordination, token rotation policy |
| Are Bearer tokens logged? | Credentials redacted across logging, tracing, APM |
| Can users control the API URL? | Block SSRF, fix/allowlist destinations |
| Is logout/disconnect/revocation required? | Distinguish local token deletion from provider revocation |
| Are manager/interceptor integrations tested? | Test principal/registration, Bearer header, API 401/403, Token Endpoint errors |

## 22. References

- Spring Security — OAuth 2.0 Client (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — Authorized Client Features, RestClient Integration: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — OAuth2ClientHttpRequestInterceptor Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/client/OAuth2ClientHttpRequestInterceptor.html
- Spring Security — OAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html
- Spring Security — DefaultOAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html
- Spring Security — AuthorizedClientServiceOAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html
- Spring Framework — RestClient: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- OAuth 2.0 Authorization Framework (RFC 6749): https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Bearer Token Usage (RFC 6750): https://www.rfc-editor.org/rfc/rfc6750
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700

## 23. Conclusion: Interceptor and Manager Collaborate, Each Layer Keeping Its Responsibility

~~~text
RestClient outbound request
  |
  +-- .attributes(clientRegistrationId("reports-service"))
  +-- .attributes(principal("system-report-exporter"))
  |
  v
OAuth2ClientHttpRequestInterceptor
  |
  +-- ClientRegistrationIdResolver -> selects registration
  +-- PrincipalResolver -> selects principal
  |
  v
OAuth2AuthorizedClientManager
  |
  +-- Loads authorized client from store
  +-- Issues/refreshes token via matching grant when needed
  +-- Saves new authorized client
  |
  v
Interceptor attaches Authorization: Bearer <access_token>
  |
  v
Resource Server validates token + scope + audience + policy
  |
  +-- 2xx -> process response
  +-- 401/403 -> failure handling per OAuth2 error code
  +-- timeout/5xx -> retry/circuit breaker policy
~~~

**Three key takeaways:**

1. **`OAuth2ClientHttpRequestInterceptor` bridges RestClient and `OAuth2AuthorizedClientManager`**, attaching Bearer Access Tokens without duplicating token logic in every controller.
2. **`clientRegistrationId` and `principal` determine which token is selected.** For user-delegated flows, the principal usually comes from `SecurityContext`; for Client Credentials, use a controlled application-level principal.
3. **The interceptor does not replace Resource Server authorization or API security policies.** Protect Access Tokens from logging/SSRF, enforce proper audience/scopes, handle HTTP 401/403 by error code, and never retry or escalate privileges arbitrarily.

When the manager, store, and resolvers are configured consistently, a Servlet application can use RestClient uniformly for both user-delegated APIs and machine-to-machine APIs while keeping **OIDC authentication**, **OAuth2 authorization**, **authorized client lifecycle**, and **secure HTTP requests** cleanly separated.
