# UserInfo Endpoint and Valid Access Token Requirements

## 1. Context and Goals

In the **OIDC UserInfo** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson explains how an OIDC Client retrieves user information from the **UserInfo Endpoint**, the conditions an Access Token must satisfy to be accepted, and how Spring Authorization Server validates the request and returns the appropriate claims.

This content aligns with the module goal: **learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application**.

Imagine a user logging into a Portal application using the Authorization Code Flow. The Portal receives an ID Token and an Access Token. The ID Token provides claims identifying the user to the client; the Access Token allows the Portal to call the UserInfo Endpoint to retrieve additional authorized profile information, such as display name or verified email.

Some common mistakes:

- Sending the ID Token to the UserInfo Endpoint instead of the Access Token.
- An Access Token that is not yet expired, but lacks the openid scope.
- Using a token from a different tenant or issuer.
- UserInfo returning a sub different from the sub in the ID Token, yet the client still uses the data.
- The mapper returning email, phone number, or address even though the user has not granted permission.
- The endpoint only verifying the signature while ignoring the token's revocation status.

After this lesson, you will be able to:

1. Describe the role of the UserInfo Endpoint in the OIDC Authorization Code Flow.
2. Distinguish between ID Token, Access Token, and UserInfo Response.
3. Identify the conditions for an Access Token to be accepted at the UserInfo Endpoint.
4. Understand the roles of the openid, profile, email, address, and phone scopes.
5. Configure the UserInfo Endpoint in Spring Authorization Server.
6. Write a userInfoMapper that only returns permitted claims and preserves the correct sub.
7. Test valid tokens, wrong-scope tokens, expired tokens, revoked tokens, and subject mismatch errors.

## 2. Where Does the UserInfo Endpoint Fit in OIDC?

OpenID Connect is built on top of OAuth 2.0. After the user authenticates and grants authorization, the client may receive:

- **ID Token:** A JWT containing claims about the authentication event and subject, issued for the OIDC Client.
- **Access Token:** A credential to call an authorized protected resource, which in this lesson is the UserInfo Endpoint.
- **UserInfo Response:** A set of claims about the End User returned via the UserInfo Endpoint after the Access Token is verified.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End User
    participant C as OIDC Client
    participant AS as OpenID Provider / Authorization Server
    U->>C: Start login
    C->>AS: Authorization Request (scope=openid profile email)
    AS->>U: Authentication + Consent
    U-->>AS: Authenticate and approve
    AS-->>C: Authorization Code
    C->>AS: Token Request + code_verifier
    AS-->>C: ID Token + Access Token
    C->>C: Verify ID Token
    C->>AS: GET /userinfo + Access Token
    AS->>AS: Validate token, scope, and authorization
    AS-->>C: UserInfo JSON with sub and permitted claims
    C->>C: Compare UserInfo sub with ID Token sub
~~~

The UserInfo Endpoint is an **OAuth 2.0 protected resource** provided by the OpenID Provider. The client presents an Access Token to retrieve claims about the End User. It is not a login endpoint, not a Token Endpoint, and not a place where the client sends a password.

### 2.1. Distinguishing the Three Data Types

| Component | Where is it issued? | Purpose | Who uses it? |
| --- | --- | --- | --- |
| ID Token | Token Endpoint | Confirms authentication and subject to the OIDC Client | OIDC Client |
| Access Token | Token Endpoint | Grants access to protected resources | UserInfo Endpoint and APIs authorized by the token |
| UserInfo Response | UserInfo Endpoint | Returns claims about the End User according to granted permissions | OIDC Client |

**Do not use an ID Token to call the UserInfo Endpoint.** The ID Token proves the authentication result to the client; the Access Token is the credential for accessing UserInfo.

### 2.2. UserInfo Does Not Always Need to Be Called

The ID Token may already contain all the claims the application needs. The client should only call UserInfo when it needs additional claims or needs to retrieve profile data according to the granted permissions. Calling UserInfo does not inherently make authentication stronger and does not replace verifying the ID Token's signature, issuer, audience, nonce, and expiration.

## 3. Basic Conditions for the Access Token

OIDC Core requires the client to call the UserInfo Endpoint using an Access Token issued during the OIDC process. The Access Token must be presented using a token presentation mechanism supported by the endpoint and must be verified by the server.

For a standard Bearer Access Token, the general conditions are:

1. The token was issued by the correct OpenID Provider/Authorization Server.
2. The token has a valid value, is not expired, and has not been revoked according to the state checkable by the endpoint.
3. The token was issued in an OIDC context and has the openid scope.
4. The token belongs to the correct authorization/client and satisfies the UserInfo access policy.
5. The scopes/consent in the token permit returning the requested claims.
6. The token is sent over HTTPS using the proper header scheme.

### 3.1. The openid Scope Identifies an OIDC Request

An OIDC authorization request must include the openid scope. For example:

~~~text
scope=openid profile email
~~~

openid indicates that the client is performing OpenID Connect. Other scopes represent groups of user information the client wants to receive:

- profile: basic profile claims group.
- email: email and email verification status.
- address: physical address.
- phone: phone number and verification status.

If an Access Token only has orders.read without openid, that token may be valid for calling the Orders API, but it is not an appropriate token for the UserInfo Endpoint.

### 3.2. An Unexpired Token Is Not Enough

An Access Token with an exp in the future can still be rejected if:

- Wrong issuer.
- Invalid signature.
- Token is inactive or has been invalidated.
- Missing openid scope.
- Does not belong to an authorized client/authorization.
- Wrong audience or resource policy if the implementation enforces audience checks for UserInfo.
- Token type or sender constraint is not presented properly.

Therefore, do not use "the token is not expired so UserInfo must return 200" as a testing criterion.

### 3.3. Do Not Send a Refresh Token or Authorization Code

A Refresh Token is only used to request a new Access Token at the Token Endpoint. An Authorization Code is only used for a one-time token exchange in the corresponding flow. Neither is a credential for calling UserInfo.

## 4. How to Send the Access Token to the UserInfo Endpoint

OIDC Core specifies that the UserInfo Endpoint supports HTTP GET and POST. With a Bearer token, the client sends the Access Token in the HTTP Authorization header:

~~~http
GET /userinfo HTTP/1.1
Host: login.example.com
Authorization: Bearer <access-token>
Accept: application/json
~~~

Or POST:

~~~http
POST /userinfo HTTP/1.1
Host: login.example.com
Authorization: Bearer <access-token>
Accept: application/json
Content-Length: 0
~~~

The exact public endpoint is published via OpenID Provider Configuration in the userinfo_endpoint field. Do not hard-code the path if the issuer has a custom path or the system sits behind a reverse proxy.

### 4.1. Do Not Pass the Access Token in the Query String

Do not use:

~~~http
GET /userinfo?access_token=<access-token>
~~~

Tokens in URLs easily appear in access logs, proxy logs, browser history, analytics, monitoring, and Referer headers. Use the Authorization header over TLS. Also, do not place the token in the URL of a link or redirect.

### 4.2. Sender-Constrained Access Tokens

If an Access Token is bound to a DPoP key, the client must use the DPoP scheme and DPoP Proof per RFC 9449 instead of treating it as a regular Bearer token. If the token is bound to an mTLS certificate per RFC 8705, the client must present the correct certificate on the TLS connection. These mechanisms add a proof-of-possession requirement; they do not replace issuer, scope, token state, and sub consistency checks.

## 5. UserInfo Response and the sub Claim

The UserInfo Endpoint returns a JSON object containing claims about the End User. **The sub claim is required** and must be the subject identifier of the user corresponding to the Access Token.

Example response:

~~~json
{
  "sub": "user-8f2a91",
  "name": "Nguyen An",
  "given_name": "An",
  "family_name": "Nguyen",
  "preferred_username": "an.nguyen",
  "email": "an@example.com",
  "email_verified": true,
  "locale": "vi-VN"
}
~~~

The claims in this example are only returned when they have been authorized and permitted by policy. Not every UserInfo Response needs to contain all of these fields.

### 5.1. Why Is sub Important?

sub is the unique identifier of the End User within the scope of the issuer under OIDC rules. The client uses sub to link the UserInfo Response with the user in the received ID Token.

OIDC Core specifies that the sub value in the UserInfo Response **must match the exact** sub value in the ID Token. If they differ, the client must not use the UserInfo Response.

Example:

~~~text
ID Token:
    iss = https://login.example.com
    sub = user-8f2a91

UserInfo:
    sub = user-8f2a91       -> valid subject binding

Another UserInfo:
    sub = user-44b021       -> client must discard response
~~~

Do not compare by email, username, or display name. Those attributes can change or collide.

### 5.2. Pairwise Subject Identifier

An OIDC Provider may use a pairwise subject identifier to limit the ability of different clients to correlate the same user. When using a pairwise subject:

- The subject is computed according to the sector/client policy.
- The same user across two different clients may have two different sub values.
- The ID Token and UserInfo for the same client/sector must still have the same sub.
- Do not recompute sub in the mapper per request or based on the current email.

Subject mapping must be stable, versioned, and used consistently where both the ID Token and UserInfo are issued.

## 6. Scopes and Standard Claim Groups

OIDC Core defines the relationship between scopes and UserInfo claim groups:

| Scope | Typical Claims |
| --- | --- |
| profile | name, family_name, given_name, middle_name, nickname, preferred_username, profile, picture, website, gender, birthdate, zoneinfo, locale, updated_at |
| email | email, email_verified |
| address | address (object containing formatted, street_address, locality, region, postal_code, country) |
| phone | phone_number, phone_number_verified |

openid is the mandatory scope to perform OIDC; it does not mean the server automatically returns all profile information. The profile/email/address/phone scopes must be requested and approved according to policy.

### 6.1. Requested Scopes Differ from Authorized Scopes

| Scope Set | Meaning |
| --- | --- |
| Requested scopes | What the client wishes to be granted |
| Registered client scopes | Limit of scopes the client is allowed to request |
| Consented/authorized scopes | Scopes approved by the Authorization Server after policy/consent |
| Access Token scopes | Actual permissions bound to the token |
| Claims in UserInfo | Data returned according to authorized scopes and data policy |

The UserInfo mapper should rely on the **authorized scopes of the authorization/token**, not on raw scopes from query parameters or headers sent by the client. Just because a client requests email does not mean the user consented or that the email is permitted to be disclosed.

### 6.2. Scope Is Not a Field in the UserInfo Response

Scope is generally not repeated as a claim named scope in the UserInfo Response. It is a permission bound to the Access Token. The client learns the granted scopes from the token response or authorization state; the server uses scopes to decide which claims to return.

### 6.3. Claims by Specific Request

OIDC Core also provides the claims parameter mechanism in the Authorization Request to request specific claims. If the implementation supports it, the server must process it according to the specification and consent/policy. Do not invent custom query parameters like email=true or includeSensitive=true on the UserInfo Endpoint and bypass scopes.

## 7. Access Token Verification Flow at the UserInfo Endpoint

Logically, the UserInfo Endpoint needs to:

1. Receive the Access Token according to the supported scheme.
2. Verify the token signature/issuer/time if it is a JWT, or look up its state if it is opaque.
3. Find the corresponding authorization/token.
4. Check that the token is active and not invalidated.
5. Confirm the openid scope and relevant permissions.
6. Identify the authenticated principal/subject when the authorization was granted.
7. Build UserInfo claims according to authorized scopes, consent, and data policy.
8. Ensure sub matches the exact subject of the authorization.
9. Return the response in the configured format.

~~~mermaid
flowchart TD
    A["GET/POST UserInfo + Access Token"] --> B{"Valid Authorization header?"}
    B -->|No| X["401 invalid_token"]
    B -->|Yes| C["Verify token / lookup authorization"]
    C --> D{"Token active, issuer/time valid?"}
    D -->|No| X
    D -->|Yes| E{"openid scope granted?"}
    E -->|No| Y["Reject per OIDC/provider policy"]
    E -->|Yes| F["Resolve principal + authorized scopes"]
    F --> G["Apply consent and claim release policy"]
    G --> H["Build UserInfo, always include sub"]
    H --> I["Return JSON response"]
~~~

Do not take the subject from a request parameter. The subject must come from the verified authorization. If the mapper cannot find the user profile or the account has been deleted/locked, there must be a clear policy: return minimal claims, reject the token, or handle according to account state; never replace the subject with a client-supplied value.

## 8. Configuring the UserInfo Endpoint in Spring Authorization Server

The UserInfo Endpoint is an OIDC feature. In Spring Authorization Server, OIDC must be enabled on OAuth2AuthorizationServerConfigurer.

Example filter chain configuration using the Spring Authorization Server 1.x API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

This is an illustrative filter chain; a complete application also requires a RegisteredClientRepository, OAuth2AuthorizationService, JWKSource, a user authentication chain, and other security rules. If OIDC is not enabled, the UserInfo Endpoint is not configured like a regular OAuth endpoint.

### 8.1. Endpoint URL

The default UserInfo Endpoint is typically:

~~~text
GET /userinfo
POST /userinfo
~~~

The actual public URL must be published in the OpenID Provider Configuration via the userinfo_endpoint field. When placed behind a reverse proxy, metadata must use the public scheme/host/path, for example:

~~~json
{
  "issuer": "https://login.example.com",
  "userinfo_endpoint": "https://login.example.com/userinfo"
}
~~~

If there is a context path or proxy prefix, verify that the published URL and the actual route are consistent. Do not only test /userinfo internally with MockMvc and assume the public endpoint works.

## 9. Customizing Claims with userInfoMapper

In Spring Authorization Server, OidcUserInfoEndpointConfigurer provides the userInfoMapper extension point. The mapper receives an OidcUserInfoAuthenticationContext and returns an OidcUserInfo.

The mapper should:

- Retrieve the verified authorization from the context.
- Retrieve the principal name/subject from the authorization.
- Retrieve the authorized scopes from the authorization.
- Fetch the user profile from an internal service.
- Return only claims permitted by scope/consent/policy.
- Always return the sub matching the ID Token issued to the client.

### 9.1. Example of a Scope-Controlled Mapper

The following example uses an application-defined UserProfileService:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcUserInfoAuthenticationContext;

@Configuration(proxyBeanMethods = false)
class UserInfoConfiguration {

    @Bean
    Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper(
            UserProfileService userProfileService) {

        return context -> {
            OAuth2Authorization authorization = context.getAuthorization();
            String subject = authorization.getPrincipalName();
            Set<String> scopes = authorization.getAuthorizedScopes();

            UserProfile profile = userProfileService.findBySubject(subject);
            Map<String, Object> claims = new HashMap<>();

            // OIDC Core requires sub in the UserInfo Response.
            claims.put("sub", subject);

            if (scopes.contains(OidcScopes.PROFILE)) {
                putIfPresent(claims, "name", profile.name());
                putIfPresent(claims, "given_name", profile.givenName());
                putIfPresent(claims, "family_name", profile.familyName());
                putIfPresent(claims, "preferred_username",
                        profile.preferredUsername());
                putIfPresent(claims, "locale", profile.locale());
            }

            if (scopes.contains(OidcScopes.EMAIL)
                    && profile.emailMayBeReleased()) {
                putIfPresent(claims, "email", profile.email());
                claims.put("email_verified", profile.emailVerified());
            }

            if (scopes.contains(OidcScopes.PHONE)
                    && profile.phoneMayBeReleased()) {
                putIfPresent(claims, "phone_number", profile.phoneNumber());
                claims.put("phone_number_verified",
                        profile.phoneNumberVerified());
            }

            if (scopes.contains(OidcScopes.ADDRESS)
                    && profile.addressMayBeReleased()
                    && profile.address() != null) {
                claims.put("address", profile.address());
            }

            return new OidcUserInfo(claims);
        };
    }

    private static void putIfPresent(
            Map<String, Object> claims, String name, String value) {
        if (value != null && !value.isBlank()) {
            claims.put(name, value);
        }
    }
}
~~~

UserProfileService, UserProfile, and methods like emailMayBeReleased()/addressMayBeReleased() are **illustrative business APIs defined by the application**, not built-in Spring classes. This mapper needs to be integrated into the OIDC configuration:

~~~java
authorizationServerConfigurer.oidc(oidc ->
    oidc.userInfoEndpoint(userInfo ->
        userInfo.userInfoMapper(userInfoMapper)
    )
);
~~~

Package imports/APIs can vary between Spring Authorization Server versions. Check the Javadoc of the dependency in use; do not copy a configuration snippet from another version and assume it will compile.

### 9.2. Registering the Mapper in the Filter Chain

Example of wiring it into SecurityFilterChain:

~~~java
http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
    .with(authorizationServerConfigurer, authorizationServer ->
        authorizationServer.oidc(oidc ->
            oidc.userInfoEndpoint(userInfo ->
                userInfo.userInfoMapper(userInfoMapper)
            )
        )
    );
~~~

Here userInfoMapper is a Function<OidcUserInfoAuthenticationContext, OidcUserInfo> bean injected into the configuration. Register only one intentional mapper; if there are multiple customizations, consolidate the logic to avoid ambiguous configuration bean overrides.

### 9.3. Do Not Return All Profile Claims Just Because the User Is Logged In

An authenticated user does not mean all user data should be shared with the client. The mapper must consider authorized scopes, consent, tenant, data classification, account state, and data policy. In particular, email, phone, address, and birthdate can be sensitive personal data.

## 10. Subject Consistency Between ID Token and UserInfo

This is the most important OIDC requirement at the client layer.

Suppose the ID Token is generated with:

~~~json
{
  "iss": "https://login.example.com",
  "aud": "portal-client",
  "sub": "user-8f2a91"
}
~~~

UserInfo must return:

~~~json
{
  "sub": "user-8f2a91",
  "name": "Nguyen An"
}
~~~

If the mapper uses email to look up a profile and produces a different sub, the client must discard the response. Do not bind UserInfo to an account simply because the email matches.

### 10.1. Subject Mapping Must Be Shared

In a system with pairwise subjects:

1. Determine the sector identifier or client policy when issuing the ID Token.
2. Generate a stable sub by user and sector.
3. Store or recompute the exact same mapping when UserInfo is called.
4. Do not change sub when email/username changes.
5. When a client changes its sector identifier, there must be a migration policy because the subject may change.

### 10.2. Principal Name Is Not Always Automatically the Correct OIDC sub

The example mapper using authorization.getPrincipalName() is only correct when the application has designed the principal name to serve as the ID Token subject identifier. If the ID Token customizer generates a different pairwise or opaque subject, the mapper must use the same subject mapping service instead of returning the raw principal name.

There should be a single component such as SubjectIdentifierService to generate subjects by issuer/client/sector. Both the ID Token generator and the UserInfo mapper call that component. Do not duplicate the subject algorithm in two places.

## 11. Checking Scope, Consent, and Claims Release

An authorization request might ask for:

~~~text
scope=openid profile email
~~~

The user might only approve:

~~~text
openid profile
~~~

In that case, UserInfo must only return claims according to openid profile and data policy. Do not return email simply because the client originally requested it.

### 11.1. Scope → Claim Matrix

| Granted Scope | Can Return | Do Not Infer |
| --- | --- | --- |
| openid | sub | Do not return the entire profile by default |
| profile | Profile claims permitted by policy | Do not automatically return email/phone/address without the corresponding scope |
| email | email, email_verified if available and permitted | Do not assert email_verified=true if not verified |
| phone | phone_number, phone_number_verified if available | Do not assert phone number verification without verification |
| address | address object per permitted data | Do not return internal addresses or invalid addresses |

### 11.2. Consent Can Change

If a user revokes consent after an Access Token has been issued, the system needs to decide:

- Are old tokens revoked?
- Does the UserInfo mapper read current consent on every request?
- Are claims immediately reduced when consent is revoked?
- Do Resource Servers receive revocation status or continue accepting JWTs offline?

Do not assume that deleting consent automatically invalidates all existing Access Tokens. Combine revocation policy, authorization state, and claim release policy.

### 11.3. Data Minimization

Only return claims the client actually needs. Do not return passwords, credentials, unnecessary internal user IDs, security answers, payment data, internal admin permissions, or risk-analysis attributes without clear justification.

## 12. Valid Access Tokens with JWT and Opaque Tokens

### 12.1. JWT Access Token

If the Access Token is a JWT, standard checks include:

- Valid signature against a trusted key.
- iss matches the issuer.
- Valid exp/nbf.
- Appropriate token type and profile.
- openid scope granted.
- Authorization/token state is still active per the Authorization Server's policy.

Do not merely decode the payload and trust the claims. Decoding does not verify the signature. Nor does a JWT indicate by itself whether the record in the authorization store has been invalidated if the endpoint does not check that state.

### 12.2. Opaque Access Token

An opaque token does not contain readable claims for the client. The UserInfo Endpoint looks up the token in the authorization store or an internal verification mechanism. The server determines the authorization, principal, scopes, and token state from a trusted source.

| Characteristic | JWT | Opaque |
| --- | --- | --- |
| Token payload | Can be decoded, but signature must be verified | Cannot be self-decoded |
| Authorization lookup | May need store to check state | Usually looks up store/introspection |
| Revocation | Offline verifier may not see revocation | Can be reflected via store/active state |
| UserInfo claims | Retrieved from authorization and profile service | Retrieved from authorization and profile service |

The UserInfo Endpoint does not require the client to decode the Access Token. The client only presents the token; the OpenID Provider is responsible for verifying the token and determining which claims to return.

### 12.3. Revocation and Verification Timing

If an Access Token is revoked, the UserInfo Endpoint should reject it when the authorization store/validation layer knows the token is no longer active. However, other APIs verifying JWTs offline may still accept the token until exp. Understand that each Resource Server has its own enforcement strategy.

## 13. UserInfo Endpoint Errors and HTTP Responses

Common errors:

| Scenario | Typical Response | Meaning |
| --- | --- | --- |
| Missing Access Token | 401 Unauthorized | No credential provided |
| Wrong, expired, or revoked token | 401 Unauthorized, invalid_token | Invalid token |
| Token missing required scope/permission | 403 Forbidden or scope error per policy | Insufficient token permissions |
| Token uses wrong scheme for sender-constrained flow | Authentication rejected | Client presented token improperly |
| UserInfo mapper hits internal error | 5xx per error handling | Server unable to process request |

For Bearer tokens, authentication error responses may use WWW-Authenticate: Bearer per RFC 6750. Never return stack traces, SQL errors, or sensitive user information to the client.

### 13.1. Do Not Turn UserInfo into a Public User Lookup API

Do not allow calls like:

~~~http
GET /userinfo?userId=another-user
~~~

UserInfo returns data for the subject bound to the Access Token. Do not take the subject from a path, query, body, or client-controlled custom header. If an application needs to look up another user, that is a separate business API with its own authorization policy, not UserInfo.

### 13.2. Client Must Handle sub Mismatch

If the UserInfo Response lacks sub or has a sub different from the ID Token, the client must discard the response. Do not fall back to email, username, or the name claim. This prevents binding another user's profile to the current login session.

## 14. Security and Privacy

### 14.1. HTTPS Is Mandatory

UserInfo contains user claims, potentially including email, address, and phone number. The endpoint must be accessed over TLS. Never allow tokens to travel over cleartext HTTP or insecure redirects.

### 14.2. Tokens and Claims Must Not Be Logged Raw

Do not log:

- Authorization header or Access Token.
- Full UserInfo Response.
- Email/phone/address without a clear purpose and access control.
- Client secret or related credentials.

Safe logs should record correlation ID, client ID, issuer, endpoint, validation result, scope category, and error code; limit logging the subject or use a pseudonymous identifier per policy.

### 14.3. CORS and Browser Clients

If an SPA calls UserInfo directly from the browser, configure CORS for specific origins and required methods/headers. Do not enable wildcard origins with credentials or enable broad CORS across all Authorization Server endpoints. CORS is not an authentication mechanism; the Access Token must still be verified on the server.

### 14.4. Caching and Response Headers

The UserInfo Response contains personal data. Configure an appropriate cache policy, typically avoiding shared caches or caching one user's response and serving it to another. Consider Cache-Control: no-store or an equivalent restrictive policy for sensitive data, and ensure CDNs/reverse proxies do not cache improperly.

### 14.5. Tenant Isolation

In a multi-tenant OIDC Provider:

- The subject is resolved within the Access Token's tenant/issuer.
- User profile lookup must be tenant-aware.
- An Acme Access Token must not retrieve a Zen profile.
- Scopes/consent from one tenant must not apply to another tenant.
- sub must be consistent per issuer and client/sector.

Do not use a global email as the sole lookup key across tenants if emails can collide or the same user has different profiles per tenant.

## 15. Testing the UserInfo Endpoint

Tests should go through a real Token Endpoint in a test fixture to obtain a valid Access Token, then call the UserInfo Endpoint with that token. Do not only mock the mapper and assert that it returns a Map.

### 15.1. Testing Response for a Token with openid profile

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UserInfoEndpointIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void returnsSubjectAndAuthorizedProfileClaims() throws Exception {
        String accessToken = obtainAccessToken("openid", "profile");

        mvc.perform(get("/userinfo")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sub").value("user-8f2a91"))
            .andExpect(jsonPath("$.name").value("Nguyen An"));
    }

    private String obtainAccessToken(String... scopes) {
        // Test fixture executes Authorization Code + PKCE,
        // user login/consent, and exchanges the code at the Token Endpoint.
        throw new UnsupportedOperationException("Provide the project's test flow");
    }
}
~~~

obtainAccessToken() is a placeholder for the project's fixture, not a complete implementation. Real tests must set up RegisteredClient, user, consent, authorization service, and signing key. Never hard-code production Access Tokens into tests.

### 15.2. Testing That Email Appears Only When Scope Is Granted

~~~java
@Test
void doesNotReturnEmailWhenEmailScopeWasNotAuthorized() throws Exception {
    String accessToken = obtainAccessToken("openid", "profile");

    mvc.perform(get("/userinfo")
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.sub").value("user-8f2a91"))
        .andExpect(jsonPath("$.email").doesNotExist());
}
~~~

This method is added to the test class above. The fixture must ensure email is not authorized; only checking scopes in the request without checking consent/authorized scopes is insufficient.

### 15.3. Testing Invalid Tokens

Minimum cases:

- Missing Authorization header.
- Token with invalid signature.
- Expired token.
- Invalidated/revoked token.
- Token without openid.
- Token belonging to a different issuer.
- Token presented with the wrong scheme.
- DPoP-bound token without a proof or with a proof having the wrong key/ath.
- mTLS-bound token presented over a different certificate.

Expected: endpoint rejects the request and returns no UserInfo claims.

### 15.4. Testing Subject Mismatch

Create a fixture intentionally where the ID Token has sub=user-A, while the UserInfo mapper returns sub=user-B. The client integration test must discard the response and not attach user-B's claims to user-A's session.

This is an **OIDC Client**-side test, because the server cannot guarantee the client will perform the subject comparison if client code ignores OIDC Core rules.

## 16. Complete Test Matrix

| # | Scenario | Expected Result |
| --- | --- | --- |
| 1 | Access Token has openid and profile, token active | HTTP 200; has sub and permitted profile claims |
| 2 | Access Token only has orders.read | UserInfo rejects per OIDC scope policy |
| 3 | Access Token lacks openid | Token is not treated as an OIDC UserInfo credential |
| 4 | No token sent | 401 |
| 5 | Token with invalid signature | 401 invalid_token |
| 6 | Expired token | 401 invalid_token |
| 7 | Revoked/invalidated token visible to endpoint | 401 invalid_token |
| 8 | Token has email scope but consent/policy disallows release | Email not returned |
| 9 | Token lacks email scope | email/email_verified not returned |
| 10 | Token has phone scope but profile has not verified number | phone_number_verified=true not asserted |
| 11 | UserInfo lacks sub | Response fails OIDC contract; test fails |
| 12 | UserInfo sub differs from ID Token sub | OIDC Client discards response |
| 13 | Access Token from issuer Acme calls Zen UserInfo | Rejected |
| 14 | Acme tenant Access Token looks up Zen profile | Must not happen |
| 15 | Token passed via query parameter | Insecure token transmission unsupported |
| 16 | DPoP-bound token with valid proof | Accepted per DPoP policy |
| 17 | DPoP-bound token with wrong key or ath in proof | Rejected |
| 18 | mTLS-bound token with wrong certificate | Rejected |
| 19 | User profile service error | Error handled safely, no stack trace returned |
| 20 | Metadata publishes wrong userinfo_endpoint | Public integration test fails |
| 21 | UserInfo response cached across two users | No cross-user cache leak occurs |
| 22 | CORS request from disallowed origin | Browser not allowed to read response |

### 16.1. Testing the Contract Between ID Token and UserInfo

An end-to-end OIDC test should:

1. Complete Authorization Code + PKCE.
2. Verify ID Token signature, iss, aud, exp, iat, and nonce per the flow.
3. Save sub from the ID Token.
4. Call UserInfo using the Access Token.
5. Verify the HTTP response and sub.
6. Assert userinfo.sub equals id_token.sub exactly.
7. Assert only authorized and permitted claims appear.

### 16.2. Testing Through a Reverse Proxy

Beyond MockMvc, test the public URL from outside the ingress:

- userinfo_endpoint in OIDC metadata is reachable.
- HTTPS/SNI/TLS certificate is valid.
- Proxy does not strip the Authorization header.
- Proxy does not log the token.
- Path prefix is rewritten properly.
- CORS and cache headers are appropriate.

## 17. Troubleshooting Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| /userinfo returns 404 | OIDC not enabled or wrong route/path | Check oidc(...), metadata, and reverse proxy |
| 401 even though token is not expired | Wrong signature/issuer, token revoked, token lookup failure, or wrong scheme | Check authorization state and Authorization header |
| 403 or scope error | Missing openid or policy requires another scope | Check authorized scopes and consent |
| UserInfo only returns sub | Default mapper or profile claims not configured | Configure userInfoMapper per policy |
| Email does not appear | Missing email scope, consent, or profile data | Check each layer; do not unconditionally return email |
| UserInfo sub differs from ID Token | Inconsistent subject mapping | Share a single subject identifier service |
| UserInfo returns another user's data | Mapper looks up by wrong request/email or lost tenant context | Look up by authenticated subject and make it tenant-aware |
| Acme token calls Zen UserInfo | Missing issuer/authorization isolation | Check tenant routing, issuer, and token lookup |
| Resource Server API rejects but UserInfo accepts | Two places have different validation/revocation policies | Align trust, audience, and token state strategy |
| Token in query is logged | Client sends token improperly | Only use Authorization header over HTTPS |
| UserInfo cached erroneously | Misconfigured CDN/shared cache | Disable shared cache or cache safely by identity |
| MockMvc passes but public URL fails | Wrong ingress TLS, forwarded headers, or prefix | Run end-to-end tests through the proxy |

## 18. Production Deployment Checklist

1. **OIDC enabled:** UserInfo Endpoint is configured only when OIDC support is enabled.
2. **Discovery:** userinfo_endpoint publishes the correct public HTTPS URL.
3. **Access Token:** client sends an Access Token, never an ID Token, Refresh Token, or Authorization Code.
4. **Scope:** token has openid; other claims are returned only per authorized scopes.
5. **Validation:** verify signature/issuer/time/token state per profile and policy.
6. **Subject:** sub is always present and matches the ID Token exactly.
7. **Mapper:** look up profile using the authenticated subject; never take user ID from the request.
8. **Consent:** do not infer consent from requested scopes.
9. **Privacy:** return minimal claims only; do not log raw tokens or UserInfo.
10. **Transport:** HTTPS; sender-constrained tokens use proper DPoP/mTLS proofs.
11. **Tenant:** issuer, principal, profile lookup, and authorization are all tenant-aware.
12. **Caching:** do not improperly shared-cache user responses; headers are verified.
13. **Errors:** appropriate 401/403 responses without leaking internal details.
14. **Testing:** test wrong-scope, expired, revoked, subject-mismatch, and tenant-mismatch tokens.
15. **Operations:** monitor latency/error rates, profile lookup failures, and anomalous claim access.

## 19. Exercises and Self-Assessment Questions

**Exercise A — Distinguishing tokens.** A client receives an ID Token and an Access Token. Explain which token is used to verify login, which token is used to call UserInfo, and why.

**Exercise B — Scopes.** A client requests openid profile email, but the user only approves openid profile. Design the appropriate UserInfo response and explain why email is not returned.

**Exercise C — Subject mismatch.** ID Token has sub=user-A, UserInfo has sub=user-B. What must the client do? Why cannot a matching email replace checking sub?

**Exercise D — Spring mapper.** Write a userInfoMapper that returns name only when the profile scope has been granted and email only when the email scope has been granted. Add a check ensuring sub is always present.

**Exercise E — Revocation.** A JWT Access Token is marked invalidated in the Authorization Server, but a Resource Server only verifies offline. Analyze why UserInfo can reject the token while another API still accepts it until exp.

**Exercise F — Multi-tenant.** The same email exists in both the Acme and Zen tenants. Design subject/profile lookup so an Acme Access Token cannot retrieve Zen data.

**Exercise G — End-to-end test.** Describe a test for Authorization Code + PKCE, obtaining an Access Token, calling UserInfo, and asserting userinfo.sub == id_token.sub.

**Review questions:**

1. Is the UserInfo Endpoint a protected resource or a Token Endpoint?
2. Why must an Access Token be used instead of an ID Token?
3. What does the openid scope signify?
4. Which scopes correspond to profile, email, address, and phone claims?
5. Which claim is mandatory in the UserInfo Response?
6. How must an OIDC Client handle a UserInfo sub that differs from the ID Token sub?
7. Why are requested scopes insufficient to decide which claims are returned?
8. What is the responsibility of userInfoMapper in Spring Authorization Server?
9. Why should a mapper not look up users by a query parameter?
10. Is an unexpired JWT guaranteed to be active?
11. How must a DPoP/mTLS-bound Access Token be presented?
12. Why should a UserInfo Response not be shared-cached?
13. Does deleting consent automatically revoke active Access Tokens?
14. Which tests prove that UserInfo does not leak cross-tenant data?

## 20. References

- [OpenID Connect Core 1.0 — Section 5.3, UserInfo Endpoint](https://openid.net/specs/openid-connect-core-1_0.html#UserInfo)
- [OpenID Connect Core 1.0 — Section 5.3.2, UserInfo Response](https://openid.net/specs/openid-connect-core-1_0.html#UserInfoResponse)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)

**Key takeaway:** The UserInfo Endpoint returns End User claims based on a **valid Access Token**. For OIDC, the token must be tied to an authorization with the openid scope; other claims are returned only per authorized scopes, consent, and policy. sub is always mandatory and must match the sub in the ID Token exactly. Spring Authorization Server allows customization via userInfoMapper, but the mapper must obtain the subject from the authenticated authorization, restrict claims, and preserve issuer/tenant isolation. The client must discard the UserInfo Response if the subject does not match.
