# Bean Names, Aliases, and Naming Conventions in Spring Core Container

## 1. What Does a Bean Name Identify?

In the Spring Framework, a **bean** is an object managed by the IoC container based on an appropriate registration/configuration. Each bean registration has a **primary bean name**, and may also have **aliases** so that the same bean can be looked up by different names.

Distinguish the things commonly lumped together as "names":

| Component | Example | Meaning |
| --- | --- | --- |
| Java class | `TextFormatter`, `GreetingService` | Data type; multiple beans can share the same class |
| Primary bean name | `textFormatter` | Name used to register a bean definition |
| Bean alias | `mainFormatter`, `legacyFormatter` | Alternative name pointing to an already-registered bean; **not a new bean** |
| `@Bean` method name | `textFormatter()` | Usually generates the default name if no other name is specified |
| Name from component scan | `orderHandler` | Name generated for a scanned `@Component` class |
| Qualifier | `@Qualifier("mainFormatter")` | Metadata assisting **candidate selection** during dependency injection; not a bean creation directive |

**Important rule:** Names used as bean identifiers must be managed consistently within the container's scope. Two **different bean definitions** must not be assumed to coexist independently under one primary name. If the same name appears in configuration, the behavior may be a conflict, a rejection, or an override depending on environment/settings; **do not rely on "the configuration declared later will always win"**.

Aliases do not increase the number of bean definitions and do not cause a singleton to create additional instances. When a bean has `singleton` scope, `getBean("textFormatter")` and `getBean("mainFormatter")` return the same bean, meaning the same reference within a context.

**Lesson goal:** know how to assign explicit names, read default names, create aliases, use inspection/lookup APIs, avoid name collisions, and apply consistent naming conventions in a Spring Core Container project without Spring Boot.

## 2. Naming Convention: Names Reflect Role, Not Syntax

The Spring documentation recommends a convention like **Java instance variable names**: starting with a lowercase letter, using **lowerCamelCase**, and expressing the role.

| Bean name | Assessment | Reason |
| --- | --- | --- |
| `orderService` | Good | Short, conveys responsibility, and easy to search |
| `paymentClient` | Good | Immediately reveals the integration component |
| `primaryDataSource` | Good when disambiguating | Indicates which data source this is |
| `userRepository` | Good | Matches clear domain/business language |
| `bean1` / `obj` | Avoid | Conveys neither responsibility nor contract |
| `serviceImpl` | Usually avoid | Technical-descriptor name, gives little information about role |
| `UserService` | Can exist, but inconsistent | Capitalized initial letter deviates from the usual default convention |
| `my-awesome-service` | Can be valid in suitable contexts | Hyphens complicate reference syntax; not the default choice for Java config |

A bean name is **not a Java identifier**, so do not confuse Java variable syntax rules with what the container accepts as a name. However, using **ASCII lowerCamelCase**, stable, and meaningful names helps with `@Qualifier`, configuration, logs, bean name matching, and code review.

**Names should reflect role** rather than being forced to reflect implementation: `notificationSender` is usually easier to keep stable than `smtpNotificationSenderV2Impl` when the implementation changes. If you genuinely have multiple simultaneous implementations, use clearly distinguishable names (`emailNotificationSender`, `smsNotificationSender`) and a consistent candidate-selection mechanism.

Do not create aliases just to have multiple names "for convenience". Every alias is a public identifier that can become a dependency of other configurations, making future renaming harder.

## 3. Default `@Bean` Names, Explicit Names, and Aliases

In Java configuration, the standard default is to **use the `@Bean` method name**:

~~~java
// Illustrative syntax snippet, not a standalone file.
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    GreetingService greetingService(TextFormatter formatter) {
        return new GreetingService(formatter);
    }
}
~~~

Under the standard default naming mechanism, the bean above is named **`greetingService`**. Since Spring Framework 7.0, `ConfigurationBeanNameGenerator` can be customized; therefore, when a project intentionally changes its naming strategy, **do not treat the method-name rule as absolute** for every situation.

### Assigning an Explicit Primary Name

~~~java
@Bean("auditRecorder")
AuditRecorder audit() {
    return new AuditRecorder();
}
~~~

The bean is registered with the primary name **`auditRecorder`**, **not `audit`** merely because the Java method is named `audit()`. `@Bean("auditRecorder")` is equivalent to `@Bean(name = "auditRecorder")`.

### One Primary Name and Multiple Aliases

~~~java
@Bean(name = {"textFormatter", "mainFormatter", "legacyFormatter"})
TextFormatter textFormatter() {
    return new PlainTextFormatter();
}
~~~

The first name is the primary registration name; the remaining names are **aliases for the same bean**. In the default singleton scope, looking up by any of the three names returns the same managed object.

**Aliases differ from separate beans:** Three names in the array are **not** equivalent to three `@Bean` methods or three bean definitions. If you want three instances with different scopes/metadata, you must configure separate registrations, not merely add aliases.

In practice, assign an explicit name when external systems reference it, when multiple implementations share the same type, or when the bean name is part of a configuration contract. Otherwise, if all dependencies are resolved by type and there is no public naming requirement, a clear default name is usually sufficient.

## 4. Default Names When `@Component` Is Discovered by Scanning

Spring can automatically find and register classes annotated with stereotypes such as `@Component`, `@Service`, `@Repository`, and `@Controller` **when they fall within an active component scan scope**.

With the common default naming generator `AnnotationBeanNameGenerator`:

| Scanned class | Default bean name | Why |
| --- | --- | --- |
| `OrderHandler` | `orderHandler` | Lowercases the first letter of the class name |
| `PaymentClient` | `paymentClient` | Follows JavaBeans decapitalization |
| `URLParser` | `URLParser` | **First two characters are uppercase**, so Spring preserves capitalization per `Introspector.decapitalize` |
| `XMLGateway` | `XMLGateway` | Same acronym case |

This is the **default rule**, not a guarantee for projects that have replaced the bean name generator. When a class already has an explicit identifier such as:

~~~java
@Component("outboundGateway")
public class GatewayClient {
    // ...
}
~~~

the bean uses the specified name (provided the class is scanned/registered properly). Adding `@Component` **alone** to a class does not automatically add the bean to every context: you need `@ComponentScan`, `context.scan(...)`, or an equivalent configuration mechanism.

**Avoid acronym surprises:** If your team commonly names classes like `URLParser`, do not assume the bean name will be `uRLParser`. Specify `@Component("urlParser")` if you want a readable, stable name matching your team's naming convention.

In Spring Framework 7, certain naming strategies can be customized to use **fully qualified bean names**, especially when multiple components share the same simple class name. Do not arbitrarily switch an entire project to a different strategy if existing configurations reference beans by name.

## 5. Complete Java 17 Demo: Primary Names, Aliases, and Component Names

The demo uses **plain Spring Framework**, with no Spring Boot, HTTP, or database. It demonstrates together:
- `@Bean` with multiple names;
- `@Bean` with default name;
- `@Bean` with an explicit name different from the method name;
- default `@Component` names after scanning;
- lookup by name, lookup by type, and reference comparison;
- verifying that an alias **does not have its own bean definition**.

### 5.1. Preparing Maven

Requires **JDK 17+**, **Maven 3.9+**, and Maven Central/mirror access for initial dependency download. Uses Spring Framework **7.0.9** to pin the version for this practice exercise.

~~~text
bean-names-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                ├── BeanNamesDemo.java
                └── scanned/
                    ├── OrderHandler.java
                    └── URLParser.java
~~~

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-names-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>7.0.9</version>
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
                    <mainClass>demo.BeanNamesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven pulls the required dependencies of `spring-context`, including the bean factory core and annotation configuration support. Do not run bare `javac` without setting up the classpath for the Spring JARs; `mvn compile` invokes `javac` with the dependency classpath via Maven.

### 5.2. File `src/main/java/demo/BeanNamesDemo.java`

~~~java
package demo;

import java.util.Arrays;

import demo.scanned.OrderHandler;
import demo.scanned.URLParser;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;

public final class BeanNamesDemo {
    private BeanNamesDemo() {
    }

    interface TextFormatter {
        String format(String name);
    }

    static final class PlainTextFormatter implements TextFormatter {
        @Override
        public String format(String name) {
            return "Hello, " + name + "!";
        }
    }

    static final class GreetingService {
        private final TextFormatter formatter;

        GreetingService(TextFormatter formatter) {
            this.formatter = formatter;
        }

        String greet(String name) {
            return formatter.format(name);
        }
    }

    static final class AuditRecorder {
    }

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(basePackages = "demo.scanned")
    public static class AppConfig {

        @Bean(name = {
                "textFormatter", "mainFormatter", "legacyFormatter"
        })
        public TextFormatter textFormatter() {
            return new PlainTextFormatter();
        }

        @Bean
        public GreetingService greetingService(TextFormatter formatter) {
            return new GreetingService(formatter);
        }

        @Bean("auditRecorder")
        public AuditRecorder audit() {
            return new AuditRecorder();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            TextFormatter first =
                    context.getBean("textFormatter", TextFormatter.class);
            TextFormatter aliasA =
                    context.getBean("mainFormatter", TextFormatter.class);
            TextFormatter aliasB =
                    context.getBean("legacyFormatter", TextFormatter.class);

            String[] aliases = context.getAliases("textFormatter");
            Arrays.sort(aliases); // Stable output, independent of registration order.

            System.out.println("primary.exists="
                    + context.containsBeanDefinition("textFormatter"));
            System.out.println("alias.main.exists="
                    + context.containsBean("mainFormatter"));
            System.out.println("alias.legacy.exists="
                    + context.containsBean("legacyFormatter"));
            System.out.println("alias.hasDefinition="
                    + context.containsBeanDefinition("mainFormatter"));
            System.out.println("alias.list=" + String.join(",", aliases));
            System.out.println("aliases.sameInstance="
                    + (first == aliasA && first == aliasB));

            System.out.println("method.defaultName="
                    + context.containsBean("greetingService"));
            System.out.println("explicit.name="
                    + context.containsBean("auditRecorder"));
            System.out.println("old.method.name.isBean="
                    + context.containsBean("audit"));

            GreetingService greeting =
                    context.getBean(GreetingService.class);
            System.out.println("service.message=" + greeting.greet("Lan"));

            OrderHandler order = context.getBean(
                    "orderHandler", OrderHandler.class);
            URLParser url = context.getBean("URLParser", URLParser.class);

            System.out.println("component.camelCase="
                    + context.containsBean("orderHandler"));
            System.out.println("component.acronym="
                    + context.containsBean("URLParser"));
            System.out.println("component.classes="
                    + order.getClass().getSimpleName() + ","
                    + url.getClass().getSimpleName());
        }
    }
}
~~~

### 5.3. File `src/main/java/demo/scanned/OrderHandler.java`

~~~java
package demo.scanned;

import org.springframework.stereotype.Component;

@Component
public class OrderHandler {
}
~~~

### 5.4. File `src/main/java/demo/scanned/URLParser.java`

~~~java
package demo.scanned;

import org.springframework.stereotype.Component;

@Component
public class URLParser {
}
~~~

Both `@Component` classes reside in the package targeted by `@ComponentScan`. The name `URLParser` is preserved by the default JavaBeans decapitalization rule; `OrderHandler` becomes `orderHandler`.

**Why does the program have no colliding names?** The `textFormatter`, `greetingService`, and `auditRecorder` beans are declared via `@Bean` in `AppConfig`, while `OrderHandler` and `URLParser` are two components from the separate scanned package. Their names do not collide; internal Spring beans may also be registered, but they do not affect these specific checks.

## 6. Run Command and Expected Stdout

Open a terminal in the `bean-names-demo` directory (containing `pom.xml`):

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

The first three commands check environment versions and **do not have a single fixed output**. The last command compiles using Maven Compiler Plugin (release 17) and then runs `demo.BeanNamesDemo`.

**13 lines of stdout produced by `System.out.println` in the program**, excluding any lines emitted by Java/Maven/the logging backend:

~~~text
primary.exists=true
alias.main.exists=true
alias.legacy.exists=true
alias.hasDefinition=false
alias.list=legacyFormatter,mainFormatter
aliases.sameInstance=true
method.defaultName=true
explicit.name=true
old.method.name.isBean=false
service.message=Hello, Lan!
component.camelCase=true
component.acronym=true
component.classes=OrderHandler,URLParser
~~~

### Explaining the Key Lines

1. `primary.exists=true` shows that `textFormatter` is the name of a registered bean definition.
2. Both `alias.*.exists=true` lines show that alias lookup works in the context.
3. `alias.hasDefinition=false` proves that **an alias does not own a second bean definition**.
4. `alias.list=...` is the result of `getAliases("textFormatter")` **sorted** via `Arrays.sort` for deterministic output.
5. `aliases.sameInstance=true` proves that all three names return **the exact same object** in the default singleton scope.
6. `method.defaultName=true` illustrates that the `greetingService()` method creates a bean with the default name in this configuration.
7. `explicit.name=true`, `old.method.name.isBean=false` prove that `@Bean("auditRecorder")` overrides the default name `audit`; Spring does not automatically create an alias named `audit`.
8. `component.camelCase` and `component.acronym` demonstrate the two default component-scan bean naming cases.
9. `component.classes` confirms that lookup by name **and** expected Java type both return the right types.

**Note on creation timing:** `containsBeanDefinition` inspects metadata without necessarily invoking the bean's constructor. `getBean` returns the bean instance; in an `ApplicationContext`, non-lazy singletons are typically already instantiated during refresh. Aliases do not create extra instances even when looked up multiple times.

## 7. APIs to Use for Lookup and Diagnostics

| API / Expression | Question it answers | Pitfall to avoid |
| --- | --- | --- |
| `context.containsBean("name")` | Does the container recognize a bean by that name or alias? | Does not distinguish primary name from alias |
| `context.containsBeanDefinition("name")` | Is there a **local bean definition** registered under that exact name? | Usually `false` for aliases; not proof the bean is inaccessible |
| `context.getBean("name")` | Look up bean by name, returning `Object` | Must cast or use the typed overload |
| `context.getBean("name", Type.class)` | Look up by name and verify type | Type mismatch can throw an exception |
| `context.getBean(Type.class)` | Find bean by type | Can be ambiguous if multiple candidates exist |
| `context.getAliases("name")` | Retrieve alias names for a bean | Do not assume alias ordering is a business rule |
| `context.getBeanNamesForType(Type.class)` | List of bean names compatible with type | Do not use to count how many aliases exist |
| `context.getBeanDefinitionNames()` | Names of registered bean definitions | May include internal framework beans; do not hardcode count or order |

In the example, `containsBean("mainFormatter")` is `true` while `containsBeanDefinition("mainFormatter")` is `false`. **The two results do not contradict each other at all**: the first asks about lookup reachability via alias, while the second asks whether a definition exists under that name.

`getBean(Type.class)` and `@Qualifier` answer **which bean is needed** by type/metadata; an alias is simply an alternative name for referencing. Do not use aliases to replace clear dependency design when a system has multiple beans implementing the same interface.

### Look Up by Name or Inject via Constructor?

Prefer **constructor injection** in services, with explicit dependency types; use `@Qualifier` or `@Primary` when multiple candidates apply. Calling `context.getBean("name")` is useful for bootstrap code, admin tooling, or lessons on bean naming, but scattering it throughout business code easily turns into a hard-to-test **service locator**.

Aliases can be helpful when migrating from an old configuration name to a new name without duplicating beans, but an overly broad or undocumented alias easily causes confusion during debugging.

## 8. Aliases Outside `@Bean` Methods: XML and Registration

XML configuration can also define an alias **without** creating a second bean:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="http://www.springframework.org/schema/beans
                           https://www.springframework.org/schema/beans/spring-beans.xsd">
    <bean id="paymentClient" class="demo.PaymentClient"/>
    <alias name="paymentClient" alias="legacyPaymentClient"/>
</beans>
~~~

This is an **illustrative XML syntax snippet**, not a file used directly in the Section 5 project. It assumes class `demo.PaymentClient` has an appropriate constructor. Once the XML is loaded, `legacyPaymentClient` is an alias for the `paymentClient` bean, rather than creating a new bean definition.

In programmatic configuration, a supporting `BeanDefinitionRegistry` can provide `registerAlias("beanName", "aliasName")` and other registry operations. This is an advanced configuration API; only register/change aliases during the appropriate bootstrap phase, and **do not** treat a refreshed context's registry as an arbitrary renaming table while the application is serving requests.

**Distinguish an alias from a separate name for a different bean:** If you register two bean definitions `primaryPaymentClient` and `backupPaymentClient` (same Java type), they can have two distinct instances. Adding an alias `legacyPaymentClient` to `primaryPaymentClient` does **not** make the backup refer to the same object.

## 9. Name Collisions, Multiple Beans of the Same Type, and Dependency Selection

There are two distinct categories of issues:

### A. Multiple Definitions Wanting to Use the **Same Name**

For example, two `@Bean("paymentClient")` declarations in different configuration sources. In an application context/bean factory configured to forbid overriding, the container may refuse to start or throw a bean-definition-overriding error. In configurations allowing overrides, one registration may replace an earlier one — but relying on configuration load order is very error-prone.

**Better solution:** use distinct meaningful names, remove duplicate configuration sources, and check scanned packages and imported configurations. Never use aliases to mask two conflicting bean definitions.

### B. Multiple Definitions with **Different Names** Sharing the Same Interface/Type

For example, beans `stripePaymentClient` and `bankPaymentClient` both implementing `PaymentClient`. Both names are completely valid, yet injecting a single `PaymentClient` by type can be ambiguous.

You can specify selection using:
- `@Qualifier("stripePaymentClient")` at the injection point;
- `@Primary` on the appropriate default candidate;
- explicitly configured factory method parameters, or deliberate selection by name at the composition root;
- if both are needed, inject a matching collection/map of beans and handle it transparently.

**Note:** `@Qualifier` uses metadata to select a candidate; it does not create new beans or aliases. **`@Primary` also does not change the primary bean name**; it only affects selection priority under appropriate resolution rules.

Within an application, you can have **two distinct beans of the same Java class** with different names, scopes, or dependency sets. Thus the number of names, definitions, instances, and Java classes **are not always equal**.

## 10. When to Use Aliases and Stable Naming Conventions

### Reasonable Scenarios for Aliases

- **Bean name migration:** an older module expects `legacyFormatter` while a newer module expects `textFormatter`. An alias preserves compatibility during the transition period.
- **Subsystem-local naming:** a shared data source can be referenced under subsystem-specific names while still remaining a single actual bean.
- **External integration configuration:** a framework extension point requires a bean with a prescribed name; you can declare the name explicitly or alias an existing bean where appropriate.

### Situations Where You Should Not Add Aliases

- Merely to avoid explicitly choosing an implementation when multiple beans share a type.
- To create the illusion of multiple instances or distinct configurations.
- To hide default name collisions between two scanned classes/components.
- To "create a new experimental bean" while only adding an alias to a production bean.

### Recommended Team Conventions

1. Default to **lowerCamelCase**, named after the business role.
2. If external contracts/configurations reference a bean by name, **declare the name explicitly** to avoid surprises when refactoring class/method names.
3. When relying on default names, document the project's actual naming generator, especially for acronym classes like `URLParser`.
4. Only add aliases when there is a concrete compatibility or integration need; document which alias is legacy and the plan to retire it.
5. Do not mix naming conventions across Java classes, files, Maven artifacts, and bean registrations.
6. Avoid changing primary names/aliases arbitrarily after the application is configured or at runtime; consider the impact on injection and external references.
7. During code reviews, inspect `@ComponentScan`, `@Bean`, `@Qualifier`, and the list of bean names whenever conflicts arise.

## 11. Java 17 Exercises for Self-Verification

Make **each change independently** on a copy and restore the original source before comparing with the expected stdout in Section 6.

1. **Remove an alias:** delete `"legacyFormatter"` from the `@Bean(name=...)` array. Predict `containsBean("legacyFormatter")` and `getAliases("textFormatter")`.
2. **Change primary name:** change `"textFormatter"` to `"primaryFormatter"` while keeping `"mainFormatter"`; identify which lookup calls must be updated.
3. **Rename method while keeping bean name:** rename the Java method `textFormatter()` to `createFormatter()` while keeping `@Bean(name=...)`. Does the bean name change?
4. **Explicitly name a component:** change `@Component` on `URLParser` to `@Component("urlParser")`, update the lookup code, and explain the change from default acronym behavior.
5. **Change scanned package:** change `@ComponentScan(basePackages="demo.scanned")` to a package that does not contain the two components; predict whether `getBean("orderHandler", OrderHandler.class)` succeeds.
6. **Create a second bean of the same type:** add `@Bean("backupFormatter") TextFormatter ...` and call `getBean(TextFormatter.class)`. Observe the ambiguity when no selection policy exists; experiment with `@Primary` or `@Qualifier`.
7. **Inspect aliases/definitions:** print `getBeanDefinitionNames()` and `getAliases("textFormatter")`. Why must aliases not be treated as additional bean definitions?
8. **Compare identity:** use `==` between two `getBean` calls via aliases; explain the result if the bean is changed to prototype scope (where each lookup can create a new instance).
9. **Two contexts:** instantiate two contexts with the same `AppConfig`, and compare `getBean("textFormatter")` across the two contexts. Why does singleton not mean sharing an object across the entire JVM?
10. **Resolve a collision:** create another component class with the same simple name `OrderHandler` in another package, include both in the scan; observe the naming generator issue and choose appropriate explicit names.

### Lesson Completion Checklist

- [ ] Distinguish primary bean name, alias, Java class name, and method name.
- [ ] State the lowerCamelCase convention and the `URLParser` exception.
- [ ] Read `@Bean(name={"primary","aliasA","aliasB"})` accurately.
- [ ] Explain why an alias does not create an extra bean definition or singleton instance.
- [ ] Distinguish `containsBean` from `containsBeanDefinition`.
- [ ] Use `getAliases`, `getBean(name,Type.class)`, and type-based lookup.
- [ ] Handle multiple beans of the same type with `@Qualifier`/`@Primary`, without confusing them with duplicate names.
- [ ] Accurately predict the 13 lines of Java 17 stdout of the original program.

## 12. Summary and Official Documentation

**Remember:** A bean name is an identifier in the IoC container, whereas an alias is a **secondary name pointing to the same registration**. A single `@Bean` can expose multiple names **without** creating extra definitions; component scanning uses a default name generation rule that can differ for uppercase acronyms. Meaningful, consistent naming reduces wiring errors and collisions as a project grows.

Official documentation:
- [Spring – Bean Overview: Naming Beans and Aliasing](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
- [Spring – Using @Bean: Customizing Bean Naming and Aliasing](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring – Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
- [Spring – Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring – Fine-tuning Annotation-based Autowiring](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)

**Conclusion:** When inspecting a Spring configuration, ask **what the bean definition's primary name, aliases, type, and scope are** before inferring how many objects are created. Understanding these identification layers is the foundation for using `@Bean`, component scanning, `@Qualifier`, and debugging the Core Container accurately.