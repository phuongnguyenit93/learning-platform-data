# Matching User Attributes, Resource Attributes, and Request Context

> **Context:** Spring Security 6 on the **Servlet stack**, Java 17+, and Spring Boot 3.x. Topic under **Authorization Models**: how to evaluate an allow/deny decision based on **user attributes (subject)**, **resource attributes (resource/object)**, **action**, and **request context (environment/request context)**. This approach is commonly called **ABAC — Attribute-Based Access Control**. The article explains everything from the conceptual model to policy placement in Spring Security, trusted data boundaries, multi-tenant isolation, a runnable demo app, and tests covering denied cases as well.

## 1. Why Is Checking Roles Alone Not Enough?

Suppose an application stores thousands of documents across many companies and departments. A rule:

```java
.requestMatchers("/api/docs/**").hasRole("EMPLOYEE")
```

only answers: "Does this person have the `EMPLOYEE` role?" It **does not** answer:

- Which tenant does the document belong to?
- Does the user belong to that tenant?
- Is the document confidential with a classification level higher than the user's viewing clearance?
- Is the user in the same department as the document?
- Is the user the document creator, and are they allowed to self-approve their own document?
- Is the request **reading** or **approving**, and has the active tenant been verified?
- Is the document state `DRAFT`, `PENDING`, or `APPROVED`?
- Was a contextual condition such as time, network location, or MFA assurance level verified from a trusted source?

If `/api/docs/**` is protected only by `hasRole("EMPLOYEE")`, an employee in tenant A can accidentally read documents of tenant B. That is an **IDOR/BOLA** vulnerability — unauthorized object access simply by changing an ID in the URL.

**ABAC idea:** decisions rely on **relationships across multiple attributes**, not just a single static role. Roles remain useful and can serve as one attribute inside the policy.

### The Central Question

Instead of:

```text
Does User have ROLE_EMPLOYEE?
       |
      YES -> allow
```

think:

```text
Which tenant is the User in? Which department? Which clearance level?
                       |
Which tenant is the Document in? What kind? Owner? Status?
                       |
Action = READ or APPROVE?
                       |
Does the request have a permitted active tenant? Which HTTP method?
                       |
                       v
                  Policy decision
              PERMIT / DENY (default DENY)
```

## 2. Four Attribute Groups to Match

ABAC typically models four groups of inputs (`subject`, `resource`, `action`, `environment`). Names may vary across systems, but their decision semantics must be unambiguous.

| Group | Examples | Trusted source |
| --- | --- | --- |
| **Subject (user)** | user ID, tenant memberships, department, roles, clearance, account status, MFA level | Verified `Authentication` and server-side user/profile store |
| **Resource (target)** | document ID, owning tenant, department, owner, sensitivity, workflow state | Server-side database/service repository after loading the record |
| **Action (operation)** | read, create, update, approve, delete, export | Defined endpoint/service operation; HTTP method is one input, not self-granted authority |
| **Environment / request context** | server time, selected tenant, trusted network/device posture, HTTP method, re-auth freshness | Server-verified values; header/query inputs are only unverified data needing validation |

Example read policy formula:

```text
allowRead(subject, document, request) =
      isAuthenticated(subject)
  AND subject.tenant == document.tenant
  AND request.selectedTenant == subject.tenant
  AND subject.department == document.department
  AND subject.clearance >= document.minClearance
```

Example approve policy:

```text
allowApprove(subject, document, request) =
      allowRead(subject, document, request)
  AND subject.hasRole("APPROVER")
  AND document.status == PENDING
  AND subject.username != document.owner
  AND action == APPROVE
  AND requiredStepUpWasVerifiedByServer   (if policy requires)
```

**Do not** interpret these expressions as exact requirements for every enterprise. They illustrate how attributes combine. Another system may allow owners to access documents across departments, or use non-linear classification labels instead of integers; policies must come from business rules and the threat model.

## 3. RBAC and ABAC: Complementary, Not Mutually Exclusive

**RBAC** (Role-Based Access Control) typically checks roles/authorities such as `ROLE_ADMIN` or `SCOPE_read`.

**ABAC** uses attributes of multiple entities and context to decide a specific request.

| Question | RBAC | ABAC |
| --- | --- | --- |
| Does the user have role `REVIEWER`? | Very suitable | Used as one attribute |
| Does the document belong to the right tenant? | Single role is usually insufficient | Matches subject tenant and resource tenant |
| May the user view a document of this sensitivity? | Needs extra roles/policies | Compares clearance with resource classification/label |
| Is the creator trying to self-approve? | Roles do not know document owner | Compares subject ID with resource owner |
| Is the resource currently `PENDING`? | Roles do not express current state | Reads state from repository and evaluates |
| Did the request occur in a fresh MFA session? | Raw role cannot guarantee this | Uses trusted authentication context/freshness |
| Operational complexity | Easy to understand when privileges are few | Richer policies, but needs data governance/testing/caching |

ABAC **does not mean discarding `hasRole`**. A real policy may require `ROLE_APPROVER` **and** matching tenant **and** sufficient clearance **and** the right state. RBAC serves as "functional capability"; ABAC verifies "is it allowed on this specific resource and context?".

### Avoiding Role Explosion

If you create roles for every combination of tenant, department, document, and state, you end up with `ROLE_NORTH_FINANCE_CONFIDENTIAL_APPROVER_PENDING`, `ROLE_SOUTH_FINANCE_CONFIDENTIAL_APPROVER_PENDING`... The role count grows rapidly, becoming hard to revoke and hard to reason about. Separating dynamic resource attributes from roles prevents unbounded role duplication.

### ABAC Does Not Mean "Trust Every Client Claim"

If a JWT carries `tenant`/`roles` claims **whose signature, issuer, audience, and expiry have been verified by the server**, those claims can be trusted subject inputs within the token's policy and lifetime. By contrast, an arbitrary header:

```http
X-User-Role: ADMIN
X-User-Tenant: north
```

is **not trustworthy** merely because the client sent it. If the application uses `X-User-Role` to grant privileges directly, an attacker can forge privileges. Always verify the source and trust boundary.

## 4. Policy Architecture: PEP, PDP, PIP, and PAP

ABAC commonly uses four logical roles:

- **PEP (Policy Enforcement Point):** blocks the request or operation when policy denies; e.g. `AuthorizationFilter`, method security interceptor.
- **PDP (Policy Decision Point):** evaluates the policy and returns permit/deny; e.g. `AuthorizationManager` or a `DocumentPolicy` bean.
- **PIP (Policy Information Point):** supplies attributes; e.g. user directory, document repository, trusted risk engine.
- **PAP (Policy Administration Point):** where policies are authored/managed, versioned, reviewed, and approved for change.

```text
HTTP request
     |
     v
Authentication filters -> verified principal
     |
     v
PEP: Spring Security AuthorizationFilter / Method Security
     |
     +--> PDP: DocumentPolicy.canRead/canApprove
                |
                +--> PIP subject: UserProfileDirectory
                +--> PIP resource: DocumentRepository
                +--> Context: verified active tenant
                +--> Action: method/service operation
                |
                v
         PERMIT / DENY
     |
     +--> PERMIT: call service / continue processing
     +--> DENY: do not execute operation
```

For small systems, PDP/PIP can simply be a few Spring beans. Across many apps/microservices, a central policy engine may be used; either way, clearly define **where enforcement happens** and **how trustworthy each attribute is**. Never write a "policy document" without a real PEP enforcing it on the request path.

### Permit, Deny, and Missing Data

A policy should **fail closed**: missing user profile, resource not found, unverified tenant, unknown clearance, or policy backend error → **never grant access by default**.

In large environments, a PDP may also return `NotApplicable`/`Indeterminate` or obligations/advice. The application must define how those states translate to HTTP, metrics, and error handling; **never** treat "unknown" as "allow".

### 401, 403, and 404

- **401 Unauthorized:** missing valid authentication (for example, a Basic request without credentials).
- **403 Forbidden:** authenticated, but the ABAC policy denies access.
- **404 Not Found:** resource does not exist, or the application intentionally hides the existence of unauthorized resources per policy.

Not every unauthorized resource must return 403; many systems choose 404 to curb enumeration. Never return distinct responses that help attackers probe internal resources when policy intends to hide existence.

## 5. Subject Attributes: Where Are They Verified and How Long Are They Valid?

Subject attributes may come from:

1. `Authentication.getName()` and authorities populated after authentication.
2. `UserDetailsService` or a server-side user directory.
3. OIDC/JWT claims verified for issuer/audience/signature/expiry.
4. A service managing tenant memberships/permissions.
5. Authentication context recording when the user completed MFA or re-authentication.

**Decision sources must be verified.** If a token/cookie is still valid while a role/tenant membership has changed, you need a privilege-refresh policy: real-time profile lookups, short cache TTLs, token versioning, or active revocation. ABAC reading claims from an old token does not automatically see newly revoked memberships.

### Attributes Can Change Over Time

Suppose a user moves from Sales to Finance. If `Authentication` in the session still holds the old authority/department, a policy relying solely on the session can accept stale data. Design must answer:

- When is the user directory refreshed?
- Is there a cache, and what is its TTL?
- When changing tenants or disabling a user, how are old sessions/tokens handled?
- If the user directory is unavailable, does it fail closed?
- Is there a deny-by-default rule when attributes cannot be fetched?

### Avoid Assigning Roles from Client-Sent Headers

Anti-pattern:

```java
// Wrong: unverified client input must never become an authority.
String role = request.getHeader("X-Role");
if ("ADMIN".equals(role)) {
    // allow admin
}
```

Even if a proxy adds the header, verify that the proxy is trusted, that the proxy **strips any client-supplied header first**, that the backend accepts traffic only from the trusted proxy, and that the connection is secured. Do not assume "there is a proxy" means headers are trustworthy.

## 6. Resource Attributes: Always Fetch the Record with Its Real Owner

If `GET /api/docs/102` carries ID `102`, **the ID is a selector**, not proof the user has permission. The server must look up resource `102`, retrieve tenant, department, owner, classification, and status from a trusted repository, and then compare them against the subject.

```text
GET /api/docs/102
          |
          +--> id=102 (chosen by client)
          |
          v
DocumentRepository.find(102) (server-side)
          |
          +--> tenant=north
          +--> department=finance
          +--> owner=alice
          +--> minClearance=2
          +--> status=PENDING
          |
          v
DocumentPolicy evaluates these attributes
```

Never take `tenant` and `classification` from a request body while **reading** a document and treat them as the document's true metadata.

### IDOR/BOLA and Tenant Isolation

A route like `/api/docs/{id}` matches any ID regardless of tenant. `authenticated()` only knows the user logged in. If the service calls `repository.findById(id)` and returns it directly, a user can change `102` to `103` to read another tenant's document.

Two sound protection strategies:

- **Scope queries by tenant/owner in the DB**, e.g. `id AND tenant_id IN allowedTenants`.
- **Load and evaluate via policy** before returning data or mutating state.

When combining both, avoid leaking information through responses or timing. For multi-tenant queries, Row-Level Security (if supported and configured properly in the DB) can add defense in depth, though it never replaces testing application authorization.

### Metadata Changing Between Check and Operation

Suppose policy checks `status=PENDING`, and another request approves the document before the current request updates it. If policy check and update lack a transaction/lock/compare-and-set, **TOCTOU** (time-of-check to time-of-use) can happen.

In the learning example, the repository uses `ConcurrentHashMap.compute(...)` to make the `PENDING → APPROVED` transition atomic **in memory within one process**. Production needs transactions, optimistic locking, version columns, or conditional SQL updates on a real database with tenant/permission scoping.

## 7. Request Context: Observations, Selections, and Trusted Data

A request has:

- HTTP method received by the container (GET/POST/DELETE).
- URL/path variables extracted by the router.
- Headers such as `X-Active-Tenant`, `X-Forwarded-For`, `User-Agent`.
- Client network address identified by the container/proxy.
- Request timestamp from the server clock.
- Session or authentication token carrying MFA/freshness indicators if supported.

**Not all values are equally trustworthy.**

### 7.1. Client-Chosen Active Tenant Is Only a Proposal

If a user belongs to multiple tenants, the frontend can send `X-Active-Tenant: north` to select a workspace. The server must still verify:

1. Is the user actually permitted in that tenant?
2. Does the resource belong to that tenant?
3. Is this action allowed in that tenant?
4. Does the session/token meet the required assurance level?

A user belonging only to `north` sending header `south` **must not be allowed to read south documents**. A context-selection header must never act as a source of authority on its own.

Example:

```text
Subject = alice, granted tenant = north
Resource = doc 103, tenant stored in DB = south
Header X-Active-Tenant: south

Subject membership and resource tenant do not match -> DENY.
```

### 7.2. IP, Proxies, and Forwarded Headers

`request.getRemoteAddr()` is normally the peer IP connecting to the container; behind a reverse proxy it may be the proxy rather than the client. An arbitrary client-sent `X-Forwarded-For` header is **untrusted** unless the gateway validates and normalizes it.

If policy depends on network zone, let a **trusted edge/gateway** provide verified results, configure forwarded header handling only from trusted proxies, and test through a production-like network path. Generally, avoid relying on IP alone as the gate for high-privilege access.

### 7.3. Server Time and Step-Up Authentication

A policy may restrict `APPROVE` to business hours or require MFA within the last 10 minutes. Time must come from a trusted server `Clock`, never a client-declared `X-Now` header; MFA level must come from a verified authentication event/claim, never `X-MFA: true`.

To test time-based policies, inject `java.time.Clock` and use `Clock.fixed(...)` in unit tests so tests do not randomly fail at night, on holidays, or in different time zones.

### 7.4. Action: HTTP Method Does Not Replace Business Privilege

`POST /api/docs/102/approve` describes the `APPROVE` action; controllers/services must define semantics explicitly. However, users might try sending `GET` or adding a parameter `action=approve`. Never trust arbitrary parameters to elevate privileges. Bind HTTP methods strictly and enforce policy on the **operation/service** that actually mutates state.

## 8. Where to Place Policies in Spring Security 6

Common extension points:

| Extension point | When to use | Things to watch |
| --- | --- | --- |
| `authorizeHttpRequests(...requestMatchers(...))` | Static policy by URL/method/role | Lacks resource metadata if object is not loaded |
| `AuthorizationManager<RequestAuthorizationContext>` | Request-level decisions on path/headers and trusted context | May need PIP lookup; handle variables and performance |
| `@PreAuthorize` on service methods | Policy on resource ID, subject, action after controller parses input | Requires `@EnableMethodSecurity`; ensure calls go via Spring proxy |
| `@PostAuthorize` / collection filtering | Certain post-read checks | Caution: work/side effects may already have run; avoid leaks |
| Custom domain authorization service | Complex workflows, tenant/object relations | Must be invoked on all code paths; test beyond controllers |
| Database Row-Level Security | Defense in depth for multi-tenant data | DB connection and session tenant identity must be right; does not replace business policy |

**Recommendation in this article:** use `authorizeHttpRequests` to enforce authentication and HTTP-level policy, then place resource-aware ABAC at the **service method boundary** with `@PreAuthorize` calling a policy bean. This keeps domain policy close to the operation and avoids copy-pasting conditions across controllers.

### 8.1. Why Not Authorize Only at the Controller?

If the same `DocumentService` is invoked from a REST controller, GraphQL resolver, message consumer, or scheduled job, a check placed only in the REST controller is bypassed on other paths. Service-layer policies reduce bypass risk.

However, `@PreAuthorize` uses Spring AOP proxies: **self-invocation** (one method on a bean calling another method on `this`) can bypass the method-security interceptor. Design bean boundaries carefully and test non-HTTP entry points too.

### 8.2. @PostAuthorize Can Be Too Late for Side Effects

If a method updates the database or sends an email before `@PostAuthorize` denies it, the side effect has already happened. For state-changing operations, use pre-authorization and transactions/atomic updates; do not rely on post-checks to "undo" side effects.

### 8.3. Default-Deny Principle

Policies should return `false` when:

- No valid `Authentication` is present.
- Subject profile does not exist or fails to load.
- Resource does not exist or fails to load.
- Active tenant is missing or mismatches.
- Clearance/role is insufficient.
- Action is outside the allowed policy.
- Request context fails requirements or cannot be verified.

**A PIP/PDP failure is not a permit**. If the policy backend errors out, the app may return 5xx per contract, but must never let the request bypass authorization.

## 9. Runnable Spring Boot Project: ABAC for Multi-Tenant Documents

The project uses **Java 17+**, **Spring Boot 3.3.5**, **Spring Security 6.x**, and **Gradle 8.5**. Its goal is demonstrating explicit policies, not just `hasRole`. The app uses local Basic authentication to keep focus on ABAC; production requires HTTPS and a real authentication provider.

**Model:**

| Username | Server-side tenant | Department | Clearance | Roles |
| --- | --- | --- | --- | --- |
| `alice` | `north` | `finance` | 2 | USER |
| `bob` | `north` | `sales` | 1 | USER |
| `carol` | `south` | `finance` | 3 | USER, APPROVER |
| `dana` | `north` | `finance` | 3 | USER, APPROVER |

| Doc ID | Tenant | Department | Min clearance | Owner | Status |
| --- | --- | --- | --- | --- | --- |
| 101 | north | finance | 1 | alice | DRAFT |
| 102 | north | finance | 2 | alice | PENDING |
| 103 | south | finance | 2 | carol | PENDING |
| 104 | north | finance | 3 | dana | PENDING |

**Read policy:** user is authenticated, active-tenant header matches the server-assigned tenant, document tenant matches, same department, and sufficient clearance.

**Approve policy:** must satisfy read policy **and** have `ROLE_APPROVER` **and** document is `PENDING` **and** approver **differs from owner** (separation of duties). A state-changing POST requires a CSRF token in the demo.

### 9.1. Project Structure

```text
abac-document-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    UserProfileDirectory.java
    DocumentRepository.java
    DocumentPolicy.java
    DocumentService.java
    DocumentController.java
  src/test/java/demo/
    DocumentAbacTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'abac-document-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += '-parameters'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`-parameters` lets Spring method security resolve parameter names `#id` and `#activeTenant` in `@PreAuthorize` expressions.

### 9.2. Startup Class

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 9.3. SecurityConfig: Authenticate First, Method Authorization Second

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demoPass!"))
                .roles("USER")
                .build();
        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("demoPass!"))
                .roles("USER")
                .build();
        UserDetails carol = User.withUsername("carol")
                .password(encoder.encode("demoPass!"))
                .roles("USER", "APPROVER")
                .build();
        UserDetails dana = User.withUsername("dana")
                .password(encoder.encode("demoPass!"))
                .roles("USER", "APPROVER")
                .build();
        return new InMemoryUserDetailsManager(alice, bob, carol, dana);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http.securityMatcher("/api/**");

        http.authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

        http.httpBasic(Customizer.withDefaults());

        // Default CSRF stays enabled: POST requires a CSRF token.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

**Key points:**

- `@EnableMethodSecurity` enables the interceptor so `@PreAuthorize` takes effect.
- The API chain only requires `authenticated()` at the HTTP layer; that is **not enough to view a document**. Resource policy lives in `DocumentPolicy`.
- The fallback chain is deny-by-default so URLs outside `/api/**` never accidentally sit outside Spring Security's scope.
- HTTP Basic is only for the demo; credentials must travel over HTTPS outside localhost.
- CSRF stays enabled. Even `POST` with `httpBasic(...)` in MockMvc needs `with(csrf())` to prove the approval policy works instead of failing on CSRF.

### 9.4. UserProfileDirectory: Server-Controlled Subject Attributes

`src/main/java/demo/UserProfileDirectory.java`:

```java
package demo;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class UserProfileDirectory {

    private final Map<String, UserProfile> profiles = Map.of(
            "alice", new UserProfile("north", "finance", 2),
            "bob", new UserProfile("north", "sales", 1),
            "carol", new UserProfile("south", "finance", 3),
            "dana", new UserProfile("north", "finance", 3));

    public UserProfile find(String username) {
        return profiles.get(username);
    }
}

record UserProfile(String tenant, String department, int clearance) {}
```

This is a **server-side source of truth for the demo**, not client-sent headers. Production uses a properly secured database/directory/service, handling caching, membership revocation, claim validity, and PIP failures.

`UserProfile` holds only tenant/department/clearance. The `APPROVER` role is granted by Spring Security from `UserDetailsService` after username/password verification. Both sources supply distinct attributes, and both are server-managed.

### 9.5. DocumentRepository: Trusted Resource Attributes

`src/main/java/demo/DocumentRepository.java`:

```java
package demo;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class DocumentRepository {

    private final ConcurrentMap<Long, Document> documents =
            new ConcurrentHashMap<>();

    public DocumentRepository() {
        reset();
    }

    public void reset() {
        documents.clear();
        documents.put(101L, new Document(
                101L, "north", "finance", 1, "alice",
                DocumentStatus.DRAFT));
        documents.put(102L, new Document(
                102L, "north", "finance", 2, "alice",
                DocumentStatus.PENDING));
        documents.put(103L, new Document(
                103L, "south", "finance", 2, "carol",
                DocumentStatus.PENDING));
        documents.put(104L, new Document(
                104L, "north", "finance", 3, "dana",
                DocumentStatus.PENDING));
    }

    public Document find(long id) {
        return documents.get(id);
    }

    public Document approve(long id) {
        return documents.compute(id, (key, current) -> {
            if (current == null) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND);
            }
            if (current.status() != DocumentStatus.PENDING) {
                throw new ResponseStatusException(HttpStatus.CONFLICT);
            }
            return new Document(
                    current.id(),
                    current.tenant(),
                    current.department(),
                    current.minClearance(),
                    current.owner(),
                    DocumentStatus.APPROVED);
        });
    }
}

enum DocumentStatus {
    DRAFT, PENDING, APPROVED
}

record Document(
        long id,
        String tenant,
        String department,
        int minClearance,
        String owner,
        DocumentStatus status) {}
```

The resource ID from the URL is only used to **look up the record**; tenant, owner, department, clearance level, and status are fetched from the server-side repository.

`approve` uses `ConcurrentMap.compute` to check `PENDING` and transition to `APPROVED` atomically for that key **within a single JVM**. This matters when two requests concurrently attempt approval. However, it **does not** turn the preceding `DocumentPolicy` check into an atomic DB transaction; production still needs transactions/locking/conditional updates with tenant scoping to prevent TOCTOU.

`reset()` exists for tests so each test starts clean; never expose a public endpoint allowing callers to reset data.

### 9.6. DocumentPolicy: Where Subject–Resource–Context Are Matched

`src/main/java/demo/DocumentPolicy.java`:

```java
package demo;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final UserProfileDirectory directory;
    private final DocumentRepository documents;

    public DocumentPolicy(UserProfileDirectory directory,
                          DocumentRepository documents) {
        this.directory = directory;
        this.documents = documents;
    }

    private UserProfile trustedProfile(Authentication authentication) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return null;
        }

        return directory.find(authentication.getName());
    }

    private boolean canAccess(Authentication authentication,
                              long id,
                              String activeTenant) {

        UserProfile subject = trustedProfile(authentication);
        Document resource = documents.find(id);

        if (subject == null
                || resource == null
                || activeTenant == null) {
            return false;
        }

        return subject.tenant().equals(activeTenant)
                && resource.tenant().equals(subject.tenant())
                && subject.department().equals(resource.department())
                && subject.clearance() >= resource.minClearance();
    }

    public boolean canRead(Authentication authentication,
                           long id, String activeTenant) {
        return canAccess(authentication, id, activeTenant);
    }

    public boolean canApprove(Authentication authentication,
                              long id, String activeTenant) {

        if (!canAccess(authentication, id, activeTenant)) {
            return false;
        }

        Document resource = documents.find(id);

        return resource != null
                && resource.status() == DocumentStatus.PENDING
                && !resource.owner().equals(authentication.getName())
                && authentication.getAuthorities().stream().anyMatch(
                    authority -> "ROLE_APPROVER".equals(
                            authority.getAuthority()));
    }
}
```

**Core principles of this ABAC pattern:**

- `authentication.getName()` comes from authentication, never a browser-supplied `X-User`.
- `directory.find(...)` looks up tenant/department/clearance **on the server**.
- `documents.find(id)` looks up document attributes **on the server**.
- `activeTenant` is a **client-supplied selection** via header, yet must **equal** both subject tenant and resource tenant. Clients cannot swap the header to grant themselves membership in a new tenant.
- When user profile is missing, resource is missing, tenant is blank, department mismatches, or clearance is insufficient, the policy returns `false`.
- Approval also requires `ROLE_APPROVER`, `PENDING` state, and **not being the owner** to enforce the *four-eyes principle*.

**Demo limitation:** each user has only one tenant. When users belong to multiple tenants, the directory should provide a verified membership set; active tenant must belong to that set and the resource must belong to that selected tenant. The single-tenant rule teaches the core pattern without extra noise.

### 9.7. DocumentService: Enforcing Policy at the Business Boundary

`src/main/java/demo/DocumentService.java`:

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final DocumentRepository documents;

    public DocumentService(DocumentRepository documents) {
        this.documents = documents;
    }

    @PreAuthorize(
        "@documentPolicy.canRead(authentication, #id, #activeTenant)")
    public String read(long id, String activeTenant) {
        Document document = documents.find(id);
        return "doc-" + document.id() + ":" + document.status();
    }

    @PreAuthorize(
        "@documentPolicy.canApprove(authentication, #id, #activeTenant)")
    public String approve(long id, String activeTenant) {
        Document updated = documents.approve(id);
        return "approved-" + updated.id();
    }
}
```

**Why use method security:**

- When the controller calls `service.read` or `service.approve`, the Spring proxy checks `@PreAuthorize` before running the method.
- `#id` and `#activeTenant` resolve from method parameter names thanks to `-parameters` in Gradle.
- Policy logic is not duplicated across every endpoint.
- `approve` mutates state only after `DocumentPolicy` permits it.

**AOP proxy note:** calling `this.approve(...)` from another method **inside the same DocumentService** can bypass `@PreAuthorize`. Invoke it from another bean through the Spring proxy, or design a domain authorization layer that does not rely solely on AOP, and test every entry point.

**Concurrency note:** `canApprove` reads state before the method executes. `documents.approve` checks `PENDING` again inside an atomic update to prevent double transitions. In a DB-backed system, policy checks and state writes need proper transaction/concurrency design. In particular, verify **tenant and membership** have not changed between the two steps if the threat model demands immediate consistency.

### 9.8. DocumentController: Reads Selected Tenant, Never Trusts It as Privilege

`src/main/java/demo/DocumentController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/docs")
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public String read(
            @PathVariable long id,
            @RequestHeader("X-Active-Tenant") String activeTenant) {
        return service.read(id, activeTenant);
    }

    @PostMapping("/{id}/approve")
    public String approve(
            @PathVariable long id,
            @RequestHeader("X-Active-Tenant") String activeTenant) {
        return service.approve(id, activeTenant);
    }
}
```

The controller accepts the **selector** `id` and **client-selected context** `X-Active-Tenant`, then forwards them to the service. It never directly decides "the header is north, so the user has north access". Only the policy validates it against the user profile and resource.

With `@RequestHeader` defaulting to `required=true`, an authenticated user omitting the header receives **400 Bad Request** during parameter binding before entering the service. Sending a **wrong value with the header present** reaches the policy and typically receives **403**. Those are two distinct failures; neither grants access.

## 10. MockMvc: Testing Attribute Matching and Cross-Access Denials

`src/test/java/demo/DocumentAbacTest.java`:

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentAbacTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentRepository documents;

    @BeforeEach
    void resetState() {
        documents.reset();
    }

    @Test
    void anonymousCannotReadDocument() throws Exception {
        mvc.perform(get("/api/docs/101")
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void aliceCanReadDocumentInHerTenantAndDepartment()
            throws Exception {
        mvc.perform(get("/api/docs/101")
                        .with(httpBasic("alice", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isOk())
                .andExpect(content().string("doc-101:DRAFT"));
    }

    @Test
    void aliceCanReadConfidentialDocumentWithinClearance()
            throws Exception {
        mvc.perform(get("/api/docs/102")
                        .with(httpBasic("alice", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isOk())
                .andExpect(content().string("doc-102:PENDING"));
    }

    @Test
    void bobIsDeniedBecauseDepartmentAndClearanceDiffer()
            throws Exception {
        mvc.perform(get("/api/docs/102")
                        .with(httpBasic("bob", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isForbidden());
    }

    @Test
    void aliceCannotReadHigherClassification()
            throws Exception {
        mvc.perform(get("/api/docs/104")
                        .with(httpBasic("alice", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isForbidden());
    }

    @Test
    void crossTenantAccessIsDenied() throws Exception {
        mvc.perform(get("/api/docs/103")
                        .with(httpBasic("alice", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isForbidden());
    }

    @Test
    void changingTenantHeaderCannotGrantMembership()
            throws Exception {
        mvc.perform(get("/api/docs/103")
                        .with(httpBasic("alice", "demoPass!"))
                        .header("X-Active-Tenant", "south"))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingTenantSelectorIsBadRequest() throws Exception {
        mvc.perform(get("/api/docs/101")
                        .with(httpBasic("alice", "demoPass!")))
                .andExpect(status().isBadRequest());
    }

    @Test
    void legitimateSouthTenantUserCanReadHerDocument()
            throws Exception {
        mvc.perform(get("/api/docs/103")
                        .with(httpBasic("carol", "demoPass!"))
                        .header("X-Active-Tenant", "south"))
                .andExpect(status().isOk())
                .andExpect(content().string("doc-103:PENDING"));
    }

    @Test
    void aliceLacksApproverRole() throws Exception {
        mvc.perform(post("/api/docs/102/approve")
                        .with(httpBasic("alice", "demoPass!"))
                        .with(csrf())
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isForbidden());
    }

    @Test
    void carolCannotApproveHerOwnDocument() throws Exception {
        mvc.perform(post("/api/docs/103/approve")
                        .with(httpBasic("carol", "demoPass!"))
                        .with(csrf())
                        .header("X-Active-Tenant", "south"))
                .andExpect(status().isForbidden());
    }

    @Test
    void approverNeedsCsrfTokenInThisDemo() throws Exception {
        mvc.perform(post("/api/docs/102/approve")
                        .with(httpBasic("dana", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isForbidden());
    }

    @Test
    void danaCanApproveAnotherOwnersPendingDocument()
            throws Exception {
        mvc.perform(post("/api/docs/102/approve")
                        .with(httpBasic("dana", "demoPass!"))
                        .with(csrf())
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isOk())
                .andExpect(content().string("approved-102"));

        mvc.perform(get("/api/docs/102")
                        .with(httpBasic("dana", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isOk())
                .andExpect(content().string("doc-102:APPROVED"));

        // Disallow a second approval once status has changed.
        mvc.perform(post("/api/docs/102/approve")
                        .with(httpBasic("dana", "demoPass!"))
                        .with(csrf())
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isForbidden());
    }

    @Test
    void unknownDocumentFailsClosed() throws Exception {
        mvc.perform(get("/api/docs/999")
                        .with(httpBasic("dana", "demoPass!"))
                        .header("X-Active-Tenant", "north"))
                .andExpect(status().isForbidden());
    }

    @Test
    void fallbackChainDeniesOutsideApi() throws Exception {
        mvc.perform(get("/external")
                        .with(httpBasic("dana", "demoPass!")))
                .andExpect(status().isForbidden());
    }
}
```

**Expected result:** 15 JUnit tests PASS with the project and dependencies shown. This is an **expected result from static code analysis**, not a claim that tests were run on the reader's machine.

### Boundaries Proven

1. **Authentication:** anonymous requests cannot access protected documents.
2. **Subject attributes:** Bob is in the same tenant but wrong department/clearance; Alice lacks clearance for doc 104.
3. **Resource attributes:** doc 103 is in tenant south; Alice in tenant north cannot read it.
4. **Request context:** Alice changing `X-Active-Tenant` to `south` is still denied; the header only selects context, never grants membership.
5. **Context missing:** omitting the header is rejected during binding with 400.
6. **Legitimate access:** Carol reads south-tenant documents matching her clearance.
7. **Action and role:** Alice can read doc 102, yet cannot approve because she lacks `ROLE_APPROVER`.
8. **Separation of duties:** Carol is an approver, yet **cannot approve her own document**.
9. **CSRF:** Dana is authorized, yet a POST without CSRF still receives 403.
10. **Stateful resource:** Dana approves doc 102 successfully; its state becomes `APPROVED`, and a second approval is denied.
11. **Unknown resource:** policy fails closed, returning 403 per demo design.
12. **Chain coverage:** paths outside `/api/**` are denied by the fallback chain.

**Why use `@BeforeEach resetState()`?** Because documents live in memory and an approval test mutates state. Each test needs an independent baseline regardless of execution order. In integration tests with a real database, use transaction rollbacks or controlled test fixture resets.

**Do not rely solely on `@WithMockUser` to test ABAC** when you need to prove the subject profile is looked up from a real authenticated username after HTTP Basic and that filters execute. `httpBasic(...)` drives requests through the authentication and authorization flows, while separate policy unit tests efficiently cover all attribute combinations.

### 10.1. Running the Project

From `abac-document-demo`, with JDK 17+ and a compatible Gradle version:

```bash
gradle test
gradle bootRun
```

If using the Gradle Wrapper, run `./gradlew test`/`./gradlew bootRun` (macOS/Linux) or `.\gradlew.bat test`/`.\gradlew.bat bootRun` (Windows).

Try local requests:

```bash
curl -i -u alice:demoPass! \
     -H 'X-Active-Tenant: north' \
     http://localhost:8080/api/docs/101

curl -i -u alice:demoPass! \
     -H 'X-Active-Tenant: south' \
     http://localhost:8080/api/docs/103

curl -i -u bob:demoPass! \
     -H 'X-Active-Tenant: north' \
     http://localhost:8080/api/docs/102

curl -i -u carol:demoPass! \
     -H 'X-Active-Tenant: south' \
     http://localhost:8080/api/docs/103
```

Expected statuses in order: **200**, **403**, **403**, **200**. These credentials are for localhost only. In real environments, Basic auth requires HTTPS because Base64 in headers **does not protect secrets**.

To test `POST /api/docs/102/approve` with an HTTP client, send a valid CSRF token per Spring Security's mechanism. `with(csrf())` works only in MockMvc, not as a fixed token for curl. Do not disable CSRF in the demo just to get a 200 on POST.

## 11. When Should You Use AuthorizationManager for HTTP-Level ABAC?

`@PreAuthorize` fits when policy needs resource metadata loaded at the service boundary. If policy depends early on method/path/context without needing a resource object yet, you can use `AuthorizationManager<RequestAuthorizationContext>`:

```java
// API illustration fragment, not a complete standalone bean.
AuthorizationManager<RequestAuthorizationContext> manager =
        (authenticationSupplier, context) -> {

            Authentication authentication =
                    authenticationSupplier.get();

            String id = context.getVariables().get("id");

            // Decide only after checking subject/profile,
            // resource metadata, and context from trusted sources.
            boolean allowed = false; // fail closed before adding real policy
            return new AuthorizationDecision(allowed);
        };
```

Use this fragment to see the **API shape**; pasting it verbatim into config will deny every request because `allowed=false`. Implement a real policy and test it before use.

It can be wired with:

```java
// Fragment inside authorizeHttpRequests:
.requestMatchers("/api/docs/{id}").access(manager)
```

For complex resource data, however, method security is usually easier to integrate with repositories, services, and transactions. Never create two conflicting policies at HTTP and service layers and test only one layer.

### RequestAuthorizationContext Variables Are Not Trusted Claims

`context.getVariables().get("id")` returns a selector from the URL; it does not verify resource owner/tenant. Even when checking role plus resource here, an authorization manager still needs to look up the server-side resource or query a trusted PIP before deciding.

## 12. Multi-Tenant: Matching Rules to Prevent Confusion

An easy mistake:

```java
// Anti-pattern: trusting client-sent selected tenant.
if ("north".equals(request.getHeader("X-Active-Tenant"))) {
    return northRepository.findById(id);
}
```

This does not prove the user belongs to north; the client can swap the header.

Conceptually sound pattern:

```text
selectedTenant = client-selected header
allowedTenants = server-side memberships of authenticated user
resourceTenant = server-side metadata of the document

Allow further evaluation:
    selectedTenant IN allowedTenants
    AND resourceTenant == selectedTenant
    AND remaining attributes satisfy policy
```

If a user belongs to multiple tenants, `Set<String> allowedTenants` should come from a trusted source; avoid arbitrary string concatenation or substring matching (`north` must not match `north-admin`).

### Tenant-Scoped Queries at the Repository Layer

A real repository might run:

```sql
SELECT *
FROM documents
WHERE id = :id
  AND tenant_id = :trusted_active_tenant
```

This is **SQL pseudocode with named parameters**, requiring safe binding via JDBC/JPA. `:trusted_active_tenant` must be a value **verified against user memberships**, never a raw header. After querying, still verify clearance, status, and action privileges.

To reduce IDOR/BOLA risk, avoid returning cross-tenant resources and relying on a controller `if` to avoid leaking data. Depending on architecture, combine repository scoping, method security, and DB Row-Level Security.

## 13. Policies Requiring Richer Context

Not every environmental condition belongs as an `if` inside a controller. Real-world examples:

### 13.1. Time and Business Hours

For instance, allow approvals only during company working hours. Use a server `Clock` and an explicit timezone policy. Without a consistent timezone, a user in Vietnam and a UTC server can disagree on the date. In tests, inject `Clock.fixed(...)` instead of calling `LocalTime.now()` directly.

### 13.2. MFA and Step-Up Authentication

A sensitive document may require MFA within the past 5 minutes. The "MFA passed" attribute must be **verified by the authentication subsystem**, with a trusted issuer/timestamp/assurance, never a `X-MFA-Passed: true` request header.

If a user just completed MFA yet the session is invalidated, there must be a way to verify fresh context for the new request. Do not rely on a permanent `ROLE_MFA` role when policy requires freshness.

### 13.3. Network Location and Device Posture

Allowing sensitive actions only from a trusted network or compliant device posture can be an extra condition. IPs can change behind NAT, proxies, or VPNs; device posture must come from an authenticated system. Never treat `User-Agent` or raw `X-Forwarded-For` as trusted identity proof.

### 13.4. Separation of Duties

The document creator must not self-approve, even with an approver role. This is the relationship **subject.username != resource.owner**. Role checks alone cannot express this constraint.

### 13.5. Resource State and Transitions

`APPROVE` only makes sense on `PENDING` resources, `REOPEN` only on `APPROVED`, and `DELETE` may be forbidden once an invoice is issued. Action policies must inspect server-side state, and updates must re-check state atomically. Never let two concurrent requests pass the pre-check and trigger illegal state transitions.

## 14. Policy Testing: A Matrix Instead of Only Happy Paths

An ABAC policy has multiple dimensions. Testing one successful request does not prove the policy works.

Minimum matrix:

| Subject | Resource | Context | Action | Expected |
| --- | --- | --- | --- | --- |
| Alice (north/finance/2) | Doc 101 (north/finance/1) | north | READ | ALLOW |
| Alice (north/finance/2) | Doc 102 (north/finance/2) | north | READ | ALLOW |
| Bob (north/sales/1) | Doc 102 (north/finance/2) | north | READ | DENY |
| Alice | Doc 104 (minClearance 3) | north | READ | DENY |
| Alice | Doc 103 (south) | north | READ | DENY |
| Alice | Doc 103 (south) | south sent by client | READ | DENY |
| Carol (south/finance/3) | Doc 103 | south | READ | ALLOW |
| Alice (no APPROVER) | Doc 102 PENDING | north | APPROVE | DENY |
| Carol (APPROVER, owner) | Doc 103 PENDING | south | APPROVE | DENY |
| Dana (APPROVER, non-owner) | Doc 102 PENDING | north | APPROVE | ALLOW |
| Dana | Doc 102 after APPROVED | north | APPROVE | DENY |
| Anonymous | Any protected document | any | READ | DENY |

### Testing the Policy Bean Directly

Alongside MockMvc, you can unit test `DocumentPolicy` with controlled `Authentication` instances. Unit tests cover many attribute combinations without sending HTTP requests. However, unit tests alone do not prove `@EnableMethodSecurity` and `@PreAuthorize` are wired properly through the Spring proxy; integration tests are still required.

### Property-Based and Mutation Tests

With complex policies, hundreds of combinations arise across tenant, role, department, clearance, status, ownership, action, and time. Property-based testing helps express invariants such as:

- Changing a resource's tenant to another tenant **never turns DENY into ALLOW**.
- Lowering a user's clearance never unlocks more sensitive documents.
- Self-approval is never permitted when SoD policy forbids it.
- Nonexistent resources always fail closed.
- Removing a required condition from the policy causes tests to fail (mutation testing).

Test each constraint **independently**; if one test case has both the wrong tenant and the wrong role, it does not prove both conditions are checked.

## 15. Caching, Consistency, and Auditing for ABAC

### 15.1. Avoiding Stale Privileges

If caching `UserProfileDirectory` or `DocumentRepository`, understand TTL and invalidation. A user removed from a tenant whose cache entry still marks them as a member can retain access until the cache expires. For sensitive actions, policies may need to bypass the cache or check a permission version/epoch.

### 15.2. PIP Latency Considerations

Loading user profiles and document metadata per request can cause N+1 queries. Attributes may be batched/cached without weakening security. Measure latency, apply rate limits and circuit breakers, and fail closed when a PIP is unavailable. In multi-service architectures, a central policy engine adds a network hop.

### 15.3. Auditing Without Leaking Data

Record the verified actor, an appropriate resource identifier, action, policy version, decision, and request correlation ID. Never log access tokens, passwords, session IDs, secret headers, or full document contents. When a request is denied due to cross-tenant access, audit may record the security event while responses must not leak metadata about the other tenant.

### 15.4. Policy Versioning

ABAC is critical business logic. Changing `clearance>=2` to `>=1` can expose sensitive data; require code review, automated tests, change approval, canary rollouts, and rollback capability. Across multiple services, prevent policy drift that produces contradictory decisions.

### 15.5. Immediate Effect vs. Eventual Consistency

Changing roles/memberships cannot always synchronize every token/cache/session instantaneously. Define a revocation SLA and strategy for sensitive actions, such as real-time state lookups or session revocation. Never claim "ABAC guarantees immediate revocation" simply because the policy code checks a tenant attribute.

## 16. Common Mistakes

| Mistake | Risk | Fix |
| --- | --- | --- |
| Checking only `authenticated()` for `/api/docs/{id}` | IDOR/BOLA | Match resource tenant/owner/clearance |
| Treating `X-Active-Tenant` as authority | User changes tenant header to read data | Compare header against server-side memberships |
| Using `X-Role` as roles | Client self-elevates privileges | Source authorities from verified Authentication/IdP |
| Checking only `APPROVER` role | Self-approval or cross-tenant approval | Add resource state/owner/tenant |
| Trusting `resource.tenant` from request body on update | Attacker alters metadata to pass policy | Load real resource and protect mutations |
| Placing policy only in one controller | GraphQL/jobs/other services bypass it | Enforce at service boundary or centralized PEP |
| Forgetting `@EnableMethodSecurity` | `@PreAuthorize` never activates | Enable it and run integration tests |
| Calling `this.securedMethod()` | Self-invocation bypasses AOP proxy | Design bean boundaries and test |
| Relying on `@PostAuthorize` after side effects | Check runs too late | Pre-check and use transactions/atomic updates |
| Allowing on missing profile or resource | Fail-open | Fail closed and handle unavailability explicitly |
| Combining wrong tenant and wrong role in one test | Does not prove each condition works | Vary one attribute per test |
| Trusting old JWT claims indefinitely | Stale permissions | Revoke, expire, refresh, or look up server-side |
| Checking PENDING then updating non-atomically | TOCTOU / double approval | Conditional update / optimistic locking |
| Blindly trusting `X-Forwarded-For` | Network context spoofing | Trusted proxy / forwarded-header config |
| Using client clock for time-based policy | Client spoofs time | Server `Clock` and explicit timezone |
| Letting deny errors return cross-tenant metadata | Information disclosure | Consistent error contract / 404 masking |

## 17. Secure Implementation Checklist

- [ ] Authentication verifies the subject (never take user from raw headers).
- [ ] Tenant memberships/roles/clearance come from sufficiently trusted sources.
- [ ] Resource metadata is loaded by ID from a server-side repository; never trust request-supplied attributes.
- [ ] Action is defined by the operation/service, not arbitrary query parameters.
- [ ] Client-provided request context is validated; headers are never treated as authorities.
- [ ] Policy expresses tenant, department, clearance, ownership, status, and role where needed.
- [ ] `@EnableMethodSecurity` is enabled and `@PreAuthorize` actually executes via the Spring proxy.
- [ ] Both HTTP security and method security have deny-by-default fallbacks.
- [ ] No bypasses via self-invocation, background jobs, GraphQL, or other service callers.
- [ ] CSRF is properly configured for state-changing browser/session requests.
- [ ] Unknown resources, missing profiles, and PIP errors never permit access.
- [ ] Resource transitions / check+update use transactions/locking/conditional writes.
- [ ] Role/tenant changes trigger policy cache invalidation and revocation.
- [ ] Policy unit tests and MockMvc integration tests cover allow/deny independently.
- [ ] Audit logs never record secrets or sensitive document payloads.
- [ ] Policy versioning, code review, and rollback procedures are in place.

## 18. Self-Check Questions

1. **How does ABAC differ from RBAC?** ABAC evaluates multiple subject/resource/action/environment attributes; RBAC focuses mainly on roles.
2. **Is the APPROVER role enough to approve any document?** No. Tenant, classification, state, ownership, SoD, and other conditions still apply.
3. **Can frontend-sent X-Active-Tenant be trusted?** Only as a context selection, never as proof the user is a member of that tenant.
4. **Why load the document from the DB during authorization?** To verify trusted tenant, owner, status, and classification.
5. **Does receiving an id from the URL mean the user owns the document?** No; the id is a selector and requires object-level authorization.
6. **Where should resource policies be placed?** Usually at the service/method authorization boundary; HTTP rules add authentication and coarse access checks.
7. **Does `@PreAuthorize` run without enabling method security?** No; `@EnableMethodSecurity` must be present in an active configuration.
8. **What is the self-invocation issue?** Internal calls via `this` can bypass the Spring AOP proxy and security interceptors.
9. **Is checking permissions after sending email or updating the DB enough?** No, side effects have already occurred; pre-check and update safely.
10. **If the user directory is down, may access be temporarily allowed?** Never fail open; define an explicit error/availability policy.
11. **What if two concurrent requests try to transition a document from PENDING to APPROVED?** Atomic transitions/DB locking are needed, not just pre-checks.
12. **Can X-MFA-Passed: true prove MFA?** No, unless verified via a trusted mechanism; normally rely on the identity subsystem's authentication context.
13. **What if a token's signature is valid, yet tenant membership was revoked?** Plan refresh/revocation/caching; unexpired claims can be stale.
14. **What should ABAC tests cover beyond the happy path?** Cross-tenant, missing clearance/role, wrong department, owner self-approval, invalid context, unknown resource, CSRF, and concurrency.
15. **Must RBAC be abandoned when adopting ABAC?** No. Roles can remain attributes inside ABAC policies.

**Key takeaway:** Resource access depends not only on "who the user is", but also "who owns the resource, which tenant it belongs to, how sensitive it is, what state it is in, which action is requested, and which request context is verified". With Spring Security Servlet, **authenticate the subject first**, **load resource attributes from the server**, **verify request context**, and enforce policy at a non-bypassable boundary such as `@PreAuthorize` on the service. Fail closed on missing data, test every dimension independently, and update resources atomically to prevent TOCTOU.
