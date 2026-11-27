# Registering an Extension on the Token Endpoint and Updating Metadata Appropriately

OAuth 2.0 allows an Authorization Server to extend how clients request access tokens. When a business use case requires an authorization grant type not covered by standard grants, the server can implement an **extension authorization grant** at the Token Endpoint. In Spring Authorization Server, this extension is plugged into the token request processing pipeline via an `AuthenticationConverter` and an `AuthenticationProvider`.

Adding a new converter/provider only enables the server to process the request. Clients also need to discover the grant type and parameters supported by the server. Therefore, you should update Authorization Server Metadata to advertise the appropriate grant type, while also registering that grant type on `RegisteredClient` for each client permitted to use it.

This lesson belongs to the **Protocol Extensions** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module. The module covers designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application. This content focuses on registering extension grants at the Token Endpoint, issuing tokens according to the Spring Authorization Server contract, and publishing consistent metadata.

> **Implementation principle:** An extension grant is only considered complete when the request parser, provider, client registration, token generation, persistence, error responses, and discovery metadata all describe one unified capability.

## 1. Extension Grants in OAuth 2.0

RFC 6749 allows clients to request access tokens using an extension grant type. The client sends a `grant_type` value that is an absolute URI defined by the Authorization Server, along with any parameters required for that grant.

Example of a custom grant using a one-time authorization code:

~~~text
urn:example:params:oauth:grant-type:custom-code
~~~

The client sends the request to the existing Token Endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Authorization: Basic BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aexample%3Aparams%3Aoauth%3Agrant-type%3Acustom-code&
code=ONE_TIME_CODE&
scope=profile.read%20orders.read
~~~

The Token Endpoint remains the standard OAuth 2.0 endpoint. The extension changes how the server interprets `grant_type` and its accompanying parameters—it does not create a separate token endpoint.

### 1.1. When Do You Need an Extension Grant?

An extension grant is appropriate when the system has a dedicated credential or authorization workflow that cannot be accurately modeled with existing grant types. Examples:

- Exchanging an enterprise-issued assertion for an access token;
- Exchanging a one-time code issued after a proprietary verification flow;
- Integrating an existing organizational delegation mechanism;
- Performing token issuance based on proof defined by a protocol extension.

Do not create a new grant type merely to rename a standard grant or add a parameter that does not alter grant semantics. When claim/token customization within an existing grant suffices, evaluate that approach first.

### 1.2. Extension Grants Are Not Client Authentication Methods

These two concepts operate at different stages:

| Component | Question It Answers | Examples |
|---|---|---|
| Client authentication method | Who is the client? | `client_secret_basic`, `private_key_jwt`, `tls_client_auth` |
| Authorization grant type | On what authorization/proof is the client requesting a token? | `authorization_code`, `client_credentials`, extension grant URI |

A client may authenticate with `client_secret_basic` and then use an extension grant. Adding a grant type does not automatically create or alter client authentication mechanisms.

### 1.3. Using an Absolute URI as the Grant Type

RFC 6749 requires an extension grant type to be an absolute URI. A URN under a private namespace can be used for internal extensions. If the extension is shared across organizations, publish a specification and choose a controlled namespace to prevent collisions.

Do not use short names like `custom_code` or `my_grant` as public extension grant values. They easily collide with other definitions and fail the absolute URI requirement.

Example constant:

~~~java
public static final AuthorizationGrantType CUSTOM_CODE =
    new AuthorizationGrantType(
        "urn:example:params:oauth:grant-type:custom-code");
~~~

`AuthorizationGrantType` is a Spring Security value object. For a custom grant type, instantiate it using the URI agreed upon between the Authorization Server and clients.

## 2. Token Endpoint Processing Pipeline

Spring Authorization Server organizes token request processing into three stages:

1. **Pre-processing:** `AuthenticationConverter` reads the HTTP request and builds an `Authentication` representing the grant.
2. **Main processing:** `AuthenticationProvider` authenticates the client, grant, and authorization conditions, then generates the access token.
3. **Post-processing:** the success handler renders an OAuth2 access token response; the error handler returns an OAuth2 error on failure.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant CA as Client Authentication Filter
    participant F as OAuth2TokenEndpointFilter
    participant CV as Custom AuthenticationConverter
    participant PM as AuthenticationManager
    participant AP as Custom AuthenticationProvider
    participant TG as OAuth2TokenGenerator
    participant AS as OAuth2AuthorizationService

    C->>CA: POST /oauth2/token + client credentials
    CA->>CA: Authenticate client
    CA->>F: Continue filter chain
    F->>CV: Convert grant request
    CV-->>F: CustomCodeGrantAuthenticationToken
    F->>PM: Authenticate grant token
    PM->>AP: Select provider by supports()
    AP->>AP: Validate client, grant and one-time code
    AP->>TG: Generate access token
    TG-->>AP: OAuth2Token
    AP->>AS: Save OAuth2Authorization
    AP-->>PM: OAuth2AccessTokenAuthenticationToken
    PM-->>F: Authentication success
    F-->>C: OAuth2 access token response
~~~

### 2.1. Client Authentication Happens Before the Grant Provider

The Token Endpoint filter receives the request after client authentication has already been processed in the Authorization Server filter chain. The converter can retrieve the client principal from `SecurityContextHolder`; the provider must still verify that the principal is an authenticated `OAuth2ClientAuthenticationToken`.

Do not authenticate the client yourself by reading `client_secret` inside a custom grant converter. Use Spring Authorization Server's client authentication pipeline so proper authentication methods, error handling, and security policies apply.

### 2.2. Converters Must Defer Requests for Other Grants

The Token Endpoint uses a `DelegatingAuthenticationConverter` comprising default converters. Your extension converter must only process the exact `grant_type` it owns. If the request uses another grant type, the converter must return `null` so the next converter can handle it.

If a custom converter intercepts every request and throws an error, it can break `authorization_code`, `refresh_token`, `client_credentials`, or other framework-supported grants.

### 2.3. Providers Are Selected via supports()

`AuthenticationManager` selects a provider based on `supports(Class<?>)`. A custom provider must return `true` for the exact custom grant authentication token class. Never write a provider that accepts every `Authentication` without an explicit reason.

## 3. Registering the Grant Type in RegisteredClient

Installing an extension grant on the server does not mean every client is allowed to use it. Each `RegisteredClient` must declare the grant type in `authorizationGrantTypes`.

~~~java
AuthorizationGrantType customCodeGrant =
    new AuthorizationGrantType(
        "urn:example:params:oauth:grant-type:custom-code");

RegisteredClient client = RegisteredClient.withId("custom-client-internal-id")
    .clientId("custom-client")
    .clientSecret(passwordEncoder.encode(clientSecret))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(customCodeGrant)
    .scope("profile.read")
    .scope("orders.read")
    .tokenSettings(TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
~~~

This is a confidential client example. Secrets must be encoded with an appropriate `PasswordEncoder`; never use `{noop}` in production. Token lifetime and scopes are client policies that should be tuned to the risk profile of the grant.

### 3.1. Providers Must Check Client Grant Permissions

Inside the provider, verify:

~~~java
if (!registeredClient.getAuthorizationGrantTypes()
        .contains(customCodeGrant)) {
    throw new OAuth2AuthenticationException(
        OAuth2ErrorCodes.UNAUTHORIZED_CLIENT);
}
~~~

This check is mandatory at token issuance time. Do not rely solely on the client existing in the database or the extension being registered on the server.

### 3.2. RegisteredClient Scopes and Requested Scopes

A client may only request scopes allowed by its registration. For grants based on one-time codes, the code may also restrict the scopes granted to the subject. The provider must take the intersection of these policies or reject requests that exceed permissions:

~~~text
requested scopes
    ⊆ RegisteredClient allowed scopes
    ⊆ scopes authorized by the grant
~~~

Do not automatically issue all `RegisteredClient` scopes simply because the request omitted `scope`. Explicitly define default scopes for the extension and enforce them in the provider.

### 3.3. Dynamic Client Registration

If the Authorization Server supports Dynamic Client Registration, the client registration endpoint also needs a policy for the custom grant type. Advertising a grant type in metadata does not mean the registration endpoint will accept every client requesting that grant.

Only permit DCR to register a custom grant when the client is eligible, the grant is enabled, and registration policy governs client type, scopes, authentication method, and usage rights.

## 4. Designing the Extension Contract Before Writing Code

Before implementing the converter/provider, document the protocol contract so server and clients share the exact same expectations.

Example contract for `custom-code`:

| Component | Convention |
|---|---|
| `grant_type` | `urn:example:params:oauth:grant-type:custom-code` |
| `code` | One-time code, required, single-use only |
| `scope` | Space-delimited list of scopes, required in this example |
| Client authentication | Confidential client authenticated via registered method |
| Code binding | Code bound to client and subject |
| Expiration | Code has a short lifetime |
| Success | Standard OAuth2 access token response |
| Invalid code | `invalid_grant` |
| Client not granted grant | `unauthorized_client` |
| Invalid scope | `invalid_scope` |

### 4.1. Distinguishing Request Parameters and Token Response Parameters

Request parameters describe the proof the client submits to exchange for a token. Token response parameters describe the resulting token issued by the server. Never echo input credentials such as `code`, assertions, or secrets into the response.

If the extension needs a custom response parameter, add it only with an explicit specification and genuine client need. Standard fields `access_token`, `token_type`, `expires_in`, `refresh_token`, and `scope` must retain OAuth2 semantics.

### 4.2. Specifying Cardinality and Validation

For every parameter, define:

- Required or optional;
- Single occurrence or repeatable;
- Data type and length limits;
- Encoding format;
- Handling of unrecognized parameters;
- Error codes when missing, duplicated, or malformed.

Standard token requests use `application/x-www-form-urlencoded` over HTTPS. Never place grant codes, assertions, or credentials in query strings.

## 5. Implementing CustomCodeGrantAuthenticationToken

Spring Authorization Server provides the base class `OAuth2AuthorizationGrantAuthenticationToken`. The custom token class extends it to hold the grant type, client principal, and additional parameters.

~~~java
public final class CustomCodeGrantAuthenticationToken
        extends OAuth2AuthorizationGrantAuthenticationToken {

    public static final AuthorizationGrantType GRANT_TYPE =
        new AuthorizationGrantType(
            "urn:example:params:oauth:grant-type:custom-code");

    private String code;
    private final Set<String> requestedScopes;

    public CustomCodeGrantAuthenticationToken(
            String code,
            Set<String> requestedScopes,
            Authentication clientPrincipal) {
        super(GRANT_TYPE, clientPrincipal, Collections.emptyMap());
        Assert.hasText(code, "code cannot be empty");
        Assert.notEmpty(requestedScopes, "requestedScopes cannot be empty");
        this.code = code;
        this.requestedScopes = Collections.unmodifiableSet(
            new LinkedHashSet<>(requestedScopes));
    }

    public String getCode() {
        return this.code;
    }

    public Set<String> getRequestedScopes() {
        return this.requestedScopes;
    }

    @Override
    public Object getCredentials() {
        return this.code;
    }

    @Override
    public void eraseCredentials() {
        this.code = null;
        super.eraseCredentials();
    }
}
~~~

The token class holds the code as credentials so it can be wiped from the object after processing. In real applications, never log the `Authentication` object or `getCredentials()`.

### 5.1. Why Not Use a Generic Authentication?

A dedicated grant token class provides a distinct type so that:

- The provider can accurately identify the grant type;
- The converter transforms HTTP data into a structured object;
- Tests can verify request parsing independently;
- Custom data is never mixed with standard grants;
- The exact grant type is recorded in `OAuth2Authorization`.

### 5.2. Retain Minimal Data

Keep only the code, scopes, and parameters required by the provider. Do not copy the entire request parameter map if it contains `client_secret`, assertions, sensitive data, or undefined parameters.

## 6. Implementing CustomCodeGrantAuthenticationConverter

The converter only processes requests whose grant type matches the extension. The example below requires each parameter to appear exactly once, requires `code` and `scope`, and converts the client principal and validated data into the custom grant token.

~~~java
public final class CustomCodeGrantAuthenticationConverter
        implements AuthenticationConverter {

    @Override
    public Authentication convert(HttpServletRequest request) {
        String[] grantTypes =
            request.getParameterValues(OAuth2ParameterNames.GRANT_TYPE);

        if (grantTypes == null) {
            return null;
        }
        if (grantTypes.length != 1) {
            throw invalidRequest();
        }
        if (!CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue()
                .equals(grantTypes[0])) {
            return null;
        }

        Set<String> allowedParameters = Set.of(
            OAuth2ParameterNames.GRANT_TYPE,
            OAuth2ParameterNames.CLIENT_ID,
            OAuth2ParameterNames.CLIENT_SECRET,
            OAuth2ParameterNames.CLIENT_ASSERTION,
            OAuth2ParameterNames.CLIENT_ASSERTION_TYPE,
            OAuth2ParameterNames.CODE,
            OAuth2ParameterNames.SCOPE);
        if (!allowedParameters.containsAll(request.getParameterMap().keySet())) {
            throw invalidRequest();
        }

        String code = requiredSingleParameter(
            request, OAuth2ParameterNames.CODE);
        String scope = requiredSingleParameter(
            request, OAuth2ParameterNames.SCOPE);

        String[] scopeValues =
            StringUtils.tokenizeToStringArray(scope, " ");
        if (scopeValues.length == 0) {
            throw invalidRequest();
        }
        Set<String> requestedScopes =
            new LinkedHashSet<>(Arrays.asList(scopeValues));
        if (requestedScopes.size() != scopeValues.length) {
            throw invalidRequest();
        }

        Authentication clientPrincipal =
            SecurityContextHolder.getContext().getAuthentication();

        return new CustomCodeGrantAuthenticationToken(
            code, requestedScopes, clientPrincipal);
    }

    private static String requiredSingleParameter(
            HttpServletRequest request, String name) {
        String[] values = request.getParameterValues(name);
        if (values == null || values.length != 1
                || !StringUtils.hasText(values[0])) {
            throw invalidRequest();
        }
        return values[0];
    }

    private static OAuth2AuthenticationException invalidRequest() {
        return new OAuth2AuthenticationException(
            OAuth2ErrorCodes.INVALID_REQUEST);
    }
}
~~~

Key imports:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Set;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.endpoint.OAuth2ParameterNames;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.util.StringUtils;
~~~

### 6.1. Why Check for Duplicate Parameters?

`getParameter()` returns only a single value and can hide duplicate parameters sent by a client. For fields like `grant_type`, `code`, and `scope`, the converter should validate cardinality before building the authentication token.

Never arbitrarily pick the first or last value when a client submits `code` multiple times. Ambiguous requests must be rejected with `invalid_request`.

### 6.2. Do Not Treat Client ID as Proof of Authentication

The converter may receive `client_id` from the form body, but that is solely an identifier. The trusted client principal must come from Spring Authorization Server's client authentication filter. The provider will verify that the principal is authenticated and extract `RegisteredClient` from the authentication token.

### 6.3. Additional Parameters Require an Allowlist

The example above does not pass all request parameters into `additionalParameters`. If the extension has fields such as `tenant`, `audience`, or `resource`, explicitly define their names and types, check occurrence counts, validate lengths/syntax, and pass only defined fields. Never copy `client_secret`, raw assertions, or other credentials into token metadata arbitrarily.

The allowlist in the converter must also account for standard form parameters used by the active client authentication method, such as `client_secret_post` or `private_key_jwt`. The example above permits `client_secret`, `client_assertion`, and `client_assertion_type` through the parser without reading them for authentication; the client authentication filter remains responsible for validating them.

## 7. Implementing AuthenticationProvider

The provider performs the decisive security checks: verifying the client, checking `RegisteredClient` grant permissions, consuming the grant once, restricting scopes, and generating the token.

For the `custom-code` example, a domain service verifies the code, client binding, expiration, used status, and authorized principal. Consumption must be atomic so two concurrent requests cannot exchange the same code for two access tokens.

### 7.1. Code Verification Service Contract

~~~java
public interface CustomCodeGrantService {

    Optional<CustomCodeGrantSubject> consume(
        String code,
        String registeredClientId,
        Set<String> requestedScopes
    );
}

public record CustomCodeGrantSubject(
        Authentication principal,
        Set<String> authorizedScopes) {
}
~~~

This service is an application-implemented domain service. The `consume` method must verify that the code exists, has not expired, has not been revoked, has never been used, was issued for the exact `RegisteredClient`, and permits `requestedScopes`. Only after all checks pass does the service mark the code used in the same transaction/atomic operation and return the principal along with granted scopes. If a scope is not permitted, the service throws `invalid_scope` and preserves code status according to defined policy.

### 7.2. CustomCodeGrantAuthenticationProvider

~~~java
public final class CustomCodeGrantAuthenticationProvider
        implements AuthenticationProvider {

    private final CustomCodeGrantService grantService;
    private final OAuth2AuthorizationService authorizationService;
    private final OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator;

    public CustomCodeGrantAuthenticationProvider(
            CustomCodeGrantService grantService,
            OAuth2AuthorizationService authorizationService,
            OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator) {
        Assert.notNull(grantService, "grantService cannot be null");
        Assert.notNull(authorizationService,
            "authorizationService cannot be null");
        Assert.notNull(tokenGenerator, "tokenGenerator cannot be null");
        this.grantService = grantService;
        this.authorizationService = authorizationService;
        this.tokenGenerator = tokenGenerator;
    }

    @Override
    public Authentication authenticate(Authentication authentication)
            throws AuthenticationException {

        CustomCodeGrantAuthenticationToken grant =
            (CustomCodeGrantAuthenticationToken) authentication;

        OAuth2ClientAuthenticationToken clientPrincipal =
            getAuthenticatedClientElseThrowInvalidClient(grant);
        RegisteredClient registeredClient =
            clientPrincipal.getRegisteredClient();

        if (!registeredClient.getAuthorizationGrantTypes()
                .contains(CustomCodeGrantAuthenticationToken.GRANT_TYPE)) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.UNAUTHORIZED_CLIENT);
        }

        Set<String> requestedScopes = grant.getRequestedScopes();
        if (!registeredClient.getScopes().containsAll(requestedScopes)) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_SCOPE);
        }

        CustomCodeGrantSubject grantSubject;
        String code = grant.getCode();
        try {
            grantSubject = this.grantService
                .consume(code, registeredClient.getId(), requestedScopes)
                .orElseThrow(() -> new OAuth2AuthenticationException(
                    OAuth2ErrorCodes.INVALID_GRANT));
        } finally {
            grant.eraseCredentials();
        }

        if (grantSubject.principal() == null
                || !grantSubject.principal().isAuthenticated()) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_GRANT);
        }
        if (!grantSubject.authorizedScopes().containsAll(requestedScopes)) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_SCOPE);
        }

        OAuth2TokenContext tokenContext =
            DefaultOAuth2TokenContext.builder()
                .registeredClient(registeredClient)
                .principal(grantSubject.principal())
                .authorizationServerContext(
                    AuthorizationServerContextHolder.getContext())
                .authorizedScopes(requestedScopes)
                .tokenType(OAuth2TokenType.ACCESS_TOKEN)
                .authorizationGrantType(
                    CustomCodeGrantAuthenticationToken.GRANT_TYPE)
                .authorizationGrant(grant)
                .build();

        OAuth2Token generatedToken =
            this.tokenGenerator.generate(tokenContext);
        if (generatedToken == null) {
            throw new OAuth2AuthenticationException(
                new OAuth2Error(
                    OAuth2ErrorCodes.SERVER_ERROR,
                    "The token generator failed to generate an access token.",
                    null));
        }

        OAuth2AccessToken accessToken = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            generatedToken.getTokenValue(),
            generatedToken.getIssuedAt(),
            generatedToken.getExpiresAt(),
            requestedScopes);

        OAuth2Authorization.Builder authorizationBuilder =
            OAuth2Authorization.withRegisteredClient(registeredClient)
                .principalName(grantSubject.principal().getName())
                .authorizationGrantType(
                    CustomCodeGrantAuthenticationToken.GRANT_TYPE)
                .authorizedScopes(requestedScopes)
                .attribute(
                    Principal.class.getName(),
                    grantSubject.principal());

        if (generatedToken instanceof ClaimAccessor claimAccessor) {
            authorizationBuilder.token(accessToken, metadata ->
                metadata.put(
                    OAuth2Authorization.Token.CLAIMS_METADATA_NAME,
                    claimAccessor.getClaims()));
        } else {
            authorizationBuilder.accessToken(accessToken);
        }

        this.authorizationService.save(authorizationBuilder.build());

        return new OAuth2AccessTokenAuthenticationToken(
            registeredClient, clientPrincipal, accessToken);
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return CustomCodeGrantAuthenticationToken.class
            .isAssignableFrom(authentication);
    }

    private static OAuth2ClientAuthenticationToken
            getAuthenticatedClientElseThrowInvalidClient(
                    Authentication authentication) {
        Object principal = authentication.getPrincipal();
        if (principal instanceof OAuth2ClientAuthenticationToken client
                && client.isAuthenticated()) {
            return client;
        }
        throw new OAuth2AuthenticationException(
            OAuth2ErrorCodes.INVALID_CLIENT);
    }
}
~~~

This snippet illustrates a provider for a user-centric custom grant: the code service returns a user principal, so the token context and authorization record use that principal. If the extension is machine-to-machine and the code represents the client rather than a resource owner, the principal must be determined according to the grant's semantics.

### 7.3. What the Provider Must Verify

| Check | Reason |
|---|---|
| Client is authenticated | Never issue tokens for unauthenticated client requests |
| Client allows the custom grant | Registration is the permission boundary for grant usage |
| Code matches the client | Prevents client A from exchanging a code issued to client B |
| Code is unexpired and unused | Prevents replay |
| Code binds to exact subject/audience | Prevents exchanging a code for a different user or resource |
| Scopes belong to client and grant | Never grant privileges beyond consent/policy |
| Token generator produces a token | Never return success if token generation fails |
| Authorization is persisted | Introspection, revocation, and auditing require state |

### 7.4. Why Must Code Consumption Be Atomic?

If the provider simply reads the code and marks it used in a separate operation, two concurrent requests could both observe an unused state and both issue tokens. Use a database transaction with a conditional update, unique constraint, or compare-and-set so only one request consumes successfully.

Example conditional update:

~~~sql
UPDATE custom_grant_code
SET consumed_at = CURRENT_TIMESTAMP
WHERE code_hash = ?
  AND registered_client_id = ?
  AND consumed_at IS NULL
  AND expires_at > CURRENT_TIMESTAMP;
~~~

Accept the grant only when the affected row count equals 1. Store a hash of the code whenever possible; avoid storing raw bearer-like codes in readable form.

### 7.5. Do Not Issue Refresh Tokens Automatically

The example above only issues access tokens. If the extension requires refresh tokens, define dedicated rules: is the client registered for the `refresh_token` grant, does a refresh token fit the extension's semantics, what is the rotation/reuse policy, can scopes be narrowed on refresh, and how is the authorization record updated?

Do not issue refresh tokens merely because the token generator is capable of generating them.

### 7.6. Transaction Between Code Consumption and Authorization Save

The provider performs two critical operations: marking the grant code consumed and saving `OAuth2Authorization` containing the new access token. If the code is committed as consumed before token generation or authorization saving succeeds, the client may lose the code without receiving a token. This is fail-closed behavior, though it may require the user/application to request a new code.

If the code store and `OAuth2AuthorizationService` share the same relational database, place claiming/consuming the code and saving the authorization inside a single transaction so a token generation or save failure rolls back both. You can implement this orchestration inside a transaction-managed application service rather than assuming two repositories automatically share a transaction.

If the two stores cannot share a transaction, design a state machine such as `issued` → `processing` → `consumed`, an idempotency key, or a controlled recovery workflow. Never automatically revert a code to unused after an indeterminate failure, because the prior request may have succeeded in issuing a token whose response was lost.

## 8. Registering Converter and Provider on the Token Endpoint

`OAuth2TokenEndpointConfigurer` provides two main extension points:

- `accessTokenRequestConverter(...)` adds a converter for requests;
- `authenticationProvider(...)` adds a provider to process the authentication token created by the converter.

Configuration example inside the Authorization Server `SecurityFilterChain`:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        AuthenticationConverter customCodeGrantAuthenticationConverter,
        AuthenticationProvider customCodeGrantAuthenticationProvider)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .tokenEndpoint(tokenEndpoint -> tokenEndpoint
                .accessTokenRequestConverter(
                    customCodeGrantAuthenticationConverter)
                .authenticationProvider(
                    customCodeGrantAuthenticationProvider)
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

Declaring the components as Spring beans:

~~~java
@Bean
AuthenticationConverter customCodeGrantAuthenticationConverter() {
    return new CustomCodeGrantAuthenticationConverter();
}

@Bean
AuthenticationProvider customCodeGrantAuthenticationProvider(
        CustomCodeGrantService grantService,
        OAuth2AuthorizationService authorizationService,
        OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator) {
    return new CustomCodeGrantAuthenticationProvider(
        grantService, authorizationService, tokenGenerator);
}
~~~

### 8.1. Add Converters/Providers Without Replacing the Default Pipeline

`accessTokenRequestConverter(...)` and `authenticationProvider(...)` append components to the pipeline. Default converters/providers for `authorization_code`, `refresh_token`, `client_credentials`, `device_code`, and `token_exchange` continue working.

Only use `accessTokenRequestConverters(...)` or `authenticationProviders(...)` when you need to manipulate the full default list—such as adjusting ordering, replacing a specific provider, or removing a default implementation. When modifying the list, ensure you do not accidentally drop grant types the application still relies on.

### 8.2. Converters Do Not Intercept Other Grants

For requests missing `grant_type` or carrying a different grant type, the custom converter returns `null`. Default converters continue processing. If no converter/provider supports the requested grant type, the Token Endpoint returns `unsupported_grant_type` per OAuth2 error handling.

### 8.3. Keep Default Success/Error Handlers

When the custom provider returns `OAuth2AccessTokenAuthenticationToken`, the default success handler can serialize it into `OAuth2AccessTokenResponse`. Only replace `accessTokenResponseHandler(...)` if the extension genuinely requires a different response format backed by a client specification.

Similarly, keep the default `errorResponseHandler(...)` unless changes are required. A custom error handler must preserve status codes, JSON shape, and OAuth2 error semantics.

## 9. Request and Response of an Extension Grant

The client must authenticate at the Token Endpoint using its registered client authentication method. The request then includes the extension `grant_type` and the parameters defined in the contract.

### 9.1. Example Request

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Authorization: Basic Y3VzdG9tLWNsaWVudDpzZWNyZXQ=
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aexample%3Aparams%3Aoauth%3Agrant-type%3Acustom-code&
code=ONE_TIME_CODE&
scope=profile.read%20orders.read
~~~

In production, the `Authorization` header containing client credentials must be constructed by an OAuth2 client library and transmitted over TLS. The Base64 example only illustrates HTTP Basic; Base64 is not security encryption.

### 9.2. Successful Response

If the provider returns `OAuth2AccessTokenAuthenticationToken`, the default handler returns a standard response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json;charset=UTF-8
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "eyJraWQiOiJzaWduaW5nLWtleSIs...",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "profile.read orders.read"
}
~~~

Do not return the redeemed code, raw assertion, or internal verification details in the response. Clients only need the credential and token metadata.

### 9.3. Error Responses

Error codes must be used in the right context:

| Error | When Used? |
|---|---|
| `invalid_request` | Missing required parameter, duplicate parameter, or request violates contract |
| `invalid_client` | Client authentication failed |
| `unauthorized_client` | Client authenticated but not permitted to use this grant |
| `unsupported_grant_type` | Server does not support the grant type in the request |
| `invalid_grant` | Code/assertion invalid, expired, used, or not bound to the client |
| `invalid_scope` | Requested scope not permitted by client/grant |
| `server_error` | Internal failure prevented processing the request |

Do not return internal details such as missing code hashes, client binding mismatches, or replay detection reasons. For those cases, `invalid_grant` is usually appropriate; internal logs should record only the correlation ID and redacted event code.

## 10. Updating Authorization Server Metadata

RFC 8414 defines `grant_types_supported` as optional metadata: a JSON array listing the OAuth 2.0 grant types supported by the Authorization Server. Its values share the same semantics as `grant_types` in Dynamic Client Registration.

After implementing a custom grant, metadata should advertise the grant's URI so clients can discover the capability instead of hard-coding assumptions.

### 10.1. Using authorizationServerMetadataCustomizer

Spring Authorization Server provides `OAuth2AuthorizationServerMetadataEndpointConfigurer.authorizationServerMetadataCustomizer(...)`. The consumer receives `OAuth2AuthorizationServerMetadata.Builder`; the builder exposes `grantType(String)` to append a value to `grant_types_supported`.

~~~java
OAuth2AuthorizationServerConfigurer authorizationServer =
    OAuth2AuthorizationServerConfigurer.authorizationServer();

http.with(authorizationServer, server -> server
    .authorizationServerMetadataEndpoint(metadataEndpoint ->
        metadataEndpoint.authorizationServerMetadataCustomizer(metadata ->
            metadata.grantType(
                CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue())
        )
    )
);
~~~

This is a configuration fragment of the Authorization Server. In a complete configuration, keep `securityMatcher(...)`, the other endpoint configurers, and `http.build()` as shown in earlier examples.

### 10.2. Metadata Output

The Authorization Server Metadata response will include the extension grant type in the list:

~~~json
{
  "issuer": "https://identity.example.com",
  "authorization_endpoint": "https://identity.example.com/oauth2/authorize",
  "token_endpoint": "https://identity.example.com/oauth2/token",
  "jwks_uri": "https://identity.example.com/oauth2/jwks",
  "grant_types_supported": [
    "authorization_code",
    "refresh_token",
    "client_credentials",
    "urn:example:params:oauth:grant-type:custom-code"
  ]
}
~~~

The endpoints and grant types in the JSON are illustrative. The actual response is generated from `AuthorizationServerSettings`, enabled endpoints, and the application's metadata customizer.

### 10.3. Avoid Accidentally Replacing the Entire Grant List

The builder offers `grantTypes(Consumer<List<String>>)` to add, replace, or remove entries in the list. When simply adding an extension, `grantType(...)` is the clearest option. If using `grantTypes(...)`, preserve the standard grant types the server actually supports.

Do not advertise a grant type merely because one registered client lists that grant. Metadata describes Authorization Server capabilities system-wide; `RegisteredClient` still determines whether a specific client is permitted to use that capability.

## 11. Synchronizing OIDC Provider Configuration When OIDC Is Enabled

An Authorization Server may publish both OAuth 2.0 Authorization Server Metadata per RFC 8414 and OpenID Provider Configuration per OpenID Connect Discovery. Both metadata documents share several fields, including supported grant types.

If clients discover via OIDC `/.well-known/openid-configuration`, update the provider configuration accordingly so clients do not receive a different grant type list than OAuth2 metadata provides.

~~~java
http.with(authorizationServer, server -> server
    .oidc(oidc -> oidc
        .providerConfigurationEndpoint(endpoint ->
            endpoint.providerConfigurationCustomizer(metadata ->
                metadata.grantType(
                    CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue())
            )
        )
    )
);
~~~

`OidcProviderConfiguration.Builder` extends the shared metadata builder, so `grantType(...)` can be used to add the extension grant. This snippet applies only when the OIDC provider configuration endpoint is enabled.

### 11.1. Configuring Both Metadata Endpoints with One Policy

In an application enabling both OAuth2 Authorization Server Metadata and OIDC:

~~~java
.authorizationServerMetadataEndpoint(endpoint ->
    endpoint.authorizationServerMetadataCustomizer(metadata ->
        metadata.grantType(
            CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue())
    )
)
.oidc(oidc -> oidc
    .providerConfigurationEndpoint(endpoint ->
        endpoint.providerConfigurationCustomizer(metadata ->
            metadata.grantType(
                CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue())
        )
    )
)
~~~

Source the grant type from the same shared constant or configuration to prevent updating one metadata endpoint while forgetting the other.

### 11.2. Custom Metadata for Proprietary Parameters

RFC 8414 does not define a general-purpose field to describe all custom request parameters of individual extension grants. If clients must discover parameters such as `code`, `assertion`, `resource`, or `tenant`, your organization may publish a namespaced custom metadata claim documented in the extension specification.

Illustrative example:

~~~java
metadata.claim(
    "urn:example:metadata:custom-code-grant",
    Map.of(
        "grant_type",
        CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue(),
        "required_parameters", List.of("code", "scope"),
        "code_usage", "single-use"
    )
);
~~~

This claim is extension-specific metadata, not a standard RFC 8414 field. Publish it only with clear specification, schema, and versioning. Clients that do not recognize the extension must still ignore unknown metadata claims per metadata extension-handling rules.

### 11.3. Do Not Alter Unrelated Metadata

Adding a custom grant does not automatically change:

- `token_endpoint_auth_methods_supported`;
- `token_endpoint_auth_signing_alg_values_supported`;
- `response_types_supported`;
- `code_challenge_methods_supported`;
- `scopes_supported`;
- `revocation_endpoint` or `introspection_endpoint`.

Only update those metadata fields when the corresponding capability actually changes. For instance, adding a grant does not mean the server now supports `private_key_jwt` or a new JWS signing algorithm.

### 11.4. Unified Configuration for Token Endpoint and Metadata

In a complete application, place the converter/provider and both metadata customizers in the same Authorization Server configuration:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        AuthenticationConverter customCodeGrantAuthenticationConverter,
        AuthenticationProvider customCodeGrantAuthenticationProvider)
        throws Exception {

    String grantType =
        CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue();
    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server -> server
            .tokenEndpoint(tokenEndpoint -> tokenEndpoint
                .accessTokenRequestConverter(
                    customCodeGrantAuthenticationConverter)
                .authenticationProvider(
                    customCodeGrantAuthenticationProvider)
            )
            .authorizationServerMetadataEndpoint(endpoint ->
                endpoint.authorizationServerMetadataCustomizer(metadata ->
                    metadata.grantType(grantType)
                )
            )
            .oidc(oidc -> oidc
                .providerConfigurationEndpoint(endpoint ->
                    endpoint.providerConfigurationCustomizer(metadata ->
                        metadata.grantType(grantType)
                    )
                )
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

The example enables OIDC. If the application does not deploy OIDC, omit the `oidc` block and configure only OAuth2 Authorization Server Metadata. `RegisteredClient`, `OAuth2AuthorizationService`, `AuthorizationServerSettings`, `JWKSource`, and the token generator must still be declared per the application's configuration.

## 12. Metadata, Client Registration, and Runtime Must Be Consistent

Three layers must reflect the same capability:

| Layer | Question It Must Answer |
|---|---|
| Runtime Token Endpoint | Does a converter/provider handle this grant type? |
| `RegisteredClient` | Is this specific client permitted to use this grant type? |
| Authorization Server Metadata | Does the server advertise this grant type as a supported capability? |

Common inconsistent states:

- Metadata advertises the grant, but converter/provider are not registered;
- Runtime processes the grant, yet metadata does not advertise it;
- Both metadata and runtime support it, yet `RegisteredClient` does not permit it;
- One node has deployed the extension while another node has not;
- OAuth2 metadata is updated, yet OIDC discovery retains stale values.

### 12.1. Metadata Is a Server-Level Capability

`grant_types_supported` does not list per-client grants. It describes grant types supported by the Authorization Server overall. Client-specific authorization remains in `RegisteredClient.getAuthorizationGrantTypes()`.

Do not automatically populate metadata with every grant type found in the `RegisteredClient` database. An old or misconfigured registration does not prove the runtime actually implements that grant.

### 12.2. Metadata Does Not Replace Registration Validation

Clients reading `grant_types_supported` learn that the server supports the extension. When registering or sending token requests, the server must still validate client registration, authentication method, grant permission, and scope policy.

### 12.3. Rolling Deployment

When deploying an extension across multiple nodes:

1. Deploy code with compatible converter/provider and policies to nodes;
2. Ensure `RegisteredClient` data is updated in alignment with the release;
3. Verify all nodes run the same extension version;
4. Once runtime is ready everywhere, publish the updated metadata;
5. Monitor `unsupported_grant_type`, `unauthorized_client`, and `invalid_grant` error rates;
6. On rollback, remove the grant from metadata and client registrations per the compatibility plan.

Do not publish new metadata before the entire processing path is live across the topology the load balancer can route to.

## 13. Extension Grants and Dynamic Client Registration

RFC 8414 uses the same grant type values as the `grant_types` field in Dynamic Client Registration. This lets clients discover general capabilities before requesting registration.

However, DCR may enforce a stricter allowlist. Some servers only allow administrators to grant custom grants; others restrict them to specific client types or require manual review prior to activation.

### 13.1. Validating Grant Types During Client Registration

The registration service should:

- Verify the grant type is a capability the server truly supports;
- Check that the caller is authorized to request that grant type;
- Apply policies by client type and tenant;
- Verify the grant type is compatible with the client authentication method;
- Audit who granted permission and when;
- Reject unknown grant URIs or ones disallowed by policy.

### 13.2. Previously Registered Clients

When adding an extension grant to a running system, do not automatically add the grant to every `RegisteredClient`. Identify the approved client list and update registrations through an audited governance/migration process.

### 13.3. Removing a Grant from a Client

When a client is no longer allowed to use an extension:

1. Remove the grant type from `RegisteredClient`;
2. The provider must reject new requests with `unauthorized_client`;
3. Decide whether already-issued tokens/authorizations remain valid until expiry or must be revoked;
4. Update client documentation and registration policy;
5. Remove server-wide metadata only when the extension is no longer supported for any client.

Removing a grant from one client does not mean the server stops supporting the grant for all other clients.

## 14. Securing Extension Grants

Extension grants often carry a custom credential or assertion. Because the server defines its own semantics, the implementation team must write an explicit threat model and validation contract. The fact that a converter parses a request does not mean the proof inside is valid.

### 14.1. Protecting One-Time Codes

For code-based grants:

- Generate codes using a cryptographically secure random generator;
- Ensure sufficient entropy to resist brute force;
- Store only hashes/digests if raw code recovery is unnecessary;
- Bind codes to registered client, subject, tenant, and audience where applicable;
- Set short expirations and attempt limits;
- Consume codes exactly once via atomic operations;
- Never put codes into URLs, logs, traces, or analytics;
- Enforce rate limits by client and request origin.

If the code is a short user-entered code, apply stronger brute-force defenses: entropy, attempt limits, lockouts/rate limits, short validity windows, and binding checks. Never assume a short code is secure merely because it is single-use.

### 14.2. Protecting Assertions

If the extension uses JWT/SAML assertions instead of codes, the provider must validate per the assertion specification:

- Signature and allowed algorithms;
- Trusted issuer;
- Audience matching the Authorization Server;
- Expiration and not-before;
- Issued-at within an acceptable time window;
- Subject/actor and delegation semantics;
- Unique identifier such as `jti` to prevent replay;
- Key rotation and trust configuration.

Do not accept an assertion just because its payload parses. Never allow the `none` algorithm or let clients choose algorithms outside an allowlist.

### 14.3. Client Authentication and Transport

The Token Endpoint must use HTTPS. Confidential clients must authenticate via their registered method. For high-privilege clients or sensitive assertions, consider `private_key_jwt` or mutual TLS based on threat model and system capabilities.

Never accept client secrets in query strings. Never implement a second client authentication mechanism inside a custom provider. Never ignore authentication results established by the filter chain.

### 14.4. Scope and Subject

The provider must bound privileges using three sources: client-registered scopes, grant scopes, and client-requested scopes. Token subjects must come from a verified source. Never treat a client-submitted username or subject as proof of identity.

For machine-to-machine grants, the principal can be the client. For grants representing an End-User, the principal must be verified from the code/assertion, and token claims must accurately reflect subject/delegation semantics. Never automatically treat every custom grant as an OIDC login flow or issue ID Tokens.

### 14.5. Token Lifetime and Refresh

Choose short access token lifetimes tailored to risk. Issue refresh tokens only if the extension has a long-lived delegation model with proper rotation, revocation, and client storage. If the grant is solely a one-time exchange, a short-lived access token may suffice.

If the access token is a JWT, Resource Servers must verify issuer, audience, signature, expiry, and scopes. If using opaque tokens, the introspection path must resolve the persisted authorization.

### 14.6. Logging and Error Disclosure

Never log raw codes, assertions, client secrets, access tokens, or refresh tokens. Log correlation ID, authenticated client ID, grant type, error code, and latency. Client-facing errors should give enough detail for clients to handle failures without disclosing whether a code exists, which client it belongs to, or who already redeemed it.

## 15. Extension Grant vs. Extending an Existing Grant?

Not every Token Endpoint change needs a new `AuthorizationGrantType`.

| Requirement | Approach |
|---|---|
| New credential/authorization grant type with distinct semantics | Extension grant and custom `AuthenticationConverter`/Provider |
| Adding claims to existing access tokens | `OAuth2TokenCustomizer` |
| Adjusting validation for a standard grant | Customize existing provider/validator |
| Adding parameters to a standard grant | Extend converter/provider only if contract requires it without breaking standard semantics |
| Changing JSON token response | Custom response handler with clear specification |
| Adding a client authentication method | Client authentication extension, not an authorization grant |
| Adding a completely new protocol endpoint | Dedicated endpoint filter/configurer and appropriate metadata |

### 15.1. Do Not Overload Standard Parameters

Do not reuse `code`, `assertion`, `scope`, or `client_id` with different meanings across grants without explicit documentation. If the extension needs custom parameters, pick names that avoid colliding with standard parameters and define how duplicate/unknown fields are handled.

### 15.2. Maintain Compatibility with Standard Grants

Custom converters handle only the extension's URI and return `null` for other requests. Custom providers support only the custom authentication token. Do not replace the default token endpoint converter/provider list without a verified compatibility reason.

## 16. Testing Extension Grants

Testing should be split into converter tests, provider tests, endpoint integration tests, and metadata tests. Each layer verifies a distinct part of the contract.

### 16.1. Converter Tests

Test at minimum:

- Request using the custom grant builds the expected authentication token;
- Request using a standard grant returns `null` for other converters to handle;
- Missing `grant_type`;
- Duplicate `grant_type`;
- Missing `code`;
- Duplicate or empty `code`;
- Missing `scope`;
- Empty or duplicate `scope`;
- Request containing extra out-of-contract parameters;
- Client principal retrieved from `SecurityContext`.

Example testing a request with another grant type:

~~~java
@Test
void returnsNullForGrantTypeOwnedByAnotherConverter() {
    MockHttpServletRequest request =
        new MockHttpServletRequest("POST", "/oauth2/token");
    request.addParameter("grant_type", "client_credentials");

    Authentication result =
        new CustomCodeGrantAuthenticationConverter().convert(request);

    assertThat(result).isNull();
}
~~~

### 16.2. Provider Tests

Mock or fake `CustomCodeGrantService`, `OAuth2AuthorizationService`, and the token generator to test:

- Unauthenticated client is rejected;
- Client without custom grant receives `unauthorized_client`;
- Invalid, expired, used, or wrong-client code receives `invalid_grant`;
- Excessive scope receives `invalid_scope`;
- Token generator returning `null` produces `server_error`;
- Authorization is saved with accurate grant type, principal, scopes, and token metadata;
- Code is consumed only once;
- Principal in token context is the principal verified by the grant service.

### 16.3. Token Endpoint Integration Test with MockMvc

Integration tests should exercise the real `SecurityFilterChain`, client authentication, and token generator from the test context:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CustomCodeGrantEndpointTests {

    @Autowired
    MockMvc mvc;

    @Test
    void issuesAccessTokenForValidCustomCodeGrant() throws Exception {
        String code = customCodeGrantFixture();

        mvc.perform(post("/oauth2/token")
                .with(httpBasic("custom-client", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type",
                    "urn:example:params:oauth:grant-type:custom-code")
                .param("code", code)
                .param("scope", "profile.read"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.access_token").isNotEmpty())
            .andExpect(jsonPath("$.token_type").value("Bearer"))
            .andExpect(jsonPath("$.expires_in").isNumber());
    }
}
~~~

This is a test skeleton. `customCodeGrantFixture()` must generate a valid code bound to the test client and corresponding scopes. The endpoint path and client authentication must match `AuthorizationServerSettings` and `RegisteredClient` in the test application.

### 16.4. Negative Endpoint Tests

Write tests for:

- Wrong client credentials;
- Authenticated client without the custom grant registered;
- Invalid/expired/used code;
- Scope outside client registration;
- Scope outside grant permissions;
- Unknown grant type;
- Missing or duplicate parameters;
- Two concurrent requests exchanging the same code, with only one succeeding.

In particular, replay tests must run against a real persistence layer or a test double with atomic semantics. A sequential unit test does not prove code consumption is safe under concurrent requests.

### 16.5. Metadata Tests

Call the Authorization Server Metadata endpoint and confirm `grant_types_supported` contains the extension URI. If OIDC is enabled, call the OpenID Provider Configuration endpoint and confirm the corresponding grant type also appears.

Also verify that metadata has no duplicate grant types, advertised grant types match exact values in `RegisteredClient` and the converter, endpoint URLs reflect actual configuration, standard grant types remain present, and custom metadata claims match the published schema/version.

Example testing RFC 8414 metadata with MockMvc:

~~~java
@Test
void advertisesCustomGrantTypeInAuthorizationServerMetadata()
        throws Exception {
    mvc.perform(get("/.well-known/oauth-authorization-server"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.grant_types_supported",
            hasItem(CustomCodeGrantAuthenticationToken.GRANT_TYPE.getValue())));
}
~~~

If `AuthorizationServerSettings` uses a custom issuer path or metadata endpoint path, call the configured URL rather than hard-coding the default path in tests. For OIDC-enabled applications, add a corresponding assertion for the OpenID Provider Configuration response.

### 16.6. Testing Persistence and Concurrent Replay

If the code store uses JDBC, Redis, or a shared store, run integration tests against a real backend. Testcontainers can spin up the matching database engine to test transactions, conditional updates, and unique constraints. Issue two concurrent requests with the same code and verify only one consumes successfully.

## 17. Operations, Versioning, and Observability

An extension grant is part of your protocol contract. Once clients have integrated, changing the URI or request semantics can break token acquisition.

### 17.1. Versioning the Contract

Keep the grant URI stable when fixing internal implementation details without altering semantics. If breaking changes occur in parameters, validation, token subject, or response semantics, publish a new version or explicit compatibility rules.

Never silently change the meaning of an existing grant URI across releases. If the server must support two versions concurrently, register a converter/provider for each grant URI and advertise both in metadata.

### 17.2. Metrics

Track credential-free metrics:

| Metric | Purpose |
|---|---|
| `oauth2_custom_grant_requests_total` | Request counts by grant type and outcome |
| `oauth2_custom_grant_success_total` | Successful token issuances |
| `oauth2_custom_grant_invalid_grant_total` | Invalid codes/assertions |
| `oauth2_custom_grant_replay_total` | Detected replay attempts |
| `oauth2_custom_grant_provider_duration` | Verification and token issuance latency |
| `oauth2_custom_grant_token_generation_errors` | Token generator failures |
| `oauth2_metadata_requests_total` | Monitor metadata endpoint traffic |

Never use codes, assertions, raw subjects, or token values as metric labels.

### 17.3. Auditing

Audit records may include authenticated client ID, grant URI, correlation ID, outcome, granted scopes, pseudonymized principal, and timestamp. Never log raw codes or assertions.

### 17.4. Rollback

Rolling back an extension involves three parts: metadata, client registrations, and runtime. Before removing a provider, check how long already-issued tokens remain valid, whether refresh tokens were issued, and which policy Resource Servers use to continue validating tokens.

Do not remove the grant from metadata while clients may still be routed to nodes handling requests differently. Nodes must maintain consistent configuration throughout rollout/rollback windows.

## 18. Endpoint Paths, Issuer, and Discovery

Authorization Server Metadata and OIDC Provider Configuration are used by clients to locate endpoint URLs. When configuring custom endpoint paths, let Spring Authorization Server generate metadata from the same `AuthorizationServerSettings` rather than hard-coding URLs inside metadata customizers.

Example endpoint settings configuration:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://identity.example.com")
        .tokenEndpoint("/oauth2/v2/token")
        .authorizationEndpoint("/oauth2/v2/authorize")
        .build();
}
~~~

Paths in the example are illustrative. The metadata response must return `token_endpoint` pointing to the exact path served by the Token Endpoint filter. Extension grants continue using this same token endpoint path.

### 18.1. Two Discovery Documents

OAuth2 clients may read Authorization Server Metadata per RFC 8414. OIDC Relying Parties typically read OpenID Provider Configuration. If the server enables both, verify:

- `issuer` matches;
- `token_endpoint` points to the same endpoint;
- `grant_types_supported` is consistent;
- `jwks_uri`, `authorization_endpoint`, and other endpoints reflect the actual configuration;
- URLs use public origins reachable by clients.

### 18.2. Reverse Proxies and Public Issuer

Behind an ingress/reverse proxy, metadata must never expose internal hostnames or insecure HTTP schemes. Configure `issuer` and forwarded headers according to deployment so the server generates accurate public URLs. Inspect metadata from an external client's perspective, not solely via internal container URLs.

### 18.3. Do Not Alter token_endpoint to Distinguish Grants

Do not create a separate token endpoint per extension unless required by a specialized protocol. Clients select grants via `grant_type` at the Token Endpoint. Maintaining one standard endpoint lets clients reuse client authentication, error handling, and token response processing.

## 19. Troubleshooting

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Token Endpoint returns `unsupported_grant_type` | Converter did not match URI or converter not registered | Check grant URI, converter bean, and `tokenEndpoint` configurer |
| Converter accepts request but provider does not run | `supports()` returns `false` or provider not registered | Check authentication token class and provider wiring |
| Client receives `unauthorized_client` | `RegisteredClient` lacks custom grant | Check `authorizationGrantTypes` on that exact registration |
| Client receives `invalid_client` | Client authentication failed | Check authentication method, secret/key, and filter chain |
| Client receives `invalid_grant` | Code invalid, expired, used, or not bound to client | Check code store, client binding, expiry, and replay |
| Client receives `invalid_scope` | Scope exceeds `RegisteredClient` or grant authorization | Check scope contract and policy |
| Token generator returns `null` | Generator lacks support for token context or missing JWK/encoder | Check token generator, `JWKSource`, and token customizer |
| Access token issued but introspection misses it | Authorization not saved or different service instance | Check `OAuth2AuthorizationService` wiring and persistence |
| Metadata lacks custom grant | Metadata customizer not attached to the endpoint | Check `authorizationServerMetadataEndpoint` |
| OAuth2 metadata right but OIDC discovery wrong | Forgot to update `providerConfigurationCustomizer` | Synchronize both discovery documents |
| Metadata advertises grant but client cannot use it | Runtime or `RegisteredClient` disallows it | Check converter/provider and client registration |
| Only some nodes handle the grant | Inconsistent deployment/configuration | Check version, config, and rollout state |
| Token response missing scopes | Provider omitted authorized scopes from token context/response | Check token context and access token scopes |
| Code used twice under concurrent requests | Consumption is non-atomic | Check transactions/conditional updates |

### 19.1. Diagnostic Procedure

1. Read the exact `grant_type` from a redacted request.
2. Verify client authentication succeeded.
3. Confirm `RegisteredClient` was resolved and contains the grant type.
4. Confirm the converter returned the expected custom `Authentication` token.
5. Confirm `AuthenticationManager` selected the provider via `supports()`.
6. Confirm the grant service verified and consumed the code.
7. Check requested scopes vs. authorized scopes.
8. Check the token generator and authorization persistence.
9. Fetch metadata from public discovery URLs to compare advertised capabilities.

Never log raw grant codes, assertions, client secrets, or tokens for diagnostics. Use correlation IDs and error categories.

## 20. Production Checklist

1. **Grant identifier:** absolute, stable URI published in the extension contract?
2. **Converter:** accepts only the target grant type, rejects missing/duplicate parameters, and defers other requests?
3. **Provider:** `supports()` accepts only the custom grant token class?
4. **Client authentication:** Token Endpoint uses the standard client authentication pipeline?
5. **Client permission:** specific `RegisteredClient` records permitted to use the extension grant?
6. **Grant validation:** code/assertion verifies signature, issuer, audience, expiry, and binding?
7. **Replay:** one-time code is consumed atomically and succeeds only once?
8. **Scopes:** requested scopes are a subset of client scopes and grant scopes?
9. **Principal:** subject comes from a verified source?
10. **Token generation:** uses shared `OAuth2TokenGenerator` and policy-compliant token customizers?
11. **Persistence:** `OAuth2Authorization` saved with grant type, principal, scopes, and token metadata?
12. **Response:** success handler returns a standard `OAuth2AccessTokenResponse`?
13. **Errors:** `invalid_request`, `invalid_client`, `unauthorized_client`, `invalid_grant`, `invalid_scope`, and `unsupported_grant_type` used in proper contexts?
14. **Metadata:** `grant_types_supported` advertises actual capabilities accurately?
15. **OIDC discovery:** Provider Configuration consistent if OIDC is enabled?
16. **DCR:** dynamic registration enforces an allowlist/policy for custom grants?
17. **Transport:** HTTPS and no credentials in URLs?
18. **Observability:** no codes/assertions/tokens logged; metrics, audits, and replay alerts in place?
19. **Testing:** converter, provider, MockMvc, metadata, and concurrent replay tests?
20. **Deployment:** nodes run identical code/config with compatible rollout/rollback?

## 21. Applied Exercises

**Scenario A — Unrecognized Grant:** The client sends the exact `grant_type` URI, yet the Token Endpoint returns `unsupported_grant_type`. Trace the filter, converter, `Authentication` token, and provider to pinpoint what was not registered.

**Scenario B — Unauthorized Client:** Both converter and provider work, yet a client receives `unauthorized_client`. Explain why server-level support does not substitute for `RegisteredClient` grant permissions.

**Scenario C — Replay:** Two concurrent requests submit the same one-time code and both receive access tokens. Redesign the consume operation so only one request updates state successfully.

**Scenario D — Scope Escalation:** A client registered for `profile.read` sends `profile.read` and `orders.read`. Build validation ensuring tokens never contain scopes outside the registration or grant.

**Scenario E — Metadata Drift:** RFC 8414 metadata lists the custom grant, yet OIDC discovery omits it. Update the provider configuration and write an integration test verifying both responses align.

**Scenario F — Non-Introspectable Token:** The client successfully receives an access token, yet introspection reports `inactive`. Inspect authorization persistence, token metadata, and the `OAuth2AuthorizationService` injected into the provider.

**Scenario G — Breaking Change:** The extension must change parameter `code` to `assertion` and alter subject semantics. Decide whether to keep the URI or publish a new versioned grant URI, then plan the rollout.

**Hints:** A check converter/provider wiring; B check `RegisteredClient`; C use atomic conditional update; D check scope set intersection; E update both discovery customizers; F save `OAuth2Authorization`; G use a versioned extension contract when changing semantics incompatibly.

## 22. Summary

Spring Authorization Server extends the Token Endpoint by registering an `AuthenticationConverter` and an `AuthenticationProvider`. The converter recognizes the grant type, validates request parameters, and constructs a dedicated `OAuth2AuthorizationGrantAuthenticationToken`. The provider authenticates the client, checks `RegisteredClient` grant permissions, verifies the proof, applies scopes, generates an access token, and persists `OAuth2Authorization`.

An extension grant requires an absolute URI, and clients must register that grant type in `RegisteredClient`. Authorization Server Metadata under RFC 8414 advertises server-level capabilities via `grant_types_supported`; if OIDC is enabled and clients use OpenID Provider Configuration discovery, OIDC metadata must also be updated so both discovery documents stay consistent.

Metadata does not grant client permissions. Runtime converter/provider, `RegisteredClient` permissions, and metadata must reflect the same capability. A production-ready extension grant also needs replay protection, client/subject binding, scope restrictions, credential protection, concurrent request testing, and a versioning/rollback process.

## 23. References

- [RFC 6749 — The OAuth 2.0 Authorization Framework, Section 4.5 Extension Grants](https://www.rfc-editor.org/rfc/rfc6749.html#section-4.5): absolute URI in `grant_type` and additional request parameters.
- [RFC 6749 — Section 5 Issuing an Access Token](https://www.rfc-editor.org/rfc/rfc6749.html#section-5): token response and error semantics.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): `grant_types_supported` and metadata fields.
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591.html): client `grant_types` and registration policy.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): security guidance for OAuth2 clients, authorization servers, and resource servers.
- [Spring Authorization Server 1.5.8 — How-to: Implement an Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html): converter, provider, token endpoint configuration, and request example.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OAuth2TokenEndpointConfigurer`, default converters/providers, and metadata endpoint.
- [Spring Authorization Server API — OAuth2TokenEndpointConfigurer](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenEndpointConfigurer.html): API for registering access token request converters/providers.
- [Spring Authorization Server API — OAuth2AuthorizationServerMetadataEndpointConfigurer](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationServerMetadataEndpointConfigurer.html): `authorizationServerMetadataCustomizer`.
- [Spring Authorization Server API — AbstractOAuth2AuthorizationServerMetadata.AbstractBuilder](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/AbstractOAuth2AuthorizationServerMetadata.AbstractBuilder.html): `grantType`/`grantTypes` and metadata builder methods.
- [Spring Authorization Server API — OAuth2AuthorizationGrantAuthenticationToken](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2AuthorizationGrantAuthenticationToken.html): base class for custom grant authentication tokens.
- [Spring Authorization Server API — OAuth2AccessTokenAuthenticationToken](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2AccessTokenAuthenticationToken.html): authentication result when issuing access tokens.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `OAuth2Authorization`, `OAuth2TokenGenerator`, and authorization services.
