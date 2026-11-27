# 29.6. Testing Controllers Using `@AuthenticationPrincipal`

## 1. Why Does Testing `@AuthenticationPrincipal` Easily Produce Misleading Results?

In a **Spring Security OAuth 2.0/OIDC Client (Servlet)** application, controllers often need to know who the current user is. A common approach is using the `@AuthenticationPrincipal` annotation:

```java
@GetMapping("/api/me")
public UserProfile me(@AuthenticationPrincipal OidcUser user) {
    return new UserProfile(
        user.getSubject(),
        user.getClaimAsString("email")
    );
}
```

At first glance, this looks like a simple controller. Yet a test using:

```java
@WithMockUser(username = "alice")
```

**does not necessarily produce an `OidcUser`**. `@WithMockUser` primarily sets up a `UsernamePasswordAuthenticationToken` with a Spring Security `UserDetails` principal. Meanwhile, the controller expects a principal of type `OidcUser`, containing an ID Token and OIDC claims.

Common consequences:

- The controller receives `null` for the `@AuthenticationPrincipal OidcUser` parameter.
- The controller throws a `NullPointerException` when calling `user.getSubject()`.
- The test fails, not due to controller code, but because **the fixture supplies the wrong principal type**.
- A test using `@WithMockUser` passes when the controller only needs a username, without actually testing **OIDC Login**.
- A test calling the service/controller directly skips the argument resolver, leaving `@AuthenticationPrincipal` wiring bugs undetected.

Therefore, distinguish two goals:

1. **Testing that the Spring MVC controller receives the right principal** from `SecurityContext` via `@AuthenticationPrincipal`.
2. **Testing the real OAuth2/OIDC protocol** such as authorization redirects, token exchanges, signatures, issuer, audience, state, nonce, and PKCE.

The first goal can be tested quickly with **`MockMvc` + `spring-security-test`**, especially the **`oidcLogin()`** and **`oauth2Login()`** request post-processors. The second goal requires integration tests at a different scope and must never be claimed as covered merely by constructing a mock principal.

> **Principle:** Build the **exact `Authentication`/principal type that production uses**. For OIDC Login, typically use `oidcLogin()` or a custom `OidcUser`; for non-OIDC OAuth2 Login, use `oauth2Login()`. `@WithMockUser` suits testing generic username/password authentication, but is not the default choice for testing controllers that depend on `OidcUser`.

### 1.1. Learning Outcomes

After this lesson, you will be able to:

1. Explain where `@AuthenticationPrincipal` actually obtains its value.
2. Distinguish `Principal`, `Authentication`, `SecurityContext`, `UserDetails`, `OAuth2User`, `OidcUser`, and `Jwt`.
3. Configure `MockMvc` with Spring Security filters so the annotation resolves properly.
4. Use `oidcLogin()` to test controllers requiring OIDC subject/claims.
5. Use `oauth2Login()` to test controllers requiring `OAuth2User`.
6. Know when `@WithMockUser` produces the wrong principal type.
7. Test `@AuthenticationPrincipal(expression = "...")`, `errorOnInvalidType`, and custom meta-annotations.
8. Test public endpoints, unauthenticated requests, and mismatched principal types.
9. Test roles/authorities/tenant isolation without trusting raw request headers.
10. Use `@WebMvcTest`, `@SpringBootTest`/`@AutoConfigureMockMvc`, and `@WithSecurityContext` within their proper scope.
11. Avoid confusing `@AuthenticationPrincipal` with `@RegisteredOAuth2AuthorizedClient`.
12. Distinguish controller slice tests from OIDC Login/Resource Server integration tests.
13. Design synthetic test data, protect claims, and keep tokens/PII out of logs.

## 2. How Does `@AuthenticationPrincipal` Work?

Spring Security Servlet resolves the principal from `SecurityContextHolder`. The annotation is handled by:

```java
org.springframework.security.web.method.annotation
    .AuthenticationPrincipalArgumentResolver
```

Conceptually:

```text
HTTP request
    ↓
Spring Security Filter Chain
    ↓
SecurityContextHolder.getContext().getAuthentication()
    ↓
Authentication.getPrincipal()
    ↓
AuthenticationPrincipalArgumentResolver
    ↓
Controller parameter @AuthenticationPrincipal
```

### 2.1. Types to Distinguish

| Type | Description | How it is used |
| --- | --- | --- |
| `SecurityContext` | Holds the request/thread's `Authentication` per `SecurityContext` strategy | Spring Security filters/test helpers |
| `Authentication` | Full principal info, authorities, and authenticated state | Direct injection or `@CurrentSecurityContext` |
| `Authentication.getPrincipal()` | Object representing the primary identity | `@AuthenticationPrincipal` |
| `UserDetails` | Typical principal for username/password login | `@WithMockUser`, `user(...)` |
| `OAuth2User` | Principal after OAuth2 Login | `oauth2Login()` |
| `OidcUser` | Principal after OpenID Connect Login, includes ID Token | `oidcLogin()` |
| `Jwt` | Typical principal of `JwtAuthenticationToken` at a Resource Server | `jwt()` when testing Bearer JWTs |
| `OAuth2AuthorizedClient` | `ClientRegistration` paired with access/refresh tokens | `@RegisteredOAuth2AuthorizedClient` or manager/service |

Controller:

```java
@GetMapping("/api/whoami")
String whoAmI(@AuthenticationPrincipal OidcUser user) {
    return user.getSubject();
}
```

The annotation extracts the **principal**, not the whole `Authentication`, does not read `Authorization: Bearer` directly, and does not itself query the OIDC UserInfo Endpoint.

### 2.2. Typical OIDC Login Structure

In a typical OIDC Login:

```text
Authentication:
    OAuth2AuthenticationToken
        |
        +-- principal: DefaultOidcUser implements OidcUser
        |     |
        |     +-- OidcIdToken
        |     +-- OidcUserInfo (optional)
        |     +-- authorities
        |
        +-- authorities
        +-- authorizedClientRegistrationId = corporate
```

`OidcUser` holds the OIDC identity; `OAuth2AuthenticationToken` also carries the **registration ID** used to distinguish providers/tenants.

Hence:

```java
@AuthenticationPrincipal OidcUser oidcUser
```

extracts the principal, **not directly** the registration ID. If a controller needs both the registration ID or authorities, it can inject `Authentication`:

```java
@GetMapping("/api/context")
Map<String, String> context(
        Authentication authentication,
        @AuthenticationPrincipal OidcUser user) {

    if (!(authentication instanceof OAuth2AuthenticationToken token)) {
        throw new IllegalStateException(
            "Expected OAuth2AuthenticationToken");
    }

    return Map.of(
        "subject", user.getSubject(),
        "registrationId",
        token.getAuthorizedClientRegistrationId());
}
```

**Note:** `registrationId` identifies the client registration used for login, but **does not replace** checking whether the user has permission to access the tenant.

### 2.3. `getName()` and `sub` Are Not Strictly Identical

For `OidcUser`, the core identity attribute is OIDC `sub`, scoped to the OP's `iss`. `DefaultOidcUser` usually uses `sub` as the default name attribute, yet applications may configure a different principal name attribute.

Therefore:

```java
oidcUser.getSubject()
```

explicitly expresses that the application wants the **OIDC subject**.

If you call:

```java
oidcUser.getName()
```

understand that `getName()` depends on how `OidcUser` and the name attribute were configured. It is not guaranteed to be an email or username.

Never unconditionally use `email` as a user identifier key; emails can change or be absent, and may be unverified depending on claims/provider. In multi-issuer models, identity normally requires the **`(issuer, subject)` pair**.

## 3. Choosing the Right Test Type for the Right Question

| Test type | Spring MVC argument resolution? | Security filter chain? | Real OAuth2/OIDC network flow? |
| --- | --- | --- | --- |
| Direct controller method call | No | No | No |
| Simple `MockMvcBuilders.standaloneSetup(controller)` | Basic MVC resolver, but security integration needs setup | Not automatic | No |
| `@WebMvcTest` + MockMvc + Spring Security test | Yes | Yes if security filters are applied | No |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Yes | Usually yes, per test config | No if using `oidcLogin()` only |
| Integration test with fake/test OP | Yes | Yes | Can test authorize/token/JWT validation |
| Browser E2E with OP sandbox | Yes | Yes | Yes, including redirects/cookies/proxies in scope |

**Lesson focus:** testing Servlet controllers with Spring MVC Test and `spring-security-test`, without running a real Authorization Code flow for every test method.

### 3.1. When Is Calling the Controller Directly Enough?

A unit test:

```java
OidcUser user = ...;
UserProfile result = controller.me(user);
```

can test DTO mapping logic from `OidcUser`.

However, it **does not prove**:

- `@AuthenticationPrincipal` is resolved properly.
- `SecurityContext` actually holds an OIDC principal.
- Unauthenticated requests are blocked.
- URL authorization rules/CSRF are active.
- Exception handling and JSON serialization work.

When the task is **testing a controller using `@AuthenticationPrincipal`**, include at least one test via **MockMvc**.

## 4. Dependencies for Servlet Tests

Gradle example for a Spring Boot Servlet app:

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

`spring-security-test` provides utilities such as:

- `SecurityMockMvcRequestPostProcessors.oidcLogin()`.
- `SecurityMockMvcRequestPostProcessors.oauth2Login()`.
- `SecurityMockMvcRequestPostProcessors.user(...)`.
- `SecurityMockMvcRequestPostProcessors.authentication(...)`.
- `SecurityMockMvcRequestPostProcessors.securityContext(...)`.
- `SecurityMockMvcRequestPostProcessors.csrf()`.
- `@WithMockUser`.
- `@WithAnonymousUser`.
- `@WithSecurityContext`.

Most examples use **JUnit Jupiter/JUnit 5**, Java 17+, and modern Spring Security APIs. Package names, builder methods, and mocking annotations may differ across Spring Boot/Spring Security versions. In real projects, keep versions aligned through the BOM/dependency management.

### 4.1. Common Static Imports

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oauth2Login;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;

import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;

import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
```

These imports are line-wrapped for readability. In real Java files, write each `import` as **a single valid statement on one line or wrapped per Java syntax**; illustrative snippets do not aim to show complete source files.

## 5. Sample Controller Using `@AuthenticationPrincipal OidcUser`

Suppose an API returns the minimal identity of an OIDC-logged-in user:

```java
package example.portal.web;

import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public ResponseEntity<MeResponse> me(
            @AuthenticationPrincipal OidcUser user) {

        if (user == null) {
            return ResponseEntity.status(401).build();
        }

        String subject = user.getSubject();

        String email = user.getClaimAsString("email");

        String issuer =
            user.getIdToken().getClaimAsString("iss");

        return ResponseEntity.ok(
            new MeResponse(subject, email, issuer));
    }

    public record MeResponse(
        String subject,
        String email,
        String issuer
    ) {}
}
```

**Why include the `user == null` branch?** The example gives the controller predictable behavior even if the endpoint is `permitAll`, called directly in a unit test, or receives the wrong authentication principal type. In a production API protected with `.authenticated()`, unauthenticated requests are normally rejected by Spring Security **before the controller executes**.

**Note:** If `@AuthenticationPrincipal` is configured with `errorOnInvalidType = true`, a mismatched principal type throws an exception before the method is invoked instead of passing `null`.

### 5.1. Never Return All Claims to the Client

The example controller returns only three fields to illustrate testing. In production:

- Never return raw `id_token`, `access_token`, or `refresh_token`.
- Do not blindly return all of `OidcUser.getClaims()`, as they may contain PII.
- `sub` + `iss` should serve as internal identifiers according to trust/tenant policy.
- If `email` is unneeded, omit it from the response.
- Never treat `email` as proof of permission or tenant membership.
- Control `Cache-Control` headers if the endpoint returns sensitive identity data.

## 6. `@WebMvcTest` Testing a Controller with `oidcLogin()`

To test **MVC argument resolution** without starting the entire application/database/IdP, you can use `@WebMvcTest`.

### 6.1. Test Security Configuration

When testing injection, you can provide a minimal security chain:

```java
@WebMvcTest(MeController.class)
@Import(MeControllerTest.TestSecurity.class)
class MeControllerTest {

    @Autowired
    MockMvc mvc;

    @TestConfiguration
    static class TestSecurity {

        @Bean
        SecurityFilterChain securityFilterChain(
                HttpSecurity http) throws Exception {

            return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/me").authenticated()
                    .anyRequest().permitAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        }
    }

    // Test methods in the following sections.
}
```

**Why use `httpBasic` instead of `oauth2Login` in this slice test?**

Because the test **does not test the login flow with an OP**, and only wants to verify:

- The security filter chain accepts a test-mocked `Authentication`.
- `@AuthenticationPrincipal` resolves `OidcUser` properly.
- `@GetMapping` returns the right JSON.
- Unauthenticated requests are blocked.

Using `httpBasic()` in a **test-only chain** also makes unauthenticated requests return `401` instead of redirecting to a login page. If you want to test **production security config**, write a separate context/integration test rather than substituting the chain with a test config.

The snippet above requires JUnit 5, Spring Boot Test, Spring Test, Spring Security, and Spring MVC Test imports. `@WebMvcTest` loads only the MVC slice; controller dependencies (services, repositories) must be mocked if present.

### 6.2. Testing `oidcLogin()` with Custom Claims

```java
@Test
void meReturnsSubjectEmailAndIssuerFromOidcPrincipal()
        throws Exception {

    mvc.perform(get("/api/me")
            .with(oidcLogin()
                .idToken(idToken -> idToken
                    .claim("sub", "user-acme-42")
                    .claim("email", "alice@example.test")
                    .claim("iss",
                        "https://idp.example.test/realms/acme")
                    .claim("aud", List.of("portal-web")))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject")
            .value("user-acme-42"))
        .andExpect(jsonPath("$.email")
            .value("alice@example.test"))
        .andExpect(jsonPath("$.issuer")
            .value("https://idp.example.test/realms/acme"));
}
```

`oidcLogin()` creates a test authentication/principal and configures the request `SecurityContext`. The consumer passed to `.idToken(...)` customizes claims on the **mock ID Token** used to construct `OidcUser`.

What is verified:

1. MockMvc routes through the Spring MVC endpoint.
2. The Spring Security test post-processor puts OIDC authentication on the request.
3. `@AuthenticationPrincipal` receives `OidcUser`.
4. The method reads claims and builds the DTO properly.
5. Jackson serializes the response to JSON.

**What is NOT verified:** the test does not prove a real OP signed a valid ID Token, that the actual issuer/audience match, that authorization code/state/nonce/PKCE were validated, or that token exchange succeeded.

### 6.3. Testing Missing Optional Claims

OIDC `email` is not always present, even when the client requests the `email` scope. The controller must define a clear contract:

- Return `null` when email is absent.
- Return a fallback value **that does not cause identity confusion**.
- Require email per business rules and return a controlled business error.
- Never fabricate an email from `sub`.

A test:

```java
@Test
void meAllowsMissingOptionalEmailClaim()
        throws Exception {

    mvc.perform(get("/api/me")
            .with(oidcLogin()
                .idToken(idToken -> idToken
                    .claim("sub", "user-without-email")
                    .claim("iss", "https://idp.example.test")
                    .claims(claims -> claims.remove("email")))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject")
            .value("user-without-email"))
        .andExpect(jsonPath("$.email").doesNotExist());
}
```

**Note on JSON serialization:** Jackson typically serializes a `null` field as JSON `null` unless configured to exclude nulls. Depending on configuration, `.doesNotExist()` can match missing or null in JsonPath matchers; if your API contract distinguishes **omitted field** from **null-valued field**, use an explicit JSON assertion matching your project's serializer.

If `claims(...)`/consumer API is unavailable in your Spring Security version, construct a mock `OidcIdToken`/`OidcUser` and pass it via `.oidcUser(...)`. Always verify against your exact version.

## 7. `@WithMockUser` Does Not Replace `oidcLogin()`

A seemingly reasonable test:

```java
@Test
@WithMockUser(username = "alice")
void meWithMockUser() throws Exception {
    mvc.perform(get("/api/me"))
        .andExpect(status().isOk());
}
```

Yet for the controller:

```java
@GetMapping("/api/me")
MeResponse me(@AuthenticationPrincipal OidcUser user) {
    return new MeResponse(
        user.getSubject(), null, null);
}
```

`@WithMockUser` creates a standard `UserDetails` principal. It is **not** an `OidcUser`.

### 7.1. Outcome Depends on Parameter and Resolver

When the actual principal type is not assignable to the parameter:

```java
@AuthenticationPrincipal OidcUser user
```

the default resolver returns `null` when `errorOnInvalidType` is at its default `false`. Dereferencing `user` in the controller then causes an NPE.

If configured as:

```java
@AuthenticationPrincipal(errorOnInvalidType = true)
OidcUser user
```

the Spring Security resolver throws a type-mismatch error upon seeing the wrong principal type.

Do not assume a wrong principal type becomes `401`. **The request is already authenticated** by `@WithMockUser`; the HTTP `.authenticated()` filter lets it reach the controller. Failure when resolving/handling the principal is a **type/test-fixture error**, not an unauthenticated request.

### 7.2. When Is `@WithMockUser` Right?

It is appropriate when the controller only needs:

```java
@GetMapping("/api/name")
String name(Authentication authentication) {
    return authentication.getName();
}
```

or:

```java
@GetMapping("/api/user")
String user(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
```

or when testing role-based URL/method authorization that **does not depend** on OIDC claims.

A practical rule:

| Controller parameter | Test helper to consider |
| --- | --- |
| `@AuthenticationPrincipal UserDetails` | `@WithMockUser` or `.with(user(...))` |
| `@AuthenticationPrincipal OAuth2User` | `.with(oauth2Login())` |
| `@AuthenticationPrincipal OidcUser` | `.with(oidcLogin())` |
| `@AuthenticationPrincipal Jwt` | `.with(jwt())` when Resource Server uses JWT |
| Generic `Authentication` or `Principal` | `@WithMockUser`, `authentication(...)`, or OIDC helpers per goal |
| Custom domain principal | `@WithSecurityContext` or `authentication(...)` with matching principal type |
| Authorized client token | Dedicated `OAuth2AuthorizedClient` helpers/fixtures and manager/service |

**Remember:** `oauth2Login()` creates an OAuth2 login context; `oidcLogin()` creates an OIDC login context. Do not treat the two principal types as equivalent merely because both carry an attribute map.

## 8. Testing Controllers Using `OAuth2User`

An OAuth2 provider without OIDC support can return OAuth2 user attributes **without an ID Token**.

Controller:

```java
@RestController
class OAuth2ProfileController {

    @GetMapping("/api/oauth2-profile")
    Map<String, String> profile(
            @AuthenticationPrincipal OAuth2User user) {

        if (user == null) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED);
        }

        return Map.of(
            "name", user.getName(),
            "providerUserId",
                String.valueOf(user.getAttribute("id")));
    }
}
```

Test with `oauth2Login()`:

```java
@Test
void oauth2ProfileReadsUserAttributes() throws Exception {
    mvc.perform(get("/api/oauth2-profile")
            .with(oauth2Login()
                .attributes(attrs -> {
                    attrs.put("id", "provider-user-17");
                    attrs.put("name", "Alice");
                })))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.name").value("Alice"))
        .andExpect(jsonPath("$.providerUserId")
            .value("provider-user-17"));
}
```

**What to check:** `OAuth2User.getName()` depends on the `nameAttributeKey` chosen by `DefaultOAuth2User` or provider mapping. If a provider uses `"id"` instead of `"name"` as its name attribute, build a matching fixture or custom `OAuth2User`.

Do not assume every OAuth2 provider returns identical claim names: GitHub uses `id`/`login`, others use `sub` or custom fields. Differences belong in the user service/attribute mapper rather than sprinkling uncontrolled fallbacks across controllers.

### 8.1. Does `oauth2Login()` Replace OIDC Login Tests?

If the controller declares:

```java
@AuthenticationPrincipal OidcUser user
```

then `.with(oauth2Login())` typically **does not produce the right OIDC principal**. Conversely, `OidcUser` is a subtype of `OAuth2User`, yet controllers relying on ID Token/issuer/nonce still need an OIDC-specific fixture.

Pick the helper matching the **`Authentication` type production creates**, not merely because both contain attribute maps.

## 9. `@AuthenticationPrincipal(expression = "...")`: Testing Extracted Values

The annotation supports **Spring Expression Language (SpEL)** to extract a portion of the principal.

Example:

```java
@RestController
class SubjectController {

    @GetMapping("/api/subject")
    Map<String, String> subject(
        @AuthenticationPrincipal(
            expression = "attributes['sub']")
        String subject) {

        if (subject == null) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED);
        }

        return Map.of("subject", subject);
    }
}
```

Test:

```java
@Test
void subjectExpressionUsesOidcClaims() throws Exception {
    mvc.perform(get("/api/subject")
            .with(oidcLogin()
                .idToken(token -> token
                    .claim("sub", "subject-123"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject")
            .value("subject-123"));
}
```

Here, the `attributes['sub']` expression accesses attributes on the OIDC principal, not JSON from the request.

### 9.1. Difference Between `attributes` and `idToken.claims`

An `OidcUser` can hold:

- `OidcIdToken` claims.
- `OidcUserInfo` claims.
- `getAttributes()`, a combined attribute view assembled by the OIDC user service.

If business logic explicitly needs the **ID Token's subject**, you can use:

```java
@AuthenticationPrincipal(
    expression = "idToken.claims['sub']")
String subject
```

Understand that the expression accesses JavaBean properties such as `getIdToken()` and `getClaims()`. If the principal is not an `OidcUser`, expression evaluation may fail rather than silently returning null.

Avoid embedding long, security-sensitive authorization SpEL expressions inside controller parameter signatures. For tenant membership, ownership, or entitlements, invoke a dedicated, separately tested domain authorization service.

### 9.2. Testing Expressions When a Claim Is Absent

Example:

```java
@GetMapping("/api/handle")
String handle(
    @AuthenticationPrincipal(
        expression = "attributes['preferred_username']")
    String preferredUsername) {

    return preferredUsername == null
        ? "anonymous-handle"
        : preferredUsername;
}
```

Verify:

```text
Claim preferred_username = "alice" -> "alice".
Claim preferred_username absent -> appropriate fallback.
Principal not an OAuth2User -> expression evaluation may error.
```

Never treat `preferred_username` or `email` as a unique identity key if the provider permits changing those fields.

### 9.3. `errorOnInvalidType`

```java
@GetMapping("/api/strict-me")
String strictMe(
        @AuthenticationPrincipal(errorOnInvalidType = true)
        OidcUser user) {

    return user.getSubject();
}
```

`errorOnInvalidType = true` surfaces type mismatches explicitly instead of silently injecting `null`.

Your test suite should cover:

1. `oidcLogin()` -> matching parameter type, endpoint succeeds.
2. `@WithMockUser` -> wrong type, request is not processed as an OIDC user.
3. Anonymous request -> blocked by security layer or handled per contract.

**Do not hardcode an expectation of HTTP 500** for type mismatches unless your exception handler/test environment defines that status; assert the exception type or contract your application actually guarantees.

## 10. Creating Custom Meta-Annotations for OIDC Principals

When many controllers require `OidcUser`, you can define:

```java
@Target({
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@AuthenticationPrincipal
public @interface CurrentOidcUser {
}
```

Then:

```java
@GetMapping("/api/me")
MeResponse me(@CurrentOidcUser OidcUser user) {
    return new MeResponse(
        user.getSubject(),
        user.getClaimAsString("email"),
        user.getIdToken().getClaimAsString("iss"));
}
```

Spring Security supports meta-annotations based on `@AuthenticationPrincipal` to keep controller signatures cleaner and express domain concepts.

### 10.1. Meta-Annotations with SpEL

You can define an annotation that extracts the user's ID from the principal:

```java
@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
@AuthenticationPrincipal(
    expression = "attributes['sub']")
public @interface CurrentSubject {
}
```

Usage:

```java
@GetMapping("/api/subject")
String subject(@CurrentSubject String subject) {
    return subject;
}
```

Test with `oidcLogin()`:

```java
@Test
void currentSubjectAnnotationResolvesOidcSub()
        throws Exception {

    mvc.perform(get("/api/subject")
            .with(oidcLogin()
                .idToken(token -> token
                    .claim("sub", "s-007"))))
        .andExpect(status().isOk())
        .andExpect(content().string("s-007"));
}
```

**Note:** Custom annotations must be tested through the Spring MVC argument resolver. Calling the controller method directly will not test annotation wiring.

## 11. Testing a Controller Accepting Both Principal and `Authentication`

An endpoint sometimes needs both `OidcUser` and the registration ID:

```java
@RestController
class IdentityContextController {

    @GetMapping("/api/identity-context")
    Map<String, String> current(
            @AuthenticationPrincipal OidcUser user,
            Authentication authentication) {

        if (!(authentication instanceof OAuth2AuthenticationToken t)) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED);
        }

        if (user == null) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED);
        }

        return Map.of(
            "subject", user.getSubject(),
            "registrationId",
            t.getAuthorizedClientRegistrationId());
    }
}
```

Test:

```java
@Test
void returnsRegistrationIdFromOAuth2Authentication()
        throws Exception {

    mvc.perform(get("/api/identity-context")
            .with(oidcLogin()
                .clientRegistration(
                    ClientRegistration.withRegistrationId("corporate")
                        .clientId("portal-web")
                        .clientSecret("FAKE_TEST_SECRET")
                        .clientAuthenticationMethod(
                            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                        .authorizationGrantType(
                            AuthorizationGrantType.AUTHORIZATION_CODE)
                        .redirectUri(
                            "{baseUrl}/login/oauth2/code/{registrationId}")
                        .authorizationUri("https://idp.example.test/auth")
                        .tokenUri("https://idp.example.test/token")
                        .jwkSetUri("https://idp.example.test/keys")
                        .scope("openid")
                        .build())
                .idToken(token -> token
                    .claim("sub", "user-88"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registrationId")
            .value("corporate"))
        .andExpect(jsonPath("$.subject")
            .value("user-88"));
}
```

**Goal:** ensure `Authentication` belongs to the expected registration, not just that the principal has the right `sub`. `ClientRegistration` here is a **test fixture**; its endpoints are fake URLs and no network requests occur.

In multi-tenant systems, a test with `registrationId = corporate` does not prove the user has entitlement to the corporate tenant. **Tenant authorization** is a separate step.

### 11.1. Use `@CurrentSecurityContext` If You Need Another Part of the Context

Spring Security also provides:

```java
@CurrentSecurityContext
```

Use it to access `SecurityContext` or evaluate an expression on the context:

```java
@GetMapping("/api/auth-name")
String authenticationName(
    @CurrentSecurityContext(
        expression = "authentication.name")
    String name) {

    return name;
}
```

This differs from `@AuthenticationPrincipal`, which extracts `authentication.principal` first and evaluates any expression on the principal.

## 12. Testing Unauthenticated Requests

A controller using `@AuthenticationPrincipal` typically sits behind:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/me").authenticated());
```

If the request lacks `Authentication`:

```java
@Test
void unauthenticatedRequestIsRejected()
        throws Exception {

    mvc.perform(get("/api/me"))
        .andExpect(status().isUnauthorized());
}
```

**This test assumes** the test security chain uses an HTTP Basic entry point as in section 6. If production uses `oauth2Login()`, an unauthenticated browser request may be **redirected (302)** to the login page or Authorization Endpoint depending on configuration. For REST APIs, you can configure an entry point returning 401 on API paths.

Therefore, **do not hardcode**:

```text
Unauthenticated -> always HTTP 401
```

and instead verify the **configured contract**:

| Security config | Typical unauthenticated request outcome |
| --- | --- |
| `httpBasic()` for API | HTTP 401 + `WWW-Authenticate` |
| `oauth2Login()` for browser UI | HTTP 302 to login page/authorization request |
| Custom JSON `AuthenticationEntryPoint` | HTTP 401 + JSON error |
| `permitAll` endpoint | Controller may receive `null` principal |
| `anonymous()` per access policy | `AnonymousAuthenticationToken` may be permitted |

### 12.1. Public Controllers May Receive `null`

Example:

```java
@GetMapping("/public/welcome")
String welcome(
        @AuthenticationPrincipal OidcUser user) {

    return user == null
        ? "Welcome, guest"
        : "Welcome, " + user.getSubject();
}
```

Tests:

```java
@Test
void publicWelcomeForAnonymous() throws Exception {
    mvc.perform(get("/public/welcome"))
        .andExpect(status().isOk())
        .andExpect(content().string("Welcome, guest"));
}

@Test
void publicWelcomeForOidcUser() throws Exception {
    mvc.perform(get("/public/welcome")
            .with(oidcLogin()
                .idToken(t -> t.claim("sub", "alice"))))
        .andExpect(status().isOk())
        .andExpect(content().string("Welcome, alice"));
}
```

**Note:** The endpoint must truly be `permitAll` in the test security config. If the test config from section 6 only requires authentication for `"/api/me"` and permits everything else, both tests can work once the controller is loaded into the MVC context.

### 12.2. Do Not Use `@WithAnonymousUser` and Expect OIDC Claims

An anonymous principal is typically a string/anonymous representation. For an `OidcUser` parameter, the default resolver will not synthesize an ID Token and in most cases injects `null`.

The behavior to test is that **public endpoints return minimal data** or **protected endpoints deny access**, rather than trying to attach a fake OIDC identity to anonymous requests.

## 13. Testing Access Control: A Valid Principal Is Not Enough

A user with a valid `OidcUser` is not automatically authorized for every endpoint.

Example security config:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**")
        .hasAuthority("SCOPE_reports.admin")
    .anyRequest().authenticated());
```

`oidcLogin()` creates a principal, but the mock's default authorities may **differ** from authorities assigned by the app's mapper in production.

To test specific roles/authorities:

```java
@Test
void readOnlyOidcUserCannotAccessAdmin()
        throws Exception {

    mvc.perform(get("/api/admin/reports")
            .with(oidcLogin()
                .authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_reports.read"))))
        .andExpect(status().isForbidden());
}
```

And:

```java
@Test
void adminAuthorityAllowsAccess()
        throws Exception {

    mvc.perform(get("/api/admin/reports")
            .with(oidcLogin()
                .authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_reports.admin"))))
        .andExpect(status().isOk());
}
```

These tests assume the URL mapping/handler and security chain are loaded. Mocking the right authorities does not prove the OP actually issued that scope/role or that the app's JWT/UserInfo mapper works; write separate integration tests for the authorities mapper if it is security-critical.

### 13.1. Never Trust Authorities from a Client-Supplied Header

An anti-pattern:

```java
@GetMapping("/api/admin")
String admin(
        @RequestHeader("X-Role") String role,
        @AuthenticationPrincipal OidcUser user) {
    // trusts X-Role from the browser
}
```

A browser can send any `X-Role: ADMIN` header. Security tests should intentionally send this header on a request with read-only authorities and assert that access **is still denied**.

`@AuthenticationPrincipal` provides the security identity established by the authentication layer; authorization must still check trusted **server-side authorities/entitlements**.

## 14. Testing Multi-Tenancy: Never Derive Tenant Blindly from an OIDC Claim

A SaaS system might use:

```text
registrationId = acme__oidc
issuer         = https://id.example.test/realms/acme
sub            = user-17
```

A user logged in via Acme sends:

```text
GET /api/tenants/beta/reports
```

Never assume the user has Beta access simply because `OidcUser` is non-null.

### 14.1. Controller + Authorization Service

```java
@RestController
class TenantProfileController {

    private final TenantAuthorization tenantAuthorization;

    TenantProfileController(
            TenantAuthorization tenantAuthorization) {
        this.tenantAuthorization = tenantAuthorization;
    }

    @GetMapping("/api/tenants/{tenantId}/profile")
    Map<String, String> profile(
            @PathVariable String tenantId,
            @AuthenticationPrincipal OidcUser user) {

        if (user == null) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED);
        }

        String issuer =
            user.getIdToken().getClaimAsString("iss");

        tenantAuthorization.requireMembership(
            tenantId,
            issuer,
            user.getSubject());

        return Map.of(
            "tenantId", tenantId,
            "subject", user.getSubject());
    }
}
```

`TenantAuthorization` is an **application-defined internal service interface**, for example:

```java
interface TenantAuthorization {
    void requireMembership(
        String tenantId,
        String issuer,
        String subject);
}
```

The service must verify membership/entitlements from a trusted source, never granting access solely from the raw URL path or email domain.

### 14.2. Slice Test with a Mocked Service

With Spring Framework 6.2+/compatible Spring Boot versions, you can use `@MockitoBean`:

```java
@WebMvcTest(TenantProfileController.class)
@Import(TestSecurity.class)
class TenantProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    TenantAuthorization tenantAuthorization;

    @Test
    void sendsVerifiedIdentityToMembershipService()
            throws Exception {

        mvc.perform(get("/api/tenants/acme/profile")
                .with(oidcLogin()
                    .idToken(token -> token
                        .claim("sub", "subject-17")
                        .claim("iss",
                            "https://id.example.test/realms/acme"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.tenantId").value("acme"));

        verify(tenantAuthorization).requireMembership(
            "acme",
            "https://id.example.test/realms/acme",
            "subject-17");
    }
}
```

`@MockitoBean` lives in package:

```java
org.springframework.test.context.bean.override.mockito.MockitoBean
```

In older Spring Boot versions, tests use Spring Boot Test's `@MockBean`. Never mix both annotations arbitrarily; choose according to your BOM/versions. `verify(...)` comes from Mockito.

**Important limitation:** A Mockito mock only proves the controller **invokes the right service with the right arguments**. It does not prove the service's membership/authorization policy is secure. Write separate tests for the service and integration tests when domain security is critical.

### 14.3. Testing Cross-Tenant Denial

With Mockito, you can stub:

```java
doThrow(new AccessDeniedException(
    "Tenant membership required"))
    .when(tenantAuthorization)
    .requireMembership(
        eq("beta"),
        eq("https://id.example.test/realms/acme"),
        eq("subject-17"));
```

Then send:

```text
GET /api/tenants/beta/profile
OIDC issuer = Acme
subject     = subject-17
```

Expected: **never return Beta's profile**. The HTTP status is typically `403` when Spring Security exception translation/controller error handling is configured appropriately; verify against your actual security configuration.

Never fix a failing test by making the service "accept every tenant" to produce a 200 response.

## 15. Customizing the Full `OidcUser` in MockMvc

Sometimes `.idToken(...)` is not enough. For example, a controller may need:

- `OidcUserInfo` from the UserInfo Endpoint.
- A customized `getName()` property.
- Pre-mapped authorities.
- A custom `OidcUser` implementation.
- A non-default name attribute key.
- Nested structured claims (groups, organization, locale).

You can build the OIDC principal explicitly:

```java
Instant issuedAt = Instant.now().minusSeconds(10);
Instant expiresAt = Instant.now().plusSeconds(300);

OidcIdToken idToken = new OidcIdToken(
    "FAKE_ID_TOKEN",
    issuedAt,
    expiresAt,
    Map.of(
        "iss", "https://idp.example.test",
        "sub", "user-17",
        "aud", List.of("portal-web")));

OidcUserInfo userInfo = new OidcUserInfo(
    Map.of(
        "sub", "user-17",
        "email", "alice@example.test",
        "preferred_username", "alice"));

OidcUser principal = new DefaultOidcUser(
    List.of(new SimpleGrantedAuthority("ROLE_USER")),
    idToken,
    userInfo,
    "sub");
```

Then:

```java
mvc.perform(get("/api/me")
        .with(oidcLogin().oidcUser(principal)))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.subject").value("user-17"));
```

This fixture is built using Spring Security's `OidcIdToken`, `OidcUserInfo`, and `DefaultOidcUser` APIs. `"FAKE_ID_TOKEN"` is not an OP-signed JWT; the MockMvc helper does not contact any OP to validate it.

### 15.1. Testing Missing UserInfo

Some providers do not use UserInfo or omit expected claims. Controller tests should confirm behavior when the principal only has an ID Token without UserInfo:

```java
OidcUser user = new DefaultOidcUser(
    List.of(new SimpleGrantedAuthority("ROLE_USER")),
    idToken);
```

If business logic requires an email, define explicit behavior when email is absent. Never assume every `OidcUser` carries email, roles, or groups.

### 15.2. Testing Custom `getName()`

When `DefaultOidcUser` takes `nameAttributeKey = "preferred_username"` or a similar attribute, `getName()` may differ from `sub`.

Test cases should distinguish:

```text
subject = "user-17"
preferred_username = "alice"
getName() = "alice" per configured nameAttributeKey
```

If a value used as a security principal key must be immutable, use subject + issuer rather than a display username.

## 16. Creating a Custom `@WithSecurityContext` for Multiple Test Methods

When dozens of controller tests share the same OIDC identity, repeating `.with(oidcLogin().idToken(...))` on every request can get verbose. Spring Security Test lets you create a custom test annotation via:

```java
@WithSecurityContext
```

### 16.1. Defining the Annotation

```java
@Target({
    ElementType.METHOD,
    ElementType.TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@WithSecurityContext(
    factory = WithTestOidcUserFactory.class)
public @interface WithTestOidcUser {

    String sub() default "test-user";

    String issuer()
        default "https://idp.example.test/realms/acme";

    String registrationId() default "corporate";
}
```

This annotation is project-defined, **not built into Spring Security**.

### 16.2. Factory Building the `SecurityContext`

```java
public final class WithTestOidcUserFactory
    implements WithSecurityContextFactory<WithTestOidcUser> {

    @Override
    public SecurityContext createSecurityContext(
            WithTestOidcUser annotation) {

        Instant now = Instant.now();

        OidcIdToken idToken = new OidcIdToken(
            "FAKE_TEST_ID_TOKEN",
            now.minusSeconds(5),
            now.plusSeconds(300),
            Map.of(
                "iss", annotation.issuer(),
                "sub", annotation.sub(),
                "aud", List.of("portal-web")));

        OidcUser oidcUser = new DefaultOidcUser(
            List.of(new SimpleGrantedAuthority("ROLE_USER")),
            idToken);

        Authentication authentication =
            new OAuth2AuthenticationToken(
                oidcUser,
                oidcUser.getAuthorities(),
                annotation.registrationId());

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();

        context.setAuthentication(authentication);
        return context;
    }
}
```

The goal is testing the **exact principal type** and `OAuth2AuthenticationToken` per production contract, not just setting a username string.

### 16.3. Using the Annotation

```java
@Test
@WithTestOidcUser(
    sub = "s-123",
    registrationId = "corporate")
void returnsSubjectWithoutPerRequestPostProcessor()
        throws Exception {

    mvc.perform(get("/api/me"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject")
            .value("s-123"));
}
```

When `MockMvc`/Spring Security `TestContext` is configured properly, the annotation populates `SecurityContext` for the test request.

**When should you use which approach?**

- A few test cases needing per-request claim variations: use `.with(oidcLogin())`.
- A large test class sharing a standard identity fixture: consider `@WithTestOidcUser`.
- Multiple requests inside **one test** using different users: request post-processors are usually clearer.
- Integration-testing real OIDC callback/token validation: **never** treat a synthetic `@WithSecurityContext` as protocol proof.

### 16.4. Preventing `SecurityContext` Leakage Between Tests

Spring Security's `TestContext` normally manages lifecycle cleanup, yet custom utilities or manual `SecurityContextHolder.setContext(...)` calls can leave stale contexts on reused threads.

If setting up the context manually in unit tests outside framework support:

```java
try {
    SecurityContextHolder.setContext(context);
    // run assertions
} finally {
    SecurityContextHolder.clearContext();
}
```

In MockMvc tests, prefer official helpers over mutating static/thread-local state manually. Never store a global static `Authentication` shared by all tests if it risks cross-test leakage.

## 17. `MockMvcBuilders.standaloneSetup(...)` and `springSecurity()`

A common cause of "controller receives a null principal" is constructing `MockMvc` via:

```java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(controller)
    .build();
```

This **does not configure the full Spring Security filter chain**. The `oidcLogin()` request post-processor is designed to work with Spring Security Test and an appropriate security filter/context setup.

When building MockMvc manually:

```java
MockMvc mvc = MockMvcBuilders
    .webAppContextSetup(webApplicationContext)
    .apply(springSecurity())
    .build();
```

This is the standard approach when the context holds a matching `springSecurityFilterChain`. Static import:

```java
import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;
```

### 17.1. Why Does Applying `springSecurity()` Matter?

It integrates security filters and the test helpers required to populate `Authentication` into `SecurityContext` properly. Building standalone MockMvc and calling `.with(oidcLogin())` can still yield a null or unexpected principal depending on setup.

### 17.2. Can You Use Standalone Setup?

Yes, but you must **configure the matching security filter chain and argument resolvers** if you intend to test security context injection. That is easy to get wrong and diverges from production.

For testing `@AuthenticationPrincipal`, **`@WebMvcTest` with auto-configured MockMvc** or `webAppContextSetup(...).apply(springSecurity())` is usually much clearer. Standalone setup fits controller logic unit tests where you pass the principal directly as a parameter.

### 17.3. Avoid Disabling the Filter Chain in Tests

Omitting Spring Security filters from MockMvc or using `@AutoConfigureMockMvc(addFilters = false)` can cause:

- Protected endpoints to return data to anonymous requests in tests.
- Request post-processors to stop behaving like production.
- `@AuthenticationPrincipal` to miss the proper context.
- `401`, `403`, and CSRF tests to become meaningless.

Only disable filters when a test **intentionally** narrows its scope, and never cite those results as proof that security integration works.

## 18. `@SpringBootTest` and `@AutoConfigureMockMvc`

When you need to run the controller with a security configuration closer to production:

```java
@SpringBootTest
@AutoConfigureMockMvc
class MeControllerIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void oidcPrincipalReachesController()
            throws Exception {

        mvc.perform(get("/api/me")
                .with(oidcLogin()
                    .idToken(t -> t.claim(
                        "sub", "integration-user"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject")
                .value("integration-user"));
    }
}
```

**Differences from `@WebMvcTest`:**

- Loads more beans and application configuration.
- May require test datasources/profiles/config secrets.
- Uses the production-style `SecurityFilterChain` unless overridden by the test.
- Still **does not run a real OIDC Authorization Code flow** when using `oidcLogin()`.

To verify that Spring Security parses ID Tokens from the Token Endpoint, validates issuer/audience/nonce, and constructs `OidcUser`, add tests using an OP sandbox or a fake token endpoint with appropriate signing keys.

### 18.1. When a Full-Context Test Fails to Start

An application configuring:

```java
.oauth2Login(...)
```

may require a valid `ClientRegistrationRepository`. If the test profile lacks OIDC issuer metadata or registrations, startup can fail due to a missing bean/config. That is a **test context configuration issue**, not an `@AuthenticationPrincipal` bug.

You can:

- Provide a test `ClientRegistrationRepository` with fake endpoints.
- Mock out-of-scope collaborators.
- Use `@WebMvcTest` with a test `SecurityFilterChain` as in section 6.
- Separate protocol integration tests with a dedicated test OP.

Never put production client secrets or real accounts in controller tests.

## 19. HTTP Request Post-Processor vs. Method-Level Annotation

Two common ways to attach a mock `Authentication`:

### 19.1. Per HTTP Request

```java
mvc.perform(get("/api/me")
    .with(oidcLogin()));
```

Advantages:

- Explicit right on the request.
- Easy to test multiple principals within a single test.
- Easy to vary attributes/authorities/registration ID.
- Easy to build positive/negative matrices for the same endpoint.

### 19.2. On the Test Method/Class

```java
@Test
@WithTestOidcUser(sub = "alice")
void testMe() throws Exception {
    mvc.perform(get("/api/me"))
       .andExpect(status().isOk());
}
```

Advantages:

- Concise for repeated fixtures.
- Readable for test classes sharing a single default identity.

Disadvantages:

- With complex request setups, it may be less obvious which `Authentication` is active.
- Combining `@WithMockUser` and `.with(oidcLogin())` in the same test makes the **effective `Authentication` depend on setup/ordering**; avoid overlapping fixtures unnecessarily.
- Requires proper Spring Security Test `TestContext` integration.

**Recommendation:** give each test one **clear principal source**, avoiding mixing annotations and post-processors with differing identities unless intentionally testing precedence.

## 20. `@AuthenticationPrincipal` Does Not Fetch `OAuth2AuthorizedClient`

An OIDC Login controller may simultaneously need:

```java
@AuthenticationPrincipal OidcUser user
```

and an authorized client:

```java
@RegisteredOAuth2AuthorizedClient("corporate")
OAuth2AuthorizedClient authorizedClient
```

Both annotations pull data from **two different sources**.

| Annotation | Object | Source |
| --- | --- | --- |
| `@AuthenticationPrincipal` | `OidcUser`, `OAuth2User`, `UserDetails`, `Jwt`... | `Authentication.getPrincipal()` |
| `@RegisteredOAuth2AuthorizedClient` | `OAuth2AuthorizedClient` | Authorized-client repository/service/manager and registration |
| `@CurrentSecurityContext` | `SecurityContext` or expression | Current `SecurityContext` |

If a controller writes:

```java
@GetMapping("/api/downstream")
String downstream(
        @AuthenticationPrincipal OidcUser user,
        @RegisteredOAuth2AuthorizedClient("corporate")
        OAuth2AuthorizedClient client) {

    // user is identity.
    // client.getAccessToken() is the OAuth2 token for the API.
    return user.getSubject();
}
```

then:

```java
.with(oidcLogin())
```

must not be treated as **sufficient proof** that the authorized-client store already holds a token for every registration. Although the test helper can set up an OAuth2 login context, the lifecycle and persistence of authorized clients still need dedicated fixtures/tests matching the resolver/service the controller uses.

### 20.1. When You Need to Test the Bearer Token

Suppose a service calls a downstream API. Mock the service/client adapter or stand up a fake API server and assert:

- The token comes from the right authorized client.
- The access token is not an ID Token.
- The registration ID/subject/tenant match.
- The token is not sent to arbitrary API hosts.
- Downstream errors are handled safely.

Never put raw bearer tokens into controller responses just to make assertions easier.

## 21. Testing the Argument Resolver with Wrong Principal Types

A thorough test suite should include these cases:

| Principal fixture | Controller expects | Baseline expectation |
| --- | --- | --- |
| `oidcLogin()` | `OidcUser` | Right type injected |
| `oidcLogin()` | `OAuth2User` | Can inject since `OidcUser` is a subtype of `OAuth2User` |
| `oauth2Login()` | `OAuth2User` | Right type injected |
| `oauth2Login()` | `OidcUser` | Mismatch; `null` or exception per annotation |
| `@WithMockUser` | `OidcUser` | Mismatch |
| `.with(jwt())` | `Jwt` | Valid when API is a JWT Resource Server |
| `.with(jwt())` | `OidcUser` | Mismatch |
| Anonymous request, protected endpoint | `OidcUser` | Security entry point blocks before controller |
| Anonymous request, public endpoint | `OidcUser` | May receive `null` |
| Custom principal | Custom parameter type | Must construct matching `Authentication` |

### 21.1. When `@AuthenticationPrincipal` Is `null` Despite an "Authenticated" Request

Investigate in order:

1. What kind of `Authentication` is in `SecurityContext`?
2. What is `authentication.getPrincipal().getClass()`? Log only the class name, never the full principal object with claims.
3. What is the controller parameter type?
4. Is `errorOnInvalidType = true` set?
5. Is a SpEL expression present?
6. Is the filter chain actually running in MockMvc?
7. Is a custom security context setup/helper overwriting the mock OIDC login?
8. Are multiple security filter chains matching different URLs?
9. Is the test using `@WithMockUser`, `oauth2Login()`, or `oidcLogin()`?
10. Does the controller's `@AuthenticationPrincipal` meta-annotation have the right retention and target?

**Never "fix" this with an unchecked cast**:

```java
OidcUser user =
    (OidcUser) SecurityContextHolder
        .getContext()
        .getAuthentication()
        .getPrincipal();
```

If the `Authentication` is genuinely not an OIDC login, that cast is equally wrong and masks configuration errors.

## 22. Testing Response and Exception Contracts

Beyond injecting the right principal, a well-designed controller needs clear response contracts.

### 22.1. Happy Path

Given: an OIDC principal with valid `sub`, issuer, and email.

When: `GET /api/me`.

Then:

- HTTP 200.
- JSON DTO contains only allowed fields.
- Subject matches.
- No access/ID/refresh tokens returned.
- Full claims containing PII are not exposed.

### 22.2. Missing Required Claim

If the application requires `sub` while a mock principal omits it, Spring Security's `OidcIdToken` or `DefaultOidcUser` may enforce its own invariants/behavior. Rather than forcing an invalid object into existence and labeling it a production OIDC response:

- Test mapper/DTO validation on invalid inputs.
- Test OIDC token validation at the protocol integration level.
- Test the controller's contract error if the application mapper can ever receive a missing identity.
- Never assume an unchecked mock `OidcUser` means a real OP would issue such an ID Token.

### 22.3. Missing Optional Email

Email may be absent. Test:

```text
email present -> DTO includes email.
email absent  -> DTO returns null/omits or raises defined business error.
```

Never fabricate a fake email from `sub` or synthesize `username@company` unless business policy explicitly mandates it.

### 22.4. Authorization Denial

Given: a validly authenticated OIDC user lacking tenant membership.

Then:

- HTTP 403 or business authorization response per policy.
- Tenant data is neither fetched nor disclosed.
- Cross-tenant responses are never cached.
- Authentication success is never equated with authorization success.

### 22.5. Sanitized Failures

When an exception occurs, responses/logs must never contain:

```text
id_token=<raw>
access_token=<raw>
refresh_token=<raw>
client_secret=<raw>
fullOidcClaims=<PII>
```

When using `@ControllerAdvice`, test safe error mapping and HTTP statuses, not merely `assertThrows`.

## 23. Testing CSRF on Controllers with HTTP POST

`@AuthenticationPrincipal` still works on POST, yet in a browser session application, POST requests can require a CSRF token:

```java
@PostMapping("/api/preferences")
ResponseEntity<Void> save(
        @AuthenticationPrincipal OidcUser user,
        @RequestBody Preferences preferences) {

    preferencesService.save(
        user.getSubject(), preferences);

    return ResponseEntity.noContent().build();
}
```

Test with CSRF token:

```java
mvc.perform(post("/api/preferences")
        .with(oidcLogin()
            .idToken(t -> t.claim("sub", "user-1")))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"theme":"dark"}
            """))
    .andExpect(status().isNoContent());
```

Test without CSRF:

```java
mvc.perform(post("/api/preferences")
        .with(oidcLogin()))
    .andExpect(status().isForbidden());
```

These tests assume **CSRF protection is enabled** in the test security chain and that method mappings and service dependencies are properly supplied. If the app uses a stateless API with a different CSRF policy, expected statuses may differ.

**Never disable CSRF globally** to fix a controller test. For OAuth2 Login backed by browser cookies, CSRF remains a vital defense.

## 24. Async Controllers and `SecurityContext` Propagation

Some Servlet controllers use asynchronous MVC:

```java
@GetMapping("/api/async-me")
Callable<String> asyncMe(
        @AuthenticationPrincipal OidcUser user) {

    return () -> "hello-" + user.getSubject();
}
```

In this example, the principal is injected **before** async work begins; the lambda captures the already-resolved reference. If a service executes on another thread and calls `SecurityContextHolder` itself, understand `SecurityContext` propagation. Spring Security supports Servlet async and provides `DelegatingSecurityContext*` wrappers for executor use cases, yet custom thread pools do not preserve context automatically.

Tests can use MockMvc async assertions:

```java
MvcResult result = mvc.perform(
        get("/api/async-me")
            .with(oidcLogin()
                .idToken(t -> t.claim("sub", "u-async"))))
    .andExpect(request().asyncStarted())
    .andReturn();

mvc.perform(asyncDispatch(result))
    .andExpect(status().isOk())
    .andExpect(content().string("hello-u-async"));
```

This is a **Servlet MockMvc** test; do not confuse it with WebFlux `Mono`/`WebTestClient`.

### 24.1. When a Service Needs `SecurityContext` on an Executor

Do not test only the output string. Verify the service receives the right principal or explicit subject parameter. For domain logic, it is best to pass the verified identity data explicitly as parameters:

```java
reportService.loadReports(
    user.getIdToken().getClaimAsString("iss"),
    user.getSubject());
```

rather than making deep business layers read `SecurityContextHolder` across threads.

## 25. Method Security and Annotation-Driven Controller Tests

A controller/service may use:

```java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
@GetMapping("/api/reports")
List<Report> reports(
        @AuthenticationPrincipal OidcUser user) {
    return reportService.forUser(user.getSubject());
}
```

For method-security annotations to actually take effect in tests, the application/test context must have **method security configuration** such as `@EnableMethodSecurity` and proper proxies.

If a `@WebMvcTest` loads only the controller without enabling method security, tests may **pass an endpoint that should have been denied**.

Distinguish:

- **Filter-chain URL rules:** `.authorizeHttpRequests(...)`.
- **Method security:** `@PreAuthorize`, `@PostAuthorize`, interceptors/proxies.
- **Domain authorization:** membership/entitlements/ownership inside services.

A test using a mock OIDC principal will not trigger all of those layers if the test context omitted them.

### 25.1. Test Both Permitted and Denied Authorities

A minimal suite:

```text
OidcUser principal + SCOPE_reports.read
    GET /api/reports -> allow

OidcUser principal without SCOPE_reports.read
    GET /api/reports -> deny

Anonymous
    GET /api/reports -> login entry point/401

Principal has scope but does not belong to tenant
    GET /api/tenants/T2/reports -> domain deny
```

**Do not merely assert that the controller's service was called** while ignoring HTTP status and authorization behavior on sensitive endpoints.

## 26. `Jwt` Principal: Distinguishing OAuth2 Client from Resource Server

A single application can simultaneously:

- Authenticate browsers via OIDC Login (`OidcUser` principal).
- Accept Bearer access tokens on an API (`Jwt` or `BearerTokenAuthentication` principal depending on token type).

These two request security flows are distinct.

Example Resource Server controller:

```java
@GetMapping("/api/service-subject")
String serviceSubject(
        @AuthenticationPrincipal Jwt jwt) {

    return jwt.getSubject();
}
```

MockMvc helper:

```java
mvc.perform(get("/api/service-subject")
        .with(jwt().jwt(token -> token
            .claim("sub", "service-user")
            .claim("aud", List.of("reports-api")))))
    .andExpect(status().isOk())
    .andExpect(content().string("service-user"));
```

Here `jwt()` comes from:

```java
SecurityMockMvcRequestPostProcessors.jwt()
```

**Never use `oidcLogin()` to test a controller expecting a Resource Server `Jwt` principal**, and never use `jwt()` to simulate an OIDC Login `OidcUser`.

### 26.1. `jwt()` Does Not Test Real JWT Signature/Audience Validation

`jwt()` sets a JWT `Authentication` directly on the test request; it does not call remote JWKS or verify signatures through the full token decoder. It suits testing controllers and selected authority mappings, **not** proving the API rejects JWTs with wrong issuer/audience/expiry.

To test the decoder:

- Use signed JWT fixtures with test JWKS/test issuer.
- Keep `JwtDecoder` validators aligned with production policy.
- Test `401 invalid_token` for wrong issuer/audience/signature/expiry.
- Never disable production JWT validation to make tests pass easily.

## 27. Separating Test Fixtures and Keeping Data Independent

When many tests need OIDC principals, use a factory:

```java
final class TestOidcUsers {

    static OidcUser user(
            String issuer,
            String subject,
            String email) {

        Instant now = Instant.now();

        Map<String, Object> claims = new HashMap<>();
        claims.put("iss", issuer);
        claims.put("sub", subject);
        claims.put("aud", List.of("portal-web"));

        if (email != null) {
            claims.put("email", email);
        }

        OidcIdToken token = new OidcIdToken(
            "FAKE_ID_TOKEN",
            now.minusSeconds(10),
            now.plusSeconds(300),
            claims);

        return new DefaultOidcUser(
            List.of(
                new SimpleGrantedAuthority("ROLE_USER")),
            token);
    }
}
```

Test:

```java
mvc.perform(get("/api/me")
        .with(oidcLogin().oidcUser(
            TestOidcUsers.user(
                "https://idp.example.test/realms/acme",
                "acme-u17",
                null))))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.subject").value("acme-u17"));
```

A factory improves consistency, yet **must not hide security assumptions**. Include separate test cases for:

- Different issuer per tenant.
- Duplicate `sub` across two issuers.
- Missing/changed email.
- Provider-specific name attribute keys.
- Missing authorities.
- Missing UserInfo.
- Wrong principal type.
- Public/anonymous requests.

Avoid using one fully populated mock ID Token with all emails/roles for every test, as it hides nullable claims and privilege boundaries.

## 28. Testing a Custom Principal Other Than `OidcUser`

An application may map OIDC claims to a domain-specific principal after authentication:

```java
public record PortalPrincipal(
    String issuer,
    String subject,
    String tenantId) {}
```

Controller:

```java
@GetMapping("/api/domain-me")
Map<String, String> me(
        @AuthenticationPrincipal PortalPrincipal user) {

    return Map.of(
        "tenantId", user.tenantId(),
        "subject", user.subject());
}
```

Default `oidcLogin()` **does not create a `PortalPrincipal`** because it creates an `OidcUser`. To test this controller, construct an `Authentication` holding the exact custom principal:

```java
PortalPrincipal user = new PortalPrincipal(
    "https://idp.example.test",
    "u-42",
    "acme");

Authentication authentication =
    new UsernamePasswordAuthenticationToken(
        user,
        "N/A",
        List.of(new SimpleGrantedAuthority("ROLE_USER")));

mvc.perform(get("/api/domain-me")
        .with(
            SecurityMockMvcRequestPostProcessors
                .authentication(authentication)))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.tenantId").value("acme"));
```

This is a **test fixture**; using `UsernamePasswordAuthenticationToken` in the mock does not imply production logs in with username/password. If production uses a custom `Authentication` class, construct that exact type in tests that verify security context details.

### 28.1. When Should You Use a Custom Principal?

It can be beneficial when an application:

- Wants controllers decoupled from Spring Security OAuth2 types.
- Needs an `(issuer, subject, tenant)` identity model.
- Supports multiple login mechanisms yet wants a unified domain principal.
- Needs claim normalization and entitlement mapping.

However, converting an OIDC principal into a domain principal must occur **after real OIDC token validation**, never from raw headers or query parameters. Controller unit tests should still stay separate from converter/validator tests.

## 29. Common Testing Anti-Patterns

### 29.1. Using `@WithMockUser` for Every Controller

Wrong when the controller needs an `OidcUser` or `OAuth2User`. Can produce nulls/exceptions or skip OIDC claim logic.

**Instead:** use `oidcLogin()`, `oauth2Login()`, or a custom security context factory of the matching type.

### 29.2. Testing `@AuthenticationPrincipal` by Calling the Method Directly

Fails to test MVC argument resolution, the filter chain, HTTP statuses, and exception mapping.

**Instead:** write at least one MockMvc test for each important principal injection pattern.

### 29.3. Using `standaloneSetup()` Without Integrating Spring Security

Can prevent the mock `Authentication` from entering the context or prevent security filters from running.

**Instead:** use `@WebMvcTest`/`@AutoConfigureMockMvc` or `webAppContextSetup(...).apply(springSecurity())`.

### 29.4. Wrong Principal Type Masked by Manual Casting in the Controller

Casting or extracting claims from `Object` unchecked makes tests hard to diagnose.

**Instead:** use typed parameters and `errorOnInvalidType` when you want fail-fast behavior.

### 29.5. Asserting Username Without Asserting Subject/Issuer

`getName()` depends on configuration. Across multiple issuers, `sub` is not globally unique.

**Instead:** explicitly test `(issuer, subject)` and tenant membership.

### 29.6. Asserting Only 200 Without Checking Payload Data

An endpoint can return 200 while returning the wrong identity or another tenant's data.

**Instead:** assert JSON fields and service call arguments.

### 29.7. Mocking All Authorities as `ADMIN`

Tests only the happy path and misses least-privilege enforcement.

**Instead:** test read-only, admin, missing authority, and cross-tenant denial.

### 29.8. Mocking an OIDC User with Every Claim Present

Misses behavior when `email`, `preferred_username`, or `locale` are absent.

**Instead:** test optional claims and provider-specific mappings.

### 29.9. Treating `oidcLogin()` as a Signature Validation Test

The helper performs no Authorization Code or JWT cryptographic verification.

**Instead:** write protocol integration tests with an OP sandbox/test JWKS.

### 29.10. Using `jwt()` for OIDC Login

A Resource Server `Jwt` is not the same type as `OidcUser`.

**Instead:** pick the helper matching the authentication mechanism.

### 29.11. Letting Controllers Read the `Authorization` Header and Parse Tokens Manually

Scatters security logic and risks bypassing framework validation.

**Instead:** rely on Spring Security authentication filters and typed principals.

### 29.12. Disabling Filters in Tests to Make Endpoints Pass

Fails to verify that requests actually pass authentication/authorization.

**Instead:** keep security filters active whenever testing request/security integration.

### 29.13. Using Email Domain to Grant Tenant Access

Emails can be unverified or changed and do not prove membership.

**Instead:** use verified OIDC identity and a domain authorization service.

### 29.14. Logging the Full `OidcUser` or ID Token

Risks exposing PII, session IDs, token claims, and credentials.

**Instead:** log only non-sensitive issuer aliases, principal types, outcomes, and correlation IDs.

### 29.15. Mixing Multiple Authentication Sources in One Test

Using `@WithMockUser` and `.with(oidcLogin())` together without controlling precedence makes tests confusing.

**Instead:** give each test one clear identity fixture.

## 30. Test Matrix for `@AuthenticationPrincipal` Controllers

| ID | Controller expects | Test context | Expectation |
| --- | --- | --- | --- |
| C01 | `OidcUser` | `.with(oidcLogin())` | Right principal type, 2xx per business logic |
| C02 | `OidcUser` | Custom ID Token `sub` | DTO contains matching `sub` |
| C03 | `OidcUser` | Custom ID Token `iss` | DTO/mapper uses matching issuer |
| C04 | `OidcUser` | Missing email | Proper nullable/fallback behavior |
| C05 | `OidcUser` | `.with(oauth2Login())` | Type mismatch handled properly |
| C06 | `OidcUser` | `@WithMockUser` | Does not masquerade as OIDC |
| C07 | `OidcUser` | Anonymous, protected endpoint | 401/302 per entry point |
| C08 | `OidcUser` | Anonymous, public endpoint | Guest response/nullable principal |
| C09 | `OAuth2User` | `.with(oauth2Login())` | Provider attributes read properly |
| C10 | `Jwt` | `.with(jwt())` | Valid Resource Server principal |
| C11 | `OidcUser` | `.with(jwt())` | Type mismatch |
| C12 | `@CurrentSubject` | `oidcLogin()` | SpEL meta-annotation extracts `sub` |
| C13 | `errorOnInvalidType=true` | Wrong principal type | Fails fast, no silent null |
| C14 | `Authentication` + `OidcUser` | OIDC login `registration=corporate` | Reads `registrationId` properly |
| C15 | Domain principal | Custom `Authentication` | Custom type injected properly |
| C16 | Tenant endpoint | OIDC Acme + Acme membership | Allowed |
| C17 | Tenant endpoint | OIDC Acme + Beta tenant | Denied |
| C18 | URL role protection | OIDC user with read authority only | Admin endpoint 403 |
| C19 | URL role protection | OIDC user with admin authority | Admin endpoint 2xx |
| C20 | POST with CSRF | OIDC principal + CSRF | Business action executes |
| C21 | POST without CSRF | OIDC principal | 403 when CSRF enabled |
| C22 | Async controller | OIDC principal + `asyncDispatch` | Subject preserved across async |
| C23 | Controller response | OIDC user with tokens | No raw tokens/PII beyond contract |
| C24 | MockMvc setup | Security filters disabled | Test must not be used to claim authn works |
| C25 | Authenticated user, missing membership | Domain service denies | No tenant data returned |
| C26 | Same `sub`, different issuers | Two OIDC principals | Identity keys not merged |
| C27 | Custom `OidcUser` name attribute | `preferred_username` differs from `sub` | Distinguish `getName` and subject |
| C28 | `@RegisteredOAuth2AuthorizedClient` | Mock OIDC login only | Does not prove token storage |
| C29 | Spring Method Security | `@PreAuthorize` + config | Verify method security is actually enabled |
| C30 | Error response | Exception/invalid context | Never log/return ID/access/refresh tokens |

**Note:** Exact HTTP statuses depend on `SecurityFilterChain`, `AuthenticationEntryPoint`, controller advice, and whether the test uses an MVC slice or full app context. Your test suite must verify your **application's contract**, rather than assuming every Spring Boot setup shares identical defaults.

## 31. Well-Structured Sample Test Layout

A project can organize tests as:

```text
src/main/java/
  example/portal/web/
    MeController.java
    TenantProfileController.java
  example/portal/security/
    SecurityConfig.java
    TenantAuthorization.java

src/test/java/
  example/portal/web/
    MeControllerTest.java
    TenantProfileControllerTest.java
  example/portal/security/
    TestOidcUsers.java
    WithTestOidcUser.java
    WithTestOidcUserFactory.java
  example/portal/integration/
    OidcLoginFlowIntegrationTest.java
    ResourceServerJwtValidationTest.java
```

### 31.1. Role of Each Test File

| File | Focus |
| --- | --- |
| `MeControllerTest` | `@AuthenticationPrincipal OidcUser`, JSON DTO, unauthenticated behavior |
| `TenantProfileControllerTest` | Controller passing `(tenant, issuer, sub)` to authorization service |
| `TestOidcUsers` | Synthetic `OidcIdToken`, `OidcUserInfo`, and authorities data |
| `WithTestOidcUser` | Sharing fixtures with the right OIDC principal type |
| `OidcLoginFlowIntegrationTest` | Authorization Request, callback, Token Endpoint, issuer/audience/nonce validation |
| `ResourceServerJwtValidationTest` | JWT decoder, `iss`, `aud`, signature, expiry, API authorization |

You do not need to put every test into a heavy `@SpringBootTest`. Controller tests run fast with `@WebMvcTest`; security protocol tests use dedicated setups matching the threat model.

### 31.2. Given-When-Then Pattern

```text
Given
    Spring MVC controller /api/me
    SecurityFilterChain protecting the endpoint
    OidcUser with synthetic issuer, subject, and email

When
    MockMvc GET /api/me + oidcLogin()

Then
    HTTP 200
    JSON subject matches
    JSON issuer matches
    No ID Token/access token in response

And
    Does not call real Authorization Endpoint/Token Endpoint
```

Denial case:

```text
Given
    OidcUser with issuer Acme, sub A17
    TenantAuthorization denies access to Beta

When
    GET /api/tenants/beta/profile

Then
    No Beta data returned
    HTTP 403 or corresponding contract error
    Does not trust tenant path or email
```

## 32. Troubleshooting When Tests Behave Unexpectedly

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `@AuthenticationPrincipal OidcUser` is null | Used `@WithMockUser`/`oauth2Login()` (wrong type) | Use `oidcLogin()` |
| Controller throws NPE in test | Null principal, missing claim | Check fixture and nullable contract |
| MockMvc request lacks `SecurityContext` | Security filters/setup not integrated | Use auto-configured MockMvc or `.apply(springSecurity())` |
| Anonymous test returns 302 instead of 401 | App uses OAuth2 Login entry point | Assert per config or configure dedicated API entry point |
| `@WithMockUser` gives 200 despite OIDC type mismatch | Security `.authenticated()` does not inspect principal Java type | Test with the matching OIDC principal |
| `getName()` differs from `sub` | Custom name attribute key | Test subject and display name separately |
| Email is always null | Claim missing from ID Token/UserInfo fixture | Configure mock `OidcUser` properly |
| Test only sees `ROLE_USER`, missing scope | Authorities fixture not configured | Set `.authorities(...)` per expected mapping |
| `@PreAuthorize` appears inactive | Method security not enabled in test context | Load security config/proxy or test separately |
| `@MockitoBean` not found | Older Spring Framework/Boot version | Use `@MockBean` per version or upgrade dependency |
| Full context fails to start | Missing `ClientRegistrationRepository`/issuer metadata/test secret | Use test profile or MVC slice |
| OIDC test passes yet production ID Token rejected | Helper skips JWT validation | Write protocol integration test |
| Unexpected UserInfo claim | Mock only has ID Token, missing UserInfo | Construct custom `DefaultOidcUser` |
| CSRF POST returns 403 | Missing `.with(csrf())` | Add CSRF token for valid test request |
| Cross-tenant test fails to deny | Mocked service allows everything | Stub denial and test the policy service |
| Async test shows no response yet | Missing `asyncDispatch` | Use MockMvc async test pattern |
| JWT API principal is `Jwt`, not `OidcUser` | Resource Server differs from OIDC Login | Use `jwt()` helper |
| Response contains unexpected claims/tokens | Controller serializes principal directly | Return minimal DTO |
| Test user data leaks across methods | Shared `SecurityContext`/global fixtures | Use per-test helpers and clear context properly |

### 32.1. A 5-Step Diagnostic Sequence

1. **Check the parameter type:** `OidcUser`, `OAuth2User`, `UserDetails`, `Jwt`, or custom type?
2. **Check the `Authentication` fixture:** `oidcLogin`, `oauth2Login`, `@WithMockUser`, `jwt`, or `authentication(...)`?
3. **Check MockMvc security integration:** are filters/`springSecurity()` active?
4. **Check access policy:** is the request authenticated/authorized and did the controller actually run?
5. **Check claims/service dependencies:** do `sub`, `iss`, `email`, authorities, and tenant membership match the contract?

Never start by disabling security filters or changing the principal parameter to `Object`.

## 33. What `oidcLogin()` Does NOT Prove

This is a critical quality boundary:

```java
mvc.perform(get("/api/me").with(oidcLogin()))
```

**Can verify:**

- OIDC principal is injected into the MVC controller.
- Controller mapping/DTO serialization.
- Role/authority checks when fixtures/security config align.
- `@AuthenticationPrincipal`/SpEL/meta-annotation behavior.
- Domain service is invoked with the right identity.

**Does NOT automatically verify:**

- RP builds authorization request with valid `redirect_uri`/`state`/PKCE.
- User is genuinely authenticated by the OP.
- Authorization code is exchanged at the right Token Endpoint.
- ID Token signature/JWKS/`iss`/`aud`/nonce/expiry.
- UserInfo Endpoint is called safely.
- Client secret or mTLS/`private_key_jwt` is valid.
- Refresh token rotation.
- Access token is accepted by API with the right audience.
- Browser cookies, proxies, SameSite, or SSO logout.
- Real user membership/entitlements when the service is mocked.

For high-security requirements, combine:

1. **Controller slice tests** using `oidcLogin()`/`oauth2Login()`.
2. **Security config tests** with real filter chains and authorities.
3. **OIDC Login integration tests** with test OP/JWKS/token fixtures.
4. **Resource Server tests** with real access token validation.
5. **Domain authorization tests** for ownership, roles, and tenant policies.
6. **End-to-end tests** for browser redirects/sessions when needed.

Do not collapse all of these into one giant test chasing "full coverage". Each layer verifies a clear contract.

## 34. Review Questions

**1. Where does `@AuthenticationPrincipal` get the principal from?**

From `Authentication.getPrincipal()` in the request's `SecurityContext`, via Spring Security's MVC argument resolver.

**2. Does `@WithMockUser` create an `OidcUser`?**

Normally no. It creates a generic `UserDetails`-based authentication, which can mismatch a controller expecting `OidcUser`.

**3. When should you use `oidcLogin()`?**

When testing Servlet MockMvc controllers or authorization behavior that needs an OIDC-Login-style principal.

**4. When should you use `oauth2Login()`?**

When the app uses non-OIDC OAuth2 Login or the controller expects `OAuth2User`.

**5. Does `oidcLogin()` perform authorization code or token exchange?**

No. It builds a mock authentication for the test request.

**6. Why is calling a controller method directly insufficient?**

It skips the MVC argument resolver, `SecurityContext`, and filter chain.

**7. How does `OidcUser.getSubject()` differ from `getName()`?**

`getSubject()` explicitly returns OIDC `sub`; `getName()` depends on the principal implementation's name attribute key.

**8. Can email be used as a unique user key across all OIDC providers?**

Never by default. Emails can be missing or change; identity typically requires `(issuer, sub)`.

**9. What does `@AuthenticationPrincipal(expression = "attributes['sub']")` do?**

Uses SpEL to extract the `sub` field from the principal's attributes.

**10. When should you use `errorOnInvalidType=true`?**

When you want a mismatched principal Java type to raise a clear error instead of the resolver silently injecting `null`.

**11. Why can a controller receive `null` even when the request is authenticated?**

Because `Authentication` may hold a principal of a different type; `.authenticated()` does not check controller Java parameter types.

**12. Do anonymous test requests always return 401?**

No. An OAuth2 Login entry point may return a 302 redirect; behavior depends on security configuration.

**13. Does a test using `oidcLogin()` alone prove the ID Token was properly signed?**

No. You need an appropriate decoder/OP integration test.

**14. How do you customize `OidcUser` claims in tests?**

Use `oidcLogin().idToken(...)`, or construct `OidcIdToken`/`DefaultOidcUser` and pass `.oidcUser(...)`.

**15. Are UserInfo claims always present inside the ID Token?**

No. UserInfo can provide additional claims; test fixtures should reflect the production contract.

**16. How should you read the registration ID?**

Use `OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()` or an appropriate identity context abstraction—not `OidcUser.getSubject()`.

**17. Does a registration ID prove tenant membership?**

No. You need domain authorization verifying the user is allowed to access that tenant.

**18. What is `@WithSecurityContext` used for?**

Defining a custom test annotation to build a `SecurityContext`/`Authentication` of the exact desired type.

**19. What is the benefit of a meta-annotation like `@CurrentOidcUser`?**

Keeps controller signatures concise and expresses reliance on an OIDC principal while still using the `@AuthenticationPrincipal` resolver.

**20. Does `standaloneSetup()` automatically run the Spring Security filter chain?**

No. Proper security setup is required if testing integration.

**21. Why is `.apply(springSecurity())` needed with `webAppContextSetup`?**

To integrate security filters and test helpers properly with MockMvc.

**22. How do `@WebMvcTest` and `@SpringBootTest` differ?**

One loads a fast MVC slice; the other loads a broader application context and security wiring closer to production.

**23. Does `@RegisteredOAuth2AuthorizedClient` retrieve the principal?**

No. It resolves an authorized client holding access/refresh tokens, distinct from `@AuthenticationPrincipal`.

**24. Should a controller accepting a `Jwt` principal be tested with `oidcLogin()`?**

No. For a JWT Resource Server, normally use `jwt()`.

**25. Why is a JWT post-processor test not enough to prove Resource Server audience validation?**

The helper sets a mock authentication without necessarily running real JWT signature/issuer/audience validators.

**26. Do POST tests need a CSRF token?**

When CSRF is enabled under browser-session security policy, valid requests typically require `.with(csrf())`.

**27. Why should you never return the raw `OidcUser` as JSON?**

It can expose all claims, PII, or token-related data. Return a minimal DTO instead.

**28. If tenant authorization is tested with a mocked service, is the real policy proven?**

No. It only proves the controller calls the service properly; the policy service must be tested separately.

**29. How do you test an async controller?**

Use MockMvc `asyncStarted()` and `asyncDispatch(result)`; with custom executors, verify `SecurityContext` propagation.

**30. What belongs in an `@AuthenticationPrincipal` test matrix?**

Matching/mismatched principal types, OIDC/OAuth2/JWT fixtures, authenticated/anonymous, missing claims, SpEL/meta-annotations, roles/scopes, tenant policies, CSRF, async, and responses free of sensitive data.

## 35. References

- [Spring Security Reference — Testing, Servlet](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [Spring Security Reference — MockMvc OAuth 2.0 Login Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security Reference — MockMvc OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security Reference — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security Reference — WithMockUser](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security Reference — MVC AuthenticationPrincipal](https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html)
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security Reference — OIDC Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security API — AuthenticationPrincipal](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/annotation/AuthenticationPrincipal.html)
- [Spring Security API — AuthenticationPrincipalArgumentResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/method/annotation/AuthenticationPrincipalArgumentResolver.html)
- [Spring Security API — OidcUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html)
- [Spring Security API — DefaultOidcUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/DefaultOidcUser.html)
- [Spring Security API — OAuth2AuthenticationToken](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/authentication/OAuth2AuthenticationToken.html)
- [Spring Security API — SecurityMockMvcRequestPostProcessors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html)
- [Spring Framework Reference — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html)
- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)

**Key takeaway:** `@AuthenticationPrincipal` in Spring MVC retrieves **`Authentication.getPrincipal()`**, so MockMvc tests must construct **the exact Java principal type**. For OIDC controllers, prefer **`.with(oidcLogin())`** or a custom `OidcUser`; for non-OIDC OAuth2 users, use **`oauth2Login()`**; for JWT Resource Servers, use **`jwt()`**. `@WithMockUser` does not create an OIDC principal. Keep Spring Security filters integrated in MockMvc, test anonymous/type-mismatch/claims/authorities/tenant-boundary cases, and return minimal DTOs. These fixtures test **controllers + argument resolution**, **not** Authorization Code integration, ID Token signature/issuer/audience validation, access token validation, or domain authorization.
