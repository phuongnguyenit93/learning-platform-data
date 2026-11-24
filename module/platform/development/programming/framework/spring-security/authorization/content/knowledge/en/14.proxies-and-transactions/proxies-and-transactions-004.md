# JDK Proxies, CGLIB, and the Impact of Interfaces, `final`, and `private`

> **Topic:** Spring Security – authorization → **Proxies and Transactions**. When using `@PreAuthorize`, `@PostAuthorize`, or `@Transactional`, understanding the proxy type and call path is just as important as the annotation's expression. This article uses Java 17+, Spring Boot 3.x, and Spring Security 6.x as the foundation for runnable examples.

## 1. Prerequisite: How Spring Protects Calls Through a Proxy

With Method Security in default Spring AOP mode, Spring normally hands callers a **proxy** wrapping the business bean:

~~~text
Another Bean / Controller
         |
         | call method on object retrieved from Spring Context
         v
     [AOP proxy] -------> Security advice (e.g. @PreAuthorize)
         |                Transaction advice (if @Transactional)
         |                Other advice
         v
   [Target service]
         |
         v
     Return result
~~~

The proxy is an intermediary object that can run an authorization check before invoking the target; if `@PreAuthorize` evaluates to false, the method is not allowed to execute and Spring Security normally throws `AccessDeniedException`. The transaction interceptor also operates around calls through the proxy: opening/joining a transaction, committing, or rolling back according to rules.

Because the mechanism is **based on calls entering the proxy**, there is a major difference between:

~~~text
otherBean.securedService.approve()  -> proxy -> advice -> target.approve()

this.approve() inside target        -------------> target.approve()
                                                     (bypasses proxy)
~~~

If a running method calls another method on the same object via `this`, the inner method's own advice **does not run for that call**, even if that method is annotated. This holds true for both JDK proxies and CGLIB, affecting Method Security and `@Transactional` alike.

## 2. Two Proxy Forms: JDK Dynamic Proxies and CGLIB

### 2.1. JDK Dynamic Proxy

The JDK creates a proxy that **implements interfaces**, without extending the target class. Example:

~~~java
public interface ReportReader {
    String read();
}

public class ReportReaderImpl implements ReportReader {
    @Override
    public String read() {
        return "report";
    }
}
~~~

When a bean uses a JDK proxy, the caller receives an object implementing `ReportReader` and can call `read()` through the interface. However, the proxy **is not** a `ReportReaderImpl`; casting the proxy to the implementation fails. Public methods existing only on the implementation and absent from the proxied interface are not part of the API a caller can invoke through a JDK proxy.

~~~text
        ReportReader (interface)
           ^            ^
           | implements | implements
ReportReaderImpl     JDK proxy
   (target)           |
                      | advice then forward to target
                      v
               ReportReaderImpl
~~~

An important characteristic: a JDK proxy can intercept calls on **interface methods** even when the target class or implementing method is declared `final`; it does not need to subclass the target. This applies only to calls actually arriving through the proxy's interface.

### 2.2. CGLIB Proxy

CGLIB generates a **subclass** at runtime, overriding overridable methods of the target:

~~~text
ReportReaderImpl
       ^
       | extends
ReportReaderImpl$$SpringCGLIB$$...
       |
       +--- intercept -> target behavior
~~~

Because it relies on inheritance:

- A `final` class cannot be subclassed by CGLIB.
- A `final` method cannot be overridden, so advice cannot be attached to calls to that method.
- A `private` method cannot be overridden; nor can it be a proxy interception point.
- Methods lacking sufficient visibility for a subclass may also fail to be advised.
- Self-invocation (`this.method()`) still bypasses the proxy.

CGLIB is already bundled inside `spring-core`; you do not need to add a separate `cglib` library in standard Spring applications. Choosing a proxy strategy is about **interceptability and object types**, not a performance race between JDK and CGLIB.

### 2.3. Comparison Table

| Criterion | JDK dynamic proxy | CGLIB class proxy |
| --- | --- | --- |
| Generated proxy is | An object implementing interfaces | A subclass of the target |
| Typical selection condition | Bean has an interface, class proxy not forced | Bean has no interface or configuration forces class proxy |
| Injectable by interface | Yes | Yes, if target implements the interface |
| Injectable by target class | No | Yes, when subclassing succeeds |
| Public method not declared in interface | Not exposed via JDK proxy | Advisable when overridable |
| `final` target class | Still proxyable via interface | Cannot be subclassed |
| `final` target method | Can intercept calls on interface | Cannot override/advise |
| `private` method | Not part of proxy interface | Cannot override/advise |
| Internal `this.other()` | Skips `other`'s advice | Skips `other`'s advice |
| Used for Method Security | Yes | Yes |
| Used for `@Transactional` | Yes | Yes |

**Do not guess the proxy type solely from the class:** a bean implementing an interface can still receive a CGLIB proxy if Spring Boot / AOP configuration forces class-based proxies.

## 3. How Do Interfaces Affect Security?

A service with a public contract:

~~~java
public interface PaymentActions {
    void approve(long paymentId);
}
~~~

Implementation:

~~~java
@Service
public class PaymentActionsImpl implements PaymentActions {
    @Override
    @PreAuthorize("hasAuthority('PAYMENT_APPROVE')")
    public void approve(long paymentId) {
        // Business logic, after authorization is granted.
    }
}
~~~

These are two illustrative snippets that belong in separate files with appropriate imports; they are not a standalone application.

If callers inject `PaymentActions`, both JDK and CGLIB can satisfy that contract. If callers inject `PaymentActionsImpl`, a JDK proxy typically causes configuration or type-assignment failures because the proxy only implements the interface. Hence, **injecting by interface** is practical whenever a service has a clear business interface.

Spring Security Method Security can locate security annotations across methods, classes, and type hierarchies (including interfaces) when using Spring AOP. Still, place permission rules deliberately at service entry points, avoid conflicting annotations on the same signature across inherited interfaces, and write integration tests for both allowed and denied paths.

Specifically, `@Transactional` has a different rule in **AspectJ weaving mode**: Java does not inherit annotations on interfaces in the way AspectJ requires, so Spring Framework recommends placing `@Transactional` on the concrete implementation class/method. Do not assume annotations on interfaces behave identically across all AOP mechanisms.

### Are Methods Not in the Interface Protected?

With a JDK proxy, a method existing only on the implementation is not part of the method set callers can normally invoke through the interface proxy. A CGLIB proxy can expose that method as long as it is overridable and accessible. Therefore, if it is a sensitive action, design an intentional public contract and attach authorization; never rely on one proxy type accidentally hiding a method as a substitute for permission checks.

## 4. `final` Class, `final` Method, `private`, and `static`: Specific Consequences

### 4.1. A `final` Class with an Interface Still Has a JDK Proxy Path

~~~java
public interface InventoryLookup {
    String view();
}

public final class FinalInventoryLookup implements InventoryLookup {
    @Override
    public String view() {
        return "stock";
    }
}
~~~

Because a JDK proxy only implements `InventoryLookup`, `FinalInventoryLookup` can be `final` and still be proxied. If configuration forces CGLIB, Spring cannot subclass this class; you will typically hit a proxy creation error rather than getting a working subclass.

### 4.2. `final` Method: JDK Can Intercept, CGLIB Cannot

~~~java
public class InventoryLookupImpl implements InventoryLookup {
    @Override
    public final String view() {
        return "stock";
    }
}
~~~

A JDK proxy can intercept the `InventoryLookup.view()` call and forward to the final implementation. CGLIB cannot override `view()`, so placing `@PreAuthorize` or `@Transactional` on this method **does not guarantee advice when using a class proxy**.

Distinguish clearly:
- **`final` class** blocks CGLIB's ability to create a subclass.
- **`final` method** prevents CGLIB from intercepting that specific method, even when the class is not final.
- **JDK proxy** does not face this subclassing limit for interface calls, yet still requires the right annotation/advisor and callers actually using the proxy.

### 4.3. `private` Methods Are Not Security Boundaries

Dangerous example:

~~~java
// Illustrates a design flaw; do not place in a sample application.
@Service
public class DocumentService {
    public String getDocument() {
        return internalRead();
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    private String internalRead() {
        return "sensitive";
    }
}
~~~

`getDocument()` is an unguarded public entry point. The annotation on `internalRead()` cannot be advised by a proxy because a private method cannot be overridden and has no interface join point. Calling `getDocument()` can go straight into sensitive logic.

The proper design places the gate on the public method called by other beans through the proxy:

~~~java
@Service
public class DocumentService {
    @PreAuthorize("hasAuthority('DOC_READ')")
    public String getDocument() {
        return loadFromRepository();
    }

    private String loadFromRepository() {
        return "sensitive";
    }
}
~~~

Here the private helper is valid because callers have already passed through `getDocument()`'s gate. Private methods should remain implementation details—never use annotations on private helpers as standalone checkpoints.

### 4.4. `protected` and Package-Private: Be Careful per Advice Type

There is no single rule covering every AOP annotation. Since Spring Framework **6.0**, `@Transactional` is supported on `protected` or package-visible methods with **class-based proxies** in default configuration; JDK interface proxies require public transactional methods on the interface. However, that **does not automatically prove** every non-public `@PreAuthorize` method is handled the same way as transaction advice.

In services with authorization requirements, choose a non-final public method as the protection boundary, invoke it from another bean, and verify with tests. Never make a `protected`/package-private method the sole gate by extrapolating from another AOP feature.

### 4.5. `static` Methods and Constructors

`static` methods belong to the class, not instance method calls through a Spring bean proxy; constructors execute during object creation before the proxy can be used as a complete bean. Method Security or transaction annotations on `static` methods or constructors do not act as proxy permission gates in normal service calls. Likewise, with `@PostConstruct`, do not rely on internal calls to annotated methods because the proxy is not yet in the same state as for external callers.

### 4.6. Kotlin and Records

Kotlin declares classes and methods `final` by default; when using class-based proxies, you generally need `kotlin-spring`/`all-open` plugin configuration to open appropriate Spring bean types. Java `record`s are also `final` classes and cannot be subclassed by CGLIB in the usual way. Records fit DTOs/models, not Spring services needing class proxies.

## 5. Self-invocation: A Blind Spot Even with the Right Proxy Type

Consider this code:

~~~java
// Illustrates bug: external() is unprotected, protectedRead() is called via this.
@Service
public class UnsafeDocumentService {
    public String external() {
        return this.protectedRead();
    }

    @PreAuthorize("denyAll()")
    public String protectedRead() {
        return "secret";
    }
}
~~~

Calling `springBean.protectedRead()` externally goes through the proxy and is blocked by `denyAll()`. However, `springBean.external()` goes through the proxy to the target, and then `this.protectedRead()` runs directly inside the target without entering the proxy; `protectedRead()`'s own gate **is bypassed**. Switching JDK for CGLIB does not fix this issue.

### Fix by Splitting Beans and Entry Points

~~~java
// Illustrates a sound design direction; requires imports/package like other Spring examples.
@Service
public class ProtectedReader {
    @PreAuthorize("hasAuthority('DOC_READ')")
    public String read() {
        return "secret";
    }
}

@Service
public class DocumentFacade {
    private final ProtectedReader reader;

    public DocumentFacade(ProtectedReader reader) {
        this.reader = reader;
    }

    public String view() {
        return reader.read(); // call through another bean: proxied
    }
}
~~~

The principle is to move the action requiring its own gate into a public method on **another bean**; Spring injects that bean's proxy into the facade. Avoid self-injection or `AopContext.currentProxy()` as a default choice because they couple code to AOP, complicate bean lifecycles, and hinder maintainability.

### Self-invocation and `@Transactional`

~~~java
// Illustrative, assuming the application has a suitable PlatformTransactionManager.
@Service
public class OrderWorkflow {
    public void process() {
        this.saveInNewTransaction();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveInNewTransaction() {
        // Write data.
    }
}
~~~

When `process()` is called from outside, `saveInNewTransaction()` does not enter the transaction proxy, so **that method's `REQUIRES_NEW` rule is not triggered on the internal call**. If the outer caller already opened a transaction, the inner code can still execute inside that existing transaction; not every case means "no transaction." When a separate transaction is needed, move the operation to a bean with a non-final public method and invoke via proxy, or use `TransactionTemplate` for programmatic control.

## 6. Which Proxy Does Spring Boot Choose?

Plain Spring Framework AOP normally selects a JDK dynamic proxy when the bean implements an interface, and CGLIB otherwise. Spring Boot **AOP auto-configuration** typically enables class-based proxies by default. You can set the property:

~~~properties
# Prefer JDK dynamic proxy when an interface exists
spring.aop.proxy-target-class=false
~~~

~~~properties
# Class-based proxy / CGLIB
spring.aop.proxy-target-class=true
~~~

To enable Spring Security at the method level:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

`spring-boot-starter-security` does not automatically enable Method Security; `@EnableMethodSecurity` (or equivalent XML configuration) is required. Additionally, `@EnableMethodSecurity(proxyTargetClass = true)` can force class proxies. `@EnableAspectJAutoProxy`, `@EnableTransactionManagement`, or other auto-proxy creators can also influence this choice. Spring can merge multiple proxy settings, so a single property alone is insufficient to predict every case.

**Diagnosing on the actual bean:**

~~~java
// When service variable is already a Spring-managed bean:
AopUtils.isAopProxy(service);
AopUtils.isJdkDynamicProxy(service);
AopUtils.isCglibProxy(service);
~~~

Import: `org.springframework.aop.support.AopUtils`. These calls help observe the **proxy type**, yet do not guarantee sensitive methods are blocked; you must write tests where unauthorized callers are denied.

## 7. Runnable Example: Spring Boot, Method Security, and Both Proxy Types

The files below belong to a Gradle Spring Boot project configured with the `org.springframework.boot`/`java` plugins, Java 17+, and JUnit 5. All Java files live in package `demo.proxysec`. `spring-boot-starter-aop` is included to make class/interface proxy configuration explicit in the demo.

### 7.1. Build Dependencies

In the existing `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 7.2. Application Configuration

**`src/main/java/demo/proxysec/ProxySecurityApplication.java`**

~~~java
package demo.proxysec;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class ProxySecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProxySecurityApplication.class, args);
    }
}
~~~

**`src/main/java/demo/proxysec/ReportReader.java`**

~~~java
package demo.proxysec;

public interface ReportReader {
    String read();
}
~~~

**`src/main/java/demo/proxysec/ReportReaderService.java`**

~~~java
package demo.proxysec;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportReaderService implements ReportReader {
    @Override
    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String read() {
        return "report-42";
    }
}
~~~

The `read` method is public, non-final, and declared in the interface; that makes it a suitable entry point for testing both proxy types.

### 7.3. JDK Proxy Test

**`src/test/java/demo/proxysec/JdkMethodSecurityTest.java`**

~~~java
package demo.proxysec;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = ProxySecurityApplication.class,
    properties = "spring.aop.proxy-target-class=false")
class JdkMethodSecurityTest {
    @Autowired
    private ReportReader reader;

    @Test
    void isJdkProxy() {
        assertTrue(AopUtils.isJdkDynamicProxy(reader));
    }

    @Test
    @WithMockUser(authorities = "REPORT_READ")
    void allowed() {
        assertEquals("report-42", reader.read());
    }

    @Test
    @WithMockUser(authorities = "OTHER")
    void denied() {
        assertThrows(AccessDeniedException.class, reader::read);
    }
}
~~~

### 7.4. CGLIB Proxy Test

**`src/test/java/demo/proxysec/CglibMethodSecurityTest.java`**

~~~java
package demo.proxysec;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = ProxySecurityApplication.class,
    properties = "spring.aop.proxy-target-class=true")
class CglibMethodSecurityTest {
    @Autowired
    private ReportReaderService reader;

    @Test
    void isCglibProxy() {
        assertTrue(AopUtils.isCglibProxy(reader));
    }

    @Test
    @WithMockUser(authorities = "REPORT_READ")
    void allowed() {
        assertEquals("report-42", reader.read());
    }

    @Test
    @WithMockUser(authorities = "OTHER")
    void denied() {
        assertThrows(AccessDeniedException.class, reader::read);
    }
}
~~~

In the JDK test, the bean is injected by interface; the CGLIB test intentionally injects by concrete class. The two test classes run in Spring Contexts with different properties. If a real project has other configuration forcing a proxy type, the `isJdkProxy`/`isCglibProxy` assertions flag the discrepancy, enabling diagnosis rather than silently assuming the property took effect.

### 7.5. Mechanism Tests: `final`, `private`, and Self-invocation

To observe AOP mechanics independently of Spring Security, we use `ProxyFactory` and a `MethodInterceptor` counting how many times it **actually sees the call**. This is a proxy-level test: it does not grant or deny permissions itself, yet explains why security or transaction advice cannot run when the proxy fails to intercept a method.

**`src/test/java/demo/proxysec/ProxyMechanismTest.java`**

~~~java
package demo.proxysec;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.aopalliance.intercept.MethodInterceptor;
import org.junit.jupiter.api.Test;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.aop.support.AopUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProxyMechanismTest {
    public interface Reader {
        String read();
    }

    public static class FinalMethodReader implements Reader {
        @Override
        public final String read() {
            return "secret";
        }
    }

    public static class PrivateHelperReader {
        public String entry() {
            return loadPrivate();
        }

        private String loadPrivate() {
            return "private-result";
        }
    }

    public static class SelfCallingReader {
        public String entry() {
            return this.securedRead();
        }

        public String securedRead() {
            return "self-result";
        }
    }

    @Test
    void jdkInterceptsInterfaceCallEvenWhenTargetMethodIsFinal() {
        AtomicInteger hits = new AtomicInteger();
        ProxyFactory factory = new ProxyFactory(new FinalMethodReader());
        factory.setInterfaces(Reader.class);
        factory.setProxyTargetClass(false);
        factory.addAdvice((MethodInterceptor) invocation -> {
            if (invocation.getMethod().getName().equals("read")) {
                hits.incrementAndGet();
            }
            return invocation.proceed();
        });

        Reader proxy = (Reader) factory.getProxy();

        assertTrue(AopUtils.isJdkDynamicProxy(proxy));
        assertEquals("secret", proxy.read());
        assertEquals(1, hits.get());
    }

    @Test
    void cglibCannotAdviseFinalMethod() {
        AtomicInteger hits = new AtomicInteger();
        ProxyFactory factory = new ProxyFactory(new FinalMethodReader());
        factory.setProxyTargetClass(true);
        factory.addAdvice((MethodInterceptor) invocation -> {
            if (invocation.getMethod().getName().equals("read")) {
                hits.incrementAndGet();
            }
            return invocation.proceed();
        });

        FinalMethodReader proxy = (FinalMethodReader) factory.getProxy();

        assertTrue(AopUtils.isCglibProxy(proxy));
        assertEquals("secret", proxy.read());
        assertEquals(0, hits.get());
    }

    @Test
    void privateHelperCannotBeInterceptedSeparately() {
        List<String> seen = new ArrayList<>();
        ProxyFactory factory = new ProxyFactory(new PrivateHelperReader());
        factory.setProxyTargetClass(true);
        factory.addAdvice((MethodInterceptor) invocation -> {
            seen.add(invocation.getMethod().getName());
            return invocation.proceed();
        });

        PrivateHelperReader proxy = (PrivateHelperReader) factory.getProxy();

        assertEquals("private-result", proxy.entry());
        assertEquals(List.of("entry"), seen);
    }

    @Test
    void selfCallBypassesInnerMethodAdvice() {
        AtomicInteger innerHits = new AtomicInteger();
        ProxyFactory factory = new ProxyFactory(new SelfCallingReader());
        factory.setProxyTargetClass(true);
        factory.addAdvice((MethodInterceptor) invocation -> {
            if (invocation.getMethod().getName().equals("securedRead")) {
                innerHits.incrementAndGet();
            }
            return invocation.proceed();
        });

        SelfCallingReader proxy = (SelfCallingReader) factory.getProxy();

        assertEquals("self-result", proxy.entry());
        assertEquals(0, innerHits.get());
        assertEquals("self-result", proxy.securedRead());
        assertEquals(1, innerHits.get());
    }
}
~~~

Expected result: the JDK proxy calls `Reader.read()` on a target with a final method yet the interceptor counts 1; the CGLIB proxy calls the same final method and the interceptor counts 0; the private helper is not intercepted separately; self-invocation does not trigger inner method advice, whereas a direct call through the proxy does.

CGLIB may log a warning when encountering a final method. **A warning log is not an access control**; only testing actual behavior uncovers the vulnerability.

### 7.6. Running Tests

In the Gradle project directory:

~~~text
./gradlew test --tests 'demo.proxysec.*'
~~~

On Windows:

~~~text
gradlew.bat test --tests "demo.proxysec.*"
~~~

The example prints no `System.out.println`, so there is no special business stdout. Expected outcome: all assertions across all three test groups pass and the Gradle `test` task completes. If `isJdkProxy` fails, review the application context's global proxy configuration before concluding Method Security is misconfigured.

## 8. Combining Security Proxies and Transaction Proxies

When a method carries both `@PreAuthorize` and `@Transactional`:

~~~java
// Illustrative: assumes repository/transaction manager already exist.
@Service
public class ApprovalService {
    @PreAuthorize("hasAuthority('PAYMENT_APPROVE')")
    @Transactional
    public void approve(long paymentId) {
        // Read state and write update.
    }
}
~~~

Both advisors can participate in the call's processing chain, **only when the call actually passes through the proxy and the method is advisable**. Hence:

- A `final` method + CGLIB can lose both the permission check and the method's own transaction advice.
- A `private` method does not become transactional/secured merely because it carries annotations.
- `this.approve()` bypasses both pieces of advice attached to the internally called method.
- A public interface method via JDK proxy can be advised even if the implementing method is final, but avoid intentionally relying on `final` when proxy types may change.
- `@Transactional` on `protected`/package-visible methods in Spring Framework 6+ may work with class proxies, which does not mean it is a safe design for public Method Security boundaries.

### Advisor Order and Transaction Timing

In common configurations, the `@PreAuthorize` advisor has an order earlier than the default transaction advisor's `Ordered.LOWEST_PRECEDENCE`. This means the permission check can run **before the service's transaction opens**. If a policy traverses a JPA lazy relation assuming a transaction has already started, it may fail. However, Spring allows changing advisor order via configuration, so check your actual version and chain.

Even when a transaction is active, `@PreAuthorize` still checks only at **invocation time**. For sensitive updates, protect owner/tenant/state conditions in the appropriate query/transaction to close the gap between check and write. `@PostAuthorize` runs after the method body and is not the sole gate for actions with side effects.

## 9. Confusions That Easily Cause Security Bugs

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `@PreAuthorize` appears in code yet does not block | Method Security not enabled, call misses proxy, `final`/`private` | Enable `@EnableMethodSecurity`, test via Spring bean, move gate |
| Service has an interface, yet bean is CGLIB | Spring Boot AOP default or another config forces class proxy | Check with `AopUtils` and inspect global configuration |
| Injecting implementation works on one machine, fails on another | Config changed from CGLIB to JDK proxy | Inject by interface |
| CGLIB reports unable to proxy `final` class | Target class is `final` so cannot subclass | Make service non-final or use JDK via interface |
| Calls not blocked on `final` method | CGLIB cannot override | Place authorization on public non-final method |
| `private` `@Transactional` method fails to roll back as expected | Private methods are not proxy-advised | Move boundary to public method / another bean |
| `this.save()` does not trigger `REQUIRES_NEW` | Self-invocation bypass | Call via another bean or use `TransactionTemplate` |
| `@Transactional` on interface stops working after switching to AspectJ | Interface annotations are not inherited by Java for weaving | Place annotation on concrete class/method |
| `isAopProxy` test passes, yet data still leaks | Proxy exists, but advisor does not match the method | Test directly with an unauthorized caller |
| `@PostAuthorize` denies after data is already written | Post-check runs after method body | Check before updates and control transactions |
| Method only on implementation cannot be called | JDK proxy only exposes interface methods | Put callable action on appropriate interface |
| Final Kotlin service fails under CGLIB proxy | Kotlin classes/methods are final by default | Check `kotlin-spring`/`all-open` or use suitable interfaces |

Some methods in these examples exist to illustrate proxy mechanics, while production applications may add AOT, the module system, multiple advisors, reactive security, or AspectJ weaving. Do not assume AOP proxy behavior of a Spring Boot servlet service is identical across all those mechanisms.

## 10. How to Test Security at Proxy Boundaries

Tests calling `new SomeService()` are insufficient to verify annotations because that object has no Spring proxy. Testing proxy type with `AopUtils` is only a diagnostic step; you must test both **allowed permissions** and **denied permissions**.

Practical test suite:

1. Invoke the bean injected from the Spring Context along the path an external controller/service would call.
2. Use `@WithMockUser(authorities = "...")` for allowed tests and a different authority for denied tests.
3. Verify unauthorized callers receive `AccessDeniedException` before any data write occurs.
4. Separately test methods called from another bean, through an interface, and via self-invocation.
5. When changing `spring.aop.proxy-target-class`, re-run the same security tests; proxy-type tests do not replace authorization outcome tests.
6. For transactions, verify data after errors and propagation behavior; do not merely check that `@Transactional` appears in source code.

## 11. Practice Exercises

**Exercise 1 – Interfaces and `final`.** Use `ProxyMechanismTest` to explain why JDK can intercept an interface call to a `final` method while CGLIB cannot. Try making the whole class `final` and observe the difference between the two mechanisms.

**Exercise 2 – Method outside the interface.** Add a public method `exportAll()` to `ReportReaderService` without declaring it in `ReportReader`. Observe callability from beans using JDK proxies and CGLIB. If this is a sensitive action, fix the design with a public contract and explicit permission gate.

**Exercise 3 – Self-invocation.** In one service, have `handle()` call `this.restricted()` while `restricted()` has `@PreAuthorize("denyAll()")`. Write tests proving a direct call to `restricted()` through the proxy is denied, while the internal call bypasses the gate. Extract `restricted` to another bean and verify the facade path is also blocked.

**Exercise 4 – Transactions.** Test a public non-final method with `@Transactional(propagation = REQUIRES_NEW)`. Compare calling through another bean versus `this.method()`, then verify transaction behavior via data changes after commit/rollback.

**Exercise 5 – Upgrade checklist.** For your current Boot/Spring Framework/Security versions, record proxy type, protected method signatures, `final`/`private` modifiers, caller paths, and denial test results. Whenever dependencies or proxy properties change, re-run tests to ensure boundaries did not shift silently.

**Completion criteria:** distinguish interface proxies from class proxies, understand how a `final` class differs from a `final` method, recognize that `private`/`static` methods lack proxy join points, explain how self-invocation affects both `@PreAuthorize` and `@Transactional`, and prove behavior with integration tests.

## Main References

- Spring Framework – **Proxying Mechanisms** (JDK/CGLIB, `final`, `private`, self-invocation): https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework – **AOP Proxies**: https://docs.spring.io/spring-framework/reference/core/aop/introduction-proxies.html
- Spring Boot – **Aspect-Oriented Programming** (`spring.aop.proxy-target-class`): https://docs.spring.io/spring-boot/reference/features/aop.html
- Spring Security – **Method Security** (`@EnableMethodSecurity`, security interceptors): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Framework – **Using @Transactional** (visibility, interface annotations, self-invocation, and AspectJ): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
