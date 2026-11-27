# 22.4. Distinguishing Extension Grants from JWT-Based Client Authentication

## 1. Problem Statement: Seeing a JWT in a Token Request—Which Grant Is It?

A Spring Security OAuth 2.0/OIDC Client application sends a request to the Token Endpoint. Inside the request is a JWT signed with a private key. The implementer jumps to a conclusion: "This is the **JWT Bearer Grant**." That conclusion **lacks sufficient evidence**.

A JWT can serve completely different roles:

- **JWT as an authorization grant:** The client presents a JWT assertion for the Authorization Server to evaluate and issue an access token. The classic example is the **JWT Bearer Authorization Grant**, specified in RFC 7523.
- **JWT as a client authentication method:** The client signs a JWT assertion to prove it is the registered client. Examples include <code>private_key_jwt</code> in OIDC and JWT-based client authentication in RFC 7523. The actual authorization grant may still be <code>client_credentials</code>, <code>authorization_code</code>, or <code>refresh_token</code>.
- **JWT as an ID Token:** Issued by the OpenID Provider to an OIDC Client to prove End-User authentication.
- **JWT as an access token:** A Resource Server receives a Bearer access token that happens to be formatted as a JWT; that format does not identify which grant was used.
- **JWT as a Request Object or DPoP proof:** The JWT protects an authorization request or proves key possession—it does not imply a new grant.

**Do not classify an OAuth flow simply because a payload "looks like a JWT."** Inspect **which OAuth parameter carries the JWT**, the assertion's purpose, <code>grant_type</code>, the client authentication method, and the validation requirements at the Authorization Server.

### What Will You Be Able to Do After This Lesson?

1. Clearly separate **authorization grant** from **client authentication** at the Token Endpoint.
2. Recognize the JWT Bearer Grant: <code>grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer</code> together with the <code>assertion</code> parameter.
3. Recognize JWT Client Authentication: <code>client_assertion_type</code> together with <code>client_assertion</code>, including <code>private_key_jwt</code> and <code>client_secret_jwt</code>.
4. Understand when a client can simultaneously use **an extension grant** and **a separate JWT for client authentication**.
5. Interpret <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code>, and <code>jti</code> accurately for each role.
6. Apply this knowledge when configuring `ClientRegistration` and extending Spring Security OAuth2 Client.
7. Correctly diagnose <code>invalid_client</code>, <code>invalid_grant</code>, and <code>unsupported_grant_type</code> without fixing the wrong protocol layer.

## 2. Two Independent Questions at the Token Endpoint

When a client requests an access token, the Authorization Server must resolve **two questions**:

**Question A — On what basis is the client requesting a token?** This is the concern of the **authorization grant**: authorization code, client credentials, refresh token, JWT bearer assertion, token exchange, or an extension grant supported by the Authorization Server.

**Question B — Who is the client, and how does it prove its identity?** This is the concern of **client authentication**: <code>client_secret_basic</code>, <code>client_secret_post</code>, <code>private_key_jwt</code>, <code>client_secret_jwt</code>, mTLS, or a mechanism appropriate for the client type.

These two dimensions interact with policy, yet **they are not the same thing**.

~~~mermaid
flowchart TD
    C["OAuth2 Client"] --> R["Token Endpoint request"]
    R --> G{"What is the authorization grant?"}
    R --> A{"What is client authentication?"}
    G --> G1["client_credentials"]
    G --> G2["authorization_code"]
    G --> G3["refresh_token"]
    G --> G4["JWT Bearer assertion grant"]
    G --> G5["Token Exchange extension"]
    A --> A1["client_secret_basic"]
    A --> A2["private_key_jwt"]
    A --> A3["client_secret_jwt"]
    A --> A4["mTLS / other method"]
    G1 --> V["Authorization Server validates request + policy"]
    G2 --> V
    G3 --> V
    G4 --> V
    G5 --> V
    A1 --> V
    A2 --> V
    A3 --> V
    A4 --> V
    V --> T["Token response if accepted"]
~~~

### 2.1. Side-by-Side Comparison

| Aspect | Authorization grant | Client authentication |
|---|---|---|
| Question | "Based on what authorization/evidence should a token be issued?" | "Is the client calling the Token Endpoint truly the registered client?" |
| Primary OAuth parameter | <code>grant_type</code> | Authentication mechanism and corresponding parameters |
| JWT per RFC 7523 | <code>assertion</code> for JWT Bearer Grant | <code>client_assertion</code> for JWT client authentication |
| Associated type identifier | <code>urn:ietf:params:oauth:grant-type:jwt-bearer</code> | <code>urn:ietf:params:oauth:client-assertion-type:jwt-bearer</code> |
| Always involves an End-User? | No; depends on grant type and policy | No; proves identity of the **Client** |
| Determines granted scope/audience? | Grant, ClientRegistration, and AS policy participate | Auth method alone does not grant scopes |
| Changes <code>grant_type</code>? | Yes, when changing the grant | No, when only changing the auth method |
| Independent example | JWT bearer grant + client-secret authentication | client_credentials + private_key_jwt |

### 2.2. Example Changing Only One Dimension

A backend previously called the Token Endpoint with:

~~~text
grant_type = client_credentials
client authentication = client_secret_basic
~~~

After migrating to asymmetric-key authentication:

~~~text
grant_type = client_credentials
client authentication = private_key_jwt
~~~

**The grant is still `client_credentials`.** What changed is how the client proves its identity. Do not report that the system "switched to JWT Bearer Grant" merely because a private-key-signed JWT appeared in the token request.

## 3. JWT Is Just a Format: Look at Where the JWT Is Used

JSON Web Token (JWT, RFC 7519) is a claims container format that can be signed or protected using JOSE mechanisms. A signed JWT typically has three parts:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

An illustrative header:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026"
}
~~~

An illustrative payload:

~~~json
{
  "iss": "registered-client",
  "sub": "registered-client",
  "aud": "https://auth.example.org/oauth2/token",
  "iat": 1794800000,
  "exp": 1794800300,
  "jti": "unique-assertion-id"
}
~~~

These values are completely hypothetical and not a valid assertion because there is no real signature.

**Identical JWT structure does not imply identical purpose.** A JWT containing <code>iss</code>, <code>sub</code>, and <code>aud</code> could be a client assertion, a grant assertion, an ID Token, or an access token, yet its validation rules and represented party **differ**.

### 3.1. What Must Not Be Inferred from a JWT

- A JWT with <code>sub=user-123</code> does not prove the client is permitted to act on behalf of `user-123`.
- A JWT with a valid signature does not prove the Authorization Server trusts that issuer or key.
- A JWT with a matching <code>aud</code> does not prove the grant type is supported.
- A JWT access token does not imply the token was issued via the JWT Bearer Grant.
- A JWT signed with a private key is not automatically <code>private_key_jwt</code>; you must check which parameter carries it.
- A JWT containing scope or role claims does not automatically authorize a client to call an API without validation/policy enforcement.

In Spring Security OAuth2 Client, keep **assertion construction**, **grant selection**, **client authentication**, **`OAuth2AuthorizedClient` persistence**, and **Resource Server access-token usage** cleanly separated.

## 4. Token Endpoint Request Structure

A standard OAuth 2.0 token request uses:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded
~~~

The request body holds <code>grant_type</code> and grant-specific parameters. Client authentication may reside in the HTTP Authorization header or in form parameters depending on the registered method.

Example: Client Credentials + HTTP Basic:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Authorization: Basic <CLIENT_CREDENTIALS_PLACEHOLDER>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=reports.read
~~~

Example: Client Credentials + JWT Client Authentication:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_id=reports-client&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=SIGNED_CLIENT_ASSERTION_PLACEHOLDER&
scope=reports.read
~~~

Line breaks after <code>&amp;</code> are solely for **readability**; real requests require valid form-url-encoding. <code>client_id</code> may be required depending on the Authorization Server; JWT Client Authentication defines rules for identifying the client through the registered assertion.

**Note:** <code>client_assertion_type</code> is distinct from <code>grant_type</code>. They have two similar-looking URNs with independent meanings.

## 5. JWT Bearer Authorization Grant Under RFC 7523

### 5.1. When Is a JWT Used as an Authorization Grant?

The JWT Bearer Authorization Grant (RFC 7523, Section 2.1) allows a client to use a **JWT assertion** as an authorization grant to request an access token.

This is an **extension grant** under OAuth 2.0's extensibility model. The Authorization Server must:

1. Recognize the extension grant type.
2. Validate the JWT assertion per the profile and trust configuration.
3. Verify that the assertion is acceptable for issuing a token to the client, subject, audience, and requested scope.
4. Enforce client registration policy, consent/delegation, and token-issuance permissions.

Simply being able to sign a JWT **does not mean** the Authorization Server must accept that JWT as a grant.

### 5.2. Defining Parameters

~~~text
grant_type = urn:ietf:params:oauth:grant-type:jwt-bearer
assertion  = <JWT signed and trusted by the AS>
scope      = per request and policy
~~~

Example:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Authorization: Basic <CLIENT_CREDENTIALS_PLACEHOLDER>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&
assertion=SIGNED_GRANT_ASSERTION_PLACEHOLDER&
scope=reports.read
~~~

In this request:

- **The grant is JWT Bearer** because <code>grant_type</code> is the JWT Bearer Grant URN.
- <code>assertion</code> is the **grant assertion**, carrying data the Authorization Server evaluates as the basis for issuing a token.
- The <code>Authorization: Basic ...</code> header is **client authentication via client secret**, completely independent of the fact that the grant is JWT Bearer.

If you replace Basic with `private_key_jwt`, **the grant is still JWT Bearer**.

### 5.3. Which Claims Appear in a Grant Assertion?

Illustrative payload:

~~~json
{
  "iss": "https://issuer.example.org/service-account",
  "sub": "service-account-123",
  "aud": "https://auth.example.org/oauth2/token",
  "iat": 1794800000,
  "exp": 1794800300,
  "jti": "grant-assertion-unique-id-001"
}
~~~

Core claims to understand:

| Claim | Meaning in JWT Bearer Grant |
|---|---|
| <code>iss</code> | Issuer of the assertion; must be accepted by the Authorization Server |
| <code>sub</code> | Subject the assertion refers to; semantics determined by trust/delegation policy |
| <code>aud</code> | Audience intended for the Authorization Server/Token Endpoint per profile and policy |
| <code>exp</code> | When the assertion expires; AS must verify it has not expired |
| <code>iat</code> | Time the assertion was issued, if present |
| <code>nbf</code> | Not valid before this timestamp, if present |
| <code>jti</code> | Assertion identifier supporting replay protection when used |

Under RFC 7523, required claims and specific validation steps must follow the profile; <code>jti</code> does not automatically provide replay protection unless the Authorization Server maintains a policy/cache to detect reuse.

**The <code>sub</code> of a grant assertion is not automatically an OIDC logged-in user.** It can represent a subject under a trust agreement between the Client, assertion issuer, and Authorization Server. If the workflow involves delegated access or impersonation, explicit permission from the Authorization Server and organizational policy is required.

### 5.4. Who Signs the JWT Bearer Grant Assertion?

A JWT grant assertion is signed by an issuer that the Authorization Server is configured to trust within the scope of that grant. Depending on the provider, this may be a service account, a delegated issuer, or a dedicated identity system.

Never assume:

~~~text
Client holds any private key
→ self-signs a JWT with sub=admin
→ Authorization Server grants admin privileges
~~~

That reasoning is dangerous. **A valid signature only proves the JWT was signed with the corresponding key**, not that the issuer is permitted to mint assertions for that subject/scope.

### 5.5. Does the JWT Bearer Grant Require Client Authentication?

Whether the client must authenticate—and using which method—depends on the **client type, OAuth 2.0 rules, and Authorization Server configuration**.

For a confidential client, the Authorization Server may require client authentication such as:

~~~text
client_secret_basic
private_key_jwt
mutual TLS
~~~

A system can use a JWT as the **grant assertion** in the body while using a **different** JWT as the **client assertion**. The two assertions serve two distinct roles and must be validated independently.

## 6. JWT as a Client Authentication Method Under RFC 7523

### 6.1. Goal: Proving the Registered Client

In JWT Client Authentication (RFC 7523, Section 2.2), the client sends a JWT assertion to the Token Endpoint to authenticate **itself**.

Key difference from the JWT Bearer Grant:

> This JWT does not determine which grant the client is using to request an access token. The grant is still specified separately by <code>grant_type</code>.

Form parameters:

~~~text
client_assertion_type =
  urn:ietf:params:oauth:client-assertion-type:jwt-bearer

client_assertion =
  <JWT proving the Client's identity>
~~~

Example: Client Credentials Grant using JWT Client Authentication:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_id=reports-client&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=SIGNED_CLIENT_ASSERTION_PLACEHOLDER
~~~

In this example:

| Parameter | Meaning |
|---|---|
| <code>grant_type=client_credentials</code> | **Grant** |
| <code>client_assertion_type=...:client-assertion-type:jwt-bearer</code> | **Client authentication mechanism** |
| <code>client_assertion=...</code> | JWT proof signed by the Client |
| <code>client_id=reports-client</code> | Client identifier, if required/allowed by provider configuration |

Do not change <code>grant_type</code> to <code>...:grant-type:jwt-bearer</code> just because you want to enable `private_key_jwt`. Doing so changes the entire **basis for requesting a token** into a different extension grant.

### 6.2. Claims of a Client Assertion

Illustrative payload:

~~~json
{
  "iss": "reports-client",
  "sub": "reports-client",
  "aud": "https://auth.example.org/oauth2/token",
  "iat": 1794800000,
  "exp": 1794800300,
  "jti": "client-assertion-unique-id-002"
}
~~~

Important differences from a grant assertion:

- In JWT Client Authentication per RFC 7523, <code>iss</code> must typically identify the **Client ID**.
- <code>sub</code> must also be the **Client ID**.
- <code>aud</code> identifies the Authorization Server to which the assertion is sent—typically the token endpoint URL per profile/provider requirements.
- <code>exp</code> limits the assertion's validity lifetime.
- <code>jti</code> helps the Authorization Server detect replay when the implementation tracks/checks identifiers.

Some OpenID Providers require the exact issuer URI or exact token endpoint URI as the audience depending on profile and configuration. **Never guess**; consult the provider's metadata and client authentication documentation. Audience must be checked by the AS against a trust policy, never taken from a user-supplied URL.

### 6.3. A Client Assertion Is Not an Access Token

A client assertion:

- Is sent to the **Token Endpoint** for client authentication.
- Is not a token issued for a Resource Server.
- Does not replace a Bearer access token at an API.
- Typically has a very short lifetime and a dedicated audience constraint.

Wrong:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.org
Authorization: Bearer SIGNED_CLIENT_ASSERTION_PLACEHOLDER
~~~

A Resource Server must never accept a Token Endpoint client assertion as an access token merely because its format is JWT.

## 7. private_key_jwt and client_secret_jwt

In OpenID Connect, common method names for JWT Client Authentication include:

### 7.1. private_key_jwt

The client generates a JWT signed with its **private key**, and the Authorization Server verifies it using the registered or securely distributed public key/JWKS.

~~~text
Client
  ├── private signing key: kept secret, used only by Client
  └── client_assertion = JWS(private key)

Authorization Server
  ├── clientId and auth method = private_key_jwt
  ├── trusted public key/JWKS of Client
  └── verify signature, iss/sub/aud/exp/jti/policy
~~~

Advantage: the Authorization Server does not need to hold the same **shared signing secret** as the client. Still, the client must protect its private key, implement key rotation, enforce signing algorithm policies, and guard against replay.

### 7.2. client_secret_jwt

The client creates a JWT authenticated with a symmetric MAC algorithm such as HMAC using the **client secret** registered with the Authorization Server.

~~~text
Client and Authorization Server share a client secret
    ↓
Client signs JWT with the secret using an accepted algorithm
    ↓
Authorization Server verifies MAC and claims
~~~

This is still **JWT Client Authentication**, not the JWT Bearer Grant. Do not treat <code>client_secret_jwt</code> as equivalent in key-management security to <code>private_key_jwt</code>, because one uses a shared secret while the other uses an asymmetric key pair.

### 7.3. Comparing Client Authentication Methods

| Method | Credential Provided by Client | Used in Token Request | Changes Grant Type? |
|---|---|---|---|
| <code>client_secret_basic</code> | Client ID/secret via HTTP Basic | Authorization header | No |
| <code>client_secret_post</code> | Client ID/secret in form body | <code>client_id</code>, <code>client_secret</code> | No |
| <code>client_secret_jwt</code> | JWT MAC using client secret | <code>client_assertion_type</code> + <code>client_assertion</code> | No |
| <code>private_key_jwt</code> | JWT signed with private key | <code>client_assertion_type</code> + <code>client_assertion</code> | No |
| mTLS client auth | Client certificate and TLS verification per profile | TLS handshake, plus matching OAuth parameters | No |
| <code>none</code> | No confidential-client secret | Public Client per registration/policy | No |

Do not assume <code>none</code> is valid for every grant; for example, Client Credentials typically requires client authentication appropriate for the Authorization Server.

### 7.4. PKCE Is Not JWT Client Authentication

In the Authorization Code Flow, PKCE uses:

~~~text
code_challenge
code_challenge_method=S256
code_verifier
~~~

PKCE binds the authorization code to the client that initiated the flow and mitigates authorization code interception. PKCE **does not replace confidential client authentication** with `private_key_jwt` or a secret when policy requires both.

An authorization code token request can simultaneously carry:

~~~text
grant_type=authorization_code
code=...
redirect_uri=...
code_verifier=...
client_assertion_type=...
client_assertion=...
~~~

That is still the **Authorization Code Grant**, using PKCE and JWT Client Authentication.

## 8. Three Scenarios You Must Read Correctly

### 8.1. Scenario A — Client Credentials Grant + private_key_jwt

A batch worker needs to read the Reports API with service privileges.

~~~text
Grant:                  client_credentials
Client authentication:  private_key_jwt
End-User:               none
JWT transmitted:        client_assertion
Token received:         service access token
~~~

Request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_id=reports-client&
scope=reports.read&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=SIGNED_CLIENT_ASSERTION_A
~~~

There is no JWT Bearer Grant <code>assertion</code>. If a diagram labels this "JWT Bearer Grant," the diagram misclassified it.

### 8.2. Scenario B — JWT Bearer Grant + client_secret_basic

An Authorization Server supports the JWT Bearer Grant and trusts issuer <code>issuer.example.org</code> to assert the grant's subject.

~~~text
Grant:                  JWT Bearer Authorization Grant
Client authentication:  client_secret_basic
JWT transmitted:        assertion
JWT client_assertion:   none
~~~

Request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Authorization: Basic <CLIENT_CREDENTIALS_PLACEHOLDER>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&
assertion=SIGNED_GRANT_ASSERTION_B&
scope=reports.read
~~~

The JWT in <code>assertion</code> is the basis of the **grant**, whereas HTTP Basic handles client authentication.

### 8.3. Scenario C — JWT Bearer Grant + private_key_jwt

Both layers use JWTs, yet they are **two distinct assertions**:

~~~text
Grant:                  urn:ietf:params:oauth:grant-type:jwt-bearer
Grant assertion:        SIGNED_GRANT_ASSERTION_C

Client auth method:     private_key_jwt
Client assertion:       SIGNED_CLIENT_ASSERTION_C
~~~

Request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&
assertion=SIGNED_GRANT_ASSERTION_C&
client_id=reports-client&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=SIGNED_CLIENT_ASSERTION_C
~~~

Here:

1. <code>assertion</code> is evaluated under **authorization grant rules**.
2. <code>client_assertion</code> is evaluated under **client authentication rules**.
3. The two JWTs may have different <code>iss</code>, <code>sub</code>, keys, and audiences per policy.
4. Simply because both are JWTs does not mean one assertion can be reused for both purposes.

**Never casually reuse the same signed JWT in both parameters.** The two layers have distinct claim profiles, trust boundaries, key policies, lifetimes, and replay rules.

### 8.4. Summary of the Three Scenarios

| Scenario | grant_type | grant assertion? | Client authentication | client_assertion? |
|---|---|---|---|---|
| A | <code>client_credentials</code> | No | <code>private_key_jwt</code> | Yes |
| B | JWT Bearer Grant URN | Yes | <code>client_secret_basic</code> | No |
| C | JWT Bearer Grant URN | Yes | <code>private_key_jwt</code> | Yes |

To read a redacted request log, ask in order:

1. What is <code>grant_type</code>?
2. Is there an <code>assertion</code> parameter serving the grant?
3. What is the registered client authentication method?
4. Are <code>client_assertion_type</code>/<code>client_assertion</code> present?
5. Does the Authorization Server support and trust the assertions under both respective profiles?

## 9. Another Extension Grant: Token Exchange RFC 8693

The JWT Bearer Grant is only **one** extension grant. Another example frequently confused with JWT client authentication is **OAuth 2.0 Token Exchange (RFC 8693)**.

Token Exchange lets a client request exchanging an existing security token for another token under Authorization Server policy.

Core parameters:

~~~text
grant_type = urn:ietf:params:oauth:grant-type:token-exchange
subject_token = <token being exchanged>
subject_token_type = <type of subject token>
requested_token_type = <desired output token type, if needed>
audience = <target resource, if supported by AS>
~~~

Example:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange&
subject_token=EXISTING_ACCESS_TOKEN_PLACEHOLDER&
subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token&
audience=https%3A%2F%2Freports-api.example.org&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=SIGNED_CLIENT_ASSERTION_D
~~~

In the request above:

- The grant is **Token Exchange**, not the JWT Bearer Grant.
- <code>subject_token</code> is the token being exchanged; it can be a JWT or an opaque token depending on its type.
- <code>client_assertion</code> is a JWT used to **authenticate the client**.
- The Authorization Server still decides whether to permit the exchange and grant the requested audience/scope.

If the input token happens to be a JWT, that **does not turn Token Exchange into the JWT Bearer Grant**. Conversely, signing a client assertion with a JWT does not automatically grant delegation/token-exchange permissions.

### 9.1. Token Exchange Does Not Automatically Permit Impersonation

Token Exchange can support delegation or token-narrowing models, yet only when both Authorization Server and Resource Server are configured to trust the appropriate entities, actor/subject semantics, and scopes.

Never take a token for user A, swap <code>subject</code> to user B, and expect the Authorization Server to accept it. Client authentication and delegation rights must be validated separately.

### 9.2. Other Extension Grants

OAuth 2.0 Device Authorization Grant (RFC 8628) uses <code>grant_type=urn:ietf:params:oauth:grant-type:device_code</code> when a client polls the Token Endpoint with a device code. If that client authenticates with a JWT, **the device code grant is still the device code grant**.

Similarly, an Authorization Server may support proprietary extension grants per its documentation. **The client authentication method never redefines those extension grants**.

## 10. JWTs Easily Confused with Grant/Client Assertions

### 10.1. ID Token in OIDC

An ID Token:

- Is issued by the OpenID Provider to the OIDC Client.
- Proves End-User authentication under OIDC.
- Contains <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code>, and related claims.
- Is validated by the Client; it is not by default a client assertion.

Example:

~~~text
OIDC Authorization Code Flow:
  grant_type=authorization_code
  → Token Endpoint response contains id_token
~~~

Receiving a JWT <code>id_token</code> does **not** prove the request used the JWT Bearer Grant or `private_key_jwt`.

### 10.2. JWT Access Token

A Resource Server may receive a Bearer access token formatted as a JWT under the JWT Access Token Profile (RFC 9068) or a provider-specific JWT format.

~~~http
GET /v1/reports HTTP/1.1
Host: api.example.org
Authorization: Bearer ACCESS_TOKEN_JWT_PLACEHOLDER
~~~

That is merely the **representation of the access token at the Resource Server**, and says nothing about which <code>grant_type</code> issued it. Client Credentials, Authorization Code, Refresh Token, JWT Bearer Grant, or Token Exchange can all yield a JWT access token if the AS chooses that format.

Never decode a JWT yourself and trust its scopes/roles unless the Resource Server has verified the signature, issuer, audience, expiry, and authorization policy.

### 10.3. Request Object (JAR)

JWT-Secured Authorization Request (RFC 9101) can place authorization request parameters inside a **Request Object JWT**, sent under <code>request</code> or via <code>request_uri</code>.

~~~text
Authorization Endpoint:
    response_type=code
    client_id=...
    request=<SIGNED_REQUEST_OBJECT_JWT>
~~~

This **protects the authorization request** on the front channel; it is not a JWT Bearer Grant at the Token Endpoint, nor is it by default a client authentication assertion.

### 10.4. DPoP Proof JWT

Demonstrating Proof of Possession (DPoP, RFC 9449) uses a JWT proof in the HTTP <code>DPoP</code> header to bind requests to a key.

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
DPoP: SIGNED_DPOP_PROOF_PLACEHOLDER
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=CODE_PLACEHOLDER
~~~

A DPoP proof **does not automatically replace client authentication** and does not redefine the grant. It provides proof-of-possession/token binding per profile; the Authorization Server may still require confidential client authentication.

### 10.5. Summary of JWT Roles

| JWT | Where Does It Appear? | Purpose |
|---|---|---|
| JWT Bearer Grant assertion | Token request <code>assertion</code> | Basis for the authorization grant |
| JWT Client Authentication assertion | Token request <code>client_assertion</code> | Authenticates the Client |
| OIDC ID Token | Token response <code>id_token</code> | End-User authentication for the Client |
| JWT access token | Token response <code>access_token</code>; API Bearer header | Accessing the Resource Server |
| JAR Request Object | Authorization request <code>request</code>/<code>request_uri</code> | Protects authorization parameters |
| DPoP proof | HTTP header <code>DPoP</code> | Proves key possession per request/token |
| Token Exchange subject token | Token request <code>subject_token</code> | Input token for the extension grant |

**Always classify by position and protocol contract**, never by counting dots in a JWT string.

## 11. Trust Boundary: Who Validates What?

### 11.1. For the JWT Bearer Grant

The Authorization Server must verify:

1. Whether <code>grant_type</code> is supported and the client is permitted to use it.
2. Whether the JWT assertion has valid format, issuer/subject/audience, and lifetime.
3. Whether the signature verifies against a **trusted key for the assertion issuer**.
4. Whether the issuer is authorized to assert that subject and request that scope/audience.
5. Whether the JWT satisfies replay policy and is authorized to yield a token under the trust agreement.
6. Whether client authentication, if required, is valid.

### 11.2. For JWT Client Authentication

The Authorization Server must verify:

1. Whether the client is registered with the corresponding JWT auth method.
2. Whether the Client ID from JWT <code>iss</code>/<code>sub</code> matches.
3. Whether the signature/MAC verifies using the key/secret **bound to that specific client**.
4. Whether <code>aud</code> targets an allowed Authorization Server/Token Endpoint.
5. Whether <code>exp</code>, <code>nbf</code>, <code>iat</code>, and <code>jti</code> comply with policy.
6. Whether the specific grant in <code>grant_type</code> is allowed for this client.

Two-track validation diagram:

~~~mermaid
flowchart LR
    REQ["Token request"] --> G["Grant validation"]
    REQ --> C["Client authentication validation"]
    G --> GA["Verify assertion / subject / scope / policy"]
    C --> CA["Verify client ID / key / JWT / audience"]
    GA --> ISSUE{"Do both checks pass?"}
    CA --> ISSUE
    ISSUE -->|Yes| TOK["Issue token per policy"]
    ISSUE -->|No| ERR["OAuth2 error response"]
~~~

**Having one validly signed JWT never replaces both validation paths.**

### 11.3. Never Accept Arbitrary JWT Algorithms

For JWT assertions:

- Accept signing algorithms only from an allowlist matching client/issuer registration.
- Never accept <code>alg=none</code> for assertions requiring signatures.
- Never trust <code>jku</code>/<code>x5u</code> in JWT headers to automatically download public keys from arbitrary URLs.
- Never let <code>kid</code> become a caller-controlled file path or URL.
- Protect against algorithm confusion: never interpret a public key as an HMAC secret.
- Verify key usage, key ID, issuer/client binding, and key rotation timing.
- Use battle-tested JOSE/JWT libraries rather than writing custom verification crypto.

### 11.4. Lifetime and Replay

Client assertions should have short lifetimes per provider requirements, and each assertion should carry a fresh <code>jti</code> when required/accepted by policy.

Example:

~~~text
iat = current time
exp = iat + 60 to a few minutes, per policy
jti = random unique ID
~~~

This is a design guideline, not a universal rule accepted identically by every provider. An Authorization Server may enforce its own maximum assertion lifetime and clock skew.

Crucially: **a random <code>jti</code> in the payload does not prevent replay on its own**. The verifier must check and store/cache used <code>jti</code> values for an appropriate validity window.

Never reuse the same client assertion from a cache for hours. If a Token Endpoint request times out, do not blindly retry the exact same JWT infinitely; issue a fresh assertion per policy, classify errors, and bound retries.

## 12. Spring Security: ClientRegistration Separates Grant and Authentication Method

This is an essential mapping into Spring Security OAuth 2.0/OIDC Client configuration.

### 12.1. Client Credentials + client_secret_basic

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-worker:
            provider: company
            client-id: reports-client
            client-secret: ${REPORTS_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope:
              - reports.read
        provider:
          company:
            token-uri: https://auth.example.org/oauth2/token
~~~

This is the **Client Credentials Grant** with Client Secret Basic Authentication.

### 12.2. Client Credentials + private_key_jwt

A registration using the same grant while changing only the auth method:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-worker:
            provider: company
            client-id: reports-client
            authorization-grant-type: client_credentials
            client-authentication-method: private_key_jwt
            scope:
              - reports.read
        provider:
          company:
            token-uri: https://auth.example.org/oauth2/token
~~~

**Important:** Configuring <code>client-authentication-method: private_key_jwt</code> **is not enough** for a real application to sign JWTs.

The client still needs:

1. A private signing key/keystore or signing service.
2. A public key/JWKS registered with or trusted by the OP.
3. An algorithm matching policy and key type.
4. A component that signs the client assertion and appends the form parameters to the token request.
5. Mechanisms for key rotation, expiry, <code>jti</code>, and private key protection.

In Spring Security, signing the client assertion and attaching it to token requests may require configuring the appropriate token response client/converter **for your version**. Never assume declaring YAML properties makes Spring Boot automatically locate a private key or generate signatures.

### 12.3. Java ClientRegistration

Example highlighting the **two independent properties**:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

ClientRegistration registration =
    ClientRegistration.withRegistrationId("reports-worker")
        .clientId("reports-client")
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.PRIVATE_KEY_JWT)
        .tokenUri("https://auth.example.org/oauth2/token")
        .scope("reports.read")
        .build();
~~~

This snippet illustrates the registration model. **The private key/JWK provider is not passed into this `ClientRegistration`**; it belongs to a separate signing/token client configuration layer. Implement and register the proper JWT assertion converter before making token requests.

Never store private keys as hard-coded strings in source just to "get a demo running."

### 12.4. JWT Bearer Grant Is a Custom AuthorizationGrantType

If the Authorization Server supports the RFC 7523 JWT Bearer Grant:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;

AuthorizationGrantType JWT_BEARER_GRANT =
    new AuthorizationGrantType(
        "urn:ietf:params:oauth:grant-type:jwt-bearer");
~~~

You can represent the registration using that grant type value per your API/version capabilities:

~~~java
ClientRegistration jwtGrantRegistration =
    ClientRegistration.withRegistrationId("assertion-worker")
        .clientId("assertion-client")
        .authorizationGrantType(JWT_BEARER_GRANT)
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .clientSecret("<PLACEHOLDER_FROM_SECRET_STORE>")
        .tokenUri("https://auth.example.org/oauth2/token")
        .build();
~~~

**This is only metadata representation, not a full JWT Bearer Grant implementation.** Creating a new <code>AuthorizationGrantType</code> does not mean Spring Security automatically has a token request converter/provider that creates <code>assertion</code> and handles responses for that grant.

If your current Spring Security version lacks a built-in provider/client for the extension grant you need, implement/integrate the proper extension point per that version's documentation, or use a dedicated token client with a clear contract. Never change <code>grant_type</code> "to look close enough" just because a built-in provider is missing.

## 13. Spring Security Authorized Client Manager Does Not Decide Client Authentication

For a job using the Client Credentials Grant, you might configure:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class ReportsManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager reportsAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);

        var provider = OAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

The code above selects the **Client Credentials Provider**. Calling <code>.clientCredentials()</code> alone does not configure private key signing.

Inside the manager:

~~~text
ClientRegistration:
    grant_type = client_credentials
    client authentication method = private_key_jwt

Authorized Client Provider:
    clientCredentials()

Token Response Client:
    must know how to build and sign client_assertion
~~~

If using the JWT Bearer **Grant**, the provider must support that extension grant rather than using <code>clientCredentials()</code> and merely swapping assertions.

### 13.1. JWT Client Authentication at the Token Request Layer

Spring Security exposes extension points for building token requests and client authentication parameters; exact APIs depend on your Spring Security version.

For example, in Spring Security versions supporting Nimbus JOSE integration, components like **<code>NimbusJwtClientAuthenticationParametersConverter</code>** construct JWT Client Authentication parameters using a configured signing JWK.

Integration diagram:

~~~text
ClientRegistration(private_key_jwt)
            |
            v
OAuth2AuthorizedClientManager
            |
            v
OAuth2AuthorizedClientProvider(clientCredentials)
            |
            v
OAuth2AccessTokenResponseClient
            |
            +-- Grant parameters: grant_type=client_credentials
            |
            +-- Client auth parameters:
            |     client_assertion_type=...
            |     client_assertion=<signed JWT>
            |
            v
Token Endpoint
~~~

Class/constructor names and how converters are registered on the token client vary across Spring Security versions (and between Servlet/Reactive stacks). Therefore, this lesson does not assume a single JWK-signing snippet works unchanged across every Boot 3.x or Spring Security 6.x release.

**Mistake to avoid:** adding <code>JwtBearerOAuth2AuthorizedClientProvider</code> from an older tutorial and thinking it configures <code>private_key_jwt</code>. The **JWT Bearer authorization grant** provider, when present in your version/extension, operates on the **grant** dimension; JWT Client Authentication is a separate dimension.

### 13.2. When Is a Custom OAuth2AuthorizedClientProvider Needed?

When implementing an extension grant not yet supported by your current manager/provider, the client may need:

- A class implementing <code>OAuth2AuthorizedClientProvider</code> or its reactive counterpart.
- Grant assertion data supplied by a trusted issuer.
- A token response client sending the right <code>grant_type</code> and <code>assertion</code>.
- A separate client authentication mechanism.
- Proper authorized-client storage and success/failure handling.
- Validation and policy enforcement for subject/audience/scopes at the Authorization Server.

Do not write a custom provider solely to replace a client secret with `private_key_jwt` when the framework already provides the appropriate extension point on the **token response client**.

## 14. Spring Boot Example with Two Registrations for Two Purposes

Suppose a system has:

1. A browser using Authorization Code + OIDC Login via <code>web-login</code>.
2. A scheduler using Client Credentials + `private_key_jwt` via <code>reports-service</code>.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          web-login:
            provider: company
            client-id: portal-web
            client-secret: ${PORTAL_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile

          reports-service:
            provider: company
            client-id: reports-worker
            authorization-grant-type: client_credentials
            client-authentication-method: private_key_jwt
            scope:
              - reports.read

        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

Here:

- <code>web-login</code> uses the **Authorization Code Grant**; <code>openid</code> enables OIDC authentication.
- <code>reports-service</code> uses the **Client Credentials Grant**; <code>private_key_jwt</code> only specifies how the service authenticates at the Token Endpoint.
- Neither registration **implicitly** uses the JWT Bearer Authorization Grant.
- <code>reports-service</code> needs its own signing key configuration trusted by the OP.
- The access token from <code>web-login</code> is not automatically suitable for the Reports API; it may be scoped for UserInfo or a different resource.

If you want to add a JWT Bearer Grant registration, that is a **genuinely new grant**, requiring Authorization Server support and software that produces valid JWT grant assertions.

### 14.1. For Background Jobs, the Principal Is Not an End-User

A job using the service manager may call:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-service")
        .principal("reports-worker-runtime")
        .build();

OAuth2AuthorizedClient authorizedClient =
    manager.authorize(request);
~~~

<code>reports-worker-runtime</code> is the principal key Spring Security uses to store the token, **not a subject the client is impersonating in a JWT Bearer Grant**. Setting an arbitrary backend principal name string does not change the subject of the issued access token or assertion grant.

If <code>authorize(...)</code> returns <code>null</code> or throws an exception, handle it according to the actual grant and error; never fabricate a fake JWT to bypass the provider.

## 15. Key Management for private_key_jwt

### 15.1. Private Key and Public Key

Typical model:

~~~mermaid
flowchart LR
    APP["Client service"] --> K["Private key in vault/HSM/keystore"]
    K --> SIGN["Sign client_assertion"]
    SIGN --> TOKEN["Token Endpoint"]
    JWKS["Registered public JWK/JWKS"] --> TOKEN
    TOKEN --> VERIFY["Verify signature + claims + client binding"]
~~~

The client holds the **private key**. The Authorization Server verifies using the corresponding **public key** configured in its trust store. Never send the private key to the Authorization Server.

Operational steps:

1. Generate the key pair using an organization-approved method.
2. Register the public JWK/JWKS with the Authorization Server.
3. Choose a signature algorithm from the allowlist.
4. Set <code>kid</code> to assist key selection when needed.
5. Configure the token client/signing converter to use the private key securely.
6. Bound JWT client assertion lifetimes and generate unique <code>jti</code> values.
7. Monitor client authentication failures and key expiry/rotation.

### 15.2. Zero-Downtime Key Rotation

A rotation strategy:

~~~text
T0: public JWK K1 is trusted by the AS
T1: add public JWK K2 to the trusted set
T2: Client switches to signing assertions with private key K2
T3: observe successful authentications with kid=K2
T4: after the overlap window, remove K1 from the trusted set
~~~

Do not delete K1 immediately before every instance has switched to K2 if some nodes are still signing with K1. If the AS caches the key store/JWKS, account for cache refresh propagation.

Keys used to sign **JWT grant assertions** may belong to a different issuer than the client keys used to sign **client assertions**. Never merge two key lifecycles into one without an explicit trust design.

### 15.3. Valid Signature, Wrong Audience

A common failure:

~~~text
JWT iss=sub=reports-client
JWT signed with the right private key
JWT aud=https://api.example.org
Token Endpoint=https://auth.example.org/oauth2/token
~~~

JWT Client Authentication will be rejected because **the audience does not target an allowed Authorization Server/Token Endpoint**. Never "fix" this by disabling audience validation.

The audience for a client assertion **differs** from the audience of an access token used to call a Resource Server.

## 16. The Authorization Server Must Support and Permit Each Capability

Before configuring Spring Security, verify the provider's details:

| Capability | What to Confirm at the Authorization Server |
|---|---|
| JWT Bearer Grant | Does it support <code>urn:ietf:params:oauth:grant-type:jwt-bearer</code> and issuer trust policy? |
| Token Exchange | Does it support <code>...:token-exchange</code>, the subject token type, and delegation policy? |
| private_key_jwt | Is the client registered with this auth method, key/JWKS, and alg/aud policy? |
| client_secret_jwt | Is the client allowed to use HMAC-based JWT authentication? |
| Client Credentials | Is the client permitted to use the grant, and which scopes/audiences are issued? |
| Authorization Code | Which redirect URI, PKCE, and client authentication policies apply? |
| Refresh Token | Are refresh tokens issued, and how do rotation/reuse detection work? |

If the provider publishes discovery metadata, you may inspect properties such as:

~~~json
{
  "issuer": "https://idp.example.org/realms/company",
  "token_endpoint": "https://idp.example.org/realms/company/protocol/openid-connect/token",
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ],
  "grant_types_supported": [
    "authorization_code",
    "client_credentials",
    "urn:ietf:params:oauth:grant-type:jwt-bearer"
  ]
}
~~~

This is **illustrative metadata**, not live data from a real provider. Entries may be omitted or incomplete in some implementations; specific client registrations and policies still determine whether the client may use that method or grant.

Never infer:

~~~text
metadata lists private_key_jwt
⇒ every Client may use JWT Bearer Grant
~~~

Those two capabilities are separate items.

## 17. Error Handling: Wrong Grant or Wrong Client Authentication?

The Token Endpoint typically returns OAuth 2.0 error codes with distinct meanings.

### 17.1. invalid_client

Example:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "error": "invalid_client"
}
~~~

Possible causes:

- Unrecognized Client ID.
- Client is registered for <code>client_secret_basic</code>, yet the request uses unpermitted `private_key_jwt`.
- Client assertion has a bad signature, wrong audience, expired timestamp, or `iss`/`sub` mismatch with Client ID.
- Signing key is unregistered, <code>kid</code> is wrong, or the JWK cache is stale.
- Client key was revoked or configuration is out of sync.

Diagnose at the **client authentication layer** first; do not rush to change <code>grant_type</code>. Under OAuth 2.0, the exact HTTP status code for client authentication errors depends on the method and implementation; 401 is not guaranteed across every provider.

### 17.2. unsupported_grant_type

Example:

~~~json
{
  "error": "unsupported_grant_type"
}
~~~

Cause: the Authorization Server does not support or recognize the submitted <code>grant_type</code>.

If you send <code>urn:ietf:params:oauth:grant-type:jwt-bearer</code> to a provider that only supports <code>client_credentials</code>, adding `private_key_jwt` will not fix this error. Use a genuinely supported grant or work with the provider to enable the capability.

### 17.3. unauthorized_client

An Authorization Server may support a grant globally while **forbidding the current client from using it**.

~~~json
{
  "error": "unauthorized_client"
}
~~~

For example, the JWT Bearer grant is supported system-wide, yet only specific registered clients are allowed to use it.

This is a **client grant-authorization error**, not necessarily an invalid JWT signature. Check the client registration policy at the Authorization Server.

### 17.4. invalid_grant

For the JWT Bearer Grant, this error can arise when the grant assertion is rejected: claims, trust, expiry, replay, or subject/scope policy.

For Authorization Code/Refresh Token, <code>invalid_grant</code> can mean an invalid, expired, replayed, or revoked code/refresh token.

Never treat <code>invalid_grant</code> as automatic justification to wipe all authorized clients for all users. Classify by grant and protect token state against concurrent updates.

### 17.5. invalid_scope

The client requested an unpermitted scope:

~~~json
{
  "error": "invalid_scope"
}
~~~

Do not try to fix this by signing a JWT containing an extra <code>scope=admin</code> claim. Token permissions are governed by Authorization Server policy, not self-asserted by the client.

### 17.6. Diagnostic Table

| Error / Symptom | Layer to Inspect First | What to Cross-Check |
|---|---|---|
| <code>invalid_client</code> | Client authentication | Auth method, Client ID, key/secret, iss/sub/aud/exp |
| <code>unsupported_grant_type</code> | Authorization grant | Whether AS supports that <code>grant_type</code> |
| <code>unauthorized_client</code> | Client registration policy | Whether the client is permitted to use that grant |
| <code>invalid_grant</code> | Grant/assertion/token state | <code>assertion</code>, code/refresh token, expiry, trust, replay |
| <code>invalid_scope</code> | Permission request | Whether requested scopes are permitted |
| HTTP 401 at Resource Server | Access-token authentication | Whether token has right issuer/audience/expiry |
| HTTP 403 <code>insufficient_scope</code> at API | Resource authorization | Whether access token carries required API permissions |
| Validly signed JWT rejected by AS | Trust/policy/claims | Issuer, Client registration, audience, alg/key, and delegation |

**Note:** HTTP 401/403 from a Resource Server **differs** from JSON errors returned by the Token Endpoint. Never read HTTP 403 <code>insufficient_scope</code> and conclude the Token Endpoint does not support JWT client authentication.

## 18. Security When Using JWT Grants and JWT Client Authentication

### 18.1. Do Not Use Assertions as Arbitrary Bearer Access Tokens

A grant <code>assertion</code> and a <code>client_assertion</code> target the **Token Endpoint**. Never place them in an API's HTTP Authorization header unless a specific protocol/profile explicitly defines and validates it.

### 18.2. Never Log Assertions or Private Keys

Avoid logging:

- Raw <code>assertion</code> and <code>client_assertion</code>.
- Token Endpoint HTTP form bodies.
- Private keys, HMAC secrets, and keystore passwords.
- Refresh tokens, access tokens, ID Tokens, and Authorization headers.
- <code>code_verifier</code> or authorization codes in other flows.

Safer logging:

~~~text
registrationId=reports-worker
grantType=client_credentials
clientAuthMethod=private_key_jwt
tokenEndpointResult=invalid_client
signingKeyId=key-2026
requestCorrelationId=...
~~~

Even <code>kid</code> or registration IDs must follow telemetry policies; never place raw tokens or sensitive claims into metric labels.

### 18.3. Never Sign for a Caller-Supplied Audience

Wrong:

~~~text
POST /internal/get-token?aud=https://unknown.example
    → backend signs client assertion for caller-chosen aud
~~~

Client assertion audience must come from a **trusted configured Authorization Server/token endpoint** and satisfy provider policy. Letting callers choose it can send assertions to untrusted destinations or abuse your signing service.

### 18.4. Never Let a Browser Pick `sub` to Impersonate

Wrong:

~~~text
POST /internal/grant
body: {"sub": "admin", "scope": "all"}
    → backend signs JWT Bearer Grant assertion
~~~

If a backend holds authority to sign assertions trusted by the AS, it must strictly protect subject selection, delegation scope, and caller authentication. Never turn a signing endpoint into an impersonation tool.

### 18.5. Replay Protection Must Be Enforced by the Verifier

The client can generate unique <code>jti</code> values and short-lived assertions, yet the Authorization Server must enforce duplicate detection when required by policy/profile. A replay cache must be designed with appropriate TTL, issuer/client namespacing, and consistency—especially across multi-node clusters.

### 18.6. Key Isolation

Never share a single private key across every issuer, tenant, and assertion type just to save configuration effort. Isolate keys by client/trust domain per policy and restrict each service's signing permissions.

With <code>client_secret_jwt</code>, remember the shared secret exists on both sides. With <code>private_key_jwt</code>, protect the private key inside an HSM/vault/keystore and distribute only public keys to the AS.

## 19. Technical Checklist for Reading a Token Request

When inspecting a failing request, proceed in order:

1. Identify the **HTTP destination**: Token Endpoint, Resource Server, or Authorization Endpoint?
2. Find the actual <code>grant_type</code>.
3. If the grant is JWT Bearer, check whether <code>assertion</code> is present.
4. If the grant is Token Exchange, check <code>subject_token</code>/<code>subject_token_type</code>.
5. Identify the registered client authentication method.
6. If JWT Client Authentication is used, inspect <code>client_assertion_type</code> and <code>client_assertion</code>.
7. Verify that the Authorization Server supports both the **grant** and the **auth method**, and that the client is authorized to use them.
8. Cross-check `iss`/`sub`/`aud`/`exp`/`jti`, algorithms, key IDs, and trust policies **for each JWT role separately**.
9. Inspect the actually granted scope/audience/entitlements.
10. Only then classify into <code>invalid_client</code>, <code>invalid_grant</code>, or <code>unauthorized_client</code> for remediation.

Decision tree:

~~~text
Is there a request to the Token Endpoint?
    |
    v
Read grant_type
    |
    +-- client_credentials ----------> client credentials grant
    |
    +-- authorization_code ---------> authorization code grant
    |
    +-- refresh_token --------------> refresh grant
    |
    +-- ...:grant-type:jwt-bearer --> JWT Bearer Grant
    |                                    |
    |                                    +-- look for assertion
    |
    +-- ...:grant-type:token-exchange -> Token Exchange
                                         |
                                         +-- look for subject_token

Then (independently):
    |
    v
Client authentication method?
    |
    +-- client_secret_basic --------> Authorization: Basic
    |
    +-- private_key_jwt ------------> client_assertion_type + client_assertion
    |
    +-- client_secret_jwt ----------> client_assertion_type + client_assertion
    |
    +-- mTLS -----------------------> client certificate/trust
~~~

Never pick the grant simply by searching for the word "JWT" anywhere in the request.

## 20. Practice Exercises

### Exercise 1 — Identifying the Request

~~~text
grant_type=client_credentials
client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
client_assertion=JWT_A
~~~

**Question:** Is this the JWT Bearer Grant?

**Answer:** No. The grant is <code>client_credentials</code>. `JWT_A` is used for client authentication.

### Exercise 2 — Identifying the Grant Assertion

~~~text
grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
assertion=JWT_B
Authorization: Basic ...
~~~

**Question:** Is `JWT_B` a client assertion?

**Answer:** No. `JWT_B` is the JWT Bearer Grant assertion; the client is authenticating via HTTP Basic.

### Exercise 3 — Two JWTs in One Request

~~~text
grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
assertion=JWT_GRANT
client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
client_assertion=JWT_CLIENT
~~~

**Question:** What must the Authorization Server validate?

**Answer:** Validate `JWT_GRANT` against trust/grant/subject policy; validate `JWT_CLIENT` against client registration/key/`iss`/`sub`/`aud`/client authentication policy; both the grant and the client must be authorized.

### Exercise 4 — Migrating from client_secret_basic to private_key_jwt

A service currently uses <code>client_credentials</code> and wants to replace its shared client secret with an asymmetric key pair.

**Question:** Does <code>grant_type</code> need to change to JWT Bearer Grant?

**Answer:** No. The grant remains <code>client_credentials</code>. Change only the client authentication method and configure the signing key, JWKS, and appropriate assertion converter/token client.

### Exercise 5 — JWT Access Token

An API receives an access token signed with RS256. The original token request had <code>grant_type=authorization_code</code>.

**Question:** Can this be called the JWT Bearer Grant?

**Answer:** No. The output token is a JWT, yet the authorization grant was Authorization Code.

### Exercise 6 — Wrong Client Assertion Audience

A client assertion has <code>iss=sub=reports-client</code> and a valid signature, yet <code>aud</code> points to the Reports API instead of the Authorization Server.

**Question:** Is disabling signature validation the right fix?

**Answer:** No. Set the audience per Token Endpoint policy and validate both signature and claims; disabling validation creates a security vulnerability.

### Exercise 7 — Token Exchange

A request contains:

~~~text
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
subject_token=<JWT access token>
client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
client_assertion=<signed JWT>
~~~

**Question:** How many JWT roles appear in this request?

**Answer:** Subject token (input to the **Token Exchange Grant**) and client assertion (used for **Client authentication**). Token Exchange does not become the JWT Bearer Grant merely because the subject token is formatted as a JWT.

### Exercise 8 — invalid_client vs. invalid_grant

Case A: Client registers `private_key_jwt`, key is not yet registered at the OP, and the request fails with <code>invalid_client</code>.

Case B: Client authentication succeeds, yet the JWT Bearer grant assertion has expired, and the request fails with <code>invalid_grant</code>.

**Question:** At which layer should each error be addressed?

**Answer:** Case A checks client authentication and key/JWKS registration. Case B checks the grant assertion, expiry/trust/subject/audience policy. Do not randomly alter both configurations.

### Exercise 9 — JWT with sub=user-123

An application self-signs a JWT grant assertion with <code>sub=user-123</code> and requests scope <code>admin</code>.

**Question:** Is this enough to be issued an admin token?

**Answer:** Not yet. The Authorization Server must trust the issuer and permit that assertion to represent `user-123` with the requested scope. A valid signature never substitutes for authorization.

### Exercise 10 — Spring Security Registration

Given YAML:

~~~yaml
authorization-grant-type: client_credentials
client-authentication-method: private_key_jwt
~~~

**Question:** Why are these two YAML lines insufficient for the Token Endpoint to accept requests?

**Answer:** You still need a valid `ClientRegistration`, a private signing key, a public key/JWKS trusted by the OP, a token request client/converter that builds the JWT client assertion, and `alg`/`aud`/`exp`/`jti` policy alignment. Nor do these two lines create a JWT Bearer Grant.

### Exercise 11 — JAR and DPoP

An OIDC Client sends a signed Request Object to the Authorization Endpoint and a DPoP JWT proof to the Token Endpoint.

**Question:** Can we conclude the client uses `private_key_jwt` or the JWT Bearer Grant?

**Answer:** No. JAR protects the authorization request, and DPoP proves key possession for the request/token; client authentication and grant type are still determined separately.

### Exercise 12 — Sketching a Complete System

Design a Reports Worker that uses:

1. <code>client_credentials</code> to obtain a service token.
2. <code>private_key_jwt</code> to authenticate the client at the Token Endpoint.
3. Private keys stored in KMS/HSM or an appropriate secret manager.
4. Public JWKS trusted by the Authorization Server.
5. JWT client assertions with <code>iss=sub=clientId</code>, provider-compliant audience, short expiry, and proper <code>jti</code>.
6. Spring Security `ClientRegistration` separating grant type and client authentication method.
7. <code>OAuth2AuthorizedClientManager</code> configured with the <code>clientCredentials()</code> provider.
8. A token response client with a version-appropriate signer/converter.
9. A Resource Server validating the access token's issuer/audience/scope.
10. Dedicated tests for wrong audience, wrong key, expired assertion, unsupported grant, missing scope, and key rotation.

Explain why **no step requires changing <code>grant_type</code> to the JWT Bearer Grant**.

## 21. Key Takeaways

- **Authorization grant** answers "on what basis should a token be issued?"; **client authentication** answers "which client is requesting the token and how does it prove its identity?".
- **JWT Bearer Grant** (RFC 7523) uses <code>grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer</code> with the JWT in the <code>assertion</code> parameter.
- **JWT Client Authentication** uses <code>client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer</code> with the JWT in the <code>client_assertion</code> parameter.
- **<code>private_key_jwt</code>** and **<code>client_secret_jwt</code>** are client authentication methods, **not grant types**.
- <code>client_credentials + private_key_jwt</code> is still the Client Credentials Grant. <code>authorization_code + private_key_jwt</code> is still the Authorization Code Grant.
- You can use **a JWT grant assertion and a JWT client assertion simultaneously**; they are **two separate JWTs with independent roles, key/trust policies, and validation**.
- Token Exchange can carry a JWT as <code>subject_token</code> while also using JWT Client Authentication, yet its grant remains <code>urn:ietf:params:oauth:grant-type:token-exchange</code>.
- ID Tokens, JWT access tokens, JAR Request Objects, and DPoP proofs are also JWTs in many setups, yet **never replace grants or client authentication on their own**.
- In Spring Security, <code>ClientRegistration.authorizationGrantType</code> and <code>clientAuthenticationMethod</code> are two separate properties. Configuring `private_key_jwt` also requires an appropriate signer/token response client.
- The Authorization Server must validate **issuer/subject/audience/expiry/signature/trust/replay and grant permissions**; being able to sign a JWT does not entitle anyone to a token.
- Diagnose by layer: <code>invalid_client</code> typically points to client authentication, <code>invalid_grant</code> to grant assertion/token state, <code>unsupported_grant_type</code> to grant support, and <code>unauthorized_client</code> to grant-usage permissions.

### References

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Client Authentication, Token Endpoint, Authorization Grants, and Extension Grants (Section 4.5).
- **RFC 7521 — Assertion Framework for OAuth 2.0 Client Authentication and Authorization Grants:** architecture separating assertion grants from assertion client authentication.
- **RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants:** the JWT Bearer Authorization Grant and JWT Client Authentication profiles.
- **RFC 7519 — JSON Web Token (JWT):** claims <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code>, <code>jti</code>.
- **OpenID Connect Core 1.0 — Client Authentication:** <code>private_key_jwt</code>, <code>client_secret_jwt</code>, OIDC ID Token.
- **RFC 8693 — OAuth 2.0 Token Exchange:** <code>subject_token</code>, <code>subject_token_type</code>, and extension grant.
- **RFC 8628 — OAuth 2.0 Device Authorization Grant:** extension grant for devices.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** distinguishing JWT access tokens from grant assertions.
- **RFC 9101 — The OAuth 2.0 JWT-Secured Authorization Request (JAR):** Request Objects distinct from grants and client authentication.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** proof JWTs distinct from client authentication.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** requirements for protecting OAuth flows and tokens.
- **Spring Security Reference — OAuth2 Client:** ClientRegistration, Authorized Client Manager, Token Response Client, and Client Authentication.
- **Spring Security Java API:** <code>ClientAuthenticationMethod</code>, <code>AuthorizationGrantType</code>, <code>OAuth2AuthorizedClientProviderBuilder</code>, and version-specific JWT Client Authentication parameter converters.
