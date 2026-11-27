# 5.5. ProviderDetails and Endpoint Configuration

## 1. What Problem Does `ProviderDetails` Solve?

A Spring Boot application acting as an **OAuth 2.0 / OpenID Connect (OIDC) Client** must know where to send users to sign in, where to send the authorization code to exchange for tokens, where to retrieve public keys to verify the ID Token, and where it can query user information. Each identity provider (*provider*) has its own URLs, policies, and metadata. That is why Spring Security's `ClientRegistration` separates **client** information from **provider** information.

For example, a company operates a Spring Boot application at `https://portal.example.com`, while the Identity Provider (IdP) has issuer `https://login.example.com/realms/company`. The application needs:

- `client-id` and, for a confidential client, `client-secret` of **the registered application**;
- `redirect-uri` so the provider returns the browser to the application;
- `authorization-uri` to redirect the browser for login and consent;
- `token-uri` for the backend to exchange the code for tokens or refresh tokens;
- `jwk-set-uri` to load the public key set for signature verification when needed, especially OIDC ID Tokens;
- `user-info-uri` to retrieve additional profile claims when supported by the provider;
- `issuer-uri` as the issuer identifier and the anchor for automatic metadata *discovery*.

In Spring Security, provider properties are accessed via:

~~~java
ClientRegistration registration = /* retrieved by registrationId */;
ClientRegistration.ProviderDetails details = registration.getProviderDetails();
~~~

**`ProviderDetails` is the data section describing the OAuth 2.0 Authorization Server / OIDC Provider inside `ClientRegistration`.** It is not an HTTP client, not a place to store Access Tokens, and does not itself represent a signed-in user.

## 2. Placing `ProviderDetails` in the `ClientRegistration` Model

`ClientRegistration` represents a client registered with an OAuth 2.0/OIDC provider. Its properties are divided into two groups:

| Group | Example properties | Meaning |
| --- | --- | --- |
| **Client-side** | `registrationId`, `clientId`, `clientSecret`, `clientAuthenticationMethod`, `authorizationGrantType`, `redirectUri`, `scopes`, `clientName` | Which application is requesting permissions, which grant it uses, and where the provider returns results |
| **Provider-side** | `providerDetails.authorizationUri`, `tokenUri`, `issuerUri`, `jwkSetUri`, `userInfoEndpoint`, `configurationMetadata` | How the provider exposes its endpoints and publishes metadata |

One way to visualize it:

~~~mermaid
flowchart TB
    R["ClientRegistration: corp-login"] --> C["Client config: clientId, secret, grant, redirectUri, scopes"]
    R --> P["ProviderDetails"]
    P --> I["issuerUri"]
    P --> AU["authorizationUri"]
    P --> TO["tokenUri"]
    P --> JW["jwkSetUri"]
    P --> UI["UserInfoEndpoint: uri, authenticationMethod, userNameAttributeName"]
    P --> MD["configurationMetadata"]
    AU --> AS["Authorization Server / OIDC Provider"]
    TO --> AS
    JW --> AS
    UI --> AS
~~~

**Do not confuse the identifiers:**

| Term | Example | Who defines it? |
| --- | --- | --- |
| `registrationId` | `corp-login` | Spring Boot application, used to look up the registration |
| `providerId` | `company-oidc` | Configuration key under `spring.security.oauth2.client.provider` |
| `client-id` | `portal-web` | Issued by the Authorization Server when registering the application |
| `issuer-uri` | `https://login.example.com/realms/company` | Issuer identifier published by the provider |
| `redirect-uri` | `https://portal.example.com/login/oauth2/code/corp-login` | **Client** endpoint, registered with the provider |
| `authorization-uri` | `https://login.example.com/realms/company/protocol/openid-connect/auth` | **Provider** endpoint where the browser begins authorization |

The URLs above are illustrative only, not universal default URLs across products. `registrationId`, `providerId`, `client-id`, and issuer do not have to be identical.

## 3. Core Endpoints in `ProviderDetails`

### 3.1. Overview Table

| `ProviderDetails` field | Spring Boot property | Role | Who calls it? |
| --- | --- | --- | --- |
| `authorizationUri` | `authorization-uri` | Authorization endpoint: initiates login/consent and issues authorization code via redirect | User's browser following client-generated redirect |
| `tokenUri` | `token-uri` | Token endpoint: exchanges code for tokens, refreshes, or executes applicable grant | Backend client via direct HTTP request |
| `issuerUri` | `issuer-uri` | Issuer identifier; used for discovery and issuer verification where applicable | Spring Security during configuration / verification |
| `jwkSetUri` | `jwk-set-uri` | JWKS endpoint: publishes keys for verifying JWT signatures | Token verification component / JWK client |
| `userInfoEndpoint.uri` | `user-info-uri` | UserInfo endpoint: returns OIDC user claims | OIDC client with an appropriate Access Token |
| `userInfoEndpoint.authenticationMethod` | `user-info-authentication-method` | How the Access Token is sent to UserInfo | OIDC/OAuth2 user service |
| `userInfoEndpoint.userNameAttributeName` | `user-name-attribute` | Field name identifying the principal from UserInfo in applicable flows | OAuth2 user service |
| `configurationMetadata` | Metadata from discovery | Provider-published data, including fields without dedicated properties | Configuration infrastructure and extension logic |

### 3.2. Authorization Endpoint: `authorization-uri`

For the Authorization Code grant, Spring Security redirects the browser to the **authorization endpoint** using a URL with parameters such as:

~~~http
GET /realms/company/protocol/openid-connect/auth
    ?response_type=code
    &client_id=portal-web
    &redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcorp-login
    &scope=openid%20profile%20email
    &state=RANDOM_STATE
    &code_challenge=RANDOM_PKCE_CHALLENGE
    &code_challenge_method=S256 HTTP/1.1
Host: login.example.com
~~~

This is an illustrative request wrapped across lines for readability. The `authorization-uri` value is the **base URL of the endpoint**, while Spring Security builds the query string for the transaction. The user authenticates at the provider; then the provider redirects back to the registered `redirect-uri` with `code` and `state`.

**Distinction:** `authorization-uri` belongs to the provider; `redirect-uri` belongs to the client. Confusing these two URIs is a very common configuration error.

### 3.3. Token Endpoint: `token-uri`

Spring Security sends a *back-channel* request from the backend to the **token endpoint** after receiving the code:

~~~http
POST /realms/company/protocol/openid-connect/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=CODE_VALUE&redirect_uri=...&code_verifier=...
~~~

An actual request also requires the appropriate client authentication method: `client_secret_basic`, `client_secret_post`, `private_key_jwt`, `none` for public clients, or another provider-supported method. The snippet above only illustrates the form body, not a guide to omitting client authentication.

An OIDC token response may return:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "id_token": "SIGNED_ID_TOKEN_JWT",
  "refresh_token": "OPTIONAL_REFRESH_TOKEN"
}
~~~

The token endpoint is also used for refresh tokens or the Client Credentials grant, if allowed by the provider and registration. **Never send a refresh token to the authorization endpoint or UserInfo endpoint.** In real systems, the token endpoint must use HTTPS with certificate verification and proper client authentication.

### 3.4. JWKS Endpoint: `jwk-set-uri`

`jwk-set-uri` points to a **JSON Web Key Set (JWKS)**, typically containing public keys published by the provider to verify signatures on JWTs it issues. Abbreviated example response:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_RSA_MODULUS",
      "e": "AQAB"
    }
  ]
}
~~~

With OIDC, Spring Security must verify the **ID Token** before treating the user as signed in. It can select a key by the JWT's `kid` and the provider's published keys while validating issuer, audience, timestamps, and other transaction bindings.

Important notes:

- `jwks_uri` in discovery is the provider's metadata field; `jwk-set-uri` is the corresponding Spring Boot property.
- **A JWKS URL is not a Token endpoint.** Never send `code`, Access Tokens, or client secrets to this URL.
- A valid signature is necessary, **not sufficient**: issuer, audience, expiration, and token-type rules must all be verified.
- Providers can **rotate keys**. Spring Security/JWT decoders typically fetch and cache keys automatically; do not hard-code a fixed `kid`/key when integrating with a provider that manages keys dynamically.
- An **OAuth2 Client**'s `jwk-set-uri` configuration for verifying ID Tokens is distinct from a **Resource Server**'s `jwk-set-uri` configuration for verifying incoming API Access Tokens.

### 3.5. UserInfo Endpoint: `user-info-uri`

An OIDC provider may publish an endpoint supplying additional user information:

~~~http
GET /realms/company/protocol/openid-connect/userinfo HTTP/1.1
Host: login.example.com
Authorization: Bearer ACCESS_TOKEN_FOR_USERINFO
~~~

The response might be:

~~~json
{
  "sub": "opaque-subject-123",
  "name": "Nguyen An",
  "email": "an@example.com",
  "email_verified": true
}
~~~

**UserInfo is not an ID Token.** It is an endpoint protected by an Access Token; the returned claims supplement the identity already verified via the ID Token. An OIDC client must **match `sub` in the UserInfo response with `sub` in the ID Token** before using the data. Never assume `name`, `email`, or `picture` are always present, even when the client requested `profile` or `email`.

`user-info-authentication-method` specifies how the Access Token is sent:

| Value | Usage | Recommendation |
| --- | --- | --- |
| `header` | `Authorization: Bearer ...` | Usually the preferred choice |
| `form` | Access Token in the form body as supported by the endpoint | Use only if required by the provider |
| `query` | Access Token in the query string | Avoid when safer options exist, as URLs easily appear in logs and history |

`user-name-attribute` indicates which attribute of the UserInfo response identifies the principal in non-OIDC OAuth2 Login flows, such as `id` or `login`. For OIDC, `sub` is the mandatory identifier and must match the ID Token; **do not replace `sub` with email** merely for convenience.

### 3.6. Issuer: `issuer-uri` Is an Identifier, Not Simply an Endpoint

`issuer-uri`, such as `https://login.example.com/realms/company`, is the **issuer identifier**. It is typically used to:

1. Identify the trusted issuer.
2. Locate the **discovery metadata** URL.
3. Match against the `iss` value of a verified OIDC ID Token.

An issuer may include a **tenant/realm path**. Do not assume an issuer is always the root hostname or that every provider uses a `/realms/...` path. Differences in hostname, path, or trailing `/` can cause issuer matching to fail.

**Do not use the issuer URI as a token-issuing endpoint.** `token-uri` and `authorization-uri` serve different roles, even when belonging to the same provider.

## 4. Configuring an OIDC Provider via Discovery

### 4.1. What Is Discovery?

Instead of declaring each URL manually, many OIDC providers publish an **OpenID Provider Configuration** following the discovery standard. For example, issuer:

~~~text
https://login.example.com/realms/company
~~~

A common corresponding metadata URL:

~~~text
https://login.example.com/realms/company/.well-known/openid-configuration
~~~

Abbreviated illustrative metadata response:

~~~json
{
  "issuer": "https://login.example.com/realms/company",
  "authorization_endpoint": "https://login.example.com/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/company/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.com/realms/company/protocol/openid-connect/certs",
  "userinfo_endpoint": "https://login.example.com/realms/company/protocol/openid-connect/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
  "code_challenge_methods_supported": ["S256"]
}
~~~

This is a mock example to explain **field names**, not metadata fetched from a live provider. A real provider may support multiple values and additional fields. Metadata fields like `authorization_endpoint` follow OIDC standard names; Spring Boot maps them to `ProviderDetails.authorizationUri`.

### 4.2. Minimal `application.yml` Configuration

Example of a Servlet application using Spring Security OAuth2 Client:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp-login:
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
            issuer-uri: https://login.example.com/realms/company
~~~

When a Spring Boot app includes the OAuth2 Client starter and discovery succeeds, the framework builds a `ClientRegistration` with provider details fetched from metadata. This configuration is easier to maintain when providers manage their own endpoint sets.

**Never place client secrets directly in YAML.** The sample uses environment variables; real deployments may use a secret manager. `redirect-uri` must match the URI registered for the client at the authorization server.

### 4.3. Application Startup Flow

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Boot as OAuth2 Client Auto-Configuration
    participant IdP as OIDC Provider
    App->>Boot: Read registration + provider.issuer-uri
    Boot->>IdP: GET discovery metadata URL
    IdP-->>Boot: issuer, authorization_endpoint, token_endpoint, jwks_uri, userinfo_endpoint...
    Boot->>Boot: Build ClientRegistration + ProviderDetails
    Boot-->>App: ClientRegistrationRepository ready
    Note over App,IdP: When browser logs in, Spring Security uses configured endpoints
~~~

Depending on declaration style and version, discovery may occur while building the application context / client registration. If the IdP is unavailable, TLS certificates are invalid, or the issuer metadata mismatches, **the application can fail right at startup**. This is an operational dependency to consider for isolated networks or IdP outages.

### 4.4. `ClientRegistrations.fromIssuerLocation()` When Configuring in Java

Spring Security also provides an API to create a builder from metadata:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;

ClientRegistration registration = ClientRegistrations
    .fromIssuerLocation("https://login.example.com/realms/company")
    .registrationId("corp-login")
    .clientId(System.getenv("OIDC_CLIENT_ID"))
    .clientSecret(System.getenv("OIDC_CLIENT_SECRET"))
    .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
    .scope("openid", "profile", "email")
    .build();
~~~

`ClientRegistrations.fromIssuerLocation(...)` discovers metadata per supported OIDC/OAuth Authorization Server standards. `fromOidcIssuerLocation(...)` is for cases where only OIDC discovery should be used. This builder API is helpful when constructing registrations in code, though in standard Spring Boot apps **configuring `issuer-uri` in YAML is enough**.

Never use an issuer taken directly from an untrusted request to perform discovery arbitrarily: doing so can create an SSRF risk or cause trusting a rogue authorization server. Trusted issuers must be managed through controlled configuration or provider registration workflows.

## 5. Explicitly Configuring Each Endpoint Without Discovery

Not every OAuth 2.0 provider supports OIDC discovery. Some providers use pure OAuth 2.0 Login, non-standard metadata, or operate in environments blocking discovery access. In those cases, configure each endpoint explicitly.

Example of **non-OIDC OAuth 2.0 Login** with a UserInfo-like API returning an `id` field:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy-login:
            provider: legacy-oauth
            client-id: ${LEGACY_CLIENT_ID}
            client-secret: ${LEGACY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile.read
        provider:
          legacy-oauth:
            authorization-uri: https://auth.example.net/oauth/authorize
            token-uri: https://auth.example.net/oauth/token
            user-info-uri: https://auth.example.net/api/user
            user-info-authentication-method: header
            user-name-attribute: id
~~~

In this example:

1. The browser is sent to `authorization-uri`.
2. Spring Security sends the code to `token-uri`.
3. After obtaining an Access Token, the OAuth2 user service can fetch the profile from `user-info-uri`.
4. `user-name-attribute: id` identifies the identifier field of the OAuth2 UserInfo-like API response.

Because `openid` is absent, **there is no ID Token by default**; this is OAuth2 Login rather than OIDC Login. The `jwk-set-uri` property is not universally required for every OAuth2 provider. If the client uses OIDC and needs to verify signed ID Tokens, a key source and exact issuer validation must be configured; using discovery is preferable when supported by the provider.

### Full Mapping Table Between Spring Boot Properties and `ProviderDetails`

| Spring Boot configuration | Spring Security Java API |
| --- | --- |
| `spring.security.oauth2.client.provider.<providerId>.issuer-uri` | `registration.getProviderDetails().getIssuerUri()` |
| `...authorization-uri` | `getAuthorizationUri()` |
| `...token-uri` | `getTokenUri()` |
| `...jwk-set-uri` | `getJwkSetUri()` |
| `...user-info-uri` | `getUserInfoEndpoint().getUri()` |
| `...user-info-authentication-method` | `getUserInfoEndpoint().getAuthenticationMethod()` |
| `...user-name-attribute` | `getUserInfoEndpoint().getUserNameAttributeName()` |

`<providerId>` in the table is a placeholder for the provider key in the YAML file, such as `company-oidc` or `legacy-oauth`. When writing real YAML, **do not put angle brackets or `<` characters in configuration keys**.

### A Note on `issuer-uri` During Manual Declaration

Setting `issuer-uri` in Spring Boot typically triggers **metadata discovery**. If the goal is a deployment **that does not contact a discovery endpoint**, do not assume declaring `issuer-uri` and then "overriding" additional URLs will always skip discovery. Verify the registration-creation behavior of the version in use.

With a custom OIDC Provider that does not support discovery, you may need to explicitly build `ClientRegistration` in Java, setting endpoints, issuer, and JWK explicitly, while ensuring proper ID Token verification. That approach demands deep understanding of OIDC security requirements; it is best to have the provider publish compliant metadata whenever possible.

## 6. Creating `ClientRegistration` in Java and Reading `ProviderDetails`

### 6.1. Manually Creating an OAuth2 Registration

Illustrative snippet using Java and Spring Security Servlet client, without OIDC:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthenticationMethod;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
public class LegacyOAuthClientRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository() {
        ClientRegistration legacy = ClientRegistration
            .withRegistrationId("legacy-login")
            .clientId(System.getenv("LEGACY_CLIENT_ID"))
            .clientSecret(System.getenv("LEGACY_CLIENT_SECRET"))
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("profile.read")
            .authorizationUri("https://auth.example.net/oauth/authorize")
            .tokenUri("https://auth.example.net/oauth/token")
            .userInfoUri("https://auth.example.net/api/user")
            .userInfoAuthenticationMethod(AuthenticationMethod.HEADER)
            .userNameAttributeName("id")
            .clientName("Legacy OAuth2")
            .build();

        return new InMemoryClientRegistrationRepository(legacy);
    }
}
~~~

This is an **alternative** to Spring Boot auto-creating `ClientRegistrationRepository` from `application.yml`. Do not blindly declare both and expect Spring Boot to merge registrations; if you supply a custom repository bean, explicitly include **all** registrations the application needs.

Use configuration properties for URLs and secrets in real environments. The Java example uses fixed illustrative URLs and environment variables to focus on demonstrating the builder API.

### 6.2. Reading `ProviderDetails` from `ClientRegistrationRepository`

Here is a Java example reading metadata registered by Spring Boot:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

public class ProviderInspector {

    private final ClientRegistrationRepository registrations;

    public ProviderInspector(ClientRegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public void inspect() {
        ClientRegistration registration =
            registrations.findByRegistrationId("corp-login");
        if (registration == null) {
            throw new IllegalStateException("Missing registration: corp-login");
        }

        ClientRegistration.ProviderDetails provider =
            registration.getProviderDetails();

        String issuerUri = provider.getIssuerUri();
        String authorizationUri = provider.getAuthorizationUri();
        String tokenUri = provider.getTokenUri();
        String jwkSetUri = provider.getJwkSetUri();
        String userInfoUri = provider.getUserInfoEndpoint().getUri();

        // These URIs are configuration metadata, not Access Tokens.
        // Use them only for diagnostics in authorized environments.
    }
}
~~~

Fields may be **unconfigured or inapplicable to the current grant**: for example, Client Credentials needs no authorization endpoint, non-OIDC OAuth2 Login may have no JWKS, and a provider without UserInfo may have an empty URI. Do not write logic that blindly calls every endpoint simply because `ProviderDetails` exists.

### 6.3. Additional Metadata: `getConfigurationMetadata()`

If a registration was created via discovery, `ProviderDetails` may hold `configurationMetadata` returned by the provider:

~~~java
ClientRegistration.ProviderDetails details = registration.getProviderDetails();
Map<String, Object> metadata = details.getConfigurationMetadata();

Object responseTypes = metadata.get("response_types_supported");
Object pkceMethods = metadata.get("code_challenge_methods_supported");
Object logoutEndpoint = metadata.get("end_session_endpoint");
~~~

This snippet assumes `registration` already exists and `java.util.Map` is imported. These values are provider-dependent: they may be absent or have different types, so **do not cast them blindly**.

Distinguish extended metadata from properties that have official getters:

- `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint`, and `jwks_uri` have standard mappings in `ProviderDetails`.
- `end_session_endpoint`, `revocation_endpoint`, `introspection_endpoint`, or PKCE metadata may be published by the provider, yet **do not automatically have built-in active APIs** in every Spring Security configuration.
- Features like OIDC logout, revocation, or introspection must be explicitly configured with the corresponding components; do not assume they work merely because metadata contains the URL.

## 7. Connecting `ProviderDetails` to a Servlet `SecurityFilterChain`

Once a `ClientRegistration` exists, you can enable OIDC login on the Servlet stack:

~~~java
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
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

In the sample configuration:

| Step | Spring Security component | `ProviderDetails` used |
| --- | --- | --- |
| Browser opens URL requiring login | `SecurityFilterChain`, OAuth2 authorization request resolver | Looks up `ClientRegistration` by `registrationId` |
| Spring redirects to IdP | OAuth2 authorization request redirect filter | `authorizationUri` |
| Browser returns to `/login/oauth2/code/{registrationId}` | OAuth2 login authentication filter | Client redirect URI, state, and code |
| Backend exchanges code for tokens | OAuth2 authorization code token response client | `tokenUri` |
| Verifies OIDC ID Token | OIDC authentication provider/JWT verification | `issuerUri`, `jwkSetUri`, and related metadata |
| Loads UserInfo if needed | OIDC user service | `userInfoEndpoint.uri` and authentication method |
| Calls another business API | OAuth2 authorized client + HTTP client | Appropriate Access Token; API endpoints are **not** in `ProviderDetails` |

Spring Security Servlet paths may include:

~~~text
/oauth2/authorization/corp-login
    -> authorizationUri of provider company-oidc

/login/oauth2/code/corp-login
    <- browser callback from provider after login
~~~

`corp-login` is the registration ID in the application. When changing the default callback URI, in addition to setting `redirect-uri` on the registration, configure `oauth2Login()`'s callback handling endpoint to match and update the allowlist at the provider.

### Sequence Diagram: Which Endpoint Is Called, and When?

~~~mermaid
sequenceDiagram
    autonumber
    actor B as Browser
    participant C as Spring Servlet OAuth2 Client
    participant AS as OAuth2/OIDC Provider
    participant API as Downstream Resource Server
    B->>C: GET /oauth2/authorization/corp-login
    C-->>B: 302 Location = authorizationUri + query
    B->>AS: GET authorization endpoint
    AS-->>B: 302 to redirect_uri with code + state
    B->>C: GET /login/oauth2/code/corp-login?code=...
    C->>AS: POST tokenUri, exchange code for tokens
    AS-->>C: ID Token + Access Token
    C->>AS: GET jwkSetUri if verification keys needed
    AS-->>C: JWK Set
    Note over C: Verify ID Token / issuer / audience / expiry
    opt Provider has UserInfo and app needs claims
        C->>AS: GET userInfoUri with Access Token
        AS-->>C: Claims, including sub
        Note over C: Verify UserInfo.sub matches ID Token.sub
    end
    C-->>B: Establish login session
    opt Access Token issued for API
        C->>API: Authorization: Bearer Access Token
        API-->>C: Data or 401/403
    end
~~~

**Note:** JWKS fetching is usually cached or performed on demand, not necessarily as a fresh request on every single login. The diagram shows functional relationships rather than mandating a fixed key-fetching order.

## 8. Reusing One Provider for Multiple `ClientRegistration`s

One provider can serve multiple applications or multiple registrations that share the same endpoint set while differing in client ID, scope, or redirect URI.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          employee-portal:
            provider: corp-provider
            client-id: ${EMPLOYEE_PORTAL_CLIENT_ID}
            client-secret: ${EMPLOYEE_PORTAL_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
          reporting-client:
            provider: corp-provider
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - report.read
        provider:
          corp-provider:
            issuer-uri: https://login.example.com/realms/company
~~~

`employee-portal` has user login; `reporting-client` requests tokens via Client Credentials. Both reference `corp-provider` to share metadata, yet have **different client IDs, secrets, scopes, and grants**. For client credentials, the application needs an authorized client manager suited for server tasks; no browser redirect or login session is needed.

**Multiple tenants/realms with different issuers** should be treated as separate providers if each realm publishes its own issuer/endpoints. Do not configure one issuer and then accept tokens from a different tenant; doing so can lead to mismatched issuers, audiences, and security boundaries.

## 9. `CommonOAuth2Provider` and Defaults for Well-Known Providers

Spring Security includes `CommonOAuth2Provider` containing default configurations for popular providers. For example, when setting `registrationId` to `google`, Spring Boot can use Google's default endpoints without requiring every `provider.*-uri` to be declared:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: ${GOOGLE_CLIENT_ID}
            client-secret: ${GOOGLE_CLIENT_SECRET}
            scope:
              - openid
              - profile
              - email
~~~

If you want `registrationId` to be `google-login` while still using the default provider:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          google-login:
            provider: google
            client-id: ${GOOGLE_CLIENT_ID}
            client-secret: ${GOOGLE_CLIENT_SECRET}
            scope:
              - openid
              - profile
              - email
~~~

Available built-in providers and default endpoints depend on the Spring Security version; check documentation matching your project version. For enterprise IdPs, custom tenants, or private environments, **`issuer-uri` is usually clearer and more reliable** than guessing authorization/token URLs from a provider name.

## 10. Common Endpoint Configuration Errors

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Fails to create `ClientRegistration` at startup | Wrong discovery URL, IdP unreachable, TLS failure, invalid metadata | Issuer value, HTTPS trust, DNS, proxy, JSON metadata, startup logs |
| Issuer mismatch error | `issuer-uri` does not match `issuer` in metadata or `iss` in ID Token | Compare literal host, path, trailing slash, tenant |
| Login redirects to wrong page | `authorization-uri` points to wrong host/tenant/endpoint | Actual provider metadata and active registration |
| Provider reports `redirect_uri_mismatch` | **Client's** Redirect URI unregistered or misbuilt behind reverse proxy | `redirect-uri`, public base URL, HTTPS, port, context path, trusted proxy |
| Token endpoint returns `invalid_client` | Wrong `client-id`, secret, or `client-authentication-method` | Client config at provider and how client credentials are sent |
| Token endpoint returns `invalid_grant` | Expired/reused code, wrong redirect URI, PKCE mismatch | State/session, code lifetime, PKCE, callback |
| ID Token received but JWT verification fails | Wrong `jwk-set-uri`, rotated keys, `kid` mismatch, disallowed algorithm | Issuer metadata, JWKS, signing algorithm, clock skew |
| UserInfo returns `401` | Wrong `user-info-uri`, invalid Access Token, or not valid for endpoint | Actual endpoint, Bearer token, scope/audience, expiry |
| Signed in but principal lacks name/email | No UserInfo endpoint or provider withholds claims | Scopes, UserInfo metadata, claims, user service |
| OAuth2 Login does not recognize user | `user-name-attribute` missing from non-OIDC provider response | Returned JSON and exact identifier field, e.g., `id` |
| `No ClientRegistration found` | Wrong registration ID called or missing matching registration | `registration.*` and `/oauth2/authorization/{registrationId}` |
| Login succeeds but external API returns 403 | Access Token lacks scope or has wrong audience for API | API policy, resource indicators, token grant |

### Distinguishing Commonly Confused Scenarios

**Confusion 1 — Authorization endpoint vs. Token endpoint:** the browser goes to the authorization endpoint for user authentication; the backend calls the token endpoint to receive tokens. Never put `client-secret` in browser URLs.

**Confusion 2 — Issuer vs. metadata URL:** the issuer is the issuer identifier, not always identical to the `/.well-known/openid-configuration` URL. Discovery is the step of resolving metadata from the issuer.

**Confusion 3 — Redirect URI vs. `ProviderDetails`:** the redirect URI is the return path on the client application; it does not live inside `ProviderDetails`. Changing `authorization-uri` will not fix `redirect_uri_mismatch` if the callback path is wrong.

**Confusion 4 — JWKS for OAuth2 Client vs. Resource Server:** OIDC login needs to verify ID Tokens issued by the IdP, whereas a REST API needs to verify incoming Access Tokens. They may share an issuer/keys in a given system, yet the two configurations and responsibilities remain separate.

**Confusion 5 — UserInfo vs. business APIs:** the UserInfo endpoint returns identity claims, not an orders API. An Access Token that successfully calls UserInfo does not automatically have permission to call any arbitrary API.

**Confusion 6 — URL in metadata means feature is automatically enabled:** discovery advertising an endpoint does not mean Spring Security automatically invokes revocation, logout, introspection, token exchange, or every extension endpoint. The corresponding feature must be configured explicitly.

## 11. Security Considerations When Configuring `ProviderDetails`

OAuth2/OIDC endpoints form part of the trust boundary. Misconfiguration can send authorization codes, tokens, or credentials to an unintended server.

1. **Trust only approved providers:** manage issuers and endpoints via trusted configuration; never take a URL from a user query parameter and feed it directly into discovery or token calls.
2. **Use HTTPS:** production Authorization Server, token, JWKS, and UserInfo endpoints require valid TLS. Never disable certificate verification to work around environment errors.
3. **Separate metadata and secrets:** `ProviderDetails` holds endpoints/public metadata; `client-secret` belongs to the registration and must be protected separately. Do not log secrets or tokens when debugging provider issues.
4. **Match issuers strictly:** metadata and ID Tokens must originate from trusted issuers. Watch out for tenants and cases where multiple issuers share one hostname.
5. **Bind redirects:** the provider must validate registered redirect URIs; Spring Security must match `state` and handle authorization code/PKCE properly.
6. **Verify JWKS and tokens:** do not load keys from arbitrary URLs specified inside a JWT without a trust policy; use trusted issuer/JWK configuration and verify signature, audience, expiry, and nonce as required.
7. **Keep tokens out of URLs:** UserInfo prefers the Bearer header; avoid logging callbacks containing `code` or `Authorization` headers.
8. **Scope application permissions properly:** an OIDC login client does not automatically gain access to call all APIs. Scopes, audiences, and resource server policies still govern access.

For multi-tenant systems, clearly define the **tenant → trusted issuer → client registration** mapping and avoid wildcard issuers. If supporting dynamic registration, enforce verification and an allowlist before using received endpoints.

## 12. Inspecting Configured Providers for Diagnostics

During operations, verify three layers of data:

**Application configuration layer** — Do values in `spring.security.oauth2.client.registration.*` and `spring.security.oauth2.client.provider.*` have the right registration ID, provider ID, client ID, grant, redirect, scope, and issuer?

**Provider metadata layer** — Does discovery (if used) return the right `issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`, and `userinfo_endpoint`? Are TLS certificates valid, and does the provider advertise compatible algorithms and client authentication methods?

**Runtime layer** — When the browser logs in, does the request go to the right authorization endpoint; does the backend exchange the code at the right token endpoint; does Spring Security receive and verify the ID Token; is UserInfo called when needed; and does the business API receive the right Access Token?

You can inspect public metadata (without sending tokens or secrets) in an authorized environment, for example:

~~~bash
curl --fail-with-body --show-error \
  "https://login.example.com/realms/company/.well-known/openid-configuration"
~~~

Some older `curl` environments do not support `--fail-with-body`; use `--fail` there instead. Perform this check only if the URL genuinely belongs to an approved provider; the lesson URL is illustrative.

When debugging, prefer logging the `registrationId`, trusted issuer, HTTP status, and correlation ID. Never log authorization codes, client secrets, ID Tokens, Access Tokens, Refresh Tokens, or full callback query strings.

## 13. Scenario-Based Application Exercises

### Scenario A: Provider Publishes Standard-Compliant Discovery

A Spring Boot application signs employees in at an OIDC provider with a known `issuer`. You only need one registration and do not want to copy changeable URLs.

**Choice:** declare `registration.*` together with `provider.*.issuer-uri`. Let Spring Security fetch metadata and map the endpoints. Verify the registered redirect URI and client authentication method.

### Scenario B: OAuth2 Provider Does Not Support Discovery

The application wants to use OAuth2 Login for a provider exposing `authorize`, `token`, and a profile API returning `id`, but it does not issue ID Tokens.

**Choice:** declare `authorization-uri`, `token-uri`, `user-info-uri`, and `user-name-attribute: id`. Do not assume OAuth2 Login has become OIDC; without an ID Token, the application does not have the corresponding OIDC guarantees.

### Scenario C: Access Token via Client Credentials, No Browser Login

A backend job only needs to request a token to call a reporting API.

**Choice:** `registration.authorization-grant-type: client_credentials`; the provider section minimally needs the token endpoint (or metadata providing the token endpoint). Neither `authorization-uri` nor `redirect-uri` is needed in this transaction. Use an authorized client manager suited for background jobs rather than relying on a Servlet login session.

### Scenario D: Two Realms on the Same Provider

Tenant A has issuer `https://login.example.com/realms/a`, and Tenant B has issuer `https://login.example.com/realms/b`.

**Choice:** configure two separate providers/registrations or a multi-tenant mechanism with an allowlist of trusted issuers. Do not use issuer A to validate ID Tokens issued by realm B; sharing a hostname does not make two issuers equivalent.

### Scenario E: OIDC Login Succeeded, Yet Calling Task API Still Fails

Spring Security used `ProviderDetails` correctly and validated the ID Token, yet the Task API returns `401` or `403`.

**Reasoning:** `ProviderDetails` configures the **Authorization Server** endpoints. The Task API is a **separate Resource Server**. Check whether the Access Token was issued for the Task API, whether audience/scopes match, and whether the API accepts the token's issuer/format.

## 14. Official References

- Spring Security — Servlet OAuth2 Client, Core Interfaces and Classes: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- Spring Security — Servlet OAuth2 Login, Core Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security — `ClientRegistration.ProviderDetails` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/registration/ClientRegistration.ProviderDetails.html
- Spring Security — `ClientRegistrations` (issuer discovery) Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/registration/ClientRegistrations.html
- Spring Boot — OAuth2 Client configuration: https://docs.spring.io/spring-boot/reference/security/oauth2.html
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html

## 15. Knowledge Summary

`ProviderDetails` is the bridge between **`ClientRegistration`** and the endpoints of an OAuth2/OIDC Provider:

~~~text
ClientRegistration
├── Client details
│   ├── registrationId, clientId, clientSecret
│   ├── authorizationGrantType, scopes
│   └── redirectUri  -> callback back to the application
└── ProviderDetails
    ├── issuerUri    -> issuer identity / discovery anchor
    ├── authorizationUri -> browser navigates here to sign in/authorize
    ├── tokenUri         -> backend exchanges code or requests/refreshes tokens
    ├── jwkSetUri        -> fetches public keys to verify JWT/ID Token
    ├── userInfoEndpoint -> fetches profile claims with a valid Access Token
    └── configurationMetadata -> extended metadata from the provider
~~~

When the provider supports OIDC discovery, **`issuer-uri`** auto-configures the endpoints and reduces URL copy errors. When discovery is unavailable, use **`authorization-uri`, `token-uri`, `user-info-uri`, and `jwk-set-uri`** as actually needed while maintaining trust boundaries. In a Spring Security Servlet Client, always distinguish between **the provider's endpoints**, **the application's redirect URI**, and **business APIs acting as separate resource servers**.
