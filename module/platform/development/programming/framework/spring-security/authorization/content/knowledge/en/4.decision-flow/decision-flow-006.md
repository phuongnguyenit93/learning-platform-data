# Allow, Deny, Abstain, and Default Handling in Spring Security

> **Context:** Authorization decision flow in Spring Security for Servlet/Spring MVC applications. This lesson explains **ALLOW/GRANT**, **DENY**, and **ABSTAIN/no decision**, how multiple policies coordinate, and how to design the final decision point with the **default deny** principle.

## 1. Three states in an authorization decision

When a user sends a request, the system must answer: **is this principal allowed to perform this action on this resource?** A single permission checker can produce three types of outcomes:

| State | Meaning from the checker | Example |
| --- | --- | --- |
| **ALLOW / GRANT** | The policy explicitly determines the request meets allow conditions | Alice is the document owner, so she can view her document |
| **DENY** | The policy explicitly determines the request is forbidden or ineligible | Alice lacks the `report:write` permission to edit the report |
| **ABSTAIN / NO DECISION** | The policy **does not decide** this request; usually because it is not responsible for that situation | A rule handling only financial documents receives a request to read an HR record |

These are **states of a single policy/authorization manager**, not necessarily the final HTTP response. Specifically:

- **ALLOW** does not mean "bypass all security layers". One checker may allow while another layer (method security, tenant conditions, record state checks) can still deny.
- **DENY** is a disallow decision. In Spring Security, it typically leads to a security exception; from there, exception handling returns 401, 403, or a redirect depending on authentication context.
- **ABSTAIN is not ALLOW**; nor is it **automatically equal to DENY** in every API. It signals **no conclusion yet from the current checker**, so clear combination and terminal handling rules are required.

This can be expressed simply:

~~~text
policy(subject, action, resource, context)
    |
    +-- ALLOW   -> this policy agrees to grant permission
    +-- DENY    -> this policy denies permission
    +-- ABSTAIN -> this policy has no conclusion

finalDecision(...) -> ALLOW or DENY
                   (ABSTAIN must be handled deliberately)
~~~

**Design principle:** *a sensitive operation may only execute when the system obtains a valid grant decision according to the policy contract*. Never treat "no rule blocked it" as proof of permission.

## 2. Correctly identifying why there is no decision

The following cases are often confused:

1. **Rule does not apply:** a "payment limit control" rule receives a profile-viewing request. If the system supports scoped rules, it can return `ABSTAIN` so another rule handles it.
2. **No matching URL rule found:** request `/api/new-feature` has not been declared in `authorizeHttpRequests`. This is a **configuration gap**, needing a fallback such as `anyRequest().denyAll()`.
3. **Matched a rule but user lacks permission:** `hasAuthority("invoice:approve")` returns **DENY**, not abstain, when the authority is missing.
4. **Unauthenticated:** when a protected endpoint requires login, missing credentials are not a valid reason to "abstain and let it pass"; Spring Security invokes the configured authentication entry point.
5. **Missing or untrusted data:** record does not exist, tenant/owner could not be read, or policy service failed. For security-sensitive operations, you must **fail closed** (deny or return an error without executing the operation), rather than interpreting missing data as ALLOW.
6. **Intentionally public endpoint:** `permitAll()` is an **explicit allow rule**; it is not synonymous with "writing no rule".
7. **Technical policy failure:** a timeout or exception from the permission store is not an ALLOW vote. The HTTP response may be 5xx or 403 per system contract, but **never execute the protected operation**.

Distinction table:

| Situation | Logical result to observe | Practical handling |
| --- | --- | --- |
| Valid grant exists, mandatory conditions met | ALLOW | Proceed to endpoint/service |
| Authority/role not met | DENY | Deny; return appropriate error |
| Specialized rule not responsible for request | ABSTAIN | Delegate to another suitable rule or fallback |
| No HTTP rule declared for the path | No matching policy | Apply `anyRequest().denyAll()` |
| Policy needs data but data store fails | Cannot evaluate safely | Halt request; never implicitly allow |
| URL declared public | ALLOW from `permitAll()` | Allow through; other protections may still apply |

## 3. Decision flow on the Servlet side

Conceptual flow for a protected request:

~~~text
Client
  |
  v
Spring Security filter chain
  |
  +-- Authentication filters
  |     -> identifies caller, sets up SecurityContext if applicable
  |
  +-- AuthorizationFilter
  |     -> selects AuthorizationManager matching the request
  |     -> AuthorizationResult:
  |          granted=true  -> allow request to proceed
  |          granted=false -> deny, handle exception
  |          null          -> manager made no decision
  |                           (must not be treated as global DENY if
  |                            there is no clear fallback mechanism)
  |
  +-- DispatcherServlet -> Controller
          |
          +-- Method security (@PreAuthorize), if enabled
          |     -> may independently continue allowing or denying
          |
          +-- Business data/logic
                -> tenant, ownership, state, other conditions
~~~

The diagram only shows checkpoints relevant to authorization decisions, not a complete list of every filter. `AuthorizationFilter` works with `AuthorizationManager`; `ExceptionTranslationFilter` participates in turning authentication/authorization exceptions into HTTP responses.

**Important:** never rely on a single checkpoint and assume everything downstream is safe. For example, HTTP may allow `GET /api/documents/101` because the caller is logged in, yet the service must still verify whether the caller is allowed to read **document 101**.

### 401 and 403 are not aliases for ALLOW/DENY/ABSTAIN

- **401 Unauthorized** usually appears when authentication is required but credentials were not provided/accepted, e.g. with HTTP Basic.
- **403 Forbidden** usually appears when an authenticated user lacks permission or hits a deny rule.
- With form login, an unauthenticated request may receive a **302 redirect** to the login page.
- CSRF, other filters, and custom exception handlers can also affect status codes.

Therefore: **ABSTAIN has no dedicated "default HTTP status"**. The HTTP outcome depends on the **final decision** and the exception-handling context.

## 4. `AuthorizationManager` in modern Spring Security

Spring Security uses the `AuthorizationManager<T>` API in place of the older `AccessDecisionManager`/`AccessDecisionVoter` customization model for many use cases.

In Spring Security **6.5**, the method:

`AuthorizationResult authorize(Supplier<Authentication> authentication, T object)`

can return an authorization result or **`null` when making no decision**. Common implementations return `AuthorizationDecision`, carrying the boolean state via `isGranted()`.

| Manager return value | Meaning |
| --- | --- |
| `new AuthorizationDecision(true)` | ALLOW from manager |
| `new AuthorizationDecision(false)` | DENY from manager |
| `null` | ABSTAIN / undecided |

The `check(Supplier<Authentication>, T)` API returns `AuthorizationDecision`, but in Spring Security 6.5 it is marked **deprecated** in favor of `authorize`; specific lambda/inheritance methods should be checked against your version when implementing custom managers.

`AuthorizationManager#verify(...)` runs evaluation and throws `AccessDeniedException` on a negative decision. **Do not assume `verify`, `AuthorizationFilter`, or every interceptor automatically turns `null` into DENY**. If your application policy requires denying when undecided, make the terminal manager/aggregator **return an explicit `AuthorizationDecision(false)`**.

### Why is `null` useful in intermediate managers?

Suppose a system has:

- Rule A checking permission to read financial documents.
- Rule B checking permission to view HR records.
- Rule C checking system administration permissions.

Rule A should neither grant nor deny HR records if it is not responsible for that resource type; it can abstain so the aggregator evaluates Rule B. **However, if A, B, and C all abstain, the system must have an explicit default.** These are two distinct jobs: *knowing which rule applies* and *making the final allow decision*.

## 5. Combining multiple decisions: OR, AND, deny overrides

When combining policies, choose an explicit contract. Common strategies include:

### 5.1. "Any permit" — only one granting rule needed

A request may read when the caller **is the owner or was granted READ sharing**. This is business OR composition. However, absolute prohibitions (such as cross-tenant) must not be overridden by a weaker grant.

### 5.2. "All required" — every mandatory condition must pass

Editing an invoice may require **having `invoice:write` authority, same tenant, and `DRAFT` state**. If just one condition denies, editing is disallowed. Mandatory conditions must be evaluated; **an unevaluated condition cannot implicitly become true**.

### 5.3. "Deny overrides" — deny takes precedence over permit

For mandatory blocking constraints (tenant boundary, locked account, forbidden resource), you can define a combination rule:

1. If any mandatory constraint returns **DENY**: result is **DENY**.
2. If there is no deny and at least one **ALLOW** from an applicable granting source: result is **ALLOW**.
3. If all rules **ABSTAIN**: result is **DENY** (default deny).

This is **a combination policy chosen by the application**, not a claim that every Spring Security API aggregates votes in this exact order.

### 5.4. `AuthorizationManagers` factory

Spring Security provides `AuthorizationManagers.allOf(...)` and `anyOf(...)` factories. Starting in Spring Security 6.3, overloads accepting an `AuthorizationDecision allAbstainDefaultDecision` let you **set an explicit default when there are no managers or all abstain**:

~~~java
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

// Illustrative fragment inside configuration with managers first, second:
AuthorizationManager<RequestAuthorizationContext> oneOf =
    AuthorizationManagers.anyOf(
        new AuthorizationDecision(false), first, second
    );

AuthorizationManager<RequestAuthorizationContext> allRequired =
    AuthorizationManagers.allOf(
        new AuthorizationDecision(false), first, second
    );
~~~

This is a **fragment**, not a standalone runnable class: `first` and `second` must be declared with the same manager type. Overloads with a fallback avoid relying on implicit behavior when **all** rules abstain. Never assume OR or AND automatically implements business "deny overrides": read the factory contract, especially when rules can abstain.

Overloads without a default parameter also exist and have their own rules for empty/all-abstain managers. For systems requiring *fail closed*, use the explicit overload or write your own aggregator and test all-abstain cases.

## 6. Plain Java 17 example: ABSTAIN resolved to DENY at the end

The standalone example below has three rules:

- `tenantBoundary`: denies cross-tenant access, otherwise **ABSTAINs** for same tenant (this rule never grants permission by itself).
- `ownerGrant`: grants permission if owner, otherwise **ABSTAINs**.
- `sharedReaderGrant`: grants **READ** if shared, otherwise **ABSTAINs**.
- `finalDecision`: **DENY** if tenant check denies; **ALLOW** if a valid grant exists; **DENY** when all abstain.

This prevents a document permission from applying across tenants or letting an unshared user view a document.

Create file **`DecisionFlowDemo.java`**:

~~~java
import java.util.List;
import java.util.Set;

public class DecisionFlowDemo {

    enum Decision { ALLOW, DENY, ABSTAIN }
    enum Action { READ, EDIT }

    record Subject(String username, String tenant) {}

    record Document(
        String id,
        String tenant,
        String owner,
        Set<String> sharedReaders
    ) {}

    @FunctionalInterface
    interface Rule {
        Decision decide(Subject subject, Action action, Document document);
    }

    static Decision tenantBoundary(
            Subject subject, Action action, Document document) {
        if (!subject.tenant().equals(document.tenant())) {
            return Decision.DENY;
        }
        return Decision.ABSTAIN;
    }

    static Decision ownerGrant(
            Subject subject, Action action, Document document) {
        return subject.username().equals(document.owner())
            ? Decision.ALLOW : Decision.ABSTAIN;
    }

    static Decision sharedReaderGrant(
            Subject subject, Action action, Document document) {
        return action == Action.READ
                && document.sharedReaders().contains(subject.username())
            ? Decision.ALLOW : Decision.ABSTAIN;
    }

    static Decision finalDecision(
            Subject subject, Action action, Document document) {
        List<Rule> rules = List.of(
            DecisionFlowDemo::tenantBoundary,
            DecisionFlowDemo::ownerGrant,
            DecisionFlowDemo::sharedReaderGrant
        );

        boolean hadGrant = false;
        for (Rule rule : rules) {
            Decision vote = rule.decide(subject, action, document);
            if (vote == Decision.DENY) {
                return Decision.DENY; // Mandatory constraint denies.
            }
            if (vote == Decision.ALLOW) {
                hadGrant = true;
            }
        }

        // All ABSTAIN -> DENY, no implicit grant.
        return hadGrant ? Decision.ALLOW : Decision.DENY;
    }

    static void show(Subject s, Action a, Document d) {
        System.out.println(
            s.username() + " " + a + " " + d.id()
                + " = " + finalDecision(s, a, d)
        );
    }

    public static void main(String[] args) {
        Subject alice = new Subject("alice", "acme");
        Subject bob = new Subject("bob", "acme");
        Subject carol = new Subject("carol", "orbit");
        Subject maya = new Subject("maya", "acme");

        Document doc101 = new Document(
            "doc-101", "acme", "alice", Set.of("bob")
        );

        show(alice, Action.EDIT, doc101);
        show(bob, Action.READ, doc101);
        show(bob, Action.EDIT, doc101);
        show(carol, Action.READ, doc101);
        show(maya, Action.READ, doc101);

        System.out.println(
            "ownerRule(bob) = " + ownerGrant(bob, Action.READ, doc101)
        );
    }
}
~~~

Compile and run with JDK 17+ in the file's directory:

~~~bash
javac DecisionFlowDemo.java
java DecisionFlowDemo
~~~

**Exact stdout:**

~~~text
alice EDIT doc-101 = ALLOW
bob READ doc-101 = ALLOW
bob EDIT doc-101 = DENY
carol READ doc-101 = DENY
maya READ doc-101 = DENY
ownerRule(bob) = ABSTAIN
~~~

Explanation:

- Alice is allowed to EDIT because she is the owner and in the right tenant.
- Bob is allowed to READ because he is shared; for EDIT there is no grant, so **every rule outside the tenant boundary abstains** and the final decision is DENY.
- Carol is DENIED due to a different tenant, even if other rules might grant permission under simpler conditions.
- Maya is in the same tenant but neither owner nor shared. The tenant rule merely abstains; the overall system still **DENYs**.
- `ownerRule(bob) = ABSTAIN` is **one rule's vote**, whereas `bob READ doc-101 = ALLOW` is the **final verdict** because the sharing rule granted access.

This is a policy simulation program and **does not use Spring Security**; it clarifies logic before wiring into the framework. In production, load tenant, owner, and sharing lists from a trusted server source, handle data errors, manage permission lifecycles, and test permission changes.

## 7. Spring Boot Java 17+: fallback DENY when a manager cannot handle a route

In a Servlet backend, `authorizeHttpRequests` establishes an explicit HTTP policy. In the example below:

- `GET /public/info` is **explicitly ALLOWED** via `permitAll()`.
- `GET /api/reports/summary` is evaluated by the custom manager for `report:read` and returns ALLOW/DENY.
- `GET /api/reports/archived` enters the custom manager, but the internal policy **has no matching rule** (`candidate = null`); **the terminal manager converts it to DENY**.
- `GET /other` matches none of the above matchers and is blocked by `anyRequest().denyAll()`.
- No API request is opened merely because the policy does not know how to handle it.

Create a Maven application with **Java 17+** and **Spring Web** and **Spring Security** dependencies (e.g., compatible Spring Boot 3.x). Put the code in **`src/main/java/com/example/decision/DecisionApplication.java`**:

~~~java
package com.example.decision;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DecisionApplication {

    public static void main(String[] args) {
        SpringApplication.run(DecisionApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthorizationManager<RequestAuthorizationContext> reportPolicy)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/info").permitAll()
                .requestMatchers("/api/reports/**").access(reportPolicy)
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    AuthorizationManager<RequestAuthorizationContext> reportPolicy() {
        return (authentication, context) -> {
            String route = context.getRequest().getServletPath();

            // Internal rule only handles /api/reports/summary.
            AuthorizationDecision candidate = null;
            if ("/api/reports/summary".equals(route)) {
                boolean canRead = authentication.get().getAuthorities()
                    .stream()
                    .anyMatch(a -> "report:read".equals(a.getAuthority()));
                candidate = new AuthorizationDecision(canRead);
            }

            // Ensure the final manager does not let ABSTAIN leak out.
            return candidate != null
                ? candidate
                : new AuthorizationDecision(false);
        };
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .authorities("report:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .authorities("ROLE_USER")
            .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }

    @RestController
    static class ReportController {

        @GetMapping("/public/info")
        String info() {
            return "public info";
        }

        @GetMapping("/api/reports/summary")
        String summary() {
            return "quarterly summary";
        }

        @GetMapping("/api/reports/archived")
        String archived() {
            return "archived report";
        }

        @GetMapping("/other")
        String other() {
            return "unlisted endpoint";
        }
    }
}
~~~

The code above uses the `AuthorizationManager<RequestAuthorizationContext>` API as supported by Spring Security 6.x. The manager lambda returns an `AuthorizationDecision` for every request; `candidate` represents an internal result that may lack a decision.

**Why not return `null` directly to `AuthorizationFilter`?** At the API level, `null` indicates abstain rather than a negative decision. The endpoint of a security policy needs an explicit outcome so it does not implicitly depend on how other interceptors/managers handle abstain. This is intentional *fail closed*.

**Example scope:** paths are compared via `getServletPath()` assuming the app runs at the default context path with standard servlet mappings. If your app uses a context path, gateway rewrites, dynamic path matchers, or multiple servlets, use appropriate matcher/path variable metadata and test actual routing. The code uses GET only to demonstrate decisions without mutating data; write operations also require action authorization and CSRF appropriate to the authentication mechanism.

### Run and observe

From the project directory:

~~~bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
~~~

Test each request once the app is running at `localhost:8080`:

~~~bash
curl -i http://localhost:8080/public/info
curl -i http://localhost:8080/api/reports/summary
curl -i -u alice:demo123 http://localhost:8080/api/reports/summary
curl -i -u bob:demo456 http://localhost:8080/api/reports/summary
curl -i -u alice:demo123 http://localhost:8080/api/reports/archived
curl -i -u alice:demo123 http://localhost:8080/other
~~~

| Request | Expected HTTP | What is illustrated |
| --- | --- | --- |
| Public, no credentials | 200, `public info` | `permitAll()` is an intentional ALLOW |
| Summary, no credentials | 401 (HTTP Basic) | Authentication/authority required |
| Summary, Alice | 200, `quarterly summary` | Has `report:read`; manager returns ALLOW |
| Summary, Bob | 403 | Missing `report:read`; manager returns DENY |
| Archived, Alice | 403 | Internal rule abstains; terminal manager returns DENY |
| `/other`, Alice | 403 | Matches no prior matcher, `anyRequest().denyAll()` |

**Status code note:** with form login, an unauthenticated request may receive a redirect. When anonymous accesses a `denyAll()` endpoint, `ExceptionTranslationFilter` may invoke the corresponding entry point instead of 403; the table uses Alice's account for the two fallback cases so DENY is clearly observed.

The passwords are for demo purposes only—never use them in production; HTTP Basic must be paired with HTTPS in production.

## 8. `permitAll`, `denyAll`, and `anyRequest` are explicit decisions

An auditable configuration:

~~~java
// Configuration fragment, placed inside http.authorizeHttpRequests:
.requestMatchers("/public/**").permitAll()
.requestMatchers("/admin/**").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
.anyRequest().denyAll()
~~~

Things to understand:

- Matchers are evaluated **in declaration order**; the first matching rule is used.
- `permitAll()` allows matching requests, but does not disable the entire security filter chain or all method/domain authorization layers.
- `denyAll()` forbids requests under that rule.
- `authenticated()` only requires an authenticated identity per Spring Security logic; it does not check specific roles or ownership.
- `anyRequest().denyAll()` is the **fallback for undeclared URLs**. It prevents new endpoints from being accidentally left open.
- Placing a broad matcher like `/api/**` before a specific matcher `/api/admin/**` means the specific matcher may never be reached. Order rules from specific to broad.

**Having an explicit HTTP fallback does not yet guarantee method and data safety.** For example, `/api/docs/{id}` may require `authenticated()`, while the service must verify whether the user has permission on **this specific doc id** and **this tenant**.

## 9. The ABSTAIN state in the legacy voter model

Before `AuthorizationManager`, Spring Security used `AccessDecisionManager` and `AccessDecisionVoter` (now legacy/deprecated in modern branches).

`AccessDecisionVoter` had three numeric constants:

- `ACCESS_GRANTED` — affirmative vote.
- `ACCESS_DENIED` — negative vote.
- `ACCESS_ABSTAIN` — voter does not apply / abstains from deciding.

Legacy `AccessDecisionManager` implementations had strategies such as:

| Legacy manager | Aggregation idea |
| --- | --- |
| `AffirmativeBased` | At least one GRANT vote allows under affirmative rules |
| `UnanimousBased` | Denied if any DENY vote exists; evaluates grants per unanimous rules |
| `ConsensusBased` | Compares GRANT/DENY votes; breaks ties per configuration |
| `AbstractAccessDecisionManager` | Provides configuration for when **all voters abstain**; typically denies by default |

Strategies had their own options and conditions; the table states the **general idea**, not a full edge-case specification. `ACCESS_ABSTAIN` in legacy voters differs in data type from `null` in modern `AuthorizationManager`, even though both express "no decision". **Never copy an old voter all-abstain configuration into the new API assuming identical behavior.**

When encountering `allowIfAllAbstainDecisions` in older documentation, recognize it as an option of the legacy model. For new code, prefer `AuthorizationManager`, explicit defaults, and tests covering all outcomes.

## 10. Building a "default deny" policy across layers

**At HTTP:** declare `anyRequest().denyAll()` for unmatched requests. With custom matchers, ensure "policy does not apply" never falls through to a grant.

**At methods:** guard sensitive service operations with `@EnableMethodSecurity` and `@PreAuthorize`/`@PostAuthorize` or an appropriate manager. Methods **without security annotations** are not automatically forbidden just by enabling method security; design coverage and tests. `@PreAuthorize("hasAuthority('invoice:approve')")` only checks the permission; checking an invoice instance may also require owner/tenant/state.

**At data:** never fetch data first and only check permissions after returning a response. Especially for `LIST/SEARCH`, filter by tenant/permissions directly in the query to avoid leaking record counts, pagination, or unauthorized details.

**On technical errors:** if the server cannot verify permissions due to a database/policy-engine failure, choose **fail-closed behavior** and return an appropriate error. Never catch all exceptions and return `new AuthorizationDecision(true)`, or interpret `null` as ALLOW "to avoid interrupting service".

**On permission changes:** sessions/JWTs/caches may retain old authorities. Ensure revocation, refresh, TTL, and test coverage when a user loses a role or switches tenants.

## 11. Mandatory test matrix

Do not test only "valid user gets 200". Also test undecided states:

| Scenario | Expected decision | Why |
| --- | --- | --- |
| Rule matches and user has authority | ALLOW | Explicit permission grant |
| Rule matches but missing authority | DENY | Explicit denial |
| Internal rule does not recognize resource type | ABSTAIN at rule layer, **DENY at end** | Fail-closed fallback |
| All rules abstain | DENY at end | No evidence of a grant |
| Accessing new endpoint without matcher | DENY | `anyRequest().denyAll()` |
| Declared public endpoint | ALLOW | `permitAll()` |
| Valid at HTTP, wrong service permission | DENY | Defense in depth across layers |
| User has right role but different tenant | DENY | Data policy |
| Permission database unavailable | Do not execute operation | Must not fail open |
| Client sends fake role/owner | DENY | Permission data must be verified server-side |

When composing `AuthorizationManagers.anyOf/allOf`, write tests for **ALLOW + ABSTAIN**, **DENY + ABSTAIN**, **ALLOW + DENY**, **all ABSTAIN**, and **no managers**; expectations follow the chosen combinator contract. The goal is to prove **no combination accidentally allows a request that should be forbidden**.

## 12. Common mistakes

1. **"ABSTAIN means not forbidden, so allow."** Wrong. It means "no conclusion yet"; an explicit final decision is needed.
2. **"If no route matcher is found, Spring Security probably denies automatically."** Never rely on that assumption. Declare `anyRequest().denyAll()`.
3. **"Only DENY is dangerous; null is harmless."** The danger lies in an aggregator that mishandles abstain. Create a DENY fallback and test it.
4. **"If there is one ALLOW, access is definitely granted."** Tenant boundaries, method security, or other mandatory prohibitions may still remain.
5. **"Returning 401 means permission denied."** 401 typically relates to authentication, whereas 403 typically denotes permission denial for an authenticated user; the final response depends on entry point/handler.
6. **"`permitAll` and a missing rule mean the same thing."** Wrong: one is an intentionally declared grant, the other is a configuration gap.
7. **"Adding `@EnableMethodSecurity` protects every service method automatically."** No: you must declare policies on the operations that need checking.
8. **"If the authorization service errors, allow temporarily."** That is fail-open behavior and can leak data. Halt the protected action whenever permissions cannot be verified.
9. **"Permission on an endpoint means permission on all records."** Permissions must be checked per resource instance, tenant, ownership, and state.
10. **"All-abstain behavior in legacy voters is identical to the new manager."** Not guaranteed; APIs and default strategies differ.

## 13. Knowledge self-check

**Q1.** Rule A handles only invoices and receives a request to open an HR record. What should it return in a multi-rule design?  
**Answer:** ABSTAIN (not applicable). The terminal point must have a matching rule or default DENY.

**Q2.** Owner rule abstains, sharing rule grants ALLOW, and no blocking constraint exists. Final decision under the example OR grant policy?  
**Answer:** ALLOW, because the sharing grant is valid.

**Q3.** Owner rule grants ALLOW, but tenant boundary returns DENY. Under deny-overrides policy?  
**Answer:** DENY. Cross-tenant access must never be allowed.

**Q4.** All rules abstain and the system wants to fail closed. What must the terminal point return?  
**Answer:** Explicit DENY, e.g., `new AuthorizationDecision(false)`.

**Q5.** `@PreAuthorize("hasAuthority('report:read')")` encounters a logged-in user missing the authority. Is this ABSTAIN or DENY?  
**Answer:** DENY for the applied permission condition.

**Q6.** Endpoint `/api/new` is not in any HTTP rule and `anyRequest().denyAll()` is configured. Result?  
**Answer:** DENY. The HTTP status code may vary depending on whether the caller is authenticated.

**Q7.** Does `AuthorizationDecision(true)` automatically bypass all `@PreAuthorize` and tenant checks?  
**Answer:** No. Remaining checking layers can deny independently.

**Q8.** Why must you test the case where all managers abstain?  
**Answer:** To uncover execution paths missing a policy and confirm an intentional fallback, preventing fail-open gaps.

**Remember:** A policy can return **ALLOW**, **DENY**, or **ABSTAIN**. **ABSTAIN is an intermediate state**, while final access must be decided by an explicit policy. For protected resources, design **deny by default**, allowing access only when valid grant conditions have been verified.

## Official documentation

- Spring Security 6.5 — Authorization Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html
- Spring Security 6.5 — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — `AuthorizationManager` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html
- Spring Security 6.5 — `AuthorizationManagers` composition APIs: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManagers.html
- Spring Security 6.5 — `AuthorizationResult` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationResult.html
- Spring Security 6.5 — `AbstractAccessDecisionManager` (legacy): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/vote/AbstractAccessDecisionManager.html
