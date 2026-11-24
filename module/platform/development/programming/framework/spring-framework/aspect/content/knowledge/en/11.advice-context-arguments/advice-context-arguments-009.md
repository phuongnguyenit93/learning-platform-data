# Spring AOP: Inference Limitations When Parameters Have Generics and Type Erasure

## 1. The problem in a Spring Aspect: is `List<String>` actually recognized?

A Spring aspect often needs to inspect or bind method arguments via `JoinPoint.getArgs()`, `args(...)`, `MethodSignature`, or advice parameter names. When the target method declares generic types such as `List<String>`, `Collection<Order>`, `Optional<User>`, or `Repository<T>`, you must distinguish:

1. **The declared type in source/class metadata**, such as `List<String>`.
2. **The runtime type of the passed object**, such as an instance of `List`.
3. **The runtime type of each element**, such as individual `String` objects.
4. **The matching/binding capability of a Spring AOP pointcut**, which is not equivalent to a complete runtime verifier for every type parameter.

Java performs **generic type erasure**: most type arguments do not reside in the runtime class of a `List` object. Spring can read a method's **generic signature metadata** via reflection if that metadata exists, yet that does not prove the collection's runtime contents actually conform.

This is an important practical limitation when using a **Spring Aspect**, not a general lesson on generics. We focus on these questions: which method does the advice match, what values can be bound, how much can reflection see, when must you inspect elements manually, and how do JDK/CGLIB proxies and bridge methods interact?

### Example distinguishing three layers of information

```java
public interface MessagePort {
    void deliver(List<String> names);
}
```

When a consumer calls `port.deliver(List.of("An", "Bình"))` on a Spring-managed proxy:

- Java compile-time checks `List<String>` against the method contract.
- `JoinPoint.getArgs()[0]` receives a **`List` object**. `getClass()` tells you the `List`'s implementation class, not `List<String>`.
- If the declaration actually retains a generic signature, reflection can read that **the method parameter** was declared as `List<String>`.
- The runtime argument could still have been constructed via raw types, unchecked casts, reflection, deserialization, or unsafe code. A method declaration does not guarantee every element is really a `String`.
- Spring AOP does not automatically iterate all `List` elements on every invocation to infer `T`, because no reliable universal rule can cover `null`, empty collections, wildcards, or mutable lists.

**Opening takeaway:** *Generic declaration metadata is different from generic runtime verification; `JoinPoint` and pointcut binding do not replace Java type-safety at application boundaries.*

## 2. Spring AOP observes calls at the proxy boundary

```text
Consumer
   |
   | port.deliver(List<String>)
   v
JDK proxy (interface) or CGLIB proxy (class)
   |
   | pointcut matches method-execution
   v
@Before / @Around advice
   |
   +-- jp.getArgs()[0]             -> List object (runtime value)
   +-- jp.getSignature()           -> method signature
   +-- Method.getGeneric...        -> declared metadata if present
   +-- args(values)                -> bind runtime object
   |
   v
Target.deliver(List<String>)
```

Spring AOP is proxy-based and supports only **method-execution join points** on Spring-managed beans. Not every method call in the JVM creates a `JoinPoint` for advice.

When the target calls `this.deliver(...)` on itself, the internal call **bypasses the proxy**, so the advice does not see that invocation. Likewise, an object instantiated with `new` outside Spring IoC has no AOP proxy.

### How a method is invoked does not undo erasure

Switching from a JDK proxy to CGLIB does not "restore" generic type arguments inside a runtime `List`; both still run on the Java runtime. What differs is that the reflected `Method` from the interface vs. implementation can differ, requiring us to **resolve the concrete method** before reading generic metadata.

## 3. When Spring can bind a parameter with a specific type

The official Spring Framework documentation, section **Advice Parameters and Generics**, explains how Spring AOP supports generics on class declarations and method parameters. Example:

```java
public interface Sample<T> {
    void sampleGenericMethod(T value);
    void sampleGenericCollectionMethod(Collection<T> values);
}
```

If a caller passes an object of class `Invoice` to `sampleGenericMethod(T)`, advice can bind the specific type based on the argument's runtime type, subject to the pointcut and method constraints:

```java
@Before(
    value = "execution(* demo.generic..*.sampleGenericMethod(..))"
          + " && args(invoice)",
    argNames = "invoice"
)
public void beforeInvoice(Invoice invoice) {
    System.out.println("invoice id=" + invoice.id());
}
```

This is a **fragment**; `Invoice` must be an actual type in the project, the aspect must be Spring-managed, and the call must go through the proxy. `args(invoice)` binds the actual argument and applies the compatible type constraint. Spring can check whether the runtime object is an `Invoice`, which is completely different from asking "does a `List` contain `Invoice` elements?".

For a parameter of generic type `T` where the actual method receives a specific subclass, Spring/AspectJ pointcut matching can use the **runtime type**, declared method signature, and other rules. Do not generalize from one simple example that every generic hierarchy, overload, `null`, interface, and bridge method matches identically.

## 4. Crucial limitation: `Collection<Invoice>` in advice

Spring explicitly highlights that you **cannot simply use** an advice parameter of type `Collection<Invoice>` as a pointcut filter to accurately verify the contents of a generic collection:

```java
// DO NOT use as a runtime verification method for List/Collection<Invoice>.
@Before(
    value = "execution(* demo.generic..*.sampleGenericCollectionMethod(..))"
          + " && args(values)",
    argNames = "values"
)
public void beforeInvoices(Collection<Invoice> values) {
    // This declared type does NOT mean Spring verified every element.
}
```

This is a **counterexample** snippet, not recommended code. The reason is not simply "Spring isn't smart enough": a normal runtime `Collection` object does not encode `Invoice` as a reified type argument, and Spring does not traverse all elements to deduce a generic match.

Recommended approach when you need to inspect actual contents:

```java
@Before(
    value = "execution(* demo.generic..*.sampleGenericCollectionMethod(..))"
          + " && args(values)",
    argNames = "values"
)
public void inspect(Collection<?> values) {
    boolean allInvoices = values.stream()
            .allMatch(Invoice.class::isInstance);
    System.out.println("all invoices=" + allInvoices);
}
```

This is a **fragment** assuming `Invoice` exists. `Collection<?>` makes explicit that the advice does not yet know the element type, and you then check each element according to a specific policy. However:

- `allMatch(...)` on an **empty collection** returns `true` by mathematical convention (vacuous truth): *having no wrong elements* does not mean *`Invoice` elements were proven*.
- If the collection contains `null`, `Invoice.class.isInstance(null)` is `false`; you must decide on a null policy.
- If the collection is mutable and modified concurrently, a one-time check does not guarantee it stays valid.
- If you only need logging, iterating every element may be unnecessary due to cost, data sensitivity, and side effects.
- If validation affects security or business rules, pick the right boundary, validate deliberately, and consider Spring Bean Validation / appropriate contract validation; do not rely on an aspect alone to secure the entire system.

**Focus:** binding `Collection<?>` is sufficient for advice to read the object in a generics-safe way, while verifying element types is a separate step depending on your goal.

## 5. How `args(...)` differs from `execution(...)` in matching

Spring AOP supports two categories of information that are frequently conflated:

- `execution(...)` evaluates whether the **method signature/execution** matches a pattern.
- `args(...)` evaluates whether **runtime arguments** match a type/argument binding.

### 5.1. Do not write a generic type argument as a runtime type in a pointcut

Do not assume you can write:

```text
execution(* demo.generic.CatalogService.store(java.util.List<java.lang.String>))
```

to make Spring AOP perform element-type matching for `List<String>`. `execution` pointcuts in proxy-based Spring AOP are not a query language over generic contents. Being able to **read** a generic signature from a method declaration is a different capability from **matching every element**.

When the goal is simply a method named `storeNames`, use a method pattern:

```java
@Before("execution(* demo.generic.CatalogService.storeNames(..))")
public void beforeNames(JoinPoint jp) {
    Object first = jp.getArgs()[0];
    System.out.println(first instanceof List<?>);
}
```

The snippet above does not prove `List<String>` is valid; it only observes that an argument is a `List`.

### 5.2. `args(value)` and `args(values)`

For a scalar argument, `args(value)` binds the actual value to a typed advice parameter. For `List<?>`, `args(values)` binds the **`List` object**, not each element. You must write explicit checking logic if you want to know element types.

Also consider `null`: a null runtime argument has no concrete class for `getClass()` inspection. Static signature conditions and type-binding mechanics can affect matching; do not infer from `null` that a generic type argument is known. If a pointcut or advice must work with `null`, verify with an integration test for that exact overload and configuration.

### 5.3. Overloading solely by generic element type is invalid in Java

You cannot declare two overloads in the same class differing only by type argument:

```java
// COUNTEREXAMPLE — both methods have the same erasure and will not compile.
public void store(List<String> values) {}
public void store(List<Integer> values) {}
```

After erasure, both have the form `store(List)`. Java does not distinguish method overloads by the `String` or `Integer` inside `List`. Therefore, never design pointcuts to distinguish two overloads that cannot even exist in Java bytecode.

You can use two differently named methods such as `storeNames(List<String>)` and `storeNumbers(List<Integer>)`, or use dedicated wrapper types if distinct APIs are truly needed.

## 6. Reflection: `getParameterTypes()` and `getGenericParameterTypes()`

When a Spring AOP call reaches a method, advice can use:

```java
MethodSignature signature = (MethodSignature) jp.getSignature();
Method method = signature.getMethod();

Class<?>[] erasedTypes = method.getParameterTypes();
Type[] declaredTypes = method.getGenericParameterTypes();
```

This is a **fragment** inside advice; imports include `org.aspectj.lang.reflect.MethodSignature`, `java.lang.reflect.Method`, and `java.lang.reflect.Type`.

Suppose the concrete declaration is:

```java
public void storeNames(List<String> values) { /* ... */ }
```

Key concepts:

| API | What can it see? | What can it not conclude? |
| --- | --- | --- |
| `Method.getParameterTypes()[0]` | `java.util.List.class` — raw `Class` | Does not tell you elements are `String` |
| `Method.getGenericParameterTypes()[0]` | `java.util.List<java.lang.String>` metadata in the method declaration if generic signature is present | Does not prove the `List` object actually contains only `String`s |
| `JoinPoint.getArgs()[0].getClass()` | Concrete runtime `List` class | Has no reified type argument like `List<String>` |
| `MethodSignature.getParameterTypes()[0]` | Erased declared parameter `Class` | Not enough to infer `T` on a generic method |
| `JoinPoint.getArgs()` | Actual runtime values | Does not supply Java type arguments on a collection |

A `ParameterizedType` can describe a method signature containing `List<String>`, yet that `Type` data **belongs to the declaration**, not to the `List` object being passed. If a caller uses raw types or unsafe unchecked casts, the signature still says `String`.

### 6.1. Spring `ResolvableType` helps read generic declarations

Spring provides `org.springframework.core.ResolvableType` for working with generic type metadata in reflection:

```java
Method method = ...; // Concrete method already resolved properly.
ResolvableType parameter = ResolvableType.forMethodParameter(method, 0);
Class<?> elementType = parameter.getGeneric(0).resolve();

System.out.println(elementType); // For List<String>: class java.lang.String.
```

This is a fragment, not a complete Java file. `ResolvableType` is more convenient than manually handling `ParameterizedType`, `TypeVariable`, `WildcardType`, and `GenericArrayType`, but:

- It resolves **declared type metadata**, without inspecting runtime collections.
- For an unresolved `T`, wildcards, or complex parameterized types, resolution may not yield `String.class`; `resolve()` can return `null` or a fallback depending on the hierarchy.
- The chosen `Method` must match the right declaring/implementation context. A generic interface `Port<T>` only holds `T`; to know the concrete binding `T = String`, you need the target implementation class or an appropriate owner context.
- Proxies, bridge methods, and hierarchies may be involved; reading the interface `Method` instead of the implementation makes metadata less specific.

Do not turn `ResolvableType.resolve() == String.class` into a "runtime check that a List contains only Strings".

### 6.2. Argument names are not generic types

Spring has `argNames`, Java parameter-name reflection, and pointcut binding. This is a mechanism to **bind advice variable names** to pointcut expressions, completely separate from enforcing generic types.

Example:

```java
@Before(
    value = "execution(* demo.generic.CatalogService.storeNames(..))"
          + " && args(values)",
    argNames = "values"
)
public void before(List<?> values) {
    System.out.println(values.size());
}
```

`argNames="values"` helps Spring bind the name `values`; it does not turn `List<?>` into `List<String>`. Compiler flags like `-parameters` support method parameter name discovery, rather than altering generic erasure.

## 7. Generic interfaces, bridge methods, and Spring proxies

Example:

```java
public interface Handler<T> {
    void handle(T value);
}

public class StringHandler implements Handler<String> {
    @Override
    public void handle(String value) {
        System.out.println("handle " + value);
    }
}
```

When Java compiles, generic `Handler<T>` is erased (for unbounded `T`, typically to `Object`). The compiler may generate a **synthetic bridge method** to ensure overriding and polymorphism work properly between `handle(Object)` and `handle(String)`.

In Spring AOP:

- A JDK proxy may see the method through the **interface declaration** whose erased parameter is `Object`, whereas the concrete implementation method takes `String`.
- A CGLIB proxy can involve subclass/bridge signatures. Never assume every invocation of a generic method always exposes the exact same Java `Method` object across all proxy types.
- When you need to locate annotations or specific generic metadata, resolve the **most-specific target method** and handle bridges if needed.

Spring provides helpers:

```java
MethodSignature sig = (MethodSignature) jp.getSignature();
Method invokedMethod = sig.getMethod();
Object target = jp.getTarget();

if (target != null) {
    Method specific = AopUtils.getMostSpecificMethod(
            invokedMethod, target.getClass());
    System.out.println(specific.toGenericString());
}
```

This snippet requires importing `org.aspectj.lang.reflect.MethodSignature`, `java.lang.reflect.Method`, and `org.springframework.aop.support.AopUtils`. Spring provides `BridgeMethodResolver` when you need to work with bridge methods specifically:

```java
Method userMethod = BridgeMethodResolver.findBridgedMethod(specific);
```

`BridgeMethodResolver` lives in `org.springframework.core`. The call above illustrates usage assuming `specific` is available. Do not blindly assume `getGenericParameterTypes()` on the resolved method always yields `List<String>`, especially when metadata is declared on a generic superclass or interface.

### 7.1. Generic type erasure is not a Spring-specific bug

When an application uses reflection, dynamic proxies, and method interception, erasure is a property of Java compilation and runtime. Spring provides utilities to **resolve metadata**, yet it cannot infer information that the Java runtime does not store on the object or method context.

Therefore, switching `@EnableAspectJAutoProxy(proxyTargetClass=true)` cannot by itself fix an advice expecting `List<String>` to match collection contents automatically.

## 8. Runnable project: distinguishing generic metadata from runtime arguments

The example uses **Java 17**, **Maven**, and **Spring Framework 6.2.x** without Spring Boot. We intentionally create a Spring-managed service with an interface and an aspect containing three before advice methods for three different methods. Each method uses a separate pointcut so stdout has verifiable ordering, independent of advisor precedence across multiple advisors on one invocation.

Goals:

1. Bind a scalar `String` parameter with `args(text)`.
2. Read the declared generic parameter types of `List<String>` and `List<Integer>`.
3. Show that the runtime list is a `List`, while determining element classes requires inspecting contents.
4. Avoid logging the concrete implementation class of `List.of(...)` because internal JDK class names are not a stable API.
5. Use a Spring-managed JDK proxy to demonstrate the exact AOP boundary.

### 8.1. Directory structure

```text
spring-aop-generic-args/
├── pom.xml
└── src/main/java/demo/generic/
    ├── AppConfig.java
    ├── PayloadPort.java
    ├── PayloadService.java
    ├── InspectAspect.java
    └── Main.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-generic-args</artifactId>
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
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. `AppConfig.java`

```java
package demo.generic;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackageClasses = AppConfig.class)
@EnableAspectJAutoProxy(proxyTargetClass = false)
public class AppConfig {
}
```

`@EnableAspectJAutoProxy(proxyTargetClass=false)` in plain Spring Framework prefers a **JDK interface proxy** because the underlying target implements `PayloadPort`.

### 8.4. `PayloadPort.java`

```java
package demo.generic;

import java.util.List;

public interface PayloadPort {
    void submit(String text);
    void storeNames(List<String> names);
    void storeNumbers(List<Integer> numbers);
}
```

These are three **differently named** methods, because Java does not permit overloads differing only in `List<String>` vs. `List<Integer>` after erasure.

### 8.5. `PayloadService.java`

```java
package demo.generic;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class PayloadService implements PayloadPort {
    @Override
    public void submit(String text) {
        System.out.println("[target] submit " + text);
    }

    @Override
    public void storeNames(List<String> names) {
        System.out.println("[target] names count=" + names.size());
    }

    @Override
    public void storeNumbers(List<Integer> numbers) {
        System.out.println("[target] numbers count=" + numbers.size());
    }
}
```

The target prints only element counts without casting elements, keeping focus on the advice's matching and generic observation.

### 8.6. `InspectAspect.java`

```java
package demo.generic;

import java.lang.reflect.Method;
import java.util.List;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.aop.support.AopUtils;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class InspectAspect {
    @Before(
        value = "execution(* demo.generic.PayloadService.submit(..))"
              + " && args(text)",
        argNames = "text"
    )
    public void beforeText(String text) {
        System.out.println("[advice] text=" + text);
    }

    @Before("execution(* demo.generic.PayloadService.storeNames(..))")
    public void beforeNames(JoinPoint jp) {
        Method method = concreteMethod(jp);
        List<?> values = (List<?>) jp.getArgs()[0];

        System.out.println("[advice] declared="
                + method.getGenericParameterTypes()[0].getTypeName());
        System.out.println("[advice] runtimeIsList=" + (values instanceof List));
        System.out.println("[advice] allStrings="
                + values.stream().allMatch(String.class::isInstance));
    }

    @Before("execution(* demo.generic.PayloadService.storeNumbers(..))")
    public void beforeNumbers(JoinPoint jp) {
        Method method = concreteMethod(jp);
        List<?> values = (List<?>) jp.getArgs()[0];

        System.out.println("[advice] declared="
                + method.getGenericParameterTypes()[0].getTypeName());
        System.out.println("[advice] runtimeIsList=" + (values instanceof List));
        System.out.println("[advice] allIntegers="
                + values.stream().allMatch(Integer.class::isInstance));
    }

    private Method concreteMethod(JoinPoint jp) {
        MethodSignature sig = (MethodSignature) jp.getSignature();
        return AopUtils.getMostSpecificMethod(
                sig.getMethod(), jp.getTarget().getClass());
    }
}
```

In `InspectAspect`:

- `@Before ... args(text)` binds the concrete scalar `String`.
- The other two advice methods use `JoinPoint` to inspect the `List` object, resolve the **concrete declaration** via Spring's `AopUtils.getMostSpecificMethod(...)`, and read generic signature metadata.
- `method.getGenericParameterTypes()[0]` describes declared `List<String>` or `List<Integer>`.
- `values instanceof List` checks only the **raw runtime class/interface**.
- `allMatch(...)` checks each present element. This is an **illustrative policy**; it is not by itself a general contract for empty/null/mutable lists.
- The three pointcuts do not overlap, so log output is predictable.

### 8.7. `Main.java`

```java
package demo.generic;

import java.util.List;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            PayloadPort port = context.getBean(PayloadPort.class);
            System.out.println("jdkProxy=" + AopUtils.isJdkDynamicProxy(port));

            port.submit("A1");
            port.storeNames(List.of("An", "Binh"));
            port.storeNumbers(List.of(10, 20));
        }
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.generic.Main
```

**Stdout emitted by the example's `System.out` calls** (excluding any Maven/Spring logs printed by the environment):

```text
jdkProxy=true
[advice] text=A1
[target] submit A1
[advice] declared=java.util.List<java.lang.String>
[advice] runtimeIsList=true
[advice] allStrings=true
[target] names count=2
[advice] declared=java.util.List<java.lang.Integer>
[advice] runtimeIsList=true
[advice] allIntegers=true
[target] numbers count=2
```

### 8.8. Reading the exact results

1. Spring manages `PayloadService`, `InspectAspect` is scanned, and the pointcuts match; an interface proxy is created, so `jdkProxy=true`.
2. `port.submit("A1")` goes through the proxy. `args(text)` binds the runtime `String`, and the advice prints `text=A1` before the target.
3. `port.storeNames(List.of("An","Binh"))` enters advice. Reflection on the concrete method returns the declared `java.util.List<java.lang.String>`, not a "type argument of the runtime List object".
4. `values instanceof List` is true. Checking each `String` element in **this call's actual data array** returns true; that comes from the sample contents, not from the pointcut inferring generics automatically.
5. `port.storeNumbers(List.of(10,20))` has the same raw `List` surface, yet the declared generic type in a **different method** is `List<Integer>` and each sample element is an `Integer`.
6. Nothing here proves every runtime `List` carries a fixed type parameter; the output reflects only the two method declarations and those specific sample arguments.

## 9. Testing common flawed inferences

### 9.1. Empty collections make `allMatch` return true

```java
List<?> empty = List.of();
boolean strings = empty.stream().allMatch(String.class::isInstance);
boolean integers = empty.stream().allMatch(Integer.class::isInstance);
System.out.println(strings + " " + integers); // true true
```

This is a standalone Java snippet (inside a method) illustrating `Stream` semantics. An empty list has no elements to falsify either check. If business policy demands **at least one element and all of them `String`**:

```java
boolean nonEmptyStrings = !empty.isEmpty()
        && empty.stream().allMatch(String.class::isInstance);
```

Rely on an explicit validation contract rather than blaming Spring AOP for empty collections.

### 9.2. Null elements and wildcards

```java
List<?> mixed = java.util.Arrays.asList("An", null);
boolean allStrings = mixed.stream().allMatch(String.class::isInstance);
System.out.println(allStrings); // false
```

If `null` is permitted by the business contract, write the condition explicitly, e.g. `value == null || value instanceof String`. In Spring AOP, `args(values)` binds the **whole list**; it does not know per-element null policies.

### 9.3. Raw types and unchecked casts can break a declaration's promise

```java
@SuppressWarnings({"rawtypes", "unchecked"})
static List<String> unsafe() {
    List raw = List.of(123);
    return raw; // Compiles with unchecked conversion, without checking elements.
}
```

This is a **counterexample** for type safety, not a pattern to use. The runtime list holds an `Integer` even though the caller statically holds a `List<String>`. `Method.getGenericParameterTypes()` still reports the `List<String>` declaration if that is the method contract; it does not prove the object holds `String`s.

When validation is an actual requirement, check contents at the appropriate boundary or use DTO/domain types that avoid type-parameter ambiguity.

### 9.4. `getClass().getTypeParameters()` is not the answer

```java
List<String> names = List.of("An");
System.out.println(names.getClass().getTypeParameters().length);
```

A concrete runtime `List` class may not even declare any formal type variable needed for inference; even when generic type variables exist, they are **not** the actual `String` type argument at the call site. Do not use `getTypeParameters()` on a runtime instance as a way to "recover `List<String>`".

### 9.5. Return-value generics have similar limitations

If a service returns `List<User>`, `@AfterReturning(returning="result")` can bind the returned reference; the advice does not automatically verify every `User` inside the list. If you only need to inspect, use `List<?>`/`Object` appropriately and avoid unverified generic casts. For `@Around`, `proceed()` returns `Object`; the advice must return a value compatible with the **declared return type** and must not swap the container object for a different type.

## 10. Pitfalls when reading generic metadata in Spring

| Issue | Cause | How to handle |
| --- | --- | --- |
| `jp.getArgs()[0].getClass()` does not contain `String` | Runtime `List` class undergoes generic erasure | Use declaration metadata for signature info; inspect elements to validate |
| `Collection<Invoice>` advice fails to filter contents | Spring does not match generic collection elements | Bind `Collection<?>` and check elements per policy |
| Empty list passes `allMatch` for `String`/`Integer` | No elements to falsify | Combine with `!isEmpty()` when policy requires non-empty |
| `null` causes `getClass()` error | `null` has no runtime class | Null-check first |
| Reflection sees type variable `T` instead of `String` | Reading generic interface/base method without resolving implementation binding | Use concrete target class context, `ResolvableType`, and Spring method resolution |
| `MethodSignature.getMethod()` points to the interface | JDK proxy operates on interface methods | Use `AopUtils.getMostSpecificMethod(...)` |
| Synthetic bridge method encountered | Java compiler generates bridge due to erasure/overriding | Use `BridgeMethodResolver` when user method is needed |
| `argNames` does not work | Insufficient parameter-name binding metadata or wrong name | Declare `argNames` accurately; configure `-parameters` if needed |
| Overloads `m(List<String>)` and `m(List<Integer>)` fail to compile | Both methods share the same erased signature | Choose distinct method names or use domain wrapper types |
| `@Around` returns a raw `List` containing wrong element types | Advice only preserves raw type, not the generic contract | Keep original value/collection; test domain contract |
| Proxy does not advise the method to inspect | Target is not a Spring bean, aspect is unregistered, or self-invocation | Check context, proxy, and pointcut |
| Switching to CGLIB fails to fix generic mismatch | Proxy mode does not reconstruct erased element types | Fix validation / API design |
| Logging entire generic payload | Data may be sensitive, expensive, or have `toString()` side effects | Redact; log only safe metadata |
| Async Future / Reactive Publisher generic `T` cannot be inferred from immediate payload | Container wrapper returned before payload is ready | Handle in async/reactive context while preserving wrapper contract |

### Verification workflow to avoid over-inference

1. Confirm the method is actually called through a **Spring AOP proxy** and the pointcut matches.
2. Decide whether you need the **declared generic signature** or the **runtime contents**.
3. Use `getArgs()` to get the actual value, checking for `null` and raw runtime interfaces.
4. Use `MethodSignature`/most-specific method/`ResolvableType` to read declared metadata when needed.
5. If element types matter, define an explicit policy for empty collections, null elements, mixed contents, and mutable data.
6. Do not use `Collection<T>`-typed advice as an automatic checker for all element types.
7. Account for bridge/interface methods when the target is a generic implementation.
8. Test Spring AOP integration under the real proxy mode with empty, null, mixed, and boundary data—not just a single happy-path sample.

## 11. Self-check questions

**1. Does Spring's `JoinPoint.getArgs()` return a reified `List<String>` object?** No. It returns the actual argument object; standard runtime Java `List`s do not retain the `String` generic type argument.

**2. If `Method.getGenericParameterTypes()[0]` returns `List<String>`, does that prove the list contains only `String`s?** No. It describes method declaration metadata, without checking runtime elements.

**3. Why is `Collection<Invoice>` in an advice signature insufficient to filter a runtime collection?** Because of type erasure, and Spring does not automatically iterate elements or decide null/empty policies.

**4. If you actually want to check elements inside a list, what should you use?** Bind `Collection<?>`/`List<?>` and inspect elements with `instanceof`/`Class.isInstance` per business policy.

**5. What does `allMatch(String.class::isInstance)` return on an empty list?** True; that is not proof that the list holds generic `String`s.

**6. Why does a JDK proxy sometimes provide only the interface `Method` in the signature?** The proxy implements the interface. When concrete metadata is needed, resolve the most-specific target method.

**7. What is a bridge method in the context of a Spring AOP generic target?** A method the compiler can generate to preserve polymorphism after erasure; reading signatures or annotations requires accounting for bridge resolution.

**8. Does `-parameters` restore `List<String>` runtime contents?** No. It retains Java parameter names; that is distinct from generic metadata and element type checking.

**9. Does setting `proxyTargetClass=true` make `args(...)` match `List<String>` elements automatically?** No. CGLIB does not change generic type erasure.

**10. Where should data validation responsibility live?** At boundary/service/domain validation with an explicit contract; advice can observe or enforce cross-cutting policies without inferring beyond what runtime supports.

## Official Spring documentation

- [Spring Framework — Declaring Advice: Advice Parameters and Generics](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Declaring Advice: binding args, advice parameter types](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework — Declaring Pointcuts: args and execution](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html)
- [Spring Framework 6.2 API — ResolvableType](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/ResolvableType.html)
- [Spring Framework 6.2 API — BridgeMethodResolver](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/BridgeMethodResolver.html)
- [Spring Framework — Proxying Mechanisms, JDK/CGLIB and self-invocation](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework 6.2 API — AopUtils.getMostSpecificMethod](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/aop/support/AopUtils.html)
