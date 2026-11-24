# `@ConvertGroup` During Cascaded Validation in Jakarta Bean Validation and Spring Framework

## 1. The Problem: Parent and Child Beans Do Not Always Share the Same Group

In a Spring system, an `OrderRequest` class may contain an `Address` or `Customer`. When submitting an order creation request, you want to validate one group of constraints on the **parent object**, while the child object may be a reusable component with its own set of groups. If you only propagate a single group throughout the entire object graph, required constraints on the child bean might be skipped.

Example requirement:

- `OrderRequest` is validated under the default `Default` group when the client submits it.
- `OrderRequest.orderCode` has `@NotBlank` in the `Default` group.
- `Address.city` has `@NotBlank` in the `Default` group, used only for ordinary checks.
- `Address.street` has `@NotBlank(groups = DeliveryChecks.class)`, meant for delivery.
- When validating `OrderRequest`, you want to **keep `Default` on the parent**, yet **use `DeliveryChecks` on `Address`**.

The proper Jakarta Bean Validation solution is **`@Valid` combined with `@ConvertGroup` at the cascade point**:

```java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

class OrderRequest {
    @NotBlank
    private String orderCode;

    @Valid
    @ConvertGroup(from = Default.class, to = DeliveryChecks.class)
    private Address shippingAddress;
}
```

This is an illustrative snippet in a project declaring `Address`, `DeliveryChecks`, and importing `@NotBlank`. When calling `validator.validate(order)`, the root bean still evaluates constraints in `Default`; **only when traversing `shippingAddress`** is the group converted to `DeliveryChecks` and applied to the `Address` bean. The group is not changed globally.

**Early takeaway:** `@Valid` decides **whether to descend into the related object**; `@ConvertGroup` decides **which group to use when crossing that edge**. Without cascade, there is no group conversion.

This article uses the **`jakarta.validation.*`** namespace from Jakarta Validation 3.x, matching Spring Framework 6 / Spring Boot 3. Examples use Java 17+. Avoid mixing `javax.validation.*` from legacy stacks with modern Jakarta APIs/providers.

## 2. Reviewing Groups and `@Valid` Before Converting Groups

A **validation group** is a marker interface used to categorize constraints:

```java
public interface DeliveryChecks {}
public interface BillingChecks {}
```

Assigning a group to a constraint:

```java
class Address {
    @NotBlank
    String city; // Default if groups is omitted.

    @NotBlank(groups = DeliveryChecks.class)
    String street;
}
```

To validate a bean, `jakarta.validation.Validator` accepts groups via varargs:

```java
validator.validate(address);                       // Default
validator.validate(address, Default.class);        // Explicit Default
validator.validate(address, DeliveryChecks.class); // DeliveryChecks
```

When no group is passed, Jakarta Validation uses `jakarta.validation.groups.Default`. When only `DeliveryChecks.class` is passed, do not assume constraints belonging only to `Default` will also run, unless group inheritance, sequences, or related metadata cause them to be selected.

### 2.1. Cascading Without Group Conversion

If the parent object has a property:

```java
@Valid
private Address shippingAddress;
```

then when calling `validator.validate(parent, Default.class)`, Bean Validation validates constraints on the parent under `Default`, then **propagates `Default`** to `shippingAddress`. `Address.city` is checked, while `Address.street` (belonging only to `DeliveryChecks`) does not run automatically.

If `shippingAddress == null`, `@Valid` does not produce an error for null; it does not cascade into a non-existent object. When the child object is required, also place `@NotNull` on the property itself in the appropriate group.

### 2.2. With `@ConvertGroup` at the Cascade Edge

If you change it to:

```java
@Valid
@ConvertGroup(from = Default.class, to = DeliveryChecks.class)
private Address shippingAddress;
```

then the `Default` group leaving the parent **is mapped to `DeliveryChecks` on this edge**. `Address.street` is checked; constraints belonging solely to `Default` such as `Address.city` do not automatically run during that cascade pass.

Comparison table with `Address(city="", street="")`:

| Call from root | Relationship configuration | Group actually reaching `Address` | Selected child constraint |
| --- | --- | --- | --- |
| `validate(root)` | `@Valid` | `Default` | `city` |
| `validate(root)` | `@Valid @ConvertGroup(Default → DeliveryChecks)` | `DeliveryChecks` | `street` |
| `validate(root, DeliveryChecks.class)` | `@Valid` only | `DeliveryChecks` | `street` |
| `validate(root, DeliveryChecks.class)` | Convert **only** from `Default` | `DeliveryChecks` unchanged | `street` |
| `validate(root, BillingChecks.class)` | Convert **only** from `Default` | `BillingChecks` unchanged | Rules in `BillingChecks` if any |

The trigger for group conversion is **matching the `from` value of the group crossing the cascade point**. If no rule matches, the group propagates unchanged.

## 3. Exact Syntax and Contract of `@ConvertGroup`

The annotation belongs to the package:

```java
import jakarta.validation.groups.ConvertGroup;
```

General syntax:

```java
@Valid
@ConvertGroup(from = SourceGroup.class, to = TargetGroup.class)
private RelatedBean related;
```

Components:

| Component | Meaning |
| --- | --- |
| `@Valid` | Marks cascading into the child bean |
| `@ConvertGroup` | Rule for switching groups at that exact cascade point |
| `from` | Incoming group to map; defaults to `Default.class` if omitted |
| `to` | Group forwarded to the child bean; required |
| `@ConvertGroup.List` | Container annotation for multiple conversion rules at the same point; repeatable when supported by Java/provider |
| `Default.class` | Marker interface `jakarta.validation.groups.Default`, not "all groups" |

Shorthand when the source group is `Default`:

```java
@Valid
@ConvertGroup(to = DeliveryChecks.class)
private Address shippingAddress;
```

Equivalent in source group to `from = Default.class`. This is the **default for the `from` attribute alone**; it does not mean `to` is automatically chosen.

### 3.1. Mandatory Conditions and Declaration Errors

- `@ConvertGroup` is valid only where **`@Valid` is present on that exact element/cascade path**. Using `@ConvertGroup` alone without `@Valid` is an invalid declaration; the provider can throw `ConstraintDeclarationException` when reading metadata or executing validation.
- You must not declare **two rules with the same `from` value on the same cascade point**. For example, having both `Default → A` and `Default → B` at the same spot is ambiguous and leads to `ConstraintDeclarationException`.
- `from` **must not be an interface defined as a group sequence**. `to` **can** be a valid group sequence.
- Do not place `@ConvertGroup` at an arbitrary spot in the project expecting it to convert groups for every association. **The annotation's location defines its exact scope.**
- On hierarchies with inheritance or overridden methods, Jakarta Validation imposes specific restrictions on adding group conversions to parameters/return values to preserve inheritance contracts. Do not alter method declarations without testing metadata validation.

**Invalid example:**

```java
// Wrong: missing @Valid at the same point.
@ConvertGroup(from = Default.class, to = DeliveryChecks.class)
Address shippingAddress;
```

**Valid example:**

```java
@Valid
@ConvertGroup(from = Default.class, to = DeliveryChecks.class)
Address shippingAddress;
```

`@ConvertGroup` **is not a constraint** like `@NotBlank`: it does not evaluate whether a value is valid by itself, but only changes **which group is requested** during an existing cascade.

### 3.2. Multiple Source Groups on One Edge

You can declare different conversions for different incoming groups:

```java
@Valid
@ConvertGroup(from = Default.class, to = DeliveryChecks.class)
@ConvertGroup(from = StrictOrder.class, to = StrictAddress.class)
Address shippingAddress;
```

Each rule has a **different `from` source**. When `Default` crosses, the first rule applies; when `StrictOrder` crosses, the second rule applies; when any other group crosses, it passes through unchanged. You must not map the same source to two different targets.

Container form:

```java
@Valid
@ConvertGroup.List({
    @ConvertGroup(from = Default.class, to = DeliveryChecks.class),
    @ConvertGroup(from = StrictOrder.class, to = StrictAddress.class)
})
Address shippingAddress;
```

These examples require `StrictOrder`, `StrictAddress`, and `Address` to be defined in the project. Do not pile up groups just because you can; mappings should reflect the actual parent–child business relationship.

## 4. Application Order: Only One Conversion per Edge

A common question: if a property has both `A → B` and `B → C`, when entering with `A`, does it automatically chain onward to `C`? **No.**

Example:

```java
@Valid
@ConvertGroup(from = A.class, to = B.class)
@ConvertGroup(from = B.class, to = C.class)
RelatedBean child;
```

If the group entering the edge is `A`, the converted result for **that edge** is `B`, not `C`. Conversion **does not loop until no rules match**; the matching rule is applied once at the cascade point. When the incoming group is `B`, it converts to `C`.

This is not a "last group wins" rule and does not depend on annotation order. Converting only once prevents rules on the same edge from unintentionally altering group contracts multiple times.

### 4.1. However, Chaining Can Happen Across Deeper Edges

A different scenario:

```text
Order --(@Valid, Default → DeliveryChecks)--> Address
      Address --(@Valid, DeliveryChecks → WarehouseChecks)--> Warehouse
```

When validating `Order` with `Default`:

1. Constraints on `Order` are checked under `Default`.
2. Crossing `Order.address`, the group switches to `DeliveryChecks`.
3. Constraints on `Address` are checked under `DeliveryChecks`.
4. Crossing **another cascade edge**, `Address.warehouse`, `DeliveryChecks` switches again to `WarehouseChecks`.
5. Constraints on `Warehouse` are checked under `WarehouseChecks`.

This **does not contradict** the "non-recursive" rule: each edge performs exactly one conversion, yet an object graph can have multiple edges, each applying its own rule.

**Distinction:** chaining `A → B → C` on **the same edge** does not cascade sequentially; `A → B` on a parent–child edge followed by `B → C` on a **child–grandchild edge** is a valid cascade chain.

### 4.2. The Group Is Not Changed at the Root

A `@ConvertGroup` annotation on `address` **does not turn the entire call** `validator.validate(order)` into `validator.validate(order, DeliveryChecks.class)`. The root still receives `Default`, and other properties on the root are unaffected. The group changes only when crossing the cascade edge bearing that declaration.

Do not use `@ConvertGroup` as a way to "globally override" groups in Spring. To choose the root group, pass it directly to `Validator` or use `@Validated(Group.class)` where Spring supports it.

## 5. Standalone Runnable Java 17+ Example: Comparing With and Without Conversion

This section uses Jakarta Validation 3.x and Hibernate Validator 8.x as the provider. The program needs no Spring MVC to demonstrate the standard mechanism, featuring these classes:

- `Warehouse`: `label` in `Default` and `code` in `WarehouseChecks`.
- `Address`: `city` in `Default`, `street` in `DeliveryChecks`, and a `warehouse` relation converting `DeliveryChecks → WarehouseChecks`.
- `PlainOrder`: only `@Valid` on `address`.
- `ConvertedOrder`: `@Valid @ConvertGroup(Default → DeliveryChecks)` on `address`.

The output shows that constraints at **two nested child levels** are selected according to the groups crossing the edges.

### 5.1. Create `pom.xml`

Create `pom.xml` in your working directory:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>convert-group-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.1.Final</version>
        </dependency>
    </dependencies>
</project>
```

The `hibernate-validator` dependency brings in the Jakarta Validation API and transitive dependencies. To run from the CLI without installing Jakarta Expression Language, the example uses Hibernate Validator's `ParameterMessageInterpolator`. That is a **provider-specific API**; applications needing EL support in message templates must configure EL appropriately.

### 5.2. File `ConvertGroupDemo.java`

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

import org.hibernate.validator.HibernateValidator;
import org.hibernate.validator.messageinterpolation.ParameterMessageInterpolator;

import java.util.List;
import java.util.Set;

public class ConvertGroupDemo {

    public interface DeliveryChecks {}
    public interface WarehouseChecks {}

    public static final class Warehouse {
        @NotBlank
        private final String label;

        @NotBlank(groups = WarehouseChecks.class)
        private final String code;

        public Warehouse(String label, String code) {
            this.label = label;
            this.code = code;
        }
    }

    public static final class Address {
        @NotBlank
        private final String city;

        @NotBlank(groups = DeliveryChecks.class)
        private final String street;

        @Valid
        @ConvertGroup(
                from = DeliveryChecks.class,
                to = WarehouseChecks.class)
        private final Warehouse warehouse;

        public Address(String city, String street, Warehouse warehouse) {
            this.city = city;
            this.street = street;
            this.warehouse = warehouse;
        }
    }

    public static final class PlainOrder {
        @NotBlank
        private final String orderCode;

        @Valid
        private final Address address;

        public PlainOrder(String orderCode, Address address) {
            this.orderCode = orderCode;
            this.address = address;
        }
    }

    public static final class ConvertedOrder {
        @NotBlank
        private final String orderCode;

        @NotNull
        @Valid
        @ConvertGroup(
                from = Default.class,
                to = DeliveryChecks.class)
        private final Address address;

        public ConvertedOrder(String orderCode, Address address) {
            this.orderCode = orderCode;
            this.address = address;
        }
    }

    private static void print(
            String name, Set<? extends ConstraintViolation<?>> errors) {
        List<String> paths = errors.stream()
                .map(v -> v.getPropertyPath().toString())
                .sorted()
                .toList();
        System.out.println(name + " -> " + paths);
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory = Validation
                .byProvider(HibernateValidator.class)
                .configure()
                .messageInterpolator(new ParameterMessageInterpolator())
                .buildValidatorFactory()) {

            Validator validator = factory.getValidator();

            Address badAddress = new Address(
                    "", "", new Warehouse("", ""));

            PlainOrder plain = new PlainOrder("", badAddress);
            ConvertedOrder converted =
                    new ConvertedOrder("", badAddress);

            print("plain Default", validator.validate(plain));
            print("converted Default", validator.validate(converted));
            print("converted DeliveryChecks",
                    validator.validate(converted, DeliveryChecks.class));

            print("converted property address",
                    validator.validateProperty(converted, "address"));
            print("converted candidate address",
                    validator.validateValue(
                            ConvertedOrder.class, "address", badAddress));

            ConvertedOrder missing =
                    new ConvertedOrder("ORD-1", null);
            print("converted null address",
                    validator.validate(missing));

            ConvertedOrder valid = new ConvertedOrder(
                    "ORD-2",
                    new Address("Hanoi", "1 Main St",
                            new Warehouse("Main", "WH-001")));
            print("converted valid", validator.validate(valid));
        }
    }
}
```

The program prints only sorted violation paths, avoiding locale-translated messages. That keeps results independent of `Set<ConstraintViolation<?>>` iteration order or provider language.

### 5.3. Run Commands

Requires **JDK 17+** and **Maven**. Place `pom.xml` and `ConvertGroupDemo.java` in the same directory.

Bash (Linux/macOS):

```bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
CP="$(cat classpath.txt)"
javac -encoding UTF-8 -cp "$CP" ConvertGroupDemo.java
java -cp ".:$CP" ConvertGroupDemo
```

PowerShell (Windows):

```powershell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
$cp = (Get-Content -Raw classpath.txt).Trim()
javac -encoding UTF-8 -cp $cp ConvertGroupDemo.java
java -cp ".;$cp" ConvertGroupDemo
```

**Expected stdout** when running with the stated dependencies (ignoring provider startup logs if any):

```text
plain Default -> [address.city, address.warehouse.label, orderCode]
converted Default -> [address.street, address.warehouse.code, orderCode]
converted DeliveryChecks -> [address.street, address.warehouse.code]
converted property address -> []
converted candidate address -> []
converted null address -> [address]
converted valid -> []
```

### 5.4. Exact Line-by-Line Explanation

1. **`plain Default`:** root `orderCode=""` fails `@NotBlank`. Since `PlainOrder.address` has only `@Valid`, `Default` descends into `Address`, so `city=""` fails. Continuing down to `Warehouse`, the conversion rule on `Address.warehouse` only matches `DeliveryChecks`, so `Default` stays unchanged and `Warehouse.label=""` fails. Three paths total.
2. **`converted Default`:** root `orderCode=""` still fails `@NotBlank`. Across `ConvertedOrder.address`, `Default` converts to `DeliveryChecks`, so `Address.street=""` fails, while `city` (only in `Default`) does not run on this branch. At `Address.warehouse`, `DeliveryChecks` converts to `WarehouseChecks`, so `Warehouse.code=""` fails. Three paths total, yet **the two child-bean paths are completely different**.
3. **`converted DeliveryChecks`:** root `orderCode` (only in `Default`) does not run. The conversion on the root edge only maps `Default → DeliveryChecks`, so the incoming `DeliveryChecks` group remains unchanged; `Address.street` is checked. The next edge switches `DeliveryChecks` to `WarehouseChecks` and checks `Warehouse.code`.
4. **`converted property address`:** `validateProperty` checks only constraints directly on the `address` property, where `@NotNull` passes because `address` is non-null. It **does not cascade**, so it does not see errors on `street` or `Warehouse.code`.
5. **`converted candidate address`:** `validateValue` likewise **does not cascade**, checking only that the candidate is non-null per `@NotNull`; returns an empty set.
6. **`converted null address`:** `@NotNull` on `address` (in `Default`) detects `null`. `@Valid` skips `null`; conversion cannot materialize a child object.
7. **`converted valid`:** root is non-blank, address has a valid street under `DeliveryChecks`, and warehouse has a valid code under `WarehouseChecks`. No violations along this path.

Key takeaway: **`@ConvertGroup` changes the group during cascade**, does not change the group at the root, does not run nested validation on property/value APIs, and does not replace `@NotNull`.

## 6. `@ConvertGroup` and `@Validated` in Spring MVC

Spring supports both mechanisms, each with a distinct responsibility:

- Spring's `@Validated(Group.class)` selects **which group starts validation** for an input object in supported controller/service contexts.
- Jakarta's `@Valid` triggers validation on the object and **cascades** into child beans wherever attached.
- Jakarta's `@ConvertGroup` controls **group switching when cascading through a specific property or type argument**.
- `jakarta.validation.Validator.validate(bean, groups...)` lets you invoke validation directly with the same group/cascade behavior without an HTTP request.

### 6.1. Illustrative Spring MVC DTO

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;

public class OrderInput {
    @NotBlank
    private String code;

    @NotNull
    @Valid
    @ConvertGroup(from = Default.class, to = DeliveryChecks.class)
    private DeliveryAddress address;

    public String getCode() { return code; }
    public void setCode(String code) { this.code = code; }

    public DeliveryAddress getAddress() { return address; }
    public void setAddress(DeliveryAddress address) {
        this.address = address;
    }
}

interface DeliveryChecks {}

class DeliveryAddress {
    @NotBlank(groups = DeliveryChecks.class)
    private String street;

    public String getStreet() { return street; }
    public void setStreet(String street) { this.street = street; }
}
```

This is **illustrative integration code**; in a real application place types in appropriate files/packages with Jackson/binding dependencies and a Bean Validation provider. To avoid name collisions, `DeliveryChecks` in the MVC snippet is an interface of that separate project, not a class inside the standalone `ConvertGroupDemo` program in section 5.

With JSON:

```json
{
  "code": "ORD-1",
  "address": {
    "street": ""
  }
}
```

`@NotBlank` on `DeliveryAddress.street` in `DeliveryChecks` will be evaluated when root `OrderInput` is validated under `Default`, thanks to `@Valid + @ConvertGroup` on `address`.

### 6.2. Controller Selecting the Initial Group

```java
@PostMapping("/orders")
public ResponseEntity<?> create(
        @Valid @RequestBody OrderInput input,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body(
                errors.getFieldErrors().stream()
                        .map(e -> e.getField() + ":" + e.getCode())
                        .toList());
    }

    return ResponseEntity.ok().build();
}
```

This is an illustrative method inside a `@RestController`, requiring Spring MVC/`ResponseEntity`/`BindingResult` imports and the corresponding model. When input object validation runs with the default group, the conversion on `address` selects `DeliveryChecks` for the child bean. `BindingResult` sits immediately after the corresponding parameter in supported Spring signatures to capture errors.

If a different initial group is needed:

```java
@Validated(Create.class) @RequestBody OrderInput input
```

then **the root receives `Create`**, not `Default`. With `@ConvertGroup(from=Default.class, to=DeliveryChecks.class)`, no conversion occurs **if the traversing group is `Create`**. You can:

- Define `@ConvertGroup(from = Create.class, to = DeliveryChecks.class)` at that exact cascade point;
- Or request both needed groups via `@Validated({Default.class, Create.class})` if the contract calls for it, while understanding the impact of each group;
- Or design separate DTOs to avoid complexity.

Do not conclude "having `@ConvertGroup` turns every incoming group into `DeliveryChecks`". **Only a matching `from` converts the group.**

### 6.3. When Placing `@Validated` on a Service

A Spring service can use `@Validated` at class level to enable **proxy-based method validation** when a provider and `MethodValidationPostProcessor` are configured. This selects groups or enables method validation; it is not a replacement for `@ConvertGroup` inside an object graph.

Illustrative example:

```java
@Service
@Validated
public class OrderService {
    public void submit(@Valid OrderInput input) {
        // Business logic runs only after validation if interceptor is active.
    }
}
```

Whether this method is actually validated depends on the bean being Spring-managed, method validation infrastructure, and calls passing through the proxy. **Self-invocation** like `this.submit(input)` can bypass the proxy. In Spring MVC 6.1+, controllers also have built-in method validation; avoid placing `@Validated` arbitrarily on controller classes if you want the built-in path. Always test behavior on your actual Spring version.

### 6.4. Binding Errors Are Not Group Conversion Errors

Malformed JSON, unparseable numbers/enums, or binder failures when constructing child beans fail at the **HTTP conversion/binding layer** before or outside Bean Validation. `@ConvertGroup` is not responsible for type conversion or instantiating nested objects.

For example, JSON `{"address": null}`: if the DTO has `@NotNull`, it reports a nullability error; `@ConvertGroup` does not fabricate a `DeliveryAddress` to check `street`. With `{"address": {}}`, the DTO has a non-null `address` with `street=null`, so `@NotBlank(groups=DeliveryChecks.class)` can report a violation along the cascade path.

In production, distinguish JSON parse errors, binding errors, field violations, object-level violations, and invalid business state to return proper responses.

## 7. `@ConvertGroup` with `List`, `Set`, `Map`, and Container Elements

Since Jakarta Bean Validation 2.0, container element constraints and cascades can be placed on **type arguments**. `@ConvertGroup` supports `TYPE_USE` and can accompany `@Valid` on the element position to cascade.

### 7.1. List of Child Beans

Suppose an order has a list of delivery addresses:

```java
class BatchOrder {
    @NotEmpty
    List<
        @NotNull
        @Valid
        @ConvertGroup(from = Default.class, to = DeliveryChecks.class)
        Address
    > shippingAddresses;
}
```

Reading from outside in:

1. `@NotEmpty`: the **`List` container** must be non-null and non-empty.
2. `@NotNull` on the type argument: **each `Address`** must be non-null.
3. `@Valid` on the type argument: cascades into each present `Address`.
4. `@ConvertGroup` on **the same type argument as `@Valid`**: switches `Default` to `DeliveryChecks` when entering each `Address`.

`@ConvertGroup` does not apply `@NotNull` to elements, does not require the list to be non-empty, and does not check constraints on the `List` itself. Those are separate responsibilities.

### 7.2. `Map` with Different Key and Value Rules

`Map<Key, Value>` has two type arguments; you can place different annotations on keys and values:

```java
class WarehouseRequest {
    @NotEmpty
    Map<
        @NotBlank String,
        @NotNull @Valid
        @ConvertGroup(from = Default.class, to = DeliveryChecks.class)
        Address
    > addressesByLabel;
}
```

- `@NotEmpty` checks the `Map` itself.
- `@NotBlank` checks keys (e.g., `"home"`, `"office"`).
- `@NotNull` checks that each value is non-null.
- `@Valid @ConvertGroup` converts the group when cascading into each `Address` value.

With `Map<@Valid @ConvertGroup(...) SomeKey, @Valid @ConvertGroup(...) SomeValue>`, both keys and values can cascade under different rules if keys are also beans needing validation. Do not put a conversion on the outer container expecting it to switch groups for an arbitrary type argument; choose the exact cascade point and understand extractors.

### 7.3. Multi-Level Nested Containers

A type like `Map<String, List<Address>>` has **two container levels**. Example declaration:

```java
Map<
    String,
    List<
        @Valid
        @ConvertGroup(from = Default.class, to = DeliveryChecks.class)
        Address
    >
> groups;
```

When the validator has matching value extractors, it traverses the `Map`, then the `List`, then cascades into each `Address` and converts the group at the marked type argument. If the list must be non-empty or `Address` non-null, add `@NotEmpty`/`@NotNull` in the proper spots.

Beyond standard extractors, a custom container `Box<T>` may need a corresponding `ValueExtractor` so Bean Validation knows how to unwrap elements. `@ConvertGroup` does not supply extractors; it operates **only after the engine identifies a valid cascade path**.

### 7.4. Warning About Mixed Declaration Styles

For some collection types, you may encounter the older style:

```java
@Valid
@ConvertGroup(from = Default.class, to = DeliveryChecks.class)
List<Address> addresses;
```

and the type-use style:

```java
List<
    @Valid
    @ConvertGroup(from = Default.class, to = DeliveryChecks.class)
    Address
> addresses;
```

Both can cascade across containers according to their respective rules; with nested generic structures, type-use syntax usually expresses the exact target receiving the group more clearly. **Do not declare `@Valid` redundantly on both the container and the same type argument path**, as that easily causes metadata/cascade confusion. Pick one consistent style, test against your actual provider, and place rules at the exact target.

## 8. Group Sequences, `Default`, and Conversion: Order Is Not Simple Varargs

Group conversion relates to `@GroupSequence`, yet they are **different mechanisms**.

- `@GroupSequence` defines **evaluation order of groups** and can skip later groups when an earlier group fails.
- `@ConvertGroup` defines **group switching when cascading across an edge**.
- Passing `validator.validate(bean, Default.class, DeliveryChecks.class)` **does not** create order; there is no guarantee `Default` runs first without a sequence.

Example sequence definition:

```java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

interface ExpensiveChecks {}

@GroupSequence({Default.class, ExpensiveChecks.class})
interface AllChecks {}
```

When `AllChecks` is requested, Bean Validation evaluates component groups in declared order. **Group conversion is applied to the group after group sequence expansion**; `from` cannot point directly to `AllChecks` if `AllChecks` is a group sequence.

`to` can point to a valid sequence and will be expanded before validating the child bean per Jakarta Validation rules. Therefore, when debugging a rule that seems not to match, inspect the group **actually crossing the cascade after sequence expansion**, not just the interface name passed by the API caller.

### 8.1. `Default` Group Sequence Redefinition

If a class uses `@GroupSequence` to **redefine its own `Default` group**, class-local rules apply; do not assume the entire root `Default` configuration propagates verbatim to child beans. Group conversion and group sequences can interact based on each class's metadata.

When combining both mechanisms, write integration tests for the **entire object graph**, including order and group outcomes on parent and child beans. Never guess `@ConvertGroup.from` with a sequence name.

## 9. API Scope: `validate` Differs from `validateProperty` and `validateValue`

`jakarta.validation.Validator` has three familiar methods:

```java
validator.validate(order, Default.class);
validator.validateProperty(order, "address", Default.class);
validator.validateValue(Order.class, "address", new Address(), Default.class);
```

This snippet illustrates API signatures; `Order` and `Address()` are conceptual examples, not the standalone code from section 5.

**Decisive differences:**

| API | Cascades `@Valid` | Applies `@ConvertGroup` | Checks constraints directly on property |
| --- | --- | --- | --- |
| `validate(object, groups...)` | Yes, where marked | Yes, when crossing matching cascade edge | Yes |
| `validateProperty(object, propertyName, groups...)` | **No** | **No** | Yes, on the selected property |
| `validateValue(beanType, propertyName, candidate, groups...)` | **No** | **No** | Yes, against property metadata for candidate |

When you need to check rules on `Address.street` under the target group, use `validate(root, ...)` with cascading or validate the `Address` bean directly with the desired group. Do not conclude "conversion does not work" just because `validateProperty(root,"address")` returns an empty set: that API does not descend into child beans.

`@ConvertGroup` is also not a way to change the group of **constraints placed directly on the parent property**. If `@NotNull(groups=Default.class)` is on `Order.address`, it is governed by the root group being validated, not switched to the target group merely because a conversion exists on the outgoing edge.

## 10. How Do Validation Failures Differ from Configuration Errors?

With a DTO whose metadata is valid while data is invalid:

```java
Set<ConstraintViolation<OrderRequest>> violations =
        validator.validate(order);
```

the call returns `ConstraintViolation`s that may have `getPropertyPath()` such as `address.street`. A path pointing to a child bean **does not mean the annotation was placed on the parent bean**: the `@NotBlank` rule belongs to `Address`, while `@ConvertGroup` only decides which group is used upon entering `Address`.

With an annotation violating the contract:

```java
@ConvertGroup(from = Default.class, to = DeliveryChecks.class)
Address address;
```

without `@Valid`, the provider may throw **`ConstraintDeclarationException`** instead of returning `ConstraintViolation`s. This is a **constraint configuration error**, not invalid user data.

Other configuration issues:

| Situation | Nature | Resolution |
| --- | --- | --- |
| Conversion missing `@Valid` | Invalid declaration | Put `@Valid` at the same cascade point |
| Two rules with same `from`, different `to` | Ambiguous mapping rule | Keep only one target per source |
| `from` points to a group sequence | Invalid per spec | Convert on the expanded component group |
| No matching `ValueExtractor` for custom container | Cannot unwrap type argument | Register a `ValueExtractor` or use a supported type |
| Null child bean yields no nested errors | No object to cascade into | Add `@NotNull` on the property if required |
| `@Validated(Create.class)` while conversion specifies `from=Default` | Group does not match, no conversion | Use `from=Create.class` or adjust root groups |
| Child's `@NotBlank` does not run | Constraint belongs to a different group than converted group | Align group metadata or add valid rule |
| Direct constraint on parent expected to be converted | Conversion does not alter parent's group | Select root group via `Validator`/`@Validated` |
| `A→B`, `B→C` on same edge, `C` never runs | No chaining on a single edge | Put the second rule on a deeper edge if needed |
| Placing `@Validated` on nested field to cascade | `@Validated` does not replace `@Valid` | Use `@Valid + @ConvertGroup` |
| Controller/service method validation does not run | Not passing through proper integration/proxy | Inspect Spring MVC/AOP stack, provider, and invocation |
| Binding error mistaken for conversion failure | JSON parser/mapper could not construct bean | Handle deserialization errors separately |

Whether `ConstraintDeclarationException` is detected during metadata bootstrap or on the first validation call depends on the provider. Do not catch it as a user field error and return "invalid input format" instead of fixing the configuration in code.

## 11. Spring Pitfalls and Safe Design Patterns

### 11.1. `@ConvertGroup` Does Not Replace DTO Contracts

When Create and Update APIs allow different sets of fields, validation groups and group conversions only validate **the values of the already-bound DTO**. They do not define which fields clients may send, do not prevent mass-assignment, do not check authorization, and do not replace database uniqueness.

When operation policies differ greatly, separate DTOs for Create and Update are often clearer than a single DTO overloaded with marker groups and conversions. For reusable components like `Address`, group conversion remains valuable to keep child modules decoupled from every caller group in parent modules.

### 11.2. Testing Both Sides of Each Edge

For a `Default → DeliveryChecks` edge, test:

1. Root `Default` + child failing `Default` yet **passing `DeliveryChecks`**: must not report child errors belonging solely to `Default`.
2. Root `Default` + child failing `DeliveryChecks`: must report the corresponding child error.
3. Root `Create` not matching `from=Default`: child receives `Create`, not `DeliveryChecks`.
4. Child `null`: `@Valid` skips; `@NotNull` (if present) reports error on the parent property.
5. `A→B` and `B→C` on **the same edge**: must not chain onward to `C`.
6. Two-edge chain `A→B` then `B→C`: verify grandchild rules under valid cascading.
7. `List`/`Map` containers with null elements, empty containers, and invalid nested beans to confirm container rules and conversion behave distinctly.
8. With `@GroupSequence`: verify post-expansion groups and sequence stopping rules.
9. Calling `validateProperty`/`validateValue`: do not confuse with full graph validation.
10. Spring MVC: type-valid JSON failing child rules vs. wrong-type requests blocked at binding.

When asserting `ConstraintViolation`s, do not depend on `Set` order. Compare sets of `propertyPath`s and, when needed, `ConstraintDescriptor` metadata to avoid brittle tests across locales. For `Map`/`List`, paths may include keys/indices; avoid hardcoding every provider's formatting detail unnecessarily.

### 11.3. Notes on "Reverse" Mappings and Bidirectional Relations

Two converters `A→B` and `B→A` on the same edge do not cause a conversion loop, because only one rule runs per edge. However, **the object graph itself can contain reference cycles** (`Order.customer.order`...). Bean Validation prevents infinite loops per traversal path/group, yet you should still model cascades intentionally and test real object graphs to avoid unnecessary work.

If child-bean constraints depend on user context or database queries, do not pack heavy logic or side effects into custom `ConstraintValidator`s running on every cascade. Most access-control and state checks belong in services, where transactions and caching strategies are explicit.

## 12. Workflow for Applying `@ConvertGroup`

A practical rollout sequence:

1. **Identify the group used to validate the parent bean.** For instance, `Default` for ordinary requests or `Create` chosen by the controller.
2. **List which groups the child bean's constraints belong to.** For example, `DeliveryChecks` checking street and postal code.
3. **Choose the edge to cascade.** Mark `@Valid` on the specific property or type argument.
4. **Write the `from → to` rule on that exact edge.** `from` is the actual group crossing the edge; `to` is the group desired for the child bean.
5. **Declare nullability independently.** If the child bean cannot be null, add `@NotNull` on the property; for collections, place container and element constraints at their proper levels.
6. **Test both direct parent rules and child rules.** Prove the parent still uses its original group, the child uses the mapped group, and unmatched groups pass through unchanged.
7. **If there are multiple tiers**, place distinct rules on each edge; do not expect converters on the same edge to chain.
8. **If sequences are involved**, verify groups after sequence expansion and stopping rules; never use a group sequence as `from`.
9. **Integrate with Spring at the right points** using `@Valid`/`@Validated`/`BindingResult` or explicit `Validator`; keep binding errors and business errors separate.
10. **Verify metadata when upgrading Jakarta/Hibernate Validator/Spring**, as validation paths and controller exception types can evolve.

**Key point:** `@ConvertGroup` is a mapping of **the group intended for a child object at a `@Valid` point**—not a new constraint, not a change to the parent bean's group, not an automatic cascade, not a `null` check, and not a blanket conversion of every group to a target group. Thinking in terms of **edges in the object graph** prevents confusion among `@Validated` at the entry point, `@Valid` for propagation, and `@ConvertGroup` for selecting the child bean's group.

### References

- Jakarta Bean Validation 3.0 Specification — Object graph validation, group conversion, group sequences: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation 3.1 Specification — Group conversion (same conversion principles): https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation 3.0 API — `ConvertGroup`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/groups/convertgroup
- Hibernate Validator 8 Reference Guide — Group conversion: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC — Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring MVC — Request body: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
