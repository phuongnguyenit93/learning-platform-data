# Dispatching Providers by grant_type

> **Chapter:** Token Endpoint  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Module Objective:** Learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application.  
> **Example Scope:** Spring Boot 3.x, Spring Security 6.x, Spring Authorization Server 1.5.x on the Servlet stack; examples use the `OAuth2AuthorizationServerConfigurer.authorizationServer()` API. For Spring Security 7.x with integrated Authorization Server functionality, verify the packages and DSL of that version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the role of `grant_type` in an HTTP request to `/oauth2/token` and distinguish it from **OAuth2 Client authentication methods**.
2. Describe the pipeline `OAuth2TokenEndpointFilter → AuthenticationConverter → AuthenticationManager/ProviderManager → AuthenticationProvider → OAuth2TokenGenerator → response handler`.
3. Identify the default converter/provider pairs for `authorization_code`, `refresh_token`, `client_credentials`, Device Code, and Token Exchange in the applicable Spring Authorization Server version.
4. Understand provider selection via **`Authentication` type** and `supports(...)`, rather than assuming the framework simply uses a direct `switch(grant_type)` statement.
5. Recognize the grant-specific checks: code/PKCE/redirect URI, refresh-token binding, client scopes, device authorization state, and token exchange subject tokens.
6. Configure `OAuth2TokenEndpointConfigurer`, customize default providers safely, and add extension grants without breaking built-in mechanisms.
7. Thoroughly test success and error branches, including missing providers, denied client grants, mismatched provider types, and concurrent requests.

**Key Idea:** `grant_type` identifies **which type of grant the client is requesting**. To issue tokens safely, however, the AS must also verify **which client is calling**, whether that client **is permitted to use that grant**, and whether all **grant-specific requirements** are satisfied.

## 2. The Token Endpoint Is Not a Login Page

In OAuth 2.0, the Token Endpoint is the HTTP endpoint where an OAuth2 Client presents an authorization grant or appropriate credentials to request a token. With Spring Authorization Server 1.x defaults, the URL is typically:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=booking.read
~~~

This example **omits client authentication credentials**; a confidential client normally must supply `Authorization: Basic ...` or another registered method. `grant_type` is a parameter in the `application/x-www-form-urlencoded` body, not a separate URL path per grant.

Unlike `/oauth2/authorize`:

- The **Authorization Endpoint** primarily coordinates the browser, Resource Owner login, consent, and issuing an authorization code.
- The **Token Endpoint** is a back-channel API receiving requests from an OAuth2 Client; it must not redirect to `/login` as the default response for grant errors.
- Depending on the grant, the client may be a BFF backend, a service account, a mobile/public client app, or an input-constrained device.
- A Resource Owner does not necessarily participate in the token request. For example, Client Credentials has no logged-in user, and Refresh Token relies on a previously stored authorization.

### 2.1. Two Distinct Questions Before Issuing a Token

| Question | Responsible Component | Examples |
| --- | --- | --- |
| **Who is calling the Token Endpoint?** | `OAuth2ClientAuthenticationFilter` with client authentication converters/providers | `client_secret_basic`, `private_key_jwt`, mTLS, `none` |
| **Which grant is the client using to request a token?** | `OAuth2TokenEndpointFilter` with grant converters/providers | `authorization_code`, `refresh_token`, `client_credentials`, Device Code, Token Exchange |

Never treat `grant_type=client_credentials` as "the client is already authenticated," and never treat a valid `client_secret` as "permitted to execute every grant."

## 3. Request Processing Architecture in Spring Authorization Server

On the Servlet stack, `OAuth2AuthorizationServerConfigurer` configures the relevant filters in the `SecurityFilterChain`. Two components are central to the token endpoint:

1. `OAuth2ClientAuthenticationFilter`: handles client authentication/identification methods per the registered client.
2. `OAuth2TokenEndpointFilter`: handles access-token requests, selects the appropriate converter and provider, and returns a token or OAuth2 error.

~~~mermaid
flowchart TD
    R["POST /oauth2/token"]
    F["SecurityFilterChain for the Authorization Server"]
    CA["OAuth2ClientAuthenticationFilter<br/>ClientAuthenticationConverter / Provider"]
    CI{"Valid client per<br/>registration and policy?"}
    TE["OAuth2TokenEndpointFilter"]
    CO["DelegatingAuthenticationConverter<br/>Classify by grant_type"]
    GT["Authentication token representing grant<br/>Code / Refresh / ClientCredentials / Device / Exchange"]
    AM["AuthenticationManager / ProviderManager"]
    PV["AuthenticationProvider supporting the Authentication type"]
    V{"Valid grant?<br/>Client allowed grant?<br/>Grant conditions met?"}
    GEN["OAuth2TokenGenerator + AuthorizationService"]
    OK["OAuth2AccessTokenAuthenticationToken"]
    RESP["Access Token Response Handler<br/>200 JSON + no-store"]
    ERR["OAuth2 Error / Client Authentication Error<br/>no token issued"]

    R --> F --> CA --> CI
    CI -->|"No"| ERR
    CI -->|"Yes"| TE --> CO --> GT --> AM --> PV --> V
    V -->|"No"| ERR
    V -->|"Yes"| GEN --> OK --> RESP
~~~

This diagram shows the **typical logical flow**; it does not assert that every request passes through the exact same method order in every implementation or that every error is thrown from the same filter. Client authentication failures can terminate the request before a grant provider is ever invoked.

### 3.1. Extension Structure

`OAuth2TokenEndpointConfigurer` is Spring Authorization Server's DSL for customizing `OAuth2TokenEndpointFilter`. According to the 1.5.x branch documentation, there are six primary extension points:

| API | Phase | Responsibility |
| --- | --- | --- |
| `accessTokenRequestConverter(...)` | Before grant authentication | Adds an `AuthenticationConverter` |
| `accessTokenRequestConverters(...)` | Before grant authentication | Accesses, adds, orders, or customizes the converter list |
| `authenticationProvider(...)` | Grant processing | Adds an `AuthenticationProvider` |
| `authenticationProviders(...)` | Grant processing | Accesses default and additional providers for customization |
| `accessTokenResponseHandler(...)` | After success | Produces the OAuth2 token response from `OAuth2AccessTokenAuthenticationToken` |
| `errorResponseHandler(...)` | After failure | Produces the OAuth2 error response from `OAuth2AuthenticationException` |

Most systems only need to configure `RegisteredClient` and the core services; **there is no need to rewrite converters, providers, or response handlers**. Deeper customization requires thorough protocol and security testing.

## 4. List of Default grant_types and Providers

In Spring Authorization Server **1.5.x**, the Token Endpoint supports the following grants; older 1.2.x releases do not include all of them—in particular, verify your release/version before using Token Exchange.

| Submitted `grant_type` | Default Converter | Default Provider | Evidence Proving the Grant |
| --- | --- | --- | --- |
| `authorization_code` | `OAuth2AuthorizationCodeAuthenticationConverter` | `OAuth2AuthorizationCodeAuthenticationProvider` | Unexpired code, matching client/redirect URI, PKCE |
| `refresh_token` | `OAuth2RefreshTokenAuthenticationConverter` | `OAuth2RefreshTokenAuthenticationProvider` | Active refresh token, matching client, non-expanded scope |
| `client_credentials` | `OAuth2ClientCredentialsAuthenticationConverter` | `OAuth2ClientCredentialsAuthenticationProvider` | Valid client, permitted grant type, valid scopes |
| `urn:ietf:params:oauth:grant-type:device_code` | `OAuth2DeviceCodeAuthenticationConverter` | `OAuth2DeviceCodeAuthenticationProvider` | Unexpired device code, approval/denial state, client binding |
| `urn:ietf:params:oauth:grant-type:token-exchange` | `OAuth2TokenExchangeAuthenticationConverter` | `OAuth2TokenExchangeAuthenticationProvider` | Subject token and valid exchange request per RFC 8693/policy |

Official source: [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html).

### 4.1. What Happens with an Unsupported grant_type?

Example:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <valid-confidential-client-credential>
Content-Type: application/x-www-form-urlencoded

grant_type=password&username=lan&password=not-for-production
~~~

`password` (Resource Owner Password Credentials) is a legacy grant, **is not in the default provider list above**, and should not be added to bypass interactive user login in new systems. When a grant type is unsupported, the token endpoint must return the appropriate OAuth2 error, typically `unsupported_grant_type`.

If a grant type **is supported by the server** but **the client is not permitted to use it** per `RegisteredClient.authorizationGrantTypes`, that is a different case; the error code is typically `unauthorized_client`. Never blindly add grants to `RegisteredClient` just to silence an error without evaluating the threat model.

### 4.2. "Token Exchange" Does Not Mean Every Token Swap Is Permitted

In versions that support Token Exchange, `grant_type=urn:ietf:params:oauth:grant-type:token-exchange` follows RFC 8693. The provider must validate the subject token, token type, actor token if present, audience/resource, scope, and delegation/impersonation policy.

Do not infer from the presence of a built-in converter/provider that any client may exchange any user's token for any API or tenant. Every token exchange case requires explicit authorization rules and tests covering audience constraints.

## 5. Step A: Authenticating the OAuth2 Client Before Grant Dispatching

At the Token Endpoint, client authentication is **independent of** evaluating `grant_type`. Mechanisms supported by Spring Authorization Server include:

- `client_secret_basic`: confidential client sends ID/secret via HTTP Basic.
- `client_secret_post`: sends credentials in the body per registration policy; consider avoiding when unnecessary.
- `private_key_jwt` or `client_secret_jwt`: signed client assertion verified by the AS.
- `tls_client_auth` or `self_signed_tls_client_auth`: binds client identity via a TLS certificate.
- `none`: public client without a secret, allowed only with suitable grants and protections.

Confidential client example:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <base64-encoded-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=booking.read
~~~

When client authentication succeeds, Spring Authorization Server can place an `OAuth2ClientAuthenticationToken` into the `SecurityContext` so grant providers can identify the authenticated client.

**Warning:** `client_id` is an identifier, not a secret. For public clients, `none` is only appropriate for supported grants with corresponding protections (such as PKCE for Authorization Code). Never switch Client Credentials to `ClientAuthenticationMethod.NONE` just to avoid managing secrets in a backend service.

### 5.1. When Do You Get `invalid_client`?

If the secret is wrong, the client assertion is invalid, the authentication method does not match registration, or the client fails policy-based authentication, the request can be rejected **before** `OAuth2TokenEndpointFilter` selects a grant provider.

Do not debug this error by customizing `OAuth2ClientCredentialsAuthenticationProvider`—the class name looks similar, but it handles the **Client Credentials Grant**, not general client-secret authentication across all grants.

## 6. Step B: Converter Accepts the Request by grant_type

### 6.1. `DelegatingAuthenticationConverter` Classifies the Request

The token endpoint receives the form-encoded request and applies converters. Under default configuration, `DelegatingAuthenticationConverter` tries each converter in order and uses the `Authentication` returned by the matching converter.

Each converter is designed to recognize one grant type:

~~~text
grant_type=authorization_code
   -> OAuth2AuthorizationCodeAuthenticationConverter
   -> OAuth2AuthorizationCodeAuthenticationToken

grant_type=refresh_token
   -> OAuth2RefreshTokenAuthenticationConverter
   -> OAuth2RefreshTokenAuthenticationToken

grant_type=client_credentials
   -> OAuth2ClientCredentialsAuthenticationConverter
   -> OAuth2ClientCredentialsAuthenticationToken

grant_type=urn:ietf:params:oauth:grant-type:device_code
   -> OAuth2DeviceCodeAuthenticationConverter
   -> OAuth2DeviceCodeAuthenticationToken

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
   -> OAuth2TokenExchangeAuthenticationConverter
   -> OAuth2TokenExchangeAuthenticationToken
~~~

These class names illustrate the default components of the **1.5.x branch**. Do not force every grant into `UsernamePasswordAuthenticationToken`: dedicated `Authentication` types tell the provider exactly which constraints to verify.

### 6.2. A Converter Is Not a Provider

A converter is typically responsible for:

- Recognizing the matching `grant_type` and returning `null` if it does not handle that type.
- Extracting parameters such as `code`, `refresh_token`, `scope`, `device_code`, etc.
- Performing preliminary request-shape checks, such as required parameters or invalid duplicate occurrences.
- Attaching the authenticated client principal to the grant authentication object.
- Creating an `Authentication` object that the corresponding provider can process.

A converter **does not** replace the following steps:

- Verifying client assertion signatures.
- Checking that an authorization code belongs to the client.
- Checking that a refresh token is still active.
- Verifying scopes granted by the Resource Owner.
- Generating access tokens or persisting authorizations.

Therefore, customizing a converter to "read extra parameters" must never turn it into a place that issues tokens or skips server-side validation.

### 6.3. Do Not Let a Custom Converter Claim Every Request

A faulty implementation might always return an `Authentication` regardless of `grant_type`, starving standard converters of the chance to run. For an extension grant, the converter must:

1. Check the exact `grant_type` value it supports.
2. Return `null` when the request belongs to another grant.
3. Parse only the required parameters, rejecting invalid multi-valued parameters.
4. Refuse raw access tokens/refresh tokens from the query string if the grant requires the body.
5. Never set `authenticated=true` itself to bypass the provider.
6. Have tests verifying that it matches its grant and **does not falsely match** other grants.

## 7. Step C: AuthenticationManager Selects the Right Provider

After the converter, `OAuth2TokenEndpointFilter` passes the `Authentication` to an `AuthenticationManager`, typically backed by `ProviderManager`.

### 7.1. Why Not Dispatch Providers with a Simple Switch?

Conceptually, the logic looks like:

~~~text
Authentication authRequest = converter.convert(httpRequest);
Authentication result = authenticationManager.authenticate(authRequest);
~~~

`ProviderManager` then inspects configured providers via the `supports(Class<?> authentication)` contract and processes the request according to Spring Security rules. Built-in providers decline `Authentication` types outside their responsibility; the matching provider verifies the grant and returns a result.

**This is pseudocode**, not the full implementation of `OAuth2TokenEndpointFilter`. The takeaway is that **the `grant_type` value is converted into a grant authentication type**, and the provider is chosen through **the contract supporting that type**. `supports(...)` **does not prove** the request is authorized to use the grant; whether the grant is permitted must be verified inside the provider.

### 7.2. Provider Order Matters When Customizing

Suppose an application adds a new provider for an internal grant. You must verify:

- The new provider's `supports(...)` matches only its custom `Authentication` class.
- The provider does not accidentally intercept default tokens such as `OAuth2RefreshTokenAuthenticationToken`.
- If multiple providers support the same type, their order and exception/return behavior produce the intended outcome.
- A provider does not treat a security exception as "try another provider until someone issues a token."
- Default providers remain present and unrelated grants continue working.

Overly broad customization can misroute requests, return misleading errors, or bypass critical default validations.

## 8. Each Provider Must Enforce Its Grant-Specific Policy

### 8.1. Authorization Code Grant

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-secret-basic>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=ONE_TIME_CODE&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&code_verifier=VALID_PKCE_VERIFIER
~~~

`OAuth2AuthorizationCodeAuthenticationProvider` must check, as applicable:

- The client has been identified/authenticated per its registration.
- The client is permitted to use `authorization_code`.
- The authorization code belongs to the right client and stored grant.
- The code is unexpired, unused, and not invalidated.
- `redirect_uri` matches the value from the authorization request when required.
- `code_verifier` satisfies the PKCE challenge when required by the flow.
- Issued tokens contain only scopes/claims permitted by policy.

Knowing `code` alone is never enough. Codes are single-use; any invalid exchange attempt must **issue no token**. Users log in at `/oauth2/authorize`, never by re-entering passwords at the Token Endpoint.

### 8.2. Refresh Token Grant

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-secret-basic>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REFRESH_TOKEN_VALUE&scope=booking.read
~~~

`OAuth2RefreshTokenAuthenticationProvider` checks:

- The client is properly authenticated and registered for `refresh_token`.
- The refresh token belongs to an AS-recognized authorization and **the right client**.
- The token is active, unexpired, and not revoked or already consumed per policy.
- Requested scopes do not exceed `OAuth2Authorization.getAuthorizedScopes()`.
- New access tokens and new/reused refresh tokens are issued and updated per `TokenSettings`.

Do not use `RegisteredClient.getScopes()` alone to expand permissions; a client may be registered with many scopes while the Resource Owner consented to only a subset. `reuseRefreshTokens(false)` enforces policy-based rotation, **and does not by itself guarantee system-wide replay detection or token-family revocation**.

### 8.3. Client Credentials Grant

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-secret-basic>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=booking.read
~~~

`OAuth2ClientCredentialsAuthenticationProvider` typically checks:

- The client is allowed to use `client_credentials`.
- Client authentication succeeded in the preceding step.
- Requested scopes fall within the registration and applicable policy.
- Tokens are issued for the client/service identity, not representing a Resource Owner.
- No refresh token is assumed; RFC 6749 recommends not issuing refresh tokens for Client Credentials.

For example, the authorization service may mint a token with `sub` or `client_id` identifying the client. On the Resource Server, **do not treat the principal as a human user** simply because a `sub` claim exists. Business domains may require distinct application permissions and tenant isolation.

### 8.4. Device Authorization Grant at the Token Endpoint

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code&device_code=DEVICE_CODE_VALUE&client_id=booking-tv
~~~

For public clients, `client_id` identifies the client per registration. `OAuth2DeviceCodeAuthenticationProvider` must verify the device code, client binding, expiration, and user verification/consent status.

Standard responses per RFC 8628:

| State | OAuth2 Error | Device Action |
| --- | --- | --- |
| User has not completed flow | `authorization_pending` | Continue polling after at least `interval` |
| Polling too fast | `slow_down` | Increase wait interval by 5 seconds |
| User denied request | `access_denied` | Stop polling |
| Device session expired | `expired_token` | Stop, start a new session when user requests |
| User approved and grant valid | Successful token response | Store token securely, stop polling |

**Devices must never send `user_code` in place of `device_code`.** `user_code` is entered by the Resource Owner at the Device Verification Endpoint; `device_code` is the device's credential at the Token Endpoint.

### 8.5. Token Exchange Grant

Conceptual example per RFC 8693:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <client-secret-basic>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange&subject_token=SUBJECT_TOKEN&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token&audience=booking-api
~~~

In versions providing `OAuth2TokenExchangeAuthenticationProvider`, the system must verify constraints such as subject token type, token validity and trust, client permission to exchange, target audience, scopes, and allowed user/client delegation relationships. If `actor_token` or `requested_token_type` is present, follow the RFC and implementation rules.

**Never assume Token Exchange lets any client swap any customer's token for a new one.** The client must hold explicit exchange permission, the input token must be verified, and the target audience/resource must be restricted. Support for RFC 8693 variants depends on the specific Spring version and configuration; always test on the target environment.

## 9. Step D: What Do the Token Generator and Authorization Service Do?

Once the provider has verified that the grant is valid, it uses core components:

| Component | Role |
| --- | --- |
| `OAuth2TokenGenerator` | API for generating tokens based on `OAuth2TokenContext`, token type, and settings |
| `DelegatingOAuth2TokenGenerator` | Delegates to the appropriate token generators |
| `JwtGenerator` | Generates JWTs for token types configured accordingly |
| `OAuth2AccessTokenGenerator` | Generates access tokens, typically reference/opaque when configured that way |
| `OAuth2RefreshTokenGenerator` | Generates refresh tokens per policy |
| `OAuth2TokenCustomizer` | Customizes claims or token details within permitted bounds |
| `OAuth2AuthorizationService` | Persists authorization state, codes/tokens, metadata, and invalidations |
| `RegisteredClientRepository` | Supplies grant types, token settings, scopes, and client auth methods |
| `OAuth2AuthorizationConsentService` | Consent data when the grant involves a Resource Owner |

**Separation of concerns:** the provider decides whether the grant is valid; the token generator mints tokens from the context; the authorization service manages state. If customizing the generator drops a required generator, a grant may fail to produce the corresponding access token, ID token, or refresh token.

### 9.1. Successful Token Response

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "booking.read"
}
~~~

Depending on the grant and policy, the response may contain `refresh_token` and/or `id_token`. An **ID token** belongs to OpenID Connect and must not be issued simply because a client sent `scope=openid` on an arbitrary grant if the protocol/provider disallows it. The **access token** is the credential the Resource Server uses to evaluate API access.

### 9.2. Do Not Use a Token Generator in Place of Authorization Checks

Anti-pattern example:

~~~java
// Wrong principle: manually generate access token after only checking grant_type.
if ("client_credentials".equals(request.getParameter("grant_type"))) {
    // Does not verify client, grant permission, scope, rate limit...
    // and issues a token directly from a controller.
}
~~~

Let requests flow through standard providers. If adding a specialized grant, the custom provider must **fully enforce its own grant requirements** and invoke the token generator only after validation passes.

## 10. Configuring SecurityFilterChain and the Token Endpoint

### 10.1. Default Configuration Should Be Your Starting Point

On Spring Authorization Server 1.x, the token endpoint is configured via `OAuth2AuthorizationServerConfigurer`. The following example leaves default providers intact:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, configurer ->
                configurer.tokenEndpoint(Customizer.withDefaults())
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

**Scope note:** this snippet assumes `RegisteredClientRepository`, `OAuth2AuthorizationService`, token generator/keys/issuer configuration, user authentication, and other required AS beans already exist. For an authorization endpoint that must redirect unauthenticated users, real applications usually configure `LoginUrlAuthenticationEntryPoint("/login")` for HTML requests in the AS chain. Since this example focuses on the token pipeline, browser login/OIDC details are omitted.

The first `SecurityFilterChain` uses `getEndpointsMatcher()` so OAuth2 endpoints are handled by dedicated filters; the second chain handles the web/login application. Never let a catch-all chain match `anyRequest` ahead of the AS chain.

### 10.2. Customizing a Default Provider's Policy

To add validation to `client_credentials`, use `authenticationProviders(...)` to locate the default provider and attach a validator while **preserving default scope validation**.

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .tokenEndpoint(token -> token
                .authenticationProviders(providers ->
                    providers.forEach(provider -> {
                        if (provider instanceof
                                OAuth2ClientCredentialsAuthenticationProvider
                                    clientCredentialsProvider) {

                            var validator =
                                OAuth2ClientCredentialsAuthenticationValidator
                                    .DEFAULT_SCOPE_VALIDATOR
                                    .andThen(context -> {
                                        String clientId = context
                                            .getRegisteredClient().getClientId();
                                        boolean wantsSensitiveScope = context
                                            .getAuthentication().getScopes()
                                            .contains("payments.write");

                                        if ("batch-reporter".equals(clientId)
                                                && wantsSensitiveScope) {
                                            throw new OAuth2AuthenticationException(
                                                new OAuth2Error(
                                                    OAuth2ErrorCodes.INVALID_SCOPE));
                                        }
                                    });

                            clientCredentialsProvider
                                .setAuthenticationValidator(validator);
                        }
                    })
                )
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Additional imports:

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2ClientCredentialsAuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2ClientCredentialsAuthenticationValidator;
~~~

**These two snippets are alternative configurations**—do not declare two identical `@Order(1)` beans from these examples simultaneously. The second configuration assumes the beans and imports from the first example are present.

Why use `DEFAULT_SCOPE_VALIDATOR.andThen(...)`?

- `setAuthenticationValidator(...)` **replaces the existing validator** rather than preserving it automatically.
- The default validator enforces scope limits from the client registration.
- Custom logic adds a stricter restriction specifically for client `batch-reporter`.
- It avoids accidentally validating `payments.write` for a client that was never granted that scope.
- Custom policies should be tested to ensure unregistered scopes are still rejected even when the custom rule does not match.

This demonstrates **targeting only the relevant grant provider** without altering `authorization_code` or `refresh_token` providers.

### 10.3. When Should You Use `authenticationProvider(...)`?

When adding **a new grant type** outside the built-in providers, you need to:

1. Define a new `AuthorizationGrantType` with a clearly namespaced URI.
2. Register that grant type on the `RegisteredClient` instances permitted to use it.
3. Write an `AuthenticationConverter` that accurately recognizes the request and builds a dedicated `Authentication` type.
4. Write an `AuthenticationProvider` whose `supports(...)` matches only that custom type and verifies the client, proof, scope, and grant policy.
5. Use `OAuth2TokenGenerator` and `OAuth2AuthorizationService` to mint and persist tokens per rules.
6. Register both converter and provider via `OAuth2TokenEndpointConfigurer`.
7. Test valid requests, invalid requests, replay, multiple clients, token lifecycles, and verify default grants remain unaffected.

Never add a provider whose `supports(Authentication.class)` returns `true`. A provider matching every authentication type can break or weaken the entire pipeline.

## 11. Controlled Extension Grant Implementation Example

Suppose a system has an internal grant `urn:example:params:oauth:grant-type:partner_ticket`. **This is not a standard OAuth2 grant** and should only be used if the organization genuinely has a verifiable credential/proof; never treat an arbitrary client-supplied `ticket` string as trustworthy.

### 11.1. Registration Must Explicitly Allow the Grant

~~~java
AuthorizationGrantType partnerGrant = new AuthorizationGrantType(
    "urn:example:params:oauth:grant-type:partner_ticket");

RegisteredClient partnerClient = RegisteredClient
    .withId("partner-client-id")
    .clientId("partner-backend")
    .clientSecret(passwordEncoder.encode(secretFromSecureConfig))
    .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(partnerGrant)
    .scope("booking.read")
    .build();
~~~

Place this snippet inside a factory/configuration that provides the imports as well as `passwordEncoder` and `secretFromSecureConfig`. For production clients, store secrets securely, rotate credentials, and persist registrations consistently.

### 11.2. Converter Accepts Only Its Own Grant

**Logic skeleton** example:

~~~java
final class PartnerTicketAuthenticationConverter
        implements AuthenticationConverter {

    private static final String GRANT_TYPE =
        "urn:example:params:oauth:grant-type:partner_ticket";

    @Override
    public Authentication convert(HttpServletRequest request) {
        if (!GRANT_TYPE.equals(
                request.getParameter(OAuth2ParameterNames.GRANT_TYPE))) {
            return null; // Do not break converters for standard grants.
        }

        // Must check HTTP method, duplicate parameters,
        // required ticket, format, and client authentication.
        //
        // After validating the request:
        // return new PartnerTicketAuthenticationToken(clientPrincipal, ticket);
        //
        // This snippet is a skeleton, without a custom Token class defined yet.
        throw new UnsupportedOperationException(
            "Complete parsing + validation before use");
    }
}
~~~

This is a **boundary-illustrating template**, intentionally not production-ready code. `PartnerTicketAuthenticationToken` must be an application-specific `Authentication` class, typically extending `OAuth2AuthorizationGrantAuthenticationToken` per Spring Authorization Server's design.

### 11.3. Custom Provider Must Actually Verify Credentials

A proper provider must:

- Confirm `OAuth2ClientAuthenticationToken` is authenticated/identified and the client is permitted `partner_ticket`.
- Verify the ticket is authentic, unexpired, matches the issuer/tenant/client, and **has not been used** if single-use.
- Prevent replay with transactions/atomicity when required.
- Derive subject and scopes from **trusted sources**; never accept client-asserted users or roles.
- Verify audience, resource, and policy constraints.
- Only then generate tokens via the generator and persist state via the authorization service.
- Return `OAuth2AccessTokenAuthenticationToken` or throw `OAuth2AuthenticationException` with proper semantics.

Never write a provider that "accepts any ticket and exchanges it for a JWT" just because the converter classified the grant type. Classifying a request and **proving authorization to issue tokens** are two separate responsibilities.

### 11.4. Registering the Converter/Provider Pair

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurity(
        HttpSecurity http,
        AuthenticationConverter partnerTicketConverter,
        AuthenticationProvider partnerTicketProvider)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .tokenEndpoint(token -> token
                .accessTokenRequestConverter(partnerTicketConverter)
                .authenticationProvider(partnerTicketProvider)
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Here `partnerTicketConverter`/`partnerTicketProvider` must be **fully implemented application beans**; the skeleton converter in section 11.2 is incomplete. Do not copy the `authorizationServerSecurity` bean from section 10 into the same project at the same time.

Spring's official documentation provides a guide: [How-to: Implement an Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html). Follow the guide's converter/provider and token-context pattern rather than writing HTTP token responses manually from a controller.

### 11.5. Test That "Default Grants Are Not Broken"

When installing an extension grant, in addition to testing `partner_ticket`, verify:

- Authorization Code still validates codes, redirect URIs, and PKCE.
- Refresh Token still validates active state, scopes, and client binding.
- Client Credentials still validates scopes.
- Device Code still returns `authorization_pending` or tokens upon approval.
- Token Exchange (if used) still validates subject tokens and audiences.
- A `partner_ticket` request from a client without that grant registered is rejected.
- A `client_credentials` request is not "swallowed" by the custom converter.

**The safest practice is to preserve default providers and extend narrowly**, rather than replacing the entire converter/provider list for a single use case.

## 12. OAuth2 Error Responses and How to Read Causes

When the token endpoint refuses to issue a token, the client usually receives an OAuth2 JSON error. Errors do not share a single cause:

| Error | Common Situations | Component to Investigate |
| --- | --- | --- |
| `invalid_request` | Missing or duplicate required parameter, malformed body | Converter/filter, HTTP request |
| `invalid_client` | Wrong client auth or unrecognized client | Client authentication filter/provider |
| `unauthorized_client` | Valid client, but not registered to use the requested grant | `RegisteredClient` + grant provider |
| `unsupported_grant_type` | Grant type unsupported by the Token Endpoint | Converter/provider list |
| `invalid_grant` | Invalid, mismatched, or expired authorization code/refresh token/grant | Grant provider, authorization store |
| `invalid_scope` | Requested scope violates registration/authorization | Grant provider, validator |
| `authorization_pending` | Device user has not yet approved | Device Code Provider |
| `slow_down` | Device polling too fast | Device Code Provider + polling interval |
| `access_denied` | User denied device approval | Device state and Token Endpoint |
| `expired_token` | Device code expired | Device Code Provider |
| `server_error` | AS handles internal failure per protocol | Observability, DB, generator; never log tokens |

The codes in this table reflect **common causes** and do not guarantee every Spring version or profile returns the exact same code for every invalid combination. For token exchange, additional RFC 8693 errors such as `invalid_target` may appear depending on `resource`/`audience` requirements and implementation.

### 12.1. Unsupported grant_type Example

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "unsupported_grant_type"
}
~~~

This example assumes client authentication already succeeded so the request reached grant classification. If client credentials are invalid, the client may receive `invalid_client` before `grant_type` is ever checked.

### 12.2. Invalid Grant Example

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_grant"
}
~~~

Never return an `error_description` revealing which user owns a code, whether a refresh token exists, or which device was approved. The AS should log minimal metadata for investigation without leaking credentials.

### 12.3. Do Not Replace All Errors with a Redirect to /login

The token endpoint is a client API. Sending an OAuth2 SDK to an HTML login page on `invalid_grant` or `invalid_client` breaks the contract and obscures the real failure.

When interactive user login is needed, the proper flow is to initiate a **new authorization request at the Authorization Endpoint**, not to have the token endpoint respond with an arbitrary login form.

## 13. Security When Customizing Providers and Converters

### 13.1. Checks You Must Never Skip

- **Client authentication:** confidential clients must present valid credentials; public clients may use only grants designed for them.
- **Grant type permission:** `RegisteredClient.authorizationGrantTypes` must permit the requested grant.
- **Token binding:** authorization codes, refresh tokens, and device codes must be matched against the right client/authorization.
- **Scope:** never grant scopes beyond the registration or the grant's actual `authorizedScopes`.
- **PKCE:** never skip `code_verifier` validation when a code is PKCE-bound.
- **Redirect URI:** authorization codes must match callbacks per OAuth2 rules.
- **Token exchange:** never allow exchanging tokens for arbitrary audiences/resources or unauthorized impersonation.
- **Token format and audience:** JWTs/opaque tokens must have the right issuer, audience, lifetime, and claim policy.
- **Atomicity:** single-use codes, refresh rotation, and one-time credentials must be protected against concurrent requests.

### 13.2. Separation of Responsibilities Across Data Sources

| Source | Meaning | Pitfall When Misused |
| --- | --- | --- |
| `RegisteredClientRepository` | Registered clients, grant types, auth methods, scopes | Relying only on registration to grant unconsented scopes |
| `OAuth2AuthorizationService` | Grants, codes, tokens, authorized scopes, and state | Ignoring revocation/reuse state during token exchange |
| `OAuth2AuthorizationConsentService` | Resource Owner consent when applicable | Treating consent as permanent access to every resource |
| `UserDetailsService` | Resource Owner account source during login | Using it to verify client secrets at the token endpoint |
| `OAuth2TokenGenerator` | Mints tokens from a validated context | Calling it directly while skipping grant validation |
| `SecurityContextHolder` | Authentication of the current request | Assuming it is always a Resource Owner, even in Client Credentials |

### 13.3. Never Log Token Endpoint Request Bodies

The token endpoint can receive client secrets, authorization codes, refresh tokens, device codes, subject tokens, or client assertions. **Never record raw `Authorization` headers, request bodies, or response tokens** in application logs, traces, reverse proxy access logs, or APM tools.

Instead, log controlled metadata: request/correlation ID, allowlisted grant type, post-authentication client ID, outcome, error code, latency, provider name (if needed), and audit events. When logging token identifiers, use internal audit IDs or policy-compliant hashes, never raw credentials.

## 14. Truly Testing "Dispatching by grant_type"

### 14.1. Minimum Test Matrix

| Request | Condition | Expected Outcome |
| --- | --- | --- |
| Valid `authorization_code` | Correct client, code, URI, PKCE | Token issued per grant |
| `authorization_code` wrong client | Code issued to A, client B exchanges | Rejected, no token issued |
| Reused `authorization_code` | Code already exchanged once | Rejected |
| Valid `refresh_token` | Active RT, matching client, authorized scopes | New access token issued |
| `refresh_token` excessive scope | Scope requested outside authorization | Rejected, never expanded |
| `refresh_token` wrong client | RT issued to A, B uses it | Rejected |
| Valid `client_credentials` | Confidential client with grant/scope | Access token issued |
| `client_credentials` with disallowed public client | Incompatible method/grant | Rejected |
| `client_credentials` unauthorized scope | Scope outside registration/policy | `invalid_scope` |
| Pending Device Code | User has not approved | `authorization_pending` |
| Denied Device Code | User denies with recorded state | `access_denied` |
| Expired Device Code | Exceeds device session TTL | `expired_token` |
| Device Code polled too fast | Violates interval | `slow_down` per policy |
| Valid Token Exchange | Correct subject token, audience, policy | Token issued if feature enabled and supported |
| Token Exchange disallowed audience | Violates target policy | Rejected |
| Unsupported grant type | `grant_type=urn:example:unknown` | `unsupported_grant_type` when client auth is valid |
| Authenticated client missing grant | `RegisteredClient` lacks grant type | `unauthorized_client` or matching error |
| Wrong client secret | Any grant | `invalid_client`, token issuance never invoked |
| Grant missing required parameter | Malformed body | `invalid_request` or matching grant error |
| Custom grant matches its type | Custom converter/provider | Runs only for the custom grant |
| Custom grant ignores other grants | Default grants retain converters | Not blocked, semantics unchanged |
| Token store failure | DB outage/transaction rollback | Never returns success if grant fails to persist |

**Testing discipline:** break **one condition at a time**. If a code has already been consumed, a "wrong redirect URI" test may fail merely due to code replay—proving nothing about the URI validator.

### 14.2. HTTP Testing with MockMvc

With `spring-security-test` and a real AS context, an example testing valid client credentials:

~~~java
@Test
void clientCredentialsGrantIssuesAccessToken() throws Exception {
    mockMvc.perform(post("/oauth2/token")
            .with(httpBasic("batch-reporter", "test-only-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "client_credentials")
            .param("scope", "booking.read"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.access_token").isNotEmpty())
        .andExpect(jsonPath("$.token_type").value("Bearer"));
}
~~~

Prerequisites: the test fixture registers `batch-reporter` with `CLIENT_SECRET_BASIC`, `CLIENT_CREDENTIALS`, `booking.read`, a secret hashed consistently with `PasswordEncoder`, and the AS has a valid token generator/JWK. The example requires static imports for MockMvc's `post`, `httpBasic`, matchers, and `jsonPath`.

Testing a forbidden grant:

~~~java
@Test
void clientNotAllowedToRefreshIsRejected() throws Exception {
    mockMvc.perform(post("/oauth2/token")
            .with(httpBasic("batch-reporter", "test-only-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "refresh_token")
            .param("refresh_token", "not-a-real-token"))
        .andExpect(status().is4xxClientError())
        .andExpect(jsonPath("$.access_token").doesNotExist());
}
~~~

This is a **negative smoke test**, but because the refresh token itself is fake, it does not conclusively prove *the grant prohibition rule*. To verify `unauthorized_client` accurately, supply a valid refresh token belonging to an eligible client while requesting it from a client without the grant—or test the provider directly with an appropriate fixture. When testing client binding, configure two clients with valid registrations/credentials so the request does not fail early during client authentication.

### 14.3. Testing Converters and Providers Separately

For an extension grant, include three test layers:

1. **Converter unit tests:** custom grant returns the expected authentication; default grants return `null`; missing/duplicate parameters are rejected.
2. **Provider unit tests:** `supports(...)` matches only the custom class; wrong credentials, wrong client, wrong scope, and replays are rejected; valid credentials mint tokens from an authenticated context.
3. **FilterChain integration tests:** POST to `/oauth2/token` through both client authentication and token endpoint filters; verify JWT/opaque token responses; verify default grants still work.

`@WithMockUser` is not a substitute for testing Client Authentication. It mocks a user principal and can bypass `OAuth2ClientAuthenticationFilter` compared to production. To evaluate true protocol behavior, test through the endpoint using real client credentials/assertions/PKCE/codes.

### 14.4. Testing Ordering and Multi-Provider Behavior

If your system has a custom provider supporting the same type as a default provider, test:

- Which provider is selected and why.
- Whether providers return `null`, throw exceptions, or return `Authentication` per contract.
- Whether a security error is "swallowed" by a subsequent provider that then issues a token.
- Whether modifying the provider list drops any default grant.
- Whether upgrading Spring versions changes converter/provider order or adds new types.

For most applications, it is much more stable to **extend using a distinct `Authentication` type** rather than overlapping a standard grant's type.

## 15. Troubleshooting by Symptom

| Symptom | Common Causes | How to Investigate |
| --- | --- | --- |
| `invalid_client` on every grant | Wrong secret, auth method, key/cert, unregistered client | Check client authentication first before debugging grant providers |
| `unsupported_grant_type` | Grant lacks converter/provider, missing extension registration | Check version and `OAuth2TokenEndpointConfigurer` |
| `unauthorized_client` | `RegisteredClient` lacks grant type | Inspect `authorizationGrantTypes` |
| `invalid_grant` on code exchange | Code expired, reused, wrong client/URI/PKCE | Inspect authorization record and Authorization Code provider |
| `invalid_grant` on refresh | Token expired, revoked, rotated, client mismatch | Inspect Refresh Token provider and authorization store |
| `invalid_scope` with client_credentials | Scope outside registration or custom validator | Inspect Client Credentials provider/validator |
| Device polling stays pending | User hasn't approved or store isn't shared | Check Device Verification flow and authorization persistence |
| Repeated `slow_down` on device polling | Client polls too aggressively | Respect `interval`, increase backoff |
| Token exchange rejected | Version unsupported, client lacks grant, or wrong audience/subject token | Check RFC 8693, provider/policy |
| Client Credentials receives wrong user info | Conflating client principal with Resource Owner | Separate client identity from user identity |
| Token issued but RS returns 401 | Mismatched issuer, audience, key/format, token type | Check JWT decoder or opaque introspector on the RS |
| Custom provider exists but is never called | Converter builds wrong `Authentication` type; wrong `supports(...)` | Test converter, provider registration, and matcher |
| Custom provider "swallows" all grants | Converter returns `Authentication` too broadly or provider `supports` is too wide | Restrict grant type and class |
| New grant breaks after framework upgrade | API/provider/setting changes across versions | Check release docs and regression tests |
| Error occurs on only one AS instance | Inconsistent registration/authorization/key store | Check persistence, JWK rotation, deployment |

### 15.1. Production Diagnostic Path

1. Verify the request reaches the right issuer and `/oauth2/token` over HTTPS.
2. Check which `SecurityFilterChain` matches the request.
3. Did the client authentication filter identify and authenticate the right `RegisteredClient`?
4. What `grant_type` was received, and did the converter create the right `Authentication` type?
5. Which provider supports that type, and is the client permitted to use the grant?
6. Are grant-specific conditions (code/PKCE, RT, scope, device, subject token) satisfied?
7. Did the token generator mint the expected token and did the authorization service save state?
8. Did the response handler emit valid OAuth2 JSON?
9. If the RS rejects the access token, inspect issuer/audience/expiry/scope and token format independently.

Never log raw tokens, client assertions, secrets, or entire request bodies while hunting for an error.

## 16. Design Mistakes to Avoid

| Mistake | Consequence | Right Principle |
| --- | --- | --- |
| Treating `grant_type` as client authentication | Client is never verified before issuing tokens | Separate client auth filter from grant providers |
| Letting a valid client secret grant every grant type | Bypasses grant-type permissions | Check `RegisteredClient` and policy |
| Selecting providers by string without checking `supports`/type | Risks handling the wrong credential type | Follow `AuthenticationConverter` and `AuthenticationProvider` contracts |
| Custom converter always returns non-null | Standard grants stop working | Return `null` for grants outside scope |
| Custom provider supports all `Authentication` | Bypasses standard providers, widens privileges | Support only the custom `Authentication` class |
| Replacing provider list and dropping defaults | Valid grants fail or lose checks | Keep defaults and add tested extensions |
| Custom scope validator omits default validator | Unregistered requested scopes are accepted | Chain `DEFAULT_SCOPE_VALIDATOR` with custom policy |
| Using Client Credentials to forge user tokens | No Resource Owner authentication/consent | Preserve client identity; use appropriate grants |
| Refresh token grants extra scopes from registration | Exceeds consented scopes | Restrict to `authorizedScopes` |
| Skipping PKCE verification during code exchange | Stolen codes can be exchanged for tokens | Keep default Authorization Code provider |
| Token exchange omits audience validation | New token accesses unauthorized APIs | Constrain token type, target, and policy |
| Using a refresh token as an access token | Credential sent to the wrong endpoint | Use RT only at the Token Endpoint |
| Redirecting token endpoint errors to `/login` | SDKs receive HTML instead of OAuth2 JSON | Return standard OAuth2 errors |
| Logging full HTTP bodies | Leaks secrets/codes/refresh tokens | Redact and audit minimal metadata |
| Skipping multi-instance AS tests | Lost codes/RTs or race conditions | Use consistent authorization storage and concurrency tests |
| Testing with `@WithMockUser` and assuming client auth works | Skips real client verification | Run HTTP tests through filters with real fixture credentials |

## 17. Pre-Production Checklist

- [ ] The Token Endpoint is protected by the AS `SecurityFilterChain` with the right matcher and `@Order`.
- [ ] Supported grant types have been verified against the **deployed library version**.
- [ ] Client authentication methods are configured and tested separately from grant providers.
- [ ] Each `RegisteredClient` includes only the necessary `authorizationGrantTypes`.
- [ ] Default converters remain active; custom converters match only their own grant.
- [ ] Custom providers have a narrow `supports(...)` and validate client, proof, scope, and audience.
- [ ] Authorization Code validates single-use codes, client binding, redirect URI, and PKCE.
- [ ] Refresh Token validates active state, binding, scopes, and rotation/reuse.
- [ ] Client Credentials never assumes a Resource Owner or refresh token.
- [ ] Device Code enforces pending, `slow_down`, denied, expired, and polling intervals.
- [ ] Token Exchange (if enabled) enforces subject token, audience/resource, and delegation policies.
- [ ] `OAuth2TokenGenerator` + `AuthorizationService` work reliably across restarts/failovers.
- [ ] Token and error responses conform to OAuth2; no HTML redirects on grant errors.
- [ ] Tests cover happy paths, wrong clients, forbidden grants, invalid scopes, replays, and custom extensions.
- [ ] Rate limiting, TLS, secret management, auditing, and raw-token log redaction are active.
- [ ] A process is in place to track security advisories, release notes, and upgrade regressions.

## 18. Self-Check Questions

**Question 1.** How do `OAuth2ClientAuthenticationFilter` and `OAuth2TokenEndpointFilter` differ?

**Answer:** The first authenticates/identifies the OAuth2 Client per its registered method. The second parses the grant request, selects the grant provider, and returns the OAuth2 token or error response.

**Question 2.** Why isn't `ProviderManager` simply a `switch(grant_type)`?

**Answer:** `grant_type` is mapped by a converter into a specialized `Authentication` type; `AuthenticationManager` dispatches providers based on `supports(...)` and authentication outcomes. The grant type string in the HTTP request does not replace checks on client identity, grant permission, or token state.

**Question 3.** A client authenticated with a valid secret but is not permitted to use `refresh_token`. What must happen?

**Answer:** The AS rejects the grant. Successful client authentication does not mean the client is entitled to every authorization grant type.

**Question 4.** Why isn't `OAuth2ClientCredentialsAuthenticationProvider` the component that handles `client_secret_basic` for all grants?

**Answer:** It handles the **Client Credentials Grant**. General client-secret authentication is handled by the AS's client authentication components.

**Question 5.** When adding a scope validator for Client Credentials, why use `DEFAULT_SCOPE_VALIDATOR.andThen(...)`?

**Answer:** Because `setAuthenticationValidator(...)` replaces the current validator. Chaining the default validator preserves registration-based scope limits before applying additional business rules.

**Question 6.** Both `grant_type=authorization_code` and `grant_type=refresh_token` accept a credential string—can they share the same provider?

**Answer:** They should not. Codes and refresh tokens differ in lifetime, binding, replay policy, and scope handling; Spring Authorization Server provides separate providers to enforce each grant's exact semantics.

**Question 7.** Is `grant_type=password` supported by default?

**Answer:** Not in the default provider list of SAS 1.5.x. It should not be added just to simplify UI/login flows.

**Question 8.** A custom converter parses `partner_ticket` properly—is it safe to issue a JWT now?

**Answer:** No. The provider must verify the client, proof/ticket, authorization, scope, audience, and replay protection; the token generator may only be called after those checks succeed.

**Question 9.** For Device Code, why isn't `authorization_pending` a Token Endpoint configuration error?

**Answer:** It is a valid state in the Device Grant when the user has not finished verification/consent. The client must wait for the specified interval and continue polling per RFC 8628.

## 19. Official References and Conclusion

References to verify against **the exact version running in your project**:

- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — OAuth2TokenEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenEndpointConfigurer.html)
- [Spring Authorization Server — How-to: Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [RFC 6749 — OAuth 2.0 Token Endpoint](https://www.rfc-editor.org/rfc/rfc6749#section-3.2)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)

**Conclusion:** In Spring Authorization Server, dispatching by `grant_type` is a two-layer chain: **a converter understands the request and creates the matching `Authentication` type**, and then **`AuthenticationManager` selects the provider supporting that type**. Each provider must verify the authenticated client, grant permission, scopes, and grant-specific proof before the token generator mints tokens. This design makes it possible to add controlled extension grants without rewriting the entire Token Endpoint, while preventing client authentication from being confused with grant authentication and avoiding unauthorized token issuance in OAuth 2.0/OIDC systems.
