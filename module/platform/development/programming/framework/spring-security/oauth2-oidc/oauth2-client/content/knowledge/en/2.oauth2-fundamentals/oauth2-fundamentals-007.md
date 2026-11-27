# 2.7. Client Credentials Grant and Application Identity

## Lesson Objectives

After this lesson, you will be able to:

- Explain when to use the **OAuth 2.0 Client Credentials Grant** for application-to-application or service-to-service communication.
- Distinguish **client authentication**, **API access authorization**, and **end-user authentication**.
- Describe the workflow for obtaining an access token directly from the token endpoint without a browser, authorization code, or user login session.
- Understand where "application identity" is represented and verified, as well as the limits of interpreting claims in an access token.
- Configure Spring Boot and use `OAuth2AuthorizedClientManager` to acquire and reuse access tokens when a backend task calls another API.
- Identify security requirements when storing client credentials, scoping permissions, and managing token lifecycles.

## 1. Context: A Service Needs Access Without a Logged-In User

Suppose a system has two services:

- **Order Scheduler:** aggregates orders ready for shipping every few minutes.
- **Inventory API:** provides inventory information and only returns data to authorized applications.

Order Scheduler runs as a background task. No user opens a browser or clicks a "Log in" button when the task starts. Even so, Inventory API still needs to know **whether the calling application has been granted permission**.

Using a fake user account and password to log in would conflate application identity with human identity. Leaving the API completely open would let anyone who knows the endpoint address send requests.

OAuth 2.0 provides a more suitable mechanism: the **Client Credentials Grant**. The application registers with the Authorization Server, proves its client identity, receives an **access token**, and uses that access token to call the API.

> Key point: with the Client Credentials Grant, **the client acts on its own behalf** or under an authorization agreement established with the Authorization Server; there is no interactive end-user login step to grant consent in this flow.

## 2. What Is the Client Credentials Grant?

The **Client Credentials Grant** is an OAuth 2.0 grant type defined in RFC 6749, Section 4.4. A client can use its own credentials to request an access token at the Authorization Server.

This grant is intended for clients capable of authenticating to the Authorization Server and protecting the required credentials—typically a **confidential client** running on a backend or server environment with secret management.

### 2.1. Participating Components

| Component | Role in the Example |
|---|---|
| **OAuth 2.0 Client** | Order Scheduler: the program wanting to call Inventory API |
| **Authorization Server (AS)** | Authenticates the client, determines granted permissions, and issues access tokens |
| **Resource Server (RS)** | Inventory API: receives the access token and decides which operations to allow |
| **Resource Owner** | The entity or organization owning rights to the resource; authorization is pre-established by policy rather than through a user consent screen in this flow |

In many systems, the Authorization Server and Resource Server are two different products or services. The Client must trust and be properly configured for the Authorization Server that issues tokens for the target API.

### 2.2. Steps Absent from This Flow

The Client Credentials Grant **does not need**:

- An interactive login page for end users.
- Browser redirects to the authorization endpoint.
- An authorization code and redirect URI.
- `state`, `nonce`, or PKCE serving interactive flows.
- An OIDC ID token to authenticate an End-User.

Having no authorization code does not mean skipping security. The Client still must prove its identity to the Authorization Server, and the Resource Server still must validate the access token and access permissions.

### 2.3. Flow Diagram

~~~mermaid
sequenceDiagram
    autonumber
    participant Job as Order Scheduler (OAuth Client)
    participant AS as Authorization Server
    participant API as Inventory API (Resource Server)
    Job->>AS: POST /oauth2/token, grant_type=client_credentials<br/>+ client auth, requested scope
    AS->>AS: Authenticates client and checks granted permissions
    AS-->>Job: access_token, token_type, expires_in
    Job->>API: GET /api/inventory<br/>Authorization: Bearer access_token
    API->>API: Validates token and authorization policies
    API-->>Job: Authorized inventory data
    Note over Job,AS: When token expires, client requests a new token per policy
~~~

The flow crosses two distinct trust relationships:

1. **Client → Authorization Server:** "Which application am I? Am I allowed to receive a token with these permissions?"
2. **Client → Resource Server:** "Is this access token valid and sufficient to perform the requested operation?"

A client that authenticates successfully at the token endpoint **is not guaranteed** to receive every scope. An issued access token **is not guaranteed** to work at every Resource Server.

## 3. Requesting a Token Over HTTP

### 3.1. Registering the Client Before Calling

Typically, an administrator or Authorization Server provisioning workflow registers a client:

| Property | Example | Meaning |
|---|---|---|
| Client ID | `order-scheduler` | Public identifier of the OAuth client |
| Client authentication | `client_secret_basic` | How the client proves its identity at the token endpoint |
| Client credential | Secret stored in a secret manager | Secret known only to the backend and the AS |
| Allowed grant | `client_credentials` | Grant type permitted by the AS for the client |
| Allowed scope | `inventory.read` | Maximum permissions that may be granted per configuration |
| Target resource/audience | Inventory API (if supported by the AS config) | Restricts where the access token is accepted |

**A Client ID is not a secret.** Knowing a client ID is not enough to obtain an access token when client authentication is properly configured.

### 3.2. Standard Request

The Client sends a request to the token endpoint using HTTP POST with an `application/x-www-form-urlencoded` body.

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <encoded-client-credentials>

grant_type=client_credentials&scope=inventory.read
~~~

In this example:

- `grant_type=client_credentials` specifies the grant type.
- `scope=inventory.read` requests inventory read permission; this field is **optional** at the protocol level and supported values depend on the Authorization Server.
- The `Authorization: Basic ...` header authenticates the client via `client_secret_basic`; data is encoded per HTTP Basic rules, **not an encryption mechanism replacing TLS**.
- The token endpoint **must use TLS/HTTPS** in production deployments.

Some ASs support other client authentication methods such as `private_key_jwt` or mutual TLS; in those cases the request will differ from the example above. Grant type and client authentication method are **two separate choices**.

### 3.3. Successful Response

The Authorization Server may return:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<opaque-or-jwt-access-token>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
~~~

Key fields:

| Field | Meaning |
|---|---|
| `access_token` | Value the client presents to the Resource Server to request access |
| `token_type` | Token type, usually `Bearer` |
| `expires_in` | Validity duration in seconds from issuance, when provided by the AS |
| `scope` | Actual granted scope; may be narrower than requested |

The payload above is illustrative only. Access tokens may be **JWTs** or **opaque tokens**. There is no universal rule requiring access tokens to be JWTs or always contain the same claim set.

According to RFC 6749, in the Client Credentials Grant, **a refresh token is normally not issued, and the standard recommends against including one**. When the access token expires, the client simply re-authenticates with the Authorization Server to obtain a new token.

Do not write code that depends on always receiving a refresh token. Nor should you invent a "renewal" workflow by altering expiration timestamps on the client side.

### 3.4. Using the Token to Call the API

~~~http
GET /api/inventory HTTP/1.1
Host: inventory.example.com
Authorization: Bearer <access_token>
~~~

The Resource Server validates the token using the configured mechanism: e.g., validating signature, issuer, audience, and validity period for JWTs; or introspection against the Authorization Server for opaque tokens. After confirming the token is valid, the API must still check scopes/authorities and the endpoint's business rules.

If a token was only granted `inventory.read`, it cannot automatically be allowed to perform `inventory.write` updates.

## 4. What Is "Application Identity" Really?

This is the easiest point to misunderstand when learning the Client Credentials Grant.

### 4.1. Client Authentication Verifies the Application at the Token Endpoint

When Order Scheduler sends a token request, the Authorization Server must verify the client according to its registered method, e.g., checking a client secret, client assertion signature, or certificate.

If successful, the AS knows the request comes from the client identified by that authenticated client registration. This is **the OAuth client's identity**, not an end-user identity.

This relationship can be depicted as:

~~~text
client_id = order-scheduler
          |
          | client authentication at token endpoint
          v
Authorization Server
          |
          | issues access token per policy
          v
Inventory API receives token intended for the API
~~~

Three artifacts must be distinguished:

1. **`client_id`:** the client's registration identifier with the Authorization Server.
2. **Client credential:** proof the client uses to authenticate itself to the Authorization Server.
3. **Access token:** authorization proof that the Resource Server can validate, which may contain client-related claims per the AS's issuance rules.

Never treat a self-declared `client_id` string in an HTTP request as trustworthy proof. The Resource Server must rely on a valid token and verified claims/policies.

### 4.2. Application Permissions Are Not an Employee's Permissions

Suppose an access token issued to Order Scheduler has permissions:

~~~text
inventory.read
shipment.create
~~~

This means the AS allows **the application** to perform those operations within current policies. It **does not say "employee A approved order 123."**

If business logic needs to verify which user is acting—for example, only the order owner may edit an order—the Client Credentials Grant alone does not carry appropriate user authentication and delegation context. In that case, choose an architecture that passes valid user context, such as Authorization Code for user-facing apps or a system-supported token exchange/on-behalf-of mechanism.

### 4.3. Identifying the Client from Claims in the Access Token

An Authorization Server might issue a JWT access token containing illustrative data like:

~~~json
{
  "iss": "https://auth.example.com",
  "aud": "inventory-api",
  "client_id": "order-scheduler",
  "scope": "inventory.read",
  "iat": 1760000000,
  "exp": 1760000300
}
~~~

This is **one possible implementation**, not a payload every OAuth 2.0 Server is required to emit. Specifically:

- `client_id` may appear as a claim, or be represented under another claim name depending on token profile standards and products.
- `sub`, if present, may represent a service account, the client itself, or another principal depending on issuer policy. Do not assume `sub` is always a real human user ID.
- `aud` expresses the token's audience when issued in a supported format; the Resource Server must ensure the token was actually issued for it.
- `scope` expresses the granted permissions in the token, though how scopes map to operational permissions depends on the Resource Server.
- With **opaque tokens**, the Resource Server cannot decode claims locally like a JWT; it must use an appropriate verification mechanism such as introspection.

A validly signed token is not enough if the issuer, audience, or permissions do not match. Nor can you guarantee "which application called the API" merely by trusting an arbitrary `X-Client-Id` header.

### 4.4. OAuth Client, Service Account, and Workload Identity

These concepts are related but not identical:

| Concept | Explanation |
|---|---|
| **OAuth client** | Entity registered with the AS to request tokens, having a `client_id` and authentication method |
| **Service account** | Non-human account created by an identity management system, which may be mapped to an OAuth client |
| **Workload identity** | Identity of a running process/service, e.g., per cloud platform or federation mechanism |
| **End-User identity** | Identity of an interactively logged-in end user, typically handled via OIDC when the app is an RP |

A system can use a workload identity to authenticate an OAuth client without storing a long-lived client secret. However, how these concepts map together is a feature of the Authorization Server/platform, not an automatic guarantee of `client_credentials`.

## 5. How Client Credentials Grant Differs from Authorization Code and OIDC

| Criterion | Client Credentials | Authorization Code + OIDC |
|---|---|---|
| Acting subject | Application/client | End user logging in via the application |
| Browser interaction | No | Typically involves browser redirects in web login |
| Authorization endpoint | Not used in this flow | Yes |
| Token endpoint | Yes | Yes, to exchange authorization code for tokens |
| `redirect_uri` / code | No | Yes |
| `state` / `nonce` / PKCE | Do not belong to Client Credentials Grant | Used per mechanism and flow requirements |
| Access token | Yes | Usually yes |
| OIDC ID token | Not issued as a standard outcome of this grant | Present in OIDC flows |
| Question answered | "Which APIs is the application allowed to call?" | "Who is the user?" and/or "What did the user authorize the application to do?" |
| Typical use cases | Background jobs, server-to-server, automation | Web login, apps needing access to user resources |

**OIDC is not an "advanced Client Credentials."** OIDC adds an End-User authentication layer to appropriate flows. There is no End-User in the Client Credentials Grant, so there is no default reason to request the `openid` scope or expect an `id_token`.

Even if a Spring Boot application is an "OIDC Client", it can still register a separate OAuth client with the `client_credentials` grant for server-to-server communication.

## 6. Configuring Spring Boot OAuth 2.0 Client Credentials

Suppose Order Scheduler runs on Spring Boot and calls Inventory API via the enterprise Authorization Server. The example focuses on a **Servlet/Spring Boot backend** or background task, requiring no user login page.

### 6.1. Adding the Dependency

With Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

This starter provides components for configuring client registrations, managing authorized clients, and interacting with the token endpoint. It does not turn the application into a Resource Server.

### 6.2. Declaring the Client Registration

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-service:
            provider: internal-as
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          internal-as:
            token-uri: https://auth.example.com/oauth2/token
~~~

Key fields:

| Setting | Role |
|---|---|
| `registration.inventory-service` | Registration name used in Java code to select the client |
| `provider: internal-as` | Links the registration to the Authorization Server config |
| `client-id` and `client-secret` | Identifies and authenticates the client with the AS |
| `client-authentication-method` | Authentication method, HTTP Basic here |
| `authorization-grant-type` | Must be `client_credentials` for this example |
| `scope` | Permissions the client asks the AS to grant |
| `token-uri` | Endpoint where the client directly requests access tokens |

Do not declare `redirect-uri` or `authorization-uri` because this flow does not redirect users. With an OAuth server that does not provide OIDC discovery, configuring `token-uri` directly suffices for the Client Credentials example.

The environment variables `INVENTORY_CLIENT_ID` and `INVENTORY_CLIENT_SECRET` are supplied in the runtime environment; never put real secrets in Git, README examples, or logs. The domain `example.com` is used purely as an illustrative address.

### 6.3. Creating `OAuth2AuthorizedClientManager` for Background Tasks

In Spring Security, `OAuth2AuthorizedClientManager` manages acquiring and re-authorizing tokens according to `ClientRegistration`.

For tasks not running within a user's HTTP request, `AuthorizedClientServiceOAuth2AuthorizedClientManager` is the right choice because it uses `OAuth2AuthorizedClientService` to store/retrieve authorized clients.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class MachineToMachineOAuthConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClientService) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        var manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                        registrations,
                        authorizedClientService
                );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

The code above assumes the Spring Boot project has configured OAuth 2.0 Client and has a corresponding `OAuth2AuthorizedClientService` bean. In standard setups, Spring Boot/Spring Security provides a default implementation; for persisting state across multiple instances or restarts, the architecture may need a more suitable implementation.

Notable points:

- `clientCredentials()` simply enables the provider handling that grant.
- The manager uses the client registration to know the client ID, authentication method, token URI, and scopes.
- The authorized client holds the access token along with registration info and principal context; the manager can reuse a still-valid token and request a new one when needed.
- Having a manager does not create a user login session. `oauth2Login()` is not needed to run background jobs with `client_credentials`.

### 6.4. Acquiring a Token and Calling Inventory API

Example using Spring Framework 6.1+'s `RestClient`:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryGateway {

    private static final String REGISTRATION_ID = "inventory-service";
    private static final String WORKER_PRINCIPAL = "order-scheduler-worker";

    private final OAuth2AuthorizedClientManager clientManager;
    private final RestClient inventoryApi;

    public InventoryGateway(
            OAuth2AuthorizedClientManager clientManager,
            RestClient.Builder restClientBuilder) {

        this.clientManager = clientManager;
        this.inventoryApi = restClientBuilder
                .baseUrl("https://inventory.example.com")
                .build();
    }

    public String fetchInventory() {
        OAuth2AuthorizeRequest authorizationRequest =
                OAuth2AuthorizeRequest
                        .withClientRegistrationId(REGISTRATION_ID)
                        .principal(WORKER_PRINCIPAL)
                        .build();

        OAuth2AuthorizedClient authorizedClient =
                clientManager.authorize(authorizationRequest);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                    "No OAuth2 authorized client for inventory-service"
            );
        }

        String accessToken =
                authorizedClient.getAccessToken().getTokenValue();

        return inventoryApi.get()
                .uri("/api/inventory")
                .headers(headers -> headers.setBearerAuth(accessToken))
                .retrieve()
                .body(String.class);
    }
}
~~~

Code flow explanation:

1. `REGISTRATION_ID` points to `spring.security.oauth2.client.registration.inventory-service`.
2. `principal("order-scheduler-worker")` is a **stable identifier key within the authorized client/token management context**. It **does not create a logged-in user** and does not automatically become a token identity claim.
3. `clientManager.authorize(...)` looks up the appropriate authorized client, requests an access token when needed, and returns it for use.
4. `RestClient` attaches the token to the `Authorization: Bearer ...` header when calling Inventory API.
5. Inventory API is responsible for validating the token and enforcing `inventory.read` or an equivalent policy.

The example returns a JSON string for brevity. In a real application, define response types (DTOs), handle network errors, timeouts, and invalid token/permission cases.

**Why use a fixed principal?** In a service-to-service grant, this principal name forms part of the authorized client's token cache key. Using a random name on every call can trigger unnecessary token requests. If an application has multiple client registrations or authorization contexts, choose separate, stable keys matching the token management strategy.

### 6.5. When to Configure `oauth2Client()` and `oauth2Login()`?

In a web application using a Spring Security Filter Chain, `oauth2Client()` enables OAuth 2.0 Client integrations suited for a servlet environment. `oauth2Login()` handles user login via redirect and can lead to OIDC authentication.

For a background task that only needs `OAuth2AuthorizedClientManager` as in the example, **there is no need to enable OIDC login**. Token acquisition is coordinated by the manager and client registration, independent of browsers or login session cookies.

If the same application has both OIDC login web pages and background jobs, use **two different registrations when grants, permissions, or application identities differ**, for example:

- `employee-login`: Authorization Code + OIDC for employees.
- `inventory-service`: Client Credentials for background jobs.

This design prevents mistakenly using a user's access token for system jobs, or using an application token for actions requiring per-user authorization checks.

## 7. Managing the Access Token Lifecycle

### 7.1. Do Not Request a New Token Before Every API Call If Still Valid

Token endpoints have rate limits and latency. A worker running 1,000 times/minute that requests a token for every call creates unnecessary load. `OAuth2AuthorizedClientManager` paired with `OAuth2AuthorizedClientService` persists and reuses authorized clients by registration/principal.

A typical client manager tracks expiration timestamps to decide when to fetch a new token. Note that a token can be revoked early or rejected by the Resource Server due to permission changes even before its expiration time arrives.

In multi-instance systems, having each instance maintain its own token cache is sometimes acceptable. If state must be shared or token endpoint traffic minimized, design an additional token storage, synchronization, and concurrency-handling layer, never storing tokens without access controls.

### 7.2. When to Request a New Token?

- When no matching authorized client/access token exists yet.
- When the access token is about to expire or has expired per the manager's criteria.
- When the token was revoked or the Resource Server returns an error indicating the current token is no longer valid, per the designed error-handling strategy.

Typically, the Client Credentials Grant **repeats the `grant_type=client_credentials` request** to obtain a new token, rather than performing a refresh token flow like user-facing grants.

Never write an infinite retry loop on HTTP 401/403. If the failure is due to wrong credentials, ungranted scopes, or wrong audience, requesting the same token again will not fix the root cause.

### 7.3. Distinguishing Errors from Authorization Server and Resource Server

| Stage | Common Symptom | How to Handle |
|---|---|---|
| Token request | `invalid_client` | Check client ID, secret, authentication method, client status |
| Token request | `unauthorized_client` | Grant type or operation is not enabled for the client |
| Token request | `invalid_scope` | Misnamed scope or outside the permissions granted to the client |
| API call | HTTP 401 / `invalid_token` | Token missing, expired, revoked, mismatched issuer/audience, or rejected |
| API call | HTTP 403 / `insufficient_scope` or business permission error | Token may be valid, but lacks permissions or fails API policy |
| Token/API call | Timeout, 429, 5xx | Monitor, bound retries, apply backoff and circuit breakers per environment |

Exact error messages and HTTP statuses depend on the AS/RS product and implementation. When troubleshooting, distinguish **failed to acquire token**, **token rejected**, and **token valid but insufficient permissions**.

## 8. Security Design for Application Identity

### 8.1. How Should the Client Authenticate?

| Authentication Method | Characteristics | Notes |
|---|---|---|
| `client_secret_basic` | Sends client secret via HTTP Basic to token endpoint | Common, easy to integrate; protect secret and require HTTPS |
| `client_secret_post` | Places client ID/secret in token request body | Use only when required for compatibility and supported by AS; avoid logging body |
| `private_key_jwt` | Client signs assertion with private key; AS verifies with public key | Suitable with key management infrastructure; validate assertion expiry/audience |
| Mutual TLS client authentication | Client proves identity with TLS certificate | Requires certificate management and AS support |
| Workload identity federation | Uses identity proof from the runtime platform to establish token-request rights | Exact mechanism depends on platform and AS; reduces reliance on long-lived shared secrets when supported |

**Grant type** `client_credentials` describes *why the client requests a token*. **Client authentication method** describes *how the client proves its identity*. Do not confuse these two concepts.

### 8.2. Principle of Least Privilege

- Each service/task should have its own client registration when responsibilities and permissions differ.
- Grant only necessary scopes, e.g., `inventory.read` for a read-only inventory task.
- Restrict target audience/resource so tokens cannot be reused arbitrarily at other APIs.
- Use appropriate token lifetimes and revocation/rotation mechanisms per policy.
- The Resource Server validates issuer, audience, validity window, and permissions—not merely "whether a token is present."
- Enforce business-level authorization at the Resource Server. For instance, `inventory.read` does not automatically grant permission to read every warehouse or every tenant.

### 8.3. Protecting Client Secrets and Access Tokens

Both client secrets and access tokens are sensitive, yet they play different roles. If a client secret leaks, an attacker can mint new tokens themselves until the credential is revoked or rotated. If a bearer access token leaks, another party can use that token for as long and as broadly as it is accepted.

Practical safeguards:

1. Use a secret manager or the deployment environment's secret injection mechanism.
2. Never commit credentials to repositories, public config files, or Docker images.
3. Never write full credentials/tokens into logs, exceptions, traces, analytics, or browser responses.
4. Only call token endpoints/APIs over valid HTTPS.
5. Periodically rotate credentials per AS capabilities and deployment processes.
6. Restrict secret access to the right workloads; avoid sharing one client secret across independent systems.
7. Control exposure risk of access tokens in memory dumps, diagnostics, or observability systems.

### 8.4. A Bearer Token Does Not Prove Which Exact Process Holds It

With a standard bearer token, the Resource Server lets any party holding a valid token within accepted boundaries use it; it does not inherently prove that the current request came from the exact process that requested the token. Therefore, the concept of "application identity" at the Resource Server **is bounded by the token authentication mechanism**.

Token mechanisms bound to a key/certificate holder (sender-constrained tokens), if supported by both AS and RS, can reduce the risk of replaying stolen tokens. However, this is an additional design choice—not something that automatically comes from using `client_credentials`.

## 9. Scenarios for Choosing a Grant

### Scenario A — Nightly Data Aggregation Job

A scheduled Spring Boot process fetches data from Reporting API. No user is logged in. Client Credentials Grant is the natural fit if the AS and API grant permissions directly to the application.

**Meaningful identity:** the background process/reporting client.

### Scenario B — User Clicks "Export Personal Report"

A web app needs to download data belonging to a specific user's permissions. If the API must know who requested it and evaluate that user's permissions, using only the web app's Client Credentials token loses user context.

**Consider:** Authorization Code with user login, an API-scoped token, or a properly designed and supported delegation/token-exchange mechanism.

### Scenario C — One API Calling Another API

Billing API receives a request from the frontend and calls Tax API. If the call to Tax API is a system operation independent of the user, Billing API can use Client Credentials. If Tax API must authorize based on the requesting user, a proper authorization-context propagation mechanism is needed.

**Do not assume:** "Backend calling backend" must always use Client Credentials; determine whether the permissions belong to the application or to the user.

### Scenario D — Multi-Tenant SaaS

A client having `orders.read` does not mean it has permission to read orders for every tenant. If access is tenant-scoped, the AS/RS need a mechanism to express and validate tenant bindings; the application must not rely solely on a broad scope and blindly accept any tenant ID in the URL.

## 10. Common Mistakes

**"Having a client ID is enough to request an access token."**  
No. Client Credentials Grant requires client authentication in a form accepted by the AS. `client_id` is only an identifier, not proof of credential possession.

**"Client Credentials returns an ID token to identify which application it is."**  
No. The standard result is an access token for resource access permissions. ID tokens belong to OIDC end-user authentication and are not a default part of Client Credentials Grant.

**"The JWT has `sub`, so `sub` must be a human user."**  
No. The meaning of `sub` depends on the token format and issuer. In a machine-to-machine flow, it may be a service account or another non-human subject.

**"If the access token is a valid JWT, it can call any API."**  
No. APIs must validate audience/resource, issuer, expiration, and authorization policies. A token issued for Inventory API is not automatically usable at Payment API.

**"Backend apps should use an admin user account's token."**  
Do not disguise server tasks as fake human activity. Register a proper application identity and grant only the permissions the job needs.

**"Manually POST for a new token before every single API call."**  
Unnecessary. The manager can track and reuse still-valid tokens; uncontrolled repeated token requests load the AS.

**"Once `oauth2Login()` is configured, Client Credentials runs automatically."**  
No. `oauth2Login()` handles interactive login. Machine-to-machine grants require a `client_credentials` registration and appropriate OAuth client/authorized client logic.

## 11. Thought Exercise

Consider a system of three services:

- **Invoice Worker** creates invoices periodically using client ID `invoice-worker`.
- **Authorization Server** authenticates Invoice Worker and issues a token with scope `invoice.create` and audience targeting Invoice API.
- **Invoice API** protects the `POST /invoices` endpoint.

**Question 1: Who is the Resource Server?**  
Invoice API, because it receives the access token to decide whether to allow creating an invoice.

**Question 2: Does having scope `invoice.create` in the token prove which employee created the invoice?**  
No. It represents permissions granted to the client in a machine-to-machine flow. If user attribution is required, the business logic must add a user identity model and appropriate proof source.

**Question 3: The worker runs overnight and the token expires after 5 minutes. Is a refresh token needed?**  
Not necessarily. The client can re-authenticate using the `client_credentials` grant to obtain a new access token; Spring Security can coordinate this.

**Question 4: Why should Invoice API not trust an `X-Client-Id: invoice-worker` header sent directly by the caller?**  
Because any client can set that header itself. The API must verify the access token and claims/policies issued by a trusted Authorization Server.

**Question 5: If the Worker also needs to call Payment API with different permissions, what should be done?**  
Define the appropriate scope/audience/registration and policy for Payment API, potentially using a separate client registration with least privilege. Never assume an Invoice API token will also be accepted by Payment API.

## Remember

The **Client Credentials Grant** is OAuth 2.0's mechanism for a backend application to authenticate its client identity with an Authorization Server and obtain an access token for API access within granted scopes. There is no end-user login and no OIDC ID token in the standard flow. Spring Security supports this mechanism through `ClientRegistration`, `OAuth2AuthorizedClientManager`, and the `clientCredentials()` provider; the application still must protect credentials, manage tokens, and let the Resource Server thoroughly enforce access permissions.
