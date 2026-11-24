# MethodSignature and Retrieving Method Information in Spring AOP

## 1. Purpose

When advice in Spring AOP runs, it often needs to know **which Spring bean method is being called**, its parameter types, return type, declaring class, or annotations attached to the method in order to perform auditing, tracing, and metrics. Rather than inferring from a proxy object's name or parsing log strings, a Spring Aspect can read metadata in a typed way via `org.aspectj.lang.reflect.MethodSignature`.

Example placed **inside a Spring `@Aspect` bean**:

~~~java
@Before("execution(* demo..service..*(..))")
public void before(JoinPoint joinPoint) {
    MethodSignature signature =
            (MethodSignature) joinPoint.getSignature();

    String methodName = signature.getName();
    Class<?> returnType = signature.getReturnType();
    Class<?>[] types = signature.getParameterTypes();
    Method method = signature.getMethod();
}
~~~

This is an illustrative snippet, not a complete Java class: it requires importing `org.aspectj.lang.JoinPoint`, `org.aspectj.lang.annotation.Before`, `org.aspectj.lang.reflect.MethodSignature`, and `java.lang.reflect.Method`. In Spring AOP, the advised join point is a **method execution of a Spring-managed bean**, invoked through a JDK/CGLIB proxy; it does not cover every method on every Java object.

**Scope:** focuses solely on how to leverage `MethodSignature` in a Spring Aspect, the difference between method metadata and runtime arguments, how to find the right implementing method when proxying by interface, common pitfalls, and a runnable Spring Framework example. It does not revisit AspectJ bytecode weaving theory.

## 2. Distinguishing objects inside a Spring AOP advice

| Type | API | Information / purpose |
| --- | --- | --- |
| `JoinPoint` | `org.aspectj.lang.JoinPoint` | Invocation context, signature, proxy, target, and runtime argument values |
| `ProceedingJoinPoint` | `org.aspectj.lang.ProceedingJoinPoint` | For `@Around`; extends `JoinPoint` and allows calling `proceed(...)` |
| `Signature` | `org.aspectj.lang.Signature` | Name, modifiers, declaring type, and string representations of the signature |
| `MethodSignature` | `org.aspectj.lang.reflect.MethodSignature` | Signature subtype specific to method execution: Java `Method`, parameter types/names, return type, exception types |
| `Method` | `java.lang.reflect.Method` | Java reflection: annotations, declaring class, generic types, modifiers, and bridge method info |

Diagram:

~~~text
Spring bean caller
       |
       v
   AOP proxy --------> target method
       |
       v
@Aspect advice(JoinPoint point)
       |
       +-- point.getThis()       : proxy reference
       +-- point.getTarget()     : target object
       +-- point.getArgs()       : runtime values
       +-- point.getSignature()  : Signature
                                    |
                                    v
                             MethodSignature
                               |        |
                         getMethod()  getReturnType()
                               |
                               v
                     java.lang.reflect.Method
~~~

**`MethodSignature` describes the signature**, whereas `JoinPoint.getArgs()` contains the **value of each argument at the invocation**. For example, `greet(String name, int times)` declares `String,int`, while in one call the caller may pass `"Ada", 2`. Do not conflate parameter types with parameter values.

Another distinction: `getThis()` typically represents the AOP proxy; `getTarget()` represents the target object the proxy delegates to. With a JDK proxy, they do not share the same class. This has a major impact on how method annotations and declaring types are read.

## 3. Useful `MethodSignature` APIs

### 3.1. Name and declaring type

~~~java
MethodSignature s = (MethodSignature) point.getSignature();

String name = s.getName();
Class<?> declaredIn = s.getDeclaringType();
String qualifiedType = s.getDeclaringTypeName();
int modifiers = s.getModifiers();
boolean isPublic = java.lang.reflect.Modifier.isPublic(modifiers);
~~~

`getName()` returns the method name, such as `greet`. `getDeclaringType()` and `getDeclaringTypeName()` return the type originating from **the signature the proxy is handling**; with a JDK dynamic proxy this can be an interface, not necessarily the implementation class. `getModifiers()` is the bitmask of Java modifiers, which can be interpreted with `java.lang.reflect.Modifier`.

`s.toShortString()`, `s.toLongString()`, and `s.toString()` are convenient for diagnostic logs. **Do not parse those display strings with regex** to build stable identifiers: string formatting can depend on library versions; extract `name`, `declaringType`, and `parameterTypes` separately.

### 3.2. Return type and declared exceptions

~~~java
Class<?> returnType = s.getReturnType();
Class<?>[] declaredExceptions = s.getExceptionTypes();
~~~

`getReturnType()` describes the **declared return type**: `String.class` for `String greet(...)`, `void.class` for `void send()`, `int.class` for `int sum(...)`. It is not the result object of an invocation. If a method declares `List<String>`, the raw class is normally `List.class` without preserving the `String` element type.

`getExceptionTypes()` describes the exceptions in the method's **`throws` declaration**; it does not tell you which error the method actually threw. To read the returned value, use `@AfterReturning(returning="...")`; to read a thrown exception, use `@AfterThrowing(throwing="...")` or `@Around` when flow-control requirements genuinely exist.

### 3.3. Parameter types and parameter names

~~~java
Class<?>[] parameterTypes = s.getParameterTypes();
String[] parameterNames = s.getParameterNames();
Object[] argumentValues = point.getArgs();
~~~

- `parameterTypes` holds the `Class<?>` entries in declaration order: `String.class` and `int.class` in the example.
- `parameterNames` may contain names such as `name`/`times`, but **is not guaranteed to always exist** across all bytecode/proxies.
- `argumentValues` holds runtime values, e.g. `["Ada", 2]`; primitive `int` is boxed into `Integer` in `Object[]`.

Enable the `-parameters` compiler flag when you control a Java 17+ project. Even so, write code with a fallback when `getParameterNames()` returns `null` or metadata is incomplete. Avoid building critical logging/audit schemas that depend solely on parameter names from a third-party dependency.

### 3.4. Java reflection `Method`

~~~java
Method method = s.getMethod();
String name = method.getName();
Class<?> declaringClass = method.getDeclaringClass();
Class<?>[] formalTypes = method.getParameterTypes();
java.lang.reflect.Type genericType = method.getGenericReturnType();
~~~

`getMethod()` is the bridge for reading annotations, modifiers, type/generic metadata, `isBridge()`, and `isSynthetic()`. However, **never assume `getMethod()` always returns the method on the target implementation**: when using a JDK proxy, it may be the method declared on the interface.

This is crucial if an audit annotation is placed only on the implementing method: `method.getAnnotation(AuditTag.class)` can be `null` when `method` comes from the interface.

## 4. The JDK proxy problem: finding the implementing method to read annotations

Suppose interface `GreetingPort` has:

~~~java
public interface GreetingPort {
    String greet(String name, int times);
}
~~~

The implementation carries the annotation:

~~~java
public class GreetingService implements GreetingPort {
    @AuditTag("greeting")
    @Override
    public String greet(String name, int times) {
        return "Hello " + name + " x" + times;
    }
}
~~~

The two snippets above are standalone illustrations; the full source is in section 5. If Spring AOP selects a **JDK dynamic proxy**, the interface method and implementation method are two different Java reflection `Method` objects. An annotation on the implementation method does not propagate automatically to the interface method.

**Unsafe reading approach:**

~~~java
MethodSignature s = (MethodSignature) point.getSignature();
AuditTag tag = s.getMethod().getAnnotation(AuditTag.class);
// Can be null even when the implementation method has @AuditTag.
~~~

**Spring-native approach:**

~~~java
MethodSignature s = (MethodSignature) point.getSignature();

Method methodOnSignature = s.getMethod();
Class<?> targetClass = point.getTarget().getClass();

Method targetMethod = org.springframework.aop.support.AopUtils
        .getMostSpecificMethod(methodOnSignature, targetClass);

AuditTag tag = targetMethod.getAnnotation(AuditTag.class);
~~~

`AopUtils.getMostSpecificMethod(method, targetClass)` locates the corresponding method on the target class if present; it also handles bridge method resolution per Spring documentation. In the `GreetingService` example, the resolved target method will contain `@AuditTag`.

Key points to remember:

1. `point.getTarget()` is the target in a typical Spring AOP invocation; do not take `point.getThis().getClass()` (the generated proxy class) and search directly for annotations there.
2. If the interface method has no specific implementing method or the target class cannot be resolved, the helper may return the original method; write an appropriate fallback.
3. `target.getClass()` can involve a custom target source or special object; general-purpose library code should check `getTarget() != null`.
4. When annotations are placed on interfaces rather than implementations, define a clear policy for reading annotations at **both locations**, rather than assuming annotations are always "inherited".
5. The method-lookup helper **does not make advice match by itself**. The pointcut must match and the invocation must pass through the Spring proxy before code inside the advice gets a chance to run.

### Finding custom meta-annotations the Spring way

~~~java
AuditTag tag =
    org.springframework.core.annotation.AnnotatedElementUtils
        .findMergedAnnotation(targetMethod, AuditTag.class);
~~~

`findMergedAnnotation` is useful when a project uses Spring composed/meta-annotations or appropriate aliasing. Unlike plain Java reflection's `getAnnotation`, it does **not** mean it always finds every annotation across any interface hierarchy or behaves identically to `@annotation(...)` pointcut matching semantics. If an interface-annotation fallback is required:

~~~java
AuditTag tag = AnnotatedElementUtils.findMergedAnnotation(
        targetMethod, AuditTag.class);
if (tag == null) {
    tag = AnnotatedElementUtils.findMergedAnnotation(
            methodOnSignature, AuditTag.class);
}
~~~

These are two illustrative snippets using the variables and imports already explained. Preferring the implementation first and the interface second is a **policy specific to this example**, not a universal rule for all system annotations. In large Spring Boot/Spring Framework apps, write integration tests for actual annotation placement.

## 5. Java 17+ Spring Framework 6.2 project: runnable example

The program uses a **JDK interface proxy**, a custom `@AuditTag` placed **only on the implementation method**, a `@Before` advice reading `MethodSignature` and the annotation, plus a non-matching method call for comparison.

Structure:

~~~text
spring-method-signature/
├── pom.xml
└── src/main/java/demo/
    ├── App.java
    ├── AuditTag.java
    ├── GreetingPort.java
    ├── GreetingService.java
    └── MetadataAspect.java
~~~

Requires JDK 17+, Maven 3.9+, Spring Framework **6.2.0**, AspectJ Weaver **1.9.22**. Versions are pinned for study; no claim is made that these are the latest releases. No AspectJ weaving/javaagent is needed.

### 5.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-method-signature</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides IoC/Java config; `spring-aop` includes `AopUtils` and the auto-proxy framework; `aspectjweaver` enables Spring to parse `@AspectJ`-style pointcuts, **without automatically enabling weaving**. `<parameters>true</parameters>` supplies compile-time parameter names, though it is not the deciding factor for the stdout below.

### 5.2. Annotation marking the implementation method

Create `src/main/java/demo/AuditTag.java`:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface AuditTag {
    String value();
}
~~~

`RUNTIME` retention allows reading it when advice inspects the `Method`. `METHOD` target restricts the annotation to methods. `value` carries the tag used for auditing.

### 5.3. Interface and implementation

`src/main/java/demo/GreetingPort.java`:

~~~java
package demo;

public interface GreetingPort {
    String greet(String name, int times);
    String echo(String message);
}
~~~

`src/main/java/demo/GreetingService.java`:

~~~java
package demo;

public class GreetingService implements GreetingPort {
    @AuditTag("greeting")
    @Override
    public String greet(String name, int times) {
        System.out.println("TARGET: greet " + name + " x" + times);
        return "Hello " + name + " x" + times;
    }

    @Override
    public String echo(String message) {
        System.out.println("TARGET: echo " + message);
        return message;
    }
}
~~~

The annotation is **only on the implementation** `GreetingService.greet`. Both `greet` and `echo` belong to the same interface, but the pointcut below selects only `greet`. The `echo` method confirms that not every call through a Spring proxy becomes an advice event.

### 5.4. Aspect using MethodSignature

`src/main/java/demo/MetadataAspect.java`:

~~~java
package demo;

import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.aop.support.AopUtils;
import org.springframework.core.annotation.AnnotatedElementUtils;

@Aspect
public class MetadataAspect {
    private final AtomicInteger adviceCount = new AtomicInteger();

    @Before("execution(* demo.GreetingPort.greet(..))")
    public void inspect(JoinPoint point) {
        if (!(point.getSignature() instanceof MethodSignature sig)) {
            throw new IllegalStateException("Not a method join point");
        }

        Method method = sig.getMethod();
        Class<?> targetClass = point.getTarget().getClass();

        Method actual = AopUtils.getMostSpecificMethod(
                method, targetClass);

        AuditTag tag = AnnotatedElementUtils.findMergedAnnotation(
                actual, AuditTag.class);
        if (tag == null) {
            throw new IllegalStateException("Missing annotation");
        }

        String formalTypes = Arrays.stream(actual.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(","));

        String methodInfo =
                actual.getDeclaringClass().getSimpleName()
                + "." + actual.getName()
                + "(" + formalTypes + ")->"
                + actual.getReturnType().getSimpleName();

        adviceCount.incrementAndGet();
        System.out.println("METHOD: " + methodInfo);
        System.out.println("TAG: " + tag.value());
        System.out.println("ARGS: " + Arrays.toString(point.getArgs()));
    }

    public int count() {
        return adviceCount.get();
    }
}
~~~

Key points in the code:

1. `@Aspect` only marks the class; this class will be registered as a Spring bean via `@Bean`.
2. `@Before` is chosen because it only reads/prints before the target; it does not need `@Around`'s `proceed()` control.
3. `point.getSignature()` is checked with `instanceof MethodSignature` to verify the join point type in code.
4. `sig.getMethod()` may come from `GreetingPort`; the `getMostSpecificMethod` helper identifies the implementation method if present.
5. `actual.getParameterTypes()` and `actual.getReturnType()` return the declared types, assembled into `GreetingService.greet(String,int)->String` without depending on parameter names.
6. `findMergedAnnotation(actual,AuditTag.class)` reads the `greeting` tag directly from the implementation method.
7. `point.getArgs()` returns runtime values and prints `[Ada, 2]` (distinct from `[String,int]`).
8. `AtomicInteger` increments only inside advice. Since `echo` does not match, the counter does not increment.
9. `getParameterNames()` is not used in stdout because its value can depend on compiler/loaded interface metadata.

For production logging, avoid unconditionally printing all of `getArgs()`: an element may contain a password, access token, card number, personal data, or a `toString()` with side effects. The demo uses only a non-sensitive name and integer.

### 5.5. Configuration and main method

`src/main/java/demo/App.java`:

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class App {
    @Bean
    public GreetingPort greetingPort() {
        return new GreetingService();
    }

    @Bean
    public MetadataAspect metadataAspect() {
        return new MetadataAspect();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            GreetingPort service = context.getBean(GreetingPort.class);
            MetadataAspect aspect = context.getBean(MetadataAspect.class);

            boolean jdk = AopUtils.isJdkDynamicProxy(service);
            System.out.println("JDK_PROXY: " + jdk);

            String greeted = service.greet("Ada", 2);
            System.out.println("RESULT: " + greeted);

            String echoed = service.echo("ping");
            System.out.println("ECHO: " + echoed);

            int count = aspect.count();
            System.out.println("ADVICE_COUNT: " + count);

            if (!jdk || !"Hello Ada x2".equals(greeted)
                    || !"ping".equals(echoed) || count != 1) {
                throw new IllegalStateException(
                        "MethodSignature verification failed");
            }
            System.out.println("CHECK: PASS");
        }
    }
}
~~~

`@EnableAspectJAutoProxy(proxyTargetClass = false)` allows JDK interface proxies when a bean has an interface; it is not a mandate forcing every bean to use a JDK proxy. In this project, the aspect has an advisor matching `greet` and `GreetingService implements GreetingPort`, so a JDK proxy is the expected result. The program checks at runtime using `AopUtils.isJdkDynamicProxy` and throws an error if the condition fails.

`new GreetingService()` is called **inside the `@Bean` factory**; the returned instance is managed by Spring and can be auto-proxied. The caller retrieves the reference from `ApplicationContext`, rather than holding another raw target reference that bypasses advice.

### 5.6. Run command and expected stdout

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Lines produced by `System.out.println`:

~~~text
JDK_PROXY: true
METHOD: GreetingService.greet(String,int)->String
TAG: greeting
ARGS: [Ada, 2]
TARGET: greet Ada x2
RESULT: Hello Ada x2
TARGET: echo ping
ECHO: ping
ADVICE_COUNT: 1
CHECK: PASS
~~~

Maven/SLF4J may print additional lines outside the block above. This shows the **expected application stdout when the project runs**, not a capture of Maven execution on the reader's machine.

The output demonstrates:

- The service reference returned by Spring is a JDK proxy.
- Method metadata resolution locates the **implementation** rather than getting stuck at the interface.
- `@AuditTag("greeting")` on the implementation is found.
- `String,int` are the **parameter types**, while `[Ada, 2]` are the **argument values**.
- The advice lines appear before the business method; `echo` has no corresponding advice.
- `ADVICE_COUNT: 1` confirms the aspect ran exactly once.
- `CHECK: PASS` appears only when the business result, proxy type, and advice count all match expectations.

## 6. Reusing `MethodSignature` across advice types

### 6.1. `@Before`: metadata before invocation

~~~java
@Before("execution(* demo..service..*(..))")
public void before(JoinPoint jp) {
    MethodSignature signature =
            (MethodSignature) jp.getSignature();
    System.out.println(signature.getName());
}
~~~

This is an illustrative advice method; the real package must match the expression. When you only need to read the method name and arguments before the business call, `@Before` is simpler than `@Around`.

### 6.2. `@AfterReturning`: metadata and actual result

~~~java
@AfterReturning(
    pointcut = "execution(* demo..service..*(..))",
    returning = "value",
    argNames = "value"
)
public void afterReturning(JoinPoint jp, Object value) {
    MethodSignature s = (MethodSignature) jp.getSignature();
    System.out.println("Declared: " + s.getReturnType().getSimpleName());
    System.out.println("Actual: " + value);
}
~~~

`getReturnType()` is the **declared return type**, whereas `value` is the actual return value on the path where the method **returns normally**. If the target throws an exception, `@AfterReturning` is not called.

### 6.3. `@AfterThrowing`: metadata and actual exception

~~~java
@AfterThrowing(
    pointcut = "execution(* demo..service..*(..))",
    throwing = "error",
    argNames = "error"
)
public void afterThrowing(JoinPoint jp, Throwable error) {
    MethodSignature s = (MethodSignature) jp.getSignature();
    System.out.println(s.getName() + " threw "
            + error.getClass().getSimpleName());
}
~~~

`error` is the actual exception; `s.getExceptionTypes()` are the types **declared in the method's `throws` clause**. `@AfterThrowing` observes failure; it does not automatically turn a thrown exception into a successful result.

### 6.4. `@Around`: metadata and forwarding

~~~java
@Around("execution(* demo..service..*(..))")
public Object around(ProceedingJoinPoint jp) throws Throwable {
    MethodSignature s = (MethodSignature) jp.getSignature();
    System.out.println(s.getName());
    return jp.proceed();
}
~~~

`ProceedingJoinPoint` extends `JoinPoint` and therefore has the same `getSignature()` API. Unlike `@Before`, `@Around` has the power to skip `proceed()`, alter arguments/return values, or rethrow exceptions. Do not use that power just to print a method name when `@Before` is sufficient.

If you actually use `proceed(Object[])` to replace arguments, the array's element count in **Spring AOP** must match the target method; `getParameterTypes()` helps inspect the signature, and `getArgs()` reads current values. That is a different problem from simply **reading metadata**.

The snippets in section 6 are **independent options** and should not all be added to the main project's `MetadataAspect` if you want the exact output from section 5.

## 7. Overloads, generics, bridge methods, and annotation placement

### 7.1. Method overloads

These two methods share the same name:

~~~java
public void dispatch(String code) {
}

public void dispatch(String code, int retries) {
}
~~~

`MethodSignature.getName()` returns `dispatch` for both. If you build a metrics key solely from the name, both overloads get merged erroneously. Include parameter types:

~~~java
String types = java.util.Arrays
        .stream(s.getParameterTypes())
        .map(Class::getTypeName)
        .collect(java.util.stream.Collectors.joining(","));

String key = s.getDeclaringTypeName()
        + "#" + s.getName() + "(" + types + ")";
~~~

This is a snippet inside advice that already has `MethodSignature s`. Decide whether the key should reflect the proxy signature or the implementation method; if you want the specific target class, use the resolved method.

### 7.2. Generic bridges

~~~java
interface Converter<T> {
    T convert(T value);
}

class StringConverter implements Converter<String> {
    @Override
    public String convert(String value) {
        return value.trim();
    }
}
~~~

This is a separate illustrative Java snippet. Java generics erasure can generate a **bridge method** in the implementation to preserve polymorphism. `Method.isBridge()`/`isSynthetic()` reveal certain reflection characteristics; `AopUtils.getMostSpecificMethod` handles bridge resolution for metadata lookup per Spring documentation. If you manually call reflection `getDeclaredMethod` by name/arity alone, you can easily pick the wrong method or miss annotations on the user-declared method.

### 7.3. Annotations on interface vs. implementation

Java method annotations are not automatically inherited from an interface method down to an implementation method via `@Inherited`; the `@Inherited` mechanism primarily relates to class annotations. Establish a clear convention:

- Annotations placed on implementation methods: resolve the target method, then look up the annotation.
- Annotations placed on interface methods: fall back to the interface method when the target method has no tag.
- Meta-annotations or aliasing needed: consider `AnnotatedElementUtils.findMergedAnnotation`.
- Aspects using `@annotation(...)` pointcuts to **select join points**: matching semantics are not necessarily mechanically identical to Spring's merged-annotation lookup inside method advice.

### 7.4. Method name, return type, and runtime arguments mean different things

| What you need to know | How to read it | Example |
| --- | --- | --- |
| Method name | `signature.getName()` | `greet` |
| Parameter types | `signature.getParameterTypes()` | `String,int` |
| Parameter names | `signature.getParameterNames()` | `name,times` (if metadata exists) |
| Actual values | `joinPoint.getArgs()` | `"Ada",2` |
| Declared return type | `signature.getReturnType()` | `String` |
| Actual return value | `@AfterReturning(returning=...)` | `Hello Ada x2` |
| Declared exceptions | `signature.getExceptionTypes()` | Types in `throws` |
| Actual exception | `@AfterThrowing(throwing=...)` | `IllegalStateException` if actually thrown |
| Java reflection Method | `signature.getMethod()` | May be the interface method |
| Implementation method | `AopUtils.getMostSpecificMethod(...)` | `GreetingService.greet` |
| Proxy vs. target | `joinPoint.getThis()` / `getTarget()` | JDK proxy / `GreetingService` |

This table helps avoid confusing **static metadata** with **dynamic invocation state**.

## 8. Common errors and how to resolve them

**1. `ClassCastException` or method metadata is not the implementation:** if a JDK proxy is used, the reference and `Method` may be tied to the interface. Do not cast the proxy to the implementation class; use the interface API for callers and `AopUtils.getMostSpecificMethod` for metadata.

**2. Annotation returns `null`:** check whether it sits on the interface or the implementation. `signature.getMethod().getAnnotation(...)` may look at the wrong method; resolve the target method first and read from it. If still null, check `RUNTIME` retention, `METHOD` annotation target, and meta-annotation setup.

**3. Parameter names are missing:** ensure `-parameters` is enabled on the module containing the method; check whether names match between interface and implementation. Even with the flag enabled, always provide a fallback when handling third-party libraries.

**4. Return type does not match the returned object's class:** declared type `List`/`Number` can differ from runtime type `ArrayList`/`Integer`. `getReturnType()` is not the value the target returned; use `@AfterReturning`/`@Around` for the outcome.

**5. Advice does not run, so metadata is never seen:** possible causes include a non-matching pointcut, aspect not registered as a bean, object instantiated outside Spring, bean not auto-proxied, or self-invocation. Verify `AopUtils.isAopProxy` on the reference the caller actually uses. Do not switch `@Before` to `@Around` merely hoping the method will get intercepted.

**6. `getDeclaringType()` is not the bean name:** the declaring type is the class/interface declaring the signature; one Spring class can have multiple bean instances or multiple bean names. `MethodSignature` does not carry the bean name, request ID, or user identity on its own.

**7. Logging method signatures with `toLongString()` and parsing with regex:** this is brittle and depends on format/version. Use the typed accessors and build a stable key format yourself if needed.

**8. Logs accidentally leak sensitive data:** `Arrays.toString(jp.getArgs())` in the example uses learning data only. In production Spring AOP, log only allowlisted fields, apply redaction, and avoid calling `toString` on sensitive objects.

**9. Using `getExceptionTypes()` to measure failures:** those are declared exceptions, not actual exceptions. Use `@AfterThrowing` with typed binding if you need failure metrics.

**10. Calling reflection `Method.invoke` directly inside advice to "call the real method":** doing so can alter or bypass the interceptor chain, causing double invocations or losing transactions/caching/security. Inside `@Around`, `ProceedingJoinPoint.proceed()` is required to continue the chain properly in Spring AOP; method reflection here is only for **reading metadata**.

## 9. Testing through ApplicationContext

When testing `MethodSignature` in Spring AOP, the test must call the actual **Spring bean proxy**. Instantiating `new GreetingService()` directly only tests Java logic and does not create an advised join point.

You can write the following JUnit 5 integration test after adding `junit-jupiter` and `maven-surefire-plugin` to `pom.xml`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MethodSignatureTest {
    @Test
    void implementationAnnotationIsVisibleThroughJdkProxy() {
        try (var context =
                new AnnotationConfigApplicationContext(App.class)) {
            GreetingPort service = context.getBean(GreetingPort.class);
            MetadataAspect aspect = context.getBean(MetadataAspect.class);

            assertTrue(AopUtils.isJdkDynamicProxy(service));
            assertEquals("Hello Ada x2", service.greet("Ada", 2));
            assertEquals("ping", service.echo("ping"));
            assertEquals(1, aspect.count());
        }
    }
}
~~~

This is a **complete Java test file**, though it cannot run with only the minimal `pom.xml` in section 5 without declaring the JUnit dependency and Surefire plugin. In the test, `MetadataAspect` throws an exception if it fails to find the implementation annotation; thus the test verifies both that the advice executed and that metadata resolution succeeded without error.

After adding the test dependencies, run:

~~~bash
mvn clean test
~~~

If you want to test method metadata separately, you can also exercise `MethodSignature.getParameterTypes()` and `AopUtils.getMostSpecificMethod(...)` directly in integration tests. However, inspecting method reflection outside the context **is no substitute** for testing real Spring AOP advice going through a JDK proxy.

## 10. Checklist when writing a Spring Aspect that needs method metadata

- [ ] `@Aspect` class is registered as a Spring bean; target is a Spring bean in the proper context.
- [ ] Caller invokes through the Spring proxy, not a raw object or self-invocation when testing advice.
- [ ] Obtain `MethodSignature` from `JoinPoint.getSignature()`; use `instanceof` where helpers need safety.
- [ ] Read method name, return type, and parameter types via accessors; do not parse string representations.
- [ ] Use `joinPoint.getArgs()` for runtime values, without confusing them with parameter types/names.
- [ ] `getParameterNames()` is handled with a fallback; `-parameters` is enabled where appropriate.
- [ ] With a JDK proxy, `getMethod()` may be the interface method; do not assume implementation annotations are present there.
- [ ] Resolve `AopUtils.getMostSpecificMethod(...)` before looking up annotations on the implementation.
- [ ] Distinguish declared return type from actual return value; declared `throws` from actual thrown exception.
- [ ] When overloads/bridge/generic methods exist, test under Spring's actual proxy configuration.
- [ ] Minimize reflection and string construction in hot-path advice; cache metadata keyed by `Method` if needed and policy-compliant.
- [ ] Do not log entire sensitive arguments; define clear observability goals.

## 11. Official documentation

- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `JoinPoint`/`ProceedingJoinPoint` and metadata in Spring advice.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK proxy, CGLIB, and self-invocation.
- [Spring Framework 6.2 — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): Spring AOP method execution on managed beans.
- [AopUtils Javadoc — Spring Framework 6.2](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aop/support/AopUtils.html): `getMostSpecificMethod` and bridge methods.
- [AnnotatedElementUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/annotation/AnnotatedElementUtils.html): annotation lookup supporting merged/composed metadata.
- [MethodSignature — AspectJ API](https://www.javadoc.io/doc/org.aspectj/aspectjrt/1.9.22/org/aspectj/lang/reflect/MethodSignature.html): accessors `getMethod`, `getParameterTypes`, `getParameterNames`, `getReturnType`, and `getExceptionTypes`.
