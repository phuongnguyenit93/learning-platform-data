# 6.4. Configuring `issuer-uri` and Fetching Metadata via Discovery

## Lesson Objectives

In **Spring Security OAuth 2.0 / OpenID Connect Client**, configuring an OpenID Provider (OP) is more than knowing the login page address. The application must identify the exact **issuer** it trusts and know the endpoints for redirecting users, exchanging an authorization code for tokens, fetching public keys, and optionally querying user details. **Discovery** retrieves this information from metadata published by the provider.

After this lesson, you will be able to:

- Explain what `issuer` is and why `issuer-uri` is a critical identifier for an OIDC Provider.
- Distinguish **issuer URI**, **discovery endpoint**, **authorization endpoint**, **token endpoint**, **JWK Set URI**, and **UserInfo endpoint**.
- Configure `spring.security.oauth2.client.provider.<providerId>.issuer-uri` in Spring Boot.
- Describe how Spring Security discovers metadata and constructs `ClientRegistration`.
- Understand the boundary between **OIDC Discovery** and **OAuth 2.0 Authorization Server Metadata**.
- Diagnose errors involving wrong issuer, unreachable metadata, reverse proxy configuration, endpoints, or TLS certificates.
- Know when to declare endpoints manually, and what must still be configured even when discovery succeeds.

## 1. The Problem to Solve: One Provider Has Many Endpoints

Suppose an **Employee Portal** application written in Spring Boot needs to sign employees in with OpenID Connect. The internal identity system is deployed at:

~~~text
https://login.example.com/realms/company
~~~

During an OIDC Authorization Code login, the Portal must know:

1. Which **authorization endpoint** to send the browser to for user authentication.
2. Which **token endpoint** to send the authorization code to in exchange for tokens.
3. Which **JWK Set URI** holds the OP's public keys to verify the ID token signature.
4. Whether there is a **UserInfo endpoint** to retrieve additional profile claims.
5. Which **issuer** to expect in the ID token and metadata.
6. Which algorithms, response types, and protocol capabilities the OP supports.

One approach is configuring each URL separately. However, if URLs change or there are multiple environments, manual copying makes it easy for an application to use an authorization endpoint from one environment with a token endpoint or issuer from another.

**OIDC Discovery** lets the RP start with a single **trusted issuer URI**, then download the metadata document published by the OP to obtain the endpoints and required details.

~~~mermaid
flowchart TD
    A["Spring Boot Client / RP"] --> B["Configured issuer-uri"]
    B --> C["OP discovery metadata"]
    C --> D["authorization_endpoint"]
    C --> E["token_endpoint"]
    C --> F["jwks_uri"]
    C --> G["userinfo_endpoint if present"]
    C --> H["issuer and protocol capabilities"]
    D --> I["Initiate OIDC Authorization Code"]
    E --> J["Exchange authorization code for tokens"]
    F --> K["Verify ID token signature"]
~~~

**Discovery helps identify the provider**, but **does not automatically register the client with the provider**. The application still needs `client-id`, client authentication method, and appropriate registration settings.

## 2. What Is an Issuer?

### 2.1. Issuer Is the Identifier of the Issuing Party

In OIDC, `issuer` is the URL identifier of the OP; the ID token contains an `iss` claim specifying the issuer that issued the token.

Example:

~~~text
Issuer:
https://login.example.com/realms/company
~~~

A valid ID token issued by that OP might contain:

~~~json
{
  "iss": "https://login.example.com/realms/company",
  "sub": "employee-8217",
  "aud": "employee-portal",
  "iat": 1760000000,
  "exp": 1760003600
}
~~~

*Illustrative payload, not an actual signed ID token.*

In an OIDC transaction, the RP must verify `iss` against the configured issuer alongside other mandatory token checks such as signature, audience, expiration, and nonce when applicable. **Merely decoding the JWT and reading `iss` is not token verification.**

The issuer acts as a **trust boundary**: the application must know which provider's authentication results it is accepting.

### 2.2. Issuer Is Not the Login Page URL

An OP may publish:

~~~text
Issuer:
https://login.example.com/realms/company

Authorization endpoint:
https://login.example.com/realms/company/protocol/openid-connect/auth

Token endpoint:
https://login.example.com/realms/company/protocol/openid-connect/token

JWKS endpoint:
https://login.example.com/realms/company/protocol/openid-connect/certs
~~~

These URLs serve different purposes:

| URL | Meaning |
|---|---|
| **Issuer URI** | Identifier of the trusted issuer; checked against metadata and the ID token's `iss` |
| **Discovery URL** | Address from which to download the metadata document |
| **Authorization endpoint** | Where the browser is redirected to begin authorization/login |
| **Token endpoint** | Where the client exchanges codes or makes appropriate token requests |
| **JWK Set URI** | Where public keys needed for signature verification are published |
| **UserInfo endpoint** | Where additional End-User claims are served when accessed properly |

Do not replace `issuer-uri` with the authorization endpoint or token endpoint. For example, the value below is incorrect if the actual provider has its issuer at `/realms/company`:

~~~yaml
# Incorrect example: this is the authorization endpoint, not the issuer
issuer-uri: https://login.example.com/realms/company/protocol/openid-connect/auth
~~~

### 2.3. Issuer Must Match Exactly

In OIDC, the `issuer` value published in metadata must match the expected issuer exactly per the specification. Do not assume URLs differing only by a trailing `/`, `http`/`https` scheme, alias domain name, or realm/tenant path are equivalent.

For example:

~~~text
https://login.example.com/realms/company
https://login.example.com/realms/partner
~~~

are **two different issuers**, even when served from the same host. They can represent two realms/tenants with distinct users, clients, and policies.

In OIDC user identity design, it is standard practice to use the **`iss` + `sub` pair** instead of `sub` alone; `sub` is only guaranteed unique within its respective issuer.

## 3. How Does Discovery Work?

### 3.1. OpenID Connect Discovery

OpenID Connect Discovery defines a mechanism to publish **OpenID Provider Configuration** at a well-known URL. For the example issuer:

~~~text
https://login.example.com/realms/company
~~~

The OIDC discovery document typically resides at:

~~~text
https://login.example.com/realms/company/.well-known/openid-configuration
~~~

The RP performs an HTTPS GET to the discovery URL, receives a JSON document describing the OP, and uses the necessary details to execute the protocol.

Example command to inspect metadata:

~~~bash
curl --include \
  "https://login.example.com/realms/company/.well-known/openid-configuration"
~~~

The address above is illustrative; replace it with the actual issuer of the OP in your environment.

### 3.2. Example Metadata Content

An OP might publish a document like:

~~~json
{
  "issuer": "https://login.example.com/realms/company",
  "authorization_endpoint": "https://login.example.com/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.com/realms/company/protocol/openid-connect/token",
  "userinfo_endpoint": "https://login.example.com/realms/company/protocol/openid-connect/userinfo",
  "jwks_uri": "https://login.example.com/realms/company/protocol/openid-connect/certs",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic"]
}
~~~

This is **illustrative JSON** for the fields relevant to this lesson. Real provider metadata usually contains many more fields and may support additional values.

How to interpret the fields:

| Field in metadata | Purpose |
|---|---|
| `issuer` | Issuer value that the RP compares against the configured issuer and `iss` claim |
| `authorization_endpoint` | URL for the browser redirect step to the OP |
| `token_endpoint` | URL where the client sends token requests |
| `jwks_uri` | URL to download the JWK Set containing the OP's public keys |
| `userinfo_endpoint` | UserInfo URL, if published by the provider and needed by the client |
| `response_types_supported` | Response types supported by the OP, such as `code` |
| `subject_types_supported` | Subject identifier types supported by the OP |
| `id_token_signing_alg_values_supported` | ID token signing algorithms the OP advertises supporting |
| `scopes_supported` | Scopes the OP may advertise |
| `token_endpoint_auth_methods_supported` | Client authentication methods the OP advertises supporting |

**Metadata describes the provider's capabilities, not a guarantee that every client is allowed to use all of them.** For example, the OP may support `client_secret_basic`, while a specific client is registered to use another method.

### 3.3. Discovery and JWK Set Are Two Different Documents

The metadata document may contain:

~~~json
{
  "jwks_uri": "https://login.example.com/realms/company/protocol/openid-connect/certs"
}
~~~

When verifying a signed ID token, the security component can fetch the **JWK Set** from this URL to obtain the matching public key.

General shape of a JWK Set example:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "signing-key-2026",
      "alg": "RS256",
      "n": "<base64url-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

The `n` value in the example is a placeholder, so this JSON is not a usable JWK for verification. In a real system, the library handles key retrieval, key selection by header, and signature verification per trusted configuration.

**Do not confuse:**

- Discovery document: describes the provider and technical URLs.
- JWK Set: publishes keys for verifying corresponding signatures.
- ID token: proof of user authentication issued by the OP to the RP.
- Access token: used to access a Resource Server under granted permissions.

Discovery does not mean the RP can skip signature verification or issuer/audience checks on the ID token.

## 4. OIDC Discovery vs. OAuth 2.0 Authorization Server Metadata

The two mechanisms are related, yet serve potentially different purposes:

- **OpenID Connect Discovery**: describes an **OpenID Provider**, including details required for an RP to perform OIDC authentication.
- **OAuth 2.0 Authorization Server Metadata** (RFC 8414): describes Authorization Server information for OAuth 2.0 mechanisms.

### 4.1. Same Idea, Potentially Different Well-Known Paths

For an issuer with a path, rules for constructing the well-known URL differ slightly between standards.

Example issuer:

~~~text
https://auth.example.com/tenant/acme
~~~

Common locations:

~~~text
OIDC Discovery:
https://auth.example.com/tenant/acme/.well-known/openid-configuration

OAuth 2.0 Authorization Server Metadata (RFC 8414):
https://auth.example.com/.well-known/oauth-authorization-server/tenant/acme
~~~

In supported versions, Spring Security can use metadata lookup methods corresponding to the issuer and well-known endpoints supported by the library. **Do not assume** there is only one path variant without checking the provider's configuration.

If an OP publishes its document at a non-standard location or Spring cannot locate it, consult the provider's documentation, verify the URLs, and then consider declaring endpoints manually.

### 4.2. OAuth Metadata Is Not Always Enough for OIDC Login

An Authorization Server that only supports OAuth 2.0 may publish metadata yet **not issue ID tokens**. In that case, it can serve OAuth clients calling APIs, but does not automatically become an OpenID Provider.

Conversely, for OIDC login, the client needs the `openid` scope along with an OP that supports OIDC and valid ID token handling.

Therefore:

- `issuer-uri` is the starting point for discovery, but does not by itself guarantee the provider supports every OIDC feature.
- `client_credentials` only needs metadata/endpoints supporting that grant; it is not an end-user authentication flow.
- `oauth2Login()` requires configuration matching the chosen login flow, especially when expecting an OIDC principal.

## 5. Configuring `issuer-uri` in Spring Boot

### 5.1. OAuth 2.0 Client Dependency

For a Maven project using Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

This starter provides OAuth 2.0 Client and OIDC Login support for the Spring Boot/Spring Security version in use.

### 5.2. Minimal Configuration for an OIDC Registration

Suppose the client has been registered at the OP:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
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
            client-name: Corporate SSO
        provider:
          company-oidc:
            issuer-uri: https://login.example.com/realms/company
~~~

The configuration is split into two parts with distinct roles.

**`registration.corporate`** describes the specific client:

| Property | Meaning |
|---|---|
| `corporate` | Spring Security's `registrationId` |
| `provider: company-oidc` | Specifies the referenced provider config |
| `client-id` | Identifier issued by the OP for the application |
| `client-secret` | Confidential client secret; loaded from environment |
| `client-authentication-method` | How the client authenticates at the token endpoint |
| `authorization-grant-type` | The `authorization_code` flow |
| `redirect-uri` | Callback to receive the code from the OP |
| `scope` | OIDC scopes, including `openid` |

**`provider.company-oidc`** describes the OP:

- `issuer-uri` tells Spring the trusted issuer.
- When discovery works, Spring retrieves the relevant metadata from the OP instead of forcing you to declare `authorization-uri`, `token-uri`, `jwk-set-uri`, and other values manually in YAML.

The names `corporate` and `company-oidc` are chosen by the application; they do not need to match each other or match `client-id`.

### 5.3. Creating the Login Flow with Spring Security

Example using the Servlet stack and Spring Security 6:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

Users can start the login flow via the default endpoint:

~~~http
GET /oauth2/authorization/corporate HTTP/1.1
Host: portal.example.com
~~~

Spring Security looks up `ClientRegistration` with `registrationId=corporate`, uses the provider endpoints determined by discovery, and constructs an OIDC Authorization Request to redirect the browser.

When the OP finishes authentication/consent, the browser returns to:

~~~text
https://portal.example.com/login/oauth2/code/corporate
~~~

with the authorization code and appropriate state. Spring handles the callback, token exchange, ID token, and principal according to the selected OIDC configuration.

**Note:** the Redirect URI must be registered at the OP and match the actual public address. Discovery does not automatically register callbacks or modify client settings at the provider.

### 5.4. Configuring Multiple Providers

An application can use two independent OPs:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          employee:
            provider: employee-idp
            client-id: ${EMPLOYEE_CLIENT_ID}
            client-secret: ${EMPLOYEE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          partner:
            provider: partner-idp
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, email]
        provider:
          employee-idp:
            issuer-uri: https://id.example.com/realms/employee
          partner-idp:
            issuer-uri: https://id.example.com/realms/partner
~~~

These two registrations may share a host yet have **different issuers** due to different realms/paths. Spring distinguishes them by their respective registration and provider.

Points to remember when supporting multiple providers:

- Choose registrations from an **application-permitted allowlist**; never build an issuer URI from arbitrary input.
- Identify users by the ID token's issuer and subject; never merge two users solely because their email matches.
- Tokens/client secrets for each registration must be managed per client/provider.
- Issuers can differ in capabilities, consent policies, signing algorithms, and endpoints.

## 6. How Spring Security Processes Discovery and `ClientRegistration`

### 6.1. From YAML to `ClientRegistration` Objects

In standard Spring Boot configuration, the `spring.security.oauth2.client.*` group is bound into client and provider configurations. Spring Boot can create a `ClientRegistrationRepository` when auto-configuration conditions are satisfied.

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Spring Boot startup
    participant Config as Client properties
    participant OP as OpenID Provider
    participant Repo as ClientRegistrationRepository
    participant Login as OAuth2 Login
    App->>Config: Read registration + provider issuer-uri
    App->>OP: GET metadata via discovery
    OP-->>App: JSON metadata (issuer, endpoints, JWKS...)
    App->>App: Create ClientRegistration
    App->>Repo: Register registrationId -> ClientRegistration
    Login->>Repo: findByRegistrationId("corporate")
    Repo-->>Login: ClientRegistration with provider metadata
    Login->>OP: Start Authorization Code using known endpoint
~~~

The flow above describes the typical setup. **Discovery may happen when creating the client registration/configuration**, so if the OP or metadata is unreachable at initialization time, the application can fail during startup depending on how it is configured.

Distinguish clearly:

- **Fetching metadata**: determines the provider description.
- **Fetching JWK Set**: obtains keys needed when verifying tokens; fetch timing and caching depend on the implementation.
- **Exchanging code for tokens**: communicates with the token endpoint after callback.
- **Fetching UserInfo**: only occurs if the flow and configuration require it.
- **Registering the client at the OP**: a separate administrative task; it does not happen merely because the application starts.

### 6.2. Inspecting Metadata in Code

After Spring builds the registration, the application can read certain provider details:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.stereotype.Component;

@Component
public class ProviderEndpointInspector {

    private final ClientRegistrationRepository registrations;

    public ProviderEndpointInspector(ClientRegistrationRepository registrations) {
        this.registrations = registrations;
    }

    public String describeProvider() {
        ClientRegistration client = registrations.findByRegistrationId("corporate");
        if (client == null) {
            throw new IllegalStateException("Missing registration: corporate");
        }

        ClientRegistration.ProviderDetails provider = client.getProviderDetails();

        return "issuer=" + provider.getIssuerUri()
                + ", authorizationEndpoint=" + provider.getAuthorizationUri()
                + ", tokenEndpoint=" + provider.getTokenUri()
                + ", jwksUri=" + provider.getJwkSetUri();
    }
}
~~~

This snippet is for **observing non-sensitive metadata** in an internal context. There is no need to implement token exchange manually from the returned URLs; Spring Security already provides the protocol components. Never log `clientSecret` or real tokens for diagnostics.

### 6.3. Building a Registration from Issuer in Java

If manual registration is needed, Spring Security provides `ClientRegistrations.fromIssuerLocation(...)` to use metadata:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
public class RegistrationConfiguration {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${OIDC_CLIENT_ID}") String clientId,
            @Value("${OIDC_CLIENT_SECRET}") String clientSecret) {

        ClientRegistration corporate = ClientRegistrations
                .fromIssuerLocation("https://login.example.com/realms/company")
                .registrationId("corporate")
                .clientId(clientId)
                .clientSecret(clientSecret)
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("openid", "profile", "email")
                .clientName("Corporate SSO")
                .build();

        return new InMemoryClientRegistrationRepository(corporate);
    }
}
~~~

Meaning:

1. `fromIssuerLocation(...)` uses the issuer to discover provider metadata via the mechanism supported by Spring Security.
2. `registrationId("corporate")` sets the internal key.
3. `clientId(...)` and `clientSecret(...)` are supplied from secure configuration; metadata **does not supply client secrets**.
4. `authorizationGrantType(...)` and `scope("openid", ...)` define the OIDC login flow.
5. `InMemoryClientRegistrationRepository` serves as the registration lookup store.

This example is **an alternative to the repository auto-configured from YAML**. Once you declare a repository bean yourself, you are responsible for the set of registrations that bean provides.

Spring Security also provides other utility APIs for OIDC metadata depending on version. In implementation, choose the API matching your dependency version; the core idea stays the same: **trusted issuer → fetch metadata → complete registration**.

## 7. What Does Discovery Provide and What Does It Not Provide?

### 7.1. Fields Determinable from Metadata

Typically, discovery tells you:

- Official `issuer`.
- Authorization, token, JWK Set, and related OIDC endpoint URLs.
- Response types, scopes, client authentication methods, or algorithms published by the provider.
- Certain optional capabilities, such as logout endpoints or PKCE methods per metadata supported by the provider.

The presence of a field in JSON does not mean every Spring Security version automatically uses that field for every feature. How components consume metadata depends on the library and configuration.

### 7.2. Fields That Must Be Supplied Separately

Discovery **does not** replace the details issued when registering the application:

| Information | Automatically provided by discovery? | Actual source |
|---|---|---|
| `client-id` | No | OP or client management system |
| `client-secret` | No | OP/secret manager, when used |
| Client's specific `client-authentication-method` | Not fully inferred | Client registration settings |
| Application's `redirect-uri` | No | Application and callback allowlist at the OP |
| `authorization-grant-type` granted to the client | Not fully inferred | Client registration and policy |
| Scopes the application wants to request | No | Business needs and permissions granted to the client |
| API authorization policies | No | Resource Server and application |
| Internal account-linking rules | No | RP application |

For example, metadata might list `scopes_supported: ["openid", "profile", "email"]`, yet the `employee-portal` registration may still be restricted to a smaller set of scopes.

### 7.3. Discovery Does Not Prove a User Is Logged In

Being able to fetch metadata only proves that the endpoint is serving provider configuration; **it does not authenticate an end user**.

OIDC Login also requires:

1. An Authorization Request with `scope=openid` and security parameters such as `state` and `nonce`/PKCE per the flow.
2. The user being authenticated by the OP and authorization completing according to policy.
3. The Client exchanging the authorization code for tokens at the appropriate endpoint.
4. The RP validating the ID token and building the principal.
5. The application enforcing its own business authorization.

Similarly, an application accepting bearer access tokens to protect an API is a **Resource Server**, requiring its own token verification configuration. `spring.security.oauth2.client.provider.*.issuer-uri` serves client/provider configuration; it does not replace `spring.security.oauth2.resourceserver.jwt.issuer-uri` when setting up a JWT Resource Server.

## 8. Distinguishing Client Configuration from Resource Server Configuration

Two properties end with the same name `issuer-uri` yet belong to **two different functions**.

### 8.1. OAuth 2.0 Client / OIDC RP

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile, email]
        provider:
          corporate-idp:
            issuer-uri: https://login.example.com/realms/company
~~~

The application is a **Client/RP**: it initiates login, receives tokens, verifies the ID token, and can call APIs with an access token.

### 8.2. OAuth 2.0 Resource Server

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/company
~~~

The application is a **Resource Server**: it receives bearer JWTs on API endpoints, locates verification configuration/keys via the supported mechanism, and checks the issuer along with corresponding token validation conditions.

Both YAML blocks can appear together if an application acts as both an RP/OAuth Client and an API accepting bearer tokens, but responsibilities and security chains must be designed appropriately. Configuring the Client does **not** automatically enable bearer token authentication for APIs.

### 8.3. Why Is It Easy to Misconfigure?

Both can use the same issuer to locate metadata or verification keys, yet:

- Client Registration focuses on **authorization/token endpoints** to request permissions and sign in.
- Resource Server focuses on **verifying incoming tokens** sent by clients to APIs.
- Resource Server may need separate audience checks, scope/authority mapping, and API policies.
- Client Registration needs `client-id`, possibly a client secret, and callbacks; a Resource Server normally does not need those to verify incoming JWTs.

Do not copy a client configuration to a resource server and assume the application has completed all OAuth/OIDC mechanisms.

## 9. What If the Provider Does Not Support Discovery?

Not every Authorization Server has an OIDC `.well-known/openid-configuration` document, or metadata may be unreachable from the application network.

Spring Security can still use **manually configured endpoints** in certain cases, provided the provider supports the required flow.

### 9.1. Declaring Endpoints in YAML

Example of an OIDC OP with explicit endpoints:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-manual
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
          company-manual:
            issuer-uri: https://login.example.com/realms/company
            authorization-uri: https://login.example.com/realms/company/protocol/openid-connect/auth
            token-uri: https://login.example.com/realms/company/protocol/openid-connect/token
            jwk-set-uri: https://login.example.com/realms/company/protocol/openid-connect/certs
            user-info-uri: https://login.example.com/realms/company/protocol/openid-connect/userinfo
~~~

**Note on the example:** When `issuer-uri` is configured in Spring Boot, registration creation may still actively attempt issuer discovery depending on version and auto-configuration. If the goal is to **avoid discovery entirely because the provider lacks metadata**, do not assume that merely adding endpoints alongside `issuer-uri` disables discovery.

An explicit way to configure without needing issuer discovery at registration creation time is using **`ClientRegistration.Builder`** with application-managed endpoints and issuer, or using a Boot configuration specifying all endpoints without triggering the discovery branch, while verifying ID token validation behavior for your library version.

### 9.2. Creating `ClientRegistration` Manually

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

ClientRegistration client = ClientRegistration
        .withRegistrationId("corporate")
        .clientId(clientId)
        .clientSecret(clientSecret)
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
        .scope("openid", "profile", "email")
        .issuerUri("https://login.example.com/realms/company")
        .authorizationUri(
                "https://login.example.com/realms/company/protocol/openid-connect/auth")
        .tokenUri(
                "https://login.example.com/realms/company/protocol/openid-connect/token")
        .jwkSetUri(
                "https://login.example.com/realms/company/protocol/openid-connect/certs")
        .userInfoUri(
                "https://login.example.com/realms/company/protocol/openid-connect/userinfo")
        .clientName("Corporate SSO")
        .build();
~~~

In this snippet, `clientId` and `clientSecret` are variables supplied from secure configuration; endpoints are pre-populated from trusted OP details.

This approach proactively declares all required details without relying on metadata from `fromIssuerLocation(...)`. **However, it shifts responsibility for keeping endpoints and issuer accurate to the application.** An OIDC OP must still support standard behaviors and tokens; skipping automatic discovery does not permit skipping ID token validation.

### 9.3. Should Endpoints Be Hard-Coded?

It may be appropriate when a provider supports OAuth 2.0 without metadata, or an enterprise requires a fixed trusted configuration. On the other hand:

- Every environment must maintain accurate endpoints.
- When the provider changes URLs/token endpoint/JWKS, the application may need configuration updates and redeployment.
- It is easier to misconfigure issuers and JWKS across tenants/realms.
- Re-evaluation is needed whenever the provider adds or changes security policies.

When discovery works reliably, **prefer `issuer-uri`** to reduce duplicated configuration and keep endpoints aligned with metadata published by the OP.

## 10. Security When Fetching and Using Metadata

### 10.1. Issuer Must Come from a Trusted Source

If an application accepts requests like:

~~~text
/login?issuer=https://some-user-input.example
~~~

and automatically fetches metadata from a user-supplied issuer, it can enable access to unintended URLs or trusting an uncontrolled issuer.

A secure design typically:

- Maintains a pre-approved, managed set of issuers.
- Selects `registrationId` from a configured list.
- Never constructs issuer, token endpoint, or JWKS URI from values sent by the client/browser.
- If dynamic multi-tenancy is required, establishes an explicit trust workflow, metadata verification, key management, and tenant isolation.

**Discovery is not a mechanism to automatically trust every reachable server.** The crux is that the RP has already decided which issuer it trusts before fetching metadata.

### 10.2. Use HTTPS and Verify TLS Certificates

OIDC endpoints typically run over HTTPS. In production, the application must trust the proper certificate chain and avoid "disabling TLS verification" as a workaround for connection errors.

If discovery reports a TLS error, inspect:

- The certificate and CA chain served by the server.
- The application's truststore/JVM trust configuration.
- Reverse proxy configuration and hostname in the certificate.
- Whether the request is hitting the right domain for the issuer.

Disabling TLS verification can allow metadata or endpoints to be altered by an untrusted party.

### 10.3. Verify Issuer in Metadata and Tokens

If the RP configures the issuer:

~~~text
https://login.example.com/realms/company
~~~

but metadata returns:

~~~json
{
  "issuer": "https://login.example.com/realms/other-tenant"
}
~~~

that indicates a configuration mismatch. Do not fix it by disabling issuer validation. Fix the URI, tenant, or OP configuration so they match.

Afterwards, the returned ID token still needs `iss`, signature, audience, expiration, and corresponding OIDC checks.

### 10.4. Signing Key Rotation and Caching Behavior

The OP can rotate ID token signing keys. The JWK Set URI gives the RP a source for public key verification.

However, do not assume:

- Public keys never change.
- Metadata is re-fetched on every request.
- JWK Set and metadata share the exact same cache lifetime.
- Any key fetched from another issuer can verify the expected token.

Key fetching/caching/refresh behavior depends on Spring Security and the JWT verification library in use. In operations, monitor key rotation, JWKS reachability, and appropriate cache policies.

## 11. Common Errors and How to Reason About Root Causes

| Symptom | Possible cause | How to investigate |
|---|---|---|
| Application fails at startup while creating `ClientRegistration` | Metadata unreachable, invalid JSON, wrong issuer, or missing required fields | Test the discovery URL from **the application's runtime network**, inspect HTTP response and metadata |
| HTTP 404 at `.well-known/openid-configuration` | Wrong issuer, wrong tenant/realm, or provider does not implement OIDC discovery | Check the issuer published by the OP and the well-known rules supported by the provider |
| TLS handshake failure | Certificate/truststore/hostname mismatch | Verify certificate and JVM trust configuration |
| Metadata returns a different issuer than configured | OP behind proxy with wrong public URL or wrong tenant configured | Fix issuer configuration at OP/application; do not skip validation |
| Authorization Request rejected | Client ID, redirect URI, grant, or scope not permitted by OP | Check client registration at the OP |
| Token exchange returns `invalid_client` | Secret or client auth method mismatch | Check secret, rotation state, `client-authentication-method` |
| Callback fails with `redirect_uri_mismatch` | Public callback differs from registered redirect URI | Compare scheme, host, port, path, reverse proxy |
| OIDC login does not produce expected principal | Missing `openid` or provider does not issue valid ID token | Check scopes, OIDC metadata, token response |
| ID token verification fails | Wrong issuer/audience, signature/key issue, or expired token | Check `iss`, `aud`, `exp`, and JWKS belonging to the right OP |
| Works locally, fails in production | Different DNS, proxy, CA, public URL, or environment configuration | Test directly from the production container/host |

The table above only outlines investigative directions. Which stage returns the error and what exception type appears depend on the framework version, OP configuration, and protocol in use.

### 11.1. Wrong Issuer Due to Mixing Up Tenant or Realm

Suppose an OP has two realms:

~~~text
https://login.example.com/realms/dev
https://login.example.com/realms/prod
~~~

If `client-id` was issued for `prod` while `issuer-uri` points to `dev`, `invalid_client` or token/issuer verification errors may occur.

How to handle: check which realm the client is registered in, use the issuer for that exact realm, and confirm the client's redirect URI is allowed.

### 11.2. Wrong Issuer Due to Reverse Proxy

Suppose the OP publicly advertises:

~~~text
https://login.example.com/realms/company
~~~

but metadata returns:

~~~text
http://idp:8080/realms/company
~~~

The cause may be that the OP is not configured with the right public hostname or forwarded headers on the reverse proxy. **Do not switch Spring's configuration to the internal URL just to make discovery succeed** if the OP actually issues ID tokens with a different public issuer.

The public address in metadata and the `iss` claim must be consistent with the issuer trusted by the RP. The proxy and OP must be configured to advertise the proper public address.

### 11.3. Metadata Is Reachable, Yet Initialization Still Fails

Returning HTTP 200 does not guarantee valid JSON for the client being built. Check:

- Does the response have the right `Content-Type` and required JSON?
- Does `issuer` match the expected URI?
- Are `authorization_endpoint`, `token_endpoint`, and required OIDC fields present?
- Is `jwks_uri` valid and reachable?
- Is the request being redirected to an HTML login/error page instead of metadata?
- Does the provider support the registered flow and client authentication method?

Normally, the metadata endpoint is a public endpoint so clients can perform discovery; it should not require the client to have an active login session before reading it.

### 11.4. Callback Configuration Behind a Proxy

A Spring Boot application might receive internal requests at:

~~~text
http://portal-service:8080
~~~

while users access it via:

~~~text
https://portal.example.com
~~~

The redirect URI template:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

must resolve to the right public address. If Spring derives `http://portal-service:8080`, the OP may reject the callback. Configure the proxy and trusted forwarded headers handling, or choose a callback pattern matching the architecture.

This error relates to the **client's redirect URI**, not necessarily bad discovery. Do not modify `issuer-uri` to solve a problem caused by the RP application's own proxy.

## 12. Method for Verifying a Provider Before Integration

To prepare a Spring Security OIDC Client configuration, follow these steps.

### Step 1. Obtain the Official Issuer

Collect the issuer published by the OP from provider configuration/admin documentation. For tenants/realms, get the **exact tenant issuer**, not just the root domain.

Example:

~~~text
https://login.example.com/realms/company
~~~

### Step 2. Inspect Metadata

For an OIDC discovery endpoint in the common format:

~~~bash
curl --include \
  "https://login.example.com/realms/company/.well-known/openid-configuration"
~~~

Check the `issuer` content and technical endpoints. If 404, re-check the exact path per the provider and the metadata standards it supports.

### Step 3. Verify the Registered Client

Identify:

- `client-id` and client authentication method.
- Enabled grant types, such as Authorization Code.
- The application's public Redirect URI.
- Required and permitted scopes, especially `openid` when using OIDC.
- PKCE, consent, logout policies, or provider-specific requirements.

### Step 4. Configure Spring Boot

Place client settings under `spring.security.oauth2.client.registration`, provider settings under `spring.security.oauth2.client.provider`, and use a trusted `issuer-uri` if discovery is supported.

Load client secrets from environment variables or a secret manager; never store secrets in documentation or publicly committed source code.

### Step 5. Test the Complete Login Flow

Log in via `/oauth2/authorization/<registrationId>`, observe the browser redirecting to **the right OP**, returning to the registered callback, and the application receiving the appropriate OIDC principal.

Also test user denial, expired OP sessions, and multi-tenant/multi-provider setups to ensure the wrong issuer is never chosen inadvertently.

### Step 6. Monitor in Operations

Monitor OP downtime, metadata/JWKS reachability, certificate/key changes, client secret configuration, and issuers after upgrades or provider migrations. Periodically confirm the OP's public URL configuration remains consistent.

## 13. Self-Check Questions

**Question 1.** Why should `issuer-uri` not point directly to the `/authorize` URL?

**Answer:** The issuer is the provider's identifier and is checked against metadata as well as `iss` in the ID token. The authorization endpoint is only a URL for the redirect step; it does not replace the issuer.

**Question 2.** If Spring Boot already has `issuer-uri`, can `client-id` be omitted?

**Answer:** No. Discovery publishes the OP's configuration, whereas `client-id` identifies the application registered at the OP. If the client must authenticate with a secret or another mechanism, that must still be configured properly.

**Question 3.** What is `jwks_uri` in metadata used for?

**Answer:** It is the URL for fetching the JWK Set, usually containing public keys to verify the signature of ID tokens issued by the OP. It is different from the token endpoint.

**Question 4.** Why should metadata for `/realms/dev` not be used in place of `/realms/prod` even on the same hostname?

**Answer:** Because different issuers represent different trust boundaries. Registrations, tokens, keys, and users can differ per realm. The RP must use the issuer matching the OP where it is registered.

**Question 5.** If an application has `spring.security.oauth2.client.provider.corporate.issuer-uri`, do its own REST endpoints automatically accept JWT bearer tokens?

**Answer:** No. That configuration belongs to OAuth Client/OIDC RP. If REST APIs should verify access tokens, the Resource Server role must be configured separately.

**Question 6.** If a provider has no discovery endpoint, is it impossible to use OAuth 2.0 Client?

**Answer:** Not necessarily. Required endpoints can be configured manually via mechanisms supported by Spring Security and the provider. However, for OIDC Login, the provider must still genuinely support OIDC and issue valid ID tokens.

**Question 7.** Metadata states the OP supports `scope=email`. Does that guarantee your registration will receive email?

**Answer:** No. Metadata describes OP capabilities; actually granted scopes, claim presence, and where claims are returned still depend on client registration, consent, and OP policy.

**Question 8.** If metadata returns `issuer=http://idp:8080/realms/company` while the client trusts `https://login.example.com/realms/company`, what should you do?

**Answer:** Investigate the OP's public issuer, hostname, and reverse proxy configuration; fix them so the values are consistent. Do not disable issuer validation or arbitrarily switch to the internal URL.

## Remember

- **`issuer-uri` is the issuer identifier trusted by the OIDC Client/RP application.** It must align with provider metadata and the `iss` claim in the ID token.
- **Discovery** lets Spring Security obtain endpoints and provider details from one metadata document, reducing scattered configuration of multiple URLs.
- **Metadata does not replace client registration.** The application must still provide client ID, authentication method, grant type, callback, and appropriate scopes.
- **OIDC Discovery and OAuth Authorization Server Metadata** are related but not identical, particularly regarding metadata content and well-known URI rules.
- **Client registration and Resource Server are two distinct roles.** Both use `issuer-uri`, but they are configured at different property paths.
- When discovery fails, check **exact tenant issuer, HTTPS, metadata, runtime network, reverse proxy, and callback**; never drop security checks just to make the application appear to work temporarily.
