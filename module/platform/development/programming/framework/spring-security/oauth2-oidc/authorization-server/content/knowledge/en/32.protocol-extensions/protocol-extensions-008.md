# Customizing Endpoints Using Public Extension Points

## 1. Objectives and Scope

In the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, we learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using **Spring Security**, **Spring Authorization Server**, and **Spring Boot**. This lesson explains how to extend protocol endpoint behavior through Spring Authorization Server's public extension points.

An Authorization Server often needs business-specific adjustments: adding extra checks at the Authorization Endpoint, adding an authorization grant, modifying claims in UserInfo, inserting validation prior to token introspection, or formatting responses according to policy. Spring Authorization Server supplies configurers and SPIs to make these adjustments while preserving the endpoint's processing lifecycle.

Common extension points include:

- `AuthenticationConverter`: converts an HTTP request into an `Authentication` object representing the protocol request.
- `AuthenticationProvider`: verifies and processes that `Authentication` object.
- `AuthenticationSuccessHandler`: renders the response on successful processing.
- `AuthenticationFailureHandler`: converts authentication failures into protocol responses.
- Validators and mappers: validate parameters or map context into claims/responses.
- Shared components such as `OAuth2TokenGenerator`, `OAuth2AuthorizationService`, and `RegisteredClientRepository`.

**Reference version:** code and APIs in this lesson target Spring Authorization Server **1.5.8**. When using another branch, check the Javadoc for your exact artifact/version because method names and endpoint configurers can change across major releases.

After this lesson, you will be able to:

1. Understand how `OAuth2AuthorizationServerConfigurer` wires endpoints into `SecurityFilterChain`.
2. Choose the right extension point for each type of change.
3. Add a converter/provider for an extension authorization grant.
4. Customize validators while keeping essential default checks intact.
5. Modify success/error handling without breaking protocol responses.
6. Extend UserInfo or other endpoints via mappers/providers.
7. Test execution order, compatibility, and security of extensions.

## 2. Processing Architecture of a Protocol Endpoint

### 2.1. Endpoint Filters Live Inside the Authorization Server SecurityFilterChain

`OAuth2AuthorizationServerConfigurer` configures the filters handling protocol endpoints and registers them into the Authorization Server's `SecurityFilterChain`. An endpoint configurer is the configuration entry point for the corresponding filter; it is not a standalone REST controller.

Filter chain configuration example per the 1.5.8 API:

```java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        RegisteredClientRepository registeredClientRepository,
        OAuth2AuthorizationService authorizationService,
        OAuth2TokenGenerator<?> tokenGenerator) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer
                .registeredClientRepository(registeredClientRepository)
                .authorizationService(authorizationService)
                .tokenGenerator(tokenGenerator)
                .tokenEndpoint(tokenEndpoint -> {
                    // Configure Token Endpoint extension points here.
                })
                .authorizationEndpoint(authorizationEndpoint -> {
                    // Configure Authorization Endpoint extension points here.
                })
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        );

    return http.build();
}
```

This is the configuration portion for the Authorization Server chain. Imports and bean dependencies are omitted to focus on endpoint configurers. The application still needs appropriate filter chains for form login, consent pages, or other web resources. Use `getEndpointsMatcher()` to scope this chain cleanly to protocol endpoints and keep chain ordering consistent with the rest of the application.

If the project already has an Authorization Server `SecurityFilterChain`, add the endpoint configurer to the existing bean. Do not create a second filter chain with the same matcher merely to register a converter/provider.

### 2.2. Three Stages: Pre-Processing, Main Processing, Post-Processing

Spring Authorization Server organizes extension points into three stages:

```text
HTTP request
     |
     v
Endpoint Filter
     |
     v
AuthenticationConverter(s)
     |  reads parameters, checks request structure
     |  creates appropriate Authentication
     v
AuthenticationManager
     |
     v
AuthenticationProvider(s)
     |  verifies client, grant, authorization,
     |  policy and issues/looks up data
     v
Authentication result
     |
     +------ success ---------> AuthenticationSuccessHandler
     |
     +------ error -----------> AuthenticationFailureHandler
                                  |
                                  v
                             HTTP response
```

| Stage | Component | Responsibility |
| --- | --- | --- |
| Pre-processing | `AuthenticationConverter` | Reads HTTP request and builds the appropriate authentication object |
| Main processing | `AuthenticationProvider` | Authenticates client/grant/token and executes protocol business logic |
| Post-processing | Success/error handler | Writes protocol-compliant status, headers, and body |

Not every endpoint exposes all four extension point categories. For example, UserInfo exposes `userInfoMapper`, the Token Endpoint exposes `accessTokenResponseHandler`, and the Authorization Endpoint exposes `consentPage`.

### 2.3. Converters and Providers Have Distinct Contracts

`AuthenticationConverter.convert(request)` can return:

- an `Authentication` if the converter recognizes and converts the request;
- `null` if the request belongs to another type so the next converter can handle it;
- a protocol exception if the request matches the converter's format but is missing/malformed parameters.

`AuthenticationProvider` provides:

- `supports(authenticationClass)` to declare which `Authentication` type the provider handles;
- `authenticate(authentication)` to authenticate and return the result, or throw an exception.

A custom grant typically requires both a converter and a provider. The converter should not issue tokens itself; the provider should not parse `HttpServletRequest` itself. This separation enables independent testing and aligns with Spring Security's architecture.

## 3. Extension Point Map by Endpoint

Public configurers in Spring Authorization Server 1.5.8 expose extension points matching each endpoint's function:

| Endpoint / Configurer | Converter | Provider | Post-Processing / Mapper |
| --- | --- | --- | --- |
| Authorization Endpoint | `authorizationRequestConverter(s)` | `authenticationProvider(s)` | `authorizationResponseHandler`, `errorResponseHandler`, `consentPage` |
| Client Authentication | `authenticationConverter(s)` | `authenticationProvider(s)` | `authenticationSuccessHandler`, `errorResponseHandler` |
| Token Endpoint | `accessTokenRequestConverter(s)` | `authenticationProvider(s)` | `accessTokenResponseHandler`, `errorResponseHandler` |
| Token Introspection | `introspectionRequestConverter(s)` | `authenticationProvider(s)` | `introspectionResponseHandler`, `errorResponseHandler` |
| Token Revocation | `revocationRequestConverter(s)` | `authenticationProvider(s)` | `revocationResponseHandler`, `errorResponseHandler` |
| Device Authorization | `deviceAuthorizationRequestConverter(s)` | `authenticationProvider(s)` | `deviceAuthorizationResponseHandler`, `errorResponseHandler` |
| Device Verification | `deviceVerificationRequestConverter(s)` | `authenticationProvider(s)` | `deviceVerificationResponseHandler`, `errorResponseHandler` |
| Pushed Authorization Request | `pushedAuthorizationRequestConverter(s)` | `authenticationProvider(s)` | `pushedAuthorizationResponseHandler`, `errorResponseHandler` |
| OIDC UserInfo | `userInfoRequestConverter(s)` | `authenticationProvider(s)` | `userInfoMapper`, `userInfoResponseHandler`, `errorResponseHandler` |
| OIDC Logout | `logoutRequestConverter(s)` | `authenticationProvider(s)` | `logoutResponseHandler`, `errorResponseHandler` |
| OIDC Client Registration | `clientRegistrationRequestConverter(s)` | `authenticationProvider(s)` | `clientRegistrationResponseHandler`, `errorResponseHandler` |
| Authorization Server Metadata | — | — | `authorizationServerMetadataCustomizer` |
| OIDC Provider Configuration | — | — | `providerConfigurationCustomizer` |

Check the Javadoc of the corresponding endpoint configurer for exact method signatures. This table shows the general pattern and does not imply every endpoint uses the exact same classes or `Authentication` types.

### 3.1. Adding Components vs. Customizing the Component List

Many configurers provide two API forms:

- `...Converter(converter)` or `authenticationProvider(provider)`: appends a single component.
- `...Converters(Consumer<List<AuthenticationConverter>>)` or `authenticationProviders(Consumer<List<AuthenticationProvider>>)`: accesses the list of default and added components for customization.

The `Consumer<List<...>>` form is useful when replacing a validator inside a default provider or reordering converters. However, modifying the list can inadvertently remove default behavior. Modify only the needed component and preserve the rest.

### 3.2. Extension Points and Shared Components

`OAuth2AuthorizationServerConfigurer` also lets you configure foundational components:

| Component | Impact |
| --- | --- |
| `RegisteredClientRepository` | Resolves clients, grant types, authentication methods, and registered scopes |
| `OAuth2AuthorizationService` | Persists, retrieves, updates, and deletes authorizations |
| `OAuth2AuthorizationConsentService` | Persists resource owner consents |
| `AuthorizationServerSettings` | Issuer and endpoint URIs |
| `OAuth2TokenGenerator` | Issues access tokens, refresh tokens, and ID Tokens per configured generators |
| Client authentication configurer | Authenticates clients at endpoints requiring client authentication |

If a requirement involves token formats or token claims, consider `OAuth2TokenGenerator`/`OAuth2TokenCustomizer` instead of rewriting the entire Token Endpoint. If a requirement involves storage, swap `OAuth2AuthorizationService` rather than intervening directly in filters.

## 4. Choosing the Right Extension Point

Before writing code, frame the change as a concrete question:

| Need | Appropriate Extension Point |
| --- | --- |
| Parse extra parameters in requests | Converter |
| Add a client authentication method | `clientAuthentication().authenticationConverter(s)`, `authenticationProvider(s)`, and handlers |
| Add validation based on client, grant, or authorization | Provider validator or custom Provider |
| Add a new grant type | Grant `AuthenticationConverter` + grant `AuthenticationProvider` + Token Endpoint |
| Customize claims in UserInfo | `userInfoMapper` |
| Customize JWT/access token claims | Token customizer or token generator |
| Change response body per endpoint spec | Success handler, if response model genuinely needs changes |
| Standardize protocol errors | Error handler, if default mapping does not meet requirements |
| Change endpoint URLs | `AuthorizationServerSettings` |
| Change authorization storage | `OAuth2AuthorizationService` |
| Change client/consent storage | `RegisteredClientRepository` / `OAuth2AuthorizationConsentService` |

Prefer the narrowest extension point that meets the requirement. Replacing an entire provider or handler carries a much larger blast radius than adding a validator or mapper.

## 5. Example: Customizing the Authorization Endpoint Validator

### 5.1. What Does the Default Validator Check?

The Authorization Endpoint processes authorization requests and consent. In the Authorization Code Flow, `OAuth2AuthorizationCodeRequestAuthenticationProvider` uses a default validator to validate parameters such as `redirect_uri` and `scope`. If validation fails, the provider throws `OAuth2AuthorizationCodeRequestAuthenticationException`.

A common requirement is adding a per-tenant or per-environment policy—for example, restricting `redirect_uri` against a custom allowlist while keeping the default scope validator intact.

### 5.2. Chaining a Custom Validator with the Default Validator

The example below uses `authenticationProviders(...)` to locate the default provider and replace its validator:

```java
private Consumer<List<AuthenticationProvider>> configureAuthorizationValidator(
        RedirectUriPolicy redirectUriPolicy) {
    return providers -> providers.forEach(provider -> {
        if (provider instanceof OAuth2AuthorizationCodeRequestAuthenticationProvider codeProvider) {
            Consumer<OAuth2AuthorizationCodeRequestAuthenticationContext> validator =
                    new TenantRedirectUriValidator(redirectUriPolicy)
                            .andThen(
                                OAuth2AuthorizationCodeRequestAuthenticationValidator
                                    .DEFAULT_SCOPE_VALIDATOR
                            );

            codeProvider.setAuthenticationValidator(validator);
        }
    });
}
```

Register the validator in the Authorization Server chain:

```java
authorizationServer.authorizationEndpoint(endpoint ->
        endpoint.authenticationProviders(
                configureAuthorizationValidator(redirectUriPolicy)
        )
);
```

`TenantRedirectUriValidator` is an application-defined validator. It receives `OAuth2AuthorizationCodeRequestAuthenticationContext`, extracts the authorization request, and checks the redirect URI against server-side policy. The validator must throw `OAuth2AuthorizationCodeRequestAuthenticationException` with an appropriate `OAuth2Error` if the request is rejected.

Example illustrating simple allowlist validation:

```java
final class TenantRedirectUriValidator
        implements Consumer<OAuth2AuthorizationCodeRequestAuthenticationContext> {

    private final RedirectUriPolicy redirectUriPolicy;

    TenantRedirectUriValidator(RedirectUriPolicy redirectUriPolicy) {
        this.redirectUriPolicy = redirectUriPolicy;
    }

    @Override
    public void accept(OAuth2AuthorizationCodeRequestAuthenticationContext context) {
        OAuth2AuthorizationCodeRequestAuthenticationToken authentication =
                context.getAuthentication();

        String redirectUri = authentication.getRedirectUri();
        RegisteredClient registeredClient = context.getRegisteredClient();

        if (!redirectUriPolicy.isAllowed(registeredClient, redirectUri)) {
            OAuth2Error error = new OAuth2Error(
                    OAuth2ErrorCodes.INVALID_REQUEST,
                    "The redirect_uri is not allowed by tenant policy",
                    null
            );
            throw new OAuth2AuthorizationCodeRequestAuthenticationException(
                    error, null
            );
        }
    }
}
```

`RedirectUriPolicy` here is an application-implemented business service. The policy must rely on the identified client registration/tenant and a server-managed URI list. Do not accept a URI merely because it comes from a seemingly trusted domain, avoid broad wildcards, and never automatically add client-submitted URIs to the allowlist.

### 5.3. Why Keep the Default Validator?

The snippet chains `DEFAULT_SCOPE_VALIDATOR` after the redirect URI validator. If you replace the entire validator while dropping the scope validator, requests can bypass scope checks that Spring Authorization Server normally performs.

When customizing a default provider:

- locate the target provider using `instanceof`;
- preserve default validators you do not intend to replace;
- do not remove default providers from the list;
- write tests for both valid requests and requests that must be rejected.

If replacing the redirect URI validator, the custom validator must enforce policies at least as strict as OAuth 2.0 security requirements.

## 6. Example: Adding an Extension Authorization Grant

### 6.1. When Do You Need a New Grant?

Spring Authorization Server supports standard grants such as Authorization Code, Refresh Token, Client Credentials, Device Code, and Token Exchange depending on version/configuration. When business requirements genuinely call for a custom grant, you can extend the Token Endpoint using a unique grant type URI, such as:

```text
urn:ietf:params:oauth:grant-type:custom_code
```

The custom grant must be clearly specified in the contract between clients and the Authorization Server. Do not create a new grant just to add a parameter to a standard grant; existing converters/validators are often better suited for that.

### 6.2. Custom Grant AuthenticationToken

The grant token carries data parsed from the HTTP request by the converter. It should extend `OAuth2AuthorizationGrantAuthenticationToken` so the provider and Token Endpoint recognize its type properly:

The snippets in this custom grant section are illustrative classes; imports are omitted to focus on the extension contract.

```java
public final class CustomCodeGrantAuthenticationToken
        extends OAuth2AuthorizationGrantAuthenticationToken {

    private final String code;

    public CustomCodeGrantAuthenticationToken(
            String code,
            Authentication clientPrincipal,
            Map<String, Object> additionalParameters) {
        super(
                new AuthorizationGrantType(
                        "urn:ietf:params:oauth:grant-type:custom_code"
                ),
                clientPrincipal,
                additionalParameters
        );
        this.code = code;
    }

    public String getCode() {
        return this.code;
    }
}
```

This is the extension's internal `Authentication` type. `code` must be the grant credential verified inside the provider, not a value assumed to be pre-verified by the converter.

### 6.3. Converter for the Custom Grant

The converter processes only requests with the exact `grant_type`; other requests return `null` so default or other converters continue processing:

```java
public final class CustomCodeGrantAuthenticationConverter
        implements AuthenticationConverter {

    private static final String GRANT_TYPE =
            "urn:ietf:params:oauth:grant-type:custom_code";

    @Override
    public Authentication convert(HttpServletRequest request) {
        String grantType = request.getParameter(OAuth2ParameterNames.GRANT_TYPE);
        if (!GRANT_TYPE.equals(grantType)) {
            return null;
        }
        String[] grantTypeValues =
                request.getParameterValues(OAuth2ParameterNames.GRANT_TYPE);
        if (grantTypeValues == null || grantTypeValues.length != 1) {
            throw new OAuth2AuthenticationException(OAuth2ErrorCodes.INVALID_REQUEST);
        }
        Set<String> allowedParameters = Set.of(
                OAuth2ParameterNames.GRANT_TYPE,
                OAuth2ParameterNames.CODE,
                OAuth2ParameterNames.SCOPE,
                OAuth2ParameterNames.CLIENT_ID,
                OAuth2ParameterNames.CLIENT_SECRET
        );
        if (!allowedParameters.containsAll(request.getParameterMap().keySet())) {
            throw new OAuth2AuthenticationException(OAuth2ErrorCodes.INVALID_REQUEST);
        }

        String code = request.getParameter(OAuth2ParameterNames.CODE);
        String[] codeValues = request.getParameterValues(OAuth2ParameterNames.CODE);
        if (!StringUtils.hasText(code) || codeValues == null || codeValues.length != 1) {
            throw new OAuth2AuthenticationException(OAuth2ErrorCodes.INVALID_REQUEST);
        }

        Map<String, Object> additionalParameters = new HashMap<>();
        String[] scopeValues = request.getParameterValues(OAuth2ParameterNames.SCOPE);
        if (scopeValues != null) {
            if (scopeValues.length != 1) {
                throw new OAuth2AuthenticationException(OAuth2ErrorCodes.INVALID_REQUEST);
            }
            if (StringUtils.hasText(scopeValues[0])) {
                additionalParameters.put(OAuth2ParameterNames.SCOPE, scopeValues[0]);
            }
        }

        Authentication clientPrincipal =
                SecurityContextHolder.getContext().getAuthentication();

        return new CustomCodeGrantAuthenticationToken(
                code,
                clientPrincipal,
                additionalParameters
        );
    }
}
```

This snippet focuses on essential parameters. In a real implementation, if the grant accepts additional parameters:

- check whether parameters appear multiple times;
- permit only specified parameters;
- exclude already-processed protocol parameters from the additional parameter map;
- enforce size limits and data types;
- return `null` when the grant type does not belong to this converter.

The converter example above permits at most one `scope` parameter into `additionalParameters`. `client_id` and `client_secret` are allowlisted for the client authentication converter to process, but are not copied into the grant's additional parameters. `CustomCodeService` must read this scope, verify it against `RegisteredClient` and grant policy, and return the actually granted scope set in `CustomCodeResult`. Never pass client-sent scopes straight into tokens unverified.

Do not read client IDs from the request to identify the authenticated client. Use the client principal in `SecurityContextHolder` established by the client authentication filter.

### 6.4. Provider for the Custom Grant

The provider is where the grant credential is verified and tokens are issued. Key skeleton:

```java
public final class CustomCodeGrantAuthenticationProvider
        implements AuthenticationProvider {

    private final OAuth2AuthorizationService authorizationService;
    private final OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator;
    private final CustomCodeService customCodeService;

    public CustomCodeGrantAuthenticationProvider(
            OAuth2AuthorizationService authorizationService,
            OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator,
            CustomCodeService customCodeService) {
        this.authorizationService = authorizationService;
        this.tokenGenerator = tokenGenerator;
        this.customCodeService = customCodeService;
    }

    @Override
    public Authentication authenticate(Authentication authentication) {
        CustomCodeGrantAuthenticationToken grant =
                (CustomCodeGrantAuthenticationToken) authentication;

        OAuth2ClientAuthenticationToken clientPrincipal =
                getAuthenticatedClientElseThrowInvalidClient(grant);
        RegisteredClient registeredClient =
                clientPrincipal.getRegisteredClient();

        if (!registeredClient.getAuthorizationGrantTypes()
                .contains(grant.getGrantType())) {
            throw new OAuth2AuthenticationException(
                    OAuth2ErrorCodes.UNAUTHORIZED_CLIENT
            );
        }

        // Verify code, client binding, expiry, audience, and one-time use.
        CustomCodeResult result = customCodeService.consume(
                grant.getCode(), registeredClient, grant.getAdditionalParameters()
        );

        // Build OAuth2TokenContext and invoke tokenGenerator.generate(...).
        // Save OAuth2Authorization with access token into authorizationService.
        // Return OAuth2AccessTokenAuthenticationToken.
        return issueToken(grant, clientPrincipal, registeredClient, result);
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return CustomCodeGrantAuthenticationToken.class
                .isAssignableFrom(authentication);
    }
}
```

`getAuthenticatedClientElseThrowInvalidClient(...)` and `issueToken(...)` are example helpers to be implemented using Spring Authorization Server APIs. The provider must verify:

1. Client is authenticated.
2. `RegisteredClient` declares the custom grant type.
3. Code belongs to the exact client/subject/audience and has not expired.
4. Code has never been used; the consume operation must be atomic to prevent replay.
5. Requested scopes fall within client-allowed scopes and grant policy; actually issued scopes must come from the verified result of the custom code service.
6. The token generator returns a valid token; otherwise, return an appropriate protocol error.
7. The authorization is persisted before sending a successful response back to the client.

Never leave TODO validations in production. Spring's official provider guide demonstrates how to build `OAuth2TokenContext`, invoke `OAuth2TokenGenerator`, construct `OAuth2Authorization`, save the authorization, and return `OAuth2AccessTokenAuthenticationToken`.

### 6.5. Registering Converter and Provider

Add both components to the Token Endpoint:

```java
authorizationServer.tokenEndpoint(tokenEndpoint ->
        tokenEndpoint
            .accessTokenRequestConverter(
                    new CustomCodeGrantAuthenticationConverter()
            )
            .authenticationProvider(
                    new CustomCodeGrantAuthenticationProvider(
                            authorizationService,
                            tokenGenerator,
                            customCodeService
                    )
            )
);
```

Clients must also be registered with the corresponding `AuthorizationGrantType`:

```java
AuthorizationGrantType customGrant =
        new AuthorizationGrantType(
                "urn:ietf:params:oauth:grant-type:custom_code"
        );

RegisteredClient registeredClient = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("integration-client")
        .clientSecret(passwordEncoder.encode(clientSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(customGrant)
        .scope("records.read")
        .build();
```

This snippet assumes `passwordEncoder` and `clientSecret` are supplied from configuration/secret manager. Secrets and repositories in examples must be configured for real environments. Never use hard-coded secrets or `{noop}` in production.

### 6.6. Calling the Token Endpoint

An authenticated client sends a request per the custom grant contract:

```http
POST /oauth2/token HTTP/1.1
Authorization: Basic BASE64(integration-client:CLIENT_SECRET)
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:custom_code&code=ONE_TIME_CODE
```

This illustrates the extension's protocol. Parameter names and code semantics must be explicitly specified for clients, including expiry, client binding, replay protection, and returned errors.

## 7. Example: Customizing UserInfo Using a Mapper

### 7.1. When Is a Mapper Sufficient?

The UserInfo Endpoint is an OAuth2 protected resource. Clients present a Bearer Access Token; the provider validates the token and retrieves the associated authorization. If you only need to customize claims in the response, `userInfoMapper` is the right extension point. There is no need to replace converters or providers if Access Token validation remains unchanged.

The mapper receives `OidcUserInfoAuthenticationContext`, which provides:

- the Access Token used for the request;
- the `OAuth2Authorization` bound to the Access Token;
- the ID Token and related authorization metadata.

### 7.2. Creating a Scope-Gated UserInfo Response

The example below returns claims strictly according to granted scopes, always sourcing `sub` from the ID Token attached to the current authorization:

```java
Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper =
        context -> {
            OidcIdToken idToken = context.getAuthorization()
                    .getToken(OidcIdToken.class)
                    .getToken();
            String subject = idToken.getSubject();
            Set<String> scopes = context.getAccessToken().getScopes();

            Map<String, Object> claims = new LinkedHashMap<>();
            claims.put("sub", subject);

            if (scopes.contains(OidcScopes.PROFILE)) {
                claims.putAll(profileService.loadProfileClaims(subject));
            }
            if (scopes.contains(OidcScopes.EMAIL)) {
                claims.putAll(profileService.loadEmailClaims(subject));
            }
            if (scopes.contains(OidcScopes.PHONE)) {
                claims.putAll(profileService.loadPhoneClaims(subject));
            }

            // Do not allow the profile service to overwrite subject.
            claims.put("sub", subject);
            return new OidcUserInfo(claims);
        };
```

Register the mapper in the OIDC configurer:

```java
authorizationServer.oidc(oidc ->
        oidc.userInfoEndpoint(userInfo ->
                userInfo.userInfoMapper(userInfoMapper)
        )
);
```

`profileService` is an application-implemented service. Its methods return only claims permitted by scopes and consent. If the profile service returns incomplete data, the mapper can omit optional claims; never fabricate placeholder values to pad the response.

### 7.3. Invariants to Maintain

- `sub` in UserInfo must match the subject of the current Access Token/ID Token.
- Never read subject from a query parameter or a client-submitted profile identifier.
- Return only claims allowed by scopes, consent, and privacy policy.
- Never return passwords, recovery data, security answers, or internal attributes.
- If `sub` cannot be obtained from a valid authorization, fail the request; never invent another subject.
- Test responses with Access Tokens carrying different scopes and with incomplete profile service data.

Only consider `authenticationProviders(...)` if you need to customize Access Token verification itself or how authorizations are retrieved. When only altering claims, a mapper keeps the change footprint smaller.

## 8. Success Handlers, Error Handlers, and Consent Pages

### 8.1. Success Handlers Render Protocol Responses

A success handler receives the `Authentication` result processed by the provider. Depending on the endpoint, it must return the appropriate response:

| Endpoint | Expected Success Response |
| --- | --- |
| Authorization | Redirect/authorization response per `response_type` and `response_mode` |
| Token | OAuth2 access token response |
| Introspection | Token introspection response |
| Revocation | Response per RFC 7009 |
| UserInfo | UserInfo claims response |
| Client Registration | Registration or Client Read response |

Custom success handlers must preserve protocol status codes, `Content-Type`, `Cache-Control`, `Pragma`, headers, and body structure. Specifically for token responses, never omit `Cache-Control: no-store` and `Pragma: no-cache`.

If you only want to add logs or metrics, use observability hooks at the service/filter layer rather than replacing response handlers. If changing the response body, verify clients can still parse the OAuth/OIDC schema properly.

### 8.2. Error Handlers Must Not Expose Internal Details

An error handler receives an exception and produces a protocol error response. When customizing:

- preserve OAuth2/OIDC `error` codes;
- return only an `error_description` helpful to clients;
- never expose stack traces, SQL errors, internal class names, or sensitive data;
- keep HTTP status codes matching the error;
- log internally with correlation IDs and error categories—never log raw tokens/client secrets.

Never turn all errors into HTTP 200 or fake success responses. Clients need to distinguish `invalid_request`, `invalid_client`, `invalid_grant`, `unauthorized_client`, `invalid_scope`, and `server_error` where applicable.

### 8.3. Consent Page Is a UI Customization Point

The Authorization Endpoint exposes `consentPage(...)` to send the resource owner to an application-provided consent page. The consent page must:

- display the client requesting access and the specific scopes;
- let the user approve/deny per policy;
- submit the form via HTTP POST to the Authorization Endpoint;
- send back `client_id`, `state`, and the list of user-approved scopes;
- enforce CSRF protection and never auto-approve solely because the request is valid.

`state` in the consent flow binds the request; preserve the server-provided value and validate it across the flow. Do not treat a `scope` query parameter on the consent page as the sole source of permissions.

### 8.4. Metadata Endpoints Also Have Customizers

Authorization Server Metadata and OIDC Provider Configuration expose customizers for their response builders. These are the right extension points to advertise additional protocol-allowed metadata. Advertise only endpoints, grant types, response types, signing algorithms, or capabilities the server actually supports; published metadata must match runtime configuration.

## 9. Testing Extension Points

### 9.1. Test Matrix

| ID | Scenario | Expected Result |
| --- | --- | --- |
| EXT-01 | Authorization Server chain uses `getEndpointsMatcher()` | Protocol endpoints are handled by the right chain |
| EXT-02 | Custom grant converter added | Requests with the custom grant type are recognized |
| EXT-03 | Converter encounters another grant type | Returns `null` for the next converter to handle |
| EXT-04 | Request missing required parameter | Converter throws `invalid_request` protocol error |
| EXT-05 | Required parameter appears multiple times | Request is rejected |
| EXT-06 | Custom `AuthenticationToken` | Supported by provider matching exact class |
| EXT-07 | Provider receives unsupported `Authentication` | `supports()` returns `false` |
| EXT-08 | Unauthenticated client calls custom grant | Rejected by client authentication |
| EXT-09 | Client has not registered custom grant | Provider returns `unauthorized_client` |
| EXT-10 | Invalid/expired grant code | Provider rejects with appropriate grant error |
| EXT-11 | Reusing consumed grant code | Replay rejected; no second token issued |
| EXT-12 | Token generator returns `null` | Authorization not saved as success; returns `server_error` |
| EXT-13 | Authorization service save fails | No successful token response sent |
| EXT-14 | Custom validator rejects redirect URI | Authorization request rejected |
| EXT-15 | Custom redirect validator chains default scope validator | Invalid scopes continue to be rejected |
| EXT-16 | UserInfo Access Token lacks `email` scope | Mapper omits `email` claim |
| EXT-17 | UserInfo `sub` cannot be obtained from authorization | Request fails; no synthetic subject created |
| EXT-18 | Profile service returns data with different `sub` | Mapper preserves subject from ID Token |
| EXT-19 | Token Endpoint success handler | Response conforms to schema and cache headers |
| EXT-20 | Error handler receives `OAuth2AuthenticationException` | Appropriate error code/status; no stack trace leaked |
| EXT-21 | Custom consent page receives `state` | Consent POST submits back valid `state`/client/scopes |
| EXT-22 | Metadata customizer advertises unsupported capability | Configuration test fails |
| EXT-23 | Custom grant converter/provider registered alongside defaults | Standard grants still work |
| EXT-24 | `authenticationProviders(...)` used to swap validator | Other default providers remain in the list |
| EXT-25 | Two extension converters match the same grant type | Test detects ambiguous ordering/ownership |
| EXT-26 | Custom provider throws internal exception | Error response leaks no implementation details |
| EXT-27 | Custom grant scope exceeds client scopes | Request rejected |
| EXT-28 | Token response carries custom JWT claims | Signature, issuer, audience, and claims remain valid |
| EXT-29 | Upgrading Spring Authorization Server version | Compilation and integration tests confirm method/API compatibility |
| EXT-30 | Multiple instances run the same extension version | Tokens/authorizations saved and read consistently |
| EXT-31 | Custom client authentication converter added | Default methods like `client_secret_basic` still work |

### 9.2. Layered Testing Strategy

**Converter unit tests**

- Use `MockHttpServletRequest`.
- Test requests owned by the converter, requests not owned by it, and duplicate parameters.
- Verify the converter does not mutate `SecurityContext`.

**Provider unit tests**

- Mock `OAuth2AuthorizationService`, `OAuth2TokenGenerator`, and the grant verification service.
- Test client/grant/scope checks, expiry, replay, and token generator failures.
- Confirm authorizations are saved only after the grant validates and the token is generated.

**Endpoint integration tests**

- Boot a real `SecurityFilterChain` with endpoint configurers.
- Send HTTP requests with authenticated clients.
- Verify status, headers, body, and persisted authorizations.
- Verify standard grants continue working after adding extensions.

**Protocol interoperability tests**

- Send requests using real clients or test clients.
- Verify OAuth2/OIDC error and success responses match schemas.
- Verify discovery metadata matches live endpoints.

## 10. Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Converter does not run | Not added to the right endpoint configurer or intercepted by another filter chain | Check `getEndpointsMatcher()` and endpoint paths |
| Custom converter runs for standard grants | Converter fails to return `null` for other grant types | Check grant type before parsing parameters |
| Provider is never invoked | `supports()` does not match `Authentication` class or provider not registered | Check token class and `authenticationProvider(...)` |
| Custom provider blocks default providers | Custom provider matches too broadly or list replaced incorrectly | Narrow `supports()` and preserve default providers |
| Client receives `unauthorized_client` | `RegisteredClient` does not register the grant type | Add the right `AuthorizationGrantType` per policy |
| `invalid_grant` despite seemingly valid code | Code expired, used, wrong client binding, or wrong audience | Check grant lifecycle and bindings |
| `invalid_scope` | Custom validator dropped scopes or provider omitted client scope checks | Keep default validator or implement full policy |
| Authorization redirect URI rejected | Custom validator fails exact match with registered URI | Use exact matching and verify registration |
| UserInfo missing claims | Scope/consent disallows them or mapper omits mapping | Check Access Token scopes and mapper |
| UserInfo `sub` mismatch | Mapper read subject from another profile source | Lock `sub` to the current ID Token/authorization |
| Token Endpoint response violates schema | Custom success handler serializes non-standard body | Preserve response converter/schema and cache headers |
| Error returns HTTP 200 | Custom error handler sets wrong status | Use appropriate HTTP status and OAuth error mapping |
| Consent page loops repeatedly | Incorrect `client_id`/`state`/scope submission or consent not saved | Check form POST and `OAuth2AuthorizationConsentService` |
| Extension works locally but fails in cluster | Node missing provider/module or version mismatch | Synchronize artifacts/configs across all nodes |
| Upgrade compilation error | Configurer API or method signatures changed | Consult version-specific Javadoc and migration guide |

### 10.1. Distinguishing Request Errors from Provider Errors

- **Request parsing:** HTTP parameter missing, duplicated, or malformed; fix the converter.
- **Authentication/grant validation:** client, grant credential, scope, or authorization invalid; fix the provider/validator.
- **Token generation/persistence:** token generator or authorization service failure; fix dependencies and transactions.
- **Response mapping:** wrong status/headers/body; fix the success/error handler.

Never mask a failure in one layer by disabling checks in another layer.

## 11. Security and Operational Principles

### 11.1. Preserve Protocol Invariants

Extension points allow logic customization, yet every extension must preserve core protocol invariants:

- client authentication is verified before processing grants requiring client authentication;
- redirect URIs match registered URIs exactly;
- scopes never exceed client permissions, user consent, or policy;
- authorization codes and custom grant credentials enforce replay protection;
- tokens carry valid issuer, audience, lifetime, subject, and claims;
- revocation/introspection observe persisted token state;
- success/error responses conform to OAuth2/OIDC standards.

### 11.2. Never Delete Defaults Without Intentional Replacement

`authenticationProviders(...)` and `...Converters(...)` lists contain multiple default components. When calling `clear()` or removing entries, document the reason explicitly and test all affected grants/flows. Removing a converter/provider can break Authorization Code, Refresh Token, Client Credentials, Device Code, or Token Exchange.

### 11.3. Controlling Inputs and Secrets

- Limit request sizes and parameter counts.
- Reject duplicate parameters wherever the protocol expects a single value.
- Never log raw authorization codes, refresh tokens, access tokens, or client secrets.
- Never trust an additional parameter merely because the converter placed it in a map.
- Validate tenant/client bindings inside the provider.
- Use transactions or atomic consumption for one-time credentials.
- Bound processing time and external service calls inside providers.

### 11.4. Observability and Auditing

Record:

- endpoint and extension name;
- request correlation ID;
- authenticated client ID;
- grant type and outcome category;
- validation failure category;
- provider/token generator/persistence latency;
- application and extension version.

Never log token values, authorization codes, raw consent details, or unnecessary PII. Keep metric labels low-cardinality; never put user IDs or tokens into metric labels.

### 11.5. Versioning and Deployment

Extensions must roll out in sync with your Spring Authorization Server version. In a cluster:

- all nodes must run the same converter/provider and grant policy;
- client registrations must be synchronized before enabling a grant;
- database schemas and authorization services must be compatible;
- rolling deployments must support reading state written by the prior version;
- if changing a grant type URI or request contract, version the contract and provide a transition window.

Never treat internal implementation classes or `protected` methods as public SPIs. Use documented configurer APIs, public interfaces, and public contexts; verify Javadoc during upgrades.

## 12. Production Checklist and Reference Documentation

### 12.1. Pre-Release Extension Checklist

- [ ] Identified the endpoint and narrowest suitable extension point.
- [ ] Extension uses public APIs of the exact Spring Authorization Server version.
- [ ] `AuthenticationConverter` accepts only its target request type and returns `null` for others.
- [ ] Converter validates required parameters, duplicate parameters, and input sizes.
- [ ] `AuthenticationProvider.supports()` accepts only the exact `Authentication` type.
- [ ] Provider validates client, grant, scopes, expiry, audience, and replay.
- [ ] Custom validators preserve default validators not intentionally replaced.
- [ ] Success handler preserves schema, status, and cache/security headers.
- [ ] Error handler exposes no stack traces, secrets, or internal details.
- [ ] Custom grants are declared on the right `RegisteredClient` records.
- [ ] Token generator and authorization service follow the standard lifecycle.
- [ ] Unit tests exist for converter/provider and integration tests for endpoints.
- [ ] Regression tests cover standard grants/endpoints.
- [ ] Cluster/version compatibility tests are in place.
- [ ] Metrics, auditing, and correlation IDs are configured.
- [ ] No credentials or unnecessary PII are logged.

### Memory Map

```text
OAuth2AuthorizationServerConfigurer
        |
        +--> Endpoint Configurer
                 |
                 v
             Endpoint Filter
                 |
                 v
          AuthenticationConverter
                 |
                 v
          Authentication Token
                 |
                 v
          AuthenticationProvider
                 |
          +------+------+
          |             |
          v             v
     Authorization   TokenGenerator
        Service          |
          |              v
          +--------> Authentication result
                          |
                   +------+------+
                   |             |
                   v             v
              SuccessHandler  ErrorHandler
                   |             |
                   v             v
              Protocol response
```

**Key points to remember:** Spring Authorization Server lets you customize endpoints through public configurers. Converters turn HTTP requests into `Authentication` objects; providers verify and execute business logic; success/error handlers render protocol responses. Custom grants require a converter, provider, and client-registered grant type. For validation, retain default checks you do not intend to change. For UserInfo, prefer `userInfoMapper` when only modifying claims. Every extension must uphold protocol invariants, have regression tests, and deploy consistently across instances.

## Official Reference Documentation

- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): extension points for Authorization, PAR, Device, Token, Introspection, Revocation, OIDC UserInfo, and Client Registration endpoints.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): `OAuth2AuthorizationServerConfigurer`, shared components, and `SecurityFilterChain` configuration.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationEndpointConfigurer.html): converters/providers/handlers and consent page.
- [Spring Authorization Server 1.5.8 — OAuth2TokenEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenEndpointConfigurer.html): access token request converters, providers, and response handlers.
- [Spring Authorization Server 1.5.8 — OAuth2ClientAuthenticationConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2ClientAuthenticationConfigurer.html): client credential converters, providers, and handlers.
- [Spring Authorization Server 1.5.8 — How-to: Implement an Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html): custom grant `AuthenticationConverter`, `AuthenticationProvider`, and Token Endpoint.
- [Spring Authorization Server 1.5.8 — How-to: Customize the OpenID Connect 1.0 UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): custom `userInfoMapper` and claims from authorization context.
- [Spring Authorization Server 1.5.8 — OidcUserInfoEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OidcUserInfoEndpointConfigurer.html): request converter, provider, mapper, and handlers.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): authorization grants, token endpoint, error responses, and extension grants.
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591.html): reference when extensions interact with dynamic client registration.
