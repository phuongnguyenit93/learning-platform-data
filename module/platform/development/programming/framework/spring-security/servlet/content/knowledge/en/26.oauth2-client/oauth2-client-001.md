# Roles of OAuth2 Client, OAuth2 Login, and OpenID Connect in a Servlet Application

**Scope:** Spring Security for **Servlet/Spring MVC** (Spring Boot 3.x, Spring Security 6.x, Java 17+). This article helps distinguish OAuth2 Client, OAuth2 Login, and OpenID Connect (OIDC), understand the Authorization Code login flow, know which token is used to verify the user and which token is used to call APIs, and configure a web application with an OIDC provider. Spring WebFlux has its own reactive configuration and does not directly use the Servlet APIs below.

## 1. Three concepts that appear together but have different responsibilities

**OAuth 2.0** is a **resource access delegation** framework. An application (client) is granted permission by an authorization server to call a resource server on behalf of a user or on behalf of the application itself. OAuth 2.0 **does not by itself define how to authenticate a user's identity** so that an application can conclude "who this person is."

**OAuth2 Client** in Spring Security is the capability of an application acting as a **client**: managing client registrations, initiating authorization flows, obtaining/storing access tokens, and using tokens to call authorized APIs. A client can run with a logged-in user or run without a user, such as a batch job using the `client_credentials` grant.

**OAuth2 Login** uses the OAuth 2.0 `authorization_code` flow to **log a user into the Spring MVC application itself**. Spring Security receives the result from the provider, establishes an `Authentication` in the `SecurityContext`, and typically maintains the login via an HTTP session. OAuth2 Login can run with an OAuth2-specific provider or a provider that supports OIDC.

**OpenID Connect (OIDC)** adds an **identity authentication** layer on top of OAuth 2.0. The OIDC provider issues an **ID token**, and the client verifies standard constraints to confirm identity. When the requested scope includes `openid` and the provider supports OIDC, Spring Security OAuth2 Login can create an `OidcUser`.

| Capability | What question does it answer? | Primary outcome | Not synonymous with |
| --- | --- | --- | --- |
| `oauth2Client()` | How does the application obtain/manage tokens to call external APIs? | `OAuth2AuthorizedClient` (registration + principal + access token, possibly refresh token). | User login or verifying incoming API bearer tokens. |
| `oauth2Login()` | How does a user log into the web app via an IdP? | `Authentication`, `SecurityContext`, usually with a session cookie. | Automatically allowing all APIs or all permissions. |
| OIDC with `openid` scope | How do we verify identity using a standard protocol? | ID token, `OidcUser`, optionally UserInfo. | API authorization. |
| `oauth2ResourceServer()` | How does an API validate an access token sent by a caller? | Verifies a JWT or opaque token and API permissions. | OAuth2 Client or OAuth2 Login. |
| Authorization Server / OpenID Provider | Who authenticates the user, asks for consent, and issues codes and tokens? | Code, access token, ID token (if OIDC). | The client application consuming the token. |

**Example:** A Portal uses corporate SSO to log employees in via OIDC (**OAuth2 Login + OIDC**), then uses an access token to call the Calendar API (**OAuth2 Client**). The Calendar API validates the access token and calendar-viewing permissions (**OAuth2 Resource Server**). An employee who successfully logs into the Portal does not necessarily have the `calendar.read` permission or permission to view colleagues' calendars.

## 2. Identifying protocol actors and artifacts

| Concept | Role |
| --- | --- |
| **Resource Owner** | Entity that has rights to the data; in user-facing flows, typically the user. |
| **Client** | Application requesting access; here, the Spring MVC web app. |
| **Authorization Server** | Authenticates/prompts for consent, issues authorization codes and tokens. |
| **OpenID Provider (OP)** | Authorization Server that supports OIDC and issues ID tokens. |
| **Resource Server** | API that receives an access token to check permissions before returning resources. |
| **Client Registration** | Configuration holding client ID, provider, redirect URI, scopes, grant type, and optionally client secret. |
| **Principal / Authentication** | User/workload identified by Spring Security and its authorities in the application. |
| **Authorized Client** | Record binding a client and principal that has been granted a token to call APIs. |

A single provider can act as both an authorization server and an OIDC provider; a single application can also play multiple roles at the same time. However, you must distinguish them on **each request**: a browser talking to a web app with a session cookie is not the same as a backend calling an API with a bearer access token.

**Client ID** is usually a public identifier. **Client secret** is a secret for a server-side confidential client and must not be embedded into JavaScript, HTML, or a repository. **Redirect URI** must be accurately registered with the provider, pointing to the callback handled by Spring Security; avoid broad wildcard redirects or redirects built from untrusted input.

### 2.1 Four easily confused artifacts

**Authorization code** is a temporary value returned by the provider via the callback after the user logs in/consents. The backend exchanges the code at the token endpoint for tokens; the code is short-lived and typically single-use. Do not use the code as a bearer access token.

**Access token** represents the granted permission to call a resource. The client sends the access token to the **appropriate resource server**, for example:

```http
GET /v1/calendar HTTP/1.1
Host: calendar.example.net
Authorization: Bearer <access-token-for-calendar>
```

The token can be a JWT or opaque; the format of an access token **is not by default a contract for the client**, and it may be that only the resource server is supposed to interpret its contents. The API must validate the issuer, audience, scope/permissions, and relevant constraints according to the token format.

**ID token** is an OIDC JWT intended for the **client application** to confirm identity and the authentication event. Core claims typically include:

- `iss`: OpenID Provider that issued the ID token.
- `sub`: subject identifier of the user within the issuer.
- `aud`: audience; must include a valid client ID.
- `exp`, `iat`: expiration time and issued-at timestamp.
- `nonce`: if used in the authentication request, must be bound/verified according to the protocol.
- Optional claims such as `name`, `email`, `email_verified`, `auth_time` may or may not be present.

An ID token **is not an access token** for calling business APIs. Do not pass an ID token in `Authorization: Bearer` instead of an access token; the resource server should normally reject tokens of the wrong type or wrong audience.

**Refresh token** (if issued) helps the client obtain a new access token. It is not always present: it depends on the provider, grant, scopes, rotation policy, and consent. Protect refresh tokens like secrets; do not log them or return them arbitrarily to the frontend.

| Artifact | Used to | Should not do |
| --- | --- | --- |
| `code` | Exchange once for tokens at the token endpoint | Use long-term, log, or replay. |
| `access_token` | Call the right authorized resource server | Send to an API with the wrong audience, embed in URLs. |
| `id_token` | Authenticate identity in the OIDC client | Use as an API bearer token. |
| `refresh_token` | Request a new access token per provider policy | Send through the browser or log. |
| Session cookie like `JSESSIONID` | Browser maintains login session with the Servlet app | Treat it as a bearer access token for external services. |

**OIDC `openid`** is a request to use the OIDC authentication layer. `profile`/`email` may allow receiving additional claims or UserInfo, but they do not guarantee that email, name, or roles will be present. For a stable identifier, the **`iss` + `sub`** pair is generally more reliable than email, because an email can change or be unverified. Identity claims do not by themselves determine business authorization.

## 3. How does Authorization Code + OIDC work on Servlet?

Suppose the Spring MVC Portal runs at `http://localhost:8080`, has registration ID `idp`, and has a properly configured OIDC provider.

```text
Browser                    Spring MVC / Spring Security                   OIDC Provider
   |                                    |                                    |
   | GET /me                            |                                    |
   |----------------------------------->|                                    |
   | 302 /login (if not logged in)      |                                    |
   |<-----------------------------------|                                    |
   | GET /oauth2/authorization/idp      |                                    |
   |----------------------------------->|                                    |
   | 302 /authorize?...state=...        |                                    |
   |<-----------------------------------|                                    |
   | GET authorization endpoint                                              |
   |------------------------------------------------------------------------->|
   |                User login / consent if needed                           |
   | 302 callback?code=...&state=...                                          |
   |<-------------------------------------------------------------------------|
   | GET /login/oauth2/code/idp?code=...&state=...                            |
   |----------------------------------->|                                    |
   |                                    | POST token endpoint to exchange code|
   |                                    |----------------------------------->|
   |                                    | access token + ID token (+refresh?)|
   |                                    |<-----------------------------------|
   |                                    | Verify OIDC, build OidcUser        |
   |                                    | Save Authentication/authorized client|
   | 302 to target page                 |                                    |
   |<-----------------------------------|                                    |
   | GET /me + session cookie           |                                    |
   |----------------------------------->|                                    |
   | 200 JSON response                  |                                    |
   |<-----------------------------------|                                    |
```

**Step by step:**

1. `OAuth2AuthorizationRequestRedirectFilter` manages the default path `/oauth2/authorization/{registrationId}`, builds the authorization request with `client_id`, `scope`, `redirect_uri`, `response_type=code`, `state`, and related parameters. Spring saves the original request to match against the callback.
2. The browser is redirected to the provider; the Spring MVC application **does not receive the user's password**. The provider may require MFA, consent, or leverage an existing SSO session.
3. The provider redirects the browser back to the default callback `/login/oauth2/code/{registrationId}` with `code` and `state`. `OAuth2LoginAuthenticationFilter` receives the result, verifies correlation/appropriate conditions, and then exchanges the code at the token endpoint.
4. For OIDC, Spring Security verifies the ID token against the provider's metadata/public keys and appropriate claims/constraints (issuer, audience, expiration, nonce if used), optionally fetches UserInfo, and then creates an `OidcUser`.
5. OAuth2 Login creates an `Authentication` in `SecurityContext`, which is maintained via the session in the traditional web model. The browser typically only sends the session cookie to the application on subsequent requests.
6. OAuth2 Client can store an `OAuth2AuthorizedClient` so the backend can use the access token when calling external resource servers. **Do not automatically expose the access token to the browser or call arbitrary APIs with that token.**

**How state, nonce, and PKCE differ:**

- `state` binds the callback to the initial authorization request and serves as a defense against login CSRF/mix-up in the appropriate context. Do not skip verification just because the redirect callback "looks right."
- `nonce` helps bind the ID token to the authentication request in OIDC, reducing replay/token substitution when used per protocol.
- **PKCE** uses `code_challenge` and `code_verifier` to bind the authorization code to the initiating party; it is especially necessary for public clients and should be considered for confidential clients when supported by the provider/Spring. PKCE **does not replace `state` or nonce**. Whether PKCE is specifically enabled depends on client type/configuration; inspect the actual authorization request rather than assuming every flow already has PKCE.
- Valid redirect URIs, HTTPS, not leaking codes, and session controls are additional requirements. Do not disable validation to fix integration errors.

## 4. Related Spring Security components

| Component | Function |
| --- | --- |
| `ClientRegistration` | Holds client ID, grant, redirect URI, scopes, and provider endpoints. |
| `ClientRegistrationRepository` | Looks up a registration by `registrationId`, for example `idp`. |
| `OAuth2AuthorizationRequestRedirectFilter` | Initiates the request and redirects the browser to the authorization endpoint. |
| `AuthorizationRequestRepository` | Stores the original authorization request to verify the callback; by default typically tied to the session. |
| `OAuth2LoginAuthenticationFilter` | Handles the authorization code callback for login. |
| `OAuth2UserService` / `OidcUserService` | Creates the principal from user/provider information after the corresponding authentication step. |
| `Authentication` and `SecurityContext` | Stores the user and authorities in the application. |
| `OAuth2AuthorizedClient` | Binds the registration, principal, access token, and refresh token if present. |
| `OAuth2AuthorizedClientRepository` / `OAuth2AuthorizedClientService` | Saves and loads authorized clients per request/session or storage service. |
| `OAuth2AuthorizedClientManager` | Orchestrates authorize/re-authorize, supporting grants and refreshes appropriate to the configured provider. |

**Key distinction:** `oauth2Login()` enables the user login flow, while `oauth2Client()` provides client support for APIs. The two capabilities can share the same client registration and authorized client, but they do not automatically replace each other.

If a provider only supports OAuth2 login based on custom attributes, the principal is typically an `OAuth2User`. When requesting the `openid` scope with an OIDC provider, the principal can be an `OidcUser` with an ID token and UserInfo. Do not cast to `OidcUser` when using an OAuth2-only provider.

## 5. Complete example: Spring Boot MVC logging in via OIDC

Goal: a public page with a login link, and a `GET /me` endpoint restricted to logged-in users that returns the OIDC subject and granted scopes **without exposing tokens**. The example uses a **server-side confidential client**, not an SPA/browser public client.

### 5.1 Create the project and register the client at the provider

Create a Gradle project via Spring Initializr with **Spring Boot 3.x**, **Java 17+**, and the dependencies **Spring Web**, **Spring Security**, **OAuth2 Client**. Use the project's Gradle wrapper to run it. The provider must support OIDC discovery, the `openid` scope, the authorization-code grant, and the callback:

```text
http://localhost:8080/login/oauth2/code/idp
```

At the provider, register a real client ID/secret, exact redirect URI, and required scopes. For production, use HTTPS and a real domain. `idp` is a **custom registration ID in Spring** and must match the name in the config and the callback path. The `example.com` URLs below are **placeholders** only and cannot be used to log in without a real provider.

**`src/main/resources/application.yml`**

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          idp:
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          idp:
            issuer-uri: ${OIDC_ISSUER_URI}
```

An example issuer might look like `https://identity.example.com/realms/company`; the application needs a real issuer value matching the metadata published by the OP. Spring Boot automatically discovers the OIDC authorization/token/JWKS (and UserInfo if available) endpoints via `issuer-uri` when the provider supports discovery. Environment variables keep the client secret on the backend; do not commit it to Git.

### 5.2 Configure the Servlet SecurityFilterChain

**`src/main/java/com/example/oidcdemo/SecurityConfig.java`**

```java
package com.example.oidcdemo;

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
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/index.html", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
```

`oauth2Login` allows Spring Security to handle redirects/callbacks and establish login state. `oauth2Client` enables using OAuth2 authorized clients. By default, CSRF protection remains active for unsafe HTTP methods; this demo does not disable CSRF or permit all APIs merely because the user is logged in.

### 5.3 Controller reading OidcUser and authorized client

**`src/main/java/com/example/oidcdemo/MeController.java`**

```java
package com.example.oidcdemo;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal OidcUser user,
            @RegisteredOAuth2AuthorizedClient("idp")
                OAuth2AuthorizedClient client) {

        // Do not expose the ID token, access token, or refresh token.
        return Map.of(
            "subject", user.getSubject(),
            "grantedScopes", client.getAccessToken().getScopes()
        );
    }
}
```

This controller is designed for a standard **OIDC provider**; `OidcUser` is not appropriate if you switch to an OAuth2-only provider. `@RegisteredOAuth2AuthorizedClient("idp")` loads the authorized client for the current principal. It does not guarantee the token was granted every requested scope; read from the actual token rather than assuming permissions from the scopes requested in YAML.

### 5.4 HTML page and main application

**`src/main/resources/static/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>OIDC demo</title>
</head>
<body>
  <h1>OIDC Login</h1>
  <a href="/oauth2/authorization/idp">Sign in via IdP</a>
  <a href="/me">View identity</a>
</body>
</html>
```

**`src/main/java/com/example/oidcdemo/OidcDemoApplication.java`**

```java
package com.example.oidcdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(OidcDemoApplication.class, args);
    }
}
```

The Java files require Spring dependencies on the classpath and **cannot be run with plain `javac`**. Once a real provider and environment variables are configured, run from the project using the Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell: `.\gradlew.bat bootRun`. Visit `http://localhost:8080/` and click login. After the IdP completes the flow, open `/me`.

Example response payload (the subject value and scopes depend on the provider):

```json
{
  "subject": "employee-123",
  "grantedScopes": ["openid", "profile", "email"]
}
```

Even though it returns the subject, the endpoint still requires authentication; do not publish tokens. The HTTP session holds the login state for the **web app**; the authorized client holds the token so the backend can call **authorized APIs**. In a real environment, use authorities and business rules to check permission to view data.

## 6. OAuth2 Client sending an access token to a Resource Server

Suppose after login the backend needs to call `https://calendar-api.example.net/v1/calendar`. `OAuth2AuthorizedClient` represents a client that has been granted an access token; the application can obtain it from the request in a controller. The following **integration illustration** is a method inside a Spring MVC controller that has imported `@GetMapping`, `@RegisteredOAuth2AuthorizedClient`, and `OAuth2AuthorizedClient`; replace the API URL with a real endpoint:

```java
@GetMapping("/calendar")
public String calendar(
        @RegisteredOAuth2AuthorizedClient("idp")
            OAuth2AuthorizedClient client) {

    String accessToken = client.getAccessToken().getTokenValue();

    return org.springframework.web.client.RestClient.create()
        .get()
        .uri("https://calendar-api.example.net/v1/calendar")
        .headers(h -> h.setBearerAuth(accessToken))
        .retrieve()
        .body(String.class);
}
```

**Do not send an ID token instead of an access token**, and do not send an OIDC provider's access token to an external API that is not the intended audience. Whether the call succeeds depends on **audience, scope, consent, and resource server policy**. If the resource server returns 401/403, the completed login may still be valid; check the token type, expiration, issuer/audience, and API permissions.

`OAuth2AuthorizedClient` may contain a refresh token; token lifecycle management should use appropriate Spring Security mechanisms such as `OAuth2AuthorizedClientManager` with a provider that supports `refresh_token`. Directly reading `getAccessToken().getTokenValue()` **is not a contract for automatic refresh in all cases**. Do not write infinite retries, log tokens, or pass tokens in URLs.

**BFF/server-side model:** The browser only sends the session cookie to the Portal; the Portal uses the access token to call downstream APIs. This model reduces the need to keep access tokens in JS, but you must still protect the session cookie, CSRF, and authorization.

### 6.1 Client credentials vs. OAuth2 Login

Service-to-service calls or batch jobs running without a user typically need **`client_credentials`**. It does not generate an OIDC ID token or a user HTTP session, and does not require a login screen. Example of a separate registration:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          service-api:
            provider: machine-idp
            client-id: ${SERVICE_CLIENT_ID}
            client-secret: ${SERVICE_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - api.read
        provider:
          machine-idp:
            token-uri: https://identity.example.com/oauth2/token
```

A manager for code running **outside an HttpServletRequest** can use `AuthorizedClientServiceOAuth2AuthorizedClientManager` with a client-credentials provider. This is a **bean snippet** (requiring imports of the relevant types from Spring OAuth2 Client), not a replacement for the entire OIDC example above:

```java
@Bean
OAuth2AuthorizedClientManager backgroundClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService authorizedClients) {

    var provider = OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();

    var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        registrations, authorizedClients
    );
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
```

When calling `manager.authorize(...)`, create an `OAuth2AuthorizeRequest` with `clientRegistrationId="service-api"` and a stable principal such as `"scheduled-job"`, verify the result is non-null, and then use the access token against the proper Resource Server. This principal serves authorized client management, **not an end user**. In an application with both login and background jobs, design the manager/authorized-client providers for each grant and actual context.

## 7. OAuth2 Login does not automatically turn an application into a Resource Server

**Web user calling a logged-in application via session:**

```http
GET /me HTTP/1.1
Host: portal.example.com
Cookie: JSESSIONID=<session-id>
```

Spring Security Servlet retrieves the `SecurityContext` associated with the session. Do not require the browser to send an ID token in a header to read `/me`.

**A mobile app/service calling an API with a bearer token:**

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token-for-orders-api>
```

If the backend needs to handle the second request, it must implement **OAuth2 Resource Server** (JWT validation or opaque-token introspection, issuer/audience/scope, and API permissions). Merely adding `spring-boot-starter-oauth2-client` + `oauth2Login()` does not make an API verify incoming bearer tokens.

An application can support both browser sessions and bearer APIs, but the filter chains, entry points, CSRF, session, and authorization must be carefully designed. Just because OIDC Login is present does not mean API endpoints should accept access tokens from every provider.

### 7.1 Roles/authorities do not appear automatically from OIDC

A user whose identity has been verified does not necessarily have `ROLE_ADMIN`. `openid` provides the identity mechanism; groups/roles may be provider-specific claims that need to be mapped to `GrantedAuthority` or fetched from an internal authorization system under trusted rules. Example SecurityConfig variant:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/", "/index.html", "/error").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
)
```

This is a **replacement snippet** in the DSL, not a complete program. If `ROLE_ADMIN` has not been mapped, `/admin/**` requests being blocked is expected. Check object-level authorization, ownership, and tenant boundaries on the backend instead of trusting roles/emails sent by the client.

## 8. Security across the login and token lifecycle

### 8.1 When initiating and handling redirects

- **State** must bind the callback to the initiating login request; do not skip verification or reuse authorization requests indefinitely.
- **OIDC nonce** is verified according to the appropriate OIDC flow; do not treat nonce as an access token.
- **PKCE** should follow the rules of the client type/provider; HTTPS and an exact redirect URI are still required.
- **Callback** must be on a domain/port/scheme allowed by the provider. Especially behind a reverse proxy, configure the external base URL and forwarded headers from **trusted** proxies to avoid wrong redirects; do not trust arbitrary forwarding data supplied by the client.
- Do not use overly broad wildcard redirects or attach codes/tokens to URLs where they could leak to third parties.

### 8.2 When storing sessions and tokens

- For a Servlet web app, `SecurityContext` is usually maintained in the HTTP session; production session cookies require HTTPS, appropriate Secure and HttpOnly flags, sensible SameSite/domain/path, and session-fixation protection.
- Logging in via OIDC **does not disable CSRF** for POST/PUT/PATCH/DELETE when the application uses cookie sessions. OAuth2 `state` protects the callback during the login flow and does not replace CSRF tokens for business operations.
- Access tokens/refresh tokens belong to backend-managed components; do not print them in logs, attach them to query strings, or return them in `/me` JSON. Protect storage and access permissions; if multiple servers share sessions/tokens, design appropriate storage.
- Refresh tokens can expire, rotate, or be revoked; handle refresh failures by reauthorizing/re-logging in when needed, not with infinite retries.
- **App logout differs from IdP logout**. Clearing the Portal session does not necessarily end the SSO session at the provider; if Single Logout is required, implement OIDC RP-initiated logout or a provider-supported mechanism.

### 8.3 When identifying users and permissions

- Properly validate issuer/audience/signature/expiry and nonce; do not just base64-decode an ID token and trust it as an identity.
- The **`iss + sub`** pair is more suitable than email as a long-term account-linking identifier; email can change, be absent, or be unverified.
- **Access token scope** is a resource-related permission; **data access permissions in the app** still require explicit mapping and checks.
- A token issued for resource A is not implicitly usable at resource B; APIs must validate audience and authorization.

## 9. Verifying in a browser and with an HTTP client

After filling in a real provider and running the application:

**Check the authorization redirect:**

```bash
curl -i http://localhost:8080/oauth2/authorization/idp
```

You typically see HTTP **302** with `Location` pointing to the authorization endpoint containing `client_id`, `response_type=code`, `redirect_uri`, `scope`, and `state`. `nonce`, PKCE challenge, or other parameters may appear depending on the provider/config. `curl` only verifies the initial redirect and **does not simulate full interactive login/consent**.

**Check with a browser:**

1. Open `http://localhost:8080/` and click the login link.
2. In DevTools → Network, inspect the redirect chain to the IdP and the `/login/oauth2/code/idp` callback; avoid copying or sharing codes/tokens/cookies in URLs and headers.
3. Log in at the provider, confirm you return to the web app with a valid session cookie. Visit `GET /me` to see the subject/scopes matching the IdP data.
4. Clear the session or log out, then access `/me`: when unauthenticated, you should typically be redirected to the login page (unless using a custom entry point). If the IdP still has an SSO session, you may log back in without entering a password.
5. For external APIs, verify the access token is sent to the **right audience** and has the actual scopes; distinguish 401 (invalid token/identity) from 403 (insufficient permissions).

**Check failure cases:** a wrong redirect URI may be rejected by the provider; losing the session/state between redirect and callback usually causes login to fail; changing to a wrong issuer/JWKS must be rejected; a POST to the app missing a CSRF token when using sessions may return 403 even if OIDC login succeeded.

## 10. Integration troubleshooting table

| Symptom | Possible cause | How to verify and resolve |
| --- | --- | --- |
| Cannot reach `/oauth2/authorization/idp` | Missing OAuth2 Client dependency, wrong registration ID, client config not created. | Check starter, `spring.security.oauth2.client.registration.idp`, and route. |
| Provider reports `redirect_uri_mismatch` | Callback differs from registered URI: port, scheme, host, proxy. | Compare `redirect_uri` in the request against the provider allowlist; audit proxy URL. |
| Cannot read OIDC metadata | Wrong `issuer-uri`, provider does not support discovery, network/TLS error. | Check issuer and discovery endpoint over a trusted connection; do not disable TLS. |
| Callback reports invalid state/missing authorization request | Session lost, cookie not sent, state mismatch, cluster not sharing sessions. | Check session cookie, SameSite/Secure, proxy, session storage, and callback. |
| ID token invalid / issuer / audience / nonce | Provider returned an invalid token or config is wrong. | Check issuer, client ID, clock, public keys/metadata; do not skip validation checks. |
| Principal is not `OidcUser` | Using an OAuth2-only provider or `openid` scope missing/invalid. | Use `OAuth2User` for OAuth2-only, or configure OIDC properly. |
| `@RegisteredOAuth2AuthorizedClient` has no client | Wrong registration, principal/session changed, authorized client not saved. | Check registration ID, authenticated principal, and client repository/service. |
| Logged in, but external API returns 401 | Access token for wrong resource, expired, missing bearer header, wrong issuer/audience. | Use an access token meant for the API; check token lifecycle and resource server. |
| External API returns 403 | Token is valid but lacks scope/role/data permissions. | Check actual consent/scopes and API-side authorization. |
| Portal continuously redirects to login | Cookie/session lost, callback failing, wrong URL/proxy. | Check Network and session cookie; protect multi-instance configuration. |
| Logged out, but logging in again does not ask for password | IdP still has an SSO session. | Distinguish local logout from OP logout; design OIDC logout if required by business needs. |

## 11. Choosing the right mechanism for your application

| Scenario | Key configuration to consider | Interactive user? |
| --- | --- | --- |
| Spring MVC web app with SSO login | `oauth2Login` + OIDC registration | Yes |
| Web Portal logs in then calls API on user's behalf | OIDC Login + OAuth2 Client + right API scopes/audience | Yes |
| Background job calling API as a service identity | OAuth2 Client with `client_credentials` | No |
| REST API validating Bearer JWT/opaque token | OAuth2 Resource Server | Not necessarily |
| App accepting both browser cookies and bearer APIs | Carefully combine session login and resource-server filters/authorization | Depends on request |
| SPA public client logging in directly from browser | Authorization Code + PKCE, no client secret in frontend | Yes |

**Checklist:** Identify the exact roles; use trusted providers/issuers; store client secrets safely; configure exact redirect URIs; handle state/nonce/PKCE properly; do not confuse ID tokens and access tokens; keep session/cookies, CSRF, and permissions correct; map claims/roles in a controlled way; ensure APIs verify audience/scope; protect tokens and manage refresh/logout; test both successful login and failed callback, session, and API permission cases.

**Remember:** **OAuth2 Client** manages permissions and access tokens to **call APIs**; **OAuth2 Login** establishes the **user session** in Spring Security Servlet; **OIDC** provides **standard identity authentication** based on ID tokens. These three capabilities complement each other, but they do not replace the role of a Resource Server or the application's authorization logic.
