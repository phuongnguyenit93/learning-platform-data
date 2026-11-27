# Claims, Audience, and Authorization Errors at the Resource Server

A Resource Server can receive an access token and still reject the request because a claim is missing or has the wrong type, the issuer is untrusted, the audience is not intended for that API, or scopes/roles are not mapped to the authorities Spring Security expects. Some cases return 401 Unauthorized because the token is invalid; other cases return 403 Forbidden because the token was authenticated, yet the principal lacks permission to access the endpoint.

When troubleshooting, trace the entire permission path: which claims the Authorization Server issues, how the Resource Server verifies the token, how the converter translates claims into GrantedAuthority objects, and which authorities the security rules check. This lesson focuses on Spring Security Resource Server in an OAuth 2.0/OpenID Connect system using Spring Authorization Server.

## 1. Distinguishing Token Authentication Errors from Authorization Errors

The first step is identifying which layer failed the request. Do not start by adding roles to tokens or loosening security matchers before knowing why the token was rejected.

| Result | Common Meaning | Where to Check |
|---|---|---|
| 401 Unauthorized | Missing bearer token, unparseable token, invalid signature, expired token, invalid issuer/audience, or inactive introspection | Authentication filter, JwtDecoder, or OpaqueTokenIntrospector |
| 403 Forbidden | Token was accepted, but lacks required scope/role/authority or is denied by policy | JwtAuthenticationConverter, authority mapping, and authorization rules |
| 404 Not Found | Possibly a nonexistent route or the application intentionally hiding the endpoint | Request mapping, security matchers, and error handling |
| 200 but wrong data scope | API authenticated successfully, yet data-layer authorization check is missing or wrong | Method security, tenant/ownership policy, and query filters |

In default Resource Server configuration, bearer token authentication failures are usually handled by BearerTokenAuthenticationEntryPoint; authorization failures typically go through BearerTokenAccessDeniedHandler or a custom access-denied handler. Actual responses can vary when the application replaces exception handlers.

Quick way to read them:

- **401**: check whether the token is valid and accepted as a credential.
- **403**: check whether the principal holds the exact authority required by the endpoint.
- **401 after changing issuer/audience**: check validators and metadata.
- **403 after changing scope/roles claims**: check converters and authorization expressions.

Do not use the status code as the sole evidence. Inspect WWW-Authenticate when present, sanitized logs, exception category, and validator output. Never log raw JWTs or send tokens to public decoding websites.

## 2. Identifying Token Type and Claim Source

Before analyzing claims, identify which type of token the API is receiving:

- **JWT access token**: Resource Server verifies the signature, lifetime, and JWT validators.
- **Opaque access token**: Resource Server typically calls the introspection endpoint to check status and receive metadata.
- **OIDC ID Token**: token meant for the OIDC client to authenticate the user; not meant by default to substitute for an access token when calling APIs.

An ID Token usually has the OIDC application's client_id as its audience. An access token needs an audience appropriate for the resource server/API. Using an ID Token to call an API or checking aud under the wrong profile can cause valid rejections or mistaken token acceptance.

With a JWT, the payload can be decoded yet must not be trusted until the signature and required claims are verified. Successfully decoding a JWT does not prove the token is valid.

With an opaque token, claims cannot be decoded from the token string. Inspect the introspection response and active flag, then check how the Resource Server maps metadata into principal/authorities. Do not apply JWT claim assumptions to opaque tokens.

## 3. Checking Claims Issued by the Authorization Server

When the Resource Server reports missing scope, roles, aud, or tenant_id, verify whether the claim is actually issued inside the access token. Do not look solely at client config or the ID Token.

In Spring Authorization Server, JWT access tokens can be customized with OAuth2TokenCustomizer<JwtEncodingContext>. Example adding audience and permission claims to an access token:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> accessTokenCustomizer() {
    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }

        context.getClaims().claim(
                "aud",
                List.of("https://api.example.test")
        );

        context.getClaims().claim(
                "roles",
                List.of("ORDER_READER")
        );
    };
}
~~~

This is an illustrative example; real policy must derive audience and roles from the client, authorization, or a trusted permission source. Never grant admin roles simply because the client passed an arbitrary parameter. If the token format is opaque, a JWT customizer is not where claims are emitted; inspect the custom access token format and corresponding introspection metadata.

When inspecting an issued token, verify:

- The token under inspection is the actual access token from that API call.
- The claim is inside the access token, not only inside the ID Token.
- The claim name is spelled accurately with exact casing.
- The claim value has the exact JSON type expected by the Resource Server.
- The claim was added before signing the token.
- The token was actually produced by the expected issuer, client, grant type, and config.
- No subsequent customizer overwrites or removes the claim.

Some common mistakes:

| Symptom | Possible Cause |
|---|---|
| Token lacks roles | Customizer did not run for access tokens or token type condition was wrong |
| Claim appears only in ID Token | Customization logic runs for OIDC ID Token |
| scope is a string, but converter expects an array | Both sides do not agree on claim schema |
| aud lacks the target API | Audience was not added or token was issued for another resource |
| Node A has the claim, node B lacks it | Inconsistent customizer config or deployment |
| Claim holds stale values | Permission source/cache was not updated before token issuance |

## 4. Checking Data Types and Claim Names

JWT claims are JSON. Claim names and data types must match between the Authorization Server and Resource Server. Values that look equivalent in logs may not be equivalent when read by a converter.

Common scope formats:

~~~json
{
  "scope": "openid profile orders.read"
}
~~~

~~~json
{
  "scp": ["openid", "profile", "orders.read"]
}
~~~

Roles example:

~~~json
{
  "roles": ["ORDER_READER", "ORDER_OPERATOR"]
}
~~~

Error-prone cases:

- scope instead of scp, or vice versa.
- roles instead of authorities.
- Role is a single string while the converter expects a list.
- String scope delimited by commas instead of spaces.
- Claim nested inside an object, such as realm_access.roles, while the converter reads only top-level claims.
- Role value already has prefix ROLE_, yet the converter prepends the prefix a second time.
- Claim has number/boolean type while logic casts it to string.

JWT claim names are case-sensitive. roles, Roles, and ROLE are distinct names. If changing the claim schema, deploy Authorization Server and Resource Server changes together, and account for still-valid older tokens carrying the previous schema.

Never fix a token by decoding and altering its payload. The signature will become invalid. Fix the issuer-side generator or converter and issue a fresh token.

## 5. Checking How Scopes Map to GrantedAuthority

Spring Security Resource Server defaults to JwtGrantedAuthoritiesConverter to convert scopes into authorities. By default, the converter looks for the scope or scp claim, splits scopes, and adds the SCOPE_ prefix.

For example, a token containing:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

can produce these authorities:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Therefore, the rule:

~~~java
.requestMatchers("/orders/**").hasAuthority("SCOPE_orders.read")
~~~

matches the default authority. The rule hasAuthority("orders.read") will not match if the converter added the SCOPE_ prefix.

### 5.1 Wrong Scope Claim Name

If the Authorization Server emits permissions instead of scope, the default converter will not recognize that claim automatically. You can configure the claim name:

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter authoritiesConverter =
            new JwtGrantedAuthoritiesConverter();

    authoritiesConverter.setAuthoritiesClaimName("permissions");
    authoritiesConverter.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(authoritiesConverter);

    return converter;
}
~~~

In that case, the token needs a matching structure, such as permissions: "orders.read orders.write" if the converter splits strings by whitespace. If the claim is a JSON array, verify your converter/version handles that type properly. You can write a custom converter if your system's schema differs from default conventions.

### 5.2 Missing or Duplicated Prefix

If authorityPrefix is set to an empty string, the authority will be orders.read. If the converter adds SCOPE_ while the claim already contains SCOPE_orders.read, the result can become SCOPE_SCOPE_orders.read.

Log the post-authentication authority list in a test/dev environment or set a breakpoint inside JwtAuthenticationConverter. Never log raw tokens. Compare actual authorities against expressions in authorizeHttpRequests or @PreAuthorize.

### 5.3 Scopes Are Not Roles

Scopes and roles generally represent two distinct concepts:

- Scope describes permissions a client is authorized to request on a resource, e.g. orders.read.
- Role describes a business role of the principal, e.g. ORDER_ADMIN.

Do not automatically turn every scope into a role or vice versa. If an endpoint requires a role, issue the role from a trusted permission source and map it explicitly. Use hasAuthority("SCOPE_orders.read") for scopes and hasRole("ORDER_ADMIN") for roles per Spring Security's prefix convention.

## 6. Checking Role and Authority Mapping

hasRole("ADMIN") in Spring Security typically checks for the ROLE_ADMIN authority. Meanwhile, hasAuthority("ADMIN") compares the exact string ADMIN without adding a prefix.

Comparison table:

| Rule | Required Authority |
|---|---|
| hasAuthority("SCOPE_orders.read") | SCOPE_orders.read |
| hasAuthority("ROLE_ORDER_ADMIN") | ROLE_ORDER_ADMIN |
| hasRole("ORDER_ADMIN") | ROLE_ORDER_ADMIN |
| hasAuthority("ORDER_ADMIN") | ORDER_ADMIN |
| hasAnyRole("ORDER_ADMIN", "SUPPORT") | ROLE_ORDER_ADMIN or ROLE_SUPPORT |

If a token contains:

~~~json
{
  "roles": ["ORDER_ADMIN"]
}
~~~

the default JwtGrantedAuthoritiesConverter will not automatically turn the roles claim into ROLE_ORDER_ADMIN. A custom converter configuration is required.

Example converter for an array-based roles claim:

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();

    Converter<Jwt, Collection<GrantedAuthority>> rolesConverter = jwt -> {
        List<String> roles = jwt.getClaimAsStringList("roles");

        if (roles == null) {
            return Collections.emptyList();
        }

        return roles.stream()
                .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                .toList();
    };

    Converter<Jwt, Collection<GrantedAuthority>> combined = jwt -> {
        Collection<GrantedAuthority> authorities =
                new ArrayList<>(scopeConverter.convert(jwt));

        authorities.addAll(rolesConverter.convert(jwt));
        return authorities;
    };

    JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(combined);

    return converter;
}
~~~

The example above requires a Java version supporting Stream.toList(); on older Java versions, replace with the corresponding collector. Include the relevant Spring Security and Java Collections/Converter imports. If the role claim is nested inside an object or has a complex schema, write an extractor that validates types and rejects invalid values.

Do not prepend prefixes blindly. If the claim already contains ROLE_ORDER_ADMIN, prepending ROLE_ produces the wrong authority. Decide on one unified schema: either the claim stores bare role names or full authorities.

## 7. Checking Issuer and Audience

A token may have a valid signature yet still not be meant for the Resource Server handling the request. Two critical claims are:

- iss: the Authorization Server that issued the token.
- aud: the resource/client for which the token was issued.

The issuer must match the value trusted by the Resource Server. The access token's audience must contain the target API identifier per policy. Do not use azp in place of aud; azp has meaning in an OIDC client context and does not replace API audience validation.

### 7.1 Checking Issuer

If the Resource Server is configured with an issuer URI, Spring Security can automatically configure issuer validation for that URI. If constructing JwtDecoder manually with a JWK Set URI, you must add an explicit issuer validator.

~~~java
NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(
                "https://auth.example.test"
        )
);
~~~

If the token has a different iss due to a mismatched hostname, scheme, path, or trailing slash, the decoder will reject it. Compare the token's issuer against the configured issuer exactly, and inspect discovery metadata and reverse proxy configuration.

### 7.2 Checking Audience

Do not assume that signature or issuer verification automatically verifies audience. If the API requires a specific audience, add a validator:

~~~java
OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
    if (jwt.getAudience().contains("https://api.example.test")) {
        return OAuth2TokenValidatorResult.success();
    }

    OAuth2Error error = new OAuth2Error(
            OAuth2ErrorCodes.INVALID_TOKEN,
            "Required audience is missing",
            null
    );
    return OAuth2TokenValidatorResult.failure(error);
};

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator
        )
);
~~~

The example above requires at least one matching audience. If policy requires exactly one audience, also check the list size and contents. Align audience representation between the Authorization Server and Resource Server.

### 7.3 Audience Missing from the Issued Token

If the Resource Server requires https://api.example.test yet the access token lacks that audience, check token issuance configuration. For JWT access tokens, you can add the aud claim via OAuth2TokenCustomizer<JwtEncodingContext> as shown in section 3. If the application supports resource indicators, verify the client sends the right resource parameter and the Authorization Server applies the mapping policy properly.

Do not issue a single shared audience across all APIs if doing so allows tokens to be reused across unrelated resource servers. Audience should reflect the intended target and be validated at each API.

## 8. Checking Endpoint Authorization Rules and Method Security

After verifying token validation and authority mapping, check the rules protecting endpoints. A common mistake is the converter producing SCOPE_orders.read while the endpoint requires ROLE_ORDERS_READ, or a rule using hasRole when the authority lacks the ROLE_ prefix.

Configuration example:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .requestMatchers("/admin/**")
                .hasRole("ORDER_ADMIN")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(resourceServer -> resourceServer
            .jwt(jwt -> jwt.jwtAuthenticationConverter(
                    jwtAuthenticationConverter()))
        );

    return http.build();
}
~~~

When method security is enabled, also inspect annotations:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Order getOrder(String id) {
    // ...
}
~~~

A request may pass the filter-chain matcher yet still be denied by method security. Conversely, an endpoint with an overly broad filter-chain matcher might allow access while the business method lacks ownership or tenant checks.

Check:

- Does the right SecurityFilterChain handle the request path?
- Does the request matcher have the right HTTP method and path?
- Does any chain with a higher @Order intercept the request first?
- Is JwtAuthenticationConverter attached to the right Resource Server chain?
- Is @EnableMethodSecurity enabled if the application relies on @PreAuthorize?
- Do hasRole/hasAuthority expressions use the right prefixes?
- Does a custom AuthorizationManager or access decision logic override the rule?
- Does business logic check ownership, tenant, and resource state?

Do not rely solely on high-level roles to protect multi-tenant data. A user holding orders.read must still only read orders belonging to their granted tenant or scope.

## 9. Diagnosing Opaque Tokens and Introspection

If the Resource Server uses opaque tokens, the verification flow differs from JWTs:

1. Client sends the bearer token to the API.
2. Resource Server calls the Authorization Server's introspection endpoint.
3. Authorization Server returns token metadata, where active indicates whether the token is active per policy.
4. Resource Server converts the metadata into principal and authorities.

When receiving 401, check:

- Is the introspection endpoint reachable?
- Does the client calling introspection authenticate properly?
- Does the response include active: true?
- Has the token expired or been revoked?
- Is audience/resource returned and checked by validators?
- Does the Resource Server cache introspection results for too long?

When receiving 403, check scope/authority metadata and OpaqueTokenIntrospector. By default, Spring Security maps scope in the introspection response into authorities prefixed with SCOPE_ using the corresponding mechanism. If the Authorization Server returns custom claims like roles, a custom introspector or converter is needed to map roles.

Do not apply a JWT JwtDecoder to handle opaque tokens. Conversely, do not use introspection merely to mask a misconfigured JWT decoder if the architecture relies on local JWT validation.

## 10. Testing and Reproducing Claims/Permissions Errors

A solid test suite should isolate each validator and each mapping step. If you test a wrong issuer together with an invalid signature, the test only proves the signature is rejected. If you test a missing scope together with an expired token, the 401 result does not prove the authorization rule works.

### 10.1 Unit Test for Audience Validator

Create a JWT fixture with test-appropriate signature/decoder, valid issuer, and valid lifetime; vary only the audience. You can test OAuth2TokenValidator<Jwt> directly:

~~~java
@Test
void rejectsTokenForDifferentAudience() {
    Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .issuer("https://auth.example.test")
            .subject("user-123")
            .audience(List.of("https://billing.example.test"))
            .issuedAt(Instant.now())
            .expiresAt(Instant.now().plusSeconds(300))
            .build();

    OAuth2TokenValidatorResult result =
            audienceValidator.validate(jwt);

    assertThat(result.hasErrors()).isTrue();
}
~~~

This is a direct validator test and does not verify signatures. You need a separate integration test with a genuinely signed JWT using a test key to prove the decoder executes signature, issuer, lifetime, and audience validators together.

### 10.2 Testing Scope-to-Authority Mapping

Test the converter against different claim shapes:

| Input Claim | Expected Authority |
|---|---|
| scope: "orders.read" | SCOPE_orders.read |
| scp: ["orders.read"] | Depends on chosen converter/configuration |
| roles: ["ORDER_ADMIN"] | ROLE_ORDER_ADMIN if custom role converter is configured |
| roles: ["ROLE_ORDER_ADMIN"] | Correct only if converter does not prepend prefix again or normalizes it |
| No scope/roles | Must not auto-generate business authorities |

Assert the GrantedAuthority list produced by the converter, not just that the claim exists in the JWT.

### 10.3 Testing Endpoints with Insufficiently Privileged Tokens

You can use Spring Security Test's jwt() request post-processor to test endpoint authorization rules:

~~~java
mockMvc.perform(get("/orders/123")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")
        )))
    .andExpect(status().isForbidden());
~~~

This constructs a test Authentication directly and usually bypasses real JWT decoding and validation. It is useful for testing endpoint rules, but does not prove production issuer, signature, audience, or converters work correctly. Supplement it with integration tests sending real JWTs signed by a test key through the Resource Server.

### 10.4 Minimum Test Matrix

| Test ID | Input | Expected Result |
|---|---|---|
| CLAIM-01 | Missing scope claim | No scope authority |
| CLAIM-02 | Scope with wrong JSON type | Converter handles per policy without granting unintended rights |
| CLAIM-03 | Misnamed roles claim | No role authority created |
| CLAIM-04 | Role with duplicated prefix | Endpoint rejects due to authority mismatch |
| ISS-01 | Different issuer | 401 / invalid token |
| ISS-02 | Missing issuer | Token rejected |
| AUD-01 | Audience is another API | 401 / invalid token |
| AUD-02 | Missing required audience | 401 / invalid token |
| AUTH-01 | Valid token, missing scope | 403 |
| AUTH-02 | Token has scope, missing role | 403 |
| AUTH-03 | Valid role, wrong tenant/owner | Rejected per business policy |
| OPAQUE-01 | Introspection returns active=false | 401 |
| OPAQUE-02 | Active token, missing authority | 403 |

## 11. Production Incident Workflow

When APIs start returning unexpected 401/403 responses:

1. Record the endpoint, HTTP method, timestamp, correlation ID, and instance ID.
2. Identify whether the Resource Server uses JWT or opaque tokens.
3. For 401, check bearer extraction, signature, issuer, audience, expiration, or introspection active status.
4. For 403, inspect the post-authentication principal and GrantedAuthority list.
5. Compare actual claims against the agreed schema and policy; use test fixtures or internal fingerprints to correlate logs.
6. Check the converter, authority prefix, security matchers, and method security.
7. Check tenant/ownership policies at the business layer.
8. Reproduce in a test environment with a valid token and a single altered claim.
9. Deploy the fix consistently and monitor 401/403 rates after release.

In production, never log full JWTs or sensitive claims. You may record required claim names, validator error categories, normalized audiences, issuer categories, client IDs, and correlation IDs per data policy. Avoid logging PII or granular user permissions when unnecessary for investigation.

When changing claim schemas, converters, or audience policies, account for still-valid older tokens. Resource Servers may receive tokens issued before the deployment using a different claim format. You may need a transition period supporting the old schema, shortened token TTLs, or a planned forced re-issuance. Never relax audience/issuer validators just to stay compatible with mis-targeted tokens.

A solid incident report clarifies whether the fault lay in claim issuance, JWT/introspection validation, authority mapping, or authorization rules, and records the reproduction tests and post-fix results. By tracing the complete chain from claims to GrantedAuthority and endpoint policy, operations teams can fix 401/403 errors accurately while preserving OAuth 2.0/OpenID Connect trust boundaries.
