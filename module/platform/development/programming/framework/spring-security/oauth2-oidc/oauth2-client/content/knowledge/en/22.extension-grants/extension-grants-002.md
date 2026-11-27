# 22.2. JWT Bearer Grant and Assertion Exchange Scenarios

In **Spring Security OAuth 2.0/OIDC Client**, familiar flows such as Authorization Code, Refresh Token, and Client Credentials typically start from a **`ClientRegistration`** and let Spring manage the `OAuth2AuthorizedClient`. However, some enterprise integration systems need another mechanism: **using a JWT assertion issued by a trusted party to request an OAuth access token at the Token Endpoint**.

That is the use case for the **JWT Bearer Authorization Grant** described in **RFC 7523**, built on the OAuth 2.0 Assertion Framework in **RFC 7521**.

A request might look like this:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&
assertion=<signed-jwt-assertion>&
scope=orders.read
```

The Authorization Server (AS) **does not simply accept any arbitrary JWT**. It must verify the issuer, subject, audience, expiration, signature, trust policy, assertion reuse controls, and token-issuance permissions. If valid under the registered contract, the AS can issue an access token so the client can call the Resource Server.

What causes the most confusion is that a JWT can appear in **three different places**:

- **JWT Bearer Grant:** the JWT is the **authorization grant/assertion**, sent in the `assertion` parameter.
- **JWT Client Authentication (`private_key_jwt`):** the JWT is **proof authenticating the OAuth client itself**, sent in the `client_assertion` parameter.
- **OAuth 2.0 Token Exchange (RFC 8693):** a token/assertion can be passed in `subject_token` under the **token exchange** protocol, using a different `grant_type`.

These three mechanisms can coexist in the same system—and even combine at some Authorization Servers—yet **they cannot be used interchangeably merely because all three contain a JWT**.

This lesson covers the role of assertions, request structure, key JWT claims, JWT signing examples, replay controls, distinguishing grants from client authentication, comparisons with Token Exchange, extension integration in Spring Security Client, and real-world deployment scenarios.

## 1. What Problem Does the JWT Bearer Grant Solve?

Suppose an organization has:

- An **Identity/Token Broker** system that has already authenticated an employee or workload using an existing mechanism.
- An **Authorization Server** dedicated to issuing OAuth access tokens for APIs.
- A **Spring Boot integration service** that needs an access token without running the browser redirect of the Authorization Code Flow.
- A **Resource Server**, such as the Orders API, that only accepts OAuth access tokens with allowed audiences/scopes.

The Token Broker can issue a **short-lived JWT assertion signed with a trusted key**. The Spring service presents this assertion to the AS. The AS verifies the assertion, evaluates policy, and issues an access token for the Orders API.

```mermaid
sequenceDiagram
    autonumber
    participant Source as Identity / Assertion Issuer
    participant App as Spring OAuth2 Client
    participant AS as Authorization Server
    participant API as Orders API

    Source->>App: Signed JWT assertion
    App->>App: Protect assertion; do not treat as API token
    App->>AS: POST /token, grant_type=jwt-bearer, assertion=JWT
    AS->>AS: Verify iss/sub/aud/exp/signature/replay/policy
    alt Assertion accepted
        AS-->>App: OAuth access token + granted scopes
        App->>API: Authorization: Bearer access token
        API->>API: Validate token, audience, scope, data permissions
        API-->>App: Response
    else Assertion rejected
        AS-->>App: OAuth error (e.g., invalid_grant)
    end
```

The key takeaway: **the assertion is used to request a token; the newly issued token is the credential that the Resource Server accepts**.

### 1.1. Common Scenarios

| Scenario | Idea | Mandatory Condition |
|---|---|---|
| Enterprise SSO/STS integration | STS issues a signed JWT describing the subject; the client exchanges it for an access token | AS trusts the issuer/key and enforces an authorization policy |
| Batch systems acting on behalf of an authenticated subject | Client presents a JWT assertion under a delegation agreement | Subject/issuer must be authorized, not arbitrarily self-asserted |
| Identity federation | An assertion from trust domain A is accepted by AS B | Federation contract, audience, signature, and claim mapping |
| Legacy token broker | Broker issues short-lived JWTs to exchange for OAuth tokens | AS supports the grant per RFC 7523 |
| Workloads using JWT assertions | Workload holds a signed JWT credential from a trusted issuer | AS explicitly defines workload permissions and token issuance bounds |

A system should never choose the JWT Bearer Grant merely to "skip logging in". It is **an authorization grant mechanism with a defined trust relationship**, not a shortcut allowing a client to set any arbitrary `sub` and obtain an access token under that identity.

## 2. Recap: Authorization Grant, Client Authentication, and Access Token

In OAuth 2.0, three concepts must be kept distinct:

1. **Authorization grant:** proof/authorization that the client presents to the AS to request an access token.
2. **Client authentication:** the AS verifies **which OAuth client** is calling the Token Endpoint, using the registered authentication method.
3. **Access token:** the credential issued by the AS for the client to present to the Resource Server.

```text
Authorization grant
   + (Client authentication when required)
   + Token Endpoint policy
       |
       v
Authorization Server
       |
       v
Access token
       |
       v
Resource Server
```

One JWT assertion can be used as a **grant**; a *different* JWT assertion can be used to authenticate the client. In both cases, the form field names and validation purposes differ.

### 2.1. Not Every JWT Is an Access Token

JWT is simply a JSON-based **token/assertion format** that can be signed with JWS. There are many kinds of JWTs:

- **OIDC ID Token:** authentication result intended for the Relying Party.
- **OAuth JWT access token:** credential intended for the Resource Server.
- **JWT assertion in RFC 7523:** proof intended for the Token Endpoint.
- **JWT used for `private_key_jwt`:** proof that the client possesses the private key.
- **JWT issued by a Token Broker/STS:** can serve as input to an exchange mechanism if supported by the AS.

A valid signature **does not by itself determine a token's purpose**. A valid ID Token issued for an OAuth client must not by default be used as a JWT bearer assertion or an access token sent to an API.

## 3. How Do RFC 7521 and RFC 7523 Relate?

### 3.1. RFC 7521: Assertion Framework

RFC 7521 describes a model for using **assertions** in OAuth 2.0 along two tracks:

- **Assertions as authorization grants.**
- **Assertions as client authentication credentials.**

The framework separates these two roles so individual profiles define specific assertion formats, validation rules, and request parameters.

### 3.2. RFC 7523: JWT Profile

RFC 7523 specifies the **JWT** profile for both tracks above.

For an **authorization grant**, the Token Endpoint receives:

```text
grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
assertion=<JWT>
```

For **client authentication**, the Token Endpoint receives:

```text
client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
client_assertion=<JWT>
```

The two URNs are different. Never substitute `client_assertion` for `assertion`, or swap the grant type with the client assertion type.

### 3.3. Even When Using JWTs, Token Issuance Policy Belongs to the AS

RFC 7523 defines an assertion exchange protocol. It does not supply a universal role/permission schema for every system.

For example, an AS might stipulate:

```text
Trusted issuer:
  https://broker.corp.example

Allowed subject namespace:
  employee:*

Audience:
  https://auth.example.org/oauth2/token

Allowed client:
  integration-portal

Allowed scopes:
  orders.read

Forbidden:
  role escalation
  cross-tenant subject substitution
  arbitrary audience
```

This policy is **implementation-defined**, not automatically granted just because a JWT contains a `scope` claim.

## 4. Structure of a JWT Assertion

A JWS-signed JWT has the form:

```text
BASE64URL(protected-header)
.
BASE64URL(claims-payload)
.
BASE64URL(signature)
```

Example JSON header before encoding:

```json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "broker-key-2026-11"
}
```

Example payload:

```json
{
  "iss": "https://broker.corp.example",
  "sub": "employee-725",
  "aud": "https://auth.example.org/oauth2/token",
  "iat": 1794800000,
  "nbf": 1794800000,
  "exp": 1794800090,
  "jti": "c6ca42e2-9aaf-4bb0-8a2e-19b60ce85ab5"
}
```

The timestamp numbers are illustrative only. In a real system they must be generated from the **current time**, never hard-coded.

### 4.1. Meaning of the Claims

| Claim | Role in JWT Bearer Profile | What to Verify |
|---|---|---|
| `iss` | Issuer that issued the assertion | Does it belong to a trusted issuer? |
| `sub` | Subject represented by the assertion | Is the subject valid and permitted by the contract? |
| `aud` | Intended recipient of the assertion, usually the AS/Token Endpoint | Does it match the Token Endpoint audience accepted by the AS? |
| `exp` | Expiration time of the assertion | Not expired, within TTL limit |
| `iat` | Issued-at time | Reasonable per clock skew/policy |
| `nbf` | Not valid before this timestamp | Has validity started? |
| `jti` | Unique ID of the assertion | Replay control during validity window |
| `kid` | Header to select the verification key | Select only from keys in the issuer's trust store |
| `alg` | JWS algorithm | In allowlist; reject `none` |
| Business claims | Tenant, purpose, permissions, actor, etc. | Matches schema and authorized source |

Under the JWT bearer profile, `iss`, `sub`, `aud`, and `exp` are key required claims of a JWT assertion; `iat`, `nbf`, and `jti` play supporting roles per profile/policy. For modern security, `jti`/short TTLs and replay detection are strongly worth considering when supported by the AS.

### 4.2. Assertion Audience Differs from Access Token Audience

The **assertion's audience** typically targets the AS or Token Endpoint:

```text
assertion.aud =
  https://auth.example.org/oauth2/token
```

The **audience of the access token issued by the AS** targets the Resource Server:

```text
access_token.aud =
  orders-api
```

Do not set `assertion.aud=orders-api` and expect the AS to accept it when the contract requires the Token Endpoint URL. Likewise, do not send an assertion whose audience is the Token Endpoint to the Orders API pretending it is an access token.

### 4.3. Business Claims Are Not Self-Enforcing

A JWT containing:

```json
{
  "sub": "employee-725",
  "role": "ADMIN",
  "scope": "orders.write"
}
```

does not compel the AS to grant `orders.write`. The AS must:

1. Determine whether the issuer is authorized to assert those claims.
2. Verify client registration and grant permissions.
3. Enforce subject, tenant, audience, and scope policies.
4. Decide the appropriate granted scopes.

Never let a client self-sign a JWT with any `sub`/`role` and gain higher privileges merely because its signature validates against a key the client registered without restriction.

## 5. Assertion Verification Flow at the Authorization Server

A trustworthy AS must enforce much more than signature verification.

```mermaid
flowchart TD
    REQ["POST /token, JWT Bearer Grant"]
    PARSE["Parse form and JWT with size limits"]
    T{"Grant type/issuer allowed?"}
    ALG{"JWS alg, kid, signature valid?"}
    CLAIM{"iss/sub/aud/exp/nbf/iat valid?"}
    REPLAY{"jti/TTL/replay policy satisfied?"}
    POLICY{"Client + subject + scopes<br/>+ tenant policy allowed?"}
    OK["Issue OAuth access token<br/>for matching resource/scope"]
    FAIL["OAuth error response"]

    REQ --> PARSE --> T
    T -->|"No"| FAIL
    T -->|"Yes"| ALG
    ALG -->|"No"| FAIL
    ALG -->|"Yes"| CLAIM
    CLAIM -->|"No"| FAIL
    CLAIM -->|"Yes"| REPLAY
    REPLAY -->|"No"| FAIL
    REPLAY -->|"Yes"| POLICY
    POLICY -->|"No"| FAIL
    POLICY -->|"Yes"| OK
```

### 5.1. Verifying Signatures Against the Right Issuer

When an assertion carries `iss=https://broker.corp.example`, the AS must look up **the keys registered/trusted for that specific issuer**. Never take `kid` or `jku` and automatically fetch keys from an arbitrary URL carried inside the JWT.

If the AS trusts multiple issuers, each issuer must have its own set of keys/algorithms and permissions. Never merge all keys into a single pool and try verifying JWTs from any issuer against any key without separating trust boundaries.

### 5.2. Never Trust "alg: none"

A JWT payload might claim:

```json
{"alg":"none"}
```

When a profile requires a signed assertion, accepting unsigned JWTs destroys proof of the issuer. The AS must enforce an algorithm allowlist and verify signatures properly; never blindly trust the `alg` declared by the token itself without policy checks.

### 5.3. Time Controls

JWT lifetimes should be **short**. The AS may tolerate a small clock skew, yet should not let an assertion remain valid for days when the business exchange only takes tens of seconds.

Checks:

```text
now < exp + allowedSkew
now + allowedSkew >= nbf (if present)
iat is not too far in the future
exp - iat is within TTL policy
```

This is an illustrative validation model; exact bounds belong to AS policy. Clients and servers need reliable clock synchronization.

### 5.4. Replay Detection

A still-valid JWT can be stolen by an attacker and replayed. `jti` is the assertion's unique ID, often paired with `iss` and TTL to detect repeated use.

A replay store might key entries as:

```text
(issuer, jti) -> "consumed", expires after JWT validity + skew
```

However, the check must be **atomic** across multiple AS instances. If two nodes simultaneously observe that `jti` has not been seen and both accept it, replay detection fails to work as intended.

JWT `jti` does not encrypt the payload and does not prevent assertion theft prior to first use. You still need TLS, short TTLs, client authentication, and trust policies.

## 6. JWT Bearer Grant Request at the Token Endpoint

### 6.1. Required Form Fields

A basic request:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&
assertion=eyJhbGciOiJSUzI1NiIs...
```

In real HTTP traffic, the body is a single-line form-urlencoded string; line breaks are added here for readability.

**`grant_type`**:

```text
urn:ietf:params:oauth:grant-type:jwt-bearer
```

**`assertion`**:

```text
JWT issued by an issuer trusted by the Authorization Server
```

### 6.2. Scope in the Request

Depending on the AS and grant policy, the client may request:

```text
scope=orders.read
```

That is a **requested scope**, not a guarantee that the new token will carry that scope. The AS determines the final scope based on the assertion, client, subject, audience, and policy.

### 6.3. Client Authentication When Required

The JWT bearer grant **does not automatically replace all OAuth client authentication requirements**. For a confidential client, the AS may require `client_secret_basic`:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Authorization: Basic <encoded-client-id-and-secret>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&
assertion=<signed-authorization-assertion>
```

Another AS might use mTLS or JWT client authentication. Whichever method is accepted must match the client registration and security policy.

### 6.4. Token Response

Example:

```json
{
  "access_token": "<new-oauth-access-token>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders.read"
}
```

The AS may issue an opaque token or a JWT. **Do not assume a refresh token**, ID token, or extra privileges are present; additional fields depend on the grant profile and AS.

The OAuth client will send the **returned `access_token`**, not the original JWT `assertion`, when calling the Orders API.

## 7. JWT Bearer Grant Does Not Mean private_key_jwt

This is the most frequently confused detail when configuring Spring Security Client.

### 7.1. private_key_jwt Is Client Authentication

In `private_key_jwt`, the client signs a JWT to prove **control of a private key** registered with the AS. Token Endpoint example:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&
client_assertion=<signed-client-authentication-jwt>&
scope=reports.read
```

Here **the grant is still `client_credentials`**. The JWT in `client_assertion` is solely a **client authentication credential**.

### 7.2. Claims of private_key_jwt

The payload typically includes:

```json
{
  "iss": "reports-service-client",
  "sub": "reports-service-client",
  "aud": "https://auth.example.org/oauth2/token",
  "exp": 1794800090,
  "iat": 1794800000,
  "jti": "b8abfa56-5106-4118-8a34-7e1f165e7083"
}
```

For JWT client authentication per RFC 7523, `sub` must identify the OAuth client ID, and `iss` identifies the client per profile. **It is not a user-delegation request**.

For a JWT Bearer **authorization grant**, `iss` may be a trusted token broker and `sub` the subject represented by the broker under an established trust policy.

### 7.3. Side-by-Side Comparison

| Characteristic | JWT Bearer Grant | private_key_jwt Client Authentication |
|---|---|---|
| Purpose | Present an assertion as an **authorization grant** | Authenticate the **OAuth client** |
| Primary form field | `assertion` | `client_assertion` |
| Form URN | `urn:ietf:params:oauth:grant-type:jwt-bearer` | `urn:ietf:params:oauth:client-assertion-type:jwt-bearer` |
| `grant_type` | **JWT Bearer URN** | May be `client_credentials`, `authorization_code`, `refresh_token`, etc. |
| `iss` | Trusted assertion issuer | Client identity per profile |
| `sub` | Subject per assertion/delegation policy | **Client ID** |
| What the JWT proves | An authorization assertion trusted by the AS | The client owns the registered key |
| Is user impersonation automatically allowed? | **No**; AS must have a delegation policy | **No**; this is client authentication |

### 7.4. Both Assertion Types Can Appear in the Same Request

An AS may support the **JWT bearer grant** while also requiring **private_key_jwt** to authenticate the client in the same token request:

```text
grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
assertion=<authorization-assertion-for-subject>
client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
client_assertion=<client-authentication-assertion>
```

The two JWTs **can have different issuers, subjects, audience policies, and signing keys**. They are not by default the same JWT string. Some AS-specific profiles might design around using the same credential, yet you should never assume or swap form fields without a defined contract.

## 8. JWT Bearer Grant Differs from OAuth Token Exchange RFC 8693

**OAuth 2.0 Token Exchange** (RFC 8693) is a separate extension grant for exchanging an existing token for another token—for example, across security domains/resources or under a delegation/impersonation policy.

### 8.1. Token Exchange Request

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange&
subject_token=<existing-security-token>&
subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Ajwt&
requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token&
resource=https%3A%2F%2Forders-api.example.org
```

This example uses `subject_token_type=urn:ietf:params:oauth:token-type:jwt`. In other systems, the subject token might be an access token, ID token, or another token type if supported and trusted by the AS.

### 8.2. Comparing the Two Request Shapes

**JWT Bearer Grant (RFC 7523):**

```text
grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
assertion=<jwt-assertion>
```

**Token Exchange (RFC 8693):**

```text
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
subject_token=<input-token>
subject_token_type=urn:ietf:params:oauth:token-type:jwt
resource=...
```

Both can turn a security credential into an OAuth access token, yet **their message formats and validation contracts differ**.

### 8.3. Delegation and Impersonation Are Not Automatic

Token Exchange can express two semantics:

- **Impersonation:** the new token represents a subject per policy; the actor is not necessarily represented.
- **Delegation:** the new token can indicate an actor acting on behalf of a subject, such as actor claims per profile.

The JWT Bearer Grant can also be used in subject-delegation scenarios under a contract, yet simply setting `sub` to user A does not mean the client is permitted to impersonate user A.

The Authorization Server must validate actor/client identity, subject, trust, tenant, and granted permissions. Never accept a `sub` from browser-submitted input and turn it into a delegated token.

### 8.4. Choosing the Right Mechanism

| Situation | Mechanism to Consider |
|---|---|
| Have a JWT assertion issued by a trusted issuer for the grant | **RFC 7523 JWT Bearer Grant** |
| Have an OAuth access token from API A and need a token for API B | **RFC 8693 Token Exchange**, if supported by the AS |
| Client uses an RSA/EC key to authenticate at the Token Endpoint | **private_key_jwt** |
| Workload needs its own token with no End-User | **client_credentials**, optionally with private_key_jwt/mTLS |
| Browser user signs in via OIDC | **Authorization Code + PKCE** |
| RP already holds a valid refresh token | **Refresh Token Grant** |
| Have an OIDC ID Token to exchange for another token | Only under a **token exchange contract** accepted by the AS; do not assume an ID Token works as a JWT grant |

## 9. A JWT Bearer Assertion Is Not Automatically an OIDC ID Token

A common mistake: "An ID Token is also a JWT signed by the OP, so passing it as `assertion` should work."

An ID Token has different properties:

```json
{
  "iss": "https://login.example.org",
  "sub": "user-725",
  "aud": "portal-client-id",
  "exp": 1794800090
}
```

Here `aud=portal-client-id` is the **Relying Party** where login happened. The JWT Bearer Grant normally requires the assertion's audience to be the **Authorization Server/Token Endpoint per policy**. An AS should not accept an ID Token scoped to a client as an arbitrary bearer grant.

Prerequisites if an AS intends to accept an input token:

1. What profile/trust contract does the AS declare as supported?
2. Are the token type and purpose valid?
3. Are the issuer and key registered?
4. Does the audience target the AS or a valid request target?
5. Are the subject and actor authorized?
6. Have replay, lifetime, scopes, and tenant policies been checked?

If a product wants to turn an OIDC ID Token or OAuth access token into another access token, **Token Exchange** may express that more accurately, still subject to AS support.

## 10. Trust Boundary Diagram When Using Assertions

```mermaid
flowchart LR
    subgraph Identity["Identity Domain"]
      User["Authenticated user or workload"]
      Broker["Trusted Token Broker"]
      IssuerKey["Issuer Signing Key"]
      User --> Broker
      IssuerKey --> Broker
    end

    subgraph OAuth["OAuth Authorization Domain"]
      Client["Spring OAuth2 Client"]
      AS["Authorization Server"]
      Trust["Trusted Issuers / Keys / Policies"]
      Client -->|"assertion + client authentication"| AS
      Trust --> AS
    end

    subgraph Resource["Resource Domain"]
      API["Orders API"]
      Domain["User / tenant / object authorization"]
      API --> Domain
    end

    Broker -->|"signed JWT assertion"| Client
    AS -->|"OAuth access token"| Client
    Client -->|"Bearer access token"| API
```

Mandatory relationships:

- **Broker → AS:** the AS trusts the issuer/keys and assertion-issuance permissions.
- **Client → AS:** the client is registered and uses an appropriate authentication method when required.
- **AS → API:** the API trusts access tokens issued by the AS for the right resource.
- **Subject → API:** the API/domain enforces actual permissions per user/workload and resource.

There is no shortcut from "the JWT is signed" to "the API must grant access".

## 11. Creating a JWT Assertion with Java and Nimbus JOSE + JWT

Below is an example of creating a **signed assertion** that **an issuer trusted by the AS** can issue. JWT signing code **does not grant issuance rights to an arbitrary service**: the AS must register the issuer, public key, claim contract, and policies.

### 11.1. Library

One option is **Nimbus JOSE + JWT**:

```groovy
dependencies {
    implementation 'com.nimbusds:nimbus-jose-jwt'
}
```

A Spring Boot project with appropriate dependency management can manage the version. Otherwise, specify a version controlled by the project's build.

### 11.2. AssertionSigner Using a Private Key

```java
import java.security.interfaces.RSAPrivateKey;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

public final class AssertionSigner {

    private final RSAPrivateKey privateKey;
    private final String keyId;
    private final String trustedIssuer;
    private final String tokenEndpointAudience;

    public AssertionSigner(
            RSAPrivateKey privateKey,
            String keyId,
            String trustedIssuer,
            String tokenEndpointAudience) {
        this.privateKey = privateKey;
        this.keyId = keyId;
        this.trustedIssuer = trustedIssuer;
        this.tokenEndpointAudience = tokenEndpointAudience;
    }

    public String signForSubject(String subject) throws Exception {
        Instant now = Instant.now();

        JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
            .type(JOSEObjectType.JWT)
            .keyID(keyId)
            .build();

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(trustedIssuer)
            .subject(subject)
            .audience(tokenEndpointAudience)
            .issueTime(Date.from(now))
            .notBeforeTime(Date.from(now.minusSeconds(5)))
            .expirationTime(Date.from(now.plusSeconds(90)))
            .jwtID(UUID.randomUUID().toString())
            .build();

        SignedJWT jwt = new SignedJWT(header, claims);
        jwt.sign(new RSASSASigner(privateKey));
        return jwt.serialize();
    }
}
```

Usage example:

```java
AssertionSigner signer = new AssertionSigner(
    issuerPrivateKey,                 // Retrieved from KMS/HSM or secure source
    "broker-key-2026-11",
    "https://broker.corp.example",
    "https://auth.example.org/oauth2/token"
);

String assertion = signer.signForSubject("employee-725");
```

These example inputs must be injected from secret/key management; never generate private keys inline or commit them to Git.

### 11.3. What Signing Code Does Not Guarantee on Its Own

The code above only produces a signed JWT. It **does not by itself prove**:

- That the service is authorized to issue assertions for `employee-725`.
- That the user consented or delegated authority to the OAuth client.
- That the AS trusts this issuer/key.
- That the claims comply with scope/tenant authorization policies.
- That the assertion has not been replayed.
- That the Resource Server will accept the issued access token.

Those checks must be enforced by the Token Broker and AS per the designed contract. If the client is not recognized by the AS as an assertion issuer, signing a JWT with its own private key is **not enough**.

### 11.4. Private Key Management

Never hard-code PEM/private key literals in source code, YAML, production test fixtures, or container images.

Best practices:

- Store private keys in a KMS/HSM or trusted secret manager.
- Restrict which service accounts can sign JWTs.
- Authorize by purpose and subject namespace.
- Use signing algorithms permitted by the AS; never let callers choose `alg`.
- Set `kid` properly for key rotation.
- Manage public keys/JWKS on the AS side under a trust policy.
- Never log newly signed assertions.
- Never sign payloads containing unvalidated claims taken directly from a request body.

## 12. Example: Calling the Token Endpoint with RestClient

In a **Servlet/backend integration service**, you can implement an HTTP client to invoke the extension grant. This demonstrates the protocol and **is not yet a provider automatically integrated into `OAuth2AuthorizedClientManager`**.

### 12.1. Token Response DTO

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public record OAuthTokenResponse(
    @JsonProperty("access_token") String accessToken,
    @JsonProperty("token_type") String tokenType,
    @JsonProperty("expires_in") Long expiresIn,
    @JsonProperty("scope") String scope,
    @JsonProperty("refresh_token") String refreshToken
) {}
```

A real token response may contain additional fields. Response handling must validate `access_token`, `token_type`, `expires_in`, and `scope` per the contract; never assume every field is always present or of the expected type.

### 12.2. JWT Bearer Token Client

```java
import java.util.Set;

import org.springframework.http.MediaType;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;

public final class JwtBearerTokenClient {

    public static final String JWT_BEARER_GRANT =
        "urn:ietf:params:oauth:grant-type:jwt-bearer";

    private final RestClient restClient;
    private final String tokenUri;
    private final String clientId;
    private final String clientSecret;

    public JwtBearerTokenClient(
            RestClient.Builder builder,
            String tokenUri,
            String clientId,
            String clientSecret) {

        this.restClient = builder.build();
        this.tokenUri = tokenUri;
        this.clientId = clientId;
        this.clientSecret = clientSecret;
    }

    public OAuthTokenResponse exchange(
            String signedAssertion,
            Set<String> requestedScopes) {

        MultiValueMap<String, String> form =
            new LinkedMultiValueMap<>();

        form.add("grant_type", JWT_BEARER_GRANT);
        form.add("assertion", signedAssertion);

        if (requestedScopes != null && !requestedScopes.isEmpty()) {
            form.add("scope", String.join(" ", requestedScopes));
        }

        return restClient.post()
            .uri(tokenUri)
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .headers(headers ->
                headers.setBasicAuth(clientId, clientSecret))
            .body(form)
            .retrieve()
            .body(OAuthTokenResponse.class);
    }
}
```

Example assumptions:

- The AS registered a confidential client with `client_secret_basic`.
- `tokenUri` is a **fixed HTTPS Token Endpoint provided by server configuration**.
- The assertion is created by an issuer trusted by the AS.
- The form request and response match the AS-specific contract.

Do not use `setBasicAuth(...)` if the AS registers client authentication via `private_key_jwt` or mTLS; replace it with the appropriate implementation. Never allow callers/browsers to pass an arbitrary `tokenUri`, or the request could send client secrets and assertions to an untrusted host.

### 12.3. Why Should You Avoid Logging HTTP Bodies?

The form body contains `assertion`, which is a sensitive credential. HTTP interceptors, proxies, and wire logs can record the entire request:

```text
grant_type=...
assertion=eyJhbGciOi...
```

Log only metadata such as registration ID, issuer alias, error code, and request duration—never log JWTs/assertions or raw client authentication credentials.

### 12.4. Do Not Retain Used JWT Assertions for Infinite Retries

A short-lived assertion may already have been accepted by the AS or have its `jti` marked as consumed. If a network timeout happens after the AS processes the request but before the client receives the response, retrying the same assertion may be rejected by replay detection.

If policy permits retrying a transient error, determine whether a **new assertion should be issued** and how to guard idempotency/replay. Never loop infinitely over the same `assertion`.

## 13. Building an OAuth2AccessToken from the Token Response

After the Token Endpoint issues a token, the application can represent the result as an `OAuth2AccessToken` to integrate with Spring Security abstractions.

```java
import java.time.Instant;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.security.oauth2.core.OAuth2AccessToken;

public final class AccessTokenFactory {

    public OAuth2AccessToken create(OAuthTokenResponse response) {
        if (response == null
                || response.accessToken() == null
                || response.accessToken().isBlank()) {
            throw new IllegalArgumentException("Missing access_token");
        }

        if (!"Bearer".equalsIgnoreCase(response.tokenType())) {
            throw new IllegalArgumentException("Unexpected token_type");
        }

        if (response.expiresIn() == null
                || response.expiresIn() <= 0) {
            throw new IllegalArgumentException("Invalid expires_in");
        }

        Set<String> scopes =
            response.scope() == null || response.scope().isBlank()
                ? Set.of()
                : Arrays.stream(response.scope().trim().split("\\s+"))
                    .filter(s -> !s.isBlank())
                    .collect(Collectors.toUnmodifiableSet());

        Instant issuedAt = Instant.now();
        Instant expiresAt =
            issuedAt.plusSeconds(response.expiresIn());

        return new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            response.accessToken(),
            issuedAt,
            expiresAt,
            scopes
        );
    }
}
```

This is **illustrative response-handling code**, not an `OAuth2AccessTokenResponseClient` registered in a manager. In production, properly handle omitted `scope` per the OAuth contract (depending on the AS, falling back to requested scopes or a known grant policy), clock skew, and deserialization errors.

**Never attach broader scopes than the token response/AS policy** by taking all requested scopes and treating them as actually granted when the AS returned a narrower set.

### 13.1. Do Not Modify expiresAt to Make a Token "Live Longer"

`expires_in` and token lifetimes are determined by the AS. Altering the value on the client will not make the Resource Server continue accepting an expired access token.

### 13.2. Access Tokens Do Not Replace Principals

`OAuth2AccessToken` carries the credential used to call an API. If the assertion represents a specific subject, the system must still track the **authorized subject, client identity, and domain permissions**. Do not treat token issuance as equivalent to an active OIDC-authenticated user Web Session.

## 14. Does Spring Security Support the JWT Bearer Grant by Default?

In typical OAuth2 Client configurations, `OAuth2AuthorizedClientProviderBuilder` supports grants such as:

```java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
```

**Do not assume `JWT Bearer Grant` is supported merely by adding the grant type string to `application.yml`.**

Extension grants like RFC 7523 typically require:

1. A `ClientRegistration` describing the custom grant type (if integrating into the client framework).
2. A way to obtain assertions from a trusted issuer.
3. A token response client that builds the exact form request.
4. A custom `OAuth2AuthorizedClientProvider`, if you want to use `OAuth2AuthorizedClientManager`.
5. Appropriate persistence and authorization success/failure handling components.
6. TTL/replay controls, client authentication, and scope governance.

Built-in support, API classes, and builder names depend on your Spring Security version; consult the documentation for **your project's version** before choosing extension points. Never drop synchronous Servlet APIs into a reactive stack out of habit.

## 15. Extending OAuth2AuthorizedClientProvider

### 15.1. Related Objects

```text
ClientRegistration
      |
      v
OAuth2AuthorizedClientManager
      |
      v
OAuth2AuthorizedClientProvider (custom JWT Bearer)
      |
      v
TrustedAssertionSupplier
      |
      v
JWT Bearer Token Client
      |
      v
Authorization Server Token Endpoint
      |
      v
OAuth2AccessTokenResponse / OAuth2AuthorizedClient
      |
      v
OAuth2AuthorizedClientService / Repository
```

When using a manager, **the provider owns the grant logic**; the manager handles loading/saving authorized clients per context and success/failure policy.

### 15.2. Custom Grant Type

You can represent the grant type with:

```java
import org.springframework.security.oauth2.core.AuthorizationGrantType;

AuthorizationGrantType jwtBearerGrant =
    new AuthorizationGrantType(
        "urn:ietf:params:oauth:grant-type:jwt-bearer"
    );
```

Do not confuse it with:

```java
AuthorizationGrantType.CLIENT_CREDENTIALS
```

They are two different grants, even though both execute at the Token Endpoint.

### 15.3. ClientRegistration in Java

An example registration:

```java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

ClientRegistration assertionRegistration =
    ClientRegistration.withRegistrationId("partner-assertion")
        .clientId(clientId)
        .clientSecret(clientSecret)
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(new AuthorizationGrantType(
            "urn:ietf:params:oauth:grant-type:jwt-bearer"))
        .tokenUri("https://auth.example.org/oauth2/token")
        .scope("orders.read")
        .build();
```

The `clientId` and `clientSecret` variables come from backend configuration/secret management. Depending on your Spring Security version/metadata provider, the builder may have extra constraints or required fields; match your actual API.

This shows how to specify a custom `grantType` in `ClientRegistration`. **Creating a registration does not automatically execute the JWT Bearer Grant** without supporting provider/token client wiring.

## 16. Custom JWT Bearer Provider Pseudocode

An extension provider typically performs these steps:

1. Check the registration's grant type.
2. Check whether an existing authorized client is still usable.
3. Obtain a **fresh assertion** from a trusted issuer/supplier.
4. Call the Token Endpoint with the JWT Bearer Grant.
5. Convert the token response into an `OAuth2AccessToken`.
6. Return the new `OAuth2AuthorizedClient` to the manager.
7. Let the manager's success handler persist the result in the repository/service.

### 16.1. Conceptual Interface for an Assertion Supplier

```java
public interface TrustedAssertionSupplier {

    String issueAssertion(
        String registrationId,
        String principalName
    );
}
```

**Security contract:** only a trusted component may call the supplier, and it may only issue assertions for principals/subjects it is authorized to represent. Never pass a `principalName` taken from an arbitrary URL parameter.

### 16.2. Illustrative Provider Code

```java
import java.time.Instant;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

public final class JwtBearerAuthorizedClientProvider
        implements OAuth2AuthorizedClientProvider {

    private static final String GRANT =
        "urn:ietf:params:oauth:grant-type:jwt-bearer";

    private final TrustedAssertionSupplier assertions;
    private final JwtBearerTokenClient tokenClient;
    private final AccessTokenFactory tokenFactory;

    public JwtBearerAuthorizedClientProvider(
            TrustedAssertionSupplier assertions,
            JwtBearerTokenClient tokenClient,
            AccessTokenFactory tokenFactory) {
        this.assertions = assertions;
        this.tokenClient = tokenClient;
        this.tokenFactory = tokenFactory;
    }

    @Override
    public OAuth2AuthorizedClient authorize(
            OAuth2AuthorizationContext context) {

        var registration = context.getClientRegistration();

        if (!GRANT.equals(
                registration.getAuthorizationGrantType().getValue())) {
            return null;
        }

        OAuth2AuthorizedClient existing = context.getAuthorizedClient();

        if (existing != null
                && existing.getAccessToken().getExpiresAt() != null
                && existing.getAccessToken().getExpiresAt()
                    .isAfter(Instant.now().plusSeconds(60))) {
            // Per provider contract: no reauthorization needed.
            return null;
        }

        String principalName = context.getPrincipal().getName();

        String assertion = assertions.issueAssertion(
            registration.getRegistrationId(), principalName);

        var response = tokenClient.exchange(
            assertion, registration.getScopes());

        OAuth2AccessToken accessToken = tokenFactory.create(response);

        return new OAuth2AuthorizedClient(
            registration,
            principalName,
            accessToken
        );
    }
}
```

This is an **illustrative integration skeleton**, not a production-ready library:

- `TrustedAssertionSupplier` must be protected with strict identity/authorization checks.
- `JwtBearerTokenClient` in this example uses synchronous `RestClient`.
- The logic does not model refresh tokens because the grant may instead require issuing a fresh assertion.
- A real provider needs policies for exception mapping, error classification, clock skew, response scopes, token types, and concurrency.
- There is no key cache, certificate validation, or distributed replay handling in this snippet.
- If the AS returns a refresh token under an extension, supporting it requires an explicit contract and storage mechanism rather than assumptions.

Still, the code draws the exact boundary: **the JWT bearer grant is a custom provider**, not something `clientCredentials()` or `refreshToken()` handles automatically.

### 16.3. Manager Integration with a Custom Provider

For scheduled/backend workers using a service-based manager:

```java
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

OAuth2AuthorizedClientProvider provider =
    new JwtBearerAuthorizedClientProvider(
        assertionSupplier,
        jwtBearerTokenClient,
        accessTokenFactory
    );

var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
    registrationRepository,
    authorizedClientService
);

manager.setAuthorizedClientProvider(provider);

OAuth2AuthorizedClientManager authorizedClientManager = manager;
```

These dependencies must be configured/injected in the application context; this shows the wiring structure.

During Servlet requests, `DefaultOAuth2AuthorizedClientManager` with `OAuth2AuthorizedClientRepository` can be used if tokens must tie to a user web session. However, JWT assertion grants have their own contract; select the manager matching your context and **never fabricate a user session**.

### 16.4. Watch Manager Success/Failure Handlers

When a provider returns a new authorized client, the manager relies on its authorization success handler to persist the token. Replacing that handler with a lambda that only logs will prevent new tokens from being persisted, causing the client to request a new token on every call.

The failure handler must handle grant errors appropriately; do not treat an `invalid_grant` on a JWT assertion as a reason to wipe all user tokens or disable the client registration system-wide.

## 17. Differences Between Servlet and Reactive When Customizing Grants

`JwtBearerTokenClient` using `RestClient` performs a **blocking HTTP call**. That fits a Servlet backend service with a managed thread pool, yet **must not be called directly on a Reactor Netty event loop** inside a WebFlux authentication path.

### 17.1. Servlet

You can use:

```text
OAuth2AuthorizedClientManager (synchronous)
   -> custom OAuth2AuthorizedClientProvider
   -> RestClient Token Endpoint call
```

with timeouts, connection pooling, and credential protection.

### 17.2. Reactive

Design the reactive equivalent:

```text
ReactiveOAuth2AuthorizedClientManager
   -> reactive provider/extension
   -> WebClient Token Endpoint call
   -> Mono<OAuth2AuthorizedClient>
```

Conceptual example of calling the Token Endpoint with WebClient:

```java
import org.springframework.http.MediaType;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public Mono<OAuthTokenResponse> exchangeReactive(
        WebClient client,
        String tokenUri,
        String assertion) {

    var form = new LinkedMultiValueMap<String, String>();
    form.add("grant_type",
        "urn:ietf:params:oauth:grant-type:jwt-bearer");
    form.add("assertion", assertion);

    return client.post()
        .uri(tokenUri)
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .bodyValue(form)
        .retrieve()
        .bodyToMono(OAuthTokenResponse.class);
}
```

This reactive snippet illustrates the **form body**; it **does not yet include client authentication**. In a real implementation, add client authentication per the registration, HTTPS/timeouts, and error mapping. Do not treat this as a complete RFC 7523 implementation.

Never call `.block()` in a Reactive HTTP filter just to fetch a token synchronously. If signing assertions requires a synchronous HSM/SDK, offload it in a controlled manner or use the HSM's async API.

## 18. Choosing a Safe Assertion Source

There are two common categories of sources.

### 18.1. An Issuer Outside the Application Generates Assertions

For example, a trusted broker returns a JWT assertion to the Spring service after authenticating and checking permissions.

```text
Trusted Broker
  -> signed assertion with iss/sub/aud/exp/jti
  -> Spring OAuth client
  -> AS Token Endpoint
```

The application must define which brokers are trusted and how assertions are securely obtained. Never let users paste an arbitrary JWT into a request and have the client exchange it for an OAuth token with higher privileges.

### 18.2. The Application Itself Is an Issuer Under a Contract

A system may be recognized by the AS as an assertion issuer. In that case, the service signs JWTs using the **issuer's** private key—not an ad-hoc key created by a developer.

The AS must restrict which subjects/scopes that issuer may assert. Having signing authority does not entitle an issuer to mint assertions for every user or tenant.

### 18.3. Never Take Assertions from Untrusted Headers

Anti-pattern:

```java
@PostMapping("/exchange")
public String exchange(@RequestHeader("X-User-JWT") String assertion) {
    // Sends any arbitrary assertion straight to the AS.
}
```

Even if the AS validates the JWT, exposing such an endpoint turns the app into a **token exchange proxy/confused deputy**, giving callers an uncontrolled path to mint tokens.

Better: authenticate the caller, verify exchange authorization policy, constrain issuer/subject/audience, apply rate limits, and avoid handing raw OAuth access tokens to the browser unless the backend architecture permits it.

## 19. Controlling Subject Permissions and Impersonation

The JWT Bearer Grant can present an assertion about a subject. However, **putting `sub=employee-725` does not automatically prove authority to act for that person**.

The AS should verify:

1. Is the issuer allowed to assert subjects within this namespace?
2. Is the current client allowed to use the JWT Bearer Grant with that issuer?
3. Is the subject locked or revoked?
4. Which scopes may the client request for that subject?
5. Are there tenant/organization constraints?
6. Is an actor/delegation chain required?
7. Was prior user consent or authorization required?
8. Does the Resource Server enforce its own object-level authorization?

An assertion signed by a trusted issuer whose `sub` lies outside the issuer's authority must still be rejected.

### 19.1. Tenant Isolation Example

```text
assertion:
  iss = corporate-broker
  sub = employee-725
  tenant = tenant-A

client:
  allowed_tenants = [tenant-A]

request:
  scope = orders.read

AS:
  may issue access token limited to tenant-A

Orders API:
  must still verify order belongs to allowed tenant
```

If the Orders API skips tenant/object checks and only inspects `scope=orders.read`, broken object-level authorization remains a risk.

### 19.2. Roles Do Not Automatically Come from Scopes

Access token scopes describe permissions granted to the token/client; user or workload roles belong to domain policy. Never blindly convert `scope=orders.read` into `ROLE_ORDER_ADMIN`.

## 20. Sample Request and Response: Step-by-Step Walkthrough

### 20.1. Assertion Issued

The issuer creates:

```json
{
  "iss": "https://broker.corp.example",
  "sub": "employee-725",
  "aud": "https://auth.example.org/oauth2/token",
  "iat": 1794800000,
  "exp": 1794800090,
  "jti": "75d9bc73-afc0-43e0-9abf-d5f0a4210a4c"
}
```

The issuer signs the JWT with key `kid=broker-key-2026-11` registered with the AS.

### 20.2. Spring Client Sends the Grant

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&
assertion=<signed-jwt>&scope=orders.read
```

### 20.3. AS Verifies and Issues the Access Token

```json
{
  "access_token": "<oauth-access-token>",
  "token_type": "Bearer",
  "expires_in": 600,
  "scope": "orders.read"
}
```

### 20.4. Client Calls the Resource Server

```http
GET /api/orders HTTP/1.1
Host: orders-api.example.org
Authorization: Bearer <oauth-access-token>
```

### 20.5. Resource Server Enforces Permissions

```text
token signature/introspection valid
AND issuer authorized
AND audience = orders-api
AND token not expired
AND scope includes orders.read
AND subject can read requested orders
AND tenant policy holds
```

**No request sends the JWT `assertion` directly to the Orders API as an access token**, unless the system defines a completely different API profile. In this OAuth2 JWT Bearer Grant, the token used for the API is **the token returned by the AS**.

## 21. Contract Testing Against the Authorization Server

Before production deployment, integration requires explicit contract test scenarios.

| Scenario | Expected Result |
|---|---|
| Assertion signed by trusted issuer with valid claims | AS may issue token per policy |
| JWT payload tampered after signing | Rejected due to invalid signature |
| `alg=none` | Rejected if profile requires signed assertions |
| Unregistered issuer | Rejected |
| `aud` targets Resource Server instead of Token Endpoint per policy | Rejected |
| `exp` in the past | Rejected |
| `nbf` in the future beyond skew | Rejected |
| JWT with already-used `jti` while replay policy enabled | Rejected |
| Client requests scope outside allowed scopes | Rejected or narrowed per AS policy |
| Wrong client auth credentials | Rejected |
| `sub` outside issuer/client authorization | Rejected |
| Tenant claim violates policy | Rejected |
| AS returns access token for a different audience | API rejects |
| Valid assertion, yet user lacks permission for the object | API rejects |
| Concurrent requests reusing one assertion | Consistent replay handling per policy |
| Key rotation in progress | Old/new keys accepted under control during transition window |

**A single test proving "the JWT has a valid signature" is insufficient** to verify the security of the JWT Bearer Grant.

## 22. Common OAuth2 Errors

The Token Endpoint may return:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant",
  "error_description": "JWT assertion rejected"
}
```

Or:

```json
{
  "error": "invalid_client"
}
```

### 22.1. Distinguishing Errors

| Error / Symptom | Possible Cause | What to Check |
|---|---|---|
| `unsupported_grant_type` | AS has not enabled JWT Bearer Grant | AS capabilities/client policy |
| `invalid_grant` | Expired assertion, bad signature, wrong audience, replay, or disallowed subject | Issuer/claims/key/replay/policy |
| `invalid_client` | Wrong client ID/secret, mTLS, or private_key_jwt | Client authentication |
| `invalid_scope` | Requested scope not permitted | Registration/grant/subject rights |
| `invalid_request` | Missing `assertion`, bad form encoding, or invalid parameters | HTTP Token Endpoint request |
| `unauthorized_client` | Client is not permitted to use JWT Bearer Grant | Client registration at AS |
| HTTP 429 | AS rate limit | Token reuse, throttling, backoff |
| HTTP 5xx/timeout | AS/network instability | Connection/TLS/timeouts; avoid blind retries |
| Token issued, yet API returns 401 | Wrong audience/issuer/expiry/token type | Resource Server validation |
| Token issued, yet API returns 403 | Missing scope or domain authorization | API permissions |
| Fails on only one node | Divergent clock skew/keys/config | Deployment configuration and time sync |
| Sudden `invalid_grant` after key rotation | AS unaware of new `kid`/public key | Key distribution and rotation rollout |

Never log raw assertions or private keys while debugging errors. Log error codes, issuer alias, client registration ID, non-secret correlation ID, and request duration.

### 22.2. Different HTTP Status Codes

The Token Endpoint returning `invalid_grant` does not mean the API is returning 403. That failure occurs at the **token request step**, before the client obtains a new access token.

When the client receives an access token yet the API returns 401/403, diagnose **Resource Server token validation and authorization** rather than assuming the AS is broken.

## 23. Handling Expired or Reused Assertions

JWT assertions are normally short-lived. If code caches an assertion in a singleton variable and reuses it across every request:

```java
// Unsuitable for short-lived/one-time assertions.
private static String cachedAssertion;
```

the AS will reject it due to `exp` or replay detection.

A more appropriate flow is:

```text
Need new token
  -> fetch/mint fresh assertion from trusted issuer
  -> send to Token Endpoint
  -> receive OAuth access token
  -> reuse access token per expiresAt
  -> when token needs reissue: fetch fresh assertion
```

Avoid **requesting a new token before every API call** when the current token is still valid and reusable under policy. Doing so strains the issuer/AS and increases the risk of improper assertion reuse.

### 23.1. Concurrent Requests

If multiple threads simultaneously issue/assert JWTs and exchange tokens, apply concurrency/rate limits:

- Multiple callers should not repeatedly send the same signed assertion if the AS enforces one-time `jti`.
- Each fresh assertion needs a truly unique `jti`.
- Access tokens must be stored under the right principal/registration.
- If the AS issues tokens for different subjects, never cache solely by registration ID.
- If a token exchange times out, never blindly retry the exact same assertion.

## 24. Issuing, Storing, and Managing OAuth2AuthorizedClient

An `OAuth2AuthorizedClient` holds:

```text
ClientRegistration
principalName
OAuth2AccessToken
optional OAuth2RefreshToken
```

With the JWT Bearer Grant, once the application receives an OAuth access token, it can persist the authorized client keyed by principal/registration for subsequent API calls.

### 24.1. Principal and Assertion Subject Are Not Automatically Identical

`principalName` in `OAuth2AuthorizedClient` is the Spring Security key associating the record with a principal. `sub` in the JWT assertion is the subject asserted by the issuer under the grant.

They **may be related, yet do not have to be the exact same string**. In delegated access, the application must clearly define the mapping and preserve subject/tenant identity.

Example:

```text
authorized client key:
  registrationId = partner-assertion
  principalName = broker-user-725

JWT assertion:
  iss = https://broker.corp.example
  sub = employee-725

OAuth access token:
  audience = orders-api
  permissions = scoped by AS policy
```

Never take a principal name from a query parameter `?subject=...` to arbitrarily retrieve another user's token.

### 24.2. Do Not Persist Raw Assertions Forever Alongside Access Tokens

Once an assertion has been exchanged for an access token, there is usually no reason to store the old JWT assertion in the authorized client store. It has a short TTL and may be a one-time credential.

If assertions must be stored for audit or protocol-specific workflows, define clear threat modeling, retention, and encryption; usually it is better to log event metadata/IDs rather than raw signed JWTs.

### 24.3. When Should Refresh Tokens Be Stored?

The JWT Bearer grant type does not guarantee the AS will issue a refresh token. If an AS-specific policy returns a refresh token, verify the contract and protect/persist it under the refresh grant workflow, without assuming a refresh token is always present.

### 24.4. Revocation Considerations

An issued access token can remain valid until its expiration even after the original assertion has expired. Therefore:

- Choose appropriate access token TTLs.
- Consider revocation/introspection when permissions change.
- Enforce domain permissions at the API when rapid revocation is needed.
- Never confuse `assertion.exp` with `accessToken.expiresAt`.

## 25. Spring OAuth2 Login and JWT Bearer Grant Are Separate Flows

### 25.1. OAuth2/OIDC Login

In a browser login:

```text
Browser
  -> /oauth2/authorization/company
  -> OP /authorize
  -> /login/oauth2/code/company
  -> Token Endpoint
  -> OIDC ID Token
  -> Authenticated principal/web session
```

Spring Security `oauth2Login()` handles the browser authorization code flow and establishes the principal.

### 25.2. JWT Bearer Grant

```text
Trusted assertion issuer
  -> signed JWT assertion
  -> Spring OAuth client
  -> Token Endpoint JWT bearer grant
  -> OAuth access token
  -> Resource Server
```

There does not have to be a browser, authorization redirect, login callback, or ID Token. Spring Security `oauth2Login()` **does not automatically process the JWT Bearer Grant** merely because OIDC login is enabled.

An application can combine both, yet must keep each flow's principal/session and token lifecycle distinct.

### 25.3. Do Not Create a Fake OidcUser from an Assertion

An assertion accepted by the AS does not mean the application authenticated an OIDC End-User through `oauth2Login()`. Never construct an `OidcUser` or populate an authenticated `SecurityContext` from an assertion that has not gone through proper authentication validation.

If the application wants to link an assertion to a local user, it needs full verification/authorization and an explicit security context design.

## 26. When a JWT Assertion Comes from a Legacy System

A common integration scenario:

- System A uses JWT assertions signed by a legacy STS.
- System B is a Spring Boot client that needs to call a new OAuth API.
- The new AS supports the JWT Bearer Grant with trusted issuer A.

Migration workflow:

1. Register trusted issuer A, its public keys/algorithms, and allowed subject namespace at the AS.
2. Register OAuth client B, the JWT bearer grant type, and its client authentication method.
3. Determine the Token Endpoint audience required by the AS.
4. Issue short-lived JWT assertions with unique `jti` and proper claims.
5. Define subject/tenant/role mappings; do not forward arbitrary claims.
6. Exchange assertions for OAuth access tokens.
7. Have the Resource Server accept only OAuth access tokens, removing direct trust in legacy JWTs.
8. Store authorized clients and track token expiry.
9. Design revocation, key rotation, and auditing.
10. Gradually retire dependencies on legacy assertions once the new architecture supports the appropriate grants.

The key architectural win here is **trust-domain separation**: the Resource Server no longer needs to accept every legacy JWT; the AS serves as the centralized policy and token-issuance point.

## 27. Multi-Tenant and Multiple Issuers

In multi-partner systems, the AS may trust multiple assertion issuers:

```text
issuer = https://sts.partner-a.example
  allowedClientIds = [client-a]
  allowedTenants = [tenant-a]
  allowedScopes = [orders.read]

issuer = https://sts.partner-b.example
  allowedClientIds = [client-b]
  allowedTenants = [tenant-b]
  allowedScopes = [orders.read, reports.read]
```

Never treat `sub=employee-725` across two issuers as the same person. External identity should be represented as:

```text
(issuer, subject)
```

Not merely by `sub` or email.

### 27.1. Issuer Confusion Risk

If a JWT claims `iss=partner-a`, yet the AS validates it using partner-b's public key because both share `kid=main`, the trust policy breaks.

`kid` is only a key identifier **within the context of an issuer/key set**, not a global identifier shared across issuers.

### 27.2. Scope Names Can Share Strings Yet Mean Different Things

`orders.read` may be defined differently by two AS/providers. In multi-issuer or multi-Resource-Server architectures, policies must specify exact scope semantics and audiences rather than matching scope strings alone.

### 27.3. Never Accept Issuers from Arbitrary URLs

Never allow a browser to send:

```text
POST /exchange?issuer=https://arbitrary.example
```

and then fetch JWKS/discovery from that URL to trust the JWT. That introduces SSRF and issuer-trust-bypass risks. Issuers must come from a server-side allowlist/trust registry.

## 28. Signing JWT Assertions and Key Rotation

### 28.1. Key ID

Header:

```json
{
  "alg": "RS256",
  "kid": "broker-key-2026-11",
  "typ": "JWT"
}
```

`kid` lets the AS select the matching public key from the key set registered for that issuer.

### 28.2. Controlled Rotation

A typical rotation workflow:

1. Generate a new key pair in KMS/HSM.
2. Provide the new public key/JWKS to the AS under the trust policy.
3. Start signing new assertions with the new `kid`.
4. Retain the old key for a short window to handle still-valid assertions if policy allows.
5. Stop signing with the old private key.
6. Revoke the old public key after the transition period.
7. Audit `invalid_grant`/unknown `kid` errors.

If the issuer switches `kid` before the AS receives the new public key, all new assertions will fail. If the AS keeps old keys too long, exposure in the event of a key compromise increases.

### 28.3. Never Let a JWT Choose Its Own Verification URL

JWS headers such as `jku`/`x5u` must be handled with extreme caution. The AS should never fetch an arbitrary URL supplied by an attacker's assertion and trust keys hosted there.

Trusted key origins must be managed server-side.

## 29. Protecting Assertions and Access Tokens in Operations

### 29.1. Sensitive Values

| Data | Sensitivity | Safeguard |
|---|---|---|
| Private signing key | Very high | KMS/HSM, ACL, rotation, never log |
| `client_secret` | Very high | Secret manager, TLS, rotation |
| Signed assertion | High while valid | Short TTL, exclude from logs, replay controls |
| OAuth access token | High | TLS, secure storage, audience/scopes |
| Refresh token (if any) | Very high | Encryption, rotation/revocation policy |
| `kid` | Metadata | May be logged under control; does not replace key trust |
| `jti` | Correlation/replay identifier | Short-lived storage, no sensitive PII |
| Granted scopes | Authorization metadata | Do not treat as unconditionally public data |

### 29.2. Safe Logging

Example:

```text
event=jwt_bearer_grant
registrationId=partner-assertion
issuerAlias=corp-broker
subjectType=employee
grantType=jwt-bearer
outcome=invalid_grant
elapsedMs=180
correlationId=<non-secret-id>
```

Never log:

```text
assertion=eyJ...
Authorization: Basic <client-credentials>
client_assertion=eyJ...
access_token=eyJ...
refresh_token=...
private_key=-----BEGIN PRIVATE KEY-----
```

`jti` can help correlate replay checks, yet avoid logging raw PII in `sub`/claims. When logging `jti`, enforce retention and access controls.

### 29.3. HTTPS and Token Endpoint Trust

The Token Endpoint must be configured from a trusted backend source using HTTPS and certificate validation. Never disable TLS verification to bypass dev-environment issues and carry that setting into production.

If an HTTP client follows redirects, ensure it **never forwards assertions/client secrets to a different host**. A Token Endpoint normally should not redirect to arbitrary domains.

## 30. Anti-Patterns to Avoid

### 30.1. Self-Signing a JWT to Claim Admin Privileges

```json
{
  "iss": "my-app",
  "sub": "ceo",
  "role": "ADMIN"
}
```

If the AS does not recognize the issuer and its right to assert that subject, it must reject the request. Never treat a valid signature alone as sufficient reason to allow impersonation.

### 30.2. Confusing grant_type with client_assertion_type

Wrong:

```text
grant_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
```

Correct for the JWT Bearer Grant:

```text
grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
assertion=<JWT>
```

### 30.3. Using an RP's ID Token as an Assertion When Audience Mismatches

An OIDC ID Token normally targets the RP client ID, not the Token Endpoint. Never strip audience validation just to accept it.

### 30.4. Sending an Assertion to an API as an Access Token

APIs typically expect **access tokens issued by the AS**, not JWT assertions intended for the Token Endpoint.

### 30.5. Skipping exp, aud, or Signature Validation

When a profile requires a signed JWT assertion, skipping these checks breaks the trust boundary.

### 30.6. Caching Assertions Indefinitely

Assertions have short TTLs and typically have replay policies. When a fresh OAuth access token is needed, obtain a fresh assertion securely.

### 30.7. Reusing One jti Across All Assertions

`jti` should be unique; using a constant breaks replay detection or causes the client to be rejected on the second request.

### 30.8. Putting JWTs in URLs

Never place assertions in Token Endpoint query parameters or logs. Use an HTTPS POST form body with redaction.

### 30.9. Letting User Input Determine tokenUri

Client secrets/assertions can leak through untrusted endpoints. Token URIs must come from a server-side allowlist configuration.

### 30.10. Configuring Only the Custom Grant String Without a Provider

`ClientRegistration` records the grant type, yet cannot execute Token Endpoint JWT assertion requests on its own.

### 30.11. Running Blocking RestClient Calls on the WebFlux Event Loop

Use a reactive token response client or isolate blocking I/O intentionally. Never call `block()` inside a reactive request handler.

### 30.12. Sharing One Token Cache Across Multiple Subjects

When a grant represents individual users/tenants, the token cache must key on the exact principal/client/resource context.

### 30.13. Skipping Object-Level Authorization at the API

An AS granting a scope does not mean a user can view every order. The Resource Server must authorize specific data objects.

### 30.14. Retrying invalid_grant Infinitely

An expired or replayed assertion will not become valid by resending it repeatedly.

### 30.15. Logging Assertions to Debug

Signed JWTs can contain subject identifiers and act as live credentials. Logging raw assertions increases theft and identity-exposure risks.

## 31. Practical Implementation Checklist

When a project genuinely requires the JWT Bearer Grant:

1. **Identify the right grant.** The JWT is an authorization assertion, distinct from `private_key_jwt` or Token Exchange.
2. **Confirm AS support for RFC 7523** and that the client is permitted to use this grant type.
3. **Define the trust contract:** issuer, public keys, subject namespace, allowed clients, scopes, tenants, Token Endpoint audience.
4. **Define client authentication:** `client_secret_basic`, `private_key_jwt`, mTLS, or whichever method the AS accepts.
5. **Design the issuer/signer:** private keys in KMS/HSM, algorithm allowlist, and key rotation policy.
6. **Issue short-lived assertions:** `iss`, `sub`, `aud`, `exp`, and required claims; unique `jti` per replay policy.
7. **Submit assertions via POST form-urlencoded** with the proper `grant_type` and `assertion`.
8. **Handle the token response:** check token type, expiry, and granted scopes; never treat the assertion as an API access token.
9. **Integrate Spring Security at the right level:** a client adapter first, or a custom `OAuth2AuthorizedClientProvider`/manager if unified lifecycle management is needed.
10. **Match Servlet vs. Reactive to your stack** and keep blocking I/O off the event loop.
11. **Persist authorized clients keyed by principal/registration/resource**; never mix users, tenants, or workloads.
12. **Have the Resource Server validate access tokens independently**, checking issuer, audience, expiry, scope, and domain permissions.
13. **Constrain retries and replay:** never reuse an assertion after consumption; handle timeouts per policy.
14. **Protect secrets and logs:** assertions, client assertions, access tokens, and signing keys must never leak.
15. **Test key rotation and negative cases:** unknown issuer, wrong audience, expired token, duplicate `jti`, unauthorized subject, over-scoped request.

**Key takeaway:** **JWT Bearer Grant (RFC 7523)** uses a **JWT authorization assertion** at the Token Endpoint to request an OAuth access token. It differs from **`private_key_jwt`** (a JWT authenticating the OAuth client) and **Token Exchange RFC 8693** (exchanging tokens via `subject_token` under its own grant type). In Spring Security OAuth2 Client, this grant typically requires **custom integration/provider setup** rather than expecting `oauth2Login()` or `clientCredentials()` to handle it automatically. A JWT signature is only part of the trust contract: issuer, subject, audience, TTL, replay protection, and permissions enforced at the AS and API determine secure access.

## 32. References

- [RFC 7521 — Assertion Framework for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7521): framework for using assertions in grants and client authentication.
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523): JWT Bearer Grant, client assertions, and validation requirements.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): `subject_token`, `actor_token`, token types, and the token exchange grant.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): grants, token endpoint, client authentication, and access tokens.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `sub`, `aud`, `exp`, `iat`, `nbf`, `jti`.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): protected header, algorithms, and signatures.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): JWT algorithms, cross-JWT confusion, trust boundaries, and validation.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): token protection and the OAuth threat model.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): requesting access tokens for specific resources/audiences.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `ClientRegistration`, `OAuth2AuthorizedClientManager`, and providers.
- [Spring Security — Reactive OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): reactive managers and HTTP token integrations.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): distinguishing OIDC browser login from assertion grants.
- [Nimbus JOSE + JWT](https://connect2id.com/products/nimbus-jose-jwt): JOSE/JWT library for Java.
