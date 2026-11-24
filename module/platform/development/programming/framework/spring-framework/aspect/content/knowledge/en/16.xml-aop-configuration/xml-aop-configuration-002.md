# `<aop:aspectj-autoproxy>`: Enabling `@Aspect` from XML Configuration in Spring

In a Spring Framework application using XML to declare beans, the **`<aop:aspectj-autoproxy/>`** element enables Spring AOP's automatic proxy creation for Spring beans matching pointcuts of aspects written with annotations **`@Aspect`, `@Before`, `@AfterReturning`, `@Around`...**. This is how AspectJ annotation syntax is used to define *advice/pointcuts* within an XML-configured application context.

Point to distinguish: XML **enables the aspect processing mechanism**, while Java classes carrying `@Aspect` **must still be registered as Spring beans** (directly via `<bean>` or via component scanning). Spring AOP applies advice through **Spring proxies**; it does not automatically bytecode-weave every Java object in the JVM.

This lesson focuses on configuring and operating **Spring Aspect/AOP**. It does not cover standalone AOP models outside Spring.

## 1. What Does `<aop:aspectj-autoproxy/>` Do?

Basic declaration example:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <aop:aspectj-autoproxy/>

    <!-- Both target and aspect must be Spring beans. -->
    <bean id="orderService" class="com.example.xmlaop.OrderServiceImpl"/>
    <bean id="loggingAspect" class="com.example.xmlaop.LoggingAspect"/>
</beans>
```

When Spring builds the `ApplicationContext`:

1. The XML `aop` namespace provides the `<aop:aspectj-autoproxy/>` element. Spring registers the auto-proxy creator (`AnnotationAwareAspectJAutoProxyCreator`, a type of bean post-processor).
2. Spring creates the declared beans, including `loggingAspect`. On aspect beans, Spring recognizes the `@Aspect` annotation and annotation-based advice.
3. When the `orderService` bean has methods matching a pointcut, Spring provides a **proxy** instead of handing the target object directly to callers retrieving it from the context.
4. Calls from clients **through the proxy** trigger the advice; the advice runs before/after/around the target depending on the annotation. Executing the target method itself remains the logic provided by the target.

`<aop:aspectj-autoproxy/>` does **not** automatically component-scan, does **not** automatically create beans for every class with `@Aspect`, and does **not** make direct calls via `new` go through a proxy. It activates how Spring applies aspect beans already present in the context.

## 2. Runnable Example with Spring Framework 6 and Java 17

This example creates a Spring application context via XML (without Spring Boot), with an order processing service and an aspect logging before service calls.

### 2.1. Project Structure

```text
spring-xml-aop/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/xmlaop/
        │   ├── Demo.java
        │   ├── OrderService.java
        │   ├── OrderServiceImpl.java
        │   └── LoggingAspect.java
        └── resources/
            └── applicationContext.xml
```

**`pom.xml`** (explicit versions for a standalone example; real projects may manage versions via a BOM):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-xml-aop</artifactId>
    <version>1.0.0</version>

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
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides the application context and bean management; `spring-aop` provides the AOP mechanism; `aspectjweaver` provides the types and AspectJ pointcut expression parsing support used by Spring AOP. This example uses only **Spring proxy AOP**: no Java agent installation or AspectJ compile-time/load-time weaving is used.

### 2.2. Interface and Target Bean

**`src/main/java/com/example/xmlaop/OrderService.java`**

```java
package com.example.xmlaop;

public interface OrderService {
    void placeOrder(String orderId);
}
```

**`src/main/java/com/example/xmlaop/OrderServiceImpl.java`**

```java
package com.example.xmlaop;

public class OrderServiceImpl implements OrderService {
    @Override
    public void placeOrder(String orderId) {
        System.out.println("SERVICE placeOrder " + orderId);
    }
}
```

We use an interface to observe **JDK dynamic proxy** behavior under the default `proxy-target-class="false"` mode.

### 2.3. Aspect Declared with Annotations

**`src/main/java/com/example/xmlaop/LoggingAspect.java`**

```java
package com.example.xmlaop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class LoggingAspect {
    @Before("execution(* com.example.xmlaop.OrderServiceImpl.placeOrder(..))")
    public void beforePlaceOrder() {
        System.out.println("ASPECT before placeOrder");
    }
}
```

- `@Aspect` tells Spring this bean contains aspect definitions.
- `@Before` declares advice that runs before the method selected by the pointcut executes.
- The expression `execution(* com.example.xmlaop.OrderServiceImpl.placeOrder(..))` selects the `placeOrder` method of the implementation in this example. Spring uses that pointcut to determine which methods need advice applied when called through the proxy.
- The aspect class **does not need `@Component`** when it is already declared as a Spring bean in XML.

Do not manually call `new LoggingAspect()` and expect Spring to apply it automatically. That instance must belong to the Spring context.

### 2.4. Enabling Proxies in XML

**`src/main/resources/applicationContext.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd">

    <!-- Enable @Aspect-based Spring AOP proxying. -->
    <aop:aspectj-autoproxy proxy-target-class="false"/>

    <bean id="orderService" class="com.example.xmlaop.OrderServiceImpl"/>

    <!-- Register the aspect as a Spring bean: required step. -->
    <bean id="loggingAspect" class="com.example.xmlaop.LoggingAspect"/>
</beans>
```

In this configuration:

- `xmlns:aop` and the `spring-aop.xsd` schema pair allow XML to recognize elements belonging to the Spring AOP namespace.
- `<aop:aspectj-autoproxy/>` activates automatic proxy creation for matching target beans.
- Both `<bean>` elements place the **target** and the **aspect** into the same application context.
- `proxy-target-class="false"` requests preferring a JDK proxy when the bean has an appropriate interface. If the target has no interface, Spring may use a class-based proxy. This is a proxy choice, unrelated to whether annotations are used on the aspect.

There is no need to place `@EnableAspectJAutoProxy` in Java code to enable it a second time; that is the corresponding activation form when using annotation/Java configuration. This example intentionally uses XML as the configuration source.

### 2.5. Client Running via Spring Context

**`src/main/java/com/example/xmlaop/Demo.java`**

```java
package com.example.xmlaop;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public class Demo {
    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                 new ClassPathXmlApplicationContext("applicationContext.xml")) {

            OrderService service =
                context.getBean("orderService", OrderService.class);

            System.out.println("PROXY " + AopUtils.isAopProxy(service));
            System.out.println("JDK_PROXY " + AopUtils.isJdkDynamicProxy(service));

            service.placeOrder("A001");
        }
    }
}
```

Run from the project directory with Maven and JDK 17 or higher:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.xmlaop.Demo
```

Lines printed by the example code, in exact order (excluding separate messages from the Maven environment):

```text
PROXY true
JDK_PROXY true
ASPECT before placeOrder
SERVICE placeOrder A001
```

Reason: `getBean(...)` returns a Spring proxy for the service; calling `service.placeOrder("A001")` goes through the proxy and executes `@Before` before the method body. If you remove `<aop:aspectj-autoproxy/>` from XML while keeping both beans, with this example configuration `getBean` will receive the plain target: `PROXY false`, `JDK_PROXY false`, and no `ASPECT` log line. This is a useful comparison to observe the effect of the configuration element.

## 3. Registering Aspects via Component Scanning in XML

Instead of declaring each `<bean>`, an application can let Spring scan annotations to find beans. In that case, `@Aspect` **only defines the aspect**, while `@Component` makes the class a candidate registered by component scanning:

```java
package com.example.xmlaop;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class LoggingAspect {
    @Before("execution(* com.example.xmlaop.OrderServiceImpl.placeOrder(..))")
    public void beforePlaceOrder() {
        System.out.println("ASPECT before placeOrder");
    }
}
```

If you also want to component-scan the service, add `@Service` to `OrderServiceImpl`. The corresponding XML can be written as:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:aop="http://www.springframework.org/schema/aop"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/aop
           https://www.springframework.org/schema/aop/spring-aop.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <context:component-scan base-package="com.example.xmlaop"/>
    <aop:aspectj-autoproxy/>
</beans>
```

**This is a configuration variant**, not a drop-in XML replacement for the complete example in Section 2 unless `@Component`/`@Service` have been added to the classes. If you switch to scanning, remove duplicate `<bean>` declarations to avoid unintended duplicate instances.

Remember two independent responsibilities:

| Declaration | Effect |
| --- | --- |
| `<context:component-scan .../>` | Registers eligible classes as Spring beans, including aspects with `@Component` |
| `<aop:aspectj-autoproxy/>` | Enables Spring AOP proxies and applies advice from beans annotated with `@Aspect` |

## 4. Important Options: `proxy-target-class` and `expose-proxy`

Two attributes of `<aop:aspectj-autoproxy>` control the proxy infrastructure without changing annotations inside `@Aspect`:

~~~xml
<aop:aspectj-autoproxy proxy-target-class="false" expose-proxy="false"/>
~~~

- `proxy-target-class="false"`: for beans with a suitable interface, Spring typically chooses a JDK dynamic proxy; without an interface, it may use a class proxy. `true` requests a class-based proxy, subject to `final`/private and module visibility limitations.
- `expose-proxy="true"`: allows `AopContext.currentProxy()` inside a call that has already passed through the proxy, useful for very specific cases but creating coupling and thread dependency. It **does not automatically turn** `this.method()` into a proxy call.
- In a context with multiple AOP/transaction configurations, auto-proxy settings may be merged; verify the actual proxy type with `AopUtils` rather than relying on a single XML line.

The lesson **"proxy-target-class and expose-proxy in XML configuration"** provides examples changing each attribute, comparing JDK/CGLIB and self-invocation.

## 5. Why Do Annotations Exist Yet Advice Does Not Run?

When annotation advice does not run, categorize the cause along the execution path instead of only looking for pointcut errors:

| Symptom | Check First |
| --- | --- |
| `@Aspect` exists but is not registered by Spring | `<bean>` or `@Component` combined with `<context:component-scan>` |
| Aspect bean exists but there is no advisor | `<aop:aspectj-autoproxy/>`, namespace/schema, `aspectjweaver` on classpath |
| Bean has a proxy but one method has no advice | Does `execution(...)` actually match the real method/annotation |
| Advice is only missing on internal calls | `this.method()` bypasses the Spring proxy |
| Manually created target has no advice | Put the target into the context and inject the proxy reference |
| Log appears twice | Are multiple aspect beans/advisors implementing the same concern |

`<aop:aspectj-autoproxy/>` is not equivalent to `<aop:aspect>` inside `<aop:config>`. Only combine them when genuinely using two separate declaration styles with non-overlapping responsibilities; the lesson **"Combining XML with Java configuration without creating duplicate behavior"** analyzes specific sources of duplication.

## 6. When to Use, and When to Switch to Java Configuration?

If an existing project uses `applicationContext.xml` to manage Spring beans, `<aop:aspectj-autoproxy/>` allows keeping application configuration in XML while writing concise advice with Java annotations.

In applications using Java configuration, the equivalent mechanism is `@EnableAspectJAutoProxy` (in Spring Boot applications, relevant auto-configuration may already enable Spring AOP depending on dependencies/config). Choosing XML or Java config changes **how proxy infrastructure is registered**; the rules for Spring beans, pointcut matching, and calling through proxies still must be followed.

**Quick checklist before handing off configuration:**

1. XML properly declares `xmlns:aop` and `spring-aop.xsd`.
2. `<aop:aspectj-autoproxy/>` is present in the appropriate application context.
3. The aspect class has `@Aspect` and valid advice annotations; the aspect is actually registered as a Spring bean.
4. The target is also a Spring bean, and the pointcut matches the method to be intercepted.
5. Code uses the bean from the context and calls **through the proxy**; the injection type matches the proxy type.
6. Spring AOP/AspectJ dependencies are complete; checking `AopUtils.isAopProxy(...)` alongside advice output confirms the mechanism works.

**Takeaway:** `<aop:aspectj-autoproxy/>` is the **Spring XML switch to enable AOP proxies for `@Aspect` beans**. It does not replace bean registration and does not turn every Java call into an intercepted join point; XML, beans, and call path must all be right for advice to run.