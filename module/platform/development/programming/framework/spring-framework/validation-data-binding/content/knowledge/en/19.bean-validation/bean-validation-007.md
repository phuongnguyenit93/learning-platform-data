# `propertyPath`, `invalidValue`, `message`, and `messageTemplate` in Bean Validation

## 1. Goal: Reading a Validation Error Accurately

When an object fails a Bean Validation constraint, the Jakarta Validation API returns a set of `ConstraintViolation<T>`. Each element describes **one violated constraint**, including the error location, the checked value, and message details. The four components to distinguish are:

| API Property | Return Type | Question Answered |
| --- | --- | --- |
| `getPropertyPath()` | `jakarta.validation.Path` | At **which path**, starting from the validated root object, did the violation occur? |
| `getInvalidValue()` | `Object` | **Which value** was passed to the constraint validator and failed? |
| `getMessage()` | `String` | What is the **interpolated message** for this violation? |
| `getMessageTemplate()` | `String` | What is the **original message template, prior to interpolation**, of the violation? |

For example, a `reference` field has `@Size(min = 4, message = "Code requires at least {min} characters")` and receives `"AB"`:

```text
propertyPath    = reference
invalidValue    = "AB"
message         = Code requires at least 4 characters
messageTemplate = Code requires at least {min} characters
```

`{min}` is taken from the annotation's `min = 4` attribute. In this simple example, `invalidValue` is the field value; however, for **class-level constraints**, method parameters, or collection elements, do not assume it is always the value of a field sharing the path's name.

After this lesson, you will be able to read and interpret the four components from `ConstraintViolation`, display errors safely, understand the relationship with `BindingResult` in Spring MVC, and test nested objects, collections, interpolation, and type conversion errors.

## 2. When Is `ConstraintViolation<T>` Produced?

Example with Jakarta Validation:

```java
Validator validator = validatorFactory.getValidator();
Set<ConstraintViolation<OrderForm>> violations =
        validator.validate(orderForm);
```

This is an **illustrative snippet**, requiring `Validator`, `ValidatorFactory`, and `ConstraintViolation` from `jakarta.validation.*` along with initialized objects. `Validator.validate(object)` returns a **Set** of violations for the object and objects cascaded via `@Valid`; element order is **not guaranteed**. An empty set means no violations were found in the evaluated constraint groups; it does not mean the data satisfies every business rule.

Each violation also has `getRootBean()`, `getRootBeanClass()`, `getLeafBean()`, and `getConstraintDescriptor()`. Those four primary pieces of information should be read in that context when multiple object levels exist.

Distinguish **error flow** from **validation execution path**:

```text
HTTP/form String --Spring data binding--> Java object
                                       |
                                       v
                            Jakarta Bean Validation
                                       |
                                       v
                           ConstraintViolation<T>
                                       |
                                       v
                        Spring BindingResult / FieldError
```

Spring must convert strings into the right Java types **before** the validator checks constraints such as `@Size`, `@Min`, or custom constraints. If `"abc"` fails to convert to `Integer`, that may be a **`typeMismatch` binding error**, not a `ConstraintViolation<Integer>`; thus not every `FieldError` carries all four Jakarta Validation fields.

## 3. `getPropertyPath()`: Error Location Structure

API signature:

```java
Path path = violation.getPropertyPath();
String displayPath = path.toString();
```

`Path` is a **structured object**, not merely a `String`. When validating an `OrderForm` object containing `@Valid Address shipping` and `Address.zip` fails a pattern, the typical path is:

```text
shipping.zip
```

`Path` consists of `Path.Node` instances. Each node can report `getName()`, `getKind()`, `isInIterable()`, `getIndex()`, or `getKey()`. Common node kinds via `jakarta.validation.ElementKind` include `PROPERTY`, `BEAN`, `METHOD`, `PARAMETER`, `RETURN_VALUE`, `CROSS_PARAMETER`, and `CONTAINER_ELEMENT`.

### 3.1. Paths of different constraint forms

| Constraint Location | Example Path via `toString()` | Meaning |
| --- | --- | --- |
| Direct property | `customerName` | Field on the root bean |
| Property in a `@Valid` nested object | `shipping.zip` | Traverses from root bean through property `shipping` |
| Element of `List<@NotBlank String>` | May be `tags[0].<list element>` | Includes container element node and index; rendering syntax depends on provider |
| Map element | May include key such as `options[K]` | Inspect `getKey()`, `ElementKind`, and full path |
| Class-level constraint on root bean | Usually an empty path (`""`) | Error relates to the whole bean, not bound to a field |
| Method parameter/return value constraint | Contains method, parameter/return value nodes | Not a regular form field path |

Strings like `<list element>` or parameter names can vary by **provider/configuration**. In particular, method parameter names depend on `ParameterNameProvider` and parameter-name metadata availability. Do not split the path string with `split("\\.")` and assume every segment is a property, because collection indices, Map keys, and container nodes have their own structure.

### 3.2. When exact path handling is needed

The following code is an **excerpt** inside a violation loop; requires importing `jakarta.validation.Path` and `jakarta.validation.ElementKind`:

```java
for (Path.Node node : violation.getPropertyPath()) {
    String name = node.getName();
    ElementKind kind = node.getKind();

    if (node.isInIterable()) {
        Integer index = node.getIndex(); // List/array: may be non-null
        Object key = node.getKey();      // Map: may be non-null
        // Handle index/key according to the node's actual structure.
    }

    if (kind == ElementKind.PROPERTY) {
        // name is the property name of this node.
    }
}
```

When returning `field` to the UI, translate from nodes according to **an application-defined field naming convention**, especially for lists or maps. `path.toString()` is very convenient for logs/tests, but it is not automatically a JSON Pointer, is not guaranteed to match JSON field names, and does not necessarily correspond to a single HTML input element.

## 4. `getInvalidValue()`: The Value Actually Checked

`violation.getInvalidValue()` returns `Object`, which may be a `String`, `Integer`, collection element, object, `null`, or custom type. Under Jakarta Validation, this is **the value passed to the constraint check** (`isValid`), not a copy guaranteed to be the raw string entered by the user.

Important cases:

1. **Field constraint:** `@Size` applied to `reference = "AB"` → `getInvalidValue()` returns `"AB"`.
2. **Nested property constraint:** `shipping.zip = "12x"` → returns `"12x"` when the constraint applies directly to `zip`; `getPropertyPath()` contains `shipping.zip`.
3. **Class-level constraint:** the checked value is typically **the entire object** annotated with the constraint, not a specific field.
4. **Container element constraint:** the returned value is the invalid **element**, e.g., `""` in `List<@NotBlank String>`.
5. **Method/constructor cross-parameter constraint:** the value can be an `Object[]` containing the checked arguments.
6. **Constraint on a `null` value:** `getInvalidValue()` can return `null`, e.g., `@NotNull`. Do not call `.toString()` without checking for null.

Additionally, `getRootBean()` is the root object passed to `Validator.validate(...)`; `getLeafBean()` points to the nearest bean containing the constraint per the spec context. The three values `rootBean`, `leafBean`, and `invalidValue` **are not always the same object**. With `Validator.validateValue(SomeClass.class, "field", value)`, `getRootBean()` may be `null` because no actual bean instance exists.

**Security note:** do not automatically return `invalidValue` in HTTP responses or log it verbatim. It may be a password, token, personal data, an object whose `toString()` exposes internal state, or large data. For debugging, use error type, filtered path, and correlation ID; if the value is genuinely needed, log only a masked/redacted form per policy. In Spring, `FieldError.getRejectedValue()` should be handled under the same principle.

## 5. `getMessage()` and `getMessageTemplate()`: Interpolation vs Keeping the Template

Suppose the annotation is:

```java
@Size(
    min = 4,
    max = 10,
    message = "Code requires at least {min} characters"
)
private String reference;
```

With `reference = "AB"`, a violation has:

```text
getMessage()         -> "Code requires at least 4 characters"
getMessageTemplate() -> "Code requires at least {min} characters"
```

`getMessage()` returns the interpolated result; `getMessageTemplate()` returns the original template prior to interpolation. **Templates do not have to contain placeholders.** For example, `@NotBlank(message = "Name must not be blank")` returns the same string from both methods.

### 5.1. A message template can be a resource bundle key

Another declaration:

```java
@NotBlank(message = "{order.customer.required}")
private String customerName;
```

And `ValidationMessages.properties` on the classpath:

```properties
order.customer.required=Customer name is required
```

When the provider and resource bundle are properly configured, `getMessageTemplate()` remains `"{order.customer.required}"`; `getMessage()` is the resolved and interpolated message, such as `"Customer name is required"`.

For the Vietnamese locale, you can have `ValidationMessages_vi.properties` containing translated messages. The locale **is chosen according to the message interpolator strategy and framework integration**, not simply inferred from a request having an `Accept-Language` header. When testing multiple languages, verify the locale resolver, `MessageInterpolator`, `MessageSource` (if Spring-integrated), and bundle files in the actual environment.

### 5.2. Templates containing annotation attributes or expressions

In messages, `{min}` and `{max}` typically reference constraint attributes. Jakarta Validation also specifies that message interpolation may support EL expressions `${...}` depending on configuration/provider; that is a different mechanism from **reading the raw template**.

- `getMessageTemplate()` is valuable for diagnostics, error statistics, or as input to a custom translation layer.
- `getMessage()` is more suitable for displaying the message processed by the provider.
- **Do not assume** the template is always a stable key code: it can be a full Vietnamese sentence, a bundle key, or a string containing placeholders.
- If a stable API error code such as `ORDER_REFERENCE_TOO_SHORT` is needed, define a dedicated code or map from constraint metadata; do not use raw messages as immutable identifiers.
- Do not let users supply message template expressions and pass them directly into the interpolation engine; templates are server-side configuration whose source must be controlled.

## 6. Complete Java 17+ Example: Reading All Four Details

The example uses **Jakarta Validation 3.0 via Hibernate Validator 8.x** and **Spring Framework 6.2.x**. The program checks three errors: a blank root field, an insufficiently long field, and a pattern mismatch on a nested object field. It then shows Spring mapping the errors into `BindingResult`.

### 6.1. Maven

Create `pom.xml` in the project directory:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>violation-details</artifactId>
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

Hibernate Validator is an implementation of Jakarta Validation. The `jakarta.el` dependency supports message interpolation using Expression Language. With Spring Boot, you normally let Boot's dependency management pick compatible versions and add starter-validation; the Maven example here pins versions for reproducibility.

### 6.2. Java Code

Create `src/main/java/example/ConstraintViolationDemo.java`:

```java
package example;

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
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.beanvalidation.SpringValidatorAdapter;

public final class ConstraintViolationDemo {

    public static final class Address {
        @Pattern(
            regexp = "\\d{5}",
            message = "Postal code requires 5 digits"
        )
        private String zip;

        public Address(String zip) {
            this.zip = zip;
        }

        public String getZip() {
            return zip;
        }

        public void setZip(String zip) {
            this.zip = zip;
        }
    }

    public static final class OrderForm {
        @NotBlank(message = "Name must not be blank")
        private String customerName;

        @Size(min = 4, max = 10,
              message = "Code requires at least {min} characters")
        private String reference;

        @Valid
        private Address shipping;

        public OrderForm(String customerName,
                         String reference,
                         Address shipping) {
            this.customerName = customerName;
            this.reference = reference;
            this.shipping = shipping;
        }

        public String getCustomerName() {
            return customerName;
        }

        public void setCustomerName(String customerName) {
            this.customerName = customerName;
        }

        public String getReference() {
            return reference;
        }

        public void setReference(String reference) {
            this.reference = reference;
        }

        public Address getShipping() {
            return shipping;
        }

        public void setShipping(Address shipping) {
            this.shipping = shipping;
        }
    }

    private static String show(Object value) {
        return value == null ? "<null>" : "\"" + value + "\"";
    }

    public static void main(String[] args) {
        OrderForm order = new OrderForm(
                " ", "AB", new Address("12x"));

        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            Set<ConstraintViolation<OrderForm>> found =
                    validator.validate(order);

            // Set does not guarantee order; sort by path for stable output.
            List<ConstraintViolation<OrderForm>> violations =
                    new ArrayList<>(found);
            violations.sort(Comparator.comparing(
                    v -> v.getPropertyPath().toString()));

            for (ConstraintViolation<OrderForm> v : violations) {
                System.out.println(
                    v.getPropertyPath() +
                    " | invalid=" + show(v.getInvalidValue()) +
                    " | message=" + v.getMessage() +
                    " | template=" + v.getMessageTemplate());
            }
            System.out.println("violationCount=" + violations.size());

            // Reuse the same Jakarta Validator via Spring's adapter.
            SpringValidatorAdapter adapter =
                    new SpringValidatorAdapter(validator);

            BeanPropertyBindingResult result =
                    new BeanPropertyBindingResult(order, "order");
            adapter.validate(order, result);

            FieldError referenceError =
                    result.getFieldError("reference");
            if (referenceError == null) {
                throw new AssertionError(
                        "Missing reference FieldError");
            }
            System.out.println(
                    "springFieldErrors=" + result.getFieldErrorCount());
            System.out.println(
                    "springReference=" + referenceError.getField() +
                    " | rejected=" +
                    show(referenceError.getRejectedValue()) +
                    " | message=" +
                    referenceError.getDefaultMessage());

            if (violations.size() != 3
                    || result.getFieldErrorCount() != 3) {
                throw new AssertionError(
                        "Expected three field violations");
            }
            System.out.println("CHECKS: PASS");
        }
    }
}
```

### 6.3. Running and Reading Stdout

From the directory containing `pom.xml` with JDK 17+, Maven 3.9+:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=example.ConstraintViolationDemo
```

Lines printed by the program, after ignoring auxiliary library logs if any, are expected to be:

```text
customerName | invalid=" " | message=Name must not be blank | template=Name must not be blank
reference | invalid="AB" | message=Code requires at least 4 characters | template=Code requires at least {min} characters
shipping.zip | invalid="12x" | message=Postal code requires 5 digits | template=Postal code requires 5 digits
violationCount=3
springFieldErrors=3
springReference=reference | rejected="AB" | message=Code requires at least 4 characters
CHECKS: PASS
```

Direct observations:
- `customerName` has `@NotBlank`, so `" "` is invalid; the template has no placeholders, so message matches template.
- `reference` has `@Size(min = 4)`, so message replaces `{min}` with `4`, while template keeps `{min}`.
- `shipping.zip` illustrates a nested path thanks to `@Valid` on `shipping`.
- `getInvalidValue()` reflects **the validated Java value**. Here all are `String`, though the API returns `Object`.
- `SpringValidatorAdapter` converts Bean Validation error info into `FieldError`s; `getField()` and `getRejectedValue()` can correspond to path/invalid value, yet **are not** identical APIs to `getPropertyPath()` and `getInvalidValue()` in all contexts.

The messages in the code are written explicitly so results do not depend on an English translation from a default message bundle. In real projects, use multi-locale bundles and test interpolation in request context.

## 7. Relationship Between Jakarta `ConstraintViolation` and Spring `BindingResult`

Spring has two different API sets:

| Jakarta Validation | Spring validation/binding | Remarks |
| --- | --- | --- |
| `ConstraintViolation.getPropertyPath()` | `FieldError.getField()` | Often same property error location meaning, though Spring uses its own field path/error rules |
| `ConstraintViolation.getInvalidValue()` | `FieldError.getRejectedValue()` | May correspond, though Spring can retain raw input or bound value depending on error source |
| `ConstraintViolation.getMessage()` | `ObjectError.getDefaultMessage()` | Usually user-facing message content; can also go through `MessageSource` |
| `ConstraintViolation.getMessageTemplate()` | **No direct corresponding getter** on `FieldError` | Spring uses `MessageSourceResolvable` error codes/arguments |
| `getConstraintDescriptor()` | `ObjectError.getCodes()`, `getArguments()` | Not a 1:1 mapping; Spring builds codes by annotation/field/object |

With Spring MVC, commonly used:

```java
@PostMapping("/orders")
String submit(
        @Valid @ModelAttribute("order") OrderForm order,
        BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return "orders/form";
    }
    return "orders/success";
}
```

This is an **illustrative controller snippet**; it needs `jakarta.validation.Valid`, `org.springframework.web.bind.annotation.PostMapping`, `ModelAttribute`, and `org.springframework.validation.BindingResult`. `BindingResult` must immediately follow the validated model parameter when you want to handle binding/validation errors for that exact argument.

- `@Valid` requests bean validation on the argument when configured; `@Validated` also allows specifying Spring constraint groups.
- When programming manually, calling `DataBinder.bind(...)` only performs binding; to run a validator, set `binder.setValidator(...)` and call `binder.validate()`.
- Spring's `LocalValidatorFactoryBean` and `SpringValidatorAdapter` help connect Jakarta Bean Validation with `org.springframework.validation.Validator`.
- Spring derives error codes (`codes`) by annotation type, object/field/type, and `MessageCodesResolver`; **do not** treat `codes[0]` as `getMessageTemplate()`.
- A `FieldError` from **type conversion** can retain the raw string entered by the user even with no `ConstraintViolation`; when designing error responses, classify sources accurately.

A class-level error usually becomes an `ObjectError` instead of a `FieldError`, because there is no specific field. If a custom class-level validator attaches an explicit property node, Spring may represent it as a field error depending on the adapter and path. Do not force every error into a `FieldError` by guessing a field name.

## 8. Path Determined by a Custom Validator in Class-Level Errors

Suppose `@ValidDateRange` sits on class `BookingRequest`, requiring `end` not to precede `start`. Initially, when `ConstraintValidator<ValidDateRange, BookingRequest>` returns `false` without adding a node, the path is typically the bean path (class level).

Inside `isValid(...)`, you can specify that the error relates to the `end` field via this **excerpt**:

```java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
           "{booking.end.before.start}")
       .addPropertyNode("end")
       .addConstraintViolation();
return false;
```

`context` is `jakarta.validation.ConstraintValidatorContext`. The code assumes the validator can access the object and has determined `end` is invalid. This is an excerpt, **not a standalone Java program**.

When adding node `end`, `getPropertyPath()` can become `end` (or a nested path if this class is a child bean). However, `getInvalidValue()` for a **class-level constraint** can still be **the entire `BookingRequest`**, because the validator applies to the class. This illustrates why you cannot grab `getInvalidValue()` and cast it to `String` based solely on the propertyPath name.

If `messageTemplate = "{booking.end.before.start}"`, the message becomes a human-readable sentence only when a resource bundle/`MessageInterpolator` resolves that key. Without a bundle, the returned content may still be the string containing `{...}`; test localization configuration.

## 9. Safe API Response Design and Logging

Do not send raw `ConstraintViolation` or `FieldError` objects directly to JSON without controlling serialization. In HTTP APIs, usually only this is needed:

```json
{
  "errors": [
    {
      "field": "reference",
      "code": "REFERENCE_TOO_SHORT",
      "message": "Code requires at least 4 characters"
    }
  ]
}
```

This is an **application-defined API contract example**, not a Spring-generated payload. Here:
- `field` is mapped cleanly from path to public name; avoid exposing unnecessary internal paths.
- `code` is a stable application-defined code, independent of locale and wording.
- `message` is the client-safe display message.
- `invalidValue` is excluded by default; values may be sensitive.
- `messageTemplate` can be helpful for internal observability, though it need not be made public; it can expose bundle key names/implementation details.

If error statistics are needed, use the constraint type from `getConstraintDescriptor().getAnnotation().annotationType()`, business code, or category. Do not group by `getMessage()`, because message text changes across locales or translations.

When using nested/container paths, standardize on one public format, such as `items[2].sku` or JSON Pointer `/items/2/sku`, derived from **path nodes**; avoid assuming `Path.toString()` is always a valid JSON Pointer. For class-level errors, you can return `field: null` and an object-level error code.

## 10. Required Testing Matrix

| Scenario | Example | Checking the Four Properties |
| --- | --- | --- |
| Basic field error | `@NotBlank`, blank name | Path is the field; invalid value is the string; message and template may match |
| Attribute interpolation | `@Size(min = 4)` | Message substitutes `{min}`; template keeps the placeholder |
| Resource bundle | `message = "{order.required}"` | Template keeps the key; message is resolved for the configured locale |
| Nested object | `@Valid Address`, bad `zip` | Path has `shipping.zip`, invalid value is the zip |
| Nested object is `null` | `shipping = null` | `@Valid` alone does not report a null error; add `@NotNull` if required |
| Collection element | `List<@NotBlank String>` | Inspect `CONTAINER_ELEMENT`, index/key, and invalid element |
| Class-level constraint | Invalid `start/end` relation | Bean-level or custom-node path; invalid value may be the whole bean |
| Cross-parameter | Constraint on method parameter pair | Path has method/parameter nodes; invalid value may be `Object[]` |
| Numeric binding failure | `Integer` field, input `"abc"` | `BindingResult` has type mismatch but may have no `ConstraintViolation` |
| Bean Validation error after binding | `@Min(1)`, input `"0"` parsed to int | `ConstraintViolation` exists, invalid value is number `0` |
| Unicode/locale | Vietnamese, English, missing bundle | Message matches language, template stays intact; test locale explicitly |
| Result order | Multiple simultaneous violations | Do not assume Set order; sort before printing/asserting if needed |
| Sensitive data | Password/token error | Do not leak invalid value, root/leaf bean, or object `toString()` |
| Group validation | `@Validated(Group.class)` | Only constraints in the matching group are evaluated |

Example check using a unit test:

```java
Set<ConstraintViolation<OrderForm>> errors =
        validator.validate(order);
boolean hasReferenceError = errors.stream().anyMatch(v ->
        v.getPropertyPath().toString().equals("reference")
        && "AB".equals(v.getInvalidValue())
        && v.getMessageTemplate().contains("{min}")
        && v.getMessage().contains("4"));
```

This is an **illustrative Java snippet** inside a test/method where `validator` and `order` exist. For stability, prefer checking a known message template and specific constraint attributes rather than relying too heavily on translated wording.

## 11. Common Pitfalls and How to Handle Them

**1. Comparing `propertyPath` directly against a field name regardless of context.** Paths can be nested, contain indices/keys, or have method/return value nodes. Use `Path.Node` when exact location resolution is needed.

**2. Treating `invalidValue` as always being the raw input String.** Bean Validation runs on the bound object, while Spring conversion can fail before the validator runs. Class-level or cross-parameter constraints have different types; check for null and type before processing.

**3. Calling `toString()` and logging the full invalid value.** Risks exposing passwords, tokens, PII, or internal object stacks. By default log only controlled path/code and correlation ID.

**4. Treating `message` and `messageTemplate` as the same thing.** With `{min}`, template retains the parameter while message holds the interpolated result; with bundle keys, template holds the key name.

**5. Equating Spring `FieldError.getCodes()` with the template.** Error codes are built by Spring for `MessageSource`, whereas the template is Bean Validation metadata prior to interpolation. Do not rely on either to define an API contract without controlling the rules.

**6. Forgetting `@Valid` on a property holding a child object.** Constraints on a child object are not cascaded merely because it exists; `@Valid` triggers cascading. Add `@NotNull` separately if the child object must be present.

**7. Relying on `Set<ConstraintViolation<?>>` order.** The spec does not guarantee order. Sort by path and constraint code when deterministic output or tests are needed.

**8. Mixing `javax.validation.*` with `jakarta.validation.*`.** Spring Framework 6+ branches use the Jakarta ecosystem; Spring Framework 5 typically uses `javax.validation`. Pick version-compatible dependencies and imports instead of migrating halfway.

**9. Confusing validation errors with configuration or binding errors.** A missing provider or misdefined constraint can throw exceptions; unparseable fields create Spring binding errors. Do not turn every exception into a violation with an untrustworthy message.

## 12. Production Readiness Checklist

- [ ] Run Bean Validation on the right bound object and the right validation groups.
- [ ] Inspect `getPropertyPath()` via `Path` when collections, maps, methods, or nested objects are involved.
- [ ] Handle `getInvalidValue()` as `Object`, null-safe, with a data protection policy.
- [ ] Understand `getMessage()` is **interpolated**, while `getMessageTemplate()` is **uninterpolated**.
- [ ] Test resource bundles, locales, placeholders, and missing translation fallbacks.
- [ ] Separate `ConstraintViolation` from Spring `BindingResult`/`FieldError`; also test type conversion errors.
- [ ] Use stable application-managed API error codes rather than depending on message text.
- [ ] Sort violations before logging/asserting when deterministic ordering is needed.
- [ ] Verify policies for class-level, nested, and container-element constraints.

## Official Documentation

- Jakarta Validation API 3.0 — `ConstraintViolation<T>`: https://javadoc.io/static/jakarta.validation/jakarta.validation-api/3.0.0/jakarta/validation/ConstraintViolation.html
- Jakarta Bean Validation 3.0 specification, ConstraintViolation and message interpolation sections: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Validation API 3.0 — `Path`: https://javadoc.io/static/jakarta.validation/jakarta.validation-api/3.0.0/jakarta/validation/Path.html
- Spring Framework 6.2 — Validation: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — `SpringValidatorAdapter`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/beanvalidation/SpringValidatorAdapter.html
- Spring Framework 6.2 — `BindingResult`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/validation/BindingResult.html
- Hibernate Validator 8 — Reference Guide: https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/
