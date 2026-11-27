# OidcUserInfoEndpointConfigurer and userInfoMapper

In OpenID Connect (OIDC), the **ID Token** informs the Relying Party (RP) of the user authentication result, while the **UserInfo Endpoint** lets the RP fetch additional claims about the End-User using an access token. The two token types serve different purposes: the ID Token describes the authentication event and subject; the access token is a credential to call a protected resource. UserInfo is a protected resource belonging to the OpenID Provider (OP), not another login endpoint.

In Spring Authorization Server, **OidcUserInfoEndpointConfigurer** configures the UserInfo endpoint and its request processing pipeline. The most important customization point is **userInfoMapper**: a Function that receives an authenticated OidcUserInfoAuthenticationContext and produces an OidcUserInfo for the response. The mapper can read claims from the ID Token, JWT access token, or a service/domain repository; it must preserve the exact subject, scopes, and granted consent.

This lesson belongs to the **OIDC UserInfo** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module. The module scope covers designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application. The content focuses on OidcUserInfoEndpointConfigurer, OidcUserInfoAuthenticationContext, and how to implement a secure userInfoMapper.

> **Important rule:** The UserInfo response must always contain the sub claim. The RP must compare this sub exactly with the sub in the ID Token. If the two values differ, the RP must discard the entire UserInfo response to prevent token substitution.

## 1. What Problem Does the UserInfo Endpoint Solve?

An RP often needs to know that a user has successfully logged in as well as some profile information to render the UI or complete a task. The ID Token may contain some claims, but does not necessarily contain all information. UserInfo lets the RP request additional details using the access token and granted scopes.

For example, the RP requests:

~~~text
scope=openid profile email
~~~

After the Authorization Server authenticates the user, applies consent, and issues tokens, the RP can call UserInfo:

~~~http
GET /userinfo HTTP/1.1
Host: identity.example.com
Authorization: Bearer ACCESS_TOKEN_VALUE
Accept: application/json
~~~

Illustrative response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "sub": "user-42",
  "name": "Nguyen Van An",
  "given_name": "An",
  "family_name": "Nguyen",
  "preferred_username": "an.nguyen",
  "email": "an@example.com",
  "email_verified": true
}
~~~

The RP can use the claims permitted by the OP to personalize the experience. The OP may omit certain claims due to privacy policies; a requested claim not being returned is not automatically a protocol error.

### 1.1. ID Token and UserInfo Differ

| Aspect | ID Token | UserInfo Response |
|---|---|---|
| Purpose | Proves authentication info and subject to the RP | Returns additional claims about the End-User |
| Common format | Signed JWT | JSON object over HTTPS |
| Credential to obtain | Returned from the token/authorization flow | Access token |
| Timing | Upon completing the OIDC authentication flow | When the RP needs to read user information |
| Identity claim | sub | sub, must match ID Token |
| Mutability of info | Snapshot at issuance time | May reflect current profile per policy |
| Access control | RP that received the ID Token | Access token must hold appropriate permissions |

Do not use an ID Token as a Bearer credential to call UserInfo. The UserInfo endpoint requires an access token.

### 1.2. UserInfo Is Not a General-Purpose User Account API

UserInfo exists for an OIDC RP to fetch claims about the End-User bound to the corresponding authorization. It should not become an account management API, a user search endpoint, or a way for the RP to read every column in the identity database.

If the RP needs business operations such as changing an email, managing devices, updating an address, or searching organizations, design an appropriate API with its own authorization model. UserInfo only returns identity/profile data permitted by the OP.

## 2. OIDC Flow from Authorization to UserInfo

~~~mermaid
sequenceDiagram
    autonumber
    participant RP as Relying Party
    participant OP as OpenID Provider
    participant U as End-User

    RP->>OP: Authorization Request (scope=openid profile email)
    OP->>U: Authenticate + obtain consent
    U-->>OP: Authentication and consent result
    OP-->>RP: Authorization Code
    RP->>OP: Token Request + code_verifier
    OP-->>RP: ID Token + Access Token
    Note over RP: Validate ID Token signature, iss, aud, exp, nonce
    RP->>OP: GET UserInfo + Authorization: Bearer Access Token
    OP->>OP: Validate access token and resolve authorization
    OP->>OP: Map authorized claims to OidcUserInfo
    OP-->>RP: JSON claims including sub
    Note over RP: Compare UserInfo sub with ID Token sub
~~~

Main steps:

1. The RP sends an Authentication Request containing the openid scope and needed profile scopes.
2. The OP authenticates the End-User and collects consent per policy.
3. The OP returns an Authorization Code; the RP exchanges the code for an ID Token and Access Token.
4. The RP independently verifies the ID Token.
5. The RP sends the Access Token to the UserInfo endpoint using the Bearer scheme.
6. The OP verifies the access token, finds the authorization, and builds UserInfo claims.
7. The RP verifies that sub in UserInfo matches sub in the ID Token exactly.

### 2.1. UserInfo Is an OAuth2 Protected Resource

According to OIDC Core, the access token obtained from an OIDC Authentication Request must be sent as a Bearer Token per RFC 6750. OIDC Core recommends HTTP GET and sending the token in the Authorization header. POST is also defined, though GET with the Authorization header is the common approach.

~~~http
GET https://identity.example.com/userinfo
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Do not send the access token in the query string. URLs routinely show up in reverse proxy logs, tracing, browser history, or analytics. Likewise, never send an ID Token, refresh token, or client secret in place of the access token.

### 2.2. openid Scope Is the OIDC Condition

openid distinguishes a regular OAuth2 authorization request from an OIDC Authentication Request. The profile, email, address, and phone scopes add requests for standard claim groups.

A client requesting only profile without openid cannot be treated as a valid OIDC UserInfo authorization. RegisteredClient configuration and the token issuance flow must support the corresponding OIDC scopes.

## 3. Standard Claims and Scopes

OIDC Core defines standard claim groups. Scopes indicate which claim groups the RP requests; the OP may still apply consent, privacy policies, and actual data limits.

| Scope | Typical Claims | Example |
|---|---|---|
| openid | sub | Stable subject identifier within the issuer |
| profile | name, given_name, family_name, middle_name, nickname, preferred_username, profile, picture, website, gender, birthdate, zoneinfo, locale, updated_at | Name, photo, and profile details |
| email | email, email_verified | Email address and verification status |
| address | address | Address as a JSON object |
| phone | phone_number, phone_number_verified | Phone number and verification status |

### 3.1. The address Claim Is an Object

address is not an arbitrary string when using the standard OIDC structure. Example:

~~~json
{
  "address": {
    "formatted": "123 Nguyen Hue, District 1, Ho Chi Minh City",
    "street_address": "123 Nguyen Hue",
    "locality": "Ho Chi Minh City",
    "region": "Ho Chi Minh",
    "postal_code": "700000",
    "country": "VN"
  }
}
~~~

Return only the address fields the user has permitted and the RP has a reason to use. Full street addresses can be sensitive PII; do not return them automatically just because the client requested the scope.

### 3.2. email_verified and phone_number_verified

These booleans represent verification states managed by the OP. Do not set email_verified=true merely because the user entered an email or because the email has valid syntax. Likewise, phone_number_verified=true applies only when a phone verification process has completed per policy.

Without proof of verification, return false or omit the claim per your system's semantics; never guess.

### 3.3. Requested Scopes Do Not Mean Unlimited Rights

An RP may request profile email address phone, but the OP is not forced to return every field. The OP may return only claims present in the profile, only claims belonging to granted scopes, apply per-client consent and policies, omit sensitive claims, withhold unverified claims, or use pairwise subject identifiers by client/sector.

An omitted claim should be left out of the JSON instead of appearing with null or an empty string.

## 4. Subject Identifier and the sub Matching Requirement

sub is the subject identifier issued by the OP. Within an issuer, the subject identifier must be locally unique and never reused for another End-User. The combination of iss and sub forms a stable identifier that the RP can rely on.

The UserInfo response MUST always contain sub. The RP also MUST verify that sub in UserInfo matches the ID Token's sub exactly. If they differ, the RP must not use any claims in the response.

Example ID Token:

~~~json
{
  "iss": "https://identity.example.com",
  "aud": "portal-web",
  "sub": "user-42",
  "exp": 1794850600
}
~~~

Valid UserInfo:

~~~json
{
  "sub": "user-42",
  "name": "Nguyen Van An"
}
~~~

Invalid UserInfo for the ID Token above:

~~~json
{
  "sub": "user-84",
  "name": "Another User"
}
~~~

In the second case, the RP must discard the entire response. Do not try to fix the subject by overwriting sub with the ID Token's value, as doing so can mask token substitution or broken authorization binding.

### 4.1. Public and Pairwise Subjects

- **Public subject:** the same subject identifier is provided to clients per the OP's policy.
- **Pairwise subject:** each client/sector receives a different sub to reduce the ability of RPs to correlate the same End-User's activity.

The UserInfo mapper must not generate a random sub on each request. It must retrieve the exact subject bound to the authorization/ID Token used in the flow. If the OP uses pairwise identifiers, the ID Token and UserInfo for the same authorization must use the same pairwise subject.

### 4.2. Do Not Use Email as the Subject Key

Emails can change, be recycled, or be unverified. Never substitute sub with email, username, or an arbitrary database primary key. RPs should use the iss + sub pair as the identity key per OIDC.

## 5. Enabling the OIDC UserInfo Endpoint in Spring Authorization Server

The UserInfo endpoint belongs to OIDC. OIDC must be enabled on OAuth2AuthorizationServerConfigurer:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer -> authorizationServer
            .oidc(oidc -> oidc
                .userInfoEndpoint(userInfo -> userInfo
                    .userInfoMapper(userInfoMapper)
                )
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This is the configuration skeleton for the Authorization Server filter chain. The application also needs beans such as RegisteredClientRepository, OAuth2AuthorizationService, AuthorizationServerSettings, JWKSource<SecurityContext>, login chain, and consent flow per use case.

### 5.1. UserInfo Requires JwtDecoder

In the standard Spring Authorization Server 1.5.x UserInfo endpoint configuration, OIDC automatically configures Resource Server support to authenticate access tokens, but requires a JwtDecoder bean:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

This bean allows Resource Server support to verify JWT access tokens before requests reach the mapper. JWKSource must provide appropriate signing keys and be managed securely. Do not confuse the JwtDecoder verifying incoming UserInfo access tokens with the mapper reading claims.

### 5.2. Two Common SecurityFilterChains

A deployment typically has a high-priority Authorization Server filter chain matching protocol endpoints; an application filter chain handles login, sessions, consent pages, and remaining routes.

UserInfo requests carry a Bearer token, not a browser login session. If the matcher/order is wrong, requests may be redirected to form login or handled by the application chain as a regular endpoint.

### 5.3. UserInfo URL

RPs should read the URL from userinfo_endpoint in OpenID Provider Configuration rather than hardcoding it. The endpoint must use HTTPS in real deployments. If changing the public host, context path, or reverse proxy, discovery and runtime routes must stay synchronized.

## 6. What Extension Points Does OidcUserInfoEndpointConfigurer Have?

OidcUserInfoEndpointConfigurer allows customizing the pre-processing, main processing, and post-processing stages of a UserInfo request.

| API | Role | When to Use? |
|---|---|---|
| userInfoRequestConverter(...) | Adds an AuthenticationConverter | Request format needs extension |
| userInfoRequestConverters(...) | Manipulates the default and custom converter list | Adjust ordering or replace a converter |
| authenticationProvider(...) | Adds an AuthenticationProvider | Handle a custom authentication type |
| authenticationProviders(...) | Manipulates the provider list | Add, remove, or customize providers |
| userInfoResponseHandler(...) | AuthenticationSuccessHandler | Customize HTTP success response |
| errorResponseHandler(...) | AuthenticationFailureHandler | Customize OAuth2 error response |
| userInfoMapper(...) | Function<OidcUserInfoAuthenticationContext, OidcUserInfo> | Map authenticated context into UserInfo claims |

### 6.1. Pre-processing: Request Converter

The internal default converter pulls the Authentication from SecurityContext and constructs an OidcUserInfoAuthenticationToken with the corresponding principal. Most applications do not need to write a custom converter for standard requests.

Add a converter only when a specific protocol extension or specialized request handling has been designed. A converter should not query the profile database directly, decide claims, or bypass access-token authentication.

### 6.2. Main Processing: Authentication Provider

The default provider is OidcUserInfoAuthenticationProvider, constructed with OAuth2AuthorizationService. It processes OidcUserInfoAuthenticationToken, links the Bearer access token to the authorization, and uses the mapper to create OidcUserInfo.

In Spring Authorization Server 1.5.8, this provider is final; it has setUserInfoMapper(...), and the configurer exposes the userInfoMapper(...) API to set the mapper. Normally there is no need to subclass the provider or replace the entire authentication flow just to change claims.

### 6.3. Post-processing: Response and Error Handlers

userInfoResponseHandler writes the UserInfo response after the provider authenticates successfully. errorResponseHandler writes the OAuth2 error when authentication fails. If you only need to change claim data, use the mapper and keep the default response handler.

Writing a custom response handler means the application is responsible for preserving exact JSON serialization, content type, status codes, and error semantics. Never use a handler to bypass token validation or turn an invalid request into a success.

## 7. What Data Does OidcUserInfoAuthenticationContext Contain?

The mapper receives an OidcUserInfoAuthenticationContext. This context provides:

| API | Contents |
|---|---|
| getAuthentication() | Request's OidcUserInfoAuthenticationToken |
| getAccessToken() | OAuth2 access token used to call UserInfo |
| getAuthorization() | OAuth2Authorization containing the OidcIdToken and OAuth2AccessToken linked to the bearer token |
| get(key) / hasKey(key) | Additional context attributes if present |

This enables the mapper to read the subject from the stored ID Token/authorization, read the access token's scopes, retrieve claims already in the ID Token, query a profile from a database or domain service, and decide which claims may appear in the response.

### 7.1. Authentication Token and Principal

OidcUserInfoAuthenticationToken holds an authenticated Authentication as its principal and may contain OidcUserInfo after provider processing. Do not treat a raw access token or request parameter as a trusted profile data source.

When the access token is a JWT and resource-server support creates a JwtAuthenticationToken, the mapper can read JWT claims from the principal. This is an option; it does not mean you should copy all access token claims into UserInfo.

### 7.2. The Authorization Record Is the Key Link

getAuthorization() gives the mapper access to the authorization that issued the token. This is useful for linking the exact subject, ID Token, and scopes. Do not look up users by a caller-supplied claim or by an unverified email.

## 8. How Does the Default userInfoMapper Work?

By default in Spring Authorization Server:

1. The UserInfo filter receives the Bearer access token and validates it using Resource Server support.
2. The provider looks up the corresponding authorization in OAuth2AuthorizationService.
3. The internal mapper extracts standard claims from the ID Token.
4. Claims are selected based on the scopes requested in the authorization.
5. The provider builds OidcUserInfo; the success handler returns the JSON response.

This fits when the ID Token already contains the required standard claims and the application wants to share the same claim source between the ID Token and UserInfo.

### 8.1. When Is Default Mapping Sufficient?

If the application already adds name, email, email_verified, or appropriate standard claims to the ID Token, and the authorization scopes determine which claims are shared, the default mapper is usually the simplest option.

### 8.2. When Is a Custom Mapper Needed?

A custom mapper is useful when UserInfo needs to read the latest profile data from a database, when certain claims should be returned only via UserInfo, when claims must be filtered by tenant/client policy, when data lives in LDAP/a domain service, or when data structures must be transformed into OIDC standard claims.

Never use a custom mapper merely to copy all claims from a token into JSON. Doing so can expose internal claims, authorization metadata, or information not intended for the RP.

## 9. Customize the ID Token or the UserInfo Mapper?

Spring Authorization Server documentation guides that the preferred way to customize UserInfo is adding standard claims to the ID Token; the default mapper can then consume those claims by scope. When you need to customize the entire UserInfo response or fetch dynamic data, use userInfoMapper.

| Requirement | Approach |
|---|---|
| Claims needed in both ID Token and UserInfo | OAuth2TokenCustomizer<JwtEncodingContext> for ID Token |
| Claims needed only in UserInfo | userInfoMapper |
| Claims fetched from a domain service at UserInfo request time | userInfoMapper + service |
| Changing HTTP headers/serialization | userInfoResponseHandler |
| Changing how UserInfo requests are authenticated | Purpose-built Authentication converter/provider |

### 9.1. Adding Claims to the ID Token

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> idTokenCustomizer(
        UserInfoService userInfoService) {

    return context -> {
        if (OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            OidcUserInfo userInfo =
                userInfoService.loadUser(context.getPrincipal().getName());
            context.getClaims().claims(claims ->
                claims.putAll(userInfo.getClaims()));
        }
    };
}
~~~

This is the illustrative approach from the Spring guide. In production, the service must return claims per granted scopes/consent and must not embed excessive PII into the ID Token. OidcUserInfo must maintain a consistent subject.

### 9.2. When the ID Token Becomes Too Large

The ID Token is received by the RP in the token response and may be stored in sessions/cookies or passed across components. Putting all profile information into the ID Token increases its size and the amount of PII distributed. Include only claims the RP truly needs at authentication time; profile data can be fetched via UserInfo when needed.

## 10. Writing userInfoMapper According to Scope and Consent

A custom mapper should perform these steps:

1. Retrieve the authorization and ID Token bound to the current access token.
2. Determine the stable subject from the ID Token/authorization.
3. Retrieve the scopes of the granted access token.
4. Look up the profile from a trusted source using the subject.
5. Put only claims belonging to permitted scopes and policies into the response.
6. Always add sub matching the ID Token.
7. Omit fields that lack data or are not permitted to be disclosed.

Illustrative mapper example:

~~~java
Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper(
        UserInfoService userInfoService) {

    return context -> {
        OAuth2Authorization authorization = context.getAuthorization();
        OidcIdToken idToken = authorization
            .getToken(OidcIdToken.class)
            .getToken();

        String subject = idToken.getSubject();
        Set<String> scopes = context.getAccessToken().getScopes();
        UserProfile profile = userInfoService.loadBySubject(subject);

        Map<String, Object> claims = new LinkedHashMap<>();
        claims.put("sub", subject);

        if (scopes.contains(OidcScopes.PROFILE)) {
            putIfPresent(claims, "name", profile.name());
            putIfPresent(claims, "given_name", profile.givenName());
            putIfPresent(claims, "family_name", profile.familyName());
            putIfPresent(claims, "preferred_username",
                profile.preferredUsername());
            putIfPresent(claims, "picture", profile.pictureUrl());
        }

        if (scopes.contains(OidcScopes.EMAIL)) {
            putIfPresent(claims, "email", profile.email());
            putIfPresent(claims, "email_verified",
                profile.emailVerified());
        }

        if (scopes.contains(OidcScopes.PHONE)) {
            putIfPresent(claims, "phone_number", profile.phoneNumber());
            putIfPresent(claims, "phone_number_verified",
                profile.phoneNumberVerified());
        }

        if (scopes.contains(OidcScopes.ADDRESS)) {
            putIfPresent(claims, "address", profile.address());
        }

        return new OidcUserInfo(claims);
    };
}

private static void putIfPresent(
        Map<String, Object> claims, String name, Object value) {
    if (value == null) {
        return;
    }
    if (value instanceof String text && text.isBlank()) {
        return;
    }
    claims.put(name, value);
}
~~~

UserInfoService and UserProfile are application-defined domain types. The code illustrates scope-based claim authorization; add handling for authorization records missing an ID Token, non-existent users, revoked consent, and per-RegisteredClient policies. Never let an infrastructure exception turn into a response containing default claims.

### 10.1. Do Not Rely Only on Requested Scopes

The initial request may ask for many scopes, yet the user or policy may not approve all of them. The mapper must rely on the scopes actually attached to the issued access token/authorization, not a scope query string manually read from the UserInfo request.

### 10.2. Client-Specific Disclosure Policy

The same subject may log in across multiple RPs. One RP needs email, while another needs only the subject. You can apply policy based on the RegisteredClient linked to the authorization, but never use an arbitrary client ID from the UserInfo request to decide what data is disclosed.

### 10.3. Claims Request Parameter

OIDC Core includes a mechanism for requesting fine-grained claims via the claims request parameter. Do not assume that merely receiving the context means the application automatically supports all individual claim requests. If you need to implement these semantics, store/read the corresponding request context, validate requests against consent/policy, and test separately. Default scope-based mapping is a separate mechanism.

## 11. Configuring userInfoMapper via the Configurer

Example wiring the mapper into the UserInfo endpoint:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http,
        UserInfoService userInfoService) throws Exception {

    Function<OidcUserInfoAuthenticationContext, OidcUserInfo> mapper =
        userInfoMapper(userInfoService);

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer -> authorizationServer
            .oidc(oidc -> oidc
                .userInfoEndpoint(userInfo -> userInfo
                    .userInfoMapper(mapper)
                )
            )
        )
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This example focuses on the configuration API. In a real codebase, you can extract the mapper into a separate bean for easier unit testing, service injection, and dependency management. Do not create a singleton mapper holding mutable state across requests.

### 11.1. Keep Default Converters/Providers When No Change Is Needed

If only customizing the mapper, keep the default request converter, provider, success handler, and failure handler. Use userInfoRequestConverters(...), authenticationProviders(...), userInfoResponseHandler(...), or errorResponseHandler(...) only when there is an explicit requirement.

### 11.2. Modifying the Provider List

The configurer provides access to the default provider list to add/remove/customize. However, the default provider OidcUserInfoAuthenticationProvider is final. If replacing the provider, the application must preserve bearer token verification, authorization linking, token checks, and response claim creation itself. Replacing the provider merely to change claims is usually unnecessary; userInfoMapper is the intended API.

## 12. RegisteredClient and OIDC Scopes

RegisteredClient must permit the OIDC scopes that the RP will request:

~~~java
RegisteredClient client = RegisteredClient.withId("portal-web-id")
    .clientId("portal-web")
    .clientSecret(passwordEncoder.encode(clientSecret))
    .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
    .redirectUri("https://portal.example.com/login/oauth2/code/portal-web")
    .scope(OidcScopes.OPENID)
    .scope(OidcScopes.PROFILE)
    .scope(OidcScopes.EMAIL)
    .clientSettings(ClientSettings.builder()
        .requireAuthorizationConsent(true)
        .build())
    .build();
~~~

This is an example confidential client for Authorization Code Flow. Public clients must be configured appropriately with PKCE and never assigned a dummy client secret. The consent requirement depends on UX and policy; if consent is enabled, the consent page must persist the user-approved scope selections.

### 12.1. Registering a Scope Does Not Mean Every Claim Is Returned

RegisteredClient.scope(...) permits the client to request a scope. It does not fabricate user profiles, verify email/phone, or force the OP to return all claims. The mapper/domain service must still filter claims by available data and policy.

### 12.2. Client Requesting Specific Scopes

~~~http
GET /oauth2/authorize?response_type=code&client_id=portal-web&scope=openid%20profile%20email&redirect_uri=https%3A%2F%2Fportal.example.com%2Fcallback&state=STATE_VALUE&code_challenge=CHALLENGE&code_challenge_method=S256
~~~

The authorization request needs appropriate protective parameters such as state, PKCE, and a registered redirect URI. After consent, the access token should contain only the actually granted scopes.

## 13. JWT Access Tokens and UserInfo Data

In a typical Spring Authorization Server setup, the UserInfo endpoint uses Resource Server support to verify JWT access tokens; hence JwtDecoder is a mandatory bean for the built-in endpoint.

Several data sources can be used by the mapper:

| Source | Advantages | Notes |
|---|---|---|
| Claims in ID Token/authorization | Data consistent with the issued authorization | Snapshot at token issuance time |
| Claims in JWT access token | Can read from JwtAuthenticationToken and custom access token claims | Access token may carry internal/resource claims not meant for UserInfo |
| Domain service/database | Freshest profile and specialized data | Requires authorization, latency budget, caching, and error handling |
| LDAP/external identity service | Integrates with existing identity systems | Do not let slow dependencies hang the endpoint |

### 13.1. Mapper Based on JWT Principal

The Spring guide shows obtaining JwtAuthenticationToken from OidcUserInfoAuthenticationToken.getPrincipal() and building OidcUserInfo from JWT claims. This is concise when the JWT access token already contains the exact claims to return.

~~~java
Function<OidcUserInfoAuthenticationContext, OidcUserInfo> mapper =
    context -> {
        OidcUserInfoAuthenticationToken authentication =
            context.getAuthentication();
        JwtAuthenticationToken principal =
            (JwtAuthenticationToken) authentication.getPrincipal();

        Map<String, Object> claims =
            new HashMap<>(principal.getToken().getClaims());

        return new OidcUserInfo(claims);
    };
~~~

This illustrates the Spring API. In production, do not copy all claims like this if the access token contains aud, internal roles, tenant metadata, policy flags, or Resource Server-only data. Use an allowlist and always ensure sub matches the ID Token.

### 13.2. Opaque Access Tokens

Spring Authorization Server 1.5.x's built-in UserInfo endpoint requires JwtDecoder and validates access tokens via Resource Server JWT support. If the architecture requires opaque access tokens, evaluate a dedicated Resource Server/introspection integration or suitable implementation; do not assume the built-in UserInfo filter understands all opaque tokens automatically just because the Authorization Server has an introspection endpoint.

## 14. Consent, Privacy, and Profile Data

UserInfo responses may contain personally identifiable data. Design disclosure according to the **data minimization** principle:

- Return only claims belonging to granted scopes/claims requests;
- Check consent and client policy;
- Do not return internal database IDs if they are not public subject identifiers;
- Do not return inaccurate email/phone verification statuses;
- Do not return full street addresses to RPs that do not need them;
- Do not use the mapper to bypass stored consent;
- Support consent revocation per the application's authorization lifecycle.

### 14.1. Consent and Granted Scopes

The consent UI may present profile, email, address, and phone as clear information groups. When a user approves only openid profile, the mapper must not return email simply because email exists in the database.

If consent is revoked after an access token has been issued, define the effective policy: revoke the authorization/access token, bound token lifetime, or look up current consent in the mapper. Do not assume changing consent automatically alters all already-issued access tokens.

### 14.2. Do Not Put PII into Logs

Do not log raw UserInfo JSON, access tokens, emails, phone numbers, addresses, or full claims in production. You may log request correlation ID, authenticated client ID, pseudonymized subject, scope names, status, and latency per privacy policy.

### 14.3. Do Not Return Claims with Fake Values

Do not return email_verified=true if unverified. Do not return phone_number_verified=true by default. Do not fabricate placeholder names/avatars for missing data. Absent or unpermitted claims should be omitted.

## 15. UserInfo Response Handler and Error Handler

userInfoResponseHandler is responsible for converting the authentication into an HTTP response. Spring Authorization Server's default success handler writes OidcUserInfo as a UserInfo response.

Customize the response handler only if needed to:

- Add headers/correlation metadata;
- Apply specialized registered/supported serialization;
- Audit success without logging PII;
- Adjust cache policy per privacy requirements.

### 15.1. Do Not Compute Claims in the Success Handler

The success handler should not query the database itself, determine the subject, or add claims after the mapper. Keep data logic inside the mapper/domain service so it is easy to unit test and guarantees responses follow a single policy.

### 15.2. Error Response

errorResponseHandler handles OAuth2AuthenticationException. Common errors:

| Case | Typical Result |
|---|---|
| Missing access token | 401 / Bearer challenge |
| Bad signature, expired, or invalid token | 401 invalid_token |
| Token lacks sufficient scope per policy | 403 insufficient_scope when appropriate |
| Authorization record missing/unlinked | Request rejected |
| Domain service failure | Appropriate server error, no speculative claims returned |

Do not turn a user lookup error into a success response with only sub if doing so masks an outage or violates the application contract. Choose clear semantics: optional claims may be omitted; failures preventing accurate subject/authorization resolution must fail closed.

## 16. Verifying Subject Consistency at the Relying Party

The RP is responsible for verifying the UserInfo response upon receipt:

1. Verify the ID Token: signature, iss, aud, exp, nonce, and applicable OIDC checks.
2. Call UserInfo using the access token received from the token response.
3. Verify TLS/endpoint trust.
4. Parse JSON claims.
5. Compare userinfo.sub against id_token.sub by exact string match.
6. If they differ, discard the entire UserInfo response.
7. If they match, use only claims the RP is permitted to store/display.

### 16.1. Why Check sub Even When TLS and Tokens Are Valid?

An access token could be substituted or mistakenly bound to another authorization. Verifying the ID Token signature does not by itself prove the UserInfo response refers to the same subject. An exact sub match prevents the RP from merging the wrong user's profile.

### 16.2. Do Not Merge Claims Before Checking

Never update the local profile from UserInfo and compare sub afterward. Verify the subject first, then accept any claims. On mismatch, discard the entire response and log an appropriate security event.

## 17. Testing the UserInfo Endpoint with MockMvc

Integration tests should run through the real SecurityFilterChain and provider, using a valid JWT access token paired with an authorization record stored in OAuth2AuthorizationService.

### 17.1. Positive Test with Bearer Token

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OidcUserInfoEndpointTests {

    @Autowired
    MockMvc mvc;

    @Test
    void returnsUserInfoForValidOidcAccessToken() throws Exception {
        String accessToken = fixtureOidcAccessToken(
            "user-42", Set.of("openid", "profile", "email"));

        mvc.perform(get("/userinfo")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + accessToken)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.sub").value("user-42"))
            .andExpect(jsonPath("$.name").value("Nguyen Van An"))
            .andExpect(jsonPath("$.email").value("an@example.com"));
    }
}
~~~

This is a test skeleton. fixtureOidcAccessToken(...) must create a JWT signed with a test key trusted by JwtDecoder, while persisting an authorization containing the corresponding access token and ID Token in OAuth2AuthorizationService. The /userinfo URL must match the endpoint matcher of the deployment under test.

### 17.2. Negative Test Without Token

~~~java
@Test
void rejectsRequestWithoutBearerToken() throws Exception {
    mvc.perform(get("/userinfo")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isUnauthorized());
}
~~~

Verify the endpoint is not open to anonymous access or falling through to HTML form login when the client requests JSON.

### 17.3. Negative Test with Invalid Token

~~~java
@Test
void rejectsInvalidAccessToken() throws Exception {
    mvc.perform(get("/userinfo")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer NOT_A_VALID_JWT")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isUnauthorized());
}
~~~

You can add cases for expired tokens, bad signatures, wrong issuers, and invalidated authorization records. Do not mock only the mapper, as you need to verify the token authentication filter works.

### 17.4. Testing Scope-Based Claims Filtering

Create two authorization fixtures:

- Token A has openid profile;
- Token B has openid email.

Expected:

- Both responses include sub;
- Token A has permitted profile claims and no email;
- Token B has permitted email claims and no profile claims;
- email_verified reflects actual state;
- Missing claims are omitted, not returned as null/empty.

### 17.5. Testing Subject Consistency

Create an ID Token with sub=user-42, but deliberately configure the test UserInfo mapper to return sub=user-84. In the RP integration test, the entire response must be discarded and no claims merged into the local account. This is a critical test against token substitution.

### 17.6. Testing the Mapper and Domain Service

Dedicated unit tests for the mapper:

- ID Token/authorization missing subject;
- User profile does not exist;
- Scope not granted;
- Unverified email;
- Profile with null/blank fields;
- Domain service timeout;
- Client not permitted to receive sensitive claims;
- Pairwise subject preserved.

Keep mapper tests separate from HTTP tests to isolate whether bugs lie in mapping policy or the filter chain.

## 18. Mapper Performance and Availability

UserInfo is called on the RP's login/profile retrieval request path. If the mapper runs a database query or calls an external service, that latency directly impacts login/profile retrieval.

Recommendations:

- Use queries indexed by subject identifier;
- Read only necessary columns;
- Set timeouts on LDAP/HTTP calls;
- Avoid making a separate external service call per claim;
- Add circuit breakers/bulkheads if the dependency is critical;
- Cache with explicit TTL and invalidation policies;
- Never publicly cache responses containing PII;
- Monitor latency and errors per dependency.

### 18.1. Caching by Subject and Authorization Context

If caching profile data, the cache key should incorporate subject/tenant and relevant policy context. Never cache a complete UserInfo response and share it across RPs if claims are restricted differently per client or consent.

### 18.2. Live Data or Snapshot?

Choose clear semantics:

- **Snapshot:** claims come from the ID Token/authorization at token issuance time; stable over the token's lifetime.
- **Live profile:** mapper reads the current database; profile changes appear immediately in the next UserInfo call.

Do not mix both semantics without defining precedence. The subject must remain stable even when profile data changes.

## 19. Common Implementation Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Forgetting to enable .oidc(...) | No UserInfo endpoint | Enable OIDC configurer |
| Missing JwtDecoder bean | UserInfo resource-server authentication fails | Configure a decoder matching the JWK source |
| Sending ID Token to UserInfo | Wrong credential type | Send access token |
| Sending token in query string | Token leaks via URL/logs | Use Authorization Bearer header |
| Mapper omits sub | Violates OIDC Core | Always include subject from authorization/ID Token |
| Mapper generates a sub different from ID Token | RP may bind the wrong user | Preserve original subject, test exact match |
| Copying all JWT claims | Leaks internal claims/PII | Use an allowlist |
| Relying on requested scopes instead of granted | Returns ungranted claims | Use scopes attached to access token/authorization |
| Returning email_verified=true by default | Falsely asserts verification state | Read status from authoritative source |
| Mapper queries by email | Unstable subject, risk of account mix-up | Look up by subject |
| Custom success handler writes invalid JSON | RP fails to parse UserInfo | Keep default handler unless customization is required |
| Logging raw UserInfo/tokens | Leaks PII and credentials | Redact logs, audit minimal metadata |
| Using UserInfo as an account search API | Exposes data beyond OIDC consent | Design a separate business API |

## 20. Operations and Monitoring

Monitor the endpoint without recording sensitive data:

| Metric/Event | Purpose |
|---|---|
| oidc_userinfo_requests_total | Request count by outcome |
| oidc_userinfo_authentication_failures_total | Bad/expired/invalid token failures |
| oidc_userinfo_mapper_duration | Time spent mapping claims |
| oidc_userinfo_profile_lookup_errors | Database/LDAP/profile service errors |
| oidc_userinfo_claims_count | Track number of returned claims |
| oidc_userinfo_scope_distribution | Distribution of granted scopes |
| oidc_userinfo_subject_mismatch | RP-side security event when mismatch is detected |

Never put raw subjects, emails, phone numbers, access tokens, or full UserInfo JSON into metric labels. Use correlation IDs and pseudonymous identifiers per privacy policy.

### 20.1. Rate Limiting

UserInfo is a protected resource, yet can still be abused by a client or leaked token. Requests can be rate-limited by client, subject, token family, or IP per policy. Do not use IP as the sole identifier since clients may sit behind NAT/proxies.

### 20.2. Caching and HTTP Headers

UserInfo responses may contain PII. Consider Cache-Control: no-store or an appropriate private cache policy to prevent shared proxies/browsers from caching user data. If replacing the default response handler, verify actual headers via integration tests.

### 20.3. Data Access Audit

An organization may give End-Users visibility into which RPs accessed their UserInfo data and when. Audits must identify the authenticated client and scope range while bounding retention and access to audit logs.

## 21. Production Checklist

1. **OIDC enabled:** Is OAuth2AuthorizationServerConfigurer.oidc(...) enabled?
2. **Discovery:** Does userinfo_endpoint publish the right HTTPS URL?
3. **JWT validation:** Is a JwtDecoder bean present and trusting the right signing keys/issuer?
4. **Bearer token:** Does the endpoint accept only access tokens via the Bearer scheme?
5. **Authorization:** Is the token tied to an OIDC authorization with openid scope and appropriate scopes?
6. **Subject:** Does the mapper always return sub from the original ID Token/authorization?
7. **RP validation:** Does the client check exact sub match with the ID Token and discard on mismatch?
8. **Scopes:** Are claims restricted by granted scopes and consent?
9. **PII:** Are only minimal claims returned, with no internal attributes leaked?
10. **Verification flags:** Are email_verified/phone_number_verified sourced from real state?
11. **Mapper:** Are subject lookup, timeouts, and error handling clear?
12. **Provider:** Is the default provider retained unless semantics must change?
13. **Response:** Are JSON content type, headers, and error semantics accurate?
14. **Transport:** HTTPS, no tokens passed in URLs?
15. **Logging:** No tokens, raw UserInfo, or PII logged?
16. **Testing:** Positive/negative, scope filtering, subject mismatch, expired/bad signature?
17. **Performance:** Do database/external lookups have timeouts, indexes, and cache policies?
18. **Operations:** Metrics, auditing, rate limiting, and incident handling?

## 22. Applied Exercises

**Scenario A — Subject mismatch:** ID Token has sub=user-42, UserInfo mapper returns sub=user-84. How must the RP handle this? Why is it forbidden to overwrite the sub claim and keep the other claims?

**Scenario B — Scope filtering:** RP requests openid profile email, but consent grants only openid profile. May the mapper return email from the database? Design a test proving it.

**Scenario C — UserInfo from database:** A mapper queries LDAP for name, email, and phone. How do you bound timeouts, avoid returning unverified claims, and handle LDAP unavailability?

**Scenario D — Oversized ID Token:** The team adds full profile, address, and phone to the ID Token so UserInfo is unnecessary. Analyze the privacy/size risks and the trade-off between a token customizer and a UserInfo mapper.

**Scenario E — Opaque access tokens:** The deployment switches access tokens from JWT to opaque while keeping the built-in UserInfo filter chain. What must be evaluated regarding Spring Authorization Server's JwtDecoder and Resource Server support?

**Scenario F — Pairwise subject:** A user logs into two RPs and receives two different sub values. What must the mapper guarantee so each RP's UserInfo still matches its ID Token?

**Hints:** A must discard the entire response; B returns only claims for actually granted scopes; C needs timeouts, circuit breakers, authoritative verification flags, and clear fail policies; D should keep ID Tokens lean and load appropriate claims via UserInfo; E built-in endpoint requires JwtDecoder/JWT resource-server support so a different integration must be designed for opaque tokens; F preserve the subject bound to each RP's authorization rather than generating a new subject.

## 23. Summary

OidcUserInfoEndpointConfigurer is Spring Authorization Server's configuration point for the UserInfo endpoint. It exposes converters, providers, success/error handlers, and userInfoMapper. For most applications, keep the default request converter/provider/handlers and customize the mapper when claim changes are needed.

OidcUserInfoAuthenticationContext provides the authentication, access token, and authorization containing both the ID Token and access token. The mapper can extract standard claims from the ID Token, read granted scopes, or call a domain service to load the profile. Every decision to release claims must rest on trusted authorization/consent and policy.

The UserInfo endpoint is an OAuth2 protected resource requiring a Bearer access token. A Spring Authorization Server 1.5.x setup requires OIDC enabled and a JwtDecoder bean. The RP must verify that sub in UserInfo matches sub in the ID Token exactly; otherwise, the entire response must be discarded.

Designing a secure mapper means keeping sub stable, filtering claims by scopes/consent, hiding PII/internal attributes, bounding dependency behavior, and testing both positive and negative flows. That way, UserInfo serves as a consistent, operable, and extensible OIDC profile interface that protects End-User privacy.

## 24. References

- [OpenID Connect Core 1.0 incorporating errata set 2 — Section 5.3 UserInfo Endpoint](https://openid.net/specs/openid-connect-core-1_0.html): UserInfo request/response, Bearer access token, sub matching, standard claims, and privacy.
- [OpenID Connect Core 1.0 — Section 5.4 Requesting Claims using Scope Values](https://openid.net/specs/openid-connect-core-1_0.html#ScopeClaims): mapping profile, email, address, and phone to standard claims.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Authorization Bearer header and protected resource error semantics.
- [Spring Authorization Server — How-to: Customize the OpenID Connect 1.0 UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): enabling the UserInfo endpoint, ID Token customization, and userInfoMapper.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OidcUserInfoEndpointConfigurer, defaults, and endpoint filter.
- [Spring Authorization Server API — OidcUserInfoEndpointConfigurer](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OidcUserInfoEndpointConfigurer.html): configuration methods and userInfoMapper.
- [Spring Authorization Server API — OidcUserInfoAuthenticationContext](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcUserInfoAuthenticationContext.html): context attributes, access token, and authorization.
- [Spring Authorization Server API — OidcUserInfoAuthenticationProvider](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcUserInfoAuthenticationProvider.html): default provider and setUserInfoMapper.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT authentication and JwtDecoder.
