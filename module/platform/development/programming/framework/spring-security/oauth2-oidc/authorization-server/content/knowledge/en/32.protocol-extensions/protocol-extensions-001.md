# Evaluating Custom Grant Needs and Protocol Impact

## 1. Context: Not Every Token Issuance Requirement Needs a New Grant

OAuth 2.0 defines an authorization grant as a credential representing the authorization granted by the Resource Owner or client policy, which the client uses to request an access token. Beyond the core grant types, RFC 6749 allows extensions through **extension authorization grants**.

In a Spring Security and Spring Authorization Server system, new requirements often arise when a client must exchange a specific type of assertion, transaction code, device proof, or internal system credential for an access token. A quick implementation might be adding a custom handling branch to the Token Endpoint. However, without properly identifying the nature of the requirement, an extension can create a grant that duplicates an existing standard, reduces interoperability, and expands the attack surface.

This lesson belongs to the **Protocol Extensions** chapter and focuses on evaluating when to define a custom grant, when standard grants or extensions suffice, and the impact on clients, the Authorization Server, the Resource Server, metadata, security, and operations.

The Spring examples use Spring Authorization Server 1.5.x APIs. When applying them to another version, verify the corresponding APIs.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish between authorization grant, grant type, client authentication, and scope.
2. Determine whether a requirement genuinely needs a new grant type.
3. Choose standard grants or extensions such as Authorization Code, Client Credentials, Device Authorization, JWT Bearer, Token Exchange, RAR, PAR, and Resource Indicators.
4. Understand the unique URI format of an extension grant under RFC 6749.
5. Evaluate impacts on interoperability and metadata.
6. Design contracts for requests, responses, errors, and the grant lifecycle.
7. Analyze replay, token substitution, over-privilege, and confused deputy risks.
8. Implement extension points using AuthenticationConverter and AuthenticationProvider.
9. Register a grant type for RegisteredClient and wire it into the Token Endpoint.
10. Test and operate extensions according to current OAuth 2.0 security requirements.

## 2. Distinguishing Concepts Before Designing

The following concepts are related but cannot be used interchangeably:

| Concept | Question It Answers | Examples |
|---|---|---|
| Authorization grant | What credential or proof authorizes requesting a token? | Authorization code, device code, JWT assertion |
| Grant type | What flow must the Token Endpoint use to process the grant? | authorization_code, client_credentials, token-exchange |
| Client authentication | Which client is calling the Token Endpoint? | client_secret_basic, private_key_jwt, mTLS |
| Scope | Which permissions is the client requesting? | orders.read, orders.write |
| Resource indicator | At which resource is the access token intended to be used? | https://api.example.com/orders |
| Authorization details | What fine-grained permissions are requested or granted? | Read balance, initiate payment |
| Token format/claims | What information does the access token carry and in what format? | JWT, opaque token, aud, scope |

### 2.1. Grant Type Is Not Client Authentication

Client authentication proves the identity of the application calling the Token Endpoint. Grant type describes how the Authorization Server evaluates the basis for issuing a token.

A client that successfully authenticates using mTLS or private_key_jwt must still prove a valid grant. Conversely, a valid assertion does not inherently prove that the client making the request is authorized to use that assertion.

### 2.2. Grant Type Is Not Scope

Scope describes the requested permissions, not how the client obtains those permissions.

For example, adding the `orders.export` scope does not require a new grant type if the client still uses Authorization Code or Client Credentials and only needs to request additional permissions under policy. Similarly, changing the scope list does not turn a request into a new grant type.

### 2.3. An OAuth Grant Is Not an Application Login Mechanism

OAuth 2.0 primarily grants access to protected resources. If the goal is to authenticate users and convey identity to an application, use OpenID Connect. Do not create a custom grant to replace an authentication protocol or pass user passwords through a client.

## 3. Process for Evaluating Custom Grant Needs

Before writing code, describe the requirement using these questions:

1. Who is requesting the token: a user, a server-side application, a device, or a workload?
2. What is the authorization proof: user consent, client identity, an assertion, a device code, or another token?
3. Who issues that proof and how is it verified?
4. Can the proof be used once or multiple times? Does it have an expiration?
5. Whom should the token represent, which client is acting, and which resource is it intended for?
6. Are permissions determined by scope, authorization details, or server-side policy?
7. Which standard grant already solves the same scenario?
8. Do the Client and Resource Server need to understand a custom protocol, or just receive a standard access token?

Consider a custom grant only when the requirement has **distinct authorization semantics** and cannot be safely modeled with existing grants/extensions. A new parameter, a new claim, or a new client authentication method is usually not enough reason to create a grant type.

## 4. Selection Map: Standard Grants and Extensions

Before defining a new grant, compare against the following options:

| Need | Standard Option to Evaluate | Why a Custom Grant May Not Be Needed |
|---|---|---|
| Web/mobile app needs user-granted permissions | Authorization Code + PKCE | Authorization Server already handles user flow and consent |
| Service calling APIs using its own identity | Client Credentials | Client authentication and policy can determine permissions |
| Device without a browser or with constrained input | Device Authorization Grant (RFC 8628) | Device code, user code, and polling protocol already exist |
| Exchanging a JWT assertion for an access token | JWT Bearer Grant (RFC 7523) | Assertion verification profile and token request rules already exist |
| Exchanging a token for delegation or impersonation | Token Exchange (RFC 8693) | Subject token, actor token, and delegation semantics already exist |
| Fine-grained permissions beyond string scopes | Rich Authorization Requests (RFC 9396) | Uses authorization_details to describe permissions |
| Specifying target API/resource | Resource Indicators (RFC 8707) | Uses resource to restrict where the access token is used |
| Sending authorization requests directly to the OP | Pushed Authorization Requests (RFC 9126) | Changes request delivery without needing a new grant |
| Authenticating clients with asymmetric keys | private_key_jwt or mTLS | This is a client authentication method |
| Preventing replay of stolen tokens | DPoP or mTLS sender-constrained tokens | This is a mechanism to bind tokens to the sender |
| Adding data to the access token | OAuth2TokenCustomizer or token claims policy | Does not change how the client obtains the token |

### 4.1. Authorization Code + PKCE

When a user interacts and grants permissions to an application, Authorization Code with PKCE is usually the appropriate choice. The client receives an authorization code via redirect and exchanges the code at the Token Endpoint.

Do not create a custom grant just to bypass the login page, consent, or PKCE. If the requirement needs a different authentication experience, consider OIDC or an appropriate authentication flow.

### 4.2. Client Credentials

When a workload calls APIs using its own authority, Client Credentials is usually appropriate. Permissions can be determined by RegisteredClient, allowed scopes, resources, and operational policies.

Do not create a separate grant just because a client needs an extra parameter identifying the environment, tenant, or job type if that parameter can be safely handled through policy and token customization.

### 4.3. Device Authorization Grant

RFC 8628 is designed for Internet-connected devices that lack a suitable browser or have input constraints. The device requests a device code, displays a user code and URI, and the user completes authentication on a secondary device.

If the requirement is essentially "a TV device needs a user to log in via phone," use the Device Authorization Grant or a compatible implementation. Designing a custom device code/polling grant creates a second protocol that is hard to interoperate with.

### 4.4. JWT Bearer Grant

RFC 7523 defines a JWT Bearer assertion that can be used as an authorization grant to request an access token. If the system already issues JWT assertions with verifiable issuer, audience, expiration, and signature, evaluate this standard profile before designing a custom grant.

Note: JWT Bearer Grant and private_key_jwt are two different uses of JWT. JWT Bearer Grant uses an assertion as an authorization grant; private_key_jwt uses a JWT to authenticate the client at the Token Endpoint.

### 4.5. Token Exchange

RFC 8693 defines Token Exchange for Security Token Service scenarios, including delegation and impersonation. The client sends a subject token and optionally an actor token, while specifying token type, resource, or scope according to the contract.

If service A needs a token to call service B on behalf of a user, evaluate Token Exchange before designing a custom "service delegation" grant. Clearly distinguish impersonation from delegation because the two models carry different responsibilities and audit trails.

### 4.6. RAR, Resource Indicators, and PAR Are Not Grant Types

- **RAR** adds `authorization_details` to describe fine-grained permissions; it does not define an entirely new way to exchange credentials for a token.
- **Resource Indicators** uses the `resource` parameter to specify the target resource server.
- **PAR** sends the authorization request to a dedicated endpoint via POST, after which the browser uses `request_uri` to continue the authorization flow.

These extensions can address most requirements that initially appear to need a custom grant. They extend the payload or transport of requests within existing protocols.

## 5. When Is a Custom Grant Justified?

A custom grant can be appropriate when all of the following conditions are clearly established:

- There is a distinct authorization credential type or verification process.
- That credential has independent authorization semantics, not just a scope or claim.
- No standard grant/extension fits, or using a standard would distort the semantics.
- The Client and Authorization Server can coordinate to implement the new protocol.
- The grant's issuer, audience, subject, client binding, and lifetime can be clearly defined.
- Replay protection, revocation, and auditing rules are in place.
- The Resource Server understands exactly what permissions the issued token represents.
- Protocol documentation, versioning, and a compatibility plan exist.

Example: a platform has a device service that issues signed assertions bound to a registered device, a specific client, a resource, and a very short-lived task. The Authorization Server must verify the assertion, check that the device has not been revoked, consume the proof once, and issue a task-scoped access token. If this assertion profile is incompatible with JWT Bearer Grant or another standard, a dedicated extension grant may be justified.

This is an architectural example. It does not mean every internal assertion warrants a new grant.

## 6. When Should You NOT Create a Custom Grant?

| Requirement | Approach to Evaluate |
|---|---|
| Adding a new scope or permission | Configure scopes and policies |
| Adding a claim to a JWT access token | OAuth2TokenCustomizer and claim policy |
| Authenticating a client with a certificate | mTLS client authentication |
| Authenticating a client with a signed JWT | private_key_jwt |
| Selecting a target resource | RFC 8707 Resource Indicators |
| Sending an authorization request with a large payload | RFC 9126 PAR |
| Transaction-level fine-grained permissions | RFC 9396 RAR |
| Exchanging an access token to call another service | RFC 8693 Token Exchange |
| Input-constrained devices | RFC 8628 Device Authorization |
| Using user passwords to request tokens | Do not design a Resource Owner Password Credentials-style grant |

RFC 9700, OAuth 2.0 Security Best Current Practice, specifies that the Resource Owner Password Credentials Grant **MUST NOT** be used. Do not create a custom grant that merely renames the password grant or passes username/password through a custom parameter. That approach still exposes user credentials to the client and fails to resolve the underlying risk.

## 7. Evaluating Protocol Impact

A custom grant alters the contract at the Token Endpoint. The impact extends beyond the Authorization Server.

| Component | Changes to Evaluate |
|---|---|
| Client | Understands grant_type, parameters, credentials, error, and retry semantics |
| Authorization Server | Parses request, authenticates client, validates grant, issues token, and persists authorization |
| RegisteredClient | Permits the appropriate clients to use the new grant |
| Resource Server | Understands token audience, subject, actor, scope, and claims |
| Authorization metadata | Publishes the grant type if the server supports metadata |
| SDK/API gateway | May need allowlist, parser, and observability updates |
| Audit/operations | Tracks grant issuance, rejections, replays, revocations, and abuse |
| Integrating organizations | Needs documentation, versioning, conformance tests, and a change process |

### 7.1. Compatibility with Standard Clients

A generic OAuth client can send a POST to the Token Endpoint and process a standard token response. However, it does not automatically know how to construct custom credentials or custom grant parameters.

Therefore, having the Token Endpoint still return `access_token`/`token_type`/`expires_in` per OAuth does not make the entire custom grant interoperable. Clients must implement the extension contract properly.

### 7.2. Resource Servers Are Also Affected

If a custom grant issues tokens with new semantics, the Resource Server must know how to evaluate those tokens. For example, a token representing both a device and a user simultaneously needs clear rules regarding subject, actor, and audience.

Do not simply add an arbitrary claim and assume APIs will interpret it automatically. You must define claims, permissions, resources, and how the Resource Server verifies them.

### 7.3. Metadata and Discovery

RFC 8414 defines Authorization Server metadata, where the optional `grant_types_supported` field lists the grant types supported by the server.

If the server publishes metadata, ensure the list accurately reflects the new grant. Do not advertise a grant that the server has not enabled or finished validating. Also verify whether Spring Authorization Server's metadata is customized to publish the extension; do not assume adding a provider automatically updates metadata.

## 8. Grant Type Identifiers and Parameter Extension Rules

RFC 6749 `4.5` requires clients to specify an extension grant using an absolute URI in the Token Endpoint's `grant_type` parameter.

RFC 6749 `8.3` also requires each new grant type to have a unique absolute URI. If the extension requires additional token endpoint request parameters, those parameters must be registered in the OAuth Parameters registry under `8.2` and `11.2`.

Example of an organization-owned URI:

~~~text
https://auth.example.com/grants/device-attestation
~~~

This is an illustrative URI using a documentation-reserved domain. In production systems, choose a namespace under your organization's control and keep it stable across versions.

### 8.1. Do Not Use Short, Collision-Prone Names

Do not name a new grant type `device`, `assertion`, or `custom`. Short names can collide with extensions from other vendors or cause clients to misinterpret semantics.

A URI clearly identifies the extension and the entity responsible for the specification.

### 8.2. Defining the Parameter Contract

For each additional parameter, specify:

- Name, data type, and encoding.
- Required or optional.
- Whether repetition is allowed.
- Size limits.
- Expiration and verification method.
- Relationship with `client_id`, grant type, scope, and resource.
- Corresponding error code.
- Handling of unsupported parameters.

For example, the `assertion` parameter might require exactly one value. If a client sends two assertions, the server must reject the request rather than silently picking the first value.

### 8.3. Error Contract

Prefer existing OAuth error codes:

| Error | Typical Meaning |
|---|---|
| `invalid_request` | Missing required parameter, duplicate parameter, or malformed request |
| `invalid_client` | Client authentication failed |
| `unauthorized_client` | Client is not authorized to use the grant type |
| `unsupported_grant_type` | Server does not support the requested grant type |
| `invalid_grant` | Assertion/code/credential is invalid, expired, already used, or mismatched |
| `invalid_scope` | Requested scope is not permitted |
| `server_error` | Internal error while issuing token or saving authorization |

If a dedicated error code is needed for a registered extension, follow the extension error rules in RFC 6749 `8.5`. Do not return details about keys, tokens, users, or internal reasons that could help an attacker probe the system.

## 9. Designing the Protocol Contract Before Writing Code

A custom grant specification should at minimum cover these sections:

1. **Purpose:** the token issuance scenario being solved.
2. **Grant type URI:** unique identifier.
3. **Client authentication:** authentication methods clients are allowed to use.
4. **Request parameters:** names, types, cardinality, encoding, and limits.
5. **Grant validation:** issuer, audience, signature, time, subject, client binding.
6. **Authorization policy:** scope, resource, tenant, consent, and permissions.
7. **Token issuance:** token type, TTL, audience, claims, refresh policy.
8. **Persistence:** authorization ID, grant type, subject, token metadata, and status.
9. **Errors:** error codes, HTTP status, and non-disclosure rules.
10. **Replay/revocation:** one-time use, jti, nonce, revocation, and retries.
11. **Metadata:** `grant_types_supported` and client documentation.
12. **Versioning:** how requests are upgraded and older clients handled.

Do not start from an `AuthenticationProvider` and let semantics emerge ad hoc in code. The contract should be reviewed beforehand by the owners of the client, Authorization Server, and Resource Server.

## 10. Security Boundaries of a Custom Grant

A custom grant typically receives a credential submitted by the client. The credential may be a signed assertion, a one-time code, a device proof, or a token from another system. Each type carries distinct risks.

### 10.1. Client Authentication Independent of Grant Verification

Perform both steps:

1. Authenticate the client according to its registered method.
2. Verify the authorization grant and bind it to the authenticated client.

Do not issue a token solely because an assertion has a valid signature. The assertion might have been issued for a different client, resource, or environment.

### 10.2. Assertion/JWT Validation

If the grant carries a JWT or signed assertion, verify at minimum:

- Signature using a key belonging to a trusted issuer.
- Algorithm is in an allowlist.
- `iss` matches a configured issuer.
- `aud` matches the Authorization Server or recipient per the profile.
- `exp` has not expired and `nbf` is already active.
- `iat` falls within a reasonable time window.
- `jti` or nonce is checked for replay when required by the profile.
- Subject, actor, tenant, and client binding comply with policy.

Do not merely decode a JWT and trust its payload. Do not accept arbitrary keys or issuers from the assertion itself without prior trust configuration.

### 10.3. Replay Protection and One-Time Use

If the grant is a one-time code:

- Generate an unpredictable value with sufficient entropy.
- Store a hash of the code if possible.
- Bind the code to the client, subject, resource, and scope.
- Enforce a short expiration.
- Consume the code atomically so two concurrent requests cannot both succeed.
- Log replay attempts without logging the raw code.

Checking "has it been used" and then marking it used in two separate database operations can create a race condition. Use transactions, compare-and-set, or an appropriate unique constraint.

### 10.4. Restricting Access Token Permissions

RFC 9700 recommends access tokens carry minimal privileges and an audience restricted to a single Resource Server or a small group of resources. A new grant must not become a bypass to issue broader tokens than existing policy allows.

Clearly define:

- Whom the token represents.
- Which client is acting.
- Which resources are permitted to accept the token.
- Which scopes/authorization details are granted.
- How long the token lives.
- Whether a refresh token is needed.

### 10.5. Sender-Constrained Tokens

When the risk of token theft is high, consider sender-constrained tokens using mTLS or DPoP. RFC 9700 recommends Authorization Servers and Resource Servers use these mechanisms to mitigate access token replay.

This is a protection layer for the token after issuance. It does not replace verifying the custom grant prior to token issuance.

## 11. Lifecycle of a Custom Grant

A typical flow:

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Spring Authorization Server
    participant V as Grant Verifier
    participant DB as Authorization Store
    participant RS as Resource Server

    C->>AS: POST /oauth2/token + client authentication + custom grant
    AS->>AS: Authenticate client
    AS->>AS: AuthenticationConverter parses request
    AS->>AS: Check RegisteredClient allows grant
    AS->>V: Verify grant credential and policy
    V->>V: Validate signature, time, audience and replay
    V-->>AS: Verified subject, client binding, resource and scopes
    AS->>AS: Build OAuth2TokenContext
    AS->>AS: OAuth2TokenGenerator creates access token
    AS->>DB: Save OAuth2Authorization
    DB-->>AS: Authorization persisted
    AS-->>C: Standard OAuth token response
    C->>RS: API request with access token
    RS->>RS: Validate token, audience and authorization
~~~

Required steps:

1. The Token Endpoint receives the request.
2. The client authentication filter authenticates the application.
3. The converter recognizes the grant type and parses the request.
4. The provider checks that the client is allowed to use the grant.
5. The provider verifies the credential and authorization policy.
6. The token context is created with the grant type, principal, scope, and resource.
7. The token generator issues the access token.
8. The authorization is persisted to support lookup, revocation, introspection, or audit per the architecture.
9. The token response follows the OAuth response contract.

## 12. Spring Authorization Server: Extension Points

Spring Authorization Server provides extension points for custom authorization grants at the OAuth2 Token Endpoint. Per the 1.5.8 guide, three parts are required:

- **AuthenticationConverter:** recognizes the grant type and converts the HTTP request into an Authentication object.
- **AuthenticationProvider:** verifies the grant, checks client/policy, and issues the token.
- **Token Endpoint configuration:** registers the converter/provider for the endpoint to use.

Additionally, you must register the grant type in `RegisteredClient` and use the application's `OAuth2TokenGenerator` and `OAuth2AuthorizationService`.

### 12.1. AuthenticationConverter

The converter only handles the grant type it owns. If the request belongs to another grant, return `null` so the next converter in the chain can process it.

The converter should not issue tokens or perform authorization logic. Its job is to parse and validate request structure:

- Is the `grant_type` correct?
- Are all required parameters present?
- Are any parameters duplicated outside the contract?
- Are types/lengths valid?
- Who is the current client principal?

### 12.2. AuthenticationProvider

The provider is responsible for verifying the credential and deciding whether a token may be issued. The provider must:

- Retrieve the authenticated client principal.
- Verify the grant type is in the RegisteredClient's allowed list.
- Verify the authorization grant.
- Determine the subject/actor, resource, and authorized scopes.
- Build the `OAuth2TokenContext`.
- Invoke `OAuth2TokenGenerator`.
- Build and save `OAuth2Authorization`.
- Return `OAuth2AccessTokenAuthenticationToken` or an appropriate OAuth2 error.

Do not place critical assertion verification logic inside the converter and assume every request is already verified simply because the converter built an Authentication object.

## 13. Defining AuthorizationGrantType and Authentication Token

Example illustrating a grant accepting a signed device attestation:

~~~java
public final class DeviceAttestationGrant {

    public static final AuthorizationGrantType GRANT_TYPE =
        new AuthorizationGrantType(
            "https://auth.example.com/grants/device-attestation");

    public static final String ASSERTION_PARAMETER = "assertion";

    private DeviceAttestationGrant() {
    }
}
~~~

Authentication token holding the assertion and client principal:

~~~java
public final class DeviceAttestationGrantAuthenticationToken
        extends OAuth2AuthorizationGrantAuthenticationToken {

    private final String assertion;

    public DeviceAttestationGrantAuthenticationToken(
            Authentication clientPrincipal, String assertion) {

        super(DeviceAttestationGrant.GRANT_TYPE,
            clientPrincipal, Collections.emptyMap());

        this.assertion = assertion;
    }

    public String getAssertion() {
        return this.assertion;
    }
}
~~~

This is an illustrative skeleton for a custom grant. In a real application, it may retain additional parsed parameters while avoiding storing unnecessary raw secrets in objects or logs.

## 14. Writing the AuthenticationConverter

The converter matches the expected grant type, checks that `assertion` appears exactly once, and creates the Authentication token:

~~~java
public final class DeviceAttestationGrantAuthenticationConverter
        implements AuthenticationConverter {

    @Override
    public Authentication convert(HttpServletRequest request) {
        String grantType =
            request.getParameter(OAuth2ParameterNames.GRANT_TYPE);

        if (!DeviceAttestationGrant.GRANT_TYPE.getValue()
                .equals(grantType)) {
            return null;
        }

        String[] assertions =
            request.getParameterValues(
                DeviceAttestationGrant.ASSERTION_PARAMETER);

        if (assertions == null
                || assertions.length != 1
                || !StringUtils.hasText(assertions[0])) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_REQUEST);
        }

        Authentication clientPrincipal =
            SecurityContextHolder.getContext().getAuthentication();

        return new DeviceAttestationGrantAuthenticationToken(
            clientPrincipal, assertions[0]);
    }
}
~~~

This snippet focuses on converter structure. Production also requires request size limits, content type validation, a parameter allowlist, and controls on request logging. If the grant has additional parameters, define cardinality and validation for each field.

## 15. Writing the AuthenticationProvider and Issuing Tokens

The provider should delegate credential verification to a service with a dedicated contract. For example:

~~~java
VerifiedDeviceGrant verifiedGrant =
    deviceAttestationVerifier.verifyAndConsume(
        grantAuthentication.getAssertion(),
        registeredClient,
        authorizationServerIssuer);
~~~

That service must verify signature/issuer/audience/timestamps, bind the assertion to the client and resource, and atomically consume the grant if it is single-use.

The service contract should return verified data, not merely a boolean:

~~~java
public interface DeviceAttestationVerifier {

    VerifiedDeviceGrant verifyAndConsume(
            String assertion,
            RegisteredClient registeredClient,
            String authorizationServerIssuer);
}

public record VerifiedDeviceGrant(
        String subject,
        String resource,
        Set<String> allowedScopes) {
}
~~~

These are illustrative data types. The assertion must be validated before constructing this object; never take subject, resource, or scope directly from an unverified request.

After verification, the provider determines the allowed scopes and builds the token context:

~~~java
OAuth2TokenContext tokenContext =
    DefaultOAuth2TokenContext.builder()
        .registeredClient(registeredClient)
        .principal(clientPrincipal)
        .authorizationServerContext(
            AuthorizationServerContextHolder.getContext())
        .tokenType(OAuth2TokenType.ACCESS_TOKEN)
        .authorizedScopes(authorizedScopes)
        .authorizationGrantType(
            DeviceAttestationGrant.GRANT_TYPE)
        .authorizationGrant(grantAuthentication)
        .build();

OAuth2Token generatedToken =
    tokenGenerator.generate(tokenContext);

if (generatedToken == null) {
    throw new OAuth2AuthenticationException(
        new OAuth2Error(
            OAuth2ErrorCodes.SERVER_ERROR,
            "The token generator failed to generate an access token.",
            null));
}
~~~

The provider then creates the access token and persists the authorization:

~~~java
OAuth2AccessToken accessToken = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    generatedToken.getTokenValue(),
    generatedToken.getIssuedAt(),
    generatedToken.getExpiresAt(),
    authorizedScopes);

OAuth2Authorization.Builder authorizationBuilder =
    OAuth2Authorization.withRegisteredClient(registeredClient)
        .principalName(verifiedGrant.subject())
        .authorizationGrantType(
            DeviceAttestationGrant.GRANT_TYPE)
        .authorizedScopes(authorizedScopes);

if (generatedToken instanceof ClaimAccessor claimAccessor) {
    authorizationBuilder.token(accessToken, metadata ->
            metadata.put(
                OAuth2Authorization.Token.CLAIMS_METADATA_NAME,
                claimAccessor.getClaims()));
} else {
    authorizationBuilder.accessToken(accessToken);
}

OAuth2Authorization authorization = authorizationBuilder.build();
authorizationService.save(authorization);

return new OAuth2AccessTokenAuthenticationToken(
    registeredClient, clientPrincipal, accessToken);
~~~

In this example, the client principal in the token context identifies the authenticated application; the subject obtained from the verified assertion is stored separately in the authorization. If the grant represents the client without a separate End-User or device subject, use the client identity as the principal per the grant semantics. When issuing a JWT, ensure the `sub` claim accurately reflects the grant's subject; because the token context in the example uses the client principal, the token customizer must retrieve the subject from the verified grant instead of defaulting to the client name. Never take the `sub` claim directly from an unverified assertion. When the generated token is a JWT, also store claims metadata so persistence components can read the claims back.

Do not issue a refresh token by default merely because the token generator supports refresh tokens. If issuing refresh tokens to public clients, RFC 9700 requires sender-constraining or rotation; for confidential clients, refresh tokens must still be bound to the issued client.

## 16. Registering the Grant Type for RegisteredClient

The Authorization Server should only allow explicitly configured clients to use the custom grant.

~~~java
RegisteredClient deviceClient = RegisteredClient
    .withId(UUID.randomUUID().toString())
    .clientId("device-agent")
    .clientSecret(passwordEncoder.encode(secretFromSecretManager))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        DeviceAttestationGrant.GRANT_TYPE)
    .scope("device.status")
    .scope("device.command")
    .build();
~~~

This is a confidential client example. Production requires storing secrets in a secret manager and using a persistent repository. Clients may only request scopes within the configured policy and the assertion's permissions.

Do not add the custom grant to every RegisteredClient just to avoid configuration errors. The grant type allowlist is an important control layer.

## 17. Wiring Converter and Provider into the Token Endpoint

Spring Authorization Server 1.5.x configuration example:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        OAuth2AuthorizationService authorizationService,
        OAuth2TokenGenerator<?> tokenGenerator,
        DeviceAttestationVerifier verifier) throws Exception {

    OAuth2AuthorizationServerConfigurer configurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    DeviceAttestationGrantAuthenticationConverter converter =
        new DeviceAttestationGrantAuthenticationConverter();

    DeviceAttestationGrantAuthenticationProvider provider =
        new DeviceAttestationGrantAuthenticationProvider(
            authorizationService, tokenGenerator, verifier);

    http
        .securityMatcher(configurer.getEndpointsMatcher())
        .with(configurer, authorizationServer ->
            authorizationServer.tokenEndpoint(tokenEndpoint ->
                tokenEndpoint
                    .accessTokenRequestConverter(converter)
                    .authenticationProvider(provider)
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        );

    return http.build();
}
~~~

Provider constructor names and dependencies depend on the application implementation. The illustrative configuration shows two integration points: the converter parses requests, and the provider handles the grant. Do not replace the entire Token Endpoint or remove the client authentication filter.

## 18. Client Calling the Token Endpoint

Sample request using HTTP Basic client authentication:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_DEVICE_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=https%3A%2F%2Fauth.example.com%2Fgrants%2Fdevice-attestation&assertion=SIGNED_DEVICE_ASSERTION&scope=device.status
~~~

If the client uses `private_key_jwt` or mTLS, the client authentication portion changes according to its registration. The assertion in the body is the authorization grant in this example; it does not replace client authentication.

The response still uses the standard OAuth token response structure:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "device.status"
}
~~~

Clients and Resource Servers should not have to learn a proprietary response envelope if the extension only changes grant verification. Keeping a standard response lets you leverage existing OAuth client libraries and middleware.

## 19. Impact on Tokens, Scopes, and Resource Servers

A custom grant establishes the basis for issuing a token; it does not automatically dictate that the token must carry all information from the grant.

Clearly define:

- Whether the token subject is a user, device, or workload.
- Which client is performing the action.
- Whether actor/delegation semantics exist.
- Target audience/resource.
- Granted scopes or authorization details.
- Token TTL and sender constraint.
- Which claims the Resource Server verifies.

If a token carries a device subject but the Resource Server interprets the subject as a user ID, authorization errors can occur. Claims need clear semantics, issuer, and audience; avoid repurposing standard claims for different meanings.

### 19.1. Restricting Scope by Grant

Do not trust scopes sent by the client. The provider must ensure requested scopes are a subset of permissions allowed by the client, grant, and policy. If the assertion only permits `device.status`, the client cannot add `device.command` by altering the request parameter.

### 19.2. Audience and Resource

The access token must be intended for the right Resource Server. If the client can specify a resource, the Authorization Server needs a resource allowlist and must verify that the assertion authorizes issuing a token for that resource.

The Resource Server must verify the audience and permissions on every request; verifying only the JWT signature is insufficient.

## 20. Metadata, Versioning, and Client Compatibility

If the Authorization Server publishes RFC 8414 metadata, it can list the custom grant in `grant_types_supported`. This metadata is optional but useful for client discovery.

In addition to metadata, publish client documentation:

- Grant type URI.
- Token endpoint and client authentication methods.
- Request parameters and examples.
- Valid scopes/resources.
- Error responses and retry policy.
- Token claims and audience.
- Version, deprecation date, and migration window.

When changing assertion or parameter semantics, do not silently cause older clients to misinterpret them. You can create a new versioned grant URI or define a version field with clear compatibility rules. Do not alter an existing grant type URI to carry different semantics.

## 21. Testing a Custom Grant

### 21.1. Request Parsing Tests

| Test Case | Expected Result |
|---|---|
| `grant_type` does not belong to custom grant | Converter returns null |
| Matching `grant_type` and structurally valid assertion | Creates Authentication token |
| Missing assertion | `invalid_request` |
| Empty assertion | `invalid_request` |
| Duplicate assertions | `invalid_request` |
| Request has unsupported parameters | Rejected per contract |
| Assertion exceeds size limit | Rejected before verification |

### 21.2. Client and Grant Policy Tests

- Client authentication fails.
- Client has not registered the custom grant.
- Client is disabled or registration has expired.
- Assertion was issued for a different client.
- Assertion has wrong issuer or audience.
- Assertion is expired or not yet active.
- Assertion has been revoked or already used.
- Assertion is signed with an untrusted algorithm/key.
- Requested scope exceeds grant permissions.
- Target resource is not permitted.

### 21.3. Token Issuance and Persistence Tests

- Token generator returns a valid token.
- Token generator fails to generate a token.
- `OAuth2Authorization` is saved with the correct grant type.
- Authorized scopes and principal are accurate.
- JWT claims contain issuer, audience, subject, and actor per contract.
- Token response has standard OAuth structure.
- Resource Server accepts valid tokens and rejects tokens with wrong audience.
- Authorization service can look up/revoke tokens per policy.

### 21.4. Concurrency and Replay Tests

Send two concurrent requests using the same one-time assertion. Only one request may successfully consume the grant. The other request must receive `invalid_grant`.

This test must run against a real persistence implementation or a test double that accurately simulates transaction/atomic consume semantics; merely mocking the verifier to always return true does not verify replay protection.

## 22. Common Design Mistakes

| Mistake | Consequence | Mitigation |
|---|---|---|
| Creating a custom grant for a new scope | Unnecessary protocol complexity | Use scopes and policy |
| Using a new grant to replace client authentication | Client identity and grant get conflated | Separate the two verification steps |
| Using short or non-unique grant names | Collisions with other extensions | Use a unique absolute URI |
| Not checking RegisteredClient grant allowlist | Unauthorized clients can use the grant | Check grant type in provider |
| Verifying only the assertion signature | Assertion may have wrong audience/client or be replayed | Verify full claims and replay state |
| Accepting client-chosen scopes | Over-privilege | Compute authorized scopes from policy |
| Not restricting audience | Token may be used at the wrong Resource Server | Audience restriction |
| Non-atomic storage of one-time grants | Two concurrent requests both receive tokens | Atomic consume and concurrency tests |
| Issuing refresh tokens without policy | Credentials may outlive the grant | TTL, rotation, and sender constraint |
| Replacing standard token response with custom envelope | Poor compatibility with client libraries | Keep standard OAuth token response |
| Not publishing metadata/documentation | Clients cannot discover or integrate properly | Update metadata and contract |
| Using password grant or a renamed variant | Exposes passwords to clients | Authorization Code + PKCE or appropriate flow |
| Skipping OAuth2Authorization persistence | Hard to revoke, introspect, and audit | Persist authorization per policy |
| Not testing the Resource Server | Issued tokens may have wrong audience/claims | End-to-end authorization tests |

## 23. Observability and Operations

Monitor:

- Request counts by grant type and client ID.
- Grant verification successes and failures.
- `invalid_grant`, `unauthorized_client`, `invalid_scope`, and `server_error` errors.
- Expired assertions, bad issuer/audience, bad signature, and replays.
- Verifier and token generation processing latency.
- Token issuance by resource/scope.
- Authorization persistence failures.
- Share of clients using legacy contract versions.
- Unusual spikes in requests or invalid grants.

Do not log raw assertions, bearer tokens, client secrets, or private keys. Audit logs should include correlation ID, client ID, grant type URI, issuer, resource, outcome, and a pseudonymized fingerprint if needed for investigation.

### 23.1. Runbook When Custom Grants Are Mass-Rejected

1. Check client authentication and `RegisteredClient` status.
2. Confirm the client is still permitted to use the grant type.
3. Check assertion issuer, audience, clock skew, and key rotation.
4. Check whether assertions are expired or being replayed.
5. Check whether scope/resource policies have changed.
6. Check availability of the verifier and grant store.
7. Check the token generator and authorization persistence.
8. Verify metadata/client configurations match the same contract version.

Do not mitigate by disabling assertion verification, allowing all clients to use the grant, or issuing broader scopes.

## 24. Decision and Implementation Checklist

### Before Deciding on a Custom Grant

- [ ] Accurately identified the authorization credential and semantics of the requirement.
- [ ] Compared against Authorization Code, Client Credentials, Device, JWT Bearer, and Token Exchange.
- [ ] Evaluated RAR, Resource Indicators, PAR, and client authentication extensions.
- [ ] Not using a custom grant to replace OIDC login or password grant.
- [ ] Clear justification for why standard grants/extensions cannot meet the requirement.

### When Defining the Protocol

- [ ] Grant type uses a unique absolute URI.
- [ ] Parameter contract defines syntax, cardinality, size, and encoding.
- [ ] Error contract uses appropriate OAuth errors.
- [ ] Parameter/error extensions follow registration rules where required.
- [ ] Metadata `grant_types_supported` and client documentation are updated.
- [ ] Versioning and migration policy are defined.

### When Implementing Spring Authorization Server

- [ ] Dedicated `AuthenticationConverter` implemented.
- [ ] Dedicated `AuthenticationProvider` implemented.
- [ ] Provider authenticates the client and checks the `RegisteredClient` grant allowlist.
- [ ] Grant verifier checks credentials and replay protection.
- [ ] Authorized scopes/resources are computed according to policy.
- [ ] Token context uses the right grant type, principal, and token type.
- [ ] Tokens are generated using `OAuth2TokenGenerator`.
- [ ] `OAuth2Authorization` is properly persisted.
- [ ] Token response preserves the standard OAuth structure.

### Before Production

- [ ] Tests exist for parsing, invalid grant, wrong client, wrong audience, and replay.
- [ ] Concurrency tests exist for one-time grants.
- [ ] Resource Server verifies audience and permissions.
- [ ] Access tokens have minimal TTL and sender constraints where appropriate.
- [ ] Refresh tokens have dedicated policies and appropriate rotation/sender constraints.
- [ ] Logs/audits do not contain raw credentials.
- [ ] Metrics, alerts, runbooks, and deprecation plans are in place.

### Key Takeaways

A custom grant is an **extension of the access token issuance process**, not a way to rewrite client authentication, scopes, token claims, or user login. Before creating a new grant, review existing standards: Authorization Code + PKCE, Client Credentials, Device Authorization, JWT Bearer, Token Exchange, RAR, Resource Indicators, and PAR.

If a custom grant is genuinely necessary, RFC 6749 requires a unique absolute URI for the grant type; any additional token endpoint parameters must follow the corresponding registration rules. Clients must authenticate independently of the grant credential. The Authorization Server must verify issuer, audience, lifetime, client binding, replay protection, and permissions before issuing a token.

In Spring Authorization Server, implement this via **AuthenticationConverter**, **AuthenticationProvider**, and **Token Endpoint** configuration. The provider verifies the grant type is allowed by `RegisteredClient`, builds the token context, invokes `OAuth2TokenGenerator`, and persists `OAuth2Authorization`. Keep the token response standard, restrict audience/scopes, publish metadata, and test the Resource Server as well. A custom grant should only be implemented when authorization semantics are truly novel and can be maintained as a long-term protocol contract.

## References

- [RFC 6749 — The OAuth 2.0 Authorization Framework, Sections 4.5 and 8.2–8.5](https://www.rfc-editor.org/rfc/rfc6749.html)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html)
- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628.html)
- [RFC 7523 — JSON Web Token Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523.html)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html)
- [RFC 9396 — OAuth 2.0 Rich Authorization Requests](https://www.rfc-editor.org/rfc/rfc9396.html)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707.html)
- [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126.html)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html)
- [Spring Authorization Server 1.5.8 — How-to: Implement an Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html)
- [Spring Authorization Server 1.5.8 — OAuth2 Token Endpoint](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
