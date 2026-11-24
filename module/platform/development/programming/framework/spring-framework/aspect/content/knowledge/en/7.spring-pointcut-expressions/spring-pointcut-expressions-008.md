# `bean(...)` — Selecting a Pointcut by Spring Bean Name

## 1. When Do You Need `bean(...)` in Spring AOP?

Spring AOP commonly uses `execution(...)`, `within(...)`, `target(...)`, or `@annotation(...)` expressions to select *method executions* to advise. Yet there is a very Spring-specific need: **two Spring beans share the same implementation class and the same method signatures, but you only want to advise one bean with a specific name**.

Spring provides the **`bean`** pointcut designator (PCD) to solve this case:

```java
@Before("execution(* demo..*.process(..)) && bean(primaryJobService)")
public void audit() {
    System.out.println("AUDIT");
}
```

This is an **illustrative advice snippet**; the method must reside in an `@Aspect`-annotated class, that class must be registered as a Spring bean, and Spring AOP support must be enabled.

In the expression above:

- `execution(* demo..*.process(..))`: selects only **method executions** named `process` within the pattern scope.
- `bean(primaryJobService)`: selects only the **Spring bean named `primaryJobService`**.
- `&&`: both conditions must be satisfied for the advice to apply.

**Key point:** `bean(...)` filters by **bean name in the Spring container**, not directly by class name, interface name, method name, Java variable name, or any `@Qualifier` value.

This lesson discusses only **Spring AOP / Spring Framework**, without diving into general Aspect concepts. `bean(...)` is a **Spring-specific extension**, not part of the standard PCD list usable equivalently in native AspectJ weaving.

## 2. Syntax and Meaning

Spring AOP syntax:

```text
bean(idOrNameOfBean)
```

Where `idOrNameOfBean` is the Spring-managed bean name, which may include the `*` wildcard:

| Expression | Meaning |
| --- | --- |
| `bean(primaryJobService)` | Selects the bean named `primaryJobService` |
| `bean(*Service)` | Selects beans whose names end with `Service` |
| `bean(order*)` | Selects beans whose names start with `order` |
| `bean(*Audit*)` | Selects beans whose names contain `Audit` |
| `!bean(backupJobService)` | Excludes the bean named `backupJobService` |
| `bean(primaryJobService) || bean(backupJobService)` | Selects either of the two names |
| `bean(*Service) && !bean(backupJobService)` | Selects beans suffixed with `Service`, excluding the backup bean |
| `bean(*Service) && execution(public * *(..))` | Selects matching public methods on beans suffixed with `Service` |

Spring supports **simple wildcarding with `*`**, combined logically with `&&`, `||`, `!`. This is not a regular expression. Do not replace `*` with regex syntax like `.*`, and do not treat this pattern like a package path in `execution` or `within`.

The `bean` condition operates at the **bean-instance/named-bean level**. It can distinguish **two bean instances of the same class** if the two beans have different names. This is why Spring AOP supports `bean`: Spring's `BeanFactory` knows bean identity by name.

### What Happens with `bean(...)` Alone?

Spring AOP still runs advice only on **method executions that the proxy can intercept**. An expression like `bean(primaryJobService)` cannot make Spring advise constructors, field accesses, or calls on objects created with `new` outside the container. Nor does it guarantee every method on the bean is interceptable (for instance, CGLIB cannot override `final`/`private` methods).

In real code, combine it with `execution(...)` to state method boundaries clearly and keep the pointcut readable:

```java
@Pointcut("bean(*Service) && execution(public * demo..service..*.*(..))")
public void serviceMethodsOnNamedBeans() {
}
```

This is an **illustrative named pointcut**, not a standalone class. In a Java string literal, you can write the `&&` operator directly; in XML configuration, you must escape it as `&amp;&amp;` or use `and`/`or`/`not` word operators according to supported syntax.

## 3. Where Do Spring Bean Names Come From?

Spring determines bean names when registering bean definitions. Common ways include:

### 3.1. `@Bean` with an Explicit Name

```java
@Configuration
class JobConfig {
    @Bean("primaryJobService")
    JobService primary() {
        return new JobServiceImpl("PRIMARY");
    }

    @Bean("backupJobService")
    JobService backup() {
        return new JobServiceImpl("BACKUP");
    }
}
```

In this snippet, the **bean names are `primaryJobService` and `backupJobService`**. They are not `primary`/`backup` simply because those are the two Java method names.

Types `JobService` and `JobServiceImpl` will be fully defined in the program in section 5. This snippet only illustrates naming via `@Bean`.

### 3.2. `@Bean` Without an Explicit Name

```java
@Configuration
class JobConfig {
    @Bean
    JobService primaryJobService() {
        return new JobServiceImpl("PRIMARY");
    }
}
```

Under standard usage, the bean receives the default name **`primaryJobService`**, matching the `@Bean` method name.

### 3.3. Component Scanning

```java
@Service("inventoryService")
public class InventoryService {
    public void check() {
        System.out.println("CHECK");
    }
}
```

This is an illustrative class. When Spring component scanning discovers the class, the explicit name is `inventoryService`. When no explicit name is given, Spring normally generates one using bean naming rules (e.g., `InventoryService` becomes `inventoryService`); special capitalization cases, custom `BeanNameGenerator`s, or other configurations also exist. For name-based pointcuts, **verify the actual name** rather than guessing from the class.

### 3.4. Bean Aliases and Renaming

Spring can support **multiple names/aliases pointing to the same bean definition**. If an application has aliases or uses a custom registry, inspect which names and aliases the Spring AOP matcher actually recognizes, as well as the impact of renaming a bean. An alias is **not** a new target instance.

Do not rely on untested alias details as a business guarantee; choose a stable, explicit bean name and test the pointcut in a real context. Changing `@Bean("primaryJobService")` to another name **can cause advice to stop matching** even though the class and methods are unchanged.

## 4. Why Is `bean(...)` Different from `execution(...)`, `within(...)`, and `target(...)`?

Suppose two beans are distinct yet share the same target class:

```text
Spring ApplicationContext
   |
   +-- bean name = primaryJobService
   |      class = JobServiceImpl
   |      method = process(String)
   |
   +-- bean name = backupJobService
          class = JobServiceImpl
          method = process(String)
```

If you use:

```java
@Before("execution(* demo..*.process(..))")
```

both beans can be advised, because Spring selects by matching **method execution** and target type/signature.

If you use:

```java
@Before("execution(* demo..*.process(..)) && bean(primaryJobService)")
```

only the bean named `primaryJobService` is selected.

| Condition | Selects by | Can separate two beans of the same class with different names? |
| --- | --- | --- |
| `execution(* demo..*.process(..))` | Method signature / execution | No, if the corresponding methods are identical |
| `within(demo..*)` | Method-declaring type/scope | No, if both use the same implementation |
| `target(demo.JobServiceImpl)` | Type of the target object | No, if both are instances of the same class |
| `this(demo.JobService)` | Type of the Spring AOP proxy | No, if both proxies expose that same interface |
| `@annotation(demo.Audited)` | Annotation on method execution | No, if the same method carries the annotation |
| **`bean(primaryJobService)`** | **Name of the Spring bean** | **Yes** |

Do not write `bean(JobServiceImpl)` when the intent is "select every bean of class `JobServiceImpl`". That expression looks for a bean **named `JobServiceImpl`**, rather than checking the class automatically. If you want to select by type, use `target(...)`, `this(...)`, or `execution(...)` as appropriate.

### Spring-Specific Characteristic

Spring Framework documents `bean(...)` as a **Spring AOP extension**, because the framework is tightly integrated with `BeanFactory` and knows bean names. Native AspectJ weaving focuses on join-point/type-level semantics and **has no equivalent `bean` PCD**. Aspects declared with `@Aspect` **and processed by Spring AOP** can still use this extension; what is incompatible is moving the expression verbatim to an AspectJ compiler/weaver outside Spring AOP.

## 5. Runnable Demo: Two Beans Sharing One Implementation with Different Advice

The example uses **Java 17+, Maven, Spring Framework 6.2.19**. It creates **two independent Spring application contexts** to show two expressions:

1. **Exact:** `bean(primaryJobService)` applies only to one bean.
2. **Wildcard:** `bean(*JobService)` applies to both beans ending with `JobService`.

Both contexts register **the same two target classes/implementations**, swapping only the `@Aspect` bean. The code uses `@Bean` with explicit names so it does not depend on a bean-name generator. Target `JobServiceImpl` implements interface `JobService`, so the example runs with Spring Framework's default JDK dynamic proxy configuration.

### 5.1. Project Structure

```text
spring-aop-bean-pointcut/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanPointcutDemo.java
```

### 5.2. File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-bean-pointcut</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.19</version>
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
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.BeanPointcutDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. File `src/main/java/demo/BeanPointcutDemo.java`

```java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.context.annotation.Import;

public class BeanPointcutDemo {

    public interface JobService {
        String process(String id);
    }

    public static class JobServiceImpl implements JobService {
        private final String label;

        public JobServiceImpl(String label) {
            this.label = label;
        }

        @Override
        public String process(String id) {
            System.out.println("TARGET " + label + " " + id);
            return label + ":" + id;
        }
    }

    @Aspect
    public static class ExactAspect {
        @Before(
            "execution(* demo..*.process(..)) " +
            "&& bean(primaryJobService)"
        )
        public void trace(JoinPoint jp) {
            System.out.println("ADVICE exact " + jp.getSignature().getName());
        }
    }

    @Aspect
    public static class WildcardAspect {
        @Before(
            "execution(* demo..*.process(..)) " +
            "&& bean(*JobService)"
        )
        public void trace(JoinPoint jp) {
            System.out.println("ADVICE wildcard " + jp.getSignature().getName());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SharedBeans {
        @Bean("primaryJobService")
        public JobService primaryJobService() {
            return new JobServiceImpl("PRIMARY");
        }

        @Bean("backupJobService")
        public JobService backupJobService() {
            return new JobServiceImpl("BACKUP");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    @Import(SharedBeans.class)
    public static class ExactConfig {
        @Bean
        public ExactAspect exactAspect() {
            return new ExactAspect();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = false)
    @Import(SharedBeans.class)
    public static class WildcardConfig {
        @Bean
        public WildcardAspect wildcardAspect() {
            return new WildcardAspect();
        }
    }

    static void run(String title, Class<?> config) {
        try (var ctx = new AnnotationConfigApplicationContext(config)) {
            JobService primary =
                    ctx.getBean("primaryJobService", JobService.class);
            JobService backup =
                    ctx.getBean("backupJobService", JobService.class);

            System.out.println("=== " + title + " ===");
            System.out.println("PRIMARY_PROXY=" + AopUtils.isAopProxy(primary));
            System.out.println("BACKUP_PROXY=" + AopUtils.isAopProxy(backup));

            System.out.println("RESULT " + primary.process("A"));
            System.out.println("RESULT " + backup.process("B"));
        }
    }

    public static void main(String[] args) {
        run("EXACT", ExactConfig.class);
        run("WILDCARD", WildcardConfig.class);
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

**Lines printed by the program in expected order** (omitting any extra Maven/Spring logs):

```text
=== EXACT ===
PRIMARY_PROXY=true
BACKUP_PROXY=false
ADVICE exact process
TARGET PRIMARY A
RESULT PRIMARY:A
TARGET BACKUP B
RESULT BACKUP:B
=== WILDCARD ===
PRIMARY_PROXY=true
BACKUP_PROXY=true
ADVICE wildcard process
TARGET PRIMARY A
RESULT PRIMARY:A
ADVICE wildcard process
TARGET BACKUP B
RESULT BACKUP:B
```

Why do the results differ?

- Both beans in each context **use `JobServiceImpl`**, both expose `JobService.process(String)`, and both are Spring-managed.
- In `ExactConfig`, Spring creates an AOP proxy only for `primaryJobService` because only that bean name matches the pointcut. `backupJobService` receives no Spring AOP proxy from this advice.
- In `WildcardConfig`, both bean names end in `JobService`, so the advisor applies to both targets and both receive Spring AOP proxies.
- `@Before` advice runs before the target method when called through the proxy and matching the pointcut.
- Two independent contexts avoid multiple advices running on the same join point with undeclared relative ordering.

**Important boundary:** the output describes the demo with only one relevant advisor in each context. If an application has transaction/caching or other aspects, a bean not matching `bean(...)` can still receive a proxy from **another advisor**. Thus `AopUtils.isAopProxy(backup)==false` in the EXACT branch holds only in this specific setup, not as a universal rule.

## 6. Restricting Multiple Beans by Pattern and Negation

Once you understand the demo, you can write clear, intentional compound pointcuts.

### 6.1. Selecting a Group of Beans Named by Convention

```java
@Pointcut("bean(*Service)")
public void namedServices() {
}

@Pointcut("execution(public * demo..*.process(..))")
public void publicProcessingMethods() {
}

@Before("namedServices() && publicProcessingMethods()")
public void auditServices() {
    System.out.println("AUDIT");
}
```

These are sample methods **inside the same Spring `@Aspect` bean**; not a standalone program. The expression can reuse pointcut names rather than repeating long patterns.

### 6.2. Excluding a Specific Bean

```java
@Before(
    "bean(*JobService) && !bean(backupJobService) " +
    "&& execution(* demo..*.process(..))"
)
public void auditNonBackup() {
    System.out.println("AUDIT-NON-BACKUP");
}
```

On the two beans in the demo, only `primaryJobService` still matches. The condition `!bean(backupJobService)` is a **negation of name matching**, not a negation of the class or whether the bean is Spring-managed.

### 6.3. Selecting an Explicit Set of Names

```java
@Before(
    "(bean(primaryJobService) || bean(backupJobService)) " +
    "&& execution(* demo..*.process(..))"
)
public void auditSelected() {
    System.out.println("AUDIT-SELECTED");
}
```

The parentheses `(...)` group the condition before combining with `execution`; the intent is to select only the `process(..)` method of the two explicitly named beans.

### 6.4. Name Scope Is Not Class/Package Scope

```text
bean(*Service)                  -> checks Spring bean name
execution(* demo.service..*.*(..))
                                -> checks method execution by package/type
within(demo.service..*)         -> checks method-declaring type scope
target(demo.service.JobService) -> checks target object type
```

These lines **illustrate expression meanings**. A `@Bean("primaryJobService")` can return an instance of a class outside `demo.service`, and `bean(primaryJobService)` can still match by name. Conversely, a class inside `demo.service` is not selected by `bean(*Service)` if its Spring bean name does not match the pattern.

## 7. `bean(...)` Is Not Equivalent to `@Qualifier` or Variable Names

`@Qualifier` primarily assists Spring dependency injection: it narrows **dependency candidates by type**. Meanwhile, `bean(...)` in Spring AOP decides **which named beans an advisor applies to**.

Example:

```java
public JobRunner(
        @Qualifier("primaryJobService") JobService jobService) {
    this.jobService = jobService;
}
```

This is a **sample constructor** requiring fields, classes, and imports. `@Qualifier("primaryJobService")` can help pick the matching bean during injection, but it does not "create a new bean name" or suddenly make `bean(primaryJobService)` match. The bean name already exists in the registry.

If a custom qualifier `@Qualifier("critical")` is attached to a bean named `mainProcessor`, `bean(critical)` **does not automatically match** that custom qualifier name. To select by annotation/type, use the appropriate pointcut mechanism or name Spring beans following a consistent convention.

Similarly, a Java field name `private JobService jobService;` or local variable name does not determine the bean name. When checking at runtime, call `context.containsBean("primaryJobService")` or retrieve the bean by name from `ApplicationContext`.

## 8. Spring Boot and Related Proxy Creation Rules

In plain Spring Framework, `@EnableAspectJAutoProxy` activates auto-proxying for `@AspectJ` style when suitable dependencies are present. In Spring Boot with `spring-boot-starter-aop` and matching classpath conditions, AOP is usually auto-configured; you do not necessarily have to add that annotation manually.

A common configuration difference:

- Plain Spring Framework: targets with interfaces generally get JDK dynamic proxies when `proxyTargetClass=false`.
- Spring Boot AOP auto-configuration by default usually prefers **class-based proxies**; `spring.aop.proxy-target-class=false` can allow JDK proxies when interfaces exist.

**Regardless of JDK or CGLIB, `bean(...)` still checks the Spring bean name**, yet the method must still be interceptable by the proxy. Switching to a JDK proxy means implementation-only methods not exposed on the interface are not callable through the JDK proxy. Under CGLIB, `final`/`private` methods cannot be overridden to advise.

Do not assume setting `spring.aop.auto=false` disables every proxy source in an application; transaction infrastructure, custom advisors, or other configurations can still create proxies. When debugging `bean(...)`, separate **bean name matching** from **whether a proxy/advisor actually applied**.

## 9. Important Limitations of Spring AOP `bean(...)`

### 9.1. Only for Proxy-Based Spring AOP Pointcuts

`bean(...)` is an extension tied to Spring's `BeanFactory`, not a standard PCD shared with native AspectJ weaving. If code moves from Spring AOP to compile-time/load-time AspectJ weaving, pointcuts must be redesigned using types/annotations/logic available in that weaving environment.

### 9.2. Calls Must Go Through the Spring Proxy

If a service calls `this.process()` inside its own target, that call **does not go back through the proxy**. Even though `bean(primaryJobService)` matches the bean name, advice will not execute again on that internal call. Likewise, objects constructed via `new JobServiceImpl(...)` outside Spring are not selected by advisors merely because they share the class.

### 9.3. Not a Security Partition

`bean(...)` selects advisors by bean name, yet **it is not an authorization or sandboxing mechanism**. A renamed bean, an aliased bean, or logic called along a non-proxied path can alter advice expectations. For security requirements, enforce authorization checks at proper boundaries with tests; do not rely solely on bean names or whether a logging/audit advice ran.

### 9.4. Results Can Differ When Beans Come from Other Factories/Proxies

Constructs such as `FactoryBean`, scoped proxies, nested proxies, dynamic target sources, and special bean definitions make name lookup or runtime objects more complex. In such situations, inspect the actual bean name, proxy type, and attached advisors. Do not assume `bean(pattern)` always reflects aliases or factory products identically for every kind of factory/proxy.

### 9.5. Bean Names Are Not Necessarily Stable During Refactoring

Switching from `@Bean("primaryJobService")` to `@Component` with auto-generated names, renaming a `@Bean` method, or using a custom naming strategy can stop a pointcut from matching. Therefore, when `bean(...)` carries long-term business significance, prefer explicit names and add integration tests verifying the advice.

## 10. Workflow for Diagnosing a `bean(...)` Pointcut That Does Not Run

1. **Actual name:** verify in the running context whether `primaryJobService` exists; do not guess from class names, fields, or `@Qualifier`.
2. **Multiple instances of the same class:** check **which bean** the client is calling, not just `getClass()`.
3. **@AspectJ auto-proxy enabled:** does the aspect class have `@Aspect` and is it registered as a Spring bean?
4. **Case sensitivity and wildcards in the pointcut:** verify `bean(*Service)` matches the actual name suffix; distinguish `*` from regex.
5. **Combined conditions:** does `execution(...)` match the method being called? If `bean(...)` matches but `execution(...)` does not, the overall `&&` still fails to match.
6. **Does the bean have a Spring AOP proxy:** check with `AopUtils.isAopProxy(bean)`. No proxy usually indicates no advisor applied to the bean in that context.
7. **Other advisors:** a bean may receive a proxy from transaction/caching/other advice even if your `bean(...)` did not match. Proxy existence alone does not prove your specific advice ran.
8. **Method called through proxy:** avoid `new` objects or self-invocation `this.method()` on the target.
9. **Method interceptability:** JDK proxies expose only interface methods; CGLIB is limited by `final`/`private` and inheritance rules.
10. **Multiple contexts/proxy layers:** ensure you are inspecting the right Spring `ApplicationContext` and bean reference; test and production contexts may register different names.

You can print bean names by type in **your application** (this is a supplementary snippet, not a standalone program):

```java
String[] names = context.getBeanNamesForType(JobService.class);
for (String name : names) {
    Object bean = context.getBean(name);
    System.out.println(name + " -> aop=" + AopUtils.isAopProxy(bean));
}
```

When multiple beans share a type, this snippet is useful for checking actual names, yet an advisor applying to one bean does not cause other beans of the same class to be advised automatically.

## 11. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "`bean(JobServiceImpl)` matches every bean of class `JobServiceImpl`." | `bean(...)` matches by **Spring bean name**, not class name. |
| "Two beans of the same class always receive the same advice." | `bean(name)` can select just one bean instance by name. |
| "`bean(*Service)` is a regex." | It is a simple `*` wildcard in a bean-name pattern. |
| "Using `@Qualifier("critical")` makes `bean(critical)` match." | Qualifier metadata does not automatically become the bean name. |
| "Just having an `@Aspect` class with `bean(...)` makes it work." | The aspect must also be registered as a Spring bean, and AOP support must be enabled properly. |
| "`bean(...)` advises every method on the bean including private/constructors." | Spring AOP only intercepts method executions through proxies, subject to proxy strategy limits. |
| "`bean(...)` works identically in native AspectJ weaving." | It is a Spring-specific pointcut designator for Spring AOP. |
| "A bean not matching `bean(...)` definitely has no proxy." | Another advisor can still create an AOP proxy for that bean. |
| "Renaming a bean has no effect on pointcuts." | Name refactoring can cause the expression to stop matching. |

## 12. Self-Check Questions

**Question 1.** Two Spring beans `primaryJobService` and `backupJobService` share class `JobServiceImpl`. How many beans does `bean(primaryJobService)` select?  
**Answer:** Selects the bean with the exact name `primaryJobService` (one of the two, assuming no special aliases/registrations and a matching method).

**Question 2.** Which beans does `bean(*JobService)` select if both names end with `JobService`?  
**Answer:** Both beans, within the scope of proxied method executions and remaining pointcut conditions.

**Question 3.** Does `bean(JobServiceImpl)` automatically treat that as a Java class name?  
**Answer:** No. Spring evaluates the bean name `JobServiceImpl` against the pattern.

**Question 4.** A method is outside the package selected by `execution(...)`, yet the bean name matches `bean(primaryJobService)`. Does `execution(...) && bean(...)` match?  
**Answer:** No, because the AND operator requires both conditions.

**Question 5.** You put custom `@Qualifier("fast")` on bean `primaryJobService`. Is `bean(fast)` guaranteed to match?  
**Answer:** No. A custom qualifier does not automatically create a bean name `fast`.

**Question 6.** If Spring AOP proxy `primaryJobService` has advice on `process()`, does an internal call `this.process()` from the target run the advice again?  
**Answer:** No new call enters the proxy; self-invocation bypasses Spring AOP interception.

**Question 7.** If bean `backupJobService` does not match an exact pointcut yet has `@Transactional`, can it still be a proxy?  
**Answer:** Yes, because another mechanism/advisor can create the proxy.

**Question 8.** Can a `bean(*Service)` expression be moved verbatim to native AspectJ weaving?  
**Answer:** No. `bean` is an extension specifically for Spring AOP integrated with `BeanFactory`.

## 13. Official Spring Framework Documentation

- [Spring Framework 6.2 — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): `bean(name)`, `*` wildcard, `&&`/`||`/`!` operators, Spring-specific instance-level matching.
- [Spring Framework — Bean Overview](https://docs.spring.io/spring-framework/reference/6.2/core/beans/definition.html): bean name, id, alias, and naming conventions.
- [Spring Framework — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): naming beans via `@Bean`.
- [Spring Framework — Spring AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): proxy limits, method execution, and self-invocation.
- [Spring Framework — Autowiring with Qualifiers](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html): distinguishing semantic qualifiers from bean names.
