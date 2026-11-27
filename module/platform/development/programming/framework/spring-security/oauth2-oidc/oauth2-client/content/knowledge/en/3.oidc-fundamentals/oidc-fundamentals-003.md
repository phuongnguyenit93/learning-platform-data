# 3.3. ID Token, Access Token, and UserInfo: Purpose and Usage

## 1. The Problem: Does Successful Login Automatically Mean Calling Any API?

Suppose a Spring Boot application integrates OpenID Connect (OIDC) so employees can log in using an Identity Provider (IdP) account. After logging in, the application needs to know **who is using the system**, display their name and avatar, and then call a task management API.

Those three needs use different components:

1. **Identify the logged-in user:** The OIDC client validates the **ID Token** issued by the identity provider.
2. **Retrieve additional profile attributes:** The OIDC client can call the **UserInfo endpoint** with an access token accepted by the IdP.
3. **Call business APIs:** The OAuth 2.0 client sends an appropriate **Access Token** to the resource server; the API decides whether to accept the token and what permissions are granted.

OIDC is an identity authentication layer built on top of OAuth 2.0. Consequently, an OIDC login typically produces both an ID Token and an Access Token, but they **are not interchangeable**.

| Component | Question It Answers | Intended Consumer | Must Not Be Used To |
| --- | --- | --- | --- |
| **ID Token** | "Which user did the IdP just authenticate for this client?" | OIDC client | Access business APIs in place of an access token |
| **Access Token** | "Which resources is the client authorized to call within the granted scope?" | Target resource server; the OIDC UserInfo endpoint is also a protected resource | Infer on its own that the user logged in or act as an ID Token |
| **UserInfo** | "What additional attributes does the IdP provide about the authenticated user?" | OIDC client, after calling the UserInfo endpoint | Replace ID Token validation or make API authorization decisions |

**Key takeaway:** The ID Token provides authentication proof for the client; the Access Token authorizes resource access; UserInfo provides profile claims, retrieved using an Access Token.

## 2. Where Do ID Token, Access Token, and UserInfo Appear in the Flow?

With the Authorization Code flow, the browser goes through the authorization endpoint, while the Spring Boot backend exchanges the authorization code for tokens at the token endpoint. Afterwards, the client can call UserInfo:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Browser / User
    participant C as Spring Boot OIDC Client
    participant I as OIDC Provider
    participant A as Business Resource Server
    U->>C: Visit page requiring login
    C-->>U: Redirect to authorization endpoint
    U->>I: Log in and approve consent if needed
    I-->>U: Redirect back to client with authorization code
    U->>C: Callback containing code and state
    C->>I: POST token endpoint (code + PKCE)
    I-->>C: id_token + access_token (+ refresh_token if issued)
    Note over C: Validate ID Token, create principal
    opt UserInfo endpoint exists and permitted
        C->>I: GET UserInfo, Authorization: Bearer access_token
        I-->>C: JSON/JWT UserInfo containing sub and granted claims
        Note over C: Match UserInfo.sub with ID Token.sub
    end
    C-->>U: Create login session
    opt Access token intended for business API
        C->>A: Send access_token matching audience/scope
        A-->>C: Data or 401/403
    end
~~~

The token endpoint may return:

~~~json
{
  "access_token": "ACCESS_TOKEN_EXAMPLE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile email",
  "id_token": "HEADER.PAYLOAD.SIGNATURE",
  "refresh_token": "OPTIONAL_REFRESH_TOKEN"
}
~~~

This is an illustrative example, not real tokens. In the OIDC Authorization Code flow, **ID Token and Access Token** are two separate fields in the token response. **UserInfo is not a third token** in this response: it is an endpoint and the response payload returned when the client calls that endpoint. Refresh Token is an optional component used to request new tokens when permitted.

An access token usable for UserInfo is not necessarily accepted by other business APIs. A token must have the audience, scope, and bindings matching the target resource server; the system may require a separate token for the API.

## 3. ID Token: Authentication Proof for the OIDC Client

### 3.1. What Is an ID Token?

An **ID Token** is a JSON Web Token (JWT) issued by the OpenID Provider containing **claims** about the user authentication event. The ID Token can be signed and, depending on configuration, encrypted. In a standard flow, Spring Security validates the ID Token and builds a principal for the application to use.

A decoded payload might look like this:

~~~json
{
  "iss": "https://id.example.com/realms/company",
  "sub": "c47a12f8-opaque-subject",
  "aud": "spring-web-client",
  "exp": 1925000300,
  "iat": 1925000000,
  "auth_time": 1924999900,
  "nonce": "nonce-from-authorization-request",
  "name": "Nguyen An",
  "email": "an@example.com",
  "email_verified": true
}
~~~

The timestamps in the example are illustrative only; real timestamps are Unix time in seconds. A decoded payload **does not mean the JWT is trustworthy**: the client must verify signature, issuer, audience, expiration, and related constraints before using any claims.

### 3.2. Claims to Understand

| Claim | Role | Implementation Notes |
| --- | --- | --- |
| `iss` (issuer) | Identifier of the issuing provider | Must match the configured/trusted issuer using exact comparison |
| `sub` (subject) | User identifier issued by the issuer | Stable identifier within the issuer/client policy scope; never assume equality across issuers |
| `aud` (audience) | Client for which the ID Token was issued | Must contain the application's `client_id`; never assume it is an API URL |
| `exp` (expiration) | Time when the token expires | Must verify the token is still valid; handle reasonable clock skew |
| `iat` (issued at) | Time when the token was issued | Helps evaluate context and freshness policies |
| `nonce` | Binds the token to the sent OIDC request | When the request sent a nonce, the returned nonce must be verified |
| `auth_time` | Time when the user actually authenticated | Important when requiring re-authentication or `max_age` |
| `azp` (authorized party) | Designated client when required | Especially relevant when the ID Token has multiple audiences |
| `acr`, `amr` | Authentication context / methods | Only use when provider and application have an agreed contract on meaning |
| `name`, `picture`, `email` | Profile claims, may be present | Not required to appear in the ID Token |

`iss`, `sub`, `aud`, `exp`, and `iat` are foundational ID Token claims per OIDC Core. Profile claims such as `name`, `email`, or `picture` depend on the provider, scopes, and claim policies; **do not assume they are always present**, even if the client requests `profile` or `email`.

### 3.3. Validating the ID Token for Its Intended Purpose

Before accepting an ID Token, the OIDC client must perform checks appropriate for the flow and provider, including:

1. **Trusted issuer:** `iss` matches the registered issuer. Never take an arbitrary issuer from a token and automatically trust it.
2. **Signature / encryption:** verify the signature with an allowed key and algorithm from the provider, fetching keys from the proper JWKS source for signed JWTs; decrypt and validate per rules for encrypted JWTs.
3. **Audience:** `aud` must contain the application's `client_id`; handle `azp` per OIDC requirements when applicable.
4. **Timestamps:** `exp` has not passed, `iat` is reasonable; check `auth_time` if the application requires recent authentication.
5. **Transaction binding:** verify `nonce` when sent, along with other checks required by the response type/flow.
6. **Never trust claims before validation:** never make account, role, or session decisions based on a JWT that was only Base64URL-decoded.

Spring Security OIDC login handles most of these steps when `issuer-uri` and the client registration are configured properly. An application should not manually parse an unverified JWT and store `sub` into the session.

### 3.4. Subject Is the Identity Key, Not Email

A person may change their email, change their name, or have two distinct accounts sharing an email address over time. Therefore, when mapping an OIDC account to an internal user, use the **pair (`iss`, `sub`)** as the provider identity key.

For example:

~~~text
issuer                                subject                 internal_user_id
https://id.example.com/realms/a      8a72bf...               103
https://login.partner.example.org    8a72bf...               855
~~~

Two subjects with identical strings from different issuers **must not be automatically merged**. A provider may also use *pairwise subject identifiers*, meaning the same user receives a different `sub` for different clients/sectors. Never assume `sub` is an email, employee number, or global ID shared across all systems.

### 3.5. An ID Token Is Not a License to Call APIs

An API might receive an ID Token as a JWT with a valid signature, yet the `aud` of the ID Token is typically the **OIDC client ID**, not the API. An API must not accept an ID Token as an Access Token simply because it is a JWT.

~~~http
GET /orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ID_TOKEN_VALUE
~~~

The request above is **misused** against an API designed for OAuth 2.0 Access Tokens. Protecting an API requires its own token and authorization checks.

## 4. Access Token: Credential for Calling Protected Resources

### 4.1. Who Is an Access Token For?

An Access Token is issued within an OAuth 2.0 context and may represent a user's permissions via a client or the client's own permissions, depending on the grant. The client presents it to the intended **resource server**, usually as a Bearer token:

~~~http
GET /orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_FOR_ORDERS_API
~~~

The resource server checks whether the token is valid and sufficiently authorized. Conditions typically involve:

| Factor | Why It Matters |
| --- | --- |
| Issuer | The API only trusts the configured authorization server |
| Audience / resource | The token must be intended for the API receiving it |
| Scope / authority | The token has permission for the requested action, such as `orders.read` |
| Expiration / revocation | The token may have expired or been revoked |
| Subject / client / token binding | The API may need to know which user, which application, or sender-constrained binding the request belongs to |

An Access Token **is not required to be a JWT**. It may be an opaque string that the client cannot interpret; the resource server can verify it via introspection or another provider-supported mechanism. Nor should you assume Access Token JWT claims share the same structure or semantics as an ID Token.

### 4.2. Why Not Use an Access Token Instead of an ID Token?

An Access Token has audience and validation criteria tailored for a **resource server**, whereas an ID Token is issued for the **OIDC client**. OAuth 2.0 does not guarantee that an Access Token contains a name, email, or proof of completed user authentication under OIDC rules. A token from Client Credentials might not even represent any user.

Thus, the following approach is unsafe:

~~~text
1. Receive access_token.
2. Simply Base64URL-decode the payload if it looks like a JWT.
3. Read "email" / "sub" and treat it as the user who just logged in.
~~~

The OIDC login process must rely on a validated ID Token (and the corresponding OAuth login state). When additional user attributes are needed, use UserInfo according to specification or trusted claims provided by the provider in the ID Token.

### 4.3. Scope Does Not Equal Business Roles

For example, the client requests:

~~~text
scope=openid profile email orders.read
~~~

`openid` requests OIDC; `profile` and `email` request standard claim sets; `orders.read` is a scope defined by the API system. These scopes do not alter the fundamental nature of each token. If the resource does not accept the `orders.read` scope or the access token lacks the proper audience, the API can reject the call even though OIDC login succeeded.

Similarly, the `email` scope does not prove the user holds administrative privileges. Business permissions may require RBAC/ABAC policies, resource ownership checks, or other internal data.

## 5. UserInfo: Fetching Profile Information via a Protected Endpoint

### 5.1. What Is the UserInfo Endpoint?

**UserInfo** is a standard OpenID Connect endpoint for the client to obtain additional claims about the authenticated end-user. This endpoint is provided by the OIDC provider; the client sends an **Access Token** accepted by the provider, typically over HTTPS:

~~~bash
curl --request GET "https://id.example.com/realms/company/protocol/openid-connect/userinfo" \
  --header "Authorization: Bearer ACCESS_TOKEN_FOR_USERINFO"
~~~

The address above is merely an illustrative example for one provider; real applications should obtain `userinfo_endpoint` from OIDC discovery metadata (`.well-known/openid-configuration`) or trusted provider configuration rather than guessing the endpoint.

The JSON response may look like:

~~~json
{
  "sub": "c47a12f8-opaque-subject",
  "name": "Nguyen An",
  "given_name": "An",
  "family_name": "Nguyen",
  "preferred_username": "an.nguyen",
  "picture": "https://cdn.example.com/avatar/an.png",
  "email": "an@example.com",
  "email_verified": true,
  "locale": "vi-VN"
}
~~~

There is no guarantee every illustrative field will be returned. Depending on provider/client configuration, the UserInfo response may be JSON or a signed/encrypted JWT; if JWT is used, it must be processed and validated according to the corresponding requirements.

**UserInfo is neither an ID Token nor a "new token".** It is a response containing claims from a resource protected by an OAuth Access Token.

### 5.2. Mandatory Matching of UserInfo.sub with ID Token.sub

This is a central security requirement of OIDC:

~~~text
Validated ID Token:
    iss = https://id.example.com/realms/company
    sub = c47a12f8-opaque-subject

UserInfo response:
    sub = c47a12f8-opaque-subject

=> UserInfo claims may be used if all other checks also pass.
~~~

If UserInfo `sub` differs from `sub` in the ID Token, **the UserInfo response must be rejected**, because the claims could belong to another account. The UserInfo response must include `sub`; never use name, email, or avatar to "guess" that two responses belong to the same person.

Spring Security normally handles this check inside the OIDC user service when loading UserInfo. If the application explicitly calls the endpoint using its own HTTP client, it must enforce that constraint itself.

### 5.3. How Do Claims in the ID Token and UserInfo Differ?

OIDC allows some profile claims to be provided in the ID Token, UserInfo, or both depending on the provider. There is no universal rule that "email is always in the ID Token" or "email is always in UserInfo". Rely on the schema and policy agreed upon with your provider.

| Claim Category | Examples | Notes |
| --- | --- | --- |
| Core identity | `sub` | Required in both ID Token and UserInfo response |
| `profile` info | `name`, `given_name`, `family_name`, `picture`, `locale`, `zoneinfo` | Only returns claims actually provided/permitted |
| `email` info | `email`, `email_verified` | `email_verified=true` reflects verification per provider policy; does not grant business roles |
| `phone` info | `phone_number`, `phone_number_verified` | Requires corresponding scope/policy |
| `address` info | `address` | An object containing address attributes per OIDC |

The `scope` parameter requests a set of permissions/claims, **not a guarantee that all attributes will be present**. Specific claims can be requested via the OIDC `claims` parameter when supported by the provider; you still need to handle cases where a claim is absent or withheld.

### 5.4. When to Call UserInfo vs. Use Claims from the ID Token?

- **Only login identity needed:** A validated ID Token with the `iss` + `sub` pair is usually sufficient to create or identify an internal user.
- **Need name, avatar, locale, or email:** Use claims already present on the OIDC principal; if missing and UserInfo endpoint/permission are available, UserInfo can be fetched.
- **Need refreshed profile data:** Re-fetch UserInfo when appropriate under policy, keeping in mind it does not guarantee real-time up-to-date data; do not treat session claims as live real-time data.
- **Need permission to call business APIs:** Use the Access Token issued for that API; UserInfo does not replace API authorization mechanisms.

Avoid calling UserInfo on every HTTP request unless necessary: doing so increases latency, network dependency, and load on the IdP. Decisions on caching/refreshing profile data must balance freshness, lifetime, and privacy.

## 6. Practical Comparison Table

| Criterion | ID Token | Access Token | UserInfo Response |
| --- | --- | --- | --- |
| Primary purpose | Authenticate the user to the OIDC client | Authorize calls to a resource server | Retrieve additional user claims |
| Source | OIDC token endpoint (Authorization Code flow) | OAuth token endpoint | OIDC UserInfo endpoint |
| Format | JWT, may be signed/encrypted | Opaque/JWT/format determined by authorization server | Usually JSON; may be JWT per configuration |
| Audience / trusted target | OIDC client (`client_id`) | Target resource server | OIDC client receiving response from trusted endpoint |
| Contains `sub`? | Mandatory | Depends on token type and grant | Mandatory |
| Always contains `email`? | No | No | No |
| Sent in `Authorization: Bearer` to business API? | No | Yes, if token is valid for that API | No |
| Used to confirm OIDC login? | Yes, after client validation | No, insufficient on its own | Only supplementary after validating ID Token and matching `sub` |
| When expired | Depends on re-authentication/session policy | Needs a new/refreshed token if issued | Data may need to be re-fetched as needed |

A quick mnemonic:

~~~text
ID Token     -> "Who was authenticated for this client?"
Access Token -> "Which resources can be accessed?"
UserInfo     -> "What extra claims does the IdP share about that user?"
~~~

## 7. Spring Security OAuth 2.0 OIDC Client Integration

### 7.1. Configuring an OIDC Client in Spring Boot

Example Servlet web application using Spring Security OAuth 2.0 Client and an OIDC provider supporting discovery:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

Replace issuer, client ID, and secret with real provider values; keep secrets in a secure environment. The Redirect URI must match the client registration at the IdP. The `openid` scope signals an OIDC request; if only OAuth scopes exist without `openid`, do not assume an ID Token will be returned.

Setting up `SecurityFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/health").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

With this configuration, `/oauth2/authorization/company` can start the login flow. Spring Security executes the Authorization Code flow, validates the OIDC result, and places the authenticated user into `SecurityContext`. `oauth2Client()` enables using the authorized client when calling resources.

### 7.2. Retrieving ID Token and UserInfo from OidcUser

In a Servlet controller, you can receive the principal with `@AuthenticationPrincipal OidcUser`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MyProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
        var result = new LinkedHashMap<String, Object>();
        result.put("issuer", user.getIdToken().getIssuer().toString());
        result.put("subject", user.getSubject());
        result.put("displayName", user.getFullName());
        result.put("email", user.getEmail());
        result.put("userInfoAvailable", user.getUserInfo() != null);
        return result;
    }
}
~~~

**Explanation:**

- `user.getIdToken()` accesses the ID Token that passed Spring Security's OIDC validation; `getSubject()` reflects the principal's subject. The application uses the issuer–subject pair for account mapping.
- `user.getUserInfo()` returns `OidcUserInfo` **if** UserInfo was loaded during login. Its value can be `null`; never assume every IdP always provides UserInfo.
- `user.getFullName()` / `getEmail()` are merged claims exposed by the principal; they may be absent and are not guaranteed fields.
- The example endpoint returns only the metadata needed. **Do not return `getIdToken().getTokenValue()`, access tokens, or refresh tokens in a browser response** just to render a page.

Spring Security uses `OidcUserService` for loading the OIDC user in standard login configurations. It may call the UserInfo endpoint when metadata, access token/scopes, and required conditions permit; exact behavior depends on version, provider, and custom configuration. If business logic specifically requires UserInfo in a given scenario, explicitly configure/customize `OidcUserService` and verify claim presence.

When supporting multiple IdPs or complex profile mapping, an application can use a custom OIDC user service to map claims to internal data, while preserving ID Token validation and `UserInfo.sub == ID Token.sub` verification.

### 7.3. Obtaining an Access Token to Call Business APIs

`OidcUser` represents the logged-in user; tokens used to call APIs are stored in **`OAuth2AuthorizedClient`** associated with the client registration and principal.

Example backend endpoint proxying an API that accepts tokens from registration `company`:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrdersController {
    private final RestClient restClient = RestClient.create();

    @GetMapping("/my-orders")
    public String orders(
            @RegisteredOAuth2AuthorizedClient("company")
            OAuth2AuthorizedClient authorizedClient) {

        String token = authorizedClient.getAccessToken().getTokenValue();
        return restClient.get()
            .uri("https://api.example.com/orders")
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .body(String.class);
    }
}
~~~

This snippet only works when the Access Token for registration `company` **is issued for** `https://api.example.com` and has an appropriate scope, such as `orders.read`. **OIDC login with `openid profile email` does not guarantee a token usable for business APIs.** You must configure additional scopes/resources/audiences per the authorization server's contract, or use an appropriate token issuance mechanism. In production, handle 401/403 responses, timeouts, connection errors, internal permissions, and token refresh via the authorized client manager.

### 7.4. Understanding How Spring Security Loads UserInfo

Spring Security's OIDC flow comprises these parts:

~~~text
ClientRegistration (issuer, client_id, scopes, endpoints)
          |
          v
OAuth2 Login / Authorization Code
          |
          +--> ID Token --> OIDC token validation --> OidcUser
          |
          +--> Access Token --> OAuth2AuthorizedClient
                                 |
                                 +--> UserInfo endpoint (if applicable)
                                 |       |
                                 |       +--> OidcUserInfo; verify sub
                                 |
                                 +--> Authorized resource server
~~~

Key APIs:

| Type | Responsibility |
| --- | --- |
| `OidcIdToken` | Represents ID Token claims and raw value |
| `OidcUserInfo` | Represents claims received from the UserInfo endpoint |
| `OidcUser` | OIDC principal; provides ID Token, UserInfo if present, and user claims |
| `OidcUserService` | Loads/maps the OIDC user, optionally fetching UserInfo per configuration |
| `OAuth2AuthorizedClient` | Holds Access Token/Refresh Token for an authorized registration |
| `OAuth2AuthorizedClientManager` | Coordinates issuing or refreshing tokens per provider configuration |

Keep a clear distinction between **reading user claims** via `OidcUser` and **obtaining an Access Token** via `OAuth2AuthorizedClient`. This is an important boundary when writing controllers, HTTP clients, or backend integrations.

## 8. UserInfo May Be Missing, Fail, or Return Unexpected Claims

An OIDC client should not be designed around the assumption that "UserInfo always returns every claim".

| Symptom | Explanation / Handling |
| --- | --- |
| Provider does not publish `userinfo_endpoint` | Do not construct a URL manually; use claims present in the ID Token or another supported integration |
| UserInfo returns `401 Unauthorized` | Access Token expired, wrong type/token/audience, or rejected by endpoint; obtain a valid token per flow |
| UserInfo returns `403 Forbidden` | Token lacks required scope or permission; inspect scopes and policies |
| Response lacks `email` | Optional field; login can still proceed using `iss` + `sub` |
| Response has `email_verified=false` | Email not verified according to provider; do not treat email as verified |
| `sub` in UserInfo differs from ID Token | Reject the entire UserInfo response; investigate user/token/provider mismatch |
| `name` claim in ID Token differs from UserInfo | Claim policy and data freshness may differ; pick display source per provider contract |
| Access Token calls UserInfo successfully but business API rejects it | The two resource servers require different audiences and scopes |
| Access Token renewed while session remains old | Access Token lifecycle differs from app session; review principal/claim update policy |

For UserInfo, the API returns claims related to the authenticated user, yet the application must still decide **whether to store them, whether to sync them, and how long to retain them**. Profile data can change; long-term identity records should use issuer–subject, not display name or email as the sole key.

## 9. Common Design Pitfalls

### Pitfall 1: "The ID Token is a JWT, so the API should accept it"

Wrong because APIs need an Access Token intended for that API. A valid signature is only one condition; **audience** and **token purpose** must still match. Do not turn an ID Token into an API credential.

### Pitfall 2: "The Access Token has a sub, so it suffices for login authentication"

OAuth 2.0 does not require an Access Token to include `sub` or provide the OIDC guarantees needed for login. Some tokens represent a client with no user at all. OIDC login relies on a validated ID Token.

### Pitfall 3: "Requesting the email scope guarantees ID Token/UserInfo always has email"

No. Requesting permission does not guarantee the claim will be disclosed; data may be missing or withheld by the provider. Design models with optional fields and profile-completion flows when needed.

### Pitfall 4: "UserInfo returned the right name/email, so checking sub isn't needed"

Never skip **matching `sub`**. Email addresses can collide, change, or be unverified. OIDC requires UserInfo's subject to match the ID Token's subject.

### Pitfall 5: "UserInfo is always fresher and is the source of truth for all permissions"

UserInfo primarily holds user claims. Freshness depends on the IdP; API action permissions must still be enforced by the resource server and appropriate policies.

### Pitfall 6: "If login succeeded, every API will accept the Access Token"

An Access Token may only be valid for UserInfo or a specific API. Each resource server requires the proper audience, scopes, and token issuance flow. Never send a token to a system that is not its intended recipient.

### Pitfall 7: Logging tokens for debugging

ID Tokens, Access Tokens, and Refresh Tokens can all contain or grant access to sensitive data. Never write token values, callback URLs containing authorization codes, or secrets into logs, URLs, analytics, or exceptions. Log only error codes, request IDs, and non-sensitive metadata.

## 10. End-to-End Example: Building a "My Account" Page

Requirement: users log in at the IdP; the application displays name/email/photo and allows reading a task list from an API.

**Login phase:**

1. Spring Security initiates Authorization Code + PKCE when the user visits a page requiring authentication.
2. The token endpoint returns an ID Token and Access Token, plus optionally a Refresh Token.
3. The OIDC client validates the ID Token and extracts `iss` and `sub` to map the internal user.
4. If UserInfo is supported and extra claims are needed, the client calls UserInfo with an IdP-accepted Access Token; it must verify that UserInfo `sub` matches the ID Token.
5. The application establishes an appropriate internal session and exposes only the display-needed profile fields to the frontend.

**Task API call phase:**

1. The backend retrieves the authorized client corresponding to the user.
2. Verifies the Access Token matches the Task API's audience/scope; if expired, uses the refresh/token-renewal mechanism if allowed.
3. Calls the Task API with `Authorization: Bearer <access_token>`.
4. The Task API validates the token and enforces permissions on the task objects; the application handles 401/403 appropriately.

**Profile update phase:** when refreshing name/photo is needed, the application can re-fetch UserInfo with a valid token, verify `sub`, and update displayed data. Never change the internal user key based on a newly received email or name.

~~~mermaid
flowchart TD
    A["OIDC Login succeeded"] --> B["Validated ID Token"]
    B --> C["User key: issuer + subject"]
    B --> D{"Need more profile claims?"}
    D -->|Yes| E["Access Token -> UserInfo endpoint"]
    E --> F{"UserInfo.sub = ID Token.sub?"}
    F -->|Yes| G["Use permitted claims: name, email, picture..."]
    F -->|No| H["Reject UserInfo response"]
    D -->|No| I["Use existing claims"]
    C --> J["Internal session/principal"]
    G --> J
    I --> J
    J --> K{"Need to call API?"}
    K -->|Yes| L["Access Token with right audience/scope -> API"]
    K -->|No| M["Render page"]
~~~

## 11. Self-Check on Purpose and Usage

**Scenario A:** Received a valid ID Token with `sub=123` and `email=a@example.com`; the orders API returns 401 when the ID Token is sent as Bearer. This can be expected behavior: the API expects an Access Token issued for it, not an ID Token.

**Scenario B:** UserInfo returns `sub=456` while the ID Token has `sub=123`. You must discard the UserInfo response, even if both responses list the same name or email.

**Scenario C:** The application only requested `openid` and wants an avatar, but `picture` is missing. Check the `profile` scope, claim configuration, and provider UserInfo support; even when requesting `profile`, `picture` can still be absent.

**Scenario D:** The IdP Access Token calls UserInfo successfully, yet calling the task API fails. Check audience, resource indicator, scopes, and API policies instead of concluding OIDC login is broken.

**Scenario E:** The system has two OIDC providers that both issue `sub="123"`. Differentiate users by the pair (`iss`, `sub`); never merge accounts automatically based on `sub` alone.

## 12. Takeaways When Designing a Spring Security OIDC Client

When writing login and API-calling logic, ask the right question of the right component:

~~~text
Verify login:
  ID Token -> validate issuer, audience, signature, expiry, nonce...
           -> OidcUser / identity (iss, sub)

Read additional profile:
  Access Token for UserInfo -> UserInfo endpoint
                            -> receive claims, mandatory sub match

Call business API:
  Access Token for API -> Resource Server
                       -> check audience, scope, expiration, policy
~~~

**The ID Token authenticates the user for the OIDC client; the Access Token authorizes access to a resource server; UserInfo supplements profile claims within the context of a validated ID Token.** Spring Security helps manage many protocol steps, yet the application must still enforce the right token, right recipient, right identity key, and right authorization rules.
