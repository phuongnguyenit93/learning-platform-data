# Never Treat a Client-Supplied User ID as Proof of Identity

## 1. The Problem: A Caller Can Claim to Be Anyone

When calling an API, **the client controls everything it sends**: URL parameters, query strings, JSON bodies, form fields, many HTTP headers, and values stored locally by the browser. Therefore, a field like `userId=u-alice` is **only input data**, not proof that the sender is actually Alice.

A common mistake is writing an API like:

```http
GET /api/users/u-alice/documents
```

and directly using `u-alice` to query documents:

```java
// WRONG example: illustrative snippet, do not put in a real application.
@GetMapping("/api/users/{userId}/documents")
public List<Document> list(@PathVariable String userId) {
    return repository.findByOwnerUserId(userId);
}
```

If Alice changes the URL to `/api/users/u-bob/documents` and the server returns Bob's data, the application has an **object-level authorization** flaw (Broken Object Level Authorization, **BOLA**; also commonly called IDOR – Insecure Direct Object Reference). Changing sequential numbers to long UUIDs, hiding the user ID in UI buttons, or validating in JavaScript **does not solve authorization**: a caller can modify requests using DevTools, `curl`, or any HTTP client.

Security principle:

> **The identity of the actor performing an action must come from authentication verified by the server.** Any user ID or resource ID supplied by the client must only be treated as the **target/object the client wants to act on**, and permissions must be checked against that specific object.

Distinguish three concepts:

| Concept | Question to answer | Proper source of truth |
| --- | --- | --- |
| **Caller identity (actor/caller)** | "Who is making the request?" | `Authentication`/principal created by Spring Security after the authentication mechanism has verified it |
| **Resource identifier (target/resource ID)** | "Which object does the caller want to view/edit?" | May come from URL, query, or body; must be treated as untrusted input until checked |
| **Authorization decision** | "Is the actor permitted to perform the action on the target?" | Business policy over the record, tenant, owner, role, state, and trusted server-side attributes |

A user may be allowed to **specify someone else's ID**, such as an administrator opening a customer profile for support. In that case, the ID in the URL is still the **target of access**, and does not turn the caller into that customer. The server must verify administrative privileges and management scope before returning data.

## 2. Where Can an Attacker Spoof a User ID?

All of the following locations **are controlled by the client**:

```http
GET /api/orders?userId=u-bob
X-User-Id: u-bob
Cookie: userId=u-bob
```

```json
{
  "userId": "u-bob",
  "documentId": "doc-982",
  "newTitle": "Update"
}
```

In a browser, client code might also store:

```javascript
// Value is only stored by the browser and can be modified arbitrarily.
localStorage.setItem("userId", "u-bob");
```

These fields can be useful for **selecting a resource**, but they cannot replace authentication. Hiding an "Edit someone else's item" button in the UI, using `hidden` inputs, disabling form fields, storing a user ID in React state, or Base64-encoding it does not turn input data into proof of identity.

**Distinguish this from real authentication tokens:** access tokens, session cookies, or assertions sent by the client also travel over the network, but Spring Security (or a trusted upstream authentication system) must **verify their validity and security bindings** before creating an `Authentication`. An arbitrary `userId` string in a cookie is completely different from a server-managed random session ID or a JWT whose signature, issuer/audience/expiry have been verified.

### BOLA Attack Example

Suppose Alice has her own valid token. The API receives:

```http
GET /api/invoices/invoice-bob-77
Authorization: Bearer <valid-token-of-Alice>
```

If the server only checks "is the token valid" and then loads `invoice-bob-77` by ID, Alice will see Bob's invoice. **Successful authentication does not mean authorization on every resource.** The API must check whether this invoice belongs to Alice, belongs to an organization Alice is in, or has been legitimately shared with Alice.

This is why OWASP ranks **Broken Object Level Authorization** as a critical API risk category: permissions must be checked in every function that handles a client-supplied object ID, not just at login time.

## 3. Obtaining Trusted Identity from Spring Security

In a Servlet application using Spring Security, after authentication succeeds, information about the current user resides in the `Authentication` inside `SecurityContext`. Spring MVC can inject this object as a controller method parameter:

```java
@GetMapping("/api/me")
public String currentUsername(Authentication authentication) {
    return authentication.getName();
}
```

**This snippet illustrates a single controller method** in an application with Spring Security enabled, not a standalone program. `authentication.getName()` retrieves the name bound to the request by the authentication mechanism rather than reading `request.getParameter("userId")`.

An alternative when the application uses `UserDetails` as the principal:

```java
@GetMapping("/api/me")
public String currentUsername(
        @AuthenticationPrincipal UserDetails principal) {
    return principal.getUsername();
}
```

In HTTP Basic examples, the principal is usually `UserDetails`. In OAuth2/JWT, the principal type can be `Jwt`, `JwtAuthenticationToken`, or another type depending on configuration; do not cast blindly to `UserDetails` across all mechanisms. Once authenticated at the Security layer, business code should look up a **stable user identifier** from the server-stored account or verified identity. Usernames and emails can change, so they are usually not ideal as long-lived immutable keys.

**Never construct an `Authentication` from a client-sent field to "simulate login":**

```java
// WRONG: grants identity from a client-asserted string.
String claimedUser = request.getHeader("X-User-Id");
// Never treat claimedUser as an authenticated principal!
```

`SecurityContextHolder` is trustworthy within the request pipeline **when** the application configures its filters properly and uses trusted authentication sources. If a developer manually injects a fake principal or misconfigures proxy trust, that guarantee is lost. Background threads, async tasks, and message consumers must also propagate identity/authorization explicitly rather than assuming another request's ThreadLocal is present.

### When Using JWT or OIDC

In an application configured as an OAuth2 Resource Server, a JWT may be used as the basis for identity **only after** the library validates its signature, expiration, issuer, audience (when required by the application), and design constraints. For a valid token, `sub` can serve as the principal ID assigned by the issuer.

However:

- Never merely Base64-decode a JWT payload and trust `sub`: an unverified payload can be forged.
- Never trust a client-sent `X-User-Id` header as authentication. Only trust identity headers injected by a trusted proxy/gateway **after** authentication, and ensure clients cannot bypass the gateway or spoof that header.
- When multiple issuers can issue the same `sub`, user identity typically needs **issuer + subject** combined or mapping to an internal user ID.
- `sub` identifies who is calling; it still **does not grant permission** to read/edit any resource ID.

## 4. Spring Boot Example: Always Resolve Permissions from the Authenticated User

We will build a document-reading API. Alice owns `doc-a`; Bob owns `doc-b`. The client may specify `documentId` in the URL, but cannot choose "which user it is". The server identifies the actor via `Authentication` and checks ownership against trusted data.

**Project:** Java 17+, Spring Boot 3.x, Spring Security 6.x (Servlet). Generate a project via Spring Initializr with **Spring Web** and **Spring Security** dependencies; select Gradle. Place the entire program below in:

```text
src/main/java/demo/identity/TrustedIdentityApplication.java
```

This example **runs inside a Spring Boot/Security project with the dependencies listed above**. It cannot be compiled with plain `javac TrustedIdentityApplication.java` without Spring/Jackson libraries on the classpath. The example uses in-memory accounts and data for easy testing, not a production storage design.

```java
package demo.identity;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class TrustedIdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(TrustedIdentityApplication.class, args);
    }

    // Username is only used as the account lookup key in this demo.
    // userId is a stable server-managed ID.
    public record UserAccount(String username, String userId) {}

    // Server-stored data; client cannot alter ownerUserId.
    public record StoredDocument(
        String id,
        String ownerUserId,
        String title
    ) {}

    // Returns only fields the client is allowed to view.
    public record DocumentView(String id, String title) {}

    static final class DataStore {
        private final Map<String, UserAccount> accounts = Map.of(
            "alice", new UserAccount("alice", "u-alice"),
            "bob", new UserAccount("bob", "u-bob")
        );

        private final Map<String, StoredDocument> documents = Map.of(
            "doc-a",
            new StoredDocument("doc-a", "u-alice", "Alice's notebook"),
            "doc-b",
            new StoredDocument("doc-b", "u-bob", "Bob's notebook")
        );

        // Authenticated username -> server-controlled account.
        UserAccount currentUser(Authentication authentication) {
            if (authentication == null) {
                return null;
            }
            return accounts.get(authentication.getName());
        }

        List<DocumentView> visibleDocuments(UserAccount caller) {
            return documents.values().stream()
                .filter(doc ->
                    doc.ownerUserId().equals(caller.userId())
                )
                .sorted(Comparator.comparing(StoredDocument::id))
                .map(doc -> new DocumentView(doc.id(), doc.title()))
                .toList();
        }

        DocumentView visibleDocument(
                UserAccount caller,
                String documentId) {

            StoredDocument doc = documents.get(documentId);

            if (doc == null
                    || !doc.ownerUserId().equals(caller.userId())) {
                return null;
            }
            return new DocumentView(doc.id(), doc.title());
        }
    }

    @Bean
    DataStore dataStore() {
        return new DataStore();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("alice123"))
                .roles("USER")
                .build(),
            User.withUsername("bob")
                .password(encoder.encode("bob123"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/**")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @RestController
    static final class ApiController {
        private final DataStore store;

        ApiController(DataStore store) {
            this.store = store;
        }

        @GetMapping("/api/me")
        public ResponseEntity<?> me(Authentication authentication) {
            UserAccount caller = store.currentUser(authentication);
            if (caller == null) {
                return ResponseEntity
                    .status(HttpStatus.FORBIDDEN).build();
            }

            return ResponseEntity.ok(
                Map.of(
                    "userId", caller.userId(),
                    "username", caller.username()
                )
            );
        }

        @GetMapping("/api/documents")
        public ResponseEntity<?> list(Authentication authentication) {
            UserAccount caller = store.currentUser(authentication);
            if (caller == null) {
                return ResponseEntity
                    .status(HttpStatus.FORBIDDEN).build();
            }

            return ResponseEntity.ok(
                store.visibleDocuments(caller)
            );
        }

        @GetMapping("/api/documents/{documentId}")
        public ResponseEntity<?> getOne(
                @PathVariable String documentId,
                Authentication authentication) {

            UserAccount caller = store.currentUser(authentication);
            if (caller == null) {
                return ResponseEntity
                    .status(HttpStatus.FORBIDDEN).build();
            }

            DocumentView visible =
                store.visibleDocument(caller, documentId);

            if (visible == null) {
                // Identical to when the ID does not exist:
                // does not disclose another user's document.
                return ResponseEntity.notFound().build();
            }
            return ResponseEntity.ok(visible);
        }
    }
}
```

### Design Explanation

**Step 1 — authentication:** `SecurityFilterChain` uses HTTP Basic for GET requests under `/api/**`. Unauthenticated callers are prompted for credentials; Spring Security returns 401 with a Basic challenge per configuration and HTTP context. `SessionCreationPolicy.STATELESS` avoids HTTP session state for this read-only demo. Other HTTP methods are rejected by the `denyAll()` fallback; default CSRF protection remains enabled and may affect write methods if added later.

**Step 2 — resolving the actor:** In the controller, the `Authentication authentication` parameter comes from the context populated by Spring Security. `DataStore.currentUser(...)` maps the authenticated username to a server-managed `UserAccount`. The IDs `u-alice` and `u-bob` **are never taken from the URL/body/header**. If an authenticated account has no internal mapping, the endpoint rejects with 403 rather than creating an account from a client-supplied ID.

**Step 3 — checking permissions on the resource:** `visibleDocument(...)` loads the record for the client-requested `documentId`, then checks the record's `ownerUserId` against `caller.userId()`. This check matters more than authenticating the request alone. A request carrying Alice's valid Basic credentials is still rejected if it asks for Bob's document.

**Step 4 — restricting returned fields:** `DocumentView` exposes only `id` and `title`, avoiding returning internal fields like `ownerUserId` or unnecessary sensitive properties. Checking permissions in the controller/service and filtering JSON fields solve **two separate problems**: whether the object can be accessed and which properties may be seen.

**Step 5 — consistent 404 behavior:** Both when a document does not exist **and** when the caller lacks permission to view it, the sample API returns 404. This reduces disclosure of whether an ID actually exists. Another product may use 403 for missing permissions, provided it stays consistent with the API contract and information-disclosure policy. Never treat "hiding with 404" as a substitute for authorization checks: the real policy still lies in comparing ownership server-side.

### Running the Example

Inside the project directory with the Gradle Wrapper:

```bash
./gradlew bootRun
# PowerShell on Windows:
# .\gradlew.bat bootRun
```

On PowerShell, `curl` may be an alias for `Invoke-WebRequest`; use `curl.exe` for the syntax below. The following examples assume the app is listening on `localhost:8080` on the default port.

```bash
# 1. No credentials provided
curl -i http://localhost:8080/api/me

# 2. Alice inspects server-determined identity
curl -i -u alice:alice123 http://localhost:8080/api/me

# 3. Alice views her own document
curl -i -u alice:alice123 http://localhost:8080/api/documents/doc-a

# 4. Alice tries to access Bob's document
curl -i -u alice:alice123 http://localhost:8080/api/documents/doc-b

# 5. Alice spoofs a user ID in the query parameter
curl -i -u alice:alice123 \
  'http://localhost:8080/api/documents/doc-b?userId=u-bob'

# 6. Bob views his own document
curl -i -u bob:bob123 http://localhost:8080/api/documents/doc-b

# 7. Each user receives only their own document list
curl -i -u alice:alice123 http://localhost:8080/api/documents
curl -i -u bob:bob123 http://localhost:8080/api/documents
```

When running in PowerShell, write each command on a single line; the trailing `\` in the example above is Bash line continuation syntax.

| Request | Expected status | Key result |
| --- | --- | --- |
| `GET /api/me` without credentials | **401** | Prompts for HTTP Basic authentication |
| `GET /api/me` as Alice | **200** | `userId` is `u-alice` from server record |
| `GET /api/documents/doc-a` as Alice | **200** | JSON of document `doc-a` |
| `GET /api/documents/doc-b` as Alice | **404** | Cannot view Bob's object |
| Same request with spoofed `?userId=u-bob` | **404** | Self-asserted user ID cannot switch the actor |
| `GET /api/documents/doc-b` as Bob | **200** | JSON of document `doc-b` |
| `GET /api/documents` as Alice | **200** | Only Alice's document list |
| `GET /api/documents` as Bob | **200** | Only Bob's document list |
| `GET /api/documents/khong-ton-tai` as Alice | **404** | No matching object found |

Expected body for `GET /api/me` as Alice (key ordering may vary):

```json
{
  "userId": "u-alice",
  "username": "alice"
}
```

Expected body for Alice's document:

```json
{
  "id": "doc-a",
  "title": "Alice's notebook"
}
```

**Note on verification evidence:** do not depend on all response headers or JSON key order; verify the status code, body, and returned data. HTTP Basic transmits credentials in Base64, which **must not be considered encryption**; use it only over HTTPS on real networks. Sample accounts and passwords are for local study only—never ship them to production.

## 5. Distinguishing "User ID Identifying a Resource" from "User ID Proving Identity"

A system may legitimately have a route like `GET /api/users/{userId}/profile`. The problem is not having a `userId` parameter, but **using it in the wrong role**.

Example of a proper authorization flow:

1. Server authenticates the request and resolves **actorId = u-alice**.
2. Client requests **targetUserId = u-bob**.
3. Service checks whether the actor has `READ_PROFILE` permission on the target (e.g., users can view only themselves, or admins may view users within the same tenant).
4. If unauthorized, reject; if authorized, query and return only permitted fields.

Comparing `actorId.equals(targetUserId)` alone may suffice for a **self-only view** feature, but is **not enough for all requirements**: admins, shared users, guardians, delegates, and enterprise workflows may need richer checks. The converse is also true: when actor and target differ, never grant access simply because the actor has role `ADMIN` without checking tenant/administrative scope.

A concise representation:

```text
actorId = validatedAuthentication -> serverAccount.id
targetId = request.path / request.query / request.body

allowed = authorizationPolicy.canPerform(
    actorId, action, targetId, trustedResourceAttributes
)
```

Here `trustedResourceAttributes` refers to owner, tenant, state, and sharing data loaded from a trusted store. **Never take owner/tenant from JSON sent by the caller as proof of permission.**

### Never Treat "Hard-to-Guess" Keys as Authorization

Even if an ID is a UUID or a long random string, ID leakage through shared links, logs, browser history, screenshots, emails, or other APIs can still happen. You cannot rely on "hard-to-guess IDs" as access control. If a product genuinely uses a **capability URL** or signed URL as a grant mechanism, that URL's token must be specifically designed, signed, scoped/time-limited, and handled for leakage under its own threat model; an ordinary ID never becomes a capability on its own.

### Never Use Roles as a Substitute for Per-Object Permissions

`hasRole("USER")` only states that the user belongs to the USER group. Both Alice and Bob hold this role; therefore:

```java
// Insufficient for per-user owned resources.
.requestMatchers("/api/documents/**").hasRole("USER")
```

does not guarantee Alice can only view Alice's documents. You must add permission checks by **owner or sharing relationship** in the service/repository/authorization manager. For multi-tenant systems, check both tenant and object permissions before exposing data; never infer from a role name that a user can access every tenant.

## 6. Placing Authorization Checks Close to Data and Writes

The Java example in section 4 only reads immutable in-memory data. In real applications, rules should be enforced in the business layer combined with constrained data queries.

For example, to let Alice fetch only documents owned by Alice, query by **both document ID and authenticated owner ID**:

```sql
SELECT id, title
FROM documents
WHERE id = :documentId
  AND owner_user_id = :authenticatedUserId;
```

`authenticatedUserId` must be determined server-side from the principal/internal identifier. `documentId` may come from the client as the query target, but must be parameter-bound—never concatenated into SQL strings.

For updates, check authorization at write time to avoid checking one state and then writing after ownership/permissions have changed (time-of-check/time-of-use):

```sql
UPDATE documents
SET title = :newTitle
WHERE id = :documentId
  AND owner_user_id = :authenticatedUserId;
```

Then verify **the number of updated rows**. If it is 0, you cannot assume the operation succeeded; handle it according to your contract (e.g., 404 for "no modifiable resource found"). For complex rules (sharing, multi-step approval, tenants, state), transactions, appropriate locking, or additional state predicates may be required.

Never rely solely on the frontend having called `GET /api/me` earlier: login state, permissions, owner, or tenant can change **between two requests**. Every sensitive operation must be checked server-side against the current identity and policy.

### Avoiding Mass Assignment: User ID and Role in the Body

A profile update API might receive JSON like:

```json
{
  "displayName": "Alice New",
  "userId": "u-bob",
  "role": "ADMIN"
}
```

If the server maps the entire JSON payload straight onto an entity and saves it, a client could alter `userId`, `ownerId`, `role`, `tenantId`, or other security-sensitive fields. For an endpoint updating **one's own profile**, the DTO should accept only fields actually allowed to change, such as `displayName`; the record to update must be identified from the authenticated actor. If an administrative endpoint permits changing roles/owners, it must require dedicated privileges and scope checks rather than allowing an arbitrary body field to trigger it.

Good policies combine **BOLA** (checking whether the actor may operate on the object), **BOPLA/mass assignment** (checking which properties may be read/modified), and **authentication** (who is acting). You cannot solve everything with a single `@PreAuthorize("isAuthenticated()")` annotation.

## 7. Sessions, Cookies, Tokens, Gateways: What Counts as a Trusted Identity Source?

There is an important distinction between an **authentication credential carrier** and a **client-asserted user ID**:

| What the client sends | Usable for authentication? | Conditions to become a trusted basis |
| --- | --- | --- |
| `?userId=u-bob` in URL | No | Merely a target/request attribute, carries no proof |
| Self-sent `X-User-Id: u-bob` | No | Trust only when actively overwritten by trusted infrastructure after auth with bypass paths blocked |
| Self-written `Cookie: userId=u-bob` | No | A raw userId cookie proves no authority |
| Session cookie with random ID | Potentially | Server validates session, binds principal, and sets proper cookie flags, fixation protection, and expiry |
| `Authorization: Basic ...` | Potentially | Server authenticates username/password; transmit only over HTTPS |
| `Authorization: Bearer <JWT>` | Potentially | Resource Server/IdP verifies signature, issuer, applicable audience/claims, expiry, and policy |
| `Authorization: Bearer <opaque-token>` | Potentially | Introspection or trusted token validation mechanism verifying expiry and scope |
| Identity header from gateway | Conditionally | Gateway authenticated caller, stripped forged client headers, and backend cannot be reached directly |

**Even an authenticated identity does not imply permission to view every record.** After authentication, you must still evaluate actor–action–resource within business context.

For session-based web apps, add CSRF protection on state-changing actions, configure `Secure`/`HttpOnly`/`SameSite` cookie attributes appropriately, manage session lifecycle, and avoid logging session IDs. For stateless Bearer-token apps, never skip object-level authorization just because the app is "stateless".

## 8. Common Technical Pitfalls

### 8.1. Trusting a `userId` Because the Frontend "Locked" the Input Field

`disabled`/`readonly`/hidden inputs only alter UI behavior; they do not stop anyone from sending forged HTTP requests. Fix: derive identity on the backend from `Authentication` and enforce business permission checks on every object access.

### 8.2. Reading `X-User-Id` Directly Behind a Gateway

Client-sent headers can share the exact name used by internal systems. If the proxy fails to strip incoming headers and regenerate authenticated headers, clients can hijack identities. Fix: define trust boundaries, use mTLS or gateway-to-backend authentication when needed, strip/overwrite headers before forwarding, ensure the backend cannot be accessed directly bypassing the gateway, and audit by verified principal.

### 8.3. Checking Session ID Ownership at Login and Trusting the ID Forever After

Permissions, tenants, owners, and user status can be revoked or modified. Verify permissions on every significant operation with clear cache/invalidation strategies; never treat browser local storage as a source of truth.

### 8.4. Filtering Only the List Endpoint While Forgetting Detail or Download Endpoints

Filtering `GET /api/documents` by owner while letting `GET /api/documents/{id}` load any ID directly is a BOLA flaw. Check download, export, preview, update, delete, attachment, GraphQL resolver, and batch endpoints as well. Every path to an object must enforce the same policy.

### 8.5. Assigning Ownership from Client Input on Write Commands

If a request accepts `ownerUserId` or `tenantId`, new objects can be created under or assigned to the wrong owner. The server must set ownership fields from the authenticated identity or verify explicit assignment privileges. Never trust `createdBy` or `approvedBy` from JSON.

### 8.6. Comparing Usernames as Plain Strings Without Namespace Context

Emails and usernames can change, be reused, or collide across identity providers. After authentication, map to a stable internal ID and the proper tenant/issuer. When supporting multiple OIDC issuers, never assume two identical `sub` values belong to the same user across different issuers.

### 8.7. Looking Only at 200 Status Codes in "Happy Path" Tests

An endpoint returning 200 for Alice does not prove it blocks Bob. You must test clients spoofing `userId` and requesting another user's object IDs. The goal is verifying **authorization after authentication succeeds**. Also test valid accounts that have been removed from the internal system.

## 9. Testing Matrix to Catch BOLA Flaws

Assume two validly logged-in accounts, Alice and Bob:

| Scenario | Required outcome |
| --- | --- |
| Alice calls `GET /api/me` | Server returns Alice's user ID |
| Alice adds `?userId=u-bob` to `/api/me` | Still Alice; parameter does not switch actor |
| Alice views her own document `doc-a` | 200 |
| Alice tries viewing Bob's `doc-b` by changing the URL ID | Rejected (404 in the example) |
| Alice sends `X-User-Id: u-bob` header when viewing `doc-b` | Still rejected |
| Bob views his own document `doc-b` | 200 |
| No credentials sent | 401/challenge with HTTP Basic in the example |
| Wrong Basic password sent | 401 |
| Requesting a nonexistent document | Rejected per contract; e.g., 404 |
| Update request containing spoofed `ownerUserId` or `role` field | Cannot alter permissions/ownership; must go through dedicated policy |
| Admin of tenant A requests tenant B's document | Blocked unless policy permits cross-tenant admins |
| Permissions revoked after login session established | Subsequent operations reflect current effective permissions per design |

Integration tests can use `MockMvc` + Spring Security Test or `curl`/HTTP clients. With the program in section 4, verify status codes and JSON after startup. For deeper testing, seed multiple tenants, shared documents, revoked permissions, and verify write operations inside transactions.

### How to Interpret Security Test Results Accurately

- **401**: no valid authentication yet or authentication needs to be initiated (e.g., HTTP Basic).
- **403**: authenticated, but denied by policy in many designs.
- **404**: either the resource does not exist **or** the application deliberately avoids disclosing resources the caller is not allowed to see.
- **200**: request succeeded; verify only the authorized resource and permitted fields are returned.

The exact status code for unauthorized access depends on the product contract; what is non-negotiable is **never leaking another user's resources** and never trusting a client-asserted user ID as identity.

## 10. Key Takeaways for Designing Data-Protecting APIs

1. **The actor comes from server-verified authentication.** In Spring Security Servlet, obtain `Authentication`/principal in the controller or service layer as appropriate.
2. **Client-supplied resource IDs are only targets.** Allow clients to specify which document/record they want to act on when appropriate for the API, then verify specific permissions.
3. **Never take an arbitrary user ID from path/query/body/header/cookie as the principal.** Use verified sessions/tokens or trusted mappings to internal user IDs.
4. **Enforce object-level authorization on every entry point.** List, detail, download, update, delete, and batch operations must all be protected.
5. **Enforce owner/tenant/action conditions on the backend**, ideally close to data queries and writes; account for transactions under concurrent changes.
6. **Fail closed when authorization is unclear.** Never fall back to a client-supplied ID just "to avoid errors" when user mapping is missing or policy evaluation fails.
7. **Write negative test cases deliberately.** A valid user spoofing another user's ID must fail, even if the UI does not allow typing that ID.

### References

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [OWASP API Security Top 10 — API1:2023 Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
