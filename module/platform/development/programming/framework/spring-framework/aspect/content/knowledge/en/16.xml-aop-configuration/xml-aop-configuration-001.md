# The `aop` Namespace and Registering Dependent Beans in Spring AOP via XML

## Objectives

In a Spring application using XML configuration, simply writing a class containing an advice method is not enough for business calls to be intercepted by Spring AOP. You need to properly coordinate the **XML `aop` namespace**, the proxy creation mechanism, and the related beans: the business bean (target), the bean containing the advice, the beans that the aspect depends on, and the separate advice bean when using `<aop:advisor>`.

This lesson focuses on Spring AOP in the Spring Framework: reading an XML configuration, identifying which beans need to be registered, understanding how Spring connects pointcuts with advice, and verifying proxy behavior. This is **proxy-based Spring AOP** configuration, not AspectJ bytecode weaving configuration.

After this lesson, you will be able to:

- Declare a valid `xmlns:aop` and `spring-aop.xsd` inside `<beans>`.
- Use `<aop:config>`, `<aop:pointcut>`, `<aop:aspect>`, and `<aop:around>` with a plain Java advice class.
- Register targets, aspects, and dependency beans using `<bean>` / `ref` / `constructor-arg`, without confusing the aspect `ref` with `pointcut-ref` or `advice-ref`.
- Distinguish between XML schema-style aspect configuration and `@Aspect` class configuration via `<aop:aspectj-autoproxy/>`.
- Diagnose unmanaged beans, advice not running, incorrect references, self-invocation, and proxy type selection.

## 1. Declaring the `aop` Namespace in Spring XML

An XML configuration file that uses `aop:` must declare the namespace and schema location:

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

    <!-- Define Spring beans and AOP configuration here. -->

</beans>
~~~

Here:

1. The default `xmlns` points to the beans namespace for using `<bean>`, `<constructor-arg>`, and `<property>`.
2. `xmlns:aop` declares the `aop` prefix bound to the Spring AOP namespace.
3. `xsi:schemaLocation` pairs each namespace URI with its corresponding XSD URL. Missing the `aop` schema pair can prevent the XML parser/schema validator from understanding the XML as expected.
4. The `aop` namespace **provides configuration syntax**; it does not automatically create aspects or target beans merely because `xmlns:aop` is present.

In a Maven project, the minimum dependencies for the following example include compatible `spring-context`, `spring-aop`, and `aspectjweaver`. For `@AspectJ`-style Spring AOP and AspectJ pointcut expressions, the AspectJ library handles parsing/matching, while runtime interception remains Spring proxy; the example does not require the AspectJ compiler or load-time weaving.

## 2. Two Ways to Declare Spring AOP in XML

Spring XML supports two AOP declaration mechanisms. With **schema-based AOP**, `<aop:config>` contains pointcuts and advice elements; the Java bean containing the advice method can be a POJO without `@Aspect`. With **@AspectJ style enabled via XML**, `<aop:aspectj-autoproxy/>` detects registered beans annotated with `@Aspect` and annotations like `@Before`, `@Around`, etc. in Java.

| Configuration | Where rules are declared | Requirements |
| --- | --- | --- |
| `<aop:config>` / `<aop:aspect ref="auditBean">` | Pointcut, advice type, and method mapping live in XML | Target bean and bean containing the Java advice method |
| `<aop:aspectj-autoproxy/>` | Pointcut and advice annotations live in Java `@Aspect` | Target bean, aspect bean, @AspectJ infrastructure enabled |

In both cases, the caller must go through the **Spring AOP proxy**. Do not register the same behavior twice across both mechanisms. The lesson **"aop:aspectj-autoproxy for annotation-based aspects"** specifically verifies how to enable `@Aspect` and register the aspect bean.

## 3. Relationships Between Beans and AOP Tags

A typical diagram:

~~~text
Spring ApplicationContext
    |
    +-- <bean id="orderService" class="...DefaultOrderService"/>
    |       |
    |       +--> target proxied by Spring AOP if pointcut matches
    |
    +-- <bean id="auditFormatter" class="...AuditFormatter"/>
    |       |
    |       +--> dependent bean injected into auditAspectBean
    |
    +-- <bean id="auditAspectBean" class="...AuditAspect">
    |       +-- constructor-arg ref="auditFormatter"
    |
    +-- <aop:config>
            +-- <aop:pointcut id="serviceCalls" .../>
            +-- <aop:aspect ref="auditAspectBean">
                    +-- <aop:around pointcut-ref="serviceCalls"
                                    method="around"/>
~~~

Distinguishing the attributes:

| Element | References | Purpose |
| --- | --- | --- |
| `<aop:aspect ref="auditAspectBean">` | **Spring bean ID** containing the advice method | Specifies the object implementing the aspect |
| `<aop:around method="around">` | **Method name** on the aspect bean | Selects the implementation of the around advice |
| `<aop:around pointcut-ref="serviceCalls">` | **Pointcut ID**, not a bean ID | Selects the join points where advice applies |
| `<constructor-arg ref="auditFormatter">` | **Spring bean ID** supporting the aspect | Injects a dependency into the aspect |
| `<aop:advisor advice-ref="interceptorBean">` | **Spring bean ID** implementing an advice interface | Configures a Spring AOP API-style advisor |

In other words, an ID used in the same string format does not mean it refers to the same kind of object. Spring manages lifecycle and dependency injection for the beans, while `<aop:config>` wires pointcuts to advice for applying proxies.

## 4. Runnable Example: `<aop:config>` with a Dependent Bean

This example uses Java 17, Spring Framework 6.1.15, Maven, and **does not use `@Aspect`**. The aspect receives an `AuditFormatter` bean via its constructor to demonstrate the exact dependency relationship.

Structure:

~~~text
spring-xml-aop-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── Application.java
        │       ├── OrderService.java
        │       ├── DefaultOrderService.java
        │       ├── AuditFormatter.java
        │       └── AuditAspect.java
        └── resources/
            └── applicationContext.xml
~~~

### 4.1. Maven Dependencies

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-xml-aop-demo</artifactId>
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
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Application</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.2. Interface and Target Bean

**src/main/java/demo/OrderService.java**

~~~java
package demo;

public interface OrderService {
    String place(String orderId);
    String reject(String orderId);
}
~~~

**src/main/java/demo/DefaultOrderService.java**

~~~java
package demo;

public class DefaultOrderService implements OrderService {
    @Override
    public String place(String orderId) {
        System.out.println("service: place " + orderId);
        return "accepted " + orderId;
    }

    @Override
    public String reject(String orderId) {
        throw new IllegalArgumentException("rejected " + orderId);
    }
}
~~~

The `DefaultOrderService` class does not need `@Service` because it will be registered via `<bean>` in XML. `OrderService` allows the example to use a JDK interface-based proxy.

### 4.3. Dependent Bean and Java Class Implementing Advice

**src/main/java/demo/AuditFormatter.java**

~~~java
package demo;

public class AuditFormatter {
    public String label(String method) {
        return "audit: " + method;
    }
}
~~~

**src/main/java/demo/AuditAspect.java**

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;

public class AuditAspect {
    private final AuditFormatter formatter;

    public AuditAspect(AuditFormatter formatter) {
        this.formatter = formatter;
    }

    // Invoked by aop:around in XML; no @Around/@Aspect required.
    public Object around(ProceedingJoinPoint joinPoint) throws Throwable {
        String operation = joinPoint.getSignature().getName();
        System.out.println(formatter.label("before " + operation));

        try {
            Object result = joinPoint.proceed();
            System.out.println(formatter.label("after " + operation));
            return result;
        } catch (Throwable ex) {
            System.out.println(formatter.label("error " + operation
                    + " " + ex.getClass().getSimpleName()));
            throw ex;
        }
    }
}
~~~

`AuditAspect` is a Spring bean containing the callback pointed to by XML. The `AuditFormatter` dependency is constructor-injected, not manually created with `new` inside the aspect. Keeping `formatter` `final` makes the dependency relationship explicit; do not store per-call state in mutable fields shared across requests.

### 4.4. Bean Registration and `aop:config`

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

    <!-- 1) Target: bean performing business logic. -->
    <bean id="orderService" class="demo.DefaultOrderService"/>

    <!-- 2) Dependency used by the aspect. -->
    <bean id="auditFormatter" class="demo.AuditFormatter"/>

    <!-- 3) Java bean implementing the advice method. -->
    <bean id="auditAspectBean" class="demo.AuditAspect">
        <constructor-arg ref="auditFormatter"/>
    </bean>

    <!-- 4) AOP configuration via XML schema. -->
    <aop:config proxy-target-class="false">
        <aop:pointcut
            id="serviceCalls"
            expression="execution(* demo.DefaultOrderService.*(..))"/>

        <aop:aspect id="orderAuditAspect" ref="auditAspectBean">
            <aop:around pointcut-ref="serviceCalls" method="around"/>
        </aop:aspect>
    </aop:config>

</beans>
~~~

Key points in the XML:

- `<bean id="orderService">` places the target under Spring's management. If the caller writes `new DefaultOrderService()`, that object is not proxied by Spring AOP.
- `<bean id="auditFormatter">` is an independent dependency.
- `<bean id="auditAspectBean">` must exist for `<aop:aspect ref="auditAspectBean">` to point to it. `constructor-arg ref="auditFormatter"` is Spring dependency injection.
- `<aop:pointcut id="serviceCalls">` defines which methods of the target class will be matched. `<aop:around pointcut-ref="serviceCalls">` uses the declared pointcut ID.
- `method="around"` must match an existing advice method name in `AuditAspect`; it is **not** an annotation name.
- `proxy-target-class="false"` tells Spring to prefer an interface-based proxy if the target has a suitable interface. In this example, `OrderService` is the interface through which the caller retrieves and invokes the bean.
- `aop:config` registers the XML-based advisor/auto-proxy infrastructure. This configuration is self-sufficient for schema-based aspects; there is no need to add `<aop:aspectj-autoproxy/>` just to run `AuditAspect`.

Inside an `<aop:config>`, the element declaration order per the Spring schema is **pointcut, advisor, then aspect**; if using multiple types, maintain this order so the XML remains valid. Specific advice tags are declared inside `<aop:aspect>`.

### 4.5. Retrieving the Bean from Spring Context and Running

**src/main/java/demo/Application.java**

~~~java
package demo;

import org.springframework.context.support.ClassPathXmlApplicationContext;

public class Application {
    public static void main(String[] args) {
        try (var context =
                     new ClassPathXmlApplicationContext("applicationContext.xml")) {
            OrderService service = context.getBean(OrderService.class);

            System.out.println("result: " + service.place("O-7"));

            try {
                service.reject("O-9");
            } catch (IllegalArgumentException ex) {
                System.out.println("caught: " + ex.getMessage());
            }
        }
    }
}
~~~

From the project directory, run:

~~~bash
mvn -q compile exec:java
~~~

The program's `System.out` lines in order:

~~~text
audit: before place
service: place O-7
audit: after place
result: accepted O-7
audit: before reject
audit: error reject IllegalArgumentException
caught: rejected O-9
~~~

Maven/the application may produce other infrastructure logs depending on environment configuration, but the lines above show the essential business execution order.

**Execution flow explanation**: `context.getBean(OrderService.class)` returns the service bean proxied by Spring AOP when the pointcut matches. The caller invokes `place()` through the proxy; the interceptor calls `AuditAspect.around()`; the aspect uses the `AuditFormatter` bean, then `proceed()` enters `DefaultOrderService.place()`. If the target throws an exception, the advice logs the error label and rethrows it; the caller still receives `IllegalArgumentException`.

**When misconfigured**: removing `<bean id="auditFormatter"...>` or changing `ref="auditFormatter"` to a nonexistent ID prevents Spring from fully initializing `AuditAspect`. Removing `<bean id="auditAspectBean"...>` while keeping `<aop:aspect ref="auditAspectBean">` makes the aspect reference invalid. Those are bean wiring errors, not `execution(...)` expression errors.

## 5. What Other Elements Does `aop:config` Support?

Besides `<aop:aspect>`, `<aop:config>` supports **named pointcuts** at the configuration level, **advisors** using an advice interface, and the advice types `before`, `after-returning`, `after-throwing`, `after`, and `around`. For example:

~~~xml
<aop:config>
    <aop:pointcut id="serviceCalls"
                  expression="execution(* demo..*Service.*(..))"/>
    <aop:aspect ref="auditBean">
        <aop:before pointcut-ref="serviceCalls" method="before"/>
    </aop:aspect>
</aop:config>
~~~

This is a fragment: the `auditBean` bean needs a compatible `before()` method. An `<aop:advisor advice-ref="interceptorBean" .../>` substitutes a **bean implementing Advice/MethodInterceptor** rather than calling an arbitrary Java method. If all three groups are present at the `aop:config` level, the XSD requires **pointcut → advisor → aspect**. The lessons **"aop:config and aop:aspect declaration"**, **"Named pointcuts and pointcut-ref"**, and **"aop:before...around"** respectively explain the structure, scope sharing, and semantics of each advice type.

## 6. Properly Registering the Beans Required by AOP

### 6.1. Business Bean (Target)

The target must be a **Spring-managed bean**, via `<bean>`, component scanning, or equivalent bean configuration. When using pure XML, `<bean id="orderService" class="..."/>` directly is the easiest to verify. Merely declaring a pointcut does not create a matching bean.

A bean is proxied when Spring has an advisor matching a suitable method/target. Not every bean in the context is wrapped in a proxy, and the bean name retrieved from the context may point to the proxy rather than the original target instance.

### 6.2. Aspect Bean and Its Dependencies

With schema-based configuration:

~~~xml
<bean id="auditFormatter" class="demo.AuditFormatter"/>

<bean id="auditAspectBean" class="demo.AuditAspect">
    <constructor-arg ref="auditFormatter"/>
</bean>

<aop:config>
    <aop:aspect ref="auditAspectBean">
        <aop:before
            pointcut="execution(* demo..*Service.place(..))"
            method="before"/>
    </aop:aspect>
</aop:config>
~~~

This is only a wiring pattern; the Java `AuditAspect` must have a `before` method if used instead of the `around` version in Section 4. The aspect's dependent beans use standard Spring beans namespace syntax (`constructor-arg`, `property`, or `autowire` if configured). `<aop:aspect ref>` must point to the bean backing the aspect; it is not a dependency injection mechanism.

If the aspect depends on another repository/client/service, declare the appropriate bean and inject it into the aspect. Be careful to avoid an overly broad pointcut accidentally intercepting methods of the aspect itself or its supporting beans, causing loops or unexpected logging.

### 6.3. Scope, Initialization, and Bean Ordering

- For schema-defined aspects, Spring supports the **singleton** model for aspect instances, so do not put request state into mutable fields of the aspect. For per-call data, use local variables inside the advice or an appropriate context mechanism.
- Constructor injection via `ref` tells Spring which dependencies need to be initialized/resolved. For ordinary singleton beans, the container creates the appropriate dependencies when initializing the aspect; **the order of `<bean>` lines in the same XML file is not a tool for ordering advice logic**.
- The execution order of multiple advisors/aspects is an AOP ordering concern (`order`, `Ordered`, `@Order` depending on how it is declared); do not infer it from `<bean>` placement order or when dependencies are injected.
- `depends-on` is an initialization-control mechanism when an ordering relationship is needed without direct dependency injection; if `constructor-arg ref` is already present, `depends-on` is normally unnecessary just to make the formatter bean ready. `depends-on` does not replace `ref` and does not determine advice order.

## 7. XML Variant: Enabling `@Aspect` Classes via `aop:aspectj-autoproxy`

When advice is written in an `@Aspect` class, XML can enable it via `<aop:aspectj-autoproxy/>` and register the aspect with `<bean>`:

~~~xml
<bean id="orderService" class="demo.DefaultOrderService"/>
<bean id="annotatedAuditAspect" class="demo.AnnotatedAuditAspect"/>
<aop:aspectj-autoproxy/>
~~~

`demo.AnnotatedAuditAspect` must actually have `@Aspect` and advice annotations. If it needs `AuditFormatter`, register the formatter bean and inject it via `constructor-arg ref="auditFormatter"` like a normal bean. `@Aspect` alone does not create a bean, and `<aop:aspectj-autoproxy>` does not automatically enable component scanning. In this style, there is no need to add `<aop:aspect ref="annotatedAuditAspect">` to redefine the same advice.

## 8. Impact of Proxy Configuration on Bean Wiring

`proxy-target-class="false"` allows Spring to prefer a **JDK interface proxy** for beans with a suitable interface; callers should retrieve the bean via its interface, such as `OrderService.class`. `proxy-target-class="true"` requests a **class-based proxy** and has limitations with `final` classes and `final`/`private` methods. Spring may merge auto-proxy settings within the same context, so another configuration requiring CGLIB can affect the outcome.

Regardless of proxy type, `this.otherMethod()` inside the target and `new Target()` outside the container do not automatically go through the proxy. To learn about `expose-proxy`, `AopContext.currentProxy()`, thread-local boundaries, and how to inspect the actual proxy yourself, see the lesson **"proxy-target-class and expose-proxy in XML configuration"**.

## 9. Common Errors When Configuring the Namespace and Dependent Beans

| Symptom | Possible Cause | How to Check/Fix |
| --- | --- | --- |
| XML parser does not recognize `aop:config` | Missing `xmlns:aop`, `schemaLocation` pair, or incompatible XSD | Verify the URI against the official `spring-aop.xsd` |
| Context reports referenced bean not found | `ref="auditAspectBean"`, `constructor-arg ref`, or `advice-ref` points to a nonexistent ID | Check the exact bean ID and the context containing the bean |
| Spring fails to create aspect bean | Constructor dependency not registered or signature/constructor-arg mismatch | Check supporting `<bean>` definitions and the aspect constructor |
| Advice does not run | Pointcut does not match class/method, target is not Spring-managed, caller uses `new` | Inspect the actual bean from ApplicationContext and the pointcut |
| Advice does not run on same-bean calls | Self-invocation `this.method()` bypasses the proxy | Invoke across an appropriate Spring bean proxy boundary |
| `<aop:aspect ref="...">` declared but advice method missing | Wrong `method="..."` name or wrong signature | Match the exact method on the backing aspect bean |
| Using `<aop:aspectj-autoproxy/>` but `@Aspect` does not run | `@Aspect` bean not registered or missing `aspectjweaver` | Register via `<bean>`/component scan and check classpath |
| Duplicate logs | Same advice defined in both schema-based and `@Aspect`, or multiple matching advisors | Remove duplicate configuration, inspect proxy/advisor chain |
| `getBean(DefaultOrderService.class)` does not work as expected | Bean is currently a JDK interface proxy | Retrieve via `OrderService`, or consider a class proxy |
| XML has `&&` in expression | Unescaped ampersand character | Use `and` or `&amp;&amp;` |
| `<aop:advisor advice-ref>` references a plain bean | Advice bean does not implement the Spring AOP Advice/MethodInterceptor contract | Register a compatible API advice class |
| Unexpected advice order | Misinterpreting bean declaration order as interception order | Explicitly configure and test advisor order |

## 10. Testing XML Configuration in Spring

Tests should initialize the context using **the same XML** that the application uses; do not `new` the target to test advice. Valuable checks include:

1. Context starts successfully: schema is parsed, bean IDs and dependencies are resolved.
2. Retrieve the bean via its interface; verify that calling `place` goes through before → service → after, while `reject` goes through before → error and the original exception still reaches the caller.
3. If removing `<aop:config>` in an isolated test environment, observe direct target output without advice logs: this helps pinpoint the activation point.
4. Change the pointcut in a test environment to intentionally exclude `place` from the match region; verify advice does not run to confirm the expression is active.
5. Configure another advisor/aspect: measure the exact interception count and ordering instead of guessing.
6. Verify the `AuditAspect` bean is properly injected with `AuditFormatter`; do not share mutable per-request state on a singleton aspect.
7. If switching between JDK/class proxies, verify how the bean is retrieved and which methods are eligible for advice.

You can inspect the proxy mechanism in a Java test:

~~~java
import org.springframework.aop.support.AopUtils;
import org.springframework.context.support.ClassPathXmlApplicationContext;

try (var context =
         new ClassPathXmlApplicationContext("applicationContext.xml")) {
    Object service = context.getBean("orderService");
    System.out.println(AopUtils.isAopProxy(service)); // true if proxied
}
~~~

This snippet is **an illustrative check embedded inside a Java method/runner**, not a standalone file with `main`. `isAopProxy` indicates whether the returned instance is a Spring AOP proxy; it does not prove that every method is matched by the pointcut. When debugging, inspect method names, proxy type, advisors, and how callers invoke the bean.

## 11. Distinguishing Three Lifecycle and Responsibility Failures

**Bean definition failure**: Spring has not created a dependency such as `auditFormatter`; the context may fail before any business method is called. Fix `<bean>`, `ref`, constructor injection, or ApplicationContext scope.

**Advisor/pointcut mismatch**: the context starts and the target runs, but the method is outside the expression, so the advice may not be applied. Inspect `execution(...)`, the actual class, and the proxy boundary.

**Business exception**: the target method is actually invoked and throws an error; `@AfterThrowing` or `aop:around` can log the error before the caller sees the exception. Preserve the exception and ensure advice does not accidentally swallow errors unless business requirements specify another policy.

These are three distinct situations, and Spring XML provides inspection signals in different places.

## Summary

In Spring AOP XML configuration, `xmlns:aop` and `spring-aop.xsd` provide the syntax, **`<aop:config>`** declares pointcuts and advice, and **`<bean>`** creates target/aspect objects along with dependencies needing injection. `<aop:aspect ref>` links to the bean implementing the advice; `pointcut-ref` links to the pointcut; `method` links to the method name. If choosing the Java `@Aspect` style, enable `<aop:aspectj-autoproxy/>` and still register the aspect bean. Every invocation must pass through the Spring proxy for advice to apply.

### Official Spring Documentation

- [Spring Framework — Schema-based AOP Support](https://docs.spring.io/spring-framework/reference/core/aop/schema.html)
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — XML Schema-based Configuration](https://docs.spring.io/spring-framework/reference/core/appendix/xsd-schemas.html)