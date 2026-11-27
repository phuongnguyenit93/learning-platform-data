# 30.6. Testing ReactiveOAuth2UserService and Claim Mapping

In a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client using WebFlux**, a user may authenticate successfully at the OpenID Provider (OP), yet the application still needs to perform several steps **after receiving tokens**:

- Fetch user information from the **UserInfo Endpoint** when allowed by protocol, scopes, and provider.
- Convert provider attributes into an `OAuth2User` or `OidcUser` usable by the application.
- Select a durable **principal name**, properly distinguishing issuer, subject, and tenant.
- Map verified information into **Spring Security authorities**.
- Check whether the user belongs to the tenant, is activated, or is allowed to access the application.
- Handle errors from the provider, database, mapping service, or missing required claims per policy.
- Return the result as **`Mono<OAuth2User>` or `Mono<OidcUser>`**, without blocking the event loop.

These behaviors are typically implemented or extended via **`ReactiveOAuth2UserService`**. They must be tested directly, because a WebFlux test such as:

```java
webTestClient.mutateWith(mockOidcLogin())
    .get().uri("/account/me")
    .exchange()
    .expectStatus().isOk();
```

only **simulates an already OIDC-logged-in user state**. It **does not** execute your custom `ReactiveOAuth2UserService` code, does not fetch real UserInfo, and does not verify the application's full authority-mapping mechanism.

This lesson explains how to design tests for **reactive user services** and **claim mapping** using JUnit Jupiter, Reactor Test `StepVerifier`, OIDC/OAuth2 fixtures, fake dependencies, and a test HTTP provider where needed. Examples progress from simple unit tests to integration tests with WebFlux Security, focusing on **return values, principal types, trusted data sources, errors, asynchronicity, and multi-provider/multi-tenant security boundaries**.

> **Key mindset:** separate three questions: **(1) were the token/identity verified properly; (2) does the user service turn verified data into the right principal/authorities; (3) does the endpoint enforce authorization properly?** Each question needs its own appropriate test layer; never treat a passing mock login as proof that all three layers are secure.

## 1. Where Does `ReactiveOAuth2UserService` Sit in the System?

An **Authorization Code + OIDC** flow on WebFlux typically looks like:

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant W as Spring Security WebFlux Client
    participant O as OpenID Provider
    participant U as Reactive OIDC User Service
    participant M as App Mapping / Membership Service

    B->>W: GET /oauth2/authorization/company
    W-->>B: Redirect to authorization endpoint
    B->>O: Login, MFA, consent
    O-->>B: Callback with code and state
    B->>W: GET /login/oauth2/code/company
    W->>W: Correlate request/state, token exchange
    W->>O: Exchange authorization code
    O-->>W: ID Token + Access Token
    W->>W: Verify ID Token per OIDC
    W->>U: loadUser(OidcUserRequest)
    opt Flow includes UserInfo
        U->>O: GET userinfo_endpoint with Access Token
        O-->>U: UserInfo claims
    end
    U->>M: Map issuer/sub, check membership/roles
    M-->>U: Trusted application authorities
    U-->>W: Mono<OidcUser>
    W->>W: Create Authentication/SecurityContext
    W-->>B: Login session or subsequent response
```

**`ReactiveOAuth2UserService` handles loading/building the principal**, while verifying the authorization code, ID Token signature, issuer, audience, `state`/`nonce`/PKCE, and session management belong to other components of the Spring Security/OIDC flow.

When a custom service is written poorly, users may experience:

- Being authenticated yet missing roles because mapping read the wrong claim.
- Being granted `ROLE_ADMIN` simply because the provider returned an untrusted `"admin"` string.
- Two users from two issuers sharing the same `sub` being merged into one principal.
- `Mono.empty()` leaving authentication with an ambiguous outcome.
- UserInfo HTTP errors being swallowed and falling back to broad authorities.
- Blocking database/HTTP calls running on the Reactor event loop.
- Failures lacking proper audit evidence while logs leak the Access Token/ID Token.

Those bugs must be tested **on the service itself**, not only by checking that a controller returns HTTP 200.

## 2. Distinguishing the Two Reactive User Service Types

The common interface in Spring Security:

```java
package org.springframework.security.oauth2.client.userinfo;

public interface ReactiveOAuth2UserService<
        R extends OAuth2UserRequest,
        U extends OAuth2User> {

    Mono<U> loadUser(R userRequest);
}
```

This is a conceptual API form to show generic bounds; the actual framework source may contain additional annotations or version-specific details.

Two primary usages:

| Scenario | Generic service | Principal | Common implementation |
|---|---|---|---|
| **Standard OAuth2 Login, not necessarily OIDC** | `ReactiveOAuth2UserService<OAuth2UserRequest, OAuth2User>` | `OAuth2User` | `DefaultReactiveOAuth2UserService` or custom implementation |
| **OIDC Login** | `ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` | `OidcUser` | `OidcReactiveOAuth2UserService` or custom implementation |

### 2.1. OAuth2 User Service

An OAuth2 provider may return user attributes from its own UserInfo-like endpoint, for example:

```json
{
  "id": "12345",
  "login": "alice",
  "display_name": "Alice"
}
```

The service turns the response into an `OAuth2User` and selects which attribute serves as the name.

### 2.2. OIDC User Service

With OIDC, the **ID Token** supplies standard claims such as:

```json
{
  "iss": "https://id.example.test",
  "sub": "subject-42",
  "aud": "web-client",
  "email": "alice@example.test"
}
```

The OP may also supply **UserInfo**, for example:

```json
{
  "sub": "subject-42",
  "name": "Alice Example",
  "preferred_username": "alice",
  "email": "alice@example.test"
}
```

The OIDC User Service is responsible for building an `OidcUser` representing the user from data verified in the OIDC context.

**Do not conflate the two generic interfaces:** a controller requiring `OidcUser` needs an OIDC principal, not merely a `DefaultOAuth2User` with attributes named like OIDC claims.

### 2.3. Tests Must Target the Right Implementation

If production code uses a custom:

```java
ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
```

then a test targeting generic:

```java
ReactiveOAuth2UserService<OAuth2UserRequest, OAuth2User>
```

will not automatically exercise that custom OIDC code. Identify the exact bean, delegate, and flow that Spring Security invokes.

## 3. Claim Sources: ID Token, UserInfo, and Internal Data

Three data sources commonly appear:

| Source | Who creates it? | What is it for? | Trust boundary |
|---|---|---|---|
| **ID Token** | Issued by OP in OIDC flow | Authenticates user to RP; issuer/subject/audience and claims | Must have signature, issuer, audience, timestamps, and `nonce` verified when required |
| **UserInfo** | Returned by OP via Access Token | Supplements profile info and extra claims | Accept only from the right OP endpoint; `sub` must match ID Token per OIDC |
| **Application membership/roles DB** | App or authorized policy source | Determines business permissions, tenant membership, account status | Must be queried using verified identity and active policy |

Example:

```text
ID Token:
  iss = https://id.example.test
  sub = subject-42

UserInfo:
  sub = subject-42
  preferred_username = alice

Internal DB:
  (iss, sub) -> tenant alpha -> ROLE_REPORT_VIEWER
```

**Never grant `ROLE_ADMIN` directly from an arbitrary profile string just because UserInfo contains `"role": "admin"`.** Whether to trust any role claim requires an explicit contract with the OP and an approved mapping policy.

### 3.1. `sub` Is Not Unique Across All Issuers

Two OPs may both have:

```text
issuer A, sub = 1001
issuer B, sub = 1001
```

Yet they can be **two different people**. OIDC identity must be keyed by the pair:

```text
(issuer, subject)
```

This is a critical case to test in multi-provider or multi-tenant systems.

### 3.2. Email Should Only Be Used as Profile Data Unless Policy Specifies Otherwise

Email can be:

- Absent.
- Unverified.
- Changed.
- Recycled.
- Duplicated across two issuers.
- Subject to different normalization rules.

Using email as display/contact data is safer than treating it as an immutable identity key by default. Unit tests should include cases for **missing email**, **changed email**, and **two issuers sharing an email**.

### 3.3. Authorities Differ from Claims

`OidcUser.getClaims()` returns claim data. `OidcUser.getAuthorities()` returns the `GrantedAuthority` instances Spring Security evaluates in checks like:

```java
.hasAuthority("report:read")
.hasRole("TENANT_ADMIN")
```

A claim `"roles": ["TENANT_ADMIN"]` does not automatically become `ROLE_TENANT_ADMIN` if mapping code has not converted it. Tests must assert the **exact authority strings** rather than only asserting that the claim still exists.

## 4. Test Layers to Separate

| Test layer | What is tested? | Suitable tools | What remains unproven |
|---|---|---|---|
| **Mapping function unit test** | Converting claims Map → profile/authorities | JUnit + AssertJ | Does not prove WebFlux wiring |
| **Reactive user service unit test** | `loadUser(request)`, `Mono` values/errors | Reactor `StepVerifier` + fake delegate | Does not prove real OP/JWKS |
| **UserInfo HTTP integration test** | HTTP request/response and OIDC UserInfo parsing | Local stub server + reactive service | Does not necessarily prove full login |
| **WebFlux authorization test** | Route/method security with principal | `WebTestClient` + `mockOidcLogin()` | Does not invoke user service |
| **Full OIDC flow integration** | Callback, code exchange, ID Token/JWKS, and service wiring | Test OP/stub, WebFlux app | Does not prove browser cookie behavior |
| **Browser E2E** | Redirect/cookie/SSO UX | Browser with test OP | Does not replace mapping error unit tests |

**Avoid cramming everything into one giant test.** If an authority is missing, a mapping unit test pinpoints the cause faster than E2E; if there is a `nonce`/callback bug, `mockOidcLogin()` cannot catch it.

## 5. Required Dependencies

With Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("io.projectreactor:reactor-test")
}

tasks.test {
    useJUnitPlatform()
}
```

This is a dependencies fragment, not a standalone `build.gradle.kts`. Spring Boot dependency management/BOM should align compatible versions; do not pin `spring-security-test` or Reactor Test to a version far out of sync with runtime.

With Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

### 5.1. Why Is `reactor-test` Needed?

`reactor-test` provides:

- `StepVerifier`: verifies signals from `Mono`/`Flux`.
- `PublisherProbe`: verifies a publisher was subscribed, requested, or canceled as expected.
- Virtual time utilities: tests time-based logic without waiting on wall-clock time when appropriate.
- Utilities for specific Reactor scenarios.

Here, the core pattern is:

```java
StepVerifier.create(service.loadUser(userRequest))
    .assertNext(user -> {
        // Check principal/claims/authorities
    })
    .verifyComplete();
```

### 5.2. Why Is `spring-security-test` Needed?

When testing post-login WebFlux routes, you can use:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;
```

However, **unit tests of `ReactiveOAuth2UserService` do not necessarily need `mockOidcLogin`**; they can invoke `loadUser` directly with an `OidcUserRequest` fixture.

### 5.3. Never Use Production Secrets in Tests

`client-secret`, Access Tokens, Refresh Tokens, and ID Tokens used in tests must be **synthetic fixtures**. Never place real user tokens into `src/test` or CI logs.

## 6. Clean Test Class Layout

Example:

```text
src/
  main/
    java/com/example/security/
      TenantMappingReactiveOidcUserService.java
      TenantRoleLookup.java
      SecurityConfiguration.java
  test/
    java/com/example/security/
      OidcRequestFixtures.java
      TenantMappingReactiveOidcUserServiceTest.java
      OAuth2ProfileMappingServiceTest.java
      OidcWebFluxAuthorizationTest.java
      OidcUserInfoIntegrationTest.java
```

Purpose:

- **Fixtures** build fake `OidcUserRequest`, ID Token, UserInfo, and `OAuth2AccessToken`.
- **Unit tests** call the service directly without an application context.
- **WebFlux tests** verify endpoints/security filters once the principal is injected.
- **HTTP integration tests** verify UserInfo/OP when needed.

Never place a production Bean using test token fixtures in `src/main` merely for convenience. Test infrastructure must stay isolated.

## 7. Building a Mock `OidcUserRequest`

`ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` takes an `OidcUserRequest` containing:

- `ClientRegistration`.
- `OAuth2AccessToken`.
- `OidcIdToken`.
- Additional parameters when supported by the flow/API.

A Java fixture:

```java
package com.example.security;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;

public final class OidcRequestFixtures {

    private OidcRequestFixtures() {}

    public static ClientRegistration registration() {
        return ClientRegistration.withRegistrationId("company")
            .clientId("test-web-client")
            .clientSecret("synthetic-test-secret")
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .authorizationUri("https://id.example.test/authorize")
            .tokenUri("https://id.example.test/token")
            .jwkSetUri("https://id.example.test/jwks")
            .issuerUri("https://id.example.test")
            .userInfoUri("https://id.example.test/userinfo")
            .userNameAttributeName("sub")
            .scope("openid", "profile")
            .build();
    }

    public static OidcIdToken idToken() {
        return new OidcIdToken(
            "synthetic-id-token",
            Instant.parse("2026-01-01T00:00:00Z"),
            Instant.parse("2030-01-01T00:00:00Z"),
            Map.of(
                "iss", "https://id.example.test",
                "sub", "subject-42",
                "aud", List.of("test-web-client"),
                "tenant_id", "alpha"
            )
        );
    }

    public static OAuth2AccessToken accessToken() {
        return new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "synthetic-access-token",
            Instant.parse("2026-01-01T00:00:00Z"),
            Instant.parse("2030-01-01T00:00:00Z"),
            Set.of("openid", "profile")
        );
    }

    public static OidcUserRequest request() {
        return new OidcUserRequest(
            registration(),
            accessToken(),
            idToken()
        );
    }
}
```

**Important:** the `OidcIdToken` constructor in this fixture sets claims directly; **it does not sign or verify a JWT**. This is deliberate for unit-testing mapping that happens *after* OIDC validation. Never use this fixture to claim a fake token can pass a real verifier.

### 7.1. Decouple Fixtures from Real Providers

Hosts under `example.test` are synthetic. No test should automatically contact a production OP to fetch metadata or JWKS on every unit suite run.

### 7.2. Control Time

Use fixed `Instant` values so tests are reproducible. When your code checks token expiry, inject a `Clock` so tests do not depend on the date they run.

Avoid scattering `Instant.now()` across both fixtures and assertions, which causes flaky tests around expiration boundaries.

### 7.3. Each Registration Is an Identity Boundary

If the application has `company` and `partner`, fixtures should create separate `ClientRegistration`s with appropriate issuers/client IDs. Do not reuse one registration for two issuers and accidentally get passing tests despite mixed-up users/tokens.

## 8. Building a Mock `OidcUser` Offline

From the fixtures above, we can build a user:

```java
package com.example.security;

import java.util.Map;
import java.util.Set;

import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;

public final class OidcUserFixtures {

    private OidcUserFixtures() {}

    public static OidcUser userWithUserInfo() {
        var idToken = OidcRequestFixtures.idToken();

        var userInfo = new OidcUserInfo(Map.of(
            "sub", "subject-42",
            "name", "Alice Example",
            "email", "alice@example.test"
        ));

        var oidcAuthority =
            new OidcUserAuthority(idToken, userInfo);

        return new DefaultOidcUser(
            Set.of(oidcAuthority),
            idToken,
            userInfo,
            "sub"
        );
    }

    public static OidcUser userWithoutUserInfo() {
        var idToken = OidcRequestFixtures.idToken();

        return new DefaultOidcUser(
            Set.of(new OidcUserAuthority(idToken)),
            idToken,
            "sub"
        );
    }
}
```

This fixture tests mappers **that already received a structurally valid `OidcUser`**. It performs no UserInfo HTTP call and does not prove that claims were signed by a provider.

### 8.1. Why Are Both Variants Needed?

UserInfo may not be called or returned depending on flow, scopes, policy, and provider. Mapping code must not throw an NPE when:

```java
oidcUser.getUserInfo() == null
```

Tests should cover cases both with and without UserInfo.

### 8.2. UserInfo Must Have the Same Subject

A core OIDC rule:

```text
ID Token sub = subject-42
UserInfo sub = subject-42
```

If UserInfo returns a different `sub`, the response **must not be merged into the authenticated user**. Tests verifying mismatch handling must run the logic of the **real OIDC user service/parser or an explicit validation wrapper**; do not just pass two Maps to `DefaultOidcUser` and expect the constructor to prove HTTP requests are checked.

### 8.3. Principal Name

`DefaultOidcUser(..., "sub")` uses `sub` as the name claim. If production selects another name attribute, tests must reflect it accurately, especially when the authorized client store uses `principalName` as part of its key.

## 9. Building a User Service That Maps Authorities from Trusted Membership

Suppose the OP authenticates the user, while **report viewing permissions** are managed internally. The app wants to add `ROLE_REPORT_VIEWER` when the user has valid membership, rather than trusting a self-asserted `role` claim.

Define a reactive role lookup service:

```java
package com.example.security;

import java.util.Set;
import reactor.core.publisher.Mono;

public interface TenantRoleLookup {

    Mono<Set<String>> rolesFor(
        String issuer,
        String subject
    );
}
```

Semantics:

- `issuer` and `subject` come from the verified OIDC identity.
- Return values can be `ROLE_REPORT_VIEWER` or policy-defined permissions.
- Production implementation may use Reactive Mongo/R2DBC/`WebClient`, but must be non-blocking or isolated from the event loop if blocking is unavoidable.
- Contract of the example: `Mono.empty()` = membership not found; empty role set = not permitted to enter the tenant app.

### 9.1. Writing the Wrapper User Service

```java
package com.example.security;

import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.ReactiveOAuth2UserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

import reactor.core.publisher.Mono;

public final class TenantMappingReactiveOidcUserService
        implements ReactiveOAuth2UserService<OidcUserRequest, OidcUser> {

    private final ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
        delegate;

    private final TenantRoleLookup roleLookup;

    public TenantMappingReactiveOidcUserService(
            ReactiveOAuth2UserService<OidcUserRequest, OidcUser> delegate,
            TenantRoleLookup roleLookup) {

        this.delegate = delegate;
        this.roleLookup = roleLookup;
    }

    @Override
    public Mono<OidcUser> loadUser(OidcUserRequest request) {

        return delegate.loadUser(request)
            .switchIfEmpty(Mono.error(denied()))
            .flatMap(user -> {

                if (user.getIdToken().getIssuer() == null
                        || user.getSubject() == null
                        || user.getSubject().isBlank()) {
                    return Mono.error(denied());
                }

                String issuer =
                    user.getIdToken().getIssuer().toString();

                String subject = user.getSubject();

                return roleLookup.rolesFor(issuer, subject)
                    .switchIfEmpty(Mono.error(denied()))
                    .flatMap(roles -> {

                        if (roles.isEmpty()) {
                            return Mono.error(denied());
                        }

                        Set<GrantedAuthority> authorities =
                            new LinkedHashSet<>(user.getAuthorities());

                        for (String role : roles) {
                            authorities.add(
                                new SimpleGrantedAuthority(role)
                            );
                        }

                        OidcUser mapped =
                            user.getUserInfo() == null
                                ? new DefaultOidcUser(
                                    authorities,
                                    user.getIdToken(),
                                    "sub"
                                  )
                                : new DefaultOidcUser(
                                    authorities,
                                    user.getIdToken(),
                                    user.getUserInfo(),
                                    "sub"
                                  );

                        return Mono.just(mapped);
                    });
            });
    }

    private static OAuth2AuthenticationException denied() {
        return new OAuth2AuthenticationException(
            new OAuth2Error("access_denied")
        );
    }
}
```

This is a **policy design example**: the app only allows login for users with backend membership/roles. An app that allows identity-only users with zero roles yet may choose another policy; what matters is that **missing-membership behavior is decided explicitly and tested**.

### 9.2. Why Use a `delegate`?

`delegate` can be the default `OidcReactiveOAuth2UserService` or an implementation configured to load UserInfo/validate claims. The wrapper only adds **business authority mapping**.

Benefits:

- Avoids rewriting the UserInfo HTTP protocol.
- Does not replace OIDC token validation.
- Allows faking the delegate in unit tests to isolate mapping.
- Allows integration-testing the delegate separately with an OP stub.
- Preserves original identity/authorities while adding internal permissions.

### 9.3. Why Preserve Existing Authorities?

`user.getAuthorities()` may include `OidcUserAuthority` and `SCOPE_...` from the framework. If code replaces everything with a new set of roles, downstream components may lose OIDC/client scope information.

The example uses:

```java
new LinkedHashSet<>(user.getAuthorities())
```

and appends business roles, rather than discarding all original authorities.

### 9.4. Why Not Map Roles with `roles.toString()`?

A set:

```text
["ROLE_VIEWER", "ROLE_EDITOR"]
```

must not become **one** authority with value `"[ROLE_VIEWER, ROLE_EDITOR]"`. Add each `GrantedAuthority` with its exact policy string.

### 9.5. Never Use Role Input from the Browser

`TenantRoleLookup` must read permissions from a **trusted source**, tied to verified `(issuer, subject)` and permitted tenant context. Never let a controller accept `?role=ADMIN` and return `Mono.just(Set.of("ROLE_ADMIN"))`.

## 10. Happy-Path Unit Test with `StepVerifier`

When testing mapping, no Spring `ApplicationContext` is needed.

```java
package com.example.security;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.ReactiveOAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TenantMappingReactiveOidcUserServiceTest {

    @Test
    void mapsTrustedRoleWithoutLosingOidcIdentity() {

        OidcUser fakeUser = OidcUserFixtures.userWithUserInfo();

        ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
            delegate = request -> Mono.just(fakeUser);

        TenantRoleLookup lookup = (issuer, subject) -> {
            assertThat(issuer)
                .isEqualTo("https://id.example.test");
            assertThat(subject)
                .isEqualTo("subject-42");

            return Mono.just(Set.of("ROLE_REPORT_VIEWER"));
        };

        var service =
            new TenantMappingReactiveOidcUserService(
                delegate,
                lookup
            );

        StepVerifier.create(
                service.loadUser(OidcRequestFixtures.request())
            )
            .assertNext(user -> {
                assertThat(user.getSubject())
                    .isEqualTo("subject-42");

                assertThat(user.getName())
                    .isEqualTo("subject-42");

                assertThat(user.getEmail())
                    .isEqualTo("alice@example.test");

                assertThat(user.getAuthorities())
                    .extracting(GrantedAuthority::getAuthority)
                    .contains(
                        "OIDC_USER",
                        "ROLE_REPORT_VIEWER"
                    );
            })
            .verifyComplete();
    }
}
```

### 10.1. What Does This Test Verify?

- `loadUser` returns a `Mono` emitting exactly **one `OidcUser`**.
- The service passes the right **issuer + subject** to membership lookup.
- Principal name is based on `sub` per the example design.
- OIDC profile remains intact after mapping.
- `ROLE_REPORT_VIEWER` is added.
- Original `OidcUserAuthority` is preserved.
- The `Publisher` **completes**, emitting neither a second user nor an error.

### 10.2. What Does This Test Not Verify?

- Whether the OP actually issued this ID Token.
- ID Token/JWKS signatures.
- The Token Endpoint.
- Whether Spring Security selects this user service during callbacks.
- HTTP endpoint URLs.
- Controller session/CSRF/authorization rules.

Those concerns have their own integration test layers.

### 10.3. Do Not Use `block()` by Default

A test could call `service.loadUser(...).block()`, but `StepVerifier` expresses **reactive signals** much more clearly:

- `onNext`.
- `onComplete`.
- `onError`.
- Empty publisher.
- Async/cancellation behavior when needed.

In production WebFlux, never call `block()` from the reactive security pipeline on an event-loop thread. In tests, prefer `StepVerifier` to verify the reactive contract cleanly.

## 11. Testing Without UserInfo

A user with an ID Token where `getUserInfo()` is `null` may still need mapping per policy.

```java
@Test
void supportsOidcPrincipalWithoutUserInfo() {

    OidcUser noUserInfo =
        OidcUserFixtures.userWithoutUserInfo();

    ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
        delegate = request -> Mono.just(noUserInfo);

    TenantRoleLookup lookup = (issuer, subject) ->
        Mono.just(Set.of("ROLE_REPORT_VIEWER"));

    var service = new TenantMappingReactiveOidcUserService(
        delegate,
        lookup
    );

    StepVerifier.create(
            service.loadUser(OidcRequestFixtures.request())
        )
        .assertNext(user -> {
            assertThat(user.getUserInfo()).isNull();
            assertThat(user.getSubject())
                .isEqualTo("subject-42");
            assertThat(user.getAuthorities())
                .extracting(GrantedAuthority::getAuthority)
                .contains("ROLE_REPORT_VIEWER");
        })
        .verifyComplete();
}
```

What to verify: **no NPE and no fabricating non-existent profile data**.

### 11.1. Never Auto-Fill Fake Emails

If `email` is missing, domain flows may choose to:

- Display a non-sensitive placeholder.
- Prompt the user to supply information.
- Deny features requiring a verified email.
- Read email from an internal profile service after permission checks.

Never fill in `"unknown@example.org"` and use it as an account-linking identity.

### 11.2. Never Skip `issuer`/`sub`

Even without UserInfo, `iss`/`sub` from the ID Token must remain the trusted basis of the identity context. Mapping unit tests should distinguish missing optional claims from missing required identity claims.

## 12. Testing `Mono.empty()` from the Delegate

In a reactive service, `Mono.empty()` is a distinct state—**neither success nor `onError`**.

Suppose the delegate returns no user:

```java
@Test
void emptyDelegateDoesNotBecomeSuccessfulLogin() {

    ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
        delegate = request -> Mono.empty();

    TenantRoleLookup lookup = (issuer, subject) ->
        Mono.just(Set.of("ROLE_REPORT_VIEWER"));

    var service = new TenantMappingReactiveOidcUserService(
        delegate,
        lookup
    );

    StepVerifier.create(
            service.loadUser(OidcRequestFixtures.request())
        )
        .expectErrorMatches(error ->
            error instanceof OAuth2AuthenticationException
        )
        .verify();
}
```

The example wrapper chooses:

```java
.switchIfEmpty(Mono.error(denied()))
```

to turn an absent user into a controlled authentication error.

### 12.1. Why Not Emit a Default Principal?

A fallback like:

```java
// WRONG: service failed to load user yet grants privileges.
return delegate.loadUser(request)
    .switchIfEmpty(Mono.just(adminUser));
```

turns a provider failure into **privilege escalation**. Never emit an `OidcUser` or broad authorities when required authentication/identity data is missing.

### 12.2. When Is `Mono.empty()` Valid?

Some repositories/lookups use `Mono.empty()` to mean "not found." However, at the **OIDC login principal-creation boundary**, the application must have an explicit policy for missing users. This lesson chooses **fail closed** when membership is absent, rather than letting the authentication pipeline end ambiguously.

## 13. Testing Missing Membership

A backend may recognize a valid `(issuer, sub)` that has not yet been granted tenant access.

Test lookup returning empty:

```java
@Test
void missingMembershipIsDenied() {

    ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
        delegate = request ->
            Mono.just(OidcUserFixtures.userWithUserInfo());

    TenantRoleLookup lookup = (issuer, subject) ->
        Mono.empty();

    var service = new TenantMappingReactiveOidcUserService(
        delegate,
        lookup
    );

    StepVerifier.create(
            service.loadUser(OidcRequestFixtures.request())
        )
        .expectErrorMatches(error ->
            error instanceof OAuth2AuthenticationException ex
                && "access_denied"
                    .equals(ex.getError().getErrorCode())
        )
        .verify();
}
```

You can add a case:

```java
TenantRoleLookup lookup = (issuer, subject) ->
    Mono.just(Set.of());
```

with the same expectation, because the example production service defines **empty role set = login not allowed**.

### 13.1. Test Policy, Not Assumptions

If your product allows new users to log in before holding business permissions, tests can expect a principal **with zero business roles**, while protected endpoints return 403. That is a different policy, not a protocol error.

What you must do is **state the policy explicitly and write negative tests**, never letting an empty behavior accidentally grant admin or unexpected login success.

### 13.2. `access_denied` and Error Messages

In a real application, map authentication/authorization errors to an appropriate UX without exposing:

- Internal user IDs.
- Access Tokens.
- Client secrets.
- Full UserInfo responses.
- Database exception details.
- Unnecessary tenant membership internals.

Tests may assert the error code without requiring stack traces in browser responses.

## 14. Testing Errors from Dependent Services

Suppose the membership lookup DB fails:

```java
@Test
void propagatesMembershipLookupFailure() {

    ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
        delegate = request ->
            Mono.just(OidcUserFixtures.userWithUserInfo());

    TenantRoleLookup lookup = (issuer, subject) ->
        Mono.error(new IllegalStateException(
            "Synthetic membership backend failure"
        ));

    var service = new TenantMappingReactiveOidcUserService(
        delegate,
        lookup
    );

    StepVerifier.create(
            service.loadUser(OidcRequestFixtures.request())
        )
        .expectError(IllegalStateException.class)
        .verify();
}
```

The example wrapper **propagates the error** rather than granting privileges. At the integration layer, the application can normalize the error into an authentication failure with a safe message; raw Java exceptions need not reach the browser.

### 14.1. Never Fall Back to Higher Roles

Anti-pattern:

```java
// DO NOT do this:
.onErrorResume(error ->
    Mono.just(adminOidcUser)
)
```

A database/network error must never elevate a user's privileges.

### 14.2. Be Careful with Low-Privilege Fallbacks

Sometimes an app wants to degrade gracefully when the membership service fails. If you allow users to continue logging in **without sensitive roles**, analyze the threat model, policy, and tests carefully. Never assume a low-privilege fallback is safe if the application has endpoints checking only `authenticated()` without checking roles.

### 14.3. Testing Delegate Errors

Include a case:

```java
ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
    delegate = request -> Mono.error(
        new IllegalStateException("Synthetic UserInfo failure")
    );
```

Expect the error never to turn into a privileged user. If the wrapper uses `onErrorMap` to normalize exceptions, assert the exact error type/domain code required by policy.

## 15. Testing Async Callbacks: Never Call Blocking APIs in Mappers

A reactive implementation might accidentally call:

```java
// Unsuitable when running directly on the event loop:
UserRoles roles = blockingJdbcRepository.findRoles(userId);
```

inside `map(...)` or `flatMap(...)`. Code may pass simple tests yet starve the event loop under production load.

### 15.1. Type-Correct Does Not Mean Non-Blocking at Runtime

The following **still blocks**:

```java
Mono.just(
    blockingRepository.findRoles(userId)
);
```

because `findRoles` executes **before `Mono` is created**.

A sound design uses genuine reactive data access:

```java
return roleRepository.findRoles(issuer, subject)
    .map(roles -> mapOidcUser(user, roles));
```

If a blocking adapter is unavoidable, configure a bounded elastic scheduler/isolated executor per policy instead of running blocking calls on the event loop—for example `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`. That is a temporary integration measure; it does not make JDBC non-blocking.

### 15.2. Unit Tests Alone Do Not Prove Non-Blocking Execution

A fast `StepVerifier` run does not prove production never blocks. You need:

- Code review of API dependencies.
- Tests verifying reactive subscription and schedulers if using custom adapters.
- BlockHound where appropriate and compatible with the runtime/test stack.
- Thread pool/event loop monitoring in integration/performance tests.
- Avoiding `.block()` and blocking I/O in the reactive authentication path.

Do not hard-code thread name assertions into every unit test, as schedulers can vary across environments.

## 16. Testing `Publisher` Laziness

Reactor typically assembles a pipeline when a method is called, then executes it upon subscription.

A mapping service should avoid sensitive side effects **before subscription** beyond pure setup.

Fake example:

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger calls = new AtomicInteger();

TenantRoleLookup lookup = (issuer, subject) ->
    Mono.defer(() -> {
        calls.incrementAndGet();
        return Mono.just(Set.of("ROLE_REPORT_VIEWER"));
    });
```

After:

```java
Mono<OidcUser> result =
    service.loadUser(OidcRequestFixtures.request());
```

and before `StepVerifier`, testing laziness requires checking precisely whether **delegate and lookup run at assembly time or subscription time**. In the wrapper example, `delegate.loadUser(request)` is invoked during assembly, whereas HTTP/DB side effects inside reactive publishers normally run on subscription.

After subscription:

```java
StepVerifier.create(result)
    .expectNextCount(1)
    .verifyComplete();

assertThat(calls.get()).isEqualTo(1);
```

This illustrates a **`Publisher` subscription**, without guaranteeing every implementation invokes factory functions at the same phase. When you need exact verification of subscribe/request/cancel, use `PublisherProbe`.

### 16.1. `PublisherProbe`

`reactor-test` provides `PublisherProbe` to verify whether a publisher was actually subscribed:

```java
import reactor.test.publisher.PublisherProbe;

PublisherProbe<Set<String>> probe =
    PublisherProbe.of(
        Mono.just(Set.of("ROLE_REPORT_VIEWER"))
    );

TenantRoleLookup lookup = (issuer, subject) ->
    probe.mono();
```

After running `StepVerifier` on the service:

```java
probe.assertWasSubscribed();
probe.assertWasRequested();
```

This is useful when fallback branches exist: verify the role lookup is subscribed or skipped under the exact expected conditions.

### 16.2. Avoid Over-Specified Tests

Do not couple tests to internal `map`/`flatMap` counts if business logic only cares about the resulting principal. Only assert subscription/cancellation when it is a meaningful contract, such as skipping the membership backend when the identity is invalid.

## 17. Testing Whether UserInfo Claims Have the Right `sub`

In OIDC, the UserInfo response carries a `sub` claim that must **match exactly** the `sub` of the ID Token used for the request.

Example:

```text
ID Token:  sub = "subject-42"
UserInfo:  sub = "subject-99"
```

That response must never be merged into the same user.

### 17.1. Simple Mapping Unit Tests Can Miss This Bug

If you construct:

```java
new DefaultOidcUser(
    authorities,
    idToken,
    userInfoWithDifferentSubject,
    "sub"
);
```

without invoking real UserInfo/OP service validation, the test may **fail to catch** the mismatch. Testing principal constructors does not test the protocol.

### 17.2. Choose the Right Place to Verify

To verify this behavior:

- Test `OidcReactiveOAuth2UserService` with a UserInfo HTTP stub per your API/version.
- Or test an explicit validation wrapper comparing both subjects before creating the mapped principal.
- In login integration tests, ensure ID Token and UserInfo are correlated properly.
- Do not use `mockOidcLogin()` to claim UserInfo subject mismatch handling was tested.

### 17.3. Testing Multiple Claim Sources

You may need to verify:

| Claim | ID Token | UserInfo | Expected behavior |
|---|---|---|---|
| `sub` | `subject-42` | `subject-42` | Use matching identity. |
| `sub` | `subject-42` | `subject-99` | Reject or fail per OIDC. |
| `email` | Absent | `alice@example.test` | Profile may supplement email. |
| `email_verified` | `false` | Absent | Do not treat email as verified. |
| `name` | `Alice` | `Alice Example` | Clear source/merge precedence rule. |
| `roles` | Absent | `["admin"]` | Never grant admin without trust policy. |

Response claims must be built via proper fixtures/test transport; never send real Access Tokens to mock endpoints.

## 18. Mapping Scopes to Authorities: Do Not Confuse Claims

In Spring Security, authorities from OAuth2 Login can include:

```text
OIDC_USER
SCOPE_openid
SCOPE_profile
ROLE_REPORT_VIEWER
```

However, a scope is a permission granted to an OAuth2 **client token**, whereas a role may be an application-level user permission. They are not automatically synonymous.

### 18.1. `hasRole` and `hasAuthority`

`hasRole("ADMIN")` by convention checks `ROLE_ADMIN`.

`hasAuthority("report:read")` checks the exact string `report:read`.

`hasAuthority("SCOPE_orders.read")` checks an exact scope authority if the principal/authentication holds it per the mapper.

Tests must match the exact strings. Do not write `hasRole("SCOPE_orders.read")` and wonder why authorization fails.

### 18.2. Never Grant Authorities from Arbitrary Claims Named `"roles"`

An OP might return OP-level roles rather than application roles. If production trusts a specific role claim, constrain:

- Trusted issuer.
- Appropriate client/audience.
- Claim location/type/schema.
- Tenant context.
- Precedence rules if the user belongs to multiple tenants.
- Allowed values and mapping table.
- Default deny when the claim is missing/malformed.
- Update/revocation lifecycle.

Unit tests must include both valid and malicious/malformed inputs.

### 18.3. Authority Preservation

If a custom mapper returns only:

```java
Set.of(new SimpleGrantedAuthority("ROLE_REPORT_VIEWER"))
```

dropping original authorities, downstream components may lose `OIDC_USER`/scope authorities that other rules depend on.

Assert that the result **contains both the original authorities and expected application authorities**, or document explicitly why an authority type is intentionally stripped.

## 19. Testing Role Mapping When Input Types Change

JSON claims might look like:

```json
{"roles": ["viewer", "editor"]}
```

or:

```json
{"roles": "viewer editor"}
```

or:

```json
{"roles": null}
```

or an unexpected shape:

```json
{"roles": {"nested": "unexpected"}}
```

Never cast blindly:

```java
@SuppressWarnings("unchecked")
List<String> roles =
    (List<String>) claims.get("roles");
```

if the provider contract does not guarantee schema stability. A type change in the response can trigger a `ClassCastException` during login.

### 19.1. Isolate Pure Claim Parsing for Testing

Example function taking claims:

```java
public static Set<String> parseAllowedRoles(
        Map<String, Object> claims) {

    Object raw = claims.get("roles");
    if (!(raw instanceof List<?> values)) {
        return Set.of();
    }

    Set<String> allowed = Set.of(
        "viewer",
        "editor"
    );

    Set<String> mapped = new HashSet<>();

    for (Object value : values) {
        if (!(value instanceof String text)) {
            continue;
        }

        if (allowed.contains(text)) {
            mapped.add(
                "ROLE_" + text.toUpperCase(Locale.ROOT)
            );
        }
    }

    return Set.copyOf(mapped);
}
```

This is an **example parser for a claim trusted under a dedicated contract**. Do not apply it to claims from an arbitrary provider without policy: a syntactically valid role list alone does not prove the user was granted business roles.

### 19.2. Input Test Table

| Input `roles` | Illustrative parser output |
|---|---|
| `["viewer"]` | `ROLE_VIEWER` |
| `["viewer","editor"]` | Both authorities. |
| `[]` | Empty set. |
| `null` | Empty set. |
| `"viewer"` | Empty set per List-only contract. |
| `["viewer", 123]` | Accepts only valid string entries. |
| `["admin"]` | Grants nothing because it is outside the allowlist. |
| `[{"name":"viewer"}]` | Ignores map entries. |
| `["VIEWER"]` | Rejected if contract is case-sensitive. |

Import `Map`, `List`, `Set`, `HashSet`, and `Locale`. Depending on your real schema, you may reject the entire malformed claim instead of skipping individual items; **tests must match the chosen policy**.

### 19.3. Avoid Silent Privilege Expansion

Never blindly turn arbitrary strings into:

```java
new SimpleGrantedAuthority("ROLE_" + input)
```

if input could contain `SUPER_ADMIN` or out-of-policy values. Use an application mapping table/allowlist rather than minting authorities from free-form strings.

## 20. Using `DefaultReactiveOAuth2UserService` for Non-OIDC Logins

In non-OIDC OAuth2 Login, the service generic is:

```java
ReactiveOAuth2UserService<OAuth2UserRequest, OAuth2User>
```

A wrapper can enrich or normalize received attributes:

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.oauth2.client.userinfo.OAuth2UserRequest;
import org.springframework.security.oauth2.client.userinfo.ReactiveOAuth2UserService;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;
import org.springframework.security.oauth2.core.user.OAuth2User;

import reactor.core.publisher.Mono;

public final class ProfileMappingReactiveOAuth2UserService
        implements ReactiveOAuth2UserService<
            OAuth2UserRequest, OAuth2User> {

    private final ReactiveOAuth2UserService<
        OAuth2UserRequest, OAuth2User> delegate;

    public ProfileMappingReactiveOAuth2UserService(
            ReactiveOAuth2UserService<
                OAuth2UserRequest, OAuth2User> delegate) {

        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2User> loadUser(
            OAuth2UserRequest request) {

        return delegate.loadUser(request)
            .map(user -> {

                Object id = user.getAttributes().get("id");

                if (!(id instanceof String externalId)
                        || externalId.isBlank()) {
                    throw new IllegalArgumentException(
                        "Required external id is missing"
                    );
                }

                Map<String, Object> normalized =
                    new LinkedHashMap<>(user.getAttributes());

                normalized.put(
                    "app_external_key",
                    request.getClientRegistration()
                        .getRegistrationId() + ":" + externalId
                );

                return (OAuth2User) new DefaultOAuth2User(
                    user.getAuthorities(),
                    normalized,
                    "app_external_key"
                );
            });
    }
}
```

**Design note:** the `registrationId + ":" + externalId` key only illustrates namespacing. In a real system, add issuer/provider trust, parsing/normalization of the external ID, and account linking. Never use this string alone to grant data access or link accounts without verification.

### 20.1. Testing Plain OAuth2 Attributes

Create a fake OAuth2 user:

```java
OAuth2User fake = new DefaultOAuth2User(
    Set.of(new SimpleGrantedAuthority("OAUTH2_USER")),
    Map.of(
        "id", "external-42",
        "login", "alice"
    ),
    "id"
);

ReactiveOAuth2UserService<OAuth2UserRequest, OAuth2User>
    delegate = request -> Mono.just(fake);
```

Create `OAuth2UserRequest`:

```java
var request = new OAuth2UserRequest(
    OidcRequestFixtures.registration(),
    OidcRequestFixtures.accessToken()
);
```

This snippet reuses the registration fixture from the OIDC section only to avoid repeating config; in a real project, maintain an OAuth2-only fixture matching the corresponding flow's provider/registration.

Test:

```java
var service =
    new ProfileMappingReactiveOAuth2UserService(delegate);

StepVerifier.create(service.loadUser(request))
    .assertNext(user -> {
        assertThat(user.getName())
            .isEqualTo("company:external-42");
        assertThat(user.getAttributes())
            .containsEntry(
                "app_external_key",
                "company:external-42"
            );
    })
    .verifyComplete();
```

### 20.2. Why Distinguish OIDC Tests?

`DefaultOAuth2User` has neither `OidcIdToken` nor OIDC-specific `getUserInfo()`. If production uses `OidcUser`, use the matching OIDC classes and generics in tests to avoid testing the wrong code path.

## 21. Testing Issuer and Tenant Mapping

In a multi-tenant system:

```text
tenant alpha -> issuer https://id.alpha.example
tenant beta  -> issuer https://id.beta.example
```

The same `sub="1001"` across two issuers does not prove the same user.

### 21.1. Identity Test Matrix

| Issuer | Subject | Tenant | Expected |
|---|---|---|---|
| A | `1001` | alpha | Look up alpha membership for identity A/1001. |
| A | `1002` | alpha | Must not receive roles of A/1001. |
| B | `1001` | beta | Must not receive roles of A/1001. |
| B | `1001` | alpha | Reject if policy forbids B in alpha. |
| A | missing `sub` | alpha | Reject; never fall back to email. |
| metadata issuer != ID Token issuer | any | alpha | Reject at OIDC validation/registration boundary. |

### 21.2. Tests Must Use a Verified Tenant Source

If the app reads the tenant from a query parameter:

```text
?tenant=alpha
```

that must not be treated as proof the user holds membership in alpha. For custom lookups, pass a **trusted tenant context** bound to the session, client registration, issuer, or verified membership.

A user may be allowed to switch tenants, yet every switch must verify authorization, not just swap a string.

### 21.3. Never Let a User Service Fetch Arbitrary Issuers

`ReactiveOAuth2UserService` must never accept an arbitrary URL from the browser and fetch UserInfo from it. `ClientRegistration`/provider metadata must come from trusted sources; outbound HTTP to the UserInfo endpoint needs destination controls to prevent SSRF/token exfiltration.

## 22. Testing That Email Is Not Used as a Unique Identity

An important test:

```text
Issuer A:
  sub=subject-A
  email=shared@example.test

Issuer B:
  sub=subject-B
  email=shared@example.test
```

If application mapping looks up users solely by email and merges both accounts, it can cause account takeover.

Tests should assert:

- Identity key relies on verified **issuer + subject**.
- Email is used only as a supporting attribute/lookup per policy.
- External identity B is never auto-linked to account A just because emails match.
- Permissions from issuer A are never automatically granted to issuer B.

### 22.1. `email_verified` Is Not Enough for Every Account Link

Even when both OPs set `email_verified=true`, that does not guarantee both external identities have equal rights to an internal account. The product needs an authorized account-linking workflow and tests for recycled/compromised emails.

### 22.2. Testing Absence of Claims

If UserInfo lacks `preferred_username`, display name, or email, the service needs an explicit policy: omit, fall back to another profile field, or reject the feature. Never let missing optional claims trigger unexpected `NullPointerException`s.

## 23. Reactive Specifics: Three Primary `Mono` Outcomes

In a reactive user service:

```text
Mono<OidcUser>
  |
  +-- onNext(user) -> onComplete
  |
  +-- onComplete with no user
  |
  +-- onError(error)
```

Test each separately:

| Signal | Meaning | Behavior in example |
|---|---|---|
| `onNext(user), onComplete` | Mapping succeeded | Returns principal with expected authorities. |
| Empty `onComplete` | No identity/membership | Converted to `access_denied`. |
| `onError` | HTTP/DB/validation error | Grants no permissions; propagates/translates per policy. |

A test using only:

```java
.expectNextCount(1)
```

without inspecting fields/authorities can miss mapping bugs. Use `assertNext(...)` for business properties, followed by `verifyComplete()`.

### 23.1. Verify It Never Emits Two Users

`Mono` emits at most one item. If a custom service joins multiple sources/records, it must select an account deterministically or reject ambiguity; never pick an arbitrary first item across multiple external identities.

### 23.2. Test Cancellation When Appropriate

If the reactive pipeline has side effects or long-running external calls, cancellation tests matter so processing stops when an authentication request is canceled. Reactor Test provides cancellation/`PublisherProbe` APIs; you do not need them on every trivial method, but you must understand cancellation in WebFlux.

### 23.3. Never Subscribe Manually Inside `loadUser`

Wrong:

```java
roleLookup.rolesFor(issuer, sub)
    .subscribe(roles -> updateSomeGlobalState(roles));

return delegate.loadUser(request);
```

This detaches work into a side effect outside the `Mono` chain, making errors, cancellation, and context hard to control. Instead, compose with `flatMap`/`map` so the role lookup stays part of the authentication pipeline.

## 24. Limitations When Mocking the Delegate

When unit-testing with:

```java
ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
    delegate = request -> Mono.just(fakeUser);
```

we **bypassed** steps inside the real delegate, such as:

- Building the UserInfo HTTP request.
- Attaching the Access Token to the `Authorization` header.
- Parsing the response.
- Handling HTTP 401/403/5xx.
- Checking that OIDC `sub` matches.
- Rules when no UserInfo endpoint is configured.
- Provider-specific claim normalization inside the delegate.

That is appropriate when the test focuses solely on **business role mapping**.

### 24.1. Test the Delegate Separately

To verify UserInfo HTTP behavior:

1. Use an OP/UserInfo stub in the test environment.
2. Configure a test `ClientRegistration` with a known issuer, token URI, and UserInfo URL.
3. Call `OidcReactiveOAuth2UserService.loadUser(request)` or the matching authentication integration.
4. Assert the outbound request carries the fixture token in the right place.
5. Return UserInfo JSON with matching/mismatched `sub`, malformed JSON, and HTTP errors.
6. Assert the resulting principal or error signal.
7. Never let stub endpoint requests reach production hosts.
8. Avoid logging raw tokens—even synthetic ones—with patterns easy to copy into production.

Depending on the Spring Security version, how you customize the built-in service's `WebClient`/transport may vary. Check your project version's extension points when writing HTTP tests rather than assuming a particular setter exists everywhere.

### 24.2. Never Test a Built-In Service with a Fake Replacing All Behavior

If a test only invokes a wrapper with a fake delegate and claims "UserInfo `sub` mismatch is handled," the assertion skips the layer enforcing validation. Write tests at the right layer.

## 25. Testing UserInfo HTTP with a Mock Server

An integration test requiring a test server can serve:

```http
GET /userinfo HTTP/1.1
Host: localhost:<test-port>
Authorization: Bearer synthetic-access-token
```

And respond:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sub": "subject-42",
  "name": "Alice Example"
}
```

Cases to verify:

| Response | Expected |
|---|---|
| 200 + matching `sub` | Builds/merges UserInfo per policy. |
| 200 + different `sub` | Rejects. |
| 200 missing `sub` | Rejects UserInfo per OIDC contract. |
| 401 | Never emits a privileged principal. |
| 403 | Never falls back to broader roles. |
| 429 | Rate-limits/backs off per policy; no infinite retry. |
| 500 | Login failure/degrades per explicit policy. |
| Empty body/invalid JSON | Error signal handled. |
| Oversized body | Enforces HTTP client size limits. |
| Redirect to another host | Never forwards token to unapproved destination. |
| Timeout | Never hangs event loop or holds session indefinitely. |

### 25.1. WireMock or MockWebServer?

Either can serve fake HTTP responses, though **neither is required** for `ReactiveOAuth2UserService` unit tests using a fake delegate.

When used, bind the server to localhost or a test-only interface, use a dynamic port, and reset state between tests. Never hard-code a port prone to conflicts during parallel CI runs.

### 25.2. An HTTP Stub Does Not Verify Real ID Tokens

Even when the service calls real UserInfo via a local stub, the test may still use an unsigned `OidcIdToken` fixture. To verify **ID Token signature/issuer/audience/nonce**, test the token decoder/authentication component or run a full OIDC flow integration test with test signing keys.

### 25.3. Never Send Real Tokens to HTTP Fixtures

Even on localhost, avoid using real client secrets/Access Tokens in requests. Test server access logs and CI output may capture full `Authorization` headers.

## 26. `WebTestClient` and `mockOidcLogin()`: A Different Goal

In reactive WebFlux, `spring-security-test` supports:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;
```

A request:

```java
webTestClient
    .mutateWith(mockOidcLogin()
        .idToken(token -> token.claim("sub", "subject-42")))
    .get()
    .uri("/account/me")
    .exchange()
    .expectStatus().isOk();
```

tests a controller receiving an authenticated OIDC principal.

### 26.1. Why Is `loadUser` Not Invoked?

`mockOidcLogin()` injects test authentication directly at the WebFlux Security layer instead of executing:

```text
Authorization Code -> token endpoint -> ID Token validation
    -> ReactiveOAuth2UserService.loadUser()
```

Therefore:

- Controllers reading `OidcUser` can be tested.
- `hasRole`/`hasAuthority` can be tested when authorities are supplied in the mock.
- UserInfo HTTP is not tested.
- Application role mappers inside the user service do not run automatically.
- Real provider configuration/callbacks are not tested.

### 26.2. Both Tests Should Coexist

**Service unit test**:

```java
StepVerifier.create(mappingService.loadUser(request))
    .assertNext(user -> {
        // Verify mapped authorities/claims.
    })
    .verifyComplete();
```

**WebFlux route test**:

```java
webTestClient.mutateWith(mockOidcLogin()
        .authorities(
            new SimpleGrantedAuthority("ROLE_REPORT_VIEWER")
        ))
    .get().uri("/reports")
    .exchange()
    .expectStatus().isOk();
```

The second test verifies **the route once the authority already exists**, not whether the authority was mapped accurately from external identity in the user service.

## 27. Building a Simple WebFlux Controller

Example:

```java
package com.example.web;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class AccountController {

    @GetMapping("/account/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal OidcUser principal) {

        return Mono.just(
            Map.of(
                "sub", principal.getSubject()
            )
        );
    }
}
```

WebFlux test:

```java
package com.example.web;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(AccountController.class)
class AccountControllerWebFluxTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void oidcUserSeesOwnSubject() {
        webTestClient
            .mutateWith(mockOidcLogin()
                .idToken(token ->
                    token.claim("sub", "subject-42")
                ))
            .get()
            .uri("/account/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.sub").isEqualTo("subject-42");
    }
}
```

This is a **WebFlux slice**; if the app has custom security configuration or service dependencies, import/mock appropriately so the filter chain/method security applies per test goal.

### 27.1. Do Not Mix `MockMvc` with Reactive `WebTestClient`

The Servlet `MockMvc` helper is:

```java
SecurityMockMvcRequestPostProcessors.oidcLogin()
```

The Reactive WebFlux helper is:

```java
SecurityMockServerConfigurers.mockOidcLogin()
```

Use the matching server/application context type. A project using `WebClient` is not automatically a WebFlux server if it still runs Spring MVC.

### 27.2. `@WebFluxTest` vs. Full Context

`@WebFluxTest` loads only the reactive web slice. For integration tests of OAuth2 Login configuration and the real user service, use `@SpringBootTest` with an appropriately bound `WebTestClient`, optionally with `@AutoConfigureWebTestClient` per setup.

If a test slice lacks the user service Bean, do not stub it with an empty mock and claim integration wiring was verified.

## 28. Testing Route Authorization After Mapping

A policy:

```java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/reports/**")
        .hasRole("REPORT_VIEWER")
    .anyExchange()
        .authenticated()
);
```

Cases:

| Principal | Authority | Request | Outcome |
|---|---|---|---|
| Anonymous | None | `GET /reports` | Authentication required. |
| OIDC user | `ROLE_REPORT_VIEWER` | `GET /reports` | Allowed if controller succeeds. |
| OIDC user | `ROLE_OTHER` | `GET /reports` | 403. |
| OIDC user | No business role | `GET /reports` | 403. |

Test:

```java
webTestClient
    .mutateWith(mockOidcLogin()
        .authorities(
            new SimpleGrantedAuthority("ROLE_OTHER")
        ))
    .get()
    .uri("/reports")
    .exchange()
    .expectStatus().isForbidden();
```

### 28.1. `ROLE_REPORT_VIEWER` Differs from `REPORT_VIEWER`

`hasRole("REPORT_VIEWER")` normally checks for `ROLE_REPORT_VIEWER`.

Mapping service tests must produce the exact authority expected by the rule. Do not merely assert that the authority set is non-empty.

### 28.2. Test Unauthenticated Requests Too

Browser OAuth2 Login chains may redirect to the login page/OP instead of returning 401. Reactive API chains may return 401. Assertions must match the **real entry point and security chain**, rather than hard-coding one status for all endpoints.

### 28.3. Method Security Needs a Real Proxy

If `@PreAuthorize` sits on a service Bean, a mocked service in `@WebFluxTest` usually does not execute production method security. To test method security, load the real Bean/proxy and enable reactive method security per configuration.

## 29. Testing Mapping Errors Without Information Leakage

A custom mapper may throw:

```java
new OAuth2AuthenticationException(
    new OAuth2Error("access_denied")
)
```

That is a security-relevant error. Tests should verify:

- Explicit error code per policy.
- No user/role is emitted after the error.
- No fallback to admin.
- No logging of raw ID Token/Access Token/Refresh Token.
- No stack trace/UserInfo response returned to the browser.
- If audited, only sanitized issuer alias, registration, correlation ID, and error code are recorded.

### 29.1. Testing the Error Signal

```java
StepVerifier.create(service.loadUser(request))
    .expectErrorMatches(error ->
        error instanceof OAuth2AuthenticationException ex
            && "access_denied"
                .equals(ex.getError().getErrorCode())
    )
    .verify();
```

### 29.2. Login Failure HTTP Status Is Not Always 403

A `loadUser` error may be handled by Spring Security's OAuth2 Login failure handler via a redirect or a specific response depending on configuration. Never assume every login `OAuth2AuthenticationException` turns into HTTP 403.

Unit tests should assert the reactive error; separate integration tests verify the failure handler/UX.

### 29.3. Do Not Inspect Logs in Tests to Confirm Token Values

When debugging, log only metadata such as issuer alias, registration ID, diagnostic principal key, and error code. Never print raw `request.getAccessToken().getTokenValue()`.

## 30. Testing Error Propagation Between Delegate and Lookup

There are two error sources:

```text
delegate.loadUser()
  |
  +-- UserInfo/claims error
  |
  v
membershipLookup.rolesFor(...)
  |
  +-- DB/permissions error
```

Unit tests should distinguish them:

| Source | Fake output | Expected behavior |
|---|---|---|
| Delegate | `Mono.just(user)` | Runs lookup then maps. |
| Delegate | `Mono.empty()` | Rejects; does not call lookup. |
| Delegate | `Mono.error(error)` | Propagates/normalizes; does not call lookup. |
| Lookup | `Mono.just(roles)` | Maps authorities. |
| Lookup | `Mono.just(emptySet)` | Denies per example policy. |
| Lookup | `Mono.empty()` | Denies. |
| Lookup | `Mono.error(error)` | Fails closed; emits no user. |

You can use `PublisherProbe`, a fake counter, or Mockito `verify(...)` to confirm role lookup **is not invoked when the delegate fails**.

### 30.1. Never Retry Indefinitely on the Authentication Path

If the membership service/network fails, unbounded retries can hold login requests open and cause DoS. If transient retries are needed, cap attempts, timeouts, and backoff, and retry only appropriate idempotent errors.

### 30.2. Authenticated Without Membership

One product might allow a user to log in and view an onboarding page; another blocks login until permissions are granted. Unit tests must codify that decision rather than treating a framework default as an implicit policy.

## 31. Testing Multiple Registrations and Claim Name Mapping

One provider returns:

```json
{
  "sub": "subject-42",
  "preferred_username": "alice"
}
```

Another provider may return:

```json
{
  "sub": "subject-99",
  "preferred_username": "alice"
}
```

If the application sets:

```text
principalName = preferred_username
```

collisions can occur. `OAuth2AuthorizedClientService` in Servlet/Reactive variants typically keys authorized clients by registration ID and principal name; changing how principal name is derived can break token loading.

### 31.1. Testing Registration-Specific Mapping

Tests should ensure:

- Issuer A and registration A yield principal A.
- Issuer B and registration B yield principal B.
- Matching display names do not merge identities.
- Changing role mapping for tenant A does not affect tenant B.
- Client registration lookups never come from arbitrary URL input.
- UserInfo endpoints match the right provider.
- If account linking is supported, it uses a dedicated verification/consent flow.

### 31.2. Mapping Claim Type Mismatches

A missing/malformed `sub` claim must never fall back to an arbitrary email or username. If the app requires a different external ID, define a trusted provider schema and explicit validation.

### 31.3. Testing Stable Principal Names

If a custom mapper builds a new `DefaultOidcUser`, check:

```java
assertThat(user.getName()).isEqualTo("subject-42");
```

This matters when the authorized client store, auditing, and session logic rely on `Authentication.getName()`.

## 32. Never Accidentally Drop UserInfo When Mapping `OidcUser`

When building a new `DefaultOidcUser` from the ID Token alone:

```java
new DefaultOidcUser(authorities, user.getIdToken(), "sub");
```

while `user.getUserInfo()` was previously non-null, you can discard already-fetched profile data.

The wrapper above branches cleanly:

```java
user.getUserInfo() == null
    ? new DefaultOidcUser(
        authorities,
        user.getIdToken(),
        "sub"
      )
    : new DefaultOidcUser(
        authorities,
        user.getIdToken(),
        user.getUserInfo(),
        "sub"
      )
```

Tests should verify:

- The ID Token retains all required claims.
- UserInfo is preserved when present.
- `sub`/`getName()` does not change unintentionally.
- Prior authorities are preserved or changed intentionally per policy.
- No token/profile copies leak into logs.

### 32.1. Never Mutate Framework Maps Directly

Claim maps can be immutable. Instead of mutating `user.getClaims()`, construct a new structure when needed, following the `DefaultOidcUser`/`DefaultOAuth2User` constructor/API.

### 32.2. Some Claims Can Overlap Between ID Token and UserInfo

When a claim appears in both sources, the implementation's merge behavior can affect `getClaims()`. If business logic depends on precedence, test it explicitly against your actual framework/version, and avoid using an overlapping claim as an identity/authorization key when a more trustworthy choice exists.

## 33. Testing Timeouts and Cancellation

An authentication user service may call a UserInfo endpoint and a membership backend. If either downstream service stalls, login must not hang indefinitely.

Example timeout policy at the boundary:

```java
return delegate.loadUser(request)
    .timeout(Duration.ofSeconds(5));
```

This is only a fragment illustrating a time limit; real timeouts must consider the full pipeline and be configured per SLA/provider. Never hard-code an unvalidated constant across all tenants.

### 33.1. Unit Testing Timeouts Without Wall-Clock Delays

`reactor-test` provides `StepVerifier.withVirtualTime(...)` to test scheduler-based operators virtually when set up properly.

However, not all HTTP network I/O or external libraries obey virtual time. For UserInfo HTTP stubs, use short real timeouts and deterministic stubs or mock publishers.

### 33.2. Fail Closed on Timeout

Do not do:

```java
.onErrorResume(TimeoutException.class,
    error -> Mono.just(adminUser))
```

If membership is unknown, never grant elevated permissions by default. If an offline/last-known-good roles cache exists, it needs expiry, revocation, and its own policy; tests must ensure revoked permissions are not honored.

### 33.3. Cancellation and Resource Cleanup

When a request is canceled, reactive operators/HTTP clients must release resources properly. A user service must never manually `subscribe()` to an unmanaged background task just to store roles, as cancellation and errors become uncontrollable.

## 34. Testing That HTTP Clients Never Send Tokens to Wrong Destinations

An OIDC user service may call `userinfo_endpoint` with an Access Token. When configuring dynamic providers/tenants, ensure this URL is trusted.

Risk:

```text
UserInfo endpoint in metadata:
  https://untrusted.example/collect

Application:
  GET that URL
  Authorization: Bearer <user-access-token>
```

That is **credential exfiltration** if metadata/registrations are unvalidated.

### 34.1. Integration Testing Destinations

An HTTP stub can record:

- Host/path hit by the request.
- Presence of `Authorization: Bearer synthetic-access-token`.
- Absence of client secret/Refresh Token.
- Not following redirects to unapproved hosts.
- TLS/timeout/destination restrictions per policy.

No need to expose raw tokens to test callers; compare fixture values inside stub server isolation.

### 34.2. Mapping Unit Tests Do Not Catch SSRF

Unit tests using a fake delegate perform no network I/O, so they cannot detect UserInfo destination SSRF. Assign security requirements to the appropriate test layers.

## 35. Integration Wiring Tests That Actually Invoke the User Service

A common issue: `TenantMappingReactiveOidcUserService` has passing unit tests, yet production Spring Security **never invokes that class** because:

- The Bean was never registered.
- Multiple Beans share the same generic type and configuration picks the wrong one.
- The non-OIDC OAuth2 user service was customized instead of the OIDC service.
- The matching `SecurityWebFilterChain` did not receive the configuration.
- The test context differs from production.
- Provider-specific registrations or chain ordering route the flow through a different authentication manager.

### 35.1. Dedicated Wiring Tests Are Needed

An integration test can use a test OP:

1. Boot the WebFlux application context with the real security config.
2. Use a test `ClientRegistration` pointing at the OP stub.
3. Initiate a login authorization flow with valid `state`/session context.
4. Have the OP stub issue the authorization code/tokens/ID Token per test config.
5. Verify the custom user service was invoked.
6. Verify the logged-in user holds the right authorities.
7. Verify failure when membership does not exist.
8. Never use a production OP or production credentials.

Depending on your Spring Security version, the API to register the service in reactive OAuth2 Login config differs from Servlet. **Do not blindly copy Servlet `oauth2Login().userInfoEndpoint().oidcUserService(...)` into WebFlux** without checking your version's Reactive DSL/extension points.

### 35.2. `@MockBean` Can Hide Real Wiring

If a test replaces the entire authentication manager/user service with a mock returning an `OidcUser`, it no longer proves the production mapper runs. Use a **spy** or test stubs at the HTTP/membership boundary to keep custom mapping real.

### 35.3. Test Deeply Enough Without Unnecessary External Dependencies

Not every unit test needs a real browser. Only tests verifying full callback/session/cookie/OP flows need the corresponding integration/E2E setup.

## 36. Testing Reactive Security Context and Concurrency

In WebFlux, authentication usually lives in the **Reactor Context**, not just Servlet-style `ThreadLocal`.

If a custom mapper calls:

```java
SecurityContextHolder.getContext()
    .getAuthentication();
```

inside a callback running on another thread, it may miss the context or introduce bugs from invalid assumptions.

### 36.1. Use Identity Present in the Request

`OidcUserRequest` contains the relevant client registration/access token/ID token; the post-delegate identity carries issuer/subject. For business role lookups, pass **explicit identifiers**:

```java
roleLookup.rolesFor(issuer, subject)
```

rather than having role lookup read an unreliable `ThreadLocal`.

### 36.2. Testing Multiple Concurrent Users

Concurrency tests can uncover shared state:

```text
User A -> subject-A -> ROLE_VIEWER
User B -> subject-B -> ROLE_EDITOR
```

Never store the current OIDC user in a mutable singleton field and reuse it across requests. `ReactiveOAuth2UserService` may be a singleton Bean, yet `loadUser` must process inputs per subscription/request without mixing shared mutable user state.

### 36.3. Testing Concurrent Mapping

Use `Flux.merge` over multiple `Mono<OidcUser>` fixtures with `StepVerifier`; each emission must carry the exact matching issuer, subject, and authorities. Never rely on the completion order of async network calls to correlate identity.

### 36.4. Avoid Caching Roles by Email

If membership is cached by email, two providers sharing an email can collide. Cache keys must include the full identity boundary—such as `issuer + sub + tenant` per trusted policy—with proper expiry/invalidation.

## 37. Account Linking and Delegated Access

A user might log in via the company OP and also link a partner account.

```text
Internal Account employee-42
  |
  +-- Issuer company, sub=subject-C
  |
  +-- Issuer partner, sub=subject-P
```

A custom user service must never conclude two records belong to the same internal user merely because emails match. Account linking requires a dedicated proof-of-control/consent workflow.

### 37.1. Tests to Include

- Unlinked company identity → cannot use partner tokens.
- Two identities with the same email → never auto-linked.
- Verified linked identity → maps to internal account per policy.
- Unlink partner → can no longer use partner authorized clients/roles.
- Tenant membership change → permissions update per policy.
- Provider issuer migration → never silently reuses old issuer tokens/roles.

### 37.2. Never Treat Access Tokens as Identity Keys

Access Tokens can rotate/expire and are not permanent identifiers. Use verified `(issuer, subject)` and application identity mapping; never use the Access Token string as a user ID or log key.

## 38. Security Regression Testing by Scenario Table

| ID | Case | Fixture/source | Expected |
|---|---|---|---|
| R01 | Delegate returns normal OIDC user | `Mono.just(user)` | Mapping succeeds. |
| R02 | Delegate returns no user | `Mono.empty()` | Denies per policy. |
| R03 | Delegate HTTP error | `Mono.error(...)` | Fails closed; skips role lookup. |
| R04 | UserInfo present | Valid `OidcUserInfo` | Profile preserved. |
| R05 | UserInfo absent | `null` | No NPE. |
| R06 | UserInfo `sub` mismatch | Stub OP | Rejects per OIDC. |
| R07 | UserInfo missing `sub` | Stub OP | Rejects. |
| R08 | Valid membership | Reactive role lookup | Receives permitted authorities. |
| R09 | Missing membership | `Mono.empty()` | Denies or defined behavior. |
| R10 | Empty membership | Empty `Set` | Grants no roles against policy. |
| R11 | Membership DB error | `Mono.error(...)` | No admin fallback. |
| R12 | Same `sub`, different issuer | Two OIDC fixtures | Identities not merged. |
| R13 | Same email, different subject | Two OIDC fixtures | No automatic account linking. |
| R14 | Wrong-type role claim | JSON/Map fixture | Fails/ignores per contract. |
| R15 | Role outside allowlist | Untrusted `admin` claim | Grants no elevated roles. |
| R16 | Mapping adds role | Trusted lookup | Preserves original OIDC authorities. |
| R17 | Principal name | `sub` fixture | Stable identity key. |
| R18 | OAuth2-only provider | `DefaultOAuth2User` | Maps cleanly in generic service. |
| R19 | WebFlux route with role | `mockOidcLogin()` | HTTP allowed. |
| R20 | WebFlux route missing role | Mock OIDC user | HTTP 403. |
| R21 | UserInfo endpoint error | HTTP stub | Never emits fake privileges. |
| R22 | UserInfo HTTP timeout | Stub/publisher | Times out/fails per policy. |
| R23 | Untrusted UserInfo URL | Endpoint policy | Never sends token. |
| R24 | Custom service not wired | Full test config | Test catches missing invocation. |
| R25 | Two concurrent users | Two publishers | No authority cross-talk. |
| R26 | Role lookup skipped on delegate error | `PublisherProbe`/Mockito | No unintended subscription. |
| R27 | Failures do not log tokens | Logging assertion if needed | Zero raw credentials. |
| R28 | Provider change/tenant mismatch | Multiple registrations | Rejects/reauthorizes at boundary. |

This table is a **coverage plan**, not a claim that a single unit test can verify every case. Cases involving HTTP/OP/security wiring require the appropriate integration test layer.

## 39. Common Test Execution Failures

| Symptom | Possible cause | Resolution |
|---|---|---|
| `Cannot resolve symbol StepVerifier` | Missing `reactor-test` in test scope. | Add test dependency aligned with Reactor version. |
| `OidcUserRequest` not found | Wrong package import or missing `oauth2-client`. | Check Spring Security version/classpath. |
| Test uses `OAuth2UserRequest` while service needs `OidcUserRequest` | Wrong generic/service type. | Build the right OIDC fixture. |
| UserInfo mapper test passes yet route lacks role | Spring wiring does not invoke custom service. | Test reactive login configuration. |
| `mockOidcLogin()` route passes despite mapping bug | Mock login bypasses mapping. | Add `StepVerifier` service unit tests. |
| `@AuthenticationPrincipal OidcUser` is null | Test injects non-OIDC principal. | Use `mockOidcLogin()`. |
| `@WebFluxTest` cannot find Bean | Slice does not load business dependencies. | Mock/import Beans within slice scope. |
| `getName()` differs from expected | Different name attribute key or claims. | Check `DefaultOidcUser` constructor/fixture. |
| `ClassCastException` on roles | Wrong claim data type. | Add parser/schema validation and negative cases. |
| Claims map immutable | Test/custom mapper tries to mutate Map. | Copy data or build new principal via API. |
| Authorities lost after mapper | Built new set without original OIDC authorities. | Preserve per policy and assert. |
| `Mono.empty()` causes unclear login error | No policy for empty publisher. | Use `switchIfEmpty`/fail closed. |
| Mapping fails yet test still succeeds | Overly broad `onErrorResume` fallback. | Assert error path, remove privilege fallback. |
| Test hangs | Blocking I/O, incomplete `Mono`, or external dependency. | Use test fakes and timeouts/resource cleanup. |
| Test flaky depending on date | `Instant.now()` and token expiry. | Fixed `Clock`/Instants. |
| 401 instead of 403 | Missing valid authentication. | Check entry point/filter chain. |
| 302 instead of 401 | Browser OAuth2 login redirect. | Match WebFlux chain assertions. |
| UserInfo test calls production OP | Reused test registration/`issuer-uri`. | Use test profile and local stub. |
| Same email across two issuers merged | Mapped by email instead of `iss`/`sub`. | Enforce identity boundary. |
| Logout test does not clear token | RP session and authorized client have separate lifecycles. | Test exact storage/policy. |
| Tests fail when run in parallel | Shared static mutable principal/lookup/cache. | Per-test fixtures, immutable data. |

### 39.1. Controlled Debugging Workflow

```mermaid
flowchart TD
    A["Reactive mapping test fails"] --> B{"Does loadUser emit a user?"}
    B -->|No, empty| C["Check delegate and switchIfEmpty"]
    B -->|No, error| D{"Error from delegate or lookup?"}
    D -->|Delegate| E["UserInfo/OIDC fixture, HTTP stub, sub validation"]
    D -->|Lookup| F["Membership DB/fake, timeout, error policy"]
    B -->|Yes| G{"Principal/claims correct?"}
    G -->|No| H["Issuer/sub, UserInfo merge, name claim"]
    G -->|Yes| I{"Authorities correct?"}
    I -->|No| J["Role mapping, allowlist, preservation"]
    I -->|Yes| K{"WebFlux route still failing?"}
    K -->|Yes| L["mockOidcLogin vs real service wiring, security matcher"]
    K -->|No| M["Test layer complete; check OP flow if required by goal"]
```

Never debug by printing token values. Log only harmless metadata/fixture identifiers, error codes, and registration aliases.

## 40. Anti-Patterns to Avoid

### 40.1. Testing Only with `mockOidcLogin()`

It tests routes with pre-existing authentication, without running your user service or UserInfo HTTP. You must write direct unit tests for `loadUser`.

### 40.2. Blindly Using Servlet `@WithMockUser` in Reactive Tests

WebFlux Test has its own mock OIDC authentication. When the application needs `OidcUser`, generic username/password mocks do not test the right principal type.

### 40.3. Mapping Roles from Claims Without a Trust Policy

`"role": "admin"` alone does not warrant `ROLE_ADMIN`. Check issuer, schema, allowlist, and business policy.

### 40.4. Falling Back to Admin on Lookup Error

A DB/HTTP error must never turn into elevated privileges. Fail closed per policy.

### 40.5. Ignoring `Mono.empty()`

A reactive empty publisher differs from an error. Explicitly test expected behavior.

### 40.6. Calling a Blocking Repository Directly on the Event Loop

Do not leave `.block()`/blocking JDBC calls in the reactive authentication path without an appropriate adapter/scheduler.

### 40.7. Rebuilding `DefaultOidcUser` and Dropping UserInfo

If the user has UserInfo, preserve it per policy or document why it is omitted. Test profile preservation.

### 40.8. Treating Same Email as Same OIDC Identity

Identity requires verified issuer + subject. Test multi-provider collisions.

### 40.9. Using ID Token Fixtures as Proof of Signature Validation

Constructor fixtures do not verify signatures; test decoders/OP flows separately.

### 40.10. Manually Subscribing Inside the User Service

Detaching subscriptions from `Mono` makes errors and cancellation hard to manage. Compose with `flatMap`/`map`.

### 40.11. Calling Real Providers on Every Commit

Flaky, risks credential exposure, and depends on MFA/network. Use synthetic fixtures and a dedicated test OP.

### 40.12. Keeping Per-Request Mutable State in a Custom User Service

A singleton Bean with a `currentUser` field can mix principals across concurrent WebFlux requests. Keep state inside the publisher/request context.

### 40.13. Assuming UserInfo `sub` Is Checked Just Because Constructors Succeed

Test OIDC user-service validation/HTTP integration if that is your goal. Do not only mock pre-validated principals.

### 40.14. Letting Malformed Claims Crash the App Uncontrolled

Use parser/schema validation and negative tests. Never cast arbitrary claims based on assumptions.

### 40.15. Not Testing Registration/Provider Routing

A correctly implemented mapping service wired to the wrong registration/chain still breaks in production. Write integration wiring tests.

## 41. Recommended Testing Architecture

```text
                  Spring Security WebFlux OIDC Client
                              |
             +----------------+------------------+
             |                                   |
             v                                   v
      Unit tests                           Integration tests
      No Spring Context                    Spring WebFlux Context
             |                                   |
   OidcUserRequest fixture                  Test ClientRegistration
   Fake OidcUser delegate                   Local OP stub/JWKS
   Fake TenantRoleLookup                    SecurityWebFilterChain
             |                                   |
             v                                   v
   TenantMappingReactiveOidcUserService     Real OIDC Login wiring
             |                                   |
             v                                   v
      Mono<OidcUser>                           User Service
             |                                   |
             v                                   v
        StepVerifier                       Authenticated principal
      - user subject                            |
      - issuer checks                           v
      - profile claims                       WebTestClient
      - authorities                        + mockOidcLogin
      - empty/error                         for route-only tests
      - non-blocking design
             |
             v
     Security regression matrix
       tenant/provider/claim cases

  Additional boundary tests:
    - UserInfo HTTP destination and Bearer token handling
    - JWT/ID Token validation and issuer/audience/nonce
    - Role/membership source trust
    - Multi-tenant account linking
    - Browser cookie/redirect behavior
    - Secure observability and token redaction
```

This separation makes every failure easy to pinpoint: role-parsing bugs in unit tests, missing user-service wiring in context tests, token/JWKS bugs in OP integration tests, and `SameSite`/cookie issues in browser tests.

## 42. Recommended Implementation Sequence

When writing tests for `ReactiveOAuth2UserService` and claim mapping:

1. **Confirm the app uses Spring WebFlux**, not Spring MVC Servlet.
2. **Identify which service runs**: OAuth2 User Service or OIDC User Service.
3. **Add `reactor-test` and `spring-security-test` in test scope** with BOM-aligned versions.
4. **Create completely synthetic fixtures** for `ClientRegistration`, Access Token, ID Token, and UserInfo.
5. **Create a fake delegate** so unit tests make zero network calls.
6. **Extract trusted membership/role lookup** into a dependency with a clear reactive contract.
7. **Use `StepVerifier`** to assert values, claims, principal name, authorities, and completion.
8. **Enforce the `issuer`/`sub` identity boundary**; never use email as a unique principal key.
9. **Test both with and without UserInfo**, preserving profile data when enriching authorities.
10. **Test `Mono.empty()` from delegate and lookup**, failing closed per policy.
11. **Test `Mono.error()` and timeouts**, never falling back to elevated roles.
12. **Validate claim schemas/types and role allowlists**, never turning arbitrary strings into authorities.
13. **Verify original authorities are preserved** when a custom mapper creates a new `DefaultOidcUser`.
14. **Test multi-provider/tenant collisions** with identical `sub` or identical email.
15. **Test concurrency** if the service caches/holds state, and avoid mutable singleton user fields.
16. **Use `PublisherProbe`** when verifying lookup subscription along the right branch.
17. **Test UserInfo HTTP and `sub` mismatch** with a local stub to verify the real delegate.
18. **Test `mockOidcLogin()` separately with `WebTestClient`** for route/method authorization.
19. **Use integration tests with an OP stub** to confirm the custom reactive user service actually runs in the login flow.
20. **Never treat results from one test layer as proof for another**: claims mapping, OIDC protocol validation, Resource Server authorization, and browser security each need dedicated tests.
21. **Never use real credentials or log raw tokens** in tests/CI.
22. **Keep failure reports safe**, favoring issuer/registration aliases, error codes, and internal correlation IDs.
23. **Keep tests independent and deterministic**, without depending on execution order, current time, or a production OP.

## 43. References

- [Spring Security Reference — OAuth2 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Security Reference — OAuth2 Client (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html)
- [Spring Security Reference — WebFlux Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Security Reference — Testing WebFlux OAuth2](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security API — ReactiveOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/ReactiveOAuth2UserService.html)
- [Spring Security API — DefaultReactiveOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/DefaultReactiveOAuth2UserService.html)
- [Spring Security API — OidcReactiveOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcReactiveOAuth2UserService.html)
- [Spring Security API — OidcUserRequest](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcUserRequest.html)
- [Spring Security API — OidcUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html)
- [Spring Security API — DefaultOidcUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/DefaultOidcUser.html)
- [Spring Security API — OidcUserAuthority](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUserAuthority.html)
- [Spring Security API — OAuth2UserRequest](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/OAuth2UserRequest.html)
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html)
- [Spring Boot Reference — Testing WebFlux](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [OpenID Connect Core 1.0 — ID Token and UserInfo](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

**Conclusion:** testing **`ReactiveOAuth2UserService`** in Spring Security WebFlux must directly verify **`Mono<OidcUser>` or `Mono<OAuth2User>`** using **`StepVerifier`**, with controlled mocks for the delegate/UserInfo, ID Token, and trusted membership lookup. Tests must assert **issuer + subject, principal name, preserved claims/UserInfo, exact authority strings, empty/error behavior, tenant isolation, and zero privilege elevation on dependency failure**. Use **`mockOidcLogin()` with `WebTestClient`** to test endpoints once a principal exists, without mistaking it for user-loading or claim-mapping tests; **UserInfo HTTP, OIDC signature/issuer/nonce validation, and login wiring** belong to integration tests at their own boundaries. Separating these layers keeps the suite fast, independent of real OPs, and capable of catching privilege or identity-mixing bugs often hidden by simple HTTP 200 checks.
