# Self-Invocation, `final` Methods, and Proxy Limitations in Spring Method Validation

## 1. The Problem: `@Validated` Is Present, Yet Invalid Data Slips Through

In Spring, a service can be annotated with `@Validated` on the class and have `@NotBlank`, `@Min`, and `@NotNull` on method parameters. Calls from another bean throw an error immediately when parameters violate constraints, while calling `this.check(...)` from inside the service itself runs normally. Some `final` or `private` methods also go unvalidated despite having constraints.

The decisive factor is **whether the call passes through the method validation trigger point**. With AOP-style Spring method validation commonly used for services, that trigger point is the **Spring proxy**; only calls that the proxy can intercept execute validation advice. Jakarta Validation annotations describe rules, but **they do not automatically cause every Java call to be validated**.

This lesson focuses on:

- **Self-invocation**: calling a method on the same object via `this`, bypassing proxy advice.
- **`final`, `private`, `static`, and `final` classes**: why subclass-based proxies (CGLIB) have limitations.
- **JDK dynamic proxies vs. CGLIB**: cases where a `final` implementation method can still be validated when invoked through a JDK interface proxy.
- How to verify behavior with Java 17, Spring Framework 6.x, and Hibernate Validator.
- How to design services and controllers so method validation occurs at the right boundaries.

Examples use **Spring Framework 6 / Jakarta Validation** with `jakarta.validation.*` imports. Spring Framework 5 / Boot 2 use the older `javax.validation.*` namespace; do not mix the two library sets and imports.

## 2. Three Layers That Make Up Method Validation

| Layer | Typical components | Role |
| --- | --- | --- |
| Rules | `@NotNull`, `@NotBlank`, `@Min`, `@Valid` | Declare conditions on parameters, return values, or nested objects |
| Jakarta Validation Engine | `Validator`, `ExecutableValidator`, `ConstraintViolation` | Perform validation checks against constraints |
| Spring invocation boundary | `MethodValidationPostProcessor`, `MethodValidationInterceptor`, AOP proxy | Invoke the engine when methods are called through the proxy |

For a Spring-managed service configured with AOP method validation, the typical flow is:

```text
Another bean calls service.save(x)
          |
          v
     Spring proxy
          |
          +--> MethodValidationInterceptor
          |      |
          |      +--> ExecutableValidator.validateParameters(...)
          |      |           |
          |      |           +--> violation? Throw exception
          |      |
          |      +--> Invoke target.save(x) if parameters are valid
          |      |
          |      +--> ExecutableValidator.validateReturnValue(...)
          |                  |
          |                  +--> violation? Throw exception
          v
     Return result to caller
```

When the call originates inside the class itself, such as `this.save(x)`, the method is invoked directly on the target object. It **does not go back through the proxy** to run the interceptor for `save`.

Spring's `@Validated` (`org.springframework.validation.annotation.Validated`) at the type level is the marker enabling `MethodValidationPostProcessor` to select the bean for method validation proxying. `@NotBlank` or `@Min` are the concrete Jakarta Validation constraints. If the Spring container does not register the post-processor, or callers do not use the proxy, merely adding annotations does not guarantee validation on method calls.

In a plain Spring application, you can register:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.MethodValidationPostProcessor;

@Configuration
public class ValidationConfig {
    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        return new MethodValidationPostProcessor();
    }
}
```

A service participating in method validation:

```java
import jakarta.validation.constraints.Min;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class OrderService {
    public void submit(@Min(1) int quantity) {
        // Process the order.
    }
}
```

These two snippets are fragments of a Spring application, not a standalone program. In Spring Boot 3, the validation starter and auto-configuration normally create the corresponding post-processor; you should still verify the provider and actual call paths.

## 3. Self-Invocation: Why Does `this.method()` Skip Validation?

Consider the service:

```java
@Service
@Validated
public class AccountService {

    public String create(@NotBlank String username) {
        return "created:" + username;
    }

    public String createInternally(String username) {
        return this.create(username);
    }
}
```

With an actual method-validation proxy created, the two paths differ:

```text
Bean A
 |
 +--> accountServiceProxy.create("")
 |          |
 |          +--> @NotBlank: error, target.create does not run
 |
 +--> accountServiceProxy.createInternally("")
            |
            +--> target.createInternally("")
                       |
                       +--> this.create("") -> runs create body
                                                bypasses validation advice
```

Writing `create(username)` without `this.` is still self-invocation. Both calls target **the same `@NotBlank` annotation** yet cross different interception boundaries.

Common points of confusion:

1. Another bean calling a **public, advisable method** through the proxy triggers method validation.
2. An outer method calling `this.inner(...)` does not trigger proxy advice specifically for `inner`; if the **outer** method has its own constraints, those outer constraints can still be checked.
3. Self-invocation can bypass other Spring AOP advice such as transactions, caching, or asynchronous execution, depending on configuration.
4. If the method body calls `Validator.validate(...)` or `ExecutableValidator` explicitly, that is manual validation and still runs. Self-invocation only bypasses automatic interception at the skipped boundary.
5. Do not conclude `@NotBlank` is globally broken just because one call path fails to throw. Inspect whether the bean is actually proxied and who holds the reference.

## 4. JDK Proxies vs. CGLIB: Different Limitations

| Characteristic | JDK dynamic proxy | CGLIB (class proxy) |
| --- | --- | --- |
| Nature | Object implementing the target's interfaces | Runtime subclass of the target class |
| Requires an interface? | Yes | No |
| Intercepted calls | Methods through the interface proxy | Instance methods the subclass can override |
| `final` implementation method | **Can be intercepted** via interface before calling target | **Cannot be intercepted** via override because Java forbids overriding final |
| `final` implementation class | Can still use JDK proxy if a valid interface exists | Cannot be subclassed; proxying can fail |
| `private` method | Cannot be called directly on the proxy interface | Cannot be overridden/advised |
| Self-invocation via `this` | Bypasses advice | Bypasses advice |
| Type to inject | Proxied interface | Concrete class or compatible type |

Spring AOP may choose a JDK proxy when the target implements an interface, or use CGLIB when it does not; `proxyTargetClass=true` can force class-based proxies. Do not rely on class names or starter defaults: inspect the **actual proxy**.

### 4.1. Why Can't CGLIB Intercept `final`?

CGLIB uses subclassing and method overriding to run interceptors. Java forbids overriding `final` methods. If a class is `final`, it cannot be subclassed at all. With CGLIB, `private` methods cannot be overridden, while `static` methods belong to the class rather than being instance methods wrapped by an AOP proxy.

Limitation example:

```java
@Validated
public class BillingService {
    public final void bill(@NotNull String accountId) {
        // Final method cannot be overridden by CGLIB.
    }
}
```

This is an illustrative fragment. If `BillingService` uses a CGLIB proxy, Spring cannot apply method-validation advice to calls to `bill(null)` because the method is `final`. The Bean Validation annotation remains in metadata, yet automatic method interception does not occur. Never skip critical input checks merely because you see an annotation.

### 4.2. JDK Proxies Can Validate `final` Implementations

```java
public interface BillingApi {
    void bill(@NotNull String accountId);
}

@Validated
public final class FinalBillingService implements BillingApi {
    @Override
    public final void bill(String accountId) {
        // Execution logic.
    }
}
```

If Spring creates a **JDK proxy for `BillingApi`**, callers invoke `billingApi.bill(null)` on the proxy. The proxy intercepts the call **before** delegating to the final implementation method; therefore validation can still run.

A crucial requirement is that callers hold the **interface reference**. A JDK proxy is not a subclass of `FinalBillingService`, so you cannot cast it to the implementation class to call class-specific methods.

The snippet above puts `@NotNull` on the **interface** and adds no parameter constraints on the implementation's override. Under Jakarta Validation's method constraint inheritance rules, an implementation generally may not strengthen parameter preconditions beyond the interface contract. Violating this rule can cause `ConstraintDeclarationException`.

## 5. Standalone Java 17 Example with Maven

The example builds two Spring ApplicationContexts: a CGLIB context demonstrating external/self/final/private calls and `new` instantiation, and a JDK context demonstrating how an interface proxy can intercept a final implementation method. No web server or database is needed.

Structure:

```text
method-validation-proxy-demo/
├── pom.xml
└── src/main/java/demo/
    └── MethodValidationProxyDemo.java
```

### 5.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>method-validation-proxy-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish.expressly</groupId>
            <artifactId>expressly</artifactId>
            <version>5.0.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.MethodValidationProxyDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` and `spring-aop` share the same version. `hibernate-validator` provides the Jakarta Validation implementation; `expressly` is the Jakarta Expression Language implementation used for message interpolation.

### 5.2. `src/main/java/demo/MethodValidationProxyDemo.java`

```java
package demo;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.constraints.NotBlank;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.annotation.Validated;
import org.springframework.validation.beanvalidation.MethodValidationPostProcessor;

import java.util.function.Supplier;

public final class MethodValidationProxyDemo {

    @Validated
    public static class BookingService {
        public String check(@NotBlank String code) {
            return "accepted:" + code;
        }

        public String viaThis(String code) {
            return this.check(code);
        }

        public final String finalCheck(@NotBlank String code) {
            return "final:" + code;
        }

        public String viaPrivate(String code) {
            return privateCheck(code);
        }

        private String privateCheck(@NotBlank String code) {
            return "private:" + code;
        }
    }

    public interface TicketApi {
        String book(@NotBlank String code);
    }

    @Validated
    public static final class FinalTicketService implements TicketApi {
        @Override
        public final String book(String code) {
            return "ticket:" + code;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class CglibConfig {
        @Bean
        static MethodValidationPostProcessor methodValidationPostProcessor() {
            MethodValidationPostProcessor p =
                    new MethodValidationPostProcessor();
            p.setProxyTargetClass(true);
            return p;
        }

        @Bean
        BookingService bookingService() {
            return new BookingService();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class JdkConfig {
        @Bean
        static MethodValidationPostProcessor methodValidationPostProcessor() {
            MethodValidationPostProcessor p =
                    new MethodValidationPostProcessor();
            p.setProxyTargetClass(false);
            return p;
        }

        @Bean
        TicketApi ticketApi() {
            return new FinalTicketService();
        }
    }

    private static void attempt(String label, Supplier<String> invocation) {
        try {
            System.out.println(label + ": " + invocation.get());
        } catch (ConstraintViolationException e) {
            System.out.println(label
                    + ": VIOLATION(" + e.getConstraintViolations().size() + ")");
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext ctx =
                     new AnnotationConfigApplicationContext(CglibConfig.class)) {
            BookingService service = ctx.getBean(BookingService.class);
            System.out.println("CGLIB proxy: "
                    + AopUtils.isCglibProxy(service));

            attempt("external", () -> service.check(""));
            attempt("self", () -> service.viaThis(""));
            attempt("final", () -> service.finalCheck(""));
            attempt("private", () -> service.viaPrivate(""));
            attempt("new", () -> new BookingService().check(""));
            attempt("valid", () -> service.check("ABC"));
        }

        try (AnnotationConfigApplicationContext ctx =
                     new AnnotationConfigApplicationContext(JdkConfig.class)) {
            TicketApi tickets = ctx.getBean(TicketApi.class);
            System.out.println("JDK proxy: "
                    + AopUtils.isJdkDynamicProxy(tickets));
            attempt("JDK final", () -> tickets.book(""));
        }
    }
}
```

**Design explanation:** `BookingService` implements no interface, and `setProxyTargetClass(true)` creates a class-based proxy to test `this` and `final` methods. `FinalTicketService` is a `final` class implementing an interface; JDK proxy configuration allows intercepting `TicketApi.book` without subclassing the implementation. Methods return plain strings with no side effects so call paths can be observed safely.

Run in the directory containing `pom.xml` with JDK 17 and Maven:

```bash
mvn -q clean compile exec:java
```

**Expected stdout lines printed by the program** (excluding separate Spring/Hibernate Validator logs):

```text
CGLIB proxy: true
external: VIOLATION(1)
self: accepted:
final: final:
private: private:
new: accepted:
valid: accepted:ABC
JDK proxy: true
JDK final: VIOLATION(1)
```

| Case | Call path | `@NotBlank` enforced automatically? | Explanation |
| --- | --- | --- | --- |
| `external` | Caller → CGLIB proxy → `check("")` | Yes, 1 violation | Public method is overridable and called through proxy |
| `self` | Caller → proxy → `viaThis("")` → `this.check("")` | No for internal `check` | Internal call does not re-enter the proxy |
| `final` | Caller → CGLIB proxy → `finalCheck("")` | No | CGLIB cannot override final methods |
| `private` | Caller → proxy → `viaPrivate` → private method | No for private method | Private methods cannot be overridden |
| `new` | Caller → `new BookingService()` | No | Not a Spring bean proxy |
| `valid` | Caller → CGLIB proxy → `check("ABC")` | Yes, valid | Input satisfies `@NotBlank` |
| `JDK final` | Caller → JDK interface proxy → target final method | Yes, 1 violation | Proxy intercepts at the interface |

The output does not rely on error text or `Set<ConstraintViolation<?>>` ordering, only violation counts. Do not infer from `accepted:` or `final:` in the bypassed cases that production should allow blank codes; the example intentionally keeps method bodies simple to highlight the **absence of advice**.

### 5.3. Why Two Separate Contexts?

If both services were placed in the same context with `proxyTargetClass=true` globally, Spring could attempt to create a CGLIB proxy for the final class in the JDK example and fail. Separating contexts keeps each experiment dependent solely on the **proxy type being demonstrated**.

## 6. `final` Methods Are Not the Only Case

### 6.1. `private` and `static`

- `private` methods cannot be overridden by subclasses and are not public methods of a JDK interface proxy. Parameter constraints on private methods are not automatically validated by Spring AOP's method-validation interceptor.
- `static` methods are invoked on the class, not on an instance proxy in the standard Spring AOP model.
- Superclass methods not visible to subclasses (such as package-private methods from another package) behave like private methods to CGLIB and cannot be advised.
- With CGLIB, the most predictable choice for advisable methods is **public, non-final instance methods**.

### 6.2. `final` Classes, Java Records, and Kotlin

- Java `record` types are final. That prevents **CGLIB proxying a record as a service**, yet it **does not prevent** using `@Valid` or `Validator.validate(record)` to validate **record data**. Those are two distinct mechanisms.
- A `final` class implementing an interface can still be wrapped by a **JDK proxy** if the method is on the proxied interface and constraint metadata is valid.
- Kotlin classes and methods are final by default. When using class-based proxies, check `kotlin-spring`/all-open configuration (where appropriate) or consider interface proxies.
- Do not try to work around CGLIB limitations simply by adding `@Validated` onto a final method. You must change the boundary or proxy type.

### 6.3. Interface Method Constraints and Inheritance Rules

Jakarta Validation restricts **adding parameter preconditions** in overridden methods. For example:

```java
public interface LoginApi {
    void login(String username);
}

public class LoginService implements LoginApi {
    @Override
    public void login(@NotBlank String username) {
        // May violate Bean Validation method inheritance rules.
    }
}
```

This fragment illustrates **an invalid design to avoid**. Because the interface declares the parameter without constraints while the implementation adds `@NotBlank`, a provider can throw `ConstraintDeclarationException`. Place constraints on the **interface contract** when all callers must satisfy the condition, and do not redeclare them on the overriding method. With multiple interfaces or complex inheritance, double-check Jakarta Validation rules rather than guessing how providers merge them.

## 7. Fixing Self-Invocation by Extracting a Bean

Instead of having a service invoke its own AOP-advised method:

```java
@Service
@Validated
public class RegistrationService {
    public void register(String email) {
        this.verifyEmail(email); // self-invocation
    }

    public void verifyEmail(@NotBlank String email) {
        // ...
    }
}
```

Split into two beans (illustrative Spring fragment, omitting imports and business logic):

```java
@Service
@Validated
public class EmailPolicy {
    public void verifyEmail(@NotBlank String email) {
        // ...
    }
}

@Service
public class RegistrationService {
    private final EmailPolicy policy;

    public RegistrationService(EmailPolicy policy) {
        this.policy = policy;
    }

    public void register(String email) {
        policy.verifyEmail(email); // via Spring-injected EmailPolicy bean
        // Continue processing.
    }
}
```

When `EmailPolicy` is properly proxied by Spring, calling through the injected field passes through the proxy and triggers validation. This keeps business boundaries clear, makes testing easier, and avoids coupling a service to proxy infrastructure.

Other options:

- **Self-injecting the proxy reference** (typically via `@Lazy` to avoid circular dependency issues) and calling via that proxy reference instead of `this`. Drawbacks include circular dependency risk and tight coupling to AOP.
- **`AopContext.currentProxy()`** only when `exposeProxy=true` is enabled and a valid proxy context exists. This tightly couples code to Spring and **does not help CGLIB intercept final methods**.
- **Manual `ExecutableValidator`**: `validator.forExecutables().validateParameters(target, method, args)` and `validateReturnValue(...)` validate methods/objects that do not pass through a proxy. The application must manage reflection, groups, and errors itself.
- **Guards in domain logic**: if a condition is an invariant that must hold on *every* call path, validate explicitly in constructors, methods, or domain services as needed. Boundary method validation is a convenience, not a replacement for all business invariants.

You do not need to extract a separate bean for every private method: extract only when you actually need a **proxied call** or a cleaner separation of responsibilities.

## 8. Spring MVC 6.1+ Has Its Own Method Validation Mechanism

Spring Framework 6.1 introduced **built-in method validation** inside Spring MVC controller processing, without necessarily relying on service-style AOP proxies.

Illustrative fragment for an application with Spring Web MVC and Jakarta Validation:

```java
import jakarta.validation.constraints.Min;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {
    @GetMapping("/products")
    String list(@RequestParam @Min(1) int page) {
        return "page=" + page;
    }
}
```

With the `@Min(1)` constraint directly on the parameter and a request flowing through the MVC pipeline, `page=0` can be rejected by **MVC built-in method validation**. The typical exception is **`HandlerMethodValidationException`**.

If you only use `@Valid @RequestBody` for a command object without requiring method validation, MVC typically uses argument-level validation and can throw **`MethodArgumentNotValidException`**. When the method has direct constraints, MVC method validation can also cover nested `@Valid` validation.

**Note:** Spring 6.1+ documentation recommends **removing class-level `@Validated` on controllers** if you want built-in method validation; with class-level `@Validated`, the controller may use AOP proxy validation instead of built-in method validation.

Boundary comparison:

| Scenario | Mechanism |
| --- | --- |
| HTTP request to Spring MVC 6.1+ controller, direct parameter constraints | MVC built-in validation |
| `@Validated` Spring service bean called via AOP proxy | `MethodValidationInterceptor` |
| DTO object passed explicitly to `Validator.validate(...)` | Direct Jakarta Validation |
| Calling `new Controller().method(...)` or `new Service().method(...)` | No automatic MVC pipeline or Spring AOP proxy |
| Target service calling `this.otherMethod(...)` | No separate interceptor run for the inner method |

Do not compare two identical annotations and assume identical behavior: controller validation and service method validation have different **trigger points, exceptions, and error handling**.

## 9. Exceptions, Groups, and Return Values

### Exceptions

With standard `MethodValidationPostProcessor`, Jakarta Validation violations produce **`jakarta.validation.ConstraintViolationException`**. Some Spring configurations enable `setAdaptConstraintViolations(true)` to receive **Spring's `MethodValidationException`**. In built-in MVC validation, the characteristic exception is `HandlerMethodValidationException`. Write handlers and tests according to the validation path actually in use.

### Return Value Constraints

Method validation does not check inputs only. Illustrative fragment:

```java
public @NotNull String issueToken(@NotBlank String username) {
    return lookupToken(username);
}
```

`lookupToken` is assumed to be an existing business helper. When the method is called through an appropriate proxy, Jakarta Validation can check `username` **before the method runs** and `@NotNull` on the result **after the method finishes**. If the method returns `null`, a violation is reported at the return boundary.

### Cascading and Null

`@Valid` requests validation of child object constraints if the object is non-null; it **does not by itself require the parameter to be non-null**. For example:

```java
public void register(@NotNull @Valid RegistrationRequest request) {
    // @NotNull checks null; @Valid validates the object if present.
}
```

This is just a fragment. If the child object needs to be validated via AOP method validation, the method must still be called through the proper proxy or another Jakarta Validation mechanism.

### Validation Groups

Spring `@Validated(SomeGroup.class)` can influence which constraint groups are evaluated when method validation runs. A method can appear "unvalidated" because a constraint belongs outside the active group; do not immediately blame self-invocation. When debugging, check the default group, type/method groups, and actual provider configuration.

## 10. Diagnostic Checklist for Proxy Method Validation Issues

When a method has constraints yet still accepts invalid input:

1. **Is it a Spring bean or just `new`?** Obtain the bean via dependency injection or the context.
2. **Is the bean actually a proxy?** Check `AopUtils.isAopProxy(service)`, `AopUtils.isCglibProxy(service)`, and `AopUtils.isJdkDynamicProxy(service)`.
3. **Are `MethodValidationPostProcessor` and a Jakarta Validation provider present?** In plain Spring config, register them explicitly; in Boot, check the validation starter and auto-configuration.
4. **Does the type have Spring `@Validated`?** For service AOP, this is typically the marker selecting the bean.
5. **Do callers go through the proxy?** Look for `this.method()`, implicit internal calls, or stale references to the raw target.
6. **Is the method/class `final`, `private`, or `static`?** Check against JDK/CGLIB proxy behavior.
7. **If using a JDK proxy, are callers using the interface?** Is the method on the proxied interface and is constraint inheritance valid?
8. **Are constraints of the right type and validation group?** Verify imports, groups, supported types, and null semantics.
9. **Are you testing a service or an MVC controller?** Spring MVC 6.1+ has distinct built-in handling.
10. **Is a handler catching and translating errors?** `ConstraintViolationException` might already be mapped to a response or swallowed.

Tests should cover: invalid external calls, valid external calls, self-invocation, CGLIB final, JDK interface, `new` instances, and return-value constraints. Method validation tests **must obtain the bean from the Spring context** when verifying advice. Unit tests instantiating `new Service()` only test Java logic and prove nothing about AOP.

### Common Mistakes

- Adding `@Validated` repeatedly without checking proxy boundaries.
- Assuming `final` classes and `final` methods behave identically under JDK proxies and CGLIB.
- Enabling `proxyTargetClass=true` while expecting interface proxies to work around final classes.
- Adding parameter constraints on overriding methods without checking Bean Validation inheritance rules.
- Believing `@Valid` on a DTO causes every self-invocation to validate automatically.
- Using `AopContext.currentProxy()` as a default workaround, creating hard-to-maintain coupling.
- Relying on advice order or assuming validation always precedes transactions/caching without checking order configuration.
- Putting all mandatory business invariants in advice while leaving internal call paths unguarded.

## 11. Practical Conclusion

The key question when method validation "does not run" is: **"Does the call pass through a proxy capable of intercepting this method?"**

- Through a proxy, compatible public/non-final methods: advice can execute.
- Via `this`, private methods, or objects created with `new`: no automatic Spring AOP method validation at that boundary.
- With CGLIB: `final` classes cannot be subclassed, `final` methods cannot be advised.
- With JDK proxies: `final` implementation methods can still be validated when invoked through an interface proxy with valid constraint metadata.
- With Spring MVC 6.1+: controllers can use built-in method validation; evaluate them against the HTTP pipeline rather than forcing the service proxy model everywhere.

To enforce constraints reliably, structure beans around clear interaction points, use compatible methods/proxies, and test both enforced and bypassed paths.

## References

- [Spring Framework 6.2 — Java Bean Validation / Spring-driven Method Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — Proxying mechanisms, final methods, and self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — MVC Method Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Jakarta Bean Validation 3.0 — Method constraints, inheritance, executable validation](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Hibernate Validator 8 — Method validation reference](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/)
