# Naming Pointcuts by Intent Instead of Expression String Details in Spring AOP

## 1. Goal

In Spring AOP, writing a long expression directly inside `@Before` or `@Around` may work today, yet is hard to read and hard to maintain. When that expression is copied across multiple advice methods, someone editing it often does not know **which business intent** it represents: monitoring all business operations, auditing payment approvals, or only intercepting a method on a specific bean?

Spring Framework lets you define a **named pointcut** with `@Pointcut` on a Java method returning `void`, then reference it by name in advice or combine smaller pointcuts into a more meaningful one. The most important goal is for readers to understand **why those methods belong in the advice scope**, rather than having to decode the characters of a long expression during every code review.

This lesson belongs to the **Pointcut Organization** section of Spring Framework and focuses strictly on proxy-based Spring Aspects / Spring AOP, covering:

1. Distinguishing **intent-descriptive names** from **implementation expressions**.
2. Organizing small pointcuts and composite pointcuts with `@Pointcut`.
3. Sharing pointcuts across Spring aspects while respecting Java visibility.
4. Avoiding misleading names that cause code reviews to miss scope changes.
5. Writing a runnable Java 17+ application proving a business name matches the exact expected bean/method.
6. Building positive and negative tests so expressions can be changed while preserving the pointcut's contract.

General Aspect concepts are not repeated; the focus is on **Spring reading named pointcuts, creating advisors, and applying them to Spring-managed beans**.

## 2. What question does a pointcut name answer?

Compare two ways of writing an advice:

**Approach 1 — embedding expression details inside the advice:**

~~~java
@Before(
    "within(example.payment..*)"
    + " && execution(public * approve(..))"
)
public void audit() {
    System.out.println("audit");
}
~~~

**Approach 2 — referencing a name that expresses purpose:**

~~~java
@Before("example.aop.PaymentPointcuts.paymentApprovalOperation()")
public void audit() {
    System.out.println("audit");
}
~~~

In approach 2, a reader immediately sees that this is a **payment approval operation**. The expression still exists where the named pointcut is defined, without being repeated across every advice. Maintainers can change how the operation is identified — by package, type, annotation, or bean name — without rewriting multiple advice methods.

**A pointcut name is a semantic contract in code**:

- The name should express **the set of methods/beans the advice intends to intercept**.
- The name should not directly describe **syntax that is likely to change** when that syntax is merely an implementation detail.
- The more public a name is and the more aspects reuse it, the more stable, documented, and scope-tested it must be.
- **The name does not alter matching results.** The expression inside `@Pointcut` still determines which methods are actually selected.

For example: `paymentApprovalOperation()` is a business-meaningful name; `executionStarApproveDotDot()` merely spells out expression characters. However, `allPaymentOperations()` is **not** a good name if the expression only matches `approve()`: a name broader than reality causes misunderstandings.

## 3. How do named pointcuts operate in Spring AOP?

Define a named pointcut with a `void` method whose body is normally empty; Spring uses the **expression metadata** as the matching condition, while the method name lets advice express clear intent:

```java
public class PaymentPointcuts {
    @Pointcut("within(example.payment..*) && execution(public * approve(..))")
    public void paymentApprovalOperation() {}
}
```

In a Spring-managed aspect, `@Before("example.aop.PaymentPointcuts.paymentApprovalOperation()")` references this definition if the actual class resides in package `example.aop`. A class storing only pointcuts does not need to be a Spring bean; an aspect containing advice must be a bean. The lesson **"Declaring Named Pointcuts with `@Pointcut`"** covers signatures, visibility, binding, and reference syntax in depth.

## 4. Naming well: intent group vs technical group

Not every technically descriptive name needs to be banned. What should be avoided is turning **expression details** into a public API that advice depends on, while the real business intent stays hidden.

| Name | Assessment | Reason |
| --- | --- | --- |
| `paymentApprovalOperation()` | Good if matching only payment approvals | Expresses advice intent and survives expression refactoring |
| `businessServiceOperation()` | Good if actual scope is the business service layer | Suitable when multiple aspects share a service boundary |
| `inPaymentModule()` | Good for a small pointcut meant for composition | Describes a clear scoping condition |
| `publicMethod()` | Good for an internal primitive pointcut | Honest about technical scope; should be combined with scoping |
| `executionPublicStarStar()` | Avoid | Merely repeats syntax, obscures business purpose |
| `allServices()` | Wrong if expression selects only one class | Name creates broader expectations than actual behavior |
| `secureOperation()` | Dangerous if backed only by a method-name pattern | Promises security that the expression does not prove |
| `paymentOperation()` | Too vague if selecting only `approve()` | Readers may assume every method in payment matches |
| `pointcut1()` / `aopCheck()` | Do not use | Conveys neither scope nor intent |
| `forLogging()` | Needs revision | States the **advice action** rather than specifying where the advice should run |

For a public name used in many places, consider adding Javadoc: "selects public approve operations in the payment module" and documenting **exceptions** such as not selecting preview, report, or calls on non-Spring objects.

## 5. Splitting pointcuts by layer and combining by intent

Spring Framework supports referencing named pointcuts by name and combining them with `&&`, `||`, `!`.

**Recommended pattern:**

~~~text
Primitive pointcuts group:
  inPaymentModule()
  publicApprovalMethod()
  hasAuditMarker()

          \______/  \_______/
                |
Intent pointcuts group:
  paymentApprovalOperation()
  sensitiveBusinessOperation()
                |
             Advice
  @Before("...paymentApprovalOperation()")
  @AfterReturning("...paymentApprovalOperation()")
~~~

A business pointcut should live in a class **close to the module owning the contract**. When shared across a large system, a dedicated class like `CommonPointcuts` can provide stable boundaries (service/data access layers); a specialized `PaymentPointcuts` class can hold payment business names. Avoid creating an oversized "global utility pointcuts" collection with no clear owner.

### 5.1. Combination rules to review

| Expression | Meaning | Scope impact |
| --- | --- | --- |
| `inPaymentModule() && publicApprovalMethod()` | Public approve method **in** payment | Intersection of two sets, typically narrower |
| `inPaymentModule() || publicApprovalMethod()` | Method in payment **or** public approve anywhere | Broader, easy to over-audit by mistake |
| `inPaymentModule() && !publicApprovalMethod()` | Methods in payment except approve | Can completely invert the intended meaning |
| `inPaymentModule() && hasAuditMarker()` | Marked methods in the payment module | Good when intentionally choosing opt-in |
| `paymentApprovalOperation() && bean(primaryPaymentService)` | Approve operation of one specifically named Spring bean | Narrower, though coupled to bean naming |

When migrating from a method-name pattern to opt-in annotations, change the pointcut implementation **only after** confirming that changing the matched set is intentional or tests prove the intended set remains unchanged. Never treat a pointcut name as a guarantee automatically verified at runtime.

### 5.2. Choosing enough scoping to prevent unintended matches

The expression `execution(public * approve(..))` alone can match `approve()` in report, inventory, or user administration. The expression `within(example.payment..*)` alone can match every method in the payment module. Combining them with `&&` expresses the intent "approval belonging to payment".

Spring AOP supports **method execution on Spring beans**, not all AspectJ designators. For proxy-based Spring AOP, common choices are `execution`, `within`, `this`, `target`, `args`, `@annotation`, and `bean`. Notably, `bean(...)` is a **Spring AOP-specific** extension; do not move that expression verbatim to native AspectJ weaving.

## 6. Runnable Java 17+ example: one pointcut name, two advice types

The example uses:

- **Spring Framework 6.2.19**, Java **17+**, **AspectJ Weaver 1.9.25.1**.
- A class declaring named pointcuts that is **not a Spring bean**.
- An aspect registered **via `@Bean`**, with both `@Before` and `@AfterReturning` referencing **one business name**.
- Two Spring service beans and three calls to test positive/negative scope.
- `@EnableAspectJAutoProxy` with class-based proxying so the demo program can retrieve concrete types easily.

### 6.1. Project structure

~~~text
spring-intent-pointcut-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── Main.java
    ├── aop/
    │   ├── PaymentPointcuts.java
    │   └── PaymentAuditAspect.java
    ├── payment/
    │   └── PaymentService.java
    └── report/
        └── ReportService.java
~~~

### 6.2. Maven: `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>spring-intent-pointcut-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.2.19</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.25.1</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The Spring Framework BOM manages `spring-*` modules so versions stay aligned. AspectJ Weaver is a dependency for parsing pointcut expressions in Spring AOP `@AspectJ`; the presence of the artifact does not automatically enable bytecode weaving.

### 6.3. Named pointcuts: `PaymentPointcuts.java`

~~~java
package example.aop;

import org.aspectj.lang.annotation.Pointcut;

public class PaymentPointcuts {

    @Pointcut("within(example.payment..*)")
    public void inPaymentModule() {}

    @Pointcut("execution(public * approve(..))")
    public void publicApprovalMethod() {}

    /**
     * Payment approval: public approve method on a type
     * in package example.payment or its subpackages.
     */
    @Pointcut("inPaymentModule() && publicApprovalMethod()")
    public void paymentApprovalOperation() {}
}
~~~

The three named pointcuts above are **metadata declarations**; there are no regular Java calls to these empty methods. The composite name `paymentApprovalOperation` will be used in advice. If how the module or method is represented changes, the edit takes place in `PaymentPointcuts`, not scattered across every aspect.

Because these signatures are `public`, they can be referenced by **fully qualified name** from another `@Aspect` class. There is no need to annotate `PaymentPointcuts` with `@Component` or register it as a Spring bean just to reference the declared pointcut definitions.

### 6.4. Aspect: `PaymentAuditAspect.java`

~~~java
package example.aop;

import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class PaymentAuditAspect {

    @Before("example.aop.PaymentPointcuts.paymentApprovalOperation()")
    public void beforePaymentApproval() {
        System.out.println("audit: before payment approval");
    }

    @AfterReturning("example.aop.PaymentPointcuts.paymentApprovalOperation()")
    public void afterPaymentApproval() {
        System.out.println("audit: after payment approval");
    }
}
~~~

The two advice methods have different execution semantics yet share **one method-selection intent**. If you change the expression at `PaymentPointcuts.paymentApprovalOperation()`, both advice methods adopt the new scope together.

Simply putting `@Aspect` on this class is not enough for Spring to scan it into a bean; the example registers `PaymentAuditAspect` using a `@Bean` method in `AppConfig`.

### 6.5. Payment service: `PaymentService.java`

~~~java
package example.payment;

public class PaymentService {

    public void preview() {
        System.out.println("payment: preview");
    }

    public void approve() {
        System.out.println("payment: approve");
    }
}
~~~

The `approve()` method resides in the payment module and is a public method, whereas `preview()` is not named approve. Both are invoked through the same bean, yet only one method should receive auditing.

### 6.6. Report service: `ReportService.java`

~~~java
package example.report;

public class ReportService {

    public void approve() {
        System.out.println("report: approve");
    }
}
~~~

`ReportService` also has an `approve()` method, yet lies outside package `example.payment` and therefore **does not satisfy** `inPaymentModule()`. This negative case proves that a pointcut name is not merely nice naming, but must be paired with an **expression narrowed to match the intent**.

### 6.7. Spring configuration: `AppConfig.java`

~~~java
package example;

import example.aop.PaymentAuditAspect;
import example.payment.PaymentService;
import example.report.ReportService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public PaymentService paymentService() {
        return new PaymentService();
    }

    @Bean
    public ReportService reportService() {
        return new ReportService();
    }

    @Bean
    public PaymentAuditAspect paymentAuditAspect() {
        return new PaymentAuditAspect();
    }
}
~~~

Thanks to `@Bean`, the Spring container holds an aspect bean. Spring AOP detects its pointcuts/advice, finds matching target classes/methods, and creates proxies when needed. `proxyTargetClass=true` lets the program retrieve beans by concrete class; enabling CGLIB **does not change the meaning of the named pointcut**.

### 6.8. Running the program: `Main.java`

~~~java
package example;

import example.payment.PaymentService;
import example.report.ReportService;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            PaymentService payment = context.getBean(PaymentService.class);
            ReportService report = context.getBean(ReportService.class);

            System.out.println("payment proxy: " + AopUtils.isAopProxy(payment));
            System.out.println("report proxy: " + AopUtils.isAopProxy(report));

            System.out.println("-- payment preview --");
            payment.preview();

            System.out.println("-- report approval --");
            report.approve();

            System.out.println("-- payment approval --");
            payment.approve();
        }
    }
}
~~~

From the directory containing `pom.xml`, run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

**Lines printed by the program in exact order:**

~~~text
payment proxy: true
report proxy: false
-- payment preview --
payment: preview
-- report approval --
report: approve
-- payment approval --
audit: before payment approval
payment: approve
audit: after payment approval
~~~

### 6.9. Reading the output as a verification of the name contract

- **`payment proxy: true`:** Spring found an advisor applicable to at least one method of `PaymentService`.
- **`report proxy: false`:** No advisor in this minimal configuration matches `ReportService`; Spring does not need to proxy it for that AOP purpose.
- **`payment.preview()`:** Caller invokes on the AOP proxy, yet `preview` does not match the composite named pointcut, so no audit advice runs.
- **`report.approve()`:** The method name matches, yet its package is not in the payment module, so no audit advice runs.
- **`payment.approve()`:** Both `inPaymentModule` and `publicApprovalMethod` match. `@Before` runs before the business method; `@AfterReturning` runs after the method finishes normally.

If another advisor is added to the app (caching, transaction, security, custom aspect), `report` could receive a proxy for that other reason. Thus `isAopProxy == false` is predicted based on **this exact example configuration**, not as a rule for every app.

## 7. Sharing a named pointcut across multiple Spring aspects

An intent name such as `paymentApprovalOperation()` can be shared by **multiple aspects**: audit `@Before`, metrics `@AfterReturning`, or tracing `@Around`. Each aspect retains its own responsibility, so sharing a match set does not automatically turn multiple policies into one policy or define advice ordering.

If only one aspect needs an extra condition, it can combine `PaymentPointcuts.paymentApprovalOperation() && bean(primaryPaymentService)` without altering the shared intent for other consumers. Real bean names must be verified, and note that `bean(...)` is a Spring AOP-specific designator, not portable to native AspectJ weaving.

## 8. When should a named pointcut be placed in a separate class?

Create a `PaymentPointcuts` or `CommonPointcuts` class when multiple advice methods/aspects genuinely depend on **one stable, meaningful set of calls**. Keep internal pointcuts `private` if only one aspect needs them, and expose `public` when there are external consumers; there is no need to extract every one-line expression into a public catalog.

Place the catalog close to the domain/module owning the policy so code reviewers see who is responsible when the expression changes. An overly large shared library easily couples unrelated modules to one another.

## 9. Safe refactoring: changing the expression without changing intent

Suppose the system initially defines:

~~~java
@Pointcut("within(example.payment..*) && execution(public * approve(..))")
public void paymentApprovalOperation() {}
~~~

After refactoring, instead of relying on method name and package, the development team wants to mark operations with `@PaymentApproval`. The intent may still be "payment approval operations", yet **the matched method set may change**.

An intentional approach:

~~~java
@Pointcut(
    "within(example.payment..*)"
    + " && @annotation(example.aop.PaymentApproval)"
)
public void paymentApprovalOperation() {}
~~~

Here `@PaymentApproval` is a **custom annotation**. The annotation definition needs `@Target(ElementType.METHOD)` and `@Retention(RetentionPolicy.RUNTIME)`; place it strictly on the methods that truly require auditing. These snippets only illustrate the refactoring direction and are **not part of the standalone project** in section 6.

If a method has not been annotated yet, it will no longer be advised. If a method not named `approve` is annotated, it can start being advised. **Do not treat two expressions as equivalent merely because the method name `paymentApprovalOperation` stayed the same.**

### 9.1. Recommended refactoring workflow

1. Write down a list of **positive matches** per the business contract, e.g., `PaymentService.approve`.
2. Write down **negative matches**, e.g., `PaymentService.preview`, `ReportService.approve`.
3. Test in a context with real bean registration and proxy strategy.
4. Change the expression in the named pointcut definition only after understanding the desired match set.
5. Run integration tests to verify both advice behavior and **no unintended interception** of out-of-scope beans.
6. Update Javadoc/contracts if business intent has changed.
7. Review advisor ordering if multiple aspects use the same named pointcut.

Expected outcome: code in advice remains readable by intent and does not require widespread edits when detection details need to change.

## 10. Do not confuse a named pointcut's name with a security guarantee

Names such as `secureOperation()`, `authorizedPayment()`, or `trustedMethod()` can mislead readers into assuming a policy **is already enforced**, whereas `@Pointcut` only defines **where advice can potentially run**.

Example:

~~~java
@Pointcut("execution(public * example.payment.PaymentService.approve(..))")
public void authorizedPayment() {}
~~~

The method above does not check authorization on its own, does not know who the caller is, and does not deny access. Unless the corresponding advice genuinely enforces security rules properly, a pointcut named `authorizedPayment` does not prove the operation is protected.

Use names describing the **set of calls** such as `paymentApprovalOperation()`; let advice carry dedicated responsibilities for auditing, authorization, metrics, or transactions, and test each layer's behavior independently.

For critical security and transactions, never rely solely on naming conventions or unverified pointcut scopes; test the real system including internal/self-invocation cases.

## 11. Common mistakes

Naming mistakes to catch during review: `allPaymentOperations()` that matches only `approve()`; `secureOperation()` making readers think authorization is enforced; literal-expression names that obscure purpose; or renaming a pointcut while forgetting fully qualified reference strings in advice/XML.

After switching implementation from a package/method pattern to `@annotation(PaymentApproval)`, **keeping the same name does not guarantee keeping the same match set**. Use positive cases (`PaymentService.approve`) and negative cases (`PaymentService.preview`, `ReportService.approve`) to verify intent, while checking bean registration and proxy boundaries.

## 12. Good naming helps review AOP changes

When reviewing a Spring Aspect pull request, a reader should immediately see:

~~~java
@Before("example.aop.PaymentPointcuts.paymentApprovalOperation()")
public void auditPaymentApproval() {
    // ...
}
~~~

The name tells **where the advice intends to run**; the advice name tells **what behavior runs there**. They address two distinct parts.

A thorough review should check:

- Is the business intent of `paymentApprovalOperation()` still accurate?
- Does the current expression truly select **only** those operations?
- Could adding a new module or method accidentally widen the matched set?
- Are there methods that should be advised yet fall outside the selected package/bean/annotation scope?
- Will multiple aspects using a shared pointcut be affected if someone edits the expression?
- Did Spring Boot/Spring Framework proxy configuration change from JDK to CGLIB and affect method visibility?
- Are there internal self-invocations via `this` or objects created with `new` that cause advice not to run?
- Are positive **and** negative tests sufficient to protect the contract?

Naming by intent helps reviews **ask the right questions**, while tests and proxy/runtime checks confirm actual behavior.

## 13. Practice scenarios

**Scenario A.** Two advice methods both contain the literal string `within(example.payment..*) && execution(public * approve(..))`. How do you reduce duplication while keeping intent clear?

**Answer:** Create a `@Pointcut` named `paymentApprovalOperation()`, place the expression in one place, and use the name in both advice methods.

**Scenario B.** The pointcut `paymentApprovalOperation()` only contains `execution(public * approve(..))`. Is it named accurately?

**Answer:** Not reliably. It also selects public `approve` methods in many other packages. Add scoping/payment conditions or rename it to reflect the actual scope.

**Scenario C.** A `PaymentPointcuts` class contains a public `@Pointcut` without `@Component`. Can the named pointcut be used from another Spring-managed `@Aspect`?

**Answer:** Yes, Spring `@AspectJ` support allows referencing named pointcuts published in another class; a class containing only signatures does not need to be a bean to be referenced. What must be registered is the aspect bean containing the advice.

**Scenario D.** A `@Pointcut` method is `private` in class A, and class B wants to reference it by its fully qualified name. Should you do that?

**Answer:** No. Java visibility applies to named pointcut references. If sharing outside the class is needed, use a public method and define a clear contract.

**Scenario E.** After changing the implementation to `@annotation(PaymentApproval)`, the name `paymentApprovalOperation()` stays unchanged. Can scope tests be skipped?

**Answer:** No. The set of matched methods can differ significantly, even though the pointcut name stayed the same.

**Scenario F.** A `payment.preview()` method on a proxied bean does not receive advice. Is it because the named pointcut was not loaded?

**Answer:** Not necessarily. If the expression selects only `approve()`, this is correct behavior: a proxied bean does not mean every method matches the same advisor.

## 14. Official documentation sources

- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html): `@Pointcut` method signatures, name references, expression composition, visibility, dedicated `CommonPointcuts`, and writing good pointcuts.
- [Spring Framework — Declaring Advice](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): `@Before`, `@AfterReturning`, and referencing named pointcuts in advice annotations.
- [Spring Framework — Pointcut API](https://docs.spring.io/spring-framework/reference/core/aop-api/pointcuts.html): `ClassFilter`, `MethodMatcher`, and reusing/composing Spring pointcuts.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html): requirements for registering aspect beans and enabling Spring AOP.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB proxy boundaries and self-invocation limits.
