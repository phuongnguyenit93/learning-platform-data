
# Escaping Characters and Using `and`, `or`, `not` in Spring AOP XML Expressions

## 1. The Practical Problem

When defining a pointcut in `applicationContext.xml`, we are writing a **Spring AOP pointcut expression inside an XML attribute**. Two syntax layers are processed sequentially:

1. The XML parser reads the document and decodes XML entities in attribute values (e.g., `&amp;` into the `&` character).
2. The Spring AOP/AspectJ pointcut parser receives the expression string after XML decoding, then determines which method calls on Spring beans match.

Therefore, an expression that is completely valid inside Java `@Pointcut` can make XML invalid if raw `&&` characters are pasted into the `expression` attribute. In XML configuration, Spring supports the **keywords `and`, `or`, and `not`** as equivalents to the `&&`, `||`, and `!` operators. Using keywords is usually more readable and avoids escaping `&`.

This lesson aims to write and verify **proxy-based Spring AOP** expressions in the `aop` namespace; it explains only the parts of the expression language directly relevant to Spring XML.

## 2. Operator Syntax Comparison Table

| Meaning | Expression in Java `@Pointcut` | Recommended in Spring XML | Symbol form still valid in XML |
| --- | --- | --- | --- |
| Both conditions satisfied (AND) | `A && B` | `A and B` | `A &amp;&amp; B` |
| At least one condition satisfied (OR) | `A || B` | `A or B` | `A || B` |
| Negate a condition (NOT) | `!A` | `not A` | `!A` |
| Grouped conditions | `(A || B) && !C` | `(A or B) and not C` | `(A || B) &amp;&amp; !C` |

In the table, `A`, `B`, `C` are valid pointcut sub-expressions, such as `execution(* demo.OrderService.save(..))`, `within(demo..*)`, `bean(*Service)`, or `@annotation(demo.Audited)`.

- `and` combines conditions: a method is advised if **all** conditions match.
- `or` forms a union: a method is advised when **at least one** branch matches.
- `not` excludes join points matched by the negated condition.
- Parentheses belong to **pointcut expression** syntax, not XML entities; use them directly to clarify evaluation order.
- `&&`, `||`, and `!` are pointcut expression operators, **not** Java operations evaluated when the business method runs. Spring parses them to construct the join-point selection predicate.

### Simple Examples

~~~xml
<!-- Only advise public methods in package demo. -->
<aop:pointcut id="publicInDemo"
    expression="within(demo..*) and execution(public * *(..))"/>
~~~

`within(demo..*)` selects the declaring scope, while `execution(public * *(..))` selects `public` method executions. Spring AOP only intercepts **method calls passing through a Spring proxy**; the expression does not turn objects instantiated with `new` into beans.

With OR:

~~~xml
<!-- Match send(...) or receive(...) methods, regardless of argument count. -->
<aop:pointcut id="ioOperations"
    expression="execution(* *.send(..)) or execution(* *.receive(..))"/>
~~~

With NOT:

~~~xml
<!-- Select beans whose name ends with Service while excluding testService. -->
<aop:pointcut id="nonTestServices"
    expression="bean(*Service) and not bean(testService)"/>
~~~

`bean(idOrNamePattern)` is a **Spring AOP**-specific pointcut designator for matching bean names. It can be combined with the operators above; it is not the same mechanism as class scanning or package selection.

## 3. Why Does `&&` Need `&amp;&amp;` in XML?

The `&` character starts an XML entity reference, so it cannot appear unescaped inside an attribute value.

**Incorrect: invalid XML**

~~~xml
<aop:pointcut id="bad"
    expression="within(demo..*) && execution(public * *(..))"/>
~~~

The XML parser hits the first `&` and expects a valid entity; parsing aborts before Spring ever sees the pointcut. Errors typically manifest as `SAXParseException` or messages about entity/name syntax, not a logic error in `execution(...)`.

**Correct: using the word `and`**

~~~xml
<aop:pointcut id="correctWords"
    expression="within(demo..*) and execution(public * *(..))"/>
~~~

**Also correct: escaping each `&` character**

~~~xml
<aop:pointcut id="correctEntities"
    expression="within(demo..*) &amp;&amp; execution(public * *(..))"/>
~~~

After XML parsing, the third example passes Spring AOP a string containing `&&`. Both valid expressions in this section have identical matching semantics; they do not differ in when advice runs or how proxies are created.

Distinguish these layers:

- **XML source content**: `&amp;&amp;` consists of two consecutive `&amp;` entities.
- **Parsed string**: `&&`.
- **Pointcut expression**: the AND operator joining two conditions.

Do not write `&amp;amp;&amp;amp;` by double-escaping: after the XML parser decodes one pass, Spring would receive literal `&amp;&amp;` and the pointcut parser would not see the intended operator.

## 4. XML Entities to Remember When Pointcuts Live in Attributes

| Character to put in attribute value | How to write in XML source | When relevant |
| --- | --- | --- |
| `&` | `&amp;` | Required if using the `&&` symbol |
| `<` | `&lt;` | Required in XML attributes if a less-than sign is ever needed |
| `>` | `&gt;` | Can be used for clarity, though `>` is usually allowed in attributes |
| `"` | `&quot;` | Needed when attribute is double-quoted and must contain a double quote |
| `'` | `&apos;` | Needed when attribute is single-quoted and must contain a single quote |

Not all entities in this table are frequently used in pointcuts; the most common is `&amp;`. The `||` and `!` operators contain no characters requiring XML escaping, so the symbolic forms of OR and NOT can be placed directly in attributes.

XML entities and pointcut syntax are **two independent mechanisms**. Writing `&amp;` merely makes the XML document valid; it does not change method selection semantics. Characters like `*`, `..`, `(..)`, and `@` in Spring AOP expressions are normally written literally.

**Special note:** Do not mechanically apply escaping to Java `@Aspect` code:

~~~java
@Pointcut("within(demo..*) && execution(public * *(..))")
public void publicOperationsInDemo() {}
~~~

In the Java string literal above, `&&` is not inside an XML attribute, so you must not write `&amp;&amp;`.

## 5. Choosing the Right Precedence with Parentheses

When combining `and`, `or`, and `not`, use parentheses to clearly express **positive groups** and **exclusion groups**. This prevents divergence between a human reader's intent and the parser's evaluation when expressions grow complex.

Consider the business rule:

> Only monitor service beans, on the `send` or `receive` methods, while excluding the `testService` test bean.

Write:

~~~text
bean(*Service)
and (execution(* demo.DefaultMessageService.send(..))
     or execution(* demo.DefaultMessageService.receive(..)))
and not bean(testService)
~~~

Inside an XML attribute, line breaks may be normalized into spaces. For lessons or configs that need clean diffs, write concisely on one line or split pointcuts intentionally.

~~~xml
<aop:pointcut id="auditedCalls"
    expression="bean(*Service) and (execution(* demo.DefaultMessageService.send(..)) or execution(* demo.DefaultMessageService.receive(..))) and not bean(testService)"/>
~~~

The rule above performs three logical steps:

1. `bean(*Service)`: selects Spring beans whose names match the wildcard.
2. `(send or receive)`: keeps only these two method groups, without restricting to a single one.
3. `and not bean(testService)`: subtracts invocations on the test bean.

Writing `bean(*Service) and send or receive and not bean(testService)` without parentheses changes operator associativity and can let `receive` bypass part of the intended outer condition. Always wrap `or` in explicit parentheses when both branches share an outer constraint.

**A negation pitfall:**

~~~text
not (A or B)   =   (not A) and (not B)
not (A and B)  =   (not A) or (not B)
~~~

For example, `not (send or receive)` selects methods **belonging to neither `send` nor `receive`**; whereas `not send or receive` has a different meaning. In Spring AOP, matched points must still be method invocations through a proxy, even if a boolean expression formally evaluates to true.

## 6. Complete Spring XML AOP Example Using `and`, `or`, `not`

This example uses Java 17, Maven, and Spring Framework 6.1.15. Two beans `messageService` and `testService` share the `DefaultMessageService` implementation. Only `messageService` is advised on `send` and `receive`; the `health` method is outside the expression, and the test bean is excluded via `not bean(testService)`.

Structure:

~~~text
spring-xml-pointcut-operators/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── Application.java
    │   ├── MessageService.java
    │   ├── DefaultMessageService.java
    │   └── LoggingAspect.java
    └── resources/applicationContext.xml
~~~

### 6.1. Maven

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-xml-pointcut-operators</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.15</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.1.15</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
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
                <version>3.5.0</version>
                <configuration><mainClass>demo.Application</mainClass></configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides `ApplicationContext`, `spring-aop` provides the Spring proxy/advisor runtime, and `aspectjweaver` contains the AspectJ pointcut parsing/matching support used by Spring. This remains **Spring AOP**, running neither compile-time nor load-time weaving.

### 6.2. Interface for Calling Through the Spring Proxy

**src/main/java/demo/MessageService.java**

~~~java
package demo;

public interface MessageService {
    String send(String id);
    String receive(String id);
    String health();
}
~~~

**src/main/java/demo/DefaultMessageService.java**

~~~java
package demo;

public class DefaultMessageService implements MessageService {
    @Override
    public String send(String id) {
        System.out.println("target: send " + id);
        return "sent " + id;
    }

    @Override
    public String receive(String id) {
        System.out.println("target: receive " + id);
        return "received " + id;
    }

    @Override
    public String health() {
        System.out.println("target: health");
        return "UP";
    }
}
~~~

Two beans of the same Java class can yield different advice outcomes because the `bean(...)` pointcut checks the Spring bean name. No annotations are needed on the classes for this XML-based example to work.

### 6.3. Bean Containing Advice

**src/main/java/demo/LoggingAspect.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;

public class LoggingAspect {
    public void before(JoinPoint joinPoint) {
        System.out.println("advice: " + joinPoint.getSignature().getName());
    }
}
~~~

`LoggingAspect` is a plain Java class. It will be registered with `<bean>` and linked to `<aop:before method="before">`. Neither `@Aspect` nor `@Before` is needed in the class when using schema-based AOP.

### 6.4. Defining the Pointcut in XML

**src/main/resources/applicationContext.xml**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
          http://www.springframework.org/schema/beans
          https://www.springframework.org/schema/beans/spring-beans.xsd
          http://www.springframework.org/schema/aop
          https://www.springframework.org/schema/aop/spring-aop.xsd">

    <bean id="messageService" class="demo.DefaultMessageService"/>
    <bean id="testService" class="demo.DefaultMessageService"/>
    <bean id="loggingAspect" class="demo.LoggingAspect"/>

    <aop:config proxy-target-class="false">
        <aop:pointcut id="auditedCalls"
            expression="bean(*Service) and (execution(* demo.DefaultMessageService.send(..)) or execution(* demo.DefaultMessageService.receive(..))) and not bean(testService)"/>

        <aop:aspect ref="loggingAspect">
            <aop:before pointcut-ref="auditedCalls" method="before"/>
        </aop:aspect>
    </aop:config>
</beans>
~~~

Each component has a clear role:

- `xmlns:aop` and `spring-aop.xsd` declare namespace syntax for the XML document.
- Three `<bean>` tags create the target beans (two names) and the aspect bean containing the advice method.
- `<aop:pointcut id="auditedCalls">` stores a complete expression; `pointcut-ref="auditedCalls"` references the **pointcut configuration ID**.
- `<aop:aspect ref="loggingAspect">` points to the Spring bean containing the `before` method.
- `proxy-target-class="false"` pairs with the `MessageService` interface of both targets. External callers should retrieve beans by interface.
- When advice runs, `LoggingAspect.before` only logs before the target method executes without changing the return value.

`not bean(testService)` does not remove the `testService` bean from the context; it only prevents **this specific pointcut** from matching method invocations on that bean.

### 6.5. Invoking Spring Beans

**src/main/java/demo/Application.java**

~~~java
package demo;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public class Application {
    public static void main(String[] args) {
        try (var context =
                new ClassPathXmlApplicationContext("applicationContext.xml")) {

            MessageService production =
                    context.getBean("messageService", MessageService.class);
            MessageService testing =
                    context.getBean("testService", MessageService.class);

            System.out.println("result: " + production.send("M-1"));
            System.out.println("result: " + production.receive("M-2"));
            System.out.println("result: " + production.health());
            System.out.println("result: " + testing.send("T-1"));
        }
    }
}
~~~

In the directory containing `pom.xml`, run:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the program (excluding environment-dependent Maven/Spring logs) in order:

~~~text
advice: send
target: send M-1
result: sent M-1
advice: receive
target: receive M-2
result: received M-2
target: health
result: UP
target: send T-1
result: sent T-1
~~~

Explanation of results:

1. `production.send`: bean named `messageService` matches `bean(*Service)`, the `send` branch matches, and `not bean(testService)` is also true ⇒ advice runs.
2. `production.receive`: matches the `receive` branch of the OR ⇒ advice runs.
3. `production.health`: matches neither method-name branch inside the parentheses ⇒ advice does not run.
4. `testing.send`: matches the method name, but bean named `testService` is negated ⇒ advice does not run.

You must retrieve the service from `ApplicationContext` to get the Spring-managed proxy. Creating `new DefaultMessageService()` and calling `send` will not go through Spring AOP. Self-invocation such as `this.send(...)` inside the target itself also normally bypasses the proxy.

## 7. Equivalent Expression Using Operator Symbols

We can replace **only the `expression` attribute** in the example pointcut with:

~~~xml
<aop:pointcut id="auditedCalls"
    expression="bean(*Service) &amp;&amp; (execution(* demo.DefaultMessageService.send(..)) || execution(* demo.DefaultMessageService.receive(..))) &amp;&amp; !bean(testService)"/>
~~~

This version is equivalent to the one using `and`, `or`, `not`. The XML parser decodes both `&amp;&amp;` pairs into `&&`; the Spring pointcut parser interprets the operators and conditions identically. `||`, `!`, parentheses, and wildcards are written literally. **Do not place both `<aop:pointcut id="auditedCalls">` definitions with the same ID in the same configuration**; this is an alternative for comparison.

Syntax pipeline diagram:

~~~text
applicationContext.xml
  expression="A &amp;&amp; (B || C) &amp;&amp; !D"
            |
            | XML parser
            v
  pointcut string: A && (B || C) && !D
            |
            | Spring AOP/AspectJ expression parser
            v
  match: A and (B or C) and not D
            |
            | Spring advisor / proxy
            v
  Only bean method calls satisfying the condition run advice
~~~

Notably, proper escaping does not alter `bean(*Service)` filtering logic: the names `messageService` and `testService` behave identically.

## 8. Distinguishing XML Parsing Errors from Pointcut Parsing Errors

**Error at the XML parsing layer:** the XML cannot be parsed into a valid document.

~~~xml
<!-- Invalid XML: unescaped & character. -->
<aop:pointcut id="brokenXml"
    expression="execution(* demo..*.*(..)) && bean(*Service)"/>
~~~

Consequence: Spring may fail while reading XML before creating the `ApplicationContext`. Fix: replace `&&` with `and` or `&amp;&amp;`; also check namespaces and `schemaLocation`.

**Error at the pointcut parsing layer:** XML is valid, but the expression passed to Spring is malformed or uses a designator unsupported by Spring AOP.

~~~xml
<!-- Valid XML; invalid expression due to missing right-hand side of and. -->
<aop:pointcut id="brokenPointcut"
    expression="execution(* demo..*.*(..)) and"/>
~~~

Consequence: the XML parser succeeds; the Spring/AspectJ pointcut parser reports an expression/advisor error while initializing infrastructure. Fix: supply the complete right-hand side and ensure the pointcut designator is supported by Spring AOP (`execution`, `within`, `this`, `target`, `args`, `bean`, corresponding annotation designators...). Spring AOP does not support every AspectJ join point kind (e.g., field `get`, `set`, or `call`).

**Advice does not run despite valid XML and pointcut:** the expression matches an empty set of methods, the bean does not pass through a proxy, or self-invocation occurs. This is a runtime/proxy boundary issue, not a reason to add more XML escaping.

## 9. Being Careful with Named Pointcuts in XML

An `<aop:pointcut id="allServiceMethods" expression="..."/>` names **one complete expression**. Advice uses `pointcut-ref="allServiceMethods"`, whereas `expression="allServiceMethods and not bean(testService)"` is **invalid** because an XML ID is not a named pointcut method callable inside an expression.

To negate a bean, declare the final scope directly in the expression:

~~~xml
<aop:pointcut id="productionServices"
    expression="execution(* demo..*Service.*(..)) and not bean(testService)"/>
~~~

When multiple advices share the same set of methods, they reference the `productionServices` ID. The lesson **"Named pointcuts and pointcut-ref in XML"** thoroughly examines ID reuse at config/aspect levels along with scope-change tests.

## 10. Combining `@annotation`, `within`, and `bean` Pointcuts

Example to log every method in package `demo` **carrying the `@Audited` annotation**, except the internal bean `internalService`:

~~~xml
<aop:pointcut id="annotatedBusinessMethods"
    expression="within(demo..*) and @annotation(demo.Audited) and not bean(internalService)"/>
~~~

Meaning of the conditions above:

- `within(demo..*)` restricts method executions to the corresponding class/type namespace.
- `@annotation(demo.Audited)` filters by the annotation on the method.
- `not bean(internalService)` excludes the internal bean by ID/name.

This is a **standalone** example; `demo.Audited` must be defined with runtime retention and placed on actual methods to run. Do not mistake `@annotation` for an XML annotation namespace; the `@` character here is pointcut syntax.

In large projects, pairing package/type scope with target conditions makes expressions easier to audit. Avoid careless `or` clauses that pull in methods outside the intended zone:

~~~xml
<!-- Easy to over-match: the second branch is not restricted by within(demo..*). -->
<aop:pointcut id="tooBroad"
    expression="within(demo..*) and execution(* *.save(..)) or execution(* *.delete(..))"/>
~~~

Version that explicitly states the shared scope:

~~~xml
<aop:pointcut id="scoped"
    expression="within(demo..*) and (execution(* *.save(..)) or execution(* *.delete(..)))"/>
~~~

These examples only illustrate conditions; there is no need to create extra advice when the current goal is analyzing syntax.

## 11. Combining with `aop:aspectj-autoproxy` and `@Aspect`

For aspects using Java annotations, logical syntax lives **inside a Java string**, so no XML entities are needed:

~~~java
@Aspect
public class TraceAspect {
    @Before("within(demo..*) && (execution(* *.send(..)) || execution(* *.receive(..))) && !bean(testService)")
    public void before() {}
}
~~~

This is a fragment requiring imports, and `TraceAspect` must be registered as a Spring bean. XML only needs to register that bean and enable `<aop:aspectj-autoproxy/>`; the annotation method can use `&&` normally. If using schema-style `<aop:config>` to define advice, do not add `@AspectJ` auto-detection for that same advice.

## 12. Debugging Sequence When an XML Pointcut Does Not Work

1. **Check valid XML:** `xmlns:aop`, `spring-aop.xsd`, proper namespace–schema pairs in `xsi:schemaLocation`, no unescaped `&`; avoid raw `&&` in attributes.
2. **Check valid expression:** each operator has its operands, parentheses are balanced, `and`/`or`/`not` are spelled right, designators are supported by Spring AOP.
3. **Check Boolean logic:** parenthesize OR groups before ANDing with shared constraints; `not` applies to the intended sub-expression; avoid filtering too narrowly or too broadly.
4. **Check actual beans:** bean names exist and match `bean(...)`, target belongs to `ApplicationContext`, advice/aspect bean is registered, `pointcut-ref` matches the ID.
5. **Check proxy invocation:** call via the Spring bean (interface when using JDK proxy), do not `new` the target or expect self-invocation to be intercepted automatically.
6. **Check output across multiple cases:** one method matching AND, one matching an OR branch, one excluded by NOT, one outside the group; compare advice/target log order.

### Test Matrix for Section 6's Example

| Bean | Method | `bean(*Service)` | `send or receive` | `not bean(testService)` | Advice? |
| --- | --- | --- | --- | --- | --- |
| `messageService` | `send` | True | True | True | Yes |
| `messageService` | `receive` | True | True | True | Yes |
| `messageService` | `health` | True | False | True | No |
| `testService` | `send` | True | True | False | No |
| `testService` | `receive` | True | True | False | No |

If the real environment has multiple auto-proxy configurations or different proxy types, verify via integration tests pulling beans directly from the same `ApplicationContext`. Do not assume a valid pointcut expression alone guarantees advice always runs: Spring AOP depends on interception through proxies.

## 13. Recurring Pitfalls

Notable errors: (1) raw `&&` causing the XML parser to reject the document; (2) double-escaping causing the pointcut parser to receive the wrong literal; (3) missing parentheses around OR widening the matched set; (4) mistaking `pointcut-ref` for an expression; (5) omitting `not bean(testService)` and accidentally advising the test bean.

When fixing, check **both parser layers** in order—XML entities → pointcut expression—then test the matrix: two methods that should match, a method outside the OR group, an excluded bean, and a method on a non-proxied object. Having a proxy alone does not prove a specific advice ran.

