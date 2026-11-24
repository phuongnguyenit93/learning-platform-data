# Binding Annotations to Advice Parameters in Spring AOP

## 1. What problem does this lesson solve?

In **Spring Framework AOP using `@AspectJ` syntax**, a pointcut can not only ask "does this method execution have a matching annotation?", it can also **pass that annotation instance itself into an advice parameter**. The advice can thereby read metadata such as an audit code, business group, metric label, or tracking level without manually looking up the annotation via reflection.

An example:

```java
@AuditAction("create")
public String create(String orderId) {
    return "created:" + orderId;
}
```

And on a Spring-managed aspect:

```java
@Before(
    value = "execution(public * com.example.binding.BillingService.*(..))"
          + " && @annotation(action)",
    argNames = "action"
)
public void beforeAction(JoinPoint jp, AuditAction action) {
    System.out.println(action.value() + ":" + jp.getSignature().getName());
}
```

In the expression, **`action` is not the name of an annotation class**. It is a **binding variable**, linked to the advice's Java parameter `AuditAction action`. When a Spring AOP proxy intercepts a matching method, the Spring/AspectJ pointcut machinery passes the annotation object into the advice so it can read `action.value()`.

**Lesson scope:** annotation binding **in Spring AOP for Spring-managed beans**, how to declare annotations and advice parameters, using `@annotation`/`@within`/`@target`/`@args` appropriately, `argNames`, Spring proxies, and testing. General AOP concepts and AspectJ weaving are not the focus; `@EnableAspectJAutoProxy` does **not** enable compile-time/load-time weaving.

## 2. Distinguishing selecting methods by annotation vs. binding an annotation

Both expressions below can select methods marked with `@AuditAction`, but their roles differ.

**Presence-check form:**

```java
@Before("@annotation(com.example.binding.AuditAction)")
public void beforeAnnotatedMethod() {
    // Knows the method execution matched the marker; does not receive the annotation object.
}
```

**Binding form to read metadata:**

```java
@Before(
    value = "@annotation(action)",
    argNames = "action"
)
public void beforeAnnotatedMethod(AuditAction action) {
    String auditCode = action.value();
}
```

The first form uses a **fully qualified annotation type name**. The second form uses a **variable name `action`**, resolved from the advice signature/`argNames`; the Java type `AuditAction` of the parameter constrains which annotation will be bound.

Points to remember:

- `@annotation(SomeType)`: requires the **method join point** to carry an annotation of that type.
- `@annotation(action)` and `AuditAction action`: requires annotation type `AuditAction` and **passes the annotation instance** into the advice.
- `action.value()`: reads metadata declared on the annotation; no manual `method.getAnnotation(...)` is needed in simple cases.
- **Binding does not create a Spring proxy automatically.** The method must belong to a Spring target bean, the aspect must be a bean, and the invocation must pass through the appropriate proxy.
- **Variable names must match exactly**; annotation attributes like `value` or `code` are not binding names unless an advice parameter actually has that name.

Do not confuse Java's `@Target` annotation type (which specifies where an annotation can be placed) with the `@target(...)` pointcut expression (which checks annotations on the Spring target object's class).

## 3. Java annotations must be declared properly for Spring AOP

An annotation for **methods**:

```java
package com.example.binding;

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

An annotation for **classes/types**:

```java
package com.example.binding;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ServiceGroup {
    String value();
}
```

Each annotation resides in its own Java file matching its public type name. In the example, `ServiceGroup` is an annotation on the target class; `AuditAction` is on the method.

### Why use `RUNTIME` retention?

Spring/AspectJ pointcut matching and binding require annotation information at runtime. For this lesson, use `@Retention(RetentionPolicy.RUNTIME)` so the annotations are available on runtime classes and methods.

- `SOURCE`: the annotation does not exist in the compiled class file at runtime.
- `CLASS`: information may be in bytecode, but is not guaranteed to be visible via standard Java reflection; **do not choose** it for runtime binding.
- `RUNTIME`: the annotation is available for runtime matchers and binding.
- `@Target(METHOD)` selects method placement; `@Target(TYPE)` selects class/interface/type placement. Match the annotation target to the corresponding pointcut designator.

These annotations are plain Java annotations; **they do not create Spring beans or trigger advice on their own**. The `@Aspect` must be a Spring-managed bean, the target must also be Spring-managed, and AOP infrastructure must be enabled.

### Is `@Inherited` needed?

`@Inherited` (Java) applies to inheriting **class-level annotations** in certain subclass lookups; it has **no** effect on making method-level annotations inherited automatically, nor does it **propagate annotations from an interface down to an implementing class**.

Do not overuse `@Inherited` as a cure-all for `@annotation`/`@target` mismatches. For interfaces, overridden methods, Kotlin types, or composed annotations, verify actual Spring advisor matching under your real proxy mode.

## 4. Four annotation pointcut groups supported by Spring AOP

Spring AOP supports the following pointcut designators for method execution join points on Spring beans:

| Designator | Where is the annotation checked? | Usable binding form | Key point |
| --- | --- | --- | --- |
| `@annotation` | **Method being executed** | `@annotation(action)` → `AuditAction action` | Best suited for reading metadata attached to individual operations. |
| `@target` | **Class of the target object** behind the Spring proxy | `@target(group)` → `ServiceGroup group` | Place the annotation on the actual implementation/target class. |
| `@within` | **Type within which the method execution is declared** and annotated | `@within(group)` → `ServiceGroup group` | Differs from `@target` in inheritance/declaring-type cases. |
| `@args` | **Runtime types of passed arguments** carrying matching type annotations | `@args(marker)` → matching type-annotation object | Not an annotation placed directly on the parameter declaration. |

All of these designators **inspect annotations as matching criteria** and have a **binding form** to pass the annotation into advice.

### 4.1. `@annotation` — annotation on the target method

```java
@Before(
    value = "execution(public * com.example.binding..*Service.*(..))"
          + " && @annotation(action)",
    argNames = "action"
)
public void inspectMethod(AuditAction action) {
    System.out.println("code=" + action.value());
}
```

This is an illustration placed inside a Spring-managed `@Aspect`. It inspects only method executions matching the package/type pattern and binds the `AuditAction` annotation. If a method lacks a matching annotation, the advice is not invoked by that expression.

This is the natural choice for per-operation metadata: `create` carries `"create"`, `refund` carries `"refund"`, while an unmarked `health` method is not selected by this `@annotation` advice.

### 4.2. `@target` — annotation on the runtime target class

```java
@Before(
    value = "execution(public * com.example.binding..*Service.*(..))"
          + " && @target(group)",
    argNames = "group"
)
public void inspectTarget(ServiceGroup group) {
    System.out.println("serviceGroup=" + group.value());
}
```

When the Spring AOP proxy's target object belongs to a class annotated with `@ServiceGroup("billing")`, the advice can receive that **target class's** annotation. `@target` does not mean "annotation on the return type", nor is it synonymous with Java's `@Target` meta-annotation.

A Spring proxy has an auto-generated runtime class; **do not inspect `proxy.getClass()` and expect the marker to be there**. When debugging, inspect the target type with `AopUtils.getTargetClass(proxy)`.

### 4.3. `@within` — annotation on the type declaring the method

```java
@Before(
    value = "execution(public * com.example.binding..*Service.*(..))"
          + " && @within(group)",
    argNames = "group"
)
public void inspectWithin(ServiceGroup group) {
    // Binds the annotation of the type associated with @within.
}
```

Compared to `@target`, Spring docs describe `@within` around **method executions declared within annotated types**. If a method is inherited from a superclass, or the annotation sits on a subclass or interface, declaring-type vs. runtime-target semantics can diverge; always test your project's Spring version and proxy mode before relying on annotations for critical policies.

### 4.4. `@args` — annotation on the runtime type of an argument

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface SensitivePayload {
}
```

```java
@SensitivePayload
public class TransferRequest {
}
```

```java
@Before(
    value = "execution(public * com.example.binding..*Service.process(..))"
          + " && @args(marker)",
    argNames = "marker"
)
public void beforeSensitivePayload(SensitivePayload marker) {
    // Annotation information on the runtime class of the argument.
}
```

These `@args` snippets are **illustrative** and are not in the runnable project in section 7; they require proper imports, Spring beans, public types, and a matching single-argument signature. `@args` is completely different from Java's `@Target(ElementType.PARAMETER)`: it inspects the **type of the argument value at runtime**, not annotations placed on the parameter declaration.

`@args` conditions depend on runtime arguments; for null, primitives, multiple arguments, interfaces/subclasses, or an annotation placed on the declared parameter type rather than the actual argument class, verify matching behavior in a real context.

## 5. `argNames` syntax and advice parameters

Spring uses names in pointcut expressions and advice parameter names to link bindings. For example:

```java
@Before(
    value = "@annotation(action)",
    argNames = "action"
)
public void beforeAction(AuditAction action) {
    // ...
}
```

All three occurrences of `action` are the **same binding name**. If you write `@annotation(audit)` but `argNames="action"`, Spring cannot link the name `audit` as intended and may fail when building the advisor.

### 5.1. `JoinPoint` is a special parameter

When you need both method metadata and the annotation:

```java
@Before(
    value = "@annotation(action)",
    argNames = "action"
)
public void beforeAction(JoinPoint jp, AuditAction action) {
    String methodName = jp.getSignature().getName();
    String actionName = action.value();
}
```

`JoinPoint` is imported from `org.aspectj.lang.JoinPoint` and **placed first in the parameter list**. Per Spring, the leading `JoinPoint` parameter name **can be omitted from `argNames`**, because the framework recognizes that special type. Thus `argNames="action"` is valid for the signature `(JoinPoint jp, AuditAction action)`.

An advice needing only `JoinPoint` can declare:

```java
@Before("execution(* com.example.binding..*Service.*(..))")
public void inspect(JoinPoint jp) {
    System.out.println(jp.getSignature().getName());
}
```

No `argNames` is needed when no other expression variables are bound.

### 5.2. `ProceedingJoinPoint` for `@Around`

```java
@Around(
    value = "execution(public * com.example.binding..*Service.*(..))"
          + " && @annotation(action)",
    argNames = "action"
)
public Object aroundAction(
        ProceedingJoinPoint pjp, AuditAction action) throws Throwable {
    // Can read action.value() before or after.
    return pjp.proceed();
}
```

This is **illustrative code** inside a Spring-managed `@Aspect` and requires importing `org.aspectj.lang.ProceedingJoinPoint` and `Around`. `ProceedingJoinPoint` must be the first parameter of `@Around`, and `proceed()` is called so the target continues executing. `argNames` does not need to list the leading `pjp`.

If you only need to read the annotation or log, `@Before` carries fewer privileges and avoids the risk of forgetting `proceed()`; use `@Around` when you genuinely need to control ordering/timing or alter the outcome per contract.

### 5.3. Multiple binding parameters

You can bind business arguments, target, and annotations together:

```java
@Before(
    value = "execution(public * com.example.binding.BillingService.create(..))"
          + " && args(id)"
          + " && @annotation(action)",
    argNames = "id,action"
)
public void beforeCreate(
        JoinPoint jp, String id, AuditAction action) {
    System.out.println(
        action.value() + ":" + id + ":" + jp.getSignature().getName()
    );
}
```

- `args(id)` binds the **runtime method argument** to `String id`.
- `@annotation(action)` binds the **method annotation** to `AuditAction action`.
- `argNames="id,action"` corresponds to the two binding variables; `jp` does not need to be listed because it is the leading `JoinPoint` parameter.
- Advice runs only when the entire expression matches.
- If input values or annotation metadata are sensitive, **do not print them directly** to production logs.

`args(id)` differs from `@args(marker)`: the former binds the **argument value**, whereas the latter inspects/binds the **annotation on the argument's type**.

## 6. Required Spring infrastructure for annotation binding to run

An annotated target method is not advised automatically. All four conditions must hold:

1. **Aspect bean:** the `@Aspect` class must be registered via `@Component` within component-scan scope or returned from a `@Bean`.
2. **AOP support:** in Spring Framework Java config, use `@EnableAspectJAutoProxy` with a compatible `aspectjweaver`; in Spring Boot, use AOP auto-configuration via the appropriate starter.
3. **Target bean:** the business object is a Spring-managed bean; instantiating `new BillingService()` outside the context will not be intercepted automatically by Spring AOP.
4. **Proxy boundary:** callers obtain/inject the target **through the proxy**, the method must be on a JDK proxy's interface or overridable in CGLIB, and `this.inner()` does not go back through the proxy.

This is **Spring AOP proxying**, not AspectJ load-time weaving. Having the `aspectjweaver` dependency so Spring can parse `@AspectJ` expressions does not mean a Java agent has been configured.

`@EnableAspectJAutoProxy(proxyTargetClass=true)` can force class-based proxies. With a Java `final class`, CGLIB cannot subclass it; a `final method` cannot be overridden, so placing an annotation on that method cannot rescue interception. When an interface exists and class proxying is not forced, a JDK dynamic proxy may be used, but the method must belong to the interface and annotation matching on interface vs. implementation requires integration tests.

### Two ways to create an aspect bean

**Component scan:**

```java
@Aspect
@Component
public class AuditAspect {
    @Before("@annotation(action)")
    public void before(AuditAction action) {
        // ...
    }
}
```

**Bean factory method:**

```java
@Configuration
@EnableAspectJAutoProxy
public class AppConfig {
    @Bean
    AuditAspect auditAspect() {
        return new AuditAspect();
    }
}
```

These snippets are **illustrative**, not a runnable project example; full imports/classes appear in section 7. `@Aspect` **does not imply `@Component`**: if using component scanning without registration, Spring will not build the advice. Avoid registering the same aspect twice via both scanning and `@Bean` unless there is an explicit reason.

## 7. Runnable demo: binding method and class annotations into two advice methods

Plain Spring Framework demo with **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, and Gradle. One Spring target class carries `@ServiceGroup("billing")`, and two methods carry `@AuditAction`. The aspect uses two separate `@Before` advice methods:

- `@annotation(action)` binds each method's metadata and records an event.
- `@target(group)` binds the target class's annotation and increments a counter for every matching method on the target.

In addition, `selfCall` proves that an internal method annotated with `@AuditAction` **is not advised again** when invoked via `this`, even though its Java body runs.

### 7.1. Directory structure

```text
spring-aop-annotation-binding/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/binding/
    ├── AuditAction.java
    ├── ServiceGroup.java
    ├── BillingService.java
    ├── BindingAspect.java
    ├── AppConfig.java
    └── Main.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-aop-annotation-binding'
```

**`build.gradle`**

```gradle
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'com.example.binding.Main'
}
```

Spring Framework 6.2.19 is compatible with Java 17+. In a Spring Boot project, avoid manually forcing Spring module versions that conflict with the BOM of the Boot version in use.

### 7.2. Defining the method annotation

**`AuditAction.java`**

```java
package com.example.binding;

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

This annotation has no runtime logic of its own; the Spring AOP aspect will bind it and read `value()` when the pointcut matches.

### 7.3. Defining the target-type annotation

**`ServiceGroup.java`**

```java
package com.example.binding;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ServiceGroup {
    String value();
}
```

`ServiceGroup` differs from `AuditAction` in `@Target`: one annotation is used on classes, the other on methods.

### 7.4. Spring service with two annotated methods

**`BillingService.java`**

```java
package com.example.binding;

@ServiceGroup("billing")
public class BillingService {
    @AuditAction("create")
    public String create(String id) {
        return "created:" + id;
    }

    @AuditAction("reject")
    public String reject(String id) {
        throw new IllegalStateException("rejected:" + id);
    }

    public String health() {
        return "ok";
    }

    public String selfCall(String id) {
        return this.create(id);
    }
}
```

- `create`: has method annotation `@AuditAction("create")`; returns normally.
- `reject`: has method annotation `@AuditAction("reject")`; throws an exception. `@Before` is still called before the target throws.
- `health`: has no `@AuditAction` method annotation, yet the **class** has `@ServiceGroup("billing")`.
- `selfCall`: has no method annotation; it calls `this.create(...)` on the same target. Self-invocation bypasses the proxy, so `@Before` for `create` does not run again for this internal call.

No method is `final`/`private` and the class is not `final`, ruling out CGLIB override restrictions.

### 7.5. Aspect binding two independent annotation kinds

**`BindingAspect.java`**

```java
package com.example.binding;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class BindingAspect {
    private final List<String> actionEvents =
            new CopyOnWriteArrayList<>();
    private final AtomicInteger groupCalls = new AtomicInteger();

    @Before(
        value = "execution(public * com.example.binding.BillingService.*(..))"
              + " && @annotation(action)",
        argNames = "action"
    )
    public void beforeAction(JoinPoint jp, AuditAction action) {
        actionEvents.add(
            action.value() + ":" + jp.getSignature().getName()
        );
    }

    @Before(
        value = "execution(public * com.example.binding.BillingService.*(..))"
              + " && @target(group)",
        argNames = "group"
    )
    public void beforeGroup(ServiceGroup group) {
        if ("billing".equals(group.value())) {
            groupCalls.incrementAndGet();
        }
    }

    public List<String> events() {
        return List.copyOf(actionEvents);
    }

    public int groupCount() {
        return groupCalls.get();
    }
}
```

Notes:

- `argNames="action"` maps to `AuditAction action`; the leading `JoinPoint jp` parameter is recognized specially and need not be listed.
- `argNames="group"` maps to `ServiceGroup group`.
- `group.value()` reads metadata from the annotation bound on the target class, not the Spring proxy class name.
- `CopyOnWriteArrayList` and `AtomicInteger` keep observation writes free of basic races; the demo calls sequentially, without treating counters as distributed metrics.
- **Do not log inside advice**, so final stdout does not depend on the ordering of the two `@Before` advice methods on the same join point.

If a real project involves additional advisors, test pointcut conditions and side effects on the actual Spring context.

### 7.6. Spring config with class-based proxy

**`AppConfig.java`**

```java
package com.example.binding;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    BillingService billingService() {
        return new BillingService();
    }

    @Bean
    BindingAspect bindingAspect() {
        return new BindingAspect();
    }
}
```

Both `BillingService` and `BindingAspect` are created by Spring as beans via `@Bean`. `@EnableAspectJAutoProxy` enables support for `@AspectJ` annotations. Setting `proxyTargetClass=true` selects a CGLIB class proxy so `Main` can retrieve the Spring bean by `BillingService.class`. The demo needs no `@ComponentScan`.

### 7.7. Main using the Spring proxy and verifying output

**`Main.java`**

```java
package com.example.binding;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            BillingService service = context.getBean(BillingService.class);
            BindingAspect aspect = context.getBean(BindingAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println("create=" + service.create("A"));

            try {
                service.reject("B");
            } catch (IllegalStateException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            System.out.println("health=" + service.health());
            System.out.println("selfCall=" + service.selfCall("C"));

            System.out.println("events=" + aspect.events());
            System.out.println("groupCalls=" + aspect.groupCount());
        }
    }
}
```

Run in the project directory with Gradle and JDK 17+ installed:

```bash
gradle run --quiet
```

If Gradle Wrapper is present: `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows.

**Lines printed by the program in exact order** (excluding external JVM/Spring/Gradle logs):

```text
proxy=true
create=created:A
caught=rejected:B
health=ok
selfCall=created:C
events=[create:create, reject:reject]
groupCalls=4
```

### 7.8. Why are there two action events but four group calls?

| Invocation from main | Method-level annotation? | Target-class annotation? | `@annotation(action)` runs? | `@target(group)` runs? |
| --- | --- | --- | --- | --- |
| `service.create("A")` | `@AuditAction("create")` | `@ServiceGroup("billing")` | Yes: `create:create` | Yes: +1 |
| `service.reject("B")` | `@AuditAction("reject")` | `@ServiceGroup("billing")` | Yes: `reject:reject` | Yes: +1 |
| `service.health()` | No | `@ServiceGroup("billing")` | No | Yes: +1 |
| `service.selfCall("C")` | Not on `selfCall` method | `@ServiceGroup("billing")` | Not at `selfCall` entry | Yes: +1 |
| `this.create("C")` inside `selfCall` target | Annotation exists on `create` | Class has annotation | **No**, because self-invocation bypasses proxy | **No**, because call does not go through proxy |
| **Total on proxy calls** | Two annotated entries | Four external entries | **2** | **4** |

The `create(..)` body executes twice (external `A` and internal `C`), yet `@annotation(action)` runs **only once for `create`** at the external entry. `reject` throws an error, yet `@Before` already ran beforehand, so `reject:reject` still appears.

The table shows that binding depends on **Spring interception**. The annotation still exists on the source method during a self-call; what is missing is the **proxy boundary**, not the metadata.

## 8. Named `@Pointcut` with annotation parameter and reuse

If multiple advice methods in the same aspect want to share a selection, declare a named pointcut with a **binding parameter**:

```java
@Aspect
public class SharedAuditAspect {
    @Pointcut(
        value = "execution(public * com.example.binding.BillingService.*(..))"
              + " && @annotation(action)",
        argNames = "action"
    )
    private void annotatedAction(AuditAction action) {}

    @Before(
        value = "annotatedAction(action)",
        argNames = "action"
    )
    public void before(AuditAction action) {
        System.out.println("before=" + action.value());
    }

    @AfterReturning(
        value = "annotatedAction(action)",
        argNames = "action"
    )
    public void afterReturning(AuditAction action) {
        System.out.println("returned=" + action.value());
    }
}
```

This is an **illustrative variant**, requiring imports for `@Aspect`, `@Pointcut`, `@Before`, `@AfterReturning`, and registration as a Spring bean; **do not add** it to section 7's demo if you want to preserve the stated stdout.

- `annotatedAction(AuditAction action)` is the **signature of the named pointcut**, not a business method, and its body should be empty.
- `argNames="action"` on `@Pointcut` defines the parameter name used by the expression.
- `annotatedAction(action)` in the advice expression passes a **binding variable**, not a Java method call returning an annotation.
- `@Before` runs before the method; `@AfterReturning` runs only if the method completes normally. `reject(..)` throws an error, so after-returning will not appear in that case.
- If you want to use a named pointcut from **another aspect class**, it needs appropriate Java visibility and a fully qualified reference; `private` works only inside the declaring type.
- Do not write a `@Pointcut` signature returning `boolean` to check annotation matching; named pointcut signatures must return `void`.

Maintain a public catalog of pointcuts with stable meanings when multiple modules reference them. For a single aspect, a private pointcut reduces coupling.

## 9. Binding multiple annotations in the same advice

A method belonging to an annotated target class that also carries a method marker can bind both:

```java
@Before(
    value = "execution(public * com.example.binding.BillingService.*(..))"
          + " && @target(group)"
          + " && @annotation(action)",
    argNames = "group,action"
)
public void beforeBoth(
        ServiceGroup group, AuditAction action) {
    System.out.println(group.value() + ":" + action.value());
}
```

This is an **illustrative snippet**, assuming it lives inside a Spring-managed `@Aspect`. In section 7's project, it would select `create(..)` and `reject(..)`, but not `health(..)` or `selfCall(..)` because the latter two lack `@AuditAction`. It would print `billing:create` and `billing:reject` if registered; do not add it so stdout stays unchanged.

### Also using `JoinPoint`

```java
@Before(
    value = "execution(public * com.example.binding.BillingService.*(..))"
          + " && @target(group) && @annotation(action)",
    argNames = "group,action"
)
public void beforeBoth(
        JoinPoint jp, ServiceGroup group, AuditAction action) {
    System.out.println(
        jp.getSignature().getName()
        + ":" + group.value()
        + ":" + action.value()
    );
}
```

Spring recognizes the leading `JoinPoint` under the special rule. `argNames` declares only the expression variables the advice binds; for different signatures, update `argNames` accordingly.

Using multiple annotation bindings makes sense when each annotation carries distinct metadata. Do not write an overly broad pointcut just to "collect" every annotation across the system; constrain it with an appropriate `execution(...)`/package/type scope.

## 10. Distinguishing reflection lookup from pointcut binding in Spring

A common way to read an annotation using reflection:

```java
Method method = BillingService.class.getMethod("create", String.class);
AuditAction marker = method.getAnnotation(AuditAction.class);
System.out.println(marker.value());
```

This is an **illustrative Java snippet**; it requires importing `java.lang.reflect.Method` and handling/wrapping checked reflection exceptions. Direct reflection is useful when you **already know the exact class and method**.

In Spring AOP, advice can receive metadata more conveniently:

```java
@Before(
    value = "execution(* com.example.binding.BillingService.create(..))"
          + " && @annotation(action)",
    argNames = "action"
)
public void beforeCreate(AuditAction action) {
    System.out.println(action.value());
}
```

The advantage is that the Spring/AspectJ matcher binds **the exact annotation participating in join point matching**, without the advice having to write code to look up Java `Method`, handle bridge methods, or decide which target type to search for the annotation.

**Do not assume binding replaces all reflection needs:** if you must inspect method overloads, annotations on generic interfaces, composed/meta-annotations, or runtime-proxy-specific details, you may need `AopUtils.getMostSpecificMethod` or Spring's `AnnotatedElementUtils`/`MergedAnnotations` depending on the problem. Those APIs have different lookup semantics from pointcut expressions; do not call them "automatically equivalent to `@annotation`".

## 11. Spring proxy pitfalls and annotation placement

### 11.1. Annotation placed only on an interface

```java
public interface PaymentPort {
    @AuditAction("pay")
    String pay(String id);
}

public class PaymentService implements PaymentPort {
    @Override
    public String pay(String id) {
        return "paid:" + id;
    }
}
```

This is an illustrative snippet. Java annotations on an interface method **are not automatically inherited onto the implementing method** via Java `@Inherited`. With Spring AOP, JDK interface proxies and CGLIB class proxies resolve methods differently; Spring provides annotation-search mechanisms in certain features, yet you should not assume every `@annotation` expression automatically finds interface annotations identically across all infrastructure.

**Recommendation:** when a critical audit policy attaches to an implementation method, place the annotation where the Spring aspect matcher has been verified to find it, or design interface contracts/pointcuts explicitly. Write separate integration tests for JDK proxies and class proxies if the project supports both.

### 11.2. Annotations on superclass/subclass

`@target` checks the target class, while `@within` describes the declared type; inherited or overridden methods can make matching/binding behave differently than expected. `@Inherited` applies only to **class-level annotations** under Java rules; it does not automatically make an inherited method annotated.

If an annotation policy needs to cover all subclasses, test a directly annotated class, subclasses with/without `@Inherited`, overridden methods, and inherited methods separately.

### 11.3. Class-level annotation used with `@annotation`

`@ServiceGroup` is placed on classes and has `@Target(TYPE)`. Using `@annotation(group)` to match a class-level annotation **targets the wrong join point construct**; use `@target(group)` or `@within(group)` appropriately. Conversely, `@AuditAction` has `@Target(METHOD)` and will not make `@target(action)` match.

### 11.4. Method has an annotation yet cannot be intercepted

A `final` method under a class-based CGLIB proxy cannot be overridden; `private` methods also cannot be advised via proxying. A richly metadata-filled `@AuditAction` **cannot fix** this technical limitation. Calling `this.create()` inside the target still bypasses even when the method is public and non-final.

### 11.5. Bean is not Spring-managed

`@AuditAction` does not register a Spring bean; `@Aspect` does not automatically turn into `@Component`. If the service is created with `new` or the aspect is missing from the bean registry, there will be no corresponding interceptor.

### 11.6. Do not conclude from `AopUtils.isAopProxy()` alone

`AopUtils.isAopProxy(bean)` tells you the bean has a Spring proxy. It **does not prove** a specific `@annotation(action)` advisor matches every method call. The proxy may exist due to another advisor, the method may lack the annotation, or the caller may actually hold the raw target.

Use an **event recorder** or counter like in the demo to verify the annotation object was passed into the right advice on the right call path.

## 12. When annotation metadata drives auditing, metrics, or security

An annotation can carry metadata:

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface ActionPolicy {
    String name();
    boolean sensitive() default false;
}
```

An advice can bind `ActionPolicy policy` and decide **how to observe** the method:

```java
@Before(
    value = "@annotation(policy)",
    argNames = "policy"
)
public void recordPolicy(ActionPolicy policy) {
    if (!policy.sensitive()) {
        System.out.println("action=" + policy.name());
    }
}
```

This is **illustrative code** requiring imports and registration. When an annotation says "sensitive", having the policy **skip logging sensitive data** is far safer than logging all of `JoinPoint.getArgs()`.

However, do not treat a custom logging aspect as the **sole security boundary**:

- Spring method security requires its own activation configuration and dedicated interceptors.
- If a custom security advice relies only on `@annotation` while callers trigger self-invocation, it can be bypassed.
- Overly broad pointcuts can also advise unintended beans.
- `@Around` can skip `proceed()`/return a fallback; authorization requires a strict contract and security integration tests.
- Annotation metadata does not guarantee the caller is authenticated/authorized; that belongs in the security infrastructure layer.

When using annotations for tracing/metrics, account for tag cardinality. For example, turning `orderId` into a metric label creates high cardinality; tag by stable `@AuditAction("create")` and service group rather than per-customer or per-request IDs.

## 13. How does Spring Boot apply this?

In Spring Boot with version-appropriate AOP auto-configuration, `@AspectJ` annotations follow the exact same rules:

- Create the annotation with `RUNTIME` retention.
- Annotate the target method or class.
- Create a **Spring-managed `@Aspect`** (typically `@Aspect` + `@Component`) within component-scan scope.
- Write a pointcut `execution(...) && @annotation(marker)` (or `@target`/`@within`) and an advice parameter with matching type and name.
- Use `argNames` when explicit binding is desired; leading `JoinPoint`/`ProceedingJoinPoint` has special rules.
- Verify proxy kind/call paths and write integration tests, especially for final classes/methods, interface annotations, or Kotlin's default-final classes.

Example Gradle dependencies (choose according to Boot major version with appropriate dependency management):

```gradle
// Spring Boot 3.x
implementation 'org.springframework.boot:spring-boot-starter-aop'
```

```gradle
// Spring Boot 4.x
implementation 'org.springframework.boot:spring-boot-starter-aspectj'
```

These two lines are **two mutually exclusive options**; do not add both to a project regardless of Boot version. `spring.aop.proxy-target-class` controls JDK vs. CGLIB proxying; using `@annotation` does not remove Spring proxy limitations.

## 14. Testing Spring annotation binding meaningfully

### 14.1. Test on a real Spring `ApplicationContext`

At minimum, an integration test must build a Spring context containing:

1. The target service bean;
2. The `@Aspect` bean;
3. `@EnableAspectJAutoProxy` or Boot AOP auto-config;
4. Method calls through the bean reference returned by Spring.

Calling Java methods directly like `new BindingAspect().beforeAction(..., ...)` only proves the Java advice method runs when called manually; it **does not prove Spring binds the annotation via the pointcut**.

### 14.2. Verifying cases from the demo

- `create("A")`: produces one `AuditAction("create")` event and one `ServiceGroup("billing")` group count.
- `reject("B")`: `@Before` still receives marker `"reject"` even though the method subsequently throws an exception.
- `health()`: no method-annotation event, yet the type-annotation event is still counted.
- `selfCall("C")`: group advice for the **entry method `selfCall`** is counted; nested `this.create()` generates no extra method event.
- Direct call to `new BillingService().create("X")` (outside the container) does not change aspect counters.
- When `@AuditAction` is removed from a method, `@annotation` advice no longer matches that method; the bean does not necessarily lose its proxy if the `@target` advisor still applies.

A standalone assertion using the demo classes:

```java
try (var context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    BillingService service = context.getBean(BillingService.class);
    BindingAspect aspect = context.getBean(BindingAspect.class);

    service.create("A");
    try {
        service.reject("B");
    } catch (IllegalStateException expected) {
        // Exception occurred, yet @Before already ran.
    }
    service.health();
    service.selfCall("C");

    if (!aspect.events().equals(
            java.util.List.of("create:create", "reject:reject"))) {
        throw new AssertionError("Incorrect method annotation binding");
    }
    if (aspect.groupCount() != 4) {
        throw new AssertionError("Incorrect target type annotation binding");
    }
}
```

This is a **test variant** creating a fresh context; it requires importing `AnnotationConfigApplicationContext` and placing in an appropriate Java test/main class; do not add it to `Main.java` if you want to preserve section 7.7's stdout.

### 14.3. Testing binding when renaming parameters

Create a separate test fixture that intentionally uses `@annotation(marker)` with `argNames="action"`. The goal is to confirm invalid configuration is caught when Spring builds the advisor. Do not put malformed advice into a production context or the main demo because it can fail startup for the entire context.

### 14.4. Testing proxy types

If the project uses both JDK dynamic proxies and CGLIB, write separate tests with interface annotations and implementation annotations; check `AopUtils.isJdkDynamicProxy(bean)` or `isCglibProxy(bean)`, then assert **advice invocation**, not merely proxy existence. Ensure callers inject by interface if the bean is a JDK proxy.

## 15. Common configuration errors

| Symptom | Likely cause | Check |
| --- | --- | --- |
| Spring context startup fails when binding annotation | `argNames` does not match expression variable name or advice parameter | Align `@annotation(marker)`, `argNames="marker"`, `AuditAction marker`. |
| Advice runs but cannot read expected metadata | Used presence-only FQCN form or wrong annotation type | Use binding form `@annotation(marker)` and matching parameter type. |
| Annotation is on class, `@annotation(marker)` does not match | `@annotation` looks for method annotations, not type annotations | Use `@target` or `@within` as appropriate. |
| Annotation is on method, `@target(marker)` does not match | `@target` looks for annotations on the target type | Use `@annotation`. |
| Annotation has only `SOURCE` retention | No annotation object exists at runtime to match/bind | Choose `RUNTIME` for the markers in this lesson. |
| Annotation is only on interface while implementation class differs | Java annotations are not inherited from interfaces by default | Test actual Spring method resolution / JDK-CGLIB and place policy properly. |
| Aspect is never called | Aspect is not a bean, AOP is off, target is outside container | Check `@Bean`/`@Component`, `@EnableAspectJAutoProxy`, and component scan. |
| Proxy exists but nested call event is missing | `this.inner()` bypasses proxy | Extract to an injected collaborator or advise the outer entry. |
| `@Before` method args mismatch | `args(arg)` binds runtime arg but type/name is incompatible | Confirm number/type of args and `argNames`. |
| Annotation fails to bind into `JoinPoint` | Confusing `JoinPoint` with the binding variable | Leading `JoinPoint`, marker declared as a separate parameter. |
| `@Around` code has annotation yet target does not run | Forgot `pjp.proceed()` or short-circuited | Call `proceed()` per contract and test side effects. |
| `final` method under CGLIB is not advised | Class proxy cannot override the method | Choose appropriate proxy strategy / entry method. |
| Method has annotation but only tested `new Service()` | No Spring proxy | Test via Spring context and injected proxy. |
| Advice logs overly sensitive data | Metadata used to log raw args/results indiscriminately | Allowlist/redact, limit cardinality, and enforce privacy policy. |

## 16. Workflow for applying to a real Spring project

### Step 1 — Define the metadata you actually need

Do not add annotations just "for decoration". Pick information that is stable at compile time: operation name, audit category, or service family. If metadata varies per request, it should come from arguments or request context rather than a constant annotation.

### Step 2 — Choose the right annotation placement

Method operation → `@Target(METHOD)` and `@annotation`; service target type → `@Target(TYPE)` and `@target`; type declaring execution → `@within`; annotation on runtime argument type → `@args`.

### Step 3 — Ensure `RUNTIME` retention

Declare `@Retention(RUNTIME)` with method/class names matching marker placement. Verify the annotation is actually present on the concrete target or method to intercept; do not assume interface inheritance.

### Step 4 — Enable Spring AOP in the right context

The aspect must be a Spring bean, the target must be a Spring bean, `@EnableAspectJAutoProxy`/Boot AOP auto-configuration must be enabled, and compatible dependencies must be present. In multi-context applications, AOP support is scoped per context; do not assume an advisor in the root context automatically applies to every child context.

### Step 5 — Write a scoped pointcut

Combine `execution(public * com.example.orders..*Service.*(..))` with the binding designator. Avoid writing `@annotation(marker)` alone across the whole application if it accidentally matches too broadly or creates unnecessary proxies.

### Step 6 — Set `argNames` and advice signature accurately

Pointcut variable names must match advice parameters; leading `JoinPoint` is bound specially, while other variables need matching Java types. When multiple binding variables exist, declare `argNames` in the exact order of binding parameters.

### Step 7 — Test through the Spring proxy

Call annotated methods from the context, unannotated methods, throwing methods, and self-invocation paths, then measure events/metadata; confirm the annotation object receives the exact expected values.

### Step 8 — Review side effects and operations

Do not store request-sensitive mutable state in a singleton aspect; do not log secrets; do not use annotation markers to replace authorization; if advice can throw exceptions or alter outcomes (`@Around`), test the actual contract.

## 17. Final checklist

- [ ] Correctly chose between `@annotation` (method), `@target` (target class), `@within` (declaring type), and `@args` (runtime argument class)?
- [ ] Annotation has appropriate `@Target` and `@Retention(RUNTIME)`?
- [ ] Know when to use `@annotation(FQCN)` for matching vs. `@annotation(marker)` for binding the annotation instance?
- [ ] Advice parameter has the right annotation type and name `marker` matching `argNames`/pointcut?
- [ ] If using `JoinPoint` or `ProceedingJoinPoint`, is it the first parameter and omitted from `argNames`?
- [ ] Aspect has `@Aspect` **and** is a Spring-managed bean?
- [ ] Target is a Spring-managed bean, AOP infrastructure is enabled in the right context, and AspectJ dependency is present?
- [ ] Pointcut expression is scoped with an appropriate package/type/method contract?
- [ ] Caller goes through the Spring proxy, without `new`/self-invocation, and the method can be intercepted by the proxy?
- [ ] If the annotation is placed on an interface/superclass, tested with the exact JDK/CGLIB proxy and inheritance semantics?
- [ ] Annotation data is handled safely without logging secrets or high-cardinality request IDs?
- [ ] Integration tests assert metadata binding/events, not just `AopUtils.isAopProxy(bean)`?
- [ ] If additionally binding `args(...)`, do argument names, positions, and Java types match?
- [ ] If using `@Around`, does `proceed()` follow proper semantics and preserve the return/exception contract?

**Takeaway:** With Spring AOP, an annotation on a method or class can become an **advice parameter value** through a binding form like `@annotation(action)` or `@target(group)`. Spring connects the **variable name in the expression**, `argNames`, and the **Java parameter type**; the advice receives the annotation object to read metadata. However, metadata is passed only when you have **a Spring-managed aspect + a Spring target bean + a proxy invocation + a pointcut match**. That is the essential boundary between an annotation sitting in source code and advice actually running.

## Spring reference documentation

- [Spring Framework 6.2 — Declaring Advice: Passing Parameters to Advice and argNames](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Declaring a Pointcut: @annotation, @target, @within, @args](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Proxying Mechanisms and self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Maven Central — AspectJ Weaver](https://central.sonatype.com/artifact/org.aspectj/aspectjweaver)
