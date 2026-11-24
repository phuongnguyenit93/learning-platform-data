# Distinguishing @AspectJ in Spring AOP from AspectJ Weaving

## 1. Two Mechanisms That Can Share Syntax Yet Work Differently

In Spring Framework, `@AspectJ` is an **aspect declaration style using AspectJ annotations**, such as `@Aspect`, `@Before`, `@Around`, and `execution(...)` expressions. **Spring AOP reads those declarations to create proxies for Spring beans**. Using these annotations does not mean AspectJ is weaving the application's bytecode.

Separate three concepts when reading configurations or diagnosing issues:

- **Declaration:** a Java class annotated with `@Aspect` and advices using `org.aspectj.lang.annotation.*` annotations. This is shared syntax.
- **Execution engine in Spring AOP:** Spring selects matching beans/methods, creates a JDK dynamic proxy or CGLIB subclass proxy; only calls **passing through the proxy** are routed through the advice chain and then to the target object.
- **Actual weaving with AspectJ:** the AspectJ compiler/weaver modifies the bytecode of affected classes at compile time, post-compile time, or load time. Advice does not depend on whether the call passes through a Spring proxy.

Therefore, `@Aspect`, `@EnableAspectJAutoProxy`, `spring-boot-starter-aop`, or the `aspectjweaver` dependency **do not by themselves prove that bytecode is being woven**. Spring uses the AspectJ library to parse/match pointcuts, while Spring AOP's execution mechanism remains proxying.

> Article scope: how Spring AOP integrates `@AspectJ` syntax, how it differs from AspectJ weaving in Spring applications, and technical consequences when choosing a mechanism. Standalone AspectJ theory outside Spring is not expanded here.

## 2. Practical Spring Comparison Table

| Criterion | Spring AOP Using `@AspectJ` | AspectJ Weaving in a Spring Application |
| --- | --- | --- |
| Tool applying advice | Spring's auto-proxy infrastructure | AspectJ compiler/weaver |
| What is modified | Bean is wrapped by a proxy; target class code remains essentially unchanged | Bytecode of woven classes is transformed |
| Main interception point | Spring AOP's practical join point is **method execution** on a Spring bean through a proxy | Can use method execution and other join points such as field access, constructors, and method calls when weaving supports them |
| Object scope | Objects managed by Spring that have been proxied | Classes/objects woven according to configuration scope, including non-Spring-bean objects |
| Calling `this.otherMethod()` inside a bean | Goes directly from target to target, typically bypassing advice on `otherMethod()` | Can be advised because the target join point's bytecode has been woven |
| `private`, `final`, constructor | Cannot be handled by proxy alone in a way equivalent to weaving; CGLIB cannot override `final`/`private` | Can intercept many of those join points if the aspect/pointcut and weaving mode are appropriate |
| Startup and operation | No `ajc`, `aop.xml` file, or Java agent needed to use Spring AOP | Requires weaving workflow setup: `ajc` or AspectJ LTW (weaver/agent, `META-INF/aop.xml`, appropriate classloader) |
| Spring integration level | Follows bean lifecycle, proxies, advisors, `ApplicationContext` | Can combine with Spring to configure weaving/aspects, though weaving happens on classes |
| Configuration cost and risk | Fewer operational steps; subject to proxy limitations | Deeper control, but requires managing weave scope, agent/build, class loading, and compatibility testing |

The accurate statement is: **Spring AOP can use @AspectJ syntax; AspectJ weaving can also use aspects written in @AspectJ style; sharing annotation code does not make the two execution mechanisms identical.**

## 3. How Does Spring Turn `@AspectJ` Into Proxies?

A typical flow:

~~~text
@Configuration / @Component + @Aspect registered as a Spring bean
       |
@EnableAspectJAutoProxy (or Spring Boot AOP auto-configuration)
       |
Spring detects the aspect, parses pointcuts, creates advisors
       |
Matching bean is exposed via a proxy
       |
Caller -> proxy -> advice chain -> target.method()
                               -> return value / exception
~~~

To enable via plain Spring Java config:

~~~java
@Configuration
@EnableAspectJAutoProxy
class AopConfiguration {
}
~~~

An aspect must be an **actual bean** in `ApplicationContext`. It can be declared with `@Bean`, or by using both `@Aspect` and `@Component` if component scanning is enabled. **Having only `@Aspect` does not automatically register a class as a Spring bean.** When using Spring Boot, the `spring-boot-starter-aop` dependency usually provides auto-proxy configuration out of the box; the aspect still must be registered.

Spring Framework has two common proxy types:

1. **JDK dynamic proxy:** wraps the bean's interfaces; callers interact through an interface.
2. **CGLIB class proxy:** creates a subclass to intercept overridable methods. Spring can choose CGLIB when the bean has no interface or when configuration forces class proxies such as `@EnableAspectJAutoProxy(proxyTargetClass = true)`. The default proxy type should be checked in the actual Spring/Spring Boot configuration, not guessed solely from whether the class has an interface.

Whether using JDK proxy or CGLIB, **internal calls on `this` still do not return through the proxy**. Forcing `proxyTargetClass = true` does not solve self-invocation.

### Pointcut Limitations in Spring

Spring AOP supports a subset of AspectJ expressions centered around *method execution* such as `execution`, `within`, `args`, `@annotation`, `target`/`@target`, `this`, and `bean` (a Spring-specific extension). Spring does not turn `call(...)`, `get(...)`, `set(...)`, or `cflow(...)` into new join points. Designators requiring a weaving mechanism may raise errors when passed to Spring AOP.

`bean(orderService)` is useful for filtering by **Spring bean name** in Spring AOP; this is a Spring extension and not an equivalent pointcut that can be ported verbatim to pure AspectJ weaving. In proxy AOP, `this` refers to the proxy while `target` refers to the object behind the proxy; the difference is clearest with JDK dynamic proxies.

## 4. Runnable Java 17+ Example: Same Bean, Two Call Paths

The example uses **Spring Framework 6.2.0 + AspectJ Weaver 1.9.22** to demonstrate Spring AOP via proxying, without enabling weaving. Directory:

~~~text
spring-aop-demo/
├── pom.xml
└── src/main/java/demo/Demo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-aop-demo</artifactId>
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
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
        <configuration>
          <mainClass>demo.Demo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

`src/main/java/demo/Demo.java`:

~~~java
package demo;

import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class Demo {
    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    static class Config {
        @Bean
        PaymentService paymentService() {
            return new PaymentService();
        }

        @Bean
        AuditAspect auditAspect() {
            return new AuditAspect();
        }
    }

    public static class PaymentService {
        public void pay() {
            System.out.println("PAY");
        }

        public void batch() {
            System.out.println("BATCH");
            this.pay();
        }
    }

    @Aspect
    public static class AuditAspect {
        @Before("execution(* demo..*.pay(..))")
        public void beforePay() {
            System.out.println("ADVICE");
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            PaymentService bean = context.getBean(PaymentService.class);
            bean.pay();   // Caller -> Spring proxy -> advice -> target
            bean.batch(); // Proxy -> target.batch() -> this.pay(), does not go through proxy a second time
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the application (ignore extra environment messages if Maven outputs them):

~~~text
ADVICE
PAY
BATCH
PAY
~~~

Why is there only **one** `ADVICE` line?

- `bean.pay()` is called **through the Spring proxy**, so `@Before` runs before `PaymentService.pay()`.
- `bean.batch()` goes through the proxy but does not match the `pay` pointcut; inside the target, `this.pay()` calls the method directly on the same object and thus does not go through the proxy. `@Before` does not run a second time.
- Setting `proxyTargetClass` to `true`, adding the `aspectjweaver` dependency, or changing annotation placement does not turn that internal call into a call going through the proxy.

This is a standalone runnable example with Maven and Java 17+. It demonstrates the Spring AOP mechanism; **it does not demonstrate an active AspectJ weaving setup**.

### How to Address the Interception Need Directly Within Spring AOP

If you want handling every time `pay()` is called across a boundary, the clearest Spring solution is usually to move `pay()` into a **separate bean**, and have `batch()` call the Spring-injected bean. Then the call passes through the proxy. Self-injecting the proxy or calling `AopContext.currentProxy()` can work in some setups, but increases coupling to Spring AOP and requires careful lifecycle configuration/control. Do not resort to weaving just to dodge every self-invocation when responsibilities can reasonably be split between beans.

## 5. When Does AspectJ Weaving Appear in a Spring Application?

Spring documents integration with **AspectJ compile-time weaving (CTW)**, **post-compile weaving**, and especially **load-time weaving (LTW)**. The core point: AspectJ transforms designated bytecode rather than wrapping a bean individually in a proxy. With LTW, the transformation happens when classes are loaded into the JVM (before the class is used). With CTW/post-compile, the build produces woven bytecode.

For LTW, an illustrative configuration usually has three coordinated parts:

1. **A suitable aspect** compiled and on the classpath, declared with AspectJ syntax or `@AspectJ` style.
2. **Weaver and weave scope**: the AspectJ weaver (for example via `-javaagent:/path/to/aspectjweaver.jar`) along with a `META-INF/aop.xml` declaration; specify the packages to weave.
3. **Spring integration where needed**: `@EnableLoadTimeWeaving`/`<context:load-time-weaver/>` helps Spring set up a `LoadTimeWeaver` according to the classloader and environment; some environments use the `spring-instrument` agent. Adding only this annotation without the proper infrastructure, configuration, and classloader does not guarantee weaving occurs.

A **separate LTW sketch**, not a drop-in replacement for the proxy project in section 4:

`src/main/resources/META-INF/aop.xml`:

~~~xml
<!DOCTYPE aspectj PUBLIC "-//AspectJ//DTD//EN"
  "https://www.eclipse.org/aspectj/dtd/aspectj.dtd">
<aspectj>
  <aspects>
    <aspect name="demo.TraceAspect"/>
  </aspects>
  <weaver>
    <include within="demo..*"/>
  </weaver>
</aspectj>
~~~

In the AspectJ Java agent model, the application must be launched with a JVM argument similar to:

~~~text
-javaagent:/absolute/path/to/aspectjweaver.jar
~~~

`TraceAspect` must be an actual aspect class present on the classpath; this example only shows **where weaving configuration lives**, and does not claim to be an immediately runnable LTW project without defining the aspect, packaging, and launch command. Restrict `include` to the application's classes; weaving across the entire classpath increases risk and complicates diagnostics.

An important pitfall: a Spring Framework application **does not guarantee** every aspect is created/dependency-injected by Spring in the same way as proxy aspects. Instantiating, configuring, and injecting dependencies into AspectJ-woven aspects must be designed explicitly, especially when using aspects outside `ApplicationContext`. Do not infer that `@Component` + `@Aspect` + `@EnableAspectJAutoProxy` has activated the AspectJ weaver.

## 6. Which Mechanism to Choose for Each Requirement in Spring?

| Requirement | Preference and Rationale |
| --- | --- |
| Logging, timing, auditing, or checks on public methods of a Spring service when called by another bean | **Spring AOP @AspectJ**, minimal configuration, fits the service bean structure |
| Cross-cutting in Spring-managed controller/service/repository where pointcut is method execution | **Spring AOP** is usually sufficient; verify async scenarios, proxy chains, and advisor order |
| Need advice on `this.method()` calls or internal execution within the same object | Can **split beans to keep Spring AOP**; consider weaving only if every internal call path inside the class must be covered |
| Need to affect constructors, field access, method call sites, or objects created via `new` outside IoC | **AspectJ weaving** fits mechanically; Spring proxies cannot cover these |
| A `final` class or `final` method truly needs interception | **Weaving or redesign**; CGLIB subclass proxies cannot override `final` |
| Only `aspectjweaver` dependency and an `@Aspect` class exist | Not enough to prove weaving; read auto-proxy/`ajc`/agent/`aop.xml` settings before concluding |

An easy-to-misunderstand example: Spring's `@Transactional` in default proxy configuration also suffers from self-invocation; that same proxy nature can show up in logging, security, or caching through advisors. However, that illustrates a consequence of Spring proxies; do not equate all annotations with a single `@Aspect` class.

## 7. Common Misconceptions and How to Diagnose

**Misconception 1: "It has `@Aspect`, so it must be AspectJ weaving."** False. Check whether `@EnableAspectJAutoProxy`/auto-configuration is present, the aspect is registered as a bean, and Spring is issuing proxies. Conversely, to confirm AspectJ weaving, look for build `ajc` configuration, startup `-javaagent`, `META-INF/aop.xml`, or bytecode/class-load weaving evidence.

**Misconception 2: "Adding `aspectjweaver.jar` will make self-invocation get advised."** False. The dependency is typically needed for Spring `@AspectJ` expression parsing; to weave, you must **actively enable and configure** the compiler/weaver.

**Misconception 3: "Turning on CGLIB will catch private/final/self-calls."** False. A CGLIB proxy is a subclass; `private`/`final` methods cannot be overridden to advise, and `this` calls on the target do not go through the proxy. JDK proxies depend on exposed interfaces; understand the actual proxy type.

**Misconception 4: "Write any AspectJ pointcut and Spring AOP will understand it."** False. Spring AOP supports a limited set of designators and has its own `bean(...)` extension. For `call`, `get`, `set`, constructor join points, etc., evaluate weaving instead of trying to force Spring proxies.

**Misconception 5: "Creating an object with `new` inside a service still gets auto-proxied."** False in a normal bean context: self-created objects do not go through the container's bean registration and proxying mechanism. To advise with Spring AOP, manage the object with Spring and call through the bean proxy; if advising out-of-container objects is mandatory, consider weaving.

**Misconception 6: "Spring LTW only needs `@EnableLoadTimeWeaving` and it's done."** False. You must verify classloader/instrumentation, aspect declaration and weave scope, class loading order, and agents when needed. If classes load before the transformer takes effect, LTW configuration may not process classes as intended.

Diagnostic procedure when advice does not run:

1. Confirm the object is truly a Spring bean retrieved from `ApplicationContext` and the aspect is also registered; avoid accidentally instantiating the service with `new`.
2. Confirm auto-proxy is enabled and the pointcut matches the exact method execution/annotations/signature being called.
3. Determine the call direction: **is the caller going through the Spring proxy?** Check self-invocation, non-advisable methods, JDK interfaces, and CGLIB class proxies.
4. If requirements exceed proxy capabilities, inspect separate weaving configuration: build/agent/`META-INF/aop.xml`, classpath, classloader, and included packages.
5. For calls with multiple advisors, check ordering via `@Order`, exception handling, and transaction state; do not guess ordering from class names.

## 8. Self-Check Questions

1. A class has `@Aspect` and `@Before`, and `aspectjweaver` is on the classpath. Is that enough basis to say it uses weaving? **Not yet**: this may simply be a Spring AOP proxy configuration.
2. Why does a Spring bean calling `this.save()` skip advice on `save()` in proxy AOP? **Because the internal call does not pass through the proxy**.
3. Does switching from JDK dynamic proxy to CGLIB make `this.save()` go through the proxy? **No**.
4. To intercept field access on an object not created by Spring, is `@EnableAspectJAutoProxy` enough? **No**; AspectJ weaving and the corresponding join point kind scope must be evaluated.
5. When a Spring service calls another bean with a method matching `execution(...)`, does Spring AOP `@AspectJ` require the `ajc` compiler? **No**.

## Official Documentation for Cross-Reference

- Spring Framework, *@AspectJ support*: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework, *Enabling @AspectJ Support*: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework, *Proxying Mechanisms*: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework, *Declaring a Pointcut*: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/pointcuts.html
- Spring Framework, *Using AspectJ with Spring Applications*: https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html