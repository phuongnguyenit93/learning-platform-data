# SecurityContext, SecurityContextHolder, and the Current Request's Identity

In a **Servlet-based Spring Security** application, the question "who is making this request?" is answered primarily through **`SecurityContext`** and **`SecurityContextHolder`**. Once the authentication mechanism has verified credentials, Spring Security places an `Authentication` object into `SecurityContext`; `SecurityContextHolder` is the access point to the context bound to the current execution thread. From there, filters, controllers, and the service layer can determine the identity recognized by the framework, along with the granted authorities.

However, **SecurityContext does not validate passwords itself, is not an HttpSession, is not a JWT token, and is not a business account profile**. It is a container holding security state loaded or established during request processing. If the context does not yet have an `Authentication`, or only holds an anonymous authentication, you must not conclude that the caller is an actually logged-in user. If you manually construct an `authenticated=true` token from client data without going through `AuthenticationManager`, you have bypassed the trust boundary.

This lesson belongs to the **Servlet Context** section in Spring Security Authentication. It builds the model from `Authentication` → `SecurityContext` → `SecurityContextHolder`, explains the lifecycle within `SecurityFilterChain`, thread-bound behavior, persistence across requests via `SecurityContextRepository`, stateless/JWT cases, safe ways to read identity, async handling, and a standalone runnable Java 17 example.

## 1. The Big Picture: Who, Authenticated by What, and Stored Where?

~~~text
HTTP request
   |
   v
Servlet FilterChainProxy / SecurityFilterChain
   |
   +--> SecurityContextRepository loads context (if configured)
   |       |
   |       '--> SecurityContextHolder of the request thread
   |
   +--> Authentication filter (session/form/basic/bearer/...)
   |       |
   |       +--> No valid proof yet -> unauthenticated / anonymous
   |       |
   |       '--> Valid credentials/token
   |               -> Authenticated Authentication
   |               -> SecurityContext.setAuthentication(...)
   |               -> SecurityContextHolder.setContext(...)
   |
   +--> Authorization filters / method security
   |       '--> Uses Authentication/authorities to decide access
   |
   +--> Controller -> Service -> Repository
   |       '--> Reads current identity if needed, checks business permissions
   |
   '--> End of dispatch / request
           -> Clear SecurityContextHolder to avoid leaking to the next request
~~~

This is a conceptual diagram. In Spring Security 6, the exact details of loading and saving the context depend on the configured filters, repository, and authentication mechanism. A request may only have an anonymous token; for a resource server using JWT, the context is typically created from the bearer token on **each request** rather than restored from a server-side login session.

### 1.1. Three Core APIs

| API | Role | Example |
|---|---|---|
| `Authentication` | Carries the **principal**, credentials (if still present), authorities, details, and authentication status | `UsernamePasswordAuthenticationToken`, `JwtAuthenticationToken`, `AnonymousAuthenticationToken` |
| `SecurityContext` | Object holding the current `Authentication` | `context.getAuthentication()` |
| `SecurityContextHolder` | Mechanism for holding/retrieving the `SecurityContext` of the current execution environment | `getContext()`, `setContext()`, `clearContext()` |

`SecurityContextHolder` is named "Holder" because **it holds the context**, not the context itself. A `SecurityContext` can be initialized empty. `Authentication` serves both as the data type describing an **unauthenticated** request passed into `AuthenticationManager` and as the data type describing an **authenticated** principal after success; distinguish them by origin and state.

### 1.2. Not ServletContext

`jakarta.servlet.ServletContext` is scoped to the entire web application, not to a user's identity. Spring Security's `SecurityContext`, by contrast, holds the authentication serving a single security processing flow. Placing the current user into a global `ServletContext` attribute is wrong: multiple users and requests share the servlet application, easily causing cross-request identity leakage.

## 2. Authentication Is the Core Information Inside SecurityContext

`org.springframework.security.core.Authentication` has these important methods:

~~~java
Object getPrincipal();
Object getCredentials();
Object getDetails();
String getName();
Collection<? extends GrantedAuthority> getAuthorities();
boolean isAuthenticated();
~~~

These are **illustrative API signatures**; they are not a class you need to create in your project.

### 2.1. Meaning of Each Component

- **Principal:** the object representing the identity: it may be a username string, `UserDetails`, `Jwt`, `OidcUser`, or a custom principal. **Do not cast to `UserDetails` by default**.
- **Credentials:** proof such as a password or token while still retained. After authentication, many providers/frameworks **erase credentials** to reduce secret exposure; do not expect to retrieve a raw password from `SecurityContext`.
- **Authorities:** the `GrantedAuthority` instances assigned to the principal by the system, such as `ROLE_READER` or `SCOPE_orders:read`. An authority only has meaning under the application policy; having a role does not imply permission to view every record.
- **Details:** auxiliary metadata about the authentication, sometimes containing request information. Do not treat IP, user-agent, or client-supplied details as standalone proof of identity.
- **getName():** the display name exposed by `Authentication`, often convenient for UI/audit, but **not guaranteed to be an immutable accountId**.
- **isAuthenticated():** an internal state flag on the token, **not sufficient as a "truly logged-in" check in all cases**; an anonymous token can return true.

### 2.2. Example of the Same Identity with Different Principals

~~~text
Form login:
  Authentication: UsernamePasswordAuthenticationToken
  principal:      UserDetails (or custom)
  name:           "linh"

JWT resource server:
  Authentication: JwtAuthenticationToken
  principal:      Jwt
  name:           may be the "sub" claim depending on configuration
  authorities:    e.g. SCOPE_orders:read

OIDC login:
  Authentication: OAuth2AuthenticationToken
  principal:      OidcUser
  name:           information per principal / name attribute
~~~

Therefore, code like `(User) authentication.getPrincipal()` easily throws a `ClassCastException` when switching login methods. For business data, there should be a safe mapping step from the external identity to an **internal accountId**. Do not use an email or arbitrary display name as the ownership key for an order.

### 2.3. Unauthenticated vs. Authenticated Authentication

An initial username/password request can be created as:

~~~java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, rawPassword);
Authentication verified = authenticationManager.authenticate(request);
~~~

This snippet is **illustrative only**, requiring the appropriate variables and dependencies. The `request` input is untrusted; `AuthenticationManager` and its providers must verify the password and account status. Only **when `authenticate` succeeds** is there a basis to place `verified` into the request's `SecurityContext` according to the appropriate flow.

**Never do the following from an unverified JSON request:**

~~~java
Authentication forged =
    UsernamePasswordAuthenticationToken.authenticated(
        inputUsername, null, userProvidedAuthorities);
SecurityContextHolder.getContext().setAuthentication(forged);
~~~

This is an **anti-pattern example**, not an implementation guide. It turns self-declared client data into "authenticated". The `authenticated(...)` factory should appear in verified framework/provider code or controlled tests/demos, not as a login shortcut.

## 3. How Do SecurityContext and SecurityContextHolder Work?

Reading the context:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();
~~~

`getContext()` usually returns a `SecurityContext` object (which may be empty), so **do not check `context != null` alone** to infer that the user is logged in. `getAuthentication()` may be null or an anonymous authentication.

Setting the context after a provider has authenticated successfully:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(context);
~~~

Here `verifiedAuthentication` is a result **already verified** by the framework/provider; the snippet cannot compile standalone without the surrounding call context. Using `createEmptyContext()` is recommended by Spring Security over mutating directly:

~~~java
SecurityContextHolder.getContext()
        .setAuthentication(verifiedAuthentication);
~~~

because a `SecurityContext` instance may be referenced/shared across certain persistence mechanisms; mutating a shared object easily causes **race conditions** or unintended modifications outside the intended scope.

### 3.1. Commonly Used Methods

| Method | Effect | When Needed |
|---|---|---|
| `getContext()` | Retrieves the context bound to the current holder | Reading principal/authorities |
| `createEmptyContext()` | Creates a new context with no authentication | Safely setting identity after authentication |
| `setContext(context)` | Assigns the current context | In auth code or controlled propagation |
| `clearContext()` | Removes the context from the current holder | Cleanup after unit tests, custom tasks, or processing outside filters |
| `getContextHolderStrategy()` | Retrieves the context management strategy | Specialized integration, when changing strategies |

In addition, modern versions provide deferred context APIs to support lazy loading; use them according to your version's documentation. Most business services do not need to call all of these methods directly.

### 3.2. Default Nature: ThreadLocal

In a standard Servlet stack, `SecurityContextHolder` defaults to **`MODE_THREADLOCAL`**. The context is bound to the **current execution thread**:

~~~text
Thread T1 handling Alice's request:
  SecurityContextHolder(T1) -> Authentication(Alice)

Thread T2 handling Bob's request:
  SecurityContextHolder(T2) -> Authentication(Bob)

Thread T3 with no context:
  SecurityContextHolder(T3) -> empty context
~~~

This is not a global `requestId -> user` map built by the app; Spring Security filters set up and clean up according to the request lifecycle. Threads can be reused from a pool for other requests, so **clearing the context is a critical security invariant**. If a worker thread retains the auth of a previous request, a subsequent request can see the wrong identity.

### 3.3. MODE_INHERITABLETHREADLOCAL and MODE_GLOBAL

Spring Security supports several strategies:

- **`MODE_THREADLOCAL` (default):** context per current thread, suitable for most Servlet applications.
- **`MODE_INHERITABLETHREADLOCAL`:** **newly created** child threads can inherit the context from the parent at creation time; **this does not mean it is automatically safe with thread pools** because workers are reused.
- **`MODE_GLOBAL`:** a single shared context across the JVM, which may fit some standalone desktop/test scenarios, **unsuitable for multi-user web apps**.
- **Custom `SecurityContextHolderStrategy`:** for special environments/integrations, requiring strict design and testing.

Do not change the global strategy just so `@Async` "can read the user". In a web application, passing high privileges from request A into a worker thread serving request B can cause severe authorization bugs. Use a clearly scoped propagation mechanism (Section 8).

## 4. How Identity Is Loaded and Cleared in a Servlet Request Lifecycle

A request arriving at a controller does not naturally carry an `Authentication`. It passes through **`FilterChainProxy`** and `SecurityFilterChain`, with the filters configured for that request. Conceptually:

~~~text
HTTP GET /orders
    |
    v
SecurityContextHolderFilter / context loading
    |
    v
Appropriate authentication mechanism
    |
    +--> session cookie -> restore context if present
    +--> Authorization: Basic ... -> verify per request
    +--> Authorization: Bearer ... -> verify token per request
    +--> no auth yet -> may set anonymous token
    |
    v
AuthorizationFilter / authorization checks
    |
    v
DispatcherServlet -> Controller -> Service
    |
    v
Filter chain finishes -> SecurityContextHolder is cleared
~~~

The actual filter order varies by version and configuration, so do not copy the diagram as a fixed filter list. What matters: **load** from a repository when needed, **set** authentication after verification, **save** if it should be used on subsequent requests, and **clear** at the proper lifecycle boundary.

### 4.1. SecurityContextHolderFilter vs. SecurityContextPersistenceFilter

In Spring Security 6, `SecurityContextHolderFilter` is the standard mechanism for **reading** the `SecurityContext` from `SecurityContextRepository` and placing it into the holder. It **does not automatically save every change by default**. If custom authentication creates a context itself and wants that context to persist for subsequent requests, the application must call `SecurityContextRepository.saveContext(...)` in the appropriate flow.

`SecurityContextPersistenceFilter` belongs to the older model, which automatically saved before the response was committed or the filter chain ended. An application **should not configure both filters simultaneously**. Spring Security has moved to an explicit-save model for Servlet security; check your version and the `requireExplicitSave` setting when upgrading older applications.

**Note:** framework-provided login mechanisms (such as form login and its corresponding filter) already include the path to save authentication according to configuration. This does not mean developers must call `saveContext` manually in every controller; issues usually arise when **writing a custom authentication flow**.

### 4.2. Clearing Differs from Logout and Session Invalidation

`SecurityContextHolder.clearContext()` only removes the context from the current execution's holder; it **does not mean** an authentication stored in `HttpSession` has been deleted, the session cookie has been invalidated, a JWT has been revoked, or the user has been logged out from the IdP.

For a real logout, the framework must run logout handlers/session invalidation, delete the context from the repository where appropriate, clear authentication, and perform any token/remember-me/CSRF actions according to policy. With stateless JWTs, there is no session to delete; TTL, revocation/token versioning, or introspection is needed if policy requires revocation before `exp`.

### 4.3. Do Not Store a Static Application-Wide Authentication

Wrong:

~~~java
static Authentication lastLoggedInUser;
~~~

If request A logs in and request B arrives later, the variable reflects **the most recent logged-in user across the entire JVM**, not request B's identity. Storing authentication in a singleton service field is also wrong:

~~~java
@Service
class UserService {
    private Authentication currentAuthentication; // wrong for multi-request
}
~~~

Both snippets are anti-patterns. The right way is to receive `Authentication` per request or read `SecurityContextHolder` in the appropriate scope; never hold it as mutable global state on a singleton bean.

## 5. SecurityContextRepository: Single Request or Multiple Requests?

`SecurityContextHolder` manages the context **currently in the execution flow**; `SecurityContextRepository` manages how the context is **restored and saved across Servlet boundaries** as configured.

| Repository | Storage Mechanism | Typical Scope of Use |
|---|---|---|
| `HttpSessionSecurityContextRepository` | Attaches context to `HttpSession` | Form login / session-based authentication |
| `RequestAttributeSecurityContextRepository` | Attaches context as an attribute on the **current request** | Preserves context across dispatches such as ERROR for the same request; does not persist across HTTP requests |
| `DelegatingSecurityContextRepository` | Saves/reads through multiple repositories in order | Spring Security 6 configuration commonly uses request attribute and session |
| `NullSecurityContextRepository` | Saves nothing | Stateless mode or mechanisms needing auth only within the request, depending on configuration |

In Spring Security 6, the default repository for many Servlet configurations is typically `DelegatingSecurityContextRepository` combining `RequestAttributeSecurityContextRepository` and `HttpSessionSecurityContextRepository`. However, **do not infer that an application has stateful sessions enabled** solely from knowing the default repository: `sessionCreationPolicy`, the authentication type, and custom security chains can alter this behavior.

### 5.1. How Can a Session-Based Login Request Progress?

~~~text
POST /login (valid credentials)
  -> AuthenticationManager verifies
  -> SecurityContext holds Authentication
  -> SecurityContextRepository saves appropriately to session
  -> Response includes session cookie (if session was created)

GET /profile (new request)
  -> Valid session cookie
  -> Repository looks up SecurityContext
  -> SecurityContextHolder of the new thread is loaded
  -> Controller knows the logged-in user
  -> End of request: holder is cleared, session may still exist
~~~

This mechanism does not guarantee the user is authorized for *every* profile; authorization and tenant/resource ownership must still be checked. A session ID is a credential that must be protected with HTTPS, cookie attributes, CSRF protection, and session fixation protection via the framework.

### 5.2. Does Stateless JWT Have a "SecurityContext"?

**Yes.** Stateless does not mean Spring Security skips `SecurityContext`. A resource server can validate a bearer JWT on every request:

~~~text
Authorization: Bearer <token>
    |
    v
BearerTokenAuthenticationFilter -> JwtAuthenticationProvider/Decoder
    |
    v
JwtAuthenticationToken (signature/issuer/exp/audience verified per config)
    |
    v
SecurityContextHolder of the current request
    |
    v
Authorization -> Controller
    |
    v
Request finishes, context is cleared, does not rely on a login session for identification
~~~

Specific JWT conditions must be configured properly. **An unexpired JWT does not guarantee the internal account has not been locked/deleted or that roles/tenant memberships are still accurate at the current moment**; revocation and permission synchronization policies must be designed separately.

Configuration snippet example for a stateless API:

~~~java
http
    .sessionManagement(s -> s.sessionCreationPolicy(
            SessionCreationPolicy.STATELESS))
    .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()));
~~~

This is a **Spring Security configuration snippet**, not a standalone program; it requires Spring Security OAuth2 resource server/JWT dependencies, imports, and appropriate issuer/JWK/decoder configuration. Merely setting `STATELESS` is not enough to verify bearer tokens.

## 6. Reading the Current Identity Properly

### 6.1. Retrieving via SecurityContextHolder

In a service on the **same thread** and in the proper scope:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication == null) {
    // No Authentication in the context yet.
} else {
    String name = authentication.getName();
}
~~~

The snippet above is **not sufficient to conclude the user is actually logged in**: `authentication` could be an anonymous token. Do not return the raw `Authentication` object, principal, or credentials in a JSON API without carefully considering sensitive data.

If you need to check whether the user is authenticated, prefer **letting Spring Security authorization handle it** via `.authenticated()`, `@PreAuthorize`, and appropriate policies. They understand anonymous semantics better than a hand-written `auth.isAuthenticated()` check.

### 6.2. An Illustrative Spring MVC Controller

~~~java
@RestController
class CurrentUserController {

    @GetMapping("/me")
    Map<String, Object> me(Authentication authentication) {
        if (authentication == null
                || authentication instanceof AnonymousAuthenticationToken) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        return Map.of(
                "name", authentication.getName(),
                "authorities", authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .toList()
        );
    }
}
~~~

This snippet is an **integration fragment**; it will not compile standalone without imports, Spring MVC configuration, and authorization setup. In a real application, `/me` is usually configured as `authenticated()` in the security chain and uses a DTO instead of `Map`, returning only fields allowed to be exposed. Do not use simple controller logic like this as a replacement for the framework's authorization mechanism when multiple `Authentication` types or a custom trust resolver are present.

### 6.3. Authentication, Principal, @AuthenticationPrincipal, @CurrentSecurityContext

Spring MVC offers several ways to access request information:

~~~java
@GetMapping("/hello")
String hello(Authentication authentication) {
    return "Hello " + authentication.getName();
}
~~~

~~~java
@GetMapping("/profile")
String profile(@AuthenticationPrincipal UserDetails user) {
    return user.getUsername();
}
~~~

~~~java
@GetMapping("/current")
String current(@CurrentSecurityContext(
        expression = "authentication.name") String username) {
    return username;
}
~~~

All three are **illustrative controller snippets**, requiring a protected endpoint and Spring imports. Not every authentication has `UserDetails`: for instance, `@AuthenticationPrincipal UserDetails` may not fit JWT/OIDC and could inject null. When only the display name is needed, an `Authentication` parameter is generally less coupled to the principal type; when JWT claims are needed, use `Jwt`/`JwtAuthenticationToken` with proper configuration.

The Servlet API also has `HttpServletRequest.getUserPrincipal()` and `getRemoteUser()`; in a Spring Security application, their values reflect the filter wrapper/configuration and are not unconditionally identical in type to `Authentication`'s principal. Check the actual mechanism when integrating legacy Servlet libraries.

### 6.4. If a Durable accountId Is Needed

`authentication.getName()` may be a username, email, IdP subject, or a custom name value. For order ownership, do:

~~~text
Authenticated Authentication
   -> trusted principal/issuer/subject
   -> verified identity mapping
   -> localAccountId (UUID)
   -> repository query by ownerAccountId + tenantId + permissions
~~~

Do not do:

~~~java
orderRepository.findByOwnerEmail(authentication.getName());
~~~

if the email can change, is unverified, or lacks per-tenant uniqueness. **Authentication identity** and **business identity** need a trustworthy server-side link. An authenticated principal does not automatically have access to all data with the same username or tenant.

## 7. The Anonymous Case: Why Can isAuthenticated() Be Misleading?

Spring Security includes `AnonymousAuthenticationFilter`, which, when configured accordingly, sets an `AnonymousAuthenticationToken` if the context does not yet have an `Authentication`. This token allows authorization to handle unauthenticated users consistently.

Trap:

~~~java
Authentication a =
        SecurityContextHolder.getContext().getAuthentication();

if (a != null && a.isAuthenticated()) {
    // Not guaranteed to be an actually logged-in user!
}
~~~

`AnonymousAuthenticationToken` normally returns `isAuthenticated() == true` by its token contract. Therefore, the check above is **not sufficient** to distinguish an anonymous user from a verified user. For endpoints requiring real login, use `authorizeHttpRequests(...).authenticated()` or Spring Security abstractions that understand anonymous tokens.

Configuration example:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

This is a **web configuration fragment**; it requires imports, bean/security dependencies, a login page/default flow, and appropriate CSRF/session configuration. `permitAll()` still allows public endpoints, while `authenticated()` does not accept anonymous users merely because the token has `isAuthenticated=true`.

### 7.1. Anonymous vs. Null Authentication

| State | `getAuthentication()` | Can It Be Treated as a Real Login? |
|---|---|---|
| Auth not processed yet and anonymous not set | `null` | No |
| Anonymous filter has placed token | `AnonymousAuthenticationToken` | No |
| Successful login via a valid provider | Authenticated `Authentication` | Yes, but authorization must still be checked |
| Valid JWT verified according to config | Typically `JwtAuthenticationToken` | Yes within the scope of token/claims and local policy |
| A custom filter constructs an authenticated token from unverified raw input | May have a token with `isAuthenticated=true` | **Untrusted; vulnerability** |

`SecurityContextHolder` is a **mechanism for conveying an authentication decision**, not standalone proof that the decision is valid. Code that constructs authentications or validates tokens must preserve the trust boundary.

## 8. Asynchronous Tasks, Thread Pools, and Propagation

### 8.1. Context Does Not Automatically Follow Every Thread

By default, `SecurityContextHolder` uses `ThreadLocal`. Therefore:

~~~text
HTTP request thread T1:
  Authentication = Alice

new Thread(...) T2:
  Authentication = null (under default MODE_THREADLOCAL)

@Async / Executor T3:
  Authentication may be null or wrong if code reuses context improperly
~~~

Do not "fix" this with a global variable or by letting every background task run with Alice's privileges. Instead:

- **Tasks that only need accountId:** pass a minimal verified identifier/DTO when submitting the job, and have the job re-check the required permissions under policy.
- **Tasks requiring method security in the proper context:** use `DelegatingSecurityContextRunnable` or `DelegatingSecurityContextExecutor`/`DelegatingSecurityContextAsyncTaskExecutor` with a clear scope.
- **System scheduled jobs:** do not borrow the identity of the last request by default; if a separate service identity is needed, define a service principal with least privilege.
- **Reactive WebFlux:** context propagation differs, typically using Reactor Context and `ReactiveSecurityContextHolder`; do not mechanically apply Servlet ThreadLocal.

### 8.2. What Does DelegatingSecurityContextRunnable Solve?

Integration snippet example:

~~~java
SecurityContext snapshot = SecurityContextHolder.getContext();
Runnable work = () -> protectedService.perform();

Runnable wrapped =
        new DelegatingSecurityContextRunnable(work, snapshot);
executor.execute(wrapped);
~~~

This is an **integration snippet**, not standalone compilable; `protectedService` and `executor` must exist. The wrapper sets the context for the delegate during execution and clears/restores the context per its implementation. However, keeping a **mutable SecurityContext reference** can be risky if another request modifies it; for long-running jobs, pass minimal data or create a controlled context snapshot.

### 8.3. Avoid MODE_INHERITABLETHREADLOCAL for Web Thread Pools

`MODE_INHERITABLETHREADLOCAL` only inherits when a **child thread is created**; it does not accurately synchronize context each time a pooled thread picks up a job. Worker pools can outlive many requests, so without safe context cleanup/encapsulation, Bob's job could see Alice. This is why `DelegatingSecurityContext...` wrappers are designed to set and clear identity **per task**.

For `@Async`, use an executor wrapped with `DelegatingSecurityContextAsyncTaskExecutor` per the relevant documentation; also determine whether a task running after the request finishes should still be allowed to use the user's privileges. Permissions at submission time are not necessarily still valid at execution time.

## 9. Runnable Example: Java 17 + Spring Security Core, No Server Needed

This example focuses on what can be verified outside a Servlet container:

1. Create an empty `SecurityContext`.
2. Place a **simulated authenticated** `Authentication` onto the main thread's holder.
3. A plain child thread **does not see** the principal due to ThreadLocal.
4. `DelegatingSecurityContextRunnable` lets the child thread see the principal within the task's scope.
5. `clearContext()` clears the authentication from the main thread's holder.

**This is a context-propagation demo**, not a valid login example. The program intentionally builds an `authenticated(...)` token from static data solely to simulate post-verification state. Never construct such a token from HTTP input that has not gone through `AuthenticationManager` in a real application.

### 9.1. Project Structure

~~~text
security-context-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/SecurityContextDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'security-context-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.3.8'
}

application {
    mainClass = 'example.SecurityContextDemo'
}
~~~

Requires JDK 17+, a compatible Gradle version, and the ability to download libraries from Maven Central on the first run. In a Spring Boot project, dependencies and versions are usually managed by starters/BOM. This example uses only the core API, without running servlet filters, HTTP sessions, or a JWT decoder.

### 9.2. Complete Java Code

Create `src/main/java/example/SecurityContextDemo.java`:

~~~java
package example;

import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public final class SecurityContextDemo {

    public static void main(String[] args) throws InterruptedException {
        // Create a simulated token for learning only; DO NOT do this
        // from HTTP input before authenticating with a provider.
        Authentication demoAuthenticated =
                UsernamePasswordAuthenticationToken.authenticated(
                        "linh",
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_READER")));

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(demoAuthenticated);
        SecurityContextHolder.setContext(context);

        Authentication current =
                SecurityContextHolder.getContext().getAuthentication();
        System.out.println("main user -> " + current.getName());
        System.out.println("main authenticated -> "
                + current.isAuthenticated());
        System.out.println("main authority -> "
                + current.getAuthorities().iterator().next()
                    .getAuthority());

        // Default MODE_THREADLOCAL: child thread does not inherit automatically.
        Thread plainChild = new Thread(() -> {
            Authentication childAuth =
                    SecurityContextHolder.getContext()
                        .getAuthentication();
            System.out.println("plain child auth is null -> "
                    + (childAuth == null));
        });
        plainChild.start();
        plainChild.join();

        // Task context is specified explicitly; do not use global mode.
        SecurityContext taskContext =
                SecurityContextHolder.createEmptyContext();
        taskContext.setAuthentication(demoAuthenticated);

        Runnable task = () -> {
            Authentication taskAuth =
                    SecurityContextHolder.getContext()
                        .getAuthentication();
            System.out.println("delegated child user -> "
                    + taskAuth.getName());
        };

        Thread delegatedChild = new Thread(
                new DelegatingSecurityContextRunnable(
                        task, taskContext));
        delegatedChild.start();
        delegatedChild.join();

        // When the child task finishes, the main thread keeps its own context.
        System.out.println("main after child -> "
                + SecurityContextHolder.getContext()
                    .getAuthentication().getName());

        // Demo runs outside a Servlet filter, so manual cleanup is required.
        SecurityContextHolder.clearContext();
        System.out.println("main after clear is null -> "
                + (SecurityContextHolder.getContext()
                        .getAuthentication() == null));
    }
}
~~~

### 9.3. How to Run and Expected Output

In the `security-context-demo` directory, if a compatible Gradle Wrapper is present:

~~~bash
./gradlew run
~~~

If no wrapper is present but a compatible Gradle installation is available:

~~~bash
gradle run
~~~

On Windows PowerShell with the wrapper, you typically run `.\gradlew.bat run`.

Output of the **`System.out.println` statements** in the program, ignoring Gradle logs:

~~~text
main user -> linh
main authenticated -> true
main authority -> ROLE_READER
plain child auth is null -> true
delegated child user -> linh
main after child -> linh
main after clear is null -> true
~~~

Explanation in order:

1. The main thread binds a context containing the simulated token and reads `linh`/`ROLE_READER`.
2. A normal child thread does not see the main context under the default `MODE_THREADLOCAL`, so `childAuth == null`.
3. `DelegatingSecurityContextRunnable` temporarily sets the task context for the delegated thread, so the task prints `linh`; the wrapper cleans up/restores the context after the task.
4. The main thread does not lose its context when the child finishes because the holder is per-thread.
5. `clearContext` causes the main thread to get an empty context on the next read.

**Limitations:** the demo does not prove valid credentials, does not check order access permissions, does not save a session, and does not connect an HttpServletRequest. In production, `Authentication` must come from a verified filter/provider; the context should be managed by the filter chain rather than creating an authenticated token from a user-supplied username.

## 10. When Setting Authentication Manually: setContext Alone Does Not Persist the Session

Some applications write a custom login filter or controller instead of using `formLogin()`, OAuth2 login, or standard mechanisms. After verifying credentials with `AuthenticationManager`:

~~~java
Authentication verified = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                loginName, rawPassword));

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// If authentication needs to be restored on subsequent HTTP requests:
securityContextRepository.saveContext(
        context, servletRequest, servletResponse);
~~~

This is a **Servlet integration snippet**, not a standalone Java program: `authenticationManager`, `securityContextRepository`, request/response, and inputs must be declared from the actual flow. To avoid mistakes, keep in mind:

1. **Authenticate first:** only use `verified` after `AuthenticationManager.authenticate` has actually succeeded.
2. **Create a new context:** do not mutate a session context that might be shared across requests.
3. **Set and save are different:** `setContext` affects the current execution; `saveContext` gives the repository an opportunity to store the context for subsequent requests according to policy.
4. **Save before the response commits** when required by the session/cookie mechanism; do not wait until the controller has finished sending the body to save.
5. **Manage login/session properly:** when writing custom login, handle session fixation, concurrent sessions, CSRF, remember-me, logout, failure handlers, authentication events, and auditing; using standard filters is better whenever feasible.
6. **Choose the right repository:** `NullSecurityContextRepository` intentionally saves no session; `RequestAttributeSecurityContextRepository` only helps within the same request/dispatch, not for "persisting login".
7. **Do not expose raw credentials:** providers/managers and filters handle credential erasure by design; do not put raw passwords into sessions or logs.

When authentication fails, do not allow context from a previous request to remain on a reused thread. In standard request flows, the filter chain cleans up the context in its lifecycle; custom code running outside that lifecycle must have proper `finally` cleanup.

### 10.1. What Is Needed to Keep a Login Across Multiple Requests?

With standard session login:

- An appropriate security chain and a `SecurityContextRepository` capable of saving the context to `HttpSession`.
- Successful authentication saved **at the right time**.
- The client receives and sends back a valid session cookie.
- The session has not expired, been logged out, or been revoked.
- Browser/proxy configuration does not block the required cookie.
- The login session is protected with HTTPS, cookie flags, CSRF protection, session fixation protection, and appropriate policies.

If the server uses the `STATELESS` session policy, you need a per-request authentication mechanism (such as JWT) rather than calling `setContext` once and expecting the next request to still know the user.

## 11. Security When Using "the Current Request's Identity"

### 11.1. Being Authenticated Does Not Mean Access to All Data Is Allowed

A controller having a valid `Authentication` proves the framework recognized the principal according to the configured mechanism. However, access to a specific order also depends on:

- Required permissions/roles/scopes for the action.
- **Owner** relationship or membership between the account and the resource.
- The **tenant** being operated on and permissions within that tenant.
- Whether account/membership status has changed since the token or session was issued.
- Step-up/MFA policy for sensitive actions.

Example query that should bind both ownership and tenant:

~~~java
Optional<Order> findByIdAndOwnerAccountIdAndTenantId(
        UUID orderId, UUID ownerAccountId, UUID tenantId);
~~~

This is an **illustrative repository signature** in an application with `Order`, not standalone code. The source of `ownerAccountId`/`tenantId` must be determined and verified from the principal and domain authorization, without trusting an arbitrary `accountId` sent by the client.

### 11.2. Context Can Become Stale After Permission Changes

If authorities were loaded into the authentication at 08:00, but the user's role is revoked at 08:05, the existing session/JWT may still carry the old list until refresh/revocation. `SecurityContext` does not automatically poll the DB to update all permissions in real time.

The application must choose among:

- Refreshing authentication/authorities per request or at sensitive operations.
- Session invalidation, token versioning/revocation, reasonable TTLs.
- Direct domain policy checks for ownership/membership when immediate decisions are needed.
- Auditing privileged operations, avoiding sole reliance on a stale `ROLE_ADMIN`.

### 11.3. Do Not Misuse getDetails/getCredentials for Logging

Do not return the entire `Authentication` in a response or dump the context into logs. These objects can contain encoded passwords, claims, request details, principal attributes, or tokens, depending on the provider. Output only explicitly filtered information:

~~~text
requestId:     <correlation ID>
actorAccountId:<stable internal ID, if verified>
authMethod:    <form / bearer / oidc, classification>
action:        <orders.read>
decision:      <ALLOW / DENY>
~~~

Do not log the `Authorization` header, session cookie, password, reset token, raw JWT, or full authorities/claims without a valid need and appropriate access controls.

## 12. Common Issues and How to Diagnose Them

| Symptom | Possible Cause | How to Check / Fix |
|---|---|---|
| `SecurityContextHolder.getContext().getAuthentication() == null` in a service | Unauthenticated request, filter does not cover the URL, code runs before the auth filter or outside a request | Check security chain/matcher/filter order and entry point |
| Controller sees `anonymousUser` | No real login; anonymous filter placed the token | Protect the endpoint with `authenticated()`; do not rely on `isAuthenticated` alone |
| After POST login, the next GET loses the user | Only called `setContext`; forgot `saveContext` in custom flow, session cookie did not arrive, or stateless repo | Check `SecurityContextRepository`, session policy, cookie, and save timing |
| Request A sees user B | Stored global/static auth or forgot to clear a custom thread | Remove singleton/global state; clean ThreadLocal per task/request |
| `@Async` reads null auth | ThreadLocal does not propagate to executor automatically | Use an executor wrapper or pass a minimal accountId/DTO |
| Thread pool retains previous job's user | Wrong InheritableThreadLocal/propagation usage, missing cleanup | Use `DelegatingSecurityContext...` per task and clean up |
| Casting principal to `UserDetails` fails | JWT/OIDC/custom principal has a different type | Use the appropriate type or an identity abstraction |
| `authentication.getName()` is an email instead of a UUID | Name is determined by the provider/principal | Map to a verified internal accountId |
| `clearContext` does not log out the session | Only cleared the thread holder; session repository still holds auth | Use the official logout flow and invalidate/revoke |
| Stateless JWT API has "no session yet has authentication" | Bearer token is verified on each request | This is expected behavior; distinguish request context from session |
| Subsequent requests still see old roles after role revocation | Stale authentication cache/session/token | Cache invalidation, session/token revocation, or domain check |
| `SecurityContext` exists but has no user | Empty context created by default | Check `getAuthentication()` and trust resolver |
| Manually creating an authenticated token lets login succeed with a wrong password | Custom code bypassed manager | Never create trusted tokens from input; always go through provider |
| Context lost on ERROR dispatch | Repository handles only certain dispatches, context already cleared | Check `RequestAttributeSecurityContextRepository` and filter dispatches |
| Multiple security chains | Selected request matcher/chain differs from expectation | Check URL/method/ordering, not just a single filterChain |

### 12.1. Debugging in the Right Order

1. **Which URL/method is being handled?** Was the right `SecurityFilterChain` selected?
2. **What credential does the request carry?** Session cookie, Basic header, bearer token, or nothing?
3. **Which filter/provider verifies it?** Is there a properly configured AuthenticationManager/decoder?
4. **Which SecurityContextRepository is used?** Session, or only request attribute/null?
5. **Which thread is the controller running on?** Is it via `@Async`, an executor, custom scheduling, or another dispatch?
6. **Is auth null, anonymous, or which real type?** Print **class + filtered status**, without dumping passwords or claims.
7. **Does it need to persist to the next request?** If so, check explicit save/session cookie.
8. **Is there a permission/tenant conflict?** Valid identity alone is not enough; check authorization/domain.
9. **Was it cleared at the end of the request?** Never let a principal leak to the next worker or request.

### 12.2. Misconceptions to Eliminate

**Misconception 1:** "`SecurityContextHolder` is the session."  
**Fact:** The holder keeps the context in the current execution; a session is only *one of* the ways to store context across requests.

**Misconception 2:** "Having a `SecurityContext` means logged in."  
**Fact:** The context can be empty; and an anonymous token does not represent a logged-in user.

**Misconception 3:** "`isAuthenticated()==true` always means a real user."  
**Fact:** `AnonymousAuthenticationToken` can return true; use the framework's `authenticated()`/trust resolver.

**Misconception 4:** "Calling `SecurityContextHolder.setContext` handles all subsequent requests."  
**Fact:** A repository/session or per-request bearer authentication is needed; custom login usually requires an explicit save.

**Misconception 5:** "`ThreadLocal` guarantees the context follows every async task."  
**Fact:** The context is bound to a thread and does not automatically follow pooled tasks. Propagate the proper context or pass the needed domain ID.

**Misconception 6:** "`Authentication.getName()` is the system's accountId."  
**Fact:** It is determined by the principal/provider; it may be an email, username, or OIDC subject.

**Misconception 7:** "`SecurityContextHolder.clearContext()` deletes all JWTs/sessions."  
**Fact:** It only cleans the holder in the current execution; logout/revocation are separate mechanisms.

**Misconception 8:** "Using a custom SecurityContext in a filter lets you skip session fixation and CSRF."  
**Fact:** Writing custom login requires protecting the full security lifecycle; leverage standard filters whenever possible.

## 13. Test Matrix

| Scenario | Expected Result |
|---|---|
| New empty context | `getAuthentication()==null` |
| Context containing verified auth | `getName/getAuthorities` match provider |
| Anonymous filter runs for public request | Anonymous is not treated as a real logged-in user |
| `.authenticated()` on protected endpoint | Anonymous is rejected / routed through entry point per config |
| Valid form login + session repository | Subsequent request has valid context while session cookie remains |
| Invalid form login | No authenticated principal attached |
| Custom login calls only setContext without save | In explicit-save flow, subsequent request does not automatically restore context |
| Custom login sets and saves with proper repository | Subsequent request restores when session policy permits |
| Valid stateless bearer JWT | Authentication created per request, no server session required |
| Bearer JWT with invalid signature/audience/expired | No successful authenticated context granted |
| Replacing `ThreadLocal` with global in web app | Test warns of cross-user leak risk; never use in production |
| Plain new Thread | Does not inherit context by default |
| `DelegatingSecurityContextRunnable` | Has correct principal inside task and cleans up afterward |
| Executor pool receives tasks from Alice/Bob sequentially | No context leakage between tasks |
| `@AuthenticationPrincipal UserDetails` with Jwt auth | Test different principal types; do not assume cast succeeds |
| User changes name/email | accountId mapping remains stable |
| User's role revoked while session is alive | Ensure domain/authorization policy reflects change within SLA |
| Session logout | Session invalidation and context repository do not restore old user |
| ERROR dispatch | Context preserved or restricted properly per repository/config |
| Multi-tenant resource | Cross-tenant access blocked even with valid principal |
| Request cookie traversing proxy | Appropriate Secure/SameSite/Path cookie flags, no session leak |
| Concurrent requests sharing session | Shared `SecurityContext` not mutated so one user affects another |

### 13.1. Self-Review Questions

**Question 1.** How does `SecurityContext` differ from `SecurityContextHolder`?  
**Answer:** Context is the container holding Authentication; Holder manages how the context of the current execution is stored and retrieved.

**Question 2.** Does `getContext() != null` prove the user is logged in?  
**Answer:** No. An empty context may be returned.

**Question 3.** Is `authentication.isAuthenticated()==true` enough to treat the caller as a real logged-in user?  
**Answer:** No. Anonymous authentication is an important exception; use the appropriate authorization abstraction.

**Question 4.** A custom controller just authenticated successfully and called `setContext`, but the next request does not see the user. Why?  
**Answer:** The holder only keeps the current context; `SecurityContextRepository.saveContext` and an appropriate session/cookie mechanism are needed to persist across requests, or per-request re-authentication if stateless.

**Question 5.** Why should new code call `createEmptyContext()`?  
**Answer:** To avoid mutating a context that may be referenced/shared, reducing race conditions.

**Question 6.** Why can't `@Async` see the user from the controller?  
**Answer:** By default the holder uses ThreadLocal, and the executor runs on a different thread. Proper propagation or passing a trusted accountId is needed.

**Question 7.** With a stateless JWT resource server, is `SecurityContext` still needed?  
**Answer:** Yes; authentication is typically verified from the token and attached to the context for that request. Persisting a session is not required.

**Question 8.** Does `clearContext()` automatically revoke a JWT?  
**Answer:** No. JWT/session revocation is a separate concern.

**Question 9.** Is `getName()` an order ownership key?  
**Answer:** Not by default. Use identity mapping to an internal accountId and resource-level authorization.

**Question 10.** Is it safe to manually construct `authenticated(...)` from a username and roles sent by the client?  
**Answer:** No; that is an authentication bypass. The framework/provider must verify proof before creating a trusted principal.

## 14. Adoption Checklist

- [ ] Clearly distinguish the roles of `Authentication`, `SecurityContext`, and `SecurityContextHolder`.
- [ ] Never confuse an empty or anonymous context with an authenticated user.
- [ ] Use `SecurityContextHolder` within the proper request/thread scope; never store auth in singleton/static state.
- [ ] Keep the default `MODE_THREADLOCAL` for Servlet web apps unless there is a verified integration reason.
- [ ] When creating a new context after authentication, use `createEmptyContext` and only set a **verified Authentication**.
- [ ] Choose the right `SecurityContextRepository` and understand the differences between request attribute, session, and null.
- [ ] If custom login needs session persistence, call `saveContext` at the right moment in an explicit-save flow.
- [ ] Avoid manually interfering with the filter chain/cleanup when standard Spring Security mechanisms already handle it.
- [ ] Configure endpoint authorization with `authenticated()`, roles/scopes, and check domain ownership.
- [ ] Use `Authentication`/`@AuthenticationPrincipal`/`@CurrentSecurityContext` matching the principal type of each login method.
- [ ] When a business user is needed, map the principal to a trusted accountId and tenant context.
- [ ] For `@Async`/executors, propagate a scoped context or pass minimal data, never a global user.
- [ ] Protect session cookies, CSRF, session fixation, logout, and token revocation according to the authentication method.
- [ ] Do not return raw Authentication/claims/hashes/credentials in APIs or logs.
- [ ] Test null, anonymous, session, JWT, async, logout, stale roles, and multi-tenant boundaries.
- [ ] Check the filters/repositories and APIs of the running Spring Security version before modifying custom flows.

**Remember:** `SecurityContext` is where the **Authentication currently recognized by the framework** lives; `SecurityContextHolder` delivers that context to the code handling the request (usually via `ThreadLocal`). Loading it properly at the start of a request, setting it only after verification, saving it if it must persist across requests, checking permissions at the appropriate layers, and clearing the context upon completion are inseparable principles.

### Official Documentation

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): roles of `SecurityContextHolder`, `SecurityContext`, `Authentication`, and accessing the principal.
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html): `SecurityContextRepository`, session/request attributes, and persistence filters.
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContextHolderFilter`, `requireExplicitSave`, and explicit save in Spring Security 6.
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html): `DelegatingSecurityContextRunnable`, executor wrappers, and context propagation.
- [Spring Security — SecurityContextHolder JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/SecurityContextHolder.html): `getContext`, `createEmptyContext`, `setContext`, `clearContext`, and strategies.
- [Spring Security — Anonymous Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html): `AnonymousAuthenticationToken`, anonymous principal, and authorization.
