# Annotations on Interfaces, Implementation Methods, and Classes in Spring AOP

## 1. Why Does Annotation Placement Affect Advice?

In Spring AOP, an annotation can live on an **interface method**, an **implementation method**, an **implementation class**, or the **interface itself**. Although the same custom annotation is written, these four locations are not equivalent when writing pointcuts or reading invocation metadata.

The core reason lies in three layers of mechanisms:

1. Spring AOP uses **proxies** to intercept method executions on Spring beans. Calls must go through the proxy and the pointcut must match.
2. **Java reflection does not automatically copy annotations** from an interface to a class or implementation method. `@Override` does not change this rule.
3. `@annotation`, `@within`, and `@target` inspect different places; the fact that a specific framework looks up additional metadata on interfaces does not mean Java has annotation inheritance for interfaces.

This article focuses on **selecting and reading annotations for Spring AOP**, with runnable examples and concrete observed results. Pure Java annotation concepts are mentioned only where needed to explain the outcome in Spring.

### Common Locations

~~~java
// (A) Annotation on an interface method
interface PaymentPort {
    @Tracked("interface-method")
    void pay();
}

// (B) Annotation on an implementation method
class PaymentService implements PaymentPort {
    @Override
    @Tracked("implementation-method")
    public void pay() { }
}

// (C) Annotation on an implementation class
@Tracked("implementation-class")
class ShippingService {
    public void ship() { }
}

// (D) Annotation on the interface itself
@Tracked("interface-type")
interface ShippingPort {
    void ship();
}
~~~

This is a **placement illustration snippet** (not a standalone Java program). The `Tracked` annotation must have `@Retention(RUNTIME)` and `@Target({METHOD, TYPE})` to be readable via reflection at runtime.

## 2. Distinguishing Pointcut Matching from Annotation Lookup

### 2.1. Three Different Expressions

Spring AOP supports annotation-related pointcut designators:

| Expression | Meaning in Spring AOP | Question Asked |
| --- | --- | --- |
| `@annotation(com.example.Tracked)` | Matches method executions carrying the annotation on the method as the join point subject | Does this method call have a matching annotation? |
| `@within(com.example.Tracked)` | Restricts to method executions within an annotated type | Is the method declared in a marked type? |
| `@target(com.example.Tracked)` | Checks the annotation on the class of the executing target object | Does the runtime target class have a matching annotation? |

With `execution(* ...)`, you select methods by signature; with the expressions above, you select based on annotations. **Do not assume `@annotation` automatically means "scan annotations on implementation methods, all interfaces, classes, and superclasses"**.

For example, to measure all public methods of objects that have an annotation on the **target class**:

~~~java
@Around("@target(com.example.annotationdemo.Tracked) && execution(public * *(..))")
public Object aroundTargetClass(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
~~~

The snippet above illustrates the expression; it must be placed inside a valid Spring `@Aspect`. `@target` does not mean taking an annotation attached to an interface by "inheriting" it onto the target class.

### 2.2. Two Proxy Types Create Important Differences

| Factor | JDK Dynamic Proxy | Class-Based Proxy (CGLIB in Spring) |
| --- | --- | --- |
| Object type client usually sees | Proxy implementing the interface | Proxy subclassing the target class |
| Methods client can invoke to advise | Public methods exposed through the proxied interface | Overridable/interceptable methods; generally public methods should be used |
| Method signature obtained from `MethodSignature.getMethod()` | May be the method declared on the interface | May be the method of the implementation class |
| Looking up annotations only from the proxy signature method | May miss annotations present only on the implementation | May miss annotations present only on the interface |
| Self-invocation `this.method()` | Does not go through proxy | Does not go through proxy |

Spring Boot 3.x normally uses class-based proxies by default for AOP; JDK proxies can be selected with `spring.aop.proxy-target-class=false` if the bean has suitable interfaces. Plain Spring Framework may have a different default depending on configuration. There is no need to guess the proxy type: `AopUtils.isJdkDynamicProxy(bean)` or `AopUtils.isCglibProxy(bean)` can be used when checking.

Note: `MethodSignature.getMethod()` provides the method corresponding to the join point signature. To inspect implementation annotations, use `AopUtils.getMostSpecificMethod(signature.getMethod(), targetClass)` and check the **target** class directly, rather than relying solely on the proxy class.

### 2.3. Java `@Inherited` Does Not Solve Interface Methods

`@Inherited` only applies to **class-level** annotation inheritance along the superclass chain in Java's lookup mechanism; it does not make an interface annotation become an annotation declared on an implementation class, nor does it apply to annotations on overridden methods. Do not treat `getDeclaredAnnotation()` on an implementation method as automatically reading annotations from an interface method.

Some Spring components such as `@Transactional` use **their own specialized metadata lookup mechanism**, which can support annotations declared on interfaces in proxy mode. Do not infer that a custom `@Aspect` with `@annotation` shares the exact same lookup policy as the transaction interceptor. When guarantees are needed, define a placement policy and verify it on the exact Spring version in use.

## 3. Recommended Rule for Consistent Custom Annotation Usage

Suppose the business requirement allows writing annotations in all four locations. A clear precedence order can be defined:

1. Annotation directly on the **implementation method**.
2. Annotation on the corresponding **interface method**.
3. Annotation on the **implementation class**.
4. Annotation on the **interface type**.

This is an **application-chosen rule**, not a universal default precedence order for all Spring annotations. It prevents a general class-level annotation from overriding method-specific configuration, while still supporting interfaces as contract declaration sites.

If multiple interfaces share the same signature yet carry different annotations, a conflict policy (e.g., failing at startup) or a documented precedence order is needed. Do not rely on `Class.getInterfaces()` ordering to make business decisions when configurations conflict. In the hands-on example below, each service implements only one interface, so that conflict does not arise.

One particular nuance: **the advice must be selected first before a resolver inside the advice can execute**. If an aspect only uses `@annotation(Tracked)` and the expression fails to match at the proxy boundary, writing thorough reflection code inside the advice still will not get that method intercepted. A safe approach when defining your own four-location policy is to select the method scope using `execution` (limiting packages/beans as needed), then look up the annotation in the advice.

## 4. Runnable Spring Boot Program: Covering All Four Locations

This example uses Java 17, Spring Boot 3.3.x, and Spring AOP. Each service has one `execute()` method, marked in **exactly one** location, to avoid confusion when observing output. The advice uses `execution` to intercept the method and then looks up the annotation in the precedence order above.

Directory structure:

~~~text
pom.xml
src/main/java/com/example/annotationdemo/
    DemoApplication.java
    Tracked.java
    Services.java
    TrackedAspect.java
~~~

### 4.1. Dependencies

`pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-annotation-aop</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-aop` provides Spring AOP along with the AspectJ components needed for Spring to parse pointcut expressions. The example does not use AspectJ compile-time weaving.

### 4.2. Annotation Storing Metadata Only

`src/main/java/com/example/annotationdemo/Tracked.java`:

~~~java
package com.example.annotationdemo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
public @interface Tracked {
    String value();
}
~~~

This annotation does not make advice run by itself. Spring must have a registered aspect and a pointcut matching calls through a proxy for the metadata to be used.

### 4.3. Four Interfaces and Four Services

`src/main/java/com/example/annotationdemo/Services.java`:

~~~java
package com.example.annotationdemo;

import org.springframework.stereotype.Service;

// Case 1: annotation on interface method
interface InterfaceMethodPort {
    @Tracked("interface-method")
    String execute();
}

@Service
class InterfaceMethodService implements InterfaceMethodPort {
    @Override
    public String execute() {
        return "A";
    }
}

// Case 2: annotation on implementation method
interface ImplementationMethodPort {
    String execute();
}

@Service
class ImplementationMethodService implements ImplementationMethodPort {
    @Override
    @Tracked("implementation-method")
    public String execute() {
        return "B";
    }
}

// Case 3: annotation on implementation class
interface ClassLevelPort {
    String execute();
}

@Service
@Tracked("implementation-class")
class ClassLevelService implements ClassLevelPort {
    @Override
    public String execute() {
        return "C";
    }
}

// Case 4: annotation on interface type
@Tracked("interface-type")
interface InterfaceTypePort {
    String execute();
}

@Service
class InterfaceTypeService implements InterfaceTypePort {
    @Override
    public String execute() {
        return "D";
    }
}
~~~

The interfaces and classes in this file have package-private visibility because the demo application and aspect share the same package. All `execute()` implementation methods are `public`, non-`final`; each bean has a single interface. Spring manages the services via `@Service`, so calls receiving beans through dependency injection can go through a Spring AOP proxy.

### 4.4. Aspect Looking Up Metadata Across Four Locations

`src/main/java/com/example/annotationdemo/TrackedAspect.java`:

~~~java
package com.example.annotationdemo;

import java.lang.reflect.Method;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.aop.support.AopUtils;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TrackedAspect {

    @Around("execution(public * com.example.annotationdemo..*.execute(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        MethodSignature signature = (MethodSignature) pjp.getSignature();
        Class<?> targetClass = pjp.getTarget().getClass();

        Method implementationMethod =
                AopUtils.getMostSpecificMethod(signature.getMethod(), targetClass);

        Tracked annotation = resolve(implementationMethod, targetClass);

        if (annotation != null) {
            System.out.println("tracked=" + annotation.value());
        }

        return pjp.proceed();
    }

    private Tracked resolve(Method method, Class<?> targetClass) {
        // 1. Annotation declared directly on the implementation method
        Tracked found = method.getDeclaredAnnotation(Tracked.class);
        if (found != null) {
            return found;
        }

        // 2. Annotation on the corresponding method of a direct interface
        for (Class<?> contract : targetClass.getInterfaces()) {
            try {
                Method interfaceMethod = contract.getMethod(
                        method.getName(), method.getParameterTypes());

                found = interfaceMethod.getDeclaredAnnotation(Tracked.class);
                if (found != null) {
                    return found;
                }
            } catch (NoSuchMethodException ignored) {
                // This interface does not declare/inherit the corresponding method.
            }
        }

        // 3. Annotation declared directly on the implementation class
        found = targetClass.getDeclaredAnnotation(Tracked.class);
        if (found != null) {
            return found;
        }

        // 4. Annotation declared directly on the interface type
        for (Class<?> contract : targetClass.getInterfaces()) {
            found = contract.getDeclaredAnnotation(Tracked.class);
            if (found != null) {
                return found;
            }
        }

        return null;
    }
}
~~~

**Why use `execution`?** The expression `execution(public * com.example.annotationdemo..*.execute(..))` catches public methods named `execute` in the demo package (or subpackages), without requiring Spring to find `@Tracked` in one fixed spot during pointcut matching. Inside the advice, the resolver decides which annotation applies.

**Why resolve `implementationMethod`?** When called via a JDK proxy, `signature.getMethod()` may be the interface method, which lacks annotations placed exclusively on the implementation method. `AopUtils.getMostSpecificMethod(...)` resolves the corresponding concrete method on the target class to accurately read annotations declared there.

This is an **intentionally scoped resolver**: it handles direct interfaces, non-generic/non-bridge methods, and one annotation per location. For multi-level interface hierarchies, generic bridge methods, meta-annotations, or multiple interfaces declaring the same signature, use an explicit policy and suitable APIs like `BridgeMethodResolver`/`AnnotatedElementUtils`. Do not turn a minimal example into a universal lookup mechanism for all Spring annotations.

### 4.5. Running and Reading Output

`src/main/java/com/example/annotationdemo/DemoApplication.java`:

~~~java
package com.example.annotationdemo;

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
    CommandLineRunner examples(
            InterfaceMethodPort fromInterfaceMethod,
            ImplementationMethodPort fromImplementationMethod,
            ClassLevelPort fromClass,
            InterfaceTypePort fromInterfaceType) {

        return args -> {
            System.out.println("== Interface method ==");
            System.out.println("result=" + fromInterfaceMethod.execute());

            System.out.println("== Implementation method ==");
            System.out.println("result=" + fromImplementationMethod.execute());

            System.out.println("== Implementation class ==");
            System.out.println("result=" + fromClass.execute());

            System.out.println("== Interface type ==");
            System.out.println("result=" + fromInterfaceType.execute());
        };
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Ignoring Spring Boot startup logs, the demo output is:

~~~text
== Interface method ==
tracked=interface-method
result=A
== Implementation method ==
tracked=implementation-method
result=B
== Implementation class ==
tracked=implementation-class
result=C
== Interface type ==
tracked=interface-type
result=D
~~~

Each call to `execute()` through the proxy enters the advice once. The resolver knows how to look up annotations across all four locations in the defined order, so the `tracked=...` lines appear accordingly. `proceed()` still returns the exact strings `A`, `B`, `C`, `D` from the services.

To test JDK proxies in Spring Boot, run again with the following property (or put it in `application.properties`):

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--spring.aop.proxy-target-class=false
~~~

All demo beans have interfaces, so interface-based proxies can be used. Because `CommandLineRunner` receives dependencies by **interface**, and the aspect uses `execution` and resolves the annotation from the target itself, **the business output lines above are still expected to be identical**. To inspect the exact proxy type, checks using `AopUtils.isJdkDynamicProxy(...)` or `AopUtils.isCglibProxy(...)` can be added in the runner. Do not force injecting concrete classes when JDK proxies are selected: a JDK proxy is not a subclass of the implementation.

## 5. What If Annotations Appear in Multiple Locations Simultaneously?

Consider the case where the interface method has `@Tracked("contract")`, the implementation method has `@Tracked("implementation")`, and the implementation class has `@Tracked("service-default")`.

With the resolver in section 4, the result is `tracked=implementation` because the implementation method is checked first. Removing the annotation on the implementation method causes the resolver to return `contract`; removing the annotation on the interface method as well returns `service-default`.

This is **this example's own precedence policy**, which can be changed to fit system requirements. Another policy might prioritize the implementation class annotation over the interface method to apply a default across the entire service. Whatever is chosen, write tests clearly describing the order because there is no single universal precedence table for all Spring AOP annotations.

Do not arbitrarily combine two conflicting configurations (e.g., `@Tracked(value="fast")` on the interface and `@Tracked(value="slow")` on the implementation) without a conflict policy. A production resolver can reject ambiguous configurations at startup, helping catch contract changes early.

## 6. Differences Between Custom `@Aspect` and Built-in Spring Annotations

A classic example is `@Transactional`. Spring has `TransactionAttributeSource` to find transaction metadata on methods and classes, including cases where interface methods are supported in **proxy mode**. That is behavior of the **transaction infrastructure**, not because Java annotations are automatically inherited or because every `@annotation` pointcut automatically uses such a resolver.

When designing your own annotation, separate two steps:

- **Join point selection step:** the pointcut determines which calls can run the advice.
- **Metadata selection step:** resolver logic determines which annotation is read, which location takes precedence, and how conflicts are handled.

In a simple application that only accepts annotations on implementation methods, `@annotation(com.example.annotationdemo.Tracked)` can be cleaner. If the API contract requires annotations on interfaces **and** supports switching between JDK/CGLIB proxies, do not rely on a single reflection call on `MethodSignature.getMethod()`; test the exact desired cases.

For meta-annotations/composed annotations (e.g., an `@AuditedCommand` marked with `@Tracked`), `getDeclaredAnnotation(Tracked.class)` will not handle the full Spring merged annotations model. In that case `AnnotatedElementUtils.findMergedAnnotation(...)` or `MergedAnnotations` can be used, while actively defining the order among method, type, and interface instead of assuming those two APIs replace the entire resolver.

## 7. Common Pitfalls and How to Verify

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `@Tracked` placed on interface method yet no advice runs | Pointcut does not match at the method execution seen by the proxy, or call does not go through proxy | Verify AOP is enabled, proxy exists, and pointcut matches; test with a clearly scoped `execution` expression |
| Advice runs yet cannot find annotation on implementation method | Only reading the interface method from `MethodSignature` | Resolve the most-specific method on the target class first |
| Class annotation absent on method | Class annotation does not mean the method has a direct annotation | Check the class separately; choose `@target`/`@within` or a resolver depending on the goal |
| Interface type marked yet target class lacks annotation | Java does not inherit annotations from interfaces to classes | Check interface types if required by policy |
| Advice runs under JDK proxy yet disappears when switching proxy config | Pointcut, visibility, exposed methods, and metadata sources differ | Test both modes, check public/interface methods |
| Inner method has annotation yet is not intercepted | `this.inner()` calls directly within the same target | Extract to another bean so the call goes through a proxy |
| Used `@Inherited` yet interface method is still unrecognized | `@Inherited` does not apply to methods or interface inheritance | Look up interface methods explicitly |
| Multiple interfaces produce inheritance-dependent results | Resolver lacks a conflict policy | Declare precedence or fail-fast; test interface hierarchies |
| Annotation placed on `private`/`final` method yet no advice runs | Proxy cannot intercept the corresponding method | Use public methods through proxy, or change design appropriately |

To verify instead of guessing: fetch the bean from `ApplicationContext`, check with `AopUtils.isAopProxy(bean)`, distinguish JDK/CGLIB, confirm the public method is called **from another bean**, then check whether the pointcut matches and the resolver looks in the exact location where the annotation is placed.

## 8. Checklist When Introducing Custom Annotations to a Project

1. Clearly define `@Target`, `@Retention(RUNTIME)`, annotation name, and data; specify which placement is the public contract.
2. Specify whether the annotation is allowed on interface methods, implementation methods, classes, and/or interface types.
3. Choose `@annotation`, `@within`, or `@target` if a single location satisfies the requirement; if a multi-location merge policy is needed, narrow with `execution` and use a tested resolver.
4. Define precedence and handling for multiple interfaces, method overloads, generic bridges, inheritance, and composed annotations.
5. Verify call paths through the proxy under all supported JDK/class-based configurations; avoid self-invocation and non-interceptable methods.
6. Verify advice preserves the return value/exceptions of `proceed()`, without creating heavy reflection overhead on hot paths. Metadata lookup results can be cached per method + target class, after ensuring the cache key accurately reflects the policy.
7. If the annotation affects authorization, transactions, or business guarantees, write integration tests for matching and non-matching cases; do not treat demo logs as sufficient proof of policy enforcement.

## 9. Conclusion

In Spring AOP, annotation placement and call routing through a proxy are two separate decisions. **Annotations on interfaces do not automatically become annotations on implementations**, and `@annotation`, `@within`, and `@target` have different matching semantics. When simultaneous support for interface methods, implementation methods, implementation classes, and interface types is needed, define an explicit metadata lookup policy, use a pointcut broad enough to cover permitted calls, and verify against the real proxy.

Official references:
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
