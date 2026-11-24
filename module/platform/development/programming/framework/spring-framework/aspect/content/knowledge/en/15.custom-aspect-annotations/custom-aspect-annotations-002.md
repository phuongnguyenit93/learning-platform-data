# Choosing the Right `@Target` and `@Retention` for Annotations Used with Spring AOP

## 1. Purpose

When building a custom annotation to trigger a **Spring AOP** advice, two Java meta-annotations are especially important:

- `@Target` specifies **where the annotation is allowed to be declared** in source code, such as on a method or a class.
- `@Retention` specifies **until which stage the annotation is retained**. Spring AOP advice runs in the JVM, so a marker that Spring/AOP must look up at runtime normally needs `RetentionPolicy.RUNTIME`.

This choice directly relates to Spring pointcuts such as `@annotation`, `@within`, and `@target`, to how Spring reads metadata via reflection/merged-annotation APIs, and to proxy boundaries. This is a guide to **Aspects in Spring**, not a standalone overview of AspectJ weaving.

## 2. Choosing `@Target` Based on Marker Placement

| Design Approach | Suitable Declaration | How Advice Is Typically Applied |
| --- | --- | --- |
| Mark a business method | `@Target(ElementType.METHOD)` | `@annotation(...)` for method executions intercepted by a Spring AOP proxy |
| Mark an entire service class | `@Target(ElementType.TYPE)` | `@within(...)` or `@target(...)` with corresponding semantics; verify target/proxy types |
| Allow on both methods and classes | `@Target({ElementType.METHOD, ElementType.TYPE})` | Design two explicit pointcut branches; do not assume a single `@annotation` will catch class annotations |
| Mark another annotation to create a composed annotation | `@Target(ElementType.ANNOTATION_TYPE)` or add required targets | Spring metadata APIs can support merged annotations; AspectJ pointcut matching has specific limits that must be tested |

`ElementType.PARAMETER` marks parameters declared in a method, and does not make `@annotation` automatically match a method execution. `ElementType.TYPE_USE` or `TYPE_PARAMETER` also does not turn Spring AOP into a pointcut matching type-use. Standard Spring AOP focuses on **method-execution join points through proxies**.

### Annotation Used on Methods

~~~java
package demo;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Audited {
    String event() default "operation";
}
~~~

Used on a Spring-managed method:

~~~java
@Service
class OrderService {
    @Audited(event = "place-order")
    public String place(String orderId) {
        return "accepted:" + orderId;
    }
}
~~~

If `@Target(TYPE)` is used yet placed on a method, the Java compiler reports an error at the declaration site. If `@Target(METHOD)` is used yet placed on a class, the compiler also rejects it; this is the benefit of a clear metadata contract.

### Annotation Used on Classes

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface MonitoredService {}
~~~

~~~java
@MonitoredService
@Service
class PaymentService {
    public String pay() { return "paid"; }
}
~~~

An `@annotation(demo.MonitoredService)` only checks annotations on methods and is not the right choice to filter class markers. Actively choose `@within`/`@target` based on the target type, static/runtime pointcut semantics, and proxy behavior.

## 3. Choosing `@Retention`: SOURCE, CLASS, or RUNTIME?

| Policy | Present in Bytecode? | Queryable via Reflection at Runtime? | Suitable for Runtime Spring AOP Markers? |
| --- | --- | --- | --- |
| `RetentionPolicy.SOURCE` | Usually discarded by the compiler when generating the class | No | No |
| `RetentionPolicy.CLASS` | Present in the class file | Does not appear through standard runtime reflection | No |
| `RetentionPolicy.RUNTIME` | Yes | Yes | **Yes, when the corresponding pointcut/proxy matches** |

If `@Retention` is omitted, Java's default is `RetentionPolicy.CLASS`. Therefore, markers without an explicit retention definition often lead to the symptom "annotation is visible in source code, yet advice does not run". For Spring to read the annotation from `AnnotatedElement` in the JVM, the standard choice is `RUNTIME`.

`RUNTIME` is a **necessary condition**, not a sufficient one. Advice also depends on:

1. Having an `@Aspect` bean recognized by Spring and `@EnableAspectJAutoProxy`/Boot AOP infrastructure configured.
2. The pointcut matching the right annotation type and the right method/class being checked.
3. The method call going through the Spring AOP proxy; `this.someMethod()` inside the target bypasses the proxy.
4. JDK dynamic proxies and CGLIB class-based proxies differing in method/interface structure and which methods can be intercepted.
5. Specifying the right pointcut if the annotation is on an interface vs. implementation; testing the actual proxy strategy.

## 4. Runnable Spring Example, Java 17 + Maven

Project structure:

~~~text
spring-aop-marker-meta/
  pom.xml
  src/main/java/demo/Audited.java
  src/main/java/demo/OrderService.java
  src/main/java/demo/AuditAspect.java
  src/main/java/demo/Application.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-aop-marker-meta</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.19</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-aop</artifactId>
      <version>6.2.19</version>
    </dependency>
    <dependency>
      <groupId>org.aspectj</groupId>
      <artifactId>aspectjweaver</artifactId>
      <version>1.9.25</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration><release>17</release></configuration>
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

**Audited.java**

~~~java
package demo;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Audited {
    String event() default "operation";
}
~~~

`@Documented` lets Javadoc include the marker in API documentation; it does not make Spring AOP match more broadly.

**OrderService.java**

~~~java
package demo;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    @Audited(event = "placed")
    public String place(String id) {
        return "accepted:" + id;
    }

    public String status() {
        return "ready";
    }
}
~~~

**AuditAspect.java**

~~~java
package demo;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class AuditAspect {
    @Before("@annotation(audited)")
    public void audit(Audited audited) {
        System.out.println("audit:" + audited.event());
    }
}
~~~

The aspect uses `@annotation(audited)` to bind the actual marker into the `audited` parameter. `argNames` can be used when compilation does not preserve parameter name information as desired; in this single annotation-typed argument example Spring AOP/AspectJ usually infers the binding, but for multi-parameter projects it should be declared explicitly.

**Application.java**

~~~java
package demo;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan("demo")
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class Application {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Application.class)) {
            OrderService service = context.getBean(OrderService.class);
            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println(service.place("o-7"));
            System.out.println(service.status());
        }
    }
}
~~~

Run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.Application
~~~

Expected output from the application's `System.out`:

~~~text
proxy=true
audit:placed
accepted:o-7
ready
~~~

`status()` is not marked with `@Audited`, so this advice does not apply. `place()` goes through the Spring proxy, the runtime marker can match, and the annotation value is bound. This is **expected output from static inspection**, not a claim that Maven was executed on the current machine.

## 5. What If the Marker Is Declared on an Interface?

Consider two declarations:

~~~java
public interface ReportApi {
    @Audited(event = "generate")
    String generate();
}
~~~

~~~java
@Service
class ReportService implements ReportApi {
    public String generate() { return "done"; }
}
~~~

A Java annotation on an interface method **does not automatically become an annotation on the implementation method**. Java `@Inherited` only has limited effect on class-level inheritance, and does not inherit method annotations or interface annotations in the way normal Java reflection expects.

In Spring AOP, the framework and matcher may select the method reflected on the interface/proxy or the implementation method depending on the advisor/pointcut. Do not assume an annotation declared only on an interface will match identically under class-based proxies. For critical policies, the annotation is usually placed consistently on the implementation method, or a custom advisor/matcher using Spring metadata APIs is built and tested for JDK/CGLIB.

Testing should cover:

- Interface method has the marker, implementation does not.
- Implementation has the marker, interface does not.
- Annotation on the class and on the method, with separate pointcuts.
- JDK dynamic proxy versus CGLIB class proxy.
- Invocation through the Spring bean proxy versus internal `this.generate()` calls.

## 6. Meta-Annotations in Spring and Pointcut Matching Limits

Spring provides `AnnotatedElementUtils`, `MergedAnnotations`, and `AnnotationUtils` along with `@AliasFor` to read composed annotations in many framework contexts. However, the existence of a composed annotation does not mean an AspectJ-style `@annotation(SomeMarker)` pointcut automatically expands to every meta-annotated annotation.

For example:

~~~java
@Target({ElementType.METHOD, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Audited(event = "trace")
public @interface Traced {}
~~~

The pattern above is only valid when `@Audited` permits `ANNOTATION_TYPE` in `@Target`. If the demo's version of `Audited` only allows `METHOD`, the compiler rejects `@Audited` on the `@Traced` declaration. This illustrates why `@Target` must be designed according to planned usage from the start.

A composed annotation `@Traced` can be seen by Spring metadata inspection via merged lookup, while AspectJ `@annotation(demo.Audited)` still needs to be verified with integration tests. For complex meta-annotation conventions, consider a custom `StaticMethodMatcherPointcut` advisor using Spring `MergedAnnotations` and test matching explicitly.

## 7. Proxy Scope Matters More Than Annotation Declaration

Spring AOP does not weave directly into every JVM method call. Even with a valid `RUNTIME` marker, advice may still not run for any of these reasons:

~~~java
@Service
class CheckoutService {
    public void outer() {
        inner(); // self-invocation: does not call back through the Spring AOP proxy
    }

    @Audited
    public void inner() {
        // ...
    }
}
~~~

An external call to `outer()` (unmarked) that then calls `inner()` on itself will not trigger `@Before("@annotation(...")` for that inner call. Solve this through proper service structuring, separating beans and calling through a Spring proxy dependency or moving the concern to the appropriate entry point, rather than changing retention.

In addition:

- Class-based proxies normally cannot advise `final`/private methods.
- JDK proxies only expose the interface contract on the caller's reference.
- A target created with `new` outside the container will not be automatically advised by Spring.
- When using `@Async` or `@Transactional`, multiple advisors have different orders and boundaries; verify method execution through the proper proxy.
- If the annotation is used for authorization or mandatory policy enforcement, do not treat marker + pointcut as the sole protection layer: self-invocation and non-proxied calls can bypass advice.

## 8. Testing `@Target` and `@Retention` with Java Reflection

This small test works for `Audited` in the demo project:

~~~java
package demo;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

public class MetadataCheck {
    public static void main(String[] args) throws Exception {
        Class<Audited> type = Audited.class;
        Target target = type.getAnnotation(Target.class);
        Retention retention = type.getAnnotation(Retention.class);
        System.out.println("targetMethod=" +
            Arrays.asList(target.value()).contains(ElementType.METHOD));
        System.out.println("runtime=" +
            (retention.value() == RetentionPolicy.RUNTIME));
        System.out.println("markerPresent=" +
            OrderService.class.getMethod("place", String.class).isAnnotationPresent(Audited.class));
    }
}
~~~

Run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MetadataCheck
~~~

Expected output:

~~~text
targetMethod=true
runtime=true
markerPresent=true
~~~

Unlike pointcut testing, this reflection test only proves the marker exists on a specific method and is retained until runtime. It **does not replace** an integration test confirming that advice actually matches the proxy.

## 9. Common Pitfalls

**Has `@Target(METHOD)` but the annotation is placed on a class.** The Java compiler reports the annotation is not applicable to this location. Fix the target declaration to match intent, then adjust the pointcut accordingly rather than adding targets indiscriminately.

**`@Retention` is omitted, so `@annotation` does not run.** The default retention is CLASS. For Spring runtime advice, `RUNTIME` is normally used.

**Declared `@Retention(RUNTIME)` yet advice does not run.** Check Spring AOP activation, bean management, pointcut, interface/implementation annotations, final/private methods, and self-invocation.

**Added `@Inherited` expecting a method marker to propagate to implementations.** Java `@Inherited` does not resolve method/interface metadata that way; test the actual target of the Spring proxy.

**Composed annotation appears in `AnnotatedElementUtils` but does not match `@annotation`.** Spring merged metadata lookup and AspectJ pointcut matching do not use the same algorithm; integration tests and potentially a custom matcher are required.

**Placed marker on a field, constructor, or parameter expecting Spring AOP advice to intercept there.** Spring AOP is proxy-based method execution. Design a method-level annotation or use a specialized tool if the requirement is genuinely different.

## 10. Checklist for Use in a Spring Project

1. State clearly whether the marker is for a **method**, **type**, or both, and use a narrow, intentional `@Target`.
2. Choose `@Retention(RUNTIME)` for metadata that runtime advice needs to read.
3. For composed annotations, add `ANNOTATION_TYPE` if the declaration needs to act as a meta-annotation; test Spring metadata APIs and AspectJ pointcuts separately.
4. Run integration tests with a Spring proxy on the actual bean type, checking interface/implementation, JDK/CGLIB, and self-invocation.
5. Avoid mixing complex business policies into annotations; annotations should only carry clear configuration metadata for the Spring AOP concern.
6. Keep `@Documented` if needed for API docs, without treating it as a matching condition.
7. Review other advisors (`@Transactional`, `@Cacheable`, `@Async`) and verify proper application order.

## Reference Documentation

- Spring Framework Reference — Declaring a pointcut: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Spring Framework Reference — Proxying mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Reference — Advice with annotation-style aspects: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Java SE 17 API: `java.lang.annotation.Target`, `Retention`, `RetentionPolicy`, `ElementType`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/package-summary.html

**Conclusion:** For custom annotations serving Spring AOP at runtime, normally use `@Retention(RUNTIME)` and `@Target(METHOD)` if marking individual methods, or `TYPE` if marking entire classes. Verify the Spring proxy, method metadata, and pointcut together; merely having the right meta-annotations does not guarantee advice will run.