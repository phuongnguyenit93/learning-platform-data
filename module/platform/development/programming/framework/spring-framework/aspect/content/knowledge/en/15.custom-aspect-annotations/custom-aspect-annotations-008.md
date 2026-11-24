# Do Not Turn Annotations into Hard-to-Track Business Rule Containers in Spring AOP

When writing custom annotations for **Spring AOP**, a common mistake is packing business decisions into an annotation and letting an aspect execute them silently. The syntax looks concise, yet anyone reading the method cannot see which conditions decide the outcome; testing, policy changes, and debugging also become difficult. An annotation should express **the intent to attach a cross-cutting concern**, while business decision rules should appear explicitly in the service or a dedicated policy class.

The scope of this article is how to design **custom annotations combined with Spring AOP proxies and advice**. General AOP concepts do not need to be relearned here.

## 1. Responsibility Boundaries in a Spring Application

| Component | Intended Responsibility | What to Avoid |
| --- | --- | --- |
| Custom annotation, e.g., `@AuditAction("create-order")` | Mark points where auditing applies; carry small, stable, easy-to-read metadata | Encoding pricing tables, customer tiers, multiple order-approval conditions |
| Spring `@Aspect` and advice | Handle logging/audit/tracing/metrics uniformly on marked methods | Deciding order validity, calculating fees, altering return results for business policies |
| `OrderService` | Orchestrate the use case, call the policy **explicitly** | Relying on an aspect to run business checks on its behalf |
| `OrderPolicy` (or domain service) | Place rules in one clearly named location, testable independently of Spring proxies | Cramming rules into annotation string names or opaque around-method handling |

Spring AOP normally applies advice when a method call **goes through a Spring proxy**. Therefore, if a business invariant is protected only by an aspect, calls bypassing the proxy can skip the check. A service calling the policy directly keeps the rule visible right inside the business flow.

## 2. Anti-Example: An Annotation Carrying Business Policy

Suppose the application must enforce that orders over 200 currency units can only be placed by premium customers. The following design **illustrates what to avoid**, not a standalone runnable program:

```java
// Misleading API: policy is pushed into metadata on the method.
@AcceptOrder(maxAmountForBasicMember = 200, requirePremiumAboveLimit = true)
public String createOrder(int amount, boolean premium) {
    return "APPROVED";
}
```

If an `@Around` advice reads these parameters and silently blocks the order, the body of `createOrder` appears to always approve. Practical problems:

- **Hidden control flow:** from the method itself you cannot see the customer-tier check, where exceptions arise, or precedence rules between conditions.
- **Hard-to-change policy:** adding promotions, regional limits, or time-based limits forces expanding the annotation and aspect, creating a business engine outside the service.
- **Layer-mismatched testing:** tests instantiating the service directly with `new` will not run Spring advice; results can differ when the bean goes through a proxy.
- **Difficult reuse:** another API needing the same rule without using the same annotation or proxy must duplicate the logic.
- **Hard to trace:** maintainers must follow pointcuts and advice to understand why an operation was rejected.

Annotation parameters do not automatically become bad: audit event names, metric tags, or operation names are legitimate metadata. The decisive factor is **whether they control business outcomes**.

## 3. Recommended Design: Explicit Policy, Annotation Serving Audit

The example below uses **Java 17+** and a **Spring Boot 3.x** application with `spring-boot-starter-aop`. Structure:

```text
src/main/java/com/example/aopaudit/
├── DemoApplication.java
├── AuditAction.java
├── AuditAspect.java
├── OrderPolicy.java
└── OrderService.java
```

In a Maven-based Spring Boot project, add this dependency if not already present (version managed by the Spring Boot parent/BOM):

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

With Gradle, the equivalent dependency is `implementation 'org.springframework.boot:spring-boot-starter-aop'`. The project also needs a Spring Boot starter to run the application. Under typical Boot configurations, the AOP starter supplies `@Aspect` annotations and the support required for Spring proxies.

**File `AuditAction.java` — the annotation is only an audit marker:**

```java
package com.example.aopaudit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AuditAction {
    String value();
}
```

`@Target(METHOD)` restricts the annotation to methods. `@Retention(RUNTIME)` lets Spring/AspectJ recognize it during execution. `value` is the action name for observability, **not a threshold or order-approval condition**.

**File `OrderPolicy.java` — where business decisions are enforced:**

```java
package com.example.aopaudit;

import org.springframework.stereotype.Component;

@Component
public class OrderPolicy {
    public void check(int amount, boolean premium) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        if (amount > 200 && !premium) {
            throw new IllegalArgumentException(
                "Premium required for amount over 200"
            );
        }
    }
}
```

This is an intentionally simple policy example: amount must be positive; if amount exceeds 200, the customer must be premium. In a real system, rules can use a domain model and dedicated policy classes. Even when policies are more complex, how they are invoked remains transparent.

**File `OrderService.java` — invoking the policy directly inside the method:**

```java
package com.example.aopaudit;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final OrderPolicy policy;

    public OrderService(OrderPolicy policy) {
        this.policy = policy;
    }

    @AuditAction("create-order")
    public String createOrder(int amount, boolean premium) {
        policy.check(amount, premium);
        return "APPROVED";
    }
}
```

Even when reading `OrderService` in isolation, you still see `policy.check(...)` called before approving. The annotation only requests additional auditing; removing the annotation does not alter the order-approval rule.

**File `AuditAspect.java` — advice only observes the outcome:**

```java
package com.example.aopaudit;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Around("@annotation(auditAction)")
    public Object audit(ProceedingJoinPoint joinPoint, AuditAction auditAction)
            throws Throwable {
        String action = auditAction.value();
        System.out.println("AUDIT start " + action);
        try {
            Object result = joinPoint.proceed();
            System.out.println("AUDIT success " + action);
            return result;
        } catch (Throwable failure) {
            System.out.println(
                "AUDIT failure " + action + ": " +
                    failure.getClass().getSimpleName()
            );
            throw failure;
        }
    }
}
```

`@Around("@annotation(auditAction)")` selects methods carrying `@AuditAction` and binds the annotation to the advice parameter. `joinPoint.proceed()` is called exactly once; the original value is returned and the original error is rethrown. The aspect **does not alter** the premium condition, does not return fake statuses, and does not swallow exceptions. `System.out` is only for easily observable output; real applications should use an appropriate logger/audit sink, avoiding logging personal data or secrets.

**File `DemoApplication.java` — running two scenarios:**

```java
package com.example.aopaudit;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(OrderService orderService) {
        return args -> {
            System.out.println(
                "RESULT " + orderService.createOrder(150, false)
            );

            try {
                orderService.createOrder(500, false);
            } catch (IllegalArgumentException failure) {
                System.out.println("REJECTED " + failure.getMessage());
            }
        };
    }
}
```

Run in a Boot project with dependencies configured:

```bash
./mvnw spring-boot:run
# Or for a Gradle project:
./gradlew bootRun
```

On Windows use `mvnw.cmd spring-boot:run` or `gradlew.bat bootRun`. Aside from Spring startup logs, the output produced by the example in order is:

```text
AUDIT start create-order
AUDIT success create-order
RESULT APPROVED
AUDIT start create-order
AUDIT failure create-order: IllegalArgumentException
REJECTED Premium required for amount over 200
```

In the first call, the policy allows 150 for a regular customer. In the second, `OrderPolicy.check` throws; the aspect records the failure and rethrows for the caller to handle. No business decision was made inside the aspect.

> Assumption when running the example: uses dependencies managed by Spring Boot 3.x and a build preserving parameter name info to bind `auditAction` (standard Spring Boot build configuration). If using a custom build and encountering an error unable to determine advice parameter names, enable the `-parameters` compiler flag or declare `argNames` per Spring AOP documentation.

## 4. Refactoring When Business-Heavy Annotations Already Exist

If existing code uses an annotation like `@AcceptOrder(...)`, move each responsibility back to its proper place:

1. **List actual behaviors:** identify which conditions accept/reject an order, which exceptions are thrown, what data they depend on, and what logging/auditing is doing.
2. **Extract the policy into a business-named API:** e.g., `OrderPolicy.check(amount, premium)` or `EligibilityPolicy.evaluate(customer, order)`, with transparent inputs/outputs.
3. **Call the policy directly from the use case/service:** all order-creation entry points must go through this business logic; write tests for edge cases.
4. **Keep the annotation for technical concerns:** if auditing is still needed, convert it to metadata like `@AuditAction("create-order")`; the aspect only logs success/failure.
5. **Remove business logic from advice after verifying behavior parity:** do not leave checks duplicated in two places with two diverging policies.

Another example: `@ApplyDiscount(level = "VIP", percentage = 15)` having an aspect modify prices is a sign of hidden pricing rules. The service should call `pricingPolicy.calculatePrice(...)`; a `@TrackOperation("price-quote")` can mark when metrics are needed without deciding prices.

## 5. Spring AOP Specifics to Remember

- **Self-invocation:** calling `this.createOrder(...)` from another method in the same bean normally does not go through the Spring proxy, so `@AuditAction` may not trigger advice. Business invariants must still rely on calling `policy.check(...)` inside the service. Do not use AOP proxies as the sole fence for policies.
- **Method visibility and proxies:** Spring AOP advice only works on methods interceptable by a proxy; e.g., prefer public methods on Spring-managed beans. Calls via `new OrderService(...)` receive no audit advice, yet policy logic still runs.
- **Do not use annotations to fake security:** access checks can use Spring Security mechanisms like properly configured `@PreAuthorize`, while domain rules such as spending limits or order eligibility belong explicitly in the business model; do not write vague custom aspects to replace security mechanisms.
- **Advice ordering and transactions:** if auditing must be persisted reliably after a transaction commits, an `@Around` logging "success" upon method return does not guarantee data has committed. Consider application events after commit or `@TransactionalEventListener(phase = AFTER_COMMIT)` depending on actual requirements.
- **Keep metadata small and stable:** event names, audit types, and observability tags fit well as annotation attributes; rules that change frequently by customer, market, or data belong in services/policies.
- **Error transparency:** advice observes failures, preserving exceptions and results; only transform results when that is an explicitly designed, named, and tested cross-cutting behavior.

## 6. Testing to Ensure Annotations Do Not Hold Business Authority

The decision-making part should be tested **without a Spring context**, so results do not depend on proxy call paths. JUnit 5 example for `OrderService`, available if `spring-boot-starter-test` is added in test scope:

```java
package com.example.aopaudit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class OrderServiceTest {
    private final OrderService service =
        new OrderService(new OrderPolicy());

    @Test
    void regularCustomerCanPlaceSmallOrder() {
        assertEquals("APPROVED", service.createOrder(150, false));
    }

    @Test
    void regularCustomerCannotPlaceLargeOrder() {
        assertThrows(
            IllegalArgumentException.class,
            () -> service.createOrder(500, false)
        );
    }

    @Test
    void amountMustBePositive() {
        assertThrows(
            IllegalArgumentException.class,
            () -> service.createOrder(0, true)
        );
    }
}
```

This test intentionally instantiates `OrderService` directly: there is no proxy or aspect, yet the policy still works. Test Spring integration separately, e.g., `@SpringBootTest` with real beans, to confirm advice catches the annotation through the proxy without altering results/exceptions. Never let an audit log be the only proof that an order was validated properly.

## 7. Design Review Checklist

- When reading the service method, are calls to business decision classes, conditions, and key errors visible?
- Would removing or disabling the audit annotation change business outcomes? **It should not.**
- Would calling the service directly without a Spring proxy bypass domain policies? **It must not.**
- Does the aspect execute only the stated concern, and return results/rethrow errors accurately from `proceed()`?
- Are annotation attributes solely technical metadata, rather than formulas/conditions used to calculate prices, approve orders, or mutate state?
- Are there unit tests for the standalone policy and separate integration tests for Spring AOP interception?

**Practical rule:** For custom annotations in Spring AOP, let the annotation answer *"which concern should apply to this method?"*, the aspect answer *"how is that concern handled?"*, and the service/policy answer *"does the business allow it and what must happen?"*. That way code expresses the true processing flow, stays testable without running Spring, and avoids hidden rules.