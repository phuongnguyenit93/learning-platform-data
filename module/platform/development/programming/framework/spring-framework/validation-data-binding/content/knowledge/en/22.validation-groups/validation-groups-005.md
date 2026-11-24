# Group Inheritance in Jakarta Bean Validation and Spring

## 1. Essence: A Child Group Includes the Constraints of Parent Groups

In Jakarta Bean Validation, a **validation group** is a Java interface used to select the set of constraints evaluated when calling `jakarta.validation.Validator.validate(...)` or at Spring integration points such as `@Validated(...)`. A constraint can belong to `Default` or to one or more application-defined groups.

**Group inheritance** means: if group interface `Child` **`extends Parent`**, requesting validation of the `Child` group causes the provider to also evaluate constraints belonging to `Parent`. A child group is a **superset** of its parent group; inheritance does not work in reverse.

```java
public interface BasicChecks {}
public interface BusinessChecks extends BasicChecks {}
```

With:

```java
@NotBlank(groups = BasicChecks.class)
private String name;

@Positive(groups = BusinessChecks.class)
private Integer quantity;
```

then:

- `validator.validate(bean, BasicChecks.class)` selects the constraint on `name`, and does **not** automatically include `BusinessChecks` constraints.
- `validator.validate(bean, BusinessChecks.class)` selects both `name` (inherited from `BasicChecks`) and `quantity` (declared directly in `BusinessChecks`).
- `validator.validate(bean)` selects `jakarta.validation.groups.Default` by default; it does not implicitly select `BasicChecks` or `BusinessChecks` if they are unrelated to `Default` via group relationships or other rules.

Group interfaces do not need methods, fields, or special annotations; **Java interface inheritance** is the exact syntax Jakarta Validation uses to express relationships between constraint sets.

> **Quick rule:** validating a child group = checking constraints of the child group itself **and** all parent groups (direct and indirect); validating a parent group does not automatically run constraints present only in child groups.

## 2. Distinguishing Groups, Constraints, and Validation Passes

| Concept | Purpose | Example |
| --- | --- | --- |
| Constraint | Describes a data rule | `@NotBlank`, `@Positive`, `@Email` |
| Group | Labels a set of constraints | `BasicChecks.class` |
| Group inheritance | Extends a constraint set via interface `extends` | `FullChecks extends BasicChecks` |
| Target group | The group the caller asks to validate | `validator.validate(bean, FullChecks.class)` |
| Default group | The group when an annotation or call omits groups | `jakarta.validation.groups.Default` |
| Group sequence | Defines **order** and stops at the first failing group | `@GroupSequence({Default.class, FullChecks.class})` |
| Cascaded validation | Validates child objects via `@Valid` | `@Valid Address address` |
| Group conversion | Switches groups when crossing a cascade edge | `@ConvertGroup(from=..., to=...)` |

A constraint annotation has a `groups` attribute of type `Class<?>[]`:

```java
@NotBlank(groups = BasicChecks.class)
private String username;

@NotNull(groups = {BasicChecks.class, CreateChecks.class})
private String email;
```

A constraint can belong to **multiple groups**. If multiple groups are requested together, the same constraint declaration must not be reported twice in a single validation pass; providers avoid duplicate evaluation of the same constraint/path per the specification contract.

**Having metadata does not mean validation has executed**: you must call `Validator.validate(...)`, Spring `SmartValidator`, or a configured MVC/service integration point. A group interface is not an object instantiated with `new`; it is group metadata selected by the provider at runtime.

## 3. Single Inheritance, Multiple-Group Inheritance, and Transitive Inheritance

### Single Parent

```java
public interface Basic {}
public interface Submit extends Basic {}
```

`Submit` includes constraints from both `Submit` and `Basic`.

### Multiple Parents

```java
public interface IdentityChecks {}
public interface PaymentChecks {}
public interface PurchaseChecks extends IdentityChecks, PaymentChecks {}
```

`PurchaseChecks` is the union of three groups: `IdentityChecks`, `PaymentChecks`, and `PurchaseChecks` itself. If a constraint declares `groups = {IdentityChecks.class, PaymentChecks.class}`, it can match via both branches, yet it must not be counted as two identical violations merely because there are two inheritance paths.

### Transitive Inheritance

```java
public interface Basic {}
public interface Shipping extends Basic {}
public interface Checkout extends Shipping {}
```

When validating `Checkout`, the provider applies constraints from `Checkout`, `Shipping`, and `Basic`. This is the **transitive relationship** of interface inheritance—there is no need to redeclare every ancestor group at the descendant level.

### A Visual Mental Model

```text
      Basic
        ^
        |
     Shipping        Payment
        ^               ^
        |               |
        +-------+-------+
                |
             Checkout

validate(Basic)     -> Basic
validate(Shipping)  -> Shipping + Basic
validate(Payment)   -> Payment
validate(Checkout)  -> Checkout + Shipping + Basic + Payment
```

In this diagram, arrows point toward the parent group; a lower group **includes** the constraints of the groups above it.

**Do not rely on the order of interfaces after `extends`**. `Checkout extends Shipping, Payment` only defines a set of groups; it does **not** mean `Shipping` constraints necessarily run before `Payment`. To enforce order, you need `@GroupSequence`.

## 4. Is `Default` Inherited Automatically?

**Not every group you define includes `Default`.** This is a very common misconception.

```java
public interface Advanced {}
```

`Advanced` does not extend `jakarta.validation.groups.Default`. If a DTO has:

```java
@NotBlank
private String title; // Default

@Positive(groups = Advanced.class)
private Integer number; // Advanced
```

then calling `validate(bean, Advanced.class)` does not automatically pick up the default constraint on `title` just because `Advanced` is named "advanced".

If you want a child group to **include `Default`**, declare it explicitly:

```java
import jakarta.validation.groups.Default;

public interface Basic {}
public interface Complete extends Default, Basic {}
```

When validating `Complete`, the provider selects constraints belonging to `Complete`, `Default`, and `Basic`. This is a simple way to express "check both default rules and specialized rules completely" **without** needing a group sequence.

Default rules to remember:

1. When a constraint omits the `groups` attribute, it belongs to `Default`.
2. When `validator.validate(object)` omits groups, the requested group is `Default`.
3. When passing `validator.validate(object, SomeGroup.class)`, only the requested groups and their parent/inherited groups are evaluated, subject to special rules if sequences or cascades apply.
4. A group `SomeGroup` does not automatically include `Default`, unless it **`extends Default`** or another declaration causes `Default` to be selected.

Do not confuse `@NotBlank(groups = Default.class)` with `@NotBlank`: in terms of group membership, they are equivalent per the standard. However, when a class redefines its default group sequence, validating the default group also follows that class's own rules, which is distinguished later.

## 5. Runnable Example: Verifying Group Inheritance with Java 17 and Spring Boot

The program below intentionally places **one invalid field constraint in each group** so the resulting sets are clear. It also illustrates `Default` included or excluded from child groups, and compares inheritance with `@GroupSequence`.

Uses Java 17+, Maven, and Spring Boot 3.5.8. Spring Boot with `spring-boot-starter-validation` configures a compatible Bean Validation provider so `jakarta.validation.Validator` can be injected from the Spring context. The `System.out.println` commands and outputs in the example do not depend on `Set<ConstraintViolation>` order because the code sorts property paths.

Structure:

```text
group-inheritance-demo/
├── pom.xml
└── src/main/java/demo/GroupInheritanceDemo.java
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.8</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>group-inheritance-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/java/demo/GroupInheritanceDemo.java`

```java
package demo;

import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.GroupSequence;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import jakarta.validation.groups.Default;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class GroupInheritanceDemo {

    // Ordinary groups.
    public interface Basic {}
    public interface Billing {}

    // Inherits both groups simultaneously.
    public interface Checkout extends Basic, Billing {}

    // Inherits Checkout and Default.
    public interface CompleteCheckout extends Checkout, Default {}

    // Dedicated sequence: differs from "extends".
    @GroupSequence({Default.class, Checkout.class})
    public interface OrderedChecks {}

    public static final class Order {
        @NotBlank
        private final String orderId; // Default

        @NotBlank(groups = Basic.class)
        private final String buyerId;

        @NotBlank(groups = Billing.class)
        private final String paymentToken;

        @Positive(groups = Checkout.class)
        private final Integer quantity;

        @Size(min = 3, groups = CompleteCheckout.class)
        private final String coupon;

        public Order(String orderId, String buyerId,
                     String paymentToken, Integer quantity,
                     String coupon) {
            this.orderId = orderId;
            this.buyerId = buyerId;
            this.paymentToken = paymentToken;
            this.quantity = quantity;
            this.coupon = coupon;
        }
    }

    public static void main(String[] args) {
        SpringApplication.run(GroupInheritanceDemo.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(Validator validator) {
        return args -> {
            Order allInvalid =
                    new Order("", "", "", 0, "X");

            show("Default", validator, allInvalid, Default.class);
            show("Basic", validator, allInvalid, Basic.class);
            show("Billing", validator, allInvalid, Billing.class);
            show("Checkout", validator, allInvalid, Checkout.class);
            show("CompleteCheckout", validator, allInvalid,
                    CompleteCheckout.class);

            show("Default + Checkout", validator, allInvalid,
                    Default.class, Checkout.class);

            // Default fails => subsequent group in sequence is skipped.
            show("Ordered", validator, allInvalid, OrderedChecks.class);

            // Default passes, so the sequence advances to Checkout.
            Order validDefault =
                    new Order("O-01", "", "", 0, "X");
            show("Ordered after Default passes",
                    validator, validDefault, OrderedChecks.class);
        };
    }

    static void show(String label, Validator validator,
                     Order order, Class<?>... groups) {

        Set<ConstraintViolation<Order>> violations =
                validator.validate(order, groups);

        String paths = violations.stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .collect(Collectors.joining(", "));

        System.out.println(label + " (" + violations.size() + "): "
                + (paths.isEmpty() ? "OK" : paths));
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Aside from standard Spring Boot startup logs, the lines printed by the program itself are:

```text
Default (1): orderId
Basic (1): buyerId
Billing (1): paymentToken
Checkout (3): buyerId, paymentToken, quantity
CompleteCheckout (5): buyerId, coupon, orderId, paymentToken, quantity
Default + Checkout (4): buyerId, orderId, paymentToken, quantity
Ordered (1): orderId
Ordered after Default passes (3): buyerId, paymentToken, quantity
```

### Line-by-Line Explanation of the Output

1. **Default (1):** `orderId=""` violates `@NotBlank` with no group declared, which belongs to `Default`. The `Default` group does not pull in specialized groups.
2. **Basic (1):** `buyerId=""` is the only constraint in `Basic`; `orderId` does not belong to `Basic`.
3. **Billing (1):** `paymentToken=""` belongs to `Billing`.
4. **Checkout (3):** `Checkout extends Basic, Billing`, so it selects `buyerId`, `paymentToken`, and `Checkout`'s own `quantity`. `orderId` is absent because `Checkout` **does not extend `Default`**.
5. **CompleteCheckout (5):** `CompleteCheckout extends Checkout, Default`, so it includes all three `Checkout` constraints, `Default`'s `orderId`, and `coupon` belonging solely to `CompleteCheckout`.
6. **Default + Checkout (4):** requesting both groups yields the union of `Default` and `Checkout` constraints; `coupon` (only in `CompleteCheckout`) is excluded. The order in which the two groups are listed in `validate` does not guarantee constraint execution order.
7. **Ordered (1):** `@GroupSequence({Default.class, Checkout.class})` runs `Checkout` only if `Default` has no violations. `orderId=""` stops the sequence.
8. **Ordered after Default passes (3):** `orderId="O-01"` passes `Default`; the sequence proceeds to `Checkout` and finds three violated constraints. `coupon` is still not checked because `CompleteCheckout` is not in the sequence.

In `Order`, the two empty `String` properties belong to `Basic`/`Billing`, `quantity = 0` fails `@Positive`, and `coupon="X"` fails `@Size(min=3)`. The violations belong to distinct properties and the code sorts paths, so stdout printed by the example has deterministic order. The example is written to run with Spring Boot 3.5.8 and Java 17; if adapting to plain Spring Framework, configure a Bean Validation provider / `LocalValidatorFactoryBean` accordingly.

**Takeaway from the demo:** group inheritance answers **"which rules should be checked?"**; a group sequence answers **"in what order should tiers of rules be checked?"**.

## 6. Group Inheritance Is Not JavaBean Class Inheritance

There are **two** inheritance concepts that are easily confused:

1. **Group inheritance:** a group interface `Child extends Parent`. When validating `Child`, constraints belonging to `Parent` are selected.
2. **Class/property constraint inheritance:** a Java class implements an interface with constraints or extends a superclass carrying constraints; constraints across the object type hierarchy may be evaluated by Bean Validation per the specification.

Group inheritance example:

```java
interface CommonChecks {}
interface AdminChecks extends CommonChecks {}
```

This is a relationship between **group-marker interfaces**, not the DTO's type hierarchy.

JavaBean inheritance example:

```java
class BaseProfile {
    @NotBlank
    protected String name;
}

class AdminProfile extends BaseProfile {
    @NotBlank(groups = AdminChecks.class)
    private String department;
}
```

When validating an `AdminProfile` with `Default`, the `name` constraint from the superclass is evaluated according to object constraint inheritance rules. When validating with `AdminChecks` without extending `Default`, the `name` constraint belonging solely to `Default` **is not automatically selected**, even though the field exists on the superclass.

When validating `AdminChecks`, if that group `extends CommonChecks`, then constraints in `CommonChecks` are also selected; that is a **group relationship** independent of JavaBean class inheritance. Do not infer from `class AdminProfile extends BaseProfile` that `AdminChecks` automatically inherits `Default` or any other group.

Changing constraints on **overridden getters** or **method parameter/return constraints** follows separate rules in Jakarta Validation to preserve method inheritance contracts; do not apply simple field-group rules blindly to all forms of method validation.

## 7. Implicit Grouping: An Interface with Constraints Also Represents a Group

Jakarta Validation has an **implicit grouping** mechanism in addition to explicit `groups = ...`. A constraint declared on an interface `Z` and belonging to the `Default` group (either by omitting `groups` or explicitly specifying `Default`) also belongs to **the group named after interface `Z` itself**.

Example:

```java
public interface NameView {
    @NotBlank
    String getDisplayName();
}

public class Person implements NameView {
    private final String displayName;

    public Person(String displayName) {
        this.displayName = displayName;
    }

    @Override
    public String getDisplayName() {
        return displayName;
    }
}
```

This is an **illustrative declaration snippet**; when placing into source files, split public types into matching files and import `@NotBlank`. With `Person("")`:

- `validator.validate(person)` sees `@NotBlank` on the interface getter because Bean Validation considers constraints from implemented interfaces.
- `validator.validate(person, NameView.class)` can also see that constraint thanks to implicit grouping, even though the getter annotation **does not write** `groups = NameView.class`.
- If interface `DetailedNameView extends NameView`, validating `DetailedNameView.class` can select `NameView`'s constraints via interface group inheritance.

**Do not conclude that any `class Person implements NameView` automatically gets a new group** just for any arbitrary interface. What matters is that **the constraint is declared on the interface** and belongs to `Default` on that interface; computing group Z per the spec creates the implicit group.

Implicit grouping is especially useful when an interface represents a data view or role and you want to validate that slice of state without annotating `groups` on every constraint.

## 8. Group Inheritance Differs from `@GroupSequence`

### Group Inheritance: Combines Conditions, Does Not Guarantee Order

```java
public interface Identity {}
public interface Payment {}
public interface Complete extends Identity, Payment {}
```

`validate(order, Complete.class)` requests constraints from `Identity`, `Payment`, and `Complete`. **There is no contract saying "Identity before Payment"**. If both fail, both can be reported in the same validation pass.

### Group Sequence: Defines Order, with Stop-on-Failure

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

public interface Payment {}

@GroupSequence({Default.class, Payment.class})
public interface OrderedPaymentChecks {}
```

When calling `validate(order, OrderedPaymentChecks.class)`:

1. Run `Default`.
2. If `Default` has at least one violation, **skip** `Payment`.
3. Only if `Default` passes, run `Payment`.

**Safety rules:**

- An interface annotated with `@GroupSequence` should **not simultaneously extend other groups**. The specification recommends that group sequence interfaces have no superinterfaces.
- Do not use a sequence interface directly in `groups = OrderedPaymentChecks.class` on a constraint; it represents an **execution sequence**, not a group assigned to constraints.
- Avoid circular references among sequences, including indirect cycles through group inheritance; when evaluated, this can throw `GroupDefinitionException`.
- If a constraint appears in multiple groups within a sequence, the provider avoids repeatedly evaluating the same constraint.
- Group inheritance is not a substitute for `@GroupSequence` and does not provide short-circuiting.

### Redefining `Default` at the Class Level Is Yet Another Mechanism

```java
@GroupSequence({Invoice.class, InvoiceExtraChecks.class})
public class Invoice {
    @NotNull
    private String number;

    public interface InvoiceExtraChecks {}
}
```

This is an **illustrative class**, requiring imports for `GroupSequence` and `NotNull`. When placing `@GroupSequence` on a **class** to redefine that class's `Default` group, the sequence must **contain `Invoice.class` itself**—**do not put `Default.class` in place of `Invoice.class`**; otherwise configuration can throw `GroupDefinitionException`. This class-level `Default` redefinition **does not automatically change the `Default` group for all nested objects**: each bean is validated according to its own group propagation/cascading rules.

Do not confuse these three mechanisms:

| Mechanism | Where is it written? | Effect |
| --- | --- | --- |
| `extends` | Group interface | Merges parent group's constraints into child group |
| `@GroupSequence` on interface | Standalone interface | Execution order and short-circuiting |
| `@GroupSequence` on class | JavaBean class | Redefines that class's own `Default` sequence |

## 9. Group Inheritance and Nested Objects with `@Valid`

A validation pass with a requested group can **cascade** into child objects:

```java
public class OrderForm {
    @NotBlank(groups = Basic.class)
    private String orderCode;

    @Valid
    private DeliveryAddress address;
}

public class DeliveryAddress {
    @NotBlank(groups = Basic.class)
    private String city;

    @NotBlank(groups = Billing.class)
    private String contactEmail;
}
```

These two classes are an **illustrative model**, requiring imports for `jakarta.validation.Valid`, `NotBlank`, and definitions of the group interfaces. Assuming `Checkout extends Basic, Billing`:

- When calling `validator.validate(order, Checkout.class)`, the `Basic` constraint on `orderCode` is selected.
- `@Valid` marks cascading; the provider proceeds to evaluate the `DeliveryAddress` object with the propagated groups per Jakarta Validation rules.
- Because `Checkout` includes `Basic` and `Billing`, both `city` and `contactEmail` can be evaluated on the child object.
- If `@Valid` is missing on `address`, the provider **does not automatically descend** into `DeliveryAddress` merely because `Checkout` inherits two groups.
- If `address == null`, cascading does not produce a required-address error; add `@NotNull` if presence is required.

A group only determines the **set of constraints**, while `@Valid` determines **traversal through the object graph**. For nested collections such as `List<@Valid DeliveryAddress>`, the provider needs a value extractor for the container; `List` is a standard supported container type.

### Switching Groups on Cascade: `@ConvertGroup`

Sometimes groups on parent and child carry different business meanings. In that case you can use:

```java
@Valid
@ConvertGroup(from = Checkout.class, to = Billing.class)
private DeliveryAddress address;
```

This is an **illustrative field**, requiring `import jakarta.validation.groups.ConvertGroup;`. When the group propagated to this cascade edge matches `Checkout` per the specification's group conversion rules, the child is validated under `Billing`; group inheritance declared on the child still applies to the effective converted group.

Note an advanced detail: Jakarta Validation expands **group sequences before applying group conversions**. The `from` rule matches the group at the cascade step after sequence expansion, not necessarily the exact initial group passed to `validate`. Do not assume conversion replaces an entire group tree or reapplies recursively multiple times; a conversion rule is applied once per cascade edge.

Do not attach `@ConvertGroup` without `@Valid` in the appropriate position; that is an invalid declaration. Only use group conversion when you have a reason to reuse an object graph without letting the parent's group propagate unchanged to the child.

## 10. Spring Framework: How Does `@Validated` Use Child Groups?

Spring Framework uses Jakarta Bean Validation via `LocalValidatorFactoryBean` (auto-configured in many Spring Boot apps that include a validation provider). Group interfaces remain **ordinary Java interfaces** and are passed directly to the provider.

### Using Jakarta `Validator` Directly

```java
Set<ConstraintViolation<OrderForm>> violations =
        validator.validate(order, Checkout.class);
```

This is an **illustrative snippet**, requiring `order` as `OrderForm`, `validator` as `jakarta.validation.Validator`, and corresponding imports. The provider expands `Checkout`'s parent groups automatically; Spring does not require registering each group interface as a separate bean.

### Spring `SmartValidator` and Validation Hints

```java
BindingResult errors =
        new BeanPropertyBindingResult(order, "order");

smartValidator.validate(order, errors, Checkout.class);
```

This snippet requires the corresponding variables and imports. `org.springframework.validation.SmartValidator` lets you pass validation hints, which `LocalValidatorFactoryBean`/adapters typically translate into Jakarta groups. `Errors`/`BindingResult` holds `FieldError`/`ObjectError` instances when constraints fail. When calling only `org.springframework.validation.Validator.validate(target, errors)` (the interface without hints), the mechanism normally uses `Default`.

### Spring MVC REST or Forms

In a Spring MVC controller:

```java
@PostMapping("/orders")
public ResponseEntity<?> createOrder(
        @Validated(Checkout.class)
        @RequestBody CreateOrderRequest request,
        BindingResult result) {

    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body(
                result.getFieldErrors().stream()
                        .map(e -> e.getField() + ": "
                                + e.getDefaultMessage())
                        .toList());
    }
    return ResponseEntity.ok().build();
}
```

This is an **illustrative method**, requiring the DTO, `Checkout` interface, and Spring/Jakarta imports. Spring MVC can use `@Validated(Checkout.class)` to request validating the object with `Checkout`; the provider expands parent groups via `extends`. `BindingResult` is placed immediately after the validated object in supported signatures.

If you replace `@Validated(Checkout.class)` with `@Valid`:

- `@Valid` normally requests validating the **`Default` group** (it does not implicitly pass `Checkout`).
- Constraints belonging only to `Basic`/`Billing`/`Checkout` may not run if `Default` does not include them through special configuration.
- Group inheritance does not replace **selecting the right group at the entry point**.

Do not confuse this with constraints placed directly on handler method parameters such as `@Min`/`@NotBlank`: in newer Spring MVC versions, method validation has its own mechanism and can produce a different exception type than DTO validation. Using `@Validated` at parameter level vs. class level must follow the rules of your Spring version.

### Spring Service Method Validation

```java
@Service
@Validated(Checkout.class)
public class OrderService {
    public void submit(@Valid OrderForm form) {
        // ...
    }
}
```

This is an **illustrative class**, requiring Spring/Jakarta imports. When the bean is managed by Spring and the method-validation interceptor is actually active, the `Checkout` group on `@Validated` can be applied to the corresponding method validation/cascade pass. **Do not** assume this annotation runs when calling `new OrderService()` manually or when self-invocation bypasses the AOP proxy. Verify `MethodValidationPostProcessor`/Spring Boot configuration and test with a Spring-managed bean.

Another common pitfall: `@Validated` on an MVC controller class may engage legacy AOP method validation, whereas modern Spring MVC has its own built-in mechanism. Do not add class-level `@Validated` to every controller if you only need to bind/validate DTOs with parameter-level groups.

## 11. Real-World Scenario: Create, Update, Checkout

Suppose there are three stages:

- **Basic:** verifies the user has an identifier/cart.
- **Billing:** verifies payment information.
- **Checkout:** requires both `Basic` and `Billing`, plus checkout-specific conditions.
- **FullSubmission:** adds application-wide `Default` constraints.

Definition:

```java
public interface Basic {}
public interface Billing {}
public interface Checkout extends Basic, Billing {}
public interface FullSubmission extends Checkout, Default {}
```

The application can use:

```java
validator.validate(order, Basic.class);          // Basic only
validator.validate(order, Billing.class);        // Billing only
validator.validate(order, Checkout.class);       // Basic + Billing + Checkout
validator.validate(order, FullSubmission.class); // Includes Default
```

**Technical choices:**

- If the requirement is *validate all groups* and return errors in one pass, group inheritance fits well.
- If the requirement is *validate basic fields first and only run expensive checks after the first step passes*, use a group sequence.
- If the requirement is *switch groups when validating a child object* because the child uses distinct groups, use `@ConvertGroup` on the cascade edge.
- If there are only a few create/update cases, sometimes two groups `OnCreate`/`OnUpdate` with a `Common` parent group are enough; avoid creating an unnecessarily complex interface tree.

Note: **do not put expensive DB lookups directly into every custom `ConstraintValidator`** without considering purpose, caching, I/O, transactions, and performance. Group inheritance does not guarantee order or skip expensive constraints when other constraints fail; a group sequence provides group-level short-circuiting.

## 12. Common Mistakes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `validate(bean, Checkout.class)` skips `@NotBlank` with no `groups` | `Checkout` does not extend `Default` | Use `Checkout extends Default, ...` if `Default` should be included |
| Validating `Basic` misses `Billing` constraints | `Basic` does not extend `Billing` | Request `Checkout` or `Billing`; inheritance is one-way |
| Child group runs, but not in the expected order | `extends` specifies a set, not execution order | Use `@GroupSequence` |
| `@Validated(Checkout.class)` has no effect in a unit test calling `new Controller()` | Does not go through Spring MVC/proxy/validator | Test through the real infrastructure or call `Validator` directly |
| Annotations on child object do not run | Missing `@Valid` | Add the cascade marker on the right path |
| Child group is not applied to nested object as expected | Group conversion or `Default` redefinition is active | Inspect `@ConvertGroup`, sequences, and group propagation |
| `@NotBlank(groups=OnCreate.class)` is skipped when calling `validate(bean)` | Defaults to `Default` only | Pass `OnCreate` or design a child group extending `Default` appropriately |
| One constraint for two groups written twice in source code | Unnecessary duplicate annotation | Use `groups = {A.class, B.class}` or a common parent group |
| `GroupDefinitionException` when running a sequence | Cycle in inheritance/sequence or invalid default redefinition | Break cycles; ensure class `@GroupSequence` includes the class itself |
| Confusing `javax.validation.*` with `jakarta.validation.*` | Dependencies from two different generations | For Spring Framework 6+/Boot 3+, standardize on the Jakarta namespace |
| Service has `@Validated` but internal call is not intercepted | Self-invocation bypasses the proxy | Use a separate boundary bean or explicit validation |
| Relying on violation order in a `Set` | API does not guarantee order | Assert on sets of property paths or sort before printing |

**Distinguish group inheritance from class inheritance** before changing code: if a bean inherits field constraints from a superclass but you invoke the wrong group, the bug is in **group selection**, not in the provider failing to read the superclass.

## 13. Testing Group Inheritance Properly

To avoid misunderstanding the logic, create a bean where each group has **one distinct failing field**, then inspect the set of violating paths:

1. `validate(bean, Basic.class)`: only `Basic` fields.
2. `validate(bean, Billing.class)`: only `Billing` fields.
3. `validate(bean, Checkout.class)`: `Basic`, `Billing`, and `Checkout` fields.
4. `validate(bean, Default.class)`: only `Default` fields (unless the class has a default-group redefinition or other rules).
5. `validate(bean, CompleteCheckout.class)`: adds `Default` and constraints belonging only to `CompleteCheckout`.
6. `validate(bean, Default.class, Checkout.class)`: combines group sets, without relying on order.
7. `validate(bean, OrderedChecks.class)`: verifies that if `Default` fails, `Checkout` does not run.
8. `@Validated(Checkout.class)` in Spring MVC: send requests and check field errors belonging to parent groups.
9. Nested `@Valid`: test child object present/absent and group propagation across the cascade.
10. Group conversion: explicitly test which group child properties run under after conversion, especially alongside sequences.

JUnit 5 test example (this is an **illustrative method** using `Order` and `Validator` declared in the main example):

```java
@Test
void checkoutInheritsBothParentGroups() {
    Order order = new Order("", "", "", 0, "X");

    Set<String> paths = validator.validate(order, Checkout.class)
            .stream()
            .map(v -> v.getPropertyPath().toString())
            .collect(Collectors.toSet());

    assertEquals(Set.of("buyerId", "paymentToken", "quantity"),
                 paths);
}
```

Requires `org.junit.jupiter.api.Test`, `Assertions.assertEquals` (static import), `java.util.Set`, and `Collectors`; `validator` should be injected from the Spring context or obtained from a compatible provider. This tests **group inheritance**, not MVC integration. For MVC testing, use `MockMvc` to ensure the controller actually requests the intended group.

**Do not assert `ConstraintViolation` ordering**: `Validator.validate(...)` returns a `Set`, not a list with a guaranteed order. Check by property paths, constraint descriptors, or expected sets rather than taking the first element.

## 14. Advanced Cases to Keep in Mind

### Interface Extending `Default` and Class-Level Group Sequence

For example, `Complete extends Default` only **expands the constraint set**; it does not redefine `Default` for a JavaBean. If a class has `@GroupSequence`, applying `Default` when validating that class follows its own sequence; do not treat "child group extends Default" as altering the validation lifecycle of every object.

### A Group Interface Can Be a Role Contract

An interface can both declare constrained getters and act as an implicit group. Extending this interface in another group can include constraints not only from explicit `groups=...` attributes, but also from the implicit group. When results contain more constraints than expected, inspect **constraints on interface getters** and metadata via `validator.getConstraintsForClass(...)`.

### Group Sequences and Dependency Cycles

A sequence can contain a group that is already inherited by another group; that does not mean every combination is valid. The specification forbids direct or indirect cycles among group sequences, including cycles through inheritance. When encountering `GroupDefinitionException`, inspect the full group/sequence dependency graph, not just the single annotation where the exception surfaces.

### Group Conversion Across Nested Collections

With `List<@Valid Address>` or `Map<Key, @Valid Value>`, group propagation/cascading applies through value extractors. `@ConvertGroup` on container elements is supported at valid positions; misplacing `@Valid`/`@ConvertGroup` can throw `ConstraintDeclarationException`. Use clear type-use annotations and test violation paths on nested objects.

### Method Validation and Method Inheritance

Adding parameter constraints on an overriding method can violate Bean Validation's Liskov substitution rules, even if the class uses valid group inheritance. Rules for overriding methods differ from group interface `extends`. If you encounter `ConstraintDeclarationException` on a service interface/implementation, check the **Method constraints in inheritance hierarchies** specification section before changing groups.

## 15. Self-Check Questions

**1. Given `interface Advanced extends Basic {}`, does calling `validate(bean, Advanced.class)` select `Basic` constraints?**  
Yes. `Advanced` inherits all constraints belonging to `Basic` and `Basic`'s parent groups.

**2. Does calling `validate(bean, Basic.class)` automatically run constraints belonging only to `Advanced`?**  
No. The inheritance relationship is one-way from child group to parent group.

**3. Does `interface CreateChecks {}` automatically include `@NotBlank` constraints with no `groups` specified?**  
No; those constraints belong to `Default`. To include `Default`, design explicit group inheritance or request both groups.

**4. Is `interface CreateChecks extends Default {}` identical to `@GroupSequence({Default.class, CreateChecks.class})`?**  
No. `extends Default` selects a constraint set; `@GroupSequence` establishes execution order and stops when an earlier group has violations.

**5. Can a group inherit from multiple groups?**  
Yes: `interface Checkout extends Identity, Billing {}`, using standard Java interface multiple inheritance.

**6. Does group inheritance make Bean Validation automatically traverse into child objects?**  
No. Traversing the object graph requires `@Valid`; groups only decide which constraints are selected on objects included in the validation pass.

**7. With `@Validated(Checkout.class)` on a Spring MVC argument, does Spring require registering each group interface as a bean?**  
No. Jakarta Bean Validation uses interface class metadata; Spring passes the requested group to the provider. However, a validation provider and active MVC integration are required.

**8. If you instantiate a class with `new` and call setters, do parent-group constraints run immediately?**  
No. A `validate` call or an appropriately configured framework entry point is required.

**9. If group `Checkout` `extends Default`, does that mean validating `Default` always checks constraints belonging only to `Checkout`?**  
No. Validating `Default` goes the other way: it only runs constraints belonging to `Default` per the applicable group/default-sequence rules.

**10. Why should tests assert sets of property paths rather than violation order?**  
Evaluation and iteration order of group constraints/violations is not guaranteed; `Set` has no ordering contract to rely on.

## 16. Summary

Group inheritance is a model for **reusing constraint sets via interface inheritance**: a child group includes its parent groups, supports multiple and transitive inheritance, yet **does not define execution order**. `Default` is included only when explicitly selected (such as `Child extends Default`); `@GroupSequence` is a separate mechanism for ordering and short-circuiting. In Spring, `@Validated(Group.class)` or `SmartValidator` specifies the group that the provider expands, while `@Valid` controls cascading through the object graph.

Always ask yourself: **"Am I selecting a set of constraints, defining evaluation order, or switching groups on cascade?"** Those three goals correspond to **`extends`, `@GroupSequence`, and `@ConvertGroup`**.

## Official References

- Jakarta Validation 3.1 — Section `5.4.1 Group inheritance`: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation 3.1 — `5.4.2 Group sequence`, `5.4.3 Redefining Default`, `5.4.4 Implicit grouping`: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation 3.1 — `5.4.5 Group conversion` and `5.4.6 Formal group definitions`: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation API — `jakarta.validation.groups` package and `Default`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/groups/package-summary.html
- Jakarta Validation API — `Validator`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/Validator.html
- Hibernate Validator Reference Guide — Chapter 5 Grouping constraints: https://docs.jboss.org/hibernate/validator/9.0/reference/en-US/html_single/#chapter-groups
- Spring Framework Reference — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Framework API — `@Validated`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/annotation/Validated.html
- Spring Framework API — `SmartValidator`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/SmartValidator.html
- Spring Framework Reference — MVC Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
