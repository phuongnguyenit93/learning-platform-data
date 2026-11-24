# execution to Select Bean Methods by Signature in Spring AOP

## 1. Lesson Objectives

In **Spring AOP**, a pointcut determines **which method executions of a Spring-managed bean** can trigger advice. Among the pointcut designators that Spring supports, **execution(...)** is the most common choice when you need to select methods based on their **method signature**: access modifier, return type, declaring class/interface, name, and parameter type list.

After this lesson, you will be able to:

1. Read and write **execution(...)** in full or abbreviated form.
2. Distinguish between the **\*** and **..** wildcards when used in types, method names, packages, and parameter lists.
3. Write pointcuts that select a specific method, a group of method names, or an entire service package in **Spring ApplicationContext**.
4. Explain why **execution** relies on declared parameter types, unlike **args(...)** which relies on runtime arguments.
5. Use **@Pointcut** to name an expression and reuse it in **@Before**.
6. Run a Java 17+ project with matching and non-matching examples, inspect log order, and diagnose limitations caused by Spring AOP proxies.

**Scope:** Focuses strictly on **Spring Framework @AspectJ-style Spring AOP**, without moving into general AspectJ weaving concepts. Even when using AspectJ pointcut syntax, Spring AOP in this lesson still operates via **proxies** and only handles **method execution join points on Spring beans**.

## 2. What Does execution(...) Select?

Imagine a client calling a Spring bean:

~~~text
Client
  |
  | calls method on bean injected by Spring
  v
Spring AOP proxy
  |
  +-- advisor evaluates execution(...) expression
  |      |
  |      +-- method signature matches -> advice can run
  |      +-- no match                 -> this advice does not run
  |
  v
Target method executes
~~~

The expression does not directly modify the method body. It is a **filter for method executions** to which advice can be applied. For example:

~~~java
@Before("execution(* demo.OrderApi.create(..))")
public void beforeCreate() {
    System.out.println("Before create");
}
~~~

This pointcut denotes method-execution join points supported by Spring AOP whose signature matches the **create** method on **demo.OrderApi**, regardless of return type or number of parameters. If a call to `create` goes through a proxy configured by Spring with the corresponding advisor, the advice can run before the target.

Conditions to distinguish:

- **Validly parsed expression**: the execution syntax is understood by Spring's AspectJ pointcut parser.
- **Signature match**: the method signature satisfies the expression.
- **Eligible bean**: the bean is a Spring-managed bean and is considered by Spring AOP for applying advisors.
- **Invocation via proxy**: the caller goes through the proxy object at an interceptable point.
- **Advice runs**: all of the above conditions hold, plus any other runtime conditions if the pointcut is combined with dynamic designators.

A valid expression can still produce no logs if the bean is not in the ApplicationContext, the advice is not registered, or the method is called via **this.method()** inside the target.

## 3. Full Syntax of execution

The general form presented in Spring documentation is as follows:

~~~text
execution(
    modifiers-pattern?
    ret-type-pattern
    declaring-type-pattern?name-pattern(param-pattern)
    throws-pattern?
)
~~~

The **?** in the diagram above indicates that the component is **optional**, **not a character you need to type** into every pointcut.

| Component | Role | Example |
| --- | --- | --- |
| **modifiers-pattern?** | Constrains the method modifier, when needed | public |
| **ret-type-pattern** | Return type of the method; **required** | void, java.lang.String, * |
| **declaring-type-pattern?** | Class/interface or type pattern owning the method | demo.OrderApi. |
| **name-pattern** | Method name, may contain wildcards | create, get*, * |
| **param-pattern** | Parameter types and count, **required** in parentheses | (), (java.lang.String), (*), (..) |
| **throws-pattern?** | Constrains exception types declared in the throws clause | Only used when truly needed to filter checked-exception signatures |

In real code, the expression is usually written on a single line:

~~~java
execution(public java.lang.String demo.OrderApi.create(java.lang.String))
~~~

Reading from left to right:

1. **public**: the method must be public.
2. **java.lang.String**: the declared return type must be String.
3. **demo.OrderApi.**: selects methods described through the OrderApi type/interface in the demo package.
4. **create**: exact name.
5. **(java.lang.String)**: the method has **exactly one parameter declared as type String**.

The dot after **demo.OrderApi** is the separator between the **declaring type** and the **method name**, not an arbitrary character. If you do not need to restrict the method to a specific type, you can omit the declaring type part and use only the method name.

These components are designed to select methods by **declaration**. They do not compare argument values like an order code equal to "A-123"; filtering by runtime values requires a different mechanism with specific conditions and a clear understanding of proxy effects.

## 4. Understanding * and .. Accurately

### 4.1. * in the Return Type

~~~java
execution(* demo.OrderApi.create(..))
~~~

The **\*** in the **ret-type-pattern** position means **any return type**, including void. If you want to select only methods returning String:

~~~java
execution(java.lang.String demo.OrderApi.create(..))
~~~

If you want to select only methods returning void:

~~~java
execution(void demo.OrderApi.cancel(..))
~~~

The return type part must reflect the **return type declared in the method signature**, not the type of an object that a code branch might return at runtime. For example, a method declared to return **Object** that returns a String is not selected just because the expression specifies **java.lang.String**.

### 4.2. * in the Method Name

~~~java
execution(* demo.OrderApi.get*(..))
~~~

Selects methods on OrderApi whose name starts with **get**. Wildcards can be used in the middle/end of a name to build a naming pattern, for example:

~~~java
execution(* demo.OrderApi.*Status(..))
~~~

Selects methods whose name ends with **Status**.

Do not confuse a pointcut wildcard with the multiplication operator in Java. The expression is inside an **annotation string** and is interpreted by the pointcut parser.

### 4.3. .. in the Parameter List

Three forms to remember:

~~~text
()   -> no parameters
(*)  -> exactly one parameter, any type
(..) -> zero, one, or more parameters, of any types
~~~

Examples:

~~~java
execution(* demo.OrderApi.status())
execution(* demo.OrderApi.create(*))
execution(* demo.OrderApi.create(..))
~~~

If the actual method is **String create(String id)**:

- **create()** does not match because there are no parameters.
- **create(*)** matches because there is exactly one parameter.
- **create(..)** matches because it accepts any number of parameters, including one.

If you want exactly one String parameter, use:

~~~java
execution(* demo.OrderApi.create(java.lang.String))
~~~

If you want two parameters, the first of any type and the second String:

~~~java
execution(* demo.OrderApi.someMethod(*,java.lang.String))
~~~

This is a **syntax example**, not a claim that the OrderApi interface in the section 7 example actually has a **someMethod** method.

### 4.4. .. in Package/Type Patterns

~~~java
execution(* demo.service.*.*(..))
~~~

Selects methods whose signatures belong to types matching the pattern directly in the **demo.service** package, without automatically expanding into all subpackages.

~~~java
execution(* demo.service..*.*(..))
~~~

Allows selecting types in **demo.service** and its subpackages below. Pay attention to the position of **..**: here it is in **declaring-type-pattern**, not the parameter list.

| Pattern | What is being expanded? |
| --- | --- |
| **demo.service.*.*(..)** | Types directly in package demo.service and any method name/parameter count |
| **demo.service..*.*(..)** | Types in demo.service or its subpackages and any method/parameter count |
| **demo.OrderApi.*(..)** | Any method name on type OrderApi, any number of parameters |
| **demo.OrderApi.get*(..)** | Methods whose names start with get |
| **demo.OrderApi.create(..)** | Method named create, any number of parameters |
| **demo.OrderApi.create()** | Method create with **no** parameters |

Do not use **..** vaguely as a whole-string wildcard. In a **parameter pattern**, it means **any number of parameters**; in a **type pattern**, it describes package/type levels according to AspectJ syntax.

## 5. Common Expressions Used with Spring Beans

| Method selection requirement | Expression |
| --- | --- |
| Every interceptable public method | **execution(public * *(..))** |
| A create method with exactly one String argument | **execution(* demo.OrderApi.create(java.lang.String))** |
| Every overload of create, any return type | **execution(* demo.OrderApi.create(..))** |
| A method with no parameters | **execution(* demo.OrderApi.status())** |
| Void-returning method named cancel taking a primitive long | **execution(void demo.OrderApi.cancel(long))** |
| Every method of the OrderApi interface/type | **execution(* demo.OrderApi.*(..))** |
| Methods starting with find on OrderApi | **execution(* demo.OrderApi.find*(..))** |
| Every public method of services in a specific package | **execution(public * demo.service.*.*(..))** |
| Every method in the service package and subpackages | **execution(* demo.service..*.*(..))** |

All expressions in the table describe the **signature**, not which beans Spring actually has. If the application does not register matching services, or calls bypass the proxy, no AOP calls will be processed.

**Note on primitives and wrappers**: a **long** parameter in a signature is not the same as a **java.lang.Long** parameter. If a method is defined as **cancel(long id)**, use **(long)** rather than **(java.lang.Long)** when you want to match the declared parameter type accurately. Autoboxing at a Java call site does not turn the method signature into Long.

## 6. Spring AOP-Specific Constraints

### 6.1. Only Selects Method Executions on Spring-Managed Beans

Spring AOP does not perform AspectJ compiler weaving. It does not intercept **field access**, **constructor execution**, or arbitrary objects created with **new**. A pointcut such as:

~~~java
execution(* demo.OrderApi.*(..))
~~~

does not mean every Java call to an object implementing OrderApi is controlled by the aspect. There must be a Spring-managed bean exposed through a proxy when a matching advisor exists.

### 6.2. JDK Proxy and CGLIB Proxy

**JDK dynamic proxy** works by interface. Calls to public interface methods can be intercepted by Spring AOP. Methods that only exist on the implementation and are not part of the proxied interface are not exposed through that JDK proxy.

**CGLIB class-based proxy** creates a subclass so it can intercept public methods, and under appropriate conditions protected or package-visible methods can also be overridden. However, CGLIB cannot override **private** or **final** methods, nor can it subclass a final class.

Therefore:

~~~java
execution(public * demo.OrderApi.*(..))
~~~

is a controllable choice for a public service interface. If an expression omits the public modifier, it does not bypass the technical limitations of proxies on its own.

### 6.3. Self-Invocation Still Bypasses Advice

If **OrderServiceImpl.outer()** calls **this.create(id)**, that internal call does not go through the proxy. Even though `create` matches the signature in the execution expression completely, Spring AOP does not automatically run advice again for the internal call.

Distinguish between:

- **Signature match**: `create` matches the expression.
- **Proxy invocation**: the caller invokes `create` through the Spring proxy.
- **Advice execution**: only happens when there is a matching call that the proxy can intercept.

### 6.4. Do Not Use call(...) as a Replacement

In **native AspectJ weaving**, execution and call join points can be distinguished. However, **Spring AOP only supports method execution join points** and does not support **call(...)** or weaving-only pointcut designators. Using a pointcut designator not supported by Spring can cause an **IllegalArgumentException** when Spring parses the configuration.

In this lesson, focus on **execution(...)** rather than trying to work around self-invocation with a `call(...)` expression.

## 7. Runnable Java 17+ Example: Three Matching Signatures, One Non-Matching Internal Call

The example uses **Spring Framework 6.2.12**, **Java 17+**, **Maven 3.9+**, and **aspectjweaver 1.9.24**, without Spring Boot. We will have a Spring service with four methods:

- **create(String)** — advice selects by exact signature, with public + return String + parameter String.
- **cancel(long)** — advice selects exact **public void** + **long**.
- **find(String)** — advice uses wildcard **\*** for return type and **(..)** for parameters.
- **outer(String)** — calls **this.create(String)** from inside the target to contrast proxy limitations.

### 7.1. Project Structure

~~~text
spring-aop-execution/
├── pom.xml
└── src/main/java/demo/
    ├── OrderApi.java
    ├── OrderServiceImpl.java
    ├── SignatureAspect.java
    ├── AppConfig.java
    └── App.java
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-execution</artifactId>
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

**spring-context** includes the container infrastructure and pulls in the required Spring AOP modules. **aspectjweaver** provides types and the parser supporting AspectJ-style pointcuts. This is still **proxy-based Spring AOP**, not a project performing AspectJ weaving.

### 7.3. Service Interface: Signatures the Pointcut Will Select

**src/main/java/demo/OrderApi.java**

~~~java
package demo;

public interface OrderApi {
    String create(String id);
    void cancel(long id);
    String find(String id);
    void outer(String id);
}
~~~

All methods are public according to Java interface rules. This is the contract that a JDK proxy can expose.

**create(String)**, **cancel(long)**, and **find(String)** have different signatures in terms of name, return type, and argument type. Compare each method with its corresponding expression to see why the advice is selected.

### 7.4. Implementation with a Self-Invocation

**src/main/java/demo/OrderServiceImpl.java**

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class OrderServiceImpl implements OrderApi {

    @Override
    public String create(String id) {
        System.out.println("SERVICE create " + id);
        return "created:" + id;
    }

    @Override
    public void cancel(long id) {
        System.out.println("SERVICE cancel " + id);
    }

    @Override
    public String find(String id) {
        System.out.println("SERVICE find " + id);
        return id;
    }

    @Override
    public void outer(String id) {
        System.out.println("SERVICE outer " + id);
        this.create(id);
    }
}
~~~

**@Service** allows the bean to be registered by **@ComponentScan**. In **outer**, the call **this.create(id)** runs directly on the target; it does not go through the Spring AOP proxy.

### 7.5. Aspect Using execution with Three Signature Patterns

**src/main/java/demo/SignatureAspect.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.aspectj.lang.annotation.Pointcut;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class SignatureAspect {

    @Pointcut(
        "execution(public java.lang.String " +
        "demo.OrderApi.create(java.lang.String))"
    )
    public void exactCreate() {
    }

    @Before("exactCreate()")
    public void beforeCreate(JoinPoint jp) {
        System.out.println("ADVICE create " + jp.getArgs()[0]);
    }

    @Before("execution(public void demo.OrderApi.cancel(long))")
    public void beforeCancel(JoinPoint jp) {
        System.out.println("ADVICE cancel " + jp.getArgs()[0]);
    }

    @Before("execution(* demo.OrderApi.find(..))")
    public void beforeFind(JoinPoint jp) {
        System.out.println("ADVICE find " + jp.getArgs()[0]);
    }
}
~~~

Explanation:

1. **exactCreate()** is a **named pointcut**. The method name lets advice reuse the expression, while the empty method body is not invoked as business logic to "check".
2. **@Pointcut** holds the expression by specific signature: public, String return, OrderApi, create, and exactly one String parameter.
3. **@Before("exactCreate()")** references the named pointcut in the same aspect.
4. **@Before("execution(public void demo.OrderApi.cancel(long))")** is an inline pointcut in the advice, selecting only the described `cancel` method.
5. **@Before("execution(* demo.OrderApi.find(..))")** uses wildcards so it does not constrain the return type or number of parameters, while still restricting the method name to `find`.
6. **JoinPoint.getArgs()** prints the actual argument inside the advice. The argument value is for **display**, not a matching condition of these expressions.

**@Aspect** declares the aspect, and **@Component** registers it as a Spring bean during scanning. If you only keep `@Aspect` without registering the bean, Spring AOP will not automatically instantiate the aspect to apply advice.

### 7.6. Enabling Spring AOP in ApplicationContext

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

**@ComponentScan** registers **OrderServiceImpl** and **SignatureAspect**. **@EnableAspectJAutoProxy** activates the Spring AOP infrastructure to find advisors and proxy eligible beans.

Enabling auto-proxy does not mean every bean in the context becomes a proxy. Spring evaluates advisor applicability for each bean.

### 7.7. Creating the Context and Calling Methods Sequentially

**src/main/java/demo/App.java**

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            OrderApi service = context.getBean(OrderApi.class);

            System.out.println(
                    "IS_PROXY " + AopUtils.isAopProxy(service));

            String created = service.create("A1");
            System.out.println("RESULT " + created);

            service.cancel(7L);

            String found = service.find("A1");
            System.out.println("FOUND " + found);

            service.outer("B2");
        }
    }
}
~~~

Run from the directory containing **pom.xml**:

~~~bash
mvn -q clean compile exec:java
~~~

Expected **logical stdout lines** in call order (excluding Maven/logging messages):

~~~text
IS_PROXY true
ADVICE create A1
SERVICE create A1
RESULT created:A1
ADVICE cancel 7
SERVICE cancel 7
ADVICE find A1
SERVICE find A1
FOUND A1
SERVICE outer B2
SERVICE create B2
~~~

### 7.8. Interpreting the Output

- **IS_PROXY true**: Spring returns the OrderApi bean as an AOP proxy.
- **ADVICE create A1**: `exactCreate()` matches the `create(String)` method called through the proxy.
- **ADVICE cancel 7**: matches the exact **void** return and primitive **long** parameter.
- **ADVICE find A1**: wildcard return type and **(..)** allow matching the `find` method with one String parameter.
- **SERVICE outer B2** then **SERVICE create B2**: `outer` is called through the proxy but does not belong to the three advices; `create` is called directly via **this** inside the target, so there is no **ADVICE create B2**.

This is an important distinction: **create(String) matches the pointcut in both situations**, but only the external call through the proxy triggers advice.

## 8. Concrete Match Table from the Project

| Expression | create(String) | cancel(long) | find(String) | outer(String) |
| --- | --- | --- | --- | --- |
| **execution(public java.lang.String demo.OrderApi.create(java.lang.String))** | Yes | No | No | No |
| **execution(public void demo.OrderApi.cancel(long))** | No | Yes | No | No |
| **execution(* demo.OrderApi.find(..))** | No | No | Yes | No |
| **execution(* demo.OrderApi.*(..))** | Yes | Yes | Yes | Yes |
| **execution(* demo.OrderApi.create())** | No | No | No | No |
| **execution(* demo.OrderApi.create(*))** | Yes | No | No | No |
| **execution(public * demo.OrderApi.*(..))** | Yes | Yes | Yes | Yes |
| **execution(void demo.OrderApi.*(..))** | No | Yes | No | Yes |

**The table describes method signature matching**, not a count of how many times advice will run. When **outer()** calls **this.create()**, the `create` signature still matches the expression, but that invocation **does not go through the proxy**.

Broad expressions like **execution(* demo.OrderApi.*(..))** can select many unintended methods if used for critical logging, authorization, or altering business results. You should restrict by name, layer, modifier, or signature to fit the actual goal.

## 9. Distinguishing execution from args in Spring AOP

A common source of confusion is **declared parameter type** versus **runtime argument type**.

Given a Java method:

~~~java
public void process(java.io.Serializable value) {
    // ...
}
~~~

And the caller passes a String:

~~~java
process("hello");
~~~

**String** implements the **Serializable** interface, yet the **declared signature** of the method still takes **Serializable**, not String.

Two pointcuts have different meanings:

~~~java
execution(* *.process(java.io.Serializable))
~~~

The expression above describes a method with **declared parameter type Serializable**.

~~~java
args(java.lang.String)
~~~

The second expression is another designator supported by Spring AOP that inspects the **argument type at invocation**. If the caller passes a **String**, it can match this runtime type condition; if the caller passes another Serializable implementation that is not a String, that condition may not match.

The snippets above are **syntax illustrations**, not standalone runnable Java files. Some type-matching details may depend on the type hierarchy and pattern semantics; the key takeaway is that **execution relies on the method signature**, whereas **args references the argument passed at runtime**. Do not replace `execution` with `args` when the requirement actually calls for filtering by method name or return type.

### 9.1. Why Use (long) Instead of (java.lang.Long)?

In the project, **cancel(long)** takes a primitive `long`. Although Java performs boxing/unboxing between `long` and `Long` at call sites, the signature still carries the **long** type. The expression **execution(* demo.OrderApi.cancel(java.lang.Long))** is not an equivalent way to write the `cancel(long)` signature.

### 9.2. Overloads and Signatures

Suppose an interface has:

~~~java
void submit(String id);
void submit(String id, int quantity);
void submit(long id);
~~~

The expressions:

~~~text
execution(* *.submit(java.lang.String))
execution(* *.submit(java.lang.String,int))
execution(* *.submit(..))
~~~

Respectively select the single-String overload, the String + int overload, and all overloads named `submit`. These are only **illustrative fragments**; to compile, the methods must be placed in a valid interface or class.

In particular, **execution(* *.submit(*))** selects overloads with any single parameter, not the overload with two parameters.

### 9.3. Varargs and Arrays in Java

The method:

~~~java
public void send(String... messages) {
    // ...
}
~~~

uses varargs, but in Java bytecode the parameter is represented as **String[]**. Therefore, the pointcut must be matched against the signature understood by the Spring/AspectJ parser for array types, rather than assuming **(..)** is a special wildcard for varargs.

If you simply want to cover any number of parameters of `send`, **execution(* *.send(..))** is a readable way to express it. If you want to match the exact array parameter, verify the pattern and result in a real project.

### 9.4. Generics and Type Erasure

In Java, generic type arguments are generally not fully present in the runtime method signature in the same way generic source calls are written. When choosing pointcuts for generic service interfaces or bridge methods, matching results should be verified against the actual types and Spring proxy.

Do not assume an expression will automatically distinguish **List<String>** from **List<Integer>** at runtime just because it writes the full parameterized type. When a problem needs to distinguish data types deep inside a generic collection, value checks must be done in explicit logic or using appropriate metadata.

## 10. Named @Pointcut: A Name for Reusing an Expression

In the example, we used:

~~~java
@Pointcut(
    "execution(public java.lang.String " +
    "demo.OrderApi.create(java.lang.String))"
)
public void exactCreate() {
}
~~~

And:

~~~java
@Before("exactCreate()")
public void beforeCreate(JoinPoint jp) {
    // ...
}
~~~

Here there are **two different signatures**:

- **The method signature inside execution(...)**: describes the **business method** you want to select (`OrderApi.create(String)`).
- **The method signature of exactCreate()**: is the **pointcut name** for referencing inside the aspect. It must return `void` and have a body without business logic; it is **not the advised service method**.

You can group expressions into more maintainable named pointcuts:

~~~java
@Pointcut("execution(public * demo.OrderApi.*(..))")
public void publicApiMethod() {
}

@Pointcut("execution(* demo.OrderApi.create(..))")
public void anyCreateOverload() {
}

@Pointcut("publicApiMethod() && anyCreateOverload()")
public void publicCreate() {
}
~~~

This is an **additional illustrative snippet inside an aspect class**, and you do not need to copy the entire block into the runnable project unless you want to add more advice. In the Java annotation value, **&&** here is the pointcut combination operator; it is not a Java loop.

The **private/protected/public** modifier of the **@Pointcut-defining method** governs Java visibility rules when other aspects reference that pointcut; it does **not** automatically make the expression select only business methods with that modifier. If you want public-only, write **public** inside **execution**.

Spring also allows referencing a named pointcut defined in another type by its fully qualified name when the method is accessible. This is useful when multiple aspects in the same module share a service-method selection convention.

## 11. Combining execution with an Explicit Bean Scope

An overly broad expression:

~~~java
@Before("execution(* *(..))")
public void aroundEverything() {
    // ...
}
~~~

is an **illustrative pattern that should not be used indiscriminately**. It can apply to far too many eligible methods, increasing log noise, proxy creation overhead, or causing confusing side effects.

Usually you should narrow by **package**, **service interface**, or **type**:

~~~java
execution(public * demo.order.service..*.*(..))
~~~

This limits the signature to **demo.order.service** and subpackages, for public methods that a Spring proxy can intercept.

Or select a stable interface contract:

~~~java
execution(* demo.OrderApi.*(..))
~~~

It can be combined with other designators supported by Spring AOP, for example:

~~~java
execution(public * demo.OrderApi.*(..)) && bean(orderServiceImpl)
~~~

**bean(...)** is a Spring-specific pointcut designator that matches by **bean name**; it is not part of the `execution` syntax. In the example with **@Service OrderServiceImpl** and default component naming, the bean name is typically **orderServiceImpl**.

Selecting by **bean name** can be useful when multiple beans share the same interface but you only want one specific bean. It carries the risk of depending on bean names and context configuration, so it should be used deliberately and tested.

Other Spring pointcut designators such as **within**, **@annotation**, and **target** can also be combined to add conditions. However, if the task is simply selecting methods by signature, prefer an **execution** expression that is sufficiently specific and readable.

## 12. Common Mistakes When Writing execution

| Symptom | Common cause | How to fix / verify |
| --- | --- | --- |
| Advice does not run | Bean is not a Spring-managed proxy or **this.method()** is called | Obtain bean from context, trace call path |
| Method has right name but does not match | Wrong return type, modifier, declared parameter type, or package/type | Compare actual signature against each part of the expression |
| Wanted any parameter count but used **(*)** | **(*)** matches only one parameter, not any count | Use **(..)** when any number of parameters is needed |
| Wanted zero-parameter method but used **(..)** | **(..)** matches 0, 1, or many args | Use **()** to select exactly 0 |
| Wanted all subpackages but pattern only has **.*** | Direct type wildcard does not descend into subpackages | Use **..*** properly in the package/type section |
| Expression returning String does not match method returning Object | Return pattern checks declared return type | Use the actual declared type or **\*** if appropriate |
| `cancel(long)` does not match `cancel(Long)` | `long` and `Long` are two different declared types | Write the exact signature |
| Method exists only on implementation while bean uses JDK proxy | JDK proxy exposes interface methods | Put the method on an appropriate interface or consider CGLIB |
| `private`/`final` method is not intercepted by CGLIB | Cannot be overridden via subclass proxy mechanism | Create a public entry point or change the design |
| Pointcut matches too many beans | Pattern selects unintended layers | Narrow package, type, or bean name |
| Named pointcut does not resolve | Wrong name or Java visibility prevents referencing | Check the `@Pointcut` method, name, and class |
| Used **call(...)** as in AspectJ weaving | Spring proxy-based AOP does not support that designator | Use `execution` and understand proxy limits |
| Have **@Aspect** without an aspect bean | `@Aspect` is not auto-registered by component scanning without `@Component` or `@Bean` | Register the aspect explicitly |
| Spring AOP not enabled in the appropriate context | Missing `@EnableAspectJAutoProxy` or equivalent config | Enable AOP in the context containing the service/aspect |
| Wrong advice count printed when overloaded methods exist | Broad **(..)** expression selects multiple overloads | Restrict the parameter pattern and write tests |
| Only checked **AopUtils.isAopProxy == true** | Proxy could have been created by another advisor | Inspect logs of the specific advice and actual pointcut |

Read the table by **checking narrow conditions first**, rather than changing annotations or proxy types wholesale without knowing where the mismatch lies.

## 13. Workflow for Debugging an execution Pointcut

### Step 1 — Record the Actual Method Signature

For example:

~~~java
public String create(String id)
~~~

Break it down clearly:

- Modifier: **public**.
- Return type: **java.lang.String**.
- Declaring contract: **demo.OrderApi** (or the actual implementation).
- Name: **create**.
- Parameter count: **1**.
- Declared parameter type: **java.lang.String**.

### Step 2 — Write the Expression from Narrow to Broad

Start with:

~~~java
execution(public java.lang.String demo.OrderApi.create(java.lang.String))
~~~

If it does not match, temporarily relax return/argument constraints to investigate:

~~~java
execution(* demo.OrderApi.create(..))
~~~

This is a **temporary debugging technique**; do not leave a broad expression in production automatically.

### Step 3 — Verify the Service Is a Spring AOP Proxy

In the section 7 example:

~~~java
System.out.println(
    org.springframework.aop.support.AopUtils.isAopProxy(service)
);
~~~

If the value is false, check whether the bean is registered and whether an advisor is applied to it by Spring. If it is true yet the advice does not run, verify the expression and caller path. **True does not prove every method is advised**.

### Step 4 — Check for Self-Invocation

Try calling **service.create("A1")** directly from `App` and calling **service.outer("B2")**. If advice runs before `create` from `App` but not before `this.create` inside the target, that is a proxy limitation, not a wrong `create` signature.

### Step 5 — Distinguish Syntax Parse Error from No Match

- **Parse error**: Spring may fail when creating the advisor/context; check parentheses, full type names, wildcard placement, and supported designators.
- **No match**: the context runs normally but advice does not appear; check signature, type, package, and call path.
- **Match but unexpected advice behavior**: check the number of aspect beans, advice order, combined pointcuts, exceptions, and advice logic.

If using overloads or subclasses/generic interfaces, write representative integration tests rather than looking at a single log run.

## 14. Hands-On Exercises

**Exercise 1 — Select every method of OrderApi.**

In a separate test copy, change one advice to:

~~~java
@Before("execution(* demo.OrderApi.*(..))")
public void allMethods(JoinPoint jp) {
    System.out.println("ALL " + jp.getSignature().getName());
}
~~~

Predict the new log when calling **create**, **cancel**, **find**, and **outer** from `App`. External calls through the proxy can trigger the `ALL` advice; the **this.create()** call inside `outer` still does not create a separate proxy invocation.

Note: this is an **illustrative snippet meant to replace an existing advice**; do not add it alongside all the old advices and compare output against section 7 without accounting for the new advice.

**Exercise 2 — Select only void methods.**

Use:

~~~java
execution(void demo.OrderApi.*(..))
~~~

Compare **cancel(long)** and **outer(String)**: both have a `void` return type. Predict why **create(String)** and **find(String)** do not match.

**Exercise 3 — Select exactly one parameter regardless of type.**

Use:

~~~java
execution(* demo.OrderApi.*(*))
~~~

Every method in the section 7 example has exactly one parameter, so all match at the signature level. Add a **status()** method with no arguments and verify that it is excluded.

**Exercise 4 — Add an overload.**

Extend **OrderApi** with **create(String,int)**, implement it in the service, then compare:

~~~java
execution(* demo.OrderApi.create(..))
execution(* demo.OrderApi.create(java.lang.String))
execution(* demo.OrderApi.create(java.lang.String,int))
~~~

The first expression selects both overloads; the latter two select individual overloads. Update valid source code and rerun Maven to verify for yourself.

**Exercise 5 — Select public methods in a package.**

Move the service class to **demo.service** and change the pointcut to:

~~~java
execution(public * demo.service.*.*(..))
~~~

If you also create **demo.service.internal**, compare with:

~~~java
execution(public * demo.service..*.*(..))
~~~

to see the difference between the direct package and subpackages. Test going through a Spring proxy from a real caller.

## 15. Checklist Before Using an execution Pointcut in an Application

1. **Correct Spring AOP scope**: Spring-managed bean, method execution, and no expectation of intercepting fields/constructors.
2. **Correct signature**: return type, modifier, declaring type, method name, parameter count, and declared parameter types.
3. **Correct wildcards**: **\*** is a contextual type/name wildcard; **(..)** is any number of parameters; **..** in a package pattern serves a different role.
4. **Correct proxy type**: JDK by interface or CGLIB by class; do not expect `private`/`final` methods under CGLIB to be overridden.
5. **Correct call path**: invocation goes from caller through proxy, not self-invocation on the target.
6. **Aspect is already a bean**: use `@Component` + component scan or `@Bean` and enable `@EnableAspectJAutoProxy` in the appropriate context.
7. **Sufficiently narrow pointcut**: does not accidentally select unrelated modules/layers.
8. **Test both match and no-match**: include at least one method that should be advised and a similar method whose signature should not match.
9. **Check overloads**: do not confuse **(*)** with **(..)**, or primitives with wrappers.
10. **Test actual behavior**: having a proxy alone is not enough; verify the specific advice actually ran for the right methods.

## 16. Self-Check Questions

**1. Why does execution(* demo.OrderApi.create(..)) not care about the return type?**

Because **\*** in the return type position matches any return type. The expression still constrains the `OrderApi` type and `create` method.

**2. How does execution(* demo.OrderApi.create(*)) differ from execution(* demo.OrderApi.create(..))?**

The first form requires **exactly one parameter** of any type; the second accepts **0 to many parameters**.

**3. When should you write execution(public * *(..))?**

When you truly want to select every interceptable public method within AOP consideration. In real applications, consider adding package/type scoping to avoid matching too broadly.

**4. Does execution select by declared parameter or runtime argument?**

Primarily by method signature and declared type; the **args(...)** designator is used when you want to match on runtime argument types.

**5. A method returns Object while returning a String at runtime; does execution(java.lang.String ... ) match?**

Not merely because the runtime value is String; you must look at the declared return type and type pattern semantics.

**6. Why is create(String) advised when App calls it, but not when outer calls this.create?**

Because the call from `App` goes through the Spring AOP proxy, whereas `this.create` is a direct internal call on the target.

**7. Is an expression selecting a private method enough for Spring AOP to advise a private method?**

No. Spring proxies do not override private methods; a pointcut does not change the interception mechanism.

**8. Does a named @Pointcut with a private method mean it only selects private business methods?**

No. The visibility of the method defining the named pointcut only controls Java referencing visibility. To select methods by modifier, specify the modifier inside **execution**.

**9. Should you use call(...) instead of execution(...) to intercept self-invocation in Spring AOP?**

No. Spring proxy-based AOP does not support the AspectJ-weaving-style `call` pointcut designator.

**10. Why compare method signatures from the interface when using a JDK proxy?**

Because a JDK proxy exposes public interface methods; an implementation-only method does not automatically become part of the JDK proxy API.

## 17. Official Spring Documentation

- Spring Framework 6.2 — **Declaring a Pointcut / execution syntax**: https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html
- Spring Framework — **@AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework — **Declaring Advice**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — **Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html

**Conclusion:** **execution(...)** is Spring AOP's primary tool for selecting **method executions by signature**. A correct expression requires specifying the modifier, return type, declaring type, method name, and parameter pattern accurately. For **advice to actually run**, that method must also belong to a Spring-managed bean and be invoked through an eligible Spring AOP proxy.
