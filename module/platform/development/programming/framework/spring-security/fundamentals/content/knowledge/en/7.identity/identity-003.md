# Meaning of getPrincipal, getCredentials, getAuthorities, and isAuthenticated

> **Context:** Spring Security for Servlet/Spring MVC, Java 17+, Spring Boot 3.x, and Spring Security 6.x. This lesson focuses on four methods of the `Authentication` interface: their values and data types, differences before and after authentication, anonymous authentication, their relationship to authorization, and proper usage in code and tests. The main example uses HTTP Basic to make the authentication flow clear; JWT/OAuth2 mechanisms are compared where relevant.

## 1. Authentication Is Both an Authentication Request and an Authentication Result

An `Authentication` object can represent either an **unverified authentication request** or a **result verified by a trusted provider**. That is why you cannot simply see an `Authentication` and conclude the caller is logged in.

With HTTP Basic, a typical flow:

~~~text
HTTP request:
    Authorization: Basic <Base64(username:password)>
                      |
                      v
          BasicAuthenticationFilter
                      |
                      v
    UsernamePasswordAuthenticationToken (request)
    principal       = "alice"
    credentials     = password sent by client
    authorities     = []
    isAuthenticated = false
                      |
                      v
            AuthenticationManager
                      |
                      v
            DaoAuthenticationProvider
            + UserDetailsService
            + PasswordEncoder
            + account status checks
                      |
                      v
      UsernamePasswordAuthenticationToken (result)
    principal       = UserDetails of alice
    credentials     = typically erased after authentication
    authorities     = [ROLE_USER, report:read]
    isAuthenticated = true
                      |
                      v
             SecurityContextHolder
                      |
                      v
          AuthorizationFilter / method security
                      |
                 ALLOW / DENY
~~~

`AuthenticationManager` typically delegates authentication to an appropriate provider; the provider loads account data and verifies credentials. Upon success, the request's **SecurityContext** is updated so filters, controllers, and services can read the current subject's information.

Concepts to distinguish:

- **Authentication:** who is requesting authentication, or an authentication result already established by the framework.
- **Principal:** which object represents the identity.
- **Credentials:** evidence used to verify identity, potentially sensitive.
- **Authorities:** high-level permissions attached to the Authentication.
- **Authorization:** whether an action on a specific resource is permitted.

**Being authenticated does not automatically mean being allowed to access every endpoint.** An account with `ROLE_USER` does not automatically pass a `hasRole("ADMIN")` rule.

## 2. Overview Table of the Four Methods

| Method | Core question | Typical values | Do not assume |
| --- | --- | --- | --- |
| `getPrincipal()` | Who is identified? | String, UserDetails, Jwt, OAuth2User, project-specific principal | Always a username String or UserDetails |
| `getCredentials()` | What is the authentication evidence? | Password, access token, credential object; can be null | Always holds password even after login |
| `getAuthorities()` | Which permissions are granted to this authentication? | Collection of GrantedAuthority: ROLE_USER, report:read, SCOPE_orders.read | Grants access to every resource of the same type |
| `isAuthenticated()` | Has the implementation marked the authentication as authenticated? | true/false | true equals a real user, full permissions, and completed MFA |

`Authentication` belongs to `org.springframework.security.core` and extends `java.security.Principal`. Key signatures excerpted:

~~~java
// Illustrative signatures only; not a complete compilable interface.
Object getPrincipal();
Object getCredentials();
Collection<? extends GrantedAuthority> getAuthorities();

boolean isAuthenticated();
void setAuthenticated(boolean authenticated);

String getName();      // from java.security.Principal
Object getDetails();
~~~

Two takeaways from the contract:

1. `getPrincipal()` and `getCredentials()` return `Object`, so actual types vary by `Authentication` implementation. Do not use a fixed cast if the API may support multiple authentication types.
2. `getAuthorities()` returns a collection (should not be null). For an **unauthenticated** username/password token, the collection is typically empty. A trusted `Authentication` has authorities populated by the appropriate provider or converter.

`getDetails()` can hold supplementary info such as remote address or session ID. It is not a permissions list, does not replace the principal, and should not be returned raw in HTTP responses.

## 3. getPrincipal(): The Object Representing Identity

### 3.1. Before Authentication

When a client sends username/password, a filter typically builds a token like:

~~~java
UsernamePasswordAuthenticationToken attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice",
        "alice123"
    );

Object principal = attempt.getPrincipal(); // String "alice"
~~~

This is a **snippet** inside a program with Spring Security dependencies/imports. It shows the username claimed by the client, **not yet proving the client is alice**.

### 3.2. After Authentication

With `DaoAuthenticationProvider`, `UserDetailsService` looks up the account and the provider verifies the credentials. The returned `Authentication` typically has a `UserDetails` principal, such as the `org.springframework.security.core.userdetails.User` implementation. At that point `getPrincipal()` is no longer just a String.

~~~text
Before authentication:
    type = UsernamePasswordAuthenticationToken
    principal = String "alice"
    isAuthenticated() = false

After authentication:
    type = UsernamePasswordAuthenticationToken
    principal = UserDetails(alice)
    isAuthenticated() = true
~~~

There is no rule requiring every provider to return `UserDetails`; a provider may use a `String` or a custom principal.

### 3.3. Principal Varies by Authentication Mechanism

| Architecture | Common Authentication | Common Principal |
| --- | --- | --- |
| HTTP Basic/form login + DaoAuthenticationProvider | UsernamePasswordAuthenticationToken | UserDetails or String |
| Anonymous authentication | AnonymousAuthenticationToken | String `"anonymousUser"` by default |
| OAuth2 Resource Server JWT | JwtAuthenticationToken | Validated/decoded Jwt |
| OAuth2 Login / OIDC | OAuth2AuthenticationToken | OAuth2User or OidcUser |
| Opaque access token | Appropriate Resource Server Authentication | OAuth2AuthenticatedPrincipal |
| Custom authentication | System-specific class | Custom principal verified by provider |

The following can break when switching from username/password to JWT:

~~~java
// Use only if certain the principal is UserDetails:
UserDetails user = (UserDetails) authentication.getPrincipal();
~~~

For code that only needs an identifier:

~~~java
String name = authentication.getName();
~~~

`getName()` is convenient, yet in real systems **the login name is not necessarily a durable ID**. Usernames/emails can change; JWT subjects can depend on the issuer; multiple tenants may share colliding usernames. When checking resource ownership, map the verified principal to a **trusted accountId/tenantId** per the application's policy.

### 3.4. @AuthenticationPrincipal

In Spring MVC, you can receive the principal directly:

~~~java
@GetMapping("/profile")
public String profile(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
~~~

This excerpt works if the authentication mechanism guarantees the principal is `UserDetails`. With a JWT Resource Server, the parameter type can be `Jwt`:

~~~java
@GetMapping("/jwt-subject")
public String jwtSubject(@AuthenticationPrincipal Jwt jwt) {
    return jwt.getSubject();
}
~~~

These are two **snippets from two different architectures**; do not drop the JWT controller into an HTTP Basic demo and expect Spring to supply a `Jwt`.

**Do not return a raw `UserDetails` or `Jwt` as JSON** because it can expose password hashes, sensitive claims, or internal metadata. Create a DTO containing only the fields the API actually needs.

## 4. getCredentials(): Authentication Evidence

`getCredentials()` indicates the data proving who the principal is. With Basic/form login, that is typically the raw password before authentication. With Bearer or other mechanisms, credentials may hold a token or a specialized object.

### 4.1. Credentials Before Authentication

~~~java
UsernamePasswordAuthenticationToken attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "demo-password"
    );

Object principal = attempt.getPrincipal();        // "alice"
Object credentials = attempt.getCredentials();    // "demo-password"
boolean authenticated = attempt.isAuthenticated();// false
~~~

The snippet uses mock credentials for learning only. **Never log or print real passwords or access tokens into logs, responses, test reports, or analytics systems.**

Raw passwords from clients must travel over **HTTPS/TLS** across untrusted networks. HTTP Basic encodes username/password in Base64; **Base64 does not protect secrets**.

### 4.2. PasswordEncoder Differs from getCredentials

`UserDetails.getPassword()` usually returns the **encoded password/hash stored in the database**. The provider matches the raw password against the hash:

~~~java
boolean valid = passwordEncoder.matches(
    rawPasswordFromRequest,
    userDetails.getPassword()
);
~~~

This is a snippet explaining the provider mechanism, not code to write inside a controller. `Authentication.getCredentials()` refers to the request's credential, **not the hash stored in the DB**. Do not use `raw.equals(storedHash)` and do not re-encode the hash on every account read.

### 4.3. After Authentication, Credentials Are Often Erased

A typical `ProviderManager` enables `eraseCredentialsAfterAuthentication`. When authentication succeeds, it tries to clear secrets on the `Authentication` and related objects implementing `CredentialsContainer` to shorten password lifetime in memory.

Therefore when a Controller reads:

~~~java
Object credentials = authentication.getCredentials();
~~~

the result **may be null** or erased/transformed depending on the implementation. **Null does not prove login failed.** Conversely, you must not assume every `Authentication` type after login always has null credentials.

Do not build logic such as "if credentials are null then not logged in". Use Spring Security's authentication and authorization mechanisms. Credential erasure only affects in-memory objects and does not delete the persisted password hash in the database.

### 4.4. UserDetails Caching Scenario

Some `UserDetails` implementations implement `CredentialsContainer`. If the exact same object instance is held in a cache and used as the `Authentication` principal, erasing the password on the principal can affect the object sitting in the cache.

When using `UserCache` or a custom cache, understand object lifecycle/references; you may need to copy the object appropriately before handing it to the provider. Do not disable credential erasure just to work around a cache bug without evaluating information security.

### 4.5. Why Not Return Authentication Directly?

Anti-example:

~~~java
// Do not use in production:
log.info("credentials={}", authentication.getCredentials());
return authentication; // Serializes the entire object
~~~

This can leak passwords/tokens or unnecessary metadata. Even when credentials have been erased, principal/authorities/details can carry info not meant for clients. Choose a DTO with approved public fields.

## 5. getAuthorities(): Permissions Attached to Authentication

`getAuthorities()` returns `Collection<? extends GrantedAuthority>`. Common values:

~~~text
ROLE_USER
ROLE_ADMIN
report:read
invoice:approve
SCOPE_orders.read
~~~

For simple authorities, `GrantedAuthority.getAuthority()` returns a string representing the permission. Example:

~~~java
List<String> authorities = authentication.getAuthorities().stream()
    .map(GrantedAuthority::getAuthority)
    .sorted()
    .toList();
~~~

This snippet needs an `Authentication` variable and imports for `List` and `GrantedAuthority`. A complex authority may return null from `getAuthority()`, so code handling arbitrary implementations should account for that. The demo only uses `SimpleGrantedAuthority` with non-null strings.

### 5.1. Role vs. Authority

| Spring Security policy | Requirement under default conventions |
| --- | --- |
| `hasRole("ADMIN")` | Authority `ROLE_ADMIN` |
| `hasAuthority("ROLE_ADMIN")` | Exact authority `ROLE_ADMIN` |
| `hasAuthority("report:read")` | Exact authority `report:read` |
| `hasAuthority("SCOPE_orders.read")` | Exact authority `SCOPE_orders.read` |

The `User.withUsername(...).roles("USER")` builder automatically prepends `ROLE_`. The `.authorities("report:read")` builder uses the exact string passed. With JWTs, scopes are typically mapped to authorities prefixed with `SCOPE_` by the converter.

**A role is one form of authority representation**, not a username. An account named "admin" does not automatically possess `ROLE_ADMIN`.

### 5.2. Authorities of an Unauthenticated Request Token

~~~java
UsernamePasswordAuthenticationToken attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "not-verified-yet"
    );

// attempt.getAuthorities().isEmpty() == true
// attempt.isAuthenticated() == false
~~~

Permissions must come from a verified source, such as a trusted `UserDetailsService` or a token processed by a validator. Do not take roles self-asserted in a request body and attach them to an `Authentication` treated as authenticated.

The following anti-example **must not be used to log in**:

~~~java
Authentication forged =
    UsernamePasswordAuthenticationToken.authenticated(
        usernameFromClient,
        passwordFromClient,
        List.of(new SimpleGrantedAuthority(roleFromClient))
    );
~~~

The `authenticated(...)` factory creates an object already marked as trusted. Only authorized code/providers after verifying credentials and permissions may produce such a result; **never build it from unverified client-sent claims/roles**.

### 5.3. Authorities Do Not Replace Resource-Level Policy

Having `report:read` does not prove a user may read a report belonging to another tenant. A domain rule usually must check:

~~~text
ALLOW if and only if:
    identity has been verified for the request
    AND granted authority for the action
    AND resource belongs to an allowed owner/tenant scope
    AND business state / required conditions are satisfied
~~~

Checking general URL access and checking a specific record are two different tasks. BOLA/IDOR vulnerabilities can arise if an API only checks roles and trusts the resource ID in the URL.

### 5.4. Permissions Can Become Stale in Sessions/JWTs

`getAuthorities()` does not automatically query the database every time. With sessions, `Authentication` can hold permissions from login time; with JWTs, permissions can be embedded in the token and remain until expiration/revocation; providers/caches can also retain old data.

If locking a user or changing a role must take effect immediately, design corresponding session invalidation, token revocation, revalidation, and domain policies.

## 6. isAuthenticated(): A Status Flag Easy to Misinterpret

For username/password:

~~~text
UsernamePasswordAuthenticationToken.unauthenticated(...)
    -> isAuthenticated() == false

Authentication successfully verified by a provider
    -> isAuthenticated() == true
~~~

However, **the raw flag true does not automatically equate to logging in with a real account, does not imply MFA, and does not grant permission to access an endpoint**.

### 6.1. AnonymousAuthenticationToken Can Also Have Flag True

`AnonymousAuthenticationFilter` in Spring Security typically places an `AnonymousAuthenticationToken` into `SecurityContext` when a request has no real user authentication yet. This gives the framework a consistent object representing an anonymous caller.

With the default `AnonymousAuthenticationToken`, `isAuthenticated()` can **return true**, yet Spring Security still recognizes it as anonymous via `AuthenticationTrustResolver`.

Verification code example:

~~~java
Authentication anonymous = new AnonymousAuthenticationToken(
    "test-key",
    "anonymousUser",
    AuthorityUtils.createAuthorityList("ROLE_ANONYMOUS")
);

boolean rawFlag = anonymous.isAuthenticated(); // true
boolean anonymousState =
    new AuthenticationTrustResolverImpl().isAnonymous(anonymous); // true
~~~

This is a snippet in a project with Spring Security. Do not manually construct anonymous tokens in production to replace the framework; use it only to see clearly how the raw flag and access state differ.

### 6.2. authenticated() Does Not Equal the Raw Flag

In `HttpSecurity`:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/private").authenticated()
    .anyRequest().denyAll()
)
~~~

Spring Security applies the `.authenticated()` policy in a way that distinguishes anonymous users. Therefore a request carrying only an `AnonymousAuthenticationToken` is still **denied** at `/private`, even though the token's flag may be true.

Common mistake in custom code:

~~~java
if (authentication != null && authentication.isAuthenticated()) {
    // Self-granting access to read sensitive data
}
~~~

The condition above is insufficient: an anonymous token can satisfy it, and a logged-in user can still lack resource permissions. Use `.authenticated()`, `.hasRole()`, `.hasAuthority()`, `.fullyAuthenticated()`, and proper owner/tenant checks instead of reducing security to a boolean.

### 6.3. Remember-Me and fullyAuthenticated()

Some remember-me mechanisms can produce an `Authentication` with flag true without a full interactive login. In authorization you may need to distinguish:

- **anonymous()**: no real user authentication yet.
- **rememberMe()**: recognized via a remember-me mechanism.
- **authenticated()**: authenticated per framework criteria, not anonymous.
- **fullyAuthenticated()**: normally excludes anonymous and remember-me.

**fullyAuthenticated() does not automatically prove MFA has been completed.** If the business requires step-up authentication, MFA, or specific trust levels, corresponding policies must be enforced.

### 6.4. Successful Login Does Not Mean Administrative Permission

~~~text
authentication.isAuthenticated() -> true
authentication.getName()        -> "alice"
authentication.getAuthorities() -> [ROLE_USER]

GET /api/profile -> may ALLOW
GET /api/admin   -> DENY when rule requires ROLE_ADMIN
~~~

If policy requires permission to view a tenant's invoices, ownership and tenant must still be checked at data access time. Authentication is only an input to authorization.

### 6.5. Do Not Call setAuthenticated(true) Yourself

An unauthenticated request token can reject `setAuthenticated(true)`. On `UsernamePasswordAuthenticationToken.unauthenticated(...)`, forcing this flag throws `IllegalArgumentException`.

Do not substitute it by calling the `authenticated(...)` factory with client-supplied roles. The right way is for the filter to send the request token to `AuthenticationManager.authenticate(...)`, where the provider verifies credentials and grants checked authorities.

## 7. SecurityContextHolder and Reading Authentication

Inside a Servlet request:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();
~~~

This is a snippet. By default the context is held per request-handling thread; Spring Security clears the context upon completion. Never store `Authentication` in a shared static variable because it can leak user information across other requests.

`authentication` **can be null**, for example in background jobs, tests that do not initialize context, requests outside `SecurityFilterChain`, or before the anonymous filter runs.

### 7.1. Spring MVC and Anonymous

For an endpoint restricted to logged-in users:

~~~java
@GetMapping("/profile")
public String profile(Authentication authentication) {
    return authentication.getName();
}
~~~

However, Spring MVC's argument resolver for `Principal`/`Authentication` may read from `HttpServletRequest.getPrincipal()`, and that value is often **null for anonymous requests**, even though `SecurityContext` already holds an `AnonymousAuthenticationToken`.

When you want to observe **even anonymous Authentication**, use:

~~~java
@GetMapping("/public")
public String publicView(@CurrentSecurityContext SecurityContext context) {
    Authentication authentication = context.getAuthentication();
    return authentication == null
        ? "none"
        : authentication.getName();
}
~~~

The snippets above require the appropriate class/controller/imports. `@CurrentSecurityContext` reads Spring Security's context. Do not conclude the context is definitely empty just because an `Authentication` parameter in an anonymous MVC handler receives null.

### 7.2. @AuthenticationPrincipal and Asynchronous Work

`@AuthenticationPrincipal` injects the current principal into a method parameter, not the whole `Authentication`. The principal type depends on the provider. When using `@Async`, an `Executor`, or new threads, `SecurityContextHolder` does not propagate across every thread by default: use a supported propagation mechanism (such as `DelegatingSecurityContextExecutor`) if business logic needs it.

Reactive WebFlux applications use Reactor Context and `SecurityWebFilterChain`, differing from the Servlet and MockMvc APIs used in this lesson.

## 8. Complete Spring Boot 3 Example: Inspecting Identity Without Exposing Credentials

We build a small API:

- **GET /api/public**: public and allows observing anonymous authentication.
- **GET /api/me**: only for authenticated accounts; returns name, principalType, authenticatedFlag, anonymous, and authorities.
- **GET /api/admin**: requires ROLE_ADMIN.
- **GET /api/unlisted**: has a controller mapping but is blocked by the fallback deny.
- No endpoint returns credentials or serializes the raw Authentication.

### 8.1. Dependencies and Project Structure

Uses Spring Boot 3.x, Java 17+, and a Gradle project with appropriate plugins/dependency management. Add to the existing `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Files:

~~~text
src/main/java/com/example/authidentity/
  AuthIdentityApplication.java
  SecurityConfig.java
  IdentityController.java

src/test/java/com/example/authidentity/
  AuthenticationIdentityTest.java
~~~

### 8.2. AuthIdentityApplication.java

~~~java
package com.example.authidentity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthIdentityApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthIdentityApplication.class, args);
    }
}
~~~

### 8.3. SecurityConfig.java

~~~java
package com.example.authidentity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .authorities("ROLE_USER", "report:read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
~~~

**Reading the configuration:**

1. `httpBasic` configures the filter to accept Basic headers and the provider to authenticate username/password.
2. `UserDetailsService` loads hashes, authorities, and account status; `PasswordEncoder` uses BCrypt.
3. `SessionCreationPolicy.STATELESS` prevents Spring Security from relying on `HttpSession` to retrieve `SecurityContext` on subsequent requests. This is a demo choice, not a requirement of the `Authentication` interface.
4. `/api/public` `permitAll` still goes through the chain and the anonymous filter can create an anonymous token.
5. `/api/me` `authenticated()` uses the policy that distinguishes anonymous users.
6. `/api/admin` requires `ROLE_ADMIN`, not the username "admin".
7. `anyRequest().denyAll()` blocks unlisted paths/methods.
8. The demo only has GET endpoints; no need to disable CSRF. If adding POST/PUT/DELETE, design CSRF according to the client/credential transport.

Demo passwords are for localhost only. HTTP Basic uses Base64, requires HTTPS when sent over a network, and must not use hard-coded credentials in production.

### 8.4. IdentityController.java

~~~java
package com.example.authidentity;

import java.util.List;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    @GetMapping("/api/public")
    public AuthenticationView publicInfo(
            @CurrentSecurityContext SecurityContext context) {
        return describe(context.getAuthentication());
    }

    @GetMapping("/api/me")
    public AuthenticationView me(
            @CurrentSecurityContext SecurityContext context) {
        return describe(context.getAuthentication());
    }

    @GetMapping("/api/admin")
    public String admin() {
        return "admin-only";
    }

    @GetMapping("/api/unlisted")
    public String unlisted() {
        return "must-not-be-exposed";
    }

    private AuthenticationView describe(Authentication authentication) {
        if (authentication == null) {
            return new AuthenticationView(
                "none", "none", false, true, List.of()
            );
        }

        String principalType = authentication.getPrincipal() == null
            ? "null"
            : authentication.getPrincipal().getClass().getSimpleName();

        List<String> authorities = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return new AuthenticationView(
            authentication.getName(),
            principalType,
            authentication.isAuthenticated(),
            trustResolver.isAnonymous(authentication),
            authorities
        );
    }

    public record AuthenticationView(
        String name,
        String principalType,
        boolean authenticatedFlag,
        boolean anonymous,
        List<String> authorities
    ) {}
}
~~~

Because this is a learning demo, the DTO returns **principalType** to inspect the object type, whereas production APIs normally do not need to expose class names. **Do not include `getCredentials()` in the DTO**, and never serialize `UserDetails`, `Authentication`, or `SecurityContext`.

### 8.5. Running and Observing

From the directory containing the Gradle Wrapper:

~~~bash
./gradlew bootRun
# Windows:
gradlew.bat bootRun
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/me
curl -i -u alice:alice123 http://localhost:8080/api/me
curl -i -u alice:alice123 http://localhost:8080/api/admin
curl -i -u admin:admin123 http://localhost:8080/api/admin
curl -i -u admin:admin123 http://localhost:8080/api/unlisted
curl -i -u alice:wrong http://localhost:8080/api/me
~~~

**Expected** for this exact demo:

| Request | HTTP | Meaning |
| --- | --- | --- |
| GET /api/public anonymous | **200** | DTO typically has name=anonymousUser, authenticatedFlag=true, and anonymous=true |
| GET /api/me anonymous | **401** | Spring Security does not treat anonymous as authenticated for this rule |
| GET /api/me alice right password | **200** | name=alice, principalType=User, authorities ROLE_USER and report:read |
| GET /api/admin alice | **403** | Login succeeded but lacks ROLE_ADMIN |
| GET /api/admin admin | **200** | Body `admin-only` |
| GET /api/unlisted admin | **403** | Fallback denyAll still blocks |
| GET /api/me alice wrong password | **401** | Wrong credentials |

Example JSON of `/api/me` for Alice (key order depends on serializer):

~~~json
{
  "name": "alice",
  "principalType": "User",
  "authenticatedFlag": true,
  "anonymous": false,
  "authorities": ["ROLE_USER", "report:read"]
}
~~~

There are no credentials, raw passwords, or tokens in the response.

## 9. MockMvc Testing: Distinguishing the States

Create `src/test/java/com/example/authidentity/AuthenticationIdentityTest.java`:

~~~java
package com.example.authidentity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthenticationIdentityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void requestTokenIsNotTrustedYet() {
        UsernamePasswordAuthenticationToken token =
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", "demo-secret"
            );

        assertEquals("alice", token.getPrincipal());
        assertEquals("demo-secret", token.getCredentials());
        assertTrue(token.getAuthorities().isEmpty());
        assertFalse(token.isAuthenticated());

        assertThrows(IllegalArgumentException.class,
            () -> token.setAuthenticated(true));
    }

    @Test
    void anonymousFlagCanBeTrueWithoutActualLogin() {
        Authentication anonymous = new AnonymousAuthenticationToken(
            "test-key",
            "anonymousUser",
            AuthorityUtils.createAuthorityList("ROLE_ANONYMOUS")
        );

        assertTrue(anonymous.isAuthenticated());
        assertTrue(
            new AuthenticationTrustResolverImpl().isAnonymous(anonymous)
        );
    }

    @Test
    void anonymousCanVisitPublicButNotProtected() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.anonymous").value(true));

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validPasswordProducesPrincipalAndAuthorities() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.authenticatedFlag").value(true))
            .andExpect(jsonPath("$.anonymous").value(false))
            .andExpect(jsonPath("$.authorities[0]").value("ROLE_USER"))
            .andExpect(jsonPath("$.authorities[1]").value("report:read"));
    }

    @Test
    void wrongPasswordIsUnauthorized() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void loggedInUserCanStillLackRole() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "alice123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-only"));
    }

    @Test
    void evenAdminCannotOverrideDenyAll() throws Exception {
        mvc.perform(get("/api/unlisted")
                .with(httpBasic("admin", "admin123")))
            .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
./gradlew test
# Windows:
gradlew.bat test
~~~

The tests verify:
- An unauthenticated token has principal/credentials, yet empty authorities and a false flag.
- An anonymous token can have a true flag, while `AuthenticationTrustResolver` recognizes it as anonymous.
- A public endpoint requires no login; a protected endpoint rejects anonymous callers.
- The provider verifies passwords and creates a trusted principal and authorities.
- An authenticated user can still lack a role and receive 403.
- The `denyAll` rule still holds even against admin.

**MockMvc with Spring Security Test sends HTTP Basic through the filter**, rather than fabricating an authenticated principal to skip password checking. This is the code and expected result of a Spring Boot 3.x project; to confirm tests actually pass, you must run `gradlew test` on a project with the proper dependencies.

## 10. With OAuth2 Resource Server, Values Can Differ

A Resource Server receives:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

After the token is verified by the decoder/provider for valid key, issuer, audience, expiration, and appropriate validators:

- `getPrincipal()` is typically `Jwt` inside `JwtAuthenticationToken`, not `UserDetails`.
- `getName()` typically uses the `sub` claim per the default converter or a custom name attribute.
- `getCredentials()` depends on the `Authentication` implementation; do not log/serialize tokens.
- `getAuthorities()` can be `SCOPE_...` strings derived from scopes/claims.
- `isAuthenticated()` is typically true on a valid result, yet the request still needs sufficient scopes and resource permissions.

Snippet in a JWT Resource Server Controller:

~~~java
@GetMapping("/jwt-subject")
public String subject(@AuthenticationPrincipal Jwt jwt) {
    return jwt.getSubject();
}
~~~

This snippet **does not belong to the HTTP Basic demo** and only runs when a JWT Resource Server is properly configured. Being able to Base64URL-decode a JWT payload **does not prove the token's signature and claims have been verified**.

If the scope is `reports.read` and the converter maps it to `SCOPE_reports.read`, the policy `hasAuthority("SCOPE_reports.read")` is what matches. Do not treat `SCOPE_reports.read`, `report:read`, and `ROLE_USER` as the same permission.

## 11. Common Mistakes

### 11.1. Using isAuthenticated() as the Entire Authorization

Anonymous tokens can have a true flag, and real users can still lack permissions on a resource. Use Spring Security policies combining role, scope, ownership, and tenant checks.

### 11.2. Assuming the Principal Is Always UserDetails

The principal depends on the provider. Only cast when controlling the type; use `getName()` or a CurrentUser abstraction when only a verified identifier is needed.

### 11.3. Logging getCredentials for Debugging

Risks exposing raw passwords or tokens. Log only safe metadata such as request ID, verified account ID, and decision; never log the Authorization header.

### 11.4. Allowing the Client to Send Roles and Self-Creating an Authenticated Token

Providers/managers must verify credentials and the authority source. Never implement login by calling `authenticated(...)` with client-supplied roles.

### 11.5. Treating getAuthorities as Permission to Read Every Resource

A coarse-grained authority does not replace owner, tenant, or object-state checks. Guard against IDOR/BOLA bugs.

### 11.6. Treating Null Credentials After Login as Failure

`ProviderManager` typically erases credentials after authentication. That is a protective mechanism, not a signal that the user is not logged in.

### 11.7. Storing Authentication in a Static Field

Authentication is scoped to the security context/request, not a global variable. When doing async work, use proper context propagation.

### 11.8. Confusing Anonymous with a Null SecurityContext

The MVC resolver may return null for anonymous, even though Spring Security's context holds an `AnonymousAuthenticationToken`. Read from the right place with `@CurrentSecurityContext` when needed.

### 11.9. Thinking Flag True Equals Fully Authenticated or MFA Completed

Remember-me, anonymous, and other trust levels require appropriate policies. MFA must be explicitly modeled and checked separately.

### 11.10. Assuming Granted Authorities Are Always Fresh

Sessions, JWTs, and `UserDetails` caches can hold data from before a role changed. Revocation/revalidation policies are needed.

### 11.11. Returning Raw Authentication as JSON

Can expose internal principals, hashes, tokens, and request details. Public DTOs should contain only fields serving the client.

## 12. Debugging a Request with the Four Methods

| Observation | What to check |
| --- | --- |
| Principal is a String instead of UserDetails | Is it an unauthenticated request token that has not gone through a provider? |
| Credentials null after login | Were credentials erased by design? |
| Authorities empty | Was there a result from a provider? Did `UserDetailsService`/converter load permissions? |
| isAuthenticated false | Is it an unverified authentication request? |
| isAuthenticated true yet still 401 | Is it an anonymous token and the entry point requires login? |
| isAuthenticated true yet 403 | Missing role/scope, resource permission, or CSRF token? |
| Principal is Jwt | Is the Resource Server using JWT, making casting to UserDetails invalid? |
| Role changed yet old permission persists | Was the Authentication in session/token/cache refreshed? |
| Public controller receives null Authentication | Is it using the servlet principal resolver instead of `SecurityContext`? |

Enable logging in development when needed:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

**Never log passwords, tokens, cookies, Authorization headers, or raw credentials.** HTTP 401 usually relates to authentication, 403 usually to authorization/CSRF, and 302 may come from form login; exact status depends on entry point, handler, and filter chain.

## 13. Self-Check Exercises

**Question 1.** Right after creating `UsernamePasswordAuthenticationToken.unauthenticated("alice", "abc")`, what are `getPrincipal()` and `isAuthenticated()`?

**Answer:** Principal is the String `"alice"`; the flag is **false**, because the credentials have not yet been verified by a provider.

**Question 2.** Does `getCredentials()` returning null after login prove the login failed?

**Answer:** No. `ProviderManager` typically erases credentials after successful authentication.

**Question 3.** An `AnonymousAuthenticationToken` has flag true. Can it pass the `.authenticated()` rule?

**Answer:** No. Spring Security distinguishes anonymous callers via its trust resolver and does not treat them as real logged-in users.

**Question 4.** A user has `ROLE_USER` and `isAuthenticated=true`, but the endpoint requires `ROLE_ADMIN`?

**Answer:** Typically receives 403 after successful authentication, because the required authority is missing.

**Question 5.** Is `getPrincipal()` always `UserDetails`?

**Answer:** False. It can be a String, `UserDetails`, `Jwt`, `OAuth2User`, or a custom principal depending on the provider.

**Question 6.** Why should you not return raw `Authentication` to the browser?

**Answer:** It can hold credentials or internal metadata/claims; return a field-restricted DTO instead.

**Question 7.** Does the `report:read` authority allow reading another tenant's reports?

**Answer:** Not automatically. Owner/tenant/resource policies must still be checked.

**Question 8.** When a role changes in the database, does `getAuthorities()` in a session/JWT update immediately?

**Answer:** Not by default. Token/session/cache invalidation or revalidation is required.

**Question 9.** Why does `SCOPE_reports.read` not equal `report:read`?

**Answer:** They are two different authority strings; policies must match the converter and convention.

**Question 10.** Can you manually set `authenticated=true` from client-sent roles to bypass `AuthenticationManager`?

**Answer:** No. That is an authentication bypass; a trusted provider must verify credentials and permissions.

**Question 11.** Why is `@CurrentSecurityContext` useful when observing anonymous callers?

**Answer:** It reads Spring Security's `SecurityContext`, whereas MVC's servlet principal resolver can return null for anonymous callers.

**Question 12.** Does `isAuthenticated() == true` automatically prove MFA has been completed?

**Answer:** No. Appropriate authentication-level and authorization policies are required.

## Official Documentation

- Spring Security — **Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — **Anonymous Authentication**: https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security — **Authorization Architecture**: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — **Authorize HTTP Requests**: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — **HTTP Basic**: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security API — **Authentication**: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/core/Authentication.html
- Spring Security API — **UsernamePasswordAuthenticationToken**: https://docs.spring.io/spring-security/site/docs/6.5.0/api/org/springframework/security/authentication/UsernamePasswordAuthenticationToken.html
- Spring Security — **OAuth2 Resource Server JWT**: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html

**Remember:** `getPrincipal()` represents identity; `getCredentials()` holds evidence and is typically erased after authentication; `getAuthorities()` holds granted permissions; `isAuthenticated()` only reflects the `Authentication` object's state. **Access decisions must be made by policies tailored to the authentication type and resource, not by checking a single boolean.**
