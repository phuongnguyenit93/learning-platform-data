# 12.3. Configuring the UserInfo Endpoint and Sending the Access Token

## 1. Where Does the UserInfo Endpoint Fit in the OIDC Login Process?

In a **Spring Security OAuth 2.0 OIDC Client** system, users normally log in using the **Authorization Code flow**. After exchanging the authorization code at the token endpoint, the application receives an **ID Token** and an **Access Token**. The ID Token provides the information needed for the client to authenticate the user under OpenID Connect (OIDC); the Access Token can allow the client to query additional profile information at the **UserInfo Endpoint** published by the OpenID Provider (OP).

Consider a Spring Boot web application that wants to display an employee's name, avatar, and email after login. The ID Token might contain only minimal claims such as `iss`, `sub`, `aud`, and `exp`. Details like `name`, `picture`, or `email` can be provided by the OP via UserInfo. To call the right endpoint, Spring Security needs to know the **UserInfo URL** and **how to send the Access Token**.

This lesson focuses on:

1. The role of UserInfo in OIDC and how it differs from the ID Token.
2. Configuring `user-info-uri` via OIDC Discovery or explicit provider configuration.
3. Ways to send the Access Token: **Bearer Authorization header**, form body, and query string.
4. How Spring Security Servlet uses `OidcUserService` and `DefaultOAuth2UserService`.
5. `sub` verification rules, handling missing claims, HTTP errors, and security requirements.

**Scope:** Examples primarily apply to Spring Boot using **Spring MVC/Servlet** with `HttpSecurity` and `SecurityFilterChain`. WebFlux uses different reactive components; do not copy Servlet configuration verbatim into WebFlux.

## 2. UserInfo Is Neither an ID Token Nor a Business API

Three components often appear together but serve different purposes:

| Component | Where It Comes From | Purpose | Who Uses It |
| --- | --- | --- | --- |
| **ID Token** | Token Endpoint in a valid OIDC flow | Proof of authentication under OIDC, after client verification | OIDC Client |
| **Access Token** | Token Endpoint | Grants access to authorized resources/endpoints | UserInfo Endpoint or corresponding Resource Server |
| **UserInfo response** | UserInfo Endpoint | Provides sharable claims about the user | OIDC Client, after identity comparison |

**UserInfo is an endpoint and its response data, not a third kind of token.** Nor can you obtain an Access Token from UserInfo; the Access Token is issued at the Token Endpoint and used by the client when calling UserInfo.

For example, a decoded ID Token for illustration:

~~~json
{
  "iss": "https://id.example.com/realms/company",
  "sub": "user-4a7f",
  "aud": "portal-web",
  "iat": 1925000000,
  "exp": 1925003600
}
~~~

The UserInfo response may provide additional data:

~~~json
{
  "sub": "user-4a7f",
  "name": "Nguyen An",
  "preferred_username": "an.nguyen",
  "email": "an@example.com",
  "email_verified": true,
  "picture": "https://cdn.example.com/avatars/u4a7f.png"
}
~~~

The application **must never look only at email or name and assume it is the same user**. In OIDC, UserInfo's `sub` field must match `sub` in the verified ID Token; if they do not match, **do not use the UserInfo response**.

### 2.1. UserInfo Endpoint Differs from Pure OAuth 2.0 Profile APIs

An **OAuth 2.0 provider that does not support OIDC** may still expose an API like `/api/me` returning JSON:

~~~json
{
  "id": 789,
  "displayName": "Nguyen An",
  "account": "an.nguyen"
}
~~~

This API can be called by Spring Security's `DefaultOAuth2UserService` via `user-info-uri` configuration, but **it is not automatically an OIDC UserInfo Endpoint**: pure OAuth 2.0 does not standardize ID Tokens or the `UserInfo.sub == IDToken.sub` constraint.

Therefore:

- For **OIDC**, use `openid`, verify the ID Token, and compare UserInfo's `sub`.
- For **pure OAuth2 Login**, identify the stable identifier field per the provider's contract, such as `id`, via `user-name-attribute`.
- For **business APIs** such as orders/work schedules, use an HTTP client calling the **appropriate Resource Server** rather than treating that API as UserInfo.

## 3. Flow of Calling UserInfo in Authorization Code + OIDC

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant Client as Spring Boot Servlet OIDC Client
    participant OP as OpenID Provider
    Browser->>Client: Open /me unauthenticated
    Client-->>Browser: Redirect to /oauth2/authorization/company
    Browser->>OP: Authorization request (openid profile email, state, PKCE...)
    OP-->>Browser: Callback with code + state
    Browser->>Client: GET /login/oauth2/code/company?code=...
    Client->>OP: POST Token Endpoint with code
    OP-->>Client: Access Token + ID Token
    Client->>Client: Verify ID Token (signature, iss, aud, exp, nonce if applicable)
    opt UserInfo is configured and profile needs loading
        Client->>OP: GET UserInfo Endpoint - Authorization: Bearer Access Token
        OP-->>Client: UserInfo response with sub and permitted claims
        Client->>Client: Verify UserInfo.sub == ID Token.sub
    end
    Client-->>Browser: Complete Authentication and session
    Browser->>Client: GET /me with session
    Client-->>Browser: Only claims the application chooses to expose
~~~

Notice the **path of the Access Token**: it is sent **from the client backend to the UserInfo Endpoint over HTTPS**, without needing to pass through frontend JavaScript, browser URLs, or HTML pages. For server-side Servlet applications, this is a *back-channel request* model.

Calling UserInfo **does not necessarily occur on every login or every page load**. Spring Security may decide to load UserInfo during principal construction depending on provider configuration, grant, scopes, and user service; afterwards, the application uses the principal already stored in SecurityContext/session.

## 4. Configuring UserInfo via OIDC Discovery

### 4.1. How Does Discovery Find the Endpoint?

An OIDC Provider may publish a metadata document, usually at a standard path based on the issuer:

~~~text
Issuer:
  https://id.example.com/realms/company

OpenID Provider Configuration:
  https://id.example.com/realms/company/.well-known/openid-configuration
~~~

Shortened metadata example:

~~~json
{
  "issuer": "https://id.example.com/realms/company",
  "authorization_endpoint": "https://id.example.com/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://id.example.com/realms/company/protocol/openid-connect/token",
  "jwks_uri": "https://id.example.com/realms/company/protocol/openid-connect/certs",
  "userinfo_endpoint": "https://id.example.com/realms/company/protocol/openid-connect/userinfo"
}
~~~

These URLs are **illustrative examples**, not live endpoints of a specific provider. A provider may structure its paths differently. `userinfo_endpoint` is the field name in **OIDC Discovery metadata**; Spring Security maps it into `ClientRegistration.ProviderDetails.UserInfoEndpoint`.

### 4.2. application.yml Using issuer-uri

A common configuration in Spring Boot Servlet:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
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
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

With valid OIDC Discovery, Spring Boot/Spring Security retrieves the endpoints, including the **UserInfo URI if published by the provider**. You do not necessarily need to copy `user-info-uri` from metadata into YAML.

**Key points:**

- `issuer-uri` identifies the trusted issuer and discovers metadata; it is **not the UserInfo URL**.
- `registration.company` is a client registration, while `provider.company-oidc` is the provider configuration.
- `openid` switches login into OIDC mode; `profile` and `email` request corresponding claims per OP policy.
- Secrets come from environment variables or a secret manager; never commit them to source control.
- OIDC discovery may require network access when initializing the registration; if the issuer is unreachable or metadata is invalid, the application may fail at startup.

In many common configurations, **setting `issuer-uri` is preferable to configuring individual endpoints**, because it keeps the token endpoint, JWKS, UserInfo, and issuer synchronized with the OP's actual metadata.

## 5. Explicit UserInfo URI Configuration

Not every provider publishes complete discovery metadata. For a **pure OAuth2 provider** with its own profile API, you can specify the URIs explicitly:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          community:
            provider: community-oauth
            client-id: ${COMMUNITY_CLIENT_ID}
            client-secret: ${COMMUNITY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile.read
        provider:
          community-oauth:
            authorization-uri: https://auth.example.net/oauth/authorize
            token-uri: https://auth.example.net/oauth/token
            user-info-uri: https://api.example.net/v1/me
            user-info-authentication-method: header
            user-name-attribute: id
~~~

In the example above, the provider **is not assumed to be OIDC** because the registration does not request `openid` and has no standard ID Token. `user-name-attribute: id` tells Spring Security to pick the `id` field from the profile API response as the principal identifier for `OAuth2User`.

Example API JSON:

~~~json
{
  "id": "member-789",
  "display_name": "Nguyen An",
  "email": "an@example.com"
}
~~~

If the provider uses `user_id` instead of `id`, change `user-name-attribute` according to the official documentation. If the JSON is deeply nested or requires special headers, you may need a custom `OAuth2UserService`.

### 5.1. Mapping Between Spring Boot Properties and Java API

| Spring Boot Property | Member in ClientRegistration | Meaning |
| --- | --- | --- |
| `spring.security.oauth2.client.provider.<id>.user-info-uri` | `getProviderDetails().getUserInfoEndpoint().getUri()` | URI for loading claims/profile |
| `...user-info-authentication-method` | `getUserInfoEndpoint().getAuthenticationMethod()` | How the Access Token is sent |
| `...user-name-attribute` | `getUserInfoEndpoint().getUserNameAttributeName()` | Identifier field in an OAuth2 UserInfo-like API response |
| `...issuer-uri` | `getProviderDetails().getIssuerUri()` | OIDC issuer, discovery entry point |
| `...authorization-uri` | `getProviderDetails().getAuthorizationUri()` | Authorization Endpoint |
| `...token-uri` | `getProviderDetails().getTokenUri()` | Token Endpoint |
| `...jwk-set-uri` | `getProviderDetails().getJwkSetUri()` | JWKS URL |

`<id>` in the table is only a placeholder for the provider ID. In actual YAML, use names like `company-oidc` or `community-oauth`; **do not put `<`/`>` characters in configuration keys**.

**For an OIDC provider, never configure an arbitrary set of endpoints that bypasses issuer, JWKS, and ID Token checks.** When a provider does not support discovery, creating an explicit registration must be accompanied by trusted and complete configuration for OIDC validation.

### 5.2. Reading the Configured UserInfo Endpoint

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

public final class ProviderDetailsInspector {

    private final ClientRegistrationRepository repository;

    public ProviderDetailsInspector(ClientRegistrationRepository repository) {
        this.repository = repository;
    }

    public String userInfoUri() {
        ClientRegistration registration =
            repository.findByRegistrationId("company");

        if (registration == null) {
            throw new IllegalStateException("Missing registration: company");
        }

        return registration.getProviderDetails()
            .getUserInfoEndpoint().getUri();
    }
}
~~~

`ClientRegistrationRepository` and `ProviderDetails` only describe configuration; **reading the URI does not send an HTTP request**. HTTP calls are handled by the corresponding user service or HTTP client.

## 6. Three Ways to Send the Access Token to UserInfo

The OIDC UserInfo Endpoint is protected by an Access Token. With a Bearer Token, the token transmission mechanism can use the HTTP Authorization header, form body, or URI query according to the applicable rules of OAuth 2.0 Bearer Token Usage.

### 6.1. Preferred Method: Authorization Header

HTTP request:

~~~http
GET /realms/company/protocol/openid-connect/userinfo HTTP/1.1
Host: id.example.com
Accept: application/json
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Meaning:

- `Authorization` is the HTTP header used to carry the Bearer credential.
- `Bearer` is the token type; what follows is the Access Token value issued by the Token Endpoint.
- The UserInfo Endpoint validates the token and returns the claims permitted by the OP.
- There is no need to put the Access Token in a query string or browser route.

This is generally easier to implement and safer than query tokens, provided the connection uses **HTTPS**, TLS is verified, and the application does not log the Authorization header.

Spring Boot configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-oidc:
            user-info-authentication-method: header
~~~

This snippet **illustrates the property** and is not a complete standalone YAML: the actual provider and registration must still be defined. When the provider supports passing Bearer tokens via header, a custom user service is normally unnecessary.

### 6.2. Form-Encoded Body When Required by the Provider

Bearer Token Usage also describes passing the token in a form body with `application/x-www-form-urlencoded` subject to that mechanism's constraints:

~~~http
POST /userinfo HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

access_token=ACCESS_TOKEN_VALUE
~~~

Use this only when the provider actually supports/requires it. The Access Token is in the **request body**, not the JSON profile response.

Corresponding configuration if the provider accepts it:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-oidc:
            user-info-authentication-method: form
~~~

Do not switch to `form` trying to "fix" a 401 error when the provider expects a Bearer header. First verify whether the token has the right issuer, audience/resource, scopes, and has not expired.

### 6.3. Token in Query String: Avoid

A URL might look like:

~~~http
GET /userinfo?access_token=ACCESS_TOKEN_VALUE HTTP/1.1
Host: id.example.com
~~~

This is documented for certain compatibility scenarios but is **discouraged** whenever another option exists because URIs are frequently recorded in access logs, tracing, monitoring, reverse proxy logs, browser history, or analytics systems.

A legacy provider might require:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          legacy-provider:
            user-info-authentication-method: query
~~~

Only use it after risk assessment and confirming it is a mandatory contract. For new systems, prefer **`header`**.

### 6.4. Comparing the Methods

| Method | Access Token Location | Strengths | Risks / Notes |
| --- | --- | --- | --- |
| `header` | `Authorization: Bearer ...` | Standard, widely supported, avoids placing token in URI | Must protect header from logs/traces, use HTTPS |
| `form` | Body `access_token=...` of a POST form | Useful if the provider only supports this form | Body is also sensitive; requires right content type/method |
| `query` | `?access_token=...` | Compatible with some legacy APIs | URLs are easily logged/leaked; avoid |

**Do not send the same Access Token in multiple locations within a single request.** Sending a Bearer Token via multiple methods simultaneously is prohibited by standard Bearer Token Usage; choose **one** method matching the provider's contract.

### 6.5. Do Not Confuse UserInfo Authentication with Client Authentication

Two properties have similar names but apply to different steps:

| Property | When It Applies | Example Values |
| --- | --- | --- |
| `client-authentication-method` | Client authenticates to the **Token Endpoint** when requesting tokens | `client_secret_basic`, `client_secret_post`, `private_key_jwt`, `none` depending on client |
| `user-info-authentication-method` | Client sends **Access Token to the UserInfo Endpoint** | `header`, `form`, `query` |

Do not use `client-secret` in place of an Access Token when calling UserInfo. For a Bearer-style UserInfo request, the client presents the **authorized user's Access Token**, not an ID Token or client credentials.

## 7. What Does the UserInfo Endpoint Return?

In OIDC, a UserInfo response can contain `sub` and various profile claims:

~~~json
{
  "sub": "user-4a7f",
  "name": "Nguyen An",
  "given_name": "An",
  "family_name": "Nguyen",
  "preferred_username": "an.nguyen",
  "email": "an@example.com",
  "email_verified": true,
  "locale": "vi-VN",
  "picture": "https://cdn.example.com/avatars/u4a7f.png"
}
~~~

### 7.1. Permitted Claims Do Not Mean Claims Are Always Returned

Common OIDC scopes:

| Scope | Commonly Associated Claims | Notes |
| --- | --- | --- |
| `openid` | OIDC identity via ID Token | Required for OIDC login |
| `profile` | `name`, `given_name`, `family_name`, `preferred_username`, `picture`, `locale`... | Claims may be missing due to user/provider policy |
| `email` | `email`, `email_verified` | Email may not exist or be unverified |
| `phone` | `phone_number`, `phone_number_verified` | Depends on provider and consent |
| `address` | `address` | May be an object containing sensitive personal data |

If `email` is requested and UserInfo does not return an email, **do not automatically treat that as an authentication failure**; check the OP's claim-release policy and how the application handles missing data.

### 7.2. Mandatory Rule: Matching `sub`

Example verified ID Token:

~~~json
{
  "iss": "https://id.example.com/realms/company",
  "sub": "user-4a7f",
  "aud": "portal-web"
}
~~~

Unexpected UserInfo response:

~~~json
{
  "sub": "user-OTHER",
  "email": "an@example.com"
}
~~~

**You must reject using this UserInfo data**, because `user-OTHER` does not equal `user-4a7f`. Having the same email or display name in both responses does not resolve a subject mismatch.

In Spring Security, `OidcUserService` performs the appropriate OIDC retrieval and validation logic; using the default implementation is generally safer than calling UserInfo manually and arbitrarily merging claims onto the principal.

### 7.3. Account Identification Key

For OIDC, a durable identifier should be based on **`issuer + subject`**, not email alone:

~~~text
trusted_issuer                                subject        internal_user_id
https://id.example.com/realms/company        user-4a7f      1207
https://login.partner.example.net            user-4a7f      9815
~~~

Two rows with the same `sub` but different issuers **do not automatically represent the same user**. If you need to link accounts across providers, have a dedicated ownership-verification workflow and account-linking policy.

### 7.4. Should UserInfo Be Called on Every HTTP Request?

No. UserInfo primarily serves to **build the principal** during login or sync claims when explicitly designed by the application. After login succeeds, `OidcUser` can be retrieved from SecurityContext/session.

Calling UserInfo again on every request:

- Increases latency and network/OP dependency.
- Increases how often the Access Token is transmitted.
- May hit rate limits, throttling, or token expiration.
- Does not guarantee fresh data if the provider caches claims.

If refreshed profile data is required, define an explicit refresh strategy, lifecycle, and permissions rather than implicitly calling UserInfo in every controller.

## 8. Which Components Does Spring Security Servlet Use to Handle UserInfo?

### 8.1. Related Classes

| Component | Role |
| --- | --- |
| `ClientRegistration` | Describes client, grant, scopes, provider |
| `ClientRegistration.ProviderDetails.UserInfoEndpoint` | Configures URI, authentication method, and user-name attribute |
| `OAuth2AccessTokenResponseClient` | Retrieves tokens from the Token Endpoint |
| `DefaultOAuth2UserService` | Fetches attributes from a UserInfo-like endpoint in OAuth2 Login flows |
| `OidcUserService` | Creates the OIDC principal, may query UserInfo and enforce OIDC conditions |
| `OAuth2UserRequest` | Request to load an OAuth2 user with client registration and Access Token |
| `OidcUserRequest` | OIDC user request carrying additional ID Token information |
| `OAuth2User` | Principal for OAuth2 Login |
| `OidcUser` | OIDC principal with ID Token and optional UserInfo |
| `OAuth2AuthorizedClient` | Access Token/Refresh Token issued for the client/principal |

**Two different services:** `DefaultOAuth2UserService` typically serves pure OAuth2 providers, whereas `OidcUserService` coordinates OIDC identity (and may use an OAuth2 user service to call UserInfo).

### 8.2. Spring Security Does Not Always Call UserInfo

Having a UserInfo URI in metadata **does not guarantee a UserInfo request will always occur**. Contributing factors include:

1. Whether the registration is using **OIDC** (`openid` scope).
2. Whether the OP publishes `userinfo_endpoint`.
3. Whether the authorization grant and Access Token are applicable.
4. Requested scopes/claims and `OidcUserService` decisions per version.
5. Whether the application has a custom user service or policy skipping UserInfo.

For example, when requesting only `openid`, the application can complete identity verification from the ID Token **without querying UserInfo**. When profile claims are needed, verify `profile`/`email` scopes and user service policy, while also not expecting the provider to return every claim.

If `user.getUserInfo() == null`, it may simply mean UserInfo was not loaded or not provided; **do not conclude that the verified ID Token is invalid**.

## 9. Spring Boot and SecurityFilterChain Configuration Examples

### 9.1. Servlet OAuth2 Client Dependencies

With Spring Boot 3.x, `build.gradle` may include:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

With Spring Boot 4.x, the corresponding starters are named `spring-boot-starter-webmvc` and `spring-boot-starter-security-oauth2-client`. Choose according to your actual Boot version and dependency management/BOM; do not arbitrarily mix Spring Security versions.

### 9.2. SecurityFilterChain for OIDC Login

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(userInfo -> {
                    // You can configure userService/oidcUserService here.
                    // The default example does not need to replace the services.
                }))
            .build();
    }
}
~~~

This example highlights the `oauth2Login().userInfoEndpoint(...)` DSL. In standard cases, you can use `.oauth2Login(Customizer.withDefaults())` to let Spring Security automatically manage OIDC Login, UserInfo services, and callback handling.

Declaring `userInfoEndpoint` here **does not replace** `user-info-uri`/`issuer-uri` on `ClientRegistration`. One part of configuration describes the endpoint; the other customizes the user-processing service.

### 9.3. Reading OIDC Data in a Controller

~~~java
package com.example.web;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("issuer", user.getIdToken().getIssuer().toString());
        result.put("subject", user.getSubject());
        result.put("displayName", user.getFullName());

        if (user.getUserInfo() != null) {
            result.put("userInfoAvailable", true);
            // Select only claims permitted for display.
        } else {
            result.put("userInfoAvailable", false);
        }

        return result;
    }
}
~~~

This controller **does not call UserInfo itself**; it reads the principal already built after OIDC login. In a system accepting both pure OAuth2 Login and OIDC Login, not every principal will be an `OidcUser`; handle `OAuth2User` accordingly.

**Do not return `getIdToken().getTokenValue()`, Access Token, Refresh Token, or all of `getClaims()` to the browser**. That data may contain sensitive information not needed by the UI.

## 10. Customizing the Request Sent to UserInfo for Special Provider Requirements

For an OIDC-compliant provider that accepts a Bearer header, Spring Security's default is usually sufficient. Only customize when you need a provider-documented custom header, specific HTTP timeouts, or a special request structure.

### 10.1. Customizing DefaultOAuth2UserService

`DefaultOAuth2UserService` allows customizing the `RequestEntity` used to query the endpoint. The example below **still sends the Access Token via the Authorization header**:

~~~java
package com.example.security;

import java.net.URI;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.RequestEntity;
import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;

public final class UserInfoServices {

    private UserInfoServices() {}

    public static DefaultOAuth2UserService oauth2UserService() {
        DefaultOAuth2UserService service = new DefaultOAuth2UserService();

        service.setRequestEntityConverter(userRequest -> {
            String uri = userRequest.getClientRegistration()
                .getProviderDetails()
                .getUserInfoEndpoint()
                .getUri();

            if (uri == null || uri.isBlank()) {
                throw new IllegalStateException("UserInfo URI is not configured");
            }

            String accessToken = userRequest.getAccessToken().getTokenValue();

            return RequestEntity.get(URI.create(uri))
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
                .accept(MediaType.APPLICATION_JSON)
                .build();
        });

        return service;
    }

    public static OidcUserService oidcUserService() {
        OidcUserService oidcService = new OidcUserService();
        oidcService.setOauth2UserService(oauth2UserService());
        return oidcService;
    }
}
~~~

**How to read this code:**

- `OAuth2UserRequest` supplies the `ClientRegistration` and received **Access Token**.
- The service obtains the **UserInfo URI from provider configuration**, never from user input.
- `RequestEntity.get(...)` constructs a GET request; `Authorization: Bearer` places the token in the header.
- `OidcUserService` can use `DefaultOAuth2UserService` to load UserInfo while preserving its OIDC logic.
- If `user-info-uri` is absent, the example proactively rejects rather than constructing a URL from the issuer.

This example is a **customization pattern**. You do not need to apply it just to enable the default Bearer header. If a provider requires `form` or `query`, prefer configuring `user-info-authentication-method` accurately when supported by Spring Security rather than writing a custom request builder that bypasses protocol constraints.

### 10.2. Wiring Custom User Services in the Servlet DSL

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CustomUserInfoConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(endpoint -> endpoint
                    .userService(UserInfoServices.oauth2UserService())
                    .oidcUserService(UserInfoServices.oidcUserService())))
            .build();
    }
}
~~~

This is an **alternative SecurityFilterChain** replacing the default example from the earlier section, not a second chain to run in parallel. If a project has multiple `SecurityFilterChain` beans, attach the user services to the chain that actually handles the OAuth2/OIDC Login callbacks.

### 10.3. Guarantees to Preserve When Customizing

When customizing `DefaultOAuth2UserService` or `OidcUserService`:

1. **Never send an ID Token instead of an Access Token** in the HTTP request to UserInfo.
2. Never take the UserInfo URI from a query parameter or an unverified JWT; only use a trusted configured provider.
3. Never disable TLS certificate/hostname verification.
4. For OIDC, preserve checking that **UserInfo `sub` matches ID Token `sub`**.
5. Never skip ID Token, issuer, audience, or nonce verification just to make an API return 200.
6. Never log the `Authorization` header, tokens, or the entire UserInfo response.
7. Use sensible timeouts/connection pools under high traffic; avoid hanging login requests on slow endpoints.

If a provider returns a signed or encrypted JWT from UserInfo instead of plain JSON, that is a **response type with distinct verification requirements** under OIDC. Do not parse it as unverified JSON, and do not assume `DefaultOAuth2UserService` supports every response variant by default; check library capabilities and OP/client algorithm registration.

## 11. Querying UserInfo Manually Over HTTP: When and How?

Sometimes an application needs to call UserInfo again **after login**, such as when the user triggers a profile sync. In such cases, prefer the existing principal data and only make a separate HTTP request if business logic genuinely requires fresh claims.

A manual operation requires:

- A valid Access Token **issued for the UserInfo Endpoint**.
- A trusted URI retrieved from ClientRegistration/metadata.
- A Bearer Authorization header if supported by the provider.
- Timeouts, error handling, security policy, and logging restrictions.
- Comparing the `sub` claim against the verified OIDC identity before updating the profile.

Example **illustrating how to build a request with RestClient** (excluding full logic for retrieving the authorized client):

~~~java
import java.util.Map;
import org.springframework.web.client.RestClient;

public final class UserInfoHttpClient {

    private final RestClient restClient = RestClient.create();

    public Map<?, ?> fetch(String trustedUserInfoUri, String accessToken) {
        return restClient.get()
            .uri(trustedUserInfoUri)
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(Map.class);
    }
}
~~~

This example is only appropriate when **both parameters come from trusted server-side sources**, never user input. It does **not yet** handle timeouts, status error codes, special JSON structures, or `sub` verification; add those before production use. For applications using the default `OidcUserService`, writing this class is normally **unnecessary**.

In real applications, retrieve the Access Token using the appropriate `OAuth2AuthorizedClient`/`OAuth2AuthorizedClientManager` mechanism and call the endpoint per contract. Never take tokens from JavaScript/browser or try to derive them from an ID Token.

## 12. Common HTTP Errors from UserInfo

### 12.1. HTTP 401 — Unauthorized

Example response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/json
~~~

Possible causes:

- Access Token expired, revoked, or invalid.
- Accidentally sent the **ID Token** in the Authorization header.
- Token is not intended for that provider/UserInfo Endpoint.
- Token was truncated or given an incorrect Bearer prefix.
- The client used a token from a **different registration**.

Resolution: check token origin, expiration, issuer/provider, presentation method, and token lifecycle. Do not solve this by ignoring `401` or editing the JWT.

### 12.2. HTTP 403 — Forbidden

The provider may reject because the Access Token lacks scopes or policy denies releasing claims. For instance, the Bearer challenge may include `insufficient_scope`. Do not assume requesting `email` forces UserInfo to return an email when the user/provider has not granted it.

Applications should handle missing permissions gracefully and request needed scopes via a valid authorization flow when justified; **never use Client Secret to bypass consent**.

### 12.3. HTTP 404 or Wrong Endpoint

If `user-info-uri` points to the wrong tenant/realm/hostname or a provider does not expose that endpoint, the client may receive 404. Check discovery documents and provider registration; do not arbitrarily guess `/userinfo` and append it to the issuer.

### 12.4. HTTP 429, Timeouts, 5xx

A UserInfo Endpoint may rate-limit, drop connections, or fail transiently. Configure **reasonable timeouts**, monitoring, and appropriate login failure messaging. Never retry indefinitely with an Access Token; excessive retries increase load and prolong logins.

### 12.5. HTTP 200 but Invalid JSON

HTTP 200 is not enough to confirm valid UserInfo. Possibilities:

- JSON lacks `sub` in OIDC UserInfo.
- `sub` differs from the subject in the ID Token.
- Response is HTML or JSON with an unexpected schema.
- The pure OAuth2 provider's identifier field is missing or has the wrong type.
- The provider returned nested structures or a UserInfo JWT that the client does not support.

In OIDC, **do not accept claims from a response with missing/wrong `sub`**. For pure OAuth2, verify the schema and configure `user-name-attribute` per the provider.

## 13. Common Spring Security Configuration Mistakes

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| UserInfo not called despite configured URI | User service decided it was unnecessary; mismatched scope/grant/flow | Check `openid`, `profile`/`email`, metadata, and `OidcUserService` conditions |
| `getUserInfo()` missing after login | ID Token may have sufficed, so no UserInfo request occurred | Do not assume UserInfo always exists; check principal and call policy |
| HTTP 401 from UserInfo | Wrong/expired Access Token, wrong transmission method | Check Bearer header, registration, token lifecycle |
| HTTP 403 from UserInfo | Insufficient scope/consent/policy | Request proper scopes via authorization flow; handle missing claims |
| HTTP 404 | Wrong `user-info-uri` or provider has no endpoint | Check discovery metadata/provider docs |
| `OAuth2AuthenticationException` due to `sub` mismatch | UserInfo response has a different subject than ID Token | Reject claims; investigate issuer, token, and provider |
| Principal is not `OidcUser` | Registration does not request `openid` or uses pure OAuth2 | Check scopes and corresponding user service |
| OAuth2 principal lacks username | `user-name-attribute` does not match JSON | Use a stable identifier field matching the contract |
| Manually calling UserInfo with ID Token | Confused the purpose of the two tokens | Use an Access Token accepted by the OP |
| Login fails when OP lacks UserInfo | Customization forced calling the endpoint unconditionally | Allow an ID Token-based flow if compliant with spec and product needs |
| Slow client login | Slow UserInfo endpoint network or overly long timeout | Measure latency, configure timeouts, avoid unnecessary calls |
| Two IdPs, wrong user from UserInfo | Used Access Token/URI from a different registration | Bind authorized client, provider URI, and identity to the right registration |
| `email` claim present but `email_verified=false` | Provider has not verified the email | Do not use this email for actions requiring a verified email |

### 13.1. How to Diagnose "UserInfo Has No Email"

Do not start by editing the controller to read more claims. Determine:

1. Does the registration include `openid`, `profile`, and `email` scopes as needed?
2. Is the UserInfo Endpoint published by the OP and is the client using the right URI?
3. Did `OidcUserService` perform the UserInfo request with a valid Access Token?
4. Does the OP release the email claim in the ID Token, UserInfo, both, or neither?
5. Does OP consent/policy restrict claims?
6. Is the email marked `email_verified`, and how should the application handle that?

**OIDC user identity remains `iss` + `sub`, not email.** A missing email does not mean a valid principal cannot be built.

### 13.2. Common Misconceptions About `user-name-attribute`

For pure OAuth2 Login, `user-name-attribute` may be needed for Spring Security to select the identifier field from a UserInfo-like API. For OIDC, the ID Token's `sub` is the foundation of identity; **do not use `user-name-attribute: email` as a substitute for OIDC verification**.

## 14. Error Handling and User Experience

When UserInfo fails while building the principal, Spring Security may treat the OAuth2/OIDC login as failed depending on the flow/configuration. An `AuthenticationFailureHandler` can redirect the user to a public page explaining the issue without exposing Access Tokens or detailed OP responses.

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

@Configuration
public class LoginFailureConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/auth/failed", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .failureHandler(
                    new SimpleUrlAuthenticationFailureHandler("/auth/failed")))
            .build();
    }
}
~~~

This is an **alternative SecurityFilterChain configuration** replacing the earlier examples, not an extra chain to run alongside them. The `/auth/failed` page must be served by the application and permitted unauthenticated to avoid redirect loops.

UI messaging should be neutral: "Unable to retrieve account information from the login provider. You can try again or contact support." Do not display raw `error_description`, URLs with tokens, UserInfo JSON, or stack traces to users.

If UserInfo only serves optional features and is not essential for a login session, you may consider designing principal creation not to depend on optional profile data. However, **never** accept UserInfo data with a mismatched `sub` or skip ID Token verification just to boost login success rates.

## 15. Key Security Principles

### 15.1. Protecting the Access Token en Route to UserInfo

- **Use HTTPS** and verify the provider's certificate/hostname.
- **Prefer the Bearer Authorization header** over query strings.
- Do not put tokens into browser URLs, frontend JavaScript, or HTML.
- Do not send a token to a user-supplied endpoint; only use `user-info-uri` from trusted provider configuration.
- Do not use an Access Token from registration A to call provider B's UserInfo.
- Do not record sensitive request headers in traces/logs; configure masking in reverse proxies and APMs.
- Do not cache UserInfo responses containing personal data in shared caches without an explicit policy.

### 15.2. Protecting Claims and Personal Data

- Only request scopes and store claims required for the product.
- Respect consent, retention policies, and access rules for profile data.
- Verify `sub` and enforce issuer binding; never automatically merge accounts solely because emails match.
- For email, check `email_verified` if business logic requires email verification.
- Never treat claims such as `groups`, `roles`, or `tenant` as application-approved admin privileges without trusted mapping/policy.
- Never return all of `OidcUser.getClaims()` to the UI; select only the exposed fields genuinely needed.

### 15.3. Never Use UserInfo to Replace ID Token Checks

UserInfo is a source of supplemental claims, not the sole proof of OIDC authentication. The client must verify the ID Token per OIDC rules (issuer, audience, signature, expiration, nonce if used, etc.), and only then use UserInfo under the `sub` constraint.

Do not argue "UserInfo returned HTTP 200 so the ID Token doesn't need checking." An HTTP 200 from an API does not by itself prove the token was issued for the right client and right authentication request.

## 16. Scenario Exercises

### Scenario A: OIDC Discovery Already Provides the UserInfo URI

The provider publishes `userinfo_endpoint` in metadata and the registration has `issuer-uri`.

**Approach:** no need to copy the URL into YAML; use the default `OidcUserService` first. If desired claims are absent, check scopes/consent and UserInfo retrieval conditions.

### Scenario B: Provider Requires a Bearer Header

The Token Endpoint returns a valid Access Token and the UserInfo API accepts `Authorization: Bearer ...`.

**Approach:** configure `user-info-authentication-method: header` if you want it explicit; avoid sending the token via query string.

### Scenario C: Legacy Provider Only Accepts Form Body

The UserInfo API uses POST form-encoded and reads `access_token` from the body.

**Approach:** verify the contract and use `user-info-authentication-method: form` if supported by the library/provider. Do not arbitrarily move the token to the query string or send it via both header and form simultaneously.

### Scenario D: UserInfo Returns 401 While the ID Token Is Verified

The user's OIDC login at the Token Endpoint succeeds, yet the UserInfo API returns `invalid_token`.

**Approach:** check whether the Access Token used for UserInfo matches the right provider/resource/scopes, or whether it expired or was revoked. Do not attempt to send the ID Token instead of the Access Token.

### Scenario E: UserInfo Returns a Different `sub` Than the ID Token

The ID Token has `sub=user-A`, while UserInfo returns `sub=user-B`.

**Approach:** reject the UserInfo data and investigate mismatched tokens/registrations/sessions or an OP bug. Do not compare by email.

### Scenario F: UserInfo Does Not Return an Email

A valid response has `sub` and `name`, without `email`.

**Approach:** show an appropriate fallback, check the `email` scope and provider policy, and never fabricate a dummy email. If the application requires a verified email, build a separate verification workflow.

### Scenario G: Multiple Registrations Sharing the Same Provider

An application has `portal` and `reporting` registrations with different scopes and Access Tokens. Portal wants to load the user's profile.

**Approach:** select the proper `OAuth2AuthorizedClient` for the user/registration and the corresponding UserInfo URI. Do not use reporting's Client Credentials token to identify a user logged into portal.

### Scenario H: UI Wants Profiles Always Fresh

A user just changed their photo at the IdP, while the principal in session holds the old photo.

**Approach:** design a controlled profile refresh using a valid token and timeouts, verifying `sub` before saving; do not assume UserInfo is called again on every request.

### Scenario I: Provider Returns a Signed UserInfo JWT

The provider is configured to return UserInfo as a signed JWT instead of plain JSON.

**Approach:** verify library and registered/supported algorithms, validate the response per the OIDC specification, or use compatible integration support. Do not turn the JWT into "automatically trusted" JSON merely because it was fetched over HTTPS.

## 17. References

- Spring Security — Servlet OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — OAuth2 Login Core Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security — OAuth2 Login Advanced Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — ClientRegistration and ProviderDetails: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- Spring Security — `DefaultOAuth2UserService` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/DefaultOAuth2UserService.html
- Spring Security — `OidcUserService` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserService.html
- OpenID Connect Core 1.0 — UserInfo Endpoint: https://openid.net/specs/openid-connect-core-1_0.html#UserInfo
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
- OAuth 2.0 Bearer Token Usage (RFC 6750): https://www.rfc-editor.org/rfc/rfc6750

## 18. Practical Summary

~~~text
OIDC Authorization Code Login
  -> Token Endpoint
       access_token + id_token
  -> Client verifies ID Token
       issuer, subject, audience, signature, exp, nonce when applicable
  -> UserInfo Endpoint available and profile needed?
       |
       +-- Yes -> Send Access Token to trusted user-info-uri
       |          Prefer Authorization: Bearer <access_token>
       |          Receive UserInfo response
       |          MUST match UserInfo.sub with ID Token.sub
       |          Use only verified and necessary claims
       |
       +-- No  -> Use already-verified OIDC claims
  -> OidcUser and SecurityContext/session
~~~

**The UserInfo Endpoint supplements user profiles; it does not replace OIDC authentication.** In Spring Security Servlet, prefer **OIDC Discovery via `issuer-uri`**, use the default `OidcUserService` when it meets your needs, and send the Access Token via the **Bearer Authorization header**. When customizing, preserve the boundaries: **right token, right provider, right endpoint, right subject, and right data-security policy**.
