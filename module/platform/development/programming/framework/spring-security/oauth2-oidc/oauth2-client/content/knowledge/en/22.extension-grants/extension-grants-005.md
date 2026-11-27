# 22.5. Designing an OAuth2AuthorizedClientProvider for a Custom Grant

## 1. Problem Statement: The Authorization Server Supports a Grant, Yet Spring Security Lacks a Matching Provider

Suppose the **Employee Portal** system uses **Spring Boot 3 / Spring Security 6** and has a background worker that needs to call the **Reports API**. The organization's Authorization Server accepts an internal extension grant using a short-lived **workload ticket** issued by a trusted service.

Protocol agreement between the OAuth2 Client and Authorization Server:

~~~text
registrationId = reports-with-ticket
grant_type     = urn:example:params:oauth:grant-type:workload-ticket
client_auth    = client_secret_basic (illustrative example only)
workload_ticket = a signed ticket with audience, expiration, and anti-replay
scope          = reports.read (if accepted by the provider)
~~~

Illustrative flow:

~~~mermaid
sequenceDiagram
    participant Job as Reports Worker
    participant Manager as OAuth2AuthorizedClientManager
    participant Provider as Custom OAuth2AuthorizedClientProvider
    participant Ticket as Trusted Ticket Issuer
    participant AS as Authorization Server
    participant API as Reports API

    Job->>Manager: authorize(reports-with-ticket, reports-worker)
    Manager->>Provider: authorize(OAuth2AuthorizationContext)
    Provider->>Provider: Check grant type, existing token, expiry
    Provider->>Ticket: Request short-lived workload ticket
    Ticket-->>Provider: Signed ticket, one-time/short-lived
    Provider->>AS: POST token endpoint, custom grant
    AS-->>Provider: OAuth2AccessTokenResponse
    Provider-->>Manager: New OAuth2AuthorizedClient
    Manager->>Manager: Save authorized client per storage policy
    Manager-->>Job: Authorized client
    Job->>API: Authorization: Bearer access token
    API-->>Job: Report data
~~~

**The problem:** the default provider chain typically supports common grants like `authorization_code`, `refresh_token`, `client_credentials`, and others depending on the version. It **does not know on its own** how to obtain a `workload_ticket` or handle `urn:example:...`.

To add a grant, do not scatter token endpoint HTTP calls across controllers or attach Bearer tokens using an ad-hoc cache. Instead, design a **custom `OAuth2AuthorizedClientProvider`** integrated with `OAuth2AuthorizedClientManager` and Spring Security's authorized client store.

> **Important:** The Workload Ticket Grant in this lesson is a **simulated protocol to illustrate the extension point**, not a standard OAuth2 grant, and is not supported by default by any Authorization Server. Only use a custom grant when the Authorization Server **genuinely defines that contract**, and it has been threat-modeled, authorized, verified for ticket handling, and agreed upon with the security team. When an existing standard or built-in provider satisfies the requirements, prefer it over inventing a new grant.

## 2. Design Goals and Boundaries of Responsibility

After this lesson, you should clearly distinguish four responsibilities:

| Component | Responsibility | Should Not Do |
|---|---|---|
| `ClientRegistration` | Describes the client, grant type, token URI, scopes, and client authentication | Does not execute the grant itself |
| `OAuth2AuthorizedClientProvider` | Decides whether this grant applies and when a new token is needed; constructs `OAuth2AuthorizedClient` | Does not own the entire cache/session/database |
| `OAuth2AccessTokenResponseClient<T>` | Sends the protocol token endpoint request and parses `OAuth2AccessTokenResponse` | Does not decide user web Authentication |
| `OAuth2AuthorizedClientManager` | Coordinates the provider chain, loads/saves authorized clients, and runs success/failure handlers | Does not define Resource Server business permissions |

When designing a custom grant, resolve these questions:

1. **Which registrations** are permitted to use the grant?
2. **Where does the evidence** (ticket/assertion/subject token) come from, and is it trustworthy?
3. When should the provider execute the grant: **no token yet**, **token nearing expiry**, **token revoked**?
4. Is the token response validated and converted into the right `OAuth2AuthorizedClient`?
5. Are **`principalName`** and **`registrationId`** kept consistent when persisting?
6. Which errors warrant retries, which require reauthorization, and which require deleting the authorized client?
7. Can the flow be used from **Servlet**, **Reactive**, and **background workers**, or are separate implementations required?

**A well-designed `OAuth2AuthorizedClientProvider` is a cleanly bounded protocol adapter**, not "any random piece of code that happens to fetch an access token."

## 3. What Is an Extension Grant in OAuth 2.0?

In an OAuth 2.0 token request, the `grant_type` parameter tells the server which authorization mechanism the client wants to use.

Familiar values include:

~~~text
authorization_code
refresh_token
client_credentials
~~~

**Extension grants** can use an absolute URI identifying the grant. For example, a standardized one is:

~~~text
urn:ietf:params:oauth:grant-type:token-exchange
~~~

defined in **RFC 8693 — OAuth 2.0 Token Exchange**. Another standard is the JWT Bearer Authorization Grant from **RFC 7523**:

~~~text
urn:ietf:params:oauth:grant-type:jwt-bearer
~~~

Meanwhile, this lesson's URI:

~~~text
urn:example:params:oauth:grant-type:workload-ticket
~~~

is an **illustrative educational URI**. It does **not** mean the system implements full RFC-compliant Token Exchange or JWT Bearer Grant. Never simply rename a grant and expect another RFC's security guarantees to apply.

### 3.1. Distinguish Custom Grants from Custom Parameters

Two cases are frequently confused:

**Case A — Genuinely new grant:**

~~~http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aexample%3Aparams%3Aoauth%3Agrant-type%3Aworkload-ticket
&workload_ticket=...
~~~

**Case B — Standard grant with extra extension parameters:**

~~~http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&resource=https%3A%2F%2Freports.example.test
~~~

Case B may only need **customizing the request parameters converter** on an existing token-response client/provider; writing a new `OAuth2AuthorizedClientProvider` is unnecessary.

**Selection rule:** write a new provider only when **grant applicability conditions, request structure, token exchange logic, or lifecycle** truly differ from grants Spring Security already supports.

### 3.2. Do Not Confuse a "Custom Grant" with Bypassing the Authorization Server

A custom grant must still:

- Call the token endpoint of a **trusted Authorization Server**.
- Authenticate the OAuth client per policy.
- Transmit evidence/credentials over HTTPS.
- Have the Authorization Server validate evidence, audience, issuer, expiry, anti-replay, and authorization policies.
- Return a valid OAuth2 token response.
- Have the Resource Server validate the access token and authorization as normal.

Never sign a string on the client and label it `access_token` if the Authorization Server did not issue or accept it.

## 4. Architecture for Extending Spring Security OAuth2 Client

~~~mermaid
flowchart TD
    C["Service / Controller / Job"] --> A["OAuth2AuthorizeRequest"]
    A --> M["OAuth2AuthorizedClientManager"]
    M --> Reg["ClientRegistrationRepository"]
    M --> Store["OAuth2AuthorizedClientRepository / Service"]
    M --> Chain["Delegating OAuth2AuthorizedClientProvider"]
    Chain --> Code["Authorization Code Provider"]
    Chain --> Refresh["Refresh Token Provider"]
    Chain --> CC["Client Credentials Provider"]
    Chain --> Custom["Custom WorkloadTicketProvider"]
    Custom --> Ticket["TrustedTicketSupplier"]
    Custom --> TR["OAuth2AccessTokenResponseClient<WorkloadTicketGrantRequest>"]
    TR --> AS["Authorization Server /token"]
    AS --> TR
    TR --> Custom
    Custom --> M
    M --> Store
    M --> C
    C --> API["Resource Server / Reports API"]
~~~

When **providers** are chained, each provider returns:

- **A new `OAuth2AuthorizedClient`** if it executed the grant successfully.
- **`null`** if the grant does not apply or no new token is needed under the synchronous contract.
- **An exception** if the selected grant execution failed.

The manager does not need to know the details of `workload_ticket`; it only sees the **provider chain** returning a token, returning no result, or failing.

## 5. The OAuth2AuthorizedClientProvider Contract

In synchronous Servlet/Spring Security OAuth2 Client, the interface is:

~~~java
package org.springframework.security.oauth2.client;

public interface OAuth2AuthorizedClientProvider {
    OAuth2AuthorizedClient authorize(
        OAuth2AuthorizationContext context
    );
}
~~~

In the actual API, the return value can be `null` by contract. Interpretation:

| Return Value | Meaning |
|---|---|
| `OAuth2AuthorizedClient` | The provider executed the grant/re-authorization and produced a resulting authorized client |
| `null` | The provider does not apply or re-authorization is unnecessary; the manager may retain the existing client or try the next provider |
| `OAuth2AuthorizationException` / appropriate error | The grant was selected, yet execution failed |

**Returning `null` does not mean authentication failed.** When the current token is still valid, a custom provider normally returns `null` so the manager keeps using the stored authorized client.

### 5.1. What Does OAuth2AuthorizationContext Contain?

A context provides:

~~~java
ClientRegistration registration = context.getClientRegistration();
Authentication principal = context.getPrincipal();
OAuth2AuthorizedClient existing = context.getAuthorizedClient();
~~~

Along with **attributes** mapped by the manager. The context is only as trustworthy as **the source that constructed it**. An unverified attribute supplied directly by a browser must never be treated as a signed assertion or employee privilege.

### 5.2. Do Not Read Sessions or Principals Arbitrarily Inside a Provider

A custom provider can be invoked from:

- A Servlet request, with `HttpServletRequest` and `SecurityContext`.
- A background job, with no browser session.
- Tests using a manually constructed `OAuth2AuthorizationContext`.

If a provider implicitly depends on `SecurityContextHolder` or thread-bound request state, it becomes hard to reuse and prone to picking the wrong principal. **Prefer data from `OAuth2AuthorizationContext` and authenticated service sources**.

## 6. Example Model: A Workload Ticket Issued by a Trusted Service

Assume the organization operates an internal **Trusted Ticket Issuer**. The issuer only issues tickets to authenticated workloads, and each ticket carries:

- A clearly identified **issuer**.
- An **audience** matching the Authorization Server's token endpoint/policy.
- A stable **subject/workload ID**.
- Short-lived **issued-at/expiration** timestamps.
- A **unique ID** or nonce against replay.
- A signature or proof verified by the Authorization Server.

This is a **server-side assumption**, not something Spring Security supplies out of the box. Educational code here will not implement JWT signing, key rotation, or ticket verification. Those must be specified, tested, and governed by your security/IdP team.

A ticket can be obtained via:

~~~java
public interface TrustedTicketSupplier {
    String issueFor(
        String clientRegistrationId,
        String trustedPrincipalName
    );
}
~~~

**Trust point:** `trustedPrincipalName` must be determined by the application, never from `?user=admin` chosen by an HTTP caller.

### 6.1. Why Not Accept Tickets from Arbitrary Request Attributes?

Dangerous example:

~~~java
// Never let a browser pass an assertion that the provider treats as trusted.
String ticket = request.getAttribute("ticket");
~~~

If a ticket must arrive from an external system, verify its origin, bind it to client/principal/tenant, and check audience, TTL, and anti-replay. A provider must never "promote" an arbitrary string into a trusted credential merely because it was placed in `OAuth2AuthorizeRequest`.

## 7. Declaring a Custom AuthorizationGrantType

Spring Security uses `AuthorizationGrantType` to represent the `grant_type` value:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;

public final class WorkloadTicketGrant {
    private WorkloadTicketGrant() {}

    public static final AuthorizationGrantType TYPE =
        new AuthorizationGrantType(
            "urn:example:params:oauth:grant-type:workload-ticket"
        );
}
~~~

In a real deployment, use the exact grant URI **officially defined** by your Authorization Server—never copy the placeholder URI above into production.

### 7.1. Connecting the Grant Type to ClientRegistration

~~~java
ClientRegistration registration =
    ClientRegistration.withRegistrationId("reports-with-ticket")
        .clientId("reports-ticket-client")
        .clientSecret("runtime-secret-placeholder")
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(WorkloadTicketGrant.TYPE)
        .tokenUri("https://login.example.test/oauth2/token")
        .scope("reports.read")
        .build();
~~~

The client ID/secret here are only **illustrative fixtures**. In Spring Boot, registrations are typically loaded from configuration + secret stores rather than hard-coded for production.

## 8. Defining a Request Type for the Custom Grant

An `OAuth2AccessTokenResponseClient<T>` is parameterized by the grant request type. Creating a dedicated class helps the compiler and codebase distinguish your custom grant from `OAuth2ClientCredentialsGrantRequest` or `OAuth2RefreshTokenGrantRequest`.

~~~java
package com.example.oauth.custom;

import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.endpoint
    .AbstractOAuth2AuthorizationGrantRequest;

public final class WorkloadTicketGrantRequest
        extends AbstractOAuth2AuthorizationGrantRequest {

    private final String workloadTicket;

    public WorkloadTicketGrantRequest(
        ClientRegistration registration,
        String workloadTicket
    ) {
        super(WorkloadTicketGrant.TYPE, registration);

        if (workloadTicket == null || workloadTicket.isBlank()) {
            throw new IllegalArgumentException(
                "workloadTicket must not be blank"
            );
        }

        this.workloadTicket = workloadTicket;
    }

    public String getWorkloadTicket() {
        return workloadTicket;
    }
}
~~~

**Never override `toString()` to print the ticket**, never log the grant request object directly, and never include the ticket in exception messages.

### 8.1. A Request Type Is Not an HTTP Request

`WorkloadTicketGrantRequest` is a **domain object** for the token-response client. Another layer must still serialize it into a form-encoded HTTP POST to the token endpoint.

Do not confuse `OAuth2AuthorizeRequest` (input to the manager) with `WorkloadTicketGrantRequest` (input to the token-response client).

## 9. Token-Response Client: Exchanging the Grant Request for OAuth2AccessTokenResponse

Synchronous contract:

~~~java
import org.springframework.security.oauth2.client.endpoint
    .OAuth2AccessTokenResponseClient;

OAuth2AccessTokenResponseClient<WorkloadTicketGrantRequest>
~~~

An implementation must:

1. Obtain the token URI **strictly from a trusted `ClientRegistration`**, never from user input.
2. Send an HTTP POST with `application/x-www-form-urlencoded`.
3. Set `grant_type` to the custom URI.
4. Put the evidence into the `workload_ticket` parameter per contract.
5. Authenticate the client using the registered method (e.g., `client_secret_basic`, mTLS, or `private_key_jwt`).
6. Parse the token response into `OAuth2AccessTokenResponse`.
7. Map OAuth2 token error responses into exceptions preserving the exact error code.
8. Enforce timeouts, body size limits, bounded retries, and zero credential logging.

### 9.1. Illustrative HTTP Request

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <redacted-client-credentials>

grant_type=urn%3Aexample%3Aparams%3Aoauth%3Agrant-type%3Aworkload-ticket&workload_ticket=<url-encoded-ticket>
~~~

Illustrative token response:

~~~json
{
  "access_token": "EXAMPLE_AT",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "reports.read"
}
~~~

An Authorization Server might also return a `refresh_token` if the custom grant contract allows it. **Never assume** a refresh token is issued, or that refresh tokens work with this registration, unless agreed upon.

### 9.2. Separating the Protocol Adapter from HTTP Transport

A testable pattern separates:

~~~java
public interface WorkloadTicketTokenEndpoint {
    OAuth2AccessTokenResponse exchange(
        WorkloadTicketGrantRequest request
    );
}
~~~

and the adapter:

~~~java
public final class WorkloadTicketTokenResponseClient
        implements OAuth2AccessTokenResponseClient<
            WorkloadTicketGrantRequest> {

    private final WorkloadTicketTokenEndpoint endpoint;

    public WorkloadTicketTokenResponseClient(
        WorkloadTicketTokenEndpoint endpoint
    ) {
        this.endpoint = endpoint;
    }

    @Override
    public OAuth2AccessTokenResponse getTokenResponse(
        WorkloadTicketGrantRequest request
    ) {
        return endpoint.exchange(request);
    }
}
~~~

This is a **contract-execution adapter**, not a complete HTTP client. `WorkloadTicketTokenEndpoint` will have an implementation using `RestClient` (Spring Framework 6.1+) or your organization's approved HTTP stack, applying proper OAuth2 form conversion, client authentication, and error mapping.

**Benefit:** the provider stays decoupled from codecs/TLS/proxies, and unit tests can replace the endpoint with a fake without making network calls.

### 9.3. Do Not Mechanically Copy Another Grant's Token Client

A token client for `client_credentials` is built around `OAuth2ClientCredentialsGrantRequest`. If your grant requires its own `workload_ticket`, do not cast requests across types or sneakily overwrite `grant_type` after signing.

If the grant is effectively `client_credentials` plus an extra parameter, use **the standard token client's extension hooks**. Create a new request type only when the grant itself differs in nature.

## 10. Implementing the Custom Servlet Provider — The Core Part

This example uses:

- `WorkloadTicketGrant.TYPE` to match registrations.
- `TrustedTicketSupplier` to issue fresh evidence per policy.
- `OAuth2AccessTokenResponseClient<WorkloadTicketGrantRequest>` to execute the token exchange.
- `Clock` and `Duration clockSkew` to control reissuance timing.

~~~java
package com.example.oauth.custom;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;
import org.springframework.security.oauth2.client.endpoint
    .OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;
import org.springframework.security.oauth2.client.registration.ClientRegistration;

public final class WorkloadTicketAuthorizedClientProvider
        implements OAuth2AuthorizedClientProvider {

    private final TrustedTicketSupplier ticketSupplier;
    private final OAuth2AccessTokenResponseClient<
        WorkloadTicketGrantRequest> tokenClient;

    private Clock clock = Clock.systemUTC();
    private Duration clockSkew = Duration.ofSeconds(60);

    public WorkloadTicketAuthorizedClientProvider(
        TrustedTicketSupplier ticketSupplier,
        OAuth2AccessTokenResponseClient<
            WorkloadTicketGrantRequest> tokenClient
    ) {
        this.ticketSupplier =
            Objects.requireNonNull(ticketSupplier);
        this.tokenClient =
            Objects.requireNonNull(tokenClient);
    }

    public void setClock(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public void setClockSkew(Duration clockSkew) {
        if (clockSkew == null || clockSkew.isNegative()) {
            throw new IllegalArgumentException(
                "clockSkew must not be negative"
            );
        }
        this.clockSkew = clockSkew;
    }

    @Override
    public OAuth2AuthorizedClient authorize(
        OAuth2AuthorizationContext context
    ) {
        ClientRegistration registration =
            context.getClientRegistration();

        // 1. Grant mismatch: this provider does not handle it.
        if (!WorkloadTicketGrant.TYPE.equals(
            registration.getAuthorizationGrantType()
        )) {
            return null;
        }

        OAuth2AuthorizedClient existing =
            context.getAuthorizedClient();

        // 2. Existing token still valid long enough: do not reissue.
        if (existing != null &&
            !isExpiredOrNearExpiry(existing.getAccessToken())) {
            return null;
        }

        String principalName = context.getPrincipal().getName();
        if (principalName == null || principalName.isBlank()) {
            throw new IllegalArgumentException(
                "A trusted principal is required"
            );
        }

        // 3. Evidence issued by a trusted server-side source.
        String ticket = ticketSupplier.issueFor(
            registration.getRegistrationId(),
            principalName
        );

        // 4. Token exchange isolated inside the response client.
        WorkloadTicketGrantRequest grantRequest =
            new WorkloadTicketGrantRequest(registration, ticket);

        OAuth2AccessTokenResponse response =
            tokenClient.getTokenResponse(grantRequest);

        // 5. Build authorized client for the right registration/principal.
        return new OAuth2AuthorizedClient(
            registration,
            principalName,
            response.getAccessToken(),
            response.getRefreshToken()
        );
    }

    private boolean isExpiredOrNearExpiry(
        OAuth2AccessToken accessToken
    ) {
        Instant expiresAt = accessToken.getExpiresAt();

        // Without reliable expiry, avoid treating the token as infinite.
        if (expiresAt == null) {
            return true;
        }

        return !clock.instant().plus(clockSkew)
            .isBefore(expiresAt);
    }
}
~~~

**This is an illustrative provider showing reissuance via a fresh ticket.** Real systems must add error handling and controls for issuer, audience, token type, concurrency, metrics, and timeouts matching the contract.

### 10.1. Why Must AuthorizationGrantType Be Checked First?

A manager can be configured with multiple providers. If a custom provider ignores grant type, it could invoke the custom token endpoint even when the registration uses `authorization_code` or `client_credentials`.

~~~java
if (!WorkloadTicketGrant.TYPE.equals(
    registration.getAuthorizationGrantType())) {
    return null;
}
~~~

This is the **first branching gate**.

### 10.2. Why Return null When an Existing Authorized Client Is Still Valid?

The manager typically loads any saved authorized client before calling the provider. If the token has not reached its reissuance window:

~~~java
if (existing != null && !isExpiredOrNearExpiry(...)) {
    return null;
}
~~~

A provider should not request a new ticket/token on **every request**. Continuous token issuance causes:

- Unnecessary load on the token endpoint.
- Increased cryptographic signing/verification overhead.
- Write races across concurrent storage updates.
- Rate limiting and cascading failures if the IdP slows down.

`null` means **the provider did not perform a new authorization on this call**; the manager may retain the existing authorized client per its contract.

### 10.3. Clock Skew Must Be Controlled

With a token expiring at `10:05:00Z` and a 60-second clock skew, the provider can request a new token starting at `10:04:00Z`.

If a token's lifetime is only 90 seconds yet skew is 80 seconds, the token is treated as "near expiry" far too early. Base this on latency, system clock stability, and actual expiry semantics.

Do not alter `expiresAt` in the authorized-client store to force refreshes; adjust the provider policy instead.

### 10.4. Tickets Must Be Fresh and Scoped

`ticketSupplier.issueFor(...)` must mint a ticket for that specific workload and instant, never load an eternal ticket from static config.

**A ticket valid for workload A does not prove workload B is allowed to use it.** In multi-tenant systems, enforce tenant binding and worker permissions at the Authorization Server level.

### 10.5. Never Swallow Exceptions and Return an Old Token

Wrong:

~~~java
try {
    return tokenClient.getTokenResponse(grantRequest);
} catch (RuntimeException ex) {
    return oldAuthorizedClient; // Wrong return type and wrong policy.
}
~~~

Never "fall back" to success when a grant failed; the provider must surface the proper exception for the manager/consumer to handle. When the token endpoint rejects a ticket, returning an expired old authorized client hides the failure and causes repeated 401s.

## 11. What If the Token Endpoint Does Not Return a Bearer Token?

If the application calls the Resource Server with:

~~~http
Authorization: Bearer <access-token>
~~~

then the response must be compatible with `Bearer` tokens and the Resource Server's expectations. A token response like:

~~~json
{
  "access_token": "opaque-value",
  "token_type": "Bearer",
  "expires_in": 300
}
~~~

can be represented as:

~~~java
OAuth2AccessTokenResponse response =
    OAuth2AccessTokenResponse.withToken("opaque-value")
        .tokenType(OAuth2AccessToken.TokenType.BEARER)
        .expiresIn(300)
        .scopes(Set.of("reports.read"))
        .build();
~~~

This only shows **how to construct a fixture response**. For live responses, verify:

- `access_token` is present and non-empty.
- `token_type` is supported.
- `expires_in` is valid per contract.
- Scopes reflect the **actual response**, never self-escalated.
- Extra parameters are handled per policy.

**Do not treat every `token_type` value as Bearer** merely because the downstream client calls `setBearerAuth()`. If the Authorization Server requires proof-of-possession or custom token binding, implement the matching integration.

## 12. Token Endpoint Errors Must Preserve OAuth2 Semantics

Example where the token endpoint rejects a ticket:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant",
  "error_description": "Workload ticket expired"
}
~~~

A solid implementation translates errors into `OAuth2AuthorizationException` or a matching OAuth2 exception, preserving the **error code** without leaking the ticket.

Errors to distinguish:

| Error | Common Meaning | Resolution |
|---|---|---|
| `unsupported_grant_type` | AS does not accept the custom grant URI | Verify grant/version contract |
| `invalid_grant` | Ticket invalid, expired, wrong audience, or already used | May issue a new ticket per policy; do not retry blindly |
| `invalid_client` | Wrong client authentication / mTLS failure | Fix credentials/configuration |
| `unauthorized_client` | Client not permitted to use the custom grant | Fix registration/AS policy |
| `invalid_scope` | Requested scope disallowed | Fix configuration/policy; do not retry same request |
| HTTP 429 | Token endpoint rate limiting | Back off; avoid request storms |
| HTTP 500/503/timeout | Transport/AS outage | Bounded retries with timeouts/deadlines |
| Malformed JSON/schema response | Protocol contract mismatch | Fail closed; monitor integration |

### 12.1. Do Not Arbitrarily Retry One-Time Tickets

If the ticket is a **one-time proof**:

~~~text
Client sends ticket T1 to AS
AS consumes T1 and issues token
Network fails before client receives response
Client retries same T1 -> invalid_grant
~~~

You cannot assume a ticket remained unused simply because an HTTP client timed out. To retry, **mint a fresh ticket if contract permits**, re-verify state, or design idempotency at the token endpoint. Never automatically loop the exact same form request infinitely.

### 12.2. HTTP Error Mapping in RestClient

If you write a custom `RestClient` token-response adapter, `retrieve()` normally throws an HTTP status exception on 4xx/5xx responses. If you let the raw transport exception propagate unchanged, the manager's failure handler may **fail to see `invalid_grant` as an OAuth2 error code**.

Therefore, the token client must **safely parse OAuth2 error responses** (with bounds), map them into the proper exception type, and preserve the error code for policy handling. Never log raw bodies that may contain credentials.

## 13. Configuring ClientRegistration in Spring Boot

In `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-with-ticket:
            provider: company
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: "urn:example:params:oauth:grant-type:workload-ticket"
            scope:
              - reports.read
        provider:
          company:
            token-uri: https://login.example.test/oauth2/token
~~~

If the provider supports discovery, you can choose `issuer-uri` per contract. When configuring the token URI manually, ensure the endpoint uses **HTTPS** and that client authentication and scopes are registered.

**Do not confuse** YAML `authorization-grant-type` with automatically activating a provider. YAML only constructs the `ClientRegistration`; you must still **wire the custom provider into the manager**.

### 13.1. Never Hard-Code Secrets or Tickets

`REPORTS_CLIENT_SECRET` is a placeholder populated from a secret manager/runtime. Tickets must be issued dynamically by an authenticated source, never committed into YAML/Git:

~~~yaml
# Never do this:
custom:
  workload-ticket: "a-real-long-lived-secret"
~~~

Expiring, anti-replay tickets lose their security value if reused like static passwords.

## 14. Connecting the Provider to AuthorizedClientServiceOAuth2AuthorizedClientManager

For **Servlet background workers/queue jobs or apps without an HTTP request**, the right manager is:

~~~java
org.springframework.security.oauth2.client
    .AuthorizedClientServiceOAuth2AuthorizedClientManager
~~~

It requires no `HttpServletRequest`.

~~~java
package com.example.oauth.custom;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client
    .AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository;

@Configuration
public class CustomGrantManagerConfig {

    @Bean("workloadTicketManager")
    OAuth2AuthorizedClientManager workloadTicketManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService authorizedClients,
        TrustedTicketSupplier ticketSupplier,
        OAuth2AccessTokenResponseClient<WorkloadTicketGrantRequest> tokenClient
    ) {
        OAuth2AuthorizedClientProvider custom =
            new WorkloadTicketAuthorizedClientProvider(
                ticketSupplier, tokenClient
            );

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients
            );

        manager.setAuthorizedClientProvider(custom);
        return manager;
    }
}
~~~

In the code above, `tokenClient` is injected by its matching generic type. If the system defines multiple `OAuth2AccessTokenResponseClient` beans, use explicit qualifiers/bean names to avoid picking up another grant's token client.

### 14.1. What Does the Manager Handle?

Logically:

~~~text
manager.authorize()
  -> look up registration
  -> load authorized client by registrationId + principalName
  -> build OAuth2AuthorizationContext
  -> customProvider.authorize(context)
  -> if new authorized client returned: save via success handler
  -> return authorized client to caller
~~~

**The provider does not need to call `authorizedClients.saveAuthorizedClient(...)` manually** on the normal happy path. That belongs to the manager/success handler. Saving directly inside the provider can cause duplicate writes or persist tokens before lifecycle policies run.

### 14.2. When to Use DefaultOAuth2AuthorizedClientManager?

Inside a **Servlet web request** with an `Authentication` and HTTP request/response, you typically use:

~~~java
DefaultOAuth2AuthorizedClientManager manager =
    new DefaultOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        oauth2AuthorizedClientRepository
    );

manager.setAuthorizedClientProvider(customProvider);
~~~

The difference lies in **storage/context**, not the nature of the custom provider. The web manager coordinates `OAuth2AuthorizedClientRepository` and request context; the service manager coordinates `OAuth2AuthorizedClientService`.

Do not use `DefaultOAuth2AuthorizedClientManager` inside a scheduled job with no Servlet request and expect it to locate an `HttpServletRequest`.

## 15. Composing Custom Providers with Standard Providers

An application may simultaneously use:

- OIDC login via authorization code.
- Refresh tokens for users.
- Client credentials for machine clients.
- Workload Ticket Grant for a specialized registration.

You can compose providers:

~~~java
import org.springframework.security.oauth2.client
    .DelegatingOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientProviderBuilder;

OAuth2AuthorizedClientProvider standard =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();

OAuth2AuthorizedClientProvider combined =
    new DelegatingOAuth2AuthorizedClientProvider(
        standard,
        customProvider
    );

manager.setAuthorizedClientProvider(combined);
~~~

This **snippet illustrates configuring a manager**; `manager` and `customProvider` must be defined in the application. Avoid creating unnecessary duplicate managers with conflicting bean names.

### 15.1. The Provider Chain Does Not Change a Registration's Grant Type

Registrations:

~~~text
reports-with-ticket -> workload-ticket grant
reports-service     -> client_credentials
company-login       -> authorization_code
~~~

are evaluated by each provider according to its grant and conditions. Adding a custom provider to the chain **does not turn `client_credentials` into a workload ticket grant**.

### 15.2. Provider Order Matters

Order matters when multiple providers can handle an existing client. For example, a registration might hold a refresh token while a custom provider can also reissue a token via a ticket.

If `refreshToken()` runs first, it can refresh the token when near expiry; if the custom provider runs first and immediately mints a new token, the refresh provider never gets a chance to run.

**Never configure providers with overlapping grant rules without defining precedence.** If the custom grant should not use refresh tokens, state that clearly in the provider policy and manager chain instead of relying on accidental ordering.

## 16. Calling the Manager in a Background Job

A service job can invoke:

~~~java
package com.example.reports;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class ReportsGateway {

    private final OAuth2AuthorizedClientManager manager;
    private final RestClient reportsApi;

    public ReportsGateway(
        @Qualifier("workloadTicketManager")
        OAuth2AuthorizedClientManager manager,
        RestClient.Builder restClientBuilder
    ) {
        this.manager = manager;
        this.reportsApi = restClientBuilder
            .baseUrl("https://reports.example.test")
            .build();
    }

    public String fetchDailySummary() {
        OAuth2AuthorizeRequest authorization =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reports-with-ticket")
                .principal("reports-worker")
                .build();

        OAuth2AuthorizedClient client =
            manager.authorize(authorization);

        if (client == null) {
            throw new IllegalStateException(
                "No authorized client for reports-with-ticket"
            );
        }

        return reportsApi.get()
            .uri("/api/daily-summary")
            .headers(headers -> headers.setBearerAuth(
                client.getAccessToken().getTokenValue()
            ))
            .retrieve()
            .body(String.class);
    }
}
~~~

`reports-worker` is a **service principal name for storage**, not a logged-in employee's username. `RestClient.Builder` should include timeouts/TLS/proxy settings and environment-managed URLs; the code is simplified to highlight manager usage.

**Never take an arbitrary client registration ID or principal name from a browser request** and call the manager with backend privileges. That creates a confused deputy vulnerability capable of retrieving another account's tokens.

## 17. Does HTTP Client Integration Automatically Know Custom Grants?

`RestClient` or `WebClient` does not need to understand how `workload_ticket` is built when integrated with **a manager containing the custom provider**.

~~~text
RestClient/WebClient
    -> manager.authorize(...)
    -> custom provider
    -> token response client
    -> authorized client
    -> Bearer header to Resource Server
~~~

However, if you call `RestClient.create(...)` or `WebClient.create(...)` without wiring OAuth2 integration, the HTTP client **will not invoke the manager automatically**.

### 17.1. RestClient OAuth2 Interceptor (Spring Security 6.4+)

~~~java
OAuth2ClientHttpRequestInterceptor oauth2 =
    new OAuth2ClientHttpRequestInterceptor(
        workloadTicketManager
    );

RestClient reportsApi = RestClient.builder()
    .baseUrl("https://reports.example.test")
    .requestInterceptor(oauth2)
    .build();
~~~

This assumes `workloadTicketManager` is configured and request attributes/principal context provide sufficient information. In background jobs, **explicit `authorize()` calls** as in Section 16 can be easier to control, because default interceptors often resolve principals from HTTP requests/security context unless configured otherwise.

### 17.2. Choosing the Registration Explicitly

In Servlet `RestClient` integration, you can use the request attribute resolver:

~~~java
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver.clientRegistrationId;

String result = reportsApi.get()
    .uri("/api/daily-summary")
    .attributes(clientRegistrationId("reports-with-ticket"))
    .retrieve()
    .body(String.class);
~~~

In a background job lacking a user `Authentication`, provide a proper **principal context** or invoke the manager directly; setting only the registration attribute may not suffice for every interceptor setup.

**Never use a single default authorized client across all outgoing HTTP requests** in a system calling multiple APIs/tenants. Tokens must never be sent to hosts outside their intended audience/trust boundary.

## 18. Storing Authorized Clients Without Exposing Tickets

The manager uses:

~~~java
OAuth2AuthorizedClientService
~~~

or:

~~~java
OAuth2AuthorizedClientRepository
~~~

depending on context. An authorized client is typically keyed by:

~~~text
(clientRegistrationId, principalName)
("reports-with-ticket", "reports-worker")
~~~

**There is no need to store the workload ticket inside `OAuth2AuthorizedClient`**. The ticket is short-lived proof used to obtain the access token; if tracing is needed, store only a **safely sanitized ticket ID**, never the raw ticket.

### 18.1. Tokens at Rest

Access tokens and refresh tokens (if issued) are credentials. In persistent stores, ensure:

- Restricted read/write permissions.
- Encryption-at-rest and key management if required by policy.
- Appropriate deletion/retention rules.
- Zero logging of raw tokens or tickets.
- Never returning credentials to frontends via debug APIs.
- Protection of backups and access logs.

### 18.2. Stable Principal Names

Avoid using:

~~~java
.principal(UUID.randomUUID().toString())
~~~

per request if it is the same service job and you want to cache/reuse the authorized client. Each new `principalName` creates a new storage key.

Conversely, **never share one generic `principalName`** across different tenants or privilege levels when doing so breaks isolation. Choose keys aligned with your designed security boundaries.

## 19. Manager Success/Failure Handlers

The provider returns the authorized client, yet **the manager** orchestrates storage and lifecycle.

Example flow:

~~~text
Provider authorize:
  -> token exchange succeeds
  -> return new OAuth2AuthorizedClient

Manager:
  -> success handler saves authorized client
  -> return token to consumer
~~~

If a custom manager replaces the default success handler, make sure **the new token is saved**. Otherwise, every call may request a new token even while the current access token is still valid.

### 19.1. Failure Handler Must Understand Error Codes

If the token endpoint returns `invalid_grant`, the manager may evict the old authorized client under a given policy. Still, never wipe tokens for all users/registrations due to one isolated failure.

For a custom grant:

1. Identify which error codes prove the **existing authorized client is no longer usable**.
2. Identify which errors mean **the new ticket** was rejected while an existing access token may still be valid.
3. Scope cleanup policies to the exact registration/principal.
4. Avoid deleting a newer token during a race between refresh/reissue and an error handler.
5. Distinguish token endpoint errors from Resource Server errors.

**Do not assume "`invalid_grant` always means the old access token was revoked."** It may simply mean **the current ticket is invalid**. Whether to delete or keep the existing authorized client must follow the extension grant contract and token state.

## 20. An Unexpired Token Does Not Guarantee Resource Server Acceptance

An access token may have `expiresAt` in the future yet still be rejected by the Reports API:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Because:

- The token was revoked.
- The audience does not match.
- The issuer or signature is invalid.
- Token binding/confirmation is missing.
- The Resource Server enforces a stricter policy.

The provider only sees token metadata on the OAuth2 Client side. The Resource Server independently decides whether a token is acceptable for that request.

Upon receiving `invalid_token`, the application may evict the stale authorized client per policy and call the manager for a fresh token, yet **must not retry infinitely** with the same grant/configuration.

### 20.1. HTTP 403 insufficient_scope

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

usually means the token may be valid, yet lacks required permissions. Requesting a new token with the same grant and scopes **will not escalate privileges**. Fix the client registration, consent/AS policy, or business authorization appropriately.

## 21. Crucially: A Custom Grant Is Part of the Security Architecture

A custom grant expands the attack surface. Your threat model must cover:

| Risk | Mitigation |
|---|---|
| Ticket copied and replayed | Short TTL, nonce/jti, one-time semantics, replay cache at AS |
| Ticket carries wrong audience | AS enforces exact audience; client never overrides token URI dynamically |
| Workload claims another user's subject | Issuer authenticates workload; AS validates mapping and delegation |
| Client secret leaked | Secret store, mTLS/`private_key_jwt` where appropriate, rotation |
| Ticket logged | Never log token request payloads/headers/bodies |
| Proxy/TLS flaw | HTTPS, valid truststore/CA, never disable validation |
| Overly broad scopes issued | Least privilege, scope allowlist, tenant/resource authorization |
| Cross-tenant token confusion | Isolate registrations, principals, storage, and security policies |
| Retrying one-time tickets | Conditional retries; never replay already-consumed credentials |
| Token response injection | Trust only TLS endpoints; strictly parse `token_type`/expiry/response |
| SSRF via dynamic token URI | Server-side configured URI, never taken from untrusted requests |
| Rate-limit bypass | Backoff, quotas, concurrency limits |

**The security of a custom grant resides primarily at the Authorization Server**: validating tickets, issuers, audiences, expiries, replay, and policies before minting tokens. The client-side provider is only one part of the design.

## 22. User-Delegated Scenarios: Custom Grants Must Not Bypass OIDC Authority

If the goal is to **call an API on behalf of an OIDC-authenticated user**, that is completely different from a workload ticket for machine identity.

Unsafe example:

~~~text
Browser sends ?sub=admin
   -> Portal mints ticket for admin
   -> AS issues access token with admin rights
~~~

If a custom grant supports delegation, you need:

- A trusted principal from a verified `Authentication`.
- Explicit consent or delegation policy.
- Binding between the subject token/ticket and the OAuth client.
- Tenant, audience, and scope validation.
- Proper logging/auditing.
- Never using `email` as an immutable identity key when OIDC provides `(iss, sub)`.

A service principal in `OAuth2AuthorizeRequest` **is only an input key to look up an authorized client**, not proof that the AS will treat the token as belonging to that person. Never grant permissions based on a caller-supplied principal string.

## 23. When Should RFC 8693 Token Exchange Be Used Instead of a Proprietary Grant?

When the problem is **exchanging an existing security token for another token** to call another API, look at **RFC 8693 Token Exchange**:

~~~text
grant_type = urn:ietf:params:oauth:grant-type:token-exchange
subject_token = ...
subject_token_type = ...
requested_token_type = ...
audience/resource = ...
~~~

Do not invent a "look-alike" grant with similar parameters without analyzing:

- Who can the subject token be delegated to?
- Does an actor token represent an intermediary service?
- Is impersonation or delegation required?
- Which audience/scopes does the output token need?
- Does the Authorization Server support token exchange?

**Depending on your Spring Security version**, a provider/token client for token exchange or matching extension hooks may already exist. Check the available library first before writing custom code. This lesson's goal is understanding the provider SPI—not advocating rewriting standards needlessly.

## 24. Reactive: Same Concept, Different Interface and Execution Model

In **Spring WebFlux**, the corresponding provider is:

~~~java
org.springframework.security.oauth2.client
    .ReactiveOAuth2AuthorizedClientProvider
~~~

with contract:

~~~java
Mono<OAuth2AuthorizedClient> authorize(
    OAuth2AuthorizationContext context
);
~~~

Comparison:

| Criterion | Servlet / Synchronous | Reactive / WebFlux |
|---|---|---|
| Provider interface | `OAuth2AuthorizedClientProvider` | `ReactiveOAuth2AuthorizedClientProvider` |
| Not-applicable result | `null` | `Mono.empty()` |
| Token response client | `OAuth2AccessTokenResponseClient<T>` | `ReactiveOAuth2AccessTokenResponseClient<T>` |
| Manager | `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| User web request manager | `DefaultOAuth2AuthorizedClientManager` | `DefaultReactiveOAuth2AuthorizedClientManager` |
| Background service manager | `AuthorizedClientServiceOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| Token I/O | May block with `RestClient` | Should be non-blocking with `WebClient` |

**Never pass a synchronous provider into a Reactive manager** via casting or calling `.block()` on an event loop. For WebFlux, design a dedicated reactive implementation.

## 25. Designing a Reactive WorkloadTicket Provider

Suppose there is an asynchronous ticket source:

~~~java
public interface ReactiveTrustedTicketSupplier {
    Mono<String> issueFor(
        String clientRegistrationId,
        String trustedPrincipalName
    );
}
~~~

And a reactive token response client:

~~~java
ReactiveOAuth2AccessTokenResponseClient<
    WorkloadTicketGrantRequest>
~~~

The provider can be written as:

~~~java
package com.example.oauth.custom;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.endpoint
    .ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import reactor.core.publisher.Mono;

public final class ReactiveWorkloadTicketProvider
        implements ReactiveOAuth2AuthorizedClientProvider {

    private final ReactiveTrustedTicketSupplier ticketSupplier;
    private final ReactiveOAuth2AccessTokenResponseClient<
        WorkloadTicketGrantRequest> tokenClient;
    private final Clock clock;
    private final Duration clockSkew;

    public ReactiveWorkloadTicketProvider(
        ReactiveTrustedTicketSupplier ticketSupplier,
        ReactiveOAuth2AccessTokenResponseClient<
            WorkloadTicketGrantRequest> tokenClient,
        Clock clock,
        Duration clockSkew
    ) {
        this.ticketSupplier = ticketSupplier;
        this.tokenClient = tokenClient;
        this.clock = clock;
        this.clockSkew = clockSkew;
    }

    @Override
    public Mono<OAuth2AuthorizedClient> authorize(
        OAuth2AuthorizationContext context
    ) {
        return Mono.defer(() -> {
            ClientRegistration registration =
                context.getClientRegistration();

            if (!WorkloadTicketGrant.TYPE.equals(
                registration.getAuthorizationGrantType())) {
                return Mono.empty();
            }

            OAuth2AuthorizedClient existing =
                context.getAuthorizedClient();

            if (existing != null &&
                !isNearExpiry(existing.getAccessToken())) {
                return Mono.empty();
            }

            String principalName = context.getPrincipal().getName();

            return ticketSupplier.issueFor(
                    registration.getRegistrationId(),
                    principalName
                )
                .flatMap(ticket -> tokenClient.getTokenResponse(
                    new WorkloadTicketGrantRequest(
                        registration, ticket
                    )
                ))
                .map(response -> new OAuth2AuthorizedClient(
                    registration,
                    principalName,
                    response.getAccessToken(),
                    response.getRefreshToken()
                ));
        });
    }

    private boolean isNearExpiry(OAuth2AccessToken token) {
        Instant expiresAt = token.getExpiresAt();
        return expiresAt == null ||
            !clock.instant().plus(clockSkew).isBefore(expiresAt);
    }
}
~~~

This illustrates the **Reactive SPI**; production code must add input validation, exception mapping, metrics, and strict token response validation per policy. Notice how:

- `Mono.defer` avoids minting a ticket before subscription.
- Grant mismatch or valid unexpired token → `Mono.empty()`.
- `ticketSupplier.issueFor(...)` returns a `Mono` without blocking the event loop.
- `flatMap` calls the token endpoint once a ticket is ready.
- `map` constructs the new authorized client.

### 25.1. What If the Ticket Source Is Blocking?

If the real ticket issuer library performs **blocking I/O**, do not invoke it directly on the Reactor event loop. Wrap it with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` after sizing threads and load, or better yet use a true reactive HTTP client.

Never call `.block()` inside `ReactiveOAuth2AuthorizedClientProvider.authorize(...)`.

### 25.2. Subscription and Cancellation

Publishers are lazy:

~~~java
Mono<OAuth2AuthorizedClient> result =
    reactiveProvider.authorize(context);
~~~

Creating the `Mono` does not mean the token endpoint has been called. The manager/WebClient/scheduler subscribes to it. If a request is canceled, upstream signals may cancel; **cancellation does not guarantee the ticket was not already consumed** at the Authorization Server.

## 26. Attaching the Custom Provider to a Reactive Manager

For a WebFlux/Reactive background worker:

~~~java
package com.example.oauth.custom;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client
    .AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
    .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
    .ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration
    .ReactiveClientRegistrationRepository;

@Configuration
public class ReactiveCustomGrantConfig {

    @Bean("reactiveWorkloadTicketManager")
    ReactiveOAuth2AuthorizedClientManager manager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService authorizedClients,
        ReactiveWorkloadTicketProvider customProvider
    ) {
        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClients
            );

        manager.setAuthorizedClientProvider(customProvider);
        return manager;
    }
}
~~~

This is a **service-based reactive manager**, requiring no `ServerWebExchange`, suitable for scheduled jobs.

When the custom grant runs inside a **WebFlux HTTP user request**, the corresponding manager may be `DefaultReactiveOAuth2AuthorizedClientManager` with `ServerOAuth2AuthorizedClientRepository`; provider attachment stays similar while storage/context differ.

### 26.1. A Reactive WebClient Step

~~~java
Mono<String> data = manager.authorize(
        OAuth2AuthorizeRequest
            .withClientRegistrationId("reports-with-ticket")
            .principal("reports-worker")
            .build()
    )
    .switchIfEmpty(Mono.error(
        new IllegalStateException("No authorized client")
    ))
    .flatMap(client -> reportsWebClient.get()
        .uri("/api/daily-summary")
        .headers(headers -> headers.setBearerAuth(
            client.getAccessToken().getTokenValue()
        ))
        .retrieve()
        .bodyToMono(String.class)
    );
~~~

Do not call `.subscribe()` and discard the result when the application must track job status or errors. Return the `Mono` to the framework or subscription-managed scheduler.

## 27. Concurrency: Multiple Requests Seeking Tokens Simultaneously

Suppose two threads/jobs simultaneously fetch the authorized client `reports-with-ticket / reports-worker`:

~~~mermaid
sequenceDiagram
    participant A as Job A
    participant B as Job B
    participant Store as Authorized Client Store
    participant Ticket as Ticket Issuer
    participant AS as Authorization Server

    A->>Store: load client (AT-1 near expiry)
    B->>Store: load client (AT-1 near expiry)
    A->>Ticket: issue T2
    B->>Ticket: issue T3
    Ticket-->>A: T2
    Ticket-->>B: T3
    A->>AS: custom grant T2
    B->>AS: custom grant T3
    AS-->>A: AT-2
    AS-->>B: AT-3
    A->>Store: save AT-2
    B->>Store: save AT-3
~~~

Both new tokens may be valid, yet this causes:

- Unnecessary tickets minted.
- Duplicate token requests.
- Cache write races.
- Higher load on the Authorization Server.
- Harder diagnostics as tokens churn continuously.

### 27.1. Are Single-Flight or Locks Needed?

Depends on throughput and policy:

- A simple single worker may not need complex locking.
- Multiple pods may need **distributed single-flight**, optimistic concurrency, or locks keyed by `(registrationId, principalName)`.
- Locking only coordinates token acquisition; it does not make jobs **exactly-once**.
- Never lock across all users/tenants just because one registration needs a token.

### 27.2. A Failed Refresh/Reissue Can Evict a Newer Token

If Job A obtains AT-2 first, while Job B fails and its failure handler deletes the authorized client for that registration/principal **after** AT-2 was saved, B can wipe out the fresh token.

Under high concurrency or strict token binding, consider **version/generation-aware cleanup** and test race conditions. Standard repositories/services do not necessarily provide compare-and-delete automatically.

## 28. Token Cache, expiresAt, and Reissuance Policy

A provider needs an explicit policy for existing tokens:

| State | Recommended Policy |
|---|---|
| No authorized client | Issue new token if grant and evidence are valid |
| Existing access token valid well past skew | Return `null` / `Mono.empty()` to retain token |
| Token nearing expiry | Issue new token per clock skew |
| Token expired | Issue new token if ticket service/AS are ready |
| Token declared invalid by Resource Server | Controlled cleanup, then reauthorize |
| Token response lacks reliable `expiresAt` | Fail closed or conservative reissue policy; never treat as infinite |
| Token lacks scope/audience | Fix `ClientRegistration`/AS policy; never self-escalate |

**Expiry metadata does not guarantee the token has not been revoked.** The Resource Server retains the right to reject tokens whose issuer/audience/signature/policy does not match.

### 28.1. Do Not Mint a Ticket Before Confirming a New Token Is Needed

Place `ticketSupplier.issueFor(...)` **after** checking the existing authorized client to avoid minting unused tickets. With one-time tickets, minting early and discarding also complicates auditing and capacity planning.

## 29. Timeouts, Retries, and Circuit Breakers

The token endpoint is a critical dependency. When the IdP slows down, hundreds of waiting requests can bring down the Portal.

Apply:

- **TCP connect timeout**.
- **Response/read timeout**.
- **Overall deadline** for an authorization attempt.
- **Rate limits/bulkheads** on token requests.
- **Backoff and jitter** for appropriate transient errors.
- **Circuit breakers** if architecture and policy allow.
- Bounded retry counts never exceeding caller SLOs.

### 29.1. Do Not Retry Every Error

| Error | Retry? |
|---|---|
| HTTP 503, 429 from AS | Possibly, respecting backoff/`Retry-After` and budget |
| `invalid_client` | No; fix client auth |
| `unauthorized_client` | No; fix AS policy |
| `invalid_scope` | No; fix scopes |
| `invalid_grant` with one-time ticket | Never blindly retry the same ticket |
| Invalid TLS certificate | No; fix trust/mTLS |
| Network timeout after sending ticket | Outcome unknown; requires policy/idempotency |

**Retries in the token-response client and retries in the job/WebClient must not multiply unboundedly.** A single job could multiply token requests if both layers retry.

## 30. Observability and Safe Logging

A new custom grant needs metrics to verify it works:

| Event / Metric | Meaning |
|---|---|
| Grant selected | Provider decided to handle the matching grant |
| Grant skipped | Not applicable due to different registration or valid existing token |
| Ticket issuance attempted | Trusted Ticket Supplier was invoked |
| Ticket issuance failure | Ticket source errored or refused |
| Token exchange attempted | HTTP POST sent to token endpoint |
| Token exchange success/failure | Grant succeeded or was rejected |
| Authorized client saved/loaded | Manager/storage operational |
| Token reissue count | Detects excessive token reissuance |
| Client credentials / AS error code | Separates configuration bugs from transient failures |
| Resource Server 401/403 | Separates invalid tokens from missing permissions |
| Principal/registration mismatch | Configuration or security warning sign |

**Never log**:

~~~text
workload_ticket=<real-ticket>
access_token=<real-token>
refresh_token=<real-refresh-token>
client_secret=<real-client-secret>
Authorization: Bearer <real-token>
Authorization: Basic <real-secret>
~~~

Never put tokens or tickets into OpenTelemetry span attributes, metric labels, or exception messages. Log only sanitized metadata, route templates, allowlisted registration IDs, error codes, and correlation IDs.

## 31. Testing the Provider: Separating Logic from the HTTP Token Endpoint

You do not need a live Authorization Server to test a custom provider. Essential tests:

1. Registration with a different grant type → `authorize()` returns `null`.
2. Matching registration with no token yet → supplier is called and token response client returns AT.
3. Token still valid well past skew → ticket is not requested and token endpoint is not called.
4. Token within clock skew → token is reissued.
5. Valid context `principalName` → returned authorized client preserves that principal.
6. Token client returns OAuth2 error → provider propagates error, never fakes success.
7. Ticket supplier fails → token endpoint is never called.
8. Invalid response → fail closed, never persist bad credentials.
9. Two registrations/tenants → tickets or tokens never leak across boundaries.
10. Concurrent requests → verify race/reissue/store behavior per policy.

### 31.1. Unit Test with a Fake Token Client

Java/JUnit 5 snippet:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.endpoint
    .OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

import static org.junit.jupiter.api.Assertions.*;

class WorkloadTicketProviderTest {

    @Test
    void customGrantCreatesAuthorizedClientForTrustedPrincipal() {
        ClientRegistration registration =
            ClientRegistration.withRegistrationId("reports-with-ticket")
                .clientId("test-client")
                .clientSecret("test-secret")
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(WorkloadTicketGrant.TYPE)
                .tokenUri("https://login.example.test/token")
                .scope("reports.read")
                .build();

        OAuth2AuthorizationContext context =
            OAuth2AuthorizationContext
                .withClientRegistration(registration)
                .principal(new TestingAuthenticationToken(
                    "reports-worker", "ignored", "ROLE_SERVICE"))
                .build();

        AtomicInteger tickets = new AtomicInteger();
        TrustedTicketSupplier supplier = (id, principal) -> {
            tickets.incrementAndGet();
            assertEquals("reports-with-ticket", id);
            assertEquals("reports-worker", principal);
            return "FAKE_SIGNED_TICKET";
        };

        OAuth2AccessTokenResponseClient<WorkloadTicketGrantRequest> fake =
            request -> {
                assertEquals("FAKE_SIGNED_TICKET",
                    request.getWorkloadTicket());
                return OAuth2AccessTokenResponse
                    .withToken("FAKE_ACCESS_TOKEN")
                    .tokenType(OAuth2AccessToken.TokenType.BEARER)
                    .expiresIn(300)
                    .scopes(Set.of("reports.read"))
                    .build();
            };

        WorkloadTicketAuthorizedClientProvider provider =
            new WorkloadTicketAuthorizedClientProvider(supplier, fake);
        provider.setClock(Clock.fixed(
            Instant.parse("2026-11-16T00:00:00Z"),
            ZoneOffset.UTC
        ));
        provider.setClockSkew(Duration.ofSeconds(30));

        OAuth2AuthorizedClient result =
            provider.authorize(context);

        assertNotNull(result);
        assertEquals("reports-worker", result.getPrincipalName());
        assertEquals("reports-with-ticket",
            result.getClientRegistration().getRegistrationId());
        assertEquals("FAKE_ACCESS_TOKEN",
            result.getAccessToken().getTokenValue());
        assertEquals(1, tickets.get());
    }
}
~~~

This unit test checks **provider logic**—it does not test HTTP token requests, OAuth2 client authentication, ticket signatures, or the Resource Server. Integration tests must verify the token client sends the right `grant_type`, parameter encoding, and OAuth2 error handling against a mock server.

### 31.2. Test That Valid Unexpired Tokens Do Not Call the Supplier

Given a context with an existing client holding an access token valid for many minutes, a spy/fake supplier should record:

~~~text
provider.authorize(contextWithFreshToken) -> null
ticketSupplier calls = 0
tokenResponseClient calls = 0
~~~

For a token expiring within the clock skew window:

~~~text
provider.authorize(contextNearExpiry) -> new OAuth2AuthorizedClient
ticketSupplier calls = 1
tokenResponseClient calls = 1
~~~

`contextWithFreshToken` and `contextNearExpiry` here are test fixtures you create; they are not built-in Spring Security classes or variables.

### 31.3. Test That Failures Do Not Cause the Manager to Store Bad Tokens

Simulate `OAuth2AuthorizationException` from the token client. Verify:

- The provider does not return a dummy authorized client.
- The manager's failure handler is invoked per contract.
- Storage cleanup runs only for policy-permitted errors.
- No raw tickets are logged.
- `invalid_client` or consumed-ticket errors are never retried infinitely.

## 32. Testing the Reactive Provider with StepVerifier

In Reactive, test three signals:

~~~text
Mono.empty()       -> provider does not apply
Mono.just(client)  -> token exchange succeeded
Mono.error(error)  -> grant failed
~~~

Example test with a fake supplier/client:

~~~java
ReactiveTrustedTicketSupplier ticketSupplier =
    (registrationId, principalName) ->
        Mono.just("FAKE_SIGNED_TICKET");

ReactiveOAuth2AccessTokenResponseClient<WorkloadTicketGrantRequest>
    tokenClient = request -> Mono.just(
        OAuth2AccessTokenResponse
            .withToken("FAKE_ACCESS_TOKEN")
            .tokenType(OAuth2AccessToken.TokenType.BEARER)
            .expiresIn(300)
            .build()
    );

ReactiveWorkloadTicketProvider provider =
    new ReactiveWorkloadTicketProvider(
        ticketSupplier,
        tokenClient,
        Clock.systemUTC(),
        Duration.ofSeconds(60)
    );

StepVerifier.create(provider.authorize(context))
    .assertNext(client -> {
        assertEquals("FAKE_ACCESS_TOKEN",
            client.getAccessToken().getTokenValue());
    })
    .verifyComplete();
~~~

`context` is a fixture built from `OAuth2AuthorizationContext` with the custom-grant registration and a valid principal. For a non-matching grant:

~~~java
StepVerifier.create(provider.authorize(otherGrantContext))
    .verifyComplete();
~~~

To test **non-blocking behavior**, the fake token client can return a delayed `Mono`; verify there is no `.block()` inside the provider. For concurrency issues, test the storage/manager rather than only `StepVerifier` on a single request.

## 33. Integration Test: Confirming the Manager Actually Uses the Custom Provider

An isolated test calling the provider directly does not prove the service wired the manager properly. Test:

~~~text
Given:
  ClientRegistrationRepository contains reports-with-ticket
  OAuth2AuthorizedClientService is empty
  manager has WorkloadTicketAuthorizedClientProvider
  fake ticket supplier and fake token endpoint

When:
  manager.authorize(
    registrationId=reports-with-ticket,
    principal=reports-worker
  )

Then:
  provider is selected
  token endpoint receives custom grant per contract
  manager returns authorized client with right principal
  authorized-client service persists token
  subsequent authorize call while token is valid does not mint a new ticket
~~~

Another test:

~~~text
Given:
  manager has both standard client_credentials provider
  and custom workload-ticket provider

When:
  authorize(reports-service, reports-worker)

Then:
  client_credentials provider is used
  custom ticket supplier is not called
~~~

**This tests wiring**, catching bugs that provider-only unit tests miss: forgetting `setAuthorizedClientProvider()`, DI picking the wrong manager, mismatched registration grant types, or an unused token client bean.

## 34. Troubleshooting

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Manager returns `null` even though registration exists | Custom provider not attached or grant URI mismatch | Compare `authorization-grant-type` and `WorkloadTicketGrant.TYPE` |
| Provider is never invoked | Service injects a different manager | Check `@Qualifier` and HTTP integration |
| Ticket supplier is not called | Existing token still valid, grant mismatch, or another chain provider handled it | Check context/`clockSkew`/chain order |
| Custom grant rejected by AS | AS does not support URI or client lacks permission | Check `unsupported_grant_type`, `unauthorized_client` |
| Repeated `invalid_grant` | Ticket has wrong audience/TTL/replay/binding | Check issuer policy; never log ticket |
| `invalid_client` | Wrong client secret/mTLS/`private_key_jwt` | Check client auth method and secret rotation |
| Token endpoint timeout | Proxy/TLS/connect/response timeout | Check the dedicated token response client |
| Token issued yet API returns 401 | Wrong issuer/audience/revoked/expired | Check Resource Server Bearer error |
| API returns 403 | Missing scope/resource permission | Do not retry as if token expired |
| New token issued on every request | Provider always reissues or storage key unstable | Check existing client/expiry/`principalName` |
| New token issued yet missing on next call | Manager success handler fails to save or wrong service used | Check repository/service |
| Node A saves token, Node B cannot find it | Per-node in-memory store | Shared storage if architecture requires |
| Fails only under concurrent requests | Ticket/token/save race | Consider single-flight/versioning |
| Reactive thread blocked | Using sync supplier/`RestClient` or `.block()` | Choose reactive transport; offload blocking safely |
| OAuth2 login behavior unchanged | Replaced API manager only, not login token client | Distinguish `oauth2Login().tokenEndpoint()` |
| WebClient does not attach Bearer | OAuth2 filter missing or manager not called | Check consumer HTTP client |
| Ticket leaked in logs | Wire logging/raw exceptions | Disable sensitive logging and rotate credentials |

## 35. Anti-Patterns to Avoid

**1. Creating a new grant merely to add one parameter to `client_credentials`.** Check the token response client's extension hooks first.

**2. Inventing a custom grant URI and assuming every IdP understands it.** Extension grants require an Authorization Server contract and configuration.

**3. Taking tickets directly from the browser without verifying trust binding.** Vulnerable to impersonation or replay.

**4. Saving tokens in the database inside the provider and letting the manager save again.** Risks inconsistent state.

**5. Skipping the `ClientRegistration` authorization grant type check.** The provider may process the wrong registration.

**6. Always requesting a new token when the existing token is still valid.** Increases load, races, and rate limiting.

**7. Returning an expired old token when the token endpoint errors.** Hides failures and causes repeated 401s.

**8. Assuming refresh tokens are always issued.** Custom grants may not issue refresh tokens.

**9. Logging client secrets or raw tickets.** Credentials can be stolen.

**10. Calling `.block()` inside a Reactive provider.** Stalls the event loop.

**11. Using a caller-supplied `principalName` to fetch another account's token.** Introduces confused deputy risk.

**12. Blindly retrying one-time tickets after timeouts.** The AS may already have consumed them.

**13. Deleting all authorized clients when one registration hits `invalid_grant`.** Overly broad blast radius.

**14. Using a custom grant to mint tokens on behalf of users while bypassing consent and authorization policy.** This is a security design flaw.

**15. Treating local token cleanup as remote token revocation.** They are two separate mechanisms.

## 36. Practice Exercises

### Exercise 1 — Wrong Grant URI

YAML:

~~~yaml
authorization-grant-type: "urn:example:params:oauth:grant-type:workload-ticket"
~~~

Provider:

~~~java
new AuthorizationGrantType("workload_ticket")
~~~

**Question:** Why is the provider never selected?

**Solution:** Grant types must match **exact URI values** via `AuthorizationGrantType.equals(...)`. A shorthand name does not equal the URI.

### Exercise 2 — Provider Returns null

An existing authorized client has an access token valid for 10 more minutes, skew is 60 seconds, and the provider returns `null`.

**Question:** Does this mean the token manager cannot call the API?

**Solution:** No. The provider signals that reissuance is not needed; the manager continues using the saved existing authorized client. Returning `null` does not mean login failure.

### Exercise 3 — User-Submitted Ticket

A controller receives:

~~~http
GET /bff/reports?ticket=USER_SUPPLIED_TICKET
~~~

and forwards that ticket directly to the AS using the custom grant.

**Question:** What is the risk?

**Solution:** The ticket could be forged/replayed or issued for another subject. It must come from a trusted source with issuer/audience/TTL/anti-replay checks and binding to principal/tenant per contract.

### Exercise 4 — No Refresh Token

The AS issues 5-minute access tokens with no refresh token.

**Question:** How can the custom provider obtain a new token?

**Solution:** If the contract permits, mint a **fresh ticket** and invoke the custom grant again. Never synthesize a refresh token by copying an ID Token or session cookie.

### Exercise 5 — Two Workers Requesting Tokens Simultaneously

Jobs A and B both observe the AT nearing expiry, mint T2 and T3, and request AT-2 and AT-3.

**Question:** Does this immediately invalidate both tokens?

**Solution:** Not necessarily; it depends on AS policy. Still, it increases load and storage races. Design single-flight/locking/versioning as needed rather than assuming only one request runs per registration.

### Exercise 6 — Servlet vs. Reactive

A WebFlux application wants to reuse the synchronous `WorkloadTicketAuthorizedClientProvider` class inside `ReactiveOAuth2AuthorizedClientManager`.

**Question:** Should it wrap it with `.block()` to share code?

**Solution:** No. Implement a separate `ReactiveOAuth2AuthorizedClientProvider` and `ReactiveOAuth2AccessTokenResponseClient`; if the ticket library is blocking, isolate it off the event loop via appropriate scheduling.

### Exercise 7 — 403 After Successful Token Exchange

A token was issued, yet the Reports API requires `reports.admin` while the registration only has `reports.read`.

**Question:** Will retrying the grant 10 times escalate permissions?

**Solution:** No. Fix the scope/policy and Resource Server permissions; never use retries to escalate privileges.

### Exercise 8 — Token Response Client Fails to Map OAuth2 Errors

The AS returns:

~~~json
{"error":"invalid_grant"}
~~~

yet the `RestClient` adapter only throws a generic HTTP 400 exception.

**Question:** What is the consequence?

**Solution:** The manager/failure handler loses the OAuth2 error code and either cleans up incorrectly or fails to trigger policy. The token client must safely parse OAuth2 error responses and translate them into the right exception.

## 37. Pre-Deployment Checklist for Custom Grants

| Question | What Must Be Defined |
|---|---|
| Is a new grant truly needed? | Checked existing standards/hooks/providers |
| Does the AS support the custom grant URI? | Protocol contract and client configuration exist |
| What is the exact grant type? | Consistent URI across registration/provider/token request |
| Where do tickets/assertions come from? | Trusted issuer, audience, TTL, anti-replay |
| Is the principal trustworthy? | Derived from server/authentication, not arbitrary input |
| Is a dedicated request type needed? | `AbstractOAuth2AuthorizationGrantRequest` if required |
| Does the token client follow contract? | `OAuth2AccessTokenResponseClient<T>` or reactive variant |
| Is client auth configured properly? | Basic/mTLS/`private_key_jwt` per registration |
| Are token responses validated? | `token_type`, `expires_in`, scopes, error mapping |
| Does the provider match the grant? | Uses `AuthorizationGrantType.equals` |
| How are valid existing tokens handled? | Avoids unnecessary token reissuance |
| Is clock skew tuned properly? | Matches token lifetime and latency |
| Which manager is used? | Servlet web/service or Reactive web/service |
| Is the provider wired into the chain? | `setAuthorizedClientProvider(...)` configured |
| Which storage is used? | Consistent repository/service and `principalName` |
| Are cleanup and failure policies defined? | Distinguishes `invalid_grant`, `invalid_client`, 401/403 |
| Can tickets be replayed? | AS enforces one-time semantics and event IDs |
| Are retries safe? | Never replays one-time tickets blindly |
| Is multi-node concurrency handled? | Single-flight/versioning if required |
| Does Resource Server check audience/scope? | Yes; presence of a token never implies full permission |
| Can logs leak credentials? | Never logs tickets/AT/RT/client secrets |
| Are unit/integration tests in place? | Provider selection, token exchange, storage, errors, and races |
| Are operations/rotation ready? | Monitoring, secret rotation, rollback, and incident response |

## 38. Summary

**`OAuth2AuthorizedClientProvider`** is the right extension point when supporting a **custom OAuth 2.0 grant** in Spring Security Client. The provider decides whether the grant applies, checks the existing authorized client, calls `OAuth2AccessTokenResponseClient<CustomGrantRequest>` with valid evidence, and returns a new `OAuth2AuthorizedClient`. The **Manager** coordinates the provider chain and storage; the **token-response client** handles the HTTP/token-endpoint protocol; and the **Resource Server** validates tokens and resource permissions.

In Servlet apps, implement `OAuth2AuthorizedClientProvider.authorize(OAuth2AuthorizationContext)` returning an authorized client or `null`. In Reactive apps, implement `ReactiveOAuth2AuthorizedClientProvider` returning `Mono<OAuth2AuthorizedClient>`, `Mono.empty()`, or an error signal. Both must be **wired into the manager actually used by consumers**, rather than simply declaring a bean and expecting every `RestClient`/`WebClient` to discover the new grant automatically.

A custom grant must be designed as **a security protocol agreed upon with the Authorization Server**, never as a trick to bypass login, consent, or audience/scope boundaries. Govern tickets/assertions, client authentication, token response parsing, clock skew, storage, concurrency, retries, and logging. Whenever an **existing standard or built-in provider** solves the problem, prefer it. When extension is truly necessary, a small, thoroughly tested provider with isolated HTTP transport and clear trust boundaries keeps the system maintainable and secure.
