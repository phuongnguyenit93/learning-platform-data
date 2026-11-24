# @Resource, Bean Names, and Differences from Type-Based Selection

In a Spring Boot application, multiple beans can implement the same interface. For example, a payment application might have `StripePaymentGateway`, `BankPaymentGateway`, and `FakePaymentGateway`, all implementing `PaymentGateway`. When a service requires `PaymentGateway`, Spring needs to know **exactly which bean will be passed in**.

Two commonly compared injection approaches are:

- **`@Resource`**: prioritizes finding beans by **name** (name-based resolution), with a default rule based on the field or property name.
- **`@Autowired`**: primarily finds beans by **Java type** (type-based resolution); when multiple candidates exist, `@Qualifier`, `@Primary`, and candidate resolution rules can be used.

This difference directly affects bean naming, renaming fields/properties, adding new implementations, and designing service constructors. Understanding it properly helps avoid injecting the wrong implementation or failing to find a bean at application startup.

## 1. A bean has two traits to distinguish: name and type

A bean in Spring has a **bean name** and a **bean type**. They answer two different questions:

- **Bean name**: by what name does the container identify the bean?
- **Bean type**: by what class/interface can the bean be injected or queried?

For example:

```java
public interface PaymentGateway {
    String charge(long amount);
}
```

Two implementations:

```java
import org.springframework.stereotype.Component;

@Component("stripeGateway")
public class StripePaymentGateway implements PaymentGateway {
    @Override
    public String charge(long amount) {
        return "Charged by Stripe: " + amount;
    }
}
```

```java
import org.springframework.stereotype.Component;

@Component("bankGateway")
public class BankPaymentGateway implements PaymentGateway {
    @Override
    public String charge(long amount) {
        return "Charged by bank: " + amount;
    }
}
```

The container can manage two beans:

| Bean name | Concrete type | Interface usable for lookup |
|---|---|---|
| `stripeGateway` | `StripePaymentGateway` | `PaymentGateway` |
| `bankGateway` | `BankPaymentGateway` | `PaymentGateway` |

Both beans can satisfy a dependency of type `PaymentGateway`. However, if you need to look up by the name `stripeGateway`, the container selects only the bean with that name (or a corresponding alias).

A way to verify while debugging:

```java
PaymentGateway stripe =
        applicationContext.getBean("stripeGateway", PaymentGateway.class);

PaymentGateway bank =
        applicationContext.getBean("bankGateway", PaymentGateway.class);
```

The snippet above assumes the context has two beans with those exact names. If no matching bean name exists, Spring throws a lookup error; if the bean exists but is incompatible with the requested type, typed retrieval also fails.

**Name and type do not substitute for each other.** A bean can be looked up by type without the caller knowing its name; conversely, a bean with a specific name may still not be the implementation the caller expects if the requested type is too broad or misconfigured.

## 2. How does Spring generate default bean names?

A bean name can be set explicitly or derived from where it is declared.

### 2.1. With stereotype annotations

If you write:

```java
@Service
public class OrderService {
}
```

Spring typically generates the default bean name from the class name using decapitalization rules: `OrderService` becomes `orderService`.

You can specify an explicit name:

```java
@Service("checkoutService")
public class OrderService {
}
```

In this example, the bean name is `checkoutService`; the class name remains `OrderService`.

The same rule applies to `@Component`, `@Repository`, `@Controller`, and corresponding stereotypes.

### 2.2. With `@Bean` methods

The default bean name is typically the name of the declaring method:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    public PaymentGateway stripeGateway() {
        return new StripePaymentGateway();
    }
}
```

The bean is registered under the name `stripeGateway`. Explicit names or aliases can be given:

```java
@Bean(name = {"stripeGateway", "primaryPaymentGateway"})
public PaymentGateway paymentGateway() {
    return new StripePaymentGateway();
}
```

In this example, `stripeGateway` is the bean name and `primaryPaymentGateway` is an alias. Both names can be used to look up the same bean. Names and aliases should be managed consistently to avoid confusion.

### 2.3. Bean names are case-sensitive

Bean names are typically matched by exact string and are case-sensitive. `stripeGateway` and `StripeGateway` should not be treated as the same name. Use a consistent convention, usually lower camel case.

Default bean names are also not always simply lowercasing the first character. JavaBeans decapitalization rules preserve certain names starting with two consecutive uppercase letters; for instance, a class named `URLClient` may keep `URLClient`. When a name is part of an integration contract, set it explicitly instead of relying on derived naming rules.

## 3. `@Resource` is name-based injection

`@Resource` belongs to Jakarta Common Annotations (formerly JSR-250), not a Spring-specific annotation. Spring supports it during dependency injection through its common annotation processing infrastructure.

For example:

```java
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    @Resource(name = "stripeGateway")
    private PaymentGateway paymentGateway;

    public String checkout(long amount) {
        return paymentGateway.charge(amount);
    }
}
```

Meaning:

1. The container processes the `@Resource` annotation on the field.
2. The value `name = "stripeGateway"` requests the bean named `stripeGateway`.
3. That bean must be compatible with the field type `PaymentGateway`.
4. Spring injects a reference to the bean into the field before the bean is put into use according to its lifecycle.

In this example, even with multiple beans implementing `PaymentGateway`, the name `stripeGateway` specifies the desired bean.

### 3.1. Without specifying `name`: default name comes from field/property

You can write:

```java
@Resource
private PaymentGateway stripeGateway;
```

When `name` is not declared, Spring infers the default name from the field: `stripeGateway`. Similarly, if using a setter `setStripeGateway(...)`, the default property name is `stripeGateway`.

Therefore, renaming a field can alter how `@Resource` looks up the bean:

```java
@Resource
private PaymentGateway paymentGateway;
```

In this case, the inferred default name becomes `paymentGateway`, no longer `stripeGateway`.

This is an important difference from `@Autowired`: **the field name is part of `@Resource`'s default bean selection rule**, so refactoring field names can affect dependency resolution.

### 3.2. How Spring handles default name and type fallback

In Spring's annotation-driven injection, when `@Resource` **does not explicitly specify `name`**, Spring first uses the default name inferred from the field/property. If no bean with that default name exists, Spring can fall back to type-based resolution.

For example, if the field is named `paymentGateway` and no bean named `paymentGateway` exists, while the context has only one bean matching `PaymentGateway`, Spring can inject that candidate by type.

If multiple beans of the same type exist and cannot be uniquely chosen, the fallback will still encounter ambiguity.

**When `name` is explicitly specified**, the intent is to look up by that name. If a bean with that name does not exist or is incompatible in type, injection fails; Spring should not silently pick another bean of the same type with a different name to mask a typo or misconfiguration.

This is Spring's supported behavior in `@Resource` processing; if you need portability across different Jakarta containers, verify the target environment's rules instead of relying on Spring-specific fallback behavior.

### 3.3. Using `@Resource` on setters

`@Resource` is supported by Spring on fields and bean property setter methods:

```java
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private PaymentGateway gateway;

    @Resource(name = "stripeGateway")
    public void setGateway(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public String checkout(long amount) {
        return gateway.charge(amount);
    }
}
```

With setters, an explicit `name` is used for lookup. If `name` is omitted, the property name inferred from the setter method is `gateway` in the `setGateway` example.

### 3.4. `@Resource` is not a constructor injection choice

Spring supports `@Resource` on fields and property setters, **not as a constructor injection annotation** in the way `@Autowired` is supported.

If a required dependency should be provided through a constructor, use `@Autowired` combined with `@Qualifier` or an appropriate constructor injection mechanism:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("stripeGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Constructor injection is usually the better choice for required dependencies because fields can be `final`, dependencies are explicit, and unit tests can easily construct instances. Thus, while `@Resource` is useful when name-based injection on fields/setters is needed, do not adopt it just to replace every use of `@Autowired`.

## 4. `@Autowired` primarily selects by type

`@Autowired` belongs to Spring Framework. Its default mechanism is finding beans matching the **dependency type**.

Example where only one bean implements `PaymentGateway`:

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Spring searches for candidates assignable to `PaymentGateway`. If only one matching candidate exists, the container injects it. This is the common approach when a dependency is naturally defined by an interface/type.

If two beans implement `PaymentGateway`, such as `stripeGateway` and `bankGateway`, relying on type alone is not enough to choose a unique candidate. You must supply additional metadata or selection rules.

### 4.1. `@Qualifier` narrows the type-based candidate set

`@Qualifier` is commonly used with `@Autowired` to choose one bean among candidates of the same type:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("stripeGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

The process can be understood in two steps:

1. Find beans matching the `PaymentGateway` type.
2. Use the `stripeGateway` qualifier to filter/select the matching candidate.

The qualifier value often matches the bean name in simple examples. However, `@Qualifier` is candidate selection metadata, not merely a lookup-by-name API. You can declare custom qualifiers on beans and injection points to describe roles/semantics, such as `@Qualifier("primary")`, `@Qualifier("external")`, or a custom qualifier annotation.

For example:

```java
@Component
@Qualifier("external")
public class RemotePaymentGateway implements PaymentGateway {
    @Override
    public String charge(long amount) {
        return "Remote charge: " + amount;
    }
}
```

Injection point:

```java
public CheckoutService(
        @Qualifier("external") PaymentGateway gateway) {
    this.gateway = gateway;
}
```

Here `external` describes the candidate's group/meaning. This way of using qualifiers is useful when implementation bean names may change while the role required by code stays the same.

### 4.2. `@Primary` selects a default candidate

If multiple beans share a type and one bean should be preferred at most injection points, you can mark it `@Primary`:

```java
@Component
@Primary
public class StripePaymentGateway implements PaymentGateway {
    @Override
    public String charge(long amount) {
        return "Stripe charge: " + amount;
    }
}
```

When a `PaymentGateway` dependency has no specific qualifier, the primary bean can be selected as the preferred candidate.

`@Primary` **does not remove** other beans from the container. You can still request another bean using `@Qualifier` or access it by name. If multiple beans are marked primary within the same selection scope, Spring may still fail to resolve uniquely.

### 4.3. Injection point name can act as a fallback in `@Autowired` resolution

`@Autowired` is primarily by type, though Spring can also use the field/parameter name as a hint when multiple candidates share a type and other precedence rules have not picked one. For instance, a field named `stripeGateway` can help Spring select a bean with the same name in certain situations.

However, do not treat this as a name-first contract like `@Resource(name = "...")`. A clearer approach is declaring an explicit `@Qualifier` when you need a specific implementation.

For constructor/method parameters, using the parameter name as a fallback depends on parameter name information available at compile time and the Spring version/configuration. If relying on this rule, ensure the build preserves parameter names; do not let critical bean selection depend on parameter names that might accidentally be stripped during compilation.

## 5. Direct comparison of `@Resource` and `@Autowired`

| Criterion | `@Resource` | `@Autowired` |
|---|---|---|
| Annotation source | Jakarta Common Annotations (formerly `javax.annotation`) | Spring Framework |
| Dominant rule | By **bean name** | By **bean type** |
| When no name/qualifier is specified | Default name from field/property; in Spring, can fall back to type if the default name does not exist | Finds candidates by type; applies qualifier/primary and other resolution rules |
| Specifying an exact name | `@Resource(name = "stripeGateway")` | Typically uses `@Qualifier("stripeGateway")` alongside type |
| Constructor injection | Not supported by Spring in the field/setter style | Supported |
| Field injection | Yes | Yes |
| Setter injection | Yes | Yes |
| Semantic qualifier selection | Not `@Resource`'s main purpose | Yes, via `@Qualifier` and custom qualifiers |
| Default candidate selection | By requested name; type fallback in Spring's default case | `@Primary` and candidate resolution rules |
| Well-suited for | Dependencies identified by name, especially when the name is part of a contract | Abstraction/type-based dependencies, constructor injection, qualifiers, and primary |

Way to remember:

- `@Resource`: "Find the bean with this name; if I omit the name, use the field/property name by default."
- `@Autowired`: "Find a bean with a matching type; if there are multiple, use qualifier/primary or candidate selection rules."

This is a shorthand summary. When debugging, consider type, name, alias, qualifier, primary, scope, and bean registration conditions together.

## 6. Complete example: two implementations, two selection styles

Suppose two beans are configured:

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean("stripeGateway")
    PaymentGateway stripeGateway() {
        return new StripePaymentGateway();
    }

    @Bean("bankGateway")
    PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
```

### 6.1. Selecting by name with `@Resource`

```java
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

@Service
public class StripeCheckoutService {

    @Resource(name = "stripeGateway")
    private PaymentGateway gateway;

    public String checkout(long amount) {
        return gateway.charge(amount);
    }
}
```

The explicit bean name is `stripeGateway`, so `bankGateway` is not selected merely because it also implements `PaymentGateway`.

### 6.2. Selecting by type + qualifier via constructor

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class BankCheckoutService {

    private final PaymentGateway gateway;

    public BankCheckoutService(
            @Qualifier("bankGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public String checkout(long amount) {
        return gateway.charge(amount);
    }
}
```

Here the constructor clearly shows the required dependency, and the qualifier identifies the implementation. If you rename the bean, you need to update the corresponding qualifier or replace it with a more stable semantic qualifier annotation.

### 6.3. Selecting default with `@Primary`

If `StripePaymentGateway` is configured with `@Primary`, the following service needs no qualifier when it only wants the default:

```java
@Service
public class DefaultCheckoutService {

    private final PaymentGateway gateway;

    public DefaultCheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Even so, code can become hard to read if business behavior heavily depends on an application-wide default implementation. For distinct payment flows, specify the qualifier/role right at the injection point.

## 7. When should you use `@Resource`?

`@Resource` is helpful when **the bean name is an intentional identifier**:

- The application has multiple beans sharing an interface and a published bean naming convention.
- You integrate components by a fixed bean name from another module.
- You maintain a codebase using Jakarta Common Annotations and need to preserve a name-based injection contract.
- You want to inject into a field or setter by a specific name.

Example where a bean name acts as configuration:

```java
@Resource(name = "primaryPaymentGateway")
private PaymentGateway gateway;
```

Readers immediately see which bean name the component expects. However, renaming the bean in configuration requires updating every reference to that name.

Do not use `@Resource` mechanically just to "make Spring find the right class." If only one matching implementation exists and the dependency is required, type-based constructor injection is simpler.

## 8. When should you use `@Autowired` with `@Qualifier`?

`@Autowired` fits well when a dependency is described by **abstraction/type** and you want to keep constructor injection:

```java
@Service
public class InvoiceService {

    private final PaymentGateway gateway;

    public InvoiceService(
            @Qualifier("stripeGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Especially recommended when:

- The dependency is required for the object to operate.
- You want fields to be `final` and unit tests easy to write.
- One bean must be selected among multiple implementations of the same type.
- The qualifier expresses a role like `@Qualifier("external")` rather than locking code to a class name.
- You want to leverage `@Primary` for defaults and qualifiers for specific exceptions.

A useful design principle: **select by type first, add qualifiers when roles need distinguishing**. Use bean names when the name itself is genuinely the contract the component requires.

## 9. `@Resource` and setter/property names

When placing `@Resource` on a setter, the default name is the property name according to JavaBeans conventions.

```java
@Resource
public void setPaymentGateway(PaymentGateway gateway) {
    this.paymentGateway = gateway;
}
```

The inferred property name is `paymentGateway`. If the container has a bean with that name, Spring prioritizes looking up by that default name.

If the setter is:

```java
@Resource
public void setGateway(PaymentGateway gateway) {
    this.gateway = gateway;
}
```

The default name changes to `gateway`. This can be surprising if the bean is still named `stripeGateway`. You can state it explicitly:

```java
@Resource(name = "stripeGateway")
public void setGateway(PaymentGateway gateway) {
    this.gateway = gateway;
}
```

**The setter method name is not the bean name.** It only contributes to deriving the property name when `@Resource` lacks an explicit `name`.

## 10. Bean name, alias, and qualifier: three concepts not to merge into one

These values often look similar in small applications, but each has its own meaning:

- **Bean name**: the primary name used to identify a bean in the container.
- **Alias**: another name pointing to the same bean.
- **Qualifier**: metadata helping pick a bean matching an injection point.

Example of a bean with a primary name and an alias:

```java
@Bean(name = {"stripeGateway", "cardGateway"})
PaymentGateway paymentGateway() {
    return new StripePaymentGateway();
}
```

Both names can look up the same bean. However, a qualifier can describe a role independently of aliases:

```java
@Component
@Qualifier("external")
public class RemotePaymentGateway implements PaymentGateway {
    // ...
}
```

`@Qualifier("external")` at an injection point expresses a requirement for an implementation carrying the `external` qualifier. A bean name can still participate as a fallback qualifier value under Spring's rules, but do not design a system assuming every qualifier string is always a bean alias.

If multiple implementations share a qualifier or carry custom metadata, you must understand how Spring filters candidates and ensure a unique result.

## 11. Annotation versions: `jakarta.annotation.Resource` and `javax.annotation.Resource`

The package name of `@Resource` depends on the Java/Spring generation:

| Common platform | Typical import |
|---|---|
| Spring Boot 2.x / Spring Framework 5.x | `javax.annotation.Resource` |
| Spring Boot 3.x / Spring Framework 6.x and later | `jakarta.annotation.Resource` |

Spring Boot 3 migrated to Jakarta EE; Common Annotations shifted from the `javax.annotation` namespace to `jakarta.annotation`. Therefore, older code with:

```java
import javax.annotation.Resource;
```

must be updated accordingly when upgrading to Boot 3+:

```java
import jakarta.annotation.Resource;
```

These are not two classes you can swap arbitrarily by switching dependencies. Use the exact API matching the Spring/Jakarta version your project uses.

If the compiler reports that `Resource` cannot be found, check the import and corresponding API dependency in the build. Do not manually add an annotation API version incompatible with your current Spring platform. Spring Boot starters/BOMs may already manage the necessary dependency; inspect the dependency tree before adding one manually.

## 12. Can `@Resource` inject into a constructor?

A constructor is an ideal place to declare required dependencies, but `@Resource` under Spring's annotation-driven injection support is not used on constructors the way `@Autowired` is.

Example not to write:

```java
// Do not use @Resource this way in Spring
public CheckoutService(@Resource PaymentGateway gateway) {
    this.gateway = gateway;
}
```

Instead:

```java
public CheckoutService(
        @Qualifier("stripeGateway") PaymentGateway gateway) {
    this.gateway = gateway;
}
```

If a class has only one constructor, Spring automatically uses that constructor for injection without requiring `@Autowired`. If there are multiple constructors, explicitly declare the chosen constructor according to injection rules.

This is a practical reason why `@Autowired` + `@Qualifier` is generally better suited for new Spring code: it supports implementation selection while preserving constructor injection.

## 13. Is combining `@Resource` and `@Autowired` necessary?

Normally, you should not place both annotations on the same injection point hoping they will "complement" each other. They are two separate injection-processing mechanisms and can cause confusion regarding processing order, especially when both try to assign a value to the same field/property.

Choose one way to express intent:

- Need a specifically named bean on a field/setter: `@Resource(name = "...")`.
- Need a dependency by type and candidate selection: `@Autowired` with `@Qualifier` or `@Primary`.
- Need a required dependency: prefer constructor injection; if multiple implementations exist, place a qualifier on the parameter.

Keeping them separate prevents code from depending on annotation-processing behavior that readers find hard to predict.

## 14. Common errors when selecting beans by name

| Symptom | Possible cause | Resolution |
|---|---|---|
| `NoSuchBeanDefinitionException` when using `@Resource` | Explicit bean name does not exist or no matching bean exists; configuration not loaded. | Check name, alias, component scan, `@Bean`, and auto-configuration conditions. |
| `NoUniqueBeanDefinitionException` | `@Resource` uses default name which does not exist, type fallback hits multiple candidates; or type injection lacks qualifier/primary. | Use explicit name or `@Qualifier`; check `@Primary`. |
| `BeanNotOfRequiredTypeException` | A bean with the right name exists, but its type is incompatible with the field/parameter. | Fix bean name, declared type, or implementation. |
| Renaming a field breaks startup | `@Resource` had no explicit name so default name changed with field/property. | Set explicit `name` or adjust bean name. |
| `@Autowired` injects the wrong implementation after adding a new bean | Previously only one candidate existed; now multiple exist and default selection changed. | Use qualifier/primary and inspect the dependency graph. |
| `@Resource` fails to compile | Wrong `javax.annotation`/`jakarta.annotation` version imported or API missing from classpath. | Use the namespace matching Spring Framework and check dependencies. |
| `@Resource` on constructor does not work | Annotation placement is not an injection point supported by Spring. | Use constructor injection with `@Qualifier`. |
| Qualifier fails to select a bean | Qualifier value does not match metadata/candidates; or bean is not of the required type. | Check type first, then qualifier and bean definition. |

### Reading errors in order

When startup fails, do not just guess and rename beans. Check:

1. What is the dependency type at the injection point?
2. How many beans are assignable to that type?
3. What is the exact bean name, and are there aliases?
4. Does `@Resource` specify `name`, or is it using the default name from the field/property?
5. If using `@Autowired`, what qualifier/primary is present?
6. Is the bean actually registered, or excluded by component scan/condition/profile?
7. Was the bean created successfully, or did its constructor/factory method throw an exception?

A right name on an unregistered bean still cannot be injected. Likewise, a registered bean of an incompatible type still cannot be assigned to a field/parameter.

## 15. Inspecting bean names and types in the container

In debugging code or tests, you can query by name and by type:

```java
PaymentGateway byName =
        context.getBean("stripeGateway", PaymentGateway.class);

Map<String, PaymentGateway> allGateways =
        context.getBeansOfType(PaymentGateway.class);

allGateways.forEach((name, gateway) ->
        System.out.println(name + " -> " + gateway.getClass().getName()));
```

- `getBean(name, type)` confirms a specific bean name exists and is type-compatible.
- `getBeansOfType(type)` shows beans that can satisfy the type; helpful when investigating multiple implementations.
- `getBean(type)` asks Spring to resolve a single unique bean by type; if multiple unresolved candidates exist, it can throw an error.

When proxies are involved, `getClass()` on the returned object may show a proxy class rather than the concrete target class. Therefore, do not rely solely on the runtime class name to conclude what the original bean definition is.

### A simple test checking qualifier/name selection

```java
@SpringBootTest
class CheckoutServiceTest {

    @Autowired
    ApplicationContext context;

    @Test
    void stripeGatewayHasExpectedBeanName() {
        PaymentGateway gateway =
                context.getBean("stripeGateway", PaymentGateway.class);

        assertNotNull(gateway);
    }
}
```

This test illustrates looking up by name in the context. To thoroughly test service behavior, invoke business methods and assert outcomes, or use a test configuration with easily observable implementations. Appropriate JUnit/Spring Boot Test imports matching the project's Boot line are required.

## 16. Selecting by name or by type in application design?

There is no single approach right for every situation. Choose the mechanism that expresses the exact relationship the code needs.

| Need | Suitable choice |
|---|---|
| Only one implementation for an abstraction | Type-based constructor injection; Spring resolves automatically. |
| Multiple implementations and one is the default | `@Primary` on the default candidate, if the application-wide rule is clear. |
| Multiple implementations and each use case needs a specific one | `@Qualifier` on the constructor parameter. |
| Bean name is an agreed contract with another module | `@Resource(name = "...")` on field/setter, or lookup by name when needed. |
| Need required dependency injection and easy testing | Constructor injection with type/qualifier. |
| Maintaining code using Jakarta Common Annotations | Can keep `@Resource` if name-based semantics fit. |
| Need selection by a business role stable across class renames | Custom qualifier annotation or semantic qualifier metadata. |

An example of a custom qualifier:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.beans.factory.annotation.Qualifier;

import static java.lang.annotation.ElementType.FIELD;
import static java.lang.annotation.ElementType.PARAMETER;
import static java.lang.annotation.ElementType.TYPE;

@Target({FIELD, PARAMETER, TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Qualifier
public @interface ExternalGateway {
}
```

Mark the implementation:

```java
@Component
@ExternalGateway
public class RemotePaymentGateway implements PaymentGateway {
    // implementation...
}
```

Inject by role:

```java
@Service
public class InternationalCheckoutService {

    private final PaymentGateway gateway;

    public InternationalCheckoutService(
            @ExternalGateway PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

This expresses **why** the dependency is chosen, not just what the bean is named. It is especially useful when a module has multiple implementations varying by environment or provider.

## 17. Practice exercises

### Exercise A — Observing default bean names

1. Create an `EmailNotifier` class with `@Component` and no explicit name.
2. Start the application and query the bean by name `emailNotifier`.
3. Change it to `@Component("mailSender")`.
4. Try looking up by the old name and the new name; explain the difference.

### Exercise B — Two beans of the same type

1. Create two implementations `StripePaymentGateway` and `BankPaymentGateway`.
2. Declare both beans with distinct names.
3. Inject a `PaymentGateway` with `@Autowired` and no qualifier.
4. Observe the ambiguity error.
5. Add `@Primary` to one bean, then use `@Qualifier` to choose the other bean in another service.

### Exercise C — Renaming a field with `@Resource`

1. Declare a bean named `stripeGateway`.
2. Inject using `@Resource` without `name` into a field named `stripeGateway`.
3. Rename the field to `paymentGateway` while keeping the bean name unchanged.
4. Observe the default name rule and try adding a bean named `paymentGateway`.
5. Switch to `@Resource(name = "stripeGateway")` to pin the requested name.

### Exercise D — Comparing with constructor injection

Write a service using `@Autowired` + `@Qualifier` on a constructor parameter. Then write a version using `@Resource(name = "...")` on a field or setter. Compare:

- Is the dependency clearly visible via the constructor?
- Does renaming the field/property change the default bean name?
- Can `final` be used for the dependency?
- What parameters does a plain Java unit test need to instantiate the service?

### Exercise E — Migrating Jakarta namespace

If you have legacy code using `javax.annotation.Resource`, identify the project's Spring Boot/Spring Framework version. Compare it with a Boot 3+ project using `jakarta.annotation.Resource`. Note the corresponding imports and API dependencies; do not mix both namespaces on the same injection point.

## 18. Principles to remember

1. **Bean name and bean type are two distinct concepts.** Multiple beans can share a type while having distinct names.
2. **`@Resource` primarily selects by name.** If `name` is omitted, Spring derives the name from the field/property; in Spring, if the default name does not exist, it can fall back to type.
3. **An explicit `@Resource(name = "...")` is a strict requirement.** A wrong name or incompatible type causes injection to fail instead of silently picking another implementation.
4. **`@Autowired` primarily selects by type.** When multiple candidates exist, use `@Qualifier` or `@Primary` to express the choice.
5. **Field/parameter names can act as fallbacks in certain `@Autowired` rules**, but should not replace explicit qualifiers when the choice matters.
6. **Boot 3+/Spring 6 `@Resource` uses `jakarta.annotation.Resource`**; Boot 2/Spring 5 code typically uses `javax.annotation.Resource`.
7. **Constructor injection is usually best for required dependencies.** Combine type and qualifier for clear, easily testable dependencies with minimal coupling to field names.

When multiple beans implement the same interface, ask: **does the component need a role/type, or does it need a bean with a specific name?** If the answer is role/type, use constructor injection with qualifier/primary as needed. If the bean name is a contract to honor, `@Resource(name = "...")` directly expresses that intent.
