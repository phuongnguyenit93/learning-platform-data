# Creating AuthenticationToken and AuthenticationConverter for a New Grant

## Lesson Objective

In the **Protocol Extensions** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson guides you through extending the OAuth 2.0 Token Endpoint with a new authorization grant type in **Spring Authorization Server 1.5.8**, using **Spring Security** and **Spring Boot**.

An extension grant allows the Authorization Server to accept a type of authorization proof that existing standard grants do not adequately model. For example, a partner system might issue a short-lived ticket bound to an OAuth client and a set of scopes. The client sends the ticket to the Token Endpoint; the Authorization Server verifies the ticket and issues an access token according to policy.

Spring Authorization Server designs extension grants around three core components:

1. **AuthenticationToken** represents the grant request after it has been converted.
2. **AuthenticationConverter** reads the HTTP request and creates the corresponding AuthenticationToken.
3. **AuthenticationProvider** verifies the grant, checks the client, and produces the token issuance result.

The first two components are the main focus of this lesson. The provider is presented alongside them to clarify how AuthenticationToken is consumed and why the converter should not verify grants or issue tokens itself.

### Expected Outcomes

After this lesson, you will be able to:

1. Explain extension authorization grants per RFC 6749 and distinguish grant types from access tokens.
2. Choose a unique absolute URI for the `grant_type` value.
3. Create a class extending `OAuth2AuthorizationGrantAuthenticationToken`.
4. Write an `AuthenticationConverter` to recognize the grant, validate parameters, and retain the authenticated client principal.
5. Distinguish requests belonging to the new grant from standard grant requests by returning `null` from the converter when there is no match.
6. Write an `AuthenticationProvider` that validates the client, grant permission, ticket, scopes, and replay state.
7. Build `OAuth2TokenContext`, invoke `OAuth2TokenGenerator`, and persist `OAuth2Authorization`.
8. Register the converter/provider with the OAuth2 Token Endpoint while preserving default converters/providers.
9. Test valid requests, malformed requests, unauthorized clients, and expired or already-used grants.
10. Evaluate risks related to replay, scope escalation, credential leakage, transactions, and token lifecycle.

> **Running scenario:** a partner sends the Authorization Server a one-time ticket confirming a user transaction. The client has been registered with a custom grant type and allowed scopes. The Authorization Server must authenticate the client, verify the ticket matches the client/audience, is unexpired, and has not been used, determine the subject and authorized scopes, and then issue an access token.

## 1. What Is an Extension Authorization Grant?

### 1.1. Grant Type Describes How a Client Requests a Token

An OAuth 2.0 authorization grant is a credential or authorization representation that a client uses to request an access token. RFC 6749 defines common grants such as Authorization Code, Client Credentials, and Refresh Token. Section 4.5 allows extending the framework with a new grant type.

The client sends the grant type value in the request to the Token Endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aexample%3Aparams%3Aoauth%3Agrant-type%3Apartner-ticket&example_partner_ticket=ONE_TIME_TICKET
~~~

An extension's `grant_type` value must be a unique absolute URI. This URI is the protocol name of the grant, not an endpoint URL for the client to invoke directly. Under RFC 6749 Section 8.3, if an extension requires additional token endpoint parameters, those parameters must be registered in the OAuth Parameters Registry. For vendor-specific parameters used only within a private deployment, RFC 6749 Section 8.2 recommends using a private prefix to reduce name collision risk; a prefix does not replace the registration requirement when a parameter falls under registration rules.

In the example, the grant type is:

~~~text
urn:example:params:oauth:grant-type:partner-ticket
~~~

The custom grant parameter is **example_partner_ticket**. The `example` prefix reflects the parameter-owning domain in an illustrative deployment. For extensions intended to interoperate across multiple organizations, follow the grant type and token endpoint parameter registration procedures in RFC 6749 Section 8.3 and the OAuth Parameters Registry. Do not use generic parameter names like `ticket`, `assertion`, or `code` if they could collide with other extensions.

### 1.2. When Should You Create a New Grant?

Only create an extension grant when there is a distinct authorization artifact or trust relationship that standard grants do not properly model.

Examples where an extension grant may be needed:

- A business system already has a short-lived, single-use authorization credential bound to a client.
- An internal trust domain issues signed assertions under a proprietary policy.
- An integration system needs to exchange an authorization artifact from a legacy platform for an Authorization Server access token.

Before creating a new grant, verify whether an existing standard already solves the exact problem. For example, Token Exchange has its own RFC; SAML 2.0 Bearer Assertion and JWT Bearer Assertion also have dedicated specifications. Do not create a vendor-specific grant merely to rename a standard flow.

### 1.3. An Extension Grant Does Not Create an OIDC Login Flow

An extension grant extends how tokens are obtained at the Token Endpoint. It does not automatically create an Authorization Endpoint flow, browser login, consent screen, ID Token, or OIDC authentication flow.

If the extension must represent an End-User, the provider must verify the subject's identity from a trusted source and persist the appropriate principal in the authorization. Never take an arbitrary username or subject from the request body and treat it as an authenticated user.

### 1.4. Roles of the Three Components

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant CA as Client Authentication Filter
    participant TE as Token Endpoint Filter
    participant CV as Custom AuthenticationConverter
    participant AM as AuthenticationManager
    participant AP as Custom AuthenticationProvider
    participant TS as Ticket Service
    participant TG as OAuth2TokenGenerator
    participant AS as OAuth2AuthorizationService

    C->>CA: POST /oauth2/token + client credentials
    CA->>CA: Authenticate client
    CA-->>TE: Authenticated client in SecurityContext
    TE->>CV: Convert HTTP request
    CV->>CV: Check grant_type and parameters
    CV-->>TE: PartnerTicketGrantAuthenticationToken
    TE->>AM: Authenticate grant token
    AM->>AP: Delegate by supports()
    AP->>AP: Check client and registered grant
    AP->>TS: Validate and consume ticket atomically
    TS-->>AP: Subject and approved scopes
    AP->>TG: Generate access token from OAuth2TokenContext
    TG-->>AP: OAuth2Token
    AP->>AS: Save OAuth2Authorization
    AP-->>TE: OAuth2AccessTokenAuthenticationToken
    TE-->>C: Standard OAuth2 access token response
~~~

| Component | Responsibility | Should Not Do |
|---|---|---|
| AuthenticationToken | Holds parsed grant data and client principal. | Must not verify the ticket or issue tokens itself. |
| AuthenticationConverter | Recognizes the grant, validates request syntax, and builds the token. | Must not access business systems to consume the ticket. |
| AuthenticationProvider | Verifies client/grant, calls domain service, creates and persists tokens. | Must not write HTTP responses directly or bypass the token generator. |
| OAuth2TokenGenerator | Generates access tokens per token context and token settings. | Must not replace the grant verification step. |
| OAuth2AuthorizationService | Persists authorization and token state. | Must not just return a token without saving state when the system needs introspection/revocation. |

## 2. AuthenticationToken in Spring Authorization Server

### 2.1. AuthenticationToken Is an Internal Spring Security Object

At the Token Endpoint, Spring Authorization Server uses the `Authentication` abstraction to pass requests through `AuthenticationManager` and `AuthenticationProvider`.

**OAuth2AuthorizationGrantAuthenticationToken** is the base class for an `Authentication` representing an authorization grant. This class holds:

- `AuthorizationGrantType`.
- The client principal authenticated during client authentication.
- Additional parameters of the grant.

The base class constructor is `protected`, so applications create their own class by extending it.

Do not confuse this object with `OAuth2AccessToken`. `AuthenticationToken` represents the authorization request; `OAuth2AccessToken` is the credential issued after the provider successfully verifies the grant.

### 2.2. Declaring the Grant Type

Create a class holding the grant type constant and supported parameter names:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;

public final class PartnerTicketGrantTypes {

    public static final AuthorizationGrantType PARTNER_TICKET =
            new AuthorizationGrantType(
                    "urn:example:params:oauth:grant-type:partner-ticket");

    public static final String PARTNER_TICKET_PARAMETER =
            "example_partner_ticket";

    private PartnerTicketGrantTypes() {
    }
}
~~~

Define the grant type name in one shared place so `RegisteredClient`, `AuthenticationToken`, `Converter`, and `Provider` do not accidentally use different strings.

### 2.3. Creating PartnerTicketGrantAuthenticationToken

This class holds the ticket and requested scopes. The client principal is passed to the base class so the provider can inspect `OAuth2ClientAuthenticationToken`.

~~~java
import java.util.Set;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2AuthorizationGrantAuthenticationToken;

public final class PartnerTicketGrantAuthenticationToken
        extends OAuth2AuthorizationGrantAuthenticationToken {

    private String ticket;
    private final Set<String> requestedScopes;

    public PartnerTicketGrantAuthenticationToken(
            String ticket,
            Authentication clientPrincipal,
            Set<String> requestedScopes) {

        super(PartnerTicketGrantTypes.PARTNER_TICKET,
                clientPrincipal,
                null);

        this.ticket = ticket;
        this.requestedScopes = Set.copyOf(requestedScopes);
    }

    public String getTicket() {
        return this.ticket;
    }

    public Set<String> getRequestedScopes() {
        return this.requestedScopes;
    }

    @Override
    public Object getCredentials() {
        return this.ticket;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        this.ticket = null;
    }
}
~~~

Several important design decisions:

- The grant type is passed to the base class constructor.
- The client principal is the `Authentication` already authenticated by the client authentication filter.
- The ticket is a sensitive credential; do not include it in logs, exception messages, or a custom `toString`.
- `requestedScopes` is copied into an immutable `Set` to prevent mutation after token construction.
- `eraseCredentials()` clears the ticket reference after processing if the framework or application invokes credential erasure.
- This token does not mark itself as authenticated. It is strictly a grant request awaiting processing by `AuthenticationProvider`.

If the grant has multiple custom parameters, add strongly typed fields and validate them in the converter. Only place genuinely needed data into additional parameters; do not blindly copy the entire request parameter map.

## 3. Writing the AuthenticationConverter

### 3.1. The Converter Recognizes the Grant Type

Spring Authorization Server runs a chain of `AuthenticationConverter` instances at the Token Endpoint. Each converter attempts to recognize requests it understands.

Key contract:

- If `grant_type` does not belong to this extension, return `null` so the next converter can handle it.
- If `grant_type` matches but the request is syntactically malformed, throw `OAuth2AuthenticationException` with `invalid_request`.
- If the request is syntactically valid, construct `PartnerTicketGrantAuthenticationToken`.
- Do not validate the ticket's contents or consume the ticket here.

The converter is invoked in the filter chain after client authentication has run. The current client principal can be retrieved from `SecurityContextHolder`. Do not trust `client_id` in the form body over the authenticated principal.

### 3.2. AuthenticationConverter Code

~~~java
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.endpoint.OAuth2ParameterNames;
import org.springframework.security.web.authentication.AuthenticationConverter;
import org.springframework.util.StringUtils;

public final class PartnerTicketGrantAuthenticationConverter
        implements AuthenticationConverter {

    @Override
    public Authentication convert(HttpServletRequest request) {
        String[] grantTypes =
                request.getParameterMap().get(OAuth2ParameterNames.GRANT_TYPE);

        if (grantTypes == null || grantTypes.length == 0) {
            return null;
        }

        boolean containsPartnerTicketGrant = Arrays.stream(grantTypes)
                .anyMatch(PartnerTicketGrantTypes.PARTNER_TICKET.getValue()::equals);
        if (!containsPartnerTicketGrant) {
            return null;
        }

        if (grantTypes.length != 1
                || !PartnerTicketGrantTypes.PARTNER_TICKET.getValue()
                        .equals(grantTypes[0])) {
            throw invalidRequest();
        }

        String[] tickets = request.getParameterMap().get(
                PartnerTicketGrantTypes.PARTNER_TICKET_PARAMETER);

        if (tickets == null || tickets.length != 1
                || !StringUtils.hasText(tickets[0])) {
            throw invalidRequest();
        }

        Set<String> requestedScopes = parseScopes(request);

        Authentication clientPrincipal =
                SecurityContextHolder.getContext().getAuthentication();

        if (clientPrincipal == null) {
            throw new OAuth2AuthenticationException(
                    OAuth2ErrorCodes.INVALID_CLIENT);
        }

        return new PartnerTicketGrantAuthenticationToken(
                tickets[0],
                clientPrincipal,
                requestedScopes);
    }

    private static Set<String> parseScopes(HttpServletRequest request) {
        String[] scopeParameters =
                request.getParameterMap().get(OAuth2ParameterNames.SCOPE);

        if (scopeParameters == null) {
            return Set.of();
        }

        if (scopeParameters.length != 1
                || !StringUtils.hasText(scopeParameters[0])) {
            throw invalidRequest();
        }

        return Arrays.stream(scopeParameters[0].trim().split("\\s+"))
                .filter(StringUtils::hasText)
                .collect(Collectors.toCollection(LinkedHashSet::new));
    }

    private static OAuth2AuthenticationException invalidRequest() {
        return new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_REQUEST);
    }
}
~~~

This converter is tailored to a specific grant. It only parses the two parameters defined in the example: `ticket` and `scope`. Client authentication parameters such as `client_id`/`client_secret` are handled separately by the client authentication filter; the converter does not use them to determine client identity.

### 3.3. Why Must Parameter Cardinality Be Checked?

An HTTP form can contain multiple values for the same parameter. If a converter simply calls `getParameter()`, the servlet typically returns the first value, which can mask an ambiguous request.

For `ticket`, the request must contain exactly one value. For `scope`, this example likewise requires a single `scope` parameter containing a space-delimited list of scopes.

Cases that must be rejected:

| Request | Result |
|---|---|
| Missing `grant_type` | Converter returns `null`. |
| Different grant type | Converter returns `null`. |
| Matching grant type, missing ticket | `invalid_request`. |
| Empty ticket | `invalid_request`. |
| Ticket appears multiple times | `invalid_request`. |
| Scope appears multiple times | `invalid_request`. |
| Scope parameter present but empty | `invalid_request`. |
| Syntactically valid request | Returns `PartnerTicketGrantAuthenticationToken`. |

If the extension has additional parameters such as `audience`, `tenant`, or `assertion type`, define syntax, cardinality, and validation rules for each field. Do not arbitrarily take the first value of every parameter and dump them into `additionalParameters`.

### 3.4. The Converter Does Not Execute Business Logic

Do not call `PartnerTicketService.consume()` inside the converter. The converter's job is to convert the request into an `Authentication` object. Verifying signature, expiration, audience, used status, subject, and scope permissions belongs to the provider/domain service.

Separating responsibilities in this way ensures:
- The converter causes no side effects when the filter chain tries multiple converters.
- The provider is the single authority deciding whether a grant is valid.
- Unit tests for the converter require no database or partner system.
- Ticket verification logic can change without modifying HTTP parsing.

## 4. Writing the AuthenticationProvider

### 4.1. The Provider Verifies the Grant and Issues the Access Token

`AuthenticationProvider` processes `PartnerTicketGrantAuthenticationToken`. Main steps:

1. Verify the client principal is an authenticated `OAuth2ClientAuthenticationToken`.
2. Retrieve `RegisteredClient` from the client principal.
3. Verify the client has registered the `PARTNER_TICKET` grant type.
4. Verify the ticket via the domain service.
5. Bind the ticket to the client, audience, subject, expiry, and scopes.
6. Build `OAuth2TokenContext`.
7. Invoke `OAuth2TokenGenerator` to generate the access token.
8. Build and persist `OAuth2Authorization`.
9. Return `OAuth2AccessTokenAuthenticationToken` to the Token Endpoint filter.

The provider does not write JSON or HTTP status codes directly. The Token Endpoint filter and standard success/error handlers serialize the outcome.

### 4.2. Contract for the Ticket Verification Service

Example domain service definition:

~~~java
import java.util.Optional;
import java.util.Set;

import org.springframework.security.core.Authentication;

public interface PartnerTicketService {

    Optional<ConsumedPartnerTicket> consume(
            String ticket,
            String clientId,
            Set<String> requestedScopes,
            Set<String> clientAllowedScopes);
}
~~~

Verification result:

~~~java
import java.util.Set;

import org.springframework.security.core.Authentication;

public record ConsumedPartnerTicket(
        Authentication subjectPrincipal,
        Set<String> authorizedScopes,
        String grantId) {

    public ConsumedPartnerTicket {
        authorizedScopes = Set.copyOf(authorizedScopes);
    }
}
~~~

The service contract must guarantee:

- The ticket exists, has not expired, and has a valid signature/integrity if using signed tickets.
- The ticket was issued for the correct client or audience.
- The ticket has not been used yet.
- The ticket is bound to an authenticated subject.
- Requested scopes are a subset of permissions in the ticket and permissions granted to the client.
- If the client sends no scopes, the service selects default scopes per policy.
- Checking and consuming a one-time ticket must be atomic.

The service returns `Optional.empty()` when the ticket is invalid, expired, already used, or not intended for the client. Infrastructure failures such as database timeouts must be distinguished from an invalid ticket; do not turn an outage into `invalid_grant`.

### 4.3. AuthenticationProvider Code

~~~java
import java.util.Optional;
import java.util.Set;

import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.ClaimAccessor;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2ErrorCodes;
import org.springframework.security.oauth2.core.OAuth2Token;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2AccessTokenAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.authentication.OAuth2ClientAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContextHolder;
import org.springframework.security.oauth2.server.authorization.token.DefaultOAuth2TokenContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenGenerator;
import org.springframework.util.Assert;

public final class PartnerTicketGrantAuthenticationProvider
        implements AuthenticationProvider {

    private final OAuth2AuthorizationService authorizationService;
    private final OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator;
    private final PartnerTicketService partnerTicketService;

    public PartnerTicketGrantAuthenticationProvider(
            OAuth2AuthorizationService authorizationService,
            OAuth2TokenGenerator<? extends OAuth2Token> tokenGenerator,
            PartnerTicketService partnerTicketService) {

        Assert.notNull(authorizationService,
                "authorizationService cannot be null");
        Assert.notNull(tokenGenerator,
                "tokenGenerator cannot be null");
        Assert.notNull(partnerTicketService,
                "partnerTicketService cannot be null");

        this.authorizationService = authorizationService;
        this.tokenGenerator = tokenGenerator;
        this.partnerTicketService = partnerTicketService;
    }

    @Override
    public Authentication authenticate(Authentication authentication)
            throws AuthenticationException {

        PartnerTicketGrantAuthenticationToken grant =
                (PartnerTicketGrantAuthenticationToken) authentication;

        OAuth2ClientAuthenticationToken clientPrincipal =
                getAuthenticatedClientElseThrowInvalidClient(grant);

        RegisteredClient registeredClient =
                clientPrincipal.getRegisteredClient();

        if (!registeredClient.getAuthorizationGrantTypes()
                .contains(PartnerTicketGrantTypes.PARTNER_TICKET)) {
            throw new OAuth2AuthenticationException(
                    OAuth2ErrorCodes.UNAUTHORIZED_CLIENT);
        }

        Optional<ConsumedPartnerTicket> consumedTicket =
                this.partnerTicketService.consume(
                        grant.getTicket(),
                        registeredClient.getClientId(),
                        grant.getRequestedScopes(),
                        registeredClient.getScopes());

        ConsumedPartnerTicket consumed = consumedTicket
                .orElseThrow(() -> new OAuth2AuthenticationException(
                        OAuth2ErrorCodes.INVALID_GRANT));

        Authentication subjectPrincipal = consumed.subjectPrincipal();
        Set<String> authorizedScopes = consumed.authorizedScopes();

        if (subjectPrincipal == null || !subjectPrincipal.isAuthenticated()) {
            throw new OAuth2AuthenticationException(
                    OAuth2ErrorCodes.INVALID_GRANT);
        }

        if (authorizedScopes.isEmpty()
                || !registeredClient.getScopes().containsAll(authorizedScopes)
                || !authorizedScopes.containsAll(grant.getRequestedScopes())) {
            throw new OAuth2AuthenticationException(
                    OAuth2ErrorCodes.INVALID_SCOPE);
        }

        OAuth2TokenContext tokenContext =
                DefaultOAuth2TokenContext.builder()
                        .registeredClient(registeredClient)
                        .principal(subjectPrincipal)
                        .authorizationServerContext(
                                AuthorizationServerContextHolder.getContext())
                        .authorizedScopes(authorizedScopes)
                        .tokenType(OAuth2TokenType.ACCESS_TOKEN)
                        .authorizationGrantType(grant.getGrantType())
                        .authorizationGrant(grant)
                        .build();

        OAuth2Token generatedToken =
                this.tokenGenerator.generate(tokenContext);

        if (generatedToken == null) {
            OAuth2Error error = new OAuth2Error(
                    OAuth2ErrorCodes.SERVER_ERROR,
                    "The token generator failed to generate the access token.",
                    null);
            throw new OAuth2AuthenticationException(error);
        }

        OAuth2AccessToken accessToken = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                generatedToken.getTokenValue(),
                generatedToken.getIssuedAt(),
                generatedToken.getExpiresAt(),
                authorizedScopes);

        OAuth2Authorization.Builder authorizationBuilder =
                OAuth2Authorization.withRegisteredClient(registeredClient)
                        .principalName(subjectPrincipal.getName())
                        .authorizationGrantType(grant.getGrantType())
                        .authorizedScopes(authorizedScopes)
                        .attribute("partner_ticket_grant_id",
                                consumed.grantId());

        if (generatedToken instanceof ClaimAccessor claimAccessor) {
            authorizationBuilder.token(accessToken, metadata ->
                    metadata.put(
                            OAuth2Authorization.Token.CLAIMS_METADATA_NAME,
                            claimAccessor.getClaims()));
        } else {
            authorizationBuilder.accessToken(accessToken);
        }

        OAuth2Authorization authorization = authorizationBuilder.build();
        this.authorizationService.save(authorization);

        return new OAuth2AccessTokenAuthenticationToken(
                registeredClient,
                clientPrincipal,
                accessToken);
    }

    @Override
    public boolean supports(Class<?> authentication) {
        return PartnerTicketGrantAuthenticationToken.class
                .isAssignableFrom(authentication);
    }

    private static OAuth2ClientAuthenticationToken
            getAuthenticatedClientElseThrowInvalidClient(
                    Authentication authentication) {

        Object principal = authentication.getPrincipal();

        if (principal instanceof OAuth2ClientAuthenticationToken clientPrincipal
                && clientPrincipal.isAuthenticated()
                && clientPrincipal.getRegisteredClient() != null) {
            return clientPrincipal;
        }

        throw new OAuth2AuthenticationException(
                OAuth2ErrorCodes.INVALID_CLIENT);
    }
}
~~~

This is a provider example for access tokens. It does not issue refresh tokens. If the business use case requires refresh tokens, you must design a dedicated policy for issuance, storage, rotation, reuse detection, and revocation; do not automatically add refresh tokens merely because the Token Endpoint response supports that field.

### 4.4. Why Check RegisteredClient?

Successful client authentication only proves the client possesses valid credentials. It does not mean the client is permitted to use every grant.

`RegisteredClient` must declare the extension grant type:

~~~java
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

RegisteredClient partnerClient =
        RegisteredClient.withId("partner-client-registration-id")
                .clientId("partner-integration")
                .clientSecret(passwordEncoder.encode(partnerClientSecret))
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        PartnerTicketGrantTypes.PARTNER_TICKET)
                .scope("orders.read")
                .scope("orders.write")
                .build();
~~~

Secrets must be hashed with an appropriate `PasswordEncoder`. `RegisteredClient` must be persisted via `RegisteredClientRepository`. Never put plaintext secrets in source code or production migrations.

If the client has not registered the grant type, the provider returns **unauthorized_client**. If the client is unauthenticated, the provider returns **invalid_client**. These two errors carry distinct meanings.

### 4.5. Scopes Must Be Constrained by Both Client and Grant

There are two permission sets to check:

- Scopes the client is permitted to request under `RegisteredClient`.
- Scopes the ticket or authorization artifact actually grants.

The final scopes must lie within the intersection of those two sets. If the client requests a scope outside the client's or ticket's permissions, reject with `invalid_scope`.

Do not trust client-supplied scopes, and do not copy all scopes from the ticket into the access token if the ticket has not been validated for audience, client binding, and subject.

### 4.6. Generating Tokens with OAuth2TokenGenerator

`OAuth2TokenContext` passes the necessary information to the token generator:

| Property | Meaning |
|---|---|
| registeredClient | The client requesting the token. |
| principal | The verified subject from the ticket service. |
| authorizationServerContext | Context of the Authorization Server handling the request. |
| authorizedScopes | Scopes granted after validation. |
| tokenType | Type of token to generate; here `access_token`. |
| authorizationGrantType | The extension grant type. |
| authorizationGrant | The `AuthenticationToken` of the current grant. |

`OAuth2TokenGenerator` can generate a JWT or reference/opaque access token depending on the generator and token settings. If no generator supports the token context, `generate()` may return `null`; the provider must return `server_error` rather than creating an empty token.

If the application configures a custom token generator, ensure the generator supports the token format required by `RegisteredClient`. For JWTs, a JWK/`NimbusJwtEncoder` and appropriate signing key are required. For reference tokens, `OAuth2AccessTokenGenerator` and a corresponding Resource Server/introspection path are needed.

Example of a generator chain capable of creating JWT or reference access tokens and supporting refresh tokens for other standard grants:

~~~java
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.server.authorization.token.DelegatingOAuth2TokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.JwtGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2AccessTokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2RefreshTokenGenerator;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenGenerator;

@Bean
OAuth2TokenGenerator<?> tokenGenerator(
        JWKSource<SecurityContext> jwkSource) {

    JwtGenerator jwtGenerator =
            new JwtGenerator(new NimbusJwtEncoder(jwkSource));
    OAuth2AccessTokenGenerator accessTokenGenerator =
            new OAuth2AccessTokenGenerator();
    OAuth2RefreshTokenGenerator refreshTokenGenerator =
            new OAuth2RefreshTokenGenerator();

    return new DelegatingOAuth2TokenGenerator(
            jwtGenerator,
            accessTokenGenerator,
            refreshTokenGenerator);
}
~~~

This is a generator chain example following the SAS guide. If the application already has a centrally configured and managed token generator, inject the existing bean into the provider instead of creating another chain. The chain supporting refresh tokens does not mean the `partner-ticket` provider automatically issues refresh tokens; the provider in this lesson only requests `ACCESS_TOKEN`.

### 4.7. Why Must OAuth2Authorization Be Persisted?

After generating the access token, the provider persists `OAuth2Authorization` via `OAuth2AuthorizationService`. The authorization stores the registered client, principal, grant type, scopes, token, and metadata.

Persisting the authorization allows other Authorization Server components to look up tokens, perform introspection, handle revocation, and manage lifecycle operations. Do not skip this step merely because a JWT can be verified offline by a Resource Server.

In the example, the provider stores `grantId` rather than the raw ticket. The raw ticket is a single-use credential and should not be persisted or logged unless there is an explicit security requirement.

## 5. Registering Converter and Provider on the Token Endpoint

### 5.1. Endpoint Configuration

Spring Authorization Server 1.5.8 provides `OAuth2TokenEndpointConfigurer` with two extension points:

- **accessTokenRequestConverter(...)** adds an `AuthenticationConverter`.
- **authenticationProvider(...)** adds an `AuthenticationProvider`.

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        PartnerTicketGrantAuthenticationConverter converter,
        PartnerTicketGrantAuthenticationProvider provider)
        throws Exception {

    OAuth2AuthorizationServerConfigurer configurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(configurer.getEndpointsMatcher())
            .with(configurer, authorizationServer ->
                    authorizationServer.tokenEndpoint(tokenEndpoint ->
                            tokenEndpoint
                                    .accessTokenRequestConverter(converter)
                                    .authenticationProvider(provider)))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

    return http.build();
}
~~~

These two methods append the converter/provider to the Token Endpoint configuration. Spring Authorization Server's default converters/providers for standard grants remain intact. The new converter returns `null` for grant types it does not own, allowing default converters to continue processing.

If using `accessTokenRequestConverters(...)` or `authenticationProviders(...)`, the API provides a `Consumer` to access and customize the default list. Add items to the list or decorate providers appropriately; do not replace the entire list without reason and risk inadvertently removing standard grants.

### 5.2. Token Endpoint Still Uses Standard Client Authentication

The OAuth2 Token Endpoint filter processes the grant request after client authentication. Therefore:

- Client credentials are verified by the client authentication filter/provider.
- The converter reads the client principal from `SecurityContextHolder`.
- The provider verifies that this principal is an authenticated `OAuth2ClientAuthenticationToken`.
- Do not re-verify the client secret a second time inside the converter.
- Do not use `client_id` in the body as proof of identity.

If the application uses `client_secret_post`, `client_secret_basic`, `private_key_jwt`, or mTLS, let the client authentication configurer handle it per `RegisteredClient`. The custom grant only adds the authorization artifact verification step.

### 5.3. Token Request

Example request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_PARTNER_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aexample%3Aparams%3Aoauth%3Agrant-type%3Apartner-ticket&example_partner_ticket=ONE_TIME_TICKET&scope=orders.read
~~~

If the request is valid and the grant is approved, the Token Endpoint returns the standard response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

The Token Endpoint filter uses the `OAuth2AccessTokenAuthenticationToken` returned by the provider to build the response. The provider does not write the JSON response itself.

## 6. Error Semantics for a Custom Grant

The provider and converter must use appropriate OAuth2 error codes. Do not return internal details about tickets, subjects, databases, or signatures to the client.

| Scenario | OAuth2 Error | Meaning |
|---|---|---|
| Missing ticket, empty ticket, or duplicate parameters | `invalid_request` | Request is syntactically malformed. |
| Client authentication failed | `invalid_client` | Client is not authenticated. |
| Client has not registered the grant type | `unauthorized_client` | Client is authenticated but not permitted to use the grant. |
| Ticket invalid, expired, replayed, or not belonging to client | `invalid_grant` | Authorization artifact is invalid. |
| Scope exceeds client/ticket permissions | `invalid_scope` | Requested scope is not permitted. |
| Token generator failed to create token | `server_error` | Internal processing error. |
| Ticket service or database hit infrastructure failure | `server_error` | Unable to complete processing due to service error. |

### 6.1. Do Not Disclose Sensitive Causes

Do not return messages such as:
- The ticket exists but was already used by another client.
- The ticket belongs to a specific user.
- The subject is locked or the account does not exist.
- Which byte of the ticket signature failed.
- Which database or verification service is failing.

You may log standardized categories and an internal correlation ID. Never log raw tickets, client secrets, or access tokens.

### 6.2. Distinguishing invalid_grant from server_error

An invalid or expired ticket is an authorization artifact error and maps to `invalid_grant`. A database timeout while checking the ticket is an infrastructure error; never pretend the ticket is invalid simply because the system could not verify it.

Group domain service exceptions clearly:
- Invalid/expired/replayed ticket: invalid result, return `invalid_grant`.
- Client/audience/scope mismatch: reject the grant or scope per policy.
- Database/remote service unavailable: server error.
- Programming error or token generator failure: server error and trigger alert.

## 7. Protecting the Ticket and Grant Lifecycle

### 7.1. Tickets Must Have a Short Lifetime and Clear Bindings

A ticket used as an authorization grant needs at minimum these properties:

- Sufficiently high entropy if the ticket is an opaque random value.
- Short lifetime and server-side expiration check.
- Explicit audience or client binding.
- Subject determined from a trusted source.
- Explicitly granted scopes.
- Atomic persistence and verification of one-time-use/replay state.
- Issuer/signature validation if the ticket is a signed artifact.
- Cannot be reused once consumed.

Do not accept a ticket solely because it is formatted as a JWT or carries a signature. Verify algorithm, issuer, audience, expiry, key trust, token purpose, and replay policy.

### 7.2. Consumption Must Be Atomic

Two concurrent requests may submit the same ticket. If the service performs a separate "check unused" read followed by a "mark used" write, both requests can receive a valid result.

Use transactions, compare-and-set, unique constraints, or an atomic consume mechanism so only one request wins. Test race conditions using concurrent requests.

### 7.3. Ticket Consumption and Token Persistence Need a Transaction Plan

In the provider, the ticket may be consumed before the token generator creates the token and the authorization is persisted. If token generation or authorization saving fails after consumption, the client may lose the ability to retry.

If the ticket store and authorization store share a database, consider wrapping consumption and authorization saving in a transaction. If they are two independent systems, design a reservation/commit flow or idempotency key for safe retries. Never leave a ticket in a reusable state purely for retry convenience.

### 7.4. Do Not Issue Refresh Tokens Automatically

The extension grant in this example only issues access tokens. If issuing refresh tokens, you must answer:

- Is the client permitted to receive refresh tokens?
- Does the refresh token remain bound to the same subject and scopes?
- Is it rotated on every refresh?
- Are reuse detection and token family revocation implemented?
- How do user deprovisioning or ticket revocation affect it?
- How does `AuthorizationService` persist refresh tokens and metadata?

Do not add `OAuth2RefreshTokenGenerator` to the provider and assume the refresh flow is safe by default. Refresh tokens must have a dedicated policy.

### 7.5. Restricting Scopes and Audience

The access token must have an audience/resource matching the target API. If extension tokens are issued for multiple APIs, establish clear per-resource policies. Never allow a partner-issued ticket to request arbitrary scopes merely because the client registered many scopes.

Final scopes must be bounded by:
1. Scopes `RegisteredClient` is permitted to use.
2. Scopes granted by the ticket.
3. Scopes permitted by the subject's authorization policy.
4. The resource/audience for which the token is being issued.

## 8. Testing AuthenticationToken, Converter, and Provider

### 8.1. Unit Tests for AuthenticationToken

Verify:
- Grant type matches the constant.
- Client principal is preserved.
- Ticket is retained for provider verification.
- Requested scopes are immutable.
- `getCredentials()` returns the ticket during processing.
- `eraseCredentials()` clears the ticket after processing.

Do not verify the ticket by printing the entire `AuthenticationToken` to test logs.

### 8.2. Unit Tests for AuthenticationConverter

| Test Case | Result |
|---|---|
| Different `grant_type` | Returns `null`. |
| Missing `grant_type` | Returns `null`. |
| Matching `grant_type`, missing ticket | `invalid_request`. |
| Empty ticket | `invalid_request`. |
| Duplicate ticket parameter | `invalid_request`. |
| Duplicate scope parameter | `invalid_request`. |
| Valid scope | Produces accurate `Set` of scopes. |
| Client principal present in `SecurityContext` | Attached to `AuthenticationToken`. |
| Missing client principal | `invalid_client`. |

Example structural test:

~~~java
@Test
void returnsNullForDifferentGrantType() {
    MockHttpServletRequest request = new MockHttpServletRequest();
    request.setParameter(
            OAuth2ParameterNames.GRANT_TYPE,
            AuthorizationGrantType.CLIENT_CREDENTIALS.getValue());

    Authentication result = converter.convert(request);

    assertThat(result).isNull();
}
~~~

Test for request missing ticket:

~~~java
@Test
void rejectsRequestWithoutTicket() {
    MockHttpServletRequest request = new MockHttpServletRequest();
    request.setParameter(
            OAuth2ParameterNames.GRANT_TYPE,
            PartnerTicketGrantTypes.PARTNER_TICKET.getValue());

    assertThatThrownBy(() -> converter.convert(request))
            .isInstanceOf(OAuth2AuthenticationException.class);
}
~~~

These examples use `MockHttpServletRequest` and AssertJ; import the corresponding test dependencies in your project.

### 8.3. Unit Tests for AuthenticationProvider

Scenarios to include:

- Authentication is not `PartnerTicketGrantAuthenticationToken`: `supports()` returns `false`.
- Client principal is not authenticated: `invalid_client`.
- Client has not registered the grant type: `unauthorized_client`.
- Ticket is invalid/expired/replayed: `invalid_grant`.
- Ticket belongs to another client: `invalid_grant`.
- Scope outside `RegisteredClient` or ticket: `invalid_scope`.
- Subject principal is not authenticated: grant rejected.
- Token generator returns `null`: `server_error`.
- Token is generated: `OAuth2AuthorizationService.save()` is called.
- Token claims are saved in metadata if generated token implements `ClaimAccessor`.
- Response `Authentication` is `OAuth2AccessTokenAuthenticationToken`.
- Scopes in access token and `OAuth2Authorization` match granted scopes.

### 8.4. Integration Tests for the Token Endpoint

Use `MockMvc` or a test client to invoke the real endpoint with client authentication:

1. Register a client with grant type `PARTNER_TICKET`.
2. Configure the converter/provider in the Authorization Server `SecurityFilterChain`.
3. Issue a valid ticket fixture for that exact client.
4. POST a form request to `/oauth2/token`.
5. Verify HTTP 200, `access_token`, `token_type`, `expires_in`, and `scope`.
6. Verify the authorization has been persisted.
7. Resubmit the same ticket and confirm the second request is rejected.
8. Send a request with a client not registered for the grant and confirm `unauthorized_client`.
9. Send a standard grant type such as `client_credentials` and confirm the custom converter returns `null` while the default flow still works.
10. Verify the token is accepted by the Resource Server or introspection returns `active` per configuration.

### 8.5. Concurrency and Failure Tests

Do not stop at single-request tests. Also test:

- Two requests consuming the same ticket concurrently.
- Ticket service timeout.
- `AuthorizationService.save()` failing after the ticket was consumed.
- Token generator error.
- Client retry after a timeout.
- Multiple Authorization Server instances verifying tickets simultaneously.
- Clock skew between the ticket issuer and Authorization Server.
- Ticket revoked while a request is in flight.

## 9. Common Issues and Troubleshooting

| Symptom | Cause | Resolution |
|---|---|---|
| Custom grant request returns `unsupported_grant_type` | Converter not registered or `grant_type` URI mismatch. | Check converter, URI, and Token Endpoint configuration order. |
| Converter is never invoked | Token Endpoint filter chain lacks converter or request misses endpoint matcher. | Check `SecurityFilterChain` and `accessTokenRequestConverter`. |
| Grant type unsupported even though converter runs | `RegisteredClient` does not register the grant type. | Add `AuthorizationGrantType` to `RegisteredClient`. |
| Client receives `invalid_client` | Client authentication failed or converter/provider lacks valid client principal. | Check client auth filter, `SecurityContext`, and `RegisteredClient`. |
| Client receives `unauthorized_client` | Client is authenticated but not permitted to use the grant. | Check `RegisteredClient.authorizationGrantTypes`. |
| Valid ticket still fails with `invalid_grant` | Ticket binding mismatch on client/audience, expiry, replay, or clock skew. | Inspect domain service and test fixtures. |
| Ticket can be used twice | Consumption is non-atomic or replay state is not shared across nodes. | Use transactions/unique constraints/atomic updates. |
| Token is missing scopes | Provider omitted `authorizedScopes` from token context or access token. | Check token context and `OAuth2AccessToken` scopes. |
| Token has excessive scopes | Trusted client-sent scopes or failed to intersect with ticket scopes. | Enforce scope validation in provider/domain service. |
| Access token returned but introspection shows inactive | Authorization was not saved or token metadata/lookup mismatch. | Check `OAuth2AuthorizationService` and token persistence. |
| Standard `client_credentials` grant breaks | Custom configurer replaced the entire converter/provider list. | Use the `add` methods or preserve the default list. |
| Tickets leaked in logs | Logging full requests, `Authentication` objects, or exceptions. | Redact parameters and credentials; log correlation IDs. |
| Retries lose tickets | Ticket was consumed before token persistence failed. | Design reservation/commit or idempotency. |
| Token generator returns `null` | Generator does not support the requested token type/format. | Check generator chain, JWK, and `TokenSettings`. |
| Token has wrong audience | Token customizer/policy fails to attach appropriate resource/audience. | Define resource policy and verify Resource Server checks. |

## 10. Hands-On Exercise

**Context:** a payment partner sends a short-lived ticket to client `partner-integration`. The ticket is issued after a user confirms a transaction. The Authorization Server must exchange the ticket for an access token with only the `orders.read` scope.

### Requirements

1. Define an absolute URI grant type for `partner-ticket`.
2. Define a custom ticket parameter with a clear namespace.
3. Create `PartnerTicketGrantAuthenticationToken` extending `OAuth2AuthorizationGrantAuthenticationToken`.
4. Write a converter recognizing `grant_type`, validating ticket, scopes, and parameter cardinality.
5. Ensure the converter returns `null` for grant types it does not own.
6. Create `PartnerTicketService` to verify ticket, client binding, audience, expiry, and replay.
7. Write a provider checking `OAuth2ClientAuthenticationToken` and `RegisteredClient` grant types.
8. Restrict scopes by both client and ticket.
9. Build `OAuth2TokenContext` and issue the access token.
10. Persist `OAuth2Authorization` using `OAuth2AuthorizationService`.
11. Register the converter/provider using `OAuth2TokenEndpointConfigurer`.
12. Test valid requests, ticket replay, wrong client, scope escalation, and token generator failures.
13. Test two concurrent requests using the same ticket.
14. Verify the standard `client_credentials` grant still functions.
15. Write a runbook for ticket service outages, token persistence failures, and key rotation.

**Completion criteria:** the custom grant works at `/oauth2/token`; clients are authenticated independently; tickets are verified and consumed once; scopes never exceed policy; access tokens are generated by `OAuth2TokenGenerator` and authorizations persisted; standard grants continue to work.

## 11. Pre-Production Checklist

- [ ] Grant type uses a unique absolute URI.
- [ ] Token endpoint parameters have distinct names and documented syntax.
- [ ] Extension registration per RFC 6749 has been evaluated.
- [ ] `AuthenticationToken` extends `OAuth2AuthorizationGrantAuthenticationToken`.
- [ ] Converter only parses the request and does not consume the grant.
- [ ] Converter returns `null` for other grant types.
- [ ] Duplicate/missing/empty parameters are validated.
- [ ] Client principal is retrieved from `SecurityContextHolder` after client authentication.
- [ ] Provider verifies `OAuth2ClientAuthenticationToken` is authenticated.
- [ ] `RegisteredClient` permits the extension grant type.
- [ ] Ticket validates issuer, signature/integrity, expiry, audience, client binding, and replay.
- [ ] Ticket consumption is atomic across concurrent requests and multiple instances.
- [ ] Scopes are constrained by `RegisteredClient` and the authorization artifact.
- [ ] Subject principal is obtained from a trusted source.
- [ ] `OAuth2TokenContext` contains accurate registered client, principal, grant type, scopes, and grant token.
- [ ] Tokens are generated via `OAuth2TokenGenerator`.
- [ ] `OAuth2Authorization` is saved via `OAuth2AuthorizationService`.
- [ ] Tickets, client secrets, and access tokens are never logged.
- [ ] Error responses use `invalid_request`, `invalid_client`, `unauthorized_client`, `invalid_grant`, `invalid_scope`, or `server_error` appropriately.
- [ ] Standard Token Endpoint success/error handlers are preserved.
- [ ] Default converters/providers of Spring Authorization Server continue working.
- [ ] Refresh tokens are issued only if a dedicated policy exists.
- [ ] Unit, integration, replay, concurrency, and failure tests are in place.
- [ ] Transaction/idempotency plan exists for ticket consumption and authorization saving.
- [ ] Rate limiting, monitoring, alerts, and runbook exist for the ticket service.

## Summary

Spring Authorization Server 1.5.8 extends the Token Endpoint through `AuthenticationConverter` and `AuthenticationProvider`. The converter recognizes `grant_type`, validates request syntax, and creates an `AuthenticationToken` extending `OAuth2AuthorizationGrantAuthenticationToken`. The provider processes that token, verifies the client and `RegisteredClient`, validates the authorization artifact, constructs `OAuth2TokenContext`, invokes `OAuth2TokenGenerator`, and persists `OAuth2Authorization`.

A secure design keeps the converter side-effect-free, authenticates clients via the standard pipeline, checks grant types against `RegisteredClient`, consumes tickets atomically, restricts scopes, and avoids leaking credentials. Registering converters/providers must preserve default implementations so Authorization Code, Refresh Token, Client Credentials, and other standard grants continue to function.

An extension grant is only complete when request parsing, grant validation, token generation, authorization persistence, error responses, and replay protection have all been thoroughly tested.

## References

1. [Spring Authorization Server 1.5.8 — How-to: Implement an Extension Authorization Grant Type](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-ext-grant-type.html): `AuthenticationConverter`, `AuthenticationProvider`, Token Endpoint configuration, and custom grant token request examples.
2. [Spring Authorization Server 1.5.8 — OAuth2TokenEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenEndpointConfigurer.html): `accessTokenRequestConverter`, `authenticationProvider`, response handler, and error handler.
3. [Spring Authorization Server 1.5.8 — OAuth2AuthorizationGrantAuthenticationToken API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2AuthorizationGrantAuthenticationToken.html): base class for an `Authentication` representing an authorization grant.
4. [Spring Authorization Server 1.5.8 — OAuth2ClientAuthenticationToken API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2ClientAuthenticationToken.html): authenticated client principal and `RegisteredClient`.
5. [Spring Authorization Server 1.5.8 — OAuth2AccessTokenAuthenticationToken API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2AccessTokenAuthenticationToken.html): `Authentication` result used to return the access token response.
6. [Spring Authorization Server 1.5.8 — OAuth2TokenContext API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenContext.html): token context and properties required by the generator.
7. [Spring Authorization Server 1.5.8 — OAuth2TokenGenerator API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenGenerator.html): generating `OAuth2Token` from `OAuth2TokenContext` and null-return handling.
8. [Spring Authorization Server 1.5.8 — OAuth2Authorization API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.html): authorization state and token lookup.
9. [Spring Authorization Server 1.5.8 — OAuth2Authorization.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.Builder.html): principal, grant type, scopes, and token metadata.
10. [RFC 6749 — The OAuth 2.0 Authorization Framework, Section 4.5](https://www.rfc-editor.org/rfc/rfc6749.html#section-4.5): extension authorization grants and absolute URI `grant_type`.
11. [RFC 6749 — Section 8.3, Defining New Authorization Grant Types](https://www.rfc-editor.org/rfc/rfc6749.html#section-8.3): absolute URI for grant types and registration requirements for additional token endpoint parameters.
12. [RFC 6749 — Section 5.2, Error Response](https://www.rfc-editor.org/rfc/rfc6749.html#section-5.2): OAuth2 token endpoint error codes.
13. [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): current OAuth2 security recommendations.
