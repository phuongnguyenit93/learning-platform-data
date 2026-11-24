# Default Bean Naming Rules and Explicit Naming

In Spring Boot, an object managed by Spring is called a **bean**. Each bean is registered in an `ApplicationContext` with a **bean name** used to identify the bean in the registry. This name appears in error messages, diagnostic tools, and certain forms of dependency injection. Understanding naming rules helps you predict which beans are created, avoid name collisions, and select the right implementation when multiple beans share the same type.

Spring Boot uses **Spring Framework's** bean mechanism. Boot itself often creates and configures many beans automatically, but the underlying naming rules for components and `@Bean` methods remain Spring's rules.

## 1. What Is a Bean Name, and How Does It Differ from a Class Name?

Consider a class:

~~~java
package com.example.store.service;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public String status() {
        return "READY";
    }
}
~~~

If the class lies within the component scan scope, Spring typically registers a bean with:

| Property | Value in example |
|---|---|
| Java class name | `OrderService` |
| Fully qualified class name | `com.example.store.service.OrderService` |
| Default Spring bean name | `orderService` |
| Bean type | `OrderService` |

**A bean name** is the identifier inside the container; **a bean type** is the information used to pick a bean that satisfies a dependency. A bean name does not have to match the class name, nor is it necessarily the name of the Java variable referencing the bean.

For example:

~~~java
private final OrderService service;
~~~

The field name `service` does not change the registered bean name `orderService`.

For Spring to manage a class, it must be registered through an appropriate mechanism such as component scanning, `@Bean`, `@Import`, or auto-configuration. **Merely declaring a class in a package does not create a bean.**

## 2. Default Rules for `@Component`, `@Service`, and Stereotypes

When component scan encounters a class annotated with `@Component` or a specialized annotation like `@Service`, `@Repository`, `@Controller`, or `@RestController`, Spring normally uses `AnnotationBeanNameGenerator` to generate a name when no explicit name is given.

Basic rule: take the **short class name** (without the package) and convert it to a JavaBeans-style property name, similar to `Introspector.decapitalize(...)`.

~~~java
package com.example.store;

import org.springframework.stereotype.Component;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.RestController;

@Component
class TaxCalculator {
}

@Service
class CustomerService {
}

@Repository
class CustomerRepositoryAdapter {
}

@RestController
class CustomerController {
}
~~~

Corresponding default bean names:

| Class | Default bean name |
|---|---|
| `TaxCalculator` | `taxCalculator` |
| `CustomerService` | `customerService` |
| `CustomerRepositoryAdapter` | `customerRepositoryAdapter` |
| `CustomerController` | `customerController` |
| `PaymentAPIClient` | `paymentAPIClient` |
| `URLParser` | `URLParser` |

The last two rows highlight an easily missed detail: the JavaBeans rule **does not always just lowercase the first character**. When **the first two characters of the class name are both uppercase**, as in `URLParser`, the name stays `URLParser` instead of becoming `uRLParser`. Therefore, do not infer bean names with `lowercase(firstCharacter)` for every class.

> Examples in the table assume the class is discovered by component scan, is not excluded by conditions/profiles, and has no other bean naming configuration.

### 2.1. Specialized Annotations Still Belong to the Component Family

`@Service`, `@Repository`, and `@Controller` are stereotypes based on `@Component`. They express architectural roles and may participate in specialized processing. However, as far as generating default names from scanned classes is concerned, they follow the same basic mechanism.

Do not confuse a Spring Data repository interface with a `@Repository`-annotated class. An interface extending `JpaRepository` can be registered via Spring Data's own repository mechanism with corresponding naming rules/configurations. This lesson focuses on **ordinary component beans** and **`@Bean`-created beans**.

### 2.2. File Paths Are Not Used as Bean Names

If you move a Java file in your IDE without changing its `package` or class name, bean name generation still relies on the class identity discovered by Spring. Packages mainly affect **scan scope** and distinguishing classes, whereas common default bean names typically come from the **short class name**.

## 3. Explicit Naming Directly on a Component

When you want a stable, clear name or need to distinguish two implementations, pass the name to the annotation:

~~~java
package com.example.store.payment;

import org.springframework.stereotype.Service;

@Service("cardPaymentService")
public class CardPaymentService {
    public void pay(long amount) {
        // Process card payment.
    }
}
~~~

Here the bean gets the name **`cardPaymentService`** chosen by the developer rather than the default derived name `cardPaymentService`. In this example the two happen to be identical; the value of an explicit declaration is that the bean name does not automatically change if the class is renamed:

~~~java
@Service("cardPaymentService")
public class CreditCardPaymentHandler {
    // Bean name is still "cardPaymentService".
}
~~~

Other stereotypes also support specifying a name, such as:

~~~java
@Component("exchangeRateCache")
class ExchangeRateCache {
}

@Repository("inventoryGateway")
class JdbcInventoryGateway {
}

@RestController("catalogHttpController")
class CatalogController {
}
~~~

The name declared in the annotation is the component's primary bean name. Explicit naming **does not change the bean's type**, does not automatically configure HTTP routes, and does not create an extra copy of the bean.

### When Should You Specify an Explicit Name?

- When distinguishing **two components with the same short class name** in different packages.
- When the bean name is part of an integration contract, e.g., used in `@Qualifier`, `@Resource`, or lookup by name.
- When you expect to rename the class later while keeping the bean identifier stable for consumers.
- When a library or framework integration requires a bean with a specific name.

You do not need to manually name **every** service. If there is only one bean per type, type-based injection is usually clearer and less dependent on name strings.

## 4. Default Rules for `@Bean` Methods

Another registration approach is placing `@Bean` on a factory method inside a Spring configuration class:

~~~java
package com.example.store.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PricingConfiguration {

    @Bean
    public PriceCalculator priceCalculator() {
        return new PriceCalculator();
    }
}

class PriceCalculator {
    long total(long price, long shipping) {
        return price + shipping;
    }
}
~~~

Spring creates a bean of type `PriceCalculator` from the factory method, and **the default bean name is the method name**: `priceCalculator`.

This differs from the `@Component` rule:

| Registration method | Default name source |
|---|---|
| `@Component` on `PriceCalculator` | Short class name via JavaBeans rules → `priceCalculator` |
| `@Bean` on method `buildCalculator()` returning `PriceCalculator` | Method name → `buildCalculator` |

Thus, the same `PriceCalculator` type can carry the bean name `priceCalculator`, `buildCalculator`, or another name depending on how it is registered. **Do not derive `@Bean` bean names from the returned class.**

### 4.1. Explicit Naming with `@Bean(name = ...)`

~~~java
@Configuration
class ShippingConfiguration {

    @Bean(name = "shippingRateCalculator")
    ShippingCalculator createShippingCalculator() {
        return new ShippingCalculator();
    }
}

class ShippingCalculator {
}
~~~

Even though the method is named `createShippingCalculator`, the bean name registered by Spring is `shippingRateCalculator`.

The shorthand syntax also works:

~~~java
@Bean("shippingRateCalculator")
ShippingCalculator createShippingCalculator() {
    return new ShippingCalculator();
}
~~~

The two snippets above show **two syntax options for the same registration**, not two methods to place simultaneously in the same configuration.

### 4.2. A Bean Can Have Multiple Aliases

The `name` attribute of `@Bean` accepts an array of names; the first is used as the **primary name**, and the remaining ones are **aliases**:

~~~java
@Bean(name = {"primaryRateCalculator", "legacyRateCalculator"})
ShippingCalculator shippingCalculator() {
    return new ShippingCalculator();
}
~~~

Here:

- `primaryRateCalculator` is the primary name.
- `legacyRateCalculator` is an alias.
- Both names refer to **the exact same bean**, not two independent objects.

Aliases are useful when renaming a bean incrementally while older references still use the old name. However, an alias is also a container-managed identifier: unclear aliases or collisions with other names can cause conflicts.

## 5. Flow from Code to Bean Name

~~~text
                      BEAN DECLARATION
                             |
                +------------+------------+
                |                         |
          Component scan             @Bean method
                |                         |
         Explicit name?              name/value set?
           /          \               /         \
         Yes          No            Yes          No
          |            |             |            |
   Use specified   Derive from   Use specified   Use method
       name        short class      name(s)        name
                   (JavaBeans)    (+ aliases)
                |                         |
                +------------+------------+
                             |
                   Register in bean registry
                             |
                Check collisions and conditions
                             |
                   Bean has name for lookup
~~~

This diagram covers the two most common registration paths. Additionally, auto-configuration, programmatic registration, `@Import`, factory beans, and other specialized mechanisms may apply their own naming rules. **Do not assume every bean in the context has a name starting with a lowercase letter.**

## 6. Are Bean Names Case-Sensitive?

In standard name-based lookups, bean names are string identifiers and **are case-sensitive**:

~~~java
@Component("emailSender")
class EmailSender {
}
~~~

`emailSender` and `EmailSender` are two distinct strings. Therefore:

~~~java
context.getBean("emailSender"); // Declared name.
context.getBean("EmailSender"); // Not the same name; may not be found.
~~~

Do not arbitrarily capitalize or lowercase bean name strings when using `@Qualifier`, `@Resource`, expressions, or name lookup APIs. Even if Spring uses aliases, pattern matching, or fallbacks in certain resolution mechanisms, the principle remains: **use the exact registered identifier**.

Bean names can contain dots or other valid characters, but you should pick a clear, consistent convention across the project. For ordinary application beans, `lowerCamelCase` such as `emailSender` or `orderRepository` is a familiar choice.

## 7. Two Classes with the Same Short Name Can Cause Component Scan Conflicts

Consider a project:

~~~text
com.example.shop
├── ShopApplication
├── sales
│   └── ReportService.java
└── support
    └── ReportService.java
~~~

Both classes have:

~~~java
@Service
public class ReportService {
}
~~~

The two files are **two different classes** because their packages differ:

~~~text
com.example.shop.sales.ReportService
com.example.shop.support.ReportService
~~~

Yet both default bean names are `reportService`. If both fall within the same scan scope and are registered into the same bean registry, Spring may throw a **bean definition conflict** error during scanning, such as `ConflictingBeanDefinitionException`.

This is a **bean name collision during registration**, not merely an issue of multiple candidates during dependency injection.

### Approach 1: Assign Role-Specific Names

~~~java
// com.example.shop.sales.ReportService
@Service("salesReportService")
public class ReportService {
}
~~~

~~~java
// com.example.shop.support.ReportService
@Service("supportReportService")
public class ReportService {
}
~~~

Now the registry has two distinct names: `salesReportService` and `supportReportService`.

### Approach 2: Rename Classes to Reflect Context

For example, `SalesReportService` and `SupportReportService`. Under default rules, Spring generates `salesReportService` and `supportReportService`. This often makes code more readable when the two classes genuinely have different responsibilities.

### Approach 3: Use a Different Name Generation Strategy for Component Scan

Spring provides `FullyQualifiedAnnotationBeanNameGenerator`, which can use the fully qualified class name as the default name when no explicit name is given:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.FullyQualifiedAnnotationBeanNameGenerator;

@SpringBootApplication(
        nameGenerator = FullyQualifiedAnnotationBeanNameGenerator.class
)
public class ShopApplication {
    public static void main(String[] args) {
        org.springframework.boot.SpringApplication.run(
                ShopApplication.class, args);
    }
}
~~~

With this strategy, components without explicit names can receive names like:

~~~text
com.example.shop.sales.ReportService
com.example.shop.support.ReportService
~~~

This option has a broad impact on the bean names of scanned components. Apply it only intentionally; if existing code relies on default name strings in `@Qualifier`, `@Resource`, `getBean(...)`, or integration configs, those references must be updated accordingly.

## 8. Bean Name Collision Differs from Multiple Beans of the Same Type

Two situations are frequently conflated:

**Situation A — Name collision:** two bean definitions compete for the same name `notificationSender`. This is a name registration conflict.

**Situation B — Same type:** two beans have different names, yet both implement the `NotificationSender` interface. Registration succeeds; an error occurs only when Spring needs to pick **one** bean by type without enough disambiguating information.

Example of two implementations:

~~~java
package com.example.shop.notification;

public interface NotificationSender {
    void send(String message);
}
~~~

~~~java
package com.example.shop.notification;

import org.springframework.stereotype.Component;

@Component("emailSender")
public class EmailSender implements NotificationSender {
    @Override
    public void send(String message) {
        // Send email.
    }
}
~~~

~~~java
package com.example.shop.notification;

import org.springframework.stereotype.Component;

@Component("smsSender")
public class SmsSender implements NotificationSender {
    @Override
    public void send(String message) {
        // Send SMS.
    }
}
~~~

There are now two beans with different names:

| Bean name | Concrete type | Interface type |
|---|---|---|
| `emailSender` | `EmailSender` | `NotificationSender` |
| `smsSender` | `SmsSender` | `NotificationSender` |

If you need to inject a `NotificationSender` without selection guidance, Spring may throw `NoUniqueBeanDefinitionException`. Changing a bean's name **will not automatically resolve** type ambiguity if two valid candidates still exist.

## 9. Selecting the Right Bean with `@Qualifier`

When you know clearly which implementation to use, you can specify it:

~~~java
package com.example.shop.notification;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class MessageService {
    private final NotificationSender sender;

    public MessageService(
            @Qualifier("emailSender") NotificationSender sender) {
        this.sender = sender;
    }

    public void notifyCustomer(String message) {
        sender.send(message);
    }
}
~~~

`@Qualifier("emailSender")` instructs Spring to filter candidates by matching qualifier. In this situation, the bean name `emailSender` matches the qualifier value. However, **a qualifier is not always just a bean name**: Spring allows declaring independent qualifier metadata to group or select beans. When reading code, distinguish between "qualifier value" and "registered bean name".

Another option, when one implementation is the default choice, is `@Primary`:

~~~java
@Primary
@Component("emailSender")
class EmailSender implements NotificationSender {
    @Override
    public void send(String message) {
        // Send email.
    }
}
~~~

`@Primary` prioritizes this bean in many single-bean type-injection scenarios; the bean name remains `emailSender`. When an explicit `@Qualifier` is present, qualifier selection narrows the candidate set before `@Primary` is considered.

Choosing the right mechanism for the goal:

| Mechanism | What problem does it solve? | Does it change the bean name? |
|---|---|---|
| `@Component("emailSender")` | Assigns an identifier to a component | Yes |
| `@Bean("emailSender")` | Assigns an identifier to a bean from a factory method | Yes |
| `@Qualifier("emailSender")` | Narrows the bean selected during injection | No |
| `@Primary` | Sets the preferred candidate among multiple same-type beans | No |
| `@Resource(name = "emailSender")` | Requests resource injection by name | No |

`@Resource` belongs to Jakarta Annotations in modern Spring apps with the right dependency; it can be useful when the intent is explicitly binding by name.

### Can Spring Use the Parameter Name During Injection?

With constructor injection or `@Autowired`, Spring primarily resolves dependencies **by type**. When multiple candidates exist, Spring may also consider qualifiers, primary markers, and **parameter/field names** under resolution rules if the required metadata is present.

~~~java
public MessageService(NotificationSender emailSender) {
    this.sender = emailSender;
}
~~~

In a suitable configuration, the parameter name `emailSender` can help select the bean of the same name. However, this relies on parameter-name metadata and resolution conditions—for example, Java compilation needs parameter names preserved (typically via `-parameters` in modern Spring Framework). **Do not treat variable names as a reliable bean selection contract** when choosing among multiple implementations matters; `@Qualifier` states intent clearly and is easier to control.

## 10. Bean Names in Application Context and Overriding

Normally, bean names must be **unique within the same bean registry**. If two configuration sources declare the same bean name, what happens depends on the registration type and the override policy.

Example:

~~~java
@Configuration
class FirstConfiguration {
    @Bean("paymentGateway")
    PaymentGateway firstGateway() {
        return new PaymentGateway("first");
    }
}

@Configuration
class SecondConfiguration {
    @Bean("paymentGateway")
    PaymentGateway secondGateway() {
        return new PaymentGateway("second");
    }
}
~~~

Assume `PaymentGateway` has a constructor taking a `String`. If both configurations are loaded into the same registry, they compete for the name `paymentGateway`.

In modern Spring Boot, bean definition overriding **is disabled by default**, so conflicts like this can lead to `BeanDefinitionOverrideException`. You can adjust the policy:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

However, enabling overriding broadly often hides problems and makes it hard to predict which bean ultimately wins. Some component scanning conflicts can also still fail under separate checks, so **enabling overriding is not a universal fix for every name collision**.

The proper fix is usually to fix bean names and registration scopes, use `@ConditionalOnMissingBean` in auto-configuration libraries when providing defaults, or remove duplicate configurations.

Note: an application with multiple application contexts in a parent–child hierarchy can have beans with the same name in different contexts, with child beans potentially shadowing parent ones on contextual lookups. The "uniqueness" rule here applies **per registry/context**, not necessarily across the entire JVM.

## 11. What Breaks When You Rename a Bean?

Suppose originally:

~~~java
@Service("invoiceService")
class InvoiceService {
}
~~~

After changing it to:

~~~java
@Service("billingService")
class InvoiceService {
}
~~~

Code injecting by the **unique type** `InvoiceService` will usually continue to work. However, places directly referencing the name `invoiceService` may need updating, such as:

- `@Qualifier("invoiceService")` or `@Resource(name = "invoiceService")`.
- `applicationContext.getBean("invoiceService")`.
- SpEL expressions referencing the bean by name, e.g., `@invoiceService`.
- Integration configurations/frameworks selecting beans by name, or conditions requiring a specific bean name.

If a controlled migration is needed, consider aliases (especially with `@Bean(name = {...})`) or an appropriate alias registration mechanism. Renaming the class while preserving an explicit bean name is often safer for components that depend on the name.

A bean name is also **distinct from**:

| Name | Meaning |
|---|---|
| `spring.application.name` | Application identifier for configuration/observability/integration |
| JPA table name (`@Table`) | Database table identifier |
| HTTP mapping (`@RequestMapping`, `@GetMapping`) | Request routing path or attributes |
| Java class name | Class identifier in code |
| Bean name | Bean identifier in the Spring container |

Changing `spring.application.name` does not rename all beans; naming a controller bean does not change API URLs.

## 12. How to Inspect Registered Bean Names

If you are unsure what name Spring gave a bean, you can query `ApplicationContext`. Below is an illustrative snippet to run in a test application:

~~~java
package com.example.store;

import java.util.Arrays;
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class BeanInspectionConfiguration {

    @Bean
    CommandLineRunner printBeanNames(ApplicationContext context) {
        return args -> {
            String[] names = context.getBeanNamesForType(
                    com.example.store.service.OrderService.class);
            Arrays.stream(names).forEach(System.out::println);
        };
    }
}
~~~

When `OrderService` is registered with `@Service` as in the first example and no other bean shares that type, the output is typically:

~~~text
orderService
~~~

This prints **bean names by type**, helping distinguish actual bean names from guesses based on class names. Other inspection options:

~~~java
context.containsBean("orderService");
context.getAliases("orderService");
context.getBean("orderService");
~~~

`containsBean(...)` checks whether the name/alias is recognized; `getAliases(...)` reports aliases exposed for that name by the context; `getBean(...)` retrieves the instance and may trigger lazy bean creation depending on the situation. When you only want to **inspect registered names**, prefer metadata lookup methods and avoid triggering unnecessary bean instantiation.

Spring Boot Actuator provides the `beans` endpoint to inspect beans per context when the Actuator starter is present and the endpoint is properly enabled/exposed. Do not expose this diagnostic endpoint publicly on the Internet without access control, as it can reveal internal application structure.

### Common Error Messages

| Error type | What to check |
|---|---|
| `NoSuchBeanDefinitionException` on lookup by name | Is the bean name cased accurately? Is there an alias? Was the bean registered in the active context? |
| `NoUniqueBeanDefinitionException` on interface injection | Multiple valid beans share the type; need `@Qualifier`/`@Primary` or a design adjustment |
| `ConflictingBeanDefinitionException` during scan | Multiple components generate the same bean name with incompatible definitions |
| `BeanDefinitionOverrideException` | Attempted to register an already-taken bean name in a context that disallows overriding |

Not all of these errors are caused by naming rules: a bean can also be missing due to package scanning, profiles, auto-configuration conditions, missing dependencies, or custom configuration.

## 13. Practical Naming Guidelines for Real Projects

A simple, maintainable strategy:

1. **Use auto-generated names by default** for components when there is only one bean of that type and no name-based contract.
2. **Choose semantic names** when there are multiple implementations or an integration selects beans by name. For example, `primaryPaymentGateway` and `backupPaymentGateway` convey roles better than `gateway1` and `gateway2`.
3. **Remember that `@Bean` defaults to the method name.** If you rename a factory method, check whether anything depends on the bean name.
4. **Do not rely on overriding to resolve duplicate names.** Rename or narrow scan/configuration scope to eliminate conflicting definitions.
5. **Use `@Qualifier` when selecting an implementation must be explicit.** Do not rely on a Java variable name accidentally matching a bean name.
6. **Check actual bean names** via `ApplicationContext`, error logs, or Actuator in an appropriate environment before guessing.

Example application layout:

~~~text
com.example.store
├── StoreApplication.java
├── payment
│   ├── PaymentGateway.java          (interface)
│   ├── StripeGateway.java           (@Component("stripeGateway"))
│   ├── BankTransferGateway.java     (@Component("bankTransferGateway"))
│   └── CheckoutService.java         (@Service; uses @Qualifier)
└── config
    └── CheckoutConfiguration.java   (@Bean("checkoutPolicy"))
~~~

If `StoreApplication` is in the root package and these classes are scanned/imported properly, the application may contain names such as:

~~~text
storeApplication
stripeGateway
bankTransferGateway
checkoutService
checkoutConfiguration
checkoutPolicy
~~~

The two beans `storeApplication` and `checkoutConfiguration` reflect that configuration classes themselves can also be registered as beans; exact names depend on discovery and configuration. `PaymentGateway` is just an interface, so no bean is automatically created from it. `checkoutPolicy` comes from the explicit name on the `@Bean` method, not derived from the return type.

**Key takeaway:** For scanned components, Spring usually generates names using JavaBeans rules from the **short class name**; for `@Bean` methods, the default is the **method name**. You can set explicit names for both and declare aliases where appropriate. Bean names serve as **identifiers in the container**, while bean selection during injection depends on **type, qualifiers, primary markers, and resolution rules**. Keeping these two roles distinct helps you resolve both name collisions and multiple-bean-of-same-type errors accurately.
