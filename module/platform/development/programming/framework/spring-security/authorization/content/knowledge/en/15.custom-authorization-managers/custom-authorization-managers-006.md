# Combining Static Permissions with Dynamic Business Conditions in Spring Security

## 1. The Problem: Having an Approval Permission Is Not Enough to Approve Every Record

Suppose an invoice management system uses `Spring Security - authorization`. Employee `alice` has the `invoice:approve` authority, yet that **does not mean** she can approve every invoice. When approving an invoice, the business simultaneously requires:

- The caller has the `invoice:approve` authority.
- The invoice belongs to the **same tenant** as the approver.
- The invoice is currently in `PENDING` state.
- The invoice total does not exceed the approval limit granted to this person.
- The approver is **not the creator** of the invoice (maker–checker principle).

The first condition is a **static permission**: a `GrantedAuthority` granted from authentication/organizational authorization. The subsequent conditions are **dynamic permissions**: decisions vary by caller, record state, limits, business policy, and execution time.

This lesson shows how to combine them so an **operation is allowed only when both layers of conditions pass**. Within the parent topic **Custom AuthorizationManager**, we will build an `AuthorizationManager<MethodInvocation>` combining two rules via `AuthorizationManagers.allOf(...)`, register a method-security interceptor with a custom pointcut, and test against real Spring beans. The lesson also presents a shorter alternative with `@PreAuthorize` and how to close the gap between permission checks and database updates.

Goals after this lesson:

1. Distinguish authorities/roles from per-resource business conditions.
2. Design a `STATIC AND DYNAMIC` composition following default-deny.
3. Understand `AuthorizationManager`, `AuthorizationDecision`, `MethodInvocation`, and `AuthorizationManagerBeforeMethodInterceptor`.
4. Create a custom business annotation, wire it to a Spring AOP advisor, and apply it to a service.
5. Run Java 17+ / Spring Boot and observe allow or deny results across multiple users and scenarios.
6. Test Spring proxies properly, guard against self-invocation, prevent tenant/owner spoofing, and handle concurrency and permission revocation.

**Scope:** Method Security via Spring AOP proxies on Spring Security 6.x. Web `authorizeHttpRequests(...)` rules, Spring Security ACL, and OAuth2 scopes are related, yet do not replace the single-record approval problem.

## 2. Distinguishing Static Permissions, Dynamic Permissions, and Composition Operators

### 2.1. What Is a Static Permission?

`Authentication` holds a list of `GrantedAuthority` objects, for example:

```text
alice:
  invoice:read
  invoice:approve

bob:
  invoice:read

carol:
  invoice:approve
```

With Spring Security, `hasAuthority('invoice:approve')` looks for the exact authority string `invoice:approve`. `hasRole('APPROVER')` under default settings is a convenient shorthand to check `ROLE_APPROVER`. Never confuse `APPROVER`, `ROLE_APPROVER`, and `invoice:approve`: they are only equivalent if the application defines an explicit mapping rule.

An authority reflects a **general capability**, such as being allowed to access the approval feature, generate reports, or edit orders. It does not inherently contain each invoice's state, current limits, or database ownership.

### 2.2. What Is a Dynamic Permission?

A rule can be written as a function:

```text
canApprove(user, invoice, businessPolicy)
    = sameTenant(user, invoice)
      AND invoice.status == PENDING
      AND invoice.amount <= user.approvalLimit
      AND invoice.creator != user
```

The sources of `user.approvalLimit` and `invoice.status` must be **server-side trusted**. Never treat an `X-Tenant` header or a `createdBy` or `approvalLimit` field in client-submitted JSON as proof of permission. In a real application, these attributes are verified via trusted tokens combined with a directory, repository, or ACL server.

Dynamic permissions may also depend on business hours, approval workflows, lock states, quotas, group membership, tenant, region, product settings, or contract status. Such conditions should live in a testable policy layer rather than scattered across controllers.

### 2.3. Why AND Instead of OR?

| Has `invoice:approve`? | Business conditions pass? | Result |
| --- | --- | --- |
| No | No | Deny |
| No | Yes | Deny |
| Yes | No | Deny |
| Yes | Yes | Allow |

Correct expression:

```text
ALLOW = HAS_AUTHORITY("invoice:approve") AND BUSINESS_RULE_ACCEPTS
```

If `OR` were used, a user with the static authority would bypass all tenant/limit/state constraints, or a user lacking the authority could still approve simply because the invoice satisfied the other conditions. Use `OR` only when the policy has an **explicitly defined and tightly controlled** exception branch, such as an independently evaluated administrative override; never add an `ADMIN` exception by guesswork.

**Default deny:** when user, target, state, limit, or policy source is missing, the result is `false`. Never treat a data-read exception as a reason to grant access.

## 3. Where Does `AuthorizationManager` Sit in the Call?

Spring Security provides the `AuthorizationManager<T>` interface to make decisions before or after an operation. For method security, `T` is typically `MethodInvocation` (before method) or `MethodInvocationResult` (after method). Key parameters include:

- `Supplier<Authentication>`: provides the executing identity.
- `MethodInvocation`: target method, target instance, arguments, and invocation context.
- `AuthorizationDecision`: allow (`true`) or deny (`false`) outcome, a subtype of `AuthorizationResult`.

In Spring Security 6.5, `check(Supplier<Authentication>, T)` is the legacy abstract method; `authorize(...)` may delegate to it and is recommended for new APIs. When using a **lambda `AuthorizationManager<T>`** in this version, the lambda returns `AuthorizationDecision`. In Spring Security 7, `authorize(...)` becomes the abstract method, so classes implementing the interface directly have signature differences; check your version before upgrading. The examples below are pinned to Spring Boot 3.5's Spring Security 6.x line.

Execution flow:

```text
Caller -> Spring-managed ApprovalService proxy
                    |
                    v
       AuthorizationManagerBeforeMethodInterceptor
              (pointcut @ApproveInvoice)
                    |
                    v
       AuthorizationManagers.allOf(...)
              /                 \
             v                   v
    Static authorization    Dynamic authorization
    invoice:approve         policy.canApprove(auth, id)
              \                 /
               v               v
           DENY if any condition is false
                    |
            granted? +--- no --> AccessDeniedException
                    |
                   yes
                    v
              ApprovalService.approve(id)
                    |
                    v
                  Database
```

**Two separate concerns:** the proxy/pointcut decides *when the policy runs*, while `AuthorizationManager` decides *whether access is allowed*. If the caller creates the service with `new` or calls an internal method `this.approve(...)` inside the same bean, protected method advice can be bypassed. An annotation does not automatically enforce checks on every Java call.

## 4. Two Implementation Styles and When to Choose Each

### Style A: `@PreAuthorize` + Policy Bean

If only a few methods need combined rules, you can write:

```java
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "@invoicePolicy.canApprove(authentication, #p0)"
)
public Invoice approve(Long invoiceId) {
    // ...
}
```

`#p0` is the first parameter. `authentication` is injected into the expression context by Spring Method Security. `@invoicePolicy` is a Spring bean with method `canApprove`. SpEL `and` clearly expresses that both conditions must be true. This approach is readable and avoids creating a custom advisor.

### Style B: Custom `AuthorizationManager` + Custom Annotation

When multiple services share one policy, you want plain Java for testing, want to compose multiple managers, and want an explicit pointcut, you can use:

```java
@ApproveInvoice
public Invoice approve(Long invoiceId) {
    // ...
}
```

This annotation **only works** when an advisor is registered to recognize it. We build the advisor ourselves, combining Spring's static authority manager and the business manager.

The complete demo uses **Style B** to highlight the nature of a custom `AuthorizationManager`. Style A is a valid alternative; you do not need to apply both layers simultaneously to the same method.

## 5. Complete Java 17+ Example: Invoice Approval by Authority and Dynamic Policy

The example uses Spring Boot **3.5.8** (Java 17; Spring Security 6.5.x), Gradle, and in-memory mock data. No HTTP server or database is required. The application simulates three users:

| User | Tenant | Limit | Authority |
| --- | --- | --- | --- |
| `alice` | `T1` | 1.000 | `invoice:approve` |
| `bob` | `T1` | 1.000 | `invoice:read` |
| `carol` | `T2` | 1.500 | `invoice:approve` |

The demo invoices have different states and creators to test both kinds of conditions. All monetary amounts in this lesson are **dummy units**, with no exchange rates or currency rules.

### 5.1. Structure and Dependencies

```text
invoice-authorization-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── InvoiceAuthorizationApplication.java
    │   ├── Invoice.java
    │   ├── InvoiceStore.java
    │   ├── ApproverDirectory.java
    │   ├── InvoicePolicy.java
    │   ├── ApproveInvoice.java
    │   ├── InvoiceSecurityConfig.java
    │   └── ApprovalService.java
    └── test/java/demo/
        └── ApprovalServiceTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'invoice-authorization-demo'
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

`spring-boot-starter-security` provides Spring Security; `@EnableMethodSecurity` activates method security in the configuration. Method-level checks still rely on Spring AOP proxies. The Gradle Wrapper is not included in the file list: you can generate a Wrapper with a Gradle version compatible with Spring Boot 3.5 if the project lacks one.

### 5.2. Invoice Entity: Server-Side Data

**`src/main/java/demo/Invoice.java`:**

```java
package demo;

public record Invoice(
        long id,
        String tenant,
        String createdBy,
        long amount,
        State state) {

    public enum State {
        PENDING, APPROVED
    }
}
```

**`src/main/java/demo/InvoiceStore.java`:**

```java
package demo;

import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

@Component
public class InvoiceStore {

    private final Map<Long, Invoice> invoices = new ConcurrentHashMap<>();

    public InvoiceStore() {
        invoices.put(101L, new Invoice(
            101L, "T1", "mary", 700L, Invoice.State.PENDING));
        invoices.put(102L, new Invoice(
            102L, "T2", "mary", 500L, Invoice.State.PENDING));
        invoices.put(103L, new Invoice(
            103L, "T1", "mary", 1_500L, Invoice.State.PENDING));
        invoices.put(104L, new Invoice(
            104L, "T1", "mary", 200L, Invoice.State.APPROVED));
        invoices.put(105L, new Invoice(
            105L, "T1", "alice", 200L, Invoice.State.PENDING));
    }

    public Optional<Invoice> find(long id) {
        return Optional.ofNullable(invoices.get(id));
    }

    public Invoice approve(long id) {
        return invoices.compute(id, (key, current) -> {
            if (current == null) {
                throw new NoSuchElementException("Invoice not found: " + id);
            }
            if (current.state() != Invoice.State.PENDING) {
                throw new IllegalStateException("Invoice already processed");
            }
            return new Invoice(
                current.id(), current.tenant(),
                current.createdBy(), current.amount(),
                Invoice.State.APPROVED
            );
        });
    }
}
```

`ConcurrentHashMap.compute` performs a single-key update atomically in the demo, so an `APPROVED` invoice cannot be approved again. **It does not turn the pre-method policy check into an atomic security transaction**: in real products, you must guarantee permissions and data cannot change unexpectedly between check time and update time.

### 5.3. Server-Managed Limit Directory

**`src/main/java/demo/ApproverDirectory.java`:**

```java
package demo;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

record ApproverProfile(String tenant, long limit) {
}

@Component
public class ApproverDirectory {

    private final Map<String, ApproverProfile> profiles = Map.of(
        "alice", new ApproverProfile("T1", 1_000L),
        "bob",   new ApproverProfile("T1", 1_000L),
        "carol", new ApproverProfile("T2", 1_500L)
    );

    public Optional<ApproverProfile> find(String username) {
        return Optional.ofNullable(profiles.get(username));
    }
}
```

This table simulates a trusted directory. The approval limit is not passed as a parameter to `approve(...)`, so clients cannot raise their own limits by editing a request body. In production, manage directory data through controlled mechanisms and account for cache/revocation timing.

### 5.4. Dynamic Policy, Separated from Controller and Service

**`src/main/java/demo/InvoicePolicy.java`:**

```java
package demo;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("invoicePolicy")
public class InvoicePolicy {

    private final InvoiceStore store;
    private final ApproverDirectory directory;

    public InvoicePolicy(InvoiceStore store, ApproverDirectory directory) {
        this.store = store;
        this.directory = directory;
    }

    public boolean canApprove(Authentication authentication, long id) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        var profile = directory.find(authentication.getName()).orElse(null);
        var invoice = store.find(id).orElse(null);

        if (profile == null || invoice == null) {
            return false;
        }

        return profile.tenant().equals(invoice.tenant())
            && invoice.state() == Invoice.State.PENDING
            && invoice.amount() <= profile.limit()
            && !authentication.getName().equals(invoice.createdBy());
    }
}
```

`InvoicePolicy` only decides **dynamic permissions** from server data. It does not grant authorities itself. This separation allows testing each part independently: authorities are checked in the static manager, while tenant, status, limit, and maker–checker constraints are checked inside the policy.

Every undetermined case (unauthenticated, missing profile, missing invoice) returns `false`; this is **fail closed** design. In real systems, also check constraints such as locked accounts, suspended states, delegations, active tenant, and ACL versions when required by the business.

### 5.5. Creating a Custom Annotation

**`src/main/java/demo/ApproveInvoice.java`:**

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface ApproveInvoice {
}
```

The annotation has runtime retention so the pointcut can detect it. It **does not enforce security on its own**; the next part registers the corresponding advisor.

### 5.6. Combining `AuthorityAuthorizationManager` and the Business Manager

**`src/main/java/demo/InvoiceSecurityConfig.java`:**

```java
package demo;

import org.aopalliance.intercept.MethodInvocation;
import org.springframework.aop.Advisor;
import org.springframework.aop.support.annotation.AnnotationMatchingPointcut;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Role;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.authorization.method.AuthorizationManagerBeforeMethodInterceptor;
import org.springframework.security.core.Authentication;

@Configuration
public class InvoiceSecurityConfig {

    @Bean
    @Role(BeanDefinition.ROLE_INFRASTRUCTURE)
    Advisor invoiceApprovalAdvisor(InvoicePolicy policy) {

        // Condition 1: static authority from Authentication.
        AuthorizationManager<MethodInvocation> staticRule =
            AuthorityAuthorizationManager.hasAuthority("invoice:approve");

        // Condition 2: dynamic business logic, based on server-side policy.
        AuthorizationManager<MethodInvocation> dynamicRule =
            (authenticationSupplier, invocation) -> {
                Authentication authentication = authenticationSupplier.get();
                Object[] args = invocation.getArguments();

                if (args.length != 1 || !(args[0] instanceof Long id)) {
                    return new AuthorizationDecision(false);
                }

                return new AuthorizationDecision(
                    policy.canApprove(authentication, id)
                );
            };

        // Allow only when BOTH rules allow.
        AuthorizationManager<MethodInvocation> combined =
            AuthorizationManagers.allOf(staticRule, dynamicRule);

        // Intercept only public methods annotated with @ApproveInvoice.
        return new AuthorizationManagerBeforeMethodInterceptor(
            AnnotationMatchingPointcut.forMethodAnnotation(
                ApproveInvoice.class),
            combined
        );
    }
}
```

**Step-by-step explanation:**

1. `AuthorityAuthorizationManager.hasAuthority("invoice:approve")` reads `GrantedAuthority` from `Authentication`; it does not inspect invoices.
2. `dynamicRule` receives `MethodInvocation`, validates a single `Long` parameter, and invokes `InvoicePolicy` to evaluate real data.
3. `AuthorizationManagers.allOf(staticRule, dynamicRule)` composes the two managers with **AND** semantics. Both in the example return explicit decisions, avoiding ambiguous `null`/abstain cases.
4. `AnnotationMatchingPointcut.forMethodAnnotation(ApproveInvoice.class)` identifies the exact methods to protect.
5. `AuthorizationManagerBeforeMethodInterceptor` requires an allow decision **before** executing the method body.
6. `@Role(BeanDefinition.ROLE_INFRASTRUCTURE)` marks the advisor as AOP infrastructure. It does not grant permissions to any user.

In Spring Security 6.5, `AuthorizationManager` is a functional interface backed by `check(...)`; the lambda above is concise Java compatible with that version line. When upgrading to Spring Security 7, check `authorize(...)` API changes and the corresponding Spring Framework/Boot dependencies. Never copy code across versions assuming every signature remains unchanged.

**Do not use `anyOf` here.** `anyOf` represents OR and would weaken the policy. If you need extra conditions such as `isAccountActive` or `isInApprovalWindow`, add managers to `allOf` or consolidate them into the policy while preserving testability and default-deny.

**Important:** the advisor above applies to methods directly annotated with `@ApproveInvoice`. To protect classes, interfaces, overloaded methods, or meta-annotations, design and test the corresponding pointcut. In the demo, the annotation sits on one concrete public method to eliminate ambiguity.

### 5.7. Service with a Protected Approval Path

**`src/main/java/demo/ApprovalService.java`:**

```java
package demo;

import org.springframework.stereotype.Service;

@Service
public class ApprovalService {

    private final InvoiceStore store;

    public ApprovalService(InvoiceStore store) {
        this.store = store;
    }

    @ApproveInvoice
    public Invoice approve(Long id) {
        return store.approve(id);
    }
}
```

Do not repeat the authority check in the Java body because the advisor already enforces it before invocation. However, **a real database write path needs atomic state and permission constraints** when multiple users act concurrently; the simple service only highlights Spring Security's check timing.

Method `approve` is `public` on a `@Service` bean. Callers must obtain the bean from Spring, never `new ApprovalService(...)` and never rely on self-invocation.

### 5.8. Enabling Method Security, Simulating Authentication, and Running

**`src/main/java/demo/InvoiceAuthorizationApplication.java`:**

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
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableMethodSecurity
public class InvoiceAuthorizationApplication {

    public static void main(String[] args) {
        SpringApplication.run(InvoiceAuthorizationApplication.class, args);
    }

    @Bean
    @Profile("!test")
    CommandLineRunner scenario(ApprovalService service) {
        return args -> {
            try {
                signInAs("alice", "invoice:approve");

                System.out.println("ALICE_101: "
                    + service.approve(101L).state());

                expectDenied("ALICE_REPEAT_101",
                    () -> service.approve(101L));
                expectDenied("ALICE_CROSS_TENANT_102",
                    () -> service.approve(102L));
                expectDenied("ALICE_OVER_LIMIT_103",
                    () -> service.approve(103L));
                expectDenied("ALICE_ALREADY_APPROVED_104",
                    () -> service.approve(104L));
                expectDenied("ALICE_SELF_APPROVAL_105",
                    () -> service.approve(105L));

                signInAs("bob", "invoice:read");
                expectDenied("BOB_NO_AUTHORITY_105",
                    () -> service.approve(105L));

                signInAs("carol", "invoice:approve");
                System.out.println("CAROL_T2_102: "
                    + service.approve(102L).state());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void signInAs(String username, String authority) {
        var token = new UsernamePasswordAuthenticationToken(
            username,
            "demo-only",
            List.of(new SimpleGrantedAuthority(authority))
        );
        SecurityContextHolder.getContext().setAuthentication(token);
    }

    private static void expectDenied(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException expected) {
            System.out.println(label + ": DENIED");
        }
    }
}
```

`@EnableMethodSecurity` activates standard method security; the custom advisor in `InvoiceSecurityConfig` is picked up via `@Configuration` component scanning. `@Profile("!test")` prevents the scenario runner from mutating invoice states when unit/integration tests run under the `test` profile.

In the example, `UsernamePasswordAuthenticationToken` is constructed manually **only to simulate an authenticated principal**; this is not a production HTTP authentication flow. In a real application, identity must come from a controlled session/JWT/OIDC mechanism or authentication provider with trusted tenant/authorities.

Run the application in the directory containing `build.gradle`:

```bash
./gradlew bootRun
```

On Windows, use `.\gradlew.bat bootRun`. If there is no Wrapper yet and a compatible Gradle is installed, you can run `gradle bootRun`.

**Expected output from the demo's `System.out.println` statements alone**, aside from Spring startup logs:

```text
ALICE_101: APPROVED
ALICE_REPEAT_101: DENIED
ALICE_CROSS_TENANT_102: DENIED
ALICE_OVER_LIMIT_103: DENIED
ALICE_ALREADY_APPROVED_104: DENIED
ALICE_SELF_APPROVAL_105: DENIED
BOB_NO_AUTHORITY_105: DENIED
CAROL_T2_102: APPROVED
```

Explanation:

- `alice` has authority `invoice:approve`, belongs to tenant `T1`, limit 1.000; invoice `101` is `PENDING`, belongs to `T1`, amount 700, created by `mary`: **approved**.
- Re-approving `101` is invalid because its state already changed to `APPROVED`.
- Invoice `102` belongs to another tenant, `103` exceeds the limit, `104` is already approved, and `105` was created by `alice` herself: **dynamic policy denies** despite valid static authority.
- `bob` belongs to `T1`, has sufficient limit for invoice `105`, and is not its creator, yet only has `invoice:read`: **static manager denies**.
- `carol` has the right authority, belongs to tenant `T2`, and has limit 1.500, so she can approve `102`.

The results accurately illustrate **AND** semantics: allowed only when both authority and business conditions pass.

## 6. Integration Testing: Proving Both Permission Layers Work

Create **`src/test/java/demo/ApprovalServiceTest.java`**:

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
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ApprovalServiceTest {

    @Autowired
    ApprovalService service;

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:approve")
    void approvesWhenBothStaticAndDynamicRulesPass() {
        assertEquals(
            Invoice.State.APPROVED,
            service.approve(101L).state()
        );

        // Same user, same authority, yet state has changed.
        assertThrows(AccessDeniedException.class,
            () -> service.approve(101L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "invoice:approve")
    void rejectsTenantLimitStatusAndSelfApprovalViolations() {
        assertThrows(AccessDeniedException.class,
            () -> service.approve(102L));
        assertThrows(AccessDeniedException.class,
            () -> service.approve(103L));
        assertThrows(AccessDeniedException.class,
            () -> service.approve(104L));
        assertThrows(AccessDeniedException.class,
            () -> service.approve(105L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "invoice:read")
    void rejectsWhenStaticAuthorityMissing() {
        // Bob has a T1 profile and did not create #105;
        // business conditions may pass, yet the authority is missing.
        assertThrows(AccessDeniedException.class,
            () -> service.approve(105L));
    }

    @Test
    @WithMockUser(username = "carol", authorities = "invoice:approve")
    void allowsApproverInMatchingTenant() {
        assertEquals(
            Invoice.State.APPROVED,
            service.approve(102L).state()
        );
    }

    @Test
    @WithAnonymousUser
    void deniesAnonymousAccess() {
        assertThrows(AccessDeniedException.class,
            () -> service.approve(101L));
    }

    @Test
    @WithMockUser(username = "unknown", authorities = "invoice:approve")
    void failsClosedWhenServerProfileMissing() {
        assertThrows(AccessDeniedException.class,
            () -> service.approve(101L));
    }
}
```

Run:

```bash
./gradlew test
```

`@WithMockUser` and `@WithAnonymousUser` come from `spring-security-test`. Each test calls the Spring-injected `ApprovalService`, giving the custom advisor **the chance to intercept the call**. `@DirtiesContext` resets the context after each test so `ConcurrentHashMap` mutations from one test do not affect subsequent tests. In real code, resetting test fixtures can replace this to save time.

**Most critical cases**: sufficient authority yet wrong tenant, matching tenant yet missing authority, both satisfied, resource whose state changed, principal missing from directory, and anonymous caller. Testing only the "allow" path does not prove the security policy is enforced.

For deeper testing, you can unit test `InvoicePolicy` directly with known entities and profiles, and test `AuthorizationManager` with a mock `MethodInvocation`. Still, **integration tests through Spring AOP** remain essential to catch pointcut, bean/proxy, and configuration errors.

## 7. Technical Points to Understand When Using Custom AuthorizationManagers

### 7.1. `allOf` Is Safe Only When There Are No Ambiguous Decisions

`AuthorizationManagers.allOf` combines multiple `AuthorizationManager`s requiring all to permit. Some Spring managers can return `null` to **abstain**. Overloads and all-abstain scenarios have their own default rules, so `null` must not be assumed to mean deny in every version.

In the example, the dynamic manager **always returns `AuthorizationDecision(true/false)`**; the static authority manager also produces a clear decision. This eliminates "checked nothing yet still allowed" due to abstain. If using multiple custom managers, explicitly enforce default-deny when no rule matches, including empty lists or all-abstain outcomes.

### 7.2. The Advisor Must Be Applied at the Right Boundary

`@ApproveInvoice` is a custom annotation, **not `@PreAuthorize`**. Creating the annotation and manager while forgetting to register `AuthorizationManagerBeforeMethodInterceptor` leaves the method running as ordinary Java. Likewise, `AnnotationMatchingPointcut` only intercepts matching methods; **other methods are not protected automatically**.

With default proxying:

- Calling `service.approve(id)` through the Spring-managed bean: advisor is evaluated.
- Manually doing `new ApprovalService(store)`: no proxy, advisor is skipped.
- Calling `this.approve(id)` from another method on the same target: self-invocation can bypass advice.
- `private`/`final` methods are not reliable boundaries for subclass proxies; use public service methods.
- With JDK interface proxies, callers must invoke through the interface method exposed by the proxy; test the actual pointcut if the annotation is placed on an interface.
- `@EnableMethodSecurity` and the advisor must be loaded in the proper `ApplicationContext`.

In multi-service designs, you can place approval methods in a dedicated bean and route every call through that bean.

### 7.3. Do Not Mix the Three Types of Data Sources

| Data | Source to use | Never trust |
| --- | --- | --- |
| `Authentication` and authorities | Verified authentication provider/token | Username or role self-sent by client in JSON |
| Approver tenant and limit | Verified server directory/claims + fresh check | Unverified `X-Tenant` or `limit` |
| Invoice status/creator/amount | Server repository/database | Client-constructed invoice DTO from request |

The policy must check **the exact same record the update operation will modify**. Never check permissions on document `A` and accidentally update document `B`; never inspect owner from a DTO while ignoring the persisted record.

### 7.4. `AND` Does Not Automatically Guarantee Atomicity

`@PreAuthorize` or a custom before-method interceptor checks before the method body runs. Between **check** and **update**, the record or caller's permissions may change. This is TOCTOU (*time of check, time of use*).

Race example:

```text
T1: check invoice #101 is PENDING, limit sufficient
T2: change limit/tenant/owner of #101
T1: update #101 based on stale decision
```

In a relational database, one technique is a conditional update constraining the exact record and valid state/permissions at write time:

```sql
UPDATE invoice
SET status = 'APPROVED'
WHERE id = :id
  AND tenant_id = :trustedTenant
  AND status = 'PENDING'
  AND created_by <> :trustedActor
  AND amount <= :trustedApprovalLimit;
```

This is an **SQL illustration**, not a standalone Java file, and must be adapted to your database/schema. Check the affected row count (`1` means update succeeded; `0` means conditions no longer held or the record does not exist). If the policy involves complex joins/ACLs, you may need transactions, locking, version columns, or re-checking permissions against consistent data. Do not treat `@Transactional` alone as proof against races if isolation is unsuitable.

**Separation of responsibilities:** method security blocks before business logic runs, while conditional DB updates protect correctness under concurrent data changes.

### 7.5. Do Not Assume `Authority` Lives Forever

An authority may come from a still-valid token/JWT, while dynamic policies come from the latest DB state. If a permission is revoked after token issuance, requests carrying the old token can still bear the prior authority until token expiry or proper revocation. For critical actions, consider server-side permission checks, short TTLs, revocation, or policy versioning according to system requirements.

Conversely, never cache `canApprove` results indefinitely because `PENDING` transitions to `APPROVED` right after approval; if caching authorization, key by user/tenant/resource/action and invalidate when state or permissions change.

### 7.6. Interaction with Cache, Async, and Transactions

Spring Method Security, transaction advice, and cache advice can all share the same Spring AOP proxy. Advisor ordering affects when the policy runs. A `@Cacheable` wrapping outside authorization can return a cache hit without entering the method body or inner advice depending on configuration; test cache-hit paths as well.

With `@Async`, thread-bound `SecurityContextHolder` may not propagate automatically to the new thread. If async tasks are protected, use propagation utilities (`DelegatingSecurityContext...`) and clearly define whose identity is checked.

With `@Transactional`, checks can run before or inside the transaction boundary depending on advisor order; never assume the dynamic policy and update automatically share one consistent data snapshot merely because both annotations exist.

## 8. Shorter Alternative: Same Policy Using `@PreAuthorize` SpEL

If you do not need a custom annotation/pointcut, you can keep `InvoicePolicy` and use:

```java
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "@invoicePolicy.canApprove(authentication, #p0)"
)
public Invoice approve(Long id) {
    return store.approve(id);
}
```

This is a **replacement snippet** for the method in `ApprovalService`, not a second method to add to the demo program. It needs `@EnableMethodSecurity` and a Spring-managed `InvoicePolicy` bean; no `@ApproveInvoice` advisor is required.

Advantages of SpEL: concise, policy is immediately visible on the method, no separate annotation class needed. Advantages of a custom `AuthorizationManager`: reusable manager compositions, plain Java logic easy to isolate and test, and centralized management of pointcuts or service-wide policies.

Never stack two `@PreAuthorize` annotations on the same method: Spring Security does not support repeating that annotation for AND semantics. Use **one** SpEL expression with `and`, or a corresponding composed manager.

## 9. When to Use `hasPermission`, `@PostAuthorize`, or Other Policies?

- `hasPermission(#invoice, 'approve')` or `hasPermission(#id, 'Invoice', 'approve')` fits systems with a `PermissionEvaluator`/ACL mapping permissions per object. It can be combined with `hasAuthority` or other business policies. `hasPermission` does not natively understand custom states/limits.
- `@PreAuthorize` and before-method `AuthorizationManager` fit when decisions must happen **before side effects**, such as approving, deleting, or transferring funds.
- `@PostAuthorize` fits when you must fetch the result first to evaluate view permissions (`returnObject`). Never rely solely on post-checks to guard operations that already mutated data.
- Web `authorizeHttpRequests(...)` fits endpoint protection. It does not replace authorization on services invoked by message listeners, schedulers, or internal call paths.
- An ACL or ABAC policy service can feed data to a dynamic manager. Labels like RBAC (roles/authorities) and ABAC (attributes/status/tenant) classify policies, yet **do not force an application into a separate framework**.

Choose tools by interception boundary and policy complexity. In multi-tenant systems, design resources and principals with tenants from the start rather than patching tenant checks on later.

## 10. Common Bugs and How to Diagnose Them

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| Having the authority allows approving every invoice | Used `OR` or checked authority alone | Switch to `allOf`/SpEL `and`; check tenant/status/limit |
| User without authority can still approve | Advisor not registered or pointcut mismatch | Check `@EnableMethodSecurity`, `@Bean Advisor`, `@ApproveInvoice`, and proxy |
| User is denied on every invoice | Wrong authority string, missing profile, mismatched data source | Check `GrantedAuthority` and server policy data |
| Non-existent resource still allowed | Policy returns true on `null` or ignores lookup result | Return `false` when principal/resource/profile is missing |
| User from another tenant can approve | Read tenant from client or forgot entity tenant check | Use verified tenant and DB data |
| Creator can self-approve | Forgot maker–checker check | Compare trusted user ID against persisted record's `createdBy` |
| Already-approved invoice can be approved again | Did not check dynamic status | Check `PENDING` first and constrain inside update |
| Annotation works from controller yet not internal service | Self-invocation or bean instantiated via `new` | Invoke via Spring-managed proxy, split beans if needed |
| Revoked user can still approve with old token | Long-lived authorities, no revocation | Review token lifecycle and server-side checks for sensitive actions |
| Data changes between check and update | TOCTOU/race | Use conditional update/locking/versioning/consistent transaction |
| Integration test runs yet rule is skipped | Test mocked service or did not load advisor | Use `@SpringBootTest` and verify both allow and deny |
| `allOf` with custom manager unexpectedly allows | Manager returned `null`/abstain or rule missing from config | Always return explicit decisions; enforce default-deny |

Useful diagnostic steps: check `AopUtils.isAopProxy(service)`, verify the method actually carries `@ApproveInvoice`, inspect `Authentication.getAuthorities()`, log/trace policy outcomes **without logging sensitive contents**, and write tests with one authorized user and one unauthorized user on the **exact same invoice**.

## 11. Self-Check Exercises

1. **A user has `invoice:approve` but the invoice belongs to another tenant. What is the result?**  
   Deny: `STATIC=true`, `DYNAMIC=false`, `AND=false`.

2. **A user is in the same tenant with sufficient limit, yet only has `invoice:read`. What is the result?**  
   Deny: dynamic policy may pass, yet static authority is insufficient.

3. **Why is `AuthorizationManagers.anyOf(staticRule, dynamicRule)` unsuitable?**  
   Because OR lets one passing branch bypass the other, weakening the policy.

4. **`@ApproveInvoice` is defined, yet the advisor bean was forgotten. What happens?**  
   The annotation does not trigger permission checks on its own. A matching interceptor/pointcut must exist.

5. **Why should `InvoicePolicy` not read `tenant` from request JSON and trust it directly?**  
   Because clients can spoof the tenant; the policy needs trusted identity/tenant and entity data.

6. **Where does `AuthorizationManager<MethodInvocation>` get method arguments?**  
   `invocation.getArguments()`; check types, argument count, and `null` before using.

7. **What if `@PreAuthorize` allows, then another user changes the invoice status before update?**  
   There is a TOCTOU gap. The write layer must enforce conditions at update time via an appropriate transaction/conditional update.

8. **Are `@WithMockUser` tests enough if calling `new ApprovalService(...)`?**  
   No. You must call through the Spring bean/proxy to genuinely test the advisor.

9. **Should the policy default to allow when the directory is temporarily unavailable?**  
   No. If permissions cannot be verified, fail closed; handle infrastructure errors separately per system standards.

10. **When should you use `@PreAuthorize` with a bean instead of a custom manager?**  
    When the AND expression is simple, few methods are involved, and framework-level pointcut/manager management is unnecessary.

## 12. References

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, annotation-based authorization, custom beans in SpEL, custom `AuthorizationManager`, and interceptors.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `GrantedAuthority`, `AuthorizationManager`, and composition.
- [Spring Security 6.5 — `AuthorizationManager` Javadoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html): `check` and `authorize` signatures for the 6.5 line.
- [Spring Security — `AuthorizationManagers` Javadoc](https://www.springframework.org/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManagers.html): `allOf`, `anyOf`, and abstain.
- [Spring Security — Method Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/method.html): testing with `@WithMockUser` and Spring test context.
- [Spring Framework — Spring AOP Proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxy boundaries and self-invocation.

**Key takeaway:** static permissions define *what kind of operation the caller may perform*; dynamic permissions define *whether that caller may perform the operation on this exact record, in its current state, under current policy*. For invoice approval, grant access only when **both pass**, always use trusted server data, and protect the update boundary against concurrent changes.