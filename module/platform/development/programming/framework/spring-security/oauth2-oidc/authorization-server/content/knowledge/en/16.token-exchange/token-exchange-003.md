# `subject_token`, `subject_token_type`, and `requested_token_type` Parameters

## 1. Context: Why Do We Need Token Exchange?

In a Spring Boot system using **Spring Security** and **Spring Authorization Server** to build an **OAuth 2.0/OpenID Connect Authorization Server**, a service often receives an external access token but needs to call another service with a **different permission scope, target recipient, or trust context**.

For example, a booking application uses three components:

- `booking-web`: client that obtained an access token for user Lan.
- `booking-api`: Resource Server accepting tokens whose audience is the Bookings API.
- `payment-api`: internal API requiring a token strictly scoped to reading payment status.

`booking-api` should not simply take the access token meant for itself and forward it as-is to `payment-api` when the audience does not match. One solution is **OAuth 2.0 Token Exchange**, standardized in **RFC 8693**. Acting as an OAuth client, `booking-api` presents an existing token to the Authorization Server (AS) and requests the issuance of a different token suited to the target usage.

In Token Exchange, three parameters are central:

- **`subject_token`**: the input token representing the subject on whose behalf the requester is performing the exchange.
- **`subject_token_type`**: identifier for the **input token type**, so the AS knows its semantics and how to verify it.
- **`requested_token_type`**: the desired **output token type**, an optional parameter that does not prove the client is permitted to receive any token type.

This lesson belongs to the **Token Exchange** chapter and explains these parameters in detail in the context of designing, configuring, securing, testing, and operating an Authorization Server with Spring Security and Spring Authorization Server.

### Learning Objectives

After this lesson, you will be able to:

1. State accurately which parameters are required and which are optional under RFC 8693.
2. Explain the difference between a token's **identity/function** and its **technical format**.
3. Write a Token Exchange Request using `application/x-www-form-urlencoded`.
4. Explain why `subject_token` does not replace OAuth client authentication.
5. Properly inspect `issued_token_type` and `token_type` in the response.
6. Distinguish impersonation-style token exchange from delegation with an actor.
7. Set up a registered client and understand Spring Authorization Server's Token Exchange extension/processing points.
8. Design policies for audience/resource/scope, TTL, and token revocation.
9. Test missing parameters, invalid token types, wrong audiences, expired tokens, and privilege-escalation attempts.

## 2. Overview of the RFC 8693 Flow

Token Exchange uses the OAuth 2.0 **Token Endpoint** with a fixed grant type:

```text
urn:ietf:params:oauth:grant-type:token-exchange
```

It is not a redirect flow, does not produce an authorization code, and does not require the browser to go through login/consent screens at the moment of the exchange.

```mermaid
sequenceDiagram
    participant W as booking-web
    participant B as booking-api / OAuth client
    participant AS as Authorization Server / STS
    participant P as payment-api / Resource Server

    W->>B: Call Bookings API with incoming access token
    B->>B: Verify token used to call B itself
    B->>AS: POST /oauth2/token<br/>client authentication + token-exchange grant<br/>subject_token + subject_token_type<br/>requested_token_type + audience/scope
    AS->>AS: Authenticate client; validate input token and policy
    AS->>AS: Determine token type, audience, scope, TTL
    AS-->>B: New token + issued_token_type + token_type
    B->>P: Call Payment API with new access token
    P->>P: Verify issuer, audience, expiry, and permissions
    P-->>B: Return authorized data
```

This example assumes the AS is configured to trust the input token and allow client `booking-api` to exchange it for a privilege-narrowed token targeted at `payment-api`. The RFC defines the exchange protocol; it **does not automatically grant exchange permissions to every client**.

### 2.1. From the Authorization Server's Perspective

The AS must answer at least four questions:

1. **Who is sending the request?** The OAuth client authenticated or identified by its registered method.
2. **What is `subject_token`?** Is the token genuine, still valid, issued by a trusted issuer, and which subject does it represent?
3. **Is the client permitted to exchange this token?** Check grant registration, token/client/tenant bindings, and impersonation/delegation policy.
4. **What token type, audience/resource, and scopes may be issued?** The output must obey policy rather than blindly copying all permissions from the input.

None of these questions should be skipped just because the client presents a JWT with a valid signature.

## 3. Token Exchange Request Parameters: Required and Optional

Per RFC 8693 Section 2.1, the main parameters are:

| Parameter | RFC 8693 | Function |
|---|---|---|
| `grant_type` | **Required** | Must be `urn:ietf:params:oauth:grant-type:token-exchange` |
| `subject_token` | **Required** | Token representing the subject on whose behalf the client is requesting the exchange |
| `subject_token_type` | **Required** | URI identifying the type of token passed in `subject_token` |
| `requested_token_type` | **Optional** | URI describing the desired output token type |
| `resource` | Optional | URI of the target resource/service where the new token will be used |
| `audience` | Optional | Logical identifier of the intended recipient of the new token |
| `scope` | Optional | Desired permission scope on the output token |
| `actor_token` | Optional | Token representing the party acting on behalf of the subject |
| `actor_token_type` | Conditional | **Required when `actor_token` is present**; must not be sent without `actor_token` |

This table describes the **standard RFC contract**. A specific Authorization Server may restrict supported token types, targets, or audiences, or require additional details per policy. "Optional in the RFC" does not mean every server must support every combination.

### 3.1. How the Three Core Parameters Relate to Each Other

You can think of the request as asking the AS:

> I am an authenticated client. Here is a **`subject_token`** of type **`subject_token_type`**. I would like to receive a token of type **`requested_token_type`** for the requested target/scope, if policy permits.

```mermaid
flowchart TD
    IN["subject_token<br/>input token value"]
    INTYPE["subject_token_type<br/>URI describing input type"]
    OUTTYPE["requested_token_type<br/>URI of desired output type"]
    AUTH["Client authentication<br/>+ registered grant"]
    POLICY["Validate input token<br/>+ audience/scope/actor policy"]
    ISSUED["Issued token<br/>access_token field"]
    TYPE["issued_token_type<br/>ACTUAL token type"]
    METHOD["token_type<br/>how the token is used"]

    IN --> POLICY
    INTYPE --> POLICY
    OUTTYPE --> POLICY
    AUTH --> POLICY
    POLICY -->|"Allowed"| ISSUED
    ISSUED --> TYPE
    ISSUED --> METHOD
```

**Do not confuse them:** `requested_token_type` is in the **request**; `issued_token_type` is in the **response**. The client must inspect the actual output details rather than assuming its request was granted as asked.

## 4. `subject_token`: Who Does the Input Token Represent?

`subject_token` is the **existing security token value** that the client hands to the AS. Per RFC 8693, it represents the identity of the party on whose behalf the request is being made; the *subject* of the output token typically relates to the subject of the input token.

In the example:

```text
subject_token = ACCESS_TOKEN_FOR_BOOKING_API
```

This is a **placeholder**, not a real token. For user Lan, the input token might carry/represent `sub=user-42`. The AS can evaluate issuing a token for `payment-api` with the same subject while adjusting permissions for the target API.

### 4.1. Who Is the Subject, and Who Is the Client?

Three roles can be distinct:

| Role | In the example | Meaning |
|---|---|---|
| **Subject** | `user-42` (Lan) | The identity associated with the eventual resource access |
| **Requesting client** | `booking-api` when calling the Token Endpoint | The component executing token exchange that must be authorized by the AS |
| **Target/Resource Server** | `payment-api` | The party receiving and validating the new token |

Do not replace `sub` in the new token with `client_id` simply because `booking-api` is calling the Token Endpoint. If the application wants a token representing **only the client**, that is a different use case and must be explicitly modeled by policy.

### 4.2. `subject_token` Is Not a Client Secret

The client can authenticate using:

- `client_secret_basic`;
- `private_key_jwt`;
- mTLS;
- or another method appropriate to the client type and AS policy.

The input token in `subject_token` **does not prove on its own that the client is permitted to perform an exchange**. An attacker could obtain a bearer token elsewhere; if the AS lets any client exchange that token for a new audience, the system easily becomes a privilege-escalation vector.

### 4.3. Validating the `subject_token` Value

The AS must validate it using a procedure suited to the token type and trusted issuer:

- Does the token's structure match `subject_token_type`?
- Are the issuer and signature trusted? If opaque, is there an approved introspection or state lookup mechanism?
- Are `exp`, `nbf`, revocation status, and other constraints valid?
- Which audience/resource was the token issued for, and is it eligible as an exchange input?
- Which subject, tenant, client, or trust domain does the token belong to?
- Can it be proven that the requesting client is authorized to exchange that token?
- Is the token bound to a certificate/key or another sender-constrained mechanism that must be verified?

**A decodable JWT is not automatically valid.** Never simply Base64-decode the payload to read `sub` and issue a new token. Verification must rely on real trust and validation, guarding against issuer and audience confusion.

### 4.4. Must the Subject Token Be an Access Token?

**According to the RFC, no.** `subject_token` is a security token of the declared type; profiles may use JWTs, access tokens, ID tokens, or other formats if the server supports them.

**In an implementation, it may be restricted.** For example, a given Spring Authorization Server version may only support a subset of token types in its default converters/providers. Do not assume every token type listed in the RFC is handled out of the box by Spring.

In particular, **an OIDC ID token must not be used as a Bearer token to call APIs**. If a system wants to accept an ID token as `subject_token` in an exchange flow, it needs dedicated trust, audience, replay, consent/policy design, and explicit server support; never treat it as automatic or universally allowed at every AS.

## 5. `subject_token_type`: Identifying the Input Token Type

The `subject_token_type` parameter is **required** and holds a **token type identifier URI**. Key standard values include:

```text
urn:ietf:params:oauth:token-type:access_token
urn:ietf:params:oauth:token-type:refresh_token
urn:ietf:params:oauth:token-type:id_token
urn:ietf:params:oauth:token-type:jwt
urn:ietf:params:oauth:token-type:saml1
urn:ietf:params:oauth:token-type:saml2
```

These URIs are not HTTP endpoints to fetch; they are standardized **type identifiers**.

### 5.1. `access_token` and `jwt` Are Fundamentally Different

This is one of the easiest points to confuse in Token Exchange.

| `subject_token_type` value | What is being declared | What it does NOT assert |
|---|---|---|
| `urn:ietf:params:oauth:token-type:access_token` | This is an OAuth access token under the issuing system's semantics | That the token must be opaque |
| `urn:ietf:params:oauth:token-type:jwt` | This is a **JWT-formatted** token | That the JWT is necessarily an OAuth access token |
| `urn:ietf:params:oauth:token-type:id_token` | This is an OIDC ID token | That the token can be used directly as an API credential |
| `urn:ietf:params:oauth:token-type:refresh_token` | This is an OAuth refresh token | That the token is permitted for exchange in the current deployment |

**An access token is a functional credential category. A JWT is a token representation format.** An access token may itself be a JWT; declaring `access_token` can still be correct if the AS understands the input as an OAuth access token from the issuing system and has the appropriate verification mechanism.

Conversely, a JWT signed by a trusted issuer might be an ID token or a JWT assertion meant for another purpose, not automatically an access token.

### 5.2. Why Not Guess the Type from Dots in the Token?

A JWT typically has three dot-separated segments, yet:

- Having dots does not prove the issuer is trusted or the signature is valid.
- Not every JWT is an access token.
- An access token may be opaque and unparseable by the client.
- Whether to use `access_token` or `jwt` depends on the AS's trust contract and profile.

The client must declare the **correct type according to its contract with the AS**. The server must check that the type is supported and verify the input matches the declared type; never trust `subject_token_type` on the caller's word alone.

### 5.3. When `subject_token_type` Does Not Match the Input

Suppose the client sends:

```text
subject_token      = OPAQUE_ACCESS_TOKEN
subject_token_type = urn:ietf:params:oauth:token-type:jwt
```

If the AS only handles JWTs under type `jwt`, an opaque input cannot verify under that branch. The AS must **reject it or apply valid profile-defined handling**; it must never guess/switch the type to issue a token unconditionally.

Conversely, if the input is a JWT access token issued by the AS itself, declaring `access_token` may be the right choice even though the string looks like a JWT.

## 6. `requested_token_type`: Requesting the Output Token Type

`requested_token_type` is **optional** in RFC 8693. It describes the type of security token the client **wants the AS to issue**.

Example:

```text
requested_token_type=urn:ietf:params:oauth:token-type:access_token
```

Meaning: the client is asking for an **OAuth access token** as output. This is the typical request when a service needs a token to call another Resource Server.

### 6.1. What Happens If `requested_token_type` Is Omitted?

RFC 8693 does not mandate a universal default output type for all Authorization Servers. When omitted, the issued token type is **decided by the AS**, potentially based on target resource/audience and deployment policy.

Therefore:

- Do not assume omitting `requested_token_type` guarantees an `access_token` under the RFC.
- Do not assume the server will emit a JWT just because the input is a JWT.
- Do not assume the server is obligated to issue the exact type requested.
- Always inspect **`issued_token_type`** in the response to know the actual outcome.

A Spring implementation may choose access tokens as its default supported output type. That is an **implementation capability**, not a universal RFC rule.

### 6.2. Does Requesting `jwt` Mean Requesting a JWT Access Token?

**Not necessarily.** Under the RFC, `urn:ietf:params:oauth:token-type:jwt` refers to the **JWT format**, whereas `...:access_token` refers to **OAuth access token semantics**.

| Request | Intent | Behavior to verify |
|---|---|---|
| `requested_token_type=...:access_token` | Wants an access token to access resources | AS may issue a JWT access token or opaque access token per policy |
| `requested_token_type=...:jwt` | Wants a JWT-structured token | Does the server/profile support JWT output with the intended semantics? |
| `requested_token_type=...:id_token` | Wants an OIDC ID token | Does not mean the AS should issue an ID token outside a valid OIDC auth context |
| Omit `requested_token_type` | Let the AS choose | Inspect `issued_token_type` and profile policy |

A system needing a JWT **to call an API** should usually still model it under OAuth **access token** semantics while configuring the access token format on the AS and the Resource Server contract. Do not force type `jwt` merely to distinguish opaque vs. JWT tokens if the AS does not support that profile.

### 6.3. A Request Is Not Authorization

Sending:

```text
requested_token_type=urn:ietf:params:oauth:token-type:access_token
```

does not mean the client is allowed to receive that token. The AS must still decide which clients may exchange, which input tokens are trusted, which targets are valid, which scopes are granted, and whether the output token would violate policy by escalating privileges.

## 7. Comparing All Three Parameters on One Example

Suppose `booking-api` has received an access token on an incoming request and needs a new token for `payment-api`:

| Parameter | Example value | Role |
|---|---|---|
| `subject_token` | `ACCESS_TOKEN_FOR_BOOKING_API` | **Input token** carrying user context |
| `subject_token_type` | `urn:ietf:params:oauth:token-type:access_token` | **Input** token type |
| `requested_token_type` | `urn:ietf:params:oauth:token-type:access_token` | **Desired output** token type |
| `audience` | `https://payments.example.com` | Intended recipient of the new token |
| `scope` | `payments.status.read` | Desired permission in the new token |

A valid outcome is not simply copying the input token. The AS can create a new access token:

```text
issued_token_type = urn:ietf:params:oauth:token-type:access_token
sub               = user-42           (if policy preserves the subject)
aud               = https://payments.example.com
scope             = payments.status.read
exp               = expiration decided by the AS
```

The AS must verify that `booking-api` is genuinely authorized to request a token for `payment-api`, that the input token is eligible for exchange, and that the user/tenant holds rights related to `payments.status.read`. **Never escalate scopes simply because the client added them to the form.**

## 8. Standard HTTP Request per RFC 8693

Example Token Exchange Request using `application/x-www-form-urlencoded`. Values in the body are **formatted for readability**; when sent over the wire, special characters must be URL-encoded:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=ACCESS_TOKEN_FOR_BOOKING_API
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&audience=https%3A%2F%2Fpayments.example.com
&scope=payments.status.read
```

Line breaks in the body are for readability only; the actual form is sent as a single URL-encoded string. This example uses a **confidential client** with `client_secret_basic`; the authentication method depends on the client registration. Never place client secrets or real subject tokens in URL query strings, browser history, Git, or logs.

### 8.1. Which Step Does Each Parameter Belong To?

```text
grant_type
  -> Selects the token exchange protocol (RFC 8693).

Authorization: Basic ...
  -> Authenticates the requesting OAuth client.

subject_token + subject_token_type
  -> Describes the INPUT credential for the AS to verify.

requested_token_type
  -> Expresses the desired OUTPUT credential type.

audience / resource / scope
  -> Expresses the target recipient and permissions of the new token.
```

`subject_token` alone does not tell the AS whether to validate it as an OAuth access token or another JWT type; `subject_token_type` is required by the specification to make this explicit.

### 8.2. `resource` vs. `audience` Parameters

RFC 8693 allows a client to specify the target via:

- `resource`: URI representing the service/resource where the token is expected to be used.
- `audience`: logical identifier of the token's recipient.
- **Multiple** `resource` and/or `audience` parameters may appear in a single request if supported by the server/profile.

However, **multiple targets do not mean broader permissions by default**. The AS must determine which targets the new token may be used at, restrict scopes, enforce policy, and reject disallowed targets.

A safe practice is to request a token for **one specific audience** when the system does not need multi-audience tokens. Each Resource Server must validate `aud`/target appropriately to prevent *token substitution* across services.

## 9. Token Exchange Response and `issued_token_type`

A successful response when issuing an **OAuth Bearer access token** looks like:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "NEW_ACCESS_TOKEN_FOR_PAYMENTS",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "payments.status.read"
}
```

Per RFC 8693:

- **`access_token`**: **required** response field carrying the issued token. The field name is historical from OAuth and can still be used even when the issued token does not have access-token semantics.
- **`issued_token_type`**: **required** field describing the **actual** token type issued by the AS.
- **`token_type`**: **required** field describing how to present the token, e.g., `Bearer` for an OAuth Bearer access token.
- **`expires_in`**: lifetime information, depending on the case and implementation.
- **`scope`**: the actual granted permissions if included in the response.
- **`refresh_token`**: should not be expected by default; depends on exchange type and policy.

### 9.1. `issued_token_type` Differs from `token_type`

These are two distinct fields:

| Response field | Example | Answers |
|---|---|---|
| `issued_token_type` | `urn:ietf:params:oauth:token-type:access_token` | "Which **security token type** did the AS issue?" |
| `token_type` | `Bearer` | "By which **access mechanism** is the credential presented?" |

When an AS issues a **JWT that is not an OAuth access token**, the RFC gives the example `issued_token_type=...:jwt` and `token_type=N_A`. Never send such a token to an API as a Bearer token simply because the response field is named `access_token`.

### 9.2. Must the New Token Have the Same Expiration as the Old Token?

No. The output token may have its own TTL and claims as decided by AS policy. The RFC does not impose a default constraint that the output lifetime equals the remaining lifetime of the input token.

A secure design often considers **bounding the output TTL by risk, subject token source, and target**, avoiding issuing long-lived outputs from short-lived or lower-trust inputs. However, that is a **policy rule to implement and test**, not an equality mandate imposed by the RFC.

## 10. Subject Token vs. Actor Token: Impersonation and Delegation

RFC 8693 supports both **impersonation** and **delegation** scenarios.

### 10.1. Impersonation (Conceptual Overview)

The client presents a subject's token and requests a new token representing that subject in a different trust context/target. The output token may carry only the subject information, depending on policy.

**Risk:** If a client can arbitrarily exchange any user's token and gain unauthorized permissions, Token Exchange becomes an identity-spoofing / privilege-escalation vulnerability. Explicit policy is required defining which client may impersonate which subject and for which target.

### 10.2. Delegation with an Actor

When you need to represent **the party acting on behalf of the subject**, the request can include:

```text
actor_token      = BOOKING_API_TOKEN
actor_token_type = urn:ietf:params:oauth:token-type:access_token
```

`actor_token_type` is **required when `actor_token` is present**, and **must not be included when `actor_token` is absent**, per the RFC.

The output JWT may use the `act` claim to record the current actor, for example (illustrative):

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://payments.example.com",
  "scope": "payments.status.read",
  "act": {
    "sub": "booking-api"
  }
}
```

**This is an illustrative payload**, not a complete signed JWT. `act` must come from information verified by the AS and approved by policy. Never pull `act.sub` from a self-asserted form field and treat it as a genuine actor.

Systems with multi-step delegation chains must manage claims and actor history per the RFC. Resource Servers should rely only on claims/actors meaningful to the current policy; never treat an entire actor history as an independent grant of access.

### 10.3. The Three Core Parameters Retain Their Roles

Whether or not `actor_token` is present:

- `subject_token` still describes the **input subject**.
- `subject_token_type` still describes the **input token type**.
- `requested_token_type` still describes the **desired output token type**.

Do not confuse `subject_token_type` with `actor_token_type`; they can differ and must each be validated according to their respective types.

## 11. Security Policy: Preventing Privilege Escalation and Token Substitution

Token Exchange is most valuable when narrowing or adapting privileges for a specific target. Essential checks include:

| Decision | Specific question |
|---|---|
| **Client authorization** | Is the requesting client registered for the Token Exchange Grant? |
| **Subject trust** | Was the input token issued by a trusted issuer, unexpired, and unrevoked? |
| **Subject binding** | Is the client allowed to exchange that subject's token? |
| **Token type** | Is `subject_token_type` consistent with the actual value and supported profile? |
| **Requested type** | Does the AS support and allow the desired output type? |
| **Audience/resource** | Is the target allowed for this client, subject, tenant, and policy? |
| **Scope attenuation** | Are the new scopes within the maximum allowed permissions? |
| **TTL and revocation** | How long does the new token live; how is source token revocation handled? |
| **Delegation** | If an actor is present, is the actor permitted to represent the subject? |

A common design invariant:

```text
output_scopes ⊆ allowed_for_subject
output_scopes ⊆ allowed_for_requesting_client
output_scopes ⊆ allowed_for_target_resource
```

This is an **illustrative policy invariant**, not a set intersection automatically enforced by the RFC for every system. In some use cases, scopes across audiences have different names; those cases require **explicit policy mapping**, not simple string comparison.

### 11.1. Input Audience and Output Audience

An input token issued for `booking-api` can be exchanged into an output token issued for `payment-api` when AS policy permits it.

- `booking-api` must verify the incoming token is authorized for calling `booking-api`.
- The AS must verify that exchanging from that context to `payment-api` is permitted.
- `payment-api` must accept only tokens matching its own audience.

Never let `payment-api` directly accept tokens with audience `booking-api` to "save a step," as doing so erodes access boundaries and enables token substitution attacks.

### 11.2. Never Use Token Exchange for Arbitrary Privilege Escalation

Example of a suspicious request:

```text
subject_token       = token with only bookings.read
requested scope     = payments.admin
requested audience  = https://payments.example.com
```

The AS must enforce client/subject/tenant/target policies. Never grant `payments.admin` simply because the caller supplied that scope and holds a valid `subject_token`.

If a product legitimately maps permissions between APIs with different scope vocabularies, that mapping must be explicitly defined in policy and auditable.

## 12. Do the Input Token and Output Token Share the Same Lifecycle?

**Not by default.** Under RFC 8693, a normal token exchange **does not alter the validity** of `subject_token` or `actor_token` unless the token type enforces its own one-time-use rule.

Furthermore, an exchange usually **does not create a tight lifecycle link** between input and output tokens. This means:

- Revoking the input token **does not automatically guarantee** every output token immediately becomes invalid.
- Extending the input token **does not automatically extend** already-issued output tokens.
- An unexpired input token **does not guarantee** an output token will be issued or remain valid.
- The output token can have its own `exp`, audience, and scopes.
- If the product requires revocation propagation, you must design an explicit linkage or state-checking mechanism.

### 12.1. Timeline Example

| Hypothetical time | Event | Outcome |
|---|---|---|
| 09:00 | Client receives subject access token for `booking-api` | Original token has its own expiry |
| 09:02 | `booking-api` exchanges for a token for `payment-api` | New token has its own TTL |
| 09:04 | Subject token is revoked | AS rejects new exchanges using the revoked input if state checks are enforced |
| 09:05 | `payment-api` receives the previously issued output token | May still accept it if unexpired and revocation propagation is not implemented |
| 09:07 | Output token expires or is revoked | Resource Server must reject it per its validation mechanism |

These timestamps are examples only. Never promise users that "revoking the original token cuts off all exchanged tokens immediately" unless your system actually implements linked revocation.

## 13. How Spring Authorization Server Supports Token Exchange

Modern Spring Authorization Server releases include components to handle the **OAuth 2.0 Token Exchange Grant** per RFC 8693 at the Token Endpoint. In the Spring Authorization Server 1.5.x line, representative components include:

- `OAuth2TokenExchangeAuthenticationConverter`: reads the HTTP form request and constructs an authentication object holding the Token Exchange parameters.
- `OAuth2TokenExchangeAuthenticationToken`: carries `subjectToken`, `subjectTokenType`, `requestedTokenType`, actor token, resources, audiences, scopes, and additional parameters.
- `OAuth2TokenExchangeAuthenticationProvider`: provider processing the grant within its supported capabilities.
- `OAuth2TokenEndpointConfigurer`: provides extension hooks for converters/providers and handlers.
- `OAuth2AuthorizationService` / `OAuth2TokenGenerator`: supports authorization state and token generation in the framework model.

**Version note:** Spring Authorization Server 1.x and newer Spring Security releases integrating Authorization Server features may differ in packages, signatures, and supported features. Always check the documentation/API for your **exact dependency version** before copying configuration.

### 13.1. The RFC Is Broader Than One Version's Built-In Capabilities

RFC 8693 defines numerous `subject_token_type` and `requested_token_type` values, but **that does not mean Spring's default converter/provider supports all of them**.

For example, the Spring Authorization Server 1.5.x line has documented limitations around accepting `id_token` as a subject token or issuing ID tokens as output in Token Exchange. Default behavior generally centers on exchanging tokens to issue an **access token**. If you need to accept external tokens, SAML, or ID tokens, or emit JWTs with different semantics, verify version support, design trust carefully, and add extensions or dedicated profiles where genuinely needed.

**Never alter a type parameter to "work around" an API restriction.** Specifically, never label an ID token as `access_token` just because both are JWTs.

### 13.2. Registering a Client Allowed to Exchange

Example of `booking-api` as a confidential OAuth client permitted to use the Token Exchange Grant:

```java
String tokenExchangeGrant =
    "urn:ietf:params:oauth:grant-type:token-exchange";

RegisteredClient bookingApiClient = RegisteredClient
    .withId("booking-api-registration-id")
    .clientId("booking-api")
    .clientSecret(passwordEncoder.encode(secretFromSecureStore))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        new AuthorizationGrantType(tokenExchangeGrant))
    .scope("payments.status.read")
    .tokenSettings(TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
```

This Java snippet illustrates **registered client policy**, not a complete Authorization Server. Expressing the grant name as the standard URI avoids coupling to whether a specific constant exists in every library version.

You still need a repository, issuer, JWK, authentication chain, token generator, authorization service, and actual Token Exchange policy. Registering the grant **only allows the client to submit requests for that grant**; it does not mean the client may exchange any input token for any audience/scope.

### 13.3. Separating Parsing, Validation, and Token Issuance

```mermaid
flowchart TD
    REQ["POST /oauth2/token<br/>Token Exchange Request"]
    AUTH["Client Authentication Filter<br/>Verify requesting client"]
    CONV["OAuth2TokenExchangeAuthenticationConverter<br/>Read form parameters"]
    OBJ["OAuth2TokenExchangeAuthenticationToken<br/>subject/actor/target/scopes"]
    PROVIDER["OAuth2TokenExchangeAuthenticationProvider<br/>and policy/trust"]
    TOKEN["OAuth2TokenGenerator<br/>Create authorized token"]
    STORE["OAuth2AuthorizationService<br/>Manage state"]
    RESP["OAuth2 Token Response<br/>issued_token_type/token_type"]

    REQ --> AUTH --> CONV --> OBJ --> PROVIDER
    PROVIDER --> TOKEN --> STORE --> RESP
```

This diagram outlines the processing flow; exact ordering and filter/provider interactions depend on the implementation and version. Default endpoints can be configured differently via the Authorization Server `SecurityFilterChain`.

- **Converter** validates request structure and how basic parameters are parsed.
- **Provider/policy** verifies client/grant/input token, evaluates audience/resource/scope, and decides token issuance.
- **Token generator** builds the appropriate token.
- **Response handler** returns the OAuth/RFC 8693 response.
- **Resource Server** still validates the new token independently when it is used.

Never write a servlet filter that simply reads `subject_token` and signs a new JWT, as that easily bypasses trust validation, client authentication, and grant authorization.

## 14. Accessing the Three Parameters in the Spring Model

Within the scope of **Spring Authorization Server 1.5.x**, `OAuth2TokenExchangeAuthenticationToken` exposes directly:

```java
// Example inside a processing component that already received this object.
// Do not construct authentication manually from an unverified request.
void inspectExchange(OAuth2TokenExchangeAuthenticationToken exchange) {

    String subjectToken = exchange.getSubjectToken();
    String subjectType = exchange.getSubjectTokenType();
    String requestedType = exchange.getRequestedTokenType();

    Set<String> audiences = exchange.getAudiences();
    Set<String> resources = exchange.getResources();
    Set<String> scopes = exchange.getScopes();

    // subjectToken is a sensitive credential:
    // NEVER log it or echo it in the response.
    // Token issuance decisions belong to a trusted provider/policy.
}
```

This illustrates the **API model**, not a standalone provider or proof that `subjectToken` has been verified. Only after the appropriate processing layers finish trust and policy checks may the system issue a token.

### 14.1. Controlled Token Endpoint Customization

`OAuth2TokenEndpointConfigurer` exposes extension points such as:

```java
// Hook integration shape; must be wired into a real SecurityFilterChain.
OAuth2AuthorizationServerConfigurer authorizationServer =
    OAuth2AuthorizationServerConfigurer.authorizationServer();

http
    .securityMatcher(authorizationServer.getEndpointsMatcher())
    .with(authorizationServer, as -> as
        .tokenEndpoint(endpoint -> endpoint
            .authenticationProvider(customExchangePolicyProvider)));
```

`customExchangePolicyProvider` is an **application-implemented business provider**. Add a provider only with clear justification and an understanding of processing order. The provider must use proper authentication, trust stores, token generators, authorization service, and OAuth error semantics—never silently bypassing default providers or hand-crafting tokens.

If a default provider already matches the same authentication type ahead of your new provider, adding a provider to the list may **fail to enforce your policy as intended**. Verify list ordering/provider matching and use the hook supported by your version, or integrate policy at a framework-supported layer.

### 14.2. Token Customizers Do Not Replace Validation

`OAuth2TokenCustomizer<JwtEncodingContext>` can add claims to a **JWT access token** using the context provided by the framework. However, it is not the place to validate `subject_token` or decide whether a client is allowed to impersonate another subject.

If an `act` or provenance claim is needed:

- Policy must genuinely verify the actor prior to issuance.
- Claims must be derived from trusted post-validation information.
- The Resource Server must know how to interpret that claim.
- Never copy the entire input JWT into new claims or log the input token.

Adding a claim like `exchange=true` does not prove your Token Exchange security policy is sound.

## 15. Calling Token Exchange from a Spring Boot Client

A client can call the Token Endpoint via a safe HTTP library, Spring Security OAuth2 Client, or a version-appropriate grant provider. The focus in this lesson is **passing the three parameters accurately** and reading the response properly.

Blocking `RestClient` example:

```java
@Service
public class TokenExchangeGateway {

    private final RestClient tokenClient;

    public TokenExchangeGateway(RestClient.Builder builder) {
        this.tokenClient = builder
            .baseUrl("https://auth.example.com")
            .build();
    }

    public Map<String, Object> exchange(
            String clientId,
            String clientSecret,
            String incomingAccessToken) {

        MultiValueMap<String, String> form = new LinkedMultiValueMap<>();
        form.add("grant_type",
            "urn:ietf:params:oauth:grant-type:token-exchange");
        form.add("subject_token", incomingAccessToken);
        form.add("subject_token_type",
            "urn:ietf:params:oauth:token-type:access_token");
        form.add("requested_token_type",
            "urn:ietf:params:oauth:token-type:access_token");
        form.add("audience", "https://payments.example.com");
        form.add("scope", "payments.status.read");

        return tokenClient.post()
            .uri("/oauth2/token")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .headers(headers ->
                headers.setBasicAuth(
                    clientId, clientSecret, StandardCharsets.UTF_8))
            .body(form)
            .retrieve()
            .body(new ParameterizedTypeReference<Map<String, Object>>() {});
    }
}
```

This is a **form-body illustrative snippet**. Production applications need imports, HTTP client timeouts, TLS, error handling, bounded retries, secrets loaded from a secret manager, and validated response DTOs. Never hard-code client secrets in source code and never log `incomingAccessToken`.

**Practical limitation:** Spring Security's client API may provide `TokenExchangeOAuth2AuthorizedClientProvider` or grant-specific support in compatible versions. When using those abstractions, configure the `subject_token` source and caching policy carefully; never assume the client library automatically grabs an arbitrary token from a thread-local.

### 15.1. Never Take `subject_token` from Untrusted Input

If `booking-api` receives a bearer token on an incoming request, it must validate that token under its Resource Server policy before deciding to exchange it. Never accept an unverified self-asserted JWT from a form field and forward it to the AS as valid subject evidence.

When exchanging via a backend, keep tokens confidential in memory/transaction scope. Never place them in URLs, query parameters, tracking events, public HTML forms, or unredacted HTTP logs.

## 16. Common Errors and Error Codes to Distinguish

RFC 8693 specifies that Token Exchange error responses follow the OAuth 2.0 Token Endpoint contract.

**Key detail:** If the request is invalid, or `subject_token`/`actor_token` is invalid or unacceptable by policy, RFC 8693 Section 2.2.2 specifies **`invalid_request`**. When the AS is unwilling or unable to issue a token for the requested `resource` or `audience` target, **`invalid_target`** should be used.

Other OAuth errors apply as appropriate, such as `invalid_client` or `unauthorized_client`.

| Scenario | Expected error group | Notes |
|---|---|---|
| Missing `subject_token` | `invalid_request` | Required parameter missing |
| Missing `subject_token_type` | `invalid_request` | Never guess type from the token string |
| Invalid duplicate parameter / malformed form | `invalid_request` | Never arbitrarily pick the first/last value |
| Expired/untrusted subject token | `invalid_request` per RFC 8693 | May include a generic description without leaking trust internals |
| Invalid actor token | `invalid_request` | Sending an actor token requires an actor token type |
| `actor_token_type` present without `actor_token` | `invalid_request` | Disallowed combination |
| Unsupported target audience/resource | `invalid_target` is typically appropriate | Consider error policy to avoid target enumeration |
| Invalid client auth | `invalid_client` | Independent of the subject token |
| Client not permitted to use the grant | `unauthorized_client` or error per framework contract | Grant must be permitted on the registered client |
| Unsupported token type requested | Error per RFC/profile/implementation | Never substitute a roughly similar type |
| Scope exceeds permissions | `invalid_scope` or appropriate policy error | Never silently escalate privileges |
| New token has wrong `aud`/`scope` | Not a client exchange error once issued | Resource Server must reject and alert on misconfiguration |

**The exact error codes returned by Spring Authorization Server must be tested on your target deployment version.** General RFC requirements do not mean every library version behaves identically in all edge cases. When differences arise, distinguish spec compliance requirements from library behavior and choose the right extension/test accordingly.

### 16.1. Error Responses Must Not Leak the Input Token

Safe error example:

```json
{
  "error": "invalid_request",
  "error_description": "Token exchange request is not acceptable"
}
```

Never return raw `subject_token` values, stack traces, sensitive JWT claim contents, JWK cache details, or messages like "token belonging to user X is not allowed" to an unauthorized client. Record correlation IDs and detailed reasons in **redacted** security/audit logs.

## 17. Test Matrix for the Three Parameters

### 17.1. Syntax and RFC Contract Tests

| Test case | Request | Expected |
|---|---|---|
| Minimal valid request | Valid `grant_type`, `subject_token`, `subject_token_type`, client auth | AS processes or evaluates per policy, not rejected for missing params |
| Missing `subject_token` | Type only | `invalid_request` |
| Empty token | `subject_token=` | Rejected |
| Missing `subject_token_type` | Token present without type | `invalid_request` |
| Unsupported type | Unknown URI in `subject_token_type` | No token issued |
| Semantically mismatched type | Opaque token declared as `jwt` | Does not bypass validation |
| Omitted requested type | Omit `requested_token_type` | AS determines output per policy; client inspects `issued_token_type` |
| Requested type is access token | Request `...:access_token` | If supported and policy allows, issues access token |
| Requested type is ID token | Request `...:id_token` | Must not issue an ID token by default; test actual support |
| Duplicate required param | Two `subject_token` values sent | Rejected per request parsing rules |
| Actor token without type | `actor_token` present, missing type | `invalid_request` |
| Actor type without actor | Only `actor_token_type` present | `invalid_request` |

### 17.2. Trust and Policy Tests

| Test case | Condition | Expected |
|---|---|---|
| Expired subject token | `exp` in the past | Rejected |
| Subject token with forged signature | Forged JWT | Rejected |
| Subject token from unknown issuer | Disallowed trust source | Rejected |
| Revoked token | AS/introspection marks invalid | Rejected per policy |
| Client not permitted to exchange | Grant not registered | Rejected |
| Different client presents user's token | No matching binding/policy | Rejected |
| Cross-tenant | Caller/subject belong to incompatible tenants | Rejected |
| Disallowed audience target | Requests `https://admin.example.com` | `invalid_target` or appropriate error |
| Scope escalation | Requests more sensitive scope than input/policy allows | Does not grant escalated permissions |
| Valid target | Requests token with Payment API audience | Output contains only allowed audience/scopes |
| Spoofed delegation actor | Untrusted actor token | `act` not accepted |
| Source token revoked after exchange | Issued output still unexpired | Verify revocation propagation matches design |
| Output token expired | Token used past `exp` | Resource Server rejects |

### 17.3. Response Verification

On a successful exchange, verify:

1. `access_token` is populated and kept confidential.
2. `issued_token_type` **is present** and matches the actual output type issued.
3. `token_type` reflects how the token is used, e.g., `Bearer`.
4. `expires_in` and expiration claims are consistent with policy.
5. `scope` and `aud` do not exceed permitted boundaries.
6. If an `act` claim is present, actor information is verified and matches the RS contract.
7. The new access token is accepted by the target API, **and rejected by other APIs if the audience does not match**.
8. The client never logs the subject token or output token.

## 18. Testing with Spring Security and Spring Authorization Server

A practical testing strategy has three layers:

### 18.1. Converter/Policy Unit Tests

- Pass a valid form and verify `OAuth2TokenExchangeAuthenticationToken` holds the right `getSubjectToken()`, `getSubjectTokenType()`, and `getRequestedTokenType()`.
- Omit or mismatch token types to verify the converter rejects them per contract.
- Run policy tests with mocked subject/client/target inputs to verify scope attenuation.
- Ensure unverified input tokens (without signature/state checks) are never accepted.
- Verify the provider refuses to issue tokens when the requesting client is unauthenticated.

### 18.2. Token Endpoint Integration Tests

Send HTTP `POST /oauth2/token` through the real `SecurityFilterChain` with client credentials, subject token, and RFC token type URIs. Verify:

- Client authentication runs before token issuance.
- Granted client has `token-exchange` in its registration.
- Issued token carries the right `issued_token_type`.
- `invalid_request`/`invalid_target` and OAuth error responses behave properly.
- Substituting `subject_token` with a token from another issuer is rejected by the AS.
- Multiple instances share consistent authorization state, JWKs, and trust policy.

Never call only a JWT-generating service directly and conclude Token Exchange works; doing so skips form parsing, client authentication, and token endpoint error handling.

### 18.3. End-to-End Resource Server Tests

Obtain a valid subject token for `booking-api`, exchange it for `payment-api`, and prove:

1. `booking-api` accepts the input token with its intended audience.
2. The AS issues output only when policy allows.
3. `payment-api` accepts the output with matching audience/scope and rejects the original input if its audience differs.
4. A third API rejects the output token if it is not in the audience.
5. Revocation/expiry behave strictly as documented.

## 19. Operations: Logging, Caching, and Revocation

Token Exchange handles **two sensitive credentials in a single workflow**: the input token and the output token. Both must be protected from exposure.

### 19.1. What to Measure

| Metric or audit | Purpose |
|---|---|
| Token exchange QPS by client | Track traffic and detect abuse |
| `invalid_request`/`invalid_target` error rate | Detect invalid types or target probing |
| Exchange ratio by subject token type | Identify active profiles |
| Requested target audiences/resources | Detect unusual targets; cap label cardinality |
| Token issuance latency | Monitor AS performance |
| JWT verification/introspection failures | Monitor input token trust health |
| Policy-denied exchanges | Detect privilege escalation or cross-tenant attempts |
| Revocation propagation delay | Measure residual window when cutting off access |
| Client credential rotation events | Track client authentication hygiene |

Never include raw `subject_token`, `access_token`, client secrets, ID tokens, or private keys in logs, traces, metrics, or audit records.

### 19.2. Is Caching Exchanged Tokens Safe?

Output tokens typically have specific audiences, scopes, and subjects. If caching:

- Cache keys must distinguish requesting client, subject, audience/resource, scope, token type, and tenant where applicable.
- Never serve subject A's output token to subject B.
- Never serve a Payment API token to Bookings API.
- Cache TTL must not exceed `exp`; account for input token expiry and revocation policy.
- Never treat an unexpired cached output token as proof that the input token is still valid if your product requires revocation propagation.
- Avoid caching raw subject tokens in unprotected storage.

Given the sensitivity of the flow, prefer skipping caching when traffic is low; when caching is necessary, design explicit redaction, encryption, concurrency, and eviction controls.

### 19.3. Incident Response

If a subject token or exchange credential is compromised:

1. Prevent the compromised credential/client from requesting new exchanges.
2. Revoke the subject token and identify output tokens derived from that input if linkage/audit records exist.
3. Decide whether to invalidate output tokens immediately or wait out short TTLs based on security requirements.
4. Verify Resource Servers properly enforce revocation, introspection, and audiences.
5. Investigate audit logs using correlation IDs, client IDs, pseudonymized subjects, and targets—never raw tokens.
6. Fold trust/target/scope controls and regression tests into the remediation plan.

**RFC 8693 does not automatically guarantee input/output revocation propagation.** If your product needs the ability to "sever an entire token chain immediately," explicitly design linked state and validity checks.

## 20. Common Misconceptions

**"`subject_token` is the client's password."** False. It is the input token representing the subject; client authentication is a separate step.

**"`subject_token_type` is JWT or opaque based on inspecting the string."** False. Type URIs represent token semantics, and in some cases format; `access_token` and `jwt` are not equivalent.

**"A JWT access token must declare `subject_token_type=jwt`."** Not necessarily. If the AS processes it under OAuth access token semantics, `...:access_token` may be the right type even when the token is formatted as a JWT.

**"`requested_token_type` is required."** False. RFC 8693 defines it as optional, though an AS may constrain choices by policy/profile.

**"Omitting requested type guarantees an access token will be issued."** False under the RFC. The Authorization Server decides; always inspect `issued_token_type`.

**"`issued_token_type` and `token_type` are the same thing."** False. One indicates the security token type, while the other indicates how the token is presented/used.

**"Holding a valid `subject_token` lets you request tokens for any audience."** False. The AS must verify client, subject, tenant, and target permissions.

**"Token exchange mints new scopes matching whatever parameter the client sends."** False. Output scopes must be approved by policy; arbitrary escalation must be blocked.

**"Token exchange automatically destroys the input token."** False. The RFC does not impose that side effect by default.

**"Revoking the input token automatically revokes all output tokens."** False. Separate propagation or linked revocation mechanisms are required.

**"An OIDC ID token can be used like an access token since both are JWTs."** False. ID tokens have different audiences and purposes; any exchange from an ID token must follow an explicitly supported profile and trust policy, never by default.

**"Whatever token types the RFC lists, Spring supports all of them out of the box."** False. Always check your specific version's converters/providers and implementation limits.

## 21. Token Exchange Design Checklist

- [ ] Does `grant_type` match the exact RFC 8693 URI?
- [ ] Are `subject_token` and `subject_token_type` required, parsed, and verified?
- [ ] Does `subject_token_type` accurately reflect **semantics/format** per the issuer's contract?
- [ ] Is `requested_token_type` treated as an optional request hint rather than an entitlement?
- [ ] Are `issued_token_type` and `token_type` in the response handled properly?
- [ ] Is the requesting client authenticated and registered for the token-exchange grant?
- [ ] Does the AS verify input issuer trust, signature/introspection, expiry, and bindings?
- [ ] Does policy verify subject/client/tenant and prevent unauthorized privilege escalation?
- [ ] Are output `audience`/`resource` and `scope` strictly constrained?
- [ ] If actor/delegation is used, is it verified and recorded accurately in `act`?
- [ ] Are input vs. output token TTLs, caching, and revocation distinguished?
- [ ] Have built-in supported token types been verified for your exact Spring version?
- [ ] Are missing parameters, wrong types, invalid tokens, invalid targets, cross-tenant, and scope escalation covered by tests?
- [ ] Do Resource Servers reject tokens with mismatched audiences or scopes?
- [ ] Are logs, traces, and audit records free of input/output credentials?

### Core Takeaways

In OAuth 2.0 Token Exchange:

- **`subject_token`** is the **input security token** representing the subject.
- **`subject_token_type`** is a **required** URI describing the input token type so the AS can verify it properly.
- **`requested_token_type`** is an **optional** URI describing the output token type desired by the client.
- **`issued_token_type`** in the response reveals the **token type actually issued**.

Token Exchange is a fresh authorization decision, not a mere token format conversion. Spring Authorization Server provides the Token Endpoint pipeline to process the grant, yet still requires complete trust, target, scope, client identity, token lifecycle policies, and thorough testing before production deployment.

## References

- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8693 Section 2.1 — Request](https://www.rfc-editor.org/rfc/rfc8693#section-2.1)
- [RFC 8693 Section 2.2 — Response](https://www.rfc-editor.org/rfc/rfc8693#section-2.2)
- [RFC 8693 Section 3 — Token Type Identifiers](https://www.rfc-editor.org/rfc/rfc8693#section-3)
- [RFC 8693 Section 4 — JSON Web Token Claims](https://www.rfc-editor.org/rfc/rfc8693#section-4)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — `OAuth2TokenExchangeAuthenticationToken` API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenExchangeAuthenticationToken.html)
- [Spring Security — OAuth 2.0 Client Authorization Grants](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html)
