# Name Patterns, Subtypes, Overloads, and Parameter Lists in Spring AOP Pointcuts

## 1. Lesson Objectives

In Spring Framework, an `@Aspect` can use `execution(...)` expressions to select specific **method executions** on **Spring-managed beans**. When a service contains many similarly named methods, overloads, interface/class hierarchy implementations, and varying parameter lists, writing an accurate expression matters more than using an overly broad wildcard.

This lesson focuses on four method-selection techniques:

1. **Name patterns**: exact names, prefixes, suffixes, or `*` wildcards in method names.
2. **Subtypes**: the `+` suffix after a **type pattern** to include that type and its compatible subtypes/implementations.
3. **Overloads**: distinguishing methods with the **same name** based on **number and declared types of parameters**.
4. **Parameter lists**: distinguishing `()`, `(*)`, `(..)`, and mixed lists such as `(java.lang.String,int)` or `(java.lang.String,..)`.

After this lesson, you will be able to predict whether a `@Before` advice will run, instead of tweaking pointcuts by guesswork. You will also understand why **runtime argument values**, **Java compile-time overload resolution**, and **Spring AOP proxy invocation** are three separate concerns.

**Content boundary:** Covers only writing and verifying pointcuts in **proxy-based Spring AOP** using `@Aspect` annotation style, without AspectJ weaving outside Spring. Examples use **Java 17+**, **Spring Framework 6.2.x**, and Maven.

## 2. Conditions for a Pointcut to Actually Trigger Advice

`execution(...)` matches **method signatures**; calls are advised only when both bean and aspect are registered in Spring, AOP infrastructure is active, and callers go through a **Spring proxy**. A matching signature still produces no advice if calling an object created directly with `new`, calling `this.method()` internally, or when the proxy cannot intercept that method (such as `private`/`final` under class-based proxies). JDK proxies expose only methods on the proxied interfaces.

When testing the name/subtype/overload patterns below, always check **three separate questions**: which signature did Java select, does the expression match that signature, and does the invocation go through the proxy? Spring AOP is limited to method executions on Spring-managed beans.

## 3. Quick Reminder on `execution(...)` Syntax

Abbreviated form: `execution(modifiers? return-type declaring-type?.method-name(parameter-pattern))`; this is descriptive notation, and **the `?` is not a character you type into expressions**. Example:

~~~java
@Before("execution(public java.lang.String demo.TaskApi.lookup(java.lang.String))")
public void beforeLookup() {
    // Matches public method lookup(String) returning String on TaskApi.
}
~~~

The snippet above sits inside a registered `@Aspect`. `*` in name/type positions and `..` in package/parameter sections carry different meanings; the examples below examine each position in turn. Note `TaskApi+` in the **type pattern** to express subtypes, while `(*)` and `(..)` in the **parameter pattern** have different parameter-count boundaries.

## 4. Method Name Patterns: Exact, Prefix, Suffix, and Wildcard

### 4.1. Exact Name

~~~text
execution(* demo.TaskApi.lookup(..))
~~~

Selects method executions named **lookup** compatible with `TaskApi`; `(..)` allows any number and types of parameters. If `TaskApi` has three `lookup` overloads, all three can be selected.

### 4.2. Prefix

~~~text
execution(* demo.TaskApi.list*(..))
~~~

Names starting with **list**, such as `listAll` and `listByOwner`. Methods like `lookup` or `inspect` do not match merely by being on the same bean.

### 4.3. Suffix

~~~text
execution(* demo.TaskApi.*Status(..))
~~~

Names ending with **Status**, such as `getStatus` and `updateStatus`. Does not select `statusCode` because the suffix does not match.

### 4.4. Arbitrary Characters in the Middle

~~~text
execution(* demo.TaskApi.find*By*(..))
~~~

Selects names starting with **find**, followed by any segment, then **By**, then any segment. For example, `findOrderById` matches, whereas `findAll` does not.

### 4.5. Any Method Name

~~~text
execution(* demo.TaskApi.*(..))
~~~

The `*` in **name-pattern** removes the name constraint. This is convenient for debugging, yet can advise far too many methods in a real application.

**Safe way to read:** keep type and method name distinct: `demo.TaskApi.list*(..)` is a specific type combined with a method prefix; it does not mean Spring scans the entire `demo` package by bean name.

## 5. Package Scope and Package Directory Levels

The most common confusion is distinguishing `.` and `..` in the type part.

~~~text
execution(* demo.service.*.*(..))
~~~

Describes methods on types **directly in package** `demo.service`.

~~~text
execution(* demo.service..*.*(..))
~~~

Expands into **demo.service and subpackages** such as `demo.service.internal` and `demo.service.payment` when types/methods match.

| Actual type | `demo.service.*` | `demo.service..*` |
| --- | --- | --- |
| `demo.service.OrderService` | Matches type scope | Matches type scope |
| `demo.service.billing.BillingService` | No | Matches type scope |
| `demo.repository.OrderRepository` | No | No |
| `demo.service_internal.LegacyService` | No | No |

The table compares only **type-pattern matching**, without stating whether the corresponding bean has a proxy/advisor.

Do not confuse this with bean-name expressions. For example, `bean(*Service)` is a **Spring-specific pointcut designator** inspecting **bean names**, not part of `execution` and not implying class packages.

## 6. Subtypes: Role of `+` After a Type Pattern

In AspectJ-style type patterns used by Spring AOP, the **`+`** suffix denotes **the type written in the expression or any compatible subtype**, including subclasses and interface implementations.

Example:

~~~text
demo.TaskApi+
~~~

Read as `TaskApi` **and subtypes/implementations** of `TaskApi`, within pointcut semantics. This symbol is completely different from Java's string concatenation `+`: inside an annotation, it is solely a character within the Spring AOP expression.

When combined with `execution`:

~~~text
execution(* demo.TaskApi+.lookup(..))
~~~

the intent is to select matching executions of method **lookup** on `TaskApi` or its subtypes. This is useful when:

- multiple implementations of the same interface are registered as different beans;
- a sub-interface declares additional methods;
- a base class is extended by multiple service classes;
- you want a contract-level pointcut convention instead of listing every implementation.

**Not every match automatically guarantees a proxy.** If Spring uses a JDK dynamic proxy, methods intended to be called through the proxy must be declared on a proxied interface. If using CGLIB, methods must still be overridable and called through the proxy.

### 6.1. Distinguishing Two Patterns

~~~text
execution(* demo.TaskApi.lookup(..))
execution(* demo.TaskApi+.lookup(..))
~~~

The first line focuses on the named type `TaskApi`. The second explicitly expresses intent to include subtypes. In Spring AOP, an execution expressed via an interface can also apply to methods implemented in concrete classes; therefore, **do not claim the two expressions always produce different results** solely based on `+`. For complex hierarchies, empirical verification through Spring-managed proxies and target methods is essential.

### 6.2. Using `+` in Parameter Patterns

Suppose:

~~~java
package demo;

public class Payload {
}

public class UrgentPayload extends Payload {
}
~~~

These are **two illustrative classes placed in two separate files**, since Java allows only one public top-level class per file. If a service has two overloads:

~~~java
void update(Payload payload);
void update(UrgentPayload payload);
~~~

then:

~~~text
execution(* demo.TaskApi.update(demo.Payload+))
~~~

can select signatures with one parameter whose type is **Payload or a subtype of Payload**. `Payload+` is a **type pattern for the declared parameter type**, not "match only when the runtime argument is a subtype".

### 6.3. Comparing with `target(...)` and `this(...)`

Other pointcut designators select by objects present at invocation:

~~~text
target(demo.TaskApi)
this(demo.TaskApi)
~~~

In Spring AOP, **target(...)** inspects the target object and **this(...)** inspects the proxy object. Neither is syntax for selecting an overloaded method by signature; they are usually combined with `execution` when specific constraints are needed.

**Do not substitute `args(Payload)` for `Payload+` carelessly**: `args` concerns the **argument type at runtime**, whereas **execution** concerns the method signature. Two calls with the same runtime argument can match different `execution` pointcuts depending on which overload was selected beforehand.

## 7. Parameter Lists: `()`, `(*)`, `(..)`, and Mixed Forms

These rules must be remembered accurately:

| Parameter pattern | Meaning |
| --- | --- |
| `()` | **No** parameters |
| `(*)` | **Exactly one** parameter, any type |
| `(..)` | **0 or more** parameters, any types |
| `(java.lang.String)` | Exactly one parameter, declared type `String` |
| `(long)` | Exactly one primitive `long` parameter |
| `(java.lang.String,int)` | Exactly two parameters, strictly `String` then primitive `int` |
| `(*,java.lang.String)` | Exactly two parameters, first any type, second `String` |
| `(java.lang.String,..)` | First parameter `String`; followed by 0 or more parameters |
| `(..,int)` | Last parameter `int`; preceded by 0 or more parameters |

Suppose **TaskApi** has:

~~~java
String lookup(String code);
String lookup(long id);
String lookup(String code, int version);
~~~

Comparison:

| Pattern | lookup(String) | lookup(long) | lookup(String,int) |
| --- | --- | --- | --- |
| `lookup()` | No | No | No |
| `lookup(*)` | Yes | Yes | No |
| `lookup(..)` | Yes | Yes | Yes |
| `lookup(java.lang.String)` | Yes | No | No |
| `lookup(long)` | No | Yes | No |
| `lookup(java.lang.String,int)` | No | No | Yes |
| `lookup(java.lang.String,..)` | Yes | No | Yes |
| `lookup(*,int)` | No | No | Yes |
| `lookup(..,int)` | No | No | Yes |

**Parameter order matters.** `(String,int)` differs from `(int,String)`. If a method is declared `lookup(String,int)`, reversing the order in the expression will not match that method.

**Primitives differ from wrappers.** `lookup(long)` does not have declared parameter type `java.lang.Long`, even though Java performs autoboxing/unboxing at various call sites. To match accurately by signature, use the declared type.

### 7.1. Ellipsis (`...`)? No, Three Dots Do Not Mean Wildcard

Sometimes learners write `lookup(...)` like Java's varargs notation. In AspectJ pointcuts:

~~~text
lookup(..)
~~~

is the pattern for **any number of parameters**. Do not add a third dot to match all parameters.

### 7.2. Using `(*)` Is Not the Same as `(..)`

If a service has `void refresh()`, pattern `refresh(*)` does **not** match, whereas `refresh(..)` does. Likewise, for `refresh(String,int)`, `refresh(*)` does not match because there are two parameters.

Practical tip: if you want to apply advice to **every overload** of a name, start with `(..)`; if you need to distinguish overloads, specify exact types or exact parameter counts.

### 7.3. Varargs

The Java method:

~~~java
public void publish(String... events) {
    // ...
}
~~~

actually has array parameter type `String[]` in its method signature. Pattern `publish(..)` can cover this method, but do not interpret it as "varargs only". To select specifically a varargs/array method, verify the supported array type pattern `java.lang.String[]`.

Fragments in this section **illustrate signatures only** and do not replace source files in the runnable project below.

## 8. Overloads: Spring AOP Does Not Perform Overload Selection for Java

**Overloading** means multiple methods with the same name and different parameter lists. Example:

~~~java
void update(Payload payload);
void update(UrgentPayload payload);
~~~

When Java compiles:

~~~java
Payload value = new UrgentPayload();
service.update(value);
~~~

Overload **update(Payload)** is selected by the **compile-time type of variable `value`** (given the overloads above), even though the runtime object is **UrgentPayload**. Spring AOP does not alter Java overload resolution.

Conversely:

~~~java
service.update(new UrgentPayload());
~~~

the argument expression has compile-time type **UrgentPayload**, so Java selects overload **update(UrgentPayload)**.

Key points:

- **execution(...update(demo.Payload))** checks the **declared parameter type** of method `update(Payload)`.
- **execution(...update(demo.UrgentPayload))** checks the **declared parameter type** of `update(UrgentPayload)`.
- **execution(...update(demo.Payload+))** includes declared types `Payload` and compatible subtypes.
- **args(demo.UrgentPayload)** is a **runtime argument** type condition in Spring AOP; it does not mean Java chose overload `update(UrgentPayload)`.

An `UrgentPayload` instance can be passed to `update(Payload)`. Therefore, a pointcut using **args** can observe runtime type `UrgentPayload` on an invocation of signature `update(Payload)`, while an `execution` expression constraining the exact signature still identifies it as `update(Payload)`.

This is why many "pointcut picked the wrong overload" bugs actually stem from misunderstanding Java variable types at call sites.

## 9. Runnable Maven Example: Name Patterns, Subtypes, Overloads, and Parameters

We build a plain Spring Framework application with a service implementing a **sub-interface** and two **update** overloads with parent/child parameter types. The aspect defines multiple `@Before` pointcuts that **do not overlap** on the same call in the main scenario, keeping stdout order easy to verify.

Environment requirements:

- **JDK 17+**
- **Maven 3.9+**
- **Spring Framework 6.2.12**
- **AspectJ Weaver 1.9.24** on the classpath so Spring parses annotations/pointcuts.

Directory structure:

~~~text
spring-aop-signature-patterns/
├── pom.xml
└── src/main/java/demo/
    ├── TaskApi.java
    ├── ExtendedTaskApi.java
    ├── Payload.java
    ├── UrgentPayload.java
    ├── TaskService.java
    ├── PatternAspect.java
    ├── AppConfig.java
    └── App.java
~~~

### 9.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-signature-patterns</artifactId>
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
                <version>3.13.0</version>
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

`spring-context` provides `ApplicationContext` and pulls in Spring AOP. `aspectjweaver` is the required dependency for `@AspectJ` syntax in Spring AOP; the project **does not enable AspectJ weaving**.

### 9.2. Parent Interface and Sub-Interface

**src/main/java/demo/TaskApi.java**

~~~java
package demo;

public interface TaskApi {
    void listAll();
    void listByOwner(String owner);

    String lookup(String code);
    String lookup(long id);
    String lookup(String code, int version);

    void update(Payload payload);
    void update(UrgentPayload payload);

    void inspect();
}
~~~

**src/main/java/demo/ExtendedTaskApi.java**

~~~java
package demo;

public interface ExtendedTaskApi extends TaskApi {
    void extra();
}
~~~

**TaskApi** defines three `lookup` overloads, two `update` overloads, and two methods starting with **list**. **ExtendedTaskApi** is a subtype of `TaskApi` and adds `extra()`.

Because `ExtendedTaskApi extends TaskApi`, type pattern `demo.TaskApi+` covers both the `TaskApi` contract and compatible subtypes. Do not confuse **interface inheritance** with **component scanning**: Spring still needs the implementation bean.

### 9.3. Parent/Child Parameter Types

**src/main/java/demo/Payload.java**

~~~java
package demo;

public class Payload {

    private final String code;

    public Payload(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
~~~

**src/main/java/demo/UrgentPayload.java**

~~~java
package demo;

public class UrgentPayload extends Payload {

    public UrgentPayload(String code) {
        super(code);
    }
}
~~~

`UrgentPayload` extends `Payload` without overriding `code()`. This is a simple hierarchy for testing **Payload+** in parameter position. Custom annotations or special frameworks are unnecessary for establishing a subtype relationship.

### 9.4. Service Implementation

**src/main/java/demo/TaskService.java**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class TaskService implements ExtendedTaskApi {

    @Override
    public void listAll() {
        System.out.println("TARGET listAll");
    }

    @Override
    public void listByOwner(String owner) {
        System.out.println("TARGET listByOwner " + owner);
    }

    @Override
    public String lookup(String code) {
        System.out.println("TARGET lookup(String) " + code);
        return code;
    }

    @Override
    public String lookup(long id) {
        System.out.println("TARGET lookup(long) " + id);
        return Long.toString(id);
    }

    @Override
    public String lookup(String code, int version) {
        System.out.println("TARGET lookup(String,int) " + code + "/" + version);
        return code + ":" + version;
    }

    @Override
    public void update(Payload payload) {
        System.out.println("TARGET update(Payload) " + payload.code());
    }

    @Override
    public void update(UrgentPayload payload) {
        System.out.println("TARGET update(UrgentPayload) " + payload.code());
    }

    @Override
    public void extra() {
        System.out.println("TARGET extra");
    }

    @Override
    public void inspect() {
        System.out.println("TARGET inspect");
        this.listAll();
    }
}
~~~

Declaring `@Service` lets the bean be discovered via `@ComponentScan`. Method `inspect()` intentionally calls `this.listAll()` to demonstrate **self-invocation**: even though `listAll` matches `list*`, the internal call does not go through the proxy so no second advice runs.

### 9.5. Aspect Using Only the Target Signature Patterns

**src/main/java/demo/PatternAspect.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class PatternAspect {

    @Before("execution(* demo.TaskApi+.list*(..))")
    public void beforeList(JoinPoint jp) {
        System.out.println("AOP name " + jp.getSignature().getName());
    }

    @Before("execution(* demo.TaskApi+.lookup(java.lang.String))")
    public void beforeLookupString() {
        System.out.println("AOP lookup(String)");
    }

    @Before("execution(* demo.TaskApi+.lookup(long))")
    public void beforeLookupLong() {
        System.out.println("AOP lookup(long)");
    }

    @Before("execution(* demo.TaskApi+.lookup(java.lang.String,int))")
    public void beforeLookupTwo() {
        System.out.println("AOP lookup(String,int)");
    }

    @Before("execution(* demo.TaskApi+.update(demo.Payload+))")
    public void beforeUpdate() {
        System.out.println("AOP update(Payload+)");
    }

    @Before("execution(* demo.TaskApi+.extra(..))")
    public void beforeExtra() {
        System.out.println("AOP extra");
    }
}
~~~

The expressions demonstrate four requirements:

- **Name:** `list*` selects `listAll()` and `listByOwner(String)`.
- **Subtype in declaring type:** `TaskApi+` includes compatible subtypes; `extra()` exists in `ExtendedTaskApi` and is implemented in `TaskService`.
- **Overloads:** three `lookup` expressions have distinct **String**, **long**, and **String,int** parameter lists.
- **Subtype in parameter:** `update(demo.Payload+)` covers both the `Payload`-declared overload and the `UrgentPayload`-declared overload.

The pointcuts in the example are chosen so **each external call maps to a single advice**, avoiding having to guess execution order when multiple advices in one aspect match together.

**@Aspect** declares advice, and **@Component** lets Spring register the aspect as a bean. Do not assume `@Aspect` automatically turns an arbitrary object outside Spring into an advisor.

### 9.6. Enabling AOP and Component Scan

**src/main/java/demo/AppConfig.java**

~~~java
package demo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy
public class AppConfig {
}
~~~

In this plain Spring Framework example:

- **@Configuration**: Java configuration source.
- **@ComponentScan**: registers `TaskService` and `PatternAspect`.
- **@EnableAspectJAutoProxy**: enables infrastructure for `@AspectJ` advices and Spring AOP proxies.

Because Spring AOP automatically uses a **JDK dynamic proxy** when the target implements interfaces, clients should retrieve the bean by `TaskApi` or `ExtendedTaskApi`, rather than casting to `TaskService`.

### 9.7. Main to Verify Signatures and Behavior

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            ExtendedTaskApi api = context.getBean(ExtendedTaskApi.class);
            System.out.println("IS_PROXY " + AopUtils.isAopProxy(api));

            api.listAll();
            api.listByOwner("team");

            System.out.println("RESULT " + api.lookup("A-1"));
            System.out.println("RESULT " + api.lookup(7L));
            System.out.println("RESULT " + api.lookup("A-2", 3));

            api.update(new Payload("B-1"));
            api.update(new UrgentPayload("U-1"));

            Payload declaredParent = new UrgentPayload("U-2");
            api.update(declaredParent);

            api.extra();
            api.inspect();
        }
    }
}
~~~

Three `lookup(...)` calls verify overloads; three `update(...)` calls prove Java selects overloads by **compile-time type**, not solely by runtime object.

Run from the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

### 9.8. Expected Logical Stdout

~~~text
IS_PROXY true
AOP name listAll
TARGET listAll
AOP name listByOwner
TARGET listByOwner team
AOP lookup(String)
TARGET lookup(String) A-1
RESULT A-1
AOP lookup(long)
TARGET lookup(long) 7
RESULT 7
AOP lookup(String,int)
TARGET lookup(String,int) A-2/3
RESULT A-2:3
AOP update(Payload+)
TARGET update(Payload) B-1
AOP update(Payload+)
TARGET update(UrgentPayload) U-1
AOP update(Payload+)
TARGET update(Payload) U-2
AOP extra
TARGET extra
TARGET inspect
TARGET listAll
~~~

This is the **expected logical output** of the sample code, omitting Maven and Spring logging. When running in practice, verify the **AOP** before **TARGET** order for matching methods, and confirm **no `AOP name listAll`** appears for the `this.listAll()` call inside `inspect`.

### 9.9. Analysis of Representative Calls

**listAll and listByOwner.** Both methods start with `list`, so they match `list*(..)`. `lookup` methods do not match the `list` prefix.

**lookup("A-1").** The argument expression has compile-time type `String`; Java selects overload `lookup(String)`. Advice `beforeLookupString` runs.

**lookup(7L).** Literal `7L` is a primitive `long`, so overload `lookup(long)` is selected and its advice runs.

**lookup("A-2", 3).** Has two parameters `String` and `int`, so only expression `lookup(java.lang.String,int)` matches among the three lookup advices.

**update(new UrgentPayload("U-1")).** Java selects overload `update(UrgentPayload)`, and `Payload+` matches the declared subtype.

**Payload declaredParent = new UrgentPayload("U-2"); api.update(declaredParent).** Even though the runtime object is `UrgentPayload`, Java selects `update(Payload)` based on the variable's type. `Payload+` still matches because it includes `Payload`. The log proves the actual chosen method is `update(Payload)`.

**api.extra().** Sub-interface `ExtendedTaskApi` declares `extra`; `TaskApi+` lets an expression referencing the parent interface include compatible subtypes.

**api.inspect().** No advice selects the name `inspect`. Inside the target, `this.listAll()` still prints `TARGET listAll` without passing through the Spring proxy to trigger `listAll` advice again.

## 10. Match Prediction Table from the Program

The table evaluates **method signatures** and does not replace bean/proxy conditions on its own.

| Pattern | listAll() | lookup(String) | lookup(long) | lookup(String,int) | update(Payload) | update(UrgentPayload) |
| --- | --- | --- | --- | --- | --- | --- |
| `execution(* demo.TaskApi+.list*(..))` | Yes | No | No | No | No | No |
| `execution(* demo.TaskApi+.lookup(..))` | No | Yes | Yes | Yes | No | No |
| `execution(* demo.TaskApi+.lookup(*))` | No | Yes | Yes | No | No | No |
| `execution(* demo.TaskApi+.lookup(java.lang.String))` | No | Yes | No | No | No | No |
| `execution(* demo.TaskApi+.lookup(java.lang.String,int))` | No | No | No | Yes | No | No |
| `execution(* demo.TaskApi+.update(demo.Payload))` | No | No | No | No | Yes | No |
| `execution(* demo.TaskApi+.update(demo.UrgentPayload))` | No | No | No | No | No | Yes |
| `execution(* demo.TaskApi+.update(demo.Payload+))` | No | No | No | No | Yes | Yes |
| `execution(* demo.TaskApi+.*(..))` | Yes | Yes | Yes | Yes | Yes | Yes |

When debugging an expression, build your own table for each method and type pattern. If it gets hard to read, split broad pointcuts into named pointcuts.

## 11. Named @Pointcut to Avoid Repeating Conditions

A large aspect can reuse conditions multiple times:

~~~java
@Pointcut("execution(* demo.TaskApi+.list*(..))")
public void listing() {
}

@Pointcut("execution(* demo.TaskApi+.lookup(..))")
public void lookups() {
}

@Pointcut("listing() || lookups()")
public void reads() {
}
~~~

These are **sample methods meant for an `@Aspect` class** importing `org.aspectj.lang.annotation.Pointcut`, not a standalone Java file. In a complete aspect, advice can reference:

~~~java
@Before("reads()")
public void beforeRead(JoinPoint jp) {
    System.out.println(jp.getSignature().getName());
}
~~~

If you add this advice to the running `PatternAspect` in section 9, some methods will have **multiple matching advices**, so stdout will no longer match the original. Replace the old advices with named-pointcut advice or use a separate test context.

Also, do not confuse the **visibility of the `@Pointcut` method** with the **modifier of business methods**. A `private void reads()` named pointcut can still select public service methods; conversely, an expression with `execution(public ...)` is what constrains the modifier of selected methods.

## 12. How to Combine Condition Groups

### 12.1. Selecting Public `lookup` on Subtypes

~~~text
execution(public * demo.TaskApi+.lookup(..))
~~~

The expression specifies:

- public method;
- any return type;
- declaring type in the compatible `TaskApi` family;
- exact name `lookup`;
- any parameter count and types.

Thanks to `(..)`, new overloads added later can also match without updating the expression.

### 12.2. Selecting `list*` with Exactly One Parameter

~~~text
execution(* demo.TaskApi+.list*(*))
~~~

In the example, `listByOwner(String)` matches while `listAll()` does not. If `list*(..)` is chosen, both match.

### 12.3. Selecting `update` Whose Parameter Is `Payload` or Subtype

~~~text
execution(* demo.TaskApi+.update(demo.Payload+))
~~~

This is a representative form for **subtypes in parameter signatures**. It does not mean an nonexistent Java method can be advised merely because an argument object has type `Payload`.

### 12.4. Constraining by Spring Bean Name

Suppose multiple beans implement `TaskApi` and you want only the bean named `taskService`:

~~~text
execution(* demo.TaskApi+.lookup(..)) && bean(taskService)
~~~

`bean(...)` is a **Spring AOP-specific** designator matching bean names. It is not a Java method name and not a subtype rule. With `@Service TaskService` and normal component scanning, the default bean name is `taskService`; if registered under another name, this condition may not match.

### 12.5. Runtime Argument Condition

~~~text
execution(* demo.TaskApi+.update(..))
&& args(demo.UrgentPayload)
~~~

The combination states: method named `update` on a matching type, and **runtime argument** is `UrgentPayload`. This can match an `update(Payload)` call passed an `UrgentPayload` instance. Do not equate it with an expression selecting only the declared `update(UrgentPayload)` overload.

When writing `@Before`, you can concatenate the two lines into a single Java string; for example:

~~~java
@Before(
    "execution(* demo.TaskApi+.update(..)) && " +
    "args(demo.UrgentPayload)"
)
public void beforeUrgent() {
    // ...
}
~~~

This is an **illustrative fragment**; if placed beside existing `update` advice, a matching invocation gets an extra advice so logs change.

## 13. Java Inheritance and Limits of Subtype Selection

### 13.1. Interface Extending Interface

~~~java
interface BaseApi {
    void run();
}

interface ExtendedApi extends BaseApi {
    void extra();
}
~~~

A pattern with suffix `BaseApi+` denotes `BaseApi` or subtypes. However, if a service bean is exposed only via a JDK proxy that does not expose `ExtendedApi`, clients cannot arbitrarily call `extra()` on the `BaseApi` interface. In the main example, the bean implements **ExtendedTaskApi** and the client retrieves **ExtendedTaskApi.class**.

### 13.2. Class Extending Class

~~~java
class BaseProcessor {
    public void process() {
    }
}

class SpecialProcessor extends BaseProcessor {
    public void extra() {
    }
}
~~~

A type pattern with suffix `BaseProcessor+` covers matching subclasses. Yet for **Spring AOP** to intercept methods on a class-based proxy, the target class/methods must still allow subclassing/overriding and callers must go through the proxy. Do not use inheritance patterns expecting to intercept `final`, `private`, or constructors.

### 13.3. Different Packages and Non-Visible Methods

If a subclass resides in a different package, a package-private method on the superclass is not visible to the subclass; CGLIB cannot override it normally. The subtype `+` expression **does not erase Java visibility constraints**.

### 13.4. Hierarchy Does Not Mean All Overloads Are Declared in One Place

A sub-interface can add a method with the same name as one in the parent interface but different parameters. From Java's perspective, these are still separate overloads. To select all, use `name(..)` with an appropriate type scope; to select one specific overload, specify its exact parameter types.

## 14. Common Corner Cases

### 14.1. Generic Types and Bridge Methods

If an interface has:

~~~java
interface Repository<T> {
    T save(T value);
}
~~~

And a class implements `Repository<String>`, the compiler can generate a **bridge method** to preserve compatibility after type erasure. Do not assume a pointcut writing generic type arguments can distinguish every `List<String>` from `List<Integer>` at runtime. When using complex generic interfaces, run real integration tests on the proxy and Spring-resolved signatures.

### 14.2. Varargs Are Arrays in Method Signatures

~~~java
void publish(String... items);
~~~

At the JVM level, the method's parameter type is `String[]`. `publish(..)` matches arbitrary parameter lists, without meaning "varargs methods only". To select a specific varargs/array method, check supported array type patterns and the actual signature.

### 14.3. Return Types Do Not Participate in Java Overload Resolution

Java **does not allow** defining two overloads with the same name and parameter list differing **only by return type**:

~~~text
String read(String id)
int read(String id)
~~~

This description is **invalid if both are placed in one class/interface**. In an `execution` pattern you can filter by return type, yet that is not how Java distinguishes two overloads in source code.

### 14.4. Using `this()` and `target()` with Proper Spring AOP Semantics

In Spring AOP, `this(demo.SomeType)` inspects the **proxy object**, while `target(demo.SomeType)` inspects the **target object**. With a JDK dynamic proxy, the proxy may not be an instance of the implementation class even though the target is.

If your condition concerns the **runtime implementation type** rather than signature, consider `target`, but do not use it in place of a specific overload expression when the requirement depends on declared parameter types.

### 14.5. Spring Boot Differs from Plain Spring Framework in Auto-Configuration

In the plain Spring Framework Maven example, `@EnableAspectJAutoProxy` is declared directly. Spring Boot can enable auto-proxying through the appropriate starter/auto-configuration and has its own proxy-type settings. When copying expressions into a Boot application, verify the actual beans, proxy types, and AOP config rather than assuming all contexts behave identically.

## 15. Common Errors and Fixes

| Symptom | Common reason | How to check |
| --- | --- | --- |
| Both `lookup(String)` and `lookup(long)` are advised when only one overload was wanted | `lookup(..)` or `lookup(*)` is too broad | Use declared parameter type `java.lang.String` or `long` |
| Two-parameter overload is not advised | Used `(*)` | Use `(..)` or `(java.lang.String,int)` |
| `lookup(java.lang.Long)` does not match `lookup(long)` | Primitive vs. wrapper difference | Fix to `long` |
| Aspect misses methods on sub-interface | Type pattern too narrow or method not on proxied interface | Check `+` subtype, concrete bean, and proxied interfaces |
| Method gets `UrgentPayload` argument yet logs `Payload` overload | Overload chosen by variable's compile-time type | Check which method Java actually picked; distinguish `execution` and `args` |
| Package-based expression misses subpackages | Confused `.*` with `..*` | Fix the declaring type pattern |
| Advice applies to too many methods | Name pattern `*` or `(..)` too broad | Narrow method name, type, or parameter list |
| `@Aspect` exists yet no logs appear | Aspect is not a Spring bean or AOP is not enabled | `@Component`/`@Bean`, component scan, `@EnableAspectJAutoProxy` |
| Advice does not run on `this.listAll()` | Self-invocation bypasses proxy | Extract call to another Spring bean or call via dependency |
| CGLIB does not intercept `private`/`final` | Cannot be overridden | Design an interceptable entry method |
| Bean is a proxy yet desired advice does not run | Proxy may exist due to another advisor; pointcut didn't match | Inspect signature and observe specific advice |
| Advice appears twice | Two advisors both match or method called via proxy twice | Check overlapping pointcuts and actual call paths |
| Used `call(...)` and got parse error | Spring AOP does not support `call` join points | Use `execution`, understand proxy boundaries |
| Selecting overloaded method by Java variable name | Variable names are not part of method parameter type signatures | Filter by type/count, not variable name |

## 16. Three-Layer Debugging Workflow: Signature, Proxy, Invocation

**Step 1 — Write down the real signature.** For example, `String lookup(String,int)` has return `String`, name `lookup`, and two parameters `String` then `int`. An expression like `lookup(*)` definitely will not match because it expects exactly one parameter.

**Step 2 — Distinguish class/interface and subtypes.** Check which interfaces the bean actually implements, whether the method appears only on a sub-interface or on the parent interface, and whether `+` is needed to express the intended hierarchy scope.

**Step 3 — Inspect the bean obtained from Spring context.** Use `AopUtils.isAopProxy(bean)` in an integration test, while remembering `true` does not prove a specific advice matched.

**Step 4 — Call each overload individually from outside the proxy.** Log the signature in both advice and target. With section 9's code, each `lookup` overload has its own advice, allowing direct match verification.

**Step 5 — Test a compile-time parent reference too.** Assign `Payload declaredParent = new UrgentPayload(...)`, call `update(declaredParent)`; verify the actual overload is `update(Payload)`.

**Step 6 — Test a method outside the pointcut.** For example, `inspect()` has no advice, even though it calls `this.listAll()`. This shows that match conditions and invocation paths are two separate things.

**Step 7 — When multiple advices exist, check ordering and overlap.** Do not rely on declaration order of `@Before` methods in the same class to infer log order. If deterministic order is needed, design and configure advisor/aspect ordering explicitly.

## 17. Self-Guided Exercises

**Exercise 1 — Replace `list*` with a suffix wildcard.** Add `getStatus()` and `updateStatus()` to the interface/service, then try:

~~~text
execution(* demo.TaskApi+.*Status(..))
~~~

Predict that those two methods match, while `listAll()` does not.

**Exercise 2 — Restrict `list` to exactly one parameter.** Replace `list*(..)` with:

~~~text
execution(* demo.TaskApi+.list*(*))
~~~

Rerun: `listByOwner(String)` is advised; `listAll()` is not advised.

**Exercise 3 — Use `lookup(..)` to cover overloads.** Replace the three `lookup` advices with one advice:

~~~java
@Before("execution(* demo.TaskApi+.lookup(..))")
public void beforeAnyLookup(JoinPoint jp) {
    System.out.println("AOP lookup " + jp.getSignature().toShortString());
}
~~~

This is a **replacement fragment**; do not keep it alongside the three old `lookup` advices if you want to preserve the lesson's log counts. All `lookup` overloads can be selected.

**Exercise 4 — Select only `update(UrgentPayload)`.** Replace `update(demo.Payload+)` with:

~~~text
execution(* demo.TaskApi+.update(demo.UrgentPayload))
~~~

Predict that only invocations of the `update(UrgentPayload)` overload are advised. Placing an `UrgentPayload` object into a variable declared as `Payload` does **not** make Java change the overload.

**Exercise 5 — Add a runtime argument condition.** Use `args(demo.UrgentPayload)` alongside `execution` for `update`, then call the `update(Payload)` overload with a runtime `UrgentPayload`. Observe the difference between passed type and selected signature.

**Exercise 6 — Create another Spring bean implementing `TaskApi`.** Compare the `TaskApi+` type pointcut with `bean(taskService)`. When multiple beans share an interface, select the bean explicitly during injection; avoid letting `NoUniqueBeanDefinitionException` disrupt the pointcut experiment.

## 18. Signature-Based Pointcut Design Checklist

- Have you identified clearly whether the target is **name**, **hierarchy**, **overload**, or **runtime argument**?
- Does the type pattern need the **`+`** subtype suffix?
- Is the method name pattern too broad (`*`) or too narrow?
- Are `()`, `(*)`, and `(..)` used accurately for parameter counts?
- Are declared parameter types exact on **primitive/wrapper** and order?
- For overloads, have you separated **compile-time overload resolution** from runtime object types?
- Does the bean's Java interface/class expose the necessary methods via the proxy?
- Are both service and aspect inside the AOP-configured **Spring ApplicationContext**?
- Do test calls go through the proxy rather than `this.method()` or `new` objects?
- Have you tested at least one **matching** method, one **non-matching** method, and one overloaded method?
- If multiple advisors overlap, have you verified actual advice behavior and ordering?

## 19. Self-Assessment Questions

**1. How does `list*(..)` differ from `list*()`?**

The first covers methods starting with `list` with any number of parameters; the second selects only methods starting with `list` that have **zero parameters**.

**2. Does `+` in `TaskApi+` mean adding a method?**

No. It belongs to the type pattern, meaning the specified type plus compatible subtypes/implementations.

**3. Can `lookup(*)` select `lookup(String,int)`?**

No. `(*)` requires exactly one parameter, whereas `lookup(String,int)` has two.

**4. Does `lookup(String,..)` select `lookup(String)` and `lookup(String,int)`?**

Yes, because it requires a leading `String` followed by 0 or more parameters.

**5. Do both overloads `update(Payload)` and `update(UrgentPayload)` match `Payload+`?**

Yes, if `Payload` is the superclass of `UrgentPayload` and the expression places that type pattern in the parameter position.

**6. Given `Payload p = new UrgentPayload()`, which overload does Java choose for `update(p)`?**

The `update(Payload)` overload, based on the compile-time type of variable `p`, even though the runtime object is `UrgentPayload`.

**7. Is `args(UrgentPayload)` equivalent to the `update(UrgentPayload)` overload?**

No. `args` inspects the runtime argument type, whereas `execution` inspects the declared method signature.

**8. Why does Spring AOP not intercept `this.listAll()` even though the method matches the wildcard?**

Internal `this` calls bypass the AOP proxy; signature matching alone is not enough for advice to run.

**9. How does type pattern `demo.service.*` differ from `demo.service..*`?**

The first refers to types in the direct package; the second expands to subpackages as well.

**10. Which pattern should you choose if the goal is every overload named `lookup`?**

Use `execution(* demo.TaskApi+.lookup(..))` along with necessary type/bean conditions.

## 20. Official Documentation

- Spring Framework — **Declaring a Pointcut**: https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html
- Spring Framework — **@AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework — **Declaring Advice**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — **Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Eclipse AspectJ — **Pointcut Semantics, Type/Subtype Patterns** (syntax reference used by Spring): https://eclipse.dev/aspectj/doc/released/progguide/semantics-pointcuts.html

**Conclusion:** When selecting methods in Spring AOP, read **method name**, **type hierarchy** (including `+` if needed), **overloads**, and **parameter patterns** as distinct constraints. A pointcut with a valid signature still triggers advice only when Spring manages the bean, creates a suitable proxy, and the call actually passes through that proxy.
