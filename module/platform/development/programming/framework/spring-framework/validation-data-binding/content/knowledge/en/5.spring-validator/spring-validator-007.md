# pushNestedPath and popNestedPath for Validating Nested Objects with Spring Validator

In Spring Framework, a `Validator` can validate a root object and delegate validation of an object-typed property to another validator. For instance, `Customer` has `Address address`; the `Address` validator knows only the `city` and `postalCode` fields, while errors returned to the user must specify `address.city` and `address.postalCode`. The two methods **`Errors.pushNestedPath(String)`** and **`Errors.popNestedPath()`** allow reusing child validators in the right context without manually concatenating paths on every statement.

This article explains the nested-path stack mechanism, the push/validate/pop order, handling `null` child objects, a runnable Java 17 example with Spring, and common pitfalls. Objects are validated via `org.springframework.validation.Validator` without needing an HTTP request; Spring MVC can use the same mechanism when processing form data.

## 1. The Problem: Child Object Errors Need Paths from the Root Object

Suppose the data has this structure:

```text
Customer
├── fullName = "Lan"
├── address: Address
│   ├── city = ""
│   └── postalCode = "12"
└── contactEmail = "lan@example.org"
```

Inside `AddressValidator`, the simplest check is:

```java
ValidationUtils.rejectIfEmptyOrWhitespace(errors, "city", "required");
```

However, when `Address` is part of `Customer`, the failing field must be recorded under the full name **`address.city`**, because the user or application receiving the result is working with the root object. At deeper nesting levels, names look like `billingAddress.country.code` or `items[0].name`.

An error-prone approach is hardcoding `"address.city"` inside `AddressValidator`. That ties the validator to living under the `address` property and breaks when reused for `shippingAddress` or `billingAddress`.

Spring's solution is maintaining a **current path** inside `Errors`. The child validator uses relative property names like `"city"`. The parent validator switches context before invoking it, then restores it afterward.

## 2. Related Components

| Component | Responsibility |
| --- | --- |
| `org.springframework.validation.Validator` | Defines `supports(Class<?>)` and `validate(Object, Errors)`; validates objects and reports errors |
| `org.springframework.validation.Errors` | Collects object/field errors; maintains the nested path and supports error lookup |
| `BindingResult` | Extends `Errors` with binding result details, commonly used in Spring MVC or `DataBinder` |
| `BeanPropertyBindingResult` | `BindingResult` implementation using JavaBean property access, supporting nested fields |
| `ValidationUtils.rejectIfEmptyOrWhitespace(...)` | Looks up field values and adds an error when `null`, empty, or whitespace-only |
| `ValidationUtils.invokeValidator(...)` | Verifies target compatibility with `supports(...)` and invokes the corresponding validator |

The term **nested path** here means a property path identifying a property inside an object—not a filesystem directory, not a URL, and not an operation that instantiates child objects. Calling `pushNestedPath("address")` does not call `getAddress()`, does not assign field values, and does not change the root target of `BeanPropertyBindingResult`; it alters **the field-name context for recording and reading errors**.

## 3. `pushNestedPath`, `popNestedPath`, and `getNestedPath`

### `pushNestedPath(String subPath)`

Pushes the current path onto a stack and switches to the child path. If currently at the root (`""`), calling:

```java
errors.pushNestedPath("address");
```

makes `errors.getNestedPath()` become `"address."`. If already at `"customer."` and you push `"address"`, the new path becomes `"customer.address."`. Spring manages the dot separator; normally pass the **segment name** `"address"` rather than adding `"."` everywhere manually.

Within the `"address."` context, calling:

```java
errors.rejectValue("city", "required");
```

records a `FieldError` whose `getField()` is `"address.city"`. The error code `"required"` is a logical code for message resolution; it is **not** a field name.

### `popNestedPath()`

Restores the path **immediately preceding the corresponding push**:

```java
errors.pushNestedPath("address");
try {
    // Validate address fields
} finally {
    errors.popNestedPath();
}
```

After popping, `getNestedPath()` returns to `""` if it was previously at root. If it was `"customer."` before pushing, it is restored to `"customer."`; popping does not necessarily return to the root.

**Mandatory rule:** every successful push requires a matching pop. Place `popNestedPath()` in `finally` so the path is still restored if the child validator throws an exception. Calling `popNestedPath()` when the stack has no prior path causes Spring to throw `IllegalStateException`.

### Stack State Transition Table

| Action | `getNestedPath()` | Relative field `"city"` resolves to |
| --- | --- | --- |
| Initial | `""` | `city` |
| `pushNestedPath("address")` | `"address."` | `address.city` |
| `pushNestedPath("billing")` | `"address.billing."` | `address.billing.city` |
| `popNestedPath()` | `"address."` | `address.city` |
| `popNestedPath()` | `""` | `city` |

The `"address.billing."` level merely illustrates path composition; for `rejectValue("city", ...)` to read values cleanly with `BeanPropertyBindingResult`, the target object must actually have that property path.

**Note:** `popNestedPath()` only restores the context; it **does not clear recorded `FieldError`s** or revert object values. Errors named `address.city` remain after returning to root.

## 4. Standard Pattern When a Validator Calls a Child Validator

Separate the two responsibilities:

- `CustomerValidator` knows the root object has an `address` field.
- `AddressValidator` knows only `Address` properties: `city`, `postalCode`.

Key invocation pattern:

```java
if (customer.getAddress() == null) {
    errors.rejectValue("address", "address.required");
} else {
    errors.pushNestedPath("address");
    try {
        ValidationUtils.invokeValidator(
                addressValidator, customer.getAddress(), errors);
    } finally {
        errors.popNestedPath();
    }
}
```

Why each line matters:

1. **Check `null` before pushing.** If `customer.getAddress()` is missing, record an error on `address` at the parent level. Invoking the child validator with `null` may violate its contract and raise an error instead of recording a useful `FieldError`.
2. **Push the parent's exact property name.** `"address"` is the property name on `Customer`, not the class name `Address`.
3. **Pass the child object as the target to the child validator.** `ValidationUtils.invokeValidator(addressValidator, customer.getAddress(), errors)` verifies compatibility via `supports` and invokes `validate`.
4. **Pass the same `Errors`.** The child validator appends errors into the same root result; the nested path turns short field names into full ones.
5. **Pop in `finally`.** Subsequent parent checks, such as `"contactEmail"`, must run back at root level. Without popping, `"contactEmail"` would be misinterpreted as `"address.contactEmail"`.

For a non-null child object, `AddressValidator` can be written independently:

```java
@Override
public void validate(Object target, Errors errors) {
    Address address = (Address) target;
    ValidationUtils.rejectIfEmptyOrWhitespace(
            errors, "city", "city.required");
    if (address.getPostalCode() == null
            || !address.getPostalCode().matches("\\d{5}")) {
        errors.rejectValue("postalCode", "postalCode.invalid");
    }
}
```

Here the child validator **does not know** whether it is validating `address`, `shippingAddress`, or `billingAddress`. Whichever name the parent pushes beforehand becomes the prefix for recorded errors. `ValidationUtils.rejectIfEmptyOrWhitespace` reads values through `Errors`, so with `BeanPropertyBindingResult`, the root object must expose the corresponding path.

## 5. Runnable Example with Java 17 and Spring Framework

This example uses **Spring Core Validation** without starting a web server. It constructs `Customer`, uses `BeanPropertyBindingResult` to hold results, invokes both validators, and prints the failing fields in order.

Create a Gradle project directory with this structure:

```text
nested-validator-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/NestedValidationDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'nested-validator-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'example.NestedValidationDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Spring Framework 6.x requires Java 17 or later; the example pins version `6.2.12` for reproducibility. Gradle fetches transitive dependencies of `spring-context` from Maven Central. Use a compatible JDK 17+ and Gradle; if the project includes a Gradle wrapper, replace `gradle` with `./gradlew`.

**`src/main/java/example/NestedValidationDemo.java`**

```java
package example;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class NestedValidationDemo {

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
        private final String fullName;
        private final Address address;
        private final String contactEmail;

        public Customer(
                String fullName, Address address, String contactEmail) {
            this.fullName = fullName;
            this.address = address;
            this.contactEmail = contactEmail;
        }

        public String getFullName() {
            return fullName;
        }

        public Address getAddress() {
            return address;
        }

        public String getContactEmail() {
            return contactEmail;
        }
    }

    public static final class AddressValidator implements Validator {
        @Override
        public boolean supports(Class<?> type) {
            return Address.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Address address = (Address) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "city", "city.required");

            if (address.getPostalCode() == null
                    || !address.getPostalCode().matches("\\d{5}")) {
                errors.rejectValue("postalCode", "postalCode.invalid");
            }
        }
    }

    public static final class CustomerValidator implements Validator {
        private final Validator addressValidator = new AddressValidator();

        @Override
        public boolean supports(Class<?> type) {
            return Customer.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Customer customer = (Customer) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "fullName", "fullName.required");

            if (customer.getAddress() == null) {
                errors.rejectValue("address", "address.required");
            } else {
                errors.pushNestedPath("address");
                try {
                    ValidationUtils.invokeValidator(
                            addressValidator, customer.getAddress(), errors);
                } finally {
                    errors.popNestedPath();
                }
            }

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "contactEmail", "contactEmail.required");
        }
    }

    public static void main(String[] args) {
        Customer customer = new Customer(
                "  ", new Address(" ", "12"), "");
        BeanPropertyBindingResult errors =
                new BeanPropertyBindingResult(customer, "customer");

        new CustomerValidator().validate(customer, errors);

        System.out.println(
                "nestedPathAfter=[" + errors.getNestedPath() + "]");
        System.out.println(
                "fields=" + errors.getFieldErrors().stream()
                        .map(FieldError::getField).toList());
        System.out.println(
                "fieldErrorCount=" + errors.getFieldErrorCount());

        Customer noAddress = new Customer(
                "Lan", null, "lan@example.org");
        BeanPropertyBindingResult missingErrors =
                new BeanPropertyBindingResult(noAddress, "customer");

        new CustomerValidator().validate(noAddress, missingErrors);
        System.out.println(
                "missingAddressFields="
                        + missingErrors.getFieldErrors().stream()
                                .map(FieldError::getField).toList());
    }
}
```

Run from the project directory:

```bash
gradle -q run
```

**Expected stdout** (with JDK 17+ and the dependencies above):

```text
nestedPathAfter=[]
fields=[fullName, address.city, address.postalCode, contactEmail]
fieldErrorCount=4
missingAddressFields=[address]
```

Result breakdown:

- `fullName` is a root-level field containing only whitespace, rejected by `rejectIfEmptyOrWhitespace`.
- `address.city` is the error for `city` in `AddressValidator`, prefixed with `address.` via `pushNestedPath`.
- `address.postalCode` is the error for `postalCode="12"`, failing the five-digit regex.
- `contactEmail` stays a root-level field because `popNestedPath()` ran before the parent validator checked the email.
- `nestedPathAfter=[]` proves the path returned to the empty string (`""`); none of the recorded errors disappeared.
- When `address == null`, the code records a single error for `address` and skips invoking the child validator, avoiding checks on nonexistent properties.

The sample classes use `final` fields and getters because this example **only validates already-constructed objects**. They do not need setters to demonstrate nested validation. If you use these same classes as targets for **property binding** from a form, consider constructor binding or mutable DTOs with setters. `pushNestedPath` does not dictate how objects are instantiated.

## 6. Why Not Hardcode Full Paths Inside the Child Validator?

Compare two styles:

```java
// Hardcoding the position of Address inside Customer:
errors.rejectValue("address.city", "city.required");

// Reusable style inside AddressValidator:
errors.rejectValue("city", "city.required");
```

At the root, the first style produces `address.city`. However, if the parent **already pushed `"address"`**, writing `"address.city"` inside the child risks producing `address.address.city`: the path gets prefixed twice.

With `AddressValidator` using relative field names, the same logic serves two properties:

```java
errors.pushNestedPath("billingAddress");
try {
    ValidationUtils.invokeValidator(
            addressValidator, customer.getBillingAddress(), errors);
} finally {
    errors.popNestedPath();
}

errors.pushNestedPath("shippingAddress");
try {
    ValidationUtils.invokeValidator(
            addressValidator, customer.getShippingAddress(), errors);
} finally {
    errors.popNestedPath();
}
```

These two snippets are **integration illustrations**, assuming `Customer` has `getBillingAddress()` and `getShippingAddress()` returning non-null objects; they are not part of the standalone program in section 5. When the objects and paths are valid, errors are recorded as `billingAddress.city` or `shippingAddress.city` without touching `AddressValidator`.

Key point: **the child validator receives the child target yet records errors into the root result with a dynamic prefix**. This decouples validation logic from where the data sits inside a parent object.

## 7. Multi-Level Nesting and LIFO Behavior

Given a property tree:

```text
Order
└── customer
    └── address
        └── city
```

You can push twice, then pop in reverse order:

```java
errors.pushNestedPath("customer");
try {
    errors.pushNestedPath("address");
    try {
        errors.rejectValue("city", "city.required");
        // FieldError.field == "customer.address.city"
    } finally {
        errors.popNestedPath(); // Back to "customer."
    }
} finally {
    errors.popNestedPath(); // Back to ""
}
```

The snippet above **only illustrates** how paths combine; to run it directly with `BeanPropertyBindingResult`, the root object needs getters for `customer.address.city`. `Errors` maintains a LIFO (*last in, first out*) stack: the last push is popped first.

Never call `popNestedPath()` once expecting to clear multiple levels; it unwinds **one stack level**. If multiple helper methods share the same `Errors`, any helper that pushes must also pop, even when an exception occurs.

## 8. How Does `setNestedPath` Differ from `pushNestedPath`?

Both deal with property path context, but manage state differently:

| Method | Meaning | When to Use |
| --- | --- | --- |
| `setNestedPath("address")` | Resets the current nested path to a specific path | Code explicitly manages state and knows the exact path to set |
| `pushNestedPath("address")` | Saves the current path onto the stack and descends into a branch | A parent validator temporarily invokes a child validator |
| `popNestedPath()` | Restores the path prior to the most recent push | Restoring prior state inside `finally` |
| `getNestedPath()` | Returns the current nested path, typically ending with a dot | Debugging, testing, verifying state after validation |

For multi-level nested validators, `pushNestedPath` + `popNestedPath` avoids manually saving the old string and calling `setNestedPath(oldPath)`. Do not mix `setNestedPath` arbitrarily with push/pop unless ownership of the path state is clear. If several validators share an `Errors`, uphold a balanced push/pop contract.

## 9. Relation to Spring MVC, DataBinder, and Bean Validation

In Spring MVC, a controller may accept:

```java
@PostMapping("/customers")
public String submit(
        @ModelAttribute("customer") CustomerForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "customer-form";
    }
    return "success";
}
```

This is an **illustrative snippet** meant to be placed in a Spring MVC controller with appropriate annotation/class imports and view setup. To execute a Spring `Validator`, invoke it manually in the controller or register it with `WebDataBinder` for the controller scope. Once the validator runs, `BindingResult.getFieldErrors()` lets the view display errors for `address.city` next to the matching input. Full field names also help map errors back to forms, JSON responses, or test assertions.

Distinguish the mechanisms:

- **Data binding**: reads the request, converts types, and populates the object; can produce errors such as `typeMismatch`.
- **Spring `Validator`**: implements `supports` and `validate`, and can use `Errors.rejectValue(...)` alongside `pushNestedPath/popNestedPath`.
- **Jakarta Bean Validation**: uses constraints like `@NotBlank`, `@Size`, `@Valid`; when integrated with Spring, errors can appear in `BindingResult`. In most cases, cascaded `@Valid` does not require you to call `pushNestedPath` manually.

Do not call `pushNestedPath` merely to fake field names when the actual object lacks those nested properties. Error paths must match the data model understood jointly by the controller/binder and the UI.

## 10. Common Pitfalls and Fixes

| Symptom | Common Cause | Solution |
| --- | --- | --- |
| After validating address, email error becomes `address.contactEmail` | Missing `popNestedPath()` | Wrap child validator invocation in `try/finally` |
| Error becomes `address.address.city` | Child validator hardcodes `address.` even though parent already pushed it | Use only `"city"` inside the child validator |
| `IllegalStateException` on pop | Calling pop more times than successful pushes | Match each successful push with one pop |
| `UnsupportedOperationException` on push | Active `Errors` implementation does not support nested paths | Use a compatible implementation such as `BeanPropertyBindingResult`, and verify its contract |
| Exception reading `address.city` | `address == null` or property path does not exist / is inaccessible | Check for null, design model/getters properly, and report an error on the parent field |
| `AddressValidator` rejects target | `supports(Address.class)` returns false or wrong class passed | Check `supports` and the object passed to the validator |
| Error displays on wrong input | Field name from `FieldError.getField()` does not match input name | Align form field names and property paths |
| Child errors vanished after pop? | Mistakenly thinking pop clears errors | Pop only changes context; inspect `getFieldErrors()` |
| Validator pushed, then exited early on exception | Pop placed at method end instead of `finally` | Put pop inside `finally` immediately after push |
| Multiple threads share one `Errors` | `Errors` and nested path state used as shared mutable context | Create or obtain a separate result per validation pass; never share across requests/threads |

A subtle detail: `Errors.rejectValue(...)` and `ValidationUtils.rejectIfEmptyOrWhitespace(...)` operate on field paths and may access values on the object to populate error metadata. If a nested object is `null` or a path does not exist, merely pushing a prefix cannot fix a missing object structure. When a child field is absent, it is usually better to report the error on the parent field before descending.

## 11. Testing Accurate Paths and Guaranteed Restoration

For `CustomerValidator` in the example, test these invariants:

1. Invalid `city` with non-null `address` → `getFieldError("address.city")` is non-null.
2. Invalid `postalCode` → `getFieldError("address.postalCode")` is non-null.
3. Invalid `contactEmail` after the child validator runs → error is named `"contactEmail"`, with no `"address."` prefix.
4. After `validate` → `errors.getNestedPath().equals("")` when starting from root.
5. `address == null` → error recorded on `"address"`; child validator is not invoked.
6. If the child validator throws an exception, the parent still restores the nested path via `finally`; verify this using a fake validator that intentionally throws `IllegalArgumentException`.

Example assertions for a case after running the validator (Java 17, Spring libraries, snippet using `errors` from section 5):

```java
assert errors.getFieldError("address.city") != null;
assert errors.getFieldError("address.postalCode") != null;
assert errors.getFieldError("contactEmail") != null;
assert errors.getNestedPath().isEmpty();
```

Java `assert` statements are disabled by default; to run them on the JVM, pass `-ea` or use JUnit/AssertJ in an actual test. When testing exception recovery separately, note that error counts may vary depending on where the child throws; the critical invariant is that the path was popped.

### Self-Practice Exercise

Given `Order` with `billingAddress` and `shippingAddress`, both of type `Address` containing `city`. Write an `AddressValidator` that checks only the relative field `"city"`. In `OrderValidator`, call `pushNestedPath("billingAddress")` before the first child validator and `pushNestedPath("shippingAddress")` before the second, each with a `finally` pop. If both cities are empty, explain why two `FieldError`s with different names are produced.

**Guided answer:** because `Errors` prepends the active path to the relative name `"city"`, the results are `billingAddress.city` and `shippingAddress.city`. Because each pop completes cleanly, the next validation begins back in the root context. That is the primary benefit of the nested-path stack: **reusing child validators while preserving exact error names on the root object**.

## Official Reference Documentation

- [Spring Framework — Validation Using Spring's Validator Interface](https://docs.spring.io/spring-framework/reference/core/validation/validator.html): child validator pattern with `pushNestedPath` and `popNestedPath`.
- [Spring Framework — Errors API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/Errors.html): nested-path stack contract, `getNestedPath`, `rejectValue`, and `FieldError`.
- [Spring Framework — ValidationUtils API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/ValidationUtils.html): `invokeValidator` and `rejectIfEmptyOrWhitespace`.
- [Spring Framework — BeanPropertyBindingResult API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/BeanPropertyBindingResult.html): error management and JavaBean property access, including nested properties.
