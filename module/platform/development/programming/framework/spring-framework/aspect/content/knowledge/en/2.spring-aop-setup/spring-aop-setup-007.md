# Distinguishing Spring Framework Proxy Defaults from Spring Boot Configuration

## 1. Problem: for the same Spring bean, why are there two proxy types?

When using Spring AOP, a bean satisfying advice conditions can be replaced by an **AOP proxy**. What easily causes confusion is that the default configurations of **plain Spring Framework** and **Spring Boot auto-configuration** differ:

- In **Spring Framework**, the default proxy mechanism chooses a **JDK dynamic proxy** if the target implements an interface; if the target has no suitable interface, Spring uses a **class-based proxy (CGLIB)**.
- In **Spring Boot**, AOP auto-configuration sets `spring.aop.proxy-target-class=true` by default, meaning it prefers a **class-based proxy (CGLIB)**, even when the target has an interface.
- In a Boot application, setting `spring.aop.proxy-target-class=false` allows Spring to use a **JDK dynamic proxy when the target has an interface**; if the target has no interface, a class-based proxy is still required.

This is a difference in **Spring AOP configuration**, not two different AOP systems. Boot builds on Spring Framework and activates a different proxy choice in its auto-configuration.

**Lesson scope:** how AOP is enabled, the JDK/CGLIB selection mechanism, Boot/Framework configuration, runtime verification, and consequences for Spring beans. General aspect concepts are not expanded here.

## 2. Default comparison table

Assuming Spring AOP actually needs to create a proxy for the bean (an advisor applies; the bean is managed by Spring):

| Target bean | Plain Spring Framework, default configuration | Spring Boot with default AOP auto-configuration | Boot with `spring.aop.proxy-target-class=false` |
| --- | --- | --- | --- |
| `PaymentServiceImpl implements PaymentService` | JDK dynamic proxy | CGLIB class-based proxy | JDK dynamic proxy |
| `ReportService` without implementing an interface | CGLIB class-based proxy | CGLIB class-based proxy | CGLIB class-based proxy |
| `final class` needing class-based proxy | Cannot create normal subclass proxy | Cannot create normal subclass proxy | If no interface to proxy, still cannot create subclass proxy |
| Bean with no applicable advisor | Usually no AOP proxy | Usually no AOP proxy | Usually no AOP proxy |

**Important condition:** the table describes proxies created by the Spring AOP mechanism configured as described. An application can have other proxy types (such as scoped proxies, custom proxies, or other infrastructure), and a stronger configuration can alter the final choice. Do not infer proxy type solely from whether a project uses Spring Boot or not.

```text
                     Is a Spring AOP proxy needed?
                                  |
                          Matching advisor exists
                                  |
                             +----v----+
                             | Target  |
                             +----+----+
                                  |
                +-----------------+--------------------+
                |                                      |
       class-based requested?                         No
         (Boot usually true)                           |
                |                                      v
                v                          Does target have interface?
             CGLIB                              /          \
                                             Yes             No
                                              |               |
                                              v               v
                                      JDK dynamic proxy     CGLIB
```

The diagram describes the general rule when no special configuration or other overrides are present. `proxy-target-class=false` **does not** mean "forbid CGLIB"; it means "do not force every bean to use a target-class proxy".

## 3. Plain Spring Framework defaults

When configuring `@EnableAspectJAutoProxy` in a Spring Framework application using `AnnotationConfigApplicationContext`, the `proxyTargetClass` attribute defaults to `false`:

```java
@Configuration
@EnableAspectJAutoProxy // proxyTargetClass defaults to false
class AopConfig {
}
```

Explicit form showing intent:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
class AopConfig {
}
```

With this configuration:

1. Bean implements one or more interfaces: the proxy is normally a JDK dynamic proxy object, implementing only the exposed proxied interfaces.
2. Bean has no interface proxyable via JDK: Spring uses a class-based proxy so advice can be applied to matching methods.
3. If `@EnableAspectJAutoProxy(proxyTargetClass = true)` is explicitly set: Spring chooses a class-based proxy, even when the bean implements an interface.

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class ClassProxyConfig {
}
```

**Enabling auto-proxy does not mean every bean is proxied.** `@EnableAspectJAutoProxy` enables advisor/aspect processing; Spring still has to find advice matching the bean. A class with only `@Aspect` that is not registered as a Spring bean will not trigger advice automatically.

With XML, the corresponding attribute is `<aop:aspectj-autoproxy proxy-target-class="true"/>`. This also affects only the proxy creation mechanism; it does not extend Spring AOP to intercept constructors or field access.

### Why does Spring Framework prefer JDK when an interface exists?

A JDK proxy implements the interface used by callers; callers invoke through the interface and Spring inserts advice before forwarding to the target. This aligns with code that injects by abstraction:

```java
public interface PaymentService {
    String pay(String id);
}

// Use interface in client:
private final PaymentService paymentService;
```

A JDK proxy **is not an instance of the implementation class**. Therefore injecting or casting to `PaymentServiceImpl` can fail even when injecting `PaymentService` works completely fine.

## 4. Spring Boot defaults and auto-configuration conditions

Spring Boot has automatic AOP configuration. In Spring Boot 3.x and 4.x versions described in official documentation, common values are:

```properties
spring.aop.auto=true
spring.aop.proxy-target-class=true
```

The two properties answer **two different questions**:

- `spring.aop.auto`: whether Boot automatically enables `@AspectJ` auto-proxy support when classpath conditions match. Defaults to `true`.
- `spring.aop.proxy-target-class`: when Boot sets up AOP auto-proxying, whether to **prefer proxying via a subclass of the target class**. Defaults to `true`.

Usually you only need to add the `spring-boot-starter-aop` dependency to a Spring Boot project; the starter places Spring AOP support and the AspectJ libraries needed for `@AspectJ` pointcuts onto the classpath. Boot can enable auto-proxy automatically when AspectJ is present, so **there is no need to declare `@EnableAspectJAutoProxy` manually in standard cases**.

Maven example using Spring Boot 3.3.x:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

This is a **dependency snippet** for a project already managing versions via the Boot parent or BOM. Do not manually add a version to this dependency when Boot dependency management already manages it.

How to switch back to JDK proxy selection for targets with interfaces in `src/main/resources/application.properties`:

```properties
spring.aop.proxy-target-class=false
```

Or `application.yml`:

```yaml
spring:
  aop:
    proxy-target-class: false
```

With `false`, remember that targets without an interface must still use a class-based proxy if Spring AOP is to intercept their methods.

### Should `@EnableAspectJAutoProxy` be added to a Boot application?

Normally **no** if Boot's AOP auto-configuration is already active. You can declare it explicitly when the application needs custom control, but the outcome must be evaluated across the **entire auto-proxy configuration of the application context**.

A common mistake:

```java
// In a Boot app still using defaults
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = false)
class ExplicitAopConfig {
}
```

Many expect the snippet above to force every bean back to JDK. However, Spring has a mechanism to **merge / upgrade the auto-proxy creator**; a `proxyTargetClass=true` setting from elsewhere can override `false`. To choose JDK in standard Boot, configure `spring.aop.proxy-target-class=false` directly and avoid anything else forcing target-class proxies; verify the proxy type after context startup.

Conversely, setting `spring.aop.auto=false` only **disables Boot's automatic enabling of `@AspectJ` auto-proxy**. It is not a "ban all proxies" switch for the application: explicit `@EnableAspectJAutoProxy`, `@EnableTransactionManagement`, custom proxies, or other infrastructure mechanisms can still create proxies under their own conditions.

## 5. Runnable experiment: same bean in Spring Framework and Boot

The experiment uses **Java 17+, Maven, and Spring Boot 3.3.13** (including Spring Framework 6.x via Boot's dependency management). There is **one service implementing an interface** and **one aspect**. Two contexts are launched separately in the same program:

- `CORE`: `AnnotationConfigApplicationContext` + `@EnableAspectJAutoProxy(proxyTargetClass=false)`; Boot auto-configuration is not enabled.
- `BOOT`: `SpringApplicationBuilder` + Boot `@EnableAutoConfiguration`; receives `spring.aop.proxy-target-class` from properties/environment.
- The same service and aspect are declared in `SharedBeans`, so any difference comes from context configuration rather than differences in business code.

Structure:

```text
spring-proxy-defaults/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── aop/
                    └── ProxyDefaultsDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-proxy-defaults</artifactId>
    <version>1.0-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/example/aop/ProxyDefaultsDemo.java`:

```java
package example.aop;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.aop.support.AopUtils;
import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class ProxyDefaultsDemo {

    public interface PaymentService {
        String pay(String orderId);
    }

    public static class PaymentServiceImpl implements PaymentService {
        @Override
        public String pay(String orderId) {
            System.out.println("TARGET " + orderId);
            return "PAID:" + orderId;
        }
    }

    @Aspect
    public static class AuditAspect {
        @Before("execution(* example.aop..*.pay(..))")
        public void beforePay(JoinPoint joinPoint) {
            System.out.println("ADVICE " + joinPoint.getSignature().getName());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SharedBeans {
        @Bean
        PaymentService paymentService() {
            return new PaymentServiceImpl();
        }

        @Bean
        AuditAspect auditAspect() {
            return new AuditAspect();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    @Import(SharedBeans.class)
    public static class CoreConfig {
    }

    @SpringBootConfiguration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    @Import(SharedBeans.class)
    public static class BootConfig {
    }

    private static void inspect(String mode, Object bean) {
        System.out.println(mode
                + " aop=" + AopUtils.isAopProxy(bean)
                + ", jdk=" + AopUtils.isJdkDynamicProxy(bean)
                + ", cglib=" + AopUtils.isCglibProxy(bean));
    }

    public static void main(String[] args) {
        try (var core = new AnnotationConfigApplicationContext(CoreConfig.class)) {
            PaymentService bean = core.getBean(PaymentService.class);
            inspect("CORE", bean);
            System.out.println("CORE_RESULT " + bean.pay("A01"));
        }

        try (var boot = new SpringApplicationBuilder(BootConfig.class)
                .bannerMode(Banner.Mode.OFF)
                .web(WebApplicationType.NONE)
                .logStartupInfo(false)
                .run(args)) {
            PaymentService bean = boot.getBean(PaymentService.class);
            inspect("BOOT", bean);
            System.out.println("BOOT_RESULT " + bean.pay("B02"));
        }
    }
}
```

**Run 1 — Boot with defaults:**

```bash
mvn -q compile exec:java -Dexec.mainClass=example.aop.ProxyDefaultsDemo
```

Key lines observed from the program:

```text
CORE aop=true, jdk=true, cglib=false
ADVICE pay
TARGET A01
CORE_RESULT PAID:A01
BOOT aop=true, jdk=false, cglib=true
ADVICE pay
TARGET B02
BOOT_RESULT PAID:B02
```

**Run 2 — ask Boot to choose JDK proxy when an interface exists:**

```bash
mvn -q compile exec:java -Dexec.mainClass=example.aop.ProxyDefaultsDemo -Dexec.args=--spring.aop.proxy-target-class=false
```

Key observed lines:

```text
CORE aop=true, jdk=true, cglib=false
ADVICE pay
TARGET A01
CORE_RESULT PAID:A01
BOOT aop=true, jdk=true, cglib=false
ADVICE pay
TARGET B02
BOOT_RESULT PAID:B02
```

The blocks above list lines printed by the program itself; Boot or Maven may emit extra logging depending on the environment. `--spring.aop.proxy-target-class=false` is passed to `SpringApplicationBuilder.run(args)` of the Boot context; the `CORE` context does not use Boot's property configuration mechanism.

**Why does the experiment prove the difference?** Both contexts have the same target type `PaymentServiceImpl implements PaymentService`, the same `@Aspect`, and the same pointcut. Only the AOP registration mechanism differs: plain Spring Framework uses the interface proxy default, while Boot applies its default property value. `AopUtils` inspects the proxy type on the **bean obtained from the container**, not on a `PaymentServiceImpl` created via `new`.

## 6. When changing proxy type, what actually changes?

### 6.1. Injection and casting capability

With a **JDK dynamic proxy**:

```java
PaymentService service = context.getBean(PaymentService.class);
// OK: proxy implements PaymentService interface.

// Do not assume the following code is valid:
PaymentServiceImpl impl = (PaymentServiceImpl) service;
```

Casting to the implementation on the second line normally throws `ClassCastException` if `service` is a JDK proxy. With a **CGLIB class-based proxy**, the proxy is a subclass of the implementation (if the class is subclassable), so referencing the implementation type can work.

Therefore, when changing `spring.aop.proxy-target-class=true` to `false` in Boot, check every place that injects the implementation directly or calls `getBean(Implementation.class)`. AOP configuration can affect bean resolution by the types the application uses.

### 6.2. Methods that can be advised

- JDK proxies **expose the interface**; callers normally invoke through the proxied interface.
- CGLIB proxies are subclass-based and can handle calls to methods on the target class within proxying limits, including public methods not declared on a business interface.
- A `final class` cannot be CGLIB-subclassed; a `final method` cannot be advised via overriding; `private method`s and methods invisible to a subclass cannot be advised that way either.
- **Switching to CGLIB does not solve self-invocation**: `this.someMethod()` inside the target still does not pass back through the Spring proxy.

For package-private/protected methods, visibility conditions, proxy type, and Spring version can determine the outcome; do not interpret "CGLIB intercepts every method" as an absolute promise.

### 6.3. Performance and compatibility

Do not choose JDK or CGLIB merely by assuming one is faster. Advice overhead, reflection/dispatch, JVM optimizations, and actual workload can all dwarf proxy differences. Use the appropriate default, prefer stable APIs, and benchmark on your specific application when there is a real performance requirement.

Class-based proxies can also be affected by module-path and Java module access because they require subclass generation. Types residing in modules/packages not opened for access require checking the corresponding JVM restrictions. Resulting failures typically relate to subclassing/access permissions, not pointcut expressions.

## 7. Overlapping auto-configuration: why setting `false` sometimes still yields CGLIB

In a Spring application, multiple auto-proxy configuration sources can coexist, such as `@EnableAspectJAutoProxy`, transaction infrastructure, XML elements, and other settings. Spring normally unifies them into one auto-proxy creator, where stronger settings such as `proxyTargetClass=true` can dominate globally. Thus:

```java
// Example of one place forcing class-based proxy:
@EnableAspectJAutoProxy(proxyTargetClass = true)
class ForceClassProxy {
}
```

If this configuration bean is loaded, having a Boot app set `spring.aop.proxy-target-class=false` does not guarantee all proxies immediately become JDK proxies. You must locate every place forcing target-class proxies in the **specific application context**, not just read one property line.

Version note: Spring Framework **7.0 and later** also introduces `@Proxyable` to select proxy type per bean in supported cases; this rule is a newer capability and **does not apply by default to Spring Framework 6.x / Spring Boot 3.x** used in the examples. If using that version, consult the exact release documentation to determine configuration precedence.

### Where are properties loaded from?

In Boot, properties can be declared via `application.properties`, `application.yml`, profile-specific configurations, environment variables, command-line arguments, and other `Environment` sources. The effective value after precedence rules may differ from the file you are currently viewing.

Example of a standard environment variable matching the property name:

```bash
SPRING_AOP_PROXY_TARGET_CLASS=false
```

In the command-line example in section 5, `--spring.aop.proxy-target-class=false` affects only the Boot context receiving `args`. When diagnosing a deployed application, check `Environment.getProperty("spring.aop.proxy-target-class")` alongside inspecting bean proxies; do not rely solely on config files.

### Checking AOP support status

- `spring.aop.auto=true` and AspectJ on the classpath: Boot can automatically enable `@AspectJ` processing.
- `spring.aop.auto=false`: stops Boot from automatically adding `@AspectJ` processing; explicit AOP configuration sources/other infrastructure can still create proxies.
- Lacking `spring-boot-starter-aop` is not enough to conclude AOP is impossible; related libraries may arrive on the classpath via another dependency. Check the dependency tree and effective configuration.
- A bean without an AOP proxy can still perform its business logic normally, simply without passing through the corresponding AOP advice chain.

## 8. Investigation workflow in a real application

When a Boot project defaults to CGLIB yet you expected JDK, or vice versa:

1. **Identify the environment:** plain Spring Framework or Spring Boot? Exact version? In which context is `@EnableAutoConfiguration` actually running?
2. **Check the classpath:** are the AOP/AspectJ starter and matching advisors or aspect beans present?
3. **Check effective configuration:** `spring.aop.auto`, `spring.aop.proxy-target-class`, and any `@EnableAspectJAutoProxy(proxyTargetClass=...)` / `@EnableTransactionManagement` declarations.
4. **Check which interfaces the target has:** if none, `false` can still produce CGLIB.
5. **Obtain the real bean from the context:** use `AopUtils.isAopProxy(bean)`, `AopUtils.isJdkDynamicProxy(bean)`, and `AopUtils.isCglibProxy(bean)`.
6. **Check injection style:** does the application request the bean by interface or implementation? After changing proxy type, are casts and injections still compatible?
7. **Check the call path:** self-invocation or `new`-instantiated objects do not go through the proxy, whether JDK or CGLIB.
8. **Verify with a real test context:** test both `true`/`false` properties and assert both proxy type and advice behavior. Do not test by calling raw objects outside Spring.

Example assertion in an integration test, for a bean already confirmed to have Spring AOP applied:

```java
Object bean = applicationContext.getBean(PaymentService.class);
assertTrue(AopUtils.isAopProxy(bean));
assertTrue(AopUtils.isJdkDynamicProxy(bean)); // When expecting JDK
assertFalse(AopUtils.isCglibProxy(bean));
```

This is an **illustrative test snippet**, requiring context/test imports and an assertion library, not a standalone program. Switch the expectation to `isCglibProxy` when testing the default Boot configuration.

## 9. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "Spring Boot must also use JDK proxies if a class implements an interface because Spring Framework defaults to that." | Boot can change the default choice via AOP auto-configuration; its common default is CGLIB. |
| "Setting `spring.aop.proxy-target-class=false` makes all AOP use JDK." | It only selects JDK when an interface exists and no other configuration forces class-based proxies. |
| "`@EnableAspectJAutoProxy(proxyTargetClass=false)` definitely overrides Boot's true default." | Multiple auto-proxy settings can merge; `true` from elsewhere can dominate. |
| "Spring Boot requires declaring `@EnableAspectJAutoProxy`." | With the proper starter/classpath, Boot already enables `@AspectJ` auto-proxying automatically. |
| "Switching to CGLIB makes calling `this.foo()` get advised." | Self-invocation still bypasses the proxied call. |
| "`spring.aop.auto=false` disables every proxy creation mechanism in the application." | It only governs Boot's AOP auto-configuration; other configurations and infrastructure can still create proxies. |
| "A bean implementing an interface is guaranteed to be a JDK proxy." | It also depends on `proxyTargetClass`, the auto-proxy creator, and the framework version. |
| "Having `@Aspect` means every bean definitely gets a proxy." | The aspect must be registered and the pointcut/advisor must apply to the bean. |

## 10. Self-check questions

**Question 1.** `UserServiceImpl implements UserService`, plain Spring Framework app with default `@EnableAspectJAutoProxy` and a matching pointcut. Expected proxy type?  
**Answer:** JDK dynamic proxy.

**Question 2.** The same bean in a Boot app with `spring-boot-starter-aop`, AOP auto-configuration, and no configuration overrides. Expected proxy type?  
**Answer:** CGLIB class-based proxy by Boot's default.

**Question 3.** `spring.aop.proxy-target-class=false` is set in Boot; bean `ReportService` does not implement any interface. Result?  
**Answer:** Spring still needs a class-based proxy if an advisor applies; `false` does not "force JDK" when there is no interface.

**Question 4.** Boot has `spring.aop.proxy-target-class=false`, yet the bean is still CGLIB. What should be checked?  
**Answer:** Does the target have an interface; is the property in effect; is another config forcing `proxyTargetClass=true`; is the bean an AOP proxy in the right context; is it a different kind of proxy?

**Question 5.** Switching from Boot CGLIB to JDK, a controller directly injecting `UserServiceImpl` fails while injecting `UserService` works. Why?  
**Answer:** A JDK proxy only implements the interface, not a subtype of the implementation class.

**Question 6.** Does `spring.aop.auto=false` guarantee there are no proxies for transactions or other AOP configurations?  
**Answer:** No. It is a flag for Boot's automatic `@AspectJ` AOP configuration; other configurations and infrastructure can still create proxies.

## 11. Official documentation

- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB rules, `final` limitations, and auto-proxy configuration behavior.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html): `@EnableAspectJAutoProxy` and aspect bean registration.
- [Spring Boot — Aspect-Oriented Programming](https://docs.spring.io/spring-boot/reference/features/aop.html): Boot's CGLIB default and switching to JDK via `spring.aop.proxy-target-class=false`.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html): default values for `spring.aop.auto` and `spring.aop.proxy-target-class`.
