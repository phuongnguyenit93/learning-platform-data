# Testing Tokens, Scopes, and Expiration Without Putting Sensitive Data in Examples

With OAuth2 and OpenID Connect (OIDC), API testing is not merely sending a bearer token and confirming HTTP 200. You must verify that the token is of the right type, has the right issuer and audience, is still valid, carries required scopes, and is handled safely when expired or rejected. At the same time, springdoc-openapi documentation must accurately describe the authentication mechanism enforced by the server.

Examples in documentation, test sources, and logs must use dummy data. Never put real access tokens, refresh tokens, ID tokens, client secrets, real API keys, or token contents captured from production into Markdown, @ExampleObject, fixtures, snapshots, or Swagger UI screenshots.

## 1. Distinguishing token types before testing

OAuth2 and OIDC can use several types of tokens, yet they serve different purposes:

| Type | Purpose | Where Commonly Used |
| --- | --- | --- |
| Access token | Grants access to a resource server per audience and scope/authority | Authorization: Bearer ... header when calling APIs |
| Refresh token | Requests a new access token without requiring the user to log in again | Sent to the authorization server's token endpoint |
| ID token | Confirms user authentication results in OIDC | Checked by the OIDC client after login |

Do not use an ID token in place of an access token when calling a resource API. An ID token has an audience intended for the OIDC client; an access token has an audience and permissions intended for the resource server. Both may be JWTs, yet they do not share the same purpose or validation rules.

A refresh token must also never be sent to business APIs as a bearer access token. It is a credential capable of minting new access tokens, so it must be strictly protected and sent only to the authorization server per configured flow.

## 2. Verification layers of an access token

A resource server typically needs to verify multiple conditions:

| Condition | Meaning | Example Failure Scenario |
| --- | --- | --- |
| Signature | Token is signed by a trusted key and accepted algorithm | Invalid signature or untrusted key |
| Issuer (iss) | Token was issued by the expected authorization server | Token comes from a different issuer |
| Audience (aud) | Token was issued for the current API | Token intended for a different application |
| Expiration (exp) | Token has not expired | Token has expired |
| Not-before time (nbf) | Token has reached the time when it becomes valid | Token is not yet valid |
| Scope/authority | Token has permission to perform the operation | Missing orders.read |
| Token type | Token matches intended purpose and accepted API type | Using an ID token instead of an access token |

iat (issued at) records when the token was issued. This claim is useful for auditing and certain custom policies, yet do not assume every resource server automatically checks iat as an expiration condition. exp defines the expiration time; nbf defines the earliest time the token is valid.

## 3. Distinguishing 401 and 403 in testing

These two status codes help identify whether an error lies in authentication or authorization:

| Scenario | Typically Expected HTTP Result |
| --- | --- |
| No access token sent to an endpoint requiring authentication | 401 Unauthorized |
| Malformed token, invalid signature, or expired token | 401 Unauthorized |
| Token before its nbf time | 401 Unauthorized |
| Valid token lacking required scopes | 403 Forbidden |
| Valid token with required scopes | 2xx per endpoint |

Exact rules also depend on exception handlers and Spring Security configuration. Do not return internal details about signatures, keys, tokens, or issuers in error responses to clients; safe error codes may be included to aid troubleshooting.

## 4. Using dummy tokens in documentation and examples

HTTP examples in documentation should use placeholders only:

~~~http
GET /api/orders
Authorization: Bearer <TEST_ACCESS_TOKEN>
~~~

<TEST_ACCESS_TOKEN> is a placeholder symbol, not a token that can be sent directly. Do not insert real JWT tokens into @ExampleObject, Markdown files, or OpenAPI JSON.

If you need to illustrate claim structure, use a dummy payload containing no personal data or secrets:

~~~json
{
  "iss": "https://issuer.test.example",
  "sub": "test-user-001",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893459600
}
~~~

This is only JSON illustrating claims, not a signed JWT. Do not combine this payload with a fake signature and describe it as a verifiable token. When signed test tokens are needed, generate tokens during tests with a test-only private key and do not include that key in public documentation.

## 5. Testing scopes with Spring Security and MockMvc

For JWT resource servers, Spring Security typically maps the scope or scp claim to authorities prefixed with SCOPE_. For example, scope orders.read becomes authority SCOPE_orders.read.

A method can be protected with:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize("hasAuthority('SCOPE_orders.read')")
@GetMapping("/api/orders")
List<OrderResponse> listOrders() {
    return orderService.findAll();
}
~~~

To use @PreAuthorize, the application must enable method security, typically via @EnableMethodSecurity in Spring Security configuration. If the project only uses request matchers in the filter chain, test the exact authorization mechanism implemented.

In tests, use the jwt() request post-processor to create a simulated JwtAuthenticationToken:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderScopeTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void allowsReadScope() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void rejectsTokenWithoutReadScope() throws Exception {
        mockMvc.perform(get("/api/orders")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority("SCOPE_profile.read"))))
            .andExpect(status().isForbidden());
    }
}
~~~

The example above tests authority-based authorization. It does not verify JWT signatures, issuer, audience, expiration, or fetching keys from JWKS, because jwt() creates an already-authenticated principal for testing and skips decoding an actual bearer token.

If the application uses a custom JwtAuthenticationConverter, verify that the converter maps claims identically to production configuration. You can unit-test the converter separately using a dummy Jwt model with a scope or scp claim and assert the resulting authorities list.

## 6. Testing missing tokens and invalid tokens as well

Tests using jwt() do not replace testing the filter chain receiving a real bearer header. Have separate integration tests for:

- Missing Authorization header.
- Header not following Bearer format.
- Structurally invalid or undecodable token.
- Token with an invalid signature.
- Valid token lacking scope.

Example without sending a token:

~~~java
mockMvc.perform(get("/api/orders"))
    .andExpect(status().isUnauthorized());
~~~

Example sending a dummy token string that is not a valid credential:

~~~java
mockMvc.perform(get("/api/orders")
        .header("Authorization", "Bearer not-a-jwt"))
    .andExpect(status().isUnauthorized());
~~~

The string not-a-jwt is intentionally malformed, not a production token. Do not log this header value. If an exception handler customizes the response, assertions should check status and public error codes rather than internal decoder error text.

## 7. Testing exp, nbf, and clock skew

JWTs can contain timestamp claims:

- exp: token is no longer accepted after expiration time, accounting for clock skew per validator.
- nbf: token is not accepted before its not-before time, accounting for clock skew.
- iat: issued-at time; if the application has specific policies for tokens issued in the future or overly old tokens, test those policies explicitly.

Machines in a system may drift by a few seconds. Validators typically allow a small clock skew window to avoid rejecting valid tokens solely due to minor time differences. This window must be configured deliberately; do not set it overly large to mask broken system clocks.

Spring Security provides JwtTimestampValidator to validate timestamp claims. You can configure clock skew and a fixed clock in unit tests:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

class JwtTimestampValidatorTest {

    private final Instant now = Instant.parse("2030-01-01T12:00:00Z");

    private JwtTimestampValidator validator() {
        JwtTimestampValidator validator = new JwtTimestampValidator();
        validator.setClock(Clock.fixed(now, ZoneOffset.UTC));
        validator.setClockSkew(Duration.ofSeconds(30));
        return validator;
    }

    @Test
    void rejectsExpiredTokenOutsideClockSkew() {
        Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .subject("test-user")
            .issuedAt(now.minusSeconds(600))
            .expiresAt(now.minusSeconds(60))
            .build();

        OAuth2TokenValidatorResult result = validator().validate(jwt);

        assertThat(result.hasErrors()).isTrue();
    }

    @Test
    void rejectsTokenBeforeNotBeforeTimeOutsideClockSkew() {
        Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .subject("test-user")
            .issuedAt(now)
            .notBefore(now.plusSeconds(60))
            .expiresAt(now.plusSeconds(600))
            .build();

        OAuth2TokenValidatorResult result = validator().validate(jwt);

        assertThat(result.hasErrors()).isTrue();
    }
}
~~~

These tests validate the timestamp validator alone using an in-memory Jwt model; they do not verify signatures. Using Clock.fixed makes test results deterministic without waiting for real time to pass. If the project uses a Spring Security version with a different API, adjust constructors or setters per the Javadoc of the installed dependency.

Add tests for a token just past expiration yet within clock skew, a token expired beyond that window, a token with nbf just inside the allowed window, and a token with nbf outside the allowed window. The goal is to confirm the exact boundaries configured in the system.

## 8. Distinguishing mock JWTs from real signature testing

Tests using jwt() or constructing Jwt directly are useful for checking authorization and individual validators. However, they are insufficient to prove the entire resource server validates tokens properly.

Split testing into two layers:

| Test Type | Components Tested | What Is Not Proven |
| --- | --- | --- |
| Mock JWT/authority | Controllers, method security, and scope rules | Signature, JWKS, issuer, audience, and bearer header decoding |
| Validator unit test | Individual timestamp, issuer, or audience rules | Filter chain and communication with real JWKS |
| Integration test with test keys | Decoding, signature, issuer, audience, and timestamp through resource server | Compatibility with every production setting if test uses a dummy issuer |
| End-to-end with test authorization server | Token issuance flow, resource server, and permissions | Does not prove production secrets or production keys |

To test signatures, generate an RSA/EC key pair exclusively for tests or run a simulated test authorization server/JWKS. Sign tokens with the test private key, configure the decoder to trust the matching public key, and send the bearer token via MockMvc or an HTTP client. Never use production private keys, real secrets, or real user tokens in tests.

Verify at least:

1. Valid signature and trusted key.
2. Tampered signature or different key.
3. Valid and wrong iss.
4. aud containing the resource server and aud missing the resource server.
5. Valid exp and expired exp.
6. nbf reached and nbf in the future.
7. Nonexistent kid or unavailable JWKS if the system must handle those cases.

## 9. Checking issuer and audience

When configuring a resource server via issuer URI, Spring Security can use the authorization server's metadata to locate JWKS and verify the issuer. If the API requires a specific audience, configure an audience validator; do not assume every default setup automatically checks audience against your service name.

Audience validator configuration example:

~~~java
import java.util.List;

import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

final class AudienceValidator implements OAuth2TokenValidator<Jwt> {

    private final String requiredAudience;

    AudienceValidator(String requiredAudience) {
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        List<String> audiences = jwt.getAudience();
        if (audiences != null && audiences.contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Token is not intended for this API.",
            null
        );
        return OAuth2TokenValidatorResult.failure(error);
    }
}
~~~

When combining an audience validator with the default validator, preserve both issuer and timestamp checks:

~~~java
OAuth2TokenValidator<Jwt> issuerAndTimestamp =
    JwtValidators.createDefaultWithIssuer("https://issuer.test.example");

OAuth2TokenValidator<Jwt> audience =
    new AudienceValidator("orders-api");

NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri("https://issuer.test.example/jwks")
    .build();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(issuerAndTimestamp, audience)
);
~~~

This snippet illustrates how to compose validators; build the JwtDecoder using an appropriate JWKS URI or test public key. Use a dummy issuer in tests, and never replace the production issuer with a test value on deployment.

## 10. Checking OIDC: ID token and access token

OIDC adds an identity authentication layer over OAuth2. In an OIDC login flow, the client validates the ID token and related claims; the resource server validates the access token intended for the API.

| Claim/Property | Check in OIDC |
| --- | --- |
| iss | Matches the configured issuer |
| sub | User identifier at the issuer |
| aud | Contains the OIDC client ID |
| exp | ID token has not expired |
| iat | Issued-at time reasonable per policy |
| nonce | Matches login session's nonce to prevent replay |
| azp | Authorized party when multiple audiences exist and authorized client must be verified |

The access token must be checked by the resource server, especially API-targeted audience and scopes. Do not infer an access token is valid merely because the ID token from the same login session is valid.

With Spring Security test support, you can use oidcLogin() to test controllers depending on OidcUser without calling a real identity provider:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

mockMvc.perform(get("/profile")
        .with(oidcLogin().idToken(token ->
            token.claim("sub", "test-user-001")
                .claim("email", "user@example.test"))))
    .andExpect(status().isOk());
~~~

This test simulates an OIDC principal to test how the application processes user info. It does not verify ID token signatures, nonce, or authorization code exchange with the identity provider. Protocol steps require separate integration tests against a test issuer.

## 11. Testing refresh tokens safely

Refresh tokens belong to the authorization server's token issuance flow, not business API calls. If the application or authorization server manages refresh tokens, verify:

- A valid refresh token issues a new access token.
- An expired or revoked refresh token is rejected.
- Token rotation issues a new refresh token per policy.
- Old refresh tokens cannot be reused after rotation if the server supports reuse detection.
- Refresh tokens are bound to the right client, user/session, and authorization scope.
- Logout or session revocation handles refresh tokens per policy.

Never put a refresh token into the Authorization header of a business API. Never write refresh tokens to logs or store them in shared fixtures. When testing rotation, keep token values in test memory, use dummy tokens issued by a test issuer, and clean up test data after execution.

If the system uses refresh token rotation, test the case of two concurrent refresh requests. Policy may allow one request to succeed while rejecting the other or triggering token family revocation upon reuse detection. Results must match the documentation of the authorization server in use.

## 12. Verifying scopes published in OpenAPI

When describing OAuth2 with springdoc, declare flows and scopes in the security scheme:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "oauth2",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        clientCredentials = @OAuthFlow(
            tokenUrl = "https://issuer.test.example/oauth/token",
            scopes = {
                @OAuthScope(
                    name = "orders.read",
                    description = "Read orders"
                ),
                @OAuthScope(
                    name = "orders.write",
                    description = "Create or update orders"
                )
            }
        )
    )
)
~~~

An operation can require a scope:

~~~java
@Operation(
    summary = "Read orders",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"orders.read"}
    )
)
~~~

Verify that the generated JSON document contains components.securitySchemes.oauth2.flows.clientCredentials.scopes and the operation's requirement contains orders.read. Scopes in OpenAPI only describe the contract; Spring Security must still map claims and enforce the corresponding authorities.

Never put access tokens or refresh tokens into @ExampleObject. When a request example is needed, use a placeholder:

~~~http
GET /api/orders
Authorization: Bearer <TEST_ACCESS_TOKEN>
~~~

## 13. Token and scope test matrix

A baseline matrix for a resource server:

| Token | Scope | Expiration | Expected Result |
| --- | --- | --- | --- |
| Not sent | — | — | 401 |
| Malformed/invalid signature | Sufficient or unknown | — | 401 |
| Valid token | Missing orders.read | Valid | 403 |
| Valid token | Has orders.read | Valid | 2xx |
| Valid token | Has orders.read | Expired | 401 |
| Valid token | Has orders.read | nbf in the future | 401 |
| Valid token from different issuer | Has scope | Valid | 401 |
| Valid token for different audience | Has scope | Valid | 401 |
| ID token sent as access token | May have fake scope claim | Valid | Rejected per token type/audience validation |

For OIDC clients, add tests for ID tokens with wrong issuer, wrong audience, mismatched nonce, and expired tokens. For authorization servers, add tests for expired, revoked, and rotated-token reuse scenarios.

## 14. Never let tokens appear in logs, traces, or error reports

Credentials can leak through many places outside source code:

| Potential Leak Location | Mitigation |
| --- | --- |
| HTTP access logs | Never log full Authorization/Cookie headers |
| Application logs | Never log tokens, request headers, or objects containing credentials |
| Exception messages | Never concatenate tokens or raw JWTs into error messages |
| Distributed tracing | Strip/redact Authorization, Cookie, and token-related attributes |
| Test reports/snapshots | Use dummy tokens; never record real credentials |
| Swagger UI screenshots | Clear authorization before capturing; use test environments |
| CI variables/output | Never echo secrets; use secret stores and masking |
| OpenAPI examples | Use placeholders or dummy data only |

Field names to treat as sensitive include Authorization, Cookie, Set-Cookie, access_token, refresh_token, id_token, client_secret, and API keys. Redaction must be applied across loggers, gateways, tracing exporters, and observability tools; masking tokens in only one layer is not enough.

Do not enable DEBUG/TRACE logging for security components in production without verifying what contents may be written. When diagnostics are needed, log a correlation ID, issuer alias, validation outcome, or safe error code instead of raw tokens.

## 15. Using test-only keys and credentials

When real signature verification is needed, generate short-lived test keys in test fixtures or use a fixed key set dedicated solely to the test repository. Test private keys must never be used in production and must never be copied from production secret managers.

Principles:

1. Use a dedicated test issuer such as https://issuer.test.example.
2. Use a dummy audience such as orders-api.
3. Use synthetic subjects, not real user emails or IDs.
4. Use test key pairs, never production private keys.
5. Give tokens short lifetimes and keep them within the test process.
6. Do not store signed tokens in long-lived fixtures if they can be generated when tests run.
7. Never log tokens or Authorization contents when tests fail.
8. Revoke/delete test keys and data if the test environment has persistent state.

If tests use WireMock or a mock JWKS endpoint, serve only test public keys. Never expose private keys via JWKS and never allow production environments to trust test issuers.

## 16. Testing error responses without leaking security details

APIs should return enough information for clients to know they need to log in, grant scopes, or fetch a new token, without exposing internal details.

Safe response example:

~~~json
{
  "code": "INSUFFICIENT_SCOPE",
  "message": "Token lacks permission to read orders.",
  "requiredScope": "orders.read"
}
~~~

Never return:

- Raw tokens or full decoded payloads.
- Signature contents or private keys.
- Internal JWKS configuration details.
- Client secrets or refresh tokens.
- Stack traces or decoder class names in public responses.

For 401, WWW-Authenticate: Bearer and appropriate error codes can be used. Avoid returning details that help an attacker distinguish finely between a nonexistent token, revoked token, bad signature, or invalid issuer unless security policy allows it.

## 17. Checking OpenAPI and Swagger UI

After declaring the OAuth2/OIDC security scheme, fetch the documentation:

~~~bash
curl -sS http://localhost:8080/v3/api-docs
~~~

Check:

1. Does the security scheme have the right type, OAuth2 or OpenID Connect?
2. Are token URL/authorization URL public endpoints for the right environment?
3. Do declared scopes have accurate names and descriptions?
4. Do operations require the right scopes?
5. Are there no real tokens in example, examples, description, or extensions?
6. Are no internal issuers or staging URLs accidentally published in public docs?
7. Do security requirements match Spring Security runtime?

Swagger UI can assist with Authorize and trying requests, yet never enter production tokens into shared UIs or shared machines. If persistence is enabled, review the browser authorization state storage policy; prefer short-lived test tokens and dedicated browser profiles.

## 18. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| MockMvc scope tests pass yet real tokens fail | jwt() bypasses signature/issuer/audience/timestamp decoder | Add integration tests sending bearer tokens through real decoder with test keys |
| Valid token receives 403 | Authority converter does not map claim to SCOPE_... as policy expects | Check scope/scp claim and JwtAuthenticationConverter |
| Expired token is still accepted briefly | Clock skew allows time drift | Check clock skew configuration and clock synchronization |
| Token before nbf is rejected/accepted unexpectedly | Validator or clock skew does not match expectations | Test nbf boundaries with a fixed Clock |
| ID token can call APIs | Resource server checks only signature without checking appropriate audience/type | Enforce audience and token type policies |
| Scopes in docs are right yet runtime allows calls | OpenAPI only describes; authorization is not configured | Test Spring Security authorities/method security |
| Token appears in CI logs | Headers or exceptions logged verbatim | Redact Authorization and token fields at every layer |
| Expired token tests flake intermittently | Relies on real clock or short-lived tokens | Use a fixed Clock and deterministic timestamps |
| Refresh token test reuses old token and succeeds | Rotation/reuse policy not tested or enforced | Add tests matching authorization server behavior |

## 19. Safe testing workflow

When building tests for OAuth2/OIDC:

1. Identify the role being tested: authorization server, OAuth2 client, or resource server.
2. Pick the right token type: access token for APIs, ID token for OIDC login, refresh token for the token endpoint.
3. Use dummy tokens and synthetic subjects; never use production credentials.
4. Test scopes/authorities using MockMvc jwt() to verify authorization logic.
5. Test exp, nbf, issuer, and audience using validators/unit tests with a fixed Clock.
6. Test signatures, JWKS, and the bearer filter chain using dedicated test keys/issuers.
7. Test OIDC nonce/audience/issuer in client flows; test refresh rotation at the authorization server.
8. Verify OpenAPI schemes, scopes, and requirements are generated accurately.
9. Redact tokens in logs, traces, CI reports, fixtures, and documentation examples.
10. Distinguish mock test outcomes from real token verification outcomes.

A good test suite must verify both granted and denied permissions, token validity windows, and that the server trusts only tokens intended for itself. By using dummy data, test keys, and consistent redaction, development teams can test OAuth2/OIDC thoroughly without introducing sensitive data into documentation or pipelines.

## References

- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security – Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [OpenID Connect Core – ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken)
- [RFC 7519 – JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 6749 – OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
