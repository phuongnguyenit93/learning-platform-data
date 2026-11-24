# Forcing Class Proxies with proxyTargetClass and Its Global Impact on Spring AOP Configuration

## 1. What Problem Does `proxyTargetClass` Solve?

Spring AOP intercepts method calls on **Spring beans through proxies**. For a bean requiring an advisor, Spring typically considers two proxy forms:

- **JDK dynamic proxy**: when the target implements suitable interfaces, the proxy implements those interfaces; callers work through interface types. Such a proxy is not an instance of the implementation class.
- **CGLIB class-based proxy**: Spring generates a subclass of the target class. The proxy is assignable to the target class type and can intercept eligible methods of the class, including `public` methods not declared on an interface.

Setting `proxyTargetClass = true` **requests Spring to use target-class proxies** instead of preferring interface proxies. In Java configuration supporting `@AspectJ`-style Spring AOP:

~~~java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class AopConfiguration {
}
~~~

This is an **illustrative configuration snippet**, used in an actual Spring configuration with `org.springframework.context.annotation.*` imports. It enables auto-proxying with class proxies for eligible beans in the context. `proxyTargetClass = false` allows Spring to choose interface proxies when appropriate; **it does not force JDK proxies** for a class that has no interfaces.

Crucial point: `proxyTargetClass` is a **setting for Spring's proxy creation mechanism**. It does not turn every bean into a proxy, create extra advisors, replace pointcuts, auto-register `@Aspect` classes as beans, or activate AspectJ weaving.

## 2. Default vs. Forcing CGLIB

Suppose `CheckoutService implements CheckoutPort` and has a `checkout(...)` method advised by Spring AOP:

| Case | Expected proxy type | Consequence for callers |
| --- | --- | --- |
| Plain Spring Framework; `@EnableAspectJAutoProxy` does not force class proxies; bean has interface | Usually JDK dynamic proxy | Use `CheckoutPort`; do not cast the proxy to `CheckoutService` |
| Bean needs AOP but has no business interface | CGLIB class proxy, even when `proxyTargetClass` is not enabled | Proxy is assignable to the implementation class if the class can be subclassed |
| `@EnableAspectJAutoProxy(proxyTargetClass = true)` | CGLIB class proxy for beans selected by the auto-proxy creator | Can inject/retrieve by implementation type if methods/class allow |
| A context contains both `proxyTargetClass = false` and `proxyTargetClass = true` across merged AOP configs | **The stronger setting (`true`) wins** | Another `false` annotation cannot force beans in the same creator back to JDK proxies |
| Bean has no applicable advisor/pointcut | Usually kept as the plain target, no AOP proxy | `AopUtils.isAopProxy(bean)` is `false`, even if forcing class proxies is enabled |

The table above applies to **Spring AOP in Spring Framework**, and does not treat `proxyTargetClass = false` as a mandate that “everywhere must use JDK.” Final outcomes also depend on context scope, auto-configuration, and how individual proxies are built.

In **Spring Boot**, AOP auto-configuration usually prefers **CGLIB by default**. The property:

~~~properties
spring.aop.proxy-target-class=false
~~~

allows selecting JDK proxies when interfaces are suitable in the corresponding Boot-managed configuration. When an application has explicit declarations requiring `proxyTargetClass = true` or other proxy infrastructure, inspect the actual configuration; do not guess from this property alone. Do not carry over assumptions about plain Spring Framework defaults to Spring Boot without accounting for auto-configuration.

## 3. Why Can One Declaration Affect the Entire Configuration?

This is the most easily overlooked part of this topic. Within an **ApplicationContext**, auto-proxy-based Spring AOP and transaction configurations are typically **merged into a shared auto-proxy creator infrastructure**, with the strongest proxy setting taking effect. According to Spring Framework 6.2 documentation, corresponding Java declarations such as `@EnableAspectJAutoProxy` and `@EnableTransactionManagement` both carry a `proxyTargetClass` attribute and participate in that merging mechanism.

Conceptual example:

~~~java
@Configuration
@EnableAspectJAutoProxy
class LoggingAopConfig {
    // Aspect beans are registered where appropriate.
}

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class ForceClassProxyConfig {
}
~~~

If both configurations above **are registered in the same context**, Spring does not treat them as two isolated zones each applying its flag only to “beans inside its own config.” The `true` flag causes the merged auto-proxy creator to prefer **class proxies for beans needing auto-proxying** within that scope. The second configuration does not need to redeclare any aspects itself to take effect.

Similarly, in Spring Framework 6.2:

~~~java
@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
class TransactionConfiguration {
}
~~~

If used in the same context/merged infrastructure as AOP, this transaction configuration can change **the proxy type of beans advised by Spring AOP**, even if the author intended to force class proxies solely for transactions. The transaction snippet above illustrates only the flag; a real transactional application still requires a transaction manager and supporting infrastructure.

With XML, the corresponding group of configurations has the same meaning:

~~~xml
<aop:aspectj-autoproxy proxy-target-class="true"/>
<aop:config proxy-target-class="true"/>
<tx:annotation-driven proxy-target-class="true"/>
~~~

These XML lines are **extracted declaration options**, not a complete standalone XML file. Spring documentation describes merging the strongest configuration across `<aop:config/>`, `<aop:aspectj-autoproxy/>`, and `<tx:annotation-driven/>`.

Understand the word **“global”** precisely:

1. **Within the same context and shared merged auto-proxy infrastructure**, choosing class proxies can have effects beyond the original declaration site.
2. **It does not mean every bean is proxied**: only beans with matching advisors that are eligible and container-managed can be auto-proxied.
3. **It does not mean across the whole JVM**: another `ApplicationContext` (especially parent/child contexts) can have separate BPP/auto-proxy registrations. Do not extrapolate from one context's configuration to another.
4. **It does not mean mutating already-created proxies at runtime**: it takes effect during configuration and bean/proxy creation. Changing annotations after beans are instantiated does not recreate singleton proxies.

In Spring Framework **7.0 and later**, documentation also describes broader unified defaults and per-bean overrides via `@Proxyable`. This lesson uses the **Spring Framework 6.2.x** model to clarify `proxyTargetClass` and AOP/transaction infrastructure impact; do not assume newer features exist in 6.2.

## 4. Processing Flow When Spring Decides the Proxy Type

With `@EnableAspectJAutoProxy`, Spring registers an auto-proxy creator, typically `AnnotationAwareAspectJAutoProxyCreator`. This is a `BeanPostProcessor`/infrastructure extending `AbstractAutoProxyCreator`. It discovers advisors from `@Aspect` Spring beans, finds matching beans, and returns an AOP proxy in place of the raw bean when needed.

~~~text
@Configuration / @EnableAspectJAutoProxy
          |
          v
Register / merge auto-proxy creator
          |
          +--> aggregate proxyTargetClass from related configs
          |
          v
Create each eligible Spring bean
          |
          v
Find advisors/pointcuts matching bean methods
          |
          +--> no match --------> return plain target
          |
          +--> match
                  |
                  v
          Check proxyTargetClass, interfaces, proxy settings
                  |
                  +--> JDK dynamic proxy (when suitable and class proxy not forced)
                  |
                  +--> CGLIB subclass proxy (when class proxy forced or needed)
                               |
                               v
                      Caller -> proxy -> advice -> target
~~~

**Changing the proxy type does not change the advice target**: pointcut expressions still determine which methods are advised; the proxy is simply how calls are routed. Advisors from logging, transactions, caching, or security can share the same chain; the proxy type affects which methods/object types can be exposed, not whether individual advisors are valid or invalid.

Two options should be kept distinct:

- `proxyTargetClass = true` — selects class-based proxies.
- `exposeProxy = true` — a different option on `@EnableAspectJAutoProxy`, allowing retrieval of the current proxy via `AopContext.currentProxy()` under suitable conditions. Do not enable it to solve JDK/CGLIB proxy selection; it addresses a different problem and tightly couples code to Spring.

Additionally, `@Configuration(proxyBeanMethods = false)` governs how `@Bean` factory methods on configuration classes are processed. This flag is **not equivalent** to `@EnableAspectJAutoProxy(proxyTargetClass = false)`.

## 5. Java 17+ Project Verifying the Impact Across Multiple Beans

We use two services that **both implement interfaces**, both having `@Before` advice. We run two independent `ApplicationContext` instances in **the same program**:

- The `BASE` context loads only normal AOP configuration: JDK proxies are used for both beans.
- The `FORCED` context loads **that same configuration plus** a `proxyTargetClass = true` configuration: both beans receive CGLIB proxies.

This control comparison proves the infrastructure impact across multiple beans. Two independent contexts keep the comparison clear, while within each context configurations are merged according to the registered annotations.

Structure:

~~~text
spring-proxy-target-class/
├── pom.xml
└── src/main/java/example/
    ├── App.java
    ├── CheckoutPort.java
    ├── CheckoutService.java
    ├── ReportPort.java
    ├── ReportService.java
    └── AuditAspect.java
~~~

Requires JDK 17 or newer, Maven 3.9+, and the ability to resolve Maven artifacts. The example pins **Spring Framework 6.2.0** and **AspectJ Weaver 1.9.22** for reproducibility, without claiming they are the latest releases.

### 5.1. Maven Build

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-proxy-target-class</artifactId>
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
                    <mainClass>example.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides `ApplicationContext`/configuration, `spring-aop` holds proxy utilities and AOP infrastructure, and `aspectjweaver` enables Spring to parse `@AspectJ` syntax. The AspectJ dependency does not turn on a compiler/weaver and does not require `-javaagent` for this AOP proxy example.

### 5.2. Two Interfaces and Two Implementations

`src/main/java/example/CheckoutPort.java`:

~~~java
package example;

public interface CheckoutPort {
    void checkout(String item);
}
~~~

`src/main/java/example/CheckoutService.java`:

~~~java
package example;

public class CheckoutService implements CheckoutPort {
    @Override
    public void checkout(String item) {
        System.out.println("CHECKOUT: " + item);
    }

    public void implementationOnly() {
        System.out.println("IMPLEMENTATION: checkout");
    }
}
~~~

`src/main/java/example/ReportPort.java`:

~~~java
package example;

public interface ReportPort {
    void generate();
}
~~~

`src/main/java/example/ReportService.java`:

~~~java
package example;

public class ReportService implements ReportPort {
    @Override
    public void generate() {
        System.out.println("REPORT: generated");
    }
}
~~~

Because both implementations have interfaces, Spring Framework auto-proxying in the `BASE` configuration can select JDK dynamic proxies. `CheckoutService.implementationOnly()` is not on `CheckoutPort`: the example could use it to demonstrate the difference between **the exposed interface type** and **a target-class proxy**. In the main executable code, we only invoke `checkout()` and `generate()` via interfaces in both cases to compare the exact same calls.

### 5.3. Aspect Using Spring AOP to Match Both Services

`src/main/java/example/AuditAspect.java`:

~~~java
package example;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;

@Aspect
public class AuditAspect {
    @Before("execution(* example.CheckoutService.checkout(..))"
          + " || execution(* example.ReportService.generate(..))")
    public void before(JoinPoint point) {
        System.out.println("ADVICE: " + point.getSignature().getName());
    }
}
~~~

Crucially, both beans have **applicable advisors**. Therefore, they are beans requiring proxies. `@Aspect` does not create a bean by itself; the `App` configuration below uses `@Bean` to register `AuditAspect` in the container.

### 5.4. Two Context Configurations and Verification Code

`src/main/java/example/App.java`:

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

public class App {
    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    public static class BaseConfig {
        @Bean
        public CheckoutService checkoutService() {
            return new CheckoutService();
        }

        @Bean
        public ReportService reportService() {
            return new ReportService();
        }

        @Bean
        public AuditAspect auditAspect() {
            return new AuditAspect();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    public static class ForceClassProxyConfig {
    }

    private static void inspect(
            String label,
            AnnotationConfigApplicationContext context,
            boolean forced) {
        Object checkout = context.getBean("checkoutService");
        Object report = context.getBean("reportService");

        boolean checkoutJdk = AopUtils.isJdkDynamicProxy(checkout);
        boolean reportJdk = AopUtils.isJdkDynamicProxy(report);
        boolean checkoutCglib = AopUtils.isCglibProxy(checkout);
        boolean reportCglib = AopUtils.isCglibProxy(report);
        boolean assignableToClass = checkout instanceof CheckoutService;

        System.out.println(label + "_CHECKOUT_JDK: " + checkoutJdk);
        System.out.println(label + "_REPORT_JDK: " + reportJdk);
        System.out.println(label + "_CHECKOUT_CGLIB: " + checkoutCglib);
        System.out.println(label + "_REPORT_CGLIB: " + reportCglib);
        System.out.println(label + "_IS_CHECKOUT_CLASS: " + assignableToClass);

        boolean correct = forced
                ? checkoutCglib && reportCglib
                        && !checkoutJdk && !reportJdk && assignableToClass
                : checkoutJdk && reportJdk
                        && !checkoutCglib && !reportCglib && !assignableToClass;

        if (!correct) {
            throw new IllegalStateException(
                    "Unexpected proxy type in context " + label);
        }

        ((CheckoutPort) checkout).checkout("book");
        ((ReportPort) report).generate();
    }

    public static void main(String[] args) {
        try (var base =
                new AnnotationConfigApplicationContext(BaseConfig.class)) {
            inspect("BASE", base, false);
        }

        try (var forced = new AnnotationConfigApplicationContext(
                BaseConfig.class, ForceClassProxyConfig.class)) {
            inspect("FORCED", forced, true);
        }

        System.out.println("CHECK: PASS");
    }
}
~~~

Analysis of the two context initializations:

1. `new AnnotationConfigApplicationContext(BaseConfig.class)` sees only `@EnableAspectJAutoProxy(proxyTargetClass = false)`. Since both services implement interfaces and have applicable advice, Spring Framework 6.2 chooses **JDK dynamic proxies** for them.
2. `new AnnotationConfigApplicationContext(BaseConfig.class, ForceClassProxyConfig.class)` loads both configurations into the same context. Although `BaseConfig` says `false`, `ForceClassProxyConfig` says `true`; the merged creator uses **class-based proxies** for **both services**, not just for beans declared in `ForceClassProxyConfig` (in fact, this config declares no service beans at all).
3. Both JDK proxies and CGLIB proxies implement `CheckoutPort` and `ReportPort` here, so calls through the interfaces share the same code without changing business logic.
4. `instanceof CheckoutService` is `false` for JDK proxies and `true` for CGLIB proxies; this illustrates the effect on injection points using the implementation class.
5. `AopUtils.isJdkDynamicProxy(...)` and `AopUtils.isCglibProxy(...)` check the actual mechanism, which is more reliable than guessing from annotations.
6. The program throws `IllegalStateException` if the proxy types are unexpected, printing `CHECK: PASS` only when both contexts meet expectations. The lesson's difference lies in **proxy class selection**; advice runs in both contexts.

### 5.5. Run Command and Stdout

Run in the project directory:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by `App`, `AuditAspect`, and the services in exact order:

~~~text
BASE_CHECKOUT_JDK: true
BASE_REPORT_JDK: true
BASE_CHECKOUT_CGLIB: false
BASE_REPORT_CGLIB: false
BASE_IS_CHECKOUT_CLASS: false
ADVICE: checkout
CHECKOUT: book
ADVICE: generate
REPORT: generated
FORCED_CHECKOUT_JDK: false
FORCED_REPORT_JDK: false
FORCED_CHECKOUT_CGLIB: true
FORCED_REPORT_CGLIB: true
FORCED_IS_CHECKOUT_CLASS: true
ADVICE: checkout
CHECKOUT: book
ADVICE: generate
REPORT: generated
CHECK: PASS
~~~

Maven or framework logging may emit additional external lines; the listing above includes **only the stdout explicitly printed by the example code**.

From the results, we can conclude:

- Same two services, same advice, same business calls, yet **different proxy types** when the configuration in the context changes.
- Merely adding `ForceClassProxyConfig` switches **both eligible beans** to CGLIB even though the forcing config declares no specific beans.
- `CHECK: PASS` is printed after verifying proxy types, not as a test that every Spring bean is proxied.
- This confirms the Spring AOP mechanism. **There is no AspectJ compile-time or load-time weaving** in this project.

## 6. Practical Consequences of Forcing Class Proxies

### 6.1. Injection Types and Casting

If the service implements `CheckoutPort`:

~~~java
@Autowired
private CheckoutPort checkout;
~~~

This injection style works with both JDK proxies and CGLIB proxies (when a single/qualifying bean is selected). If you write:

~~~java
@Autowired
private CheckoutService checkout;
~~~

When the actual bean is a JDK dynamic proxy, the proxy object **is not** an instance of `CheckoutService`; class-based injection can fail due to type incompatibility. A CGLIB proxy is a subclass of `CheckoutService`, so provided a class proxy can be created, this type can be injected. The two snippets above **illustrate field injection inside a Spring-managed class**, not standalone Java files; in real applications, constructor injection usually makes dependencies easier to manage.

**Do not force CGLIB across the entire infrastructure just to avoid interface design** if most dependencies use interfaces cleanly and stably. When there is a genuine need to call implementation-only methods, weigh the tradeoffs before selecting class proxies for the entire context.

### 6.2. Methods Not on the Interface

A JDK proxy does not expose `CheckoutService.implementationOnly()` because `CheckoutPort` does not declare it. With a class proxy, that method is accessible via `CheckoutService` (assuming no method/class restrictions).

However, **being able to call the method does not mean the method will be advised**. The pointcut in the example only matches `checkout(...)` and `generate(...)`. For `implementationOnly()` to run advice as well, you must expand the pointcut or create a matching advisor; `proxyTargetClass = true` does not add advice by itself.

### 6.3. Class Proxy Limitations

| Target characteristic | Things to keep in mind when using CGLIB |
| --- | --- |
| `final class` | Cannot create a subclass proxy for that class |
| `final method` | Cannot override/intercept that method through a CGLIB proxy |
| `private method` | Cannot be overridden; Spring AOP proxies do not advise it normally |
| Method invisible from subclass | May not be interceptable; e.g., a package-private method in a parent class from a different package |
| Object instantiated with `new` outside Spring | Does not automatically get proxied simply because `proxyTargetClass` is set |
| Self-invocation `this.otherMethod()` in target | Still bypasses calls through the proxy, even with CGLIB |
| JVM module path / module accessibility limits | Some classes do not allow subclass proxies unless the package is opened appropriately |
| Constructor of a class proxy | Spring typically uses Objenesis to avoid calling the target constructor twice; depending on JVM limits, exceptions/diagnostics may occur |

These limitations stem from the **subclassing** technique and how Spring AOP invokes the target. Using CGLIB does not provide the ability to intercept field accesses or constructors like AspectJ weaving. Do not flip the flag to `true` trying to fix self-invocation: the design-level fix is invoking through a bean proxy (usually extracting a service) or choosing another mechanism if requirements exceed Spring AOP's scope.

### 6.4. Impact on Transactions and Other Advisors

A Spring project may use `@Transactional`, caching, security, and `@Aspect` logging simultaneously. These mechanisms can all rely on Spring AOP proxies/advisors. In Spring Framework 6.2, Spring AOP and transaction configurations with the `proxyTargetClass` flag can merge into **global auto-proxy creator settings** within the same context.

That does **not** mean every annotation automatically joins the advice chain or every `@Async` mechanism follows identical rules in every version. Do not generalize conclusions beyond the framework/version in use; when upgrading to Spring 7.x, read the documentation on changes to merging proxy processors.

Before enabling forced class proxies for a transactional application, audit all targets needing proxies: `final` classes/methods, injection types, and behavior when multiple advisors apply together. A small configuration change can alter the runtime type of many beans.

## 7. Configuration Across Common Spring Styles

### Plain Spring Java Configuration

~~~java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfig {
}
~~~

You can use any Java configuration loaded by Spring. The aspect must be a bean, such as having both `@Aspect` and `@Component` under component scanning, or being created via `@Bean` as in the main example.

### Spring Boot Auto-Configuration

~~~properties
spring.aop.proxy-target-class=true
~~~

Spring Boot typically already configures AOP if the required dependency is on the classpath; in many Boot versions, CGLIB is also enabled by default. Setting the property to `false` requests interface proxies in Boot's corresponding setup, but you should not assume it overrides any separate AOP configuration that forces `true`. Check `AopUtils` and the effective configuration.

### XML AOP

~~~xml
<aop:aspectj-autoproxy proxy-target-class="true"/>
~~~

This is an element in the AOP namespace that must be declared inside a Spring XML configuration, not a standalone XML file. If the same context has `<tx:annotation-driven/>`, remember the strongest-setting merge rule rather than assuming each namespace affects only itself.

### Direct Runtime Inspection

Inside a Java method having a `context` variable of type Spring `ApplicationContext`:

~~~java
Object bean = context.getBean("checkoutService");

System.out.println(org.springframework.aop.support.AopUtils.isAopProxy(bean));
System.out.println(org.springframework.aop.support.AopUtils.isJdkDynamicProxy(bean));
System.out.println(org.springframework.aop.support.AopUtils.isCglibProxy(bean));
~~~

The snippet above **plugs into an existing application**, not a separately compiled program. If the object truly has an AOP proxy, the first call must be `true`; the latter two distinguish the type. Do not infer proxy type from whether a class has interfaces once application configuration becomes complex.

## 8. Common Misconceptions

**“`proxyTargetClass = true` only affects beans declared in the configuration containing the annotation.”** False with a shared auto-proxy mechanism in the same context: other beans eligible for advisors can also receive the strongest setting, like `ReportService` in the example.

**“`proxyTargetClass = false` forces every service to become a JDK proxy.”** False. If a class has no interface to proxy, Spring can still use CGLIB. If another related config in the context forces `true`, a `false` flag elsewhere does not erase the stronger setting.

**“Enabling `proxyTargetClass` causes all beans to be proxied.”** False. Spring AOP still requires matching advisors/pointcuts and eligible beans. Setting `true` only selects the type **when a proxy must be created**.

**“CGLIB can handle `final`, `private`, constructors, or `this.save()`.”** False. CGLIB is a subclass proxy so it cannot override `final`/`private` methods; internal calls on `this` do not pass through the Spring AOP proxy.

**“CGLIB is AspectJ weaving.”** False. CGLIB is a runtime subclass-proxy generation technique; AspectJ weaving is a bytecode transformation mechanism via a dedicated compiler/weaver. Sharing `@AspectJ` syntax does not equate the two mechanisms.

**“Changing the Boot property to `false` definitely disables all class proxies.”** False when the application still has Spring AOP/transaction configurations requiring class proxies or when a bean has no interfaces. Confirm by observing the actual proxy.

**“Since we use CGLIB, we don't need interfaces anymore.”** Removing interfaces from your design is not mandatory. Interfaces remain useful for APIs, testing, and defining contracts. Choosing JDK or CGLIB is a technical proxy decision and should be based on actual needs.

## 9. Diagnostic Workflow When Changing `proxyTargetClass`

1. **Confirm the right context and profile:** which configs are actually loaded, which Spring Framework/Spring Boot version is used, and are there parent/child contexts?
2. **List all sources forcing class proxies:** `@EnableAspectJAutoProxy`, `@EnableTransactionManagement`, XML AOP/transaction, Boot's `spring.aop.proxy-target-class`, and related proxy infrastructure.
3. **Identify beans needing proxies:** which aspects/advisors apply, and do pointcuts match methods on Spring beans? Without an advisor, changing the flag may show no visible change.
4. **Measure the proxy type at runtime:** `AopUtils.isAopProxy`, `isJdkDynamicProxy`, `isCglibProxy` on references obtained from the context.
5. **Check target compatibility:** `final`, `private`, visibility, interfaces, and module accessibility before forcing CGLIB.
6. **Cross-check injection types and casts:** a bean that used to be a JDK proxy and is now a subclass proxy can alter assumptions at injection points or in reflection code; focus on the contract that needs to be exposed.
7. **Verify actual advice behavior:** invoke the method through the proxy and observe logs/counters or integration tests; a proxy of the right type with a non-matching pointcut still will not run advice.
8. **After changing configuration, recreate the context to verify:** do not rely on singleton proxies already created under the old configuration.
9. **Evaluate impact on other beans:** especially when the application has AOP and transactions sharing infrastructure; also test beans not inside the edited configuration that have advisors.

## 10. Self-Check Questions

1. Given `CheckoutService implements CheckoutPort`, why does `proxyTargetClass = false` usually yield a JDK proxy while `true` yields CGLIB?  
   Because `false` allows the mechanism to select an interface proxy when suitable, whereas `true` requires a subclass proxy based on the target class.

2. Does enabling `proxyTargetClass = true` turn a bean matching no advisor into a proxy?  
   No. The flag controls the proxy **type**, not whether new advice requirements are created.

3. Given two configurations in the same `ApplicationContext`, one specifying `false` and the other `true`, what is the outcome?  
   With the merged auto-proxy creator, **the strongest setting (`true`)** is applied to beans needing proxies in the context.

4. Why can code injecting the implementation class break when switching from CGLIB back to JDK proxies?  
   A JDK proxy only implements interfaces, so it is not an instance of the implementation class.

5. Can self-invocation be fixed by setting `proxyTargetClass = true`?  
   No. `this.method()` on the target still does not go through the Spring proxy.

6. A Spring Boot app defaults to class proxies while a plain Spring Maven project uses JDK proxies; is there a contradiction?  
   No. Spring Boot has its own auto-configuration and defaults; check the effective settings of each application.

## Official Documentation

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB selection, class proxy limits, and the strongest-setting mechanism.
- [Spring Framework 6.2 — @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj.html): Spring's use of AspectJ syntax in proxy-based runtime AOP.
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): enabling the auto-proxy creator.
- [Spring Framework 6.2 — AOP Proxies](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-proxies.html): why JDK proxies and class proxies have different method surfaces.
- [Spring Boot — AOP auto-configuration](https://docs.spring.io/spring-boot/reference/features/aop.html): Boot defaults and the `spring.aop.proxy-target-class` property.
