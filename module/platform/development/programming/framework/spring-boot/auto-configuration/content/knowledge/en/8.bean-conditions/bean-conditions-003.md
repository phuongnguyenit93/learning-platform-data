# Looking Up Beans by Type, Name, and Annotation in Spring Boot Auto Configuration

## 1. Purpose and Context

In Spring Boot, a *bean condition* decides whether to register a configuration or a bean based on **the beans already known to the `BeanFactory` at condition evaluation time**. For this lesson, the three lookup approaches to distinguish are:

1. **By type:** is there a bean with the desired type or compatible with that type?
2. **By name:** is there a bean registered with a specific name?
3. **By annotation on the bean:** is there a bean whose class carries the desired annotation?

These three approaches serve different intents. For example, a library creates `AuditDecorator` only when the application has an `AuditService` bean (by type), creates an integration component only when the `"primaryDataSource"` bean exists (by name), or enables specialized support when there is a bean whose class is annotated with `@AuditedComponent` (by annotation).

**Distinction:** "is the `AuditService` class on the classpath?" is the question for `@ConditionalOnClass`; "is there already an `AuditService` bean in the context?" is the question for `@ConditionalOnBean`. Having a class present in dependencies **does not mean** a bean has already been registered.

## 2. The Two Core Annotations and Choosing Criteria

- `@ConditionalOnBean`: matches when **all declared requirements are satisfied** by the inspected beans. Requirements may be satisfied by **different beans**.
- `@ConditionalOnMissingBean`: matches when **no bean satisfies any of the declared requirements**. Commonly used to provide a default bean while yielding to configuration declared by the application itself.

Both can be placed on a `@Configuration`/`@AutoConfiguration` class or a `@Bean` method. When placed on a class, the entire configuration inside is governed by the condition; when placed on a method, only that method's bean is governed by the condition.

| Attribute | Lookup Method | Example | What to Remember |
| --- | --- | --- | --- |
| `value` | Type as `Class<?>[]` | `@ConditionalOnBean(PaymentGateway.class)` | Shorthand for `value = PaymentGateway.class`; matches type-compatible beans too. |
| `type` | Type as class name `String[]` | `@ConditionalOnBean(type = "com.acme.PaymentGateway")` | Useful when specifying class names as strings, especially for meta-annotations or optional integrations. |
| `name` | Bean name `String[]` | `@ConditionalOnBean(name = "billingGateway")` | Bean name is not the Java type name; `@Bean("billingGateway")` sets an explicit name. |
| `annotation` | Class-level annotation on the bean `Class<? extends Annotation>[]` | `@ConditionalOnBean(annotation = FastPath.class)` | Looks up beans with the relevant annotation; use `@Retention(RUNTIME)` in custom examples. |

Example within the same application:

```java
@Bean("billingGateway")
PaymentGateway gateway() {
    return new StripeGateway();
}
```

- `@ConditionalOnBean(PaymentGateway.class)`: checks **type**, matching the `billingGateway` bean because its return type is `PaymentGateway`.
- `@ConditionalOnBean(name = "billingGateway")`: checks **name**, matching even without knowing the implementation class.
- `@ConditionalOnBean(annotation = SpecialGateway.class)`: checks **the annotation on the corresponding bean's type**; it does not automatically match just because the method is named `billingGateway`.

The snippet above is a **short illustration**, assuming `PaymentGateway` and `StripeGateway` are already defined; a complete standalone runnable example is in section 5.

## 3. Presence, Absence, and Combining Multiple Criteria

### 3.1. Lookup by Type

```java
@ConditionalOnBean(PaymentGateway.class)
@Configuration(proxyBeanMethods = false)
class GatewaySupportConfiguration {
    // @Bean methods are only considered when PaymentGateway already exists.
}
```

This is the condition "at least one bean of this type exists." It does not require the bean to have a fixed name; an implementation of the interface can also satisfy the condition if the registered type information is sufficiently accurate.

Use the inverse condition to provide a default:

```java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
PaymentGateway defaultGateway() {
    return new LocalPaymentGateway();
}
```

Meaning: register `defaultGateway` only when no `PaymentGateway` bean has been found yet. Here `PaymentGateway` and `LocalPaymentGateway` are hypothetical types for illustration; this snippet belongs inside a configuration class and is not a standalone Java file.

### 3.2. Lookup by Name

```java
@Bean("billingGateway")
PaymentGateway billingGateway() {
    return new StripeGateway();
}
```

In this case `@ConditionalOnBean(name = "billingGateway")` matches. If there is only an `"otherGateway"` bean of the same type `PaymentGateway`, the name condition **does not match**. For `@Bean` without an explicit name, the default usually uses the method name (`billingGateway` in the example above); declare names explicitly when the name is part of an integration contract.

`@ConditionalOnMissingBean(name = "billingGateway")` allows creating a bean with this name if that name is still missing. It **does not** guarantee the entire context lacks type `PaymentGateway`; a `PaymentGateway` under a different name may already exist.

### 3.3. Lookup by Annotation on the Bean

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@interface SpecialGateway {
}

@SpecialGateway
final class FastGateway implements PaymentGateway {
    // PaymentGateway implementation ...
}
```

The `@ConditionalOnBean(annotation = SpecialGateway.class)` condition looks for a bean carrying the matching annotation on the **bean class**. It is **not** a condition for "this annotation appears anywhere in the code," nor is it a substitute for `@ConditionalOnClass`. With this pattern, a bean of `FastGateway` must actually be registered before condition evaluation time.

**Important note specific to Spring Boot 3.3:** on a **`@Bean` method**, if you only write `@ConditionalOnBean(annotation = SpecialGateway.class)` without declaring `value`, `type`, or `name`, Spring Boot 3.3 also adds **the method's return type** to the requirement by default. As a result, the outcome can differ from the intuition of "check annotation only." The same applies to `@ConditionalOnMissingBean`. The clearest approach is to place the annotation condition on the **configuration class**, or explicitly declare the full type criterion you actually want to check. Starting in Spring Boot **3.4**, specifying `annotation` changed the default type-inference rule; you must re-check your conditions when upgrading versions. The standalone example in section 5 places the condition on the class to express the exact intent.

### 3.4. Combining Multiple Criteria: Every Requirement Must Be Met, Not Necessarily by One Bean

```java
@ConditionalOnBean(
    value = PaymentGateway.class,
    name = "billingGateway",
    annotation = SpecialGateway.class
)
```

The presence condition above simultaneously means:

1. A bean of type `PaymentGateway` exists.
2. A bean named `billingGateway` exists.
3. A bean with the `@SpecialGateway` annotation exists.

**It does not have to be the same bean.** For example, suppose there is a bean of type `PaymentGateway` annotated with `@SpecialGateway` named `fastGateway`, and a `String` bean named `billingGateway`: all three requirements above are satisfied! Do not use this combination if the business rule requires "the bean named `billingGateway` must itself be a `PaymentGateway` carrying `@SpecialGateway`." To check a relationship on the **same single bean**, check it with custom logic or redesign the declaration/identification; the standard conditional annotation does not express that relational predicate.

With `@ConditionalOnMissingBean(value = PaymentGateway.class, name = "billingGateway")`, the condition matches only if **there is neither a bean of type `PaymentGateway` nor a bean named `billingGateway`**. It does not mean "there is no single bean that has both that type and that name." This is a very common reasoning mistake.

## 4. Parameters and Limitations Affecting Results

- **Multiple types/names/annotations:** `@ConditionalOnBean(value = {A.class, B.class})` requires both A and B to have matching beans, potentially two different beans. `@ConditionalOnMissingBean(value = {A.class, B.class})` requires both A and B to be **absent**.
- **Parent–child contexts:** `search = SearchStrategy.ALL` (default) searches the hierarchy; `CURRENT` searches only the current context; `ANCESTORS` searches parent contexts. For example: `@ConditionalOnBean(value = PaymentGateway.class, search = SearchStrategy.CURRENT)`.
- **Generic containers:** `parameterizedContainer` allows recognizing the target type inside an explicitly specified generic wrapper, for example treating `Registration<PaymentGateway>` as the presence of `PaymentGateway` if the corresponding wrapper is declared. It does not infer arbitrary wrappers by default.
- **Exclusions when checking missing beans:** `@ConditionalOnMissingBean` supports `ignored` and `ignoredType` to ignore certain bean types when checking absence. `@ConditionalOnBean` does not have these two parameters.
- **Existence vs. unique selection:** `@ConditionalOnBean(PaymentGateway.class)` can still match when multiple gateways exist, yet autowiring a single `PaymentGateway` can be ambiguous. When the goal is having exactly one injectable candidate, look at `@ConditionalOnSingleCandidate(PaymentGateway.class)`; multiple beans can still match if a single `@Primary` candidate is designated.
- **Registration order:** conditions only see bean definitions processed **up to evaluation time**. Spring Boot recommends using bean conditions in auto-configuration because auto-configuration runs after beans declared by the application. If a condition depends on a bean from another auto-configuration, set the order via `@AutoConfiguration(after = OtherAutoConfiguration.class)` or `@AutoConfigureAfter`. Do not rely on the lexical order of `@Bean` methods.
- **`@Bean` return type:** declare a sufficiently specific return type so Spring has metadata to detect the type. Returning `Object` when actually creating a `PaymentGateway` can prevent type-based conditions from recognizing the bean at evaluation time.
- **A condition is not a promise about bean count:** `@ConditionalOnBean` only decides *configuration registration*, has no role in selecting a bean to inject, and does not mean the object has already been instantiated.

## 5. Standalone Runnable Java 17+ Example

The example uses **Spring Boot 3.3.13** and `AnnotationConfigApplicationContext` to isolate each scenario. Each condition is placed **on the configuration class**, so the annotation lookup is not affected by Boot 3.3's mechanism that adds the `@Bean` method's return type.

Structure:

```text
bean-lookup-demo/
├── pom.xml
└── src/main/java/demo/BeanLookupDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-lookup-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
            <version>3.3.13</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/BeanLookupDemo.java`:

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class BeanLookupDemo {

    interface Transport { }

    static final class PlainTransport implements Transport { }

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @interface Featured { }

    @Featured
    static final class FeaturedTransport implements Transport { }

    record Marker(String rule) { }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnBean(Transport.class)
    static class ByTypeConfiguration {
        @Bean("byType")
        Marker byType() {
            return new Marker("type");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnBean(name = "preferredTransport")
    static class ByNameConfiguration {
        @Bean("byName")
        Marker byName() {
            return new Marker("name");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnBean(annotation = Featured.class)
    static class ByAnnotationConfiguration {
        @Bean("byAnnotation")
        Marker byAnnotation() {
            return new Marker("annotation");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnBean(
        value = Transport.class,
        name = "preferredTransport",
        annotation = Featured.class
    )
    static class AllRequirementsConfiguration {
        @Bean("byAll")
        Marker byAll() {
            return new Marker("all");
        }
    }

    static void scenario(
        String label,
        boolean plainTransport,
        boolean featuredTransport,
        boolean unrelatedNamedBean
    ) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            // Register source beans before analyzing conditional configurations.
            if (plainTransport) {
                context.registerBean("plainTransport", PlainTransport.class);
            }
            if (featuredTransport) {
                context.registerBean("featuredTransport", FeaturedTransport.class);
            }
            if (unrelatedNamedBean) {
                context.registerBean(
                    "preferredTransport", String.class, () -> "unrelated"
                );
            }

            context.register(
                ByTypeConfiguration.class,
                ByNameConfiguration.class,
                ByAnnotationConfiguration.class,
                AllRequirementsConfiguration.class
            );
            context.refresh();

            System.out.printf(
                "%s: type=%s, name=%s, annotation=%s, all=%s%n",
                label,
                context.containsBean("byType"),
                context.containsBean("byName"),
                context.containsBean("byAnnotation"),
                context.containsBean("byAll")
            );
        }
    }

    public static void main(String[] args) {
        scenario("none", false, false, false);
        scenario("type-only", true, false, false);
        scenario("name-only", false, false, true);
        scenario("separate-beans", false, true, true);
    }
}
```

Requirements: **JDK 17+**, **Maven 3.8+**, ability to download Maven dependencies. Inside the `bean-lookup-demo` directory, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BeanLookupDemo
```

Four lines from `System.out.printf` (ignore any other messages Maven itself may print in the environment):

```text
none: type=false, name=false, annotation=false, all=false
type-only: type=true, name=false, annotation=false, all=false
name-only: type=false, name=true, annotation=false, all=false
separate-beans: type=true, name=true, annotation=true, all=true
```

Explanation of each scenario:

1. `none`: no source `Transport` bean, `preferredTransport` bean, or `@Featured` bean declared → all false.
2. `type-only`: only `PlainTransport` registered → condition by **type** matches; by name and annotation do not match.
3. `name-only`: `String` bean named `preferredTransport` → only the condition by **name** matches. Having a bean with the right name does not mean it is a bean of the right type.
4. `separate-beans`: `FeaturedTransport` has both type `Transport` and `@Featured` but is named `featuredTransport`; another `String` bean is named `preferredTransport` → all three criteria match, and the combined `byAll` condition also matches even though **no single bean satisfies all attributes**.

To turn the example into a real starter, use `@AutoConfiguration`, declare the auto-configuration in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, and write tests using `ApplicationContextRunner`. The current example uses a plain context so the observed results are clear and independent of package scanning.

## 6. How to Read and Diagnose Conditions When Building Auto-Configuration

1. State the business question clearly: "which bean type is needed," "which exact name is needed," or "which annotation on the bean class is needed." If all of them are needed on **the same bean**, do not assume combining `value`/`name`/`annotation` guarantees that relationship.
2. Check where `@Bean` is declared (return type, assigned name), `@Component`/`@Configuration`, runtime annotations on the class, and auto-configuration ordering.
3. Use Spring Boot's **condition evaluation report**: run the application with `--debug` to see why conditions matched/unmatched; with Actuator properly configured, the `/actuator/conditions` endpoint also provides condition report information.
4. Write tests with `ApplicationContextRunner` for at least three cases: no bean, bean with right type but wrong name/annotation, and full matching bean. Add a case where two different beans satisfy multiple criteria when using combined conditions.
5. When testing `@ConditionalOnMissingBean`, verify that a custom-defined bean blocks the default; also check bean names because name-based and type-based conditions have different semantics.

## 7. Common Mistakes and Fixes

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Confusing `@ConditionalOnBean` with `@ConditionalOnClass` | A class being on the classpath does not make it a bean | Check bean definitions / bean types; use `@ConditionalOnClass` separately for dependency checks |
| Assuming `name` is the class name | Bean names are determined by `@Bean`/bean registration | Check the actual registered name; specify an explicit name if part of a contract |
| Assuming combined criteria must belong to one bean | Requirements can be satisfied by different beans | Check the relationship separately if the same bean is genuinely required |
| Using `annotation` on a method in Boot 3.3 and forgetting the default return type | The method may implicitly add a return-type condition | Put the condition on the class or declare `value`/`type`/`name` intentionally |
| Thinking `@ConditionalOnMissingBean` means "missing one of several things" | It requires **none of the criteria** to be met | Analyze each absence requirement individually; do not mix AND/OR logic |
| Condition is false even though the bean appears later | At evaluation time the bean definition had not been processed yet | Place in auto-configuration and declare `after` when depending on another configuration |
| Injecting an interface bean when multiple candidates exist | Existence condition does not guarantee unique selection | Use qualifiers / primary or `@ConditionalOnSingleCandidate` as needed |
| Returning `Object` in a `@Bean` method | The bean's type metadata may be too generic | Declare a sufficiently specific return type |

## 8. Self-Check

**Question 1.** There is a `"standard"` bean of type `PaymentGateway` and a `"billingGateway"` bean of type `String`. Does `@ConditionalOnBean(value = PaymentGateway.class, name = "billingGateway")` match?  
**Answer:** Yes; one bean satisfies the type, and the other bean satisfies the name. Do not infer that `billingGateway` is a `PaymentGateway`.

**Question 2.** There is a `PaymentGateway` bean named `"customGateway"`, but no bean named `"billingGateway"`. Does `@ConditionalOnMissingBean(name = "billingGateway")` match?  
**Answer:** Yes; a lookup by name is not blocked by another bean of the same type with a different name.

**Question 3.** In Spring Boot 3.3, if you place `@ConditionalOnBean(annotation = Featured.class)` directly on a `@Bean Marker marker()` method, is it guaranteed to check only the annotation?  
**Answer:** No; when `value`/`type`/`name` are not declared, Boot 3.3 also uses the return type `Marker` as a default condition. Choose the annotation placement and criteria to match your intent.

**Remember:** type answers "what type is the bean?", name answers "what is the bean called?", and annotation answers "how is the bean class marked?". Spring Boot evaluates **the beans already registered at that moment**, and when combining multiple criteria, each criterion may be satisfied by a different bean.

## Official Reference Documentation

- Spring Boot 3.3 — [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html), *Bean Conditions* section.
- Spring Boot 3.3 — [`@ConditionalOnBean` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html).
- Spring Boot 3.3 — [`@ConditionalOnMissingBean` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html).
- Spring Boot 3.3 — [`@ConditionalOnSingleCandidate` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html).
- Spring Boot 3.4 [Release Notes — Bean-based Conditions](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes): differences when specifying `annotation` on `@Bean` methods.