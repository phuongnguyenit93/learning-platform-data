# Composed Annotations in Spring and Pointcut Matching Limits to Verify

## 1. The Practical Problem in Spring AOP

When building custom annotations for logging, auditing, or access control, a Spring project often wants to declare high-level annotations that are intuitive to the business domain. For example, `@BusinessTraced` is built on top of `@Traced`, and then attached to service methods to receive the same tracing behavior.

A common point of confusion is that **Spring being able to read a meta-annotation does not mean every Spring AOP pointcut automatically matches that meta-annotation**. Two mechanisms are related yet distinct:

1. **Spring's composed annotation model**: `MergedAnnotations` and `AnnotatedElementUtils` can find direct annotations, meta-annotations, and merge attributes, including values declared via `@AliasFor`.
2. **`@AspectJ`-style pointcut matching**: `@annotation(com.example.Traced)` uses the annotation matching rules of the AspectJ pointcut language, and does not automatically apply all of Spring's meta-annotation search rules.
3. **Spring's programmatic pointcut**: `AnnotationMatchingPointcut` has a `checkInherited=true` option to additionally inspect annotations on superclasses, interfaces, and meta-annotations according to its matcher mechanism.

This lesson examines only **Spring Framework / Spring AOP**: annotation design on Spring beans, advice matching limits, and how to write tests to verify real behavior. It does not expand into standalone AspectJ weaving knowledge beyond this scope.

### Objectives

- Declare `@Traced` and the composed annotation `@BusinessTraced` with proper `@Target`, `@Retention`, and `@AliasFor`.
- Understand the difference between **an annotation being found** and **a call actually being intercepted by a Spring AOP proxy**.
- Write tests proving that direct annotations, composed annotations, and unmarked methods behave differently.
- Know how to choose a solution when supporting composed annotations without causing pointcuts to accidentally match unintended methods.
- Identify other limits to verify: JDK proxy/CGLIB, annotations on interfaces, self-invocation, method scope, and class-level annotations.

## 2. How Does Spring Recognize Composed Annotations?

A meta-annotation is an annotation placed **on the declaration of another annotation**. For example:

~~~java
@Target({ElementType.METHOD, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface Traced {
    String label() default "default";
}

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Traced
public @interface BusinessTraced {
    @AliasFor(annotation = Traced.class, attribute = "label")
    String label() default "default";
}
~~~

These are **two illustrative declarations**; to put them into a project they must be placed in `Traced.java` and `BusinessTraced.java`, with imports for `java.lang.annotation.*` and `org.springframework.core.annotation.AliasFor`. Section 4 provides a complete single-file Java test.

Meaningful conditions:

- `Traced` must permit `ElementType.ANNOTATION_TYPE` before it can be used as a meta-annotation for `BusinessTraced`.
- `BusinessTraced` permits `ElementType.METHOD` because the task marks methods on Spring beans.
- `RetentionPolicy.RUNTIME` lets reflection/Spring APIs read metadata at runtime.
- `@AliasFor(annotation = Traced.class, attribute = "label")` declares that the `label` attribute of the composed annotation overrides the `label` attribute of the base annotation in **Spring's merged annotations model**. It **does not** automatically alter AspectJ's `@annotation` matching semantics.
- The types of the two attributes must be compatible, and their corresponding default values must agree; do not set two conflicting values expecting Spring to pick one automatically.

When writing:

~~~java
@BusinessTraced(label = "checkout")
public void checkout() {
    // business logic
}
~~~

Standard Java reflection using **direct** lookup `checkoutMethod.getAnnotation(Traced.class)` does not see `@Traced` on the method itself. Spring can retrieve `Traced` along the meta-annotation branch:

~~~java
Method method = CheckoutService.class.getMethod("checkout");

Traced direct = method.getAnnotation(Traced.class);
Traced merged = AnnotatedElementUtils.findMergedAnnotation(method, Traced.class);

System.out.println(direct == null);
System.out.println(merged.label());
~~~

Here `CheckoutService` is the class containing the `checkout` method in the immediately preceding example, requiring imports for `java.lang.reflect.Method` and `org.springframework.core.annotation.AnnotatedElementUtils`. If both annotations are declared properly, the two printed lines are respectively:

~~~text
true
checkout
~~~

That is proof that Spring **can read the metadata**. It does not yet prove that a `@Before`, `@Around`, or `@AfterReturning` advice runs.

### Where Spring Uses This Mechanism

Spring has many specialized mechanisms that handle composed annotations, such as stereotypes based on `@Component`, mappings in Spring MVC, or certain annotation-driven transaction/caching features. **Do not generalize from their behavior to every custom pointcut**: each subsystem has its own matcher and annotation search strategy.

## 3. Distinguishing Spring AOP Matching Points

In proxy-based AOP mode, Spring intercepts **method executions on beans through proxies**. Related pointcut forms:

| Syntax | Subject Matched | What Not to Infer |
| --- | --- | --- |
| `@annotation(demo.Traced)` | Annotation on the method at the join point | Does not automatically equate to `MergedAnnotations` meta-annotation lookup |
| `@within(demo.ServiceTag)` | Annotation on the type containing the matched method | Not `@annotation` on each individual method |
| `@target(demo.ServiceTag)` | Annotation on the class of the runtime target | Not a drop-in replacement for all interface annotation cases |
| `execution(public * demo.CatalogueService.*(..))` | Signature and scope of method execution | Matches methods whether or not they have `@Traced` |

Below is an example with a **method annotation**:

~~~java
@Aspect
public class DirectTraceAspect {
    @Before("@annotation(demo.Traced)")
    public void record(JoinPoint joinPoint) {
        System.out.println(joinPoint.getSignature().getName());
    }
}
~~~

The aspect above requires `demo.Traced` per AspectJ `@annotation` syntax. **Do not assume by default** that a method marked only with `@BusinessTraced` will enter the advice, even though Spring `findMergedAnnotation` recognizes `Traced` on that method. For many kinds of composed annotations, the actual outcome in Spring AOP is that the direct method is intercepted while the composed method is skipped. Prove it with tests on the **exact Spring version and proxy configuration of your project**.

> Note: `@AliasFor` resolves how Spring merges attribute values. It does not add an alternative pointcut expression to advice.

## 4. JUnit 5 Test: Valid Metadata Yet Pointcut May Skip

This example tests three independent questions:

1. Does `MergedAnnotations` see the base annotation through `@BusinessTraced` and read the overridden `label` value?
2. Is `@Before("@annotation(demo.Traced)")` advice actually invoked for directly marked methods, composed-annotated methods, and plain methods?
3. Does an `AnnotationMatchingPointcut` with `checkInherited=true` allow matching both direct and composed annotations?

### Dependencies

For a Spring Boot 3.x application using Gradle Groovy DSL that already includes the Spring Boot plugin and BOM/dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

For a plain Spring Framework project, `spring-aop`, `spring-context` when integrating beans, `aspectjweaver` for pointcut expressions, and JUnit Jupiter for testing are required; versions must be compatible and explicitly managed. `AspectJProxyFactory` and `ProxyFactory` in the example below are real Spring AOP, even though the test does not run an HTTP server.

### Complete Test File

Create `src/test/java/demo/ComposedAnnotationPointcutTest.java`:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

import org.aopalliance.intercept.MethodInterceptor;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.junit.jupiter.api.Test;
import org.springframework.aop.aspectj.annotation.AspectJProxyFactory;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.DefaultPointcutAdvisor;
import org.springframework.aop.support.annotation.AnnotationMatchingPointcut;
import org.springframework.core.annotation.AliasFor;
import org.springframework.core.annotation.AnnotatedElementUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

@Target({ElementType.METHOD, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@interface Traced {
    String label() default "default";
}

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Traced
@interface BusinessTraced {
    @AliasFor(annotation = Traced.class, attribute = "label")
    String label() default "default";
}

class CatalogueService {
    @Traced(label = "direct")
    public String direct() {
        return "direct";
    }

    @BusinessTraced(label = "business")
    public String composed() {
        return "composed";
    }

    public String plain() {
        return "plain";
    }
}

@Aspect
class DirectAnnotationAspect {
    final List<String> invoked = new ArrayList<>();

    @Before("@annotation(demo.Traced)")
    public void before(JoinPoint joinPoint) {
        invoked.add(joinPoint.getSignature().getName());
    }
}

public class ComposedAnnotationPointcutTest {

    @Test
    void springCanReadAComposedAnnotation() throws Exception {
        Method method = CatalogueService.class.getMethod("composed");

        // Direct Java reflection does not see @Traced on the method.
        assertNull(method.getAnnotation(Traced.class));

        // Spring traverses @BusinessTraced -> @Traced and merges @AliasFor.
        Traced merged =
                AnnotatedElementUtils.findMergedAnnotation(method, Traced.class);
        assertNotNull(merged);
        assertEquals("business", merged.label());
    }

    @Test
    void aspectJStyleAnnotationPointcutOnlyRecordsDirectAnnotation() {
        DirectAnnotationAspect aspect = new DirectAnnotationAspect();
        AspectJProxyFactory factory = new AspectJProxyFactory(new CatalogueService());
        factory.addAspect(aspect);
        CatalogueService service = factory.getProxy();

        assertEquals("direct", service.direct());
        assertEquals("composed", service.composed());
        assertEquals("plain", service.plain());

        // Key point: the test measures advice actually running through the Spring proxy.
        assertEquals(List.of("direct"), aspect.invoked);
    }

    @Test
    void springAnnotationPointcutCanInspectMetaAnnotations() {
        List<String> intercepted = new ArrayList<>();
        ProxyFactory factory = new ProxyFactory(new CatalogueService());

        AnnotationMatchingPointcut pointcut =
                new AnnotationMatchingPointcut(null, Traced.class, true);

        factory.addAdvisor(new DefaultPointcutAdvisor(
                pointcut,
                (MethodInterceptor) invocation -> {
                    intercepted.add(invocation.getMethod().getName());
                    return invocation.proceed();
                }));

        CatalogueService service = (CatalogueService) factory.getProxy();
        assertEquals("direct", service.direct());
        assertEquals("composed", service.composed());
        assertEquals("plain", service.plain());

        assertEquals(List.of("direct", "composed"), intercepted);
    }
}
~~~

Run this test alone:

~~~bash
./gradlew test --tests demo.ComposedAnnotationPointcutTest
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests demo.ComposedAnnotationPointcutTest
~~~

**Test expectations:**

| Test | Verified Conclusion |
| --- | --- |
| `springCanReadAComposedAnnotation` | Direct reflection does not see `Traced`; Spring finds the meta-annotation and the `business` label |
| `aspectJStyleAnnotationPointcutOnlyRecordsDirectAnnotation` | With the described Spring AOP/AspectJ-style pointcut, advice only records `direct` |
| `springAnnotationPointcutCanInspectMetaAnnotations` | With `checkInherited=true`, the advisor catches `direct` and `composed`, skipping `plain` |

Nothing is printed to stdout in this test suite; when passing, Gradle reports the test task succeeded according to the environment's format. If matching assertions do not match your Spring stack, investigate the version and created proxy; **do not modify assertions just to turn a test green**. This example uses a class-based proxy for a class declaring no interfaces, with all methods public and non-final, helping focus on annotation semantics.

**This is a test of Spring AOP behavior**, not merely a reflection test. Ensure `AspectJProxyFactory` actually creates a proxy and applies the aspect. In a real application, add an `ApplicationContext` test to confirm auto-proxying and corresponding bean wiring.

## 5. When You Want Composed Annotations Intercepted, Which Approach to Choose?

### 5.1. Simple Solution: Declare Annotations Explicitly in the Pointcut

If the number of composed annotations is small and controlled:

~~~java
@Before("@annotation(demo.Traced) || @annotation(demo.BusinessTraced)")
public void before(JoinPoint joinPoint) {
    // Track calls marked with either annotation.
}
~~~

Pros: explicit, easy to understand, and simple in some projects. Cons: every new composed annotation must be added to the expression and tested; not a mechanism for finding arbitrary-depth meta-annotations.

### 5.2. Use a Spring Programmatic Advisor Supporting Meta-Annotation Lookup

In section 4's test, `AnnotationMatchingPointcut(null, Traced.class, true)` inspects metadata at the method level while enabling Spring's inherited/meta-annotation support. Combining `DefaultPointcutAdvisor` with `MethodInterceptor` can organize advice without writing `@Before("@annotation(...)")` for every child annotation.

In a Spring-managed application, an `Advisor` bean can be registered in the context instead of manually creating a `ProxyFactory` for each object. Example **configuration skeleton**:

~~~java
@Configuration
class TraceAdvisorConfig {
    @Bean
    Advisor traceAdvisor(TraceInterceptor traceInterceptor) {
        return new DefaultPointcutAdvisor(
                new AnnotationMatchingPointcut(null, Traced.class, true),
                traceInterceptor);
    }
}
~~~

In this snippet, `TraceInterceptor` is an application class implementing `MethodInterceptor`; `Advisor`, `@Configuration`, `@Bean`, and related types must be imported. This is an **integration skeleton**, not a standalone runnable file. When applying it, verify whether `BeanFactory` actually attaches the advisor to target beans and note advisor ordering when transactions, security, and caching are present.

### 5.3. Use a Narrow-Enough Pointcut and Read Merged Annotations Inside Advice

If an existing `@Aspect` advice is needed and the list of composed annotations changes frequently, an `execution(...)` expression can match the **selected service scope**, then look up merged annotations inside the advice:

~~~java
@Around("execution(public * demo.CatalogueService.*(..))")
public Object around(ProceedingJoinPoint pjp) throws Throwable {
    Method signatureMethod = ((MethodSignature) pjp.getSignature()).getMethod();
    Method targetMethod = AopUtils.getMostSpecificMethod(
            signatureMethod, pjp.getTarget().getClass());

    Traced traced = AnnotatedElementUtils.findMergedAnnotation(
            targetMethod, Traced.class);
    if (traced == null) {
        return pjp.proceed();
    }

    recordTrace(traced.label()); // application tracing integration
    return pjp.proceed();
}
~~~

This is an **illustrative code snippet** inside an `@Aspect`, requiring imports:
`org.aspectj.lang.ProceedingJoinPoint`, `org.aspectj.lang.annotation.Around`,
`org.aspectj.lang.reflect.MethodSignature`, `java.lang.reflect.Method`,
`org.springframework.aop.support.AopUtils`, and
`org.springframework.core.annotation.AnnotatedElementUtils`.

Pros: decisions rely directly on the merged annotations model; the `label` attribute can be retrieved immediately. Cons: the proxy/pointcut may intercept more methods than need tracing, increasing overhead. Narrow `execution` by package, type, or specific method signatures, handle interface annotations per project policy, and test the null case. This approach also does not solve self-invocation by itself.

### Selection Criteria

| Need | Suitable Approach |
| --- | --- |
| Few annotations, stable names | Combined pointcut `@annotation(A) || @annotation(B)` and test both |
| Want Spring to find meta-annotations at pointcut level | `AnnotationMatchingPointcut` with explicitly configured `checkInherited` |
| Need `@AliasFor` merged values and dynamic selection logic | Narrow scope match, use `AnnotatedElementUtils` inside advice |
| Need support for non-Spring beans or internal method calls | Different design beyond Spring proxy AOP limits; cannot just tweak `@annotation` |

## 6. Boundaries to Verify in a Real Project

**1. Annotation placed on method or class?** `@annotation` only refers to method annotations. If you want to mark an entire class, design an annotation with appropriate `@Target(TYPE)` and use the right pointcut (`@within`/`@target`) or class annotation matcher; do not put a method annotation on a class expecting it to match automatically.

**2. Annotations on interfaces, overridden methods, and implementations:** JDK proxies view through interfaces; class-based proxies work with the concrete class. An annotation may be placed on an interface method without being redeclared on the implementation. Method resolution order and metadata lookup strategies can yield different results. Tests must compare **actual proxy, implementation method, and interface method**. Java's `@Inherited` applies to type inheritance under specific rules; it does not mean method annotations are automatically inherited in all cases.

**3. Proxy must actually be invoked:** self-invocation (one method in the target calling another method on the same target directly), instantiating objects with `new` outside Spring, final/private methods, or wrong proxy configuration can prevent advice from running. A test that merely calls `new CatalogueService().composed()` will not prove Spring AOP works.

**4. Advisor ordering and conditions:** when a service has transactions, caching, or authorization, advice ordering can alter logging timing. A `@Transactional` composite annotation recognized by Spring's transaction infrastructure does not prove `@Around("@annotation(Transactional)")` catches it identically.

**5. Annotations and attribute values:** `@AliasFor` is only applied by Spring when the annotation is read through merge-supporting APIs. Plain Java reflection does not enforce alias rules. Verify the actual received value, default cases, and invalid/conflicting alias configurations.

**6. For reactive applications:** Spring AOP intercepts method calls returning `Mono`/`Flux`; advice runs when the method returns the publisher, which differs from when the publisher emits signals. When writing tracing for Reactor, test on subscription/signal/context via the proper mechanism. This is a boundary of Spring Aspects, not evidence that an annotation pointcut automatically handles the entire reactive chain.

## 7. Recommended Test Matrix

| Case | Input Configuration | What to Assert |
| --- | --- | --- |
| Method marked directly with `@Traced` | Proxy calls `direct()` | Advice runs exactly once |
| Method marked with `@BusinessTraced` | Proxy calls `composed()` | Confirm matching per **chosen approach**; `MergedAnnotations` returns overridden label |
| Unmarked method | Proxy calls `plain()` | No tracing side effects |
| Annotation on interface method | JDK proxy and class-based proxy | No reliance on vague assumptions about annotation placement |
| Annotation on class | Use `TYPE` annotation, choose `@within`/`@target` or class matcher | Confirm type level differs from method level |
| Methods calling each other internally | `outer()` calls `inner()` on same target | Advice counted only on calls that actually go through the proxy |
| Multi-level composed annotation | `@Feature` -> `@BusinessTraced` -> `@Traced` | Merged API receives right value; test pointcut separately, do not guess |
| Invalid or conflicting alias | Invalid annotation configuration | Test proves the configuration is detected, not silently using a wrong label |

A dedicated `@SpringBootTest` can be organized on real beans: call through the injected bean, assert `AopUtils.isAopProxy(bean)`, and observe an independent recorder to confirm advice ran. When using the same test matrix for JDK proxy/CGLIB, declare interfaces if needed and set `proxyTargetClass` explicitly.

## 8. Common Errors and Diagnostics

- **Annotation found by `findMergedAnnotation` yet advice does not run:** check the `@annotation` pointcut expression, proxy, annotation placement, and whether the meta-annotation is listed or the matcher has `checkInherited`.
- **Advice runs yet label value remains default:** check `@AliasFor`, `@Retention(RUNTIME)`, how the annotation is read via reflection/merged APIs, and conflicting default values.
- **`@annotation` on class does not match:** it targets methods; distinguish from `@within` and `@target`.
- **Annotation on interface works in one test yet breaks in another:** identify the proxy type and the actual resolved method; do not assume implementations always carry interface annotations.
- **Test passes even though advice was skipped:** only asserted business return values without recording advice invocations; add a counter/recorder so tests fail when the pointcut does not match.
- **Broadening scope to `execution(* *(..))` as a quick fix:** can cause too many beans/methods to be proxied and enter advice; choose the right scope and run performance or integration tests when expanding.
- **Using `@AliasFor` as a pointcut expansion tool:** aliases only resolve merged metadata; they do not rewrite AspectJ expressions.

## 9. Adoption Checklist

1. Document whether the base and composed annotations are placed on **methods** or **types**, and whether they have `RUNTIME` retention.
2. Decide explicitly on the **pointcut matching engine**: AspectJ-style `@annotation` or Spring `AnnotationMatchingPointcut`/custom advisor.
3. Create at least three sample methods: directly marked, composite-marked, and unmarked; assert **advice invocation** for each method.
4. Test `MergedAnnotations`/`AnnotatedElementUtils` independently from proxy tests to tell whether an issue lies in metadata or matching.
5. Test interface/class proxies, overrides, and self-invocation when the application structure includes those cases.
6. Verify labels/attributes from `@AliasFor`, both custom and default values.
7. Keep pointcut scope narrow enough, avoiding intercepting the entire application only to filter metadata manually afterward.

**Completion criteria:** The team has tests clearly showing which methods are intercepted by Spring AOP advice, which methods are only recognized by Spring annotation APIs, and that composed annotation support is a design decision verified by tests.

## Reference Documentation

- Spring Framework — Declaring a Pointcut: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Spring Framework — `AliasFor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/core/annotation/AliasFor.html
- Spring Framework — `AnnotationMatchingPointcut` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/aop/support/annotation/AnnotationMatchingPointcut.html
- Spring Framework — `MergedAnnotations` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/core/annotation/MergedAnnotations.html
