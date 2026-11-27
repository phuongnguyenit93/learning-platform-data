# 25.2. Multiple Registrations Sharing One Provider

## 1. The Problem: One OpenID Provider Serving Multiple OAuth2 Clients

Suppose a company operates an **Employee Portal** for reading orders and an **Admin Console** for administrators. Both applications, or two features of the same application, authenticate through a single OpenID Provider (OP):

~~~text
Issuer: https://login.company.example
~~~

However, at the OP there are **two different OAuth2 client records**:

~~~text
Client A:
  client_id = employee-portal-web
  redirect_uri = https://portal.example.com/login/oauth2/code/portal-web
  scopes = openid profile orders.read

Client B:
  client_id = employee-portal-admin
  redirect_uri = https://portal.example.com/login/oauth2/code/portal-admin
  scopes = openid profile admin.read
~~~

Both clients share the same issuer, authorization endpoint, token endpoint, JWK Set endpoint, and possibly the same UserInfo endpoint. However, **client ID, client secret, redirect URI, scopes, consent, tokens, and API permissions are not automatically shared**.

In **Spring Security OAuth 2.0/OIDC Client**, the proper representation is:

~~~text
registrationId = portal-web
         |
         +---- provider key = company-oidc
         |
registrationId = portal-admin
         |
         +---- provider key = company-oidc
                          |
                          v
              issuer = https://login.company.example
~~~

**One provider configuration referenced by multiple registrations does not mean Spring Security only has one OAuth2 client.** That is the core focus of this lesson.

> Context: Java 17+, Spring Boot 3, Spring Security 6, Spring MVC/Servlet, and OIDC Authorization Code Flow. The Reactive side is noted separately. Hostnames/client IDs/scopes are illustrative for educational purposes; the real IAM/Authorization Server and Resource Server must actually configure, issue, and verify those permissions.

## 2. Distinguishing Three Concepts Often Called "Provider"

| Concept | Example | Responsibility |
|---|---|---|
| **ClientRegistration** | `portal-web`, `portal-admin` | Defines an OAuth client with ID, secret, grant, redirect, scopes |
| **Provider configuration** in Spring Boot | `company-oidc` | Shared metadata about the Authorization Server/OpenID Provider |
| **Actual OpenID Provider** | `https://login.company.example` | Performs login, authorization, and issues tokens |

`spring.security.oauth2.client.provider` is also **not** the `AuthenticationProvider` class in the Spring Security authentication pipeline. The word "provider" appears at multiple layers, each with a different function.

### 2.1. Inside ClientRegistration

Spring Security uses:

~~~java
org.springframework.security.oauth2.client.registration.ClientRegistration
~~~

**Client-specific** information:

~~~text
registrationId
clientId
clientSecret
clientAuthenticationMethod
authorizationGrantType
redirectUri
scopes
clientName
~~~

**Provider metadata** information:

~~~text
providerDetails.authorizationUri
providerDetails.tokenUri
providerDetails.jwkSetUri
providerDetails.issuerUri
providerDetails.userInfoEndpoint
providerDetails.configurationMetadata
~~~

Two `ClientRegistration` instances can share the same metadata endpoints while having different client-specific fields.

### 2.2. Example matrix

| Property | portal-web | portal-admin | Conclusion |
|---|---|---|---|
| registration ID | `portal-web` | `portal-admin` | **Separate** |
| client ID | `employee-portal-web` | `employee-portal-admin` | **Separate** |
| client secret | WEB secret | ADMIN secret | **Separate** |
| grant | authorization_code | authorization_code | Can be the same |
| scopes | openid, profile, orders.read | openid, profile, admin.read | Different |
| redirect URI template | `{baseUrl}/login/oauth2/code/{registrationId}` | Same template | Expanded URIs differ |
| provider key | `company-oidc` | `company-oidc` | **Shared** |
| issuer | `https://login.company.example` | Same issuer | **Shared** |
| token endpoint | OP token endpoint | Same endpoint | **Shared** |
| JWKS | OP JWK Set endpoint | Same endpoint | **Shared** |

**Having the same redirect URI template does not mean having the same actual redirect URI.** `{registrationId}` is replaced with each registration's own ID.

## 3. Architecture Diagram

~~~mermaid
flowchart TD
    Browser["Employee's Browser"] --> Portal["Employee Portal / Spring Security"]
    Portal --> Repo["ClientRegistrationRepository"]
    Repo --> Web["portal-web registration"]
    Repo --> Admin["portal-admin registration"]
    Web --> Provider["provider: company-oidc"]
    Admin --> Provider
    Provider --> OP["OpenID Provider / shared issuer"]
    Portal --> Tokens["OAuth2AuthorizedClientRepository / Service"]
    Tokens --> WToken["portal-web + principal -> token W"]
    Tokens --> AToken["portal-admin + principal -> token A"]
    Portal --> Orders["Orders API"]
    Portal --> AdminAPI["Admin API"]
~~~

Boundaries to preserve:

1. **The OP** provides metadata and token endpoints for registered clients.
2. **ClientRegistrationRepository** stores distinct registration IDs.
3. **Authorization Code Flow** is initiated per registration ID.
4. **OAuth2AuthorizedClient** is stored per registration/principal.
5. **The Resource Server** verifies the token, audience, scopes, and data permissions.
6. **The Browser session** does not automatically merge two authorization grants.

## 4. Spring Boot Configuration: Multiple Registrations, One Provider

This is the core configuration:

~~~yaml
# src/main/resources/application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          portal-web:
            provider: company-oidc
            client-id: ${PORTAL_WEB_CLIENT_ID}
            client-secret: ${PORTAL_WEB_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read

          portal-admin:
            provider: company-oidc
            client-id: ${PORTAL_ADMIN_CLIENT_ID}
            client-secret: ${PORTAL_ADMIN_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - admin.read

        provider:
          company-oidc:
            issuer-uri: ${COMPANY_OIDC_ISSUER_URI}
~~~

All client secrets here are **placeholders** and must be injected from a secret manager/runtime. Do not put real secrets in Git, README files, or browser JavaScript.

### 4.1. Reading the YAML structure

~~~text
spring.security.oauth2.client.registration.<registrationId>
spring.security.oauth2.client.provider.<providerId>
~~~

The setting:

~~~yaml
portal-web:
  provider: company-oidc
~~~

means registration `portal-web` references the provider alias `company-oidc`.

Similarly:

~~~yaml
portal-admin:
  provider: company-oidc
~~~

The provider alias is defined **once**:

~~~yaml
provider:
  company-oidc:
    issuer-uri: ${COMPANY_OIDC_ISSUER_URI}
~~~

There is only **one provider configuration**, yet still **two ClientRegistration objects**.

### 4.2. No need to duplicate provider metadata

A duplicated configuration like:

~~~yaml
provider:
  web-idp:
    issuer-uri: https://login.company.example
  admin-idp:
    issuer-uri: https://login.company.example
~~~

is not syntactically invalid, but when the issuer/endpoints are genuinely the same, it increases the risk of drift, inconsistent settings, and unnecessary maintenance. Sharing the provider key clearly expresses a **shared trust boundary**.

### 4.3. Provider alias is not the ClientRegistration ID

Do not confuse them:

~~~text
provider alias: company-oidc
registration ID: portal-web
client ID: employee-portal-web
issuer URI: https://login.company.example
~~~

These values have different semantics. When Spring Security asks for `clientRegistrationId`, use `portal-web` or `portal-admin`, not the provider alias.

## 5. OpenID Discovery and issuer-uri

OpenID Providers typically publish discovery metadata at:

~~~text
/.well-known/openid-configuration
~~~

An illustrative response:

~~~json
{
  "issuer": "https://login.company.example",
  "authorization_endpoint": "https://login.company.example/oauth2/authorize",
  "token_endpoint": "https://login.company.example/oauth2/token",
  "jwks_uri": "https://login.company.example/oauth2/jwks",
  "userinfo_endpoint": "https://login.company.example/oidc/userinfo"
}
~~~

If `issuer-uri` is set in the provider configuration, Spring Security can use OIDC discovery to build provider details and support validation according to the library.

**Sharing a provider config means sharing metadata values and the trust source**, not a guarantee that the framework creates only one Java object or executes HTTP discovery only once. That depends on the implementation/caching.

### 5.1. Issuer is a security identity

Two URLs:

~~~text
https://login.company.example/realms/employees
https://login.company.example/realms/partners
~~~

can be **two different issuers** even though they share the same host and vendor. Do not merge two realms into the same provider just because the company name is the same.

### 5.2. Same JWKS does not mean same issuer

In OIDC, validating an ID Token requires checking the issuer, audience, signature, expiration, nonce, and other conditions. Two issuers might use similar keys, but issuer validation must never be skipped just because the JWK Set URI is the same.

### 5.3. Providers that do not support discovery

For a custom OAuth2 provider, endpoints can be configured manually:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          legacy-oauth:
            authorization-uri: https://auth.example.test/oauth2/authorize
            token-uri: https://auth.example.test/oauth2/token
            user-info-uri: https://auth.example.test/api/userinfo
            user-name-attribute: sub
~~~

If a client genuinely requires OIDC (the `openid` scope and an ID Token), you must configure the full issuer/JWK/metadata and proper validation rather than copying an arbitrary token URI and assuming it is a standard OP.

## 6. Two OAuth Client Records Must Exist at the Authorization Server

YAML in the Portal **does not create clients in the IdP**. The IAM administrator must register them correspondingly:

| Client at IdP | Client ID | Registered Redirect URI |
|---|---|---|
| Employee Portal | employee-portal-web | `https://portal.example.com/login/oauth2/code/portal-web` |
| Admin Console | employee-portal-admin | `https://portal.example.com/login/oauth2/code/portal-admin` |

Client scopes, secret/client auth method, consent, PKCE, and token policies must also be permitted properly on each record.

### 6.1. Why is the redirect URI template the same while callbacks differ?

YAML:

~~~yaml
redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

With `baseUrl` as `https://portal.example.com`:

~~~text
portal-web   -> /login/oauth2/code/portal-web
portal-admin -> /login/oauth2/code/portal-admin
~~~

The OP needs to allow the actual URI **per client**. Do not use the web client ID with the admin redirect URI and expect the OP to fix it.

### 6.2. Can a single shared redirect URI be used?

A shared callback URI can work if the application customizes the resolver/filter/correlation properly, but using `{registrationId}` by default is clearer.

If you customize the callback URL, you must ensure the Authorization Code response is matched with the right **registration, original state, redirect URI, and client credentials**. Do not drop correlation just to use a single path.

### 6.3. Client secrets are independent

Two records with different client IDs usually have separate credentials. Do not copy `PORTAL_WEB_CLIENT_SECRET` into the admin registration unless that is genuinely the credential registered and accepted by the IdP.

Common errors:

~~~text
invalid_client
unauthorized_client
invalid_scope
redirect_uri_mismatch
~~~

Exact error names vary by provider, but investigate **registration-specific settings** before modifying the shared issuer.

## 7. Login Initiation URL Depends on the Registration ID

By default in Servlet Spring Security:

~~~text
/oauth2/authorization/portal-web
/oauth2/authorization/portal-admin
~~~

When the browser requests:

~~~http
GET /oauth2/authorization/portal-web HTTP/1.1
Host: portal.example.com
~~~

Spring Security builds the authorization request with:

~~~text
client_id=employee-portal-web
redirect_uri=https://portal.example.com/login/oauth2/code/portal-web
scope=openid profile orders.read
state=<random-web-state>
response_type=code
~~~

With the URL:

~~~http
GET /oauth2/authorization/portal-admin HTTP/1.1
Host: portal.example.com
~~~

the parameters change:

~~~text
client_id=employee-portal-admin
redirect_uri=https://portal.example.com/login/oauth2/code/portal-admin
scope=openid profile admin.read
state=<random-admin-state>
response_type=code
~~~

**Both redirect to the same authorization endpoint**, but the Authorization Server makes decisions based on the client ID, redirect URI, requested scopes, and per-client policies.

## 8. SecurityFilterChain Does Not Need Duplication Just for Multiple Registrations

A basic configuration:

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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

A single chain with `oauth2Login()` can support multiple `authorization_code` registrations through the same `ClientRegistrationRepository`.

### 8.1. When is it necessary to split SecurityFilterChain?

If the Admin Console requires different security rules/entry points, or the app has both a stateless API and stateful browser login, you can split chains using request matchers. However, **two registrations by themselves do not require two chains**.

In particular, if you create multiple chains, verify `@Order`, `securityMatcher`, and ensure that login initiation/callback paths are handled by the chain with the corresponding OAuth2 login filters.

## 9. Login Method Selection Page

When offering two choices:

~~~html
<main>
  <h1>Sign in</h1>
  <a href="/oauth2/authorization/portal-web">
    Employee Portal
  </a>
  <a href="/oauth2/authorization/portal-admin">
    Admin Console
  </a>
</main>
~~~

If using a custom login page:

~~~java
http.oauth2Login(oauth2 -> oauth2
    .loginPage("/login")
);
~~~

then you must provide `GET /login` yourself and permit access to that URL.

### 9.1. Choosing Admin Console does not grant ROLE_ADMIN

A user clicking:

~~~text
/oauth2/authorization/portal-admin
~~~

only asks the Authorization Server to process the **admin OAuth client**. It **does not automatically grant admin privileges** to the user.

The Application/Resource Server must still verify RBAC, permissions, organization/tenant, scopes, and resource ownership.

### 9.2. Public login allowlist

If there is an additional machine registration such as `reports-service`, do not list it as a browser login option or allow the browser to choose arbitrary registration IDs via an unchecked query parameter. A configured registration **does not imply** it is suitable for user login.

## 10. State, Nonce, and PKCE Belong to Each Authorization Request

Sharing an OP does not mean correlation values are shared:

~~~text
portal-web:
  state = W1
  nonce = NW1
  PKCE code_verifier = VW1 (if applicable)

portal-admin:
  state = A1
  nonce = NA1
  PKCE code_verifier = VA1 (if applicable)
~~~

Each callback must be matched to the right authorization request:

~~~mermaid
sequenceDiagram
    actor Browser as Browser
    participant Portal as Spring Security Portal
    participant OP as Shared OpenID Provider

    Browser->>Portal: GET /oauth2/authorization/portal-web
    Portal-->>Browser: Redirect: client_id=WEB, state=W1
    Browser->>OP: Authenticate/authorize WEB
    OP-->>Browser: Redirect: code=C1, state=W1
    Browser->>Portal: GET /login/oauth2/code/portal-web?code=C1&state=W1
    Portal->>Portal: Find original WEB request / validate state
    Browser->>Portal: GET /oauth2/authorization/portal-admin
    Portal-->>Browser: Redirect: client_id=ADMIN, state=A1
    Browser->>OP: Authenticate/authorize ADMIN
    OP-->>Browser: Redirect: code=C2, state=A1
    Browser->>Portal: GET /login/oauth2/code/portal-admin?code=C2&state=A1
    Portal->>Portal: Find original ADMIN request / validate state
~~~

`state` prevents login CSRF and binds the response to the request; OIDC `nonce` binds the ID Token to the authentication request; PKCE `code_verifier` binds the code exchange.

**Do not share state/nonce/code_verifier** just because the issuer matches.

### 10.1. Do not swap authorization codes between clients

An authorization code is issued for a specific client ID and redirect URI. Do not use WEB's code to exchange at the token endpoint using admin client credentials. The Authorization Server must verify this binding and may return `invalid_grant` if mismatched.

## 11. Browser Session, OP Session, and Authorized Clients: Three Different Things

~~~text
Browser:
  Portal's JSESSIONID
  OpenID Provider's own SSO cookie

Portal:
  HttpSession / SecurityContext
  OAuth2AuthorizationRequest during the login flow
  OAuth2AuthorizedClient store

OP:
  SSO session
  client registrations, authorization/consent policy
~~~

If a user has already logged in via `portal-web`, when they start logging in via `portal-admin`, the OP may reuse the SSO session without prompting for a password again.

**Not re-entering a password does not mean web/admin share the same token or that the user has been granted admin permissions.** The OP is still processing a new authorization request for the admin client and may require consent or step-up MFA.

### 11.1. Current Authentication in SecurityContext

Within a Servlet browser session, Spring Security usually stores **one current Authentication**. Logging in again through another registration can replace that Authentication.

~~~text
T0: Browser is authenticated via portal-web.
T1: Browser initiates portal-admin authorization.
T2: After callback, the current Authentication may be portal-admin.
~~~

This differs from the **authorized-client store**, which may still hold both WEB and ADMIN entries.

### 11.2. Multiple tabs and session correlation

If tab A initiates web login, tab B initiates admin login, and then tab A hits the callback, state conflicts may occur depending on the authorization request repository/session implementation.

Do not attribute every `authorization_request_not_found` error to provider config. Check cookies, `HttpSession` persistence, multiple tabs, the authorization request repository, and callback correlation.

## 12. SameSite Cookies and Reverse Proxies Apply to Both Login Flows

For a typical top-level GET callback:

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

is usually suitable when the IdP is cross-site. For OIDC `response_mode=form_post` producing a cross-site POST callback, a `Lax` cookie is typically not sent; `SameSite=None; Secure` and narrowly designed CSRF callback POST handling may be needed.

**Having the same provider does not guarantee all registrations use the same response mode or step-up policy.**

### 12.1. Reverse proxy must understand the public base URL

If the browser accesses:

~~~text
https://portal.example.com
~~~

but the app sees:

~~~text
http://portal-service:8080
~~~

then `{baseUrl}` may be constructed incorrectly, causing both registrations to hit redirect URI mismatches or cookies not to be sent due to the wrong scheme/host.

An illustrative configuration:

~~~yaml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Only trust forwarded headers from trusted proxies; ingress must strip/overwrite client-supplied values to prevent host/header spoofing.

## 13. OAuth2AuthorizedClient Belongs to the Registration, Not the Provider Alias

Spring Security represents an authorization result with:

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClient
~~~

An authorized client is associated with:

~~~text
ClientRegistration + principalName + accessToken [+ refreshToken]
~~~

Example:

~~~text
Authorized Client W:
  registrationId = portal-web
  principalName = employee-0042
  accessToken = AT-W
  refreshToken = RT-W (if issued)

Authorized Client A:
  registrationId = portal-admin
  principalName = employee-0042
  accessToken = AT-A
  refreshToken = RT-A (if issued)
~~~

The authorized-client store normally keys entries by **(clientRegistrationId, principalName)**. Do not cache by:

~~~text
key = providerId + ":" + username
~~~

because two clients sharing `company-oidc` would overwrite each other's tokens.

### 13.1. Tokens are not interchangeable across registrations

AT-W may have scope `orders.read` and an audience for the Orders API. AT-A may have scope `admin.read` and a different audience.

**The same issuer/JWK does not make a WEB token valid for the ADMIN API.** The Resource Server checks issuer, signature/introspection, audience, scopes, expiry, and resource authorization.

### 13.2. ID Token is not an access token

An OIDC ID Token serves authentication at the client. If:

~~~text
ID Token W:
  iss = https://login.company.example
  aud = employee-portal-web

ID Token A:
  iss = https://login.company.example
  aud = employee-portal-admin
~~~

then even with the same issuer/signing key, **audience still follows the client ID**. Do not use ID Token W for the Admin client, and do not use an ID Token to call the Orders API instead of an access token.

## 14. Refresh Tokens Are Also Not Shared

An OP may issue a refresh token to one, both, or neither registration, depending on client policy, scopes, and consent.

~~~text
portal-web:
  RT-W issued to WEB client

portal-admin:
  RT-A issued to ADMIN client
~~~

Do not use RT-W with admin client credentials at the token endpoint. RT-W may be bound to the WEB client ID/authorization grant.

### 14.1. Refresh token rotation

~~~text
WEB: RT-W1 -> AT-W2 + RT-W2
ADMIN: RT-A1 exists independently
~~~

If `invalid_grant` occurs on RT-W1, do not automatically delete/revoke RT-A1 just because the provider key is the same.

### 14.2. Different token TTLs

The OP might enforce:

~~~text
WEB access token TTL   = 5 minutes
ADMIN access token TTL = 2 minutes
~~~

A shared provider URI **does not mean identical client policies**. The authorized-client manager must rely on each client's expiry/token response.

## 15. Reading the Current Registration After Login

In Servlet, the `Authentication` for OAuth2 login is typically:

~~~java
org.springframework.security.oauth2.client.authentication
    .OAuth2AuthenticationToken
~~~

Example controller:

~~~java
package com.example.portal.web;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentLoginController {

    @GetMapping("/api/login-context")
    public Map<String, String> current(Authentication authentication) {
        if (!(authentication instanceof OAuth2AuthenticationToken oauth)) {
            throw new IllegalStateException(
                "Current authentication is not OAuth2 Login"
            );
        }
        return Map.of(
            "registrationId",
            oauth.getAuthorizedClientRegistrationId(),
            "principalName",
            oauth.getName()
        );
    }
}
~~~

The resulting registration ID can be `portal-web` or `portal-admin`. **Do not expose tokens, client secrets, or sensitive claims** to the browser; illustrative endpoints require authorization and data minimization.

### 15.1. Current Authentication differs from the authorized-client store

`getAuthorizedClientRegistrationId()` reflects the current login `Authentication`. The authorized-client repository/service may still hold other authorized clients for a previous principal or the same principal.

Do not infer from "currently logged in via `portal-admin`" that the `portal-web` token has been deleted, or vice versa.

## 16. Does @RegisteredOAuth2AuthorizedClient Need a Registration ID Specified?

Servlet Spring Security provides the annotation:

~~~java
org.springframework.security.oauth2.client.annotation
    .RegisteredOAuth2AuthorizedClient
~~~

Example:

~~~java
@GetMapping("/api/orders/registration")
public String currentOrdersRegistration(
    @RegisteredOAuth2AuthorizedClient("portal-web")
    OAuth2AuthorizedClient authorizedClient
) {
    if (authorizedClient == null) {
        return "portal-web authorized client not available";
    }
    return authorizedClient.getClientRegistration().getRegistrationId();
}
~~~

Do not return `authorizedClient.getAccessToken().getTokenValue()` to the frontend. If no authorized client exists yet for the specified registration, the annotation/resolver does not guarantee the browser has authorized that client; an interactive Authorization Code Flow may need to run separately.

### 16.1. Do not pick another client just because a scope is missing

If a user has a WEB token and the Orders API requires an ADMIN scope, do not silently switch to `portal-admin` or `reports-service` to "escalate privileges". Business policy and consent govern how new scopes are requested.

## 17. OAuth2AuthorizedClientManager Selects a Registration per Request

~~~java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("portal-web")
        .principal(authentication)
        .build();

OAuth2AuthorizedClient client = manager.authorize(request);
~~~

`manager` is `OAuth2AuthorizedClientManager`. `authentication` must come from a verified security context; do not use a username entered by the browser.

### 17.1. Servlet manager for HTTP requests

~~~java
DefaultOAuth2AuthorizedClientManager manager =
    new DefaultOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        authorizedClientRepository
    );

manager.setAuthorizedClientProvider(
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build()
);
~~~

This code illustrates wiring; the variables must be injected by Spring. The manager uses Servlet request context/repository, so calling it outside standard integration may require `HttpServletRequest`/`HttpServletResponse` mapped into the authorization context.

### 17.2. Do not complete authorization-code flows inside cron jobs

If the application also has a `reports-service` registration using `client_credentials`, a scheduled job should use `AuthorizedClientServiceOAuth2AuthorizedClientManager` with a service principal and the appropriate authorized-client service.

**A shared provider does not create an HttpSession for a background job.**

## 18. WebClient on Servlet with an Explicit Registration ID

`WebClient` can integrate with Servlet OAuth2:

~~~java
import org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction;
~~~

Illustrative bean:

~~~java
@Bean("ordersWebClient")
WebClient ordersWebClient(OAuth2AuthorizedClientManager manager) {
    ServletOAuth2AuthorizedClientExchangeFilterFunction oauth =
        new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return WebClient.builder()
        .baseUrl("https://orders.example.test")
        .apply(oauth.oauth2Configuration())
        .build();
}
~~~

When calling:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> orders = ordersWebClient.get()
    .uri("/api/orders")
    .attributes(clientRegistrationId("portal-web"))
    .retrieve()
    .bodyToMono(String.class);
~~~

**Do not set `clientRegistrationId("company-oidc")`**; that is the provider alias, not the registration.

### 18.1. One WebClient per Resource Server

A safer configuration when there are multiple downstreams:

~~~text
ordersWebClient -> https://orders.example.test + portal-web
adminWebClient  -> https://admin-api.example.test + portal-admin
~~~

Do not automatically send Bearer tokens to arbitrary user-entered hosts/URLs. Control destinations, redirects, and registration selection within the backend trust boundary.

### 18.2. Servlet async and SecurityContext

`WebClient` returns a `Mono`, whereas a Servlet app relies on request-scoped `SecurityContext`/`HttpServletRequest`. When subscribing on another thread, ensure the OAuth2 filter has sufficient context per the integration API. Never attach an arbitrary `principalName` to look up another token.

## 19. RestClient on Servlet (Spring Security 6.4+)

Starting in Spring Security 6.4+, there is:

~~~java
org.springframework.security.oauth2.client.web.client
    .OAuth2ClientHttpRequestInterceptor
~~~

Example:

~~~java
OAuth2ClientHttpRequestInterceptor oauth =
    new OAuth2ClientHttpRequestInterceptor(authorizedClientManager);

RestClient ordersClient = RestClient.builder()
    .baseUrl("https://orders.example.test")
    .requestInterceptor(oauth)
    .build();
~~~

Selecting the registration:

~~~java
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver.clientRegistrationId;

String orders = ordersClient.get()
    .uri("/api/orders")
    .attributes(clientRegistrationId("portal-web"))
    .retrieve()
    .body(String.class);
~~~

`authorizedClientManager` is a manager configured appropriately for the request context/store. If the app has multiple managers, use qualifiers so consumers receive the right instance.

### 19.1. Failure handlers remove tokens per registration/principal

If the Admin API returns:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

then authorized client cleanup must target **portal-admin + trusted principal**, not delete every token issued by `company-oidc`.

If the API returns `403 insufficient_scope`, the token may still be valid for other APIs. Do not treat every 403 as a revoked token and do not retry infinitely.

## 20. Same Provider, Different Client Authentication Methods

The OP can have clients:

~~~text
portal-web:
  confidential client, client_secret_basic

public-frontend:
  public client, no client secret, Authorization Code + PKCE

reports-service:
  confidential service client, client_credentials
~~~

**`ClientAuthenticationMethod` belongs to each `ClientRegistration`.** Sharing provider endpoints does not force every client to use the same client secret, mTLS certificate, or `private_key_jwt` policy.

### 20.1. Do not put confidential client secrets in the browser

If a registration is an SPA/public client, do not copy the server-side secret into JavaScript. PKCE supports Authorization Code Flow for public clients, but does not turn the browser into a place to keep client secrets.

### 20.2. Audience and token type

An access token can be opaque or JWT depending on the provider. The Resource Server validates the token per contract; the same issuer does not guarantee tokens share the same audience or claims.

## 21. Adding a `client_credentials` Registration on the Same Provider

A worker needs to fetch reports using a machine identity:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-service:
            provider: company-oidc
            client-id: ${REPORTS_SERVICE_CLIENT_ID}
            client-secret: ${REPORTS_SERVICE_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
~~~

It uses the same provider alias, but the grant and identity differ:

| Registration | Grant | Token represents |
|---|---|---|
| portal-web | authorization_code | User authorization for WEB client |
| portal-admin | authorization_code | User authorization for ADMIN client |
| reports-service | client_credentials | OAuth client/service |

Do not use the `reports-service` token to automatically "log in an employee". Machine identity does not replace user identity/consent.

### 21.1. Refresh tokens are not required in `client_credentials`

The Client Credentials Grant normally does not issue refresh tokens; when the access token expires, the manager can request a new access token using `client_credentials`. Do not use a browser registration's refresh token to issue a service token.

## 22. One Issuer, Yet OIDC `sub` May Differ Between Registrations

In OIDC, identity is typically evaluated by:

~~~text
(iss, sub)
~~~

If the OP uses **public subject identifiers**, two clients on the same issuer may see the same `sub` for the same person.

If the OP uses **pairwise subject identifiers**, `sub` may differ across clients or sector identifiers:

~~~text
WEB:
  iss = https://login.company.example
  sub = pairwise-web-7e8

ADMIN:
  iss = https://login.company.example
  sub = pairwise-admin-2ac
~~~

**Two different subjects are not enough to prove two different people**, yet they also must not be auto-merged solely because their emails match.

### 22.1. Pairwise sector policy

OIDC pairwise identifiers can depend on the sector identifier; in some models, the redirect host or `sector_identifier_uri` affects the sector. Thus, changing client registration/redirect hosts can affect `sub`.

### 22.2. Email is not an immutable identifier key

Emails can change, be unverified, be reassigned, or collide in some systems. Never assume:

~~~text
email_web == email_admin => same internal account
~~~

If account linking is required, run a verified backend workflow based on trustworthy evidence/identity mapping.

## 23. Account Linking Is Not Token Linking

Suppose an internal user ID:

~~~text
app_user.id = u-0042
~~~

is securely linked to two external identities:

~~~text
WEB identity:
  issuer = https://login.company.example
  subject = pairwise-web-7e8

ADMIN identity:
  issuer = https://login.company.example
  subject = pairwise-admin-2ac
~~~

Both identities may map to `u-0042` according to policy. However:

~~~text
WEB authorized client != ADMIN authorized client
~~~

Account linking does not make tokens, refresh tokens, scopes, or consent of two OAuth clients equivalent.

### 23.1. Do not treat the admin registration as proof of role

A user logging in via `portal-admin` must still have RBAC/roles/membership checked by the application. The client ID identifies **the OAuth client application**, not that the user holds admin privileges.

### 23.2. Step-up MFA may differ per registration

The admin client may require `max_age`, `acr_values`, `prompt`, or another OP policy. Even on the same issuer, do not assume an SSO session satisfies the authentication level required for sensitive operations.

The application must verify authentication assurance/`auth_time` and authorization per the OP contract, not infer them from the registration name.

## 24. Multi-tenant: When Must Multiple Provider Configurations Be Used?

Compare two models.

**Model A — One issuer with multiple OAuth clients:**

~~~text
issuer = https://id.example.com/realms/corporate
client_id = web
client_id = admin
client_id = reports
~~~

=> Can share a provider configuration.

**Model B — Multiple issuers/realms:**

~~~text
issuer A = https://id.example.com/realms/tenant-a
issuer B = https://id.example.com/realms/tenant-b
~~~

=> Usually requires separate provider configurations per issuer/trust boundary.

### 24.1. Do not trust browser-entered issuers

A request such as:

~~~http
GET /login?issuer=https://attacker.example HTTP/1.1
~~~

must not cause the backend to create a `ClientRegistration` and trust an arbitrary issuer. Dynamic issuer onboarding requires an allowlist, SSRF prevention, metadata validation, and trusted governance.

### 24.2. Tenant authorization does not depend on the provider alias

`company-oidc` only indicates the provider configuration. Tenant/resource authorization must still be checked at the backend/Resource Server. Never take an untrusted `tenantId` and treat it as proof the user belongs to that tenant.

## 25. Dev, Staging, and Production

For example, each environment has its own issuer:

~~~text
DEV:
  https://login-dev.company.example

STAGING:
  https://login-staging.company.example

PROD:
  https://login.company.example
~~~

Each environment can keep the same structure:

~~~yaml
registration:
  portal-web:
    provider: company-oidc
  portal-admin:
    provider: company-oidc
provider:
  company-oidc:
    issuer-uri: ${COMPANY_OIDC_ISSUER_URI}
~~~

but `issuer-uri`, client IDs, secrets, and registered redirect URIs must belong to the **same environment**.

### 25.1. Do not share prod secrets in dev

Separating secrets/clients by environment limits blast radius if dev/staging credentials are exposed. Do not add overly broad wildcard redirect URIs just to switch environments easily.

### 25.2. Verify actual redirect URIs behind a reverse proxy

Even when YAML is correct, wrong forwarded host/proto headers can turn `{baseUrl}` into an internal host and break both registrations. Check the actual URL sent to the OP and the issuer registration.

## 26. Reading ClientRegistrationRepository in Java

In Servlet:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

ClientRegistration web =
    registrations.findByRegistrationId("portal-web");

ClientRegistration admin =
    registrations.findByRegistrationId("portal-admin");
~~~

`registrations` is the `ClientRegistrationRepository` bean provided by Spring or configured by the application.

Values that can be compared:

~~~java
String issuerWeb = web.getProviderDetails().getIssuerUri();
String issuerAdmin = admin.getProviderDetails().getIssuerUri();

String clientIdWeb = web.getClientId();
String clientIdAdmin = admin.getClientId();
~~~

Expected:

~~~text
issuerWeb.equals(issuerAdmin) == true
clientIdWeb.equals(clientIdAdmin) == false
web.getRegistrationId() != admin.getRegistrationId()
~~~

**Do not log `getClientSecret()` or raw tokens.**

### 26.1. Shared configuration does not mean the same Java reference

A test:

~~~java
assertSame(web.getProviderDetails(), admin.getProviderDetails());
~~~

is not a functionally valid condition. Spring may build distinct `ProviderDetails` objects from the same metadata. Check issuer/endpoints and client-specific fields, not object identity.

## 27. Testing Spring Boot Configuration with JUnit 5

~~~java
package com.example.portal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class SharedProviderRegistrationTest {

    @Autowired
    ClientRegistrationRepository registrations;

    @Test
    void twoRegistrationsHaveSharedIssuerButDistinctClients() {
        ClientRegistration web =
            registrations.findByRegistrationId("portal-web");

        ClientRegistration admin =
            registrations.findByRegistrationId("portal-admin");

        assertNotNull(web);
        assertNotNull(admin);
        assertNotEquals(
            web.getRegistrationId(), admin.getRegistrationId());
        assertEquals(
            web.getProviderDetails().getIssuerUri(),
            admin.getProviderDetails().getIssuerUri());
        assertNotEquals(web.getClientId(), admin.getClientId());

        assertTrue(web.getScopes().contains("openid"));
        assertTrue(admin.getScopes().contains("openid"));
        assertTrue(web.getScopes().contains("orders.read"));
        assertTrue(admin.getScopes().contains("admin.read"));

        assertEquals(
            "{baseUrl}/login/oauth2/code/{registrationId}",
            web.getRedirectUri());
        assertEquals(
            "{baseUrl}/login/oauth2/code/{registrationId}",
            admin.getRedirectUri());
    }
}
~~~

This is a **configuration** integration test. If `issuer-uri` is used, Spring Boot may perform discovery over the network when building registrations. Configure mock/fake IdP metadata in the test profile; **do not require unit/integration tests to call a production IdP**.

### 27.1. Testing login entrypoints

With MockMvc and Spring Security enabled:

~~~java
@Test
void webEntryPointRedirectsForWebClient() throws Exception {
    mvc.perform(get("/oauth2/authorization/portal-web"))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().string(
            "Location",
            org.hamcrest.Matchers.containsString(
                "client_id=employee-portal-web")));
}
~~~

This is a **test fragment**, assuming `mvc`, registrations, and a test IdP are set up. Also test the admin entrypoint, actual redirect URI, requested scopes, and state; do not stop at a single substring.

### 27.2. Testing callback correlation

~~~text
Given:
  Initiate portal-web authorization.
  State W1 and clientId WEB have been stored.

When:
  Callback uses WEB's code/state but hits the admin callback path.

Then:
  Do not accept it as an ADMIN authorization.
~~~

Use a fake OP/test tokens; do not disable state/nonce/PKCE validation to make a happy-path test pass.

## 28. Testing That Tokens Are Not Cross-Used

A fake manager returns:

~~~text
portal-web -> TEST_WEB_TOKEN
portal-admin -> TEST_ADMIN_TOKEN
~~~

With a mock HTTP server or fake `WebClient` `ExchangeFunction`, verify:

1. Orders API receives `Bearer TEST_WEB_TOKEN`.
2. Admin API receives `Bearer TEST_ADMIN_TOKEN`.
3. `TEST_ADMIN_TOKEN` is never sent to Orders API.
4. `TEST_WEB_TOKEN` is never sent to Admin API.
5. No token is ever sent to a host outside the allowlist.
6. Token values, refresh tokens, or client secrets are never logged.

### 28.1. Testing 401/403 errors

~~~text
Admin API -> 401 Bearer invalid_token
  => clean up portal-admin authorized client per policy.

Orders API -> 200 OK
  => portal-web client is not deleted.
~~~

Do not delete all authorized clients under provider `company-oidc` when only one token is rejected.

### 28.2. Testing server-side admin permissions

A security test should prove:

- A user without ADMIN permissions still cannot access admin endpoints even if logged in via `portal-admin`.
- A user with permissions who has not yet authorized the admin client must go through the proper consent/authorization flow.
- The API verifies the actual audience/scopes/resource permissions.
- A user belonging to another tenant cannot read admin data simply by changing the registration ID.

**Authentication and authorization are two separate layers.**

## 29. Observability and Operations

When multiple registrations share an OP, metrics should distinguish them:

~~~text
oauth.client.authorization.failure{registration=portal-web}
oauth.client.authorization.failure{registration=portal-admin}
oauth.client.refresh.attempt{registration=portal-web}
oauth.client.refresh.attempt{registration=portal-admin}
oauth.provider.discovery.failure{provider=company-oidc}
oauth.resource.invalid_token{registration=portal-admin}
~~~

Metric names here are **examples only**, not automatically emitted by Spring Boot out of the box.

### 29.1. Distinguishing shared failures from individual failures

| Error | Which layer to inspect first? |
|---|---|
| Both web/admin time out on issuer discovery | Shared OP/network/proxy/TLS |
| Only admin gets `invalid_client` | Admin client ID/secret/method |
| Only web gets `redirect_uri_mismatch` | Web redirect URI / IdP record |
| Both callbacks miss state | Cookies, HttpSession, shared session store |
| Only Admin API returns 403 | Scopes/roles/resource authorization |
| Web token sent to Admin API | Registration selection/HTTP client wiring |
| Two registrations have different `sub` | Pairwise subject policy |
| Only admin refresh fails | RT/admin client-specific policy |

If one registration fails, **do not modify the shared issuer or purge all tokens** before finding the root cause.

### 29.2. Safe logging

You can log registration ID, provider alias, error code, status code, correlation ID, and latency. Do not log:

~~~text
access_token=<actual-token>
refresh_token=<actual-token>
client_secret=<actual-secret>
authorization_code=<actual-code>
Cookie: JSESSIONID=<actual-session>
Authorization: Bearer <actual-token>
~~~

Do not store raw tokens/JWTs in metric labels or distributed tracing attributes.

## 30. Troubleshooting

| Symptom | Likely cause | Remediation |
|---|---|---|
| Spring Boot fails to start | Missing provider key or discovery error | Check `registration.*.provider` and `provider.company-oidc` |
| Only portal-admin `invalid_client` | Wrong admin ID/secret | Cross-check admin client record against secret manager |
| Only web `redirect_uri_mismatch` | Wrong redirect URI on WEB client | Check expansion, public URL, and IdP |
| Started web login but hit admin callback | Wrong custom redirect matcher | Check state, registrationId, and callback path |
| Both logins fail after proxy deployment | Wrong forwarded scheme/host/cookie | Check ingress trusted headers, HTTPS |
| User clicks Admin Console but gets 403 | Lacks admin permissions | Check RBAC, scopes, tenant, and Resource Server |
| Same user has two different `sub` values | OP pairwise subjects | Check sector policy; do not auto-link by email |
| WebClient sends another client's token | Wrong default client/registration attribute | Specify `clientRegistrationId` and separate HTTP clients |
| Token issued but API returns 401 | Wrong audience/issuer, expired/revoked token | Check Bearer error and token lifecycle |
| `OAuth2AuthorizedClient` not found after login | Different storage key/principal or lost session | Check repo/service, registration/principal |
| Fails only when running multiple replicas | Local session/token storage | Use appropriate shared store/routing strategy |
| Logged out but OP still has SSO | Local logout is not OP logout | Design RP-initiated logout/revocation |
| Reports job demands `HttpServletRequest` | Servlet request manager used outside web context | Switch to service-based manager |
| Admin refresh fails while web works | RT-A/client-specific policy | Do not substitute RT-W |
| Discovery issuer differs from config | Wrong trusted issuer | Fix provider config; do not disable validation |

### 30.1. Decision tree

~~~text
Login/API fails with multiple registrations
    |
    v
Is the right Registration ID selected?
    |-- No -> Fix login link/HTTP request attribute.
    |
    v
Does ClientRegistration exist in the repository?
    |-- No -> Fix YAML/binding.
    |
    v
Are provider key/issuer metadata correct?
    |-- No -> Fix shared provider/trust settings.
    |
    v
Do Client ID/secret/redirect/scopes match the IdP?
    |-- No -> Fix the corresponding individual client registration.
    |
    v
Are callback state/session/nonce/PKCE valid?
    |-- No -> Check cookies/session/concurrency.
    |
    v
Is the authorized client for registration + principal correct?
    |-- No -> Fix storage/manager selection.
    |
    v
Are token audience/scope and Resource Server permissions valid?
    |-- No -> Fix token/client policy or RBAC.
    |
    v
Check refresh, expiry, failure handlers, and logs.
~~~

## 31. Anti-Patterns to Avoid

**1. Duplicating provider config for each registration despite having the same issuer.** Causes metadata drift and makes maintenance harder.

**2. Treating the same provider as having the same client ID/secret.** Each client record has its own credentials.

**3. Using the provider alias in the login URL.** The default login endpoint selects `registrationId`.

**4. Assuming the same redirect URI template means the same actual URI.** `{registrationId}` produces different callbacks.

**5. Allowing a WEB token to call the Admin API.** The Resource Server checks the exact audience/scope/role.

**6. Caching tokens by issuer instead of registration + principal.** Risks cross-use or overwriting.

**7. Using `client_credentials` like a user token.** Machine identity has no user consent/authentication.

**8. Clicking the Admin Console button grants `ROLE_ADMIN`.** OAuth client selection does not replace RBAC.

**9. Auto-linking user accounts solely by email.** Pairwise `sub` can differ; email is not immutable.

**10. Skipping state/nonce/PKCE because login shares an OP.** Each authorization request requires correlation.

**11. Deleting all tokens for an issuer due to one `invalid_grant`.** Clean up only the affected registration/principal.

**12. Automatically attaching access tokens to every outgoing HTTP host.** Bearer tokens can be exfiltrated.

**13. Merging multiple realms from the same vendor into one issuer.** The Issuer URI is a trust boundary.

**14. Hard-coding secrets/refresh tokens.** Use a secret manager, rotation, and safe logging.

**15. Treating an OP SSO session as proof the user has permissions across all apps.** SSO is not authorization.

## 32. Practice Exercises

### Exercise 1 — How many registrations?

~~~yaml
registration:
  web:
    provider: corp
  admin:
    provider: corp
  reports:
    provider: corp
provider:
  corp:
    issuer-uri: https://idp.example.test
~~~

**Question:** How many registrations and provider configurations are there?

**Answer:** Three `ClientRegistration` IDs (`web`, `admin`, `reports`) and one provider alias `corp`. Each registration still needs valid client/grant details.

### Exercise 2 — Which login URL?

~~~text
registrationId = portal-web
provider = company-oidc
~~~

**Question:** What is the default login initiation URL?

**Answer:** `/oauth2/authorization/portal-web`, not `/oauth2/authorization/company-oidc`.

### Exercise 3 — Callback URLs

Two registrations use the template:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

**Question:** Are the callback URIs the same?

**Answer:** No; with `baseUrl` `https://portal.example.com`, the suffixes are `/portal-web` and `/portal-admin`. Each actual URI must be registered accurately at the IdP.

### Exercise 4 — Cross-using tokens?

WEB token has scope `orders.read`, ADMIN token has `admin.read`. Same issuer.

**Question:** Is sending the WEB token to the Admin API valid?

**Answer:** Not by default. The Resource Server also checks audience, scopes, and permissions.

### Exercise 5 — OP does not ask for a password a second time

The user logs into web, and then admin login is automatically completed via OP SSO.

**Question:** Does that mean the user already has admin permissions?

**Answer:** No. The OP reused the SSO session, but the application must still verify RBAC/MFA/authentication assurance per policy.

### Exercise 6 — Different pairwise `sub` values

~~~text
WEB: iss=X, sub=W1, email=a@example.com
ADMIN: iss=X, sub=A9, email=a@example.com
~~~

**Question:** Should they be automatically linked into one user?

**Answer:** No. They may be pairwise identifiers; a trustworthy account linking mechanism is required rather than linking by email alone.

### Exercise 7 — Two issuer realms

~~~text
https://id.example.test/realms/a
https://id.example.test/realms/b
~~~

**Question:** Should they use a single provider config?

**Answer:** No, if metadata confirms these are two distinct issuers. Trust and config must be separated.

### Exercise 8 — Admin refresh `invalid_grant`

RT-A is rejected; RT-W is still valid.

**Question:** Should both WEB and ADMIN authorized clients be deleted?

**Answer:** No. Handle only the client registration and principal whose token failed.

### Exercise 9 — Job and the same provider

Adding `reports-service` with `client_credentials` on the same provider.

**Question:** Does the job need a browser login?

**Answer:** No. Use a service-based manager and machine credentials per policy; the token does not represent a user.

### Exercise 10 — `assertSame` on `ProviderDetails`?

~~~java
assertSame(
    web.getProviderDetails(),
    admin.getProviderDetails()
);
~~~

**Question:** Is this the right test for a "shared provider"?

**Answer:** No. Compare issuer/endpoints according to the security contract; do not require identical Java object references.

## 33. Implementation Checklist

| Check | Requirement |
|---|---|
| Does each registration have a unique ID? | Separate WEB and ADMIN |
| Do both reference the right provider alias? | `company-oidc` |
| Is the issuer genuinely one and the same? | Check OIDC metadata |
| Are Client IDs/secrets independent? | Match IdP records |
| Are client authentication methods valid? | Per client |
| Are scopes/grants permitted? | Per consent/IAM policy |
| Does the redirect URI template expand properly? | Exact registered URIs |
| Do login URLs use registration IDs? | `/oauth2/authorization/{registrationId}` |
| Is callback correlation accurate? | State/nonce/PKCE |
| Are cookies/sessions/proxies configured properly? | HTTPS/Secure/HttpOnly/SameSite |
| Are ID Token audience/issuer verified? | Match client ID/issuer |
| Are tokens stored under the right key? | Registration + trusted principal |
| Are refresh tokens prevented from cross-use? | No cross-use |
| Does the Resource Server validate tokens? | Audience, scopes, permissions |
| Is Admin RBAC enforced server-side? | Yes |
| Are pairwise `sub` values handled properly? | No blind email linking |
| Are SSO/Portal sessions/tokens separated? | Yes |
| Are multi-tenant issuers properly separated? | Yes |
| Is logout/revoke cleanup scoped properly? | Yes |
| Is the multi-node session/token store appropriate? | Yes |
| Do WebClient/RestClient restrict token destinations? | Yes |
| Are login entrypoints and client IDs tested? | Yes |
| Are token isolation and 401/403 tested? | Yes |
| Do logs redact credentials? | Yes |

## 34. Summary

In **Spring Security OAuth 2.0/OIDC Client**, **multiple registrations sharing one provider** is the right model when a single Authorization Server/OpenID Provider serves multiple OAuth clients for an organization. We only need one:

~~~yaml
provider:
  company-oidc:
    issuer-uri: ${COMPANY_OIDC_ISSUER_URI}
~~~

and independent registrations:

~~~yaml
registration:
  portal-web:
    provider: company-oidc
    client-id: ${PORTAL_WEB_CLIENT_ID}
  portal-admin:
    provider: company-oidc
    client-id: ${PORTAL_ADMIN_CLIENT_ID}
~~~

In doing so, issuer/authorization/token/JWK metadata can be shared, while **client ID, secret, grant, scopes, redirect URI, authorization requests, access/refresh tokens, and policies remain specific to each registration**. Login uses the **registration ID**; callbacks must match the exact request/state; HTTP clients must select the proper authorized client; and Resource Servers verify audience/scopes/resource permissions.

**Sharing a provider does not automatically mean sharing the same token, permissions, browser Authentication, or subject identifier in all cases.** OP SSO can make login smoother, but does not replace RBAC/MFA; pairwise OIDC `sub` can differ between clients; token cleanup must target the exact registration/principal. The right design is to **share metadata by trusted issuer**, while **keeping OAuth client identity, token lifecycles, and business authorization independent**.
