# Configuring Audience and Proving the API Rejects Tokens Intended Elsewhere

## 1. Why Must a Resource Server Validate the Audience?

A JWT can have a valid signature, be issued by a trusted Authorization Server (AS), and still not be permitted to call the current API.

Suppose a system has two APIs:

- **orders-api** handles orders.
- **billing-api** handles payments.

Both APIs use the same issuer and the same set of signing keys. The AS issues a token for billing:

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "user-42",
  "aud": ["billing-api"],
  "scope": "orders.read billing.pay",
  "iat": 1794729600,
  "exp": 1794730500
}
~~~

Suppose the token has a valid signature and its scope contains `orders.read`. If `orders-api` only validates the signature, issuer, expiration, and scope while ignoring audience, it could accept a token issued for `billing-api`.

This is a **token substitution / cross-resource token acceptance** flaw: a credential issued for resource server A is accepted at resource server B.

**Audience validation answers the question: which resource server was this access token issued for?**

For `orders-api`, the policy can require:

~~~text
iss == https://auth.example.com/
AND aud contains orders-api
AND signature is valid
AND token is within its validity window
AND required scope is present
~~~

These conditions serve different roles:
- **iss** identifies the issuer.
- **aud** identifies the recipient/resource allowed to receive the token.
- **exp/nbf** bounds the validity window.
- **scope/authorities** describes granted permissions.
- **signature** protects the integrity and origin of the claims.

No single condition replaces another.

## 2. What Does Audience Mean in a JWT?

The JWT Registered Claim **aud** identifies the recipients that the JWT is intended for. Its value can be a single string or an array of strings.

Single-audience form:

~~~json
{
  "aud": "orders-api"
}
~~~

Multi-audience form:

~~~json
{
  "aud": ["orders-api", "reporting-api"]
}
~~~

Per the JWT specification, a recipient must identify itself in the audience claim when that claim is present. With the OAuth 2.0 access token profile, the API should require the audience according to the access-token issuer contract; RFC 9068 defines a JWT access token profile with audience.

A Resource Server typically has an expected audience identifier:

~~~text
Expected audience for this API = orders-api
~~~

If a token has `aud` equal to `billing-api`, `orders-api` must reject it, even when the token:
- Has a valid signature.
- Is signed by a key belonging to an issuer that `orders-api` trusts.
- Is not expired.
- Has a scope with the same name as an `orders-api` scope.
- Has a subject representing a valid user.

### An Audience Identifier Can Be a URI or a Resource Name

For example:

~~~json
{
  "aud": ["https://api.example.com/orders"]
}
~~~

Or:

~~~json
{
  "aud": ["urn:shop:orders-api"]
}
~~~

The value must be agreed upon between the AS and RS. If the issuer emits `orders-api` but the RS configures `https://api.example.com/orders`, the two values are not automatically equivalent.

Do not normalize arbitrarily by stripping trailing slashes, changing case, or comparing URLs with ad-hoc rules. Audience matching must follow the identifier contract agreed upon by the AS and the API.

## 3. Audience Differs from Issuer, `client_id`, `azp`, and Scope

The following claims are frequently confused:

| Claim | Meaning | Question answered |
|---|---|---|
| **iss** | Issuer | Who issued the token? |
| **aud** | Audience/recipient | Which resource server is the token intended for? |
| **sub** | Subject | Which subject does the token represent? |
| **client_id** | OAuth client | Which client requested/is associated with the token? |
| **azp** | Authorized party in an OIDC context | Which client is authorized to use the ID token in that context? |
| **scope** | Granted permissions | What permissions were granted to the token? |
| **exp** | Expiration | When does the token expire? |

A web client may call multiple APIs:

~~~text
shop-web
   |
   +---- access token for orders-api
   |
   +---- access token for billing-api
   |
   +---- access token for inventory-api
~~~

Having the same client ID does not mean the access tokens share the same audience.

For example:

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "user-42",
  "client_id": "shop-web",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

This token is intended for `orders-api`. `client_id=shop-web` does not make it usable across every API that `shop-web` can call.

### Scope Does Not Replace Audience

Suppose a token has:

~~~json
{
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

The `orders.read` scope does not turn a billing token into an orders token. The audience is still wrong, so `orders-api` must reject it before evaluating scope-based authorization.

### `azp` Does Not Replace `aud`

In an OIDC ID Token, `azp` can identify the authorized party. A Resource Server must not use `azp` or `client_id` in place of `aud` when validating the recipient of an access token.

## 4. Audience Validation Flow at the Resource Server

~~~mermaid
flowchart TD
    A["HTTP request with Bearer JWT"] --> B["Parse JWT"]
    B --> C["Select trusted verification key"]
    C --> D{"Signature valid?"}
    D -->|No| X["Reject: 401 invalid_token"]
    D -->|Yes| E["Validate issuer"]
    E --> F{"Expected issuer?"}
    F -->|No| X
    F -->|Yes| G["Validate timestamps and token profile"]
    G --> H{"Audience contains this API?"}
    H -->|No| X
    H -->|Yes| I["Create authenticated principal"]
    I --> J["Check scope and domain permissions"]
    J --> K{"Authorized?"}
    K -->|No| Y["Reject: 403"]
    K -->|Yes| L["Invoke API"]
~~~

Audience validation is part of **authentication/token validation**. A token intended for another API is not an authenticated principal lacking a scope; it is invalid for the current resource server.

Some implementations may run validators in a different order or aggregate errors into a combined result. What matters is that all required validations succeed before the Resource Server creates an `Authentication`.

## 5. Configuring Audience at the Authorization Server

A Resource Server can only validate audience properly if the AS issues access tokens with a clear audience contract.

A token endpoint might issue a token for `orders-api`:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_CREDENTIALS

grant_type=client_credentials&scope=orders.read&resource=orders-api
~~~

Here `resource` is an example of how a client indicates the target resource depending on AS support. OAuth 2.0 Resource Indicators are standardized in RFC 8707; not every AS supports the same request parameter or maps it to `aud` in the same way.

The AS can:
- Determine the audience based on a resource indicator.
- Use client registration/resource mapping.
- Use an audience mapper or token customization.
- Issue separate tokens per API.
- Enforce policies by grant, client, user, and requested resource.

Crucially, the client must not be able to modify the `aud` claim after the token is signed. Audience is a claim issued by the AS and protected by the signature.

### Do Not Let Clients Arbitrarily Choose Any Audience by Default

If the AS allows a client to send `resource=orders-api`, the AS must still verify that the client/grant is authorized to request a token for that resource. A resource indicator is a request input, not a self-granted permission.

### Avoid Issuing a Single Token for All APIs

A token containing:

~~~json
{
  "aud": [
    "orders-api",
    "billing-api",
    "inventory-api",
    "admin-api"
  ]
}
~~~

may be valid under JWT semantics if those recipients are intentionally specified. However, a token shared across many resources increases the blast radius if leaked and easily creates authorization coupling.

If APIs have different trust boundaries, data, or permissions, prefer narrow per-resource token audiences. Only use multi-audience when the AS and all recipients have an explicit policy.

## 6. Designing Audience Identifiers Across Multiple APIs

One naming scheme could be:

| Resource Server | Audience identifier |
|---|---|
| Orders API | orders-api |
| Billing API | billing-api |
| Inventory API | inventory-api |
| Reporting API | reporting-api |
| Admin API | admin-api |

Or using URI identifiers:

| Resource Server | Audience identifier |
|---|---|
| Orders API | https://api.example.com/orders |
| Billing API | https://api.example.com/billing |
| Inventory API | https://api.example.com/inventory |

Choose one convention and keep it stable. Decide:
- Does the audience distinguish dev/staging/prod environments?
- Does each tenant have a separate audience, or is tenant an authorization dimension inside the API?
- Does the API version change the audience?
- Do internal services have different audiences from public APIs?
- Do the gateway and downstream services receive the same token, or does each hop get its own token?
- Does token exchange produce a new audience?
- When an API is renamed or migrated to a new domain, what are the overlap and migration policies?

### Audience Does Not Have to Be a Public URL

An audience identifier can be a URI or an opaque string. There is no requirement for an endpoint to be public or reachable at that URI. What is necessary is that the issuer and recipient understand the same identifier.

### Do Not Use Audience to Encode Every Authorization Detail

Do not create a separate audience per order ID or per granular action. Audience defines the recipient/resource boundary; scopes, roles, tenant membership, and object policies handle fine-grained permissions.

## 7. Configuring Spring Boot Resource Server with `audiences`

On Spring Boot versions that support the `audiences` property, you can configure:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/
          audiences:
            - orders-api
~~~

Meaning:
- `issuer-uri` identifies the trusted issuer and enables discovery/JWK configuration.
- `audiences` lists the resource identifiers the JWT must be issued for.
- JWTs with the wrong issuer or without the expected audience are rejected.
- Timestamp/signature validations continue to be enforced.

Check your project's Spring Boot/Spring Security version because property binding and APIs may differ across versions. If your current version does not support the `audiences` property, you can configure `JwtDecoder`/`ReactiveJwtDecoder` with a custom validator.

Do not merely decode the JWT in a controller to compare `aud`. Validation must run in the Resource Server authentication pipeline so tokens with the wrong audience are rejected before reaching any application handler.

### `SecurityWebFilterChain`

The filter chain configuration still needs to declare the Resource Server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class OrdersApiSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

The audience policy is enforced by the configured decoder/validators. The filter chain above does not create an audience validator on its own if the decoder is misconfigured without one.

## 8. Custom Audience Validator in WebFlux

When explicit control over the expected audience is needed, attach a validator to `NimbusReactiveJwtDecoder`.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;

@Configuration
public class OrdersJwtDecoderConfiguration {

    private static final String ISSUER =
            "https://auth.example.com/";

    private static final String AUDIENCE =
            "orders-api";

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withIssuerLocation(ISSUER)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        OAuth2TokenValidator<Jwt> issuerValidator =
                new JwtIssuerValidator(ISSUER);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            List<String> audiences = jwt.getAudience();

            if (audiences != null && audiences.contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Token is not intended for this resource server",
                            null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        new JwtTimestampValidator(),
                        issuerValidator,
                        audienceValidator));

        return decoder;
    }
}
~~~

Explanation:
- `withIssuerLocation` configures trusted issuer metadata/JWK discovery.
- `jwsAlgorithm` restricts accepted signing algorithms per policy.
- `JwtIssuerValidator` validates the issuer.
- `JwtTimestampValidator` validates `exp`/`nbf` using the implementation's default clock skew.
- `audienceValidator` requires `orders-api` to appear in `aud`.
- `DelegatingOAuth2TokenValidator` requires all validators to succeed.

**`setJwtValidator` replaces the existing validator set.** When configuring it manually, you must retain timestamp, issuer, and any other validators the application requires. Do not set only an audience validator and accidentally drop `exp`/`nbf` checks.

The example above uses exact string matching for the audience. If the API uses a URI identifier, set `AUDIENCE` to the exact URI issued by the AS.

### Add a Required-Claim Policy When Required by the Profile

Generic JWTs do not mandate that every registered claim be present. If the API uses the OAuth JWT access token profile or a custom contract requiring `aud`/`exp`/`iat`, the validator must enforce required claims. The audience validator above already rejects when `aud` is missing or lacks the expected string; the timestamp validator checks timestamps that are present, while requiring `exp` needs an explicit policy based on profile/version.

## 9. Servlet Resource Server Using `JwtDecoder`

In the Servlet stack, the idea is the same, except the decoder type is `JwtDecoder`:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;

@Configuration
public class ServletOrdersDecoderConfiguration {

    private static final String ISSUER =
            "https://auth.example.com/";

    private static final String AUDIENCE =
            "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            List<String> audiences = jwt.getAudience();

            if (audiences != null && audiences.contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Token is not intended for this resource server",
                            null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        new JwtTimestampValidator(),
                        new JwtIssuerValidator(ISSUER),
                        audienceValidator));

        return decoder;
    }
}
~~~

This is a Servlet decoder configuration; it does not use `ReactiveJwtDecoder`. Both stacks must retain all required validators.

## 10. Selecting Audience Per API Instead of One Overly Broad Shared Decoder

If a deployment serves multiple resource servers or multiple API zones, each zone needs its own audience policy.

~~~text
/orders/**
  expected aud = orders-api

/billing/**
  expected aud = billing-api

/inventory/**
  expected aud = inventory-api
~~~

A decoder using an overly broad list of expected audiences:

~~~text
allowedAudiences = {
  orders-api,
  billing-api,
  inventory-api
}
~~~

can allow an orders endpoint to accept a billing token if code only checks whether `aud` belongs to the shared set. This is rarely the intended behavior.

Choose one of:
- A dedicated Resource Server/decoder per trust boundary; or
- A resolver that selects the `AuthenticationManager`/decoder by route prior to authentication; or
- An intentional multi-audience policy for an API gateway that genuinely acts as a shared recipient.

Do not use a single global validator that accepts every audience just because the application hosts multiple APIs.

### Route Selection Does Not Replace Token Validation

If the `/orders` path selects the orders decoder, that decoder must still verify the signature against the trusted issuer, exact issuer, `orders-api` audience, `exp`/`nbf`, token type/profile, and other required claims.

Do not use a caller-chosen path to expand trust sources.

## 11. String and Array Audience Forms

A JWT audience can be a string or an array per RFC 7519. Spring Security's `Jwt.getAudience()` exposes a list of audiences for the application to inspect.

For example:

~~~json
{
  "aud": "orders-api"
}
~~~

and:

~~~json
{
  "aud": ["orders-api", "reporting-api"]
}
~~~

Both can contain `orders-api` under a membership-check policy.

A validator following a recipient membership policy:

~~~java
boolean intendedForOrders =
        jwt.getAudience() != null
        && jwt.getAudience().contains("orders-api");
~~~

Do not write:

~~~java
jwt.getAudience().get(0).equals("orders-api")
~~~

because array order is not a contract for identifying a unique audience. The API may appear as the second or later element.

### When Is a Strict Single Audience Needed?

An organization may require a token to be intended for exactly one API:

~~~java
List<String> aud = jwt.getAudience();

boolean exactAudience =
        aud != null
        && aud.size() == 1
        && aud.contains("orders-api");
~~~

This is stricter than a standard membership check. Apply it only if the AS contract requires a single audience. If the issuer intentionally issues multi-audience tokens, a strict-single policy will reject those tokens.

### Audience Set Policy

An API may allow a controlled set of audiences:

~~~text
orders-api accepts:
  orders-api
  orders-api-v2 (during migration)
~~~

This should have a migration window, owner, and sunset plan. Do not put every audience in the system into a global allow-list.

## 12. Audience Validation Must Run After the JWT Is Verified

A JWT payload is typically just Base64URL-encoded JSON. Anyone can craft a self-asserted payload string:

~~~json
{
  "iss": "https://auth.example.com/",
  "aud": ["orders-api"],
  "sub": "admin"
}
~~~

If you simply decode the payload and check `aud`, an attacker can self-declare `orders-api`.

Correct flow:

~~~text
Receive compact JWT
  |
  v
Verify JWS signature using trusted key
  |
  v
Validate trusted issuer
  |
  v
Validate audience and time claims
  |
  v
Create Authentication
~~~

The audience claim becomes a trusted assertion only after the token signature is verified with a trusted issuer's key and required validations succeed.

Do not:
- Build a JWKS URL from an unverified `iss`.
- Fetch arbitrary `jku`/`x5u` from the JOSE header.
- Use an unverified `aud` to select permissions.
- Map tenant or admin roles from the payload before signature verification.
- Fall back to another provider when a token fails signature verification.

Certain claims may be used as routing hints in a safely designed resolver, but the final outcome must still be verified against pre-configured trust settings.

## 13. Audience Validation and Scope Authorization Run in Two Stages

Consider two tokens:

Token A:

~~~json
{
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Token B:

~~~json
{
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

Token A:
- Correct audience.
- Can authenticate if signature/issuer/time/profile are valid.
- GET orders can be authorized.

Token B:
- Wrong audience.
- Authentication must fail at `orders-api`.
- Do not evaluate scope to rescue the token.
- The API returns `401 invalid_token` per Bearer error semantics.

Token C:

~~~json
{
  "aud": ["orders-api"],
  "scope": "billing.pay"
}
~~~

Token C:
- Correct audience.
- Authentication can succeed.
- If the endpoint requires `orders.read`, authorization denies the request, typically with `403`.

| Token | Signature/issuer/time | Audience | Scope | Result |
|---|---|---|---|---|
| A | Valid | orders-api | orders.read | Authentication passes; GET may be permitted |
| B | Valid | billing-api | orders.read | 401 invalid_token |
| C | Valid | orders-api | billing.pay | Authentication passes; `orders.read` returns 403 |
| D | Invalid signature | orders-api | orders.read | 401 invalid_token |
| E | Valid | orders-api | orders.write | May pass if endpoint policy requires write |

**A wrong audience is an authentication failure; a missing scope is an authorization failure.**

## 14. Audience with Opaque Token Introspection

An opaque access token has no payload for the Resource Server to inspect `aud` directly. The Resource Server sends the token to a trusted introspection endpoint per RFC 7662.

The response may contain:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "shop-web",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1794730500
}
~~~

If the introspection response contains `aud`, the Resource Server must ensure the token is intended for the current resource per the contract. An AS might already bind the token to a resource upon issuance and only return `active=true` for an authorized resource; the implementation must understand that behavior.

If the RS performs an additional audience check itself, it must validate claims from the introspection response after verifying that the response came from the trusted AS over TLS with proper client authentication.

### `active=true` Does Not Automatically Mean Correct Audience

A token can be active at the AS while intended for `billing-api`. If the introspection endpoint only returns a generic active status, `orders-api` must still enforce resource binding per contract.

### Do Not Infer Audience from `client_id`

An opaque response with `client_id=shop-web` does not mean the token is intended for `orders-api`. Client and resource are two distinct entities.

## 15. Resource Indicators and Audience Issuance

RFC 8707 defines OAuth 2.0 Resource Indicators. A client can specify the resource it wants the access token for, depending on AS support.

Illustrative example:

~~~http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=...&
redirect_uri=https%3A%2F%2Fshop.example.com%2Fcallback&
resource=https%3A%2F%2Fapi.example.com%2Forders
~~~

The AS must verify that the client/grant is permitted to request a token for that resource. The AS can issue a JWT with the corresponding `aud`.

Not every AS uses this exact URL/resource indicator or maps it 1:1 into `aud`. Check vendor documentation and the token contract.

### Token Exchange

In token exchange, the subject token may be intended for service A, while the exchanged token is issued for service B with a different audience:

~~~text
User token for gateway
      |
      v
Trusted token exchange
      |
      v
Downstream token for orders-api
~~~

Downstream services should receive tokens issued with their own audience. Do not forward a bearer token intended for the gateway verbatim to all downstream APIs unless the contract allows it.

## 16. Audience and the API Gateway

A gateway can act as a resource server at the edge and call downstream APIs. You must decide which token is used at each hop:

~~~text
Client
  |
  | token aud = gateway-api
  v
API Gateway
  |
  | token aud = orders-api
  v
Orders Service
~~~

Options:
- The client requests a dedicated token for the downstream resource and sends it through the gateway per the defined architecture.
- The gateway uses token exchange to obtain a token with audience `orders-api`.
- The gateway uses its own service credentials to call the backend while passing protected actor context per contract.
- The gateway is the sole recipient if the backend accepts identity assertions only from the gateway over a trusted channel.

Do not assume a token with `aud=gateway-api` is valid for `orders-api`. The gateway can validate its token, but downstream services still require an appropriate credential/identity trust contract.

### Do Not Confuse Audience with Network Destination

Making an HTTP call to host `orders.example.com` does not automatically give a token `aud=orders-api`. Network routing and token recipient are two separate layers.

## 17. Multi-Audience Tokens: Accept Only When Intentional

JWT allows `aud` to be an array. For example:

~~~json
{
  "aud": [
    "orders-api",
    "reporting-api"
  ]
}
~~~

If `orders-api` is an explicitly designated recipient, a membership check can pass. However, multi-audience tokens come with trade-offs:
- The token can be used across multiple recipients.
- A single token leak has a wider blast radius.
- Scopes may be interpreted differently across APIs.
- APIs may have different trust levels.
- Revocation/incident response impacts multiple services.
- It is harder to distinguish whether a token was issued for one API or a group of APIs if the contract is vague.

If using multi-audience:
1. Enumerate explicit recipients.
2. Each API accepts only its own audience.
3. Each API still enforces its own scope/tenant/object authorization.
4. Do not share one broad allow-list across all APIs.
5. Audit and test each resource individually.
6. Establish a revocation/migration policy for old audiences.

## 18. Audience Migration When Changing an API Identifier

Suppose `orders-api` changes its audience from `orders-api` to `urn:shop:orders:v2`.

~~~text
Phase 1:
  AS emits old audience.
  RS accepts old audience.

Phase 2:
  AS can issue new audience for migrated clients.
  RS accepts old + new during explicit overlap.

Phase 3:
  Monitor old audience usage.
  Migrate remaining clients.

Phase 4:
  AS stops issuing old audience.
  RS removes old audience after token lifetime + skew/propagation window.
~~~

During the overlap, the validator can accept both identifiers:

~~~java
Set<String> allowedDuringMigration =
        Set.of("orders-api", "urn:shop:orders:v2");

OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
    boolean accepted = jwt.getAudience() != null
            && jwt.getAudience().stream()
                    .anyMatch(allowedDuringMigration::contains);

    return accepted
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Audience is not allowed",
                            null));
};
~~~

This is a single API's migration allow-list, not an allow-list for all APIs. Maintain a clear sunset date, metrics, and owner.

Do not use audience wildcards, arbitrary prefix matching, URL host substring matching, or accept tokens missing `aud` by default.

## 19. Unit Testing the Validator Independently

You can test the audience validator with a `Jwt` object:

~~~java
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.assertj.core.api.Assertions.assertThat;

class AudienceValidatorTests {

    private final OAuth2TokenValidator<Jwt> validator =
            new OrdersAudienceValidator("orders-api");

    @Test
    void acceptsExpectedAudience() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "RS256")
                .claim("aud", List.of("orders-api"))
                .issuedAt(Instant.now())
                .expiresAt(Instant.now().plusSeconds(300))
                .build();

        assertThat(validator.validate(jwt).hasErrors()).isFalse();
    }

    @Test
    void rejectsTokenForAnotherApi() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "RS256")
                .claim("aud", List.of("billing-api"))
                .issuedAt(Instant.now())
                .expiresAt(Instant.now().plusSeconds(300))
                .build();

        assertThat(validator.validate(jwt).hasErrors()).isTrue();
    }

    @Test
    void rejectsMissingAudience() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "RS256")
                .issuedAt(Instant.now())
                .expiresAt(Instant.now().plusSeconds(300))
                .build();

        assertThat(validator.validate(jwt).hasErrors()).isTrue();
    }
}
~~~

Validator implementation:

~~~java
public final class OrdersAudienceValidator
        implements OAuth2TokenValidator<Jwt> {

    private final String expectedAudience;

    public OrdersAudienceValidator(String expectedAudience) {
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        List<String> audiences = jwt.getAudience();

        if (audiences != null && audiences.contains(expectedAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                        "invalid_token",
                        "Token is not intended for this API",
                        null));
    }
}
~~~

This is a unit test for claim-matching logic. Because `Jwt` is constructed directly, there is no real signature; the test does not prove the decoder verifies signatures, issuers, or JWK sources.

## 20. Proving the API Rejects Tokens Intended Elsewhere

A test that only calls the audience validator or uses `mockJwt()` is not enough to prove the entire Resource Server pipeline.

A negative integration test needs:
1. A JWT signed with a test private key.
2. The Resource Server trusting the corresponding public key.
3. A valid JWT issuer.
4. Valid JWT timestamps.
5. The JWT having the scope required by the endpoint.
6. The JWT audience set to `billing-api`.
7. A request sending the token to `orders-api`.
8. The decoder running the real validators.
9. The response being rejected before reaching the controller.

This rules out the possibility that the test failed merely because of a bad signature or an expired token.

### Test Token with Wrong Audience While Everything Else Is Valid

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "user-42",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "iat": 1794729600,
  "nbf": 1794729600,
  "exp": 1794730500
}
~~~

Control test token with the correct audience:

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1794729600,
  "nbf": 1794729600,
  "exp": 1794730500
}
~~~

Both tokens must share the same issuer, signing key, algorithm, timestamps, and scope. Change only the audience so the test isolates the exact variable under verification.

## 21. Generating Signed JWTs in Integration Tests

You can use Nimbus JOSE + JWT to create compact JWS tokens for tests. Illustrative helper example:

~~~java
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import java.security.interfaces.RSAPrivateKey;
import java.time.Instant;
import java.util.Date;
import java.util.List;

public String signedAccessToken(
        RSAPrivateKey privateKey,
        String issuer,
        List<String> audience,
        String scope) throws JOSEException {

    Instant now = Instant.now();

    JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("user-42")
            .audience(audience)
            .issueTime(Date.from(now))
            .notBeforeTime(Date.from(now.minusSeconds(1)))
            .expirationTime(Date.from(now.plusSeconds(300)))
            .claim("scope", scope)
            .build();

    SignedJWT jwt = new SignedJWT(
            new JWSHeader.Builder(JWSAlgorithm.RS256)
                    .keyID("test-signing-key")
                    .build(),
            claims);

    jwt.sign(new RSASSASigner(privateKey));
    return jwt.serialize();
}
~~~

Test fixtures should generate a dedicated RSA key pair. The private key is only used in tests to sign tokens; the Resource Server decoder is configured only with the corresponding public key/JWKS.

Do not use production private keys in tests. Do not commit real private keys or real access tokens to the repository.

## 22. `WebTestClient` Integration Test with a Real Decoder

A WebFlux test can invoke the protected route through the filter chain:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AudienceIntegrationTests {

    @Autowired
    WebTestClient client;

    @Autowired
    TestTokenFactory tokens;

    @Test
    void rejectsBillingTokenAtOrdersApi() throws Exception {
        String token = tokens.signedToken(
                List.of("billing-api"),
                "orders.read");

        client.get()
                .uri("/api/orders")
                .headers(headers -> headers.setBearerAuth(token))
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader()
                    .valueMatches(
                            "WWW-Authenticate",
                            ".*invalid_token.*");
    }

    @Test
    void acceptsOrdersTokenAtOrdersApi() throws Exception {
        String token = tokens.signedToken(
                List.of("orders-api"),
                "orders.read");

        client.get()
                .uri("/api/orders")
                .headers(headers -> headers.setBearerAuth(token))
                .exchange()
                .expectStatus().is2xxSuccessful();
    }
}
~~~

Test assumptions:
- The test application has a real `SecurityWebFilterChain`.
- `ReactiveJwtDecoder` uses the test public key or a test JWKS endpoint.
- The issuer validator is configured.
- The audience validator requires `orders-api`.
- The token factory signs tokens with the matching test private key.
- The endpoint returns 2xx when the token is valid and has sufficient scope.

The test must not use `mockJwt()` in these two cases because `mockJwt` fabricates an `Authentication` and can bypass the decoder/audience validator.

### Assert the Controller Is Not Invoked

You can mock a service/handler dependency and verify it is never called when the audience is wrong:

~~~java
verifyNoInteractions(ordersService);
~~~

Complete the `WebTestClient` exchange before verifying. This proves the request was blocked before the business layer, rather than merely happening to end in a 401 status.

## 23. Distinguishing Audience Failures from Scope Failures in Tests

There should be three independent tests:

| Test | Audience | Scope | Result |
|---|---|---|---|
| Token for the right resource | orders-api | orders.read | GET is allowed |
| Token intended for another API | billing-api | orders.read | 401 invalid_token |
| Token for the right resource, missing scope | orders-api | billing.pay | 403 or authorization denial |

The wrong-audience token needs the correct scope to prove the API rejects it due to a resource mismatch.

The right-audience token lacking scope needs a valid signature, issuer, and timestamps to prove authentication passes and authorization fails.

Do not write a single test with a token that has both the wrong audience and missing scope and conclude the 401 was caused by audience. That test does not isolate the cause.

## 24. Using `mockJwt()` for Its Intended Purpose

Spring Security Test supports `mockJwt()` in WebFlux to test authorization rules.

Example:

~~~java
client.mutateWith(mockJwt().jwt(jwt ->
                jwt.claim("aud", List.of("orders-api")))
        .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().is2xxSuccessful();
~~~

This is an authorization test after mocking `Authentication`. It does not prove:
- The JWT signature is valid.
- The issuer was verified.
- The audience validator ran.
- The JWKS endpoint was called.
- Timestamp claims were validated.

Use `mockJwt` for permission mapping/route access; use signed JWTs through a real decoder to prove audience enforcement.

## 25. Testing Missing, Malformed, and Multiple Audience Tokens

Negative tests should include:

| Token claim | Policy | Result |
|---|---|---|
| aud = orders-api | Orders API | Passes audience |
| aud = [orders-api, reporting-api] | Membership policy | Passes if multi-audience is allowed |
| aud = billing-api | Orders API | Rejected |
| aud missing | API requires aud | Rejected |
| aud = [] | API requires aud | Rejected |
| aud = [""] | API requires orders-api | Rejected |
| aud = ["orders-api-v2"] | Expected orders-api | Rejected unless in migration allow-list |
| aud = ["ORDERS-API"] | Expected lowercase exact ID | Rejected if identifier is case-sensitive |
| aud = [billing-api, inventory-api] | Orders API | Rejected |
| aud malformed type | JWT parser/claim validation | Rejected |

JWT parsers typically validate claim types per the library; if a claim is malformed, the token is not converted into a valid principal.

### Duplicate Audience Values

A JWT array might be issued with duplicate strings due to an issuer bug. If the contract requires unique audience values, add a validator/policy or fix the issuer. Do not rely on the first index.

## 26. Testing Multi-Issuer and Audience Independently

An API can trust multiple issuers while accepting only its own audience:

~~~text
Trusted issuers:
  https://auth-a.example.com/
  https://auth-b.example.com/

Orders API audience:
  orders-api
~~~

Policy:

~~~text
(iss == auth-a AND aud contains orders-api)
OR
(iss == auth-b AND aud contains orders-api)
~~~

A token from `auth-a` with `aud=billing-api` must be rejected. A token from `auth-b` with `aud=orders-api` can pass if issuer B is authorized to issue access tokens for `orders-api` and other claims are valid.

Do not let issuer A accept `billing-api` merely because issuer B issues `orders-api` tokens. The issuer allow-list and audience allow-list are two independent control dimensions.

### Namespacing Audiences by Issuer

If each issuer has its own naming conventions, configure explicit mappings:

~~~text
issuer A:
  orders resource = urn:auth-a:orders

issuer B:
  orders resource = orders-api
~~~

Do not infer the audience from the issuer URL or tenant name. Use trusted configuration.

## 27. Frontend Tokens Are Not API Tokens

An OIDC ID token typically has the relying party's `client_id` as its audience:

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "user-42",
  "aud": ["shop-web"],
  "exp": 1794730500
}
~~~

An ID token is used by the client to understand the user's authentication outcome. A Resource Server API must not accept it as an access token merely because:
- Same issuer.
- Same signing key.
- Same `sub`.
- Valid signature.
- Contains a claim named `scope` added by the issuer.

An access token for `orders-api` must have the proper token purpose/profile and audience. If using RFC 9068, you can check `typ=at+jwt` per the profile; do not treat ID tokens and access tokens as the same kind of credential.

### Token Type and Audience Are Two Separate Checks

A JWT with `aud=orders-api` but the wrong `typ`/profile can still be rejected. Conversely, `typ=at+jwt` does not rescue a token with `aud=billing-api`.

## 28. Audience in Service-to-Service Client Credentials

With client credentials, the token represents a client application rather than a user. The AS may issue:

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "inventory-worker",
  "client_id": "inventory-worker",
  "aud": ["orders-api"],
  "scope": "orders.sync"
}
~~~

The Orders API needs to:
- Verify issuer/signature/time.
- Require audience `orders-api`.
- Identify the actor as a machine client per the token profile.
- Check the `orders.sync` scope.
- Apply resource/tenant policies for the client identity.

Do not accept a token for every API just because `client_id` is registered in the AS. Client credentials tokens still require audience/resource binding.

## 29. Audience and Tenant in Multi-Tenant APIs

A SaaS API may use the same `orders-api` audience across all tenants:

~~~json
{
  "aud": ["orders-api"],
  "tenant_id": "blue",
  "scope": "orders.read"
}
~~~

Audience states that the token is intended for the Orders API. `tenant_id`/membership states which tenant the actor can operate in. Object policies decide whether the actor can access a specific order.

Do not use tenant ID as the audience by default for all tenants unless the architecture requires a separate resource server per tenant. Conversely, if each tenant has an independent API endpoint/resource boundary, it may have its own audience per contract.

Layers to keep independent:
- API recipient.
- Issuer.
- Actor identity.
- Tenant membership.
- Scope/authority.
- Object ownership/business policy.

## 30. HTTP Response on Wrong Audience

A token with the wrong audience is invalid for the Resource Server. For Bearer tokens, the response is typically:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/problem+json
~~~

Do not return `403 insufficient_scope` because the principal has not been validly authenticated for this API.

Do not disclose:
- That the token's actual audience was `billing-api`.
- The list of audiences trusted by the API.
- The internal issuer.
- JWT claims.
- Signing key or `kid`.
- The token string.

A generic body:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "code": "invalid_token",
  "detail": "A valid access token for this resource is required"
}
~~~

`WWW-Authenticate` preserves Bearer protocol semantics; the JSON body is just a representation for the client.

## 31. Logging and Metrics for Audience Mismatches

Safe logs may record:

~~~text
requestId = req-421
resourceServer = orders-api
configuredIssuerId = shop-auth
authenticationOutcome = failure
failureCategory = audience_mismatch
httpStatus = 401
~~~

Do not log raw tokens or full claims. The audience in an unverified token should not be logged as a trusted resource identity; if diagnostics are needed, log a sanitized category or only the expected resource ID.

Metrics to track:
- `audience_validation_success_total`.
- `audience_validation_failure_total`.
- `missing_audience_total`.
- `issuer_validation_failure_total`.
- `invalid_signature_total`.
- `resource_server_id` (configured, bounded label).
- `issuer_id` (configured identifier).

Do not use arbitrary raw audience strings from tokens as metric labels because they can cause high cardinality or be attacker-controlled.

### Alerting on Mismatch Rates

A spike in audience mismatches may indicate:
- Clients calling the wrong token endpoint/resource.
- An API deployment changed its audience while clients have not migrated yet.
- An AS audience mapper malfunction.
- A gateway forwarding a token intended for itself downstream.
- A token substitution attempt.
- Mixed dev/staging/prod environment configs.

Do not automatically open up the audience allow-list just to silence alerts. Find the true issuer/client/resource configuration issue.

## 32. Common Anti-Patterns

| Anti-pattern | Risk | Correct approach |
|---|---|---|
| Checking only signature and issuer | Tokens for other APIs can be accepted | Validate `aud` |
| Using `client_id` instead of `aud` | Confusing caller with recipient | Validate resource audience |
| Using `azp` instead of `aud` | Confusing OIDC authorized party with API recipient | Validate access-token audience |
| Ignoring `aud` because scope matches | Cross-resource token substitution | Both `aud` and scope are required |
| Checking only `aud[0]` | Missing other audiences or order dependency | Membership check |
| Accepting all audiences | Overly broad trust boundary | Per-API allow-list |
| Accepting missing `aud` | Token not bound to resource | Reject if required by API contract |
| Decoding payload before signature and authorizing | Attacker self-asserts `aud` | Validate in the decoder pipeline |
| Using `mockJwt` to prove audience validator | Test bypasses decoder | Signed token + real decoder |
| Returning 403 on wrong `aud` | Confusing authentication with authorization | `401 invalid_token` |
| Using audience wildcards/prefixes | Accepting unintended resources | Exact identifier matching |
| Using one decoder for all APIs with a union allow-list | Billing token can enter Orders API | Separate decoder/manager policy |
| Removing old audience immediately on identifier change | Migrating clients break | Time-bounded overlap |
| Not testing multi-value audience | Bugs when `aud` is an array | Test string/array contract |
| Gateway forwarding wrong-`aud` token to service | Downstream trust confusion | Token exchange/downstream audience |
| Using ID token to call Resource Server | Cross-JWT confusion | Access token profile + `aud` |
| Logging full token on mismatch | Credential leakage | Sanitized logs |

## 33. Pre-Deployment Checklist

**Authorization Server**
1. Does the AS issue access tokens with the audience matching the resource?
2. Is the client permitted to request that audience?
3. Is the resource indicator/client registration mapping clear?
4. Do tokens for other APIs have different audiences?
5. Are ID tokens and access tokens issued with distinct purposes?
6. Is multi-audience genuinely necessary?

**Resource Server**
1. What is the exact expected audience identifier?
2. Does the decoder validate issuer and audience together?
3. Are timestamp and signature validators retained when a custom validator is added?
4. Is a missing audience rejected?
5. Is the multi-audience policy membership or strict single?
6. Is token type/profile checked when required by the contract?
7. Does opaque introspection enforce resource/audience binding?
8. Does each API have its own policy?

**Testing**
1. A token with the right audience and right scope is accepted.
2. A token with the wrong audience but valid signature/issuer/time/scope is rejected.
3. A token missing audience is rejected.
4. Array-formatted token audiences are handled properly.
5. A token with the right audience but missing scope returns 403.
6. A token with an invalid signature is rejected.
7. A token with the wrong issuer is rejected.
8. Controller/service is not invoked when audience is wrong.
9. `mockJwt` is not used as a substitute for signed-token integration tests.
10. Multi-issuer and gateway/downstream paths are tested separately.

## 34. Summary

~~~text
AS issues access token for billing-api
              |
              v
Client sends token to orders-api
              |
              v
Orders Resource Server
  verify signature
  validate trusted issuer
  validate timestamps/profile
  require aud contains orders-api
              |
       +------+------+
       |             |
       v             v
  aud matches     aud mismatch
       |             |
       v             v
 Authentication   401 invalid_token
       |
       v
 Check scope / tenant / object policy
       |
   +---+---+
   |       |
   v       v
 Allow   403 if authorization denied
~~~

Key principles to remember:

1. **Audience identifies the resource server intended to receive the token**.
2. **Issuer and audience are two independent checks**: a valid issuer does not mean the right recipient.
3. **`client_id`, `azp`, and `scope` do not replace `aud`**.
4. Audience can be a string or an array; check membership per contract without depending on the first element.
5. The Resource Server must validate audience in the decoder/validation pipeline after signature verification.
6. A token intended for another API must be rejected even if signature, issuer, timestamps, and scope are all valid.
7. A wrong audience is an authentication failure, typically returning `401 invalid_token`; a right audience lacking scope typically returns `403`.
8. Each API needs its own expected audience; do not use an overly broad global allow-list.
9. Multi-audience should only be used intentionally with clear policies for all recipients.
10. Gateways/downstream services need hop-appropriate token audiences or a dedicated trusted identity contract.
11. Use signed JWTs through a real decoder and `WebTestClient` to prove the API rejects wrong-audience tokens.
12. `mockJwt()` is suitable for authorization tests, but does not prove signature/audience validation ran.

**Conclusion:** Configuring audience is how a Resource Server confirms an access token was issued for the right API. A token signed by a trusted issuer must still be rejected if its audience does not include the current resource. To prove this, generate two test JWTs identical in issuer, key, timestamps, and scope, differing only in `aud`; send them through a real `SecurityWebFilterChain` and verify the valid token is accepted while the token intended for another API receives `401` before any business handler executes.

## 35. References

- **Spring Security Reference — Reactive OAuth 2.0 Resource Server JWT:** `ReactiveJwtDecoder`, issuer, and audience validation. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server JWT:** `JwtDecoder`, issuer, and audience validation. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Boot Reference — OAuth2 Resource Server:** JWT issuer, JWK Set URI, and `audiences` properties by version. https://docs.spring.io/spring-boot/reference/security/oauth2.html
- **Spring Security API — Jwt:** audience claim accessor and JWT claim model. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/Jwt.html
- **Spring Security API — JwtValidators:** default issuer/timestamp validator composition. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html
- **Spring Security Reference — Reactive Testing:** `WebTestClient` and mock JWT. https://docs.spring.io/spring-security/reference/reactive/test/web/index.html
- **RFC 7519 — JSON Web Token:** `aud` claim, issuer, and registered claims. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** JWT access-token profile and audience requirements. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 8707 — Resource Indicators for OAuth 2.0:** `resource` parameter and resource-specific tokens. https://www.rfc-editor.org/rfc/rfc8707
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** `invalid_token` and Bearer error response. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** issuer metadata and JWKS discovery. https://www.rfc-editor.org/rfc/rfc8414
- **OpenID Connect Core 1.0:** ID Token audience and authorized party semantics. https://openid.net/specs/openid-connect-core-1_0.html
- **Nimbus JOSE + JWT Documentation:** JWS signing and verification APIs for test fixtures. https://connect2id.com/products/nimbus-jose-jwt
