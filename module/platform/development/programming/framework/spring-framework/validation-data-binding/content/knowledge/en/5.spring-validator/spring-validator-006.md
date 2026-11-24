# Composing Validators by Delegating to Child Validators in Spring Framework

When an input object has multiple parts, writing every validation rule inside a single `Validator` class easily creates long methods, tight coupling to the data structure, and poor reusability. Spring allows a **parent validator (composite/parent validator)** to delegate specific rules to **child validators (delegate/child validators)**. Each child validator knows how to validate one object or one group of rules; the parent orchestrates the calls and aggregates errors.

This article focuses on **`org.springframework.validation.Validator`**, `Errors`, `ValidationUtils.invokeValidator(...)`, and nested error paths. This is validator composition using Spring's interface; it differs from Jakarta Bean Validation's automatic cascaded validation via `@Valid`.

## 1. Why Compose Validators?

Suppose a customer creation form has the following data:

```text
Customer
├── firstName
├── email
└── address
    ├── city
    └── postalCode
```

There are two groups of responsibilities: customer details (`firstName`, `email`) and address (`city`, `postalCode`). Instead of forcing `CustomerValidator` to know every field, we split them into:

- `CustomerFieldsValidator` validates only the simple fields of `Customer`.
- `AddressValidator` validates only `Address` and does not need to know it lives inside `Customer`.
- `CustomerValidator` checks structural conditions (e.g., `address` is required) and then **delegates** to the two child validators.

```text
                           CustomerValidator
                          /                 \
                    same object          nested object
                        /                     \
      CustomerFieldsValidator              AddressValidator
             Customer                          Address
                        \                     /
                         \                   /
                         same Errors / BindingResult
                               |
                      firstName, email,
                    address.city, address.postalCode
```

All errors are collected in **a single `Errors` instance belonging to the root object**. The calling layer (controller, service, or test) does not have to merge error lists manually.

## 2. The Spring Validator Contract

The basic interface has two methods:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

This is an **abbreviated signature for learning**; the actual `Validator` resides in the Spring library. `supports` indicates whether the validator accepts the input data type. `validate` records errors into the `Errors` object passed by the caller; its return type is `void`, not `boolean`.

Common implementation:

```java
@Override
public boolean supports(Class<?> clazz) {
    return Customer.class.isAssignableFrom(clazz);
}
```

The check `Customer.class.isAssignableFrom(clazz)` accepts `Customer` and its subclasses. Reversing the operands can cause the validator to accept wrong types. `supports` must match the actual type to which `validate` casts.

`Errors` offers two ways to record errors:

- `errors.rejectValue("email", "email.required", "Email is required")`: error for a single field. The result is typically a `FieldError` with a field path and error code.
- `errors.reject("customer.invalid", "Customer is invalid")`: object-level error not tied to any individual field (often called a *global error*).

In addition, `ValidationUtils.rejectIfEmptyOrWhitespace(...)` is a utility that checks whether a field is `null`, empty, or whitespace-only and calls `rejectValue` when needed. Error codes like `email.required` can be mapped via `MessageSource` to produce localized messages; default messages in examples keep outputs readable when no bundle is configured.

## 3. Two Kinds of Delegation to Distinguish

### 3.1. Same-Target Delegation

Multiple validators receive the same `Customer`, but check different groups of rules:

```java
ValidationUtils.invokeValidator(customerFieldsValidator, customer, errors);
```

The error collector remains at the root path (`errors.getNestedPath()` is usually `""`), so the child validator can call `rejectValue("firstName", ...)` directly.

`ValidationUtils.invokeValidator(...)` checks compatibility via `supports` before calling `validate`. If the validator does not support the object type, that is a **configuration/programming bug** and it can throw `IllegalArgumentException`; do not confuse this with “invalid user input”.

### 3.2. Nested-Object Delegation

`AddressValidator` only knows the field names `city` and `postalCode` on `Address`. To place errors under the `address` branch of `Customer`, the parent validator temporarily pushes a prefix onto `Errors`:

```java
errors.pushNestedPath("address");
try {
    ValidationUtils.invokeValidator(addressValidator, customer.getAddress(), errors);
} finally {
    errors.popNestedPath();
}
```

As a result, when `AddressValidator` records an error on `city`, the root error collector receives the path **`address.city`**. `pushNestedPath` and `popNestedPath` only change the **error path context**, not the root object bound to `Errors`. With `BeanPropertyBindingResult`, `getFieldValue("city")` under this path accesses `address.city` on the root object.

Always use `try/finally` so the path is restored even if the child validator throws an exception. If you forget `popNestedPath`, subsequent errors can accidentally carry the `address.` prefix.

**Important:** If `customer.getAddress() == null`, decide clearly whether that is a required error or optional, and **do not call** `AddressValidator` with `null`. The example below records `address.required` once; if the address is optional, you can skip validating that branch.

## 4. Complete Runnable Example on Java 17 and Spring 6

The following example runs in a console application without Spring Boot, an HTTP server, or a Bean Validation provider. It demonstrates `org.springframework.validation.Validator` and delegation directly, making errors easy to observe before integrating into MVC.

Create a Gradle project with `settings.gradle`:

```groovy
rootProject.name = 'spring-validator-composition'
```

And `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.0'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.validation.ValidationCompositionDemo'
}
```

The `spring-context` library contains the `org.springframework.validation` classes used in the example and pulls in required Spring components. If your project already uses Spring Boot and dependency version management, use the Spring Framework version managed by Boot instead of pinning the version as in this standalone console project.

Create `src/main/java/demo/validation/ValidationCompositionDemo.java`:

```java
package demo.validation;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class ValidationCompositionDemo {

    // Simple JavaBean: BeanPropertyBindingResult reads properties via getters.
    public static final class Address {
        private final String city;
        private final String postalCode;

        public Address(String city, String postalCode) {
            this.city = city;
            this.postalCode = postalCode;
        }

        public String getCity() {
            return city;
        }

        public String getPostalCode() {
            return postalCode;
        }
    }

    public static final class Customer {
        private final String firstName;
        private final String email;
        private final Address address;

        public Customer(String firstName, String email, Address address) {
            this.firstName = firstName;
            this.email = email;
            this.address = address;
        }

        public String getFirstName() {
            return firstName;
        }

        public String getEmail() {
            return email;
        }

        public Address getAddress() {
            return address;
        }
    }

    // Child validator A: same Customer object.
    static final class CustomerFieldsValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return Customer.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "firstName", "firstName.required",
                    "First name is required");
            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "email", "email.required",
                    "Email is required");
        }
    }

    // Child validator B: knows only the Address object.
    static final class AddressValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return Address.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "city", "city.required",
                    "City is required");
            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "postalCode", "postalCode.required",
                    "Postal code is required");
        }
    }

    // Parent validator: coordinates both responsibilities via delegation.
    static final class CustomerValidator implements Validator {
        private final Validator customerFieldsValidator;
        private final Validator addressValidator;

        public CustomerValidator(Validator customerFieldsValidator,
                                 Validator addressValidator) {
            this.customerFieldsValidator =
                    Objects.requireNonNull(customerFieldsValidator);
            this.addressValidator = Objects.requireNonNull(addressValidator);

            if (!customerFieldsValidator.supports(Customer.class)) {
                throw new IllegalArgumentException(
                        "Customer fields validator must support Customer");
            }
            if (!addressValidator.supports(Address.class)) {
                throw new IllegalArgumentException(
                        "Address validator must support Address");
            }
        }

        @Override
        public boolean supports(Class<?> type) {
            return Customer.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Customer customer = (Customer) target;

            // Same target, no need to change nested path.
            ValidationUtils.invokeValidator(
                    customerFieldsValidator, customer, errors);

            Address address = customer.getAddress();
            if (address == null) {
                errors.rejectValue("address", "address.required",
                        "Address is required");
                return;
            }

            // Different target: switch error context to the address branch.
            errors.pushNestedPath("address");
            try {
                ValidationUtils.invokeValidator(
                        addressValidator, address, errors);
            } finally {
                errors.popNestedPath();
            }
        }
    }

    public static void main(String[] args) {
        Validator customerValidator = new CustomerValidator(
                new CustomerFieldsValidator(),
                new AddressValidator());

        List<Customer> samples = List.of(
                new Customer("An", "an@example.com",
                        new Address("Hanoi", "10000")),
                new Customer(" ", "", new Address(" ", "")),
                new Customer("Mai", "mai@example.com", null));

        for (int index = 0; index < samples.size(); index++) {
            Customer customer = samples.get(index);
            BeanPropertyBindingResult errors =
                    new BeanPropertyBindingResult(customer, "customer");

            ValidationUtils.invokeValidator(
                    customerValidator, customer, errors);

            // Verify parent restored the nested path.
            if (!errors.getNestedPath().isEmpty()) {
                throw new IllegalStateException("Nested path was not reset");
            }

            List<FieldError> fieldErrors = errors.getFieldErrors()
                    .stream()
                    .sorted(Comparator.comparing(FieldError::getField))
                    .toList();

            System.out.println("Sample " + (index + 1) + ": "
                    + fieldErrors.size() + " error(s)");
            for (FieldError error : fieldErrors) {
                System.out.println("  " + error.getField()
                        + " -> " + error.getDefaultMessage());
            }
        }
    }
}
```

Run using Gradle Wrapper if the project has one (`./gradlew run` on Unix or `gradlew.bat run` on Windows); if Gradle is installed without a wrapper, run `gradle run`. Gradle fetches dependencies from Maven Central if the environment allows.

Output of `main`, alongside task lines printed by Gradle:

```text
Sample 1: 0 error(s)
Sample 2: 4 error(s)
  address.city -> City is required
  address.postalCode -> Postal code is required
  email -> Email is required
  firstName -> First name is required
Sample 3: 1 error(s)
  address -> Address is required
```

The output is sorted using `Comparator.comparing(FieldError::getField)` so the example produces a deterministic order. Spring itself does not guarantee sorting `FieldError`s alphabetically by field name.

### Analyzing Each Case

**Sample 1:** `CustomerFieldsValidator` records no errors; `AddressValidator` also records no errors. Both were invoked through the parent validator on the same `Errors`, so `getFieldErrors()` is empty.

**Sample 2:** `firstName` and `email` are empty on the root object; `city` and `postalCode` are whitespace-only or empty on the address. That makes **4 errors** total, with the two nested errors prefixed with `address.`. Had `pushNestedPath` been forgotten, the child validator would have looked up `city`/`postalCode` on `Customer`, causing a property access failure or wrong paths.

**Sample 3:** `address == null`. The parent validator records exactly **one error** on `address` and does not delegate to `AddressValidator`. Thus no `address.city` or `address.postalCode` errors are generated from a nonexistent address.

## 5. Deep Dive into Error Aggregation

In the example, `BeanPropertyBindingResult(customer, "customer")` holds a reference to the **root Customer**. As the parent validator sequentially invokes child validators, both receive this exact `errors` instance. Each `rejectValue` call adds a `FieldError` carrying useful metadata:

| FieldError Property | Meaning |
| --- | --- |
| `getField()` | Full field name, e.g., `address.city`. |
| `getCode()` and `getCodes()` | Error codes resolved by `MessageCodesResolver`, potentially including variants with object/field/type names. |
| `getDefaultMessage()` | Fallback message in the example. |
| `getRejectedValue()` | Rejected value when determinable; be careful when logging or returning it since it may be sensitive. |
| `getObjectName()` | Root object name, here `customer`. |

`errors.hasErrors()` answers whether any error exists; `errors.hasFieldErrors("address.city")` or `errors.getFieldErrors("address.city")` lets you inspect a specific branch. `errors.getGlobalErrors()` holds only object-level errors and does not substitute for `getFieldErrors()`.

Note that `Errors` is **not thread-safe**: each validation pass needs its own instance. Validators must not store `Errors` or request objects in shared fields; that allows Spring singleton validators to be reused across requests safely as long as their own dependencies are thread-safe.

## 6. Composing Multiple Same-Type Validators into a Group

Data does not always have a parent–child relationship. Sometimes you want a list of validators all checking the same `Customer` type: one checks the name, one checks the email, and one checks cross-field consistency.

You can organize a list of child validators and invoke each in turn via `ValidationUtils.invokeValidator(...)`. The snippet below is a **structural variant**, shown separately and not needed in the complete program above:

```java
final class CompositeCustomerValidator implements Validator {
    private final List<Validator> delegates;

    CompositeCustomerValidator(List<Validator> delegates) {
        this.delegates = List.copyOf(delegates);
        for (Validator delegate : this.delegates) {
            if (!delegate.supports(ValidationCompositionDemo.Customer.class)) {
                throw new IllegalArgumentException(
                        "Delegate must support Customer");
            }
        }
    }

    @Override
    public boolean supports(Class<?> type) {
        return ValidationCompositionDemo.Customer.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        for (Validator delegate : delegates) {
            ValidationUtils.invokeValidator(delegate, target, errors);
        }
    }
}
```

To compile this variant standalone, add imports for `java.util.List`, `org.springframework.validation.Validator`, `Errors`, and `ValidationUtils`, and place it in a package that can access `ValidationCompositionDemo.Customer`. Every delegate in the list must **support the same `Customer` object**. Do not put `AddressValidator` directly into a same-target list and pass `Customer`: `supports` will reject it. For nested-object validators, you still need a delegation branch and `pushNestedPath` as in the main example.

Do not automatically skip a delegate merely because earlier delegates recorded errors. Whether to run all delegates to report all errors at once or stop early for a specific reason is a design decision. Stopping early often hurts UX because users only see errors one by one. However, skip steps that depend on missing or already-invalid prerequisite data to avoid exceptions and misleading messages.

## 7. Validating Nested Paths for Lists and Multiple Levels

If a parent object has both `shippingAddress` and `billingAddress`, the same `AddressValidator` can be reused for each branch. Each time, set the appropriate path before delegating:

```java
errors.pushNestedPath("shippingAddress");
try {
    ValidationUtils.invokeValidator(addressValidator,
            order.getShippingAddress(), errors);
} finally {
    errors.popNestedPath();
}

errors.pushNestedPath("billingAddress");
try {
    ValidationUtils.invokeValidator(addressValidator,
            order.getBillingAddress(), errors);
} finally {
    errors.popNestedPath();
}
```

This snippet illustrates the syntax for an `order` object and a validator declared elsewhere; invoke each only when the corresponding address is **non-null**. Resulting paths take the form `shippingAddress.city` and `billingAddress.city`. You can extract the null check into a helper method to avoid repetition, while keeping each branch's path and required-ness policy explicit.

For deeper structures, calling `pushNestedPath("shippingAddress")` followed by `pushNestedPath("contact")` produces paths like `shippingAddress.contact.*`; balance every `push` with a `pop` in `finally`. For collections, paths can include indices like `items[0].code`, provided the root object and `Errors` implementation support indexed property access.

If you use `DirectFieldBindingResult` instead of `BeanPropertyBindingResult`, field values are read directly from fields rather than getters. Choose a binding mechanism matching your data structure and consistent with how Spring reads the properties to validate.

## 8. Integrating into DataBinder and Spring MVC

### 8.1. Plain DataBinder

When you do not want to construct `BindingResult` yourself, you can register the parent validator on a `DataBinder`:

```java
Customer customer = new Customer(
        " ", "", new Address("", ""));

DataBinder binder = new DataBinder(customer, "customer");
binder.setValidator(new CustomerValidator(
        new CustomerFieldsValidator(), new AddressValidator()));
binder.validate();

BindingResult result = binder.getBindingResult();
// result.getFieldErrors() contains errors from the child validators.
```

This is an **excerpt**, requiring `Customer`, `Address`, and the validators from the example, plus Spring imports for `DataBinder` and `BindingResult`. In the example file, the validators are declared inside `ValidationCompositionDemo`, so reference them by their nested names or place this snippet in the same class. The output of `binder.validate()` is aggregated into one `BindingResult`; in this snippet, HTTP parameter binding has not occurred because we passed a pre-built Java object.

### 8.2. In a Spring MVC Controller

Once `CustomerValidator` is a Spring bean, you can add it to a controller's binder using `@InitBinder`:

```java
@InitBinder("customer")
void initCustomerBinder(WebDataBinder binder) {
    binder.addValidators(customerValidator);
}
```

This is a **controller configuration snippet**, assuming `customerValidator` was constructor-injected and supports the object bound under the name `customer`. A parameter like `@Valid @ModelAttribute("customer") CustomerForm form` triggers validation in the MVC flow and places errors into `BindingResult` if the controller signature declares `BindingResult` right after the validated parameter. In a real application, `CustomerForm` must be bindable from a request and supported by the validator; the immutable `Customer` class in the console demo lacks setters and is therefore not typical for form binding.

`binder.addValidators(...)` appends to existing validators; `binder.setValidator(...)` replaces the current validator. Use `addValidators` when you want to combine existing checks (such as Bean Validation) with custom Spring Validator rules; avoid running the same rule twice via two different mechanisms. `@InitBinder` is scoped to its controller/object and does not make the validator global automatically.

Spring also supports validation for `@RequestBody` and Jakarta Bean Validation. However, placing `@Valid` on a nested field in a Jakarta DTO **does not automatically invoke** a custom `org.springframework.validation.Validator` you wrote. To achieve the delegation behavior shown here, register or invoke the Spring validator in the appropriate flow.

## 9. Designing Maintainable Validator Composition

**Each validator should own one group of rules with a single reason to change.** `AddressValidator` knows only `Address` structure and constraints; it does not care whether its parent is `Customer`, `Order`, or something else. The parent validator only checks branch presence, picks the delegate, and manages the path.

**Verify `supports` when wiring.** The parent validator's constructor rejects a delegate that does not support the expected type, catching configuration mistakes early. `ValidationUtils.invokeValidator` also re-checks compatibility at call time.

**Do not instantiate delegates on every request.** With Spring IoC, declare validators as beans, inject them via constructor, and let the parent call them. Validators should hold no mutable per-request state; a fresh `Errors` instance is created per validation pass.

**Separate input validation from business-rule checks.** Required fields and local cross-field relationships belong in `Validator`. Checks requiring the database, identity, transactions, or resource availability generally belong in the appropriate service/domain layer; avoid slow network calls or uncontrolled data access inside form-binding validators.

**Use stable error codes.** Use codes like `address.required` and resolve messages via `MessageSource` instead of coupling clients to hardcoded English strings. When building APIs, avoid logging or echoing back `rejectedValue` if it may hold passwords, sensitive identifiers, or private data.

## 10. Testing Key Scenarios

| Scenario | What to Verify |
| --- | --- |
| Valid object | No `FieldError` or object-level error. |
| Empty root fields | Errors attached accurately to `firstName`/`email`. |
| Empty address fields | Errors attached accurately to `address.city`/`address.postalCode`. |
| `address` is `null` | Only an `address` error if that branch is required; no exception thrown. |
| Multiple errors across branches | All present in the **same** `BindingResult`. |
| Wrong-type delegate | Rejected with a configuration error instead of an input error. |
| Delegate throws exception | `errors.getNestedPath()` is restored thanks to `finally`. |
| Concurrent requests | No `Errors` or request objects shared across threads. |
| Using `@InitBinder` | Validator bound to the right object name; errors accessible via `BindingResult`. |

When using JUnit, assert directly on `errors.hasFieldErrors("address.city")`, `errors.getFieldErrorCount()`, and `errors.getNestedPath()`. Do not assert on error ordering unless your code explicitly sorts them.

## 11. Common Mistakes and Fixes

1. **Passing the wrong type to a delegate:** `AddressValidator` expects `Address`, not `Customer`. Verify `supports` and `invokeValidator` calls.
2. **Forgetting `pushNestedPath`:** `AddressValidator` calls `rejectValue("city", ...)` while `Errors` points at the root; error paths become wrong or field value lookups fail.
3. **Forgetting `popNestedPath`:** subsequent errors retain the previous branch's prefix. Always put `pop` inside `finally`.
4. **Calling a child validator with `null`:** the validator's cast or property read can fail. Decide the `null` policy in the parent validator.
5. **Creating a separate `Errors` per delegate and discarding results:** the caller misses errors. Share a single `Errors` instance when the structure allows.
6. **Using `reject(...)` for a single-field error:** the error ends up at object level. Use `rejectValue(...)` to produce a `FieldError` tied to the field.
7. **Duplicating rules across delegates:** the same field gets checked twice by two delegates, producing duplicate errors. Partition responsibilities cleanly.
8. **Confusing `@Valid` with Spring Validator:** Jakarta's `@Valid` does not automatically run unregistered custom Spring delegate classes.
9. **Sharing `Errors` on a singleton bean:** error state leaks between concurrent requests. Validators hold dependencies; `Errors` lives per request.
10. **Ignoring binding/conversion errors:** validators do not replace converting HTTP string parameters into target Java types.

## 12. Self-Study Questions

1. If `CustomerValidator` invokes `AddressValidator` without `pushNestedPath("address")`, what happens when the child validator checks `city`?
2. Why is `try/finally` necessary even when `AddressValidator` is only a few lines long?
3. If the same `AddressValidator` is reused for shipping and billing addresses, what needs to change in `Errors`'s path?
4. When `address == null`, what error should the parent validator record, and when can it skip validation?
5. How does a list of child validators all checking `Customer` differ from delegating to `AddressValidator`?
6. When should checks live in a Spring Validator versus in a service/domain layer?

If you can explain in your own words that **the parent validator decides whom to call and sets the path context, child validators enforce their own rules, and `Errors` accumulates every result**, you have mastered delegation-based validator composition.

**References:**
- [Spring Framework 6.2 — Validation Using Spring's Validator Interface](https://docs.spring.io/spring-framework/reference/6.2/core/validation/validator.html)
- [Spring Framework 6.2 — Resolving Codes to Error Messages](https://docs.spring.io/spring-framework/reference/6.2/core/validation/conversion.html)
- [Spring — ValidationUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/ValidationUtils.html)
- [Spring — Errors Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/Errors.html)
