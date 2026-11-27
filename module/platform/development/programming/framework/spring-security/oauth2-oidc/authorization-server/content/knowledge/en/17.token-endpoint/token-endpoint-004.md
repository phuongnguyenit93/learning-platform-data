# Customizing accessTokenRequestConverter and AuthenticationProvider

## 1. Objectives and Context

In a **Spring Security OAuth2/OIDC Authorization Server** built with **Spring Boot** and **Spring Authorization Server**, the **Token Endpoint** receives requests to exchange an authorization grant for an access token. Grants such as <code>authorization_code</code>, <code>refresh_token</code>, and <code>client_credentials</code> all pass through this endpoint, yet each has distinct parameter checks, client authentication rules, authorization conditions, and token states.

Spring Authorization Server provides **extension points** so an application can customize how requests are parsed and how grants are processed without rewriting the entire endpoint:

- <code>accessTokenRequestConverter(...)</code>: adds an <code>AuthenticationConverter</code> that transforms an HTTP request into an authentication object representing a grant.
- <code>authenticationProvider(...)</code>: adds an <code>AuthenticationProvider</code> that verifies the grant, enforces token-issuance policies, and returns the authentication result.
- <code>accessTokenRequestConverters(...)</code> and <code>authenticationProviders(...)</code>: access the **list of default and added components** for intentional adjustments.

These extension points are powerful and security-sensitive: an overly broad converter can hijack requests belonging to standard grants; a provider that skips client authentication or scope checks can issue tokens beyond registered permissions; and a new validator that completely replaces the default validator can silently weaken critical checks.

After this lesson, you will be able to:

1. Understand the pipeline **HTTP → converter → AuthenticationManager/provider → token generator → authorization store → token response**.
2. Distinguish methods that add converters/providers from methods that customize the default lists.
3. Design an **extension authorization grant** with its own URI and token class.
4. Write a converter that validates parameters, rejects invalid input, and yields requests belonging to other grants.
5. Write a provider that verifies the client, registered grant, business credential, scopes, and single-use consumption before issuing tokens.
6. Use <code>OAuth2TokenGenerator</code> and <code>OAuth2AuthorizationService</code> within proper responsibility boundaries.
7. Add rules to a **default** provider while preserving its baseline validator.
8. Build integration tests proving standard grants still work and the extension grant cannot cause privilege escalation.

**Running Example:** An Authorization Server at <code>https://auth.example.com</code> serves a confidential client <code>reports-worker</code>. Alongside Client Credentials, the experimental system wants to issue access tokens via a **one-time ticket issued by a trusted internal component**, pre-bound to a registered client and a restricted set of scopes. The illustrative grant uses the URI <code>urn:example:oauth:grant-type:one-time-ticket</code> and is **not an IETF standard grant**. In production systems, prefer standard grants such as Token Exchange (RFC 8693) when appropriate instead of inventing a custom protocol.

**Version Scope:** Java DSL examples use Spring Authorization Server **1.5.x** APIs with <code>OAuth2AuthorizationServerConfigurer.authorizationServer()</code> and <code>HttpSecurity.with(...)</code>. Newer Spring Security releases integrate Authorization Server into different packages; always verify the API of your exact version. Example business classes (such as <code>OneTimeTicketService</code>) are application-defined contracts, not built-in Spring APIs.

## 2. Which Components Actually Process the Token Endpoint?

### 2.1. Flow from Request to Response

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant CF as OAuth2ClientAuthenticationFilter
    participant TF as OAuth2TokenEndpointFilter
    participant CV as AuthenticationConverter
    participant AM as AuthenticationManager
    participant P as AuthenticationProvider
    participant S as Authorization/Token services
    C->>CF: POST /oauth2/token + client authentication + grant parameters
    CF->>CF: Authenticate client per RegisteredClient
    CF->>TF: Allow request to proceed if valid
    TF->>CV: convert(HttpServletRequest)
    CV-->>TF: OAuth2AuthorizationGrantAuthenticationToken
    TF->>AM: authenticate(grantToken)
    AM->>P: Select provider with supports(grantToken)
    P->>S: Verify grant, client, scope, and state
    S-->>P: Valid result
    P->>S: Generate token and save OAuth2Authorization
    P-->>AM: OAuth2AccessTokenAuthenticationToken
    AM-->>TF: Authentication succeeded
    TF-->>C: JSON access_token or OAuth error
~~~

This diagram shows the typical flow, not the exact filter position in every configuration. The critical point is that **client authentication** and **authorization grant authentication** are two distinct responsibilities. In the default pipeline, <code>OAuth2ClientAuthenticationFilter</code> authenticates the OAuth client; <code>OAuth2TokenEndpointFilter</code> and the grant provider then process the token request.

### 2.2. Three Extension Points Corresponding to Three Phases

| Phase | Common API | Responsibility | What Not to Do |
| --- | --- | --- | --- |
| **Pre-processing** | <code>AuthenticationConverter</code> | Reads and validates HTTP request shape; constructs the matching authentication request. | Mint access tokens directly, trust unauthenticated client IDs, run heavy DB queries unnecessarily. |
| **Core processing** | <code>AuthenticationProvider</code> | Verifies client/grant/policy, checks state, mints/saves tokens, and returns authentication. | Skip scopes, issue tokens for unauthenticated clients, accept already-used tickets/codes. |
| **Post-processing** | <code>AuthenticationSuccessHandler</code> / <code>AuthenticationFailureHandler</code> | Produces protocol-compliant success/error HTTP responses. | Implement authorization logic in the handler simply because JSON is written there. |

In Spring Authorization Server 1.5.x, the Token Endpoint supports common grants by default, including Authorization Code, Refresh Token, Client Credentials, Device Code, and Token Exchange (support depends on version). Older releases may lack some of these default converters/providers, so verify when changing versions.

### 2.3. Do Not Confuse Three Authentication Types

| Object | Represents | Example |
| --- | --- | --- |
| <code>OAuth2ClientAuthenticationToken</code> | A client that has been or is being authenticated. | <code>reports-worker</code> using <code>client_secret_basic</code>. |
| <code>OAuth2AuthorizationGrantAuthenticationToken</code> | A **request to use a grant** at the token endpoint. | <code>authorization_code</code>, <code>refresh_token</code>, or a custom ticket. |
| <code>OAuth2AccessTokenAuthenticationToken</code> | The **successful result** of grant processing; holds the access token and metadata. | Provider mints token; filter writes JSON response. |

Never convert <code>OAuth2AccessTokenAuthenticationToken</code> into <code>UsernamePasswordAuthenticationToken</code> to "log a user into the system," and never treat successful client authentication as automatic entitlement to every scope.

## 3. OAuth2TokenEndpointConfigurer API

Typical methods:

~~~java
authorizationServer.tokenEndpoint(tokenEndpoint -> tokenEndpoint
    .accessTokenRequestConverter(customConverter)
    .accessTokenRequestConverters(converters -> {
        // Can inspect/adjust default and added converters.
    })
    .authenticationProvider(customProvider)
    .authenticationProviders(providers -> {
        // Can inspect/adjust default and added providers.
    })
    .accessTokenResponseHandler(successHandler)
    .errorResponseHandler(errorHandler)
);
~~~

| Method | Effect | When to Use |
| --- | --- | --- |
| <code>accessTokenRequestConverter(converter)</code> | **Adds** a converter so the token endpoint accepts a custom request format. | Adding a new extension grant. |
| <code>accessTokenRequestConverters(consumer)</code> | Gives a consumer access to the converter list, including defaults. | Need to inspect, reorder, or replace a specific converter. |
| <code>authenticationProvider(provider)</code> | **Adds** a provider to handle a new authentication request. | Adding a new extension grant with its own token class. |
| <code>authenticationProviders(consumer)</code> | Gives a consumer access to the provider list, including defaults. | Configuring a default provider or adjusting the list carefully. |
| <code>accessTokenResponseHandler(handler)</code> | Customizes how successful responses are written. | Integrating compliant response handling after understanding the OAuth2 structure. |
| <code>errorResponseHandler(handler)</code> | Customizes token endpoint error handling. | Standardizing logging/responses without leaking credentials or breaking protocol error codes. |

**Key Rule:** The **singular** methods are normally used to **add** components; do not mistake them for commands that replace all defaults. The **plural** methods expose the current list; removing, altering, or reordering elements there can break standard grant behavior. To verify exactly which converters/providers are active, check the API/version docs and run integration tests.

### 3.1. How Is a Converter Selected?

By default, the Token Endpoint uses a <code>DelegatingAuthenticationConverter</code> holding multiple converters. Each converter inspects the same request in list order; the first converter that returns a non-<code>null</code> authentication is used. An extension grant converter must:

1. Check <code>grant_type</code> first.
2. **Return <code>null</code>** if the request belongs to another grant.
3. **Throw <code>OAuth2AuthenticationException</code>** if the request is recognized as its own grant but required parameters are invalid.
4. Return a specialized <code>OAuth2AuthorizationGrantAuthenticationToken</code> if the request shape is valid.

If a converter returns <code>null</code> when a client sends the custom grant without a ticket, the error may take the wrong path and surface as an unsupported grant error that misrepresents the bad input. Conversely, if a converter always returns non-null even for <code>authorization_code</code>, it can "swallow" standard requests and break the entire Token Endpoint.

### 3.2. How Is a Provider Selected?

<code>AuthenticationManager</code>, typically implemented by <code>ProviderManager</code>, calls <code>AuthenticationProvider.supports(Class&lt;?&gt;)</code> to determine whether a provider can handle an authentication token. A provider should accept **only the exact class** it supports, then verify:

- The OAuth client is authenticated and backed by a real <code>RegisteredClient</code>.
- The client is permitted to use that grant type.
- The credential or grant proof is valid per policy.
- Scopes, audience/resource, principal, and related state are validated.
- Token generation, persistence, replay protection, and error mapping preserve OAuth2 invariants.

Never write a provider with <code>supports(Authentication.class)</code> or an overly generic class and then branch on multiple conditions inside <code>authenticate()</code>. An overly broad provider can intercept requests meant for built-in providers.

## 4. Reading HTTP Requests and OAuth Errors at the Token Endpoint

Example of a client using Authorization Code:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <redacted-client-credential>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=example-code&redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&code_verifier=example-verifier
~~~

This is an illustrative request; `code` and PKCE `verifier` values must be real, properly generated data. The token endpoint typically receives form-URL-encoded requests over HTTPS. Clients must send fields matching the grant and their registered client authentication method. Never place tokens, codes, or secrets in query URLs or raw request logs.

### 4.1. Error Codes to Distinguish

| OAuth 2.0 Error Code | Example | Proper Handling in Converter/Provider |
| --- | --- | --- |
| <code>invalid_request</code> | Missing ticket, duplicate parameters, malformed form body. | Converter or token endpoint validation rejects the request. |
| <code>invalid_client</code> | Unauthenticated client or invalid client credentials. | Client authentication/provider rejects; do not arbitrarily substitute <code>invalid_grant</code>. |
| <code>unauthorized_client</code> | Client exists but is not registered for this grant. | Provider checks <code>RegisteredClient</code>'s allowed grants. |
| <code>invalid_grant</code> | Expired, reused, mismatched-client, or revoked code/ticket. | Provider rejects with a generic error, avoiding leaking credential details. |
| <code>invalid_scope</code> | Scope exceeds registered permissions or grant policy. | Provider/validator rejects unauthorized scope. |
| <code>unsupported_grant_type</code> | No converter/provider supports the submitted grant. | Token endpoint returns the protocol error. |
| <code>server_error</code> | Token generator or storage failure. | Do not issue unpersisted tokens; record safe audit logs. |

Never return HTTP 200 with a custom JSON `"error"` string for a failed request. Throw <code>OAuth2AuthenticationException</code> with an appropriate <code>OAuth2Error</code> so the framework translates it into a protocol error; never allow stack traces, tokens, or signing key details to appear in client responses.

## 5. Illustrative Scenario: Custom Grant Using a One-Time Ticket

Suppose an internal system has a trusted **Ticket Issuer** component responsible for issuing short-lived, random, single-use credentials to the confidential client <code>reports-worker</code>. After proving its identity at the token endpoint, the client can exchange the ticket for an access token restricted to the <code>reports.generate</code> scope.

~~~mermaid
sequenceDiagram
    autonumber
    participant I as Trusted Ticket Issuer
    participant C as reports-worker
    participant AS as Authorization Server
    participant TS as OneTimeTicketService
    participant P as Custom AuthenticationProvider
    I-->>C: Issue ticket over trusted channel, bound to client + scope + TTL
    C->>AS: POST /oauth2/token + client auth + grant_type + ticket
    AS->>AS: OAuth2ClientAuthenticationFilter authenticates reports-worker
    AS->>P: Converter builds OneTimeTicketAuthenticationToken
    P->>TS: Verify and consume ticket atomically with registeredClientId
    TS-->>P: Valid, unused ticket, approved scopes
    P->>AS: Generate access token via OAuth2TokenGenerator
    P->>AS: Save OAuth2Authorization
    AS-->>C: Access token with scope reports.generate
~~~

This is an **internal grant example**, not meant to replace standard OAuth 2.0 where standard flows suffice. Never issue tickets based merely on an email address, a guessable OTP, or unverified browser parameters. Tickets must have high entropy, client binding, a short TTL, single-use semantics, pre-approved scopes, and replay protection.

### 5.1. Why Choose a Dedicated URI?

Per Spring Authorization Server guidelines, an extension grant needs a <code>grant_type</code> that is a **unique absolute URI**. This lesson uses:

~~~text
urn:example:oauth:grant-type:one-time-ticket
~~~

Do not reuse names like <code>authorization_code</code> or <code>client_credentials</code> to redefine standard grant semantics. Likewise, do not arbitrarily use an IETF-namespaced URN to imply a custom grant is standardized.

### 5.2. Sample HTTP Request

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <redacted-reports-worker-credential>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aexample%3Aoauth%3Agrant-type%3Aone-time-ticket&ticket=high-entropy-one-time-value
~~~

For this illustrative grant:

- <code>ticket</code> is required and must have **exactly one** value.
- Do not let the client pass <code>scope</code> or <code>resource</code> in the form to escalate privileges: permissions are decided by the Ticket Issuer and bound to the ticket.
- The client must use its registered client authentication method.
- The ticket is sent over HTTPS, never in query URLs and never logged in plaintext.
- A successfully redeemed ticket must never be usable again.

## 6. Defining a Dedicated AuthenticationToken

<code>OAuth2AuthorizationGrantAuthenticationToken</code> is the base class for OAuth authorization grant authentication requests. Creating a subclass with dedicated fields ensures the provider handles only the intended grant and avoids parsing the request body a second time.

~~~java
public final class OneTimeTicketAuthenticationToken
        extends OAuth2AuthorizationGrantAuthenticationToken {

    public static final AuthorizationGrantType GRANT =
        new AuthorizationGrantType(
            "urn:example:oauth:grant-type:one-time-ticket");

    private final String ticket;

    public OneTimeTicketAuthenticationToken(
            String ticket, Authentication clientPrincipal) {
        super(GRANT, clientPrincipal, Map.of());
        this.ticket = ticket;
    }

    public String getTicket() {
        return ticket;
    }
}
~~~

The constructor passes the **client principal** to the base class; it is not an End-User identity. In this example, the ticket grants permissions only to a workload/client, not a specific human login. For grants representing an End-User, developers must verify the subject, consent, authentication level, and applicable policies—**never** take a username from a form field and turn it directly into an authenticated principal.

<code>ticket</code> is a sensitive credential even inside a short-lived object. Never override <code>toString()</code> to print it, never place it in events or logs, and keep the object's lifecycle scoped to the request. If credential clearing is desired, design the data structure to allow wiping the credential without disrupting required checks.

## 7. Writing an AuthenticationConverter for a Custom Grant

The converter only transforms the HTTP request into an object describing the **request**. It neither proves the ticket is valid nor issues a token.

~~~java
public final class OneTimeTicketAuthenticationConverter
        implements AuthenticationConverter {

    @Override
    public Authentication convert(HttpServletRequest request) {
        String grant = request.getParameter(
            OAuth2ParameterNames.GRANT_TYPE);

        // Yield requests for authorization_code, refresh_token,
        // client_credentials, device_code... to other converters.
        if (!OneTimeTicketAuthenticationToken.GRANT.getValue()
                .equals(grant)) {
            return null;
        }

        String[] grantValues = request.getParameterValues(
            OAuth2ParameterNames.GRANT_TYPE);
        if (grantValues == null || grantValues.length != 1) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_REQUEST);
        }

        String[] tickets = request.getParameterValues("ticket");
        if (tickets == null || tickets.length != 1
                || !StringUtils.hasText(tickets[0])) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_REQUEST);
        }

        // This grant DOES NOT allow clients to specify scope/resource.
        if (request.getParameterMap().containsKey("scope")
                || request.getParameterMap().containsKey("resource")) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_REQUEST);
        }

        Authentication clientPrincipal =
            SecurityContextHolder.getContext().getAuthentication();

        return new OneTimeTicketAuthenticationToken(
            tickets[0], clientPrincipal);
    }
}
~~~

**Notable Details:**

1. The converter compares <code>grant_type</code> exactly. If it belongs to another grant, it returns <code>null</code> so a default converter can handle it.
2. <code>getParameterValues()</code> checks parameter **cardinality**. Calling only <code>getParameter("ticket")</code> could silently pick the first value when two tickets are submitted, making validation ambiguous.
3. If <code>grant_type</code> matches but the ticket is missing, throw <code>invalid_request</code>. Never use <code>return null</code> to mask malformed input.
4. Never rely on a browser-submitted client ID to mark a client authenticated. <code>SecurityContextHolder</code> only supplies the client authentication outcome from the preceding chain; the provider **must re-verify** the principal's type and status.
5. The example avoids copying arbitrary <code>additionalParameters</code> into the token. If extra parameters are genuinely needed, validate cardinality, type, and length, and copy only explicitly selected values into a controlled map.
6. <code>HttpServletRequest</code> here is a Token Endpoint request. Do not add GET/query handling or raw JSON parsing as substitutes for form-URL-encoded POST when the protocol specifies form POST.

**Snippet Scope Note:** This converter focuses on validating the ticket grant's shape. Constraints on HTTP method, content type, payload size, multipart, URL encoding, and client authentication are enforced at the Token Endpoint/filter/infrastructure layers; production deployments should test end-to-end so unexpected requests cannot be parsed into valid grants.

## 8. Contract for Validating One-Time Tickets

To separate responsibilities, assume the application provides this service:

~~~java
public interface OneTimeTicketService {
    /**
     * Verifies and consumes the ticket for the registered client record ID.
     * Returns null when invalid / already used / expired / wrong client.
     * Verification + consumption must be atomic in shared storage.
     */
    ValidatedTicket validateAndConsume(
        String rawTicket, String registeredClientRecordId);
}

public record ValidatedTicket(
    String safeAuditId,
    Set<String> approvedScopes
) {}
~~~

**Important:** <code>OneTimeTicketService</code> and <code>ValidatedTicket</code> are **application-authored abstractions**, not built-in library types. A production implementation must guarantee:

- Tickets are generated with a CSPRNG, have sufficient entropy, remain confidential, have short TTLs, and (where appropriate) are issued only over trusted channels.
- Ticket lookups use protected values or hashes, not guessable identifiers.
- Tickets are **bound to <code>RegisteredClient.getId()</code>**, not merely a form-submitted client ID.
- Each ticket carries its approved scopes and specific resource/audience bounds; clients cannot alter them.
- Unused/unexpired/unrevoked status is checked and transitioned to consumed via an **atomic operation** in shared storage.
- Any replay of a ticket is rejected, even if two requests hit two different Authorization Server instances simultaneously.
- Auditing uses only safe identifiers; raw tickets never appear in logs, traces, or error responses.

If a ticket represents End-User delegation, the service must also provide a verified **principal, tenant, consent, and authentication level**; this workload-only example intentionally assumes no End-User.

**Atomicity Between Consumption and Saving Authorization:** If a ticket is marked consumed and then the token generator or database fails, the request fails and the ticket cannot be reused. This **fail-closed** behavior is acceptable for security, though UX should allow requesting a fresh ticket. If consuming the ticket and saving the authorization must happen in one transaction, choose a storage/transaction model that supports it and test rollbacks/races. Never silently allow ticket reuse when it is uncertain whether the prior attempt issued a token.

## 9. Writing an AuthenticationProvider That Issues Access Tokens

The provider performs the **core security checks** and then delegates to Spring Authorization Server's token generation and persistence mechanisms. In this workload-only example, the access token represents client permissions; no refresh token is issued and no user principal is fabricated.

### 9.1. Provider Skeleton with Key Checks

~~~java
public final class OneTimeTicketAuthenticationProvider
        implements AuthenticationProvider {

    private final OneTimeTicketService tickets;
    private final OAuth2AuthorizationService authorizations;
    private final OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator;

    public OneTimeTicketAuthenticationProvider(
            OneTimeTicketService tickets,
            OAuth2AuthorizationService authorizations,
            OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator) {
        this.tickets = Objects.requireNonNull(tickets);
        this.authorizations = Objects.requireNonNull(authorizations);
        this.tokenGenerator = Objects.requireNonNull(tokenGenerator);
    }

    @Override
    public Authentication authenticate(Authentication authentication)
            throws AuthenticationException {

        OneTimeTicketAuthenticationToken request =
            (OneTimeTicketAuthenticationToken) authentication;

        if (!(request.getPrincipal()
                instanceof OAuth2ClientAuthenticationToken client)
                || !client.isAuthenticated()
                || client.getRegisteredClient() == null) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_CLIENT);
        }

        RegisteredClient registeredClient = client.getRegisteredClient();
        if (!registeredClient.getAuthorizationGrantTypes()
                .contains(OneTimeTicketAuthenticationToken.GRANT)) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.UNAUTHORIZED_CLIENT);
        }

        // Business service must bind ticket to client ID,
        // verify TTL, policy, replay protection, and consume atomically.
        ValidatedTicket verified = tickets.validateAndConsume(
            request.getTicket(), registeredClient.getId());
        if (verified == null) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_GRANT);
        }

        Set<String> scopes = Set.copyOf(verified.approvedScopes());
        if (scopes.isEmpty()
                || !registeredClient.getScopes().containsAll(scopes)) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_SCOPE);
        }

        OAuth2TokenContext tokenContext = DefaultOAuth2TokenContext
            .builder()
            .registeredClient(registeredClient)
            .principal(client)
            .authorizationServerContext(
                AuthorizationServerContextHolder.getContext())
            .authorizedScopes(scopes)
            .tokenType(OAuth2TokenType.ACCESS_TOKEN)
            .authorizationGrantType(
                OneTimeTicketAuthenticationToken.GRANT)
            .authorizationGrant(request)
            .build();

        OAuth2Token generated = tokenGenerator.generate(tokenContext);
        if (generated == null) {
            throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.SERVER_ERROR);
        }

        OAuth2AccessToken accessToken = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            generated.getTokenValue(),
            generated.getIssuedAt(),
            generated.getExpiresAt(),
            scopes
        );

        OAuth2Authorization.Builder authorizationBuilder =
            OAuth2Authorization.withRegisteredClient(registeredClient)
                .principalName(client.getName())
                .authorizationGrantType(
                    OneTimeTicketAuthenticationToken.GRANT)
                .authorizedScopes(scopes)
                .attribute("ticket_audit_id", verified.safeAuditId());

        if (generated instanceof ClaimAccessor claims) {
            authorizationBuilder.token(accessToken, metadata ->
                metadata.put(
                    OAuth2Authorization.Token.CLAIMS_METADATA_NAME,
                    claims.getClaims()));
        } else {
            authorizationBuilder.accessToken(accessToken);
        }

        authorizations.save(authorizationBuilder.build());

        return new OAuth2AccessTokenAuthenticationToken(
            registeredClient, client, accessToken);
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return OneTimeTicketAuthenticationToken.class
            .isAssignableFrom(authentication);
    }
}
~~~

Imports are omitted; this class uses APIs common in Spring Authorization Server 1.5.x. The snippet relies on a **hypothetical business service** and does not supply ticket storage, transactions, auditing, OAuth error logging, or tests. Do not treat it as a production-ready extension grant merely because it compiles once beans are wired.

### 9.2. Why Each Step Is Mandatory

| Step | Why It Is Needed |
| --- | --- |
| Check <code>OAuth2ClientAuthenticationToken</code> | Refuses requests that only supply a self-asserted client ID. |
| <code>client.isAuthenticated()</code> and non-null <code>RegisteredClient</code> | Requires a client authenticated through its registered mechanism. |
| <code>registeredClient.getAuthorizationGrantTypes().contains(GRANT)</code> | Prevents arbitrary clients from using the custom grant. |
| <code>validateAndConsume(ticket, registeredClient.getId())</code> | Ensures the ticket is authentic, bound to the right client, unused, unexpired, and not replayed. |
| <code>getScopes().containsAll(scopes)</code> | Even scopes from a ticket must never exceed client registration or policy. |
| <code>DefaultOAuth2TokenContext</code> | Provides client, principal, grant, scope, and token type to the generator. |
| <code>OAuth2TokenGenerator.generate(...)</code> | Uses the AS's token-generation pipeline instead of ad-hoc JWT signing. |
| <code>OAuth2AuthorizationService.save(...)</code> | Persists the token and authorization state for inspection, introspection, or revocation. |
| <code>OAuth2AccessTokenAuthenticationToken</code> | Returns the expected result type so the endpoint writes the access token response. |

Never store the raw ticket in <code>OAuth2Authorization.attribute(...)</code>. Store only an audit ID designed not to reveal the credential. For JWT token generators, <code>ClaimAccessor</code> retains claims metadata in the authorization store following Spring's pattern; you must still control sensitive claim data.

### 9.3. Scopes and Subject of the Access Token

In this client-only example:

- <code>principal(client)</code> means the token-issuance principal is the client; never fabricate Alice/Bob.
- <code>scopes</code> come from the ticket verified by the Ticket Issuer and are further bounded by the registered client.
- If the JWT has a <code>sub</code> claim, verify what <code>sub</code> means under your generator/profile; never substitute a form-submitted username.
- The access token's <code>aud</code> must target an authorized Resource Server—never the Token Endpoint or an unverified client-supplied resource URI.
- If using reference/opaque tokens, the token generator and metadata must align with introspection and revocation mechanisms.

Because this custom grant has no authorization code or End-User consent, **do not issue a refresh token or ID Token by default**. If a use case requires refresh tokens, design and test lifecycle/rotation/replay policies explicitly; if an ID Token is needed, that involves distinct OIDC End-User authentication semantics.

### 9.4. Compatibility with TokenSettings and Generators

<code>OAuth2TokenGenerator</code> can be a <code>DelegatingOAuth2TokenGenerator</code> composed of <code>JwtGenerator</code>, <code>OAuth2AccessTokenGenerator</code>, and other appropriate generators. It inspects <code>OAuth2TokenContext</code>, <code>TokenSettings</code>, keys/JWKs, and format configuration to decide which token to emit. The provider must handle <code>generate(...)</code> returning <code>null</code> rather than returning an empty token.

Also check that token claim customization runs only for the intended token type/format. For instance, an <code>OAuth2TokenCustomizer&lt;JwtEncodingContext&gt;</code> does not automatically apply to opaque tokens; the Resource Server must still validate issuer, audience, expiration, and actual permissions.

## 10. Wiring Converters and Providers into the Token Endpoint

### 10.1. Adding an Extension Grant While Preserving Default Grants

~~~java
@Configuration
@EnableWebSecurity
class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http,
            OneTimeTicketService ticketService,
            OAuth2AuthorizationService authorizationService,
            OAuth2TokenGenerator<?> tokenGenerator) throws Exception {

        OAuth2AuthorizationServerConfigurer as =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(as.getEndpointsMatcher())
            .with(as, server -> server
                .tokenEndpoint(tokenEndpoint -> tokenEndpoint
                    .accessTokenRequestConverter(
                        new OneTimeTicketAuthenticationConverter())
                    .authenticationProvider(
                        new OneTimeTicketAuthenticationProvider(
                            ticketService,
                            authorizationService,
                            tokenGenerator))))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }
}
~~~

This configuration **adds** the converter and provider for the ticket grant. Standard grants such as Authorization Code, Refresh Token, and Client Credentials continue using their default converters and providers unless you modify those lists via other APIs.

A real application also needs <code>RegisteredClientRepository</code>, <code>OAuth2AuthorizationService</code>, token generators/JWKs, client authentication, and baseline beans. If enabling Authorization Code/OIDC for users, you also need the web/login filter chain and user authentication/consent services. Do not disable CSRF globally across the application.

### 10.2. RegisteredClient Must Permit the Custom Grant

~~~java
RegisteredClient reportsWorker = RegisteredClient
    .withId("reports-worker-record-001")
    .clientId("reports-worker")
    .clientSecret(encodedClientSecret)
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        OneTimeTicketAuthenticationToken.GRANT)
    .scope("reports.generate")
    .tokenSettings(TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
~~~

<code>encodedClientSecret</code> is encoded compatibly with your <code>PasswordEncoder</code> and provisioned securely; never commit plaintext secrets. This is a **confidential client**, so real client authentication is used. If <code>authorizationGrantType(...)</code> is omitted, the provider must reject the request with <code>unauthorized_client</code> even if the client authenticated properly.

Do not enable the custom grant for an SPA/mobile public client merely because it can submit a ticket. Analyze trust boundaries carefully: stolen bearer tickets, inability of public clients to protect shared secrets, resource protection needs, and replay risks.

### 10.3. Cases Where Standard Grants Should Be Preferred

| Need | Approach to Consider |
| --- | --- |
| User logs in and consents to grant access | Authorization Code + PKCE/OIDC. |
| Service runs jobs under an application identity | Client Credentials, if client permissions suffice. |
| Client exchanges an existing token for another audience per policy | Token Exchange (RFC 8693), if your framework/version supports the requirements. |
| Device without a suitable browser | Device Authorization Grant (RFC 8628). |
| Presenting a signed JWT assertion as an authorization grant | Standard profiles such as RFC 7523, if genuinely appropriate and supported/configured. |
| Internal one-time ticket with domain-specific semantics | Consider a custom grant only after full threat modeling, validation, storage, auditing, and testing. |

Never build a homegrown "password grant" to circumvent the deprecation of Resource Owner Password Credentials in modern security practices. Never accept End-User passwords or MFA codes in a custom Token Endpoint without a properly engineered user authentication protocol.

## 11. Customizing a Built-In AuthenticationProvider Without Widening Scopes

Not every requirement warrants a custom grant. For example, a company wants to add a policy to **Client Credentials** preventing <code>reports-worker</code> from requesting <code>reports.admin</code> even though that scope remains registered in a legacy record. Updating the authoritative registration/policy is best; if runtime enforcement in the provider is needed, use the built-in extension point.

Spring Authorization Server 1.5.x provides <code>OAuth2ClientCredentialsAuthenticationProvider.setAuthenticationValidator(...)</code> and <code>OAuth2ClientCredentialsAuthenticationValidator.DEFAULT_SCOPE_VALIDATOR</code>. When replacing the validator, **preserve the default check and append the new rule**:

~~~java
private static Consumer<List<AuthenticationProvider>>
        clientCredentialsPolicy() {

    return providers -> providers.forEach(provider -> {
        if (provider instanceof
                OAuth2ClientCredentialsAuthenticationProvider credentials) {

            credentials.setAuthenticationValidator(context -> {
                // REQUIRED: preserve default scope validation.
                OAuth2ClientCredentialsAuthenticationValidator
                    .DEFAULT_SCOPE_VALIDATOR.accept(context);

                RegisteredClient registeredClient =
                    context.getRegisteredClient();

                Set<String> requestedScopes =
                    context.getAuthentication().getScopes();

                if ("reports-worker".equals(registeredClient.getClientId())
                        && requestedScopes.contains("reports.admin")) {
                    throw new OAuth2AuthenticationException(
                        OAuth2ErrorCodes.INVALID_SCOPE);
                }
            });
        }
    });
}
~~~

Attach that consumer:

~~~java
http.securityMatcher(as.getEndpointsMatcher())
    .with(as, server -> server.tokenEndpoint(tokenEndpoint ->
        tokenEndpoint.authenticationProviders(
            clientCredentialsPolicy())))
    .authorizeHttpRequests(authorize ->
        authorize.anyRequest().authenticated());
~~~

Here <code>as</code> is the <code>OAuth2AuthorizationServerConfigurer</code> already created in the same <code>SecurityFilterChain</code>. This is a **continuation snippet**, not a standalone complete security chain.

**Key Point:** <code>setAuthenticationValidator(...)</code> replaces the provider's validator; setting a custom validator **without** calling <code>DEFAULT_SCOPE_VALIDATOR</code> can silently drop validation against the scopes allowed in <code>RegisteredClient</code>. In real systems, enforce policies backed by trusted sources (tenant, client status, entitlements) rather than comparing against a single hard-coded string as in this illustration.

### 11.1. When to Use the List Variants?

- <code>authenticationProviders(listConsumer)</code> is useful when locating a default provider by its **exact class**, configuring a supported validator/hook, or inserting a provider before/after a specific one.
- <code>accessTokenRequestConverters(listConsumer)</code> is useful when inspecting default converters and intentionally adjusting order or behavior.
- If simply adding a new grant, prefer <code>authenticationProvider(...)</code> and <code>accessTokenRequestConverter(...)</code> rather than rebuilding the entire list, reducing the risk of dropping standard grants.
- Never remove the <code>authorization_code</code> or <code>refresh_token</code> providers without a replacement plan and integration tests: doing so can cause valid requests to fail with <code>unsupported_grant_type</code> or similar errors.

**Clear Distinction:** <code>authenticationProviders(...)</code> on the **Token Endpoint** differs from <code>clientAuthentication(...)</code> on the **Authorization Server**. If your goal is to customize <code>client_secret_basic</code>, <code>private_key_jwt</code>, or mTLS authentication, look at the **client authentication** extension point—never use an authorization grant converter to bypass client authentication.

## 12. Security Invariants That Must Be Preserved

A well-engineered custom converter/provider must preserve these invariants:

~~~text
Client:
  Has a real Authentication and a valid RegisteredClient
  Client authentication method matches registration

Grant:
  Single, properly formatted grant_type permitted for the client
  Valid, unexpired, unused credential/grant proof bound to the right client
  No replay or cross-issuer/tenant/resource misuse per policy

Token:
  grantedScopes ⊆ registeredClient.scopes ∩ grantAllowedScopes
  Permitted audience/resource, never self-asserted from the form
  token_type/expiry/format aligned with TokenSettings
  Authorization state persisted consistently
  No tokens/secrets/codes written to logs

Response:
  Success returns OAuth2AccessTokenAuthenticationToken
  Failure returns the appropriate OAuth2 error
  No token issued when persistence or policy validation fails
~~~

### 12.1. Client Binding

When the service verifies a ticket, it must use the authenticated <code>registeredClient.getId()</code>, not a self-asserted <code>client_id</code> from the request body that bypassed <code>OAuth2ClientAuthenticationFilter</code>. The <code>registeredClientId</code> and <code>authorization</code> record must stay consistent in the token store.

Even if two clients share identical registered scopes, client B must never be allowed to redeem a ticket owned by client A. Matching scopes **do not** make credentials transferable between clients.

### 12.2. Grant Evidence and Replay

A custom ticket/code can behave like a bearer credential: anyone who steals it may attempt to redeem it before the legitimate owner. Checking only the expiration timestamp without marking it consumed allows an unexpired ticket to be redeemed repeatedly.

Your design should ensure:

1. High-entropy random values and short TTLs.
2. Binding to client, issuer, resource, and tenant as needed.
3. Tracking pending/consumed/revoked state using **atomic compare-and-set** or proper transactions.
4. Only one request succeeds if two instances attempt to consume the same ticket concurrently.
5. Replay monitoring without storing or logging raw credentials.
6. **Fail-closed** database error handling—never issue a token when ticket verification fails.

Never rely on JVM-local <code>synchronized</code> blocks as your sole concurrency guard when running multiple Authorization Server instances.

### 12.3. Scope and Audience

Scopes declared on <code>RegisteredClient</code> are only a registration ceiling; the ticket itself must also carry policy-approved scopes. Never blindly copy all of <code>registeredClient.getScopes()</code> into the token simply because the client is allowed to request them.

For JWT access tokens, <code>aud</code> must match the target Resource Server and <code>iss</code> must be the Authorization Server's issuer; never issue tokens with a universal `"*"` audience. If the grant accepts a <code>resource</code> parameter, verify it against the ticket-issuance contract/policy to prevent token substitution across APIs.

### 12.4. Refresh Tokens, Consent, and End-Users

The custom grant in this lesson has **no** End-User and issues only an access token; do not issue refresh tokens or ID Tokens by default. For user-facing extension grants, require valid authentication/consent proof, user status checks, and dedicated refresh/revocation policies.

<code>OAuth2AuthorizationConsentService</code> records consent decisions for a client and principal; it does not turn an arbitrary ticket into login authorization. <code>OAuth2AuthorizationService</code> stores issued authorizations/tokens; deleting consent alone does not automatically invalidate already-minted JWT access tokens.

### 12.5. Do Not Put Policy Checks in Response Handlers to Bypass Providers

<code>accessTokenResponseHandler(...)</code> runs after authentication has already succeeded. Placing authorization decisions or scope selection here risks persisting an authorization and minting a token before you decide to reject the request. All security checks belong in converters, providers, and services before token generation and response writing.

## 13. Testing Converters and Providers

### 13.1. Converter Unit Tests

The converter must yield other grants and report errors when its own grant is malformed:

~~~java
@Test
void converterIgnoresOtherGrantTypes() {
    MockHttpServletRequest request =
        new MockHttpServletRequest("POST", "/oauth2/token");
    request.setParameter("grant_type", "client_credentials");

    Authentication result =
        new OneTimeTicketAuthenticationConverter().convert(request);

    assertThat(result).isNull();
}

@Test
void converterRejectsDuplicateTickets() {
    MockHttpServletRequest request =
        new MockHttpServletRequest("POST", "/oauth2/token");
    request.setParameter(
        "grant_type",
        OneTimeTicketAuthenticationToken.GRANT.getValue());
    request.setParameter("ticket", "first", "second");

    assertThatThrownBy(() ->
        new OneTimeTicketAuthenticationConverter().convert(request))
        .isInstanceOf(OAuth2AuthenticationException.class);
}
~~~

Add tests for missing tickets, blank tickets, duplicate <code>grant_type</code>, unsupported <code>scope</code>/<code>resource</code> parameters, excessive length, and unusual encodings. Converter unit tests verify **input parsing**, not that the client has been authenticated.

### 13.2. Provider Unit Tests

Using a fake/mock <code>OneTimeTicketService</code> and test <code>OAuth2TokenGenerator</code>, verify:

- Client principal is not <code>OAuth2ClientAuthenticationToken</code> or is unauthenticated ⇒ <code>invalid_client</code>.
- Authenticated client lacks custom grant registration ⇒ <code>unauthorized_client</code>.
- Ticket missing/expired/used/wrong registered client ID ⇒ <code>invalid_grant</code>.
- Ticket carries scopes outside <code>RegisteredClient</code> ⇒ <code>invalid_scope</code>.
- Token generator returns <code>null</code> ⇒ <code>server_error</code>, no access token issued.
- Valid ticket and scopes ⇒ saves <code>OAuth2Authorization</code> with right client/grant/scopes, returns <code>OAuth2AccessTokenAuthenticationToken</code>.
- Two concurrent requests with the same ticket ⇒ exactly one succeeds per atomic service design.

In unit tests, you may pass a fake authenticated <code>OAuth2ClientAuthenticationToken</code> to isolate the provider. However, **never treat that fake as proof that HTTP client authentication works**.

### 13.3. Token Endpoint Integration Tests

Example HTTP test using <code>MockMvc</code>, assuming fixtures for the confidential client, a valid ticket, and all Authorization Server beans:

~~~java
@Test
void acceptsValidOneTimeTicket() throws Exception {
    String issuedTicket = ticketFixtures.issueFor(
        "reports-worker-record-001", Set.of("reports.generate"));

    mockMvc.perform(post("/oauth2/token")
            .with(httpBasic("reports-worker", "test-only-secret"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type",
                OneTimeTicketAuthenticationToken.GRANT.getValue())
            .param("ticket", issuedTicket))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.access_token").exists())
        .andExpect(jsonPath("$.token_type").value("Bearer"));
}
~~~

<code>ticketFixtures.issueFor(...)</code> is a **project-authored test helper**, not a Spring API. <code>test-only-secret</code> is used solely with a properly registered/encoded test client. A complete test also reloads <code>OAuth2Authorization</code>, verifies scopes and token claims/audience, calls a Resource Server if needed, and confirms the ticket works only once.

### 13.4. Integration Regression Test Matrix

| Test Case | Expected Result |
| --- | --- |
| Valid custom grant, valid ticket, authenticated client | Access token issued with valid scopes; authorization persisted properly. |
| Custom grant missing ticket | <code>invalid_request</code>. |
| Custom grant with two tickets | <code>invalid_request</code>. |
| New grant with client lacking grant registration | <code>unauthorized_client</code>. |
| Wrong client secret or missing auth | <code>invalid_client</code> or corresponding client authentication response. |
| Used or expired ticket | <code>invalid_grant</code>; no token issued. |
| Client A's ticket presented by client B | Rejected; no authorization created for client B. |
| Ticket carries scopes beyond client registration | <code>invalid_scope</code>; no extra permissions granted. |
| Client adds form scope/resource | Rejected if unsupported by custom grant; ticket scope unchanged. |
| Token generator failure | No access token returned; safe <code>server_error</code>/infrastructure handling. |
| Authorization DB failure | Never reports success when required state fails to save. |
| Two requests with same ticket hit two nodes | Only one request consumes the ticket; never issued twice against policy. |
| Standard <code>authorization_code</code> with PKCE | Still works; custom converter returns <code>null</code> for other grants. |
| Standard <code>refresh_token</code> | Still checks client, authorization, active state, and scopes. |
| Standard <code>client_credentials</code> | Still enforces default scope checks and added policies. |
| <code>device_code</code> if enabled | Still handles pending/denied/success per protocol. |
| <code>token-exchange</code> if supported by version | Not intercepted by custom converter/provider. |
| Sensitive credentials in logs | Log inspection/tests verify secret/ticket/token are masked. |

Do not test only HTTP 200; verify **the minted token actually carries the right issuer, audience, scope, client, and authorization**, and that failure cases emit no tokens.

## 14. Common Design Mistakes and Diagnosis

### Mistake 1: Converter Returns Non-Null for Every Request

**Symptom:** Authorization Code or Refresh Token suddenly breaks after adding a custom grant.

**Cause:** The converter fails to check <code>grant_type</code> accurately or always constructs a custom authentication token.

**Fix:** Return <code>null</code> immediately for other grants; run regression tests for standard grants.

### Mistake 2: Converter Returns Null When Custom Request Is Invalid

**Symptom:** Client sends the custom grant URI without the <code>ticket</code> parameter, and the endpoint returns an unclear error or never reaches the provider.

**Cause:** Using <code>return null</code> instead of throwing <code>invalid_request</code>.

**Fix:** Distinguish "not my grant" from "my grant with malformed input"; throw the appropriate <code>OAuth2AuthenticationException</code>.

### Mistake 3: Provider Validates Grant but Forgets Client Authentication

**Symptom:** Any unknown client holding a ticket can obtain tokens.

**Cause:** Trusting a client ID from the request or skipping <code>OAuth2ClientAuthenticationToken.isAuthenticated()</code>.

**Fix:** Require an authenticated principal with a <code>RegisteredClient</code>, validate client authentication at the proper layer, and bind tickets to internal client record IDs.

### Mistake 4: Skipping Registered Grant Checks

**Symptom:** Every client can use the new grant.

**Cause:** The provider fails to check <code>RegisteredClient.getAuthorizationGrantTypes()</code>.

**Fix:** Reject with <code>unauthorized_client</code> if the grant is unregistered; govern grant assignments explicitly.

### Mistake 5: Replacing the Default Validator with an Overly Simple One

**Symptom:** Client Credentials requests for unregistered scopes still receive tokens.

**Cause:** Calling <code>setAuthenticationValidator()</code> without invoking <code>DEFAULT_SCOPE_VALIDATOR</code>.

**Fix:** Compose the default validator with your additional policy; add tests for unregistered scopes.

### Mistake 6: Minting Tokens by Signing JWTs Directly in the Converter

**Symptom:** Tokens lack standard issuer/audience, no authorization is persisted, introspection/revocation fails, or TTL ignores client settings.

**Cause:** Mixing request parsing with token issuance and bypassing <code>OAuth2TokenGenerator</code>/<code>OAuth2AuthorizationService</code>.

**Fix:** Keep parsing in the converter; use the token generator and persist state in the provider per contract.

### Mistake 7: Building a TicketService That Checks Then Deletes Separately

**Symptom:** Two concurrent requests both redeem the same ticket successfully.

**Cause:** <code>if (ticket.active) ... ticket.active=false</code> is not atomic across nodes.

**Fix:** Use database transactions or compare-and-set in shared storage, and test races; never rely on single-JVM locks.

### Mistake 8: Confusing Token Endpoint with Client Authentication Configuration

**Symptom:** Customizing the grant converter has no effect on <code>client_secret_jwt</code> or mTLS.

**Cause:** Client authentication mechanisms are configured via <code>clientAuthentication(...)</code>, not <code>tokenEndpoint(...)</code>.

**Fix:** Choose the right extension point for the responsibility; never disable client authentication to "fix" an error.

### Mistake 9: Lacking a Unified Authorization Store

**Symptom:** A token issued on node A cannot be found by introspection/revocation on node B.

**Cause:** Separate in-memory stores per node or incompatible database schemas/transactions.

**Fix:** Use a shared repository, properly versioned migrations, and test concurrency and token state consistency.

## 15. Production Operations and Change Control

Before deploying a custom converter/provider, the team should verify:

| Item | Question |
| --- | --- |
| Protocol need | Can this be solved with standard Authorization Code/PKCE, Client Credentials, Device Grant, or Token Exchange? |
| Grant naming | Is the URI unique and free of conflicts with standard grants or other clients? |
| Client authentication | Which clients may use the grant? Are credentials protected and methods properly registered? |
| Input validation | Are cardinality, content type, length, encoding, unexpected parameters, and grant type controlled? |
| Grant evidence | Do tickets/codes have sufficient entropy, TTL, client/tenant/resource binding, and single-use semantics? |
| Token policy | Are scope, audience, TTL, format, claims, and target Resource Servers properly constrained? |
| Persistence | Are authorizations/tokens saved before returning success, with proper transactions? |
| Multi-instance | Are ticket consumption, token issuance, and replay detection atomic against shared storage? |
| Error handling | Are OAuth errors accurate without leaking tickets, secrets, tokens, or stack traces? |
| Observability | Do logs capture error codes, client IDs, request IDs, and safe audit IDs without raw credentials? |
| Testing | Do tests cover converter/provider unit cases, HTTP integration, standard grant regressions, and DB race conditions? |
| Upgrades | Are APIs, configurers, and default provider lists verified when upgrading Spring Boot/Security/Authorization Server? |

Beyond technical testing, perform **threat modeling** for custom grants: who issues tickets, who can obtain them, can they be replayed or used across clients, what are their lifetimes, and what is the blast radius if the Ticket Issuer is compromised? In regulated systems or multi-party integrations, non-standard custom grants should generally be avoided.

## 16. Practice Exercise

A company has three clients: <code>billing-worker</code> running Client Credentials, <code>reports-worker</code> authorized to exchange one-time tickets, and <code>portal-web</code> using Authorization Code + PKCE. Complete the following:

1. Diagram the flow <code>OAuth2ClientAuthenticationFilter → OAuth2TokenEndpointFilter → converter → provider → token generator → authorization service</code>. Indicate which steps authenticate the client and which verify the grant.
2. Register the custom grant <code>urn:example:oauth:grant-type:one-time-ticket</code> **only for <code>reports-worker</code>**.
3. Write a converter that rejects custom requests missing a ticket, supplying duplicate tickets, or adding out-of-contract scopes, while yielding all other grants with <code>null</code>.
4. Write <code>OneTimeTicketAuthenticationToken</code> extending <code>OAuth2AuthorizationGrantAuthenticationToken</code> and explain why a dedicated class is needed.
5. Design a database-backed <code>OneTimeTicketService</code> that consumes tickets once atomically. Illustrate two requests racing on two nodes.
6. Write a provider that verifies the authenticated client, registered grant, ticket client binding/expiration/single-use status, client-bounded scopes, and permitted resources.
7. Use <code>OAuth2TokenGenerator</code> to issue an access token, save <code>OAuth2Authorization</code>, and return <code>OAuth2AccessTokenAuthenticationToken</code>. Do not issue refresh/ID tokens in this workload-only example.
8. Add a Client Credentials validator blocking a sensitive scope while still invoking <code>DEFAULT_SCOPE_VALIDATOR</code>.
9. Write integration tests for wrong secrets, another client's ticket, reused tickets, concurrent requests, token generator failures, scope escalation, and intact standard grants.
10. If the project upgrades Spring Security to a newer Authorization Server API, list the classes, packages, and configurers that must be re-verified before deployment.

**Success Criteria:** The converter only **parses valid requests**, the provider **thoroughly verifies and issues tokens per policy**, customization **does not break default grants**, and a ticket belonging to one client can never mint a token for another client.

## 17. References

- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Token Endpoint, default converters/providers, and extension points.
- [Spring Authorization Server — How-to Implement an Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html): official pattern for custom grants, <code>AuthenticationConverter</code>, <code>AuthenticationProvider</code>, and configuration.
- [Spring Authorization Server — OAuth2TokenEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenEndpointConfigurer.html): method signatures for <code>accessTokenRequestConverter(s)</code> and <code>authenticationProvider(s)</code>.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>RegisteredClient</code>, <code>OAuth2Authorization</code>, and <code>OAuth2AuthorizationService</code>.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): filter chains, client authentication, and endpoint configurers.
- [Spring Authorization Server — OAuth2ClientCredentialsAuthenticationValidator API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2ClientCredentialsAuthenticationValidator.html): preserving default validation when adding policy rules.
- [Spring Security — OAuth2 Authorization Server Protocol Endpoints](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/protocol-endpoints.html): APIs in Spring Security branches with integrated Authorization Server.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): token endpoint, grant validation, error codes, and client authentication.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): modern OAuth 2.0 security practices, grant/credential restrictions, and refresh tokens.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): standard grant for exchanging tokens when appropriate.
