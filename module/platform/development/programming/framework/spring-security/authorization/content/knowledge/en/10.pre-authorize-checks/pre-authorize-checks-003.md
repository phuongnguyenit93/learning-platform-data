# Referencing authentication, principal, and username

> **Module:** Spring Security – authorization  
> **Group:** Pre-method checks  
> **Focus:** Using `authentication`, `principal`, `authentication.name`, and `principal.username` expressions inside `@PreAuthorize`; comparing method parameters against the caller's identity; handling differences across UserDetails, JWT, OAuth2, and anonymous; avoiding confusing display names with stable identifiers and resource permissions.

## 1. Problem: is the caller truly the profile owner?

An application has a service:

~~~java
public ProfileDto getProfile(String username) {
    return repository.findByUsername(username);
}
~~~

If Alice calls `getProfile("alice")`, reading her own profile may be permitted. If Bob calls `getProfile("alice")`, it must be denied unless Bob has a specifically designed permission.

Spring Security allows writing:

~~~java
@PreAuthorize(
    "isAuthenticated() and #username == authentication.name"
)
public ProfileDto getProfile(String username) {
    return repository.findByUsername(username);
}
~~~

This expression intends: **the caller must be considered authenticated, and the call's `username` parameter must match the name reported by `Authentication#getName()`**.

However, to use it safely, you must understand:

- `authentication` is the **Authentication object**, not a username string.
- `principal` is the **identity object** inside Authentication, not necessarily a `UserDetails`.
- `authentication.name` is **the result of `getName()`**, which may be a username, an ID inside a JWT, or a provider-specific identifier.
- `principal.username` is only valid when **the principal type has a username property**.
- `#username` is a method parameter resolved by Spring Security in SpEL, not a value verified by the framework on its own.
- A user with a matching name is still not allowed by default to read **just any record**: authority, owner, tenant, and object policies are also required.

**Key takeaway:** `authentication.name` is often useful for comparing names in simple problems, but **it is not a universal authorization key for every resource or every authentication mechanism**.

## 2. Enabling method security and determining check timing

In Spring Boot 3.x/Spring Security 6.x, declare:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

When `@EnableMethodSecurity` is active, Spring Security registers method-security interceptors. With `@PreAuthorize`, the expression is evaluated **before the method body** when the invocation goes through a Spring-managed proxy.

~~~text
Controller / scheduler / message listener
                |
                v
      Spring-managed service proxy
                |
                +--> @PreAuthorize
                |      |
                |      +--> Current Authentication
                |      +--> Method arguments
                |      +--> Authorization expression
                |
            allow / deny
                |
                v
           Method body
~~~

The annotation does not run automatically if the service is created with `new` instead of Spring DI or when the call bypasses Spring AOP advice. In normal proxy mode, `this.securedMethod()` is **self-invocation**, which can bypass the interceptor.

A service can be called from HTTP, a batch job, or an event consumer. HTTP `authorizeHttpRequests` rules and method rules are **two distinct layers** and do not replace each other. For HTTP requests, denial can map to 401/403/redirect depending on the authentication entry point and exception handling; not every `@PreAuthorize` false result returns the exact same status.

## 3. Source of Authentication: SecurityContext

In a typical Servlet stack:

~~~text
SecurityContextHolder
    |
    v
SecurityContext
    |
    v
Authentication
    +--> getName()
    +--> getPrincipal()
    +--> getAuthorities()
    +--> getCredentials()
    +--> getDetails()
    +--> isAuthenticated()
~~~

`Authentication` can be the input passed into `AuthenticationManager` during authentication or the token representing an already-authenticated user. After authentication, Spring Security stores it in the appropriate `SecurityContext`.

To access it via the Java API:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    String name = authentication.getName();
    Object principal = authentication.getPrincipal();
    var authorities = authentication.getAuthorities();
}
~~~

The snippet above requires Spring Security dependencies and runtime context; **it is not a standalone Java program**.

In method-security SpEL, Spring Security provides built-in security expression root fields and helpers:

~~~text
authentication              -> Authentication bound to the invocation
authentication.name         -> Authentication#getName()
authentication.principal    -> Authentication#getPrincipal()
principal                   -> Authentication#getPrincipal()
hasAuthority("document:read")-> Check authority
hasRole("ADMIN")            -> Check role with default ROLE_ prefix
isAuthenticated()           -> Framework helper following trust semantics
~~~

### 3.1. Authentication and principal are not the same type

Username/password login example:

~~~text
authentication:
  type        = UsernamePasswordAuthenticationToken
  name        = alice
  principal   = UserDetails(username=alice, ...)
  authorities = [ROLE_USER, profile:read]
~~~

`authentication` is **the entire token**; `principal` is **one field of the token**. The token also holds authorities and authentication state. Do not write `#username == authentication` because the two sides do not share the same meaning.

## 4. authentication, principal, authentication.name, principal.username

| SpEL | Meaning | Example | What to avoid |
|---|---|---|---|
| `authentication` | Current `Authentication` object | UsernamePasswordAuthenticationToken/JwtAuthenticationToken | Treating it as a String |
| `principal` | `authentication.getPrincipal()` | UserDetails/Jwt/OAuth2User/String | Assuming it is always UserDetails |
| `authentication.name` | `authentication.getName()` | `alice` or `u-42` | Assuming it is username/email |
| `authentication.principal` | Same object as `principal` | A Jwt or custom principal | Treating it as a normalized ID |
| `principal.username` | `username` getter/property **if it exists** | `UserDetails#getUsername()` | Using with String/Jwt |
| `authentication.authorities` | Set of GrantedAuthority | `ROLE_USER`, `SCOPE_read` | Comparing manually with wrong prefix |
| `authentication.authenticated` | Token `isAuthenticated()` flag | Can be true on anonymous token | Treating as real login |
| `isAuthenticated()` | Expression helper per Spring trust semantics | Properly recognizes authenticated users | Equating with raw flag |

**Core difference:** `authentication.name` asks **what name the token returns**. `principal.username` asks **whether the principal has a username property**. They may share the same value in form login, but there is no universal contract across JWT, OAuth2, and anonymous.

### 4.1. UserDetails

If the principal is `UserDetails`, the following expression is usually valid:

~~~java
@PreAuthorize(
    "isAuthenticated() and #username == principal.username"
)
public String readOwnSettings(String username) {
    return "settings:" + username;
}
~~~

`principal.username` invokes the property from `UserDetails#getUsername()`. However, you must ensure the `username` parameter is discovered properly and the method invocation goes through the Spring proxy.

### 4.2. String or Jwt

In some anonymous flows:

~~~text
principal = "anonymousUser"
~~~

`String` has no `username` property under the `UserDetails` contract. Similarly, a `Jwt` principal has claims rather than `getUsername()`.

Evaluating `principal.username` on an incompatible principal type **can cause a SpEL property resolution error** rather than being guaranteed to return false. SpEL's null-safe operator does not turn a String into a UserDetails.

If the application supports multiple authentication mechanisms, use `authentication.name` when the contract is clear or delegate identification logic to a policy bean that handles each principal type fail-closed.

## 5. Why does #username have # while authentication does not?

Example:

~~~java
@PreAuthorize("#username == authentication.name")
~~~

- `#username` is a method parameter variable.
- `authentication` is a property on the security expression root.
- `principal` is also a root property.
- `hasAuthority('x')` is a helper method on the root.
- `authentication.name` accesses a property on the Authentication object.

Do not blindly change it to:

~~~java
@PreAuthorize("#username == #authentication.name")
~~~

thinking `#authentication` is a universal built-in variable. Per Spring Security documentation, the standard syntax here is **`authentication` without `#`**.

### 5.1. Parameter names must be discovered

Spring Security uses `DefaultSecurityParameterNameDiscoverer`, with name sources such as:

1. Spring Security's `@P("username")`.
2. Spring Data's `@Param` in supported cases.
3. Metadata from the Java compiler flag `-parameters`.
4. Debug symbols of concrete methods in applicable cases.

Explicit example:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;

@PreAuthorize(
    "isAuthenticated() and #username == authentication.name"
)
public String selfProfile(@P("username") String username) {
    return "profile:" + username;
}
~~~

In a project with `-parameters` enabled, `@P` may not be necessary. But when the annotation sits on an interface, debug local-variable metadata does not provide names the way a concrete method does, so `@P` or `-parameters` is especially helpful.

If the build does not preserve method parameter names, SpEL may fail to resolve `#username` and the policy malfunctions. **Do not remove the condition just to make tests pass**; fix the parameter metadata and write integration tests.

## 6. Spring Service example: one's own profile

Full example in a Spring-managed service class:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {

    @PreAuthorize(
        "isAuthenticated() and #username == authentication.name"
    )
    public String selfProfile(@P("username") String username) {
        return "profile:" + username;
    }
}
~~~

When `authentication.name = "alice"`:

| Context | `#username` | Method pre-authorization result |
|---|---|---|
| Alice logged in | `alice` | Allow |
| Alice logged in | `bob` | Deny |
| Bob logged in | `alice` | Deny |
| Anonymous | `anonymousUser` | Deny due to `isAuthenticated()` |
| JWT name is `u-42` | `alice` | Does not match by default |
| Account permissions revoked but token is stale | `alice` | Needs additional freshness/revocation checks |

This class only returns a string to test the concept; production data needs owner/tenant queries and corresponding permissions.

### 6.1. Combining permissions

~~~java
@PreAuthorize(
    "hasAuthority('profile:read') and " +
    "isAuthenticated() and #username == authentication.name"
)
public ProfileDto readOwnProfile(@P("username") String username) {
    return repository.findByUsername(username);
}
~~~

The snippet depends on a real `ProfileDto` and repository. The condition requires **both the authority and the username**. If a user has the matching name but lacks `profile:read`, access is denied.

### 6.2. Expanding admin/support permissions must be intentional

~~~java
@PreAuthorize(
    "hasAuthority('profile:read') and " +
    "(#username == authentication.name or hasRole('SUPPORT'))"
)
public ProfileDto readProfile(@P("username") String username) {
    return repository.findByUsername(username);
}
~~~

**This is only an illustration:** a support user could read all profiles without additional constraints. In a multi-tenant system or with private data, the policy must check tenant, assignment, purpose, and target resource. Role SUPPORT alone does not prove authorization to read every customer's PII.

## 7. JWT: authentication.name can be sub

Spring Security OAuth2 Resource Server typically follows the flow:

~~~text
Bearer token
  -> JwtDecoder + validators
  -> JwtAuthenticationConverter
  -> JwtAuthenticationToken
  -> SecurityContext
~~~

Example verified JWT:

~~~json
{
  "iss": "https://id.example",
  "sub": "u-42",
  "preferred_username": "alice",
  "tenant": "tenant-7",
  "scope": "document:read"
}
~~~

In a common default configuration:

~~~text
authentication.name          = "u-42"
principal                    = Jwt
principal.claims['sub']      = "u-42"
principal.username           = not present by default
~~~

The user might see the name `alice` in the UI while `Authentication#getName()` is `u-42`. Comparing `#username="alice"` with `authentication.name="u-42"` yields false.

`JwtAuthenticationConverter` can be configured to use another principal claim, so never claim every JWT app returns `name=sub`. What is true is that **you must verify the converter and contract of each authentication mechanism**.

### 7.1. Claim-based expressions only work when the type is known

If you know for sure the principal is a verified `Jwt`, for example:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_document:read') " +
    "and principal.claims['sub'] == #subject"
)
public String readForSubject(@P("subject") String subject) {
    return "subject:" + subject;
}
~~~

This is a **JWT Resource Server-dependent** snippet; the `SCOPE_document:read` authority only applies when the converter uses that mapping. The token must have its signature, issuer, audience, timestamps, algorithm, and critical claims validated per architecture. Comparing `sub` to a parameter still does not prove the user has rights to a **specific document**.

### 7.2. The sub identifier must be tied to the issuer

~~~text
(issuer A, sub=u-42)  !=  (issuer B, sub=u-42)
~~~

Two providers can issue the same subject string for different users. With multi-IdP setups, map `issuer + subject` to a **stable internal user ID** before applying business authorization.

Do not use email or `preferred_username` as a general owner key if they can change, are not unique, or are unverified.

## 8. OAuth2 Login and OIDC

With OAuth2 Login, the principal is typically `OAuth2User` and in OIDC it may be `OidcUser`. Names and attributes depend on the provider:

~~~text
authentication.name
principal.name
principal.attributes
principal.claims     (depending on OIDC/JWT principal)
~~~

Do not assume every OAuth2 principal has `username` or `email`. If comparing:

~~~java
@PreAuthorize("principal.attributes['email'] == #email")
~~~

to determine ownership, consider whether the email is verified, mutable, or collides across accounts/providers. **Provider attributes do not inherently carry permissions over application data**.

A better solution is mapping the authenticated IdP identity to an internal ID and trusted tenant memberships, then checking service policies using server data.

## 9. Anonymous and remember-me are not like real authenticated users

An `AnonymousAuthenticationToken` can have `isAuthenticated()==true` even though it represents an anonymous user. Therefore:

~~~java
authentication.isAuthenticated()
~~~

should not be used **alone** to detect a real login.

Method-security expression helpers like:

~~~java
@PreAuthorize("isAuthenticated()")
@PreAuthorize("isFullyAuthenticated()")
~~~

follow Spring Security's trust-resolver semantics, distinct from the raw token flag.

| Expression/field | Effect | Remember |
|---|---|---|
| `authentication.authenticated` | Token flag | Can be true for anonymous |
| `isAuthenticated()` | Caller treated as authenticated by the framework | Not identical to raw flag |
| `isAnonymous()` | Anonymous principal | Not a user account |
| `isRememberMe()` | Remember-me context | Lower trust than full login |
| `isFullyAuthenticated()` | Full authentication, not merely remember-me | May still need MFA/step-up |

Do not use the string `anonymousUser` as an owner ID. A client can send the path `/profiles/anonymousUser`, which **does not** constitute a trusted identity.

### 9.1. Account status and token/session freshness

If a user is disabled after a session/token was issued, `authentication.name` might not change. Permission freshness, token expiry, revocation, account-status checks, and cache invalidation must be designed according to the action's sensitivity.

**A matching name does not prove permissions are still valid.**

## 10. Custom principals and immutable user IDs

An application can standardize its principal:

~~~java
public final class CurrentUser {
    private final String userId;
    private final String tenantId;
    private final String username;

    public CurrentUser(String userId, String tenantId, String username) {
        this.userId = userId;
        this.tenantId = tenantId;
        this.username = username;
    }

    public String getUserId() { return userId; }
    public String getTenantId() { return tenantId; }
    public String getUsername() { return username; }
}
~~~

When the actual principal is `CurrentUser`, SpEL can read `principal.userId`, `principal.tenantId`, and `principal.username`. However, declaring this class **does not automatically convert Jwt/OAuth2User into CurrentUser**; an explicit authentication provider/converter or identity mapping is required.

An illustrative expression:

~~~java
@PreAuthorize(
    "isAuthenticated() and #userId == principal.userId"
)
public ProfileDto readProfile(@P("userId") String userId) {
    return repository.findByUserId(userId);
}
~~~

This is better than comparing usernames if the ID is stable, the principal is established from a trusted authentication source, and the method is called with the expected principal type. Tenant/resource constraints are still needed when accessing real data.

**Never construct CurrentUser from client-supplied `X-User-Id` or `tenantId` without authenticating the source.**

## 11. When is comparing username not enough?

Username/email are metadata that can change or be reused.

~~~text
Month 1: Alice username=alice,        internal userId=u-42
Month 4: Alice username=alice.nguyen, internal userId=u-42
Month 5: Another user takes username=alice, internal userId=u-99
~~~

If ownership is stored by username, permissions can become mismatched upon rename/reuse. Resources should carry a stable owner ID and tenant ID:

~~~text
userId           = u-42
username         = alice.nguyen
verified subject = (issuer, sub)
tenant membership= server data
document.ownerId = u-42
document.tenantId= tenant-7
~~~

An API with path `GET /users/u-42/documents/100` is not authorized merely because the user put `u-42` in the path. The server must obtain the real identity from authentication, load the real document from the repository, and verify owner/tenant/authority.

### 11.1. Authorization by action and resource

Granting `document:read` does not implicitly grant `document:export`, `document:delete`, or `document:approve`. Each action needs its own permission, and object policies may check state, owner, tenant, sharing, assignment, or processing purpose.

## 12. Policy beans: passing Authentication into resource-check logic

Instead of stuffing tenant, owner, and principal type checks into SpEL:

~~~java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@documentPolicy.canRead(authentication, #documentId)"
)
public DocumentDto readDocument(@P("documentId") long documentId) {
    return documentRepository.getDto(documentId);
}
~~~

Here:

- `authentication` is the full object.
- `#documentId` is the parameter named with `@P`.
- `hasAuthority('document:read')` checks the functional permission.
- `@documentPolicy` is a Spring bean used for the security decision.
- `canRead(...)` checks the resource and identity in testable code.

Illustrative implementation example:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentRepository repository;

    public DocumentPolicy(DocumentRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication authentication, long documentId) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        Object principal = authentication.getPrincipal();
        if (!(principal instanceof CurrentUser user)) {
            return false;
        }

        return repository.existsReadableByOwnerAndTenant(
                documentId, user.getUserId(), user.getTenantId());
    }
}
~~~

This is a **snippet depending on CurrentUser, DocumentRepository, and application data**, not standalone Java. Because `authentication.isAuthenticated()` can be true for anonymous tokens, rejecting unsupported principal types in the example is important; in multi-mechanism apps, add `AuthenticationTrustResolver` or an identity resolver to distinguish states.

`existsReadableByOwnerAndTenant` represents a query scoped by owner and tenant. Real policies may include shared users, organization memberships, and document statuses.

### 12.1. Avoiding time-of-check/time-of-use on writes

For deleting/approving documents, checking ownership first and then performing the write outside a transaction can suffer races if state changes. Consider transactions, locking, version checks, or conditional updates. Do not replace `@PreAuthorize` with `@PostAuthorize` on writes with side effects, because post-checks run after the method body.

## 13. Standardizing identity across multiple login flows

~~~text
Form login -> UserDetails ---------+
                                    |
JWT        -> Jwt ------------------+--> IdentityResolver
                                    |         |
OAuth2     -> OAuth2User -----------+         v
                                           InternalIdentity
                                          (userId,tenantId)
                                                |
                                                v
                                         Resource policy
~~~

There are two approaches:

1. Have every authentication provider/converter produce the same custom principal after authentication.
2. Keep native principals, while an `IdentityResolver` knows how to convert each trusted type into an internal identity.

Illustrative interface:

~~~java
public interface IdentityResolver {
    InternalIdentity requireIdentity(Authentication authentication);
}
~~~

Unsupported token types must be rejected; never treat anonymous or an unknown String as a valid user. Do not put raw credentials/JWTs into logs or business identity DTOs unnecessarily.

### 13.1. Authority namespaces

JWT scopes may be mapped to `SCOPE_document:read`, roles to `ROLE_USER`, and business permissions to `document:read`:

~~~text
ROLE_USER             : role
SCOPE_document:read   : JWT scope under common converter
document:read         : application business authority
~~~

`hasAuthority('document:read')` and `hasAuthority('SCOPE_document:read')` are not equivalent by default. Test the production converter and policies in the right namespace.

## 14. How does @AuthenticationPrincipal in a controller differ from principal in SpEL?

Spring MVC supports injecting the principal:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {
    @GetMapping("/whoami")
    public String whoami(@AuthenticationPrincipal Object principal) {
        return principal == null
                ? "unknown"
                : principal.getClass().getSimpleName();
    }
}
~~~

This is a Spring MVC controller snippet, not plain Java. If the actual principal is a `Jwt`, do not inject it into a `UserDetails` parameter and assume binding succeeds.

| Location | How it is used |
|---|---|
| `@PreAuthorize` | Root properties `authentication` and `principal` |
| Spring MVC controller | `@AuthenticationPrincipal` or `Authentication` |
| Service Java code | `SecurityContextHolder.getContext().getAuthentication()` |
| Policy bean | `@documentPolicy.canRead(authentication, #id)` |

Spring Security also offers `@CurrentSecurityContext` to obtain the context or a property from it in supported locations. Inside `@PreAuthorize`, `authentication` is already available, so there is usually no need to pass it down from a controller just to compare names.

## 15. Async and scheduled method calls

By default in the Servlet stack, `SecurityContextHolder` uses `ThreadLocal`. When switching from an HTTP request thread to an executor:

~~~text
Request thread: Alice's Authentication
       |
       +--> submit async task
                    |
                    v
               Worker thread
               Does not have the same context by default
~~~

If a method protected by `@PreAuthorize("authentication.name == #username")` is called from a task lacking a SecurityContext, it may be denied or evaluate unexpectedly.

Spring Security provides concurrency wrappers such as `DelegatingSecurityContextExecutor`/`DelegatingSecurityContextRunnable` to propagate context properly. For scheduled jobs without an end-user, create a **dedicated service identity and permissions** or a controlled execution policy. Never set one shared global SecurityContext for all threads/users.

Important: propagated context must be cleaned up after the task finishes so identities do not leak across tasks reused on a thread pool.

## 16. Standalone Java 17: token name vs. stable subject

The following program uses **plain Java** to simulate two principal types and an anonymous token. It does not use Spring Security, verify JWTs, or replace an authentication provider. Its goal is to show that `name` and `stable subject` can differ.

Create `AuthenticationReferenceDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class AuthenticationReferenceDemo {
    record UserProfile(String username, String userId) {}
    record JwtLike(String subject, Map<String, String> claims) {}
    record AuthenticationView(
            Object principal, String name, Set<String> authorities,
            boolean authenticatedFlag, boolean anonymous) {}

    static boolean mayUseSelfProfile(AuthenticationView auth, String username) {
        return !auth.anonymous() && auth.authenticatedFlag()
                && auth.name().equals(username);
    }

    static String stableId(AuthenticationView auth) {
        if (auth.anonymous() || !auth.authenticatedFlag()) {
            return null;
        }
        if (auth.principal() instanceof UserProfile user) {
            return user.userId();
        }
        if (auth.principal() instanceof JwtLike jwt) {
            return jwt.subject();
        }
        return null;
    }

    static boolean canReadOwned(AuthenticationView auth, String ownerUserId) {
        String subject = stableId(auth);
        return subject != null
                && auth.authorities().contains("document:read")
                && subject.equals(ownerUserId);
    }

    public static void main(String[] args) {
        var password = new AuthenticationView(
                new UserProfile("alice", "u-42"),
                "alice", Set.of("document:read"), true, false);
        var jwt = new AuthenticationView(
                new JwtLike("u-42", Map.of("sub", "u-42")),
                "u-42", Set.of("document:read"), true, false);
        var anonymous = new AuthenticationView(
                "anonymousUser", "anonymousUser", Set.of(), true, true);

        System.out.println("password authentication.name: " + password.name());
        System.out.println("password principal.username: "
                + ((UserProfile) password.principal()).username());
        System.out.println("jwt authentication.name: " + jwt.name());
        System.out.println("jwt principal has username: "
                + (jwt.principal() instanceof UserProfile));
        System.out.println("same authentication.name: "
                + password.name().equals(jwt.name()));
        System.out.println("same stable subject: "
                + stableId(password).equals(stableId(jwt)));
        System.out.println("password self alice: "
                + mayUseSelfProfile(password, "alice"));
        System.out.println("password self bob: "
                + mayUseSelfProfile(password, "bob"));
        System.out.println("JWT can read own document: "
                + canReadOwned(jwt, "u-42"));
        System.out.println("JWT can read another document: "
                + canReadOwned(jwt, "u-99"));
        System.out.println("anonymous authenticated flag: "
                + anonymous.authenticatedFlag());
        System.out.println("anonymous accepted as user: "
                + mayUseSelfProfile(anonymous, "anonymousUser"));
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 AuthenticationReferenceDemo.java
java AuthenticationReferenceDemo
~~~

Exact verified output:

~~~text
password authentication.name: alice
password principal.username: alice
jwt authentication.name: u-42
jwt principal has username: false
same authentication.name: false
same stable subject: true
password self alice: true
password self bob: false
JWT can read own document: true
JWT can read another document: false
anonymous authenticated flag: true
anonymous accepted as user: false
~~~

Interpretation:

- Password principal has username `alice`, and its name is also `alice`.
- JWT-like principal has no UserProfile/username type; its name comes from subject `u-42` in the simulation.
- The two names differ yet share the same stable subject because the demo intentionally maps them to one ID.
- Self-profile check rejects Bob.
- Reading a document also requires permission and matching owner ID.
- Anonymous has the flag set to true, yet is not treated as a real user.

The simulation **does not guarantee all JWTs share the same stable subject namespace**. Production must verify `issuer + subject`, signature, audience, expiry, and identity mapping before trusting a token.

## 17. Integration testing with @WithMockUser

Assume `ProfileService` from section 6 and `@EnableMethodSecurity` exist.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class ProfileMethodSecurityTest {

    @Autowired
    ProfileService profiles;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void aliceCanReadAlice() {
        assertEquals("profile:alice", profiles.selfProfile("alice"));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void aliceCannotReadBob() {
        assertThrows(AccessDeniedException.class,
                () -> profiles.selfProfile("bob"));
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void bobCannotReadAlice() {
        assertThrows(AccessDeniedException.class,
                () -> profiles.selfProfile("alice"));
    }
}
~~~

**This is a test class in a project with Spring Boot, Spring Security Test, and real beans**, not runnable with a single `javac` command. Tests must inject the Spring-managed proxy so the annotation is evaluated.

### 17.1. @WithMockUser tests are not enough for production JWT

`@WithMockUser` typically sets up a UserDetails-style principal whose name is the username given by the test. If the production JWT name is `sub`, a `@WithMockUser(username="alice")` test can pass while real JWT users are denied when the expression compares against `alice`.

Add JWT resource server tests with claims, authorities, issuer/subject, and the converter reflecting production. Test that the principal has the right type and the policy resolves to a stable identity cleanly.

### 17.2. Negative tests are the most important part

| Case | Expected result |
|---|---|
| Alice views Alice with valid username contract | Allow |
| Alice views Bob | Deny |
| Bob views Alice | Deny |
| Anonymous sends `anonymousUser` | Deny |
| User lacks `document:read` | Deny |
| User has authority but different owner | Deny |
| User has authority but different tenant | Deny |
| JWT name=sub, argument=username | Do not assume equality |
| Principal is Jwt, expression requires `principal.username` | Detect type mismatch, update policy |
| OAuth2 providers A/B use different names | Identity mapping present |
| Token revoked/account disabled | Deny per freshness policy |
| Missing `@P` and `-parameters` | Test detects parameter name issue |
| Service called via `this.securedMethod()` | Test detects proxy bypass |
| Async task without context | Deny or proper service identity |

Test resources with two users, two tenants, and documents with different owners to catch BOLA/IDOR. A `404` from a nonexistent controller **does not prove** security blocked it; for method security, call the real service bean.

## 18. Common mistakes

| Mistake | Risk | Fix |
|---|---|---|
| Treating `authentication` as a String | Type mismatch comparison | Use `authentication.name` |
| Assuming `principal` is always UserDetails | JWT/OAuth2/String have different types | Know principal runtime type |
| Using `principal.username` across all flows | Property missing | Standardize identity/policy bean |
| Assuming `authentication.name` is email | Could be `sub`/provider ID | Check converter contract |
| Missing `#` before parameter | SpEL doesn't read argument | `#username` |
| Using `#authentication` out of habit | Wrong default root property | `authentication` |
| Missing `@P`/`-parameters` | Cannot resolve parameter names | Configure build/tests |
| Reading `authentication.authenticated` as “real login” | Anonymous can be true | Trust-aware helper |
| Comparing only username to read data | Skips owner/tenant | Stable ID + object policy |
| Trusting client tenantId/header | Tenant spoofing | Verified identity/server data |
| Email/display name as owner key | Rename/reuse causes mix-ups | Immutable user ID |
| Confusing `SCOPE_document:read` with `document:read` | Unexpected authorization | Authority mapping |
| Using only `@WithMockUser` | Fails to test JWT principal type | JWT/OAuth2 integration tests |
| Calling `new Service()` or `this.method()` | Bypasses AOP proxy | Spring DI / separate bean |
| Using `@PostAuthorize` for writes | Body runs before denial | `@PreAuthorize` / transaction guard |
| Async thread lacks context | Missing/wrong authentication | Propagation and cleanup |
| Logging raw Authentication/JWT | Leaks credentials/PII | Minimal logging and masking |

## 19. Pre-merge checklist

- [ ] `@EnableMethodSecurity` is enabled and calls go through the Spring bean/proxy.
- [ ] Authentication and principal types are identified for all login flows.
- [ ] Distinguished `authentication`, `principal`, `authentication.name`, and `principal.username`.
- [ ] `#argument` is used properly and names are preserved with `@P`/`-parameters`.
- [ ] Raw token flags are not used as proof of a real user.
- [ ] Mutable username/email are not used as owner keys.
- [ ] JWT issuer+subject are verified and mapped to an internal user ID.
- [ ] Authority prefixes `ROLE_`/`SCOPE_`/business permissions are consistent.
- [ ] Object authorization verifies resource owner, tenant, action, and context.
- [ ] Path/query/headers are not trusted as proof of authorization.
- [ ] Tested Alice/Bob, anonymous, cross-tenant, missing permission, and revoked accounts.
- [ ] Tested JWT/OAuth2 runtime rather than only mocked usernames.
- [ ] No proxy bypasses via self-invocation/`new`/final/private methods.
- [ ] Async/schedulers have clear service identities and SecurityContext lifecycles.
- [ ] Secrets, raw JWTs, or credentials are never logged.

**Remember:** *Use `authentication.name` only when you know for sure what kind of name it represents; use `principal.username` only when the actual principal has that property; resource permissions must rely on verified identity and server data.*

## 20. Self-check questions

**1. What is `authentication`?**  
It is the `Authentication` object, not a username String.

**2. What is `principal`?**  
It is `Authentication#getPrincipal()`.

**3. Where does `authentication.name` come from?**  
From `Authentication#getName()`.

**4. Does `principal.username` always exist?**  
No; only when the principal has a username property.

**5. Why does `#username` have `#`, while `authentication` does not?**  
Method parameters are SpEL variables; `authentication` is a root property.

**6. A JWT has `sub=u-42`, `preferred_username=alice`; is comparing `authentication.name` with `alice` guaranteed true?**  
No, `name` may be `sub` depending on the converter.

**7. If an anonymous token has `isAuthenticated()==true`, is it a real user?**  
No. Use trust-aware method-security expressions/helpers.

**8. Does having `document:read` allow reading every document in the system?**  
No; owner, tenant, and resource-specific policies also apply.

**9. Why does `@WithMockUser` pass in tests while production JWT fails?**  
Mock users may use UserDetails/username, whereas JWT has a `Jwt` principal whose name is subject.

**10. Why should a stable internal user ID be used?**  
Usernames/emails can change, be reused, and are not unique across providers/tenants.

**11. When should `@documentPolicy.canRead(authentication,#id)` be used?**  
When complex principal mapping, authorities, tenant/owner, and object rules are needed.

**12. Is `this.securedMethod()` guaranteed to evaluate `@PreAuthorize`?**  
No in normal proxy mode; self-invocation can bypass advice. Place security at a testable Spring-managed service boundary.

## 21. Official documentation

- Spring Security – **Method Security**, sections *Expressing Authorization with SpEL* and *Using Method Parameters*: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – **Servlet Authentication Architecture**: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – **Authorization Architecture**: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security – **Anonymous Authentication**: https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html
- Spring Security – **OAuth2 Resource Server JWT**: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security – **Authentication JavaDoc**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html
- Spring Security – **Method Security Testing**: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Framework – **Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
