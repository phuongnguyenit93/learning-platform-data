# Enabling the Dynamic Registration Endpoint by Scope and Version

## 1. Lesson Objectives and Scope

In the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, we learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using **Spring Security**, **Spring Authorization Server**, and **Spring Boot**. This lesson guides you through enabling the **OpenID Connect Dynamic Client Registration Endpoint** in Spring Authorization Server, restricting registration permissions by scope, and selecting configuration compatible with the library version in use.

Typically, clients are pre-registered by an administrator in `RegisteredClientRepository`. When a system has many tenants, many integrating applications, or needs to automatically create clients during onboarding, manually registering each client can become a bottleneck. Dynamic Client Registration (DCR) lets a client/developer send registration metadata to the Authorization Server and receive a `client_id` along with the accepted configuration details.

Spring Authorization Server supports **OpenID Connect Dynamic Client Registration 1.0**. This endpoint is **disabled by default** because many systems do not need dynamic registration. When enabled, the endpoint remains an OAuth 2.0 protected resource: the registering party must hold a valid Access Token with the appropriate scope. This is a critical point when deciding to enable the feature in production.

After this lesson, you will be able to:

1. Distinguish OIDC Dynamic Client Registration from statically adding clients to the repository.
2. Identify configuration APIs according to the Spring Authorization Server branch in use.
3. Enable the Client Registration Endpoint in `SecurityFilterChain`.
4. Declare `JwtDecoder`, the endpoint path, and the registrar client.
5. Issue an initial access token with the exact `client.create` scope.
6. Send a registration request, read the response, and retrieve the client registration.
7. Restrict metadata, redirect URIs, grant types, scopes, and protect credentials.
8. Test the endpoint, diagnose errors, and operate it safely.

**Example scope:** the main configuration code in this lesson uses the Spring Authorization Server **1.5.x** API, referencing the **1.5.8** documentation. The lesson also notes other stable branches so you can check the documentation for your actual dependency. The examples use an authorized registrar rather than anonymous open registration.

## 2. What Is Dynamic Client Registration?

### 2.1. Static Registration and Dynamic Registration

| Registration Method | Who creates the client? | When is it suitable? |
| --- | --- | --- |
| Static registration | Administrator or provisioning job creates `RegisteredClient` before the application uses it | Few clients, manual approval workflows, stable configuration |
| Dynamic registration | Client/developer sends metadata to the Registration Endpoint; Authorization Server validates and creates the registration | Multi-tenant/multi-client onboarding, controlled automated integration |

Dynamic registration **does not mean the client chooses all of its permissions**. The Authorization Server still decides which metadata is accepted, replaced with default values, or rejected. `redirect_uris`, `grant_types`, `response_types`, `scope`, client authentication methods, JWKs, and other metadata must be validated against policy.

### 2.2. Distinguishing Three Types of Tokens/Credentials

The Spring Authorization Server flow uses credentials with distinct purposes:

| Credential | Who uses it? | Purpose |
| --- | --- | --- |
| Registrar client credentials | Registration management service | Authenticates the registrar at the Token Endpoint to request an initial access token |
| Initial access token | Authorized registrar/developer | Authorizes performing a single new client registration with the `client.create` scope |
| `registration_access_token` | Party managing the created client | Calls the Client Read Endpoint via `registration_client_uri` |

Do not confuse the registrar's `client_secret` with the secret issued for the new client. Nor should you use a business client's Access Token to call the Registration Endpoint if that token lacks `client.create`.

### 2.3. OIDC DCR in Spring Authorization Server vs. RFC 7591

RFC 7591 defines the OAuth 2.0 Dynamic Client Registration Protocol. OIDC Dynamic Client Registration 1.0 extends this metadata model and workflow for OpenID Connect. Spring Authorization Server describes its feature as an implementation of **OpenID Connect Dynamic Client Registration 1.0**.

There is an operational difference to keep in mind:

- RFC 7591 allows an open registration model without an initial access token if the Authorization Server chooses to support it.
- Spring Authorization Server's endpoint is documented as an **OAuth2 protected resource**, requiring a Bearer Access Token.
- The Spring guide uses a pre-registered registrar client and an initial token carrying only the `client.create` scope, used once.
- The Spring guide demonstrates registering and reading a client registration. Do not assume that merely enabling this endpoint provides full RFC 7592 registration management (update/delete) or a complete admin portal.

Therefore, treat DCR as a provisioning API that must be constrained by registrar identity and Authorization Server policy, not a public form where anyone can create arbitrary clients.

## 3. Selecting the Spring Authorization Server Version

### 3.1. Documentation Versions and APIs Used

At the time of documentation reference, the Spring Authorization Server site lists stable branches 1.5.8, 1.4.8, 1.3.7, and 1.2.7; branch 2.0.0-M2 is a preview. Dynamic Client Registration has a guide in the 1.5.x branch as well as in 1.3.x/1.4.x.

| Branch | Reference Documentation | Approach in This Lesson |
| --- | --- | --- |
| 1.5.x | Stable docs 1.5.8 | Used for the primary code samples |
| 1.4.x | Stable docs 1.4.8 | Open the 1.4.x docs and verify API signatures when upgrading |
| 1.3.x | Stable docs 1.3.7 | DCR also has a guide; check the matching Spring Security version |
| 1.2.x | Stable docs 1.2.7 | Reference the API/configuration docs for this branch |
| 2.0 preview | 2.0.0-M2 | Experimental only; do not apply preview APIs to a 1.x production app |

Do not mix `spring-security` and `spring-authorization-server` from incompatible branches. With Spring Boot, prefer the dependency management/BOM recommended by Spring for your Boot version; avoid pinning individual Security modules to mismatched versions.

### 3.2. Checking the Actual Dependency

Before applying the examples, inspect the dependency tree or build file to confirm which branch `spring-security-oauth2-authorization-server` is on. If your IDE does not recognize `clientRegistrationEndpoint(...)`, check:

1. Whether the actual dependency is Spring Authorization Server.
2. Whether the version includes `OidcClientRegistrationEndpointConfigurer`.
3. Whether you are using the `OAuth2AuthorizationServerConfigurer.authorizationServer()` API for the matching branch or an older configuration style.
4. Whether dependency management accidentally pulled a different version than declared.

Do not add a custom filter or controller class just to compensate for a method missing from your dependency. Choose the right version/API first, then use the provided extension points.

### 3.3. Key API Classes

| Class/API | Role |
| --- | --- |
| `OAuth2AuthorizationServerConfigurer` | Configures Authorization Server protocol endpoints |
| `OidcConfigurer` | Enables and customizes OIDC endpoints |
| `clientRegistrationEndpoint(...)` | Enables/configures the Dynamic Client Registration Endpoint |
| `OidcClientRegistrationEndpointConfigurer` | Customizes converters, providers, response handlers, and error handlers |
| `OidcClientRegistrationEndpointFilter` | Handles Client Registration and Client Read requests |
| `OidcClientRegistrationAuthenticationProvider` | Processes registration requests |
| `OidcClientConfigurationAuthenticationProvider` | Processes client configuration/read requests |
| `RegisteredClientRepository` | Stores and looks up registrars and newly created clients |
| `JwtDecoder` | Verifies JWT Access Tokens used to protect the endpoint |

## 4. Enabling the OIDC Client Registration Endpoint

### 4.1. Minimal Configuration for Spring Authorization Server 1.5.x

The endpoint is enabled through the OIDC configurer. The example below preserves the default converter/provider configuration and enables the Client Registration Endpoint:

```java
package com.example.authserver;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AuthorizationServerSecurityConfig {

    @Bean
    SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer
                    .oidc(oidc ->
                        oidc.clientRegistrationEndpoint(Customizer.withDefaults())
                    )
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated()
            );

        return http.build();
    }
}
```

If the application already enables OIDC for Provider Configuration, UserInfo, or Logout, **add `clientRegistrationEndpoint(...)` to the existing `oidc(...)` call**. Example:

```java
.oidc(oidc -> oidc
    .userInfoEndpoint(Customizer.withDefaults())
    .clientRegistrationEndpoint(Customizer.withDefaults())
)
```

Do not create two `SecurityFilterChain` beans with `securityMatcher(getEndpointsMatcher())` just to enable an extra endpoint. Keep one filter chain for Authorization Server endpoints and extend the OIDC configurer inside that existing bean.

### 4.2. Default Endpoint

In Spring Authorization Server, the commonly used default path is:

```text
/connect/register
```

This filter handles both:

- **Client Registration Request**: `POST` JSON to create a registration.
- **Client Read Request**: `GET` to the client configuration URI returned in the registration response.

This is an OIDC endpoint, not the OAuth Token Endpoint. The Token Endpoint `/oauth2/token` is used beforehand to request the initial access token.

### 4.3. Customizing the Endpoint Path

If a custom path is needed, declare it in the `AuthorizationServerSettings` bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .oidcClientRegistrationEndpoint("/connect/v1/register")
            .build();
}
```

If the application already has an `AuthorizationServerSettings` bean defining the issuer, authorization endpoint, token endpoint, introspection, or revocation, add `oidcClientRegistrationEndpoint(...)` to the **existing bean**. Do not create a competing settings bean.

After changing the path, verify that Provider Configuration/Discovery publishes `registration_endpoint` with the correct public URL. When deployed behind a reverse proxy, the URL must match the issuer and external HTTPS host; never let clients receive an internal container URL or an untrusted HTTP address.

## 5. Required Beans

### 5.1. RegisteredClientRepository

Dynamic registration creates a new `RegisteredClient` and saves it through `RegisteredClientRepository`. If the system already has a repository, reuse it; do not declare a second repository bean just to add the registrar.

Simple lab example:

```java
import java.util.UUID;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Configuration
public class RegistrarClientConfig {

    @Bean
    RegisteredClientRepository registeredClientRepository(
            PasswordEncoder passwordEncoder) {

        RegisteredClient registrar = RegisteredClient
                .withId(UUID.randomUUID().toString())
                .clientId("registration-service")
                .clientSecret(passwordEncoder.encode("change-this-lab-secret"))
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .scope("client.create")
                .scope("client.read")
                .build();

        return new InMemoryRegisteredClientRepository(registrar);
    }
}
```

This is a standalone example with only one registrar and assumes the application already has a `PasswordEncoder` bean. If the application already has other clients, add the registrar to the existing repository or provision it appropriately. `InMemoryRegisteredClientRepository` is only suitable for labs/tests or a single process that does not require durable storage; production generally needs `JdbcRegisteredClientRepository` or an equivalent durable repository.

Lab secrets must be replaced with securely managed secrets. Do not use `{noop}` or hard-code production secrets in source code.

### 5.2. JwtDecoder Is Required by the Endpoint

Spring Authorization Server requires a `JwtDecoder` bean for the Client Registration Endpoint because the endpoint is protected by an OAuth2 Access Token; resource server support is configured, yet the decoder must still be provided:

```java
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.JWKSource;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
```

This example assumes the Authorization Server already has a `JWKSource<SecurityContext>` used to sign JWTs. If a suitable `JwtDecoder` bean already exists, reuse it. Keys must be durably managed, rotated, and never regenerated randomly on every restart.

### 5.3. Do Not Confuse client.create with the New Client's Business Scopes

There are two independent layers of scopes:

| Scope | Belongs To | Purpose |
| --- | --- | --- |
| `client.create` | Registrar client / initial access token | Authorizes creating a new registration |
| `client.read` | Registrar / client management permission | Authorizes reading registration details |
| `openid`, `profile`, `email`, `orders.read`... | Newly registered client | Permissions the new client may request in subsequent OAuth/OIDC flows |

A registration request may ask for scopes `openid profile email`, yet the initial access token used to call `POST /connect/register` must still carry only `client.create` per the Spring Authorization Server guide. Do not grant `client.create` to every business client just because it needs `orders.read`.

## 6. Issuing an Initial Access Token to the Registrar

### 6.1. The Registrar Client Must Be Pre-Registered

A registrar is a special client authorized to create other clients. In the example, the registrar uses:

- Grant type `client_credentials` to request an Access Token directly.
- Client authentication method `client_secret_basic`.
- Scope `client.create` to register clients.
- Scope `client.read` if the registrar needs to read registrations.

These are administrative permissions, not scopes that the newly registered web/mobile application will receive.

### 6.2. Request to the Token Endpoint

Obtain the initial access token with **only the `client.create` scope**:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64(registration-service:REGISTRAR_SECRET)
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=client.create
```

Illustrative response:

```json
{
  "access_token": "INITIAL_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "client.create"
}
```

Do not add `client.read`, `openid`, `profile`, or business scopes to this initial token request. Spring Authorization Server requires the registration token to have **only** the `client.create` scope; tokens with additional scopes will be rejected when calling the Client Registration Endpoint.

### 6.3. The Initial Token Is Single-Use

In the Spring Authorization Server guide, the initial access token is single-use. After a client is successfully registered, this token is invalidated. Therefore:

- Do not store the initial token as a long-lived client management token.
- Do not blindly retry registration POSTs with the same token if the client times out.
- If the response is lost after the server created the client, handle it as an ambiguous outcome; check state through an administrative workflow or registration read if you already have the needed info.
- Do not write the initial token to logs, tickets, shell history, or telemetry.

`registration_access_token` in the response is a separate credential for reading the registration; it is not the initial token.

## 7. Sending a Client Registration Request

### 7.1. JSON Metadata

Example registering a confidential web client using Authorization Code:

```http
POST /connect/register HTTP/1.1
Host: auth.example.com
Authorization: Bearer INITIAL_ACCESS_TOKEN
Content-Type: application/json
Accept: application/json

{
  "client_name": "inventory-web",
  "application_type": "web",
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "redirect_uris": [
    "https://inventory.example.com/login/oauth2/code/oidc"
  ],
  "token_endpoint_auth_method": "client_secret_basic",
  "scope": "openid profile email"
}
```

Metadata is proposed by the registrar. The Authorization Server may accept it, substitute appropriate values, or reject it. The client must not assume every submitted field will be stored verbatim.

### 7.2. Checking Metadata Consistency

| Metadata | What to Validate |
| --- | --- |
| `redirect_uris` | HTTPS in production; exact match with approved domain/path; no wildcards |
| `grant_types` | Enable only required grants; never automatically allow dangerous or deprecated grants |
| `response_types` | Consistent with grant types; Authorization Code corresponds to `code` |
| `token_endpoint_auth_method` | Matches the client type and issued credentials |
| `scope` | Within the allowed scope set for the tenant/client and does not exceed registrar authority |
| `jwks_uri` / `jwks` | Accept public keys only; validate HTTPS, source, and JWK contents |
| `post_logout_redirect_uris` | Validate similarly to login redirect URIs |
| `client_name`, `logo_uri`, `client_uri` | Treat as registrant-supplied display metadata; not proof of identity |

Do not enable Implicit Grant or Resource Owner Password Credentials simply because a client requests them. For new applications, generally prefer Authorization Code + PKCE and select an appropriate client authentication method.

### 7.3. Registration Response

A successful response following the Spring Authorization Server example may contain:

```json
{
  "client_id": "generated-client-id",
  "client_secret": "GENERATED_CLIENT_SECRET",
  "client_id_issued_at": 1800000000,
  "client_secret_expires_at": 0,
  "client_name": "inventory-web",
  "grant_types": [
    "authorization_code",
    "refresh_token"
  ],
  "response_types": [
    "code"
  ],
  "redirect_uris": [
    "https://inventory.example.com/login/oauth2/code/oidc"
  ],
  "scope": "openid profile email",
  "registration_access_token": "REGISTRATION_ACCESS_TOKEN",
  "registration_client_uri": "https://auth.example.com/connect/register/generated-client-id"
}
```

This is a condensed illustrative response. The actual metadata fields depend on client type, converters, and version. `client_secret` is issued only for applicable client types; `registration_access_token` and `client_secret` are sensitive data and must be stored in a secret manager immediately upon receipt. Never expose them in logs or unprotected admin UIs.

### 7.4. Reading Back the Registration

Spring Authorization Server supports Client Read via the returned `registration_client_uri`. The request uses `registration_access_token`:

```http
GET /connect/register/generated-client-id HTTP/1.1
Host: auth.example.com
Authorization: Bearer REGISTRATION_ACCESS_TOKEN
Accept: application/json
```

The Client Read Response returns the registered metadata; per the Spring guide, the read response does not return `registration_access_token` again. Store the management token securely elsewhere if subsequent reads are needed.

The Client Read request is also a protected resource and requires an Access Token with the `client.read` scope. In the Spring guide's flow, the registrar is configured with `client.read` so it can read registrations; ensure the registration access token is issued with the proper read permission and do not use the `client.create` initial token in its place.

**Scope limitation:** the feature covered here includes registering and reading clients. If the system needs update/delete registration operations, verify the specific APIs of your version or build a separate administrative workflow; do not assume full RFC 7592 support simply because the registration endpoint is enabled.

## 8. Customizing Validators and Metadata When Needed

### 8.1. Start with Default Converters/Providers

If you only use standard OIDC metadata supported by Spring Authorization Server, enable the endpoint with `Customizer.withDefaults()` first. The default configuration already includes:

- `OidcClientRegistrationAuthenticationConverter` to parse registration/read requests.
- `OidcClientRegistrationAuthenticationProvider` to validate and create clients.
- `OidcClientConfigurationAuthenticationProvider` to handle client reads.
- Success/error handlers to return registration responses or OAuth errors.

There is no need to write a custom REST controller or custom `AuthenticationProvider` just to get the endpoint working.

### 8.2. Custom Metadata Is Not Persisted Automatically

If your application wants to support custom fields like `logo_uri`, `contacts`, `tenant_id`, or internal metadata, determine:

1. Does the metadata belong to the standard OIDC/OAuth registry or is it a custom extension?
2. Which values may be self-declared by the client, and which must come from registrar policy?
3. Is the data stored in `RegisteredClient`/`ClientSettings` or a separate metadata store?
4. Does Client Read return the same accepted metadata?
5. Is the metadata used for security decisions or display only?

The Spring guide illustrates configuring custom converters on both `OidcClientRegistrationAuthenticationProvider` and `OidcClientConfigurationAuthenticationProvider`, along with converters mapping between `OidcClientRegistration` and `RegisteredClient`. If you extend only the write converter without extending the read converter, client reads may lose custom metadata.

### 8.3. Preserving Default Validation

There is an important difference in recent releases: starting in Spring Authorization Server 1.5.7, `DEFAULT_SCOPE_VALIDATOR` rejects any registration request with a non-empty scope. Therefore, the registration example in section 7.1 containing `scope` will require a custom scope validator; enabling the endpoint with `Customizer.withDefaults()` alone is not enough to accept that scope metadata.

Spring provides `SIMPLE_SCOPE_VALIDATOR` to keep the legacy behavior and accept any scope, but this API **does not enforce an allowlist**. Do not use it as a production solution without another policy restricting scopes. The example below illustrates a static allowlist validator; in a multi-tenant system, replace the static scope set with a policy looked up from the authenticated registrar:

```java
import java.util.List;
import java.util.Set;
import java.util.function.Consumer;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.server.authorization.oidc.OidcClientRegistration;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationValidator;

private static Consumer<List<AuthenticationProvider>> registrationValidator() {
    Set<String> allowedScopes = Set.of("openid", "profile", "email");

    return providers -> providers.forEach(authenticationProvider -> {
        if (authenticationProvider instanceof OidcClientRegistrationAuthenticationProvider provider) {
            provider.setAuthenticationValidator(context -> {
                OidcClientRegistrationAuthenticationValidator
                        .DEFAULT_REDIRECT_URI_VALIDATOR.accept(context);
                OidcClientRegistrationAuthenticationValidator
                        .DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR.accept(context);
                OidcClientRegistrationAuthenticationValidator
                        .DEFAULT_JWK_SET_URI_VALIDATOR.accept(context);

                OidcClientRegistrationAuthenticationToken request =
                        context.getAuthentication();
                OidcClientRegistration registration = request.getClientRegistration();
                List<String> requestedScopes = registration.getScopes();
                if (requestedScopes == null) {
                    requestedScopes = List.of();
                }

                if (!allowedScopes.containsAll(requestedScopes)) {
                    throw new OAuth2AuthenticationException(
                            new OAuth2Error(OAuth2ErrorCodes.INVALID_SCOPE));
                }
            });
        }
    });
}
```

Wire this validator into the endpoint configurer:

```java
.oidc(oidc -> oidc
    .clientRegistrationEndpoint(endpoint ->
        endpoint.authenticationProviders(registrationValidator())
    )
)
```

This example replaces the validator on `OidcClientRegistrationAuthenticationProvider`, while still invoking the default validators for redirect URI, post-logout redirect URI, and JWK Set URI before applying the scope allowlist. In production, the scope allowlist must be derived from server-side registrar/tenant policy; never derive allowed scopes from the registration request itself.

When replacing `authenticationProviders(...)` for customization, do not wipe out all validators just to allow a new scope or metadata field. Keep the default checks for:

- redirect URIs;
- post-logout redirect URIs;
- JWK Set URIs;
- and add your own scope policy tailored to the tenant/registrar.

Never replace these checks with an "accept all" validator for `redirect_uris` or `jwks_uri`. In particular, `SIMPLE_SCOPE_VALIDATOR` accepts every scope; use it only when backward compatibility is strictly required and another policy layer prevents scope injection.

### 8.4. Registrar Scope and Client Metadata Scope Are Two Separate Policies

Permissions are checked at two different stages:

| Stage | Policy |
| --- | --- |
| Requesting initial access token | Is the registrar granted `client.create`? |
| Sending registration request | Is the `scope` metadata requested by the new client permitted? |
| Client performing authorize/token requests later | Is the scope in the registration and permitted by authorization policy? |

Do not infer from a registrar having `client.create` that the new client is allowed to have every scope. The registrar is only allowed to request creating a registration; the server must still evaluate the registration's metadata.

## 9. Securing and Operating Dynamic Client Registration

### 9.1. Protecting the Endpoint with TLS and Registrar Identity

RFC 7591 requires the Registration Endpoint to be protected by transport-layer security. Spring Authorization Server additionally requires a Bearer Access Token for Client Registration and Client Read. In production:

- Issue registrar credentials only to approved provisioning services.
- Issue initial access tokens via an authenticated and audited out-of-band workflow.
- Protect both the Token Endpoint and Registration Endpoint with HTTPS; verify certificates on every calling client.
- Apply network restrictions, rate limits, and quotas per registrar/tenant.
- Revoke registrar credentials if the service is compromised or decommissioned.
- Do not expose the endpoint through a browser/SPA or embed registrar secrets in public applications.

If the organization needs users to initiate onboarding themselves, let an authenticated portal/backend perform approval and issue the initial token to a provisioning service. Never remove Bearer authentication from the Registration Endpoint to turn it into a public API.

### 9.2. Protecting Initial Access Tokens and Registration Access Tokens

- Issue initial access tokens only to the intended registrar and strictly for client creation.
- With Spring Authorization Server, the initial token request has only the `client.create` scope; the token is invalidated after successful registration.
- `registration_access_token` grants read access to the corresponding client configuration; treat it as an administrative credential.
- The new `client_secret` appears only in the registration response; store it in a secret manager immediately and never log the response body.
- Do not share registration access tokens across tenants/clients.
- When a registration is no longer needed, use an appropriate administrative workflow to revoke the client/credentials and clean up metadata.

### 9.3. Metadata Validation and Abuse Prevention

Enforce server-side policies for:

- maximum number of registrations per registrar, tenant, or software publisher;
- `redirect_uris` and `post_logout_redirect_uris` allowlists;
- allowed grant types, response types, scopes, and authentication methods;
- JWK Set URLs, logo URIs, and registrant-supplied URLs;
- public/confidential client types and PKCE requirements;
- client secret lifetimes, token lifetimes, and rotation policies;
- which custom metadata fields may be stored/returned.

Client-supplied URLs can cause the server or admin console to access unintended resources. If your application fetches `jwks_uri`, logos, or metadata URLs, enforce allowlists, redirect limits, blocking of loopback/private/link-local addresses, and timeouts/response size caps to mitigate SSRF risk.

### 9.4. Durable Storage and Multiple Instances

In production, `RegisteredClientRepository` must store data durably and be shared across instances. If one node registers a client and another node cannot read that registration, the client will experience intermittent errors at the Authorization Endpoint or Token Endpoint.

Verify:

- shared repository (e.g., `JdbcRegisteredClientRepository`) and transaction commit before returning registration success;
- unique constraints for client IDs and registration identifiers;
- backup/restore and schema migrations;
- cache invalidation when a client is updated or revoked;
- auditing of who created the client, which registrar, which tenant, and what metadata was accepted;
- handling cases where the initial token was consumed but the response was lost;
- pruning unused registrations according to a retention policy.

### 9.5. Discovery and Endpoint Path

OIDC Provider Configuration includes the `registration_endpoint` metadata to advertise the dynamic registration URL when supported by the OP. After enabling the endpoint or changing the path, inspect the discovery response from a trusted issuer and verify the URL matches `AuthorizationServerSettings`.

Never take `registration_endpoint` from a query parameter or metadata supplied by an untrusted client. Clients/developers must know the issuer first, verify the issuer/discovery document, and only then send credentials to the published endpoint.

## 10. Testing the Endpoint by Scope and Version

### 10.1. Test Matrix

| ID | Scenario | Expected Result |
| --- | --- | --- |
| DCR-01 | OIDC enabled but Client Registration Endpoint not enabled | Registration endpoint is not registered in the filter chain |
| DCR-02 | Enable `clientRegistrationEndpoint(Customizer.withDefaults())` | Filter handling registration/read is registered |
| DCR-03 | Call `POST /connect/register` with a valid initial token | Client is created and registration response is returned |
| DCR-04 | Missing Bearer token | Request is rejected |
| DCR-05 | Invalid/expired Bearer token | Request is rejected due to invalid Access Token |
| DCR-06 | Initial token has only `client.create` and metadata scope validator is configured | Registration succeeds if metadata is valid |
| DCR-07 | Initial token also contains `client.read` or another scope | Registration rejected per Spring Authorization Server policy |
| DCR-08 | Token lacks `client.create` | Client is not created |
| DCR-09 | Reuse initial token after successful registration | Subsequent request rejected because token was invalidated |
| DCR-10 | Registering an unacceptable redirect URI | Registration rejected |
| DCR-11 | Inconsistent grant/response type metadata | Registration rejected or metadata adjusted per validator |
| DCR-12 | Client requests out-of-policy scopes | Server does not grant over-privileged scopes; response/error reflects decision |
| DCR-13 | `JwtDecoder` bean missing | Incomplete endpoint configuration; startup/integration tests must catch it |
| DCR-14 | `AuthorizationServerSettings` path changed but client calls old path | Request does not reach configured endpoint |
| DCR-15 | Discovery publishes `registration_endpoint` | URL matches the configured path and public issuer |
| DCR-16 | Read registration with valid registration access token | Client Read returns registered metadata |
| DCR-17 | Read registration with wrong token or different registration URI | Request is rejected |
| DCR-18 | Client Read response | Does not re-expose `registration_access_token` per Spring guide |
| DCR-19 | Registrar client lacks `client.create` in RegisteredClient | Cannot request an initial access token with this scope |
| DCR-20 | Registrar client requests both `client.create` and `client.read` | Token fails initial registration requirements; must request only `client.create` |
| DCR-21 | Multiple registrars create clients concurrently | No duplicate client IDs; repository stays consistent |
| DCR-22 | Two Authorization Server instances share a repository | The other node can read the new client after commit |
| DCR-23 | Custom metadata mapped only on write | Test catches metadata missing on Client Read |
| DCR-24 | Custom validator skips redirect URI validation | Security test must fail; preserve default validators |
| DCR-25 | Registrar exceeds quota | Registration rejected and audited |
| DCR-26 | Registering `jwks_uri` pointing to an internal address | URL policy rejects or refuses to fetch the resource |
| DCR-27 | Initial token response lost after server creates client | Do not blindly retry with old token; perform reconciliation |
| DCR-28 | Upgrade Spring Authorization Server from 1.4.x to 1.5.x | Compile/integration tests confirm configurer, decoder, and metadata work |
| DCR-29 | Run on 2.0 preview branch | Test separately; do not assume compatibility with 1.x APIs |
| DCR-30 | New client uses Authorization Code + PKCE | Registration metadata and Authorization Endpoint policy accept configuration properly |
| DCR-31 | SAS 1.5.7+ uses default scope validator with a request containing `scope` | Request rejected until a custom scope validator is configured |
| DCR-32 | Scope allowlist validator accepts `openid profile email` | Only allowlisted scopes accepted; non-listed scopes rejected |
| DCR-33 | Client Read uses Access Token missing `client.read` | Request rejected even if token is unexpired |

### 10.2. End-to-End Flow Integration Test

A basic integration test scenario:

1. Start the Authorization Server with OIDC and the Client Registration Endpoint enabled.
2. Register a registrar client with `client_credentials`, `client.create`, and `client.read`.
3. Request an initial access token with only `scope=client.create`.
4. Send a registration POST with valid redirect URIs and metadata.
5. Verify the response contains `client_id`, along with `registration_client_uri` and `registration_access_token` when issued.
6. Use the registration access token to call the Client Read Endpoint.
7. Verify the read-back metadata matches the accepted registration.
8. Retry POST using the old initial token and verify it is rejected.
9. Try POST using a token missing the scope or containing extra scopes.
10. Verify the new client can execute its registered flow, such as Authorization Code with the corresponding redirect URI.

Do not only test that `POST /connect/register` returns success. Verify that the client is persisted in the repository and actually recognized by the Authorization Endpoint/Token Endpoint.

### 10.3. Version Compatibility Checks

When changing versions:

- recompile the filter chain and `AuthorizationServerSettings`;
- confirm `OidcClientRegistrationEndpointConfigurer` and provider classes remain in the API;
- confirm `JwtDecoder` is properly wired;
- re-run tests for registrar scopes, one-time tokens, and Client Read;
- inspect discovery metadata after upgrading;
- read the release notes/migration notes for the exact branch before modifying custom converters or validators.

## 11. Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `404` at `/connect/register` | Endpoint not enabled or path customized | Check `.oidc(...clientRegistrationEndpoint(...))` and `AuthorizationServerSettings` |
| `401` on registration | Missing/invalid/expired initial access token | Check Bearer header and verify token was issued by the right issuer |
| Valid token but registration rejected | Token lacks exact `client.create` scope or has extra scopes | Request initial token with `client.create` only |
| `invalid_client` when requesting token | Wrong registrar client credentials or auth method | Check `RegisteredClient`, secret encoder, and `client_secret_basic` |
| `invalid_scope` at Token Endpoint | Registrar has not been granted `client.create` | Add scope to the registrar registration per policy |
| `invalid_client_metadata` | Invalid redirect URI, grant type, scope, or metadata | Read error response and validators; do not disable all validation |
| Cannot create registration in database | Repository cannot persist or transaction/schema error | Check repository and database migrations |
| Missing `JwtDecoder` bean | Protected resource endpoint cannot verify JWT Access Token | Declare a decoder matching the JWK source |
| New client cannot authorize | Metadata was substituted, redirect URI mismatch, or grant rejected | Inspect registration response and stored `RegisteredClient` |
| Client Read returns `401` | Wrong/expired registration access token or wrong registration | Use the token and URI from the matching registration response |
| Custom metadata missing on read | Customized only the registration-direction converter | Configure the `RegisteredClient` → `OidcClientRegistration` converter too |
| Client registration works on one node only | Repository/cache not shared across nodes | Use a shared repository and synchronize caches |
| Retrying registration always fails | Initial token was already consumed and invalidated | Request a new token per policy; reconcile first to see if client was created |
| Discovery missing `registration_endpoint` | Metadata not published or custom provider config | Check `OidcProviderConfiguration` and metadata customizers |
| IDE does not recognize `clientRegistrationEndpoint` | Wrong version or dependency conflict | Inspect dependency tree and docs for the right branch |

### 11.1. Distinguishing Registrar Errors from New Client Metadata Errors

1. **Registrar authentication failure:** The Authorization Server cannot authenticate the registrar at the Token Endpoint.
2. **Initial token authorization failure:** The registrar is authenticated, but the token lacks the exact scope to register.
3. **Registration metadata failure:** The token is valid, but the new client's metadata fails validation.
4. **Persistence/runtime failure:** Metadata is valid, but the repository or database fails to save it.

Separating these error layers prevents loosening validators or over-granting permissions just to work around a configuration issue.

### 11.2. Unsafe Fixes to Avoid

- Do not disable Bearer token validation to work around a `401`.
- Do not grant `client.create` to all clients just to avoid `invalid_scope`.
- Do not allow wildcard redirect URIs or arbitrary hosts.
- Do not remove default validators when adding custom metadata.
- Do not log initial access tokens, registration access tokens, or client secrets.
- Do not use `InMemoryRegisteredClientRepository` for a production cluster needing durable data.
- Do not claim the endpoint fully supports update/delete if your version is only configured/tested for register and read.

## 12. Production Checklist and Reference Documentation

### 12.1. Pre-Enablement Checklist

- [ ] Spring Authorization Server version confirmed and code uses the matching branch API.
- [ ] OIDC enabled in the Authorization Server configurer.
- [ ] Client Registration Endpoint enabled only when there is a clear provisioning need.
- [ ] Endpoint path and `registration_endpoint` discovery match the public URL.
- [ ] `JwtDecoder` bean is present and verifies Access Tokens against trusted keys/issuer.
- [ ] Registrar client is pre-registered, uses `client_credentials`, and has an appropriate auth method.
- [ ] Registrar is granted only required admin scopes (`client.create`, and `client.read` if needed).
- [ ] Initial access token is requested with only `client.create`.
- [ ] Initial token is treated as a one-time credential and never saved/logged for reuse.
- [ ] `redirect_uris`, grant types, response types, scopes, and auth methods metadata are validated.
- [ ] Clients cannot self-grant scopes exceeding tenant/registrar authority.
- [ ] Custom metadata has converters for both write and read directions.
- [ ] Default validators for redirect URI/JWK/scope are preserved or replaced by an equally strict policy.
- [ ] `RegisteredClientRepository` uses durable storage shared across nodes.
- [ ] `client_secret` and `registration_access_token` are stored in a secret manager.
- [ ] Rate limits, quotas, auditing, and registrar/client revocation procedures are in place.
- [ ] Integration tests cover registration, read, invalid tokens, wrong scopes, one-time tokens, and version upgrades.
- [ ] Reconciliation procedure exists for cases where POST created a client but the response was lost.

### Memory Map

```text
Provisioning service / Registrar
       |
       | client_id + client_secret (registrar)
       v
POST /oauth2/token
grant_type=client_credentials
scope=client.create
       |
       v
Initial Access Token (one-time)
       |
       | Authorization: Bearer <initial-token>
       v
POST /connect/register
Content-Type: application/json
       |
       v
Spring Authorization Server
  - authenticate bearer token
  - require client.create only
  - validate client metadata
  - save RegisteredClient
       |
       v
Registration response
  client_id
  client_secret (if applicable)
  registration_access_token
  registration_client_uri
       |
       v
GET registration_client_uri
Authorization: Bearer <registration-access-token>
       |
       v
Client Read Response

Security boundary:
  registrar permission != new client's OAuth scopes
```

**Key takeaway:** Spring Authorization Server disables the OIDC Client Registration Endpoint by default. With the 1.5.x API, enable the endpoint via `oidc.clientRegistrationEndpoint(...)`, configure `JwtDecoder`, register a registrar client, and issue an initial access token with only `client.create`. The endpoint uses that token to create a `RegisteredClient`; the response returns client metadata along with registration access details. Client Read uses a separate registration access token. Maintain metadata validation, constrain registrar scopes, use durable repository persistence, and verify the API for your exact version before taking DCR to production.

## Authoritative Reference Documentation

- [Spring Authorization Server 1.5.8 — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): enabling the endpoint, registrar scopes, initial access tokens, registration, and client read.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OidcClientRegistrationEndpointConfigurer`, filters, providers, protected resource behavior, and scope requirements.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `AuthorizationServerSettings` and protocol endpoint configuration.
- [Spring Authorization Server 1.5.8 — OidcClientRegistrationAuthenticationValidator API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationValidator.html): strict/default validators, scope behavior, and compatibility validators.
- [Spring Authorization Server 1.4.8 — Dynamic Client Registration guide](https://docs.spring.io/spring-authorization-server/reference/1.4/guides/how-to-dynamic-client-registration.html): reference for the 1.4.x branch.
- [Spring Authorization Server 1.3.7 — Dynamic Client Registration guide](https://docs.spring.io/spring-authorization-server/reference/1.3/guides/how-to-dynamic-client-registration.html): reference for the 1.3.x branch.
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591.html): client metadata, registration request/response, software statements, and initial access tokens.
- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): OIDC client registration metadata and protocol rules.
- [RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol](https://www.rfc-editor.org/rfc/rfc7592.html): separate registration management protocol to consult before designing update/delete operations.
