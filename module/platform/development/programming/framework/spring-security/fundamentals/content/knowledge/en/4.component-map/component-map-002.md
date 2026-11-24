# Principal, Credentials, and GrantedAuthority in Authentication

In Spring Security, **`Authentication`** represents either the data used in an authentication request or the result of the authentication process. Inside this object are three key groups of data: **`principal`** (the identified subject), **`credentials`** (the proof verifying identity), and **`authorities`** (the permissions or permission labels granted to the subject). Understanding their relationship helps you read configuration, debug 401/403 errors, and avoid mistakes such as treating a username as an access permission or logging passwords.

Core mental model:

- **Principal:** "Who is requesting access?"
- **Credentials:** "What evidence verifies that the requester is really who they claim to be?"
- **GrantedAuthority:** "Which roles, scopes, or permissions has the system granted to that subject?"
- **Authorization:** "Given those authorities and the current context, is the subject allowed to perform this action on a specific resource?"

This lesson uses the **Spring Security Servlet / Spring MVC** architecture, with examples targeting Spring Boot 3, Spring Security 6, and Java 17+. Mechanisms like HTTP Basic, form login, JWT, and OIDC may produce different `Authentication` types, yet still apply the same principles above.

## 1. Where Does Authentication Sit in the Spring Security Architecture?

A Servlet application typically passes requests through `SecurityFilterChain`. A security filter extracts authentication data from the HTTP request, delegates to `AuthenticationManager`/`AuthenticationProvider` when needed, receives a verified `Authentication`, and stores it in `SecurityContext` via the appropriate mechanism. Authorization rules then use that information to decide access.

```text
HTTP request
    |
    | Authorization header / login form / session / ...
    v
SecurityFilterChain
    |
    +-- Build an authentication request Authentication:
    |      principal   = claimed identity
    |      credentials = proof presented by client
    |      authorities = not yet treated as granted permissions
    |
    v
AuthenticationManager
    |
    v
AuthenticationProvider
    |-- Verify evidence, account status, trusted source
    |-- Load/map GrantedAuthority
    |
    +-- Failure -> authentication failure response
    |
    +-- Success -> trusted Authentication
                           |
                           v
                      SecurityContext
                           |
                           v
                    Authorization rules
                           |
                           v
                     Controller/Service
```

This is a logical model: filter order and context storage vary by mechanism. With session login, the context may be restored from the session; with a bearer token, the token may be re-validated on every request. A publicly permitted request may not require a logged-in user at all.

### 1.1. One Interface, Two Different Moments

Spring Security can use `Authentication` as:

1. **Input to `AuthenticationManager`:** carrying an unverified identity and credentials, usually with `isAuthenticated() == false`.
2. **Authentication result:** carrying a principal and authorities constructed from a trusted source, used inside `SecurityContext`.

This is a difference in **trust level**, not just a difference in data type. The fact that a client sends a username, password, or list of roles does not mean those values have been verified.

### 1.2. APIs to Remember

| API | Purpose | Note |
| --- | --- | --- |
| `getPrincipal()` | Returns the object describing the identity | Type depends on mechanism: `String`, `UserDetails`, `Jwt`, `OAuth2User`... |
| `getCredentials()` | Returns evidence related to authentication | May be a password/token; may have been erased after authentication |
| `getAuthorities()` | Returns `Collection<? extends GrantedAuthority>` | Holds only authorities attached to Authentication; does not resolve ownership by itself |
| `getName()` | Returns the string name of the principal | Not required to be an immutable database identifier key |
| `getDetails()` | Additional metadata attached to authentication/request | Not the principal or permission set |
| `isAuthenticated()` | Status of the authentication token | Must not replace the full authn/authz policy |
| `setAuthenticated(boolean)` | API to change state on implementations that allow it | Never mark as authenticated from unverified input |

`Authentication` extends `java.security.Principal`. Concrete implementations may handle authorities, state, and data types differently; do not assume every Authentication is username/password.

## 2. Principal: The Identified Subject

### 2.1. A Principal Is Not Necessarily a Username

`principal` may be a user, client, service account, or equivalent identifier. In common username/password flows, the principal after authentication is typically a `UserDetails` object.

| Mechanism | Typical Principal | Characteristics |
| --- | --- | --- |
| Username/password with `DaoAuthenticationProvider` | `UserDetails` | Holds username and data needed for authentication |
| HTTP Basic with `UserDetailsService` | `UserDetails` after login | Basic is a credential transport, not what dictates a single principal type |
| JWT resource server | `Jwt` inside `JwtAuthenticationToken` | Holds claims; name may be mapped from `sub` |
| OAuth2/OIDC login | `OAuth2User` / `OidcUser` | Holds identity attributes from the provider |
| Custom authentication | Application's identity/domain object | Created by a trusted provider/converter |
| Anonymous authentication | Anonymous representation | Not an actual logged-in account |

Example:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    String name = authentication.getName();
    Object principal = authentication.getPrincipal();
}
```

This snippet is for illustration inside a Spring Security application and requires Spring Security imports; it is not a standalone Java program. In code serving public requests, `authentication` may be null or represent an anonymous user, so handle the context accordingly.

### 2.2. `UserDetails` Is a Common Principal Type, Not the Only One

`UserDetails` is a common interface in username/password authentication; it holds username, password hash, authorities, and account status attributes. However, `Authentication.getPrincipal()` returns `Object`, so hard casting like this can fail:

```java
// Valid only if you have guaranteed that principal is actually UserDetails.
UserDetails user = (UserDetails) authentication.getPrincipal();
```

When an application adopts JWT, OIDC, or custom authentication, the principal may be a `Jwt` or `OAuth2User`. Use `getName()` for simple naming needs, or design a unified adapter to extract a **stable subject ID** from the verified mechanism.

### 2.3. Principal and Business Identifiers

A username may be renamed; an email may change; `getName()` may be overridden by a custom mapper. If the database uses an immutable `user_id`, do not rely on username as the order ownership key without a verified mapping.

For example, to serve `GET /api/orders/100`, the service must determine the **real caller**, tenant, and relationship to Order 100 from trusted information. An `X-User-Id: alice` header or body `{"userId":"alice"}` sent by the client must never automatically count as an authenticated principal.

### 2.4. Retrieving the Principal in a Controller

Spring Security provides annotations to read `Authentication` from the context:

```java
@GetMapping("/api/me")
public String me(
        @CurrentSecurityContext(expression = "authentication")
        Authentication authentication
) {
    return authentication.getName();
}
```

If you already know the authentication mechanism produces `UserDetails`, you can bind it directly:

```java
@GetMapping("/api/profile")
public String profile(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
```

Both snippets above are Spring controller fragments and require appropriate imports. If an endpoint permits anonymous access or uses another principal mechanism, guard the type/null check properly and never assume every request carries `UserDetails`.

## 3. Credentials: Evidence Proving Identity

### 3.1. What Can Credentials Be?

- A password entered by a user in form login or HTTP Basic.
- A Bearer token in the HTTP `Authorization` header.
- Proof data from a certificate or another authentication mechanism.
- A custom credentials object understood by the application's `AuthenticationProvider`.

The principal answers "who is being claimed?", while credentials are what gets **verified** to trust that the request represents that identity. Merely knowing a username or email is not enough to prove ownership of an identity.

### 3.2. Plaintext Password vs. Password Hash

In common username/password flows:

1. The request sends the username and raw password over a secure transport channel (HTTPS).
2. `UserDetailsService` looks up the corresponding user by username.
3. `PasswordEncoder.matches(raw, encoded)` checks the raw password against the stored hash.
4. The provider checks required conditions and builds the resulting `Authentication`.
5. Sensitive credentials may be erased from the result after authentication.

Example:

```java
PasswordEncoder encoder = new BCryptPasswordEncoder();
String storedHash = encoder.encode("demo-password");
boolean matches = encoder.matches("demo-password", storedHash);
```

This snippet uses Spring Security libraries and will not compile on its own with `javac` without dependencies/imports. Because BCrypt uses a salt, do not compare `encoder.encode(password).equals(storedHash)`: hashing the same password twice normally produces different strings. Never store plaintext passwords and never hardcode real passwords.

**Password hashes are also sensitive.** A `UserDetails` instance may carry the hash in its password field; never write it to logs or expose it in JSON responses.

### 3.3. Credentials Are Commonly Erased After Authentication

`ProviderManager` has a mechanism to erase credentials from the resulting `Authentication` when appropriate; some principal/details types implement `CredentialsContainer` and `eraseCredentials()`.

Consequences:

- `authentication.getCredentials() == null` **does not mean** the user is not logged in.
- Do not rely on `getCredentials()` to retrieve the password in business logic.
- Not every provider is guaranteed to return null: some token/custom mechanisms store credentials differently.
- Erasing credentials after authentication does not justify logging them beforehand.
- Watch out for cached objects: if multiple places share the same `UserDetails` instance, erasing credentials on one object may affect the cached copy.

The goal is to **reduce how long secrets remain in memory and prevent leaks**, not to replace TLS, secret management, or session policies.

### 3.4. Having Credentials Present Does Not Mean Authenticated

Example of creating an input token in Spring Security:

```java
Authentication request =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "password-from-request"
    );

Authentication result = authenticationManager.authenticate(request);
```

`request` is not yet a trusted result; the provider must verify the password and account. This snippet is a fragment inside a Spring application, not a complete login servlet. If writing a custom login flow, you must set, save/restore the `SecurityContext`, and apply the protections appropriate for the mechanism.

### 3.5. HTTP Basic Is Only a Way to Transmit Credentials

The `Authorization: Basic ...` header contains the Base64-encoded username/password. Base64 **is not security encryption**, so real connections must use HTTPS. HTTP Basic may resend credentials across requests; never log the raw header or use real passwords in documentation examples.

## 4. GrantedAuthority: Granted Roles, Scopes, and Permissions

### 4.1. What Does GrantedAuthority Represent?

`GrantedAuthority` is an interface with the primary method `String getAuthority()`. `SimpleGrantedAuthority` is a common implementation that uses a string to represent an authority, for example:

```text
ROLE_USER
ROLE_ADMIN
report:read
invoice:approve
SCOPE_orders.read
```

In `Authentication`, `getAuthorities()` returns a `Collection<? extends GrantedAuthority>`. These authorities may be loaded via `UserDetailsService`, a provider, or mapped from a **verified** token. Never take a `roles` array submitted by the client in the request body and assign it directly as authorities.

### 4.2. How Does a Role Differ from a Specific Authority?

| Kind | Example | Meaning |
| --- | --- | --- |
| Role | `ROLE_ADMIN` | Responsibility group following a role-naming convention |
| Permission/authority | `report:read` | Specific action permission in the application |
| OAuth2 scope mapping | `SCOPE_orders.read` | Authority mapped by a converter from an access token scope |
| Custom authority | `tenant:shop-a:auditor` | Application-defined authority convention requiring a trusted source |

In the default configuration:

- `hasRole("ADMIN")` typically checks for `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")` checks for the exact string `ROLE_ADMIN`.
- `hasAuthority("ADMIN")` checks for `ADMIN`; it does not automatically prepend `ROLE_`.
- `hasAuthority("report:read")` checks for the exact `report:read` authority.
- When a JWT resource server maps scopes using the default converter, scope `orders.read` typically becomes `SCOPE_orders.read`.

The role prefix is customizable, so keep data, converters, and authorization configuration consistent. Do not confuse the argument to `hasRole` with a string that already includes `ROLE_`.

### 4.3. Authorities Granted to a Principal Differ from Per-Object Permissions

Both Alice and Bob have `ROLE_USER` and `order:read`. Both may enter the order-reading feature, yet Alice must not automatically view Bob's orders. An access decision must evaluate further conditions:

```text
authenticated
AND authority("order:read")
AND sameTenant(principal, order)
AND (isOwner(principal, order)
     OR authority("order:read:any"))
AND businessStateAllowsRead(order)
```

Tenant, owner, and actual state checks require server-side data. With thousands of records, attaching a separate authority per object causes data bloat, hard updates, and difficult revocation. Use authorities for broad permissions and domain policies for permissions on specific resources.

### 4.4. Complex GrantedAuthority

Not every type of authority is accurately represented as a single string. Spring Security documentation allows a complex `GrantedAuthority` to return `null` from `getAuthority()` if the permission cannot be represented as a String. In that case, the authorization component must explicitly understand that custom type. For most applications, `SimpleGrantedAuthority` and clear authority strings are sufficient.

### 4.5. Authenticated Without ROLE_ADMIN

A validly authenticated `Authentication` may still lack `ROLE_ADMIN`, `invoice:approve`, or the corresponding scope. Therefore:

- **Authentication** establishes identity/evidence.
- **GrantedAuthority** describes granted permissions.
- **AuthorizationManager**, request matchers, or method security define rules.
- **Domain policy** makes further decisions on object/tenant/state.

A logged-in user calling an admin API may receive **403 Forbidden**. A user who omits or sends invalid credentials via HTTP Basic typically receives **401 Unauthorized**. Form login may redirect; an invalid CSRF token can also produce 403, so do not deduce a missing role solely from the status code.

## 5. Lifecycle of Authentication: Before and After Verification

| Attribute | Before provider accepts | After successful authentication |
| --- | --- | --- |
| `principal` | Username/identity claimed by client | Verified principal, often `UserDetails` for username/password |
| `credentials` | Password/token awaiting check | May be erased or handled per mechanism |
| `authorities` | No trusted authorities yet | Validly granted/mapped roles, permissions, scopes |
| `authenticated` | Usually `false` | Usually `true` |
| `details` | May carry secondary request metadata | Mechanism-dependent, not permissions |

When authentication fails, no valid resulting `Authentication` is placed in the security context as a logged-in user. Manually constructing a token with `authenticated=true` from a JSON body or header does not substitute for identity verification.

### 5.1. SecurityContext and SecurityContextHolder

`SecurityContext` holds the `Authentication` of the currently executing context. `SecurityContextHolder` is where code accesses the context, typically using a per-thread strategy in traditional Servlet apps. Background threads, `CompletableFuture` tasks, or scheduled jobs do not automatically carry identity/permissions from an HTTP request; if needed, design context propagation or service identity according to policy.

Never write code assuming `SecurityContextHolder.getContext().getAuthentication()` is always non-null on every endpoint and every thread.

### 5.2. AnonymousAuthenticationToken Is an Easy Source of Confusion

An `AnonymousAuthenticationToken` can return `isAuthenticated()==true` on the object itself. Hence the expression `authentication != null && authentication.isAuthenticated()` is **not** a complete way to determine whether a user has actually logged in.

When declaring policies, prefer `.authenticated()`, `.fullyAuthenticated()`, or checks supported by Spring Security. Those rules carry semantics that distinguish anonymous/remember-me users when appropriate.

### 5.3. Authorities Can Become Stale After Role Changes

With long-lived sessions or tokens, authorities may reflect the state at the time the context/token was created. If a role is revoked, active tokens/sessions **do not necessarily update immediately by default**. The system needs refresh/revocation policies, token lifetimes, and runtime permission checks appropriate for the business domain.

## 6. Complete Spring Boot 3 Example: Returning Identity and Authorities Safely

This example uses **Spring MVC + Spring Security 6**, Java 17+, two demo accounts, and HTTP Basic:

- Alice has `ROLE_USER` and `report:read`;
- Admin has `ROLE_USER`, `ROLE_ADMIN`, and `report:read`;
- `GET /api/me` returns name, principal type, and list of authorities, **never credentials**;
- `GET /api/reports` requires `report:read`;
- `GET /api/admin` requires role `ADMIN`.

In a Spring Boot 3 project with the Gradle plugin and dependency management configured, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Create `src/main/java/example/authparts/AuthenticationPartsApplication.java`:

```java
package example.authparts;

import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthenticationPartsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthenticationPartsApplication.class, args);
    }
}

@Configuration
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice-pass"))
            .authorities("ROLE_USER", "report:read")
            .build();

        var admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin-pass"))
            .authorities("ROLE_USER", "ROLE_ADMIN", "report:read")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("report:read")
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}

@RestController
class AuthenticationPartsController {
    record IdentityView(
        String name,
        String principalType,
        boolean authenticated,
        List<String> authorities
    ) {}

    @GetMapping("/api/me")
    IdentityView me(
            @CurrentSecurityContext(expression = "authentication")
            Authentication authentication
    ) {
        List<String> authorities = authentication.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return new IdentityView(
            authentication.getName(),
            authentication.getPrincipal().getClass().getSimpleName(),
            authentication.isAuthenticated(),
            authorities
        );
    }

    @GetMapping("/api/reports")
    Map<String, String> reports() {
        return Map.of("message", "report available");
    }

    @GetMapping("/api/admin")
    Map<String, String> admin() {
        return Map.of("message", "admin allowed");
    }
}
```

Notes:

1. `UserDetailsService` supplies users for username/password authentication. `PasswordEncoder` hashes the demo passwords using BCrypt.
2. Spring Security verifies credentials; the controller neither compares passwords nor reads names from self-asserted headers.
3. Alice has permission to read reports but does not have the admin role.
4. `@CurrentSecurityContext` retrieves the current `Authentication` in Spring Security.
5. The controller does not access `getCredentials()` and does not serialize the raw `Authentication`. Real APIs should further restrict exposed fields.
6. This is **a Java file inside a Spring Boot project**. It requires a Spring Boot Gradle/Maven setup and dependencies; do not compile with plain `javac` without the Spring jars. The demo should only run locally; production HTTP Basic requires HTTPS and proper secret handling.

Run from the project root:

```bash
./gradlew bootRun
```

On Windows, use `gradlew.bat bootRun`.

### 6.1. Testing with curl

```bash
# Not logged in
curl -i http://localhost:8080/api/me

# Alice authenticated
curl -i -u alice:demo-alice-pass http://localhost:8080/api/me

# Has report:read authority
curl -i -u alice:demo-alice-pass http://localhost:8080/api/reports

# Missing ROLE_ADMIN
curl -i -u alice:demo-alice-pass http://localhost:8080/api/admin

# Admin has ROLE_ADMIN
curl -i -u admin:demo-admin-pass http://localhost:8080/api/admin

# Wrong password
curl -i -u alice:wrong-pass http://localhost:8080/api/me
```

Expected results under the example configuration:

| Request | HTTP status | Reason |
| --- | --- | --- |
| Anonymous `GET /api/me` | 401 | HTTP Basic requires authentication |
| Alice `GET /api/me` | 200 | Valid identity |
| Alice `GET /api/reports` | 200 | Has `report:read` |
| Alice `GET /api/admin` | 403 | Missing `ROLE_ADMIN` |
| Admin `GET /api/admin` | 200 | Has `ROLE_ADMIN` |
| Alice with wrong password `GET /api/me` | 401 | Credentials rejected |

Sample JSON response for Alice:

```json
{
  "name": "alice",
  "principalType": "User",
  "authenticated": true,
  "authorities": ["ROLE_USER", "report:read"]
}
```

The authorities list is sorted before output. JSON field order may vary by serializer; the principal type name `User` reflects the built-in `UserDetails` in this example and is **not guaranteed across all mechanisms**. There is no plaintext password, hash, or bearer token in the response.

`curl -u` with demo passwords is convenient for local testing; with real secrets, watch out for shell history, process lists, TLS policy, and credential management.

## 7. Using GrantedAuthority in Access Decisions

In a service, you can read authorities from the context:

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

boolean canReadReport = auth != null
    && auth.getAuthorities().stream()
        .anyMatch(a -> "report:read".equals(a.getAuthority()));
```

This is an illustrative fragment; for public/anonymous endpoints, apply a proper policy instead of only checking non-null. Most applications should use `@PreAuthorize`, `AuthorizationManager`, or a unified policy service to avoid repeating logic.

Method security example:

```java
@PreAuthorize("hasRole('ADMIN')")
public void createAdminReport() {
    // Business operation
}

@PreAuthorize("hasAuthority('report:read')")
public ReportDto readReport(long id) {
    return reportPolicy.loadAuthorizedReport(id);
}
```

These snippets require a real service/method and `@EnableMethodSecurity`; they are not a complete Java file. `hasRole('ADMIN')` checks for `ROLE_ADMIN` by default; `hasAuthority('report:read')` matches the exact string.

Even when a method call passes the authority check, `reportPolicy` must still check object ID, tenant, owner, and state. **Authentication carries broad authorities, but does not by itself decide every permission on individual resources.**

### 7.1. Do Not Build a Trusted Authentication from Unverified Data

Dangerous pattern:

```java
// Anti-pattern: request roles have not been verified.
Authentication forged =
    UsernamePasswordAuthenticationToken.authenticated(
        request.username(),
        null,
        request.roles().stream()
            .map(SimpleGrantedAuthority::new)
            .toList()
    );
```

This snippet merely shows that an object can be constructed with its authenticated flag set without verifying any password or real permission. Calling a factory method does not turn client-supplied data into trusted data. Only components designed to authenticate/map from a trusted source may establish the corresponding principal and authorities.

### 7.2. Different Authorities for Different Sources

- Username/password: authorities usually come from `UserDetailsService` or a provider.
- JWT: claims must be verified before mapping to authorities, especially issuer, audience, signature, and expiry.
- OAuth2 scope: the converter defines the `SCOPE_` convention and which scopes are valid.
- Service account: permissions must match the service's scope and never automatically inherit an end user's admin rights.

Your design should unify identities and authorities even when multiple authentication mechanisms coexist in the same application. A `ROLE_ADMIN` string coming from an unverified token carries no security guarantee.

## 8. Standalone Java 17: Understanding the Three Parts via Access Decisions

The following exercise **simulates** principal, credentials, and authority in plain Java without Spring. It shows that having a username/password in an object is not enough, and an authenticated user still lacks access without the corresponding authority.

Create `AuthenticationModelDemo.java`:

```java
import java.util.Set;

public class AuthenticationModelDemo {

    record Identity(String id, String name) {}

    record AuthState(
        Identity principal,
        String credentials,
        Set<String> authorities,
        boolean authenticated
    ) {}

    static boolean canReadReport(AuthState state) {
        return state != null
            && state.authenticated()
            && state.principal() != null
            && state.authorities() != null
            && state.authorities().contains("report:read");
    }

    public static void main(String[] args) {
        Identity alice = new Identity("u-100", "alice");

        AuthState incoming = new AuthState(
            alice, "demo-password", Set.of(), false
        );
        AuthState verified = new AuthState(
            alice, null,
            Set.of("ROLE_USER", "report:read"),
            true
        );
        AuthState withoutPermission = new AuthState(
            alice, null,
            Set.of("ROLE_USER"),
            true
        );

        System.out.println("Before authentication: "
            + canReadReport(incoming));
        System.out.println("Verified with authority: "
            + canReadReport(verified));
        System.out.println("Verified without authority: "
            + canReadReport(withoutPermission));
        System.out.println("Credentials cleared: "
            + (verified.credentials() == null));
    }
}
```

Compile/run with JDK 17 or higher:

```bash
javac AuthenticationModelDemo.java
java AuthenticationModelDemo
```

**Exact stdout:**

```text
Before authentication: false
Verified with authority: true
Verified without authority: false
Credentials cleared: true
```

Explanation:

- `incoming` has a principal and password, yet its authenticated flag is not successful and it has no trusted authorities.
- `verified` has a principal and the `report:read` authority, so the simulated logic grants read access.
- `withoutPermission` is also authenticated yet still fails the `report:read` check.
- `credentials` can be null after authentication while principal and authorities remain present.

**Limitation:** `AuthState` is only a learning record; any code could instantiate `authenticated=true`. It does not verify passwords/tokens, does not create a `SecurityContext`, and **must not be used as production authentication**. In Spring Security, only a trusted provider establishes the resulting `Authentication`.

## 9. Common Mistakes

### 9.1. Reading `isAuthenticated` as the Sole Authorization Rule

`isAuthenticated()` is a token flag; an anonymous token can carry true. For endpoints requiring an actual login, use `authenticated()`, and sensitive endpoints also need authorities and object-level policies.

### 9.2. Confusing `UserDetails` with Every Principal Type

Hard-casting `(UserDetails) authentication.getPrincipal()` will fail when the principal is a `Jwt` or custom type. Choose an appropriate abstraction or branch by mechanism in a controlled way.

### 9.3. Logging or Serializing Credentials

Never log raw passwords, access tokens, refresh tokens, `Authorization` headers, or password hashes. Only return safe fields in DTOs. Even `getDetails()` should be reviewed before exposing externally.

### 9.4. Comparing Roles with the Wrong Prefix

Under the default convention, `hasRole("ADMIN")` looks for `ROLE_ADMIN`. `hasAuthority("ADMIN")` and `hasAuthority("ROLE_ADMIN")` check two different strings. Pick a consistent convention and test with users who have and lack the authority.

### 9.5. Trusting Client-Claimed Roles

A client can send `roles: ["ROLE_ADMIN"]` or swap in an unverified JWT. Never use those to create authorities; verify the source and map permissions from trusted data.

### 9.6. Treating an Authority as Permission to Read Every Record

`order:read` does not prove a user owns an order. You need resource-level checks for tenant, owner, and specific business conditions.

### 9.7. Inferring Logout from Null Credentials

After authentication, credentials may be erased. Access rights are determined by the security context and proper policies, not by the presence of a password in memory.

### 9.8. Forgetting to Update Authorities When Roles Change

Issued sessions or tokens may retain old authorities. Design revocation mechanisms, lifetimes, refresh flows, and runtime permission checks aligned with risk.

### 9.9. Confusing `PasswordEncoder` with Full Authentication

`PasswordEncoder` only compares a password against a hash. It does not check permissions, ownership, account status, MFA, or brute-force limits. Those responsibilities belong to providers and other protective layers.

## 10. Testing and Debugging Checklist

| Scenario | Principal | Credentials | Authorities | Expected outcome |
| --- | --- | --- | --- | --- |
| Valid login | Verified | Valid | `ROLE_USER` and `report:read` | Appropriate private APIs succeed |
| Wrong password | No valid identity | Wrong | No permissions granted | HTTP Basic typically returns 401 |
| Logged in without admin | Valid identity | Verified | No `ROLE_ADMIN` | Admin API denied, typically 403 |
| User with admin role | Valid identity | Verified | Has `ROLE_ADMIN` | Admin API permitted |
| Anonymous | Null/anonymous | None | No business permissions | Private endpoints denied |
| Valid JWT, missing scope | Identity from verified token | Valid token | Missing required scope | Scope-protected endpoint denied |
| User reading another user's order | Valid identity | Valid | Has general read authority | Object-level policy denies |
| Role changed while session is alive | Old identity may still be valid | Mechanism-dependent | May not yet be updated | Test revocation policy |

When encountering HTTP 401/403, check in order:

1. Which `SecurityFilterChain` and authentication mechanism did the request pass through?
2. Which source set the principal? Is it anonymous?
3. How did the provider verify credentials? **Never log secret values**.
4. What exact strings are inside `authentication.getAuthorities()`?
5. Does the rule require `hasRole`, `hasAuthority`, `authenticated`, a scope, or another condition?
6. Are object/owner/tenant permissions checked in the service?
7. Is the session/token holding stale authorities?
8. Was a POST request rejected by the CSRF layer?

A 403 response can result from a missing role, failed object permission, or CSRF; do not assume every 403 is caused by a missing `GrantedAuthority`. Good tests cover both allow and deny paths, and for state-changing operations verify no unauthorized side effects occur.

## 11. Self-Check Questions

**1.** Username and password are already inside an unauthenticated `Authentication`. Why can't you trust its principal or authorities at that moment?

**2.** After login, `getCredentials()` returns null. Does that mean logged out?

**3.** Alice has `ROLE_USER` and `report:read`. Why doesn't Alice pass `hasRole("ADMIN")`?

**4.** How do `getPrincipal()`, `getName()`, and `getDetails()` differ?

**5.** Why is `hasAuthority("ADMIN")` not identical to `hasRole("ADMIN")`?

**6.** If a caller has `order:read`, can they read every `Order`?

**7.** Why can casting principal to `UserDetails` fail in JWT/OIDC?

**8.** If `ROLE_ADMIN` is revoked from a user, should you assume an active open session updates instantaneously?

**Suggested answers:**

1. The data is merely claimed and has not yet been verified by a provider.
2. No. Credentials may be erased to reduce exposure; login state lives in the context/token/session mechanism.
3. Because the admin role checks for `ROLE_ADMIN` by default, and Alice has not been granted that authority.
4. `principal` is the identity object; `name` is its string name representation; `details` is secondary request/authentication metadata.
5. `hasAuthority` checks the exact string, whereas `hasRole` prepends `ROLE_` by default.
6. No. You must enforce permissions by object, owner, tenant, and context.
7. Because the principal may be a `Jwt`, `OAuth2User`, or a custom type depending on the provider.
8. No. You need refresh/revocation/TTL policies or fresh permission checks at execution time.

### Official References

- [Spring Security: Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security: Authorization Architecture / GrantedAuthority](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security: Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security: Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html)
- [Spring Security: OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
