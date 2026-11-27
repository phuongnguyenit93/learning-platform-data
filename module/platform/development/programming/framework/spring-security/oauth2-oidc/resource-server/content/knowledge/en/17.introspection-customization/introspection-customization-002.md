# Checking Audience, Issuer, or Token Type When Metadata Has Corresponding Requirements

In a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, having an **opaque access token** confirmed as active by the Authorization Server (AS) is not enough for the API to allow access. The introspection endpoint may return `active: true` along with metadata such as `aud`, `iss`, `token_type`, or a custom field specifying the **intended use of the token**. The Resource Server must know **which metadata is required**, **which metadata may be absent**, and **which contract to validate it against**.

Suppose the Orders API and Billing API share an Identity Server. A token issued for the Billing API can still be active. If the Orders API only sees `active: true` and an overlapping scope name and accepts the token, the system faces the risk of **token substitution**: a credential valid at one Resource Server is misused at another Resource Server. Likewise, a system with multiple realms/issuers could return active tokens from an environment or organization not trusted by the Orders API.

> **Principle:** Trusted introspection is the foundation of authentication, but **`active` does not mean the right audience, the right issuer, the right token type, or sufficient permissions**. These attributes must be checked **when metadata and the contract require them**, or there must be an **equivalent guarantee from a trusted endpoint/AS**. If the necessary evidence is missing, the Resource Server must reject rather than assign values to the token itself.

## 1. Context: How Does an Opaque Token Flow Through a Resource Server?

Suppose the system consists of:

- **Identity Server**: Authorization Server issuing opaque access tokens and providing an introspection endpoint.
- **Shop Web**: OAuth2/OIDC Client requesting access tokens and sending them to the API.
- **Orders API**: Spring Security Resource Server protecting orders; logical audience `orders-api`.
- **Billing API**: Another Resource Server; logical audience `billing-api`.

The client calls:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer 8xqP2...opaque-access-token...
~~~

The Orders API calls introspection:

~~~http
POST /introspect HTTP/1.1
Host: identity.example.test
Authorization: Basic <orders-api-credential>
Content-Type: application/x-www-form-urlencoded

token=8xqP2...opaque-access-token...&token_type_hint=access_token
~~~

Illustrative response:

~~~json
{
  "active": true,
  "iss": "https://identity.example.test/realms/shop",
  "aud": ["orders-api"],
  "token_type": "Bearer",
  "token_usage": "access_token",
  "sub": "user-842",
  "client_id": "shop-web",
  "scope": "orders.read",
  "exp": 1893459600
}
~~~

**`token_usage` in the example is custom metadata under the Identity Server's contract**, not a mandatory RFC 7662 claim. On the other hand, `token_type: "Bearer"` indicates **how the credential is used**, and does not by itself prove this token is an OAuth access token rather than an ID token.

Desired processing flow:

~~~mermaid
flowchart TD
    A["Receive Bearer opaque token"]
    B["OpaqueTokenIntrospector calls trusted AS"]
    C{"Is active true?"}
    X["Reject token / authentication"]
    D["Check metadata contract"]
    E{"audience/resource matches?"}
    F{"issuer trusted?"}
    G{"token purpose valid?"}
    H["Create OAuth2AuthenticatedPrincipal"]
    I["Map scope/roles/permissions"]
    J["HTTP and method authorization"]
    K["Owner, tenant, data state"]
    L["Execute protected request"]

    A --> B --> C
    C -->|No| X
    C -->|Yes| D --> E
    E -->|No| X
    E -->|Yes| F
    F -->|No| X
    F -->|Yes| G
    G -->|No| X
    G -->|Yes| H --> I --> J --> K --> L
~~~

The diagram is an **illustrative policy**, not a claim that every AS returns all fields. If the AS does not return a piece of metadata, the API must identify **which equivalent condition is proven by the endpoint/credential/profile** before deciding to skip direct checking.

## 2. Distinguishing `active` from Token Acceptance Conditions

In **OAuth 2.0 Token Introspection (RFC 7662)**, `active` is the central attribute reflecting whether the token is still recognized by the AS under its policy.

Inactive token:

~~~json
{
  "active": false
}
~~~

An active token is not necessarily issued for the Orders API:

~~~json
{
  "active": true,
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

Two distinct questions:

1. **Is the token still valid in the AS's system?**
2. **Is the token allowed to be used to call this API and perform this operation?**

| Scenario | Correct Assessment |
| --- | --- |
| `active: false` | Do not produce a successful authentication |
| `active: true`, valid `aud`, `iss`, and purpose | May proceed to evaluate scopes and permissions |
| `active: true`, Billing API audience | Reject if Orders API requires `orders-api` |
| `active: true`, untrusted issuer | Reject when issuer is a mandatory constraint |
| `active: true` but token purpose is ID token | Reject if API only accepts OAuth access tokens |
| `active: true`, missing required audience | Reject, unless a trusted equivalent resource binding exists |
| `active: true`, valid scope but wrong tenant | Reject at the data-level authorization policy |

Successful introspection is **a prerequisite for trusting metadata**, not a guarantee that every API can accept that token. Many Authorization Servers restrict which tokens can be introspected according to the Resource Server client's permissions; if relying on this guarantee, a clear contract and tests are required.

## 3. What Metadata Exists in RFC 7662?

RFC 7662 describes a `POST` request with the `token` parameter and optional `token_type_hint`, along with a JSON response containing `active` and metadata that may appear.

| Attribute | Common Meaning | Safe Usage |
| --- | --- | --- |
| **`active`** | Is the token active? | Must have a trusted result before authenticating |
| **`scope`** | List of the token's OAuth2 scopes | Used to grant `SCOPE_...` per contract |
| **`client_id`** | OAuth2 Client issued the token | Not the Resource Server's Client ID used to call introspection |
| **`username`** | Username | Not by default a stable identity key |
| **`token_type`** | Token type, commonly `Bearer` | Does not mean token purpose is `access_token` |
| **`exp`** | Expiration time | Bounds caching and checks time policy when needed |
| **`iat`** | Issuance time | Used per profile if needed |
| **`nbf`** | Token must not be used before this time | Can be checked additionally per policy |
| **`sub`** | Subject the token refers to | May be a user or service depending on grant |
| **`aud`** | Audience/resource of the token | Check if required by contract or equivalent resource binding |
| **`iss`** | Issuer of the token | Check per contract or binding from the AS endpoint |
| **`jti`** | Token identifier | Does not grant permissions or validity on its own |
| **`token_usage`**, **`token_use`** | Custom token-purpose metadata | Meaningful only when the AS defines its schema and allowed values |

**Not every response contains `aud`, `iss`, `token_type`, or custom token usage.** If they are mandatory for the Orders API, both sides must agree and test them. Do not require a nonexistent field and conclude all opaque tokens are invalid; nor should you drop a security requirement merely because the AS does not return that field.

### 3.1. Source of Trust for Metadata

~~~text
Caller's bearer token
  -> unverified credential

Introspection response from AS
  -> trusted only after connecting to the right endpoint,
     authenticating the Resource Server to the AS, and handling active

Orders API policy
  -> validates audience/issuer/purpose
     before deciding permissions
~~~

Never use arbitrary headers such as:

~~~http
X-Token-Audience: orders-api
X-Token-Issuer: https://identity.example.test/realms/shop
X-Token-Usage: access_token
~~~

to substitute for metadata from the AS. Callers can freely populate those values themselves.

## 4. Audience: Which Resource Server Was the Token Issued For?

Audience is a critical boundary between APIs sharing an Authorization Server.

Valid audience token for Orders API:

~~~json
{
  "active": true,
  "aud": ["orders-api"],
  "scope": "orders.read",
  "sub": "user-842"
}
~~~

Token for another API:

~~~json
{
  "active": true,
  "aud": ["billing-api"],
  "scope": "orders.read",
  "sub": "user-842"
}
~~~

The latter case must be **rejected for audience**, even though it is active and has the same scope string.

### 4.1. Audience Can Be a String or a List

Depending on the AS/serialization, the introspection response may return:

~~~json
{"aud": "orders-api"}
~~~

or:

~~~json
{"aud": ["orders-api", "reports-api"]}
~~~

A common policy is checking whether **the audience set contains the expected audience**. However, not every API wants to accept multi-audience tokens; it may require a single audience or check additional resource indicators. Document the policy explicitly instead of accepting any set containing the API's name by default.

### 4.2. Audience Identifier Is Not Necessarily the API URL

~~~text
orders-api
https://api.example.test/orders
urn:example:resource:orders
~~~

These are three identifier styles used in different systems. Do not assume `aud` is always a hostname, an OAuth2 Client ID, or a key under `resource_access`. The value must be agreed upon between the AS and Resource Server.

### 4.3. If the Response Omits `aud`

Distinguish clearly:

1. **Contract requires returning `aud`:** absence is invalid metadata → reject.
2. **AS guarantees resource binding via endpoint/credential:** e.g., Resource Server `orders-api` is only allowed to introspect tokens intended for it, and Billing API tokens return inactive. The API may rely on that guarantee if **documented and tested**.
3. **No field and no proven resource binding:** there is no basis to know which API the token is for. Metadata or a binding mechanism must be added; do not accept every active token.

Merely having an introspection Client ID named "orders-api" **does not prove** that the AS restricts tokens by audience. It must be an actual enforced AS policy.

## 5. Issuer: Restricting Trusted Issuers

Issuer identifies the token-issuing authority when the AS includes the `iss` attribute in the response. A production Orders API might trust only:

~~~text
https://identity.example.test/realms/shop
~~~

A matching response:

~~~json
{
  "active": true,
  "iss": "https://identity.example.test/realms/shop",
  "aud": ["orders-api"]
}
~~~

A response from another source:

~~~json
{
  "active": true,
  "iss": "https://id.dev.example.test/realms/shop",
  "aud": ["orders-api"]
}
~~~

If the contract requires the production issuer, the second response must be rejected. Having the same scope or role names in dev and production **does not make two issuers the same**.

### 5.1. Trusting the Introspection Endpoint vs. Checking `iss`

With opaque tokens, the Resource Server primarily relies on **responses from a trusted introspection endpoint** rather than verifying a JWS locally with a public key. There are two layers of binding:

| Layer | Meaning | Example |
| --- | --- | --- |
| Endpoint trust | Which AS the Resource Server contacts over HTTPS with the right credentials | `https://identity.example.test/introspect` |
| Metadata issuer | Which issuer the AS reports as having issued the token | `https://identity.example.test/realms/shop` |

If the endpoint **only introspects tokens issued by a single issuer**, endpoint trust can substitute for checking the `iss` claim when the AS omits it and the contract allows. If an introspection gateway handles tokens from **multiple realms/issuers**, `iss` or dedicated routing/binding becomes essential.

**Never fill in the expected issuer value into the response when the field is absent** and claim the issuer was verified. That merely inserts an API-supplied string, not proof that the token belongs to that issuer.

### 5.2. Matching Issuer by Official Identifier Value

~~~text
https://identity.example.test/realms/shop
https://identity.example.test/realms/shop/
~~~

Two values can differ under the issuer contract. Do not strip paths, downgrade `https` to `http`, remove trailing slashes, or compare hostnames only unless there is a normalization rule agreed upon with the issuer.

For a multi-issuer API, each issuer needs appropriate **credentials/endpoints or claim mapping, audience, and role semantics**. Do not merge permissions across issuers merely because both have an `admin` role.

## 6. Token Type vs. Token Purpose

A particularly dangerous misconception is treating:

~~~json
{"token_type": "Bearer"}
~~~

as equivalent to:

~~~text
This token is definitely an OAuth 2.0 access token.
~~~

In OAuth 2.0:

- **Access token** is the credential a Client uses to access a Resource Server.
- **Bearer** is how the token is used: the party holding the credential can present it without proof-of-possession in the Bearer model.
- **OIDC ID token** serves the OIDC Client to confirm a login result, not as an access token for APIs.

Therefore, **`token_type: "Bearer"` does not prove the token purpose is `access_token`**. Similarly, an introspection request with `token_type_hint=access_token` is only a **hint**, not a token-kind verification result.

### 6.1. A Custom Contract May Define `token_usage`

Suppose the AS is configured to return:

~~~json
{
  "active": true,
  "token_type": "Bearer",
  "token_usage": "access_token",
  "aud": ["orders-api"],
  "iss": "https://identity.example.test/realms/shop"
}
~~~

Then the Orders API can check that **the custom `token_usage` field equals `access_token`**. However, this field is part of a custom contract, **not required by RFC 7662**. Another issuer might use `token_use: "access"`, a `purpose` field, or return no field at all while **the introspection endpoint only accepts access tokens**.

Do not write:

~~~java
// WRONG under RFC 7662 semantics:
"access_token".equals(principal.getAttribute("token_type"))
~~~

If the AS returns `token_type = Bearer`, the code above will reject valid tokens without properly checking token purpose.

### 6.2. Do Not Infer Token Kind from Shape

The following inferences are unsafe:

~~~text
Has 3 dot-separated parts -> definitely an access token.
Has no dots -> definitely an opaque token intended for access.
Authorization header is Bearer -> definitely the right token kind.
AS returns active = true -> token definitely works for every API.
~~~

An OAuth access token can be a JWT or opaque; an ID token is usually a JWT, yet **must not be used in place of an access token**. The Resource Server must rely on the AS's profile/metadata and dedicated audience.

### 6.3. When There Is No Token-Purpose Field

If the AS does not return `token_usage`, ask:

- Does the introspection endpoint **only recognize OAuth access tokens**?
- Could an ID token or refresh token also be returned as active?
- Is the Orders API's introspection credential restricted to checking access tokens for this resource only?
- Is there other metadata specifying purpose or resource binding?

Only with a reliable guarantee can the API omit checking this custom field. Never set a `"default = access_token"` when the field is absent.

## 7. A Good Metadata Contract Distinguishes Required vs. Optional

Example Orders API policy:

| Metadata | Illustrative Policy | If Missing |
| --- | --- | --- |
| `active` | Must be true | Do not authenticate |
| `aud` | Must contain `orders-api` | Reject unless an equivalent trusted resource binding exists |
| `iss` | Must equal production shop issuer | Reject unless an equivalent issuer binding exists |
| `token_usage` | Must be `access_token` in this custom profile | Reject if the profile commits to providing it |
| `token_type` | If returned by AS, must equal `Bearer` | If AS does not commit to returning it, absence alone does not prove invalidity |
| `scope` | Requires `orders.read` on GET | May authenticate, then reject due to missing permission → 403 |
| `sub` | Required for user endpoints per profile | Reject or apply separate service policy |
| `client_id` | Accept only Clients per endpoint rules when needed | Handle per client contract |
| `tenant_id` | Required for certain multi-tenant APIs | Reject or resolve tenant from trusted source |
| `exp` | Limits validity/caching per profile | Do not cache indefinitely when expiration is unknown |

### 7.1. Three Levels of Assurance

1. **Required metadata**: The AS commits to returning the field; missing, wrong type, or wrong value → reject.
2. **Optional but checked if present**: The field may be absent; when present, it must be valid. Safe only if that condition is unnecessary or guaranteed elsewhere.
3. **Bound by AS endpoint/registration**: Metadata is not returned in the body, but the endpoint, credential, or registration itself guarantees the same condition. This must be a **verified constraint**, not guesswork.

Do not turn a required field into optional just to make requests succeed after deployment. Any policy change must be reviewed as **a security change**.

### 7.2. Example of an Insufficient Response

~~~json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "shop-web"
}
~~~

You cannot conclude issuer, audience, or token purpose **from this JSON alone**. If the AS endpoint has a contract guaranteeing all three, those constraints can be documented on the server side; otherwise, the Resource Server needs more evidence rather than accepting tokens based on scope alone.

## 8. Where Does Spring Security Process Opaque Tokens and Metadata?

Typical flow in Spring Security 6:

~~~text
HTTP Authorization: Bearer <opaque-token>
     |
BearerTokenAuthenticationFilter
     |
OpaqueTokenAuthenticationProvider
     |
OpaqueTokenIntrospector
     |-> POST to AS with Resource Server credentials
     |-> Check active status and parse metadata
     |
Custom OpaqueTokenIntrospector wrapper
     |-> Check issuer / audience / token purpose
     |-> Throw on contract violation
     |
OAuth2AuthenticatedPrincipal
     |
BearerTokenAuthentication, authorities
     |
authorizeHttpRequests / @PreAuthorize
     |
Business policy: owner, tenant, state
~~~

Components to understand:

| Component | Responsibility |
| --- | --- |
| `OpaqueTokenIntrospector` | Interface verifying an opaque token via introspection |
| `NimbusOpaqueTokenIntrospector` or equivalent implementation | Sends HTTP requests and interprets responses per framework |
| `OAuth2AuthenticatedPrincipal` | Principal with attributes/authorities returned by the introspector |
| `BadOpaqueTokenException` | Rejects tokens not accepted under policy |
| `BearerTokenAuthentication` | Authentication for an authenticated Bearer request |
| `SecurityFilterChain` | Matches HTTP method, URL, and authority |
| Method security/service | Checks permissions on actual resources |

**The right place for common metadata checks is inside `OpaqueTokenIntrospector` or a centralized authentication policy layer.** Checking audience in controller A while forgetting controller B can cause the same token to be handled inconsistently.

## 9. Configuring Spring Boot Resource Server

The examples below use **Spring Boot 3 / Spring Security 6** with an API using opaque access tokens.

### 9.1. Dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 9.2. Configuring Introspection and Expected Metadata

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: ${OAUTH_INTROSPECTION_URI}
          client-id: ${OAUTH_INTROSPECTION_CLIENT_ID}
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}

app:
  security:
    expected-issuer: ${OAUTH_EXPECTED_ISSUER}
    expected-audience: ${OAUTH_EXPECTED_AUDIENCE}
    expected-token-usage: access_token
~~~

Example environment:

~~~text
OAUTH_INTROSPECTION_URI=https://identity.example.test/realms/shop/protocol/openid-connect/token/introspect
OAUTH_INTROSPECTION_CLIENT_ID=orders-api-introspection
OAUTH_INTROSPECTION_CLIENT_SECRET=<secret-supplied-by-secret-manager>
OAUTH_EXPECTED_ISSUER=https://identity.example.test/realms/shop
OAUTH_EXPECTED_AUDIENCE=orders-api
~~~

URIs are illustrative; the actual endpoint and how the Resource Server authenticates to the AS are defined by the issuer. Secrets must be supplied via a secret management system, **never committed to repositories, logs, or public config files**.

### 9.3. Protecting HTTP Endpoints

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

The example assumes `/api/**` is a REST API accepting only Bearer tokens without session cookies. Therefore, CSRF is disabled and sessions are stateless only in this chain. If there are endpoints outside `/api/**`, you need another `SecurityFilterChain` or an appropriate fallback policy so nothing is accidentally left exposed.

## 10. Creating an `OpaqueTokenIntrospector` That Enforces the Metadata Contract

Designing a **decorator**:

1. The delegate introspector sends the token to the trusted AS endpoint and evaluates `active`.
2. The wrapper reads **the introspected metadata itself** and validates `iss`, `aud`, and custom `token_usage`.
3. If a required field is missing or wrong, the wrapper raises an error.
4. Only when valid does it return the original `OAuth2AuthenticatedPrincipal` so Spring Security can apply scopes and policy.

In this example, **the contract requires `iss`, `aud`, and `token_usage`**. Do not interpret this as mandatory for every RFC 7662 response.

### 10.1. Decorator Checking Issuer, Audience, Usage, and Bearer Token Type

~~~java
import java.util.Collection;
import java.util.Objects;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class ExpectedTokenMetadataIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedIssuer;
    private final String expectedAudience;
    private final String expectedTokenUsage;

    public ExpectedTokenMetadataIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedIssuer,
            String expectedAudience,
            String expectedTokenUsage) {

        this.delegate = Objects.requireNonNull(delegate);
        this.expectedIssuer = Objects.requireNonNull(expectedIssuer);
        this.expectedAudience = Objects.requireNonNull(expectedAudience);
        this.expectedTokenUsage = Objects.requireNonNull(expectedTokenUsage);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Delegate handles the protocol, AS connection, and active check.
        OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

        Object issuer = principal.getAttribute("iss");
        if (!expectedIssuer.equals(issuer)) {
            throw new BadOpaqueTokenException(
                "Token issuer is not accepted");
        }

        Object audience = principal.getAttribute("aud");
        if (!containsAudience(audience, expectedAudience)) {
            throw new BadOpaqueTokenException(
                "Token audience is not accepted");
        }

        // This is a CUSTOM AS attribute, not standard RFC 7662.
        Object usage = principal.getAttribute("token_usage");
        if (!expectedTokenUsage.equals(usage)) {
            throw new BadOpaqueTokenException(
                "Token usage is not accepted");
        }

        // Bearer = credential usage style, NOT access token purpose.
        Object tokenType = principal.getAttribute("token_type");
        if (tokenType != null && !"Bearer".equals(tokenType)) {
            throw new BadOpaqueTokenException(
                "Token type is not supported");
        }

        return principal;
    }

    static boolean containsAudience(Object rawAudience, String expected) {
        if (rawAudience instanceof String value) {
            return expected.equals(value);
        }
        if (rawAudience instanceof Collection<?> values) {
            return values.contains(expected);
        }
        return false;
    }
}
~~~

Decisions in this code:

- **`iss` and `aud` are mandatory** per the example profile: null or mismatched values are rejected.
- **`token_usage` is mandatory** and must be `access_token`: no fallback to other token kinds.
- **`token_type`, if present, must be `Bearer`**. If the AS commits to always returning it, you can make it mandatory; if the AS does not return this field, rely on how the token is used and contract-specific guarantees.
- **Audience can be a String or a Collection**. Wrong-typed data will not match and will be rejected.
- The wrapper does not parse the raw opaque token, read arbitrary caller-sent headers, or invent admin permissions.
- On success, it returns the **unchanged principal** from the delegate to preserve metadata/authorities created by framework policy.

**Note:** Introspection implementations may convert metadata into different Java types depending on the version and response. Match the actual runtime types returned by your AS rather than bypassing safety checks when a type mismatch occurs.

### 10.2. Registering the Decorator in Spring Security

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
class IntrospectionConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaque-token.introspection-uri}")
            String introspectionUri,
            @Value("${spring.security.oauth2.resourceserver.opaque-token.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaque-token.client-secret}")
            String clientSecret,
            @Value("${app.security.expected-issuer}") String issuer,
            @Value("${app.security.expected-audience}") String audience,
            @Value("${app.security.expected-token-usage}") String usage) {

        OpaqueTokenIntrospector delegate =
                new NimbusOpaqueTokenIntrospector(
                        introspectionUri,
                        clientId,
                        clientSecret);

        return new ExpectedTokenMetadataIntrospector(
                delegate, issuer, audience, usage);
    }
}
~~~

In some Spring Security 6 versions, you can use `SpringOpaqueTokenIntrospector` or a recommended builder instead of the `NimbusOpaqueTokenIntrospector` constructor; the core pattern remains **delegating to a trusted HTTP introspector and then applying metadata validation**. When defining a custom bean, ensure `SecurityFilterChain` actually uses that bean, avoiding registering competing `OpaqueTokenIntrospector` beans or directly configuring another introspector that bypasses the wrapper.

### 10.3. If the AS Does Not Return Issuer/Audience/Usage

The strict code above **is not meant for every IdP**. Do not copy it and strip out conditions one by one when the endpoint errors, because each condition represents a security boundary.

Instead:

- **Issuer absent:** verify the introspection endpoint only processes tokens issued by a single issuer, or use another issuer-binding mechanism.
- **Audience absent:** verify the AS rejects introspecting tokens for other resources when called with Orders API credentials, or add another resource binding.
- **Usage absent:** verify the endpoint only introspects OAuth access tokens and does not recognize ID/refresh tokens in the API context; or ask the AS to provide custom metadata.
- **Different field names:** verify your AS product's schema and semantics—for example, `token_use: access` does not automatically equal `token_usage: access_token`.

Every decision to omit a field check must be **documented in the contract, tested, and monitored**, never based on assuming "the AS probably checked it by default."

## 11. `token_type_hint` Is Not a Token Verification Result

An introspection request may contain:

~~~http
Content-Type: application/x-www-form-urlencoded

token=<opaque-token>&token_type_hint=access_token
~~~

`token_type_hint` is an **optional hint** helping the AS decide which token type to look up. It does not mean the token actually is an access token. The AS must still verify the token and determine `active`.

Never infer:

~~~text
Resource Server sends token_type_hint=access_token
  -> token is definitely an access token
  -> skip all purpose checks
~~~

Likewise, a Client sending `Authorization: Bearer ...` is only how the **credential is presented**, not proof of issuer, audience, or token purpose.

## 12. When Multiple Issuers Share an Introspection Gateway

An AS gateway may handle tokens from multiple sources:

~~~text
https://identity-gateway.example.test/introspect
  - shop production
  - shop staging
  - partner-A
  - partner-B
~~~

If the gateway returns `active: true` for tokens belonging to multiple issuers, the Orders API must specify **which issuers are allowed**, rather than trusting every token known to the gateway.

| Issuer/Profile | Allowed Audience | Mapped Permissions | Policy |
| --- | --- | --- | --- |
| Shop production | `orders-api` | `SCOPE_orders.read` | Check shop user/tenant |
| Shop staging | `orders-api-staging` | Staging environment permissions | Do not allow into production |
| Partner-A | `partner-orders-api` | Partner-contracted permissions | Linked tenants only |
| Partner-B | Not registered | None | Must not be accepted automatically |

**The same `sub` or the same `admin` role does not mean the same identity/permissions across two different issuers.** With multiple valid issuers, maintain separate mappings and policies per source rather than using one converter that scans any role string and grants shared permissions.

### 12.1. Multi-Valued Audience

A token with:

~~~json
{"aud": ["orders-api", "billing-api"]}
~~~

The example `containsAudience` function accepts this token because `orders-api` is present. If your system forbids tokens usable across multiple resources, replace the policy with an exact audience-set check and corresponding tests. Never assume mere presence of one audience is sufficient in every architecture.

### 12.2. Environment Separation

~~~text
DEV
  introspection_uri = https://id.dev.example.test/introspect
  issuer            = https://id.dev.example.test/realms/shop
  audience          = orders-api-dev

PRODUCTION
  introspection_uri = https://identity.example.test/introspect
  issuer            = https://identity.example.test/realms/shop
  audience          = orders-api
~~~

Credentials, issuer, and audience must be configured separately per environment; never accept dev tokens in production merely because scopes or roles look the same.

## 13. Relationship with `scope`, `exp`, and Resource Permissions

**Token metadata validation** and **authorization decisions** are two distinct layers.

Response:

~~~json
{
  "active": true,
  "iss": "https://identity.example.test/realms/shop",
  "aud": ["orders-api"],
  "token_usage": "access_token",
  "scope": "orders.read",
  "sub": "user-842",
  "tenant_id": "tenant-A"
}
~~~

allows the Resource Server to confirm the token matches the profile and, with the default converter, can produce the `SCOPE_orders.read` authority. Yet the caller is still **not automatically permitted** to read Order 42 if the order belongs to `tenant-B` or another subject under policy.

| Layer | Example Check | If Missing |
| --- | --- | --- |
| Introspection | `active`, issuer, audience, usage | Authentication fails |
| HTTP authorization | `SCOPE_orders.read` for GET | Usually 403 |
| Method authorization | Specialized role/permission | Usually 403 |
| Data policy | Owner, tenant, assignment, state | 403/404 or business error |

`exp`, `nbf`, and `iat` can support validation and cache policy. With introspection, the AS is responsible for determining active status; if `exp` is also provided, do not cache responses beyond the token's lifetime or agreed limits. Never extract `exp` from a caller-supplied opaque string and verify it yourself.

### 13.1. User Principal vs. Service Principal

A `client_credentials` token may carry:

~~~json
{
  "active": true,
  "aud": ["orders-api"],
  "client_id": "nightly-sync",
  "sub": "nightly-sync",
  "scope": "orders.sync",
  "token_usage": "access_token"
}
~~~

Never infer that `sub = nightly-sync` is a customer who owns Order 42. The API must distinguish service principals from user principals by token/profile, endpoint, and granted permissions. The `client_id` of the introspected token is also different from the `client-id` the Orders API uses to authenticate to the introspection endpoint.

## 14. Classifying Errors So Dependency Outages Do Not Become Bypasses

| Scenario | Handling Layer | Security Expectation |
| --- | --- | --- |
| No Bearer token | Authentication filter | Protected request is rejected |
| AS returns `active:false` | Delegate introspector | No authenticated principal |
| AS returns `active:true` with wrong audience | Metadata wrapper | Reject token |
| Untrusted issuer | Metadata wrapper | Reject token |
| Custom usage is not access token | Metadata wrapper | Reject token |
| Metadata valid, missing scope | HTTP authorization | Usually 403 |
| Sufficient scope, wrong owner/tenant | Data policy | 403/404 per policy |
| Resource Server uses wrong introspection client secret | AS / HTTP client | Integration error, no access granted |
| AS 503/timeout or DNS/TLS failure | Dependency | Do not execute protected operation |
| AS returns malformed JSON or omits `active` | Parser/delegate | Do not produce successful authentication |

With Bearer authentication, an invalid token usually results in **401 Unauthorized**, whereas an authenticated token lacking permission usually results in **403 Forbidden**. HTTP/network errors during temporary AS outages may be mapped to different statuses by the framework and exception handlers. In all cases, **no protected request may execute when the token cannot be verified**.

### 14.1. Never Fail Open

~~~java
// WRONG CODE: NEVER APPLY THIS.
try {
    return delegate.introspect(token);
} catch (RuntimeException unavailable) {
    return createAdminPrincipal();
}
~~~

When the AS is unreachable, the API cannot assume a token is still active or has admin permissions. If introspection caching is used, rely on results only within the **approved TTL and revocation policy**, never extending indefinitely when the AS is down.

### 14.2. Distinguishing Inactive Tokens from an Unavailable AS

~~~text
HTTP 200 + {"active":false}
    -> AS evaluated: token is not active

HTTP 503 / timeout / TLS / DNS error
    -> no trustworthy verification result available
~~~

Neither may permit protected operations, but logs/metrics must distinguish them to diagnose token errors, configuration errors, or dependency incidents.

## 15. Unit Testing the Validator with a Fake Introspector

Because the wrapper depends on the `OpaqueTokenIntrospector` interface, you can unit test metadata logic without HTTP calls.

### 15.1. Principal Fixture

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

final class TestPrincipalFactory {

    static OAuth2AuthenticatedPrincipal principal(
            Map<String, Object> attributes) {

        return new DefaultOAuth2AuthenticatedPrincipal(
                "user-842",
                attributes,
                List.of(new SimpleGrantedAuthority(
                        "SCOPE_orders.read")));
    }

    private TestPrincipalFactory() {}
}
~~~

This is a **mock principal for unit tests**, not a representation of a real introspection response. In production, only a trusted configured delegate creates principals from AS metadata.

### 15.2. Testing Valid Audience, Issuer, and Usage

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

class ExpectedTokenMetadataIntrospectorTest {

    private static final String ISSUER =
            "https://identity.example.test/realms/shop";

    private Map<String, Object> valid() {
        Map<String, Object> attributes = new HashMap<>();
        attributes.put("iss", ISSUER);
        attributes.put("aud", List.of("orders-api"));
        attributes.put("token_type", "Bearer");
        attributes.put("token_usage", "access_token");
        attributes.put("sub", "user-842");
        attributes.put("scope", "orders.read");
        return attributes;
    }

    private OpaqueTokenIntrospector policy(Map<String, Object> attrs) {
        OpaqueTokenIntrospector fakeDelegate =
                token -> TestPrincipalFactory.principal(attrs);

        return new ExpectedTokenMetadataIntrospector(
                fakeDelegate, ISSUER, "orders-api", "access_token");
    }

    @Test
    void acceptsCorrectMetadata() {
        var principal = policy(valid()).introspect("opaque-test-token");
        assertEquals("user-842", principal.getAttribute("sub"));
    }

    @Test
    void rejectsWrongAudience() {
        var attrs = valid();
        attrs.put("aud", List.of("billing-api"));
        assertThrows(BadOpaqueTokenException.class,
                () -> policy(attrs).introspect("opaque-test-token"));
    }

    @Test
    void rejectsWrongIssuer() {
        var attrs = valid();
        attrs.put("iss", "https://id.dev.example.test/realms/shop");
        assertThrows(BadOpaqueTokenException.class,
                () -> policy(attrs).introspect("opaque-test-token"));
    }

    @Test
    void rejectsWrongTokenUsageEvenIfBearer() {
        var attrs = valid();
        attrs.put("token_usage", "id_token");
        assertThrows(BadOpaqueTokenException.class,
                () -> policy(attrs).introspect("opaque-test-token"));
    }

    @Test
    void rejectsMissingRequiredAudience() {
        var attrs = valid();
        attrs.remove("aud");
        assertThrows(BadOpaqueTokenException.class,
                () -> policy(attrs).introspect("opaque-test-token"));
    }

    @Test
    void rejectsMissingRequiredUsage() {
        var attrs = valid();
        attrs.remove("token_usage");
        assertThrows(BadOpaqueTokenException.class,
                () -> policy(attrs).introspect("opaque-test-token"));
    }
}
~~~

These tests only verify **post-delegate metadata checking logic**. They **do not prove** that the Resource Server sent a POST to the right endpoint, authenticated to the AS with the right secret, or handled `active`, TLS, or timeouts. To test those aspects, use integration tests with a mocked HTTP AS.

### 15.3. Recommended Matrix of Negative Cases

| Metadata | Test Case | Result |
| --- | --- | --- |
| `aud` String | Equals `orders-api` | Accept if other conditions pass |
| `aud` List | Contains `orders-api` | Accept under "contains" policy |
| `aud` List | Only `billing-api` | Reject |
| `aud` | Absent or wrong type | Reject under strict contract |
| `iss` | Dev issuer instead of production | Reject |
| `iss` | Absent when required by contract | Reject |
| `token_usage` | `access_token` | Accept under custom profile |
| `token_usage` | `id_token` | Reject |
| `token_usage` | Absent when required by contract | Reject |
| `token_type` | `Bearer` | Not rejected by type check |
| `token_type` | Value disallowed by contract | Reject |
| `scope` | Missing `orders.read` | Authentication may succeed; authorization 403 |
| `active` | `false` | Delegate must reject before wrapper |

## 16. Integration Testing with a Mocked Introspection Endpoint

Use **WireMock** or **OkHttp MockWebServer** to test the actual protocol:

~~~mermaid
sequenceDiagram
    participant C as Test Client
    participant API as Spring Resource Server
    participant AS as Mock AS

    C->>API: Bearer opaque-valid
    API->>AS: POST token + introspection credential
    AS-->>API: active:true, valid iss/aud/usage
    API->>API: Wrapper accepts metadata
    API-->>C: Passes authentication and policy

    C->>API: Bearer opaque-wrong-audience
    API->>AS: POST token + credential
    AS-->>API: active:true, aud:billing-api
    API->>API: Wrapper rejects
    API-->>C: Authentication failure
~~~

### 16.1. Key Scenarios

1. AS returns `active:true`, valid issuer/audience/usage, and sufficient scope → request passes authentication.
2. AS returns `active:false` → reject.
3. AS returns active, but audience belongs to another API → reject.
4. AS returns disallowed dev/partner issuer → reject.
5. AS returns custom usage = `id_token` → reject.
6. AS returns `token_type = Bearer` but omits required `token_usage` → reject under strict profile.
7. AS returns wrong-typed `aud` or malformed metadata → reject.
8. Metadata valid, insufficient scope → HTTP authorization rejects.
9. Metadata/scope valid, wrong owner/tenant → business policy rejects.
10. AS returns 401 for wrong introspection credentials → no successful authentication.
11. AS 5xx/timeout → no protected operation executed.
12. AS returns JSON missing `active` or malformed → do not treat as authenticated token.
13. Billing API token introspected using Orders API credentials → verify whether AS returns inactive or active with wrong audience; neither path may grant Orders permissions.

### 16.2. Verifying the HTTP Protocol

The mock AS should observe:

~~~text
POST /introspect
Content-Type: application/x-www-form-urlencoded
token=<opaque-test-token>
Authorization: <resource-server-credential>
token_type_hint=access_token (if sent by the HTTP client)
~~~

**`token_type_hint` is optional**; do not make tests require it if the library does not send it. The goal is to confirm the AS is called with valid credentials, the right token body, and that responses actually flow through the wrapper.

### 16.3. Do Not Assert Only the HTTP Status Code

When a request is rejected for invalid metadata, integration tests should verify:

~~~text
No trusted Authentication
Protected controller is never entered
Data-updating service is never called
No database writes / business events emitted
~~~

A request that ultimately returns 401/403 after mutating an order **fails security requirements**.

## 17. Introspection Caching and Potentially Stale Metadata

Caching reduces calls to the AS but introduces trade-offs:

- Cached `active:true` may persist after a token has been revoked.
- Roles/scopes may change in the AS before the cache updates.
- Resource bindings or issuer policies may change while old cache entries still retain metadata.
- Caching by user `sub` rather than by token can mix multiple tokens with different audiences/scopes.

If caching is used, manage:

1. TTLs bounded by `exp` and policy.
2. Rules for caching positive/negative results.
3. Invalidation when a token/credential is revoked.
4. Protecting cache keys, because opaque tokens are secret credentials.
5. Rules when the AS is down: only use results within the **approved lifetime**, never extending indefinitely.
6. Policy version: when expected issuer/audience changes, do cached entries validated under the old policy need invalidation?

Two common patterns:

~~~text
HTTP introspection -> metadata validation -> cache validated principal

HTTP introspection -> cache AS response -> validation on every request
~~~

If choosing the first pattern, policy changes may require clearing/versioning the cache. If choosing the second, ensure both caching and validation execute with trusted data and TTLs.

**Never cache using `sub` as the sole key**, because the same subject can have multiple tokens with different scopes, audiences, and expirations. Avoid logging raw tokens or placing plaintext tokens in metric labels.

## 18. Operations, Observability, and Handling Contract Changes

Metrics/logs you can record:

- Request/correlation ID, API endpoint.
- **Configured** introspection endpoint and environment.
- Latency, timeouts, dependency HTTP 4xx/5xx.
- Rejection reason by category: inactive, wrong audience, wrong issuer, wrong usage, missing required metadata, insufficient scope.
- Schema/contract version in use.

**Never log raw opaque tokens, introspection client secrets, refresh tokens, or unnecessary sensitive metadata.** Before a token is verified, caller-controlled input can cause log injection or cardinality issues if left unhandled.

### 18.1. When the AS Renames Metadata

For example, the AS changes:

~~~text
aud = ["orders-api"]
~~~

to:

~~~text
audience = ["orders-api"]
~~~

Do not disable the audience validator to avoid errors. Update **the contract, wrapper, and positive/negative test suites** together. If two schemas must be supported during a migration window, define the types, scope, and compatibility period explicitly.

### 18.2. Never Let the Caller Choose Expected Issuer/Audience

Wrong:

~~~http
X-Expected-Issuer: https://id.dev.example.test
X-Expected-Audience: billing-api
~~~

Expected values must come from **server configuration and trusted routing policy**, never from headers/queries/bodies set by the caller. In multi-tenant setups, tenant/profile resolution must also align with trust boundaries, avoiding unverified strings that widen the set of allowed issuers.

## 19. Common Misconceptions

**"`active:true` means every API can accept the token."** False. Audience/resource binding must be ensured separately.

**"RFC 7662 requires every response to return `aud` and `iss`."** No. Metadata varies by AS.

**"If `aud` is missing, just ignore it."** No. Without equivalent resource binding, missing a required audience must lead to rejection.

**"`token_type: Bearer` means access token."** No. Bearer is the usage method, not the purpose.

**"`token_type_hint=access_token` proves the token is the right type."** No. It is only a hint sent with the introspection request.

**"Opaque tokens have readable claims like JWTs."** There is no local decoding contract; trust only AS results or agreed mechanisms.

**"Same issuer means a Billing API token also works at the Orders API."** No. Issuer and audience are two separate checks.

**"If the right introspection URI is chosen, issuer checking is unnecessary."** Not necessarily. If the endpoint is multi-issuer, issuer binding from metadata or policy is still needed.

**"Valid metadata means access to every order."** No. Scopes and owner/tenant policies still apply.

**"To check token type, just inspect the suffix of the opaque token string."** False. Token purpose must be determined by the AS/profile.

**"When the AS is down, assume previously seen tokens are still active."** False. Use only valid cache entries under policy; never fail open.

**"Fake introspector unit tests prove the HTTP client authenticated with the AS."** No. Integration tests for POST/form/credentials and real error handling are required.

## 20. Sample Contract Between Identity and Orders API

~~~yaml
# Example contract, not configuration automatically read by Spring.
resource_server: orders-api
token_format: opaque
trusted_authorization_server: https://identity.example.test
introspection_endpoint: https://identity.example.test/introspect
introspection_auth: client_secret_basic

metadata:
  active:
    required: true
    equals: true
  audience:
    claim: aud
    required: true
    contains: orders-api
  issuer:
    claim: iss
    required: true
    exact: https://identity.example.test/realms/shop
  token_usage:
    claim: token_usage
    provenance: "custom metadata from Authorization Server"
    required: true
    equals: access_token
  token_type:
    claim: token_type
    required: false
    if_present: Bearer
  scope:
    endpoint_rules:
      GET_orders: orders.read
      POST_orders: orders.write

missing_required_metadata: reject
unexpected_metadata: reject
upstream_unavailable: fail_closed
data_policy: verify_owner_and_tenant
~~~

If an IdP does not return `iss` or `token_usage`, the contract can replace the direct requirement with **endpoint binding and verified AS policy**. That must be documented explicitly; never "fake" a field and treat it as valid.

### Questions to Align On Before Implementation

1. Does the introspection endpoint accept tokens from a single issuer or multiple issuers?
2. What result is returned if a Billing API token is introspected using Orders API credentials?
3. Does the AS return `aud`, as a String or an array, and what identifier is expected?
4. If `iss` is not returned, how does endpoint/registration guarantee the issuing source?
5. Can the AS introspect ID tokens or refresh tokens?
6. Does the AS's `token_type` reflect `Bearer` or a custom meaning?
7. Is there a custom `token_usage`/`token_use`, and what are the valid values?
8. Which fields are required, optional, or already bound by the endpoint?
9. Does the Orders API accept multi-audience tokens?
10. Do `client_credentials` tokens have a separate policy from user tokens?
11. Does caching have clear TTLs, invalidation, and policy versioning?
12. Is AS downtime guaranteed not to lead to authentication bypass?

## 21. Scenario Exercises

**Scenario A:** The AS returns `active:true`, `aud:["billing-api"]`, `scope:"orders.read"`. Can the Orders API accept it?

**No**, if the `orders-api` audience is required. A matching scope name cannot fix the wrong audience.

**Scenario B:** The AS returns `active:true` and `token_type:"Bearer"`. Can you conclude this is definitely an access token?

**No.** `Bearer` describes the credential/protocol usage type. Token purpose must rely on profile/metadata or introspection endpoint guarantees.

**Scenario C:** The AS has custom `token_usage:"id_token"`. The Orders API only accepts access tokens. Outcome?

**Reject**, even though the token is active and audience/issuer appear valid.

**Scenario D:** The response omits `iss`; a developer assigns `iss = expectedIssuer` before validating. Is that issuer verification?

**No.** You need a trusted source proving the issuer or an alternative endpoint binding, not a self-populated value.

**Scenario E:** The AS guarantees that Orders API introspection credentials return active only for tokens intended for Orders API, yet the response omits `aud`. Is requiring the `aud` field strictly necessary?

**Not under RFC 7662** if the equivalent resource binding has been agreed upon, verified, and tested. However, never assume that when the AS has no such policy.

**Scenario F:** Token metadata is valid, but `SCOPE_orders.read` is missing. Is this an authentication failure or an authorization failure?

The token **can authenticate successfully**, after which HTTP authorization must reject it, usually with 403.

**Scenario G:** A fake `OpaqueTokenIntrospector` returns the right principal and unit tests pass, yet production returns 401 because the introspection client secret is wrong. Why?

Unit tests **do not test the HTTP/credential protocol**. You need integration tests with a mock AS and environment configuration verification.

**Scenario H:** A token authenticated with the right issuer/audience and has `orders.read`, yet the order belongs to another tenant. Should reading be allowed?

**No** if tenant/owner policy forbids it. Introspection does not replace data-level permissions.

---

## Conclusion

When customizing **opaque-token introspection** in a Spring Security Resource Server, start from the **actual metadata contract of the Authorization Server**. `active: true` only confirms token status according to the AS; when required by the contract, the Resource Server must also validate **audience**, **issuer**, and **token purpose**. `token_type: Bearer` **does not mean** `token_usage: access_token`, and `token_type_hint` is only a request hint.

An **`OpaqueTokenIntrospector` decorator** is the right place to combine trusted introspection with metadata validators before producing a principal/authorities. If a required field is missing or wrong, reject; if the issuer does not return that field, replace it only with an **equivalent contracted and tested guarantee**. After authentication, the API must still verify scopes, roles, and actual permissions regarding owner/tenant/resource. Never skip token verification when the AS is unavailable or when metadata fails requirements.
