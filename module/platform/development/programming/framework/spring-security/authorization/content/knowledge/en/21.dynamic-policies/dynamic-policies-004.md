# Integrating a Policy Decision Service Using `AuthorizationManager` in Spring Security

## 1. Why is a policy decision service needed?

An invoice processing system uses Spring Security. Approval rules are no longer "having role `APPROVER` means you can approve everything":

- The caller must be authenticated and hold the functional authority `invoice:approve`.
- The invoice must belong to a tenant the caller is authorized to work in.
- The invoice must be in `PENDING` state.
- The amount must not exceed the caller's approval limit.
- The invoice creator must not self-approve (*maker–checker*).
- Policies may change at runtime, operated by a **policy decision service**.
- If the policy decision service does not respond, the system **must not allow by default**.

This is a **dynamic policy**: decisions depend on identity, resource, action, context, and current state. Using only:

```java
@PreAuthorize("hasAuthority('invoice:approve')")
```

is **insufficient**; this annotation does not automatically know the tenant, invoice status, approval limit, maker–checker rule, or external policies.

Spring Security provides `AuthorizationManager<T>` to connect an **enforcement point** to a **decision service**. You can write a custom `AuthorizationManager` to query an in-process policy engine, an independent PDP service via HTTP/gRPC, or another policy system.

This Knowledge lesson belongs to the **Dynamic Policies** group of the *Spring Security – authorization* module. The focus is **integrating a policy decision service with `AuthorizationManager`**, rather than merely listing static roles or replacing a manual `canApprove()` boolean.

After this lesson, you will be able to:

1. Distinguish **PEP, PDP, PIP, PAP** and trust boundaries.
2. Understand `AuthorizationManager<T>`, `Supplier<Authentication>`, `AuthorizationDecision`, and abstain results.
3. Convert a `MethodInvocation` into a policy evaluation request with `subject`, `resource`, `action`, and `context`.
4. Build an `AuthorizationManager<MethodInvocation>` that calls `PolicyDecisionClient` and returns **explicit allow/deny**.
5. Register a custom **method interceptor** with a pointcut for the `@RequiresInvoiceApproval` annotation.
6. See how to extend the same mindset to **HTTP `AuthorizationManager<RequestAuthorizationContext>`**.
7. Run a **Java 17 + Spring Boot 3.5.x + Spring Security 6.5.x** example with full source code, sample data, expected stdout, and integration tests.
8. Control **PDP timeouts, 5xx responses, policy versions, caching, multi-tenancy, auditing, TOCTOU**, and limitations of remote authorization.
9. Recognize `AuthorizationManagers.allOf(...)` and the risk of **misinterpreting abstain**.
10. Test allow, deny, missing authority, cross-tenant, self-approval, policy-down, and state-change paths.

**Safety principle:** An `ALLOW` is valid only when the policy request is built from **trusted** data, the PDP response is authenticated/verified, the decision remains valid under the consistency contract, and the write operation does not bypass authorization checks at time of use.

---

## 2. The PEP – PDP – PIP – PAP model

Common terminology in decoupled authorization systems:

| Role | Meaning | Spring/application component |
| --- | --- | --- |
| **PEP** – Policy Enforcement Point | Blocks or lets requests proceed | `AuthorizationManagerBeforeMethodInterceptor`, filter-chain authorization, service guards |
| **PDP** – Policy Decision Point | Computes allow/deny decisions | `PolicyDecisionClient`, OPA/Cedar/policy service, or business policy engine |
| **PIP** – Policy Information Point | Supplies trusted attributes | User/tenant directory, repositories, invoice state, limits, risk context |
| **PAP** – Policy Administration Point | Authors/manages rules and versions | Policy management tools and policy change approval workflows |

Diagram:

```text
Request / Scheduler / Message Consumer
                  |
                  v
          Spring Security PEP
          AuthorizationManager<T>
                  |
       +----------+-----------+
       |                      |
       v                      v
Authentication           Resource context
(server verified)        (DB/server trusted)
       |                      |
       +----------+-----------+
                  |
                  v
         PolicyDecisionClient
           /       |       \
          v        v        v
       PIP      Policy     PDP
     attributes  version   evaluate
                  |
                  v
       ALLOW / DENY / INDETERMINATE
                  |
                  v
       AuthorizationDecision
             |        |
           ALLOW     DENY
             |        |
       method runs   no execution
```

`AuthorizationManager` is Spring Security's **decision-enforcement adapter**, not necessarily where all policy logic lives. If the PDP runs in a separate service, the manager must canonicalize inputs, verify the caller, call the client, interpret responses, and fail closed to **deny** on errors.

**Separation of responsibilities:**

- The manager knows **which invocation needs protection** and how to extract identity/resource/action.
- The policy client knows **how to call and interpret the PDP**.
- Directories/repositories supply **trusted facts**.
- The PDP knows **business/ABAC/RBAC rules** and rule versions.
- Services/domain/databases ensure **post-authorization mutations** do not violate newly changed state.

## 3. `AuthorizationManager<T>` in Spring Security 6.5

The interface belongs to:

```java
package org.springframework.security.authorization;
```

Conceptual API:

```java
AuthorizationDecision check(
    Supplier<Authentication> authentication,
    T object
);
```

This is a simplified signature for Spring Security 6.5. Key types:

- `T`: context to evaluate, such as `MethodInvocation` or `RequestAuthorizationContext`.
- `Supplier<Authentication>`: provider of the current authentication; do not assume it is always invoked or memoized.
- `AuthorizationDecision(true/false)`: explicit decision.
- `null`: **abstain**, meaning the manager made no decision, which **does not always mean deny**.

**Version note:** In Spring Security 6.5, `check(...)` remains the abstract method though marked **deprecated**; a default `authorize(...)` method returns `AuthorizationResult`. When implementing a class targeting Spring Security **6.5.x**, overriding `check(...)` satisfies the compile-time contract. In Spring Security **7.x**, `authorize(...)` becomes the primary extension point and signatures may differ; do not copy a 6.5 class verbatim without migrating.

Simple manager example:

```java
// Illustrative CODE SNIPPET; compatible with the 6.5 interface.
@Override
public AuthorizationDecision check(
        Supplier<Authentication> authentication,
        MethodInvocation invocation) {

    return new AuthorizationDecision(
        policyService.decide(authentication.get(), invocation)
    );
}
```

In production, this snippet still lacks anonymous checks, authority checks, argument validation, timeouts, policy response parsing, and exception handling. The complete version appears in section 7.

### 3.1. How do `check`, `authorize`, and `verify` differ?

| API | Return value | Notes |
| --- | --- | --- |
| `check(...)` | `AuthorizationDecision` or `null` | Abstract/deprecated API in 6.5; custom implementations may still need to override it |
| `authorize(...)` | `AuthorizationResult` or `null` | Recommended API for new code; default bridge in 6.5 |
| `verify(...)` | Void; may throw `AccessDeniedException` | Used when only fail-fast on denial is needed |

Never write:

```java
AuthorizationDecision decision = manager.check(auth, invocation);
if (decision == null || decision.isGranted()) {
    // DANGEROUS: null (abstain) is interpreted as allowed
}
```

If system policy requires a decision at all times, return `new AuthorizationDecision(false)` whenever info is invalid, targets do not match, or the PDP is unresponsive. `null` is appropriate only when **a composition mechanism intentionally** understands abstain and defines an explicit default.

### 3.2. `AuthorizationManager<T>` is not the same as `PermissionEvaluator`

`PermissionEvaluator` is an SPI for `hasPermission(...)` expressions, typically used for object ACLs. `AuthorizationManager` is more general: it can be invoked by HTTP authorization or method interceptors and easily serves as an adapter for a remote PDP.

| `PermissionEvaluator` | `AuthorizationManager` |
| --- | --- |
| Primarily invoked via `hasPermission(...)` | Invoked directly by the authorization mechanism |
| Typical inputs: authentication, object/ID, permission | Inputs: authentication supplier + generic context `T` |
| Returns boolean | Returns `AuthorizationDecision`/`AuthorizationResult` or abstains |
| Fits ACLs and permission expressions | Fits custom policy engines/remote PDPs, HTTP, method, messaging |
| Not a complete PEP on its own | Used directly by interceptor/filter-chain PEPs |

Both can be used together: a manager calls an internal service using an ACL evaluator, or a PDP combines ACLs with other rules. What matters is **a single source of truth or a clear combining rule** so two paths never produce conflicting answers.

## 4. Designing the contract between PEP and PDP

### 4.1. What belongs in the policy input?

A conceptual policy request:

```json
{
  "requestId": "7fd9f2d0-1511-4f2e-a2ad-784cf8b4279d",
  "subject": {
    "id": "u-alice",
    "tenantId": "T1",
    "authorities": ["invoice:approve"]
  },
  "action": "INVOICE_APPROVE",
  "resource": {
    "type": "INVOICE",
    "id": 101,
    "tenantId": "T1",
    "createdBy": "u-bob",
    "state": "PENDING",
    "amount": 250,
    "version": 3
  },
  "context": {
    "policyVersion": "approval-policy-v12"
  }
}
```

This is an **illustrative contract JSON**, not an actual request sent to an external service. In production, you do not need to send every resource attribute or authority: send only minimal facts needed to decide, with sensitive data classification and retention controls.

Trusted sources for each field:

| Field | Recommended source | Do NOT use |
| --- | --- | --- |
| `subject.id` | Verified `Authentication` + server mapping | Arbitrary `"userId"` from request body |
| `tenantId` | Membership/tenant directory, verified active tenant | Unverified `X-Tenant` header |
| `action` | Server-side constant/enum set by endpoint/method | Arbitrary client-supplied action string |
| `resource.id` | Validated argument from method/path | ID tied to an unverified object |
| `resource.tenantId`, `createdBy` | Repository or authoritative attribute source | Client-declared JSON fields |
| `amount`, `state`, `version` | Current record from DB | DTO sent to bypass policy |
| `policyVersion` | Deployed engine/PAP version | Client-selectable version to bypass |

**Never query the PDP with a client-declared DTO containing `tenantId=MY_TENANT`** and assume an ALLOW response is valid. A PDP is only as trustworthy as **the provenance of its inputs**.

### 4.2. Responses must distinguish statuses

A policy engine might return:

```json
{
  "decision": "DENY",
  "reasonCode": "MAKER_CHECKER",
  "policyVersion": "approval-policy-v12",
  "decisionId": "6c78364c-0240-43b4-9711-470e01292b30"
}
```

At minimum, specify:

- `ALLOW`: permitted under policy.
- `DENY`: explicitly refused.
- `NOT_APPLICABLE`: no matching policy.
- `INDETERMINATE`: missing data, engine error, or inconclusive result.

**Safe mapping:** only `ALLOW` maps to `AuthorizationDecision(true)`. `DENY`, `NOT_APPLICABLE`, `INDETERMINATE`, empty responses, and schema errors are all **not permitted**, unless the application has a different specified and tested composition protocol.

`reasonCode` is for auditing/observability; do not blindly expose all internal reasons in HTTP responses because that can leak roles, quotas, tenants, policies, or object existence.

### 4.3. Avoid leaking sensitive data externally

If the PDP is a remote service:

- Use HTTPS/TLS, mTLS, or appropriate service-to-service authentication.
- Allowlist input fields; avoid sending entire JWTs, secrets, document contents, or unnecessary personal data.
- Control network egress; never derive `PDP_URL` from user input.
- Verify the response matches the policy request (request ID, tenant/scope, signature if required by the model).
- Log correlation IDs, latency, policy version, and bounded reason codes; never log credentials.
- Configure timeouts, concurrency limits, circuit breakers, and load shedding so request floods cannot take down the PDP.
- Cache only **cacheable decisions**, keyed and TTL-bound to policy/resource versions.

A remote ALLOW does not let the client skip domain invariants such as `state == PENDING` if data changed after the PDP evaluated it.

## 5. Choosing the integration point: HTTP or Method Security?

Spring Security uses `AuthorizationManager<T>` across multiple layers. Two key layers for servlet applications:

### 5.1. HTTP authorization

Create an `AuthorizationManager<RequestAuthorizationContext>` and wire it with:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.POST, "/api/invoices/{id}/approve")
        .access(invoiceHttpAuthorizationManager)
    .anyRequest().denyAll()
);
```

This is a **web configuration snippet**, not a standalone runnable application. `RequestAuthorizationContext` provides `HttpServletRequest` and route variables when supported by `RequestMatcher`. An HTTP manager can use path/method to identify the action, but must **parse IDs safely** and fetch the authoritative resource before calling the PDP.

Pros: blocks requests early, preventing the controller from running on deny. Risk: business logic may also be invoked by schedulers, message consumers, or services bypassing the filter chain. Therefore, for sensitive writes, **service/domain protection** remains necessary.

### 5.2. Method Security

Create an `AuthorizationManager<MethodInvocation>` and wrap it in `AuthorizationManagerBeforeMethodInterceptor` with a pointcut matching protected methods.

Pros:

- Protects the service whether callers arrive via HTTP, batch, scheduled jobs, or Java code through the Spring proxy.
- Receives exact method arguments, making it easy to extract resource ID and action.
- Fits policies that depend on business data state.
- Testable via `@SpringBootTest` + `@WithMockUser`.

Risks: self-invocation (`this.securedMethod()`), `new Service(...)`, non-proxied methods, or misconfigured advisors/pointcuts will bypass enforcement. Always test through real Spring beans.

**When to use both?** HTTP manager filters entry paths and method manager protects the use case. If both call a remote PDP, latency can double; design coordination/caching carefully instead of dropping an essential protection layer.

## 6. Method Security integration approaches

Three common options:

| Approach | When appropriate | Example |
| --- | --- | --- |
| `@PreAuthorize` calling a policy bean | Simple, keeps SpEL annotations | `@PreAuthorize("@policyGuard.canApprove(authentication, #id)")` |
| Custom `AuthorizationManager<MethodInvocation>` + advisor | Wants clean Java logic, reuse, audit/manager composition | `@RequiresInvoiceApproval` and `AuthorizationManagerBeforeMethodInterceptor` |
| Replacing application-wide `PreAuthorizeAuthorizationManager` | Wants to alter built-in annotation behavior | `@EnableMethodSecurity(prePostEnabled=false)` + custom advisors |

This lesson uses **the second option** to illustrate `AuthorizationManager` directly. Do not override default `@PreAuthorize` globally unless necessary: broad overrides can break existing annotations and raise risk.

### 6.1. Combining static authorities and dynamic policies

Desired rule:

```text
ALLOW = authenticated
        AND hasAuthority("invoice:approve")
        AND PDP(actor, invoice, "INVOICE_APPROVE") == ALLOW
```

Two approaches worth considering:

1. A custom manager checks both the static authority and the PDP response, always returning explicit ALLOW or DENY.
2. Use `AuthorizationManagers.allOf(...)` to combine `AuthorityAuthorizationManager` and a custom manager.

To keep the demo easy to run without abstain subtleties, **the custom manager enforces both conditions**. Section 10 explains composition.

## 7. Complete demo: AuthorizationManager calling a policy decision service

The project uses **Java 17**, **Spring Boot 3.5.8**, and Spring Security 6.5.x APIs. `PolicyDecisionClient` represents the PDP boundary; the demo implementation `InProcessPdp` runs in-process for deterministic testing and **does not call a real HTTP PDP**.

Importantly, even though the demo PDP runs in-process, the architecture manager -> `PolicyDecisionClient` -> policy mirrors how you integrate a remote PDP. Section 11 explains switching to HTTP/gRPC in production.

### 7.1. Project structure

```text
authorization-manager-pdp-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── AuthorizationManagerPdpApplication.java
    │   ├── Invoice.java
    │   ├── ActorDirectory.java
    │   ├── InvoiceStore.java
    │   ├── PolicyDecisionClient.java
    │   ├── InProcessPdp.java
    │   ├── RequiresInvoiceApproval.java
    │   ├── InvoiceApprovalManager.java
    │   ├── MethodSecurityConfig.java
    │   └── InvoiceService.java
    └── test/java/demo/
        └── InvoiceSecurityTest.java
```

This example **does not use HTTP**; it runs via `CommandLineRunner` and exercises the Spring-managed `InvoiceService`. No database is needed since `InvoiceStore` holds records in memory; in production, use DB transactions/locking as covered in section 12.

### 7.2. Gradle

**`settings.gradle`:**

```groovy
rootProject.name = 'authorization-manager-pdp-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-security` brings in the required authorization and AOP modules; Spring Boot manages Spring Framework/Spring Security versions. Sample code targets Spring Boot 3.5.x. If upgrading to Spring Boot 4/Spring Security 7, re-check the `AuthorizationManager` API against that version.

### 7.3. Modeling the invoice

**`src/main/java/demo/Invoice.java`:**

```java
package demo;

public record Invoice(
        Long id,
        String tenantId,
        String creatorId,
        long amount,
        Status status) {

    public enum Status {
        PENDING,
        APPROVED
    }
}
```

Here `tenantId`, `creatorId`, `amount`, and `status` are facts from the **server store**, not client-declared values meant to influence the PDP.

### 7.4. User directory and verified identity

**`src/main/java/demo/ActorDirectory.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

record Actor(String userId, String tenantId, long approvalLimit) {
}

@Component
public class ActorDirectory {

    private final Map<String, Actor> actors = Map.of(
        "alice", new Actor("u-alice", "T1", 500),
        "bob",   new Actor("u-bob", "T1", 1000),
        "carol", new Actor("u-carol", "T2", 900)
    );

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    public Actor require(Authentication authentication) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || trustResolver.isAnonymous(authentication)) {
            throw new AccessDeniedException("No trusted user");
        }

        Actor actor = actors.get(authentication.getName());
        if (actor == null) {
            throw new AccessDeniedException(
                "User has no trusted tenant mapping");
        }
        return actor;
    }
}
```

`Actor` is a package-private record in the same file; Java permits one public top-level type alongside other package-private types per file. All demo files reside in package `demo`.

The hardcoded directory is solely for learning and tests. With production JWT/OIDC, map stable `issuer + subject`/internal user IDs to tenant membership, approval limits, and account status; never rely on `getName()` if it can collide across tenants or is uncanonicalized.

`AnonymousAuthenticationToken` can report `isAuthenticated() == true`, so distinguish anonymous users via `AuthenticationTrustResolver` rather than reading the raw boolean alone.

### 7.5. In-memory invoice store

**`src/main/java/demo/InvoiceStore.java`:**

```java
package demo;

import java.util.HashMap;
import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Component;

@Component
public class InvoiceStore {

    private final Map<Long, Invoice> invoices = new HashMap<>();

    public InvoiceStore() {
        invoices.put(101L, new Invoice(
            101L, "T1", "u-bob", 250, Invoice.Status.PENDING));
        invoices.put(102L, new Invoice(
            102L, "T2", "u-service", 400, Invoice.Status.PENDING));
        invoices.put(103L, new Invoice(
            103L, "T1", "u-bob", 700, Invoice.Status.PENDING));
        invoices.put(104L, new Invoice(
            104L, "T1", "u-bob", 200, Invoice.Status.APPROVED));
        invoices.put(105L, new Invoice(
            105L, "T1", "u-alice", 100, Invoice.Status.PENDING));
        invoices.put(106L, new Invoice(
            106L, "T1", "u-bob", 120, Invoice.Status.PENDING));
    }

    public synchronized Invoice snapshot(Long id) {
        return invoices.get(id);
    }

    public synchronized String approveIfAllowed(
            Long id,
            Actor actor,
            PolicyDecisionClient policyClient) {

        Invoice current = invoices.get(id);
        if (current == null) {
            throw new AccessDeniedException("Resource unavailable");
        }

        try {
            PolicyVerdict verdict = policyClient.decide(
                new DecisionInput(
                    actor, "INVOICE_APPROVE", current)
            );

            if (verdict != PolicyVerdict.ALLOW) {
                throw new AccessDeniedException(
                    "Dynamic policy denied operation");
            }
        } catch (PolicyUnavailableException unavailable) {
            throw new AccessDeniedException(
                "Policy decision unavailable");
        }

        invoices.put(
            id,
            new Invoice(
                current.id(),
                current.tenantId(),
                current.creatorId(),
                current.amount(),
                Invoice.Status.APPROVED
            )
        );

        return "APPROVED";
    }
}
```

**Why re-check the policy in `approveIfAllowed`?** The interceptor evaluates policy **before** invoking the service. Between that check and the state transition, another thread might have already approved or modified the resource. The demo store uses `synchronized` on the single instance to re-check **and** mutate state atomically within one process.

In multi-node production, `synchronized` is **insufficient**. You need transactions, row locks/conditional UPDATEs, policy versions, and revocation protocols consistent with the PDP source. Section 12 covers this.

### 7.6. Policy Decision Client contract

**`src/main/java/demo/PolicyDecisionClient.java`:**

```java
package demo;

record DecisionInput(
    Actor actor,
    String action,
    Invoice invoice) {
}

enum PolicyVerdict {
    ALLOW,
    DENY,
    NOT_APPLICABLE,
    INDETERMINATE
}

interface PolicyDecisionClient {
    PolicyVerdict decide(DecisionInput input);
}

final class PolicyUnavailableException extends RuntimeException {

    PolicyUnavailableException(String message) {
        super(message);
    }
}
```

`DecisionInput` holds the **directory-verified actor** and the **invoice from the server store**. `PolicyVerdict` has four statuses to model external PDP semantics.

`PolicyDecisionClient` is a package-private interface, sufficient for `demo` components to inject by type. In a real project, you can move client/API models into their own package and add `requestId`, `policyVersion`, obligations, and `resourceVersion`.

### 7.7. Internal policy service simulating a PDP

**`src/main/java/demo/InProcessPdp.java`:**

```java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.stereotype.Component;

@Component
public class InProcessPdp implements PolicyDecisionClient {

    private final AtomicBoolean available =
        new AtomicBoolean(true);

    public void setAvailable(boolean value) {
        available.set(value);
    }

    @Override
    public PolicyVerdict decide(DecisionInput input) {

        if (!available.get()) {
            throw new PolicyUnavailableException(
                "Simulated PDP outage");
        }

        if (input == null
                || input.actor() == null
                || input.invoice() == null
                || !"INVOICE_APPROVE".equals(input.action())) {
            return PolicyVerdict.NOT_APPLICABLE;
        }

        Actor actor = input.actor();
        Invoice invoice = input.invoice();

        if (!actor.tenantId().equals(invoice.tenantId())) {
            return PolicyVerdict.DENY;
        }

        if (invoice.status() != Invoice.Status.PENDING) {
            return PolicyVerdict.DENY;
        }

        if (invoice.amount() > actor.approvalLimit()) {
            return PolicyVerdict.DENY;
        }

        if (actor.userId().equals(invoice.creatorId())) {
            return PolicyVerdict.DENY;
        }

        return PolicyVerdict.ALLOW;
    }
}
```

Business conditions:

```text
ALLOW =
  actor.tenant == invoice.tenant
  AND invoice.status == PENDING
  AND invoice.amount <= actor.approvalLimit
  AND actor.userId != invoice.creatorId
```

**Key point:** `InProcessPdp` **does not read roles from the client**. `AuthorizationManager` blocks missing `invoice:approve` authority before calling the PDP. In an out-of-process PDP deployment, verified roles/authorities should also be included in the policy request under the inter-service trust contract.

`setAvailable(false)` is solely for testing fail-closed behavior. In production, timeouts, HTTP 5xx responses, invalid payloads, or open circuit breakers must similarly result in denial/blocking mutations.

### 7.8. Annotation for protected methods

**`src/main/java/demo/RequiresInvoiceApproval.java`:**

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface RequiresInvoiceApproval {
}
```

This annotation is a marker: "This method requires invoice approval policy evaluation." The demo assumes the annotated method takes **exactly one `Long invoiceId` parameter**. In large projects, use an explicit adapter/factory to resolve resource IDs rather than relying on positional argument assumptions when method signatures vary.

### 7.9. Custom `AuthorizationManager<MethodInvocation>`

**`src/main/java/demo/InvoiceApprovalManager.java`:**

```java
package demo;

import java.util.function.Supplier;

import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class InvoiceApprovalManager
        implements AuthorizationManager<MethodInvocation> {

    private final ActorDirectory directory;
    private final InvoiceStore store;
    private final PolicyDecisionClient policyClient;

    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    public InvoiceApprovalManager(
            ActorDirectory directory,
            InvoiceStore store,
            PolicyDecisionClient policyClient) {
        this.directory = directory;
        this.store = store;
        this.policyClient = policyClient;
    }

    @Override
    @SuppressWarnings("deprecation")
    public AuthorizationDecision check(
            Supplier<Authentication> authentication,
            MethodInvocation invocation) {

        Authentication actorAuth =
            authentication == null ? null : authentication.get();

        if (actorAuth == null
                || !actorAuth.isAuthenticated()
                || trustResolver.isAnonymous(actorAuth)) {
            return deny();
        }

        boolean hasFunctionalAuthority = actorAuth.getAuthorities()
            .stream()
            .anyMatch(a ->
                "invoice:approve".equals(a.getAuthority()));

        if (!hasFunctionalAuthority) {
            return deny();
        }

        // Fail closed if the manager is invoked on a method
        // outside the application-managed contract.
        if (invocation == null
                || !invocation.getMethod()
                    .isAnnotationPresent(
                        RequiresInvoiceApproval.class)) {
            return deny();
        }

        Object[] args = invocation.getArguments();

        if (args.length != 1 || !(args[0] instanceof Long id)) {
            return deny();
        }

        try {
            Actor actor = directory.require(actorAuth);
            Invoice invoice = store.snapshot(id);

            if (invoice == null) {
                return deny();
            }

            PolicyVerdict verdict = policyClient.decide(
                new DecisionInput(
                    actor,
                    "INVOICE_APPROVE",
                    invoice
                )
            );

            // Only ALLOW produces a granted decision.
            return new AuthorizationDecision(
                verdict == PolicyVerdict.ALLOW
            );
        } catch (AccessDeniedException | PolicyUnavailableException denied) {
            return deny();
        }
    }

    private static AuthorizationDecision deny() {
        return new AuthorizationDecision(false);
    }
}
```

**Technical points to read carefully:**

1. The manager receives Spring's `Supplier<Authentication>`, **never** a client-supplied username.
2. It filters out anonymous users, requires the static authority, and verifies the marker annotation.
3. The ID must be a `Long` from method arguments; it does not accept arbitrary objects or unparsed path strings.
4. `InvoiceStore.snapshot` fetches the server record. If missing, **deny**.
5. The PDP returns `ALLOW`, `DENY`, `NOT_APPLICABLE`, or `INDETERMINATE`. Only `ALLOW` produces `AuthorizationDecision(true)`.
6. PDP unavailable -> `PolicyUnavailableException` -> **deny**; the service body never runs.
7. `check` **never returns `null`**. Abstain can be interpreted differently by composite managers; the demo intentionally fails closed.
8. `@SuppressWarnings("deprecation")` only silences the `check(...)` deprecation warning in Spring Security 6.5; **it does not mean skipping migration to `authorize(...)` on a major version upgrade**.

If a remote implementation throws exceptions other than `PolicyUnavailableException`, normalize transport/schema errors into an appropriate exception **before** returning to the manager. Runtime errors must never become `ALLOW`; log/monitor system failures with correlation IDs while redacting sensitive details.

### 7.10. Registering the Spring Method Security advisor

**`src/main/java/demo/MethodSecurityConfig.java`:**

```java
package demo;

import org.springframework.aop.Advisor;
import org.springframework.aop.Pointcut;
import org.springframework.aop.support.annotation.AnnotationMatchingPointcut;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Role;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    static Advisor invoiceApprovalAdvisor(
            InvoiceApprovalManager authorizationManager) {

        Pointcut pointcut =
            AnnotationMatchingPointcut.forMethodAnnotation(
                RequiresInvoiceApproval.class
            );

        return new AuthorizationManagerBeforeMethodInterceptor(
            pointcut, authorizationManager
        );
    }
}
```

Crucially, the **advisor** pairs:

- A pointcut specifying **which methods are intercepted**.
- A manager determining the **authorization decision** for the matching `MethodInvocation`.

`@EnableMethodSecurity` ensures method security infrastructure is active. A `static @Bean` with infrastructure role publishes the advisor at the right lifecycle phase; in applications with multiple advisors, test ordering alongside other annotations.

**Do not apply a manager's logic to every method and guess the ID from the first argument**. A narrow pointcut reduces the risk of affecting unrelated services and makes security boundaries reviewable.

If a method is declared on an interface while the annotation is placed only on the implementation (or vice versa), Spring proxy/method resolution can behave differently between JDK proxies and CGLIB. The demo uses a concrete class without a service interface; in production, test pointcut matching against the real structure.

### 7.11. Service executing business logic and re-checking

**`src/main/java/demo/InvoiceService.java`:**

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    private final ActorDirectory directory;
    private final InvoiceStore store;
    private final PolicyDecisionClient policyClient;

    public InvoiceService(
            ActorDirectory directory,
            InvoiceStore store,
            PolicyDecisionClient policyClient) {
        this.directory = directory;
        this.store = store;
        this.policyClient = policyClient;
    }

    @RequiresInvoiceApproval
    public String approve(Long invoiceId) {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        Actor actor = directory.require(authentication);

        // Re-check policy inside the store's critical section.
        return store.approveIfAllowed(
            invoiceId, actor, policyClient
        );
    }
}
```

This is the **permission and data enforcement layer**, not custom logic replacing the manager. The manager blocks early when unauthorized; the service enforces domain rules and re-checks inside the atomic update to guard against state changing between authorization and mutation.

If the advisor is missing, the method body still runs the business policy guard; however, **the `invoice:approve` authority is not duplicated by the service**. Therefore, an integration test is needed where an actor meets business policy conditions yet lacks the authority. That test catches a bypassed advisor.

In production, place critical security invariants at application/domain/database boundaries strong enough to cover call paths bypassing Spring AOP. Never rely on in-memory `synchronized` as proof of multi-node authorization.

### 7.12. Spring Boot application and scenario

**`src/main/java/demo/AuthorizationManagerPdpApplication.java`:**

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
public class AuthorizationManagerPdpApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            AuthorizationManagerPdpApplication.class, args);
    }

    @Bean
    @Profile("!test")
    CommandLineRunner scenario(
            InvoiceService service,
            InProcessPdp pdp) {

        return args -> {
            try {
                as("alice", "invoice:view");
                denied("ALICE_NO_AUTHORITY_101",
                    () -> service.approve(101L));

                as("alice", "invoice:approve");
                System.out.println("ALICE_101: "
                    + service.approve(101L));

                denied("ALICE_REPEAT_101",
                    () -> service.approve(101L));

                denied("ALICE_CROSS_TENANT_102",
                    () -> service.approve(102L));

                denied("ALICE_OVER_LIMIT_103",
                    () -> service.approve(103L));

                denied("ALICE_ALREADY_APPROVED_104",
                    () -> service.approve(104L));

                denied("ALICE_SELF_APPROVAL_105",
                    () -> service.approve(105L));

                as("bob", "invoice:view");
                denied("BOB_NO_AUTHORITY_106",
                    () -> service.approve(106L));

                as("carol", "invoice:approve");
                System.out.println("CAROL_T2_102: "
                    + service.approve(102L));

                as("alice", "invoice:approve");
                pdp.setAvailable(false);

                denied("PDP_DOWN_ALICE_106",
                    () -> service.approve(106L));
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void as(
            String username, String authority) {

        var authentication =
            new UsernamePasswordAuthenticationToken(
                username,
                "demo-only",
                List.of(
                    new SimpleGrantedAuthority(authority))
            );

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
    }

    private static void denied(
            String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException expected) {
            System.out.println(label + ": DENIED");
        }
    }
}
```

Constructing `UsernamePasswordAuthenticationToken` with chosen authorities is **strictly for CLI/test simulation**. It is **not an authentication provider** for production HTTP. On real web endpoints, Spring Security filters verify credentials/sessions/JWTs and construct a trusted `Authentication`; never read caller-supplied roles to mint privileged tokens.

Run in the directory containing `build.gradle`:

```bash
./gradlew bootRun
```

PowerShell:

```bash
.\gradlew.bat bootRun
```

If the project has no Gradle Wrapper yet, use an appropriate installed Gradle or generate the wrapper first.

**Expected `System.out.println` lines from the application** (excluding Spring/Gradle logs):

```text
ALICE_NO_AUTHORITY_101: DENIED
ALICE_101: APPROVED
ALICE_REPEAT_101: DENIED
ALICE_CROSS_TENANT_102: DENIED
ALICE_OVER_LIMIT_103: DENIED
ALICE_ALREADY_APPROVED_104: DENIED
ALICE_SELF_APPROVAL_105: DENIED
BOB_NO_AUTHORITY_106: DENIED
CAROL_T2_102: APPROVED
PDP_DOWN_ALICE_106: DENIED
```

**Explanation:**

- Alice lacks `invoice:approve`, so the manager blocks her before calling the PDP even though invoice 101 meets business rules.
- Once granted the authority, Alice approves 101 because tenant is T1, status is `PENDING`, limit 500 covers amount 250, and maker is Bob.
- Re-approving 101 is denied because its status is now `APPROVED`.
- Invoice 102 belongs to T2, so Alice is denied despite having the functional authority.
- Invoice 103 has amount 700 exceeding Alice's 500 limit.
- Invoice 104 is already `APPROVED` and cannot be approved again.
- Invoice 105 was created by Alice herself, violating maker–checker.
- Bob lacks authority so he never enters the service, regardless of invoice 106's state.
- Carol belongs to T2 with limit 900 and invoice 102 was created by a service account, so she is allowed to approve.
- When the simulated PDP is unavailable, Alice is denied on invoice 106; there is no fallback to `permitAll`.

**Note:** This stdout is **expected from reading the source code**, not an execution verified in this article's environment. Behavior is fully verified once you run Gradle/tests and confirm the Spring Method Security advisor actually takes effect.

## 8. Integration testing with real Spring Method Security

**`src/test/java/demo/InvoiceSecurityTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD
)
class InvoiceSecurityTest {

    @Autowired
    InvoiceService service;

    @Autowired
    InvoiceStore store;

    @Autowired
    InProcessPdp pdp;

    @Test
    @WithMockUser(
        username = "alice",
        authorities = "invoice:approve"
    )
    void allowsOnlyWhenStaticAndDynamicPoliciesPass() {
        assertEquals("APPROVED", service.approve(101L));
        assertEquals(
            Invoice.Status.APPROVED,
            store.snapshot(101L).status()
        );

        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(101L)
        );
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = "invoice:view"
    )
    void detectsMissingAuthorizationManagerAdvisor() {
        // Business policy for invoice 101 allows Alice,
        // yet she lacks the invoice:approve authority.
        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(101L)
        );

        assertEquals(
            Invoice.Status.PENDING,
            store.snapshot(101L).status()
        );
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = "invoice:approve"
    )
    void deniesCrossTenantAndOverLimitAndMakerChecker() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(102L)
        );

        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(103L)
        );

        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(104L)
        );

        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(105L)
        );

        assertEquals(
            Invoice.Status.PENDING,
            store.snapshot(103L).status()
        );
    }

    @Test
    @WithMockUser(
        username = "carol",
        authorities = "invoice:approve"
    )
    void tenantT2ApproverCanApproveItsOwnScope() {
        assertEquals("APPROVED", service.approve(102L));
        assertEquals(
            Invoice.Status.APPROVED,
            store.snapshot(102L).status()
        );
    }

    @Test
    @WithMockUser(
        username = "alice",
        authorities = "invoice:approve"
    )
    void failsClosedWhenPdpIsUnavailable() {
        pdp.setAvailable(false);

        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(106L)
        );

        assertEquals(
            Invoice.Status.PENDING,
            store.snapshot(106L).status()
        );
    }

    @Test
    @WithMockUser(
        username = "ghost",
        authorities = "invoice:approve"
    )
    void userWithoutTrustedDirectoryMappingIsDenied() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(101L)
        );

        assertEquals(
            Invoice.Status.PENDING,
            store.snapshot(101L).status()
        );
    }

    @Test
    @WithAnonymousUser
    void anonymousIsDeniedEvenIfTokenIsAuthenticated() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.approve(101L)
        );
    }
}
```

Run:

```bash
./gradlew test
```

Tests use `@SpringBootTest`, creating the example's real Spring application context, advisor bean, service proxy, and policy client. `@WithMockUser` sets up the security context per test; `@DirtiesContext` resets invoice/PDP state after each test. The runner activates only when the profile is not `test`, so tests do not accidentally execute the CLI scenario.

**Why is `detectsMissingAuthorizationManagerAdvisor` especially important?** Alice satisfies every dynamic condition for invoice 101 yet **lacks the authority**. If the custom advisor is not applied, the service body would still let Alice approve via internal policy; the test fails. Testing only dynamic DENY cases cannot prove the advisor is genuinely active.

### 8.1. Decision matrix to maintain as you evolve

| Caller | Authority | Invoice | PDP evaluation | Outcome |
| --- | --- | ---: | --- | --- |
| Alice/T1 | `invoice:view` | 101 | Dynamic allow if asked | **DENY** before calling PDP |
| Alice/T1 | `invoice:approve` | 101, PENDING | Allow | **ALLOW** |
| Alice/T1 | `invoice:approve` | 101, after approve | Deny – no longer PENDING | **DENY** |
| Alice/T1 | `invoice:approve` | 102/T2 | Deny – cross tenant | **DENY** |
| Alice/T1 | `invoice:approve` | 103/700 | Deny – exceeds 500 limit | **DENY** |
| Alice/T1 | `invoice:approve` | 104/APPROVED | Deny – status | **DENY** |
| Alice/T1 | `invoice:approve` | 105 created by Alice | Deny – maker checker | **DENY** |
| Bob/T1 | `invoice:view` | 106 | Not yet asked | **DENY** |
| Carol/T2 | `invoice:approve` | 102/T2 | Allow | **ALLOW** |
| Alice/T1 | `invoice:approve` | 106, PDP down | No trusted decision | **DENY** |

With a real remote PDP, expand the matrix: HTTP 500, connection timeout, TLS error, malformed JSON, `NOT_APPLICABLE`, `INDETERMINATE`, policy version mismatch, stale cache, caller missing tenant mapping, lost authentication, nonexistent resource, and concurrent grant revocation.

## 9. Integrating into the HTTP `SecurityFilterChain`

Method adapters fit use cases well; sometimes you also want early policy checks directly at HTTP routes.

An example **`AuthorizationManager<RequestAuthorizationContext>`**:

```java
// Illustrative CODE SNIPPET for a Servlet web application.
// Requires adding spring-boot-starter-web, corresponding imports,
// Controller, and project-appropriate dependencies.
final class InvoiceHttpAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final ActorDirectory directory;
    private final InvoiceStore store;
    private final PolicyDecisionClient client;
    private final AuthenticationTrustResolver trustResolver =
        new AuthenticationTrustResolverImpl();

    InvoiceHttpAuthorizationManager(
            ActorDirectory directory,
            InvoiceStore store,
            PolicyDecisionClient client) {
        this.directory = directory;
        this.store = store;
        this.client = client;
    }

    @Override
    @SuppressWarnings("deprecation")
    public AuthorizationDecision check(
            Supplier<Authentication> authSupplier,
            RequestAuthorizationContext context) {

        Authentication auth =
            authSupplier == null ? null : authSupplier.get();

        if (auth == null || trustResolver.isAnonymous(auth)
                || !auth.isAuthenticated()
                || auth.getAuthorities().stream().noneMatch(
                    a -> "invoice:approve".equals(a.getAuthority()))) {
            return new AuthorizationDecision(false);
        }

        Object rawId = context.getVariables().get("id");
        if (!(rawId instanceof String text)) {
            return new AuthorizationDecision(false);
        }

        try {
            Long id = Long.valueOf(text);
            Invoice invoice = store.snapshot(id);
            if (invoice == null) {
                return new AuthorizationDecision(false);
            }

            Actor actor = directory.require(auth);
            PolicyVerdict verdict = client.decide(
                new DecisionInput(
                    actor, "INVOICE_APPROVE", invoice));

            return new AuthorizationDecision(
                verdict == PolicyVerdict.ALLOW
            );
        } catch (NumberFormatException
                | AccessDeniedException
                | PolicyUnavailableException denied) {
            return new AuthorizationDecision(false);
        }
    }
}
```

Wiring snippet:

```java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        InvoiceHttpAuthorizationManager invoiceAuthz)
        throws Exception {

    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(
            HttpMethod.POST,
            "/api/invoices/{id}/approve"
        ).access(invoiceAuthz)
        .anyRequest().denyAll()
    );

    return http.build();
}
```

**Notes:**

- `context.getVariables()` depends on a `RequestMatcher` supporting path variables; if the actual route/matcher does not supply `id`, the manager returns **DENY** rather than guessing from an arbitrary path string.
- `RequestAuthorizationContext` is not `MethodInvocation`, so a method manager cannot be reused directly as an HTTP manager without an adapter.
- HTTP managers run only when requests traverse the configured filter chain. Schedulers or direct service calls **bypass** them.
- Do not disable CSRF by default if the app uses browser cookies/sessions. For bearer-only APIs, evaluate your threat model before choosing CSRF settings.
- If both HTTP and Method Security call the PDP for one action, latency can double. Optimizations must preserve security boundaries and proper invalidation.

Common practice is an **HTTP coarse-grained guard** (authenticated, route/authority) paired with a **method policy guard** inspecting trusted data, avoiding duplicate remote calls unless genuinely needed.

## 10. Combining multiple `AuthorizationManager` instances with `AuthorizationManagers`

Spring Security provides:

```java
AuthorizationManagers.allOf(...);
AuthorizationManagers.anyOf(...);
AuthorizationManagers.not(...);
```

**`allOf`** fits AND-style rules. Example configuration snippet:

```java
// Illustrative CODE SNIPPET, not a direct drop-in bean replacement
// for MethodSecurityConfig in section 7.
AuthorizationManager<MethodInvocation> staticRule =
    AuthorityAuthorizationManager.<MethodInvocation>hasAuthority(
        "invoice:approve"
    );

AuthorizationManager<MethodInvocation> combined =
    AuthorizationManagers.allOf(
        new AuthorizationDecision(false),
        staticRule,
        dynamicInvoiceManager
    );
```

Here:

- `staticRule` checks the authority.
- `dynamicInvoiceManager` queries the PDP.
- `new AuthorizationDecision(false)` is the **default DENY if all delegates abstain** using the default-decision overload (available since Spring Security 6.3).
- Ensure sensitive delegates **never** abstain on invalid cases, because "abstain" in composition can differ from "deny".

**Important pitfall:** `AuthorizationManagers.allOf(manager1, manager2)` in some versions tolerates **abstaining** managers and may grant when all abstain. Therefore, never treat `null` as synonymous with DENY and return `null` on PDP timeouts.

**`anyOf`** fits only when **any one of the policies is sufficient to grant** per specification. Never combine `isAdmin` and `tenantPolicy` inside `anyOf` if admins must not access across tenants. AND/OR composition must come from security requirements, not API convenience.

### 10.1. Do not apply AND mechanically everywhere

Suppose a system has the rule:

```text
ALLOW =
  sameTenant
  AND (
        owner
        OR sharedByAcl
      )
  AND notDeleted
```

This can be expressed by composing `allOf(sameTenant, anyOf(owner, sharedByAcl), notDeleted)`, provided missing data defaults to **deny**. When deny-overrides, obligations, or multi-level approvals exist, it is often cleaner for the PDP to perform the combination while the manager enforces the final decision.

## 11. Switching `InProcessPdp` to a real remote PDP

In production, `PolicyDecisionClient` can be implemented via `RestClient`, gRPC, or a policy engine SDK. Never register two `@Component` implementations of the same interface simultaneously without explicitly selecting one via `@Profile`, `@ConditionalOnProperty`, or `@Primary`.

### 11.1. Remote request/response pattern

```java
// Illustrative DTO SNIPPET for remote adapter; not part of the demo files.
record RemoteDecisionRequest(
    String subjectId,
    String tenantId,
    String action,
    Long resourceId,
    String resourceTenant,
    String resourceCreator,
    long resourceAmount,
    String resourceStatus,
    long approvalLimit,
    String requestId
) {}

record RemoteDecisionResponse(
    String decision,
    String policyVersion,
    String decisionId,
    String reasonCode
) {}
```

Use server-side `Actor` and `Invoice` to populate the DTO; never serialize raw `Authentication`, HTTP requests, or entity graphs containing secrets.

### 11.2. `RestClient` adapter: fail-closed sketch

```java
// Integration CODE SNIPPET, NOT standalone:
// requires spring-web/RestClient, service-to-service authentication,
// timeout configuration, exception mapping, observability, and DI.
public PolicyVerdict decide(DecisionInput input) {

    RemoteDecisionRequest request = requestFactory.fromTrusted(
        input.actor(), input.invoice(), input.action());

    RemoteDecisionResponse result;

    try {
        result = restClient.post()
            .uri("/v1/decisions")
            .body(request)
            .retrieve()
            .body(RemoteDecisionResponse.class);
    } catch (RestClientException transportProblem) {
        throw new PolicyUnavailableException(
            "Remote policy decision unavailable");
    }

    if (result == null || result.decision() == null) {
        return PolicyVerdict.INDETERMINATE;
    }

    return switch (result.decision()) {
        case "ALLOW" -> PolicyVerdict.ALLOW;
        case "DENY" -> PolicyVerdict.DENY;
        case "NOT_APPLICABLE" -> PolicyVerdict.NOT_APPLICABLE;
        default -> PolicyVerdict.INDETERMINATE;
    };
}
```

**This is not a standalone file**: `restClient`, `requestFactory`, DTO classes/imports, and configuration are not defined in the demo project. It illustrates mapping transport failures and unrecognized responses to **not granted**.

For production use:

1. Initialize `RestClient` with a **server-configured static base URL**, never derived from requests.
2. Configure `connectTimeout`, `readTimeout`/request deadline, and appropriate connection pooling.
3. Use mTLS or narrow-scoped service-to-service tokens; never forward arbitrary user secrets.
4. Attach `requestId` and log policy version/decision ID for traceability.
5. Validate response schema, status/version, and input attribute provenance.
6. Add circuit breakers/bulkheads to avoid cascading failures when the PDP errors out.
7. Map timeouts, 429, 5xx, and invalid responses to **deny** or infrastructure errors blocking execution.
8. Run offline/chaos tests confirming **no fallback to allow**.

### 11.3. Timeout: what is a reasonable choice?

Timeouts depend on SLAs and operation sensitivity; no single millisecond value fits every system. Guidelines:

- The PDP deadline must be shorter than the overall HTTP/request timeout so time remains to deny/audit.
- Never retry indefinitely; a single policy check could amplify into a storm of calls.
- For low-risk READs, consider caching valid policy results with bounded TTL if the contract allows.
- For sensitive WRITE/APPROVE/TRANSFER/DELETE operations, do not use stale ALLOWs when the PDP is down unless an approved **stale-while-revalidate** policy and matching revocation mechanism exist.
- When the circuit breaker opens, **never switch to default allow** to "preserve availability".

Any system intending to operate offline must **specify in advance** which operations and snapshot lifetimes are permitted; that is an explicit security trade-off, not a `catch (Exception) { return true; }` branch.

## 12. Dynamic policy and TOCTOU: ALLOW is not a permanent license

The biggest challenge with a decoupled PDP is that **a decision valid at T1** may already be stale by T2:

```text
T1: PDP ALLOWs invoice#101 while PENDING, limit 500
T2: Admin lowers Alice's limit to 100
T3: Worker invokes approve(invoice#101)
T4: DB updates status = APPROVED
```

An `AuthorizationManagerBeforeMethodInterceptor` does not create a distributed transaction spanning the remote PDP and resource DB. `@PreAuthorize` or a custom advisor may execute before the service transaction starts. Therefore:

- Use the manager solely to **fail early**.
- On writes, re-verify **resource state, tenant, owner/creator, amount, permission, and policy version** close to the mutation per contract.
- Use conditional UPDATEs, row locks, optimistic versioning, or policy epochs to avoid mutating after data changed.
- If policies live in another service and immediate revocation is required, establish a consistency protocol between PDP and DB rather than merely adding local `@Transactional`.

### 12.1. Conditional UPDATE

Illustrative SQL example:

```sql
UPDATE invoices
SET status = 'APPROVED',
    approved_by = :trustedApproverId,
    version = version + 1
WHERE id = :invoiceId
  AND tenant_id = :trustedTenantId
  AND status = 'PENDING'
  AND amount <= :trustedApprovalLimit
  AND created_by <> :trustedApproverId
  AND version = :expectedVersion;
```

This statement guards facts **residing on the same resource row**. Check affected rows: `1` means success; `0` means preconditions failed or version changed. For roles/tenants/limits stored in other tables, ensure consistency per the agreed policy contract.

### 12.2. Locking and re-checking for dynamic grants

If approval depends on `approval_grants`, `acl_entry`, or separately updated memberships:

```text
Transaction APPROVE                 Transaction REVOKE
--------------------------------    --------------------------------
Lock invoice row                    Lock same invoice row
Read grant/policy version           Modify grant / bump authzVersion
Recheck dynamic authorization       Commit
Conditional update invoice
Commit
```

Order can vary, yet **every path mutating grants affecting the invoice must follow the same lock/version protocol**. If revocation updates the grant table without locking the invoice, a writer holding only the invoice lock **cannot guard the permission**.

With Redis/caches and multiple nodes, `synchronized` in the demo is safe **within one JVM only**. Cached decisions with TTL/versioning must be invalidated when actor roles, tenant memberships, resource state, or policies change.

### 12.3. Policy decision tokens and versioning

Some PDP systems return:

```json
{
  "decision": "ALLOW",
  "policyVersion": "approval-policy-v12",
  "resourceVersion": 3,
  "expiresAt": "2026-11-05T10:20:30Z"
}
```

This is illustrative, not a standard Spring API requirement. If carrying a decision into the write step, re-verify:

- The decision matches the exact `subject + tenant + action + resource`.
- `policyVersion` and `resourceVersion` remain valid against authoritative sources.
- The token/decision is authenticated/tamper-proof.
- `expiresAt` has not elapsed and clock skew is handled.
- Current business state remains valid.

**Never rely solely on a short TTL** to guarantee immediate revocation. Extremely sensitive operations may require a "fresh PDP decision inside the transaction" or multi-person approval workflows.

## 13. Caching and dynamic policies

Caching can lower PDP latency yet increases stale authorization risk. A sound cache key usually requires:

```text
(subjectId,
 tenantId,
 action,
 resourceType,
 resourceId,
 resourceVersion,
 policyVersion,
 relevantAttributesHash)
```

Never key solely by `resourceId` when decisions depend on user, tenant, limits, or action. If IDs are unique only per tenant, include tenant in the key; if decisions depend on invoice state, include version or corresponding invalidation.

### 13.1. Privilege accumulation via bad cache keys

Example:

```text
ALICE / T1 / invoice#101 / APPROVE -> ALLOW
Cache key = "invoice:101"
BOB / T1 / invoice#101 / APPROVE -> cache hit ALLOW
```

Such a cache key is an **authorization vulnerability**. It is equally dangerous to cache an ALLOW for `version=3` and apply it to `version=4` after it became `APPROVED` or changed tenants.

### 13.2. Positive vs negative caching

- **ALLOW cache:** high performance yet risks stale grants; weigh short TTLs, policy versioning, and invalidation.
- **DENY cache:** can delay newly granted permissions from taking effect; requires a documented latency contract.
- **INDETERMINATE / ERROR:** never cache as ALLOW; typically needs backoff/circuit-breakers.
- **Policy deploy:** every cache must be `policyVersion`-aware or flushed appropriately.

For approvals/payments/privileged actions, the simplest safe strategy is typically **not caching ALLOW across resource versions**, or re-evaluating policy directly at the mutation point.

## 14. Observability and auditing of PEP/PDP

Authorization failures are critical security signals, yet secrets must stay out of logs. Useful fields to log:

| Audit field | Example |
| --- | --- |
| `requestId` | Correlation ID |
| `subjectId` | Protected/encoded internal stable ID |
| `tenantId` | Canonical tenant |
| `action` | `INVOICE_APPROVE` |
| `resourceRef` | `"INVOICE:101"` with proper retention |
| `decision` | ALLOW/DENY/INDETERMINATE |
| `reasonCode` | `OVER_LIMIT`, `CROSS_TENANT` |
| `policyVersion` | `approval-policy-v12` |
| `decisionLatency` | PDP call duration |
| `enforcementPoint` | HTTP / METHOD / DOMAIN |
| `resourceVersion` | Version at evaluation time |
| `outcome` | MUTATION_COMMITTED / ROLLED_BACK / NOT_RUN |

**Distinguish two events:**

1. **Authorization decision:** PDP returned ALLOW at T1.
2. **Business mutation:** actual transaction committed/rolled back at T2.

An ALLOW followed by a transaction rollback is not proof the action succeeded. Conversely, a DENY where DB state still changed is a **critical vulnerability**. Integration tests must assert resource state after denials.

**Never log:** raw access tokens, refresh tokens, passwords, session cookies, full invoice metadata containing PII, or sensitive request bodies.

## 15. Tenant scoping, maker–checker, and approval limits

### 15.1. Tenant scope must come from the server

A caller might send:

```json
{
  "invoiceId": 102,
  "tenantId": "T2",
  "actorId": "u-carol"
}
```

If the manager uses this `tenantId`/`actorId` when querying the PDP, Alice could impersonate Carol. The manager must use authenticated identity and the directory; invoice tenant must come from the DB.

### 15.2. Maker–checker is not a static role

Even when a user holds `invoice:approve`, policy must block:

```text
invoice.creatorId == actor.userId
```

If actor/creator were stored only as mutable usernames that could collide, use stable subject IDs. Never compare display names or unverified emails.

### 15.3. Approval limits need exact units

The demo uses `long amount` and `long approvalLimit` in the same integer unit to avoid floating-point errors. In real payment systems:

- Use minor units (e.g., cents) or `BigDecimal` with strict scale and currency.
- Limits may depend on currency, tenant, product, transaction type, and time window.
- Never allow clients to declare limits or approval roles.
- When policy limits change, caches/decision versions must reflect the change.
- For daily or cumulative limits, read-then-write checks are insufficient; transactional/atomic budget reservations are required.

## 16. When to use `@PreAuthorize("@bean...")` instead of a custom manager?

A shorter alternative:

```java
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "@invoicePolicyGuard.canApprove(authentication, #invoiceId)"
)
public String approve(Long invoiceId) {
    return invoiceService.approve(invoiceId);
}
```

This is a **design snippet**, not part of the demo code. `invoicePolicyGuard` is a custom bean returning a boolean from `Authentication` and the ID. It can invoke the same `PolicyDecisionClient` used above.

Pros:

- Quick for a few rules.
- Familiar to Spring Method Security users.
- Less advisor boilerplate.

Cons:

- Complex logic inside SpEL becomes harder to test/reuse.
- Harder to unify policy mapping and auditing across HTTP and methods.
- Bypassed if the method does not go through a Spring proxy.
- Lacks the abstraction benefits of custom `AuthorizationManager<T>` for composition and observability.

**Choose a custom `AuthorizationManager`** when you need to standardize across multiple context types, reuse PDP adapters, return structured decisions, test cleanly, compose managers, or integrate with HTTP/message authorization.

Do not replace a working mechanism solely because "custom manager sounds more modern". Value lies in security boundaries and clear policy contracts.

## 17. Common mistakes and fixes

| Issue | Symptom | Fix |
| --- | --- | --- |
| Checking only static role | Approvers approve any tenant/invoice | Query PDP with authoritative resource/tenant |
| Taking `actorId` from JSON | Clients impersonate others | Derive from `Authentication` and trusted directory |
| Taking `tenantId` from unverified header | Cross-tenant access | Verify membership before building policy request |
| Manager returns `null` when PDP is down | Composition may abstain and allow | Explicit `AuthorizationDecision(false)` |
| Catching exception and returning allow | PDP outage opens access | Fail closed, log, and alert |
| Unrecognized response | `"UNKNOWN"` treated as true | Map only `ALLOW` to granted; deny everything else |
| Missing timeouts | Worker threads hang indefinitely | Connection/request deadlines, bulkheads |
| Unbounded retries | PDP overload cascades into app | Bounded retries within request deadline |
| Cache key uses resource ID only | Alice's permissions apply to Bob | Key on subject/tenant/action/version |
| Cached allow persists after revoke | User still approves after revocation | Versioning/invalidation/re-checking |
| Using stale resource attributes | Already-approved invoice gets approved again | Versioned snapshots and DB conditional writes |
| Using `@PostAuthorize` for writes | Mutations can commit before denial | Before-method checks + transaction guards |
| Custom advisor does not match | Method runs without consulting PDP | Test allow and deny through Spring-managed proxy |
| Self-invocation `this.approve()` | Bypasses AOP authorization | Separate secured service/bean, test real call paths |
| Manager reads wrong parameter position | Evaluates a different resource | Use annotation contracts/typed adapters |
| Policy service checks ID without tenant | BOLA/cross-tenant | Tenant-scoped resource lookups |
| Treating anonymous `isAuthenticated()` as real user | Anonymous bypass | `AuthenticationTrustResolver`/security expressions |
| Misusing `anyOf` | One manager allows bypassing tenant | Use AND on mandatory boundaries |
| All abstain with `allOf` | May default to granted | Use overload with default deny and explicit denials |
| Two manager beans without disambiguation | DI ambiguity | `@Qualifier`, `@Primary`, `@Profile` |
| HTTP-only policy | Schedulers/batch jobs bypass | Method/domain guards |
| Lost policy version on write | Stale decision still used | Compare versions or re-evaluate |
| Unit test instantiates `new InvoiceService()` | No interceptor attached | `@SpringBootTest`/proxy integration tests |
| Testing DENY cases only | Always-deny advisor still passes | Test ALLOW, DENY, and state transitions |
| Audit logs ALLOW = committed | Misreports actual outcome | Separate PDP decision from mutation outcome |

### Pre-release checklist

1. Does `AuthorizationManager<T>` match the generic type for request or method?
2. Does `Supplier<Authentication>` come from Spring Security, not JSON?
3. Are anonymous/unknown principals denied?
4. Is `action` server-determined and allowlisted?
5. Are resource/tenant/creator/state/amount fetched from authoritative DB/server sources?
6. Does the PDP enforce inter-service auth, TLS, and egress controls?
7. Does the client enforce timeouts, circuit breakers, and bounded retries?
8. Is `ALLOW` accepted only on valid responses matching scope/version?
9. Do `DENY`, `NOT_APPLICABLE`, `INDETERMINATE`, timeouts, and 5xx all fail closed?
10. Does the advisor/pointcut match the target method on the Spring proxy?
11. Are allow/deny/missing role/cross-tenant/self-approve/over-limit tested?
12. Is DB immutability verified after denials?
13. Are re-checks/conditional writes/locks in place for state or grant changes between check and use?
14. Are cache keys scoped by subject/tenant/action/resource/policy version with invalidation?
15. Are decisions + mutation outcomes + policy versions audited without logging secrets?
16. On major Spring Security upgrades, has `check()`/`authorize()` migration been verified?

## 18. Exercises

### Exercise 1 – One role, two tenants

Alice is in `T1` and holds `invoice:approve`. Invoice `102` belongs to `T2`. `@PreAuthorize("hasAuthority('invoice:approve')")` passes, so what must the PDP return?

**Answer:** `DENY`, because the resource's tenant differs from the actor's trusted tenant. Functional permissions and tenant scope combine with AND.

### Exercise 2 – Policy returns `NOT_APPLICABLE`

A new request uses action `INVOICE_EXPORT` while the PDP only knows `INVOICE_APPROVE`. What should the manager return?

**Answer:** Under this lesson's contract, explicit deny. Never turn "no policy" into allow.

### Exercise 3 – PDP timeout

The remote policy service fails to respond within the deadline. If code has `catch (Exception) { return new AuthorizationDecision(true); }`, what is the risk?

**Answer:** PDP unavailability becomes a bypass for every authorization check. It must fail closed and classify the incident.

### Exercise 4 – Resource changes after decision

The PDP ALLOWs because the invoice is `PENDING`, yet another transaction transitions it to `APPROVED` before the update. Is the manager alone sufficient?

**Answer:** No. Writes require state/version guards via transactions, conditional UPDATEs, or appropriate locking/re-checking.

### Exercise 5 – Cache missing tenant

Cache key `(invoiceId, action)` stores Alice's ALLOW. Bob queries the same ID. Why is this dangerous?

**Answer:** Decisions depend on **subject, tenant, limit, and policy version**; omitting them from the cache key leaks results across principals.

### Exercise 6 – Manager does not run in tests

A `@WithMockUser` test invokes the service via `new`, or calls an internal method via `this.approve`. Why was the PDP never called?

**Answer:** Spring Method Security relies on AOP proxies. Call Spring-managed beans through the proxy, or enforce at an independent domain boundary that cannot be bypassed.

### Exercise 7 – `allOf` when managers return null

Both managers return null. Is the request guaranteed to be denied?

**Answer:** Do not assume so. `allOf` can use abstain semantics; configure an all-abstain default DENY and prefer explicit DENY when information is missing.

### Exercise 8 – HTTP-only approval protection

The controller uses an HTTP manager, yet a scheduled job calls the approval service directly. Is it protected?

**Answer:** HTTP filters do not execute on job threads. Method Security/domain guards or a controlled authoritative mutation path is required.

### Exercise 9 – Upgrading Spring Security 6.5 to 7.x

Why must implementations overriding `check(...)` be reviewed?

**Answer:** Spring Security 6.5 deprecates `check`, moving toward `authorize(...)` returning `AuthorizationResult`. New major versions can change abstract contracts; consult API/version-migration docs.

### Exercise 10 – PDP returns ALLOW on client-supplied tenant data

Should the response be trusted?

**Answer:** No. A PDP cannot fix bad input facts; policy requests must be built from verified authentication and authoritative resource attributes.

### Exercise 11 – Remote PDP returns deny yet the service already updated the DB

Is an HTTP 403 status enough to prove safety?

**Answer:** No. Verify actual DB state, transaction rollbacks, and enforcement ordering relative to side effects.

### Exercise 12 – Maker–checker and roles

A user holds `invoice:approve` and sufficient limit yet created the invoice themselves. Which rule must block it?

**Answer:** `actor.userId != invoice.creatorId`; valid roles and limits do not override separation of duties.

## 19. Official references

1. [Spring Security 6.5 – Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): `AuthorizationManager`, PEP contexts, static/dynamic composition.
2. [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `AuthorizationManagerBeforeMethodInterceptor`, custom managers, pointcuts, proxy/annotation behavior.
3. [Spring Security 6.5 – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): integrating policy agents/remote services with `AuthorizationManager<RequestAuthorizationContext>`.
4. [Spring Security 6.5 API – `AuthorizationManager<T>`](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): `check`, `authorize`, `verify`, and deprecation.
5. [Spring Security 6.5 API – `AuthorizationDecision`](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationDecision.html): explicit granted/denied results.
6. [Spring Security 6.5 API – `AuthorizationManagers`](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManagers.html): `allOf`/`anyOf`, handling all-abstain defaults.
7. [Spring Security 6.5 API – `AuthorizationManagerBeforeMethodInterceptor`](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/authorization/method/AuthorizationManagerBeforeMethodInterceptor.html): pointcut + manager constructor, advisor.
8. [Spring Framework 6.2 API – `AnnotationMatchingPointcut`](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/aop/support/annotation/AnnotationMatchingPointcut.html): `forMethodAnnotation`.
9. [Spring Framework – Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): `@Transactional`, self-invocation, transaction boundaries.
10. [Spring Security – Test Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser`, and Method Security integration tests.
11. [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, resource-level checks.

**Conclusion:** `AuthorizationManager<T>` is a consistent extension point for **Spring Security to enforce decisions from a policy service**. The manager must identify the right action/resource, obtain trusted authentication and attributes, query the PDP, accurately interpret `ALLOW`/`DENY`/errors, and return an explicit authorization result. When permissions and resources change over time, add transactions/re-checks/conditional writes; for remote PDPs, include timeouts, caching/versioning, auditing, and fail-closed behavior. A valid role, a valid token, or a stale ALLOW alone **is never enough** to guarantee the final authorization decision.