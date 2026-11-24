# `@Valid` on Reference Properties to Child Objects in Bean Validation

## 1. Purpose and Real-World Scenario

In a Spring application, an input-receiving object often contains child objects. For example, `OrderForm` contains `Customer`, and `Customer` contains `Address`:

```text
OrderForm
├── orderCode
└── customer                  <- @Valid on reference property
    ├── name                  <- @NotBlank
    └── address               <- @Valid on reference property
        ├── city              <- @NotBlank
        └── zip               <- @Pattern
```

When validating `OrderForm`, constraints located on `Customer` or `Address` **are not automatically traversed just because those objects exist in the Java object graph**. `@Valid` marks the point where **cascaded validation** is needed, so Bean Validation proceeds from the parent object to the child object. Every reference edge that needs to be traversed must be marked appropriately if validation is to continue deeper.

Example:

```java
public class OrderForm {
    @Valid
    private Customer customer;
}

public class Customer {
    @NotBlank
    private String name;

    @Valid
    private Address address;
}

public class Address {
    @NotBlank
    private String city;
}
```

This is a **structural illustration snippet**, not a standalone Java program; you need to import `jakarta.validation.Valid`, `jakarta.validation.constraints.NotBlank`, and the corresponding classes. When both `OrderForm.customer` and `Customer.address` have `@Valid`, calling `validator.validate(order)` can detect `customer.name` and `customer.address.city` along with errors on the root object.

After this lesson, you should be able to:
- Understand the meaning of `@Valid` on a **field/getter referencing a child bean** and how traversal works across multiple levels.
- Distinguish `@Valid` from `@NotNull`, constraints placed directly on a field, and `@Validated`/validation groups.
- Correctly read error paths (`ConstraintViolation.getPropertyPath()`) on nested objects and in Spring `BindingResult`.
- Understand the difference between validating an object with Jakarta Validation and binding/validation in Spring MVC.
- Write tests for valid, invalid, and `null` child objects, missing `@Valid`, collections, and circular reference cases.

The core scope is **nested validation through reference properties**. Examples involving collections and group conversion will help clarify the mechanism, though they do not replace the scenario where a field points to a single child bean.

## 2. What `@Valid` Is, and What It Is Not

Jakarta API:

```java
import jakarta.validation.Valid;
```

`@Valid` is a **marker annotation used to request validation cascading** into the referenced object. It has no `message`, `value`, `groups`, or `payload` attributes like constraints such as `@NotBlank`, `@Min`, or `@Size`; `@Valid` itself **never produces an "invalid" error**.

Consider the two annotations:

```java
@NotNull(message = "Customer is required")
@Valid
private Customer customer;
```

- `@NotNull` checks whether the `customer` property itself is non-null.
- `@Valid` requests validating constraints **inside** the `Customer` instance if the instance exists.
- If `customer == null`, Jakarta Bean Validation **skips cascading** and does not traverse deeper, so only `@NotNull` produces a violation.
- If `customer != null` but `customer.name` is blank, only `@Valid` on the `customer` edge causes the validator invoked from `OrderForm` to reach `@NotBlank` on `Customer.name`.
- If `customer != null` and all constraints in `Customer` are valid, `@Valid` produces no additional violations.

Comparing four cases:

| Declaration | `customer == null` | `customer.name` violated |
| --- | --- | --- |
| `private Customer customer;` | No error from this field | Not traversed into `Customer` |
| `@NotNull private Customer customer;` | Error on `customer` | Not traversed into `Customer` |
| `@Valid private Customer customer;` | No error from `@Valid` | Error on `customer.name` |
| `@NotNull @Valid private Customer customer;` | Error on `customer` | Error on `customer.name` when child object exists |

Therefore, **`@Valid` is not synonymous with `@NotNull`**. If the API requires an address object to be present, you must explicitly state that requirement with `@NotNull` on the reference. Adding `@NotNull` inside `Address.city` will not catch `address == null`, because `Address` is not traversed in that case.

### 2.1. `@Valid` on Field or Getter?

Both field declarations and JavaBean getters are supported locations in Jakarta Validation:

```java
@Valid
private Address address;

// Or in property style:
@Valid
public Address getAddress() {
    return address;
}
```

The two snippets above illustrate **two alternative approaches**; in practice, choose a clear convention for your model. Do not accidentally duplicate annotations on both the field and the getter assuming traversal will beneficially run in some double order. The provider determines how declarations and metadata are resolved; test on the real class.

With Spring data binding, JavaBean getters and setters allow the mapper/binder to read and write properties. Jakarta Bean Validation can still read annotated private fields; this is a separate mechanism from Spring needing setters or a binding strategy to populate data.

## 3. Step-by-Step Cascaded Validation Mechanism

Suppose:

```java
class OrderForm {
    @NotBlank
    String orderCode;
    @Valid
    Customer customer;
}

class Customer {
    @NotBlank
    String name;
    @Valid
    Address address;
}

class Address {
    @NotBlank
    String city;
}
```

When calling:

```java
Set<ConstraintViolation<OrderForm>> errors =
        validator.validate(order);
```

This is **illustrative code**; it requires `Validator` and `ConstraintViolation` from Jakarta Validation, the defined classes, and actual `validator` and `order` instances.

Logical sequence:

1. The validator starts at `OrderForm`, evaluating constraints applied to the root object itself, such as `@NotBlank` on `orderCode`.
2. It sees `OrderForm.customer` marked with `@Valid`; if the value is non-null, the validator moves to the `Customer` object.
3. It evaluates constraints on `Customer`, such as `@NotBlank` on `name`.
4. It sees `Customer.address` marked with `@Valid`; if the value is non-null, it continues to `Address`.
5. It evaluates `@NotBlank` on `Address.city` and other constraints.
6. It creates `ConstraintViolation<OrderForm>` instances with paths computed **from the validated root**, such as `customer.name` and `customer.address.city`.

This is a **path-explanation model**; the specification does not guarantee that constraints will be executed in the exact 1 → 6 order as read in code. `Set<ConstraintViolation<T>>` **does not guarantee element order**. When stable logging, output, or tests are needed, sort by property path and constraint details before displaying.

### 3.1. What If `@Valid` Is Missing on an Edge?

If only `OrderForm.customer` has `@Valid`, while `Customer.address` does not:

```text
OrderForm --@Valid--> Customer --(no @Valid)--> Address
                     |
                     +-- name is validated
                         address.city is not traversed
```

Even though `Address.city` has `@NotBlank`, calling `validator.validate(order)` **does not automatically visit every property of every object in the graph**. It only checks declared cascade edges (and constraints applied to the current value).

Conversely, if you directly call `validator.validate(address)`, `Address`'s constraints are still checked because `address` is now the root, requiring no parent with `@Valid`.

### 3.2. A Nested Child Object Can Have Both Constraints and Cascading

```java
@NotNull(message = "Address is required")
@Valid
private Address address;
```

`@NotNull` applies to the `Address` reference; `@Valid` traverses deeper to check `city` and `zip` when non-null. This lesson differs from `@NotEmpty` used for strings/collections and also from `@Size`, which does not inspect the contents of each child object.

## 4. `propertyPath` and Nested Object Errors

Errors in a child object are still returned as a `ConstraintViolation` belonging to the root validation call. For example, `Address.zip = "12x"` failing `@Pattern(regexp = "\\d{5}")` when `@Valid` is present on both edges:

```text
root                         = OrderForm
propertyPath.toString()      = customer.address.zip
invalidValue                 = "12x"
message                      = "ZIP must contain 5 digits"
```

`getPropertyPath()` returns a `jakarta.validation.Path`, **not merely a string**. `Path.Node` provides `getName()`, `getKind()`, `isInIterable()`, `getIndex()`, and `getKey()` when structured path processing is needed.

For simple nested objects, `Path.toString()` typically produces a dot-separated string. With collections or Maps, indices/keys, container element nodes, or provider-specific path segments may appear; **do not assume** every path is a dot-delimited list of field names.

Useful APIs:

```java
violation.getRootBean();        // root OrderForm instance
violation.getLeafBean();        // instance closest to where the constraint is evaluated
violation.getPropertyPath();    // path from root to violation location
violation.getInvalidValue();    // value evaluated by the constraint
violation.getMessage();         // interpolated message
violation.getMessageTemplate(); // template before interpolation
```

These are illustrative expressions on an existing `ConstraintViolation<?>` instance. `getInvalidValue()` is not necessarily a String or the final property in every constraint type: a class-level constraint may have the entire child bean as its invalid value, even when a custom validator adds a property node to the path.

If you use error paths for a UI, map them to the public field names of the form/API. `customer.address.zip` is a Bean Validation path, not necessarily a JSON Pointer `/customer/address/zip` or an input name in the UI.

## 5. Complete Java 17+ Example: Two Levels of `@Valid`, Null Values, and Spring Integration

The example uses **Jakarta Validation 3.0, Hibernate Validator 8.0.2.Final** as the provider, and **Spring Framework 6.2.14** as the adapter to demonstrate `BindingResult`. The program runs standalone with Maven, without starting Spring Boot or an HTTP server.

Scenario:
- `OrderForm.orderCode` has `@Size(min = 3)`.
- `OrderForm.customer` has `@NotNull @Valid`.
- `Customer.name` has `@NotBlank`.
- `Customer.address` has `@NotNull @Valid`.
- `Address.city` has `@NotBlank`; `Address.zip` has `@Pattern` requiring exactly 5 digits.
- Also includes `OrderWithoutCascade` without `@Valid`, to prove that merely holding a reference does not cause validation to traverse deeper.

### 5.1. Create `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>nested-valid-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.14</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`hibernate-validator` provides the Jakarta Bean Validation provider; `jakarta.el` supports the message interpolation system as configured; `spring-context` contains the Spring adapter needed for the integration section. In a Spring Boot application, you typically let the Boot BOM manage compatible versions and add `spring-boot-starter-validation` instead of pinning every dependency manually as in this example.

### 5.2. Create `src/main/java/demo/NestedValidationDemo.java`

```java
package demo;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.beanvalidation.SpringValidatorAdapter;

public final class NestedValidationDemo {

    public static final class Address {
        @NotBlank(message = "City is required")
        private String city;

        @Pattern(regexp = "\\d{5}", message = "ZIP must contain 5 digits")
        private String zip;

        public Address(String city, String zip) {
            this.city = city;
            this.zip = zip;
        }

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }

        public String getZip() {
            return zip;
        }

        public void setZip(String zip) {
            this.zip = zip;
        }
    }

    public static final class Customer {
        @NotBlank(message = "Name is required")
        private String name;

        @NotNull(message = "Address is required")
        @Valid
        private Address address;

        public Customer(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public static final class OrderForm {
        @Size(min = 3, message = "Order code needs 3 characters")
        private String orderCode;

        @NotNull(message = "Customer is required")
        @Valid
        private Customer customer;

        public OrderForm(String orderCode, Customer customer) {
            this.orderCode = orderCode;
            this.customer = customer;
        }

        public String getOrderCode() {
            return orderCode;
        }

        public void setOrderCode(String orderCode) {
            this.orderCode = orderCode;
        }

        public Customer getCustomer() {
            return customer;
        }

        public void setCustomer(Customer customer) {
            this.customer = customer;
        }
    }

    public static final class OrderWithoutCascade {
        // Intentionally without @Valid.
        private Customer customer;

        public OrderWithoutCascade(Customer customer) {
            this.customer = customer;
        }

        public Customer getCustomer() {
            return customer;
        }

        public void setCustomer(Customer customer) {
            this.customer = customer;
        }
    }

    private static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Customer invalidCustomer =
                new Customer(" ", new Address("", "12x"));
        OrderForm invalidOrder =
                new OrderForm("A", invalidCustomer);

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Set<ConstraintViolation<OrderForm>> errorSet =
                    validator.validate(invalidOrder);
            List<ConstraintViolation<OrderForm>> errors =
                    new ArrayList<>(errorSet);
            errors.sort(Comparator.comparing(
                    v -> v.getPropertyPath().toString()));

            require(errors.size() == 4, "Expected four violations");
            for (ConstraintViolation<OrderForm> error : errors) {
                System.out.println(error.getPropertyPath()
                        + " => " + error.getMessage());
            }

            // Spring converts violations to FieldError.
            BeanPropertyBindingResult bindingResult =
                    new BeanPropertyBindingResult(invalidOrder, "order");
            new SpringValidatorAdapter(validator)
                    .validate(invalidOrder, bindingResult);

            require(bindingResult.getFieldErrorCount() == 4,
                    "Expected four field errors");

            FieldError zipError =
                    bindingResult.getFieldError("customer.address.zip");
            require(zipError != null, "Nested ZIP field error missing");
            System.out.println(
                    "springFieldErrors=" + bindingResult.getFieldErrorCount());
            System.out.println("springZipField=" + zipError.getField());

            // @Valid does not reject null by itself; @NotNull does that.
            OrderForm nullCustomer = new OrderForm("ORD-123", null);
            Set<ConstraintViolation<OrderForm>> nullErrors =
                    validator.validate(nullCustomer);
            require(nullErrors.size() == 1, "Expected one required error");
            require("customer".equals(nullErrors.iterator().next()
                    .getPropertyPath().toString()),
                    "Expected customer required error");
            System.out.println("nullCustomerErrors=" + nullErrors.size());

            // Without @Valid on parent -> does not traverse to child constraints.
            Set<ConstraintViolation<OrderWithoutCascade>> uncascaded =
                    validator.validate(new OrderWithoutCascade(invalidCustomer));
            require(uncascaded.isEmpty(), "Unexpected cascade");
            System.out.println("withoutCascadeErrors=" + uncascaded.size());

            // With sufficient @Valid, all child fields valid -> no violations.
            OrderForm validOrder = new OrderForm(
                    "ORD-123",
                    new Customer("Lan", new Address("Hanoi", "12345")));
            require(validator.validate(validOrder).isEmpty(),
                    "Expected fully valid order");
            System.out.println("validOrderErrors=0");
            System.out.println("CHECKS: PASS");
        }
    }
}
```

### 5.3. Run the Program

In the directory containing `pom.xml` (Java 17+ and Maven):

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.NestedValidationDemo
```

The stdout produced by the program, after omitting library startup logs if any:

```text
customer.address.city => City is required
customer.address.zip => ZIP must contain 5 digits
customer.name => Name is required
orderCode => Order code needs 3 characters
springFieldErrors=4
springZipField=customer.address.zip
nullCustomerErrors=1
withoutCascadeErrors=0
validOrderErrors=0
CHECKS: PASS
```

**Output explanation:**
- `orderCode` violates the constraint on the root.
- The two violations `customer.address.city` and `customer.address.zip` only appear because **both hops**, `OrderForm.customer` and `Customer.address`, have `@Valid`.
- `customer.name` is a constraint on the child `Customer`; `@Valid` on `OrderForm.customer` is enough to reach it.
- `SpringValidatorAdapter` records the same four violations via `BindingResult`. The ZIP error path can be retrieved using `FieldError.getField()`.
- With `nullCustomer`, `@Valid` skips the null reference, but `@NotNull` reports the missing customer.
- With `OrderWithoutCascade`, the `Customer` field holds an invalid object without `@Valid`, so the validator does not cascade to the child and the result is empty.
- With `validOrder`, all root and child constraints are satisfied; the result is empty.

In the program, `errors` is **sorted by path** before printing to keep stdout deterministic. Jakarta Validation itself returns a `Set` with no guaranteed order.

The code uses explicit English messages to avoid output changes caused by bundles or locales. Real-world applications can internationalize messages using resource bundles and `MessageInterpolator`.

## 6. Spring MVC: Validating Nested DTOs on Incoming Requests

A DTO used in Spring MVC might look like this (this is a **snippet**, requiring appropriate constructors/getters/setters):

```java
public class CheckoutForm {
    @NotNull(message = "Customer is required")
    @Valid
    private CustomerForm customer;
}

public class CustomerForm {
    @NotBlank
    private String name;

    @NotNull
    @Valid
    private AddressForm address;
}

public class AddressForm {
    @NotBlank
    private String street;
}
```

The imports are `jakarta.validation.Valid`, `jakarta.validation.constraints.NotNull`, and `jakarta.validation.constraints.NotBlank`. In Spring Framework 6+, Jakarta APIs use the `jakarta.*` namespace; older Spring Framework 5.x projects typically belong to the `javax.validation.*` ecosystem.

Example controller for an HTML form (**illustrative code**, requires Spring Web MVC):

```java
@PostMapping("/checkout")
public String submit(
        @Valid @ModelAttribute("checkout") CheckoutForm checkout,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "checkout/form";
    }
    return "checkout/success";
}
```

Controller imports:
- `jakarta.validation.Valid`
- `org.springframework.web.bind.annotation.PostMapping`
- `org.springframework.web.bind.annotation.ModelAttribute`
- `org.springframework.validation.BindingResult`

With a Bean Validation provider integrated into Spring MVC, `@Valid` **before the root parameter** triggers validation on `CheckoutForm`. Then `@Valid` **on the `customer` and `address` fields** controls cascading down to child objects. These are **two different roles at two annotation positions**:

```text
@Valid @ModelAttribute CheckoutForm    -> validates root on request
    @Valid CustomerForm customer        -> cascades root -> customer
        @Valid AddressForm address      -> cascades customer -> address
```

`BindingResult` should be placed **immediately after the parameter** whose errors it receives. When there is a nested error like `customer.address.street`, it can be retrieved via `errors.getFieldError("customer.address.street")` or the `errors.getFieldErrors()` list.

### 6.1. What If No `BindingResult` Follows?

Spring MVC may throw a validation exception, typically `MethodArgumentNotValidException` when validating individual command object arguments; when **method validation** is triggered on direct parameters or return values, it may be `HandlerMethodValidationException`. The exception type depends on the method signature and the actual validation path. For forms that need to redisplay errors, accepting a `BindingResult` right after the model is a proactive way to handle them.

For `@RequestBody`, Jackson (or the configured HTTP message converter) deserializes JSON into Java objects before validation; nested `@Valid` still means cascading, but **JSON parsing failures** are message-reading errors distinct from violations on the deserialized object.

### 6.2. Spring Does Not Automatically Validate Every Object Immediately After `bind`

When using `DataBinder` manually, `binder.bind(propertyValues)` primarily performs binding. To run Bean Validation, you must configure a validator and call:

```java
binder.setValidator(localValidatorOrSpringAdapter);
binder.bind(propertyValues);
binder.validate();
BindingResult errors = binder.getBindingResult();
```

This is a **snippet**; `localValidatorOrSpringAdapter` must be a valid `org.springframework.validation.Validator` instance. In Spring MVC, the `@Valid`/`@Validated` handling infrastructure typically invokes validation as part of the controller workflow; it does not impose the same default on every `DataBinder` created manually by the application.

Distinguish two kinds of errors:
- **Binding/conversion:** failing to convert `"abc"` to `Integer`, producing a `typeMismatch` error.
- **Bean Validation:** successfully binding to the object, but failing `@NotBlank`, `@Size`, or `@Pattern` on the root or child.

Both can appear in `BindingResult`; not every `FieldError` originates from a Jakarta `ConstraintViolation`.

## 7. `null` Cases, Missing Objects, and Partially Bound DTOs

There are three commonly confused scenarios:

1. **Child is `null`, only `@Valid` is present:** the validator **skips** traversal, so no error is produced from the child's constraints.
2. **Child is `null`, `@NotNull @Valid` is present:** `@NotNull` on the **parent reference** produces a `customer` violation; the validator does not generate additional errors for `customer.name` because there is no `Customer` instance.
3. **Child exists, but internal fields are null/blank:** once cascaded into the child, constraints such as `@NotBlank` and `@NotNull` on child fields run and produce nested path errors.

Example:

```text
customer = null
  -> @Valid: no errors
  -> @NotNull @Valid: "customer" is invalid

customer = Customer(name = null, address = null)
  -> @NotBlank Customer.name: invalid at "customer.name"
  -> @NotNull Customer.address: invalid at "customer.address"
  -> @Valid Customer.address: not traversed because it is null
```

**Do not create an empty child object just to force nested constraints to run** if the business logic genuinely allows the child to be absent. Express **required vs optional** clearly, and choose `@NotNull` and `@Valid` accordingly.

Note specifically: calling `validator.validate(null)` with a **null root argument** is not equivalent to cascading through a null field; the validator API requires a valid root object and may throw `IllegalArgumentException`. The "skip null" rule here applies to **child references during cascading**.

### 7.1. Optional and `@Valid`

`Optional<Customer>` can hold an empty value or a child object, and Jakarta Bean Validation 2.0+/3.0 has a **value extraction** mechanism for certain standard containers. When using wrapper/container types, you can declare annotations on type arguments such as `Optional<@Valid Customer>` depending on provider capabilities. However, an empty `Optional` and a field requiring a `Customer` are different requirements; appropriate constraints on value/presence are needed.

For typical form/Jackson DTOs, consider using a direct `Customer` reference with `@NotNull @Valid` if that makes the contract clearer. Do not automatically replace every nullable field with `Optional` in DTO classes.

## 8. Cascading Through `List`, `Map`, Arrays, and Multiple Levels

Although the main focus of this lesson is a property **referencing a single child object**, the same principle applies to multi-child relationships. Jakarta Validation supports cascaded validation on standard containers via annotations on the container or on the **type argument**.

Example for an item list:

```java
public class OrderForm {
    private List<@Valid LineItem> items;
}

public class LineItem {
    @Min(1)
    private int quantity;
}
```

This is **illustrative structural code**; you need to import `java.util.List`, `jakarta.validation.Valid`, and `jakarta.validation.constraints.Min`. If `items` contains a `LineItem(quantity=0)`, the path may look like `items[0].quantity`, with the index accessible through Jakarta Validation's `Path.Node` structure. The exact displayed container node name depends on the provider and collection type.

Another common way to declare a cascaded collection is:

```java
@Valid
private List<LineItem> items;
```

For providers supporting type-use annotations (Jakarta Bean Validation 2.0+), declaring `List<@Valid LineItem>` makes it explicit that **elements** are cascaded. Choose one convention rather than redundantly putting `@Valid` on both the container and the type argument without clear intent.

- `@Valid` **does not require** the collection to exist or contain elements. To require non-empty, use `@NotEmpty` on the collection according to your contract.
- `@Valid` **does not require** each element to be non-null: for that, you can use `List<@NotNull @Valid LineItem>`; pay attention to error nodes and provider behavior.
- `List<@NotBlank String>` validates **each String element** via a type-use constraint; it is not cascaded validation into a child bean because `String` is not a bean with child fields.
- With `Map<K,V>`, validation can apply to keys/values using appropriate annotations; paths may contain Map keys. Do not assume Map paths always look like List paths.

### 8.1. Multi-Level Cascading Must Be Declared on Every Edge

Example:

```text
CheckoutRequest
  -> @Valid order
       -> @Valid customer
            -> @Valid address
                 -> @NotBlank street
```

Missing `@Valid` on any edge along the path will cause validation starting from `CheckoutRequest` to **never reach** constraints beyond that edge. Conversely, when directly validating an intermediate object, the process starts at that object and applies annotations declared from the new root position.

### 8.2. Circular References Do Not Cause Infinite Loops

A Java object graph may contain cycles:

```text
Parent -> Child -> Parent -> Child -> ...
```

Jakarta Validation specifies that providers must prevent infinite loops during cascaded validation. Per **navigation path**, an already-visited instance is not traversed infinitely along the same path. This mechanism does not mean "each instance is validated only once across the entire graph": the same object can be reached via different reference paths and produce appropriate error paths.

Therefore, do not write a custom `ConstraintValidator` that manually traverses the entire graph when `@Valid` can solve the problem. With large graph models, also consider performance and request lifecycle; only mark cascade on relationships that genuinely need validation.

## 9. Validation Groups and `@ConvertGroup` During Cascading

By default, when calling:

```java
validator.validate(order);
```

Bean Validation validates the `Default` group. When cascading, the active validation group **is propagated down** to child objects, unless you configure group conversion.

Common point of confusion: `@Valid` **does not accept `groups`**:

```java
@Valid  // Valid, only marks cascade.
private Address address;
```

If you want to validate child constraints using a different group from the parent's group, use `@ConvertGroup` on the edge with `@Valid`. **Illustrative structural example**, not a standalone class:

```java
public interface Detailed {}

public class Address {
    @NotBlank(groups = Detailed.class)
    private String street;
}

public class Customer {
    @Valid
    @ConvertGroup(from = Default.class, to = Detailed.class)
    private Address address;
}
```

Imports:
- `jakarta.validation.Valid`
- `jakarta.validation.groups.ConvertGroup`
- `jakarta.validation.groups.Default`
- `jakarta.validation.constraints.NotBlank`

When validating `Customer` with the `Default` group, the `address` edge converts the group used for `Address` to `Detailed`. Without `@ConvertGroup`, constraints assigned only to `Detailed` will not run when the `Default` group is requested (unless another group inheritance/sequence rule is configured).

**Key rule:** `@ConvertGroup` must be attached to an element marked with `@Valid`, and the conversion applies **per cascade edge**, not as a global transformation for every bean. If multiple conversion rules are configured with the same `from`, the provider may throw `ConstraintDeclarationException`.

In Spring, `@Validated` helps specify groups at the controller/service validation entry point; `@Valid` on child properties still controls **cascading traversal**. Spring's `@Validated` does not automatically replace `@Valid` on each edge.

## 10. Advanced Cases to Understand Correctly

### 10.1. `@Valid` on Root Parameter vs `@Valid` on Reference Property

Both positions often appear together:

```java
public Response submit(@Valid @RequestBody OrderForm order) { ... }
```

and:

```java
public class OrderForm {
    @Valid
    private Customer customer;
}
```

The annotation on the **root parameter** tells the Spring infrastructure to validate the incoming object. The annotation on the **child property** controls traversal from the root to `Customer`. If you omit the annotation on the parameter without another validation mechanism, Spring MVC may not trigger root validation. If you omit the annotation on the property, Spring only checks root constraints and does not descend into `Customer`.

In the direct Jakarta API call `validator.validate(order)`, the call itself initiates root validation; you do not need to put `@Valid` on the local variable `order`.

### 10.2. Class-Level Errors Inside Child Objects

A class-level custom constraint such as `@ValidPeriod` on `Address`/`Reservation` can report a violation on the **bean node** when the parent cascades to the child. In that case, the path may stop at the child object name (`customer.address`) rather than a specific field, unless the custom validator explicitly calls `ConstraintValidatorContext.addPropertyNode(...)` to attach the error to a field.

`ConstraintViolation.getInvalidValue()` for a class-level error is typically the **entire child bean**, not a single String inside it. Therefore, do not automatically serialize or log the entire `invalidValue`; the object may carry sensitive data.

### 10.3. Persistence/JPA and Spring MVC Are Different Trigger Points

`@Valid` on an association in an HTTP DTO determines cascading when validating the DTO. `@Valid` in an entity can also be evaluated when the application or JPA provider runs Bean Validation at a configured lifecycle hook. **Do not confuse** JPA `CascadeType.PERSIST`/`MERGE` with Jakarta Validation `@Valid`: one manages entity lifecycle, while the other traverses constraints.

You should not rely solely on frontend validation or assume that calling repository `.save(...)` always performs the entire graph validation you expect; test the actual data-saving path and validation setup of your application.

### 10.4. When Should You Not Cascade?

If a child is a shared object containing many constraints unrelated to the current request, marking `@Valid` indiscriminately can cause the form to be rejected due to fields not even submitted in this context. Solutions include:
- Designing dedicated DTOs per endpoint that bind exactly the required input data.
- Using validation groups/group conversion purposefully.
- Marking cascade only on necessary relationships, avoiding huge object graphs.
- Separating data-syntax validation from business invariants that require multiple services/databases.

These choices should be based on actual request contracts rather than mechanically adding `@Valid` to every reference field.

## 11. Test Matrix for Nested `@Valid`

| Scenario | Data or Configuration | Expectation |
| --- | --- | --- |
| No cascade | Parent has invalid child but **no** `@Valid` on property | Only parent constraints are checked |
| Single-level cascade | Parent has `@Valid`, `child.name` `@NotBlank` and blank | Violation at `child.name` |
| Two-level cascade | Parent → child → address all have `@Valid` | Violation with path such as `child.address.city` |
| Missing second-level `@Valid` | Only parent → child has cascade | Constraints on address are not traversed from parent |
| Null child, `@Valid` only | `child = null` | No error produced by cascade |
| Null child, `@NotNull @Valid` | `child = null` | One error at `child` from `@NotNull` |
| Child exists, invalid content | `child.name = " "` | `@NotBlank` violation on child |
| Valid child | Root and all children valid | Empty `ConstraintViolation` set |
| Collection with invalid child | `List<@Valid LineItem>` with quantity 0 | Path identifies item/index and invalid property |
| Null collection element | `List<@Valid Item>` contains `null` | Null is skipped unless `@NotNull` is on the element |
| Default group | Validate root in `Default` | Child receives `Default` unless conversion is configured |
| Group conversion | `@Valid @ConvertGroup(Default → Detailed)` | Child uses group `Detailed` on that edge |
| Cyclic objects | A → B → A, cascaded edges | Provider prevents infinite loops per navigation path |
| Type binding error | Unparseable String for child numeric field | Spring may produce `typeMismatch`, not a nested Bean Validation violation |
| MVC request | `@Valid @ModelAttribute`, `BindingResult` right after | Nested errors recorded at corresponding field paths |
| JSON request | `@Valid @RequestBody` with nested JSON object | Deserialized first, then validates object graph if valid |
| Missing validation provider | Annotations present but no suitable Jakarta implementation | Cannot assume the application runs validation automatically |
| Wrong namespace | Mixing `javax.validation` and `jakarta.validation` | Provider/infrastructure may fail to recognize annotations |
| Sensitive data | Child has password/token | Do not expose raw `getInvalidValue()` or `FieldError.getRejectedValue()` to logs/APIs |

### 11.1. Testing Behavior by Property Path Instead of Order

The following snippet sits inside a test that already has `validator` and `order`, **not a standalone program**:

```java
Set<ConstraintViolation<OrderForm>> violations =
        validator.validate(order);

boolean hasCityError = violations.stream().anyMatch(v ->
        "customer.address.city".equals(
                v.getPropertyPath().toString()));
```

This is a clean way to verify error location without relying on the iteration order of `Set`. If the path involves a container element, consider using `Path.Node` to verify index/key/kind rather than asserting provider-dependent text.

### 11.2. Testing Edge-by-Edge Changes

A very valuable test is creating **the exact same invalid child** and two parents:
- Parent A has `@Valid` → child violations occur.
- Parent B does not have `@Valid` → no child violations from validating the parent.

This test demonstrates **the purpose of the `@Valid` marker** much more clearly than just running a single default error case. The sample program in Section 5 includes `OrderWithoutCascade` for this exact purpose.

## 12. Common Pitfalls and How to Fix Them

**1. "The child already has `@NotBlank`, why doesn't Spring report it?"** Because the parent is missing `@Valid` on the reference property or lacks a validation entry point on the root. Check both `@Valid` on the controller argument and `@Valid` on every edge of the object graph.

**2. "Put `@Valid` on `Customer.address` but not on `OrderForm.customer`."** Validation starting from `OrderForm` will never reach `Customer` to see the next-level annotation. An annotation on a deeper object alone cannot compensate for a missing edge higher up.

**3. "`@Valid` doesn't catch `customer = null`."** This is standard behavior: null references are skipped. Use `@NotNull @Valid` if the child is required to exist.

**4. "The child is null, and I want all errors for its inner fields reported."** There is no object to validate, so inner constraints do not run. Define the missing-object error on the parent property; do not fabricate errors for fields of a nonexistent object.

**5. "Why is the error `customer.address.zip` instead of `zip`?"** The validator returns paths relative to the root of the call. To display in a form, map nested paths properly; if you validate `Address` standalone, the path is simply `zip`.

**6. "Called `DataBinder.bind()` but got no `@NotBlank` errors."** Binding does not automatically run validation in all usage patterns. Register an appropriate Spring validator and call `validate()`, or use Spring MVC `@Valid`/`@Validated` infrastructure.

**7. "Failed right during JSON binding, with no `ConstraintViolation`."** The parser/deserializer can fail before Java objects are even constructed. Separate JSON syntax/type mismatch errors from Bean Validation.

**8. "The same child object was validated twice or hit a cycle."** The Jakarta provider must prevent infinite loops, but multiple valid paths to the same instance can produce violations along each path. Do not assume a single global visited-set across the whole graph.

**9. "Adding `@Validated` to a child field is enough."** `@Validated` is a Spring annotation typically used to specify validation groups at appropriate call sites; child reference fields need Jakarta `@Valid` for cascading.

**10. "Put `@Valid` on every referenced DTO and got unrelated errors."** Limit the graph or use business-specific DTOs/groups; choose the necessary cascade paths instead of validating the entire domain model regardless of the request.

**11. "Only tested direct fields."** This lesson emphasizes nested paths, null parents, missing annotations on an edge, collections, and Spring `BindingResult`; skipping those cases makes configuration bugs hard to catch.

**12. "Mixed `javax.validation.Valid` with `jakarta.validation.constraints.*`."** Spring Framework 6+ uses the Jakarta namespace; for Spring Framework 5 applications, choose the corresponding API/provider. Inspect your dependency tree and imports instead of changing only part of the packages.

## 13. Pre-Project Checklist

- [ ] Identify the **root validation entry point**: Jakarta `Validator.validate`, Spring MVC `@Valid`, `@Validated`, or calling `DataBinder.validate()`.
- [ ] Place `@Valid` on **every reference property** that must be traversed from parent to child, including across multiple levels.
- [ ] Place `@NotNull` on the reference **if and only if** the child must exist.
- [ ] Verify constraints on child classes and data types match the provider/Jakarta version in use.
- [ ] Test root errors, empty/invalid child, null child, missing `@Valid`, nested paths, and a fully valid case.
- [ ] For `List`/`Map` containing child beans, place `@Valid` where cascading is needed and test indices/keys.
- [ ] If using groups, determine how groups propagate across each edge; only use `@ConvertGroup` when explicitly required.
- [ ] When integrating with Spring MVC, verify appropriate `BindingResult`/exception handling and distinguish binding errors from constraint violations.
- [ ] Keep sensitive data out of error responses/logs; do not expose whole objects in `invalidValue`.
- [ ] Do not rely on `ConstraintViolation` ordering or validation execution order; sort when deterministic output is needed.
- [ ] Run runtime tests with the actual Spring/Jakarta Validation provider dependencies and real endpoints.

## Official Documentation

- Jakarta Bean Validation 3.0 Specification — Cascaded Validation / Object Graph Validation: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation 3.0 API — `@Valid`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Valid.html
- Jakarta Validation 3.0 API — `ConstraintViolation`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintViolation.html
- Spring Framework 6.2 — Bean Validation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — MVC Validator Configuration: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html
- Spring Framework 6.2 — `SpringValidatorAdapter`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/beanvalidation/SpringValidatorAdapter.html
- Hibernate Validator 8 Reference Guide — Cascaded validation: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/
