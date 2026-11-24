# `proxy-target-class` and `expose-proxy` in Spring AOP XML Configuration

## 1. Why Are These Two Attributes Needed?

In Spring Framework, a bean advised by Spring AOP is normally supplied to callers as a **proxy**. When configuring aspects in XML, two attributes have significant impact yet solve **two different problems**:

- `proxy-target-class`: decides which kind of proxy Spring prefers for proxyable beans, especially when the class implements an interface. `true` requests a class-based proxy (CGLIB); `false` allows Spring's default mechanism to choose a JDK dynamic proxy when a suitable interface exists, while classes without interfaces still need a class proxy.
- `expose-proxy`: decides whether Spring temporarily exposes the current proxy to `AopContext.currentProxy()` on **the thread currently executing a proxied call**. `true` enables that access; `false` is the default and does not guarantee reading the proxy.

Both attributes appear on **`<aop:config>`** (schema-based aspects) and **`<aop:aspectj-autoproxy>`** (auto-detecting `@Aspect` beans). They are settings of the **Spring AOP proxy** mechanism, not AspectJ compile-time weaving or load-time weaving techniques.

### Quick Comparison Table

| XML | Primary Effect | What It Cannot Do |
| --- | --- | --- |
| `proxy-target-class="false"` | Uses normal proxy selection rules; beans with interfaces usually receive JDK proxies, beans without interfaces use class proxies. | Cannot force a JDK proxy for a class with no interfaces; does not fix self-invocation. |
| `proxy-target-class="true"` | Forces class proxies (CGLIB) for beans handled by the corresponding auto-proxy creator. | Cannot intercept `private`, `final` methods, or self-invocation via `this`. |
| `expose-proxy="false"` | Does not enable looking up the current proxy via `AopContext.currentProxy()`. | Does not mean advice is disabled; calls through the proxy are still intercepted. |
| `expose-proxy="true"` | Allows `AopContext.currentProxy()` to work inside a call managed by an AOP proxy. | Does not automatically turn `this.method()` into a proxy call; does not propagate the proxy to other threads. |

## 2. Writing Valid Spring Schema XML

Example `src/main/resources/aop.xml` using the Spring AOP schema:

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

    <bean id="orderService" class="com.example.springxml.OrderService"/>
    <bean id="traceAdvice" class="com.example.springxml.TraceAdvice"/>

    <aop:config proxy-target-class="false" expose-proxy="true">
        <aop:aspect ref="traceAdvice">
            <aop:pointcut id="orderMethods"
                          expression="execution(* com.example.springxml.OrderService.*(..))"/>
            <aop:around method="around" pointcut-ref="orderMethods"/>
        </aop:aspect>
    </aop:config>
</beans>
```

Meaning in Spring:

1. `<aop:config>` registers the infrastructure to auto-create proxies when an advisor matches a bean.
2. `<aop:aspect ref="traceAdvice">` points to a bean containing plain Java advice methods; **this advice bean does not have to carry `@Aspect`** because XML already declares the aspect.
3. `<aop:pointcut>` specifies which `OrderService` method executions apply; `<aop:around>` binds the `around` method to the named pointcut.
4. `proxy-target-class="false"` allows choosing a JDK proxy for `OrderService` since the example below has an interface. `expose-proxy="true"` lets the service retrieve the proxy while executing inside an advised call.

XML syntax uses `proxy-target-class` and `expose-proxy` (kebab-case), differing from Java attribute names `proxyTargetClass` and `exposeProxy`. Do not write `proxyTargetClass` directly in an XML tag.

### When Using `@Aspect` Instead of XML-Declared Aspects

If the aspect is a Java bean annotated with `@Aspect`, you can enable detection with:

```xml
<aop:aspectj-autoproxy proxy-target-class="true"
                       expose-proxy="true"/>
```

`@Aspect` beans still must be registered via `<bean>` or component scanning. This tag **does not create aspect beans automatically** and differs from `<aop:config><aop:aspect ...>`. Usually pick the declaration style fitting the project; avoid creating duplicate advisors by configuring both paths. Both require Spring AOP on the classpath and AspectJ expression parsing support (typically `aspectjweaver`).

## 3. Java 17+ Example Observing Proxy Type and Self-Invocation

The following example runs with **Spring Framework + Spring AOP initialized directly via XML**, without relying on Spring Boot auto-configuration; as a result, comparing `proxy-target-class` yields easily controlled outcomes. Code layout:

```text
src/main/java/com/example/springxml/
  OrderOperations.java
  OrderService.java
  TraceAdvice.java
  Demo.java
src/main/resources/aop.xml
```

**`OrderOperations.java`** — interface used by the caller:

```java
package com.example.springxml;

public interface OrderOperations {
    void place();
    void reserve();
}
```

**`OrderService.java`** — two ways of calling the same `reserve()` method:

```java
package com.example.springxml;

import org.springframework.aop.framework.AopContext;

public class OrderService implements OrderOperations {

    @Override
    public void place() {
        System.out.println("service: place");

        // Direct call on 'this': does not go through the Spring proxy.
        this.reserve();

        // Goes through the Spring proxy currently exposed during place().
        ((OrderOperations) AopContext.currentProxy()).reserve();
    }

    @Override
    public void reserve() {
        System.out.println("service: reserve");
    }
}
```

**`TraceAdvice.java`** — POJO containing the advice referenced in XML:

```java
package com.example.springxml;

import org.aspectj.lang.ProceedingJoinPoint;

public class TraceAdvice {

    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String method = pjp.getSignature().getName();
        System.out.println("before: " + method);
        try {
            return pjp.proceed();
        } finally {
            System.out.println("after: " + method);
        }
    }
}
```

**`Demo.java`** — retrieving the bean via its interface and inspecting the proxy:

```java
package com.example.springxml;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public class Demo {

    public static void main(String[] args) {
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("aop.xml")) {

            OrderOperations orders =
                    context.getBean("orderService", OrderOperations.class);

            System.out.println("aopProxy=" + AopUtils.isAopProxy(orders));
            System.out.println("jdkProxy=" + AopUtils.isJdkDynamicProxy(orders));
            orders.place();
        }
    }
}
```

**Required dependencies:** `spring-context`, `spring-aop`, and `org.aspectj:aspectjweaver` at compatible versions (manageable via a Spring/Boot BOM). The Java example above needs those libraries on the classpath; plain JDK `javac` alone is not enough. In a Maven project configured with `exec-maven-plugin`, you can run main with `mvn compile exec:java -Dexec.mainClass=com.example.springxml.Demo`. In Gradle with the `application` plugin, set main class to `com.example.springxml.Demo` and run the `run` task. These commands assume appropriate dependencies/plugins are declared.

With the XML in Section 2, the lines printed by the example code (excluding other runtime logging) in order will be:

```text
aopProxy=true
jdkProxy=true
before: place
service: place
service: reserve
before: reserve
service: reserve
after: reserve
after: place
```

Explanation: `orders.place()` calls into the JDK proxy and passes through `around`. `this.reserve()` executes directly on the target, so only `service: reserve` prints. Calling `AopContext.currentProxy().reserve()` goes back through the proxy, producing both `before: reserve` and `after: reserve`. `AopContext.currentProxy()` is called on the same thread inside the method currently handled by the proxy; calling it outside those conditions can cause Spring to throw `IllegalStateException`.

## 4. Changing `proxy-target-class`: What Output Changes?

Change only the attribute in the XML file:

```xml
<aop:config proxy-target-class="true" expose-proxy="true">
    <!-- Keep the aspect, pointcut, and beans from the example intact -->
</aop:config>
```

**This is an abbreviated snippet showing attribute placement:** in the runnable file you must keep the `<aop:aspect>` and `<aop:pointcut>` child elements from Section 2 rather than replacing them with a comment. After this change, Spring creates a proxy based on a subclass of `OrderService`; the first lines become:

```text
aopProxy=true
jdkProxy=false
```

The `before/after/service` logs of the example remain the same. In this CGLIB configuration, `context.getBean("orderService", OrderService.class)` works because the proxy is a subclass of the target class; in JDK proxy mode, the bean is injected/cast via `OrderOperations`, whereas looking up specifically `OrderService.class` can fail to match the type.

Points to remember:

- `false` is not a promise of "always a JDK proxy". Without a suitable interface, Spring needs a class proxy.
- `true` requests a class proxy even when the target has an interface. It **does not** turn Spring AOP into bytecode weaving or make `final`/`private` methods interceptable.
- CGLIB uses a subclass of the target; `final` classes cannot be subclassed to be proxied. `final` methods cannot be overridden; `private` methods are not advised under this mechanism. JDK proxies only expose methods of the proxied interfaces to callers.
- When code injects via an interface, switching to CGLIB is usually unnecessary just to invoke methods declared on that interface. If switching in order to inject the concrete target type or intercept class-only methods, test thoroughly.
- You can use `AopUtils.isCglibProxy(bean)` and `AopUtils.isJdkDynamicProxy(bean)` in integration tests; avoid assuming fixed runtime class names.

### Multiple XML Configurations and the "Strongest Wins" Mechanism

Spring merges auto-proxy creator configurations within the **same ApplicationContext**. If one `<aop:config>` enables `proxy-target-class="true"` while another configuration leaves it `false`, enabling class proxies can affect all beans proxied by those AOP mechanisms, including interacting configurations such as `<aop:aspectj-autoproxy>` and `<tx:annotation-driven>`. A local `false` value is not guaranteed to override a `true` setting from another configuration.

Therefore, when actual behavior differs from the example, inspect all imported XML files alongside Spring AOP and transaction infrastructure. In Spring Boot, auto-configuration may default to class proxies depending on version/settings; `spring.aop.proxy-target-class` is a Spring Boot-level property, whereas the XML attributes here belong to Spring Framework. Do not use a Boot application's defaults to infer the output of a pure `ClassPathXmlApplicationContext` example.

## 5. Changing `expose-proxy`: Impact and Boundaries

If you change `expose-proxy` alone to `false`:

```xml
<aop:config proxy-target-class="false" expose-proxy="false">
    <!-- Keep the aspect and pointcut from the example intact -->
</aop:config>
```

`this.reserve()` inside `place()` still executes directly without advice. However, `AopContext.currentProxy()` has no exposed current proxy under this setting, so it throws `IllegalStateException`. Because `TraceAdvice.around` has `finally`, the logs before the error propagates out of the caller (excluding startup) will be:

```text
aopProxy=true
jdkProxy=true
before: place
service: place
service: reserve
after: place
```

A stack trace may follow if the exception escapes `main`. This is **intentional behavior to distinguish the settings**: toggling `expose-proxy` does not determine whether a bean gets advised; it only controls whether the proxy can be looked up within the context of an actively intercepted call.

### Why Doesn't Spring Automatically Fix Self-Invocation?

In Spring AOP, external calls entering the proxy trigger the interceptor chain. Inside the target's body, `this` remains the target object; `this.reserve()` bypasses the proxy. Setting `proxy-target-class="true"` does not change this either.

When advice must run on an internal call, the sensible order of choices is:

1. **Extract the method needing interception into another Spring bean**, so the current bean calls it through an injected reference; this is easy to test and keeps business code decoupled from Spring AOP APIs.
2. If the architecture requires keeping it in the class, you can route the call through a self-reference pointing to the bean proxy, though dependency cycles and proxy types must be handled carefully.
3. Only when necessary enable `expose-proxy="true"` and call `AopContext.currentProxy()`. This couples business source directly to Spring AOP, makes plain-Java unit testing harder, and adds current-proxy lookup overhead.

**Limitations of `AopContext.currentProxy()`:**

- The proxy is exposed via a context bound to the current AOP call's thread; it does not carry over automatically to `CompletableFuture`, `@Async`, `ExecutorService`, or other threads.
- Calling it from a constructor, from an object created with `new`, before entering a proxied call, or after exiting a proxied call has no guarantee of retrieving a proxy.
- The return type is `Object`. With a JDK proxy, cast to **a proxied interface**; casting to the implementation class causes `ClassCastException`.
- The retrieved proxy must be the Spring proxy associated with the current call; `expose-proxy` does not provide a global singleton lookup.
- Enabling `true` "just in case" is unnecessary. It introduces coupling and overhead even when the application never uses `AopContext`.

## 6. Comparing `<aop:config>`, `<aop:aspectj-autoproxy>`, and Java Config

| Context | Configuration | When to Use |
| --- | --- | --- |
| Plain Java aspect declared via Spring XML | `<aop:config proxy-target-class="true" expose-proxy="true"> ... </aop:config>` | Advice/pointcuts live in XML, referencing beans via `ref`. |
| Spring-detected `@Aspect` bean | `<aop:aspectj-autoproxy proxy-target-class="true" expose-proxy="true"/>` | Advice/pointcuts live in Java `@Aspect`, XML enables auto-proxy. |
| Spring `@Configuration` | `@EnableAspectJAutoProxy(proxyTargetClass = true, exposeProxy = true)` | Same two semantics in Java configuration. |
| Programmatic AOP | `ProxyFactory.setProxyTargetClass(true)` and `ProxyFactory.setExposeProxy(true)` | Manual proxy creation via `ProxyFactory`, unlike context-wide XML auto-proxy. |

Note that `<aop:scoped-proxy proxy-target-class="..."/>` belongs to scoped proxies for scoped beans; do not equate it with `expose-proxy` on `<aop:config>`/`<aop:aspectj-autoproxy>`.

In a Boot application, import XML via `@ImportResource("classpath:aop.xml")` when integrating legacy configuration into Java configuration; then inspect beans and auto-proxy settings that Boot or other modules may already have registered. This is not a reason to duplicate AOP tags in multiple places.

## 7. Checking Configuration and Troubleshooting

| Symptom | Check | Resolution |
| --- | --- | --- |
| `getBean(..., OrderService.class)` fails, while injecting the interface works | Bean is a JDK dynamic proxy | Inject the interface; force a class proxy only when actually required. |
| Method has no advice despite a configured pointcut | Was the proxy created, does the method match, or does the call go via `this` | Check `AopUtils.isAopProxy`, the expression, and how callers obtain the bean from context. |
| `AopContext.currentProxy()` throws `IllegalStateException` | `expose-proxy` not enabled or called outside a proxied call | Prefer calling another bean; if `AopContext` is required, enable the setting and check thread/call path. |
| `ClassCastException` on `(OrderService) AopContext.currentProxy()` | Actual proxy is a JDK interface proxy | Cast to `OrderOperations` or consider a class proxy. |
| `proxy-target-class="true"` set yet Spring fails to create proxy | `final` target class, `final` method, Java module/classloading restriction, or infra conflict | Adjust target proxyability and inspect bean definitions and JVM/runtime. |
| `proxy-target-class="false"` set yet still seeing CGLIB | Target has no interface or another config forces `true` | Audit the same `ApplicationContext`, `<tx:annotation-driven>`, `<aop:aspectj-autoproxy>`, and Boot. |
| XML written yet Spring reports unknown `aop:` | Missing `xmlns:aop`, schemaLocation, or AOP dependency | Declare proper Spring AOP XSD and compatible libraries. |
| Advice called twice | Duplicate advisor/aspect registration, two aspect beans, or overlapping pointcuts | Inspect XML/Java configs in the same context and keep one clear registration path. |

You can test the proxy in an integration test after context startup:

```java
Object bean = context.getBean("orderService");

assert org.springframework.aop.support.AopUtils.isAopProxy(bean);
assert org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean);
```

Both `assert` lines belong to **the example's `proxy-target-class="false"` XML scenario** and require `-ea` if run as plain Java code; in JUnit tests, use `assertTrue(...)`. You also need to test advice traces (a counter or log collector), because checking the proxy class alone does not prove the pointcut expression actually applied.

### Review Checklist When Modifying Real XML

1. Identify whether `<aop:config>` or `<aop:aspectj-autoproxy>` is used and whether aspect/advice beans are registered.
2. List the interfaces consumers use to inject the bean; only enable class proxies when class/methods outside the interface are required.
3. Decide whether self-invocation truly needs interception. If so, prefer extracting a bean; if using `AopContext`, verify `expose-proxy` and proxied call paths.
4. Check the impact of `<tx:annotation-driven>`, Spring Boot AOP, `@EnableAspectJAutoProxy`, or multiple XML files on the merged auto-proxy creator.
5. Run tests with beans retrieved from the Spring context, testing success/failure paths, comparing proxy types, counting advice invocations, and checking callers that inject concrete classes.

## 8. Official Spring Documentation for Reference

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): choosing JDK/CGLIB, self-invocation, and `AopContext`.
- [Spring Framework 6.2 — Schema-based AOP Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/schema.html): `<aop:config>`, declaring XML aspects, pointcuts, and advice.
- [Spring AOP XSD](https://www.springframework.org/schema/aop/spring-aop.xsd): confirms both `proxy-target-class` and `expose-proxy` are supported on `config` and `aspectj-autoproxy`.

**Key takeaway:** `proxy-target-class` controls the **proxy type**; `expose-proxy` controls **whether the current proxy can be retrieved via `AopContext`**. Both operate within Spring AOP's proxy mechanism and do not automatically resolve self-invocation through `this`.